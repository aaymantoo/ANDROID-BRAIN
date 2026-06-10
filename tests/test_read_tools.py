import unittest
from pathlib import Path

from project_brain.generators.prd_parser import PRDParser
from project_brain.tools.read_tools import ReadTools


class ReadToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.brain = PRDParser().parse_file(Path("tests/fixtures/sample_prd.md"))
        for screen in self.brain.screens:
            screen.phase = 1
        self.tools = ReadTools(self.brain)

    def test_project_context(self) -> None:
        context = self.tools.get_project_context()

        self.assertEqual(context["meta"]["project_name"], "Sample Porter")
        self.assertEqual(context["summary"]["screens"], 2)

    def test_screen_graph(self) -> None:
        graph = self.tools.get_screen_graph("OrderTrackingScreen")

        self.assertEqual(graph["screen"]["id"], "OrderTrackingScreen")
        self.assertEqual(graph["viewmodel"]["id"], "OrderTrackingViewModel")
        self.assertEqual(graph["repository"]["id"], "OrderRepository")

    def test_phase_status(self) -> None:
        self.brain.screens[0].generated = True

        status = self.tools.get_phase_status(1)

        self.assertEqual(status["completion_percent"], 50.0)
        self.assertEqual(status["screens_done"], ["HomeScreen"])

    def test_dependencies(self) -> None:
        dependencies = self.tools.get_dependencies("OrderTrackingScreen")

        self.assertEqual(dependencies["dependencies"]["repository"], "OrderRepository")
        self.assertEqual(dependencies["missing"], [])

    def test_state_machine(self) -> None:
        state_machine = self.tools.get_state_machine("Order")

        self.assertEqual(state_machine["entity"], "Order")
        self.assertIn("PENDING", state_machine["states"])


if __name__ == "__main__":
    unittest.main()
