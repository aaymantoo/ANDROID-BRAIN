"""Phase 0C: Roadmap MCP tools — session continuity and pipeline tracking."""

from __future__ import annotations

from project_brain.brain.schema import Feature, ProjectBrain
from project_brain.generators.roadmap_generator import RoadmapGenerator


def get_session_context(brain: ProjectBrain) -> dict:
    """Return last session summary, overall progress, current feature, and next recommended step.

    Call this at the start of every new session to resume work without re-explaining context.
    """
    rg = RoadmapGenerator()
    done, total = rg._overall_counts(brain)
    pct = int(done / total * 100) if total else 0

    last_session = None
    if brain.session_log:
        last = brain.session_log[-1]
        last_session = {
            "date": last.date,
            "components_built": last.components_built,
            "features_completed": last.features_completed,
        }

    current_feature = _current_feature(brain, rg)
    next_step = rg.next_step(brain)

    blocked = [
        {"id": f.id, "name": f.name, "waiting_for": f.feature_dependencies}
        for f in brain.features
        if f.status != "complete" and rg._is_blocked(brain, f)
    ]

    feature_summary = [
        {
            "id": f.id,
            "name": f.name,
            "status": f.status,
            "priority": f.priority,
        }
        for f in sorted(brain.features, key=lambda x: x.priority)
    ]

    return {
        "project": brain.meta.project_name,
        "overall_progress": f"{done}/{total} components ({pct}%)",
        "last_session": last_session,
        "current_feature": current_feature,
        "next_step": next_step,
        "blocked_features": blocked,
        "all_features": feature_summary,
    }


def get_next_task(brain: ProjectBrain) -> dict:
    """Return the single most important next generation step with the exact tool call to make.

    Respects feature priority order and dependency blocking.
    """
    rg = RoadmapGenerator()
    call = rg.next_step(brain)

    if call is None:
        done, total = rg._overall_counts(brain)
        return {
            "done": True,
            "message": f"All {total} components built and validated. Project is complete.",
            "next_step": None,
        }

    # Determine which feature and screen this call is for
    feature_name = None
    screen_id = _extract_screen_id(call)
    if screen_id:
        for f in brain.features:
            if screen_id in f.screens:
                feature_name = f.name
                break

    return {
        "done": False,
        "next_step": call,
        "feature": feature_name,
        "screen": screen_id,
        "reason": _reason_for_call(brain, call, screen_id),
    }


def get_feature_status(brain: ProjectBrain, feature_id: str) -> dict:
    """Return component-level generation status for every screen in a feature."""
    rg = RoadmapGenerator()
    feature = next(
        (f for f in brain.features if f.id == feature_id or f.name.lower() == feature_id.lower()),
        None,
    )
    if not feature:
        return {"error": f"Feature '{feature_id}' not found. Available: {[f.id for f in brain.features]}"}

    done, total = rg._feature_counts(brain, feature)
    pct = int(done / total * 100) if total else 0
    blocked = rg._is_blocked(brain, feature)

    screens = []
    for sid in feature.screens:
        status = rg._get_status(brain, sid)
        c = status.components
        screens.append({
            "screen_id": sid,
            "viewmodel": c.viewmodel,
            "ui_state": c.ui_state,
            "repository": c.repository,
            "scaffold": c.scaffold,
            "di_module": c.di_module,
            "nav_route": c.nav_route,
            "tests": c.tests,
            "validated": c.validated,
            "done_count": c.done_count(),
            "all_generated": c.all_generated,
        })

    next_step = rg._next_for_feature(brain, feature)

    return {
        "feature_id": feature.id,
        "feature_name": feature.name,
        "status": feature.status,
        "priority": feature.priority,
        "blocked": blocked,
        "progress": f"{done}/{total} ({pct}%)",
        "screens": screens,
        "next_step": next_step,
    }


def get_project_roadmap(brain: ProjectBrain) -> dict:
    """Return the full feature → screen → component status tree for the entire project."""
    rg = RoadmapGenerator()
    done, total = rg._overall_counts(brain)
    pct = int(done / total * 100) if total else 0
    next_step = rg.next_step(brain)

    features = []
    for feature in sorted(brain.features, key=lambda f: f.priority):
        fdone, ftotal = rg._feature_counts(brain, feature)
        fpct = int(fdone / ftotal * 100) if ftotal else 0
        blocked = rg._is_blocked(brain, feature)

        screens = []
        for sid in feature.screens:
            status = rg._get_status(brain, sid)
            c = status.components
            screens.append({
                "screen_id": sid,
                "done_count": c.done_count(),
                "all_generated": c.all_generated,
                "components": {
                    "viewmodel": c.viewmodel,
                    "ui_state": c.ui_state,
                    "repository": c.repository,
                    "scaffold": c.scaffold,
                    "di_module": c.di_module,
                    "nav_route": c.nav_route,
                    "tests": c.tests,
                    "validated": c.validated,
                },
            })

        features.append({
            "id": feature.id,
            "name": feature.name,
            "status": feature.status,
            "priority": feature.priority,
            "blocked": blocked,
            "dependencies": feature.feature_dependencies,
            "progress": f"{fdone}/{ftotal} ({fpct}%)",
            "screens": screens,
        })

    # Orphan screens (no feature assignment)
    assigned = {sid for f in brain.features for sid in f.screens}
    orphans = []
    for screen in brain.screens:
        if screen.id not in assigned:
            status = rg._get_status(brain, screen.id)
            c = status.components
            orphans.append({"screen_id": screen.id, "done_count": c.done_count()})

    session_log = [
        {
            "date": e.date,
            "components_built": len(e.components_built),
            "features_completed": e.features_completed,
        }
        for e in brain.session_log
    ]

    return {
        "project": brain.meta.project_name,
        "overall_progress": f"{done}/{total} ({pct}%)",
        "next_step": next_step,
        "features": features,
        "unassigned_screens": orphans,
        "session_count": len(brain.session_log),
        "recent_sessions": session_log[-3:],
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _current_feature(brain: ProjectBrain, rg: RoadmapGenerator) -> dict | None:
    unblocked = rg._unblocked_features(brain)
    for f in unblocked:
        fdone, ftotal = rg._feature_counts(brain, f)
        return {
            "id": f.id,
            "name": f.name,
            "status": f.status,
            "progress": f"{fdone}/{ftotal}",
        }
    return None


def _extract_screen_id(call: str) -> str | None:
    """Extract screen_id from a call like generate_viewmodel("phone_entry")."""
    import re
    m = re.search(r'"([^"]+)"', call)
    return m.group(1) if m else None


def _reason_for_call(brain: ProjectBrain, call: str, screen_id: str | None) -> str:
    if screen_id is None:
        return "Next unbuilt component."
    for f in brain.features:
        if screen_id in f.screens:
            return (
                f"Next unbuilt component in feature '{f.name}' (priority {f.priority})."
            )
    return f"Next unbuilt component for screen '{screen_id}'."
