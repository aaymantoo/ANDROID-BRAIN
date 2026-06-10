"""Deterministic Kotlin MVVM validation engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from project_brain.brain.manager import BrainManager
from project_brain.brain.schema import ProjectBrain
from rules.mvvm_rules import MVVM_RULES, MVVMRule


Severity = Literal["CLASS_A", "CLASS_B", "CLASS_C"]
FileType = Literal["ViewModel", "Repository", "Screen", "DataModel", "Unknown"]


@dataclass(frozen=True)
class KotlinAnalysis:
    content: str
    imports: list[str]
    package_name: str | None
    classes: list[str]
    interfaces: list[str]
    functions: list[tuple[str, int]]
    composable_ranges: list[tuple[int, int]]
    file_type: FileType

    def line_for_pattern(self, pattern: str) -> int | None:
        for index, line in enumerate(self.content.splitlines(), start=1):
            if re.search(pattern, line):
                return index
        return None

    def has_import_containing(self, needle: str) -> bool:
        return any(needle in item for item in self.imports)

    def composable_has_business_logic(self) -> bool:
        markers = (
            r"\.collection\s*\(",
            r"\.document\s*\(",
            r"\.where\w+\s*\(",
            r"\.addSnapshotListener\s*\(",
            r"\.set\s*\(",
            r"\.update\s*\(",
            r"\.delete\s*\(",
            r"\.launch\s*\{",
            r"\bwithContext\s*\(",
            r"\bThread\s*\(",
        )
        for start, end in self.composable_ranges:
            block = "\n".join(self.content.splitlines()[start - 1 : end])
            if any(re.search(marker, block) for marker in markers):
                return True
        return False

    def stateflows_have_correct_visibility(self) -> bool:
        if self.file_type != "ViewModel":
            return True
        mutable_names = re.findall(r"private\s+val\s+_(\w+)\s*=\s*MutableStateFlow\b", self.content)
        exposed_names = re.findall(r"val\s+(\w+)\s*:\s*StateFlow<[^>]+>\s*=\s*_(\w+)\.asStateFlow\(\)", self.content)
        exposed_map = {private_name: public_name for public_name, private_name in exposed_names}
        public_mutable = re.search(r"(?<!private\s)val\s+\w+\s*=\s*MutableStateFlow\b", self.content)
        if public_mutable:
            return False
        stateflow_props = re.findall(r"val\s+(\w+)\s*:\s*StateFlow<", self.content)
        if stateflow_props and not mutable_names:
            return False
        return all(name in exposed_map for name in mutable_names)

    def repository_has_interface(self) -> bool:
        if self.file_type != "Repository":
            return True
        repository_classes = [name.removesuffix("Impl") for name in self.classes if "Repository" in name]
        if not repository_classes:
            return True
        return any(name in self.interfaces or f"I{name}" in self.interfaces for name in repository_classes)

    def has_direct_firestore_call(self) -> bool:
        return bool(re.search(r"\.collection\s*\(", self.content))


@dataclass(frozen=True)
class Violation:
    rule_id: str
    severity: Severity
    description: str
    fix: str
    line: int | None = None

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "description": self.description,
            "fix": self.fix,
            "line": self.line,
        }


@dataclass(frozen=True)
class ValidationReport:
    file: str
    file_type: FileType
    violations: list[Violation] = field(default_factory=list)

    @property
    def class_a_count(self) -> int:
        return count_severity(self.violations, "CLASS_A")

    @property
    def class_b_count(self) -> int:
        return count_severity(self.violations, "CLASS_B")

    @property
    def class_c_count(self) -> int:
        return count_severity(self.violations, "CLASS_C")

    @property
    def mvvm_compliant(self) -> bool:
        return self.class_a_count == 0

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "file_type": self.file_type,
            "violations": [violation.to_dict() for violation in self.violations],
            "class_a_count": self.class_a_count,
            "class_b_count": self.class_b_count,
            "class_c_count": self.class_c_count,
            "mvvm_compliant": self.mvvm_compliant,
        }


@dataclass(frozen=True)
class PhaseValidationReport:
    phase: int
    reports: list[ValidationReport]

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "files_checked": len(self.reports),
            "class_a_count": sum(report.class_a_count for report in self.reports),
            "class_b_count": sum(report.class_b_count for report in self.reports),
            "class_c_count": sum(report.class_c_count for report in self.reports),
            "mvvm_compliant": all(report.mvvm_compliant for report in self.reports),
            "reports": [report.to_dict() for report in self.reports],
        }


class KotlinAnalyzer:
    """Small structural analyzer for Kotlin files."""

    import_pattern = re.compile(r"^\s*import\s+([\w.*]+)", re.M)
    package_pattern = re.compile(r"^\s*package\s+([\w.]+)", re.M)
    class_pattern = re.compile(r"\b(?:data\s+)?class\s+(\w+)")
    interface_pattern = re.compile(r"\binterface\s+(\w+)")
    function_pattern = re.compile(r"^\s*(?:public\s+)?fun\s+(\w+)\s*\(", re.M)

    def parse_file(self, file_path: str | Path) -> KotlinAnalysis:
        return self.parse(Path(file_path).read_text(encoding="utf-8", errors="ignore"))

    def parse(self, content: str) -> KotlinAnalysis:
        classes = self.class_pattern.findall(content)
        interfaces = self.interface_pattern.findall(content)
        file_type = detect_file_type(content, classes, interfaces)
        return KotlinAnalysis(
            content=content,
            imports=self.import_pattern.findall(content),
            package_name=first_or_none(self.package_pattern.findall(content)),
            classes=classes,
            interfaces=interfaces,
            functions=[(match.group(1), line_number(content, match.start())) for match in self.function_pattern.finditer(content)],
            composable_ranges=find_composable_ranges(content),
            file_type=file_type,
        )


class MVVMValidationEngine:
    """Runs deterministic MVVM and pattern rules against Kotlin files."""

    def __init__(self, rules: list[MVVMRule] | None = None) -> None:
        self.rules = rules or MVVM_RULES
        self.analyzer = KotlinAnalyzer()

    def validate_file(self, file_path: str | Path) -> ValidationReport:
        analysis = self.analyzer.parse_file(file_path)
        return self._make_report(str(file_path), analysis)

    def validate_content(self, content: str, file_path_hint: str = "<generated>") -> ValidationReport:
        analysis = self.analyzer.parse(content)
        return self._make_report(file_path_hint, analysis)

    def _make_report(self, file_path: str, analysis) -> ValidationReport:
        violations = [
            Violation(
                rule_id=rule.id,
                severity=rule.severity,
                description=rule.description,
                fix=rule.fix,
                line=rule.line_finder(analysis),
            )
            for rule in self.get_rules_for_type(analysis.file_type)
            if not rule.check(analysis)
        ]
        return ValidationReport(file=file_path, file_type=analysis.file_type, violations=violations)

    def validate_phase(self, phase: int, brain_path: str | Path = "PROJECT_BRAIN.json") -> PhaseValidationReport:
        brain = BrainManager(brain_path).load()
        return self.validate_phase_brain(phase, brain)

    def validate_phase_brain(self, phase: int, brain: ProjectBrain) -> PhaseValidationReport:
        file_paths = phase_file_paths(brain, phase)
        reports = [self.validate_file(path) for path in file_paths if Path(path).exists()]
        return PhaseValidationReport(phase=phase, reports=reports)

    def get_rules_for_type(self, file_type: FileType) -> list[MVVMRule]:
        return [rule for rule in self.rules if file_type in rule.file_types or "Any" in rule.file_types]


def detect_file_type(content: str, classes: list[str], interfaces: list[str]) -> FileType:
    if "@Composable" in content or any(name.endswith("Screen") for name in re.findall(r"\bfun\s+(\w+Screen)\s*\(", content)):
        return "Screen"
    if any(name.endswith("ViewModel") for name in classes) or "ViewModel" in content:
        return "ViewModel"
    if any("Repository" in name for name in classes + interfaces):
        return "Repository"
    if "data class" in content:
        return "DataModel"
    return "Unknown"


def find_composable_ranges(content: str) -> list[tuple[int, int]]:
    lines = content.splitlines()
    ranges: list[tuple[int, int]] = []
    for index, line in enumerate(lines, start=1):
        if "@Composable" not in line:
            continue
        start = index
        end = min(len(lines), index + 80)
        depth = 0
        seen_body = False
        for inner_index in range(index, len(lines) + 1):
            current = lines[inner_index - 1]
            depth += current.count("{")
            if "{" in current:
                seen_body = True
            depth -= current.count("}")
            if seen_body and depth <= 0:
                end = inner_index
                break
        ranges.append((start, end))
    return ranges


def phase_file_paths(brain: ProjectBrain, phase: int) -> list[str]:
    phase_screen_ids = {screen.id for screen in brain.screens if screen.phase == phase}
    phase_item = next((item for item in brain.phases if item.number == phase), None)
    if phase_item:
        phase_screen_ids.update(phase_item.screens)
    file_paths: list[str] = []
    for screen in brain.screens:
        if screen.id not in phase_screen_ids:
            continue
        if screen.file_path:
            file_paths.append(screen.file_path)
        if screen.viewmodel:
            viewmodel = next((item for item in brain.viewmodels if item.id == screen.viewmodel), None)
            if viewmodel and viewmodel.file_path:
                file_paths.append(viewmodel.file_path)
        if screen.repository:
            repository = next((item for item in brain.repositories if item.id == screen.repository), None)
            if repository and repository.file_path:
                file_paths.append(repository.file_path)
    return sorted(set(file_paths))


def line_number(content: str, index: int) -> int:
    return content.count("\n", 0, index) + 1


def first_or_none(values: list[str]) -> str | None:
    return values[0] if values else None


def count_severity(violations: list[Violation], severity: Severity) -> int:
    return len([violation for violation in violations if violation.severity == severity])
