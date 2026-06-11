 Plan: Autonomous Brain Build Agent — brain build

 Context

 The MCP server has 35 fully working tools across 6 phases but no orchestrator that drives them end-to-end. Today a developer must call each tool manually (generate_viewmodel,
 validate_mvvm, etc.) per screen. This plan adds an autonomous Build Agent that loops through every phase, every screen, generates only missing artifacts, validates each output, forecasts
 bugs, and syncs the brain — with Claude Code as the LLM runtime (Option A) to minimise token consumption by delegating all generation work to the MCP pipeline (deterministic filler + CLI
 adapters) and reserving LLM calls strictly for TODO-stub fill gaps.

 ---
 Agent Loop (13 Steps)

 LOOP START
   1.  get_session_context()            → resume state, blocked features, last session
   2.  get_next_task()                  → exact next MCP call, feature, screen_id
   3.  get_phase_context(task)          → get_screen_graph + get_dependencies + get_phase_status
   4.  Classify task type               → SCREEN | DATA | DOMAIN | NAVIGATION | INFRA | TESTING
   5.  Build dependency graph           → ordered missing artifacts only (check ComponentStatus)
   6.  Generate missing artifacts       → call generation tools in dependency order
   7.  Logic fill pass                  → ONLY if spec_coverage < 1.0 and used_llm=False
   8.  Compile gate                     → compile_ok from write_result CompileVerifier
   9.  validate_generation(feature_id)  → gate on ≥ 90 % completeness, retry missing if < 90 %
   10. validate_phase(phase)            → check CLASS_A violations, report
   11. forecast_bugs(screen_id)         → 5 zero-LLM detectors, report CLASS_A
   12. sync_brain()                     → detect drift, update known_violations
   13. Update roadmap                   → already done by write_result via update_brain_status()
       └─ loop back to step 2 until get_next_task() returns done=True
 LOOP END → audit_production_readiness(phase)

 ---
 Step Detail

 Step 1 — get_session_context()

 Return fields used:
 - overall_progress → skip loop if "100%"
 - blocked_features → log and skip
 - current_feature.id → pass to step 3
 - next_step → hint for what's next

 Step 2 — get_next_task()

 - Returns {done, next_step, feature, screen, reason}
 - If done=True → exit loop, run final audit
 - screen is the screen_id used in all subsequent calls

 Step 3 — Phase Context (3 parallel calls)

 get_screen_graph(screen_id)    → full spec: viewmodel, repository, models, business_rules, nav
 get_dependencies(screen_id)    → {viewmodel, repository, use_cases, models, missing[]}
 get_phase_status(screen.phase) → completion_percent, screens_pending, blocking_violations
 Single get_screen_graph call provides ALL spec data for logic fill — no extra read calls.

 Step 4 — Task Type Classification

 ┌────────────────┬───────────────────────────────────────────────────────────────────┐
 │      Type      │                         Trigger condition                         │
 ├────────────────┼───────────────────────────────────────────────────────────────────┤
 │ SCREEN         │ screen.viewmodel is set AND viewmodel flag is False               │
 ├────────────────┼───────────────────────────────────────────────────────────────────┤
 │ DATA           │ screen.models non-empty AND (any model not in generation_history) │
 ├────────────────┼───────────────────────────────────────────────────────────────────┤
 │ DOMAIN         │ screen.use_cases non-empty AND any not generated                  │
 ├────────────────┼───────────────────────────────────────────────────────────────────┤
 │ NAVIGATION     │ scaffold flag True AND nav_route flag False                       │
 ├────────────────┼───────────────────────────────────────────────────────────────────┤
 │ INFRASTRUCTURE │ all screen flags True AND di_module flag False                    │
 ├────────────────┼───────────────────────────────────────────────────────────────────┤
 │ TESTING        │ viewmodel flag True AND tests flag False                          │
 └────────────────┴───────────────────────────────────────────────────────────────────┘

 Classification is read from brain.generation_status[screen_id].components (ComponentStatus flags).

 Step 5 — Dependency Graph (per screen)

 Ordered generation chain — only items where ComponentStatus flag is False:

 1. generate_datamodel(model_id)        ← for each model in screen.models
 2. generate_repository(repository_id)  ← screen.repository (or viewmodel.repository)
 3. generate_usecase(usecase_name)       ← for each in screen.use_cases
 4. generate_ui_state(screen_id)
 5. generate_viewmodel(screen_id)       ← LLM-assisted (DeterministicFiller first)
 6. generate_screen_scaffold(screen_id)
 7. generate_nav_route(screen_id)
 8. generate_di_module(feature_name)    ← once per feature, last
 9. generate_viewmodel_test(screen_id)

 Token saving rule: Before calling any generation tool, check ComponentStatus flag. If True, skip — no tool call made.

 Step 6 — Generate Missing Artifacts

 Each tool call passes output_path so write_result() handles:
 - Backup (.brain_backup_*.kt)
 - CompileVerifier smoke-check
 - BugEngine.forecast() (non-blocking)
 - update_brain_status() + BrainManager.save()
 - ROADMAP.md rewrite

 Output paths follow: {output_dir}/{feature_name}/{ClassName}.kt

 Step 7 — Logic Fill Pass (token-minimal)

 Only triggered when: result.spec_coverage < 1.0 AND result.used_llm == False
 (means NullAdapter ran — no LLM was available during generation)

 When triggered:
 1. Read the generated file content
 2. Count // TODO markers
 3. Fetch get_screen_graph(screen_id) (already fetched in step 3 — reuse)
 4. Use prompts/logic_fill_pass.txt prompt with screen_graph context
 5. Replace TODO sections in-place
 6. Overwrite via orchestrator.write_result() (creates backup, revalidates)

 When NOT triggered: If used_llm=True or spec_coverage == 1.0 — the deterministic filler or CLI adapter already produced real implementations. Skip entirely.

 Step 8 — Compile Gate

 Already executed by write_result(). Agent reads result.compile_ok:
 - True or None (kotlinc absent) → continue
 - False → log COMPILE_ERROR violation, do NOT block pipeline (non-blocking by design)

 Step 9 — validate_generation(feature_id=current_feature.id)

 completeness_pct = result["completeness_pct"]
 if completeness_pct < 90:
     missing_screens = [s for s in result["screens"] if not s["roadmap_match"]]
     → re-enter step 5 for each missing screen (max 1 retry per screen)

 Step 10 — validate_phase(phase)

 Checks all files for CLASS_A MVVM violations. Agent:
 - Logs each violation with rule_id, severity, description
 - CLASS_A violations are reported but not blocking (already auto-fixed during generation)

 Step 11 — forecast_bugs(screen_id)

 Returns {bug_count, class_a_count, bugs[]}. Agent:
 - Logs CLASS_A bugs as warnings in session output
 - Does NOT block the loop (forecasting is advisory)

 Step 12 — sync_brain()

 Called once per screen after all components generated. Detects drift between generation_history files and brain spec. Adds NEEDS_REVIEW violations for missing/extra functions.

 Step 13 — Roadmap Update

 No explicit call needed. write_result() already calls RoadmapGenerator.update_brain_status() → feature status promotion happens automatically. Loop detects completion via
 get_next_task().done == True.

 ---
 Task Type → Tool Mapping

 SCREEN       → [4, 5, 6] generate_ui_state + generate_viewmodel + generate_screen_scaffold
 DATA         → [1, 2]    generate_datamodel + generate_repository
 DOMAIN       → [3]       generate_usecase
 NAVIGATION   → [7]       generate_nav_route
 INFRASTRUCTURE → [8]     generate_di_module
 TESTING      → [9]       generate_viewmodel_test

 Full screen generation hits all 9 tools in dependency order.

 ---
 New Files to Create

 ┌─────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────┐
 │                    File                     │                                Purpose                                 │
 ├─────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
 │ project_brain/agents/__init__.py            │ Package init                                                           │
 ├─────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
 │ project_brain/agents/build_orchestrator.py  │ Main BuildOrchestrator class — Python-level loop driver                │
 ├─────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
 │ project_brain/agents/dependency_resolver.py │ DependencyResolver — builds ordered artifact list from ComponentStatus │
 ├─────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
 │ project_brain/agents/task_classifier.py     │ TaskClassifier — maps screen+ComponentStatus → TaskType enum           │
 ├─────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
 │ prompts/logic_fill_pass.txt                 │ Second-pass TODO fill prompt using full screen_graph context           │
 ├─────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
 │ .claude/agents/brain-build-agent.md         │ Claude Code agent definition (Option A)                                │
 ├─────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
 │ docs/AGENT-LOOP.md                          │ This plan, rendered as reference doc                                   │
 └─────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────┘

 Modified Files

 ┌───────────────────────────────┬───────────────────────────────┐
 │             File              │            Change             │
 ├───────────────────────────────┼───────────────────────────────┤
 │ project_brain/cli/commands.py │ Add brain build Click command │
 ├───────────────────────────────┼───────────────────────────────┤
 │ CLAUDE.md                     │ Document brain build command  │
 └───────────────────────────────┴───────────────────────────────┘

 ---
 New Module Detail

 build_orchestrator.py — BuildOrchestrator

 class BuildOrchestrator:
     def __init__(self, brain_path, output_dir, registry: ToolRegistry): ...
     async def run(self) -> BuildReport                    # full project build
     async def run_phase(self, phase: int) -> PhaseReport  # single phase
     async def run_screen(self, screen_id: str) -> ScreenReport  # single screen
     async def _logic_fill_pass(self, result, screen_graph) -> GenerationResult
     def _classify_task(self, screen_id) -> TaskType
     def _missing_artifacts(self, screen_id) -> list[ArtifactTask]

 Key: calls ToolRegistry.execute(tool_name, args) for all tool calls — same code path as MCP server. No duplication.

 dependency_resolver.py — DependencyResolver

 class DependencyResolver:
     def resolve(self, brain, screen_id) -> list[ArtifactTask]:
         """Returns ordered list of (tool_name, args) for missing components only."""
         # Reads ComponentStatus flags
         # Returns only items where flag is False
         # Preserves dependency order: data → domain → ui → nav → infra → test

 task_classifier.py — TaskClassifier

 class TaskType(str, Enum):
     SCREEN = "SCREEN"
     DATA = "DATA"
     DOMAIN = "DOMAIN"
     NAVIGATION = "NAVIGATION"
     INFRASTRUCTURE = "INFRASTRUCTURE"
     TESTING = "TESTING"

 class TaskClassifier:
     def classify(self, brain, screen_id) -> TaskType: ...

 brain build CLI command

 brain build --prd ./rough.md --output ./app/src/main/kotlin
 brain build --output ./app/src/  # if brain already exists
 brain build --phase 2 --output ./app/src/
 brain build --screen home --output ./app/src/
 brain build --resume --output ./app/src/  # continue from last session

 Full flow for --prd:
 1. brain enrich-prd (auto-runs if brain doesn't exist)
 2. brain init --from-prd (auto-runs if brain doesn't exist)
 3. BuildOrchestrator.run()

 prompts/logic_fill_pass.txt

 Prompt format (fills TODO stubs using full screen spec context):
 You are filling TODO stubs in a generated Kotlin {file_type} file.

 Screen spec:
 {screen_graph_json}

 Generated file (fill ALL // TODO markers):
 {current_content}

 Rules: [same rules as function_fill_v2.txt]
 Return ONLY the complete updated file content.

 .claude/agents/brain-build-agent.md

 Agent definition that Claude Code uses when invoked as a subagent. Contains:
 - System prompt with the 13-step loop as instructions
 - Rules: check ComponentStatus before each call, reuse step 3 context for step 7
 - Progress reporting format

 ---
 Token Minimisation Strategy

 ┌───────────────────────────────────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────┐
 │                                           Rule                                            │                                         Saving                                         │
 ├───────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ Check ComponentStatus before each generate call — skip if True                            │ Avoids regenerating already-done components                                            │
 ├───────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ Reuse get_screen_graph() result from step 3 in step 7                                     │ 1 read call per screen instead of 2                                                    │
 ├───────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ Logic fill pass ONLY when spec_coverage < 1.0 AND used_llm=False                          │ Skips LLM call when deterministic filler covered everything                            │
 ├───────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ get_next_task() drives the loop — no scanning or listing calls                            │ Single call determines full next action                                                │
 ├───────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ All generation uses MCP pipeline first (deterministic filler → CLI adapter → NullAdapter) │ LLM only called for complex function bodies; Claude Code fills gap only for TODO stubs │
 ├───────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
 │ write_result() handles save+roadmap update atomically                                     │ No separate save or roadmap calls needed                                               │
 └───────────────────────────────────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────┘

 ---
 Verification Plan

 1. Unit tests — tests/test_build_orchestrator.py:
   - test_classify_task_screen: verify SCREEN type for screen with unbuilt viewmodel
   - test_classify_task_data: verify DATA when models missing
   - test_dependency_order: verify datamodel before repository before viewmodel
   - test_skip_already_generated: verify component with flag=True is skipped
   - test_logic_fill_not_triggered_when_llm_used: verify fill pass skipped when used_llm=True
   - test_full_screen_build: NullAdapter brain → all 9 components → validate_generation ≥ 90%
 2. Integration test — brain build --output /tmp/test_build/ against sample brain:
   - All ComponentStatus flags flip to True
   - ROADMAP.md updated
   - validate_generation() returns ≥ 90%
   - forecast_bugs() runs without error
 3. Claude Code agent test — configure brain serve as MCP in Claude Code, invoke agent:
   - Agent calls tools in correct order
   - No duplicate generate calls for already-built components
   - Session resumable: stop mid-way, restart, resumes from correct position

 ---
 Existing Code to Reuse

 ┌─────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────┐
 │                 Purpose                 │                           Existing location                           │
 ├─────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
 │ Generation loop (template+LLM+validate) │ GenerationOrchestrator in code_generation.py                          │
 ├─────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
 │ All 35 tool executors                   │ ToolRegistry.execute() in tools/registry.py                           │
 ├─────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
 │ Component flag tracking                 │ update_brain_status() in roadmap_generator.py                         │
 ├─────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
 │ Task ordering hints                     │ RoadmapGenerator.next_step() in roadmap_generator.py                  │
 ├─────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
 │ Dependency data                         │ ReadTools.get_dependencies() in read_tools.py                         │
 ├─────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
 │ Prompt templates                        │ prompts/function_fill_v2.txt, prompts/function_fill_repository_v2.txt │
 ├─────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
 │ Validation                              │ validate_generation_brain() in validation_tools.py                    │
 ├─────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
 │ Bug forecasting                         │ BugEngine.forecast() in bug_engine.py                                 │
 ├─────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────┤
 │ Brain persistence                       │ BrainManager.load() / .save() in brain/manager.py                     │
 └─────────────────────────────────────────┴───────────────────────────────────────────────────────────────────────┘
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌

─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Claude has written up a plan and is ready to execute. Would you like to proceed?

 > 1. Yes, and use auto mode
   2. Yes, manually approve edits
   3. No, refine with Ultraplan on Claude Code on the web
   4. Tell Claude what to change
      shift+tab to approve with this feedback