"""Zero-LLM read tools for PROJECT_BRAIN.json."""

from __future__ import annotations

from typing import Any

from project_brain.brain.schema import (
    BusinessRule,
    DataModel,
    ProjectBrain,
    Repository,
    Screen,
    StateMachine,
    ViewModel,
)


class ReadTools:
    """Read-only tool facade over a loaded ProjectBrain."""

    def __init__(self, brain: ProjectBrain) -> None:
        self.brain = brain

    def get_project_context(self) -> dict[str, Any]:
        """Return project name, architecture, phase summary, and design system."""

        return {
            "meta": dump(self.brain.meta),
            "summary": self.brain.summary(),
            "phase_summary": [
                {
                    "number": phase.number,
                    "name": phase.name,
                    "status": phase.status,
                    "screen_count": len(phase.screens),
                    "completion_percent": self._phase_completion_percent(phase.number),
                }
                for phase in self.brain.phases
            ],
            "design_system": dump(self.brain.design_system),
            "user_roles": dump_list(self.brain.user_roles),
        }

    def get_screen_graph(self, screen_id: str) -> dict[str, Any]:
        """Return a screen with ViewModel, Repository, model, and navigation links."""

        screen = self._screen(screen_id)
        viewmodel = self._viewmodel(screen.viewmodel)
        repository = self._repository(screen.repository or (viewmodel.repository if viewmodel else None))
        return {
            "screen": dump(screen),
            "viewmodel": dump(viewmodel),
            "repository": dump(repository),
            "models": dump_list([self._data_model(model_id) for model_id in screen.models]),
            "navigation": {
                "parent_screen": screen.parent_screen,
                "child_screens": screen.child_screens,
                "nav_args": screen.nav_args,
                "routes": [
                    dump(route)
                    for route in self.brain.navigation_graph.routes
                    if route.screen == screen.id or route.id == screen.route or screen.id in route.next
                ],
            },
            "business_rules": dump_list(self._related_business_rules(screen)),
        }

    def get_phase_status(self, phase: int) -> dict[str, Any]:
        """Return completion status and blockers for a phase."""

        phase_item = next((item for item in self.brain.phases if item.number == phase), None)
        phase_screen_ids = set(phase_item.screens if phase_item else [])
        if not phase_screen_ids:
            phase_screen_ids = {screen.id for screen in self.brain.screens if screen.phase == phase}

        screens = [screen for screen in self.brain.screens if screen.id in phase_screen_ids or screen.phase == phase]
        done = [screen for screen in screens if screen.generated or screen.status.lower() in {"complete", "completed", "done"}]
        pending = [screen for screen in screens if screen not in done]
        blockers = [
            violation
            for violation in self.brain.known_violations
            if not violation.resolved and any(screen.id in f"{violation.location} {violation.message}" for screen in screens)
        ]
        return {
            "phase": dump(phase_item) if phase_item else {"number": phase, "status": "unknown"},
            "completion_percent": round((len(done) / len(screens)) * 100, 2) if screens else 0.0,
            "screens_done": [screen.id for screen in done],
            "screens_pending": [screen.id for screen in pending],
            "blocking_violations": dump_list(blockers),
        }

    def get_all_screens(self) -> dict[str, Any]:
        """Return all screens with status, phase, and compliance state."""

        return {
            "screens": [
                {
                    "id": screen.id,
                    "route": screen.route,
                    "phase": screen.phase,
                    "status": screen.status,
                    "generated": screen.generated,
                    "mvvm_compliant": screen.mvvm_compliant,
                    "viewmodel": screen.viewmodel,
                    "repository": screen.repository,
                    "file_path": screen.file_path,
                }
                for screen in self.brain.screens
            ]
        }

    def get_dependencies(self, screen_id: str) -> dict[str, Any]:
        """Return required preconditions before building a screen."""

        screen = self._screen(screen_id)
        viewmodel = self._viewmodel(screen.viewmodel)
        repository = self._repository(screen.repository or (viewmodel.repository if viewmodel else None))
        dependencies = {
            "screen_id": screen.id,
            "viewmodel": screen.viewmodel,
            "repository": screen.repository or (viewmodel.repository if viewmodel else None),
            "use_cases": sorted(set(screen.use_cases + (viewmodel.use_cases if viewmodel else []))),
            "models": screen.models,
            "firestore_listeners": screen.firestore_listeners,
            "nav_args": screen.nav_args,
        }
        missing = []
        if dependencies["viewmodel"] and not viewmodel:
            missing.append(f"ViewModel not found: {dependencies['viewmodel']}")
        if dependencies["repository"] and not repository:
            missing.append(f"Repository not found: {dependencies['repository']}")
        for model_id in screen.models:
            if not self._data_model(model_id):
                missing.append(f"Data model not found: {model_id}")
        return {"dependencies": dependencies, "missing": missing}

    def get_firestore_schema(self) -> dict[str, Any]:
        """Return all Firestore collections, fields, and consistency rules."""

        return dump(self.brain.firestore_schema)

    def get_business_rules(self) -> dict[str, Any]:
        """Return all business rules with triggers and required updates."""

        return {"business_rules": dump_list(self.brain.business_rules)}

    def get_state_machine(self, entity: str) -> dict[str, Any]:
        """Return the full state machine for an entity."""

        machine = self._state_machine(entity)
        if not machine:
            raise KeyError(f"State machine not found: {entity}")
        return dump(machine)

    def get_design_tokens(self) -> dict[str, Any]:
        """Return design system values and token rules."""

        return dump(self.brain.design_system)

    def get_navigation_graph(self) -> dict[str, Any]:
        """Return the full navigation graph."""

        return dump(self.brain.navigation_graph)

    def _screen(self, screen_id: str) -> Screen:
        screen = next((item for item in self.brain.screens if item.id == screen_id), None)
        if not screen:
            raise KeyError(f"Screen not found: {screen_id}")
        return screen

    def _viewmodel(self, viewmodel_id: str | None) -> ViewModel | None:
        if not viewmodel_id:
            return None
        return next((item for item in self.brain.viewmodels if item.id == viewmodel_id), None)

    def _repository(self, repository_id: str | None) -> Repository | None:
        if not repository_id:
            return None
        return next((item for item in self.brain.repositories if item.id == repository_id), None)

    def _data_model(self, model_id: str | None) -> DataModel | None:
        if not model_id:
            return None
        return next((item for item in self.brain.data_models if item.id == model_id), None)

    def _state_machine(self, entity: str) -> StateMachine | None:
        return next((item for item in self.brain.state_machines if item.entity.lower() == entity.lower()), None)

    def _related_business_rules(self, screen: Screen) -> list[BusinessRule]:
        searchable = " ".join([screen.id, screen.viewmodel or "", screen.repository or "", *screen.models])
        return [
            rule
            for rule in self.brain.business_rules
            if any(token and token in f"{rule.description} {rule.trigger} {' '.join(rule.required_updates)}" for token in searchable.split())
        ]

    def _phase_completion_percent(self, phase_number: int) -> float:
        phase_screens = [screen for screen in self.brain.screens if screen.phase == phase_number]
        if not phase_screens:
            phase = next((item for item in self.brain.phases if item.number == phase_number), None)
            phase_screens = [screen for screen in self.brain.screens if phase and screen.id in phase.screens]
        if not phase_screens:
            return 0.0
        done = [screen for screen in phase_screens if screen.generated or screen.status.lower() in {"complete", "completed", "done"}]
        return round((len(done) / len(phase_screens)) * 100, 2)


def get_project_context(brain: ProjectBrain) -> dict[str, Any]:
    return ReadTools(brain).get_project_context()


def get_screen_graph(brain: ProjectBrain, screen_id: str) -> dict[str, Any]:
    return ReadTools(brain).get_screen_graph(screen_id)


def get_phase_status(brain: ProjectBrain, phase: int) -> dict[str, Any]:
    return ReadTools(brain).get_phase_status(phase)


def get_all_screens(brain: ProjectBrain) -> dict[str, Any]:
    return ReadTools(brain).get_all_screens()


def get_dependencies(brain: ProjectBrain, screen_id: str) -> dict[str, Any]:
    return ReadTools(brain).get_dependencies(screen_id)


def get_firestore_schema(brain: ProjectBrain) -> dict[str, Any]:
    return ReadTools(brain).get_firestore_schema()


def get_business_rules(brain: ProjectBrain) -> dict[str, Any]:
    return ReadTools(brain).get_business_rules()


def get_state_machine(brain: ProjectBrain, entity: str) -> dict[str, Any]:
    return ReadTools(brain).get_state_machine(entity)


def get_design_tokens(brain: ProjectBrain) -> dict[str, Any]:
    return ReadTools(brain).get_design_tokens()


def get_navigation_graph(brain: ProjectBrain) -> dict[str, Any]:
    return ReadTools(brain).get_navigation_graph()


def dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True, mode="json")
    return value


def dump_list(values: list[Any]) -> list[Any]:
    return [dump(value) for value in values if value is not None]
