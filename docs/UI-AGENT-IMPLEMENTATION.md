The Plan is Sound — Here's Why

  The ui-agent.md approach is the right call because:

  - No brain schema changes needed
  - Claude Code naturally reads files — it's built for exactly this
  - The design system files are the single source of truth for UI (not the brain)
  - validate_design_tokens() already exists as a compliance gate after

  ---
  What the UI Agent Would Read

  Design system files (in the target Android project):
  ├── design.md              → layout patterns, spacing rules, component usage guide
  ├── ui/theme/Theme.kt      → MaterialTheme setup, color scheme
  ├── ui/theme/Typography.kt → text styles (headlineSmall, bodyMedium, etc.)
  ├── ui/theme/Shape.kt      → corner radii, shapes
  └── ui/components/         → existing custom Composables to reuse (Button, Card, etc.)

  From MCP server:
  └── get_screen_graph(screen_id) → UiState fields, ViewModel functions, nav args, business rules

  The agent generates real Compose content inside ScreenNameContent() using MaterialTheme.colorScheme.*, MaterialTheme.typography.*, and existing components — never inventing values.

  ---
  Where to Insert It in the Loop

  Step 6c — UI Design Pass, inserted between scaffold generation and logic fill:

  Step 6a  generate_screen_scaffold(screen_id)
           → writes HomeScreen.kt with // TODO: implement screen content

  Step 6b  Logic fill pass (ViewModel / Repository // TODOs)
           → fills business logic stubs

  Step 6c  ── UI Design Pass (NEW) ──────────────────────────────────
           IF scaffold file contains "// TODO: implement screen content"
           AND design system files exist at design_system_dir:
               spawn ui-agent with:
                 - screen_id          → calls get_screen_graph() via MCP
                 - scaffold file path → reads + rewrites ScreenContent()
                 - design_system_dir  → reads Theme/Typography/Shape/components
           ELSE:
               log "UI pass skipped — no design system files found at {path}"
               leave TODO stub (validate_design_tokens will flag later)
           ──────────────────────────────────────────────────────────

  Step 7   validate_mvvm(output_path)
  Step 8   validate_design_tokens(output_path)    ← catches any token violations
  Step 9   validate_generation(feature_id)

  This position is correct because:
  - The scaffold file is already on disk (step 6a wrote it)
  - The UI fill happens before MVVM and token validation
  - validate_design_tokens() acts as the quality gate on what the agent produced
  - If the agent produces a violation, the build loop can flag it before marking the phase complete

  ---
  Before Marking the Phase Complete

  The phase complete gate should be:

  Phase Complete requires ALL of:
    ✓ validate_generation(phase) → completeness_pct ≥ 90%
    ✓ validate_phase(phase)      → zero CLASS_A MVVM violations
    ✓ validate_design_tokens()   → zero token violations (per generated screen file)
    ✓ forecast_bugs(screen_id)   → zero CLASS_A bugs
    ✓ NO scaffold files with "// TODO: implement screen content" remaining

  That last check is the new gate the UI agent enables — a phase is not complete if any screen still has the TODO stub in its ScreenContent() function.

  ---
  What ui-agent.md Needs to Know

  The agent prompt should include:

  1. Task: Fill the // TODO: implement screen content section in {file_path}
  2. Rules:
    - Use only MaterialTheme.colorScheme.*, MaterialTheme.typography.*, MaterialTheme.shapes.* — never hardcoded values
    - Reuse components from components/ dir before writing new ones
    - No business logic in Composables — only call ViewModel lambdas passed as parameters
    - UiState fields are available via the uiState parameter already wired
    - All onX lambdas are already wired — call them, don't reimplement them
  3. Read first: design.md → Theme.kt → Typography.kt → Shape.kt → components/ → get_screen_graph()
  4. Output: Replace // TODO: implement screen content section only, leave everything else untouched

  ---
  One Configuration Needed

  The build orchestrator needs to know where design system files live. Two options:

  ┌─────────────────────────────────────────────────────────────┬───────────────────────────────────────┐
  │                           Option                            │                  How                  │
  ├─────────────────────────────────────────────────────────────┼───────────────────────────────────────┤
  │ brain build --design-system ./app/src/main/kotlin/ui/theme/ │ CLI flag, most flexible               │
  ├─────────────────────────────────────────────────────────────┼───────────────────────────────────────┤
  │ Store path in ProjectBrain.meta as design_system_path       │ Persisted in brain, no flag each time │
  └─────────────────────────────────────────────────────────────┴───────────────────────────────────────┘

  The second option is cleaner — add one field to Meta so the agent always knows where to look.

  ---
  Verdict: This fits perfectly into the plan. The UI agent becomes step 6c, runs conditionally, and validate_design_tokens() already exists to enforce correctness. The only schema touch is
  one optional design_system_path field on Meta. Want me to update the plan document and move to implementation?
