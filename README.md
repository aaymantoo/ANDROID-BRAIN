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
Claude Code / Gemini CLI          ← queries + generates enterprise Kotlin
```

---

## Compatibility

| Tool | Works? | Notes |
|---|---|---|
| **Claude Code** (`claude`) | Yes — recommended | No config needed if Claude Code is already installed. Brain Engine detects and uses it automatically. |
| **Gemini CLI** (`gemini`) | Yes | Install: `npm install -g @google/gemini-cli`. Brain Engine detects it automatically. |
| `llm` CLI | Yes | Install: `pip install llm`. Works with Claude, GPT, Gemini, Mistral via plugins. |
| **Ollama** (local) | Yes | Install: https://ollama.com. Fully offline, no account needed. `ollama pull llama3.2` first. |
| `ANTHROPIC_API_KEY` | Yes | Fallback when no CLI tool is installed. |
| `OPENAI_API_KEY` | Yes | Fallback when no CLI tool is installed. |
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

You should see `brain-engine` listed with all 25 tools available.

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
```

---

## Setup with Gemini CLI

Gemini CLI (also called "Google's AI CLI" or colloquially "Antigravity") supports MCP servers through its `settings.json` configuration.

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

Gemini CLI will call Brain Engine's MCP tools automatically.

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
- Fill every ViewModel function signature
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

### 5. Generate code via MCP tools

From your LLM tool session:

```
generate_viewmodel("login")
generate_repository("auth")
generate_screen_scaffold("login")
generate_di_module("auth")
generate_viewmodel_test("login")
```

Generated files are written to your project directory, validated against MVVM rules, and backed up before overwriting.

### 6. Validate written code

```bash
# From your LLM session, or directly:
brain serve   # then call:
validate_mvvm("app/src/main/kotlin/ui/login/LoginViewModel.kt")
validate_naming_conventions("app/src/main/kotlin/...")
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
| `brain rollback <file>` | Restore the last `.brain_backup_*` for a generated file |
| `brain roadmap [--update] [--feature <id>]` | Print or regenerate ROADMAP.md; filter to one feature |
| `brain doctor` | Show active LLM adapter, installed CLI tools, API key status |

---

## MCP Tool Catalogue (29 tools)

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

### Generation tools — LLM-assisted, fall back to `// TODO` stubs

All generation tools: validate output with the rule engine → auto-fix CLASS_A violations → retry up to 3 times → write with `.brain_backup_*` and log to `generation_history`.

| Tool | What it generates |
|---|---|
| `generate_viewmodel(screen_id)` | `@HiltViewModel` + `StateFlow` + `Channel<Event>` |
| `generate_ui_state(screen_id)` | `@Immutable data class` UiState with typed fields |
| `generate_repository(repository_id)` | Interface + `@Singleton` implementation pair |
| `generate_datamodel(model_id)` | `@Keep` data class with `@PropertyName` for Firestore |
| `generate_screen_scaffold(screen_id)` | `@Composable` + `collectAsStateWithLifecycle` + Content split |
| `generate_usecase(usecase_name)` | Single-function `UseCase` with `invoke()` |
| `generate_di_module(feature_name)` | Hilt `@Module @Binds` for feature repositories |
| `generate_nav_route(screen_id)` | Type-safe route object with path args |
| `generate_viewmodel_test(screen_id)` | mockk + `StandardTestDispatcher` + `runTest` scaffold |

v2 enterprise templates (data-class UiState, Channel events, `Result<T>` repos) are selected automatically when the brain was produced by `brain enrich-prd`. Legacy v1 templates are used otherwise.

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
pytest              # 86 tests
pytest tests/test_cli_adapter.py -v   # CLI adapter detection
pytest tests/test_prd_enricher.py -v  # enrichment engine
pytest tests/test_schema.py -v        # Pydantic schema
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
| 4 | Code generation, self-healing orchestrator, 9 generation tools | Complete |
| 5 | Predictive bug engine | Not started |
| 6 | Self-healing sync (`brain sync`) | Not started |
