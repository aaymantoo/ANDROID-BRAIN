"""Phase 5 bug forecasting tool facades."""

from __future__ import annotations

from typing import Any

from project_brain.brain.manager import BrainManager
from project_brain.brain.schema import ProjectBrain
from project_brain.engines.bug_engine import BugEngine


def forecast_bugs(screen_id: str, brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Run all 5 bug detectors for a single screen."""
    brain = BrainManager(brain_path).load()
    return forecast_bugs_brain(brain, screen_id)


def forecast_bugs_brain(brain: ProjectBrain, screen_id: str) -> dict[str, Any]:
    bugs = BugEngine().forecast(brain, screen_id)
    return {
        "screen_id": screen_id,
        "bug_count": len(bugs),
        "class_a_count": sum(1 for b in bugs if b.severity == "CLASS_A"),
        "class_b_count": sum(1 for b in bugs if b.severity == "CLASS_B"),
        "bugs": [b.to_dict() for b in bugs],
    }


def detect_race_conditions(brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Scan all generated files for Firestore race conditions."""
    from project_brain.engines.bug_engine import RaceConditionDetector
    brain = BrainManager(brain_path).load()
    return detect_race_conditions_brain(brain)


def detect_race_conditions_brain(brain: ProjectBrain) -> dict[str, Any]:
    from project_brain.engines.bug_engine import RaceConditionDetector
    bugs = RaceConditionDetector().detect(brain)
    return {"bug_count": len(bugs), "bugs": [b.to_dict() for b in bugs]}


def detect_orphaned_documents(brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Detect consistency_link violations that would produce orphaned documents."""
    from project_brain.engines.bug_engine import FirestoreConsistencyDetector
    brain = BrainManager(brain_path).load()
    return detect_orphaned_documents_brain(brain)


def detect_orphaned_documents_brain(brain: ProjectBrain) -> dict[str, Any]:
    from project_brain.engines.bug_engine import FirestoreConsistencyDetector
    bugs = FirestoreConsistencyDetector().detect(brain)
    return {"bug_count": len(bugs), "bugs": [b.to_dict() for b in bugs]}


def audit_production_readiness(phase: int, brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Full pre-launch audit for a phase."""
    brain = BrainManager(brain_path).load()
    return audit_production_readiness_brain(brain, phase)


def audit_production_readiness_brain(brain: ProjectBrain, phase: int) -> dict[str, Any]:
    return BugEngine().audit(brain, phase)
