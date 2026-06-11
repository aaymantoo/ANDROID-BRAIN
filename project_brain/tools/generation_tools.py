"""Phase 4 MCP generation tool facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from project_brain.brain.schema import ProjectBrain
from project_brain.generators.code_generation import GenerationOrchestrator, GenerationResult, RepositoryPair
from project_brain.llm.adapter import LLMAdapter, NullAdapter
from project_brain.tools.path_resolver import resolve_android_path, resolve_all_paths


class GenerationTools:
    """MCP-facing generation methods backed by the GenerationOrchestrator.

    Pass ``output_base`` (e.g. ``app/src/main/kotlin``) to have every
    artifact automatically placed in the correct Android directory tree.
    Pass ``output_path`` on individual calls to override for that file only.
    """

    def __init__(
        self,
        brain: ProjectBrain,
        llm: LLMAdapter | None = None,
        brain_path: str = "PROJECT_BRAIN.json",
        output_base: str | None = None,
    ) -> None:
        self._orchestrator = GenerationOrchestrator(
            brain=brain,
            llm=llm,
            brain_path=brain_path,
        )
        self._brain = brain
        self._output_base = output_base
        self._audit_cache: dict[str, Any] | None = None

    def _get_audit_block(self) -> dict[str, Any] | None:
        """Lazily run audit_brain once; return error dict if generation is blocked."""
        if self._audit_cache is None:
            from project_brain.tools.validation_tools import audit_brain_instance
            self._audit_cache = audit_brain_instance(self._brain)
        if not self._audit_cache["generation_allowed"]:
            top = self._audit_cache["critical_issues"][:3]
            return {
                "error": "Brain audit failed — run audit_brain() to see all issues.",
                "audit_score": self._audit_cache["score"],
                "critical_issues": top,
                "generation_allowed": False,
            }
        return None

    # ── path helpers ──────────────────────────────────────────────────────────

    def _resolve(self, artifact_type: str, identifier: str, override: str | None) -> str | None:
        """Return the output path: explicit override > output_base derived > None."""
        if override:
            return override
        if self._output_base:
            if artifact_type == "test":
                from project_brain.tools.path_resolver import _test_base
                base = _test_base(self._output_base)
            else:
                base = self._output_base
            return resolve_android_path(base, self._brain, artifact_type, identifier)
        return None

    def get_expected_paths(self) -> dict[str, str]:
        """Return all expected output paths for every artifact in the brain.

        Useful for previewing the file tree before generation starts.
        Requires ``output_base`` to have been set on construction.
        """
        if not self._output_base:
            return {}
        return resolve_all_paths(self._output_base, self._brain)

    # ── generation tools ──────────────────────────────────────────────────────

    async def generate_viewmodel(self, screen_id: str, output_path: str | None = None) -> dict[str, Any]:
        if block := self._get_audit_block():
            return block
        result = await self._orchestrator.generate_viewmodel(screen_id)
        return self._write_and_return(result, self._resolve("viewmodel", screen_id, output_path))

    async def generate_ui_state(self, screen_id: str, output_path: str | None = None) -> dict[str, Any]:
        if block := self._get_audit_block():
            return block
        result = await self._orchestrator.generate_ui_state(screen_id)
        return self._write_and_return(result, self._resolve("ui_state", screen_id, output_path))

    async def generate_repository(self, repository_id: str, output_path: str | None = None) -> dict[str, Any]:
        if block := self._get_audit_block():
            return block
        dest = self._resolve("repository_interface", repository_id, output_path)
        if dest:
            pair = await self._orchestrator.generate_repository_pair(repository_id)
            # Interface goes to domain/repository/, impl to data/repository/
            iface_path = self._resolve("repository_interface", repository_id, None) if not output_path else dest
            impl_path = self._resolve("repository_impl", repository_id, None)
            if impl_path:
                # Write each file to its own layer directory
                iface_result = self._orchestrator.write_result(pair.interface, iface_path)
                impl_result = self._orchestrator.write_result(pair.implementation, impl_path)
                return {
                    "repository_id": repository_id,
                    "interface": iface_result.to_dict(),
                    "implementation": impl_result.to_dict(),
                    "clean": iface_result.clean and impl_result.clean,
                }
            written = self._orchestrator.write_repository_pair(pair, Path(dest).parent)
            return written.to_dict()
        result = await self._orchestrator.generate_repository(repository_id)
        return result.to_dict()

    async def generate_datamodel(self, model_id: str, output_path: str | None = None) -> dict[str, Any]:
        if block := self._get_audit_block():
            return block
        result = await self._orchestrator.generate_datamodel(model_id)
        return self._write_and_return(result, self._resolve("datamodel", model_id, output_path))

    async def generate_screen_scaffold(self, screen_id: str, output_path: str | None = None) -> dict[str, Any]:
        if block := self._get_audit_block():
            return block
        result = await self._orchestrator.generate_screen_scaffold(screen_id)
        return self._write_and_return(result, self._resolve("scaffold", screen_id, output_path))

    async def generate_usecase(self, usecase_name: str, output_path: str | None = None) -> dict[str, Any]:
        if block := self._get_audit_block():
            return block
        result = await self._orchestrator.generate_usecase(usecase_name)
        return self._write_and_return(result, self._resolve("usecase", usecase_name, output_path))

    async def generate_di_module(self, feature_name: str, output_path: str | None = None) -> dict[str, Any]:
        if block := self._get_audit_block():
            return block
        result = await self._orchestrator.generate_di_module(feature_name)
        return self._write_and_return(result, self._resolve("di_module", feature_name, output_path))

    async def generate_nav_route(self, screen_id: str, output_path: str | None = None) -> dict[str, Any]:
        if block := self._get_audit_block():
            return block
        result = await self._orchestrator.generate_nav_route(screen_id)
        return self._write_and_return(result, self._resolve("nav_route", screen_id, output_path))

    async def generate_viewmodel_test(self, screen_id: str, output_path: str | None = None) -> dict[str, Any]:
        if block := self._get_audit_block():
            return block
        result = await self._orchestrator.generate_viewmodel_test(screen_id)
        return self._write_and_return(result, self._resolve("test", screen_id, output_path))

    def _write_and_return(self, result: GenerationResult, output_path: str | None) -> dict[str, Any]:
        if output_path:
            result = self._orchestrator.write_result(result, output_path)
        return result.to_dict()
