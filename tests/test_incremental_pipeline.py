"""Tests for the incremental enrichment pipeline.

Covers:
- IncrementalBrainManager: save/load feature artifacts, status checkpoint,
  aggregate(), directory layout.
- split_prd_into_features: PRD section detection.
- IncrementalEnricher with NullAdapter: enrich_feature, resume, enrich_phase.
- Incremental MCP tools: get_enrichment_status, get_feature_artifacts, aggregate_brain_cache.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from project_brain.brain.incremental_manager import IncrementalBrainManager
from project_brain.brain.schema import (
    BusinessRule,
    DataField,
    DataModel,
    DesignSystem,
    EnrichmentSession,
    FeatureArtifacts,
    FeatureEnrichmentStatus,
    Meta,
    Repository,
    RepositoryMethod,
    Screen,
    StateField,
    StateMachine,
    StateTransition,
    ViewModel,
    ViewModelFunction,
)
from project_brain.generators.incremental_enricher import (
    IncrementalEnricher,
    _audit_artifacts,
    _null_artifacts_json,
    _parse_artifacts,
    split_prd_into_features,
)
from project_brain.llm.adapter import NullAdapter
from project_brain.tools.incremental_tools import (
    aggregate_brain_cache,
    get_enrichment_status,
    get_feature_artifacts,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _sample_artifacts(feature_id: str = "auth", name: str = "Authentication") -> FeatureArtifacts:
    return FeatureArtifacts(
        feature_id=feature_id,
        feature_name=name,
        screens=[
            Screen(id=f"{feature_id}_screen", route=f"{feature_id}/login", phase=1, viewmodel=f"{feature_id.title()}ViewModel")
        ],
        viewmodels=[
            ViewModel(
                id=f"{feature_id}_vm",
                screen=f"{feature_id}_screen",
                functions=[ViewModelFunction(name="signIn", params=["email: String", "password: String"])],
                state_fields=[StateField(name="isLoading", type="Boolean", default="false")],
            )
        ],
        repositories=[
            Repository(
                id=f"{feature_id}_repo",
                interface=f"{feature_id.title()}Repository",
                implementation=f"{feature_id.title()}RepositoryImpl",
                methods=[RepositoryMethod(name="signIn", params=["email: String"], result_wrapped=True)],
            )
        ],
        business_rules=[
            BusinessRule(id="BR-001", description="User must be authenticated", enforcement="ViewModel")
        ],
        state_machines=[
            StateMachine(
                entity="User",
                states=["ANONYMOUS", "AUTHENTICATED"],
                transitions=[
                    StateTransition(**{"from": "ANONYMOUS", "to": "AUTHENTICATED", "required_firestore_updates": ["users/{uid}.status = active"]})
                ],
            )
        ],
        use_cases=["SignInUseCase"],
        data_models=[DataModel(id="user_model", fields=[DataField(name="uid", type="String")], firestore_collection="users")],
        audit_passed=True,
    )


# ── Manager tests ──────────────────────────────────────────────────────────────

class TestIncrementalBrainManager(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.mgr = IncrementalBrainManager(Path(self.tmp) / "brain")

    def test_init_dirs_creates_structure(self) -> None:
        self.mgr.init_dirs()
        for subdir in ["features", "roadmap", "graphs", "generation", "cache"]:
            self.assertTrue((self.mgr.brain_dir / subdir).is_dir(), subdir)

    def test_save_and_load_feature_roundtrip(self) -> None:
        arts = _sample_artifacts()
        self.mgr.save_feature(arts)

        loaded = self.mgr.load_feature("auth")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.feature_id, "auth")
        self.assertEqual(loaded.feature_name, "Authentication")
        self.assertEqual(len(loaded.screens), 1)
        self.assertEqual(loaded.screens[0].id, "auth_screen")
        self.assertEqual(len(loaded.viewmodels), 1)
        self.assertEqual(loaded.viewmodels[0].functions[0].name, "signIn")
        self.assertEqual(len(loaded.repositories), 1)
        self.assertEqual(len(loaded.business_rules), 1)
        self.assertEqual(len(loaded.state_machines), 1)
        self.assertEqual(loaded.use_cases, ["SignInUseCase"])
        self.assertEqual(len(loaded.data_models), 1)

    def test_load_feature_returns_none_for_missing(self) -> None:
        self.assertIsNone(self.mgr.load_feature("nonexistent"))

    def test_list_features_empty(self) -> None:
        self.assertEqual(self.mgr.list_features(), [])

    def test_list_features_populated(self) -> None:
        self.mgr.save_feature(_sample_artifacts("auth"))
        self.mgr.save_feature(_sample_artifacts("profile", "Profile"))
        features = self.mgr.list_features()
        self.assertIn("auth", features)
        self.assertIn("profile", features)

    def test_save_and_load_status(self) -> None:
        session = self.mgr.new_session(prd_path="./prd.md", feature_ids=["auth", "profile"])
        session.mark_complete("auth")
        self.mgr.save_status(session)

        loaded = self.mgr.load_status()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.prd_path, "./prd.md")
        self.assertIn("auth", loaded.completed_features)
        self.assertIn("profile", loaded.pending_features)
        self.assertEqual(loaded.last_checkpoint, "auth")

    def test_load_status_returns_none_when_absent(self) -> None:
        self.assertIsNone(self.mgr.load_status())

    def test_save_project_meta_and_reload(self) -> None:
        meta = Meta(project_name="TestApp", entry_point="prd")
        ds = DesignSystem(primary_color="#FF0000")
        self.mgr.save_project_meta(meta, ds)

        result = self.mgr.load_project_meta()
        self.assertIsNotNone(result)
        loaded_meta, loaded_ds, _ = result
        self.assertEqual(loaded_meta.project_name, "TestApp")
        self.assertEqual(loaded_ds.primary_color, "#FF0000")

    def test_aggregate_produces_brain(self) -> None:
        meta = Meta(project_name="AggTest", entry_point="prd")
        self.mgr.save_project_meta(meta)
        self.mgr.save_feature(_sample_artifacts("auth"))
        self.mgr.save_feature(_sample_artifacts("profile", "Profile"))

        brain = self.mgr.aggregate()
        self.assertEqual(brain.meta.project_name, "AggTest")
        self.assertEqual(len(brain.screens), 2)
        self.assertEqual(len(brain.viewmodels), 2)
        self.assertEqual(len(brain.repositories), 2)
        self.assertTrue(self.mgr.aggregated_brain_path.exists())

    def test_aggregate_cache_file_is_valid_json(self) -> None:
        self.mgr.save_feature(_sample_artifacts("auth"))
        self.mgr.aggregate()
        raw = self.mgr.aggregated_brain_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        self.assertIn("meta", data)
        self.assertIn("screens", data)

    def test_new_session_populates_pending(self) -> None:
        session = self.mgr.new_session(feature_ids=["auth", "booking"])
        self.assertEqual(sorted(session.pending_features), ["auth", "booking"])
        self.assertEqual(len(session.features), 2)

    def test_mark_failed_moves_to_failed_list(self) -> None:
        session = self.mgr.new_session(feature_ids=["auth"])
        session.features.append(FeatureEnrichmentStatus(feature_id="auth"))
        session.mark_failed("auth", "LLM timeout")
        self.assertIn("auth", session.failed_features)
        status = session.feature_status("auth")
        self.assertEqual(status.status, "failed")
        self.assertEqual(status.error, "LLM timeout")


# ── PRD splitter tests ─────────────────────────────────────────────────────────

class TestSplitPrdIntoFeatures(unittest.TestCase):
    def test_splits_on_feature_headings(self) -> None:
        prd = (
            "# My App\n\n"
            "## Feature: Authentication\nSign in with email.\n\n"
            "## Feature: Profile\nUser profile management.\n\n"
            "## Feature: Booking\nBook services.\n"
        )
        sections = split_prd_into_features(prd)
        ids = [s["id"] for s in sections]
        self.assertIn("authentication", ids)
        self.assertIn("profile", ids)
        self.assertIn("booking", ids)

    def test_splits_on_features_subsection(self) -> None:
        prd = (
            "# App\n\n"
            "## Features\n\n"
            "### Auth\nLogin flow.\n\n"
            "### Payments\nPayment flow.\n"
        )
        sections = split_prd_into_features(prd)
        ids = [s["id"] for s in sections]
        self.assertIn("auth", ids)
        self.assertIn("payments", ids)

    def test_falls_back_to_main_for_flat_prd(self) -> None:
        sections = split_prd_into_features("No headings here")
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["id"], "main")

    def test_section_text_contains_feature_content(self) -> None:
        prd = (
            "# App\n\n"
            "## Authentication\nEmail OTP login.\n\n"
            "## Profile\nUser settings.\n"
        )
        sections = split_prd_into_features(prd)
        auth = next(s for s in sections if "auth" in s["id"])
        self.assertIn("Email OTP", auth["text"])

    def test_skips_architecture_headings(self) -> None:
        prd = (
            "# App\n\n"
            "## Overview\nIntro.\n\n"
            "## Tech Stack\nKotlin.\n\n"
            "## Authentication\nLogin flow.\n"
        )
        sections = split_prd_into_features(prd)
        ids = [s["id"] for s in sections]
        self.assertNotIn("overview", ids)
        self.assertNotIn("tech_stack", ids)
        self.assertIn("authentication", ids)

    def test_numbered_feature_headings(self) -> None:
        prd = (
            "# App\n\n"
            "## Features\n\n"
            "### 1. Authentication\nLogin.\n\n"
            "### 2. Booking\nBook.\n"
        )
        sections = split_prd_into_features(prd)
        names = [s["name"] for s in sections]
        self.assertIn("Authentication", names)
        self.assertIn("Booking", names)


# ── Artifact parsing tests ─────────────────────────────────────────────────────

class TestParseArtifacts(unittest.TestCase):
    def test_parse_valid_json(self) -> None:
        raw = json.dumps({
            "screens": [{"id": "login_screen", "route": "auth/login", "phase": 1}],
            "viewmodels": [{"id": "login_vm", "screen": "login_screen", "functions": [{"name": "signIn", "params": []}]}],
            "repositories": [],
            "business_rules": [],
            "state_machines": [],
            "use_cases": ["SignInUseCase"],
            "data_models": [],
        })
        arts = _parse_artifacts("auth", "Authentication", raw)
        self.assertEqual(arts.feature_id, "auth")
        self.assertEqual(len(arts.screens), 1)
        self.assertEqual(arts.screens[0].id, "login_screen")
        self.assertEqual(arts.use_cases, ["SignInUseCase"])

    def test_parse_strips_markdown_fences(self) -> None:
        raw = "```json\n" + json.dumps({"screens": [], "viewmodels": [], "repositories": [], "business_rules": [], "state_machines": [], "use_cases": [], "data_models": []}) + "\n```"
        arts = _parse_artifacts("auth", "Auth", raw)
        self.assertEqual(arts.feature_id, "auth")

    def test_parse_handles_prose_before_json(self) -> None:
        raw = "Here are the artifacts:\n" + json.dumps({"screens": [], "viewmodels": [], "repositories": [], "business_rules": [], "state_machines": [], "use_cases": [], "data_models": []})
        arts = _parse_artifacts("auth", "Auth", raw)
        self.assertEqual(arts.feature_id, "auth")

    def test_parse_raises_on_invalid_json(self) -> None:
        with self.assertRaises(Exception):
            _parse_artifacts("auth", "Auth", "not json at all")

    def test_audit_passes_with_valid_artifacts(self) -> None:
        arts = _sample_artifacts()
        self.assertTrue(_audit_artifacts(arts))

    def test_audit_fails_with_no_screens_or_vms(self) -> None:
        arts = FeatureArtifacts(feature_id="empty", feature_name="Empty")
        self.assertFalse(_audit_artifacts(arts))


# ── IncrementalEnricher + NullAdapter tests ────────────────────────────────────

class TestIncrementalEnricher(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.brain_dir = Path(self.tmp) / "brain"
        self.prd_path = Path(self.tmp) / "test_prd.md"
        self.prd_path.write_text(
            "# Test App\n\n"
            "## Authentication\nEmail login with OTP.\n\n"
            "## Profile\nUser profile management.\n",
            encoding="utf-8",
        )

    async def test_enrich_feature_creates_artifacts(self) -> None:
        enricher = IncrementalEnricher(llm=NullAdapter(), brain_dir=self.brain_dir)
        artifacts = await enricher.enrich_feature("authentication", self.prd_path)
        self.assertIsNotNone(artifacts)
        self.assertEqual(artifacts.feature_id, "authentication")
        self.assertTrue((self.brain_dir / "features" / "authentication" / "screens.json").exists())

    async def test_enrich_feature_saves_status_checkpoint(self) -> None:
        enricher = IncrementalEnricher(llm=NullAdapter(), brain_dir=self.brain_dir)
        await enricher.enrich_feature("authentication", self.prd_path)
        session = enricher.manager.load_status()
        self.assertIsNotNone(session)
        self.assertIn("authentication", session.completed_features)

    async def test_enrich_feature_raises_for_missing_feature(self) -> None:
        enricher = IncrementalEnricher(llm=NullAdapter(), brain_dir=self.brain_dir)
        with self.assertRaises(ValueError):
            await enricher.enrich_feature("nonexistent_xyz", self.prd_path)

    async def test_enrich_all_processes_all_features(self) -> None:
        enricher = IncrementalEnricher(llm=NullAdapter(), brain_dir=self.brain_dir)
        result = await enricher.enrich_all(self.prd_path)
        self.assertTrue(len(result.completed) >= 1)
        self.assertEqual(len(result.failed), 0)

    async def test_enrich_all_creates_aggregated_cache(self) -> None:
        enricher = IncrementalEnricher(llm=NullAdapter(), brain_dir=self.brain_dir)
        await enricher.enrich_all(self.prd_path)
        self.assertTrue((self.brain_dir / "cache" / "aggregated_brain.json").exists())

    async def test_resume_skips_completed_features(self) -> None:
        enricher = IncrementalEnricher(llm=NullAdapter(), brain_dir=self.brain_dir)
        # First enrich authentication
        await enricher.enrich_feature("authentication", self.prd_path)
        # Save a session that marks authentication complete and profile as pending
        session = enricher.manager.load_status()
        session.pending_features = ["profile"]
        session.features.append(FeatureEnrichmentStatus(feature_id="profile"))
        enricher.manager.save_status(session)

        # Resume should skip authentication
        result = await enricher.resume(self.prd_path)
        self.assertNotIn("authentication", result.completed)
        self.assertIn("authentication", result.skipped)

    async def test_resume_raises_when_no_session(self) -> None:
        enricher = IncrementalEnricher(llm=NullAdapter(), brain_dir=self.brain_dir)
        with self.assertRaises(RuntimeError):
            await enricher.resume(self.prd_path)

    async def test_enrich_phase_with_name_match(self) -> None:
        enricher = IncrementalEnricher(llm=NullAdapter(), brain_dir=self.brain_dir)
        result = await enricher.enrich_phase("auth", self.prd_path)
        self.assertEqual(len(result.failed), 0)

    async def test_null_adapter_produces_stub_artifacts(self) -> None:
        raw = _null_artifacts_json("auth", "Authentication")
        arts = _parse_artifacts("auth", "Authentication", raw)
        self.assertEqual(arts.feature_id, "auth")
        self.assertTrue(len(arts.screens) > 0)


# ── MCP incremental tools tests ───────────────────────────────────────────────

class TestIncrementalMCPTools(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.brain_dir = str(Path(self.tmp) / "brain")

    def test_get_enrichment_status_no_session(self) -> None:
        result = get_enrichment_status(self.brain_dir)
        self.assertEqual(result["status"], "no_session")

    def test_get_enrichment_status_with_session(self) -> None:
        mgr = IncrementalBrainManager(self.brain_dir)
        session = mgr.new_session(prd_path="./prd.md", feature_ids=["auth", "profile"])
        session.mark_complete("auth")
        mgr.save_status(session)

        result = get_enrichment_status(self.brain_dir)
        self.assertIn("auth", result["completed"])
        self.assertIn("profile", result["pending"])
        self.assertTrue(result["can_resume"])

    def test_get_feature_artifacts_not_found(self) -> None:
        result = get_feature_artifacts("missing_feature", self.brain_dir)
        self.assertIn("error", result)
        self.assertIn("available_features", result)

    def test_get_feature_artifacts_returns_summary(self) -> None:
        mgr = IncrementalBrainManager(self.brain_dir)
        mgr.save_feature(_sample_artifacts("auth"))

        result = get_feature_artifacts("auth", self.brain_dir)
        self.assertEqual(result["feature_id"], "auth")
        self.assertEqual(result["feature_name"], "Authentication")
        self.assertEqual(len(result["screens"]), 1)
        self.assertEqual(len(result["viewmodels"]), 1)
        self.assertEqual(len(result["repositories"]), 1)
        self.assertEqual(result["business_rules"][0]["id"], "BR-001")

    def test_aggregate_brain_cache_no_features(self) -> None:
        result = aggregate_brain_cache(self.brain_dir)
        self.assertIn("error", result)

    def test_aggregate_brain_cache_produces_file(self) -> None:
        mgr = IncrementalBrainManager(self.brain_dir)
        mgr.save_feature(_sample_artifacts("auth"))
        mgr.save_feature(_sample_artifacts("profile", "Profile"))

        result = aggregate_brain_cache(self.brain_dir)
        self.assertIn("aggregated_brain_path", result)
        self.assertIn("auth", result["features_merged"])
        self.assertIn("profile", result["features_merged"])
        self.assertEqual(result["screens"], 2)
        self.assertTrue(Path(result["aggregated_brain_path"]).exists())


if __name__ == "__main__":
    unittest.main()
