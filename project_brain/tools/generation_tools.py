"""Phase 4 MCP generation tool facade."""

from __future__ import annotations

from typing import Any

from project_brain.brain.schema import ProjectBrain
from project_brain.generators.code_generation import GenerationOrchestrator, GenerationResult
from project_brain.llm.adapter import LLMAdapter, NullAdapter


class GenerationTools:
    """MCP-facing generation methods backed by the GenerationOrchestrator."""

    def __init__(
        self,
        brain: ProjectBrain,
        llm: LLMAdapter | None = None,
        brain_path: str = "PROJECT_BRAIN.json",
    ) -> None:
        self._orchestrator = GenerationOrchestrator(
            brain=brain,
            llm=llm or NullAdapter(),
            brain_path=brain_path,
        )

    async def generate_viewmodel(self, screen_id: str, output_path: str | None = None) -> dict[str, Any]:
        result = await self._orchestrator.generate_viewmodel(screen_id)
        return self._write_and_return(result, output_path)

    async def generate_ui_state(self, screen_id: str, output_path: str | None = None) -> dict[str, Any]:
        result = await self._orchestrator.generate_ui_state(screen_id)
        return self._write_and_return(result, output_path)

    async def generate_repository(self, repository_id: str, output_path: str | None = None) -> dict[str, Any]:
        result = await self._orchestrator.generate_repository(repository_id)
        return self._write_and_return(result, output_path)

    async def generate_datamodel(self, model_id: str, output_path: str | None = None) -> dict[str, Any]:
        result = await self._orchestrator.generate_datamodel(model_id)
        return self._write_and_return(result, output_path)

    async def generate_screen_scaffold(self, screen_id: str, output_path: str | None = None) -> dict[str, Any]:
        result = await self._orchestrator.generate_screen_scaffold(screen_id)
        return self._write_and_return(result, output_path)

    async def generate_usecase(self, usecase_name: str, output_path: str | None = None) -> dict[str, Any]:
        result = await self._orchestrator.generate_usecase(usecase_name)
        return self._write_and_return(result, output_path)

    async def generate_di_module(self, feature_name: str, output_path: str | None = None) -> dict[str, Any]:
        result = await self._orchestrator.generate_di_module(feature_name)
        return self._write_and_return(result, output_path)

    async def generate_nav_route(self, screen_id: str, output_path: str | None = None) -> dict[str, Any]:
        result = await self._orchestrator.generate_nav_route(screen_id)
        return self._write_and_return(result, output_path)

    async def generate_viewmodel_test(self, screen_id: str, output_path: str | None = None) -> dict[str, Any]:
        result = await self._orchestrator.generate_viewmodel_test(screen_id)
        return self._write_and_return(result, output_path)

    def _write_and_return(self, result: GenerationResult, output_path: str | None) -> dict[str, Any]:
        if output_path:
            result = self._orchestrator.write_result(result, output_path)
        return result.to_dict()
