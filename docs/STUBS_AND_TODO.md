# Stubs And TODO

This file tracks intentional stubs, known limitations, and follow-up work.

Phases 5 and 6 are now complete. All stubs that were listed for those phases have been filled.

---

## Remaining Follow-Up Gaps

### Phase 0C

- `features` list is only populated when `brain init` is run from an enriched PRD that includes explicit feature groupings. A post-init heuristic that auto-groups screens by shared route prefix or ViewModel naming would help brains generated from `--from-code`.
- `validate_mvvm` does not yet call `mark_validated()` automatically. Wire it: when `validate_mvvm` returns zero CLASS_A violations, flip `ComponentStatus.validated = True` for that screen and rewrite ROADMAP.md.
- `brain roadmap --feature` currently outputs raw JSON via `get_feature_status`; replace with a rendered markdown table for readability in the terminal.

### Phase 1

- PRD parser is deterministic and heuristic-first. For unstructured or narrative PRDs that do not follow `PRD_TEMPLATE.md`, consider an LLM-assisted parse fallback.
- `brain review` lists and clears items but does not support editing individual items interactively.

### Phase 2

- Manually connect `brain serve` to Claude Code or another MCP client once a real `PROJECT_BRAIN.json` is generated to verify end-to-end stdio wiring.
- Add protocol-level MCP integration tests if a lightweight test client is added.

### Phase 3

- Add more Kotlin fixtures for edge cases in nested composables, extension functions, and multiline repository method signatures.
- Firestore/state-transition validation uses string presence checks; upgrade to structured write-operation detection.
- Add CLI wrapper commands for validation tools for direct command-line use.

### Phase 4

- `ClaudeAdapter` and `OpenAIAdapter` are tested only via static inspection; add integration tests once a test API key is available in CI.
- `generate_usecase` uses a heuristic `invoke()` signature; extend brain schema to allow explicit UseCase function specs.
- Auto-fixer handles A001 and A002 only; A003 (business logic in Composable) and A005 (missing Repository interface) require structural changes the auto-fixer cannot make safely.
- `DeterministicFunctionBodyGenerator` falls through to LLM (or TODO stub) for complex `business_rule` strings that describe multi-step validation logic. Extending the pattern matcher to handle conditional branching would raise confidence further.

### Phase 5 (Bug Engine)

- `StateTransitionBugDetector` and `FirestoreConsistencyDetector` use string presence checks. Upgrade to structured Firestore call detection for fewer false positives.
- `RevenueIntegrityDetector` pattern is broad — any ViewModel with financial terms triggers it. Narrow by also checking for direct `emit()` / `.set()` calls instead of just `viewModelScope`.
- No integration tests exercise the detectors against real generated files (only temp file in `test_race_condition_detected_in_content`). Add fixture files in `tests/fixtures/generated/` and test all 5 detectors against them.
- `BugEngine.forecast()` results are non-blocking in `write_result()` but not persisted to the brain. Consider adding a `bug_history` field to `ProjectBrain` to track forecast trends across sessions.

### Phase 6 (Sync)

- `sync_brain` detects deleted files and missing/extra function names, but does not offer an interactive resolution flow ("trust code" vs "trust brain"). Wire this into the CLI: `brain sync --resolve`.
- `StateTransitionEngine.validate_brain()` walks all files in `generation_history` but has no test coverage for the multi-file path. Add a fixture-based integration test.
- `brain sync` CLI command stub in `cli/commands.py` — wire it to call `sync_brain()` and print the `SyncReport`.

### validate_generation

- `_load_prd()` scans the brain file's parent directory for `.md` files starting with `prd`/`enriched`/`product`. If the PRD is stored elsewhere, `prd_match` will always be `None`. Add `brain.meta.source_prd` field to store the PRD path explicitly during `brain init`.
- `_check_screen()` uses `brain.generation_history` lookup which may miss files written before the brain was upgraded to track history. Add a fallback file-glob search.

### Testing

- No test covers the full `brain init → write_result → ROADMAP.md updated → validate_generation gated` integration path end-to-end. Add one integration test that calls `BrainGenerator.write()`, writes at least one component, then asserts `validate_generation` returns non-zero `completeness_pct`.
- `StateTransitionEngineTest` and `ValidateGenerationTest.test_feature_filter_works` skip when the fixture brain has no state machines or features. Extend `tests/fixtures/sample_prd.md` to include at least one state machine with transitions.
