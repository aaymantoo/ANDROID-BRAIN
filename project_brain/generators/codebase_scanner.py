"""Zero-LLM Kotlin codebase scanner."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from project_brain.brain.schema import (
    DataField,
    DataModel,
    FirestoreCollection,
    FirestoreSchema,
    KnownViolation,
    Meta,
    ProjectBrain,
    Repository,
    Screen,
    ViewModel,
)


@dataclass(frozen=True)
class FileAnalysis:
    path: Path
    package_name: str | None = None
    viewmodels: list[str] = field(default_factory=list)
    screens: list[str] = field(default_factory=list)
    stateflows: list[tuple[str, str]] = field(default_factory=list)
    dependencies: list[tuple[str, str]] = field(default_factory=list)
    repositories: list[str] = field(default_factory=list)
    repository_interfaces: list[str] = field(default_factory=list)
    data_models: list[DataModel] = field(default_factory=list)
    firestore_calls: list[str] = field(default_factory=list)
    confidence: float = 1.0


class KotlinFileAnalyzer:
    """Regex and structural heuristic analyzer for Kotlin source files."""

    hilt_viewmodel_pattern = re.compile(r"@HiltViewModel\s*(?:\n|.){0,200}?class\s+(\w+ViewModel)", re.M)
    viewmodel_pattern = re.compile(r"class\s+(\w+ViewModel)\s*(?:@Inject\s+constructor|\()", re.M)
    stateflow_pattern = re.compile(r"val\s+(\w+)\s*:\s*StateFlow<([^>]+)>")
    composable_pattern = re.compile(r"@Composable\s+fun\s+(\w+Screen)\s*\(")
    inject_pattern = re.compile(r"private\s+val\s+(\w+)\s*:\s*(\w+(?:Repository|UseCase|StateHolder))")
    firestore_pattern = re.compile(r"\.collection\(\s*\"([^\"]+)\"\s*\)")
    repository_class_pattern = re.compile(r"class\s+(\w+Repository(?:Impl)?)\b")
    repository_interface_pattern = re.compile(r"interface\s+(\w+Repository)\b")
    package_pattern = re.compile(r"^\s*package\s+([\w.]+)", re.M)
    data_class_pattern = re.compile(r"data\s+class\s+(\w+)\s*\((.*?)\)", re.S)
    constructor_field_pattern = re.compile(r"(?:val|var)\s+(\w+)\s*:\s*([\w?.<>]+)")

    def analyze(self, path: str | Path) -> FileAnalysis:
        file_path = Path(path)
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        viewmodels = sorted(set(self.hilt_viewmodel_pattern.findall(content) + self.viewmodel_pattern.findall(content)))
        data_models = [
            DataModel(
                id=name,
                fields=[
                    DataField(name=field_name, type=field_type.rstrip("?"), nullable=field_type.endswith("?"))
                    for field_name, field_type in self.constructor_field_pattern.findall(body)
                ],
            )
            for name, body in self.data_class_pattern.findall(content)
        ]
        return FileAnalysis(
            path=file_path,
            package_name=first_or_none(self.package_pattern.findall(content)),
            viewmodels=viewmodels,
            screens=sorted(set(self.composable_pattern.findall(content))),
            stateflows=self.stateflow_pattern.findall(content),
            dependencies=self.inject_pattern.findall(content),
            repositories=sorted(set(self.repository_class_pattern.findall(content))),
            repository_interfaces=sorted(set(self.repository_interface_pattern.findall(content))),
            data_models=data_models,
            firestore_calls=sorted(set(self.firestore_pattern.findall(content))),
            confidence=self.calculate_confidence(content),
        )

    def calculate_confidence(self, content: str) -> float:
        score = 1.0
        if "@Composable" not in content and "ViewModel" not in content and "Repository" not in content and "data class" not in content:
            score = 0.3
        if content.count("class ") > 3:
            score *= 0.7
        if "TODO(" in content:
            score *= 0.9
        return round(score, 2)


class CodebaseScanner:
    """Builds a PROJECT_BRAIN.json model from Kotlin source files."""

    def __init__(self, analyzer: KotlinFileAnalyzer | None = None) -> None:
        self.analyzer = analyzer or KotlinFileAnalyzer()

    def scan(self, project_path: str | Path) -> ProjectBrain:
        root = Path(project_path)
        files = sorted(root.rglob("*.kt")) if root.exists() else []
        analyses = [self.analyzer.analyze(path) for path in files]
        package_name = first_or_none([analysis.package_name for analysis in analyses if analysis.package_name])

        viewmodels = build_viewmodels(analyses)
        repositories = build_repositories(analyses)
        data_models = unique_models([model for analysis in analyses for model in analysis.data_models])
        screens = build_screens(analyses, {viewmodel.id for viewmodel in viewmodels})
        collections = [
            FirestoreCollection(path=f"/{name}/{{id}}")
            for name in sorted({call for analysis in analyses for call in analysis.firestore_calls})
        ]
        violations = build_scan_violations(analyses, screens)

        return ProjectBrain(
            meta=Meta(
                project_name=root.name or "AndroidProject",
                entry_point="codebase",
                package_name=package_name,
            ),
            screens=screens,
            viewmodels=viewmodels,
            repositories=repositories,
            data_models=data_models,
            firestore_schema=FirestoreSchema(collections=collections),
            known_violations=violations,
        )


def build_screens(analyses: list[FileAnalysis], viewmodel_ids: set[str]) -> list[Screen]:
    screens: list[Screen] = []
    for analysis in analyses:
        for screen_id in analysis.screens:
            expected_vm = screen_id.replace("Screen", "ViewModel")
            injected_vm = first_or_none([dep_type for _, dep_type in analysis.dependencies if dep_type.endswith("ViewModel")])
            viewmodel = expected_vm if expected_vm in viewmodel_ids else injected_vm
            screens.append(
                Screen(
                    id=screen_id,
                    route=snake(screen_id.replace("Screen", "")),
                    viewmodel=viewmodel,
                    stateflows=[name for name, _ in analysis.stateflows],
                    firestore_listeners=[f"/{call}/{{id}}" for call in analysis.firestore_calls],
                    file_path=str(analysis.path),
                )
            )
    return unique_screens(screens)


def build_viewmodels(analyses: list[FileAnalysis]) -> list[ViewModel]:
    viewmodels: list[ViewModel] = []
    for analysis in analyses:
        for viewmodel_id in analysis.viewmodels:
            dependencies = [dep_type for _, dep_type in analysis.dependencies]
            repository = first_or_none([dep for dep in dependencies if dep.endswith("Repository")])
            viewmodels.append(
                ViewModel(
                    id=viewmodel_id,
                    screen=viewmodel_id.replace("ViewModel", "Screen"),
                    repository=repository,
                    use_cases=[dep for dep in dependencies if dep.endswith("UseCase")],
                    inject_dependencies=dependencies,
                    file_path=str(analysis.path),
                )
            )
    return unique_viewmodels(viewmodels)


def build_repositories(analyses: list[FileAnalysis]) -> list[Repository]:
    repo_names = sorted({name.removesuffix("Impl") for analysis in analyses for name in analysis.repositories + analysis.repository_interfaces})
    interfaces = {name for analysis in analyses for name in analysis.repository_interfaces}
    classes = {name for analysis in analyses for name in analysis.repositories}
    return [
        Repository(
            id=name,
            interface=name if name in interfaces else f"I{name}",
            implementation=f"{name}Impl" if f"{name}Impl" in classes else name if name in classes else None,
            data_sources=["FirebaseFirestore"] if any(analysis.firestore_calls for analysis in analyses) else [],
        )
        for name in repo_names
    ]


def build_scan_violations(analyses: list[FileAnalysis], screens: list[Screen]) -> list[KnownViolation]:
    violations: list[KnownViolation] = []
    for screen in screens:
        if not screen.viewmodel:
            violations.append(
                KnownViolation(
                    id=f"SCREEN_{screen.id}_NO_VIEWMODEL",
                    severity="CLASS_A",
                    message=f"{screen.id} has no mapped ViewModel.",
                    location=screen.file_path,
                    confidence=0.0,
                )
            )
    for analysis in analyses:
        if analysis.confidence < 0.85:
            violations.append(
                KnownViolation(
                    id=f"LOW_CONFIDENCE_{analysis.path.stem}",
                    severity="NEEDS_REVIEW",
                    message=f"Scanner confidence below 85 percent for {analysis.path}.",
                    location=str(analysis.path),
                    confidence=analysis.confidence,
                )
            )
    return violations


def unique_models(models: list[DataModel]) -> list[DataModel]:
    seen: set[str] = set()
    result: list[DataModel] = []
    for model in models:
        if model.id not in seen:
            result.append(model)
            seen.add(model.id)
    return result


def unique_screens(screens: list[Screen]) -> list[Screen]:
    seen: set[str] = set()
    result: list[Screen] = []
    for screen in screens:
        if screen.id not in seen:
            result.append(screen)
            seen.add(screen.id)
    return result


def unique_viewmodels(viewmodels: list[ViewModel]) -> list[ViewModel]:
    seen: set[str] = set()
    result: list[ViewModel] = []
    for viewmodel in viewmodels:
        if viewmodel.id not in seen:
            result.append(viewmodel)
            seen.add(viewmodel.id)
    return result


def first_or_none(values: list[str | None]) -> str | None:
    for value in values:
        if value:
            return value
    return None


def snake(value: str) -> str:
    text = re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "route"

