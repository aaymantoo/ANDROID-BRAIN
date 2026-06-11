"""Incremental PRD enrichment — processes one feature at a time.

This module replaces the monolithic PRDEnricher for large PRDs.  After every
successfully extracted feature the artifacts are written to disk so that a
crash or timeout cannot erase prior work.  The `brain resume` command reads
the checkpoint and continues from where it stopped.

CLI entry points (added to commands.py):
    brain enrich-feature <feature_id>  --prd <file> [--brain-dir <dir>]
    brain enrich-phase   <phase_name>  --prd <file> [--brain-dir <dir>]
    brain resume                       --prd <file> [--brain-dir <dir>]

Algorithm
---------
1. Parse PRD → list of (feature_id, feature_name, feature_section_text) tuples.
2. Load or create EnrichmentSession in brain/generation/status.json.
3. For each pending feature (skipping already-completed ones):
   a. Mark feature as "enriching" and save checkpoint.
   b. Call LLM to extract FeatureArtifacts JSON from the feature section.
   c. Parse JSON → FeatureArtifacts (retry up to 2 times on parse error).
   d. Run lightweight audit (field-level validation).
   e. Save artifacts atomically to brain/features/{id}/*.json.
   f. Mark feature as "complete" and save checkpoint.
4. After all features: aggregate → brain/cache/aggregated_brain.json.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from project_brain.brain.incremental_manager import IncrementalBrainManager
from project_brain.brain.schema import (
    BusinessRule,
    DataField,
    DataModel,
    EnrichmentSession,
    FeatureArtifacts,
    FeatureEnrichmentStatus,
    Repository,
    RepositoryMethod,
    Screen,
    StateMachine,
    StateField,
    StateTransition,
    ViewModel,
    ViewModelFunction,
    utc_now,
)
from project_brain.llm.adapter import LLMAdapter, NullAdapter, create_adapter


_PROMPT_PATH = (
    Path(__file__).parent.parent.parent / "prompts" / "feature_extraction_v1.txt"
)

# Regex patterns for feature section detection in PRD markdown
_FEATURE_HEADING_RE = re.compile(
    r"^#{1,3}\s+(?:Feature[:\s]+)?(.+)$",
    re.MULTILINE | re.IGNORECASE,
)


@dataclass
class IncrementalEnrichmentResult:
    completed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    session: EnrichmentSession | None = None

    @property
    def success(self) -> bool:
        return len(self.failed) == 0


class IncrementalEnricher:
    """Enriches a PRD feature-by-feature with full resume support."""

    def __init__(
        self,
        llm: LLMAdapter | None = None,
        brain_dir: Path | str = "brain",
        max_retries: int = 2,
    ) -> None:
        self._llm = llm or create_adapter()
        self._manager = IncrementalBrainManager(brain_dir)
        self._max_retries = max_retries
        self._prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")

    @property
    def manager(self) -> IncrementalBrainManager:
        return self._manager

    # ── Public API ─────────────────────────────────────────────────────────

    async def enrich_feature(
        self,
        feature_id: str,
        prd_path: Path,
        feature_name: str | None = None,
    ) -> FeatureArtifacts | None:
        """Enrich a single feature from the PRD and save it to disk."""
        prd_text = prd_path.read_text(encoding="utf-8")
        sections = split_prd_into_features(prd_text)

        match = next(
            (
                s
                for s in sections
                if s["id"] == feature_id
                or s["name"].lower() == (feature_name or feature_id).lower()
            ),
            None,
        )
        if match is None:
            raise ValueError(
                f"Feature '{feature_id}' not found in PRD. "
                f"Available: {[s['id'] for s in sections]}"
            )

        self._manager.init_dirs()
        session = self._manager.load_status() or self._manager.new_session(
            prd_path=str(prd_path), feature_ids=[match["id"]]
        )

        artifacts = await self._enrich_one(match, session)
        self._manager.save_status(session)
        if artifacts:
            self._manager.aggregate()
        return artifacts

    async def enrich_phase(
        self,
        phase_name: str,
        prd_path: Path,
        phase_feature_ids: list[str] | None = None,
    ) -> IncrementalEnrichmentResult:
        """Enrich all features belonging to a named phase."""
        prd_text = prd_path.read_text(encoding="utf-8")
        sections = split_prd_into_features(prd_text)

        if phase_feature_ids:
            target_sections = [
                s for s in sections if s["id"] in phase_feature_ids
            ]
        else:
            # Fall back: features whose id or name contains the phase name
            target_sections = [
                s
                for s in sections
                if phase_name.lower() in s["id"].lower()
                or phase_name.lower() in s["name"].lower()
                or s.get("phase", "") == phase_name
            ]
            if not target_sections:
                target_sections = sections  # enrich everything if no match

        return await self._run_enrichment(target_sections, prd_path)

    async def enrich_all(self, prd_path: Path) -> IncrementalEnrichmentResult:
        """Enrich every feature found in the PRD from scratch."""
        prd_text = prd_path.read_text(encoding="utf-8")
        sections = split_prd_into_features(prd_text)
        return await self._run_enrichment(sections, prd_path)

    async def resume(self, prd_path: Path) -> IncrementalEnrichmentResult:
        """Continue from the last checkpoint, skipping completed features."""
        session = self._manager.load_status()
        if session is None:
            raise RuntimeError(
                "No enrichment session found in brain/generation/status.json. "
                "Start a new session with `brain enrich-feature` or `brain enrich-all`."
            )

        prd_text = prd_path.read_text(encoding="utf-8")
        all_sections = split_prd_into_features(prd_text)

        # Pass all sections; _run_enrichment skips completed ones (adding them to result.skipped)
        return await self._run_enrichment(all_sections, prd_path, existing_session=session)

    # ── Core enrichment loop ───────────────────────────────────────────────

    async def _run_enrichment(
        self,
        sections: list[dict[str, str]],
        prd_path: Path,
        existing_session: EnrichmentSession | None = None,
    ) -> IncrementalEnrichmentResult:
        self._manager.init_dirs()
        result = IncrementalEnrichmentResult()

        if existing_session:
            session = existing_session
        else:
            session = self._manager.load_status() or self._manager.new_session(
                prd_path=str(prd_path),
                feature_ids=[s["id"] for s in sections],
            )

        for sec in sections:
            fid = sec["id"]
            if fid in session.completed_features:
                result.skipped.append(fid)
                continue

            artifacts = await self._enrich_one(sec, session)
            if artifacts:
                result.completed.append(fid)
            else:
                result.failed.append(fid)

            self._manager.save_status(session)

        result.session = session

        # Rebuild the aggregated cache once after the run
        if result.completed:
            self._manager.aggregate()

        return result

    async def _enrich_one(
        self,
        section: dict[str, str],
        session: EnrichmentSession,
    ) -> FeatureArtifacts | None:
        fid = section["id"]
        fname = section["name"]

        # Ensure feature is tracked in session
        if not session.feature_status(fid):
            session.features.append(FeatureEnrichmentStatus(feature_id=fid, feature_name=fname))
        for f in session.features:
            if f.feature_id == fid:
                f.status = "enriching"
                f.feature_name = fname

        self._manager.save_status(session)

        for attempt in range(1, self._max_retries + 2):
            try:
                raw_json = await self._call_llm(section)
                artifacts = _parse_artifacts(fid, fname, raw_json)
                artifacts.audit_passed = _audit_artifacts(artifacts)
                self._manager.save_feature(artifacts)
                session.mark_complete(fid)
                return artifacts
            except Exception as exc:  # noqa: BLE001
                if attempt > self._max_retries:
                    session.mark_failed(fid, str(exc))
                    return None

        return None  # unreachable but satisfies type checker

    async def _call_llm(self, section: dict[str, str]) -> str:
        if isinstance(self._llm, NullAdapter):
            return _null_artifacts_json(section["id"], section["name"])

        prompt = (
            self._prompt_template
            .replace("{feature_id}", section["id"])
            .replace("{feature_name}", section["name"])
            .replace("{feature_section}", section["text"][:8000])  # guard token limit
        )
        return await self._llm.complete(prompt)


# ── PRD feature splitter ───────────────────────────────────────────────────────


def split_prd_into_features(prd_text: str) -> list[dict[str, str]]:
    """Split a PRD into feature sections.

    Returns a list of dicts with keys: id, name, text, phase (optional).

    The splitter looks for ## or ### headings that indicate feature boundaries.
    Common patterns supported:
    - ## Feature: Authentication
    - ## Authentication Feature
    - ### 1. Authentication
    - ## Features \\n ### Auth
    """
    sections = []

    # Find all H2/H3 headings and their positions
    heading_re = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
    matches = list(heading_re.finditer(prd_text))

    if not matches:
        # Flat PRD — treat everything as a single "main" feature
        return [{"id": "main", "name": "Main Feature", "text": prd_text, "phase": "1"}]

    # Try to find a "Features" section to extract sub-features from
    features_section_start = None
    for i, m in enumerate(matches):
        if re.match(r"features?$", m.group(2).strip(), re.IGNORECASE):
            features_section_start = i
            break

    feature_headings = []
    if features_section_start is not None:
        # Sub-features are H3 headings inside the Features section
        parent_level = len(matches[features_section_start].group(1))
        for m in matches[features_section_start + 1:]:
            level = len(m.group(1))
            if level <= parent_level:
                break
            feature_headings.append(m)

    if not feature_headings:
        # Fall back: use all H2 headings that look like features
        skip_names = {
            "overview", "introduction", "tech stack", "architecture",
            "environment", "requirements", "appendix", "glossary",
            "non-functional", "design system", "deployment",
        }
        feature_headings = [
            m for m in matches
            if len(m.group(1)) == 2
            and not any(sk in m.group(2).lower() for sk in skip_names)
        ]

    if not feature_headings:
        # Last resort: single feature from full PRD
        return [{"id": "main", "name": "Main Feature", "text": prd_text, "phase": "1"}]

    for i, m in enumerate(feature_headings):
        start = m.end()
        end = (
            feature_headings[i + 1].start()
            if i + 1 < len(feature_headings)
            else len(prd_text)
        )
        name = re.sub(r"^(feature[:\s]+|\d+[\.\)]\s*)", "", m.group(2), flags=re.IGNORECASE).strip()
        fid = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        sections.append(
            {
                "id": fid,
                "name": name,
                "text": prd_text[start:end].strip(),
                "phase": "1",
            }
        )

    return sections or [{"id": "main", "name": "Main Feature", "text": prd_text, "phase": "1"}]


# ── JSON parsing helpers ───────────────────────────────────────────────────────


def _strip_fences(text: str) -> str:
    """Remove markdown code fences from LLM response."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_artifacts(feature_id: str, feature_name: str, raw: str) -> FeatureArtifacts:
    raw = _strip_fences(raw)
    # Find the first '{' in case LLM prepended prose
    brace = raw.find("{")
    if brace > 0:
        raw = raw[brace:]
    data: dict[str, Any] = json.loads(raw)
    return _dict_to_artifacts(feature_id, feature_name, data)


def _dict_to_artifacts(
    feature_id: str, feature_name: str, data: dict[str, Any]
) -> FeatureArtifacts:
    screens = [_parse_screen(s) for s in data.get("screens", [])]
    vms = [_parse_viewmodel(v) for v in data.get("viewmodels", [])]
    repos = [_parse_repository(r) for r in data.get("repositories", [])]
    rules = [_parse_business_rule(r) for r in data.get("business_rules", [])]
    machines = [_parse_state_machine(m) for m in data.get("state_machines", [])]
    use_cases = [str(u) for u in data.get("use_cases", [])]
    models = [_parse_data_model(d) for d in data.get("data_models", [])]
    return FeatureArtifacts(
        feature_id=feature_id,
        feature_name=feature_name,
        screens=screens,
        viewmodels=vms,
        repositories=repos,
        business_rules=rules,
        state_machines=machines,
        use_cases=use_cases,
        data_models=models,
    )


def _parse_screen(d: dict) -> Screen:
    return Screen(
        id=str(d.get("id", "unknown_screen")),
        route=d.get("route"),
        phase=d.get("phase"),
        viewmodel=d.get("viewmodel"),
        repository=d.get("repository"),
        use_cases=d.get("use_cases", []),
        nav_args=d.get("nav_args", []),
        ui_states=d.get("ui_states", []),
    )


def _parse_viewmodel(d: dict) -> ViewModel:
    functions = [
        ViewModelFunction(
            name=str(f.get("name", "doAction")),
            params=f.get("params", []),
            returns=f.get("returns", "Unit"),
            business_rule=f.get("business_rule"),
            concurrent=bool(f.get("concurrent", False)),
            state_updates=f.get("state_updates", []),
            events_fired=f.get("events_fired", []),
        )
        for f in d.get("functions", [])
    ]
    state_fields = [
        StateField(
            name=str(sf.get("name", "field")),
            type=str(sf.get("type", "String")),
            nullable=bool(sf.get("nullable", False)),
            default=str(sf.get("default", '""')),
        )
        for sf in d.get("state_fields", [])
    ]
    return ViewModel(
        id=str(d.get("id", "unknown_vm")),
        screen=d.get("screen"),
        repository=d.get("repository"),
        inject_dependencies=d.get("inject_dependencies", []),
        ui_state_type=d.get("ui_state_type", "data_class"),
        event_class=d.get("event_class"),
        has_mutex=bool(d.get("has_mutex", False)),
        has_saved_state=bool(d.get("has_saved_state", False)),
        state_fields=state_fields,
        functions=functions,
    )


def _parse_repository(d: dict) -> Repository:
    methods = [
        RepositoryMethod(
            name=str(m.get("name", "method")),
            params=m.get("params", []),
            returns=m.get("returns"),
            result_wrapped=bool(m.get("result_wrapped", False)),
            is_flow=bool(m.get("is_flow", False)),
            firebase_pattern=m.get("firebase_pattern"),
        )
        for m in d.get("methods", [])
    ]
    return Repository(
        id=str(d.get("id", "unknown_repo")),
        interface=d.get("interface"),
        implementation=d.get("implementation"),
        data_sources=d.get("data_sources", []),
        methods=methods,
    )


def _parse_business_rule(d: dict) -> BusinessRule:
    return BusinessRule(
        id=str(d.get("id", f"BR-{utc_now()[:10]}")),
        description=str(d.get("description", "")),
        trigger=d.get("trigger"),
        enforcement=d.get("enforcement"),
        required_updates=d.get("required_updates", []),
    )


def _parse_state_machine(d: dict) -> StateMachine:
    transitions = [
        StateTransition(**{"from": str(t.get("from", "")), "to": str(t.get("to", "")), "required_firestore_updates": t.get("required_firestore_updates", [])})
        for t in d.get("transitions", [])
    ]
    return StateMachine(
        entity=str(d.get("entity", "Entity")),
        states=d.get("states", []),
        transitions=transitions,
    )


def _parse_data_model(d: dict) -> DataModel:
    fields = [
        DataField(
            name=str(f.get("name", "field")),
            type=str(f.get("type", "String")),
            nullable=bool(f.get("nullable", False)),
        )
        for f in d.get("fields", [])
    ]
    return DataModel(
        id=str(d.get("id", "unknown_model")),
        fields=fields,
        firestore_collection=d.get("firestore_collection"),
    )


def _audit_artifacts(artifacts: FeatureArtifacts) -> bool:
    """Lightweight structural audit — returns True if artifacts look valid."""
    if not artifacts.screens and not artifacts.viewmodels:
        return False
    for screen in artifacts.screens:
        if not screen.id:
            return False
    for vm in artifacts.viewmodels:
        if not vm.id:
            return False
    return True


def _null_artifacts_json(feature_id: str, feature_name: str) -> str:
    """Minimal stub returned when no LLM is available."""
    return json.dumps(
        {
            "screens": [{"id": feature_id + "_screen", "route": feature_id}],
            "viewmodels": [
                {
                    "id": feature_id + "_vm",
                    "screen": feature_id + "_screen",
                    "functions": [{"name": "load", "params": [], "returns": "Unit"}],
                }
            ],
            "repositories": [],
            "business_rules": [],
            "state_machines": [],
            "use_cases": [],
            "data_models": [],
        }
    )
