"""Phase 6 brain management tools — sync_brain and drift detection."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from project_brain.brain.manager import BrainManager
from project_brain.brain.schema import KnownViolation, ProjectBrain


@dataclass
class DriftItem:
    screen_id: str
    file_path: str
    drift_type: str  # "missing_function" | "extra_function" | "file_deleted"
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "screen_id": self.screen_id,
            "file_path": self.file_path,
            "drift_type": self.drift_type,
            "detail": self.detail,
        }


@dataclass
class SyncReport:
    scanned: int = 0
    matched: list[str] = field(default_factory=list)
    drifted: list[DriftItem] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    new_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "matched_count": len(self.matched),
            "drifted_count": len(self.drifted),
            "deleted_count": len(self.deleted),
            "drifted": [d.to_dict() for d in self.drifted],
            "deleted": self.deleted,
            "new_violations": self.new_violations,
        }


def sync_brain(project_path: str, brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Re-scan generated files and detect drift from the brain spec.

    For each file recorded in brain.generation_history:
    - If deleted: marks it
    - If present: compares extracted function/class names to brain spec

    Drift is added to brain.known_violations (severity NEEDS_REVIEW).
    """
    brain = BrainManager(brain_path).load()
    report = _sync_brain(brain)
    # persist new violations
    for item in report.drifted:
        violation_id = f"DRIFT_{item.screen_id}_{item.drift_type}"
        if not any(v.id == violation_id for v in brain.known_violations):
            brain.known_violations.append(KnownViolation(
                id=violation_id,
                severity="NEEDS_REVIEW",
                message=item.detail,
                location=item.file_path,
                confidence=0.8,
                resolved=False,
            ))
    BrainManager(brain_path).save(brain)
    return report.to_dict()


def sync_brain_instance(brain: ProjectBrain) -> SyncReport:
    """In-memory sync — used internally without re-loading brain."""
    return _sync_brain(brain)


def _sync_brain(brain: ProjectBrain) -> SyncReport:
    report = SyncReport()

    # Build expected function sets per screen from brain viewmodels
    vm_expected: dict[str, set[str]] = {}
    for vm in brain.viewmodels:
        vm_expected[vm.id] = {f.name for f in vm.functions}

    # Build expected method sets per repository
    repo_expected: dict[str, set[str]] = {}
    for repo in brain.repositories:
        repo_expected[repo.id] = {m.name for m in repo.methods}

    seen_paths: set[str] = set()
    for entry in brain.generation_history:
        if not entry.output_path:
            continue
        path = Path(entry.output_path)
        seen_paths.add(str(path))
        report.scanned += 1

        if not path.exists():
            report.deleted.append(str(path))
            continue

        content = path.read_text(encoding="utf-8", errors="ignore")
        actual_fns = _extract_function_names(content)

        # Match generation entry to brain spec
        screen_id = _infer_screen_id(entry.target, brain)
        vm_id = entry.target if entry.target in vm_expected else None
        repo_id = entry.target if entry.target in repo_expected else None

        if vm_id:
            expected_fns = vm_expected[vm_id]
            missing = expected_fns - actual_fns
            extra = actual_fns - expected_fns - _ALWAYS_ALLOW
            for fn in sorted(missing):
                report.drifted.append(DriftItem(
                    screen_id=screen_id or vm_id,
                    file_path=str(path),
                    drift_type="missing_function",
                    detail=f"Function '{fn}' is in brain spec but not in generated file.",
                ))
            for fn in sorted(extra):
                report.drifted.append(DriftItem(
                    screen_id=screen_id or vm_id,
                    file_path=str(path),
                    drift_type="extra_function",
                    detail=f"Function '{fn}' is in generated file but not in brain spec (may be manual addition).",
                ))

        elif repo_id:
            expected_methods = repo_expected[repo_id]
            actual_methods = _extract_function_names(content)
            missing = expected_methods - actual_methods
            for fn in sorted(missing):
                report.drifted.append(DriftItem(
                    screen_id=repo_id,
                    file_path=str(path),
                    drift_type="missing_function",
                    detail=f"Repository method '{fn}' is in brain spec but not in generated file.",
                ))

        else:
            report.matched.append(str(path))

        if not report.drifted or report.drifted[-1].file_path != str(path):
            report.matched.append(str(path))

    return report


_ALWAYS_ALLOW = {"onCleared", "init", "toString", "hashCode", "equals"}


def _extract_function_names(content: str) -> set[str]:
    """Extract all `fun` names from Kotlin content."""
    return set(re.findall(r"\bfun\s+([a-z][A-Za-z0-9_]*)\s*\(", content))


def _infer_screen_id(target: str, brain: ProjectBrain) -> str | None:
    for vm in brain.viewmodels:
        if vm.id == target and vm.screen:
            return vm.screen
    for screen in brain.screens:
        if screen.viewmodel == target or screen.repository == target:
            return screen.id
    return None
