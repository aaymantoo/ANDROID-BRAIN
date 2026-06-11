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

**Run the autonomous build agent (Option A — Claude Code as loop driver)**
```
# Full pipeline from a sparse PRD (enrich + init + start MCP server):
brain build --prd ./rough.md --output ./app/src/main/kotlin

# From an existing brain:
brain build --output ./app/src/main/kotlin

# Limit scope:
brain build --output ./app/src/ --phase 1
brain build --output ./app/src/ --screen login

# With UI design pass:
brain build --output ./app/src/ --design-system ./app/src/main/kotlin/ui/theme
```
After the server starts, invoke the build agent in Claude Code:
`"Use the brain-build-agent to build my project to ./app/src/main/kotlin"`

**Show or regenerate the project roadmap**
```
brain roadmap
brain roadmap --update
brain roadmap --feature auth
```

**Environment variables** (copy `.env.example` → `.env`):
- `BRAIN_PATH` — path to `PROJECT_BRAIN.json` (default: `./PROJECT_BRAIN.json`)
- `ANTHROPIC_API_KEY` — fallback direct API (only used when no CLI tool is detected)
- `OPENAI_API_KEY` — fallback direct API (only used when no CLI tool is detected)

### LLM adapter auto-detection

`brain enrich-prd` and Phase 4 generation use the first available LLM in this priority order:

1. `claude` CLI — Claude Code **Pro subscription** (**recommended** — no API key needed)
2. `gemini` CLI — Google Gemini CLI
3. `llm` CLI — Simon Willison's universal LLM CLI (`pip install llm`)
4. `ollama` — local models, fully offline (`https://ollama.com`)
5. `ANTHROPIC_API_KEY` env var — direct Anthropic API (fallback for API-key users)
6. `OPENAI_API_KEY` env var — direct OpenAI API
7. `NullAdapter` — graceful degradation (generates `// TODO` stubs)

CLI tools take priority because they reuse the user's existing authenticated session (Claude Code
Pro, Gemini CLI) with no API key required. Run `brain doctor` to see which adapter is active.

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
| `project_brain/generators/deterministic_body_filler.py` | **Phase 4 / B.** `DeterministicFunctionBodyGenerator` — fills 80–90 % of ViewModel function bodies from `state_updates`, `events_fired`, and `concurrent` brain fields with zero LLM calls. Confidence ≥ 0.75 skips the LLM subprocess entirely. |
| `project_brain/tools/read_tools.py` | `ReadTools` — zero-LLM, pure read-only queries over a loaded `ProjectBrain` (get_project_context, get_screen_graph, get_dependencies, etc.). All MCP read tools are backed by this class. |
| `project_brain/tools/validation_tools.py` | Standalone validation functions for Firestore consistency, state transitions, design tokens, naming conventions, and `validate_generation` (three-column per-screen verdict). |
| `project_brain/tools/registry.py` | `ToolRegistry` — wires all tools into `ToolDefinition` objects and exposes them as MCP tools. **35 tools total.** |
| `project_brain/engines/rule_engine.py` | `MVVMValidationEngine` + `KotlinAnalyzer` — deterministic regex-based MVVM rule checker. Violations are `CLASS_A` (blocking), `CLASS_B`, or `CLASS_C`. |
| `project_brain/engines/bug_engine.py` | **Phase 5.** Five zero-LLM bug detectors: `StateTransitionBugDetector`, `FirestoreConsistencyDetector`, `RaceConditionDetector`, `ListenerLeakDetector`, `RevenueIntegrityDetector`. Orchestrated by `BugEngine`. |
| `project_brain/engines/state_engine.py` | **Phase 6.** `StateTransitionEngine` — validates that generated files contain all `required_firestore_updates` declared in brain state machine transitions. |
| `project_brain/tools/management_tools.py` | **Phase 6.** `sync_brain` — scans `generation_history` files for drift vs. brain spec; adds `NEEDS_REVIEW` violations for missing or extra functions. |
| `project_brain/tools/bug_tools.py` | Phase 5 MCP facades: `forecast_bugs_brain`, `detect_race_conditions_brain`, `detect_orphaned_documents_brain`, `audit_production_readiness_brain`. |
| `rules/mvvm_rules.py` | `MVVM_RULES` list — the actual rule definitions referenced by `MVVMValidationEngine`. B004 skips `@Immutable data class` UiState (v2 pattern). |
| `rules/firestore_rules.py` | Firestore consistency rules. |
| `rules/naming_rules.py` | Kotlin naming convention rules. |
| `project_brain/server.py` | Async stdio MCP server entry point. Loads the brain, builds the registry, runs `mcp.server.stdio`. |
| `project_brain/cli/commands.py` | Click CLI (`brain` entry point): `validate-prd`, `init`, `status`, `review`, `roadmap`, `serve`, `sync`. |
| `project_brain/generators/roadmap_generator.py` | **Phase 0C.** `RoadmapGenerator` — produces and incrementally updates `ROADMAP.md`. `update_brain_status()` is called by `write_result()` after every successful generation to flip `ComponentStatus` flags. Feature promotion to `"complete"` is gated on `validate_generation` returning ≥ 90 % completeness when files have been written. |
| `project_brain/tools/roadmap_tools.py` | `get_session_context`, `get_next_task`, `get_feature_status`, `get_project_roadmap` — the four session-continuity MCP tools. |
| `templates/v1/*.kt.j2` | Jinja2 Kotlin templates for Phase 4 (sealed-class UiState, basic patterns). Used for non-enriched brains. |
| `templates/v2/*.kt.j2` | **Enterprise templates.** Auto-selected when brain has `ui_state_type="data_class"` (Phase 0B enriched). data-class UiState, Channel events, Result<T> repository, @Singleton, @Keep, @Immutable, LaunchedEffect, collectAsStateWithLifecycle. Includes v2 `nav_route.kt.j2` with `NavController` extension and `NavGraphBuilder` composable builder. |
| `templates/hyperspec_template.md` | The canonical output target for `brain enrich-prd`. The enrichment LLM fills this template. |
| `project_brain/llm/adapter.py` | `create_adapter()` — auto-detects best available LLM (CLI tools → API keys → NullAdapter). `describe_adapter()` for `brain doctor`. |
| `project_brain/llm/cli_adapter.py` | `CLIAdapter` ABC + `ClaudeCodeCLIAdapter`, `GeminiCLIAdapter`, `LLMCLIAdapter`, `OllamaCLIAdapter`. Subprocess-based, stdin pipe, no shell injection risk. `fill_functions()` runs `DeterministicFunctionBodyGenerator` first — only spawns a subprocess if confidence < 0.75. |
| `project_brain/llm/claude.py` | Direct Anthropic API adapter (fallback when no CLI tool is found). |
| `project_brain/llm/openai.py` | Direct OpenAI API adapter (fallback). |
| `project_brain/engines/template_engine.py` | `TemplateEngine` (v1) and `TemplateEngineV2` (enterprise). `_resolve_domain_imports()` maps `AppResult`/`User` return types to `domain.util`/`domain.model` import paths. |
| `project_brain/generators/code_generation.py` | `GenerationOrchestrator` — template render → LLM fill → MVVM validate → auto-fix CLASS_A → retry (×3). `write_result()` runs `CompileVerifier` (kotlinc smoke-check), calls `BugEngine.forecast()` for ViewModel/Repository files, and computes `spec_coverage`. `RepositoryPair` + `write_repository_pair()` produce two separate `.kt` files. |
| `project_brain/tools/generation_tools.py` | `GenerationTools` MCP facade for all 9 generation methods. `generate_repository()` with `output_path` writes two files via `write_repository_pair()`. |

### Phase status

- **Phase 0B (PRD Enrichment)** — complete. `brain enrich-prd` transforms any sparse PRD into a hyperspec using LLM. Produces enterprise-grade brains that drive 8+/10 code generation. Degrades gracefully without an API key.
- **Phase 0C (Roadmap & Feature Pipeline)** — complete. `brain init` now produces `ROADMAP.md` alongside `PROJECT_BRAIN.json`. Four session-continuity MCP tools. Generation tools auto-update ROADMAP.md after each file is written. Feature promotion gated on `validate_generation` ≥ 90 %.
- **Phase 1 (Brain Generation)** — complete. PRD parser, codebase scanner, schema, manager.
- **Phase 2 (MCP Server & Read Tools)** — complete. All read tools and the stdio server are live.
- **Phase 3 (Rule Engine & Validation)** — complete. MVVM, Firestore, naming, state-transition validation. B004 false positive on `@Immutable data class` UiState fixed.
- **Phase 4 (Code Generation)** — complete. Template engine (v1 + v2), LLM adapters, `DeterministicFunctionBodyGenerator`, self-healing orchestrator, 9 generation tools, repository two-file split, `CompileVerifier`, `spec_coverage` and `bug_warnings` on `GenerationResult`.
- **Phase 5 (Bug Forecasting)** — complete. `BugEngine` with 5 zero-LLM detectors. Four MCP tools.
- **Phase 6 (Self-Healing & Sync)** — complete. `StateTransitionEngine`, `sync_brain`. `brain sync` CLI command.

### MCP tool catalogue (35 tools — all live)

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
- `validate_generation(feature_id?, phase?)` — three-column per-screen verdict: `brain_match` / `roadmap_match` / `prd_match`; returns `completeness_pct`

Roadmap & pipeline tools (Phase 0C — zero-LLM):
- `get_session_context` — last session + overall progress + next recommended step (call at session start)
- `get_next_task` — single most important next generation call, respects priority + dependency blocking
- `get_feature_status(feature_id)` — component-level status for all screens in a feature
- `get_project_roadmap` — full feature → screen → component status tree

Generation tools (Phase 4 — LLM-assisted where noted, deterministic pre-pass covers ~80 % of cases):
- `generate_viewmodel(screen_id, output_path?)` — HiltViewModel with StateFlow + Channel<Event>; deterministic filler covers 80–90 % of function bodies
- `generate_ui_state(screen_id, output_path?)` — sealed or data-class UiState from brain `ui_states`
- `generate_repository(repository_id, output_path?)` — two-file split: interface `.kt` + implementation `Impl.kt`
- `generate_datamodel(model_id, output_path?)` — @Keep data class, zero-LLM
- `generate_screen_scaffold(screen_id, output_path?)` — @Composable with ViewModel injection and UiState when/is block
- `generate_usecase(usecase_name, output_path?)` — UseCase with invoke() operator
- `generate_di_module(feature_name, output_path?)` — Hilt @Module @Binds block
- `generate_nav_route(screen_id, output_path?)` — v2: type-safe route object + NavController extension + NavGraphBuilder composable builder
- `generate_viewmodel_test(screen_id, output_path?)` — coroutine test scaffold with StandardTestDispatcher

All generation tools: validate output with Phase 3 rule engine, auto-fix CLASS_A violations, retry up to 3 times. Writing to `output_path` saves a `.brain_backup_*`, runs `CompileVerifier`, runs `BugEngine.forecast()` (non-blocking), and appends to `generation_history`.

Bug forecasting tools (Phase 5 — all zero-LLM):
- `forecast_bugs(screen_id)` — run all 5 detectors for one screen; returns CLASS_A/B bug list
- `detect_race_conditions()` — scan all generated files for read-then-write without transaction
- `detect_orphaned_documents()` — find `consistency_link` violations across data models
- `audit_production_readiness(phase)` — full pre-launch bug audit for a phase

Sync tool (Phase 6 — zero-LLM):
- `sync_brain` — re-scan all previously generated files for drift from brain spec; adds `NEEDS_REVIEW` violations

### PRD requirements

`brain init --from-prd` gates on a completeness score ≥ 80/100. Run `brain validate-prd` first to see the breakdown by dimension. Use `PRD_TEMPLATE.md` as the canonical template for new PRDs.

### Autonomous build agent (Option A)

The `brain build` command prepares the brain and starts the MCP stdio server. Claude Code IS the loop driver — it calls MCP tools directly.

| File | Purpose |
|---|---|
| `.claude/agents/brain-build-agent.md` | 13-step loop agent definition — drives feature → screen → artifact generation |
| `.claude/agents/ui-agent.md` | UI design pass — fills scaffold `// TODO: implement screen content` using design system |
| `prompts/logic_fill_pass.txt` | Prompt for logic fill pass — Claude fills TODO stubs when `spec_coverage < 1.0 AND used_llm=False` |
| `docs/AGENT-LOOP.md` | Full loop reference doc including dependency order, task classification, token minimisation |

See `docs/AGENT-LOOP.md` for the complete loop specification.

### MVVM violation severities

- `CLASS_A` — must fix before continuing (blocks `validate_mvvm`); auto-fixed and retried by generation loop
- `CLASS_B` — should fix
- `CLASS_C` — advisory
- `NEEDS_REVIEW` — low scanner confidence (< 0.85); use `brain review` to inspect and resolve

### GenerationResult fields

Every generation call returns a `GenerationResult` with:
- `content` — generated Kotlin source
- `clean` — True if no CLASS_A violations remain after retries
- `attempts` — 1–3
- `used_llm` — True if a real LLM adapter (not NullAdapter) was used
- `compile_ok` — True/False if `kotlinc` is installed; None if not checked
- `spec_coverage` — fraction of non-TODO function bodies (0.0–1.0); None for zero-LLM templates
- `bug_warnings` — list of CLASS_A bug forecasts from BugEngine (non-blocking, ViewModel/Repository only)
- `violations` — list of MVVM rule violation dicts
- `output_path` — path where the file was written (if `write_result()` was called)
