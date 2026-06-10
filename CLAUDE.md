# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**Project Brain Engine** is a self-hosted MCP server that acts as persistent architectural memory and code quality enforcer for Android projects. It consumes a PRD or an existing Kotlin codebase, produces a `PROJECT_BRAIN.json` file (the single source of truth), and then serves that file over MCP stdio so any LLM tool (Claude Code, aider, Continue.dev) can query it.

Tech stack: Python 3.11+, `mcp` SDK, Pydantic v2, Jinja2, Click, httpx.

---

## Commands

**Install (editable with dev deps)**
```
pip install -e ".[dev]"
```

**Run all tests**
```
pytest
```

**Run a single test file**
```
pytest tests/test_schema.py -v
```

**Enrich a sparse PRD into a production-ready hyperspec (Phase 0B)**
```
brain enrich-prd ./rough_notes.md --output ./enriched_prd.md
brain enrich-prd ./rough_notes.md --output ./enriched_prd.md --interactive
```

**Validate a PRD before generating**
```
brain validate-prd path/to/PRD.md
```

**Generate PROJECT_BRAIN.json from a PRD**
```
brain init --from-prd path/to/enriched_prd.md --output PROJECT_BRAIN.json
```

**Generate PROJECT_BRAIN.json from an existing Kotlin codebase**
```
brain init --from-code path/to/android/src
```

**Show brain summary**
```
brain status
```

**List and clear low-confidence review items**
```
brain review
brain review --clear-review
```

**Start the MCP stdio server** (requires a `PROJECT_BRAIN.json` in the working directory or `BRAIN_PATH` env var)
```
brain serve
```

**Rollback a generated file to its last backup**
```
brain rollback path/to/HomeViewModel.kt
```

**Show which LLM adapter will be used and what CLI tools are installed**
```
brain doctor
```

**Show or regenerate the project roadmap**
```
brain roadmap
brain roadmap --update
brain roadmap --feature auth
```

**Environment variables** (copy `.env.example` → `.env`):
- `BRAIN_PATH` — path to `PROJECT_BRAIN.json` (default: `./PROJECT_BRAIN.json`)
- `ANTHROPIC_API_KEY` — direct Anthropic API (optional — CLI tools take priority)
- `OPENAI_API_KEY` — direct OpenAI API (optional — CLI tools take priority)

### LLM adapter auto-detection

`brain enrich-prd` and Phase 4 generation use the first available LLM in this priority order:

1. `claude` CLI — Claude Code installed and logged in (**recommended** — no API key needed)
2. `gemini` CLI — Google Gemini CLI
3. `llm` CLI — Simon Willison's universal LLM CLI (`pip install llm`)
4. `ollama` — local models, fully offline (`https://ollama.com`)
5. `ANTHROPIC_API_KEY` env var — direct Anthropic API
6. `OPENAI_API_KEY` env var — direct OpenAI API
7. `NullAdapter` — graceful degradation (generates `// TODO` stubs)

Run `brain doctor` to see which adapter is active in your environment.

---

## Architecture

### Data flow

```
PRD .md  ──► PRDEnricher (Phase 0B) ──► Hyperspec PRD ──► PRDParser ──► ProjectBrain (Pydantic) ──► PROJECT_BRAIN.json
Kotlin src ──► CodebaseScanner ───────────────────────────────────────────────────────────────────────────────────────┘
                                                                                  ▲
brain serve ──► server.py ──► ToolRegistry(brain) ──► MCP tools ──► LLM queries ─┘
```

### Key modules

| Path | Role |
|---|---|
| `project_brain/brain/schema.py` | The canonical Pydantic schema for `PROJECT_BRAIN.json`. All data shapes are defined here — `ProjectBrain`, `Screen`, `ViewModel`, `Repository`, `StateMachine`, `BusinessRule`, etc. `StrictModel` (base) rejects unknown fields. |
| `project_brain/brain/manager.py` | `BrainManager` — reads and atomic-writes `PROJECT_BRAIN.json` via a temp file + `os.replace`. |
| `project_brain/brain/validator.py` | Validates a raw JSON payload against the schema; raises `BrainValidationError`. |
| `project_brain/generators/prd_parser.py` | Heuristic markdown parser that turns a PRD file into a `ProjectBrain`. Requires PRD score ≥ 80; raises `IncompletePRDError` otherwise. |
| `project_brain/generators/prd_enricher.py` | **Phase 0B.** `PRDEnricher` — converts sparse PRD to hyperspec via LLM; `_detect_patterns()` counts enterprise pattern adoption. |
| `project_brain/generators/prd_scorer.py` | `PRDCompletenessScorer` — scores a PRD across dimensions and gates `brain init`. |
| `project_brain/generators/codebase_scanner.py` | Regex/heuristic Kotlin scanner (`KotlinFileAnalyzer` + `CodebaseScanner`). Produces a `ProjectBrain` from `.kt` files with no LLM. Assigns per-file confidence scores; low-confidence files become `NEEDS_REVIEW` violations. |
| `project_brain/generators/brain_generator.py` | Thin facade that delegates to `PRDParser` or `CodebaseScanner` and calls `BrainManager.save()`. |
| `project_brain/tools/read_tools.py` | `ReadTools` — zero-LLM, pure read-only queries over a loaded `ProjectBrain` (get_project_context, get_screen_graph, get_dependencies, etc.). All MCP read tools are backed by this class. |
| `project_brain/tools/validation_tools.py` | Standalone validation functions for Firestore consistency, state transitions, design tokens, and naming conventions. |
| `project_brain/tools/registry.py` | `ToolRegistry` — wires `ReadTools` + validation tools into `ToolDefinition` objects and exposes them as MCP tools. |
| `project_brain/engines/rule_engine.py` | `MVVMValidationEngine` + `KotlinAnalyzer` — deterministic regex-based MVVM rule checker. Violations are `CLASS_A` (blocking), `CLASS_B`, or `CLASS_C`. |
| `rules/mvvm_rules.py` | `MVVM_RULES` list — the actual rule definitions referenced by `MVVMValidationEngine`. |
| `rules/firestore_rules.py` | Firestore consistency rules. |
| `rules/naming_rules.py` | Kotlin naming convention rules. |
| `project_brain/server.py` | Async stdio MCP server entry point. Loads the brain, builds the registry, runs `mcp.server.stdio`. |
| `project_brain/cli/commands.py` | Click CLI (`brain` entry point): `validate-prd`, `init`, `status`, `review`, `roadmap`, `serve`, `sync` (Phase 6 stub). |
| `project_brain/generators/roadmap_generator.py` | **Phase 0C.** `RoadmapGenerator` — produces and incrementally updates `ROADMAP.md`. `update_brain_status()` is called by `write_result()` after every successful generation to flip `ComponentStatus` flags and promote feature status. |
| `project_brain/tools/roadmap_tools.py` | `get_session_context`, `get_next_task`, `get_feature_status`, `get_project_roadmap` — the four session-continuity MCP tools. |
| `templates/v1/*.kt.j2` | Jinja2 Kotlin templates for Phase 4 (sealed-class UiState, basic patterns). Used for non-enriched brains. |
| `templates/v2/*.kt.j2` | **Enterprise templates.** Auto-selected when brain has `ui_state_type="data_class"` (Phase 0B enriched). data-class UiState, Channel events, Result<T> repository, @Singleton, @Keep, @Immutable, LaunchedEffect, collectAsStateWithLifecycle. |
| `templates/hyperspec_template.md` | The canonical output target for `brain enrich-prd`. The enrichment LLM fills this template. |
| `project_brain/llm/adapter.py` | `create_adapter()` — auto-detects best available LLM (CLI tools → API keys → NullAdapter). `describe_adapter()` for `brain doctor`. |
| `project_brain/llm/cli_adapter.py` | `CLIAdapter` ABC + `ClaudeCodeCLIAdapter`, `GeminiCLIAdapter`, `LLMCLIAdapter`, `OllamaCLIAdapter`. Subprocess-based, stdin pipe, no shell injection risk. `detect_cli_adapter()` and `list_available_cli_adapters()` helpers. |
| `project_brain/llm/claude.py` | Direct Anthropic API adapter (fallback when no CLI tool is found). |
| `project_brain/llm/openai.py` | Direct OpenAI API adapter (fallback). |
| `project_brain/engines/template_engine.py` | Phase 4 stub. |
| `project_brain/engines/state_engine.py` | Phase 6 stub. |
| `project_brain/tools/generation_tools.py` | Phase 4 stub. |
| `project_brain/tools/management_tools.py` | Phase 6 stub. |
| `project_brain/tools/bug_tools.py` | Phase 5 stub. |

### Phase status

- **Phase 0B (PRD Enrichment)** — complete. `brain enrich-prd` transforms any sparse PRD into a hyperspec using LLM. Produces enterprise-grade brains that drive 8+/10 code generation. Degrades gracefully without an API key.
- **Phase 0C (Roadmap & Feature Pipeline)** — complete. `brain init` now produces `ROADMAP.md` alongside `PROJECT_BRAIN.json`. Four new MCP tools: `get_session_context`, `get_next_task`, `get_feature_status`, `get_project_roadmap`. Generation tools auto-update ROADMAP.md after each file is written. Features group screens by domain (auth, home, orders, profile) with priority ordering and dependency blocking.
- **Phase 1 (Brain Generation)** — complete. PRD parser, codebase scanner, schema, manager.
- **Phase 2 (MCP Server & Read Tools)** — complete. All read tools and the stdio server are live.
- **Phase 3 (Rule Engine & Validation)** — complete. MVVM, Firestore, naming, state-transition validation.
- **Phase 4 (Code Generation)** — complete. Template engine (v1 + v2), LLM adapters, self-healing orchestrator, 9 generation tools live. v2 templates auto-selected for enriched brains.
- **Phase 5 (Bug Forecasting)** — stubbed.
- **Phase 6 (Self-Healing & Sync)** — stubbed. `brain sync` and `StateTransitionEngine` not yet implemented.

### MCP tool catalogue (Phases 2, 3 & 4 — all live)

Read tools (no arguments unless noted):
- `get_project_context` — meta, architecture, phases, design system
- `get_screen_graph(screen_id)` — screen + ViewModel + Repository + nav links + business rules
- `get_all_screens` — all screens with status and compliance
- `get_phase_status(phase)` — completion %, done/pending screens, blocking violations
- `get_dependencies(screen_id)` — required preconditions before building a screen
- `get_firestore_schema` — all Firestore collections
- `get_business_rules` — all business rules
- `get_state_machine(entity)` — full state machine for an entity
- `get_design_tokens` — design system values and token rules
- `get_navigation_graph` — full navigation graph

Validation tools:
- `validate_mvvm(file_path)` — run CLASS_A/B/C MVVM rules against a Kotlin file
- `validate_phase(phase)` — validate all phase files from the brain
- `validate_firestore_consistency` — check brain rules vs. Firestore declarations
- `validate_state_transitions(entity, file_path)` — check required state update presence
- `validate_design_tokens(file_path)` — check for disallowed token usage
- `validate_naming_conventions(file_path)` — Kotlin naming convention check

Roadmap & pipeline tools (Phase 0C — zero-LLM):
- `get_session_context` — last session + overall progress + next recommended step (call at session start)
- `get_next_task` — single most important next generation call, respects priority + dependency blocking
- `get_feature_status(feature_id)` — component-level status for all screens in a feature
- `get_project_roadmap` — full feature → screen → component status tree

Generation tools (Phase 4 — LLM-assisted where noted, all fall back to TODO stubs without an API key):
- `generate_viewmodel(screen_id, output_path?)` — HiltViewModel with StateFlow pattern; LLM fills function bodies
- `generate_ui_state(screen_id, output_path?)` — sealed UiState class from brain `ui_states`
- `generate_repository(repository_id, output_path?)` — interface + implementation pair
- `generate_datamodel(model_id, output_path?)` — @Keep data class, zero-LLM
- `generate_screen_scaffold(screen_id, output_path?)` — @Composable with ViewModel injection and UiState when/is block
- `generate_usecase(usecase_name, output_path?)` — UseCase with invoke() operator
- `generate_di_module(feature_name, output_path?)` — Hilt @Module @Binds block
- `generate_nav_route(screen_id, output_path?)` — type-safe route object; extracts path args from route or `nav_args`
- `generate_viewmodel_test(screen_id, output_path?)` — coroutine test scaffold with StandardTestDispatcher

All generation tools: validate output with Phase 3 rule engine, auto-fix CLASS_A violations, retry up to 3 times. Writing to `output_path` saves a `.brain_backup_*` and appends to `generation_history`.

### PRD requirements

`brain init --from-prd` gates on a completeness score ≥ 80/100. Run `brain validate-prd` first to see the breakdown by dimension. Use `PRD_TEMPLATE.md` as the canonical template for new PRDs.

### MVVM violation severities

- `CLASS_A` — must fix before continuing (blocks `validate_mvvm`)
- `CLASS_B` — should fix
- `CLASS_C` — advisory
- `NEEDS_REVIEW` — low scanner confidence (< 0.85); use `brain review` to inspect and resolve
