"""Regression tests for the 3 minor compatibility fixes.

Fix 1 — brain_path threading: ToolRegistry / create_registry accept brain_path
         and thread it to GenerationTools → GenerationOrchestrator so that
         write_result() saves back to the correct file (not always "PROJECT_BRAIN.json").

Fix 2 — RoadmapGenerator in aggregate(): IncrementalBrainManager.aggregate()
         writes brain/ROADMAP.md at the brain/ root, not inside cache/.

Fix 3 — BRAIN_DIR env-var: incremental MCP tools resolve brain_dir from the
         BRAIN_DIR environment variable when no explicit argument is given.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from project_brain.brain.incremental_manager import IncrementalBrainManager
from project_brain.brain.schema import DesignSystem, Meta
from project_brain.generators.prd_parser import PRDParser
from project_brain.llm.adapter import NullAdapter
from project_brain.tools.incremental_tools import (
    aggregate_brain_cache,
    get_enrichment_status,
    get_feature_artifacts,
)
from project_brain.tools.registry import ToolRegistry, create_registry

from tests.test_incremental_pipeline import _sample_artifacts


# ── Fix 1: brain_path threading ───────────────────────────────────────────────

class TestBrainPathThreading(unittest.TestCase):
    def _make_brain(self):
        return PRDParser().parse_file(Path("tests/fixtures/sample_prd.md"))

    def test_tool_registry_accepts_brain_path(self) -> None:
        brain = self._make_brain()
        registry = ToolRegistry(brain, brain_path="/custom/path/BRAIN.json")
        self.assertEqual(
            registry.generation_tools._orchestrator.brain_path,
            Path("/custom/path/BRAIN.json"),
        )

    def test_tool_registry_defaults_to_project_brain_json(self) -> None:
        brain = self._make_brain()
        registry = ToolRegistry(brain)
        self.assertEqual(
            registry.generation_tools._orchestrator.brain_path,
            Path("PROJECT_BRAIN.json"),
        )

    def test_create_registry_accepts_brain_path(self) -> None:
        brain = self._make_brain()
        registry = create_registry(brain, llm=NullAdapter(), brain_path="/alt/BRAIN.json")
        self.assertEqual(
            registry.generation_tools._orchestrator.brain_path,
            Path("/alt/BRAIN.json"),
        )

    def test_create_registry_default_path(self) -> None:
        brain = self._make_brain()
        registry = create_registry(brain, llm=NullAdapter())
        self.assertEqual(
            registry.generation_tools._orchestrator.brain_path,
            Path("PROJECT_BRAIN.json"),
        )

    def test_aggregated_brain_path_threads_correctly(self) -> None:
        """Simulate the server loading aggregated_brain.json and threading its path."""
        tmp = tempfile.mkdtemp()
        aggregated = Path(tmp) / "brain" / "cache" / "aggregated_brain.json"
        brain = self._make_brain()
        registry = create_registry(brain, llm=NullAdapter(), brain_path=str(aggregated))
        self.assertEqual(
            registry.generation_tools._orchestrator.brain_path,
            aggregated,
        )


# ── Fix 2: ROADMAP.md at brain/ root ──────────────────────────────────────────

class TestRoadmapInAggregate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.brain_dir = Path(self.tmp) / "brain"

    def test_aggregate_writes_roadmap_at_brain_root(self) -> None:
        mgr = IncrementalBrainManager(self.brain_dir)
        meta = Meta(project_name="RoadmapTest", entry_point="prd")
        mgr.save_project_meta(meta)
        mgr.save_feature(_sample_artifacts("auth"))

        mgr.aggregate()

        roadmap = self.brain_dir / "ROADMAP.md"
        self.assertTrue(roadmap.exists(), "ROADMAP.md should be at brain/ root")

    def test_roadmap_not_written_inside_cache(self) -> None:
        mgr = IncrementalBrainManager(self.brain_dir)
        meta = Meta(project_name="RoadmapTest", entry_point="prd")
        mgr.save_project_meta(meta)
        mgr.save_feature(_sample_artifacts("auth"))

        mgr.aggregate()

        wrong_path = self.brain_dir / "cache" / "ROADMAP.md"
        self.assertFalse(wrong_path.exists(), "ROADMAP.md must NOT be inside cache/")

    def test_roadmap_contains_project_name(self) -> None:
        mgr = IncrementalBrainManager(self.brain_dir)
        meta = Meta(project_name="MyAwesomeApp", entry_point="prd")
        mgr.save_project_meta(meta)
        mgr.save_feature(_sample_artifacts("auth"))

        mgr.aggregate()

        content = (self.brain_dir / "ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("MyAwesomeApp", content)

    def test_aggregate_succeeds_even_when_roadmap_write_fails(self) -> None:
        """aggregate() must not raise if RoadmapGenerator encounters an error."""
        mgr = IncrementalBrainManager(self.brain_dir)
        mgr.save_feature(_sample_artifacts("auth"))

        # aggregated_brain.json should still be written even if roadmap fails
        brain = mgr.aggregate()
        self.assertIsNotNone(brain)
        self.assertTrue(mgr.aggregated_brain_path.exists())


# ── Fix 3: BRAIN_DIR env-var support ──────────────────────────────────────────

class TestBrainDirEnvVar(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.custom_brain_dir = str(Path(self.tmp) / "custom_brain")

    def test_get_enrichment_status_uses_brain_dir_env(self) -> None:
        with patch.dict(os.environ, {"BRAIN_DIR": self.custom_brain_dir}):
            result = get_enrichment_status()  # no explicit brain_dir
        # Should return no_session (custom dir is empty) without error
        self.assertEqual(result["status"], "no_session")

    def test_get_feature_artifacts_uses_brain_dir_env(self) -> None:
        mgr = IncrementalBrainManager(self.custom_brain_dir)
        mgr.save_feature(_sample_artifacts("auth"))

        with patch.dict(os.environ, {"BRAIN_DIR": self.custom_brain_dir}):
            result = get_feature_artifacts("auth")  # no explicit brain_dir

        self.assertEqual(result["feature_id"], "auth")

    def test_aggregate_brain_cache_uses_brain_dir_env(self) -> None:
        mgr = IncrementalBrainManager(self.custom_brain_dir)
        mgr.save_feature(_sample_artifacts("auth"))

        with patch.dict(os.environ, {"BRAIN_DIR": self.custom_brain_dir}):
            result = aggregate_brain_cache()  # no explicit brain_dir

        self.assertIn("aggregated_brain_path", result)
        self.assertIn("auth", result["features_merged"])

    def test_explicit_brain_dir_overrides_env(self) -> None:
        other_dir = str(Path(self.tmp) / "other_brain")
        mgr = IncrementalBrainManager(other_dir)
        mgr.save_feature(_sample_artifacts("profile", "Profile"))

        with patch.dict(os.environ, {"BRAIN_DIR": self.custom_brain_dir}):
            # Explicit arg wins over env var
            result = get_feature_artifacts("profile", brain_dir=other_dir)

        self.assertEqual(result["feature_id"], "profile")

    def test_fallback_to_brain_when_env_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("BRAIN_DIR", None)
            result = get_enrichment_status()  # should resolve to "brain"
        # "brain" dir doesn't exist in test CWD → no_session
        self.assertEqual(result["status"], "no_session")


if __name__ == "__main__":
    unittest.main()
