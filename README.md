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
              ├─ audit_brain          ← integrity gate before any generation
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
git clone https://github.com/aaymantoo/ANDROID-BRAIN.git brain-mcp
cd brain-mcp
pip install -e ".[dev]"

# Confirm the LLM adapter detected
brain doctor
```

Expected output:

```
LLM adapter : ClaudeCodeCLIAdapter (claude CLI)
CLI tools   : claude ✓  gemini ✗  llm ✗  ollama ✗
API keys    : ANTHROPIC_API_KEY ✗  OPENAI_API_KEY ✗
```

If `brain` is not found after install, add the pip scripts directory to your PATH:
- **Windows**: `%APPDATA%\Python\Python3xx\Scripts`
- **macOS/Linux**: `~/.local/bin`

---

## Setup with Claude Code

Claude Code is the recommended host. Brain Engine registers as an MCP server so Claude Code can call all 39 tools directly inside your chat session.

### Step 1 — Register the MCP server

Create `.mcp.json` in your **Android project root** (where `PROJECT_BRAIN.json` will live):

```json
{
  "mcpServers": {
    "brain-engine": {
      "command": "brain",
      "args": ["serve"],
      "env": {
        "BRAIN_PATH": "./PROJECT_BRAIN.json"
      }
    }
  }
}
```

This tells Claude Code to launch `brain serve` whenever it opens that project.

**Or register globally** (`~/.claude/mcp.json`) using an absolute path — useful if you work across multiple Android projects:

```json
{
  "mcpServers": {
    "brain-engine": {
      "command": "brain",
      "args": ["serve"],
      "env": {
        "BRAIN_PATH": "/absolute/path/to/your/android/project/PROJECT_BRAIN.json"
      }
    }
  }
}
```

### Step 2 — Verify the connection

Open your Android project in Claude Code and run:

```
/mcp
```

You should see `brain-engine` listed as a connected server with **39 tools**.

### Step 3 — Prepare a PRD

**Option A — Enrich a rough PRD (recommended):**

You don't need a perfect PRD. Even rough notes work:

```bash
brain enrich-prd ./rough_notes.md --output ./enriched_prd.md
# Add --interactive to answer gap questions in the terminal
brain enrich-prd ./rough_notes.md --output ./enriched_prd.md --interactive
```

The LLM fills every gap — ViewModel functions, state fields, repository method signatures, state machines, Firestore schema, business rules — and marks inferences as `[INFERRED]` and unknowns as `[UNKNOWN — please specify]`. Open the output and search for `[UNKNOWN]` to fill any fields it could not infer.

**Option B — Use an existing PRD:**

```bash
brain validate-prd ./my_prd.md   # must score ≥ 80 / 100
```

The score must reach **80** before `brain init` will proceed. If it is lower, the output lists exactly which dimensions are incomplete.

### Step 4 — Generate the brain

```bash
brain init --from-prd ./enriched_prd.md --output PROJECT_BRAIN.json
brain status    # shows screen, ViewModel, repository, and feature counts
```

This produces `PROJECT_BRAIN.json` (the single source of truth) and `ROADMAP.md` (feature → screen → component status tree).

**Or scan an existing Android codebase:**

```bash
brain init --from-code ./app/src/main/kotlin
```

### Step 5 — Run the build agent

```bash
brain build --prd ./enriched_prd.md --output ./app/src/main/kotlin
```

This command:
1. Runs `enrich-prd` + `brain init` if a brain does not yet exist
2. Starts `brain serve` (the MCP server)
3. Prints the exact agent prompt to paste into Claude Code

Paste the printed prompt into Claude Code. The `brain-build-agent` takes over and drives the full pipeline automatically — see [Brain Build Agent](#brain-build-agent) below.

**Scoped builds:**

```bash
brain build --output ./app/src/main/kotlin --phase 1
brain build --output ./app/src/main/kotlin --screen LoginScreen
brain build --output ./app/src/main/kotlin --resume         # continue after interruption
brain build --output ./app/src/ --design-system ./app/src/main/kotlin/ui/theme
```

### Step 6 — Monitor progress

While the build agent runs, it prints a progress block after each screen:

```
[auth] Screen 1/3: LoginScreen
  Generated : viewmodel, ui_state, repository, scaffold, nav_route
  Skipped   : datamodel (already done)
  Coverage  : 94%
  Bugs      : 0 CLASS_A
  Status    : COMPLETE
```

And after each feature:

```
[FEATURE COMPLETE] auth — 3 screens, completeness=97%
```

When all features are done:

```
╔══════════════════════════════════════╗
║         BUILD COMPLETE               ║
╠══════════════════════════════════════╣
║ Features:      4                     ║
║ Screens:       12                    ║
║ Files written: 84                    ║
║ Avg coverage:  91%                   ║
║ CLASS_A bugs:  0                     ║
╚══════════════════════════════════════╝
```

### Generated File Layout

Given `--output ./app/src/main/kotlin` and package `com.example.app`:

```
app/src/main/kotlin/com/example/app/
│
├── presentation/
│   └── auth/
│       ├── LoginScreen.kt          (scaffold)
│       ├── LoginViewModel.kt
│       └── LoginUiState.kt
│
├── domain/
│   ├── repository/
│   │   └── AuthRepository.kt       (interface)
│   ├── usecase/
│   │   └── LoginUseCase.kt
│   └── model/
│       └── User.kt
│
├── data/
│   └── repository/
│       └── AuthRepositoryImpl.kt
│
├── navigation/
│   └── LoginNavRoute.kt
│
└── di/
    └── AuthModule.kt

app/src/test/kotlin/com/example/app/
└── presentation/auth/
    └── LoginViewModelTest.kt
```

---

## Setup with Gemini CLI

```bash
npm install -g @google/gemini-cli
gemini auth login
```

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

Then use it normally:

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

brain enrich-prd ./my_prd.md --output ./enriched_prd.md
brain init --from-prd ./enriched_prd.md
brain serve
```

---

## Incremental Builds (large PRDs)

For large PRDs (10+ features), use the incremental enrichment pipeline to avoid losing progress on timeout or crash:

```bash
# Enrich one feature at a time
brain enrich-feature auth --prd ./enriched_prd.md
brain enrich-feature payments --prd ./enriched_prd.md

# Or enrich an entire phase
brain enrich-phase core --prd ./enriched_prd.md

# Resume after any interruption
brain resume --prd ./enriched_prd.md
```

After enriching, `brain/cache/aggregated_brain.json` is rebuilt automatically and used as the `BRAIN_PATH` for `brain serve`.

---

## Troubleshooting

### `Brain Engine MCP server is not connected`

The `brain serve` process is not running. Start it in a terminal:

```bash
cd /path/to/your/android/project
brain serve
```

Or use `brain build` — it starts the server automatically.

### `brain: command not found`

The package is not installed or the pip scripts directory is not on your PATH.

```bash
pip install -e ".[dev]"
where brain     # Windows
which brain     # macOS/Linux
```

### `Brain audit FAILED` before generation

The brain has structural issues. Common causes:

| Issue | Fix |
|---|---|
| `broken_reference: Screen 'X' → ViewModel 'Y' not found` | Add a ViewModel with `id: Y` to your brain, or fix the screen's `viewmodel` field |
| `missing_screen: Feature 'X' references screen 'Y' not in brain.screens` | Add the screen to `brain.screens`, or remove it from the feature |
| `circular_dependency` | Fix the navigation graph so no route loops back to itself |

Run `audit_brain()` directly in Claude Code to see the full issue list with scores.

### `PRD score too low (< 80)`

Run `brain validate-prd ./enriched_prd.md` — it prints a per-dimension breakdown. The most commonly missing sections are Firestore schema, state machines, and business rules. Use `brain enrich-prd` to fill them automatically.

### `/mcp` shows `brain-engine` but only 35 tools

The server started before `PROJECT_BRAIN.json` existed, or `BRAIN_PATH` points to a stale path. Verify with `brain status`, then restart the server.

---

## Full Workflow Reference

```bash
# 1. Enrich sparse notes into a hyperspec
brain enrich-prd ./rough_notes.md --output ./enriched_prd.md

# 2. Validate (must score ≥ 80)
brain validate-prd ./enriched_prd.md

# 3. Generate brain + ROADMAP.md
brain init --from-prd ./enriched_prd.md --output PROJECT_BRAIN.json
brain status

# 4. Run full autonomous build
brain build --output ./app/src/main/kotlin
# → paste the printed prompt into Claude Code

# 5. Useful day-to-day commands
brain roadmap               # print current ROADMAP.md
brain roadmap --update      # regenerate ROADMAP.md from brain
brain review                # list low-confidence NEEDS_REVIEW items
brain review --clear-review # resolve all review items
brain rollback <file>       # restore last .brain_backup_* for a generated file
brain sync                  # detect drift between generated files and brain spec
brain doctor                # confirm active LLM adapter
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
| `brain build --output <dir> [--prd FILE] [--phase N] [--screen ID] [--resume] [--design-system DIR]` | Enrich + init + serve; print agent invocation instructions |
| `brain rollback <file>` | Restore the last `.brain_backup_*` for a generated file |
| `brain roadmap [--update] [--feature <id>]` | Print or regenerate ROADMAP.md; filter to one feature |
| `brain doctor` | Show active LLM adapter, installed CLI tools, API key status |
| `brain enrich-feature <id> --prd <file>` | Incremental: enrich a single feature |
| `brain enrich-phase <name> --prd <file>` | Incremental: enrich all features in a named phase |
| `brain resume --prd <file>` | Incremental: continue from last checkpoint |

---

## Brain Build Agent

`brain build` is the one-command entry point for autonomous project generation. It prepares the brain, starts the MCP server, and tells you exactly what to type in Claude Code to launch the build agent.

### How the Agent Loop Works

The `brain-build-agent` Claude Code sub-agent drives a pipeline until the entire project is built:

```
Pre-flight
  get_session_context()       → resume from last session
  audit_brain()               → integrity gate (score ≥ 60, no broken refs)
                                 FAIL → print report, stop
                                 PASS → enter loop

13-step generation loop (repeats per screen until get_next_task() returns done=True):
  1.  get_session_context()          → check overall progress
  2.  get_next_task()                → next screen, feature, reason
  3.  get_screen_graph() +           → full spec (cached for reuse)
      get_dependencies() +
      get_phase_status()
  4.  Classify task                  → SCREEN | DATA | DOMAIN | NAVIGATION | INFRA | TESTING
  5.  Build dependency list          → only items where ComponentStatus flag = False
  6.  Generate missing artifacts     → dependency order:
                                        datamodel → repository → usecase → ui_state
                                        → viewmodel → scaffold → nav_route → di_module → tests
  6c. UI design pass (conditional)   → ui-agent fills scaffold content from design system
  7.  Logic fill pass (conditional)  → Claude fills TODO stubs when spec_coverage < 1.0
                                        AND used_llm == False
  8.  Compile gate                   → reads result.compile_ok (non-blocking)
  9.  validate_generation()          → gate on ≥ 90% completeness; retry if below
  10. validate_phase()               → CLASS_A/B violations (report only)
  11. forecast_bugs()                → 5 zero-LLM detectors (advisory)
  12. sync_brain()                   → drift detection
  13. Roadmap update                 → automatic via write_result()
      └─ loop back to step 2

Final audit: audit_production_readiness()
```

**Feature order is automatic.** The brain schema enforces priority and dependency blocking — `auth` builds before `home`, `home` before `profile`. Feature promotion to `complete` is gated on `validate_generation ≥ 90%`.

**Token-minimal by design.** The deterministic filler covers ~80–90% of ViewModel function bodies with zero LLM calls. Claude only fills gaps when `spec_coverage < 1.0 AND used_llm == False`. `ComponentStatus` flags prevent any artifact from being generated twice.

### Agent Files

| File | Purpose |
|---|---|
| `.claude/agents/brain-build-agent.md` | Main build agent — full pipeline instructions for Claude Code |
| `.claude/agents/ui-agent.md` | UI design pass (step 6c) — fills scaffold `// TODO: implement screen content` using MaterialTheme tokens |
| `prompts/logic_fill_pass.txt` | Logic fill pass prompt — rules for filling TODO stubs in ViewModel and Repository files |
| `docs/AGENT-LOOP.md` | Full loop reference: dependency table, task classification matrix, token minimisation rules |

---

## v3 Brain Spec — Richer Brain, Less TODO

By default, the generator produces correct skeletons with `// TODO: implement` stubs for logic it cannot derive deterministically. The **v3 brain spec fields** let you annotate the brain JSON with enough intent that the generator fills those stubs itself — no LLM pass, no manual editing.

These fields are all optional. Omit any you don't need; the generator falls back to its existing behaviour.

### `ViewModel` — private fields, init block, helpers, computed guards

```jsonc
{
  "id": "OtpViewModel",
  // ... existing fields ...

  "private_fields": [
    { "name": "savedVerificationId", "type": "String", "default": "\"\"", "volatile": true }
  ],
  "init_lines": [
    "savedStateHandle.get<String>(\"phone\")?.let { _uiState.update { s -> s.copy(phoneNumber = it) } }",
    "startResendCountdown()"
  ],
  "private_functions": [
    {
      "name": "startResendCountdown",
      "signature": "()",
      "return_type": "Unit",
      "body_hint": "countdown from 60 to 0 with delay(1000), updating resendSecondsRemaining each tick"
    }
  ],
  "computed_properties": [
    {
      "name": "canVerify",
      "type": "Boolean",
      "expression": "_uiState.value.digits.all { it.length == 1 } && !_uiState.value.isVerifying"
    }
  ]
}
```

### `RepositoryMethod` — Firebase pattern stubs

```jsonc
{
  "name": "sendOtp",
  "params": ["phoneNumber: String"],
  "firebase_pattern": "phone_auth"
}
```

| `firebase_pattern` | Emits |
|---|---|
| `auth_state_listener` | `callbackFlow { firebaseAuth.addAuthStateListener { … }; awaitClose { … } }` |
| `phone_auth` | `suspendCancellableCoroutine` + full `PhoneAuthProvider.OnVerificationStateChangedCallbacks` |
| `credential_sign_in` | `PhoneAuthProvider.getCredential(savedVerificationId, otp)` → `signInWithCredential` → Firestore fetch |
| `firestore_get` | `runCatching { firestore.collection(…).document(uid).get().await() }` |
| `firestore_update` | `runCatching { firestore.collection(…).document(uid).update(updates).await() }` |

### `Screen` — UI component list for zero-TODO scaffolds

```jsonc
{
  "id": "PhoneEntryScreen",
  "ui_components": [
    { "type": "OutlinedTextField", "bound_to": "phoneNumber", "label": "Mobile number", "prefix": "+91 ", "action": "onPhoneNumberChanged" },
    { "type": "ErrorText", "error_field": "errorMessage", "retry_action": "retrySendOtp" },
    { "type": "Button", "label": "Send OTP", "action": "onSendOtpClicked", "enabled_when": "!uiState.isSendingOtp && uiState.phoneNumber.length == 10", "loading_when": "isSendingOtp" },
    { "type": "OfflineBanner", "bound_to": "isOfflineMode" }
  ]
}
```

| `type` | Renders |
|---|---|
| `OutlinedTextField` | Text input with optional `prefix`, wired to `action` |
| `Button` | Primary button with optional `enabled_when` and loading spinner |
| `TextButton` | Flat secondary button |
| `ErrorText` | Conditional error message with optional "Retry" button |
| `OtpDigitRow` | Row of `count` (default 6) single-char boxes with auto-focus advance |
| `TimerText` | Countdown display that switches to a "Resend OTP" button at zero |
| `OfflineBanner` | `errorContainer` Card shown when `bound_to` is true |

---

## MCP Tool Catalogue (39 tools)

### Roadmap & pipeline tools

| Tool | What it returns |
|---|---|
| `get_session_context` | Last session + overall progress + current feature + next recommended step |
| `get_next_task` | Single next generation call with exact args; respects feature priority and dependency blocking |
| `get_feature_status(feature_id)` | Component-level status for every screen in a feature |
| `get_project_roadmap` | Full feature → screen → component status tree |

### Read tools

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

### Validation tools

| Tool | What it checks |
|---|---|
| `audit_brain` | Pre-generation integrity gate: reference integrity, circular nav deps, feature completeness, business rule coverage. Returns `{status, score, critical_issues, warnings, generation_allowed}`. All generation tools refuse when `generation_allowed=false`. |
| `validate_mvvm(file_path)` | CLASS_A/B/C MVVM rule violations in a Kotlin file |
| `validate_phase(phase)` | All phase files from the brain |
| `validate_firestore_consistency` | Brain Firestore rules vs. declarations |
| `validate_state_transitions(entity, file_path)` | Required state update presence |
| `validate_design_tokens(file_path)` | Disallowed token usage |
| `validate_naming_conventions(file_path)` | Kotlin naming convention violations |
| `validate_generation(feature_id?, phase?)` | Three-column per-screen verdict: `brain_match` / `roadmap_match` / `prd_match` with `completeness_pct` |

### Generation tools

All generation tools: validate output → auto-fix CLASS_A violations → retry (×3) → write with `.brain_backup_*` → compile-check → bug forecast → log to `generation_history`.

| Tool | What it generates |
|---|---|
| `generate_viewmodel(screen_id)` | `@HiltViewModel` + `StateFlow` + `Channel<Event>`; deterministic filler covers 80–90 % of function bodies. v3: emits `private_fields`, `init {}`, `computed_properties`, and `private_functions` from brain spec. |
| `generate_ui_state(screen_id)` | `@Immutable data class` UiState (v2) or sealed class (v1) |
| `generate_repository(repository_id)` | Interface `.kt` + `Impl.kt` as two files. v3: uses `firebase_pattern` for real Firebase boilerplate. |
| `generate_datamodel(model_id)` | `@Keep` data class with `@PropertyName` for Firestore |
| `generate_screen_scaffold(screen_id)` | `@Composable` + `collectAsStateWithLifecycle`. v3: renders a real `Column` UI body from `Screen.ui_components` — no TODO stub when the list is populated. |
| `generate_usecase(usecase_name)` | Single-function `UseCase` with `invoke()` |
| `generate_di_module(feature_name)` | Hilt `@Module @Binds` for feature repositories |
| `generate_nav_route(screen_id)` | Route object + `NavController` extension + `NavGraphBuilder` composable builder |
| `generate_viewmodel_test(screen_id)` | mockk + `StandardTestDispatcher` + `runTest` scaffold with correct state field names from brain spec |

### Bug forecasting tools

| Tool | What it detects |
|---|---|
| `forecast_bugs(screen_id)` | All 5 detectors for one screen; returns prioritised CLASS_A/B list |
| `detect_race_conditions()` | Read-then-write Firestore patterns without transactions |
| `detect_orphaned_documents()` | `consistency_link` violations that produce orphaned documents |
| `audit_production_readiness(phase)` | Full pre-launch bug audit for a phase |

### Sync & incremental tools

| Tool | What it does |
|---|---|
| `sync_brain` | Re-scans all generated files; adds drift items to `brain.known_violations` |
| `get_enrichment_status` | Session status: completed / pending / failed features and last checkpoint |
| `get_feature_artifacts(feature_id)` | All artifacts for one enriched feature from `brain/features/{id}/` |
| `aggregate_brain` | Rebuild `brain/cache/aggregated_brain.json` from all feature artifact files |

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
pytest                                     # 203 tests
pytest tests/test_new_phases.py -v         # Phase 4–6 coverage
pytest tests/test_cli_adapter.py -v        # CLI adapter detection
pytest tests/test_prd_enricher.py -v       # enrichment engine
pytest tests/test_schema.py -v             # Pydantic schema
pytest tests/test_generation_tools.py -v   # Phase 4 generation + registry
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
| 7 | Brain audit pre-generation gate: audit_brain, 39 MCP tools total | **Complete** |
| v3 | Brain spec enrichment fields: `private_fields`, `init_lines`, `private_functions`, `computed_properties`, `firebase_pattern`, `ui_components` | **Complete** |
