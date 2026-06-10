import unittest
from pathlib import Path

from project_brain.brain.schema import (
    BusinessRule,
    DesignSystem,
    FirestoreCollection,
    FirestoreSchema,
    Meta,
    Phase,
    ProjectBrain,
    Repository,
    Screen,
    StateMachine,
    StateTransition,
    ViewModel,
)
from project_brain.tools.validation_tools import (
    validate_design_tokens_brain,
    validate_firestore_consistency_brain,
    validate_naming_conventions_brain,
    validate_state_transitions_brain,
)


class ValidationToolsTest(unittest.TestCase):
    def test_firestore_consistency_reports_missing_update(self) -> None:
        brain = ProjectBrain(
            meta=Meta(project_name="Test", entry_point="prd"),
            firestore_schema=FirestoreSchema(
                collections=[FirestoreCollection(path="/orders/{id}", consistency_rules=["order.status = COMPLETED"])]
            ),
            business_rules=[
                BusinessRule(
                    id="BR001",
                    description="Completion updates porter.",
                    required_updates=["porter.isAvailable = true"],
                    missing_any="CLASS_A",
                )
            ],
        )

        result = validate_firestore_consistency_brain(brain)

        self.assertFalse(result["consistent"])
        self.assertEqual(result["violations"][0]["missing_updates"], ["porter.isAvailable = true"])

    def test_state_transition_reports_missing_required_update(self) -> None:
        brain = ProjectBrain(
            meta=Meta(project_name="Test", entry_point="prd"),
            state_machines=[
                StateMachine(
                    entity="Order",
                    states=["IN_PROGRESS", "COMPLETED"],
                    transitions=[
                        StateTransition(
                            **{
                                "from": "IN_PROGRESS",
                                "to": "COMPLETED",
                                "required_firestore_updates": [
                                    "order.status = COMPLETED",
                                    "porter.isAvailable = true",
                                    "porter.activeRideId = null",
                                ],
                                "missing_any": "CLASS_A",
                            }
                        )
                    ],
                )
            ],
        )

        result = validate_state_transitions_brain("Order", "tests/fixtures/OrderCompletionHandler.kt", brain)

        self.assertFalse(result["valid"])
        self.assertEqual(result["violations"][0]["missing_updates"], ["porter.activeRideId = null"])

    def test_design_tokens_reports_disallowed_token(self) -> None:
        brain = ProjectBrain(
            meta=Meta(project_name="Test", entry_point="prd"),
            design_system=DesignSystem(token_rules=["Use colors.statusCompleted not colors.success"]),
        )

        result = validate_design_tokens_brain("tests/fixtures/TokenScreen.kt", brain)

        self.assertFalse(result["valid"])
        self.assertEqual(result["violations"][0]["found"], "colors.success")

    def test_naming_conventions_reports_filename_mismatch(self) -> None:
        brain = ProjectBrain(meta=Meta(project_name="Test", entry_point="prd"))

        result = validate_naming_conventions_brain("tests/fixtures/WrongName.kt", brain)

        self.assertFalse(result["valid"])
        self.assertEqual(result["violations"][0]["expected"], "ExpectedName.kt")

    def test_phase_validation_uses_brain_file_paths(self) -> None:
        brain = ProjectBrain(
            meta=Meta(project_name="Test", entry_point="prd"),
            screens=[
                Screen(
                    id="BadScreen",
                    phase=1,
                    viewmodel="BadViewModel",
                    repository="PaymentRepository",
                    file_path="tests/fixtures/bad_screen.kt",
                )
            ],
            viewmodels=[ViewModel(id="BadViewModel", file_path="tests/fixtures/bad_viewmodel.kt")],
            repositories=[Repository(id="PaymentRepository", file_path="tests/fixtures/repository_no_interface.kt")],
            phases=[Phase(number=1, name="Bad Phase", screens=["BadScreen"])],
        )

        from project_brain.engines.rule_engine import MVVMValidationEngine

        result = MVVMValidationEngine().validate_phase_brain(1, brain).to_dict()

        self.assertEqual(result["files_checked"], 3)
        self.assertGreaterEqual(result["class_a_count"], 3)


if __name__ == "__main__":
    unittest.main()
