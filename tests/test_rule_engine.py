import unittest
from pathlib import Path

from project_brain.engines.rule_engine import MVVMValidationEngine


class RuleEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = MVVMValidationEngine()

    def test_bad_viewmodel_reports_class_a_violations(self) -> None:
        report = self.engine.validate_file(Path("tests/fixtures/bad_viewmodel.kt"))
        rule_ids = {violation.rule_id for violation in report.violations}

        self.assertEqual(report.file_type, "ViewModel")
        self.assertFalse(report.mvvm_compliant)
        self.assertIn("A001", rule_ids)
        self.assertIn("A002", rule_ids)
        self.assertIn("A004", rule_ids)
        self.assertIn("B006", rule_ids)

    def test_bad_screen_reports_business_logic(self) -> None:
        report = self.engine.validate_file(Path("tests/fixtures/bad_screen.kt"))
        rule_ids = {violation.rule_id for violation in report.violations}

        self.assertEqual(report.file_type, "Screen")
        self.assertIn("A003", rule_ids)
        self.assertIn("B005", rule_ids)

    def test_repository_without_interface_reports_violation(self) -> None:
        report = self.engine.validate_file(Path("tests/fixtures/repository_no_interface.kt"))
        rule_ids = {violation.rule_id for violation in report.violations}

        self.assertEqual(report.file_type, "Repository")
        self.assertIn("A005", rule_ids)


if __name__ == "__main__":
    unittest.main()

