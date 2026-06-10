"""High-level Phase 1 brain generation facade."""

from __future__ import annotations

from pathlib import Path

from project_brain.brain.manager import BrainManager
from project_brain.brain.schema import GenerationStatus, ProjectBrain
from project_brain.generators.codebase_scanner import CodebaseScanner
from project_brain.generators.prd_parser import PRDParser


class BrainGenerator:
    """Coordinates PRD and codebase entry points."""

    def from_prd(self, prd_path: str | Path) -> ProjectBrain:
        return PRDParser().parse_file(prd_path)

    def from_code(self, project_path: str | Path) -> ProjectBrain:
        return CodebaseScanner().scan(project_path)

    def write(self, brain: ProjectBrain, output_path: str | Path = "PROJECT_BRAIN.json") -> Path:
        self._init_generation_status(brain)
        saved = BrainManager(output_path).save(brain)
        self._write_roadmap(brain, saved)
        return saved

    @staticmethod
    def _init_generation_status(brain: ProjectBrain) -> None:
        """Ensure every screen has a GenerationStatus entry (idempotent)."""
        existing_ids = {s.screen_id for s in brain.generation_status}
        for screen in brain.screens:
            if screen.id not in existing_ids:
                brain.generation_status.append(GenerationStatus(screen_id=screen.id))

    @staticmethod
    def _write_roadmap(brain: ProjectBrain, brain_path: Path) -> None:
        from project_brain.generators.roadmap_generator import RoadmapGenerator
        roadmap_path = brain_path.parent / "ROADMAP.md"
        RoadmapGenerator().write(brain, roadmap_path)

