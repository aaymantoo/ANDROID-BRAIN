# Project Status

## Current Phase

Phases 0B, 0C, and 1–4 are complete. 133 tests passing.

## Phase Progress

| Phase | Scope | Status |
|---|---|---|
| Phase 0 | Project scaffold, packaging, docs, tracking files | Complete |
| Phase 0B | PRD enrichment engine, CLI adapters | Complete |
| Phase 0C | ROADMAP.md, feature pipeline, session-continuity MCP tools | **Complete** |
| Phase 1 | Brain schema, PRD scorer/parser, codebase scanner, CLI | Complete |
| Phase 2 | MCP server and read tools | Complete |
| Phase 3 | Rule engine and validation tools | Complete |
| Phase 4 | Code generation engine (v1 + v2 templates, self-healing) | Complete |
| Phase 5 | Predictive bug engine | Not started |
| Phase 6 | Self-healing and sync | Not started |

---

## Phase 0C Verification (Roadmap & Feature Pipeline)

- Full test suite: 133 tests passing (25 roadmap generator + 22 roadmap tools + all prior).
- `test_roadmap_generator` (25 tests): template→component mapping, ROADMAP.md content, `update_brain_status()` flag flipping, feature status promotion (planned→in_progress→complete), session log merging, `di_module` marking all feature screens, `next_step()` priority and dependency ordering.
- `test_roadmap_tools` (22 tests): `get_session_context` (empty brain, last session, blocked features), `get_next_task` (done state, feature/screen attribution), `get_feature_status` (by id, by name, component flags), `get_project_roadmap` (priority sort, orphan screens, session count).
- `brain init` now writes `ROADMAP.md` alongside `PROJECT_BRAIN.json`. Every `generate_*` call that writes a file auto-updates `ROADMAP.md`.
- Registry: 25 → 29 tools. New tools: `get_session_context`, `get_next_task`, `get_feature_status`, `get_project_roadmap`.
- Schema additions: `Feature`, `ComponentStatus`, `GenerationStatus`, `SessionEntry`; `ProjectBrain` gains `features`, `generation_status`, `session_log`.
- `brain roadmap` CLI command added.

---

## Phase 0B Verification (PRD Enrichment + CLI Adapters)

- Full test suite: 86 tests passing (21 new CLI adapter tests + 17 enricher tests + all prior).
- `test_cli_adapter` (21 tests): CLI command names, `is_available()`, `detect_cli_adapter()` priority order (claude > gemini > llm > ollama), fallback to None, `list_available_cli_adapters()`, `create_adapter()` priority over API keys, `describe_adapter()`, `_args()` correctness for all adapters.
- `test_prd_enricher` (17 tests): pattern detection, NullAdapter degradation, mocked LLM enrichment, v2 engine auto-routing.
- `brain enrich-prd ./rough.md --output enriched.md` transforms sparse PRD → hyperspec with LLM.
- `brain doctor` shows active adapter, installed CLI tools, API key status.
- LLM adapter priority: `claude` CLI → `gemini` CLI → `llm` CLI → `ollama` → `ANTHROPIC_API_KEY` → `OPENAI_API_KEY` → `NullAdapter`.
- No API key is required if Claude Code, Gemini CLI, `llm`, or Ollama are installed.

## Phase 1 Verification

- `test_prd_scorer.test_sample_prd_scores_100`: passed.
- `test_prd_parser.test_parse_sample_prd`: passed.
- `test_scanner.test_analyzer_finds_viewmodel`: passed.
- `test_scanner.test_scanner_builds_brain`: passed.
- `test_schema.test_brain_round_trip`: passed.

## Phase 2 Verification

- Full unittest discovery passed: 12 tests across parser, scorer, read tools, registry, scanner, and schema.
- `test_read_tools` verifies project context, screen graph, phase status, dependencies, and state machine reads.
- `test_registry` verifies all 10 read tools are exposed and executable through the registry.

## Phase 3 Verification

- Full unittest discovery passed: 20 tests.
- `test_rule_engine` verifies CLASS_A MVVM violations for ViewModel, Screen, and Repository files.
- `test_validation_tools` verifies Firestore consistency, state transition required updates, design token usage, naming conventions, and phase validation.
- `test_registry` verifies the registry exposes 16 tools: 10 read tools and 6 validation tools.

## Phase 4 Verification

- Full unittest discovery passed: 48 tests across all modules.
- `test_template_engine` (14 tests): all 10 Jinja2 templates render, produce correct Kotlin structures, context builders extract the right brain data.
- `test_generation_tools` (14 tests): self-healing orchestrator, NullAdapter graceful degradation, all 9 generation methods, registry wiring.
- Registry exposes 25 tools: 10 read + 6 validation + 9 generation.
- `brain rollback <file_path>` CLI command added.
- v2 enterprise templates auto-selected when brain contains enriched ViewModel data (`ui_state_type="data_class"` or `state_fields` or `events`).

---

## Current Capabilities

### CLI commands
- `brain enrich-prd ./PRD.md [--output] [--interactive]` — Phase 0B: LLM-powered PRD enrichment.
- `brain doctor` — show active LLM adapter and installed CLI tools.
- `brain validate-prd ./PRD.md` — scores PRD completeness (≥ 80 required).
- `brain init --from-prd ./PRD.md` — generates schema-validated brain, seeds `GenerationStatus` for every screen, writes `ROADMAP.md`.
- `brain init --from-code ./app/src/main/kotlin` — scans Kotlin files and generates a brain.
- `brain status` — summarizes a brain file.
- `brain review [--clear-review]` — lists or resolves low-confidence NEEDS_REVIEW items.
- `brain roadmap [--update] [--feature <id>]` — prints or regenerates ROADMAP.md; filter to one feature.
- `brain serve` — starts the stdio MCP server using `BRAIN_PATH` or `./PROJECT_BRAIN.json`.
- `brain rollback <file>` — restores the most recent `.brain_backup_*` for a generated file.

### MCP roadmap & pipeline tools (Phase 0C)
- `get_session_context` — last session + overall progress + current feature + next recommended step
- `get_next_task` — single next generation call, respects feature priority and dependency blocking
- `get_feature_status(feature_id)` — component-level status for all screens in a feature
- `get_project_roadmap` — full feature → screen → component status tree

### MCP read tools (Phase 2)
- `get_project_context` · `get_screen_graph` · `get_phase_status`
- `get_all_screens` · `get_dependencies` · `get_firestore_schema`
- `get_business_rules` · `get_state_machine` · `get_design_tokens` · `get_navigation_graph`

### MCP validation tools (Phase 3)
- `validate_mvvm` · `validate_phase` · `validate_firestore_consistency`
- `validate_state_transitions` · `validate_design_tokens` · `validate_naming_conventions`

### MCP generation tools (Phase 4)
- `generate_viewmodel` · `generate_ui_state` · `generate_repository`
- `generate_datamodel` · `generate_screen_scaffold` · `generate_usecase`
- `generate_di_module` · `generate_nav_route` · `generate_viewmodel_test`

All generation tools validate output with the Phase 3 rule engine and auto-fix CLASS_A violations with up to 3 retries.

---

## Residual Risk

- MCP stdio wiring is implemented against the installed `mcp` SDK but has not been manually connected to Claude Code in this environment. Run `brain serve` to verify end-to-end once a `PROJECT_BRAIN.json` is generated.
- Direct API adapters (`ClaudeAdapter`, `OpenAIAdapter`) are not exercised in tests due to no live API key; verified via unit inspection and NullAdapter parity tests. CLI adapters are fully mocked in tests.
- v2 template auto-selection fires when brain has enriched fields; legacy v1 brains from `--from-code` continue to use v1 templates unchanged.
- `features` list in `ProjectBrain` is populated only when the brain was produced from an enriched PRD that includes feature groupings. Brains from `--from-code` will have an empty `features` list; roadmap tools fall back to a flat screen table in that case.
