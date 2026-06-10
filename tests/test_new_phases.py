"""Tests for Phase 4 fixes, Phase 5 bug engine, Phase 6 sync, validate_generation, and DeterministicFunctionBodyGenerator."""

from __future__ import annotations

import unittest
from pathlib import Path

from project_brain.generators.prd_parser import PRDParser
from project_brain.llm.adapter import FillFunctionsSpec, FunctionSpec, NullAdapter


def _brain():
    return PRDParser().parse_file(Path("tests/fixtures/sample_prd.md"))


# ── B004 fix: data-class UiState no longer triggers B004 ────────────────────

class B004FalsePositiveTest(unittest.TestCase):
    def test_immutable_data_class_uistate_passes_b004(self) -> None:
        from project_brain.engines.rule_engine import MVVMValidationEngine
        content = (
            "package com.example.auth\n"
            "import androidx.compose.runtime.Immutable\n\n"
            "@Immutable\n"
            "data class PhoneEntryUiState(\n"
            "    val phoneNumber: String = \"\",\n"
            "    val isLoading: Boolean = false,\n"
            ")\n"
        )
        report = MVVMValidationEngine().validate_content(content, "PhoneEntryUiState.kt")
        b004 = [v for v in report.violations if v.rule_id == "B004"]
        self.assertEqual(b004, [], "B004 should not fire for @Immutable data class UiState")

    def test_sealed_class_without_loading_still_triggers_b004(self) -> None:
        from project_brain.engines.rule_engine import MVVMValidationEngine
        content = (
            "sealed class HomeUiState {\n"
            "    data class Success(val data: String) : HomeUiState()\n"
            "    data class Error(val msg: String) : HomeUiState()\n"
            "}\n"
        )
        report = MVVMValidationEngine().validate_content(content, "HomeUiState.kt")
        b004 = [v for v in report.violations if v.rule_id == "B004"]
        self.assertTrue(len(b004) > 0, "B004 should fire for sealed class UiState without Loading")


# ── Repository split ─────────────────────────────────────────────────────────

class RepositorySplitTest(unittest.IsolatedAsyncioTestCase):
    async def test_generate_repository_pair_returns_two_results(self) -> None:
        from project_brain.generators.code_generation import GenerationOrchestrator
        brain = _brain()
        orch = GenerationOrchestrator(brain, llm=NullAdapter())
        pair = await orch.generate_repository_pair("OrderRepository")
        self.assertIsNotNone(pair.interface)
        self.assertIsNotNone(pair.implementation)
        self.assertIn("interface", pair.interface.content)
        self.assertIn("class", pair.implementation.content)

    async def test_generate_repository_still_returns_combined_for_compat(self) -> None:
        from project_brain.generators.code_generation import GenerationOrchestrator
        brain = _brain()
        orch = GenerationOrchestrator(brain, llm=NullAdapter())
        result = await orch.generate_repository("OrderRepository")
        self.assertIn("interface", result.content)
        self.assertIn("class", result.content)


# ── v2 nav_route template ────────────────────────────────────────────────────

class NavRouteV2Test(unittest.IsolatedAsyncioTestCase):
    async def test_v2_nav_route_has_navcontroller_extension(self) -> None:
        from project_brain.brain.schema import ViewModel
        from project_brain.generators.code_generation import GenerationOrchestrator
        brain = _brain()
        # Force v2 engine by adding enriched ViewModel
        brain.viewmodels[0] = brain.viewmodels[0].model_copy(update={"ui_state_type": "data_class"})
        orch = GenerationOrchestrator(brain, llm=NullAdapter())
        result = await orch.generate_nav_route("OrderTrackingScreen")
        self.assertIn("NavController", result.content)
        # v2 template renders extension as: fun NavController.navigateTo{ScreenName}(
        self.assertIn("NavController.navigateTo", result.content)

    async def test_v1_nav_route_still_works(self) -> None:
        from project_brain.generators.code_generation import GenerationOrchestrator
        brain = _brain()
        orch = GenerationOrchestrator(brain, llm=NullAdapter())
        result = await orch.generate_nav_route("OrderTrackingScreen")
        self.assertIn("object OrderTrackingRoute", result.content)


# ── DeterministicFunctionBodyGenerator ──────────────────────────────────────

class DeterministicFillerTest(unittest.TestCase):
    def _make_spec(self, functions, ui_state_type="data_class") -> FillFunctionsSpec:
        return FillFunctionsSpec(
            functions=functions,
            architecture="MVVM+Hilt",
            package_name="com.example",
            state_class_name="TestUiState",
            dependencies=["sendOtpUseCase: SendOtpUseCase"],
            business_rules=[],
            violations_to_avoid=[],
            ui_state_type=ui_state_type,
        )

    def test_simple_state_update_high_confidence(self) -> None:
        from project_brain.generators.deterministic_body_filler import DeterministicFunctionBodyGenerator
        fn = FunctionSpec(name="onPhoneNumberChanged", params=["phoneNumber: String"],
                          returns="Unit", business_rule=None)
        fn.state_updates = ["phoneNumber", "phoneNumberError"]
        fn.events_fired = []
        fn.concurrent = False
        spec = self._make_spec([fn])
        result, confidence = DeterministicFunctionBodyGenerator().fill(spec)
        self.assertGreaterEqual(confidence, 0.75)
        self.assertIn("_uiState.update", result)
        self.assertIn("phoneNumber", result)

    def test_event_firing_async_body(self) -> None:
        from project_brain.generators.deterministic_body_filler import DeterministicFunctionBodyGenerator
        fn = FunctionSpec(name="onSendOtpClicked", params=[], returns="Unit", business_rule=None)
        fn.state_updates = ["isSendingOtp", "errorMessage"]
        fn.events_fired = ["NavigateToOtp"]
        fn.concurrent = False
        spec = self._make_spec([fn])
        result, confidence = DeterministicFunctionBodyGenerator().fill(spec, {"event_class": "PhoneEntryUiEffect"})
        self.assertGreaterEqual(confidence, 0.75)
        self.assertIn("viewModelScope.launch", result)
        self.assertIn("runCatching", result)

    def test_zero_confidence_falls_through_to_todo(self) -> None:
        from project_brain.generators.deterministic_body_filler import DeterministicFunctionBodyGenerator
        fn = FunctionSpec(name="doSomethingComplex", params=[], returns="Unit", business_rule="Complex rule")
        fn.state_updates = []
        fn.events_fired = []
        fn.concurrent = False
        spec = self._make_spec([fn], ui_state_type="sealed_class")
        result, confidence = DeterministicFunctionBodyGenerator().fill(spec)
        self.assertLess(confidence, 0.75)


# ── StateTransitionEngine ────────────────────────────────────────────────────

class StateTransitionEngineTest(unittest.TestCase):
    def test_detect_missing_update(self) -> None:
        from project_brain.engines.state_engine import StateTransitionEngine
        brain = _brain()
        if not brain.state_machines:
            self.skipTest("No state machines in fixture brain")
        machine = brain.state_machines[0]
        transition = machine.transitions[0] if machine.transitions else None
        if transition is None or not transition.required_firestore_updates:
            self.skipTest("No transitions with required updates")
        engine = StateTransitionEngine()
        violations = engine.validate_transition(
            entity=machine.entity,
            from_state=transition.from_state,
            to_state=transition.to,
            file_content="// empty file",
            brain=brain,
        )
        self.assertTrue(len(violations) > 0)
        self.assertEqual(violations[0].missing_update, transition.required_firestore_updates[0])

    def test_no_violation_when_update_present(self) -> None:
        from project_brain.engines.state_engine import StateTransitionEngine
        brain = _brain()
        if not brain.state_machines or not brain.state_machines[0].transitions:
            self.skipTest("No state machines in fixture brain")
        machine = brain.state_machines[0]
        transition = machine.transitions[0]
        update = transition.required_firestore_updates[0] if transition.required_firestore_updates else None
        if not update:
            self.skipTest("No required updates")
        engine = StateTransitionEngine()
        violations = engine.validate_transition(
            entity=machine.entity,
            from_state=transition.from_state,
            to_state=transition.to,
            file_content=f"// contains: {update}",
            brain=brain,
        )
        self.assertEqual(violations, [])


# ── BugEngine ────────────────────────────────────────────────────────────────

class BugEngineTest(unittest.TestCase):
    def test_forecast_returns_list(self) -> None:
        from project_brain.engines.bug_engine import BugEngine
        brain = _brain()
        bugs = BugEngine().forecast(brain, "HomeScreen")
        self.assertIsInstance(bugs, list)

    def test_audit_returns_production_ready_flag(self) -> None:
        from project_brain.engines.bug_engine import BugEngine
        brain = _brain()
        result = BugEngine().audit(brain, phase=1)
        self.assertIn("production_ready", result)
        self.assertIn("class_a_count", result)
        self.assertIn("bugs", result)

    def test_race_condition_detected_in_content(self) -> None:
        from project_brain.engines.bug_engine import RaceConditionDetector
        import tempfile, os
        content = (
            "suspend fun complete() {\n"
            "    val doc = firestore.collection(\"orders\").document(id).get().await()\n"
            "    firestore.collection(\"orders\").document(id).set(updated).await()\n"
            "}\n"
        )
        brain = _brain()
        with tempfile.NamedTemporaryFile(suffix=".kt", mode="w", delete=False) as f:
            f.write(content)
            tmp = f.name
        try:
            from project_brain.brain.schema import GenerationHistoryEntry
            brain.generation_history.append(GenerationHistoryEntry(
                tool="repository_impl.kt.j2", target="HomeScreen",
                output_path=tmp, status="clean",
            ))
            bugs = RaceConditionDetector().detect(brain)
            self.assertTrue(any(b.bug_type == "RACE_CONDITION" for b in bugs))
        finally:
            os.unlink(tmp)


# ── sync_brain ───────────────────────────────────────────────────────────────

class SyncBrainTest(unittest.TestCase):
    def test_sync_detects_deleted_file(self) -> None:
        from project_brain.tools.management_tools import sync_brain_instance
        from project_brain.brain.schema import GenerationHistoryEntry
        import os
        brain = _brain()
        fake_path = os.path.join("nonexistent", "path", "HomeViewModel.kt")
        brain.generation_history.append(GenerationHistoryEntry(
            tool="viewmodel.kt.j2", target="HomeScreen",
            output_path=fake_path, status="clean",
        ))
        report = sync_brain_instance(brain)
        # report.deleted normalises paths; check basename is present
        deleted_basenames = [os.path.basename(p) for p in report.deleted]
        self.assertIn("HomeViewModel.kt", deleted_basenames)

    def test_sync_empty_history_returns_zero_scanned(self) -> None:
        from project_brain.tools.management_tools import sync_brain_instance
        brain = _brain()
        brain.generation_history.clear()
        report = sync_brain_instance(brain)
        self.assertEqual(report.scanned, 0)


# ── validate_generation ──────────────────────────────────────────────────────

class ValidateGenerationTest(unittest.TestCase):
    def test_returns_completeness_pct(self) -> None:
        from project_brain.tools.validation_tools import validate_generation_brain
        brain = _brain()
        result = validate_generation_brain(brain)
        self.assertIn("completeness_pct", result)
        self.assertIn("screens", result)
        self.assertIsInstance(result["completeness_pct"], int)

    def test_screen_report_has_three_verdicts(self) -> None:
        from project_brain.tools.validation_tools import validate_generation_brain
        brain = _brain()
        result = validate_generation_brain(brain)
        if result["screens"]:
            screen = result["screens"][0]
            self.assertIn("brain_match", screen)
            self.assertIn("roadmap_match", screen)
            self.assertIn("prd_match", screen)

    def test_feature_filter_works(self) -> None:
        from project_brain.tools.validation_tools import validate_generation_brain
        brain = _brain()
        if not brain.features:
            self.skipTest("No features in fixture brain")
        fid = brain.features[0].id
        result = validate_generation_brain(brain, feature_id=fid)
        self.assertEqual(result["feature_id"], fid)


# ── compile_ok field present in GenerationResult ─────────────────────────────

class CompileVerifierFieldTest(unittest.IsolatedAsyncioTestCase):
    async def test_generation_result_has_compile_ok_field(self) -> None:
        from project_brain.generators.code_generation import GenerationOrchestrator
        brain = _brain()
        orch = GenerationOrchestrator(brain, llm=NullAdapter())
        result = await orch.generate_ui_state("HomeScreen")
        self.assertIn("compile_ok", result.to_dict())


if __name__ == "__main__":
    unittest.main()
