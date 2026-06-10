"""Phase 3 zero-LLM validation tools."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from project_brain.brain.manager import BrainManager
from project_brain.brain.schema import ProjectBrain
from project_brain.engines.rule_engine import MVVMValidationEngine


def validate_mvvm(file_path: str) -> dict[str, Any]:
    """Validate a Kotlin file for deterministic MVVM rule compliance."""

    return MVVMValidationEngine().validate_file(file_path).to_dict()


def validate_phase(phase: int, brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Validate all known files for a brain phase."""

    return MVVMValidationEngine().validate_phase(phase, brain_path).to_dict()


def validate_firestore_consistency(brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Check brain business rules against Firestore consistency declarations."""

    brain = BrainManager(brain_path).load()
    return validate_firestore_consistency_brain(brain)


def validate_firestore_consistency_brain(brain: ProjectBrain) -> dict[str, Any]:
    collection_rules = " ".join(
        rule for collection in brain.firestore_schema.collections for rule in collection.consistency_rules
    )
    violations = []
    for rule in brain.business_rules:
        if rule.required_updates and not all(update in collection_rules for update in rule.required_updates):
            violations.append(
                {
                    "rule_id": rule.id,
                    "severity": rule.missing_any or "CLASS_A",
                    "description": f"Business rule {rule.id} has required updates not reflected in Firestore consistency rules.",
                    "missing_updates": [update for update in rule.required_updates if update not in collection_rules],
                }
            )
    return {"violations": violations, "violation_count": len(violations), "consistent": not violations}


def validate_state_transitions(entity: str, file_path: str, brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Check that a file contains required updates for an entity's state transitions."""

    brain = BrainManager(brain_path).load()
    return validate_state_transitions_brain(entity, file_path, brain)


def validate_state_transitions_brain(entity: str, file_path: str, brain: ProjectBrain) -> dict[str, Any]:
    content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    machine = next((item for item in brain.state_machines if item.entity.lower() == entity.lower()), None)
    if not machine:
        return {"entity": entity, "violations": [{"severity": "CLASS_A", "description": f"State machine not found: {entity}"}]}
    violations = []
    for transition in machine.transitions:
        missing = [update for update in transition.required_firestore_updates if not update_present(update, content)]
        if missing:
            violations.append(
                {
                    "transition": {"from": transition.from_state, "to": transition.to},
                    "severity": transition.missing_any or "CLASS_A",
                    "missing_updates": missing,
                    "recommended_implementation": transition.recommended_implementation,
                }
            )
    return {"entity": machine.entity, "violations": violations, "valid": not violations}


def validate_design_tokens(file_path: str, brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Check for disallowed design-token usage from brain token rules."""

    brain = BrainManager(brain_path).load()
    return validate_design_tokens_brain(file_path, brain)


def validate_design_tokens_brain(file_path: str, brain: ProjectBrain) -> dict[str, Any]:
    content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    violations = []
    for rule in brain.design_system.token_rules:
        match = re.search(r"Use\s+([A-Za-z0-9_.]+)\s+not\s+([A-Za-z0-9_.]+)", rule, re.I)
        if match and match.group(2) in content:
            violations.append(
                {
                    "severity": "CLASS_B",
                    "description": rule,
                    "found": match.group(2),
                    "expected": match.group(1),
                }
            )
        required = re.search(r"must\s+use\s+([A-Za-z0-9_.]+)", rule, re.I)
        if required and required.group(1) not in content:
            violations.append(
                {
                    "severity": "CLASS_B",
                    "description": rule,
                    "missing": required.group(1),
                }
            )
    return {"file": file_path, "violations": violations, "valid": not violations}


def validate_naming_conventions(file_path: str, brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Check Kotlin naming conventions against brain/MVVM naming."""

    brain = BrainManager(brain_path).load()
    return validate_naming_conventions_brain(file_path, brain)


def validate_naming_conventions_brain(file_path: str, brain: ProjectBrain) -> dict[str, Any]:
    path = Path(file_path)
    content = path.read_text(encoding="utf-8", errors="ignore")
    violations = []
    class_match = re.search(r"\b(?:data\s+)?class\s+(\w+)|\binterface\s+(\w+)", content)
    class_name = next((group for group in class_match.groups() if group), None) if class_match else None
    if class_name and path.stem != class_name:
        violations.append(
            {
                "severity": "CLASS_B",
                "description": "Kotlin file name should match the primary class or interface name.",
                "expected": f"{class_name}.kt",
                "actual": path.name,
            }
        )
    if class_name and class_name.endswith("ViewModel"):
        expected_screen = class_name.replace("ViewModel", "Screen")
        if not any(screen.id == expected_screen for screen in brain.screens):
            violations.append(
                {
                    "severity": "CLASS_B",
                    "description": "ViewModel name should map to a known Screen.",
                    "expected_screen": expected_screen,
                }
            )
    return {"file": file_path, "violations": violations, "valid": not violations}


def update_present(update: str, content: str) -> bool:
    compact_update = re.sub(r"[^A-Za-z0-9_]+", "", update).lower()
    compact_content = re.sub(r"[^A-Za-z0-9_]+", "", content).lower()
    return compact_update in compact_content or all(part.lower() in compact_content for part in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", update))
