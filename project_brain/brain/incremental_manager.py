"""Incremental brain persistence layer.

Manages the brain/ directory structure so enrichment can be paused and
resumed feature by feature without losing prior work.

Layout
------
brain/
  project.json                       ← meta + design_system + user_roles
  features/
    <feature_id>/
      feature.json                   ← id, name
      screens.json
      viewmodels.json
      repositories.json
      business_rules.json
      state_machines.json
      usecases.json
      data_models.json
  roadmap/
    roadmap.json
    phases.json
  graphs/
    navigation_graph.json
    dependency_graph.json
  generation/
    status.json                      ← EnrichmentSession checkpoint
    history.json
    sessions.json
  cache/
    aggregated_brain.json            ← derived; never the primary source
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from project_brain.brain.schema import (
    BusinessRule,
    DataModel,
    DesignSystem,
    EnrichmentSession,
    Feature,
    FeatureArtifacts,
    FeatureEnrichmentStatus,
    FirestoreSchema,
    Meta,
    NavigationGraph,
    Phase,
    ProjectBrain,
    Repository,
    Screen,
    StateMachine,
    UserRole,
    ViewModel,
    utc_now,
)


def _atomic_json(path: Path, data: Any) -> None:
    """Write *data* to *path* atomically via a temp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=str(path.parent),
            suffix=".tmp",
        ) as fh:
            temp_name = fh.name
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(temp_name, path)
    finally:
        if temp_name and Path(temp_name).exists():
            Path(temp_name).unlink()


class IncrementalBrainManager:
    """Manages the brain/ directory structure for incremental feature enrichment."""

    def __init__(self, brain_dir: Path | str = "brain") -> None:
        self.brain_dir = Path(brain_dir)
        self.features_dir = self.brain_dir / "features"
        self.roadmap_dir = self.brain_dir / "roadmap"
        self.graphs_dir = self.brain_dir / "graphs"
        self.generation_dir = self.brain_dir / "generation"
        self.cache_dir = self.brain_dir / "cache"

    # ── Directory bootstrap ────────────────────────────────────────────────

    def init_dirs(self) -> None:
        for d in [
            self.features_dir,
            self.roadmap_dir,
            self.graphs_dir,
            self.generation_dir,
            self.cache_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def feature_dir(self, feature_id: str) -> Path:
        return self.features_dir / feature_id

    # ── Project-level metadata ─────────────────────────────────────────────

    def save_project_meta(
        self,
        meta: Meta,
        design_system: DesignSystem | None = None,
        user_roles: list[UserRole] | None = None,
    ) -> None:
        self.brain_dir.mkdir(parents=True, exist_ok=True)
        _atomic_json(
            self.brain_dir / "project.json",
            {
                "meta": meta.model_dump(by_alias=True, mode="json"),
                "design_system": (design_system or DesignSystem()).model_dump(
                    by_alias=True, mode="json"
                ),
                "user_roles": [
                    r.model_dump(by_alias=True, mode="json")
                    for r in (user_roles or [])
                ],
            },
        )

    def load_project_meta(
        self,
    ) -> tuple[Meta, DesignSystem, list[UserRole]] | None:
        path = self.brain_dir / "project.json"
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        meta = Meta.model_validate(raw["meta"])
        ds = DesignSystem.model_validate(raw.get("design_system", {}))
        roles = [UserRole.model_validate(r) for r in raw.get("user_roles", [])]
        return meta, ds, roles

    # ── Feature artifact persistence ───────────────────────────────────────

    def save_feature(self, artifacts: FeatureArtifacts) -> None:
        """Atomically write all artifact files for one feature."""
        fdir = self.feature_dir(artifacts.feature_id)
        fdir.mkdir(parents=True, exist_ok=True)

        _atomic_json(
            fdir / "feature.json",
            {"id": artifacts.feature_id, "name": artifacts.feature_name},
        )
        _atomic_json(
            fdir / "screens.json",
            [s.model_dump(by_alias=True, mode="json") for s in artifacts.screens],
        )
        _atomic_json(
            fdir / "viewmodels.json",
            [v.model_dump(by_alias=True, mode="json") for v in artifacts.viewmodels],
        )
        _atomic_json(
            fdir / "repositories.json",
            [r.model_dump(by_alias=True, mode="json") for r in artifacts.repositories],
        )
        _atomic_json(
            fdir / "business_rules.json",
            [r.model_dump(by_alias=True, mode="json") for r in artifacts.business_rules],
        )
        _atomic_json(
            fdir / "state_machines.json",
            [m.model_dump(by_alias=True, mode="json") for m in artifacts.state_machines],
        )
        _atomic_json(fdir / "usecases.json", artifacts.use_cases)
        _atomic_json(
            fdir / "data_models.json",
            [d.model_dump(by_alias=True, mode="json") for d in artifacts.data_models],
        )

    def load_feature(self, feature_id: str) -> FeatureArtifacts | None:
        fdir = self.feature_dir(feature_id)
        if not fdir.exists():
            return None

        def _load(name: str) -> Any:
            p = fdir / name
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

        meta = _load("feature.json")
        if isinstance(meta, list):
            meta = {}
        return FeatureArtifacts(
            feature_id=feature_id,
            feature_name=meta.get("name", feature_id),
            screens=[Screen.model_validate(s) for s in _load("screens.json")],
            viewmodels=[
                ViewModel.model_validate(v) for v in _load("viewmodels.json")
            ],
            repositories=[
                Repository.model_validate(r) for r in _load("repositories.json")
            ],
            business_rules=[
                BusinessRule.model_validate(r) for r in _load("business_rules.json")
            ],
            state_machines=[
                StateMachine.model_validate(m) for m in _load("state_machines.json")
            ],
            use_cases=_load("usecases.json"),
            data_models=[
                DataModel.model_validate(d) for d in _load("data_models.json")
            ],
        )

    def list_features(self) -> list[str]:
        if not self.features_dir.exists():
            return []
        return sorted(d.name for d in self.features_dir.iterdir() if d.is_dir())

    # ── Session / checkpoint ───────────────────────────────────────────────

    def save_status(self, session: EnrichmentSession) -> None:
        self.generation_dir.mkdir(parents=True, exist_ok=True)
        _atomic_json(
            self.generation_dir / "status.json",
            session.model_dump(by_alias=True, mode="json"),
        )

    def load_status(self) -> EnrichmentSession | None:
        path = self.generation_dir / "status.json"
        if not path.exists():
            return None
        return EnrichmentSession.model_validate_json(path.read_text(encoding="utf-8"))

    def new_session(
        self,
        prd_path: str | None = None,
        feature_ids: list[str] | None = None,
    ) -> EnrichmentSession:
        return EnrichmentSession(
            session_id=str(uuid.uuid4())[:8],
            prd_path=prd_path,
            pending_features=list(feature_ids or []),
            features=[
                FeatureEnrichmentStatus(feature_id=fid)
                for fid in (feature_ids or [])
            ],
        )

    def append_session_history(self, session: EnrichmentSession) -> None:
        self.generation_dir.mkdir(parents=True, exist_ok=True)
        path = self.generation_dir / "sessions.json"
        history: list[dict] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        )
        history.append(session.model_dump(by_alias=True, mode="json"))
        _atomic_json(path, history)

    # ── Roadmap / graph persistence ────────────────────────────────────────

    def save_roadmap(self, phases: list[Phase]) -> None:
        self.roadmap_dir.mkdir(parents=True, exist_ok=True)
        _atomic_json(
            self.roadmap_dir / "phases.json",
            [p.model_dump(by_alias=True, mode="json") for p in phases],
        )

    def save_navigation_graph(self, graph: NavigationGraph) -> None:
        self.graphs_dir.mkdir(parents=True, exist_ok=True)
        _atomic_json(
            self.graphs_dir / "navigation_graph.json",
            graph.model_dump(by_alias=True, mode="json"),
        )

    # ── Cache aggregation ──────────────────────────────────────────────────

    def aggregate(self) -> ProjectBrain:
        """Build a full ProjectBrain by merging all feature artifact files.

        The result is written to cache/aggregated_brain.json and also returned.
        This is a derived view — the per-feature JSON files are the source of truth.
        """
        project_meta = self.load_project_meta()
        if project_meta:
            meta, design_system, user_roles = project_meta
        else:
            meta = Meta(project_name="Unknown", entry_point="prd")
            design_system = DesignSystem()
            user_roles = []

        all_screens: list[Screen] = []
        all_vms: list[ViewModel] = []
        all_repos: list[Repository] = []
        all_rules: list[BusinessRule] = []
        all_machines: list[StateMachine] = []
        all_models: list[DataModel] = []
        all_features: list[Feature] = []

        seen_ids: set[str] = set()

        for fid in self.list_features():
            arts = self.load_feature(fid)
            if not arts:
                continue
            all_features.append(
                Feature(
                    id=fid,
                    name=arts.feature_name,
                    screens=[s.id for s in arts.screens],
                    status="complete" if arts.audit_passed else "in_progress",
                )
            )
            for s in arts.screens:
                if s.id not in seen_ids:
                    all_screens.append(s)
                    seen_ids.add(s.id)
            for v in arts.viewmodels:
                if v.id not in seen_ids:
                    all_vms.append(v)
                    seen_ids.add(v.id)
            for r in arts.repositories:
                if r.id not in seen_ids:
                    all_repos.append(r)
                    seen_ids.add(r.id)
            for rule in arts.business_rules:
                if rule.id not in seen_ids:
                    all_rules.append(rule)
                    seen_ids.add(rule.id)
            for m in arts.state_machines:
                if m.entity not in seen_ids:
                    all_machines.append(m)
                    seen_ids.add(m.entity)
            for d in arts.data_models:
                if d.id not in seen_ids:
                    all_models.append(d)
                    seen_ids.add(d.id)

        brain = ProjectBrain(
            meta=meta,
            design_system=design_system,
            user_roles=user_roles,
            screens=all_screens,
            viewmodels=all_vms,
            repositories=all_repos,
            business_rules=all_rules,
            state_machines=all_machines,
            data_models=all_models,
            features=all_features,
        )

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        _atomic_json(
            self.cache_dir / "aggregated_brain.json",
            brain.model_dump(by_alias=True, mode="json"),
        )

        # Write ROADMAP.md at brain/ root (not inside cache/)
        try:
            from project_brain.generators.roadmap_generator import RoadmapGenerator
            RoadmapGenerator().write(brain, self.brain_dir / "ROADMAP.md")
        except Exception:
            pass  # roadmap is best-effort; never block aggregation

        return brain

    @property
    def aggregated_brain_path(self) -> Path:
        return self.cache_dir / "aggregated_brain.json"
