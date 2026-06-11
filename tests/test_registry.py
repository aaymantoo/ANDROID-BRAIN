import unittest
from pathlib import Path

from project_brain.generators.prd_parser import PRDParser
from project_brain.tools.registry import create_registry


class RegistryTest(unittest.IsolatedAsyncioTestCase):
    async def test_registry_exposes_all_tools(self) -> None:
        brain = PRDParser().parse_file(Path("tests/fixtures/sample_prd.md"))
        registry = create_registry(brain)

        names = [tool.name for tool in registry.list_definitions()]

        # 35 original + 3 incremental enrichment tools + 1 audit_brain
        self.assertEqual(len(names), 39)
        self.assertIn("get_project_context", names)
        self.assertIn("get_navigation_graph", names)
        self.assertIn("validate_mvvm", names)
        self.assertIn("validate_naming_conventions", names)
        self.assertIn("generate_viewmodel", names)
        self.assertIn("generate_datamodel", names)

    async def test_registry_executes_tool(self) -> None:
        brain = PRDParser().parse_file(Path("tests/fixtures/sample_prd.md"))
        registry = create_registry(brain)

        result = await registry.execute("get_screen_graph", {"screen_id": "HomeScreen"})

        self.assertEqual(result["screen"]["id"], "HomeScreen")


if __name__ == "__main__":
    unittest.main()
