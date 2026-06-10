"""Deterministic PRD completeness scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScoreDimension:
    name: str
    points: int
    earned: int
    guidance: str


@dataclass(frozen=True)
class CompletenessScore:
    total: int
    dimensions: list[ScoreDimension]

    @property
    def missing(self) -> list[ScoreDimension]:
        return [dimension for dimension in self.dimensions if dimension.earned < dimension.points]

    @property
    def can_proceed(self) -> bool:
        return self.total >= 80


class PRDCompletenessScorer:
    """Scores the required PRD sections from the Phase 1 specification."""

    dimensions = (
        ("User roles defined", 10, "Add a User Roles section with at least one role."),
        ("All screens listed", 15, "Add Features & Screens with every Screen name."),
        ("State machines defined", 20, "Add states and explicit transitions for each stateful entity."),
        ("Firestore schema present", 15, "Add Firestore collections, fields, and consistency rules."),
        ("Business rules explicit", 20, "Add explicit when/then rules and required updates."),
        ("Phase breakdown present", 10, "Add a Phase Breakdown section."),
        ("Data models defined", 10, "Add Data Models with fields and types."),
    )

    def score_file(self, path: str | Path) -> CompletenessScore:
        return self.score_text(Path(path).read_text(encoding="utf-8"))

    def score_text(self, text: str) -> CompletenessScore:
        checks = (
            self._has_user_roles,
            self._has_screens,
            self._has_state_machines,
            self._has_firestore_schema,
            self._has_business_rules,
            self._has_phase_breakdown,
            self._has_data_models,
        )
        scored: list[ScoreDimension] = []
        for (name, points, guidance), check in zip(self.dimensions, checks, strict=True):
            earned = points if check(text) else 0
            scored.append(ScoreDimension(name=name, points=points, earned=earned, guidance=guidance))
        return CompletenessScore(total=sum(item.earned for item in scored), dimensions=scored)

    def _has_user_roles(self, text: str) -> bool:
        section = section_text(text, "user roles")
        return bool(section and (re.search(r"\|\s*id\s*\|", section, re.I) or re.search(r"\b(role|customer|admin|user|porter)\b", section, re.I)))

    def _has_screens(self, text: str) -> bool:
        section = section_text(text, "features") or section_text(text, "screens")
        return bool(section and re.search(r"\b[A-Z]\w*Screen\b", section))

    def _has_state_machines(self, text: str) -> bool:
        section = section_text(text, "state machines")
        return bool(section and (re.search(r"\b[A-Z_]{3,}\b", section) and re.search(r"(->| to |transition)", section, re.I)))

    def _has_firestore_schema(self, text: str) -> bool:
        section = section_text(text, "firestore")
        return bool(section and re.search(r"/[A-Za-z][\w-]*(/\{[^}]+\})?", section))

    def _has_business_rules(self, text: str) -> bool:
        section = section_text(text, "business rules")
        return bool(section and re.search(r"\b(when|must|required|should|BR\d+)\b", section, re.I))

    def _has_phase_breakdown(self, text: str) -> bool:
        section = section_text(text, "phase")
        return bool(section and re.search(r"\bphase\s+\d+\b", section, re.I))

    def _has_data_models(self, text: str) -> bool:
        section = section_text(text, "data models")
        return bool(section and (re.search(r"^###\s+\w+", section, re.M) or re.search(r"\|\s*name\s*\|\s*type\s*\|", section, re.I)))


def section_text(text: str, heading_fragment: str) -> str:
    pattern = re.compile(r"^(#{2,4})\s+.*" + re.escape(heading_fragment) + r".*$", re.I | re.M)
    match = pattern.search(text)
    if not match:
        return ""
    level = len(match.group(1))
    next_heading = None
    for candidate in re.finditer(r"^(#{1,4})\s+", text[match.end() :], re.M):
        if len(candidate.group(1)) <= level:
            next_heading = candidate
            break
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end() : end]
