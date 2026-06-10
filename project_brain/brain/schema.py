"""Canonical PROJECT_BRAIN.json schema."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base model that rejects unexpected fields."""

    model_config = ConfigDict(extra="forbid")


class Meta(StrictModel):
    project_name: str
    version: str = "1.0.0"
    created_at: str = Field(default_factory=lambda: utc_now())
    last_synced: str = Field(default_factory=lambda: utc_now())
    entry_point: Literal["prd", "codebase"]
    architecture: str = "MVVM+Hilt+Compose+Firebase"
    package_name: str | None = None
    min_sdk: int | None = 26
    target_sdk: int | None = 35
    brain_version: str = "1.0"


class DesignSystem(StrictModel):
    name: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    font_heading: str | None = None
    font_body: str | None = None
    token_rules: list[str] = Field(default_factory=list)


class UserRole(StrictModel):
    id: str
    name: str
    description: str | None = None
    app_module: str | None = None


class DataField(StrictModel):
    name: str
    type: str
    nullable: bool = False


class ConsistencyLink(StrictModel):
    field: str
    linked_to: str
    rule: str


class DataModel(StrictModel):
    id: str
    fields: list[DataField] = Field(default_factory=list)
    firestore_collection: str | None = None
    consistency_links: list[ConsistencyLink] = Field(default_factory=list)


class RequiredUpdate(StrictModel):
    value: str


class StateTransition(StrictModel):
    from_state: str = Field(alias="from")
    to: str
    required_firestore_updates: list[str] = Field(default_factory=list)
    recommended_implementation: str | None = None
    missing_any: str | None = None


class StateMachine(StrictModel):
    entity: str
    states: list[str] = Field(default_factory=list)
    transitions: list[StateTransition] = Field(default_factory=list)


class Screen(StrictModel):
    id: str
    route: str | None = None
    phase: int | None = None
    status: str = "pending"
    mvvm_compliant: bool | None = None
    viewmodel: str | None = None
    repository: str | None = None
    use_cases: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    parent_screen: str | None = None
    child_screens: list[str] = Field(default_factory=list)
    nav_args: list[str] = Field(default_factory=list)
    ui_states: list[str] = Field(default_factory=list)
    stateflows: list[str] = Field(default_factory=list)
    firestore_listeners: list[str] = Field(default_factory=list)
    design_tokens_used: list[str] = Field(default_factory=list)
    generated: bool = False
    file_path: str | None = None
    last_generated: str | None = None


class ViewModelFunction(StrictModel):
    name: str
    params: list[str] = Field(default_factory=list)
    returns: str = "Unit"
    business_rule: str | None = None
    concurrent: bool = False
    state_updates: list[str] = Field(default_factory=list)
    events_fired: list[str] = Field(default_factory=list)


class StateField(StrictModel):
    name: str
    type: str
    nullable: bool = False
    default: str = "false"


class EventSpec(StrictModel):
    name: str
    has_data: bool = False
    data: str | None = None


class DataSource(StrictModel):
    param_name: str
    type: str
    import_path: str | None = None


class ViewModel(StrictModel):
    id: str
    screen: str | None = None
    repository: str | None = None
    use_cases: list[str] = Field(default_factory=list)
    inject_dependencies: list[str] = Field(default_factory=list)
    ui_state_class: str | None = None
    functions: list[ViewModelFunction] = Field(default_factory=list)
    generated: bool = False
    mvvm_compliant: bool | None = None
    file_path: str | None = None
    # v2 enriched fields
    ui_state_type: str = "sealed_class"
    event_class: str | None = None
    has_mutex: bool = False
    has_saved_state: bool = False
    state_fields: list[StateField] = Field(default_factory=list)
    events: list[EventSpec] = Field(default_factory=list)


class RepositoryMethod(StrictModel):
    name: str
    params: list[str] = Field(default_factory=list)
    returns: str | None = None
    firestore_path: str | None = None
    result_wrapped: bool = False
    is_flow: bool = False
    result_type: str | None = None
    flow_type: str | None = None


class Repository(StrictModel):
    id: str
    interface: str | None = None
    implementation: str | None = None
    data_sources: list[str] = Field(default_factory=list)
    methods: list[RepositoryMethod] = Field(default_factory=list)
    generated: bool = False
    file_path: str | None = None
    typed_data_sources: list[DataSource] = Field(default_factory=list)


class NavigationRoute(StrictModel):
    id: str
    screen: str | None = None
    next: list[str] = Field(default_factory=list)


class NavigationGraph(StrictModel):
    start_destination: str | None = None
    routes: list[NavigationRoute] = Field(default_factory=list)


class FirestoreCollection(StrictModel):
    path: str
    fields: list[str] = Field(default_factory=list)
    consistency_rules: list[str] = Field(default_factory=list)


class FirestoreSchema(StrictModel):
    collections: list[FirestoreCollection] = Field(default_factory=list)


class Phase(StrictModel):
    number: int
    name: str
    status: str = "pending"
    screens: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)


class BusinessRule(StrictModel):
    id: str
    description: str
    trigger: str | None = None
    required_updates: list[str] = Field(default_factory=list)
    missing_any: str | None = None
    enforcement: str | None = None


class KnownViolation(StrictModel):
    id: str
    severity: str
    message: str
    location: str | None = None
    confidence: float | None = None
    resolved: bool = False


class GenerationHistoryEntry(StrictModel):
    tool: str
    target: str
    generated_at: str = Field(default_factory=lambda: utc_now())
    output_path: str | None = None
    status: str
    notes: str | None = None


# ── Phase 0C: Roadmap & Feature Pipeline ────────────────────────────────────


class ComponentStatus(StrictModel):
    """Per-screen generation completion flags."""

    viewmodel: bool = False
    ui_state: bool = False
    repository: bool = False
    scaffold: bool = False
    di_module: bool = False
    nav_route: bool = False
    tests: bool = False
    validated: bool = False

    @property
    def all_generated(self) -> bool:
        return all([
            self.viewmodel, self.ui_state, self.repository,
            self.scaffold, self.di_module, self.nav_route, self.tests,
        ])

    @property
    def all_complete(self) -> bool:
        return self.all_generated and self.validated

    def done_count(self) -> int:
        return sum([
            self.viewmodel, self.ui_state, self.repository,
            self.scaffold, self.di_module, self.nav_route, self.tests, self.validated,
        ])


class GenerationStatus(StrictModel):
    screen_id: str
    components: ComponentStatus = Field(default_factory=ComponentStatus)
    last_generated: str | None = None
    last_validated: str | None = None


class SessionEntry(StrictModel):
    date: str
    components_built: list[str] = Field(default_factory=list)
    features_completed: list[str] = Field(default_factory=list)


class Feature(StrictModel):
    id: str
    name: str
    description: str = ""
    screens: list[str] = Field(default_factory=list)       # screen ids
    priority: int = 0                                       # 1 = first to build
    status: str = "planned"                                 # planned|in_progress|complete
    feature_dependencies: list[str] = Field(default_factory=list)  # feature ids


class ProjectBrain(StrictModel):
    meta: Meta
    design_system: DesignSystem = Field(default_factory=DesignSystem)
    user_roles: list[UserRole] = Field(default_factory=list)
    data_models: list[DataModel] = Field(default_factory=list)
    state_machines: list[StateMachine] = Field(default_factory=list)
    screens: list[Screen] = Field(default_factory=list)
    viewmodels: list[ViewModel] = Field(default_factory=list)
    repositories: list[Repository] = Field(default_factory=list)
    navigation_graph: NavigationGraph = Field(default_factory=NavigationGraph)
    firestore_schema: FirestoreSchema = Field(default_factory=FirestoreSchema)
    phases: list[Phase] = Field(default_factory=list)
    business_rules: list[BusinessRule] = Field(default_factory=list)
    known_violations: list[KnownViolation] = Field(default_factory=list)
    generation_history: list[GenerationHistoryEntry] = Field(default_factory=list)
    # Phase 0C
    features: list[Feature] = Field(default_factory=list)
    generation_status: list[GenerationStatus] = Field(default_factory=list)
    session_log: list[SessionEntry] = Field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        done = sum(s.components.done_count() for s in self.generation_status)
        total = len(self.generation_status) * 8
        return {
            "project_name": self.meta.project_name,
            "entry_point": self.meta.entry_point,
            "screens": len(self.screens),
            "viewmodels": len(self.viewmodels),
            "repositories": len(self.repositories),
            "data_models": len(self.data_models),
            "state_machines": len(self.state_machines),
            "business_rules": len(self.business_rules),
            "known_violations": len([v for v in self.known_violations if not v.resolved]),
            "features": len(self.features),
            "components_done": done,
            "components_total": total,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

