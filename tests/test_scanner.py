from pathlib import Path
import unittest

from project_brain.generators.codebase_scanner import CodebaseScanner, KotlinFileAnalyzer


class ScannerTest(unittest.TestCase):
    def test_analyzer_finds_viewmodel(self) -> None:
        analysis = KotlinFileAnalyzer().analyze(Path("tests/fixtures/sample_viewmodel.kt"))

        self.assertIn("OrderTrackingViewModel", analysis.viewmodels)
        self.assertIn(("uiState", "OrderTrackingUiState"), analysis.stateflows)

    def test_scanner_builds_brain(self) -> None:
        brain = CodebaseScanner().scan(Path("tests/fixtures/scanner"))

        self.assertEqual(brain.meta.entry_point, "codebase")
        self.assertEqual(brain.meta.package_name, "com.example.sampleporter")
        self.assertEqual(len(brain.screens), 1)
        self.assertEqual(brain.screens[0].viewmodel, "OrderTrackingViewModel")
        self.assertEqual(len(brain.repositories), 1)
        self.assertEqual(len(brain.data_models), 1)


if __name__ == "__main__":
    unittest.main()

