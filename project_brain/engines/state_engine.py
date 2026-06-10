"""Phase 6 state transition validation engine.

Verifies that generated Kotlin files contain all required Firestore updates
for each state machine transition defined in the brain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from project_brain.brain.schema import ProjectBrain, StateMachine, StateTransition


@dataclass(frozen=True)
class TransitionViolation:
    entity: str
    from_state: str
    to_state: str
    missing_update: str
    severity: str
    recommended_implementation: str | None = None

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "transition": f"{self.from_state} → {self.to_state}",
            "missing_update": self.missing_update,
            "severity": self.severity,
            "recommended_implementation": self.recommended_implementation,
        }


class StateTransitionEngine:
    """Deterministic validator — checks brain state machines against generated file content."""

    def validate_transition(
        self,
        entity: str,
        from_state: str,
        to_state: str,
        file_content: str | None = None,
        file_path: str | None = None,
        brain: ProjectBrain | None = None,
    ) -> list[TransitionViolation]:
        """Check that a single transition's required updates appear in the file."""
        if file_content is None:
            if file_path is None:
                raise ValueError("Provide either file_content or file_path.")
            file_content = Path(file_path).read_text(encoding="utf-8", errors="ignore")

        machine = self._find_machine(brain, entity) if brain else None
        if machine is None:
            return []

        transition = next(
            (t for t in machine.transitions if t.from_state == from_state and t.to == to_state),
            None,
        )
        if transition is None:
            return []

        return self._check_transition(entity, transition, file_content)

    def validate_file(self, file_path: str, brain: ProjectBrain) -> list[TransitionViolation]:
        """Check all state machine transitions against a single file."""
        content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        violations: list[TransitionViolation] = []
        for machine in brain.state_machines:
            for transition in machine.transitions:
                # Only check files that plausibly handle this transition
                if not self._file_handles_transition(content, machine.entity, transition):
                    continue
                violations.extend(self._check_transition(machine.entity, transition, content))
        return violations

    def validate_brain(self, brain: ProjectBrain) -> list[TransitionViolation]:
        """Check all generated files referenced in brain.generation_history."""
        violations: list[TransitionViolation] = []
        for entry in brain.generation_history:
            if entry.output_path and Path(entry.output_path).exists():
                violations.extend(self.validate_file(entry.output_path, brain))
        return violations

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _find_machine(brain: ProjectBrain, entity: str) -> StateMachine | None:
        return next((m for m in brain.state_machines if m.entity.lower() == entity.lower()), None)

    @staticmethod
    def _file_handles_transition(content: str, entity: str, transition: StateTransition) -> bool:
        entity_lower = entity.lower()
        from_lower = transition.from_state.lower()
        to_lower = transition.to.lower()
        return entity_lower in content.lower() and (from_lower in content.lower() or to_lower in content.lower())

    @staticmethod
    def _check_transition(
        entity: str, transition: StateTransition, content: str
    ) -> list[TransitionViolation]:
        violations = []
        for update in transition.required_firestore_updates:
            if not _update_present(update, content):
                violations.append(TransitionViolation(
                    entity=entity,
                    from_state=transition.from_state,
                    to_state=transition.to,
                    missing_update=update,
                    severity=transition.missing_any or "CLASS_A",
                    recommended_implementation=transition.recommended_implementation,
                ))
        return violations


def _update_present(update: str, content: str) -> bool:
    """Check if a required update string is represented in the file content."""
    compact_update = re.sub(r"[^A-Za-z0-9_]+", "", update).lower()
    compact_content = re.sub(r"[^A-Za-z0-9_]+", "", content).lower()
    if compact_update in compact_content:
        return True
    # Accept partial match: all individual words present
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", update)
    return bool(words) and all(w.lower() in compact_content for w in words)
