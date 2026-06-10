"""Heuristic PRD parser for Phase 1 brain generation."""

from __future__ import annotations

import re
from pathlib import Path

from project_brain.brain.schema import (
    BusinessRule,
    DataField,
    DataModel,
    FirestoreCollection,
    FirestoreSchema,
    KnownViolation,
    Meta,
    NavigationGraph,
    NavigationRoute,
    Phase,
    ProjectBrain,
    Repository,
    Screen,
    StateMachine,
    StateTransition,
    UserRole,
    ViewModel,
)
from project_brain.generators.prd_scorer import CompletenessScore, PRDCompletenessScorer, section_text


class IncompletePRDError(ValueError):
    def __init__(self, score: CompletenessScore) -> None:
        self.score = score
        missing = ", ".join(item.name for item in score.missing)
        super().__init__(f"PRD score {score.total}/100 is below 80. Missing: {missing}")


class PRDParser:
    """Parses the official PRD template into PROJECT_BRAIN.json structure."""

    def __init__(self, minimum_score: int = 80) -> None:
        self.minimum_score = minimum_score
        self.scorer = PRDCompletenessScorer()

    def parse_file(self, path: str | Path) -> ProjectBrain:
        prd_path = Path(path)
        text = prd_path.read_text(encoding="utf-8")
        score = self.scorer.score_text(text)
        if score.total < self.minimum_score:
            raise IncompletePRDError(score)

        project_name = extract_project_name(text) or prd_path.stem
        package_name = first_match(text, r"\b([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,})\b")
        brain = ProjectBrain(
            meta=Meta(
                project_name=project_name,
                entry_point="prd",
                package_name=package_name,
                min_sdk=extract_int(text, r"min(?:imum)?\s*sdk\s*:?\s*(\d+)") or 26,
                target_sdk=extract_int(text, r"target\s*sdk\s*:?\s*(\d+)") or 35,
            ),
            user_roles=parse_user_roles(text),
            data_models=parse_data_models(text),
            state_machines=parse_state_machines(text),
            screens=parse_screens(text),
            viewmodels=parse_viewmodels(text),
            repositories=parse_repositories(text),
            navigation_graph=parse_navigation(text),
            firestore_schema=parse_firestore(text),
            phases=parse_phases(text),
            business_rules=parse_business_rules(text),
        )
        brain.known_violations.extend(score_review_violations(score))
        link_screen_relationships(brain)
        return brain


def extract_project_name(text: str) -> str | None:
    patterns = [
        r"^#\s+PRD:\s*(.+)$",
        r"^#\s+(.+)$",
        r"project\s+name\s*:?\s*(.+)$",
    ]
    for pattern in patterns:
        value = first_match(text, pattern, re.I | re.M)
        if value:
            return cleanup(value)
    return None


def parse_user_roles(text: str) -> list[UserRole]:
    section = section_text(text, "user roles")
    roles: list[UserRole] = []
    for row in markdown_rows(section):
        if len(row) >= 2 and row[0].lower() not in {"id", "---"}:
            roles.append(
                UserRole(
                    id=slug(row[0]),
                    name=cleanup(row[1]),
                    description=cleanup(row[2]) if len(row) > 2 else None,
                    app_module=slug(row[3]) if len(row) > 3 and row[3] else None,
                )
            )
    if roles:
        return unique_by_id(roles)

    for match in re.finditer(r"[-*]\s*(?:Role:\s*)?([A-Z][A-Za-z ]+)", section):
        name = cleanup(match.group(1))
        roles.append(UserRole(id=slug(name), name=name))
    return unique_by_id(roles)


def parse_data_models(text: str) -> list[DataModel]:
    section = section_text(text, "data models")
    models: list[DataModel] = []
    for name, block in subheading_blocks(section):
        fields: list[DataField] = []
        for row in markdown_rows(block):
            if len(row) >= 2 and row[0].lower() not in {"name", "---"}:
                fields.append(DataField(name=cleanup(row[0]), type=cleanup(row[1]), nullable=parse_bool(row[2]) if len(row) > 2 else False))
        firestore_collection = first_match(block, r"(/[A-Za-z][\w-]*(?:/\{[^}]+\})?)")
        models.append(DataModel(id=cleanup(name), fields=fields, firestore_collection=firestore_collection))
    return unique_by_id(models)


def parse_state_machines(text: str) -> list[StateMachine]:
    section = section_text(text, "state machines")
    machines: list[StateMachine] = []
    for heading, block in subheading_blocks(section):
        entity = cleanup(re.sub(r"\s+States?$", "", heading, flags=re.I))
        states_line = first_match(block, r"states?\s*:?\s*([A-Z0-9_,\s]+)", re.I)
        states = split_csv(states_line) if states_line else sorted(set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", block)))
        transitions: list[StateTransition] = []
        for source, target in re.findall(r"\b([A-Z][A-Z0-9_]{2,})\s*(?:->|to)\s*([A-Z][A-Z0-9_]{2,})\b", block):
            transitions.append(StateTransition(**{"from": source, "to": target}))
        machines.append(StateMachine(entity=entity, states=states, transitions=transitions))
    return unique_by_entity(machines)


def parse_screens(text: str) -> list[Screen]:
    section = section_text(text, "features") or section_text(text, "screens")
    screens: list[Screen] = []
    for screen_id in sorted(set(re.findall(r"\b[A-Z]\w*Screen\b", section))):
        idx = section.find(screen_id)
        local = section[idx : idx + 500] if idx >= 0 else ""
        screens.append(
            Screen(
                id=screen_id,
                route=first_match(local, r"route\s*:?\s*`?([A-Za-z0-9_/{},.-]+)`?", re.I) or snake(screen_id.replace("Screen", "")),
                viewmodel=first_match(local, r"\b([A-Z]\w*ViewModel)\b"),
                repository=first_match(local, r"\b([A-Z]\w*Repository)\b"),
                ui_states=split_csv(first_match(local, r"UI states?\s*:?\s*([A-Za-z0-9_,\s]+)", re.I)),
            )
        )
    return unique_by_id(screens)


def parse_viewmodels(text: str) -> list[ViewModel]:
    names = sorted(set(re.findall(r"\b[A-Z]\w*ViewModel\b", text)))
    return [ViewModel(id=name, screen=name.replace("ViewModel", "Screen")) for name in names]


def parse_repositories(text: str) -> list[Repository]:
    names = sorted(set(re.findall(r"\b[A-Z]\w*Repository\b", text)))
    return [Repository(id=name, interface=f"I{name}", implementation=f"{name}Impl") for name in names]


def parse_navigation(text: str) -> NavigationGraph:
    section = section_text(text, "navigation")
    routes: list[NavigationRoute] = []
    for source, target in re.findall(r"\b([A-Z]\w*Screen)\s*->\s*([A-Z]\w*Screen)\b", section):
        route = find_route(routes, source)
        route.next.append(target)
        if not route.screen:
            route.screen = source
    return NavigationGraph(start_destination=snake(routes[0].id.replace("Screen", "")) if routes else None, routes=routes)


def parse_firestore(text: str) -> FirestoreSchema:
    section = section_text(text, "firestore")
    collections: list[FirestoreCollection] = []
    for path, block in collection_blocks(section):
        fields = split_csv(first_match(block, r"fields?\s*:?\s*([A-Za-z0-9_,\s]+)", re.I))
        rules = [cleanup(match.group(1)) for match in re.finditer(r"consistency rule\s*:?\s*(.+)", block, re.I)]
        collections.append(FirestoreCollection(path=path, fields=fields, consistency_rules=rules))
    return FirestoreSchema(collections=unique_by_path(collections))


def parse_phases(text: str) -> list[Phase]:
    section = section_text(text, "phase")
    phases: list[Phase] = []
    for number, name, block in phase_blocks(section):
        phases.append(
            Phase(
                number=number,
                name=name,
                screens=sorted(set(re.findall(r"\b[A-Z]\w*Screen\b", block))),
                completion_criteria=[cleanup(item) for item in re.findall(r"completion criteria\s*:?\s*(.+)", block, re.I)],
            )
        )
    return phases


def parse_business_rules(text: str) -> list[BusinessRule]:
    section = section_text(text, "business rules")
    rules: list[BusinessRule] = []
    for index, line in enumerate(re.findall(r"^\s*[-*]\s*(.+)$", section, re.M), start=1):
        rule_id = first_match(line, r"\b(BR\d+)\b", re.I) or f"BR{index:03d}"
        description = cleanup(re.sub(r"^BR\d+\s*:?\s*", "", line, flags=re.I))
        trigger = first_match(line, r"\bwhen\s+(.+?),", re.I)
        rules.append(BusinessRule(id=rule_id.upper(), description=description, trigger=trigger, missing_any="CLASS_A"))
    return unique_by_rule_id(rules)


def link_screen_relationships(brain: ProjectBrain) -> None:
    viewmodel_ids = {viewmodel.id for viewmodel in brain.viewmodels}
    repository_ids = {repository.id for repository in brain.repositories}
    for screen in brain.screens:
        expected_vm = screen.id.replace("Screen", "ViewModel")
        if not screen.viewmodel and expected_vm in viewmodel_ids:
            screen.viewmodel = expected_vm
        expected_repo = screen.id.replace("Screen", "Repository")
        if not screen.repository and expected_repo in repository_ids:
            screen.repository = expected_repo


def score_review_violations(score: CompletenessScore) -> list[KnownViolation]:
    violations: list[KnownViolation] = []
    for item in score.missing:
        violations.append(
            KnownViolation(
                id=f"PRD_{slug(item.name).upper()}",
                severity="NEEDS_REVIEW",
                message=item.guidance,
                location="PRD",
                confidence=item.earned / item.points if item.points else 0.0,
            )
        )
    return violations


def markdown_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cleanup(cell) for cell in stripped.strip("|").split("|")]
        if all(set(cell) <= {"-"} for cell in cells if cell):
            continue
        rows.append(cells)
    return rows


def subheading_blocks(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^###\s+(.+)$", text, re.M))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((cleanup(match.group(1)), text[match.end() : end]))
    return blocks


def collection_blocks(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^###\s+Collection:\s*(/[^\s]+).*$", text, re.I | re.M))
    if not matches:
        return [(match.group(1), local_context(text, match.group(1))) for match in re.finditer(r"(/[A-Za-z][\w-]*(?:/\{[^}]+\})?)", text)]
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((cleanup(match.group(1)), text[match.end() : end]))
    return blocks


def phase_blocks(text: str) -> list[tuple[int, str, str]]:
    matches = list(re.finditer(r"^###\s+Phase\s+(\d+)\s*:?\s*(.+)$", text, re.I | re.M))
    blocks: list[tuple[int, str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((int(match.group(1)), cleanup(match.group(2)), text[match.end() : end]))
    return blocks


def find_route(routes: list[NavigationRoute], screen: str) -> NavigationRoute:
    route_id = snake(screen.replace("Screen", ""))
    for route in routes:
        if route.id == route_id:
            return route
    route = NavigationRoute(id=route_id, screen=screen)
    routes.append(route)
    return route


def local_context(text: str, marker: str, radius: int = 500) -> str:
    index = text.find(marker)
    if index < 0:
        return ""
    return text[max(0, index - radius) : min(len(text), index + radius)]


def first_match(text: str, pattern: str, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags)
    return cleanup(match.group(1)) if match else None


def extract_int(text: str, pattern: str) -> int | None:
    value = first_match(text, pattern, re.I)
    return int(value) if value else None


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [cleanup(item) for item in re.split(r"[,;]", value) if cleanup(item)]


def parse_bool(value: str) -> bool:
    return cleanup(value).lower() in {"true", "yes", "nullable", "1"}


def cleanup(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip("`")).strip()


def slug(value: str) -> str:
    text = cleanup(value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "item"


def snake(value: str) -> str:
    text = re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()
    return slug(text)


def unique_by_id(items: list) -> list:
    seen: set[str] = set()
    result = []
    for item in items:
        if item.id not in seen:
            result.append(item)
            seen.add(item.id)
    return result


def unique_by_entity(items: list[StateMachine]) -> list[StateMachine]:
    seen: set[str] = set()
    result: list[StateMachine] = []
    for item in items:
        if item.entity not in seen:
            result.append(item)
            seen.add(item.entity)
    return result


def unique_by_path(items: list[FirestoreCollection]) -> list[FirestoreCollection]:
    seen: set[str] = set()
    result: list[FirestoreCollection] = []
    for item in items:
        if item.path not in seen:
            result.append(item)
            seen.add(item.path)
    return result


def unique_by_rule_id(items: list[BusinessRule]) -> list[BusinessRule]:
    seen: set[str] = set()
    result: list[BusinessRule] = []
    for item in items:
        if item.id not in seen:
            result.append(item)
            seen.add(item.id)
    return result

