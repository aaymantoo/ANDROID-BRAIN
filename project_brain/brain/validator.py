"""Schema validation helpers."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from project_brain.brain.schema import ProjectBrain


class BrainValidationError(ValueError):
    """Raised when PROJECT_BRAIN.json does not match the canonical schema."""


def validate_brain_payload(payload: str) -> ProjectBrain:
    try:
        return ProjectBrain.model_validate_json(payload)
    except ValidationError as exc:
        raise BrainValidationError(str(exc)) from exc


def validate_brain_file(path: str | Path) -> ProjectBrain:
    return validate_brain_payload(Path(path).read_text(encoding="utf-8"))

