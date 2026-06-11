"""MCP tools for the incremental enrichment pipeline.

These three tools let a Claude Code session inspect the brain/ directory
structure, query per-feature artifacts, and trigger cache aggregation —
without needing to load the full monolithic PROJECT_BRAIN.json.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from project_brain.brain.incremental_manager import IncrementalBrainManager


def _manager(brain_dir: str | None = None) -> IncrementalBrainManager:
    return IncrementalBrainManager(brain_dir or os.environ.get("BRAIN_DIR", "brain"))


def get_enrichment_status(brain_dir: str | None = None) -> dict[str, Any]:
    """Return current incremental enrichment session status.

    Shows completed / pending / failed features and the last checkpoint
    so a Claude Code agent can decide whether to call brain resume or
    start a new enrichment pass.
    """
    mgr = _manager(brain_dir)
    session = mgr.load_status()
    if session is None:
        return {
            "status": "no_session",
            "message": "No incremental enrichment session found. "
            "Run `brain enrich-feature` or `brain enrich-all` to start.",
            "brain_dir": str(mgr.brain_dir),
        }

    features_summary = [
        {
            "feature_id": f.feature_id,
            "feature_name": f.feature_name,
            "status": f.status,
            "completed_at": f.completed_at,
            "audit_passed": f.audit_passed,
            "error": f.error,
        }
        for f in session.features
    ]

    return {
        "session_id": session.session_id,
        "started_at": session.started_at,
        "last_updated": session.last_updated,
        "last_checkpoint": session.last_checkpoint,
        "prd_path": session.prd_path,
        "completed": session.completed_features,
        "pending": session.pending_features,
        "failed": session.failed_features,
        "features": features_summary,
        "can_resume": bool(session.pending_features or session.failed_features),
    }


def get_feature_artifacts(
    feature_id: str, brain_dir: str | None = None
) -> dict[str, Any]:
    """Return all artifacts for a single enriched feature.

    Reads directly from brain/features/{feature_id}/*.json — the primary
    source of truth.  Returns a summary of screens, ViewModels, repositories,
    business rules, and state machines for the requested feature.
    """
    mgr = _manager(brain_dir)
    arts = mgr.load_feature(feature_id)
    if arts is None:
        available = mgr.list_features()
        return {
            "error": f"Feature '{feature_id}' not found in {mgr.features_dir}",
            "available_features": available,
        }

    return {
        "feature_id": arts.feature_id,
        "feature_name": arts.feature_name,
        "enriched_at": arts.enriched_at,
        "audit_passed": arts.audit_passed,
        "screens": [
            {
                "id": s.id,
                "route": s.route,
                "phase": s.phase,
                "viewmodel": s.viewmodel,
                "repository": s.repository,
            }
            for s in arts.screens
        ],
        "viewmodels": [
            {
                "id": v.id,
                "screen": v.screen,
                "functions": [f.name for f in v.functions],
                "state_fields": [f.name for f in v.state_fields],
            }
            for v in arts.viewmodels
        ],
        "repositories": [
            {
                "id": r.id,
                "interface": r.interface,
                "methods": [m.name for m in r.methods],
            }
            for r in arts.repositories
        ],
        "business_rules": [
            {"id": r.id, "description": r.description}
            for r in arts.business_rules
        ],
        "state_machines": [
            {"entity": m.entity, "states": m.states}
            for m in arts.state_machines
        ],
        "use_cases": arts.use_cases,
        "data_models": [d.id for d in arts.data_models],
    }


def aggregate_brain_cache(brain_dir: str | None = None) -> dict[str, Any]:
    """Regenerate brain/cache/aggregated_brain.json from all feature artifacts.

    This is a pure derivation step — the per-feature JSON files are the
    source of truth.  Call this after adding or updating any feature to
    refresh the aggregated view that `brain serve` can load.
    """
    mgr = _manager(brain_dir)
    features = mgr.list_features()
    if not features:
        return {
            "error": "No feature artifacts found.",
            "brain_dir": str(mgr.brain_dir),
            "hint": "Run `brain enrich-feature <id>` to populate features.",
        }

    brain = mgr.aggregate()
    cache_path = mgr.aggregated_brain_path
    return {
        "aggregated_brain_path": str(cache_path),
        "features_merged": features,
        "screens": len(brain.screens),
        "viewmodels": len(brain.viewmodels),
        "repositories": len(brain.repositories),
        "business_rules": len(brain.business_rules),
        "state_machines": len(brain.state_machines),
    }
