import unittest
from pathlib import Path

from project_brain.generators.code_generation import GenerationOrchestrator
from project_brain.generators.prd_parser import PRDParser
from project_brain.llm.adapter import NullAdapter
from project_brain.tools.generation_tools import GenerationTools
from project_brain.tools.registry import create_registry


class GenerationOrchestratorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.brain = PRDParser().parse_file(Path("tests/fixtures/sample_prd.md"))
        self.orchestrator = GenerationOrchestrator(self.brain, llm=NullAdapter())

    async def test_generate_viewmodel_returns_clean_result(self) -> None:
        result = await self.orchestrator.generate_viewmodel("HomeScreen")
        self.assertTrue(result.clean, f"CLASS_A violations: {result.violations}")
        self.assertIn("@HiltViewModel", result.content)
        self.assertIn("MutableStateFlow", result.content)
        self.assertIn("asStateFlow()", result.content)

    async def test_generate_viewmodel_uses_null_adapter_stubs(self) -> None:
        result = await self.orchestrator.generate_viewmodel("HomeScreen")
        self.assertFalse(result.used_llm)
        self.assertEqual(result.template, "viewmodel.kt.j2")

    async def test_generate_ui_state_returns_sealed_class(self) -> None:
        result = await self.orchestrator.generate_ui_state("HomeScreen")
        self.assertTrue(result.clean, f"Violations: {result.violations}")
        self.assertIn("sealed class", result.content)
        self.assertIn("data object Loading", result.content)

    async def test_generate_repository_returns_both_files(self) -> None:
        result = await self.orchestrator.generate_repository("OrderRepository")
        self.assertIn("interface", result.content)
        self.assertIn("class", result.content)
        self.assertIn("FirebaseFirestore", result.content)

    async def test_generate_datamodel_is_zero_llm(self) -> None:
        result = await self.orchestrator.generate_datamodel("Order")
        self.assertFalse(result.used_llm)
        self.assertIn("@Keep", result.content)
        self.assertIn("data class Order", result.content)

    async def test_generate_screen_scaffold_no_class_a_violations(self) -> None:
        result = await self.orchestrator.generate_screen_scaffold("HomeScreen")
        self.assertTrue(result.clean, f"Violations: {result.violations}")
        self.assertIn("@Composable", result.content)
        self.assertIn("hiltViewModel()", result.content)

    async def test_generate_nav_route_for_screen_with_args(self) -> None:
        result = await self.orchestrator.generate_nav_route("OrderTrackingScreen")
        self.assertIn("object OrderTrackingRoute", result.content)
        self.assertIn("createRoute", result.content)

    async def test_generate_di_module_has_binds(self) -> None:
        result = await self.orchestrator.generate_di_module("order")
        self.assertIn("@Binds", result.content)
        self.assertIn("@Module", result.content)

    async def test_generate_viewmodel_test_scaffold(self) -> None:
        result = await self.orchestrator.generate_viewmodel_test("HomeScreen")
        self.assertIn("StandardTestDispatcher", result.content)
        self.assertIn("HomeViewModel", result.content)


class GenerationToolsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.brain = PRDParser().parse_file(Path("tests/fixtures/sample_prd.md"))
        self.tools = GenerationTools(self.brain, llm=NullAdapter())

    async def test_generate_viewmodel_returns_dict(self) -> None:
        result = await self.tools.generate_viewmodel("HomeScreen")
        self.assertIn("content", result)
        self.assertIn("clean", result)
        self.assertIn("attempts", result)
        self.assertIn("used_llm", result)
        self.assertTrue(result["clean"])

    async def test_generate_datamodel_returns_dict(self) -> None:
        result = await self.tools.generate_datamodel("Order")
        self.assertIn("content", result)
        self.assertFalse(result["used_llm"])


class RegistryPhase4Test(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.brain = PRDParser().parse_file(Path("tests/fixtures/sample_prd.md"))
        self.registry = create_registry(self.brain, llm=NullAdapter())

    def test_registry_exposes_all_tools(self) -> None:
        names = [tool.name for tool in self.registry.list_definitions()]
        # 35 original + 3 incremental enrichment tools + 1 audit_brain
        self.assertEqual(len(names), 39)

    def test_all_generation_tools_registered(self) -> None:
        names = {tool.name for tool in self.registry.list_definitions()}
        for expected in [
            "generate_viewmodel",
            "generate_ui_state",
            "generate_repository",
            "generate_datamodel",
            "generate_screen_scaffold",
            "generate_usecase",
            "generate_di_module",
            "generate_nav_route",
            "generate_viewmodel_test",
        ]:
            self.assertIn(expected, names, f"Missing tool: {expected}")

    async def test_registry_executes_generate_datamodel(self) -> None:
        result = await self.registry.execute("generate_datamodel", {"model_id": "Order"})
        self.assertIn("content", result)
        self.assertIn("@Keep", result["content"])


if __name__ == "__main__":
    unittest.main()
