# Brain Build Agent — Loop Reference

This document describes the autonomous 13-step build loop executed by the `brain-build-agent` Claude Code sub-agent.

## Overview

The build agent drives the full Android project generation pipeline. It calls Brain Engine MCP tools in sequence, generates every artifact for every screen in dependency order, validates, forecasts bugs, and syncs the brain — all with minimal LLM token consumption because ~80–90 % of generation is handled deterministically by the MCP pipeline.

---

## Entry Points

### Option A — Claude Code agent (recommended)

Claude Code IS the loop driver. Register `brain-engine` as an MCP server, then invoke the agent:

```bash
# Start the MCP server (keep running in a terminal)
brain build --output ./app/src/main/kotlin

# In Claude Code, type:
# "Use the brain-build-agent to build my project to ./app/src/main/kotlin"
```

The agent `.claude/agents/brain-build-agent.md` contains the full loop instructions. Claude Code calls MCP tools directly and fills TODO stubs using its own LLM (no subprocess overhead).

### Full pipeline from a sparse PRD

```bash
brain build --prd ./rough.md --output ./app/src/main/kotlin
```

This auto-runs `brain enrich-prd` + `brain init`, then starts the MCP server. Switch to Claude Code and invoke the agent.

---

## The 13-Step Loop

```
LOOP until get_next_task().done == True
  1.  get_session_context()           → resume state, blocked features
  2.  get_next_task()                 → next screen_id, feature_id
  3.  get_screen_graph()              → full spec (cached for steps 7 + 6c)
      get_dependencies()
      get_phase_status()
  4.  Classify task type              → SCREEN | DATA | DOMAIN | NAVIGATION | INFRA | TESTING
  5.  Build dependency list           → ordered missing artifacts (ComponentStatus flag=False only)
  6.  Generate missing artifacts      → call generation tools in dependency order
  6c. UI design pass (conditional)    → spawn ui-agent if scaffold has TODO content stub
  7.  Logic fill pass (conditional)   → fill TODO stubs when spec_coverage<1.0 AND used_llm=False
  8.  Compile gate                    → read result.compile_ok (non-blocking)
  9.  validate_generation(feature_id) → gate on ≥ 90 % completeness
  10. validate_phase(phase)           → CLASS_A/B violations (report only)
  11. forecast_bugs(screen_id)        → 5 detectors (advisory)
  12. sync_brain()                    → drift detection
  13. Roadmap update                  → automatic via write_result()
LOOP END → audit_production_readiness(phase)
```

---

## Artifact Dependency Order (per screen)

Only items where the corresponding `ComponentStatus` flag is `False` are generated:

| Step | Tool | Flag |
|------|------|------|
| 1 | `generate_datamodel(model_id)` per model | `data_models` |
| 2 | `generate_repository(repository_id)` | `repository` |
| 3 | `generate_usecase(usecase_name)` per use_case | `use_cases` |
| 4 | `generate_ui_state(screen_id)` | `ui_state` |
| 5 | `generate_viewmodel(screen_id)` | `viewmodel` |
| 6 | `generate_screen_scaffold(screen_id)` | `scaffold` |
| 7 | `generate_nav_route(screen_id)` | `nav_route` |
| 8 | `generate_di_module(feature_name)` | `di_module` |
| 9 | `generate_viewmodel_test(screen_id)` | `tests` |

---

## Task Type Classification

| TaskType | Trigger |
|----------|---------|
| SCREEN | `viewmodel == False` |
| DATA | any model not in `generation_history` |
| DOMAIN | any use_case not generated |
| NAVIGATION | `scaffold=True` AND `nav_route=False` |
| INFRASTRUCTURE | all screen flags `True` AND `di_module=False` |
| TESTING | `viewmodel=True` AND `tests=False` |

---

## Phase-wise Feature Order

The brain schema enforces feature priority and dependency blocking:

```
auth (priority 1)   → builds first
home (priority 2)   → blocked until auth.status == "complete"
profile (priority 3) → blocked until home.status == "complete"
```

`get_next_task()` implements this logic. The agent loop never needs to check feature blocking manually — it just follows `get_next_task()`.

Feature promotion (`in_progress → complete`) is gated on `validate_generation(feature_id).completeness_pct >= 90`.

---

## Logic Fill Pass

Triggered only when `result.spec_coverage < 1.0 AND result.used_llm == False`.

This means NullAdapter ran (no LLM was available for generation) and left `// TODO` stubs. Claude Code fills them directly using:
- The `screen_graph` already loaded in Step 3 (no extra MCP call)
- The rules in `prompts/logic_fill_pass.txt`

The prompt template is at `prompts/logic_fill_pass.txt`.

---

## UI Design Pass (Step 6c)

Triggered only when:
- Scaffold file contains `// TODO: implement screen content`
- AND design system files exist at the design system directory

The `ui-agent` sub-agent (`.claude/agents/ui-agent.md`) handles this. It:
1. Reads the design system (Theme.kt, Typography.kt, Shape.kt, components/)
2. Calls `get_screen_graph(screen_id)` for UiState fields and event handlers
3. Fills the TODO with real MaterialTheme-based Compose UI
4. Overwrites only the TODO section, leaving all other scaffold code intact

`validate_design_tokens(file_path)` acts as the quality gate after the UI pass.

---

## Token Minimisation

| Rule | Saving |
|------|--------|
| Check ComponentStatus before each generate call — skip if True | Avoids regenerating already-done components |
| Reuse `get_screen_graph()` from Step 3 in Steps 7 and 6c | 1 read call per screen instead of 3 |
| Logic fill pass ONLY when spec_coverage < 1.0 AND used_llm=False | Skips LLM call when deterministic filler covered everything |
| `get_next_task()` drives the loop | Single call determines full next action, no scanning |
| All generation uses MCP pipeline first | LLM only fills gaps for TODO stubs |

---

## Output Path Convention

```
{OUTPUT_DIR}/{feature_name}/{ClassName}.kt
```

Examples:
```
app/src/main/kotlin/auth/LoginViewModel.kt
app/src/main/kotlin/auth/LoginUiState.kt
app/src/main/kotlin/auth/AuthRepositoryImpl.kt
app/src/main/kotlin/home/HomeScreen.kt
```

---

## Agent Files

| File | Purpose |
|------|---------|
| `.claude/agents/brain-build-agent.md` | Main build agent — 13-step loop driver |
| `.claude/agents/ui-agent.md` | UI design pass — fills scaffold content stubs |
| `prompts/logic_fill_pass.txt` | Prompt for logic fill pass TODO replacement |

---

## CLI Flags

```
brain build --prd <prd>              Enrich + init from a sparse PRD, then start server
brain build --output <dir>           Required: where to write generated .kt files
brain build --phase <n>              Limit to a single phase
brain build --screen <screen_id>     Limit to a single screen
brain build --resume                 Continue from last session (default behaviour)
brain build --design-system <dir>    Path to design system dir for UI agent step 6c
```

---

## Verification

Tests covering the agent scaffolding are in `tests/test_build_agent.py` (to be added when unit coverage is extended to the agent layer).

The integration path is:
1. `brain build --prd <prd> --output <dir>` — pre-processes and starts MCP server
2. Claude Code agent drives `get_next_task() → generate_* → validate_*` loop
3. `audit_production_readiness(phase)` confirms zero CLASS_A issues at exit
