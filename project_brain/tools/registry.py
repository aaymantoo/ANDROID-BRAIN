"""MCP tool registry for Phase 2-4 tools."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from project_brain.brain.schema import ProjectBrain
from project_brain.engines.rule_engine import MVVMValidationEngine
from project_brain.llm.adapter import LLMAdapter, NullAdapter, create_adapter
from project_brain.tools.generation_tools import GenerationTools
from project_brain.tools.read_tools import ReadTools
from project_brain.tools.roadmap_tools import (
    get_feature_status,
    get_next_task,
    get_project_roadmap,
    get_session_context,
)
from project_brain.tools.bug_tools import (
    audit_production_readiness_brain,
    detect_orphaned_documents_brain,
    detect_race_conditions_brain,
    forecast_bugs_brain,
)
from project_brain.tools.management_tools import sync_brain_instance
from project_brain.tools.incremental_tools import (
    aggregate_brain_cache,
    get_enrichment_status,
    get_feature_artifacts,
)
from project_brain.tools.validation_tools import (
    validate_design_tokens_brain,
    validate_firestore_consistency_brain,
    validate_generation_brain,
    validate_naming_conventions_brain,
    validate_state_transitions_brain,
)


JsonDict = dict[str, Any]
Executor = Callable[[JsonDict], JsonDict | Awaitable[JsonDict]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: JsonDict
    executor: Executor

    async def execute(self, arguments: JsonDict | None = None) -> JsonDict:
        result = self.executor(arguments or {})
        if inspect.isawaitable(result):
            return await result
        return result

    def to_mcp_tool(self):
        from mcp.types import Tool

        return Tool(name=self.name, description=self.description, inputSchema=self.input_schema)


class ToolRegistry:
    """In-memory registry initialized with a loaded ProjectBrain."""

    def __init__(
        self,
        brain: ProjectBrain,
        llm: LLMAdapter | None = None,
        brain_path: str = "PROJECT_BRAIN.json",
    ) -> None:
        self.brain = brain
        self.read_tools = ReadTools(brain)
        self.generation_tools = GenerationTools(brain, llm or NullAdapter(), brain_path=brain_path)
        self._tools = self._build_tools()

    def list_definitions(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def list_mcp_tools(self):
        return [tool.to_mcp_tool() for tool in self.list_definitions()]

    async def execute(self, name: str, arguments: JsonDict | None = None) -> JsonDict:
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"Unknown tool: {name}")
        return await tool.execute(arguments)

    def _build_tools(self) -> dict[str, ToolDefinition]:
        no_arg = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
        screen_arg = {
            "type": "object",
            "properties": {"screen_id": {"type": "string"}},
            "required": ["screen_id"],
            "additionalProperties": False,
        }
        phase_arg = {
            "type": "object",
            "properties": {"phase": {"type": "integer"}},
            "required": ["phase"],
            "additionalProperties": False,
        }
        entity_arg = {
            "type": "object",
            "properties": {"entity": {"type": "string"}},
            "required": ["entity"],
            "additionalProperties": False,
        }
        file_arg = {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
            "additionalProperties": False,
        }
        generate_arg = {
            "type": "object",
            "properties": {
                "screen_id": {"type": "string"},
                "output_path": {"type": "string"},
            },
            "required": ["screen_id"],
            "additionalProperties": False,
        }
        generate_repo_arg = {
            "type": "object",
            "properties": {
                "repository_id": {"type": "string"},
                "output_path": {"type": "string"},
            },
            "required": ["repository_id"],
            "additionalProperties": False,
        }
        generate_model_arg = {
            "type": "object",
            "properties": {
                "model_id": {"type": "string"},
                "output_path": {"type": "string"},
            },
            "required": ["model_id"],
            "additionalProperties": False,
        }
        generate_usecase_arg = {
            "type": "object",
            "properties": {
                "usecase_name": {"type": "string"},
                "output_path": {"type": "string"},
            },
            "required": ["usecase_name"],
            "additionalProperties": False,
        }
        generate_di_arg = {
            "type": "object",
            "properties": {
                "feature_name": {"type": "string"},
                "output_path": {"type": "string"},
            },
            "required": ["feature_name"],
            "additionalProperties": False,
        }
        state_transition_arg = {
            "type": "object",
            "properties": {"entity": {"type": "string"}, "file_path": {"type": "string"}},
            "required": ["entity", "file_path"],
            "additionalProperties": False,
        }
        validation_engine = MVVMValidationEngine()

        tools = [
            ToolDefinition(
                "get_project_context",
                "Return project name, phase summary, architecture, design system, and user roles.",
                no_arg,
                lambda _: self.read_tools.get_project_context(),
            ),
            ToolDefinition(
                "get_screen_graph",
                "Return a screen plus its ViewModel, Repository, models, navigation links, and related rules.",
                screen_arg,
                lambda args: self.read_tools.get_screen_graph(str(args["screen_id"])),
            ),
            ToolDefinition(
                "get_phase_status",
                "Return completion percentage, done/pending screens, and blocking violations for a phase.",
                phase_arg,
                lambda args: self.read_tools.get_phase_status(int(args["phase"])),
            ),
            ToolDefinition(
                "get_all_screens",
                "Return all screens with status, phase, generated flag, and compliance state.",
                no_arg,
                lambda _: self.read_tools.get_all_screens(),
            ),
            ToolDefinition(
                "get_dependencies",
                "Return required preconditions before building a screen.",
                screen_arg,
                lambda args: self.read_tools.get_dependencies(str(args["screen_id"])),
            ),
            ToolDefinition(
                "get_firestore_schema",
                "Return all Firestore collections, fields, and consistency rules.",
                no_arg,
                lambda _: self.read_tools.get_firestore_schema(),
            ),
            ToolDefinition(
                "get_business_rules",
                "Return all business rules with triggers and required updates.",
                no_arg,
                lambda _: self.read_tools.get_business_rules(),
            ),
            ToolDefinition(
                "get_state_machine",
                "Return the full state machine for an entity.",
                entity_arg,
                lambda args: self.read_tools.get_state_machine(str(args["entity"])),
            ),
            ToolDefinition(
                "get_design_tokens",
                "Return design system values and token rules.",
                no_arg,
                lambda _: self.read_tools.get_design_tokens(),
            ),
            ToolDefinition(
                "get_navigation_graph",
                "Return the full navigation graph.",
                no_arg,
                lambda _: self.read_tools.get_navigation_graph(),
            ),
            ToolDefinition(
                "validate_mvvm",
                "Validate a Kotlin file for deterministic MVVM rule compliance.",
                file_arg,
                lambda args: validation_engine.validate_file(str(args["file_path"])).to_dict(),
            ),
            ToolDefinition(
                "validate_phase",
                "Validate all known files for a brain phase.",
                phase_arg,
                lambda args: validation_engine.validate_phase_brain(int(args["phase"]), self.brain).to_dict(),
            ),
            ToolDefinition(
                "validate_firestore_consistency",
                "Check brain business rules against Firestore consistency declarations.",
                no_arg,
                lambda _: validate_firestore_consistency_brain(self.brain),
            ),
            ToolDefinition(
                "validate_state_transitions",
                "Check that a file contains required updates for an entity's state transitions.",
                state_transition_arg,
                lambda args: validate_state_transitions_brain(str(args["entity"]), str(args["file_path"]), self.brain),
            ),
            ToolDefinition(
                "validate_design_tokens",
                "Check for disallowed design-token usage from brain token rules.",
                file_arg,
                lambda args: validate_design_tokens_brain(str(args["file_path"]), self.brain),
            ),
            ToolDefinition(
                "validate_naming_conventions",
                "Check Kotlin naming conventions against brain and MVVM naming.",
                file_arg,
                lambda args: validate_naming_conventions_brain(str(args["file_path"]), self.brain),
            ),
            # ── Phase 4: Generation tools ─────────────────────────────
            ToolDefinition(
                "generate_viewmodel",
                "Generate a compliant HiltViewModel .kt file for a screen (LLM fills function bodies).",
                generate_arg,
                lambda args: self.generation_tools.generate_viewmodel(
                    str(args["screen_id"]), args.get("output_path")
                ),
            ),
            ToolDefinition(
                "generate_ui_state",
                "Generate a sealed UiState class for a screen.",
                generate_arg,
                lambda args: self.generation_tools.generate_ui_state(
                    str(args["screen_id"]), args.get("output_path")
                ),
            ),
            ToolDefinition(
                "generate_repository",
                "Generate Repository interface and implementation .kt files.",
                generate_repo_arg,
                lambda args: self.generation_tools.generate_repository(
                    str(args["repository_id"]), args.get("output_path")
                ),
            ),
            ToolDefinition(
                "generate_datamodel",
                "Generate a data class .kt file from the brain schema (zero-LLM).",
                generate_model_arg,
                lambda args: self.generation_tools.generate_datamodel(
                    str(args["model_id"]), args.get("output_path")
                ),
            ),
            ToolDefinition(
                "generate_screen_scaffold",
                "Generate a Composable screen scaffold with ViewModel injection and UiState handling.",
                generate_arg,
                lambda args: self.generation_tools.generate_screen_scaffold(
                    str(args["screen_id"]), args.get("output_path")
                ),
            ),
            ToolDefinition(
                "generate_usecase",
                "Generate a UseCase class with an invoke() operator.",
                generate_usecase_arg,
                lambda args: self.generation_tools.generate_usecase(
                    str(args["usecase_name"]), args.get("output_path")
                ),
            ),
            ToolDefinition(
                "generate_di_module",
                "Generate a Hilt @Module that binds repository interfaces to implementations.",
                generate_di_arg,
                lambda args: self.generation_tools.generate_di_module(
                    str(args["feature_name"]), args.get("output_path")
                ),
            ),
            ToolDefinition(
                "generate_nav_route",
                "Generate a type-safe navigation route object from the brain screen spec.",
                generate_arg,
                lambda args: self.generation_tools.generate_nav_route(
                    str(args["screen_id"]), args.get("output_path")
                ),
            ),
            ToolDefinition(
                "generate_viewmodel_test",
                "Generate a ViewModel unit test scaffold with coroutine test dispatcher setup.",
                generate_arg,
                lambda args: self.generation_tools.generate_viewmodel_test(
                    str(args["screen_id"]), args.get("output_path")
                ),
            ),
            # ── Phase 5: Bug Forecasting tools ───────────────────────
            ToolDefinition(
                "forecast_bugs",
                "Run all 5 predictive bug detectors (state transitions, consistency, race conditions, listener leaks, revenue integrity) for a screen.",
                screen_arg,
                lambda args: forecast_bugs_brain(self.brain, str(args["screen_id"])),
            ),
            ToolDefinition(
                "detect_race_conditions",
                "Scan all generated files for Firestore read-then-write patterns without transactions.",
                no_arg,
                lambda _: detect_race_conditions_brain(self.brain),
            ),
            ToolDefinition(
                "detect_orphaned_documents",
                "Detect data_model consistency_link violations that would produce orphaned Firestore documents.",
                no_arg,
                lambda _: detect_orphaned_documents_brain(self.brain),
            ),
            ToolDefinition(
                "audit_production_readiness",
                "Full pre-launch bug audit for all screens in a phase. Returns prioritised CLASS_A/B bug list.",
                phase_arg,
                lambda args: audit_production_readiness_brain(self.brain, int(args["phase"])),
            ),
            # ── Phase 5/6: validate_generation & sync_brain ──────────
            ToolDefinition(
                "validate_generation",
                "Compare generated files against Brain spec + ROADMAP.md + source PRD. Returns per-screen completeness % with brain_match / roadmap_match / prd_match verdict columns.",
                {
                    "type": "object",
                    "properties": {
                        "feature_id": {"type": "string"},
                        "phase": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
                lambda args: validate_generation_brain(
                    self.brain,
                    feature_id=args.get("feature_id"),
                    phase=args.get("phase"),
                ),
            ),
            ToolDefinition(
                "sync_brain",
                "Re-scan all previously generated files for drift from the brain spec. Adds drift items to brain.known_violations.",
                no_arg,
                lambda _: sync_brain_instance(self.brain).to_dict(),
            ),
            # ── Phase 0C: Roadmap & Pipeline tools ───────────────────
            ToolDefinition(
                "get_session_context",
                "Return last session summary, overall progress, current feature, and next recommended step. Call at the start of every session to resume without re-explaining context.",
                no_arg,
                lambda _: get_session_context(self.brain),
            ),
            ToolDefinition(
                "get_next_task",
                "Return the single most important next generation step with the exact tool call. Respects feature priority and dependency blocking.",
                no_arg,
                lambda _: get_next_task(self.brain),
            ),
            ToolDefinition(
                "get_feature_status",
                "Return component-level generation status for every screen in a feature.",
                {
                    "type": "object",
                    "properties": {"feature_id": {"type": "string"}},
                    "required": ["feature_id"],
                    "additionalProperties": False,
                },
                lambda args: get_feature_status(self.brain, str(args["feature_id"])),
            ),
            ToolDefinition(
                "get_project_roadmap",
                "Return the full feature → screen → component status tree for the entire project.",
                no_arg,
                lambda _: get_project_roadmap(self.brain),
            ),
            # ── Incremental Enrichment tools ─────────────────────────
            ToolDefinition(
                "get_enrichment_status",
                "Return the current incremental enrichment session status: completed / pending / failed features and the last checkpoint. Use to decide whether to call brain resume or start fresh.",
                no_arg,
                lambda _: get_enrichment_status(),
            ),
            ToolDefinition(
                "get_feature_artifacts",
                "Return all artifacts (screens, ViewModels, repositories, business rules, state machines) for a single enriched feature from brain/features/{feature_id}/.",
                {
                    "type": "object",
                    "properties": {"feature_id": {"type": "string"}},
                    "required": ["feature_id"],
                    "additionalProperties": False,
                },
                lambda args: get_feature_artifacts(str(args["feature_id"])),
            ),
            ToolDefinition(
                "aggregate_brain",
                "Rebuild brain/cache/aggregated_brain.json from all feature artifact files. Call after adding or updating any feature to refresh the aggregated view.",
                no_arg,
                lambda _: aggregate_brain_cache(),
            ),
        ]
        return {tool.name: tool for tool in tools}


def create_registry(
    brain: ProjectBrain,
    llm: LLMAdapter | None = None,
    brain_path: str = "PROJECT_BRAIN.json",
) -> ToolRegistry:
    return ToolRegistry(brain, llm or create_adapter(), brain_path=brain_path)
