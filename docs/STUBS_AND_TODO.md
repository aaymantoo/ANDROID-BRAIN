# Stubs And TODO

This file is the project gap ledger. It records intentional stubs and follow-up work so future phases can be filled smoothly.

---

## Phase 0C Follow-Up Gaps

- `features` list is only populated when `brain init` is run from an enriched PRD that includes explicit feature groupings. Add a post-init heuristic that auto-groups screens by shared route prefix or ViewModel naming when no features are declared (e.g., all screens whose id starts with `auth_` → Auth feature).
- `di_module` target resolution: the template uses `feature_name` as `target_id`, so `update_brain_status` looks up the feature by id/name. If the feature name has spaces or mixed case, the lookup can miss — normalise both sides to lowercase before comparing.
- `validate_mvvm` does not yet call `mark_validated()` automatically. Wire it: when `validate_mvvm` returns zero CLASS_A violations, flip `ComponentStatus.validated = True` for that screen and rewrite ROADMAP.md.
- `brain roadmap --feature` currently outputs raw JSON via `get_feature_status`; replace with a rendered markdown table for readability in the terminal.
- No test exercises the full `brain init → write_result → ROADMAP.md updated` integration path. Add one integration test that calls `BrainGenerator.write()` and asserts ROADMAP.md is created.

## Phase 0B Follow-Up Gaps

- `brain enrich-prd` currently runs the entire enrichment as one LLM call. For very long PRDs (> 6 000 tokens), consider chunking by feature or using a streaming response.
- Pattern detection in `_detect_patterns()` is text-presence heuristics. A structured parse of the LLM output JSON would be more reliable.
- `--interactive` gap-fill asks one question per missing dimension; could be extended to use a structured dialogue for more complex gaps.
- Integration test for `PRDEnricher` with a live CLI adapter is not included (would require `claude` or `ollama` in CI).

## Phase 1 Follow-Up Gaps

- PRD parser is deterministic and heuristic-first. For unstructured or narrative PRDs that do not follow `PRD_TEMPLATE.md`, consider an LLM-assisted parse fallback.
- `brain review` lists and clears items but does not support editing individual items interactively.
- Expand PRD parser coverage for complex tables and nested feature specifications.

## Phase 2 Follow-Up Gaps

- Manually connect `brain serve` to Claude Code or another MCP client once a real `PROJECT_BRAIN.json` is generated to verify end-to-end stdio wiring.
- Add protocol-level MCP integration tests if a lightweight test client is added.

## Phase 3 Follow-Up Gaps

- Add more Kotlin fixtures for edge cases in nested composables, extension functions, and multiline repository method signatures.
- Firestore/state-transition validation uses string presence checks; upgrade to structured write-operation detection.
- Add CLI wrapper commands for validation tools for direct command-line use.

## Phase 4 Follow-Up Gaps

- `ClaudeAdapter` and `OpenAIAdapter` are tested only via static inspection; add integration tests once a test API key is available in CI.
- Combined repository output (`interface + impl`) is written to one file; consider splitting into two separate paths.
- `generate_usecase` uses a heuristic `invoke()` signature; extend brain schema to allow explicit UseCase function specs.
- Auto-fixer handles A001 and A002 only; A003 (business logic in Composable) and A005 (missing Repository interface) require structural changes the auto-fixer cannot make safely.
- v2 templates cover all 9 generation tools except `nav_route` (falls back to v1 via ChoiceLoader); write a dedicated v2 nav_route template with type-safe sealed-class routes.

## Phase 5 Stubs

- `project_brain/engines/bug_engine.py`
- `project_brain/tools/bug_tools.py`

Planned scope: static analysis of brain state machines and historical violation patterns to predict likely runtime bugs before the screen is built.

## Phase 6 Stubs

- `project_brain/engines/state_engine.py`
- `project_brain/tools/management_tools.py`
- `brain sync` command (registers generated files and tracks drift from brain).
- Incremental sync and conflict resolution implementation.

Planned scope: keep `PROJECT_BRAIN.json` in sync as the codebase evolves; detect when generated code has diverged from the brain spec and surface diffs.
