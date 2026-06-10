"""Phase 5 predictive bug engine — zero-LLM detection, LLM for explanations only.

Five detectors:
  D1  StateTransitionBugDetector   — missing required_firestore_updates in transitions
  D2  FirestoreConsistencyDetector — consistency_links not honored across screens
  D3  RaceConditionDetector        — read-then-write without Firestore transaction
  D4  ListenerLeakDetector         — Firestore listeners without cleanup in scaffold
  D5  RevenueIntegrityDetector     — client-side financial calculations in ViewModel
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from project_brain.brain.schema import ProjectBrain


@dataclass
class Bug:
    bug_type: str
    severity: str  # CLASS_A | CLASS_B | CLASS_C
    screen_id: str | None
    file_path: str | None
    description: str
    forecast: str
    fix: str
    transition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bug_type": self.bug_type,
            "severity": self.severity,
            "screen_id": self.screen_id,
            "file_path": self.file_path,
            "description": self.description,
            "forecast": self.forecast,
            "fix": self.fix,
            "transition": self.transition,
        }


# ── D1: State Transition Bug Detector ───────────────────────────────────────


class StateTransitionBugDetector:
    def detect(self, brain: ProjectBrain, screen_id: str | None = None) -> list[Bug]:
        bugs: list[Bug] = []
        files = _files_for_screen(brain, screen_id)
        for file_path, sid in files:
            if not file_path.exists():
                continue
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for machine in brain.state_machines:
                for transition in machine.transitions:
                    if not _file_handles_entity(content, machine.entity):
                        continue
                    for update in transition.required_firestore_updates:
                        if not _update_present(update, content):
                            bugs.append(Bug(
                                bug_type="MISSING_STATE_UPDATE",
                                severity=transition.missing_any or "CLASS_A",
                                screen_id=sid,
                                file_path=str(file_path),
                                description=(
                                    f"{machine.entity} transition "
                                    f"{transition.from_state}→{transition.to} "
                                    f"is missing required update: {update}"
                                ),
                                forecast=(
                                    f"If this transition completes without '{update}', "
                                    f"data inconsistency will appear in production after the first "
                                    f"{transition.from_state}→{transition.to} transition."
                                ),
                                fix=f"Add '{update}' in the {transition.to} handler.",
                                transition=f"{transition.from_state}→{transition.to}",
                            ))
        return bugs


# ── D2: Firestore Consistency Detector ──────────────────────────────────────


class FirestoreConsistencyDetector:
    def detect(self, brain: ProjectBrain, screen_id: str | None = None) -> list[Bug]:
        bugs: list[Bug] = []
        files = _files_for_screen(brain, screen_id)
        for file_path, sid in files:
            if not file_path.exists():
                continue
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for model in brain.data_models:
                for link in model.consistency_links:
                    if _field_updated(content, link.field) and not _field_updated(content, link.linked_to):
                        bugs.append(Bug(
                            bug_type="FIRESTORE_CONSISTENCY",
                            severity="CLASS_A",
                            screen_id=sid,
                            file_path=str(file_path),
                            description=(
                                f"{model.id}.{link.field} is updated without updating {link.linked_to}. "
                                f"Rule: {link.rule}"
                            ),
                            forecast=(
                                f"'{link.field}' will be out of sync with '{link.linked_to}'. "
                                "Orphaned document detected in production data."
                            ),
                            fix=f"Always update '{link.linked_to}' when updating '{link.field}'.",
                        ))
        return bugs


# ── D3: Race Condition Detector ──────────────────────────────────────────────


_RACE_PATTERNS = [
    re.compile(r"\.get\(\)"),
    re.compile(r"\.set\s*\("),
    re.compile(r"\.update\s*\("),
]
_TRANSACTION_PATTERNS = [
    re.compile(r"runTransaction"),
    re.compile(r"\.batch\(\)"),
    re.compile(r"WriteBatch"),
]


class RaceConditionDetector:
    def detect(self, brain: ProjectBrain, screen_id: str | None = None) -> list[Bug]:
        bugs: list[Bug] = []
        files = _files_for_screen(brain, screen_id)
        for file_path, sid in files:
            if not file_path.exists():
                continue
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            has_read = any(p.search(content) for p in [_RACE_PATTERNS[0]])
            has_write = any(p.search(content) for p in _RACE_PATTERNS[1:])
            has_transaction = any(p.search(content) for p in _TRANSACTION_PATTERNS)
            if has_read and has_write and not has_transaction:
                bugs.append(Bug(
                    bug_type="RACE_CONDITION",
                    severity="CLASS_A",
                    screen_id=sid,
                    file_path=str(file_path),
                    description="Read-then-write Firestore pattern detected without a transaction.",
                    forecast=(
                        "Two concurrent users can read the same value simultaneously. "
                        "Double-booking or double-assignment will occur in production."
                    ),
                    fix="Wrap the read-modify-write in a Firestore transaction: runTransaction { ... }",
                ))
        return bugs


# ── D4: Listener Leak Detector ───────────────────────────────────────────────


class ListenerLeakDetector:
    def detect(self, brain: ProjectBrain, screen_id: str | None = None) -> list[Bug]:
        bugs: list[Bug] = []
        for screen in brain.screens:
            if screen_id and screen.id != screen_id:
                continue
            if not screen.firestore_listeners:
                continue
            scaffold_path = _find_file(brain, screen.id, "screen_scaffold.kt.j2")
            if not scaffold_path or not scaffold_path.exists():
                continue
            content = scaffold_path.read_text(encoding="utf-8", errors="ignore")
            has_cleanup = (
                "DisposableEffect" in content
                or "awaitClose" in content
                or "removeEventListener" in content
                or "registration.remove()" in content
            )
            if not has_cleanup:
                bugs.append(Bug(
                    bug_type="LISTENER_LEAK",
                    severity="CLASS_B",
                    screen_id=screen.id,
                    file_path=str(scaffold_path),
                    description=(
                        f"{screen.id} has {len(screen.firestore_listeners)} Firestore listener(s) "
                        "but no cleanup (DisposableEffect / awaitClose) in the scaffold."
                    ),
                    forecast=(
                        "Listeners will keep firing after the user navigates away. "
                        "Memory leak and spurious state updates in background."
                    ),
                    fix=(
                        "Use DisposableEffect { onDispose { registration.remove() } } "
                        "or callbackFlow { awaitClose { listener.remove() } } in the ViewModel."
                    ),
                ))
        return bugs


# ── D5: Revenue Integrity Detector ──────────────────────────────────────────


_FINANCIAL_TERMS = re.compile(
    r"\b(earning|fare|payment|revenue|wallet|balance|price|amount|charge|fee)\b", re.I
)
_VIEWMODEL_SCOPE = re.compile(r"viewModelScope")


class RevenueIntegrityDetector:
    def detect(self, brain: ProjectBrain, screen_id: str | None = None) -> list[Bug]:
        bugs: list[Bug] = []
        files = _files_for_screen(brain, screen_id)
        for file_path, sid in files:
            if not file_path.exists():
                continue
            if "ViewModel" not in file_path.name:
                continue
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if _FINANCIAL_TERMS.search(content) and _VIEWMODEL_SCOPE.search(content):
                bugs.append(Bug(
                    bug_type="REVENUE_INTEGRITY",
                    severity="CLASS_A",
                    screen_id=sid,
                    file_path=str(file_path),
                    description="Financial calculation in ViewModel with viewModelScope detected.",
                    forecast=(
                        "If the app crashes between the earnings calculation and the Firestore write, "
                        "the user loses earned money. Legal and trust risk."
                    ),
                    fix=(
                        "Move earnings/payment calculation to a Cloud Function triggered by the "
                        "relevant Firestore write (e.g., order completion event)."
                    ),
                ))
        return bugs


# ── BugEngine orchestrator ───────────────────────────────────────────────────


class BugEngine:
    """Run all 5 detectors for a screen (or the entire brain if screen_id is None)."""

    def __init__(self) -> None:
        self._detectors = [
            StateTransitionBugDetector(),
            FirestoreConsistencyDetector(),
            RaceConditionDetector(),
            ListenerLeakDetector(),
            RevenueIntegrityDetector(),
        ]

    def forecast(self, brain: ProjectBrain, screen_id: str | None = None) -> list[Bug]:
        bugs: list[Bug] = []
        for detector in self._detectors:
            bugs.extend(detector.detect(brain, screen_id))
        # Sort: CLASS_A first, then CLASS_B, then CLASS_C
        priority = {"CLASS_A": 0, "CLASS_B": 1, "CLASS_C": 2}
        bugs.sort(key=lambda b: priority.get(b.severity, 3))
        return bugs

    def audit(self, brain: ProjectBrain, phase: int | None = None) -> dict[str, Any]:
        """Full production-readiness audit for a phase or the whole project."""
        if phase is not None:
            p = next((p for p in brain.phases if p.number == phase), None)
            target_screens = p.screens if p else []
        else:
            target_screens = [s.id for s in brain.screens]

        all_bugs: list[Bug] = []
        for sid in target_screens:
            all_bugs.extend(self.forecast(brain, sid))

        class_a = [b for b in all_bugs if b.severity == "CLASS_A"]
        class_b = [b for b in all_bugs if b.severity == "CLASS_B"]
        production_ready = len(class_a) == 0

        return {
            "phase": phase,
            "production_ready": production_ready,
            "class_a_count": len(class_a),
            "class_b_count": len(class_b),
            "total_bugs": len(all_bugs),
            "bugs": [b.to_dict() for b in all_bugs],
        }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _files_for_screen(brain: ProjectBrain, screen_id: str | None) -> list[tuple[Path, str]]:
    result: list[tuple[Path, str]] = []
    for entry in brain.generation_history:
        if entry.output_path:
            sid = entry.target
            if screen_id is None or sid == screen_id or sid == screen_id.replace("Screen", ""):
                result.append((Path(entry.output_path), sid))
    return result


def _find_file(brain: ProjectBrain, target: str, template_hint: str) -> Path | None:
    for entry in reversed(brain.generation_history):
        if entry.target == target and template_hint in entry.tool and entry.output_path:
            p = Path(entry.output_path)
            if p.exists():
                return p
    return None


def _file_handles_entity(content: str, entity: str) -> bool:
    return entity.lower() in content.lower()


def _update_present(update: str, content: str) -> bool:
    compact_update = re.sub(r"[^A-Za-z0-9_]+", "", update).lower()
    compact_content = re.sub(r"[^A-Za-z0-9_]+", "", content).lower()
    if compact_update in compact_content:
        return True
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", update)
    return bool(words) and all(w.lower() in compact_content for w in words)


def _field_updated(content: str, field_name: str) -> bool:
    field_lower = field_name.replace(".", "").replace("_", "").lower()
    return field_lower in content.replace(".", "").replace("_", "").lower()
