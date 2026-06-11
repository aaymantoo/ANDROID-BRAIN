# Project Brain Engine

A self-hosted MCP server that acts as persistent architectural memory and code-quality enforcer for Android projects. Give it a PRD or an existing Kotlin codebase; it produces a single `PROJECT_BRAIN.json` file and then serves it over MCP stdio so any LLM tool — **Claude Code, Gemini CLI, aider, Continue.dev** — can query and generate code from it.

**No API key required.** If you are already running inside Claude Code or Gemini CLI, Brain Engine uses those sessions automatically.

Tech stack: Python 3.11+, `mcp` SDK, Pydantic v2, Jinja2, Click.

---

## How It Works

```
Your PRD (sparse notes)
     │
     ▼  brain enrich-prd          ← LLM fills every gap
Hyperspec PRD (production-ready)
     │
     ▼  brain init --from-prd     ← deterministic Pydantic parse
PROJECT_BRAIN.json                ← single source of truth
     │
     ▼  brain serve               ← stdio MCP server
Claude Code / Gemini CLI          ← queries, generates, validates, and forecasts bugs
```

**Or use `brain build` to run the full pipeline in one command:**

```
brain build --prd ./rough.md --output ./app/src/main/kotlin
     │
     ├─ enrich-prd  →  brain init  →  brain serve (auto)
     │
     └─▶  brain-build-agent (Claude Code sub-agent)
              │
              ├─ 13-step loop: get_next_task → generate → validate → forecast → sync
              ├─ Dependency order enforced: datamodel → repository → usecase → ui_state
              │  → viewmodel → scaffold → nav_route → di_module → tests
              ├─ Logic fill pass: Claude fills TODO stubs when deterministic filler < 100%
              └─ UI design pass: ui-agent fills scaffold content from design system files
Generated .kt files (validated, spec-covered, bug-forecast)
```

---

## Compatibility

| Tool | Works? | Notes |
|---|---|---|
| **Claude Code** (`claude`) | Yes — recommended | Claude Code Pro subscription. No API key needed. Brain Engine calls `claude --print` using your existing session. |
| **Gemini CLI** (`gemini`) | Yes — no key needed | Install: `npm install -g @google/gemini-cli`. Authenticated via `gemini auth`. |
| `llm` CLI | Yes | Install: `pip install llm`. Works with Claude, GPT, Gemini, Mistral via plugins. |
| **Ollama** (local) | Yes | Install: https://ollama.com. Fully offline, no account needed. `ollama pull llama3.2` first. |
| `ANTHROPIC_API_KEY` | Yes | Fallback when no CLI tool is installed. API-key users only. |
| `OPENAI_API_KEY` | Yes | Fallback when no CLI tool is installed. API-key users only. |
| Nothing installed | Yes (degraded) | Generates `// TODO` stubs. Brain reading and validation still work fully. |

Run `brain doctor` at any time to see which adapter is active.

---

## Installation

```bash
git clone <this-repo>
cd BRAIN-MCP
pip install -e ".[dev]"

# Confirm the LLM adapter detected
brain doctor
```

---

## Setup with Claude Code

Claude Code is the recommended host. Brain Engine registers as an MCP server so Claude Code can call all tools directly inside your chat session.

### Step 1 — Register the MCP server

In your project directory (where `PROJECT_BRAIN.json` will live), run:

```bash
claude mcp add brain-engine -- brain serve
```

Or add it manually to `.claude/settings.json` (project-level) or `~/.claude/settings.json` (global):

```json
{
  "mcpServers": {
    "brain-engine": {
      "command": "brain",
      "args": ["serve"],
      "env": {
        "BRAIN_PATH": "${workspaceFolder}/PROJECT_BRAIN.json"
      }
    }
  }
}
```

### Step 2 — Verify connection

Inside a Claude Code session:

```
/mcp
```

You should see `brain-engine` listed with all 35 tools available.

### Step 3 — Generate your brain

```bash
# Option A: from a PRD
brain enrich-prd ./my_prd.md --output ./enriched_prd.md
brain init --from-prd ./enriched_prd.md

# Option B: from an existing Android codebase
brain init --from-code ./app/src/main/kotlin
```

### Step 4 — Use it in Claude Code

Claude Code now has access to all Brain Engine tools. Example prompts:

```
What screens are defined in the brain?
→ uses get_all_screens

Generate the AuthViewModel for the login screen
→ uses generate_viewmodel

Validate my HomeViewModel against MVVM rules
→ uses validate_mvvm

Check for race conditions in the generated repository
→ uses detect_race_conditions

Is the auth feature complete per the PRD?
→ uses validate_generation
```

---

## Setup with Gemini CLI

Gemini CLI supports MCP servers through its `settings.json` configuration.

### Step 1 — Install Gemini CLI

```bash
npm install -g @google/gemini-cli
gemini auth login
```

### Step 2 — Register the MCP server

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "brain-engine": {
      "command": "brain",
      "args": ["serve"],
      "env": {
        "BRAIN_PATH": "/path/to/your/project/PROJECT_BRAIN.json"
      }
    }
  }
}
```

### Step 3 — Generate your brain (same as Claude Code)

```bash
brain enrich-prd ./my_prd.md --output ./enriched_prd.md
brain init --from-prd ./enriched_prd.md
```

### Step 4 — Use it in Gemini CLI

```bash
gemini
> What viewmodels are defined in the brain?
> Generate the repository for the auth feature
```

---

## Setup with Ollama (fully offline)

No internet or account required.

```bash
# Install Ollama from https://ollama.com, then:
ollama pull llama3.2

# Brain Engine detects Ollama automatically
brain doctor      # should show OllamaCLIAdapter

# Run the full workflow
brain enrich-prd ./my_prd.md --output ./enriched_prd.md
brain init --from-prd ./enriched_prd.md
brain serve
```

---

## Full Workflow (step by step)

### 1. Start with a sparse PRD

You don't need a perfect PRD. Even rough notes work:

```bash
brain enrich-prd ./rough_notes.md --output ./enriched_prd.md
```

The LLM (using whatever tool is installed) will:
- Fill every ViewModel function signature with `state_updates`, `events_fired`, and `concurrent` fields
- Add typed state fields and event specs
- Infer repository method signatures with `Result<T>` wrapping
- Apply 20 enterprise Android patterns (Channel events, Mutex guards, `@Keep`, `@Immutable`, etc.)
- Mark inferences as `[INFERRED]` and unknowns as `[UNKNOWN — please specify]`

Use `--interactive` to answer gap questions in the terminal:

```bash
brain enrich-prd ./rough_notes.md --output ./enriched_prd.md --interactive
```

### 2. Review the enriched PRD

Open `enriched_prd.md` and search for `[UNKNOWN]` — these are fields the LLM could not infer. Fill them before continuing.

### 3. Validate and generate the brain

```bash
brain validate-prd ./enriched_prd.md   # must score ≥ 80
brain init --from-prd ./enriched_prd.md --output PROJECT_BRAIN.json
brain status                            # summary of what was parsed
```

### 4. Start the MCP server

```bash
brain serve
```

This runs forever in the terminal and waits for tool calls from Claude Code or Gemini CLI. Keep it running while you work.

### 5. Generate code — automated or manual

**Option A (recommended): let the brain-build-agent do it**

```bash
# brain build already started the MCP server in step 4.
# In your Claude Code session, type:
Use the brain-build-agent to build my project to ./app/src/main/kotlin
```

The agent drives the full generation loop automatically — see [Brain Build Agent](#brain-build-agent) below.

**Option B: call tools manually from your LLM session**

```
generate_viewmodel("login")
generate_repository("auth")       # writes AuthRepository.kt + AuthRepositoryImpl.kt
generate_screen_scaffold("login")
generate_di_module("auth")
generate_viewmodel_test("login")
```

Generated files are:
- Validated against MVVM rules and auto-fixed
- Smoke-checked by `kotlinc` if installed
- Backed up before overwriting
- Logged to `generation_history` in the brain

Each result includes `spec_coverage` (fraction of non-TODO function bodies) and `bug_warnings` (CLASS_A forecasts).

### 6. Validate and check for bugs

```bash
# From your LLM session, or directly:
validate_generation(feature_id="auth")     # brain + roadmap + PRD check
forecast_bugs("LoginScreen")               # 5-detector bug forecast
audit_production_readiness(1)              # full phase pre-launch report
sync_brain                                 # detect drift from brain spec
```

---

## CLI Reference

| Command | Description |
|---|---|
| `brain enrich-prd <prd> [--output FILE] [--interactive]` | Convert sparse PRD → hyperspec using LLM |
| `brain validate-prd <prd>` | Score PRD completeness (≥ 80 required for `init`) |
| `brain init --from-prd <prd>` | Generate `PROJECT_BRAIN.json` from a scored PRD |
| `brain init --from-code <src_dir>` | Generate `PROJECT_BRAIN.json` by scanning Kotlin files |
| `brain status [--brain-path FILE]` | Print brain summary |
| `brain review [--clear-review]` | List or resolve low-confidence `NEEDS_REVIEW` items |
| `brain serve` | Start the stdio MCP server |
| `brain build --output <dir> [--prd FILE] [--phase N] [--screen ID] [--design-system DIR]` | Enrich + init + serve; print agent invocation instructions |
| `brain rollback <file>` | Restore the last `.brain_backup_*` for a generated file |
| `brain roadmap [--update] [--feature <id>]` | Print or regenerate ROADMAP.md; filter to one feature |
| `brain doctor` | Show active LLM adapter, installed CLI tools, API key status |

---

## Brain Build Agent

`brain build` is the one-command entry point for autonomous project generation. It prepares the brain, starts the MCP server, and tells you exactly what to type in Claude Code to launch the build agent.

### Quickstart

```bash
# From a sparse PRD (auto-enriches and inits the brain):
brain build --prd ./rough_notes.md --output ./app/src/main/kotlin

# From an existing brain:
brain build --output ./app/src/main/kotlin

# Limit scope:
brain build --output ./app/src/ --phase 1
brain build --output ./app/src/ --screen login --resume

# With UI design pass (fills Compose screen content from your design system):
brain build --output ./app/src/ --design-system ./app/src/main/kotlin/ui/theme
```

After the server starts, the terminal prints the agent prompt. Paste it into Claude Code.

### How the Agent Loop Works

The `brain-build-agent` Claude Code sub-agent drives a 13-step loop until the entire project is built:

```
1.  get_session_context()           → resume from last session
2.  get_next_task()                 → next screen, feature, reason
3.  get_screen_graph() +            → full spec (cached for reuse)
    get_dependencies() +
    get_phase_status()
4.  Classify task                   → SCREEN | DATA | DOMAIN | NAVIGATION | INFRA | TESTING
5.  Build dependency list           → only items where ComponentStatus flag = False
6.  Generate missing artifacts      → tools called in dependency order (datamodel →
                                       repository → usecase → ui_state → viewmodel →
                                       scaffold → nav_route → di_module → tests)
6c. UI design pass (conditional)    → ui-agent fills scaffold content from design system
7.  Logic fill pass (conditional)   → Claude fills TODO stubs when spec_coverage < 1.0
                                       AND used_llm == False
8.  Compile gate                    → reads result.compile_ok (non-blocking)
9.  validate_generation()           → gate on ≥ 90% completeness; retry if below
10. validate_phase()                → CLASS_A/B violations (report only)
11. forecast_bugs()                 → 5 zero-LLM detectors (advisory)
12. sync_brain()                    → drift detection
13. Roadmap update                  → automatic via write_result()
    └─ loop back to step 2 until get_next_task() returns done=True
→ audit_production_readiness()      → final pre-launch report
```

**Feature order is automatic.** The brain schema enforces priority and dependency blocking — `auth` builds before `home`, `home` before `profile`. Feature promotion to `complete` is gated on `validate_generation ≥ 90%`.

**Token-minimal by design.** The deterministic filler covers ~80–90% of ViewModel function bodies with zero LLM calls. Claude only fills gaps when `spec_coverage < 1.0 AND used_llm == False`. ComponentStatus flags prevent any artifact from being generated twice.

### Agent Files

| File | Purpose |
|---|---|
| `.claude/agents/brain-build-agent.md` | Main build agent — full 13-step loop instructions for Claude Code |
| `.claude/agents/ui-agent.md` | UI design pass (step 6c) — fills scaffold `// TODO: implement screen content` using MaterialTheme tokens from your design system |
| `prompts/logic_fill_pass.txt` | Logic fill pass prompt — rules for filling TODO stubs in ViewModel and Repository files |
| `docs/AGENT-LOOP.md` | Full loop reference: dependency table, task classification matrix, token minimisation rules |

---

## MCP Tool Catalogue (35 tools)

### Roadmap & pipeline tools — zero-LLM, call at session start

| Tool | What it returns |
|---|---|
| `get_session_context` | Last session + overall progress + current feature + next recommended step |
| `get_next_task` | Single next generation call with exact args; respects feature priority and dependency blocking |
| `get_feature_status(feature_id)` | Component-level status table for every screen in a feature |
| `get_project_roadmap` | Full feature → screen → component status tree for the entire project |

### Read tools — zero-LLM, instant

| Tool | What it returns |
|---|---|
| `get_project_context` | Project meta, architecture, design system |
| `get_screen_graph(screen_id)` | Screen + ViewModel + Repository + nav links + business rules |
| `get_all_screens` | All screens with completion status |
| `get_phase_status(phase)` | % complete, done/pending screens, blocking violations |
| `get_dependencies(screen_id)` | Preconditions before building a screen |
| `get_firestore_schema` | All Firestore collections |
| `get_business_rules` | All business rules |
| `get_state_machine(entity)` | Full state machine for an entity |
| `get_design_tokens` | Design system values and token rules |
| `get_navigation_graph` | Full navigation graph |

### Validation tools — deterministic, no LLM

| Tool | What it checks |
|---|---|
| `validate_mvvm(file_path)` | CLASS_A/B/C MVVM rule violations in a Kotlin file |
| `validate_phase(phase)` | All phase files from the brain |
| `validate_firestore_consistency` | Brain Firestore rules vs. declarations |
| `validate_state_transitions(entity, file_path)` | Required state update presence |
| `validate_design_tokens(file_path)` | Disallowed token usage |
| `validate_naming_conventions(file_path)` | Kotlin naming convention violations |
| `validate_generation(feature_id?, phase?)` | Three-column per-screen verdict: `brain_match` / `roadmap_match` / `prd_match` with `completeness_pct` |

### Generation tools — LLM-assisted, deterministic pre-pass covers ~80 % of bodies

All generation tools: validate output → auto-fix CLASS_A violations → retry (×3) → write with `.brain_backup_*` → compile-check → bug forecast → log to `generation_history`.

| Tool | What it generates |
|---|---|
| `generate_viewmodel(screen_id)` | `@HiltViewModel` + `StateFlow` + `Channel<Event>`; deterministic filler fills 80–90 % of function bodies without LLM |
| `generate_ui_state(screen_id)` | `@Immutable data class` UiState (v2) or sealed class (v1) |
| `generate_repository(repository_id)` | Interface `.kt` + `Impl.kt` as two separate files |
| `generate_datamodel(model_id)` | `@Keep` data class with `@PropertyName` for Firestore |
| `generate_screen_scaffold(screen_id)` | `@Composable` + `collectAsStateWithLifecycle` + Content composable split |
| `generate_usecase(usecase_name)` | Single-function `UseCase` with `invoke()` |
| `generate_di_module(feature_name)` | Hilt `@Module @Binds` for feature repositories |
| `generate_nav_route(screen_id)` | v2: route object + `NavController.navigateTo{Screen}()` extension + `NavGraphBuilder.{screen}Screen()` composable builder |
| `generate_viewmodel_test(screen_id)` | mockk + `StandardTestDispatcher` + `runTest` scaffold |

### Bug forecasting tools — zero-LLM, Phase 5

| Tool | What it detects |
|---|---|
| `forecast_bugs(screen_id)` | All 5 detectors for one screen; returns prioritised CLASS_A/B list |
| `detect_race_conditions()` | Read-then-write Firestore patterns without transactions across all generated files |
| `detect_orphaned_documents()` | `consistency_link` violations that produce orphaned Firestore documents |
| `audit_production_readiness(phase)` | Full pre-launch bug audit for a phase |

### Sync tool — zero-LLM, Phase 6

| Tool | What it does |
|---|---|
| `sync_brain` | Re-scans all previously generated files; adds drift items to `brain.known_violations` |

---

## MVVM Violation Severities

| Class | Meaning | Effect |
|---|---|---|
| `CLASS_A` | Must fix — blocks generation | Auto-fixed and retried |
| `CLASS_B` | Should fix before merge | Reported as warning |
| `CLASS_C` | Advisory | Reported as note |
| `NEEDS_REVIEW` | Low scanner confidence (< 0.85) | Listed by `brain review` |

---

## Environment Variables

```bash
BRAIN_PATH=./PROJECT_BRAIN.json   # path to brain file (default: ./PROJECT_BRAIN.json)
ANTHROPIC_API_KEY=...             # optional — only used if no CLI tool is detected
OPENAI_API_KEY=...                # optional — only used if no CLI tool is detected
```

Copy `.env.example` → `.env` to set these permanently.

---

## Running Tests

```bash
pytest              # 150 tests
pytest tests/test_new_phases.py -v     # Phase 4–6 coverage (20 tests)
pytest tests/test_cli_adapter.py -v    # CLI adapter detection
pytest tests/test_prd_enricher.py -v   # enrichment engine
pytest tests/test_schema.py -v         # Pydantic schema
pytest tests/test_generation_tools.py -v  # Phase 4 generation + registry
```

---

## Phase Status

| Phase | Scope | Status |
|---|---|---|
| 0 | Scaffold, packaging | Complete |
| 0B | PRD enrichment engine, CLI adapters, v2 templates | **Complete** |
| 0C | ROADMAP.md, feature pipeline, 4 session-continuity MCP tools | **Complete** |
| 1 | Brain schema, PRD scorer/parser, codebase scanner | Complete |
| 2 | MCP server, 10 read tools | Complete |
| 3 | Rule engine, 6 validation tools | Complete |
| 4 | Code generation: v1+v2 templates, DeterministicFunctionBodyGenerator, self-healing orchestrator, CompileVerifier, 9 generation tools | **Complete** |
| 5 | Predictive bug engine: 5 zero-LLM detectors, 4 MCP tools | **Complete** |
| 6 | Self-healing sync: StateTransitionEngine, sync_brain MCP tool | **Complete** |
