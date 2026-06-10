"""Phase 0C: Roadmap generator.

Produces and maintains ROADMAP.md — a persistent, human-readable progress
board that lets a new LLM session resume exactly where the last one left off
without any re-explanation of project context.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from project_brain.brain.manager import BrainManager
from project_brain.brain.schema import (
    ComponentStatus,
    Feature,
    GenerationStatus,
    ProjectBrain,
    SessionEntry,
    utc_now,
)


# Maps GenerationResult.template → ComponentStatus field name
_TEMPLATE_TO_COMPONENT: dict[str, str] = {
    "viewmodel.kt.j2": "viewmodel",
    "uistate.kt.j2": "ui_state",
    "repository_interface.kt.j2 + repository_impl.kt.j2": "repository",
    "repository_impl.kt.j2": "repository",
    "repository_interface.kt.j2": "repository",
    "screen_scaffold.kt.j2": "scaffold",
    "di_module.kt.j2": "di_module",
    "nav_route.kt.j2": "nav_route",
    "viewmodel_test.kt.j2": "tests",
}

_TOTAL_COMPONENTS = 8  # flags in ComponentStatus


class RoadmapGenerator:
    """Generates and incrementally updates ROADMAP.md alongside PROJECT_BRAIN.json."""

    # ── Public API ───────────────────────────────────────────────────

    def write(self, brain: ProjectBrain, path: str | Path) -> Path:
        """Write (or overwrite) ROADMAP.md at path."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.generate(brain), encoding="utf-8")
        return out

    def generate(self, brain: ProjectBrain) -> str:
        """Produce the full ROADMAP.md content string."""
        lines: list[str] = []
        project = brain.meta.project_name
        date = _today()

        done, total = self._overall_counts(brain)
        pct = int(done / total * 100) if total else 0
        bar = self._progress_bar(pct)

        n_features = len(brain.features) or "–"
        n_screens = len(brain.screens)

        lines.append(f"# {project} — Project Roadmap")
        lines.append(
            f"*Generated {date} · Brain: PROJECT_BRAIN.json · "
            f"{n_features} features · {n_screens} screens · {total} components*"
        )
        lines.append("")
        lines.append(f"## Progress: {done}/{total} components ({pct}%)")
        lines.append(bar)
        lines.append("")
        lines.append("---")
        lines.append("")

        if brain.features:
            for feature in sorted(brain.features, key=lambda f: f.priority):
                lines.extend(self._feature_section(brain, feature))
                lines.append("")
        else:
            # No features defined — show flat screen list
            lines.extend(self._flat_screen_section(brain))

        lines.extend(self._session_log_section(brain))
        return "\n".join(lines) + "\n"

    def update_brain_status(
        self,
        brain: ProjectBrain,
        template: str,
        target_id: str,
        success: bool,
    ) -> None:
        """Update GenerationStatus and session log in the brain (in-memory only).

        Call before BrainManager.save() so everything is persisted in one write.
        """
        if not success:
            return

        component = _TEMPLATE_TO_COMPONENT.get(template)
        if not component:
            return

        screen_ids = self._resolve_screen_ids(brain, component, target_id)
        now = utc_now()
        built_labels: list[str] = []

        for sid in screen_ids:
            status = self._get_or_create_status(brain, sid)
            setattr(status.components, component, True)
            status.last_generated = now
            built_labels.append(f"{sid}.{component}")

        # Promote feature statuses
        for feature in brain.features:
            new_status = self._compute_feature_status(brain, feature)
            if feature.status != new_status:
                feature.status = new_status

        # Append to today's session entry
        if built_labels:
            self._append_session(brain, built_labels, brain.features)

    def mark_validated(self, brain: ProjectBrain, screen_id: str) -> None:
        """Mark a screen's validated flag (called from validate_mvvm when all pass)."""
        status = self._get_or_create_status(brain, screen_id)
        status.components.validated = True
        status.last_validated = utc_now()
        for feature in brain.features:
            new_status = self._compute_feature_status(brain, feature)
            feature.status = new_status

    def next_step(self, brain: ProjectBrain) -> str | None:
        """Return the most valuable next generation call, or None if everything is done."""
        unblocked = self._unblocked_features(brain)
        for feature in unblocked:
            for screen_id in feature.screens:
                status = self._get_status(brain, screen_id)
                call = self._next_component_call(status, screen_id)
                if call:
                    return call
        # All features blocked or complete — try any screen with no feature assignment
        orphan_screens = self._orphan_screens(brain)
        for screen_id in orphan_screens:
            status = self._get_status(brain, screen_id)
            call = self._next_component_call(status, screen_id)
            if call:
                return call
        return None

    # ── Section builders ─────────────────────────────────────────────

    def _feature_section(self, brain: ProjectBrain, feature: Feature) -> list[str]:
        lines: list[str] = []
        done, total = self._feature_counts(brain, feature)
        pct = int(done / total * 100) if total else 0

        status_badge = {
            "complete": "COMPLETE ✓",
            "in_progress": "IN PROGRESS",
            "planned": "PLANNED",
        }.get(feature.status, feature.status.upper())

        dep_names = self._dep_names(brain, feature)
        dep_str = f"*Dependencies: {dep_names}*" if dep_names else "*Dependencies: none*"
        blocked = self._is_blocked(brain, feature)

        lines.append(f"## Feature {feature.priority}: {feature.name} [{status_badge}]")
        lines.append(dep_str)
        if feature.description:
            lines.append(f"*{feature.description}*")
        lines.append(f"*Progress: {done}/{total} ({pct}%)*")
        lines.append("")

        if blocked and feature.status != "complete":
            blocking = [
                f.name for f in brain.features
                if f.id in feature.feature_dependencies and f.status != "complete"
            ]
            lines.append(f"**Blocked by:** {', '.join(blocking)}")
            lines.append("")
            return lines

        if not feature.screens:
            lines.append("*No screens defined for this feature.*")
            return lines

        # Table header
        lines.append("| Screen | VM | State | Repo | Scaffold | DI | Nav | Tests | Valid |")
        lines.append("|--------|----|-------|------|----------|----|-----|-------|-------|")

        for screen_id in feature.screens:
            status = self._get_status(brain, screen_id)
            c = status.components
            row = (
                f"| {screen_id} "
                f"| {'✓' if c.viewmodel else '✗'} "
                f"| {'✓' if c.ui_state else '✗'} "
                f"| {'✓' if c.repository else '✗'} "
                f"| {'✓' if c.scaffold else '✗'} "
                f"| {'✓' if c.di_module else '✗'} "
                f"| {'✓' if c.nav_route else '✗'} "
                f"| {'✓' if c.tests else '✗'} "
                f"| {'✓' if c.validated else '✗'} |"
            )
            lines.append(row)

        lines.append("")
        if feature.status != "complete":
            nxt = self._next_for_feature(brain, feature)
            if nxt:
                lines.append(f"**Next:** `{nxt}`")

        return lines

    def _flat_screen_section(self, brain: ProjectBrain) -> list[str]:
        """Fallback when no features are defined — show all screens in a flat table."""
        lines: list[str] = []
        lines.append("## All Screens")
        lines.append("")
        lines.append("| Screen | VM | State | Repo | Scaffold | DI | Nav | Tests | Valid |")
        lines.append("|--------|----|-------|------|----------|----|-----|-------|-------|")
        for screen in brain.screens:
            status = self._get_status(brain, screen.id)
            c = status.components
            row = (
                f"| {screen.id} "
                f"| {'✓' if c.viewmodel else '✗'} "
                f"| {'✓' if c.ui_state else '✗'} "
                f"| {'✓' if c.repository else '✗'} "
                f"| {'✓' if c.scaffold else '✗'} "
                f"| {'✓' if c.di_module else '✗'} "
                f"| {'✓' if c.nav_route else '✗'} "
                f"| {'✓' if c.tests else '✗'} "
                f"| {'✓' if c.validated else '✗'} |"
            )
            lines.append(row)
        lines.append("")
        nxt = self.next_step(brain)
        if nxt:
            lines.append(f"**Next:** `{nxt}`")
        lines.append("")
        return lines

    def _session_log_section(self, brain: ProjectBrain) -> list[str]:
        lines: list[str] = ["---", "", "## Session Log", ""]
        if not brain.session_log:
            lines.append("*(No sessions yet — start with `get_session_context()`)*")
            lines.append("")
            return lines

        for entry in reversed(brain.session_log[-10:]):  # last 10 sessions
            lines.append(f"### {entry.date}")
            if entry.components_built:
                lines.append(f"- Built: {', '.join(entry.components_built)}")
            if entry.features_completed:
                lines.append(f"- Completed features: {', '.join(entry.features_completed)}")
            lines.append("")

        nxt = self.next_step(brain)
        lines.append("### Next Session")
        lines.append("Start with: `get_session_context()` or `get_next_task()`")
        if nxt:
            lines.append(f"Recommended: `{nxt}`")
        return lines

    # ── Helpers ──────────────────────────────────────────────────────

    def _resolve_screen_ids(
        self, brain: ProjectBrain, component: str, target_id: str
    ) -> list[str]:
        if component in ("viewmodel", "ui_state", "scaffold", "nav_route", "tests"):
            # target_id is the screen_id
            if any(s.id == target_id for s in brain.screens):
                return [target_id]
            return []
        if component == "repository":
            # find screens that reference this repository
            ids = [s.id for s in brain.screens if s.repository == target_id]
            # also check viewmodels
            for vm in brain.viewmodels:
                if vm.repository == target_id and vm.screen:
                    if vm.screen not in ids:
                        ids.append(vm.screen)
            return ids if ids else [target_id]  # fallback: treat as screen_id
        if component == "di_module":
            # target_id is the feature name/id — mark all screens in that feature
            feature = next((f for f in brain.features if f.id == target_id or f.name.lower() == target_id.lower()), None)
            return feature.screens if feature else []
        return []

    def _get_or_create_status(self, brain: ProjectBrain, screen_id: str) -> GenerationStatus:
        for s in brain.generation_status:
            if s.screen_id == screen_id:
                return s
        new = GenerationStatus(screen_id=screen_id)
        brain.generation_status.append(new)
        return new

    def _get_status(self, brain: ProjectBrain, screen_id: str) -> GenerationStatus:
        for s in brain.generation_status:
            if s.screen_id == screen_id:
                return s
        return GenerationStatus(screen_id=screen_id)  # read-only default

    def _compute_feature_status(self, brain: ProjectBrain, feature: Feature) -> str:
        if not feature.screens:
            return feature.status
        statuses = [self._get_status(brain, sid) for sid in feature.screens]
        if all(s.components.all_generated for s in statuses):
            return "complete"
        if any(s.components.done_count() > 0 for s in statuses):
            return "in_progress"
        return "planned"

    def _is_blocked(self, brain: ProjectBrain, feature: Feature) -> bool:
        for dep_id in feature.feature_dependencies:
            dep = next((f for f in brain.features if f.id == dep_id), None)
            if dep and dep.status != "complete":
                return True
        return False

    def _unblocked_features(self, brain: ProjectBrain) -> list[Feature]:
        result = []
        for f in sorted(brain.features, key=lambda x: x.priority):
            if f.status != "complete" and not self._is_blocked(brain, f):
                result.append(f)
        return result

    def _orphan_screens(self, brain: ProjectBrain) -> list[str]:
        assigned = {sid for f in brain.features for sid in f.screens}
        return [s.id for s in brain.screens if s.id not in assigned]

    def _next_component_call(self, status: GenerationStatus, screen_id: str) -> str | None:
        c = status.components
        if not c.viewmodel:
            return f'generate_viewmodel("{screen_id}")'
        if not c.ui_state:
            return f'generate_ui_state("{screen_id}")'
        if not c.repository:
            return f'generate_repository("{screen_id}")'
        if not c.scaffold:
            return f'generate_screen_scaffold("{screen_id}")'
        if not c.nav_route:
            return f'generate_nav_route("{screen_id}")'
        if not c.di_module:
            return f'generate_di_module("{screen_id}")'
        if not c.tests:
            return f'generate_viewmodel_test("{screen_id}")'
        if not c.validated:
            return f'validate_mvvm("{screen_id}.kt")'
        return None

    def _next_for_feature(self, brain: ProjectBrain, feature: Feature) -> str | None:
        for screen_id in feature.screens:
            status = self._get_status(brain, screen_id)
            call = self._next_component_call(status, screen_id)
            if call:
                return call
        return None

    def _overall_counts(self, brain: ProjectBrain) -> tuple[int, int]:
        if brain.generation_status:
            done = sum(s.components.done_count() for s in brain.generation_status)
            total = len(brain.generation_status) * _TOTAL_COMPONENTS
            return done, total
        # Fall back to screens list
        total = len(brain.screens) * _TOTAL_COMPONENTS
        return 0, total

    def _feature_counts(self, brain: ProjectBrain, feature: Feature) -> tuple[int, int]:
        done = 0
        total = len(feature.screens) * _TOTAL_COMPONENTS
        for sid in feature.screens:
            done += self._get_status(brain, sid).components.done_count()
        return done, total

    def _dep_names(self, brain: ProjectBrain, feature: Feature) -> str:
        names = []
        for dep_id in feature.feature_dependencies:
            dep = next((f for f in brain.features if f.id == dep_id), None)
            if dep:
                tick = " ✓" if dep.status == "complete" else " ✗"
                names.append(dep.name + tick)
        return ", ".join(names) if names else ""

    def _append_session(
        self, brain: ProjectBrain, built: list[str], features: list[Feature]
    ) -> None:
        today = _today()
        completed_now = [f.name for f in features if f.status == "complete"]

        existing = next((e for e in brain.session_log if e.date == today), None)
        if existing:
            existing.components_built.extend(built)
            for name in completed_now:
                if name not in existing.features_completed:
                    existing.features_completed.append(name)
        else:
            brain.session_log.append(
                SessionEntry(
                    date=today,
                    components_built=list(built),
                    features_completed=completed_now,
                )
            )

    @staticmethod
    def _progress_bar(pct: int) -> str:
        filled = int(pct / 5)
        empty = 20 - filled
        return f"[{'█' * filled}{'░' * empty}] {pct}%"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
