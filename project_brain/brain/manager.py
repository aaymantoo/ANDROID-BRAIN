"""Read and write PROJECT_BRAIN.json safely."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from project_brain.brain.schema import ProjectBrain, utc_now


class BrainManager:
    """Persistence layer for the single source of truth brain file."""

    def __init__(self, brain_path: str | Path = "PROJECT_BRAIN.json") -> None:
        self.brain_path = Path(brain_path)

    def exists(self) -> bool:
        return self.brain_path.exists()

    def load(self) -> ProjectBrain:
        return ProjectBrain.model_validate_json(self.brain_path.read_text(encoding="utf-8"))

    def save(self, brain: ProjectBrain) -> Path:
        self.brain_path.parent.mkdir(parents=True, exist_ok=True)
        brain.meta.last_synced = utc_now()
        payload = brain.model_dump(by_alias=True, mode="json")
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                delete=False,
                dir=str(self.brain_path.parent or Path(".")),
                suffix=".tmp",
            ) as handle:
                temp_name = handle.name
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            os.replace(temp_name, self.brain_path)
        finally:
            if temp_name and Path(temp_name).exists():
                Path(temp_name).unlink()
        return self.brain_path

