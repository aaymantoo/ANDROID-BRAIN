# Setting Up Brain Engine MCP in Claude Code

This guide walks you through installing the Brain Engine MCP server, wiring it into Claude Code, and running your first Android project build from a PRD.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | `python --version` |
| pip | latest | `pip install --upgrade pip` |
| Claude Code | latest | [claude.ai/code](https://claude.ai/code) |
| Git | any | for cloning this repo |
| Android project | any | target directory for generated code |

**Recommended (no API key needed):** Claude Code Pro subscription. The `brain` CLI auto-detects and reuses your Claude Code session.

---

## Step 1 — Install the Brain Engine

Clone this repository and install it as an editable package:

```bash
git clone https://github.com/aaymantoo/ANDROID-BRAIN.git brain-mcp
cd brain-mcp
pip install -e ".[dev]"
```

Verify the install:

```bash
brain doctor
```

Expected output:

```
LLM adapter : ClaudeCodeCLIAdapter (claude CLI)
CLI tools   : claude ✓  gemini ✗  llm ✗  ollama ✗
API keys    : ANTHROPIC_API_KEY ✗  OPENAI_API_KEY ✗
```

If `claude ✗` appears, the `claude` CLI is not on your PATH. Claude Code Pro users can install it from [claude.ai/code](https://claude.ai/code). Alternatively, any of the other adapters will work.

---

## Step 2 — Register the MCP Server in Claude Code

Claude Code reads MCP server configuration from a `.mcp.json` file in your **Android project root** (or from `~/.claude/mcp.json` for a global registration).

### Option A — Project-level (recommended)

Inside your Android project root, create `.mcp.json`:

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

This tells Claude Code to launch `brain serve` whenever it opens that project, using `PROJECT_BRAIN.json` in the project root as the brain file.

### Option B — Global (all projects)

Add the same block to `~/.claude/mcp.json` (create the file if it does not exist). Use an absolute path for `BRAIN_PATH`:

```json
{
  "mcpServers": {
    "brain-engine": {
      "command": "brain",
      "args": ["serve"],
      "env": {
        "BRAIN_PATH": "/absolute/path/to/your/project/PROJECT_BRAIN.json"
      }
    }
  }
}
```

### Verify the registration

Open your Android project in Claude Code and run:

```
/mcp
```

You should see `brain-engine` listed as a connected server with 39 tools.

---

## Step 3 — Prepare a PRD

The Brain Engine requires a Product Requirements Document (PRD). If you already have detailed requirements, write them as a Markdown file. If you only have rough notes, the enrichment step will expand them into a full hyperspec.

### Option A — Enrich a rough PRD (recommended)

```bash
brain enrich-prd ./rough_notes.md --output ./enriched_prd.md
```

This calls your LLM (Claude Code session, no API key needed) and produces a complete hyperspec covering screens, ViewModels, repositories, state machines, business rules, and Firestore schema.

Validate the result:

```bash
brain validate-prd ./enriched_prd.md
```

The score must be **≥ 80 / 100** before you can generate the brain. If it is lower, the output lists exactly which dimensions are incomplete.

### Option B — Skip enrichment

If you already have a detailed PRD, run `brain validate-prd` directly. If it passes, proceed to Step 4.

---

## Step 4 — Generate the Brain

```bash
brain init --from-prd ./enriched_prd.md --output ./PROJECT_BRAIN.json
```

This produces:
- `PROJECT_BRAIN.json` — the single source of truth for all generation
- `ROADMAP.md` — feature → screen → component status tree

Inspect the result:

```bash
brain status
```

Expected output:

```
Project     : YourAppName
Screens     : 12
ViewModels  : 12
Repositories: 6
Features    : 4
Components  : 0 / 96 done
```

---

## Step 5 — Run the Brain Audit

Before generating any code, audit the brain for structural issues:

```bash
# Via CLI (optional manual check)
brain serve &
# then in Claude Code: audit_brain()

# Or just let the build agent do it automatically (Step 6)
```

The audit checks:
- Broken Screen → ViewModel / Repository references
- Circular navigation dependencies
- Features referencing screens that don't exist
- Business rules not wired to any ViewModel function

A score ≥ 60 with no critical issues is required for generation to proceed. The build agent runs this automatically — you do not need to call it manually.

---

## Step 6 — Build the Project

### Option A — Full autonomous build (recommended)

```bash
brain build --prd ./enriched_prd.md --output ./app/src/main/kotlin
```

This command:
1. Detects that a brain needs to be built (runs `enrich-prd` + `brain init` if needed)
2. Starts `brain serve` (the MCP server)
3. Prints the exact agent invocation to paste into Claude Code

Paste the printed prompt into Claude Code. The `brain-build-agent` takes over and drives the full pipeline:

```
Pre-flight → audit_brain → 13-step generation loop (per screen):
  datamodel → repository → usecase → ui_state → viewmodel →
  scaffold → nav_route → di_module → test →
  UI design pass → logic fill pass → compile gate →
  validate_generation → validate_phase → forecast_bugs → sync_brain
→ Final audit
```

### Option B — Start server manually, then invoke agent

```bash
brain serve
```

In a separate Claude Code session:

```
Use the brain-build-agent to build my project to ./app/src/main/kotlin
```

### Option C — Scoped build (single feature or screen)

```bash
brain build --output ./app/src/main/kotlin --phase 1
brain build --output ./app/src/main/kotlin --screen LoginScreen
brain build --output ./app/src/main/kotlin --resume   # continue after interruption
```

---

## Step 7 — Monitor Progress

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

---

## Step 8 — Incremental Builds (large PRDs)

For large PRDs (10+ features), use the incremental enrichment pipeline to avoid timeout/crash losing all progress:

```bash
# Enrich one feature at a time
brain enrich-feature auth --prd ./enriched_prd.md
brain enrich-feature payments --prd ./enriched_prd.md

# Or enrich an entire phase at once
brain enrich-phase core --prd ./enriched_prd.md

# Resume after any interruption
brain resume --prd ./enriched_prd.md
```

After enriching, rebuild the aggregated brain:

```bash
brain serve  # uses brain/cache/aggregated_brain.json automatically
```

---

## Useful Commands During Development

```bash
# Show current generation progress
brain status

# Print or regenerate ROADMAP.md
brain roadmap
brain roadmap --update

# Rollback a generated file to its last backup
brain rollback app/src/main/kotlin/com/example/auth/LoginViewModel.kt

# List low-confidence items for manual review
brain review

# Re-scan generated files for drift from brain spec
brain sync
```

---

## Generated File Layout

Given `--output ./app/src/main/kotlin` and package `com.example.app`, generated files land at:

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
│       └── User.kt                 (data model)
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

## Troubleshooting

### `Brain Engine MCP server is not connected`

The `brain serve` process is not running. Start it in a terminal:

```bash
cd /path/to/your/android/project
brain serve
```

Or use `brain build` which starts the server automatically.

### `brain: command not found`

The package is not installed or the pip scripts directory is not on your PATH.

```bash
pip install -e ".[dev]"
# then check:
where brain        # Windows
which brain        # macOS/Linux
```

If `where brain` returns nothing, add the pip scripts directory to your PATH:
- **Windows**: `%APPDATA%\Python\Python3xx\Scripts`
- **macOS/Linux**: `~/.local/bin`

### `Brain audit FAILED` before generation

The brain has structural issues. The failure report lists them. Common causes:

| Issue | Fix |
|---|---|
| `broken_reference: Screen 'X' → ViewModel 'Y' not found` | Add a ViewModel with `id: Y` to your brain, or fix the screen's `viewmodel` field |
| `missing_screen: Feature 'X' references screen 'Y' not in brain.screens` | Add the screen to `brain.screens`, or remove it from the feature's `screens` list |
| `circular_dependency` | Fix the navigation graph so no route loops back to itself |

Run `brain status` and `brain validate-prd` to diagnose incomplete brains before running `brain init`.

### `PRD score too low (< 80)`

Run `brain validate-prd ./enriched_prd.md` — it prints a per-dimension breakdown. The most commonly missing sections are:
- Firestore schema (collections, fields, consistency rules)
- State machines (entity states and transitions)
- Business rules (triggers and required updates)

Use `brain enrich-prd` to fill these automatically.

### `audit_brain` not appearing in `/mcp` tool list

The server started before `PROJECT_BRAIN.json` existed, or `BRAIN_PATH` points to the wrong file. Check:

```bash
brain status   # verifies the brain file is readable
```

Then restart the server (kill the `brain serve` process and re-run `brain build`).

---

## Pipeline Summary

```
rough_notes.md
    │
    ▼  brain enrich-prd
enriched_prd.md
    │
    ▼  brain validate-prd  (score ≥ 80 required)
    │
    ▼  brain init --from-prd
PROJECT_BRAIN.json + ROADMAP.md
    │
    ▼  brain build  (starts brain serve + triggers brain-build-agent)
    │
    ▼  audit_brain  (score ≥ 60 + no critical issues required)
    │
    ▼  13-step generation loop (per screen, dependency order)
    │
    ▼  Final audit (audit_production_readiness)
    │
    ▼  Generated Kotlin files in OUTPUT_DIR
```
