  Q1: Is this plan capable of phase-wise generation (auth → home → profile)?

  Yes, and it's already designed for it. Here's why:

  The brain schema has a Feature model with priority, feature_dependencies, and a screens[] list. The existing get_next_task() tool already implements this logic:

  Feature priority order:  auth (priority 1) → home (priority 2) → profile (priority 3)
  Feature blocking:        home is blocked until auth.status == "complete"
                           profile is blocked until home.status == "complete"

  The agent loop follows get_next_task() which always returns the next unblocked, highest-priority screen. So the loop naturally builds auth fully → home fully → profile fully without any
  extra logic. Feature promotion from in_progress → complete is gated on validate_generation ≥ 90%, so the next feature doesn't start until the current one genuinely passes.

  Within each feature, it goes screen by screen, and within each screen it builds all 9 components in dependency order.

  ---
  Q2: Is the loop Claude agent → MCP tools, or brain build → BuildOrchestrator, or both?

  Both — and they are two separate entry points for the same loop. Here's the distinction:

  OPTION A — Claude Code as agent (recommended for interactive dev)
  ─────────────────────────────────────────────────────────────────
  User says "build my project" inside Claude Code
      Claude Code (the LLM) IS the loop driver
          │
          ├─ calls MCP tools: get_next_task() → generate_viewmodel() → validate_generation() …
          │    (MCP server handles all generation: DeterministicFiller → CLIAdapter → NullAdapter)
          │
          └─ logic fill pass: Claude fills TODO stubs using its own LLM (no subprocess, zero overhead)

  Token cost: LOWEST — MCP pipeline handles ~80-90% deterministically, Claude only fills gaps


  OPTION B — brain build CLI (for automation / CI / scripts)
  ────────────────────────────────────────────────────────────
  Developer runs: brain build --output ./app/src/
      Python BuildOrchestrator IS the loop driver
          │
          ├─ calls ToolRegistry.execute("get_next_task", {}) (same code as MCP server, no stdio overhead)
          │    (same generation pipeline: DeterministicFiller → CLIAdapter → NullAdapter)
          │
          └─ logic fill pass: spawns CLIAdapter subprocess (claude --print) for TODO stubs

  Token cost: SAME deterministic path, but LLM call goes via subprocess if needed

  The relationship between the two:
  - Both drive the identical 13-step loop
  - Both call the same 35 tool implementations (Option A via MCP stdio, Option B via ToolRegistry directly)
  - Option A is better for interactive development inside Claude Code — Claude fills gaps natively
  - Option B is better for CI/CD, automation, or when running headless
  - The BuildOrchestrator Python class is the shared engine for Option B AND can serve as fallback if Option A is not in a Claude Code session

  For your stated goal ("scaffold using Claude Code and MCP server runs inside it") — Option A is the primary path. The brain build CLI is a bonus that makes it scriptable.

IMPORTANT  DIRECTIONS FOR CLUADE CODE: ONLY IMPLEMENT OPTION-A FOR NOW.