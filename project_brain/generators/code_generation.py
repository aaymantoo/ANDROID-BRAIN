"""Phase 4 code generation orchestrator: template + LLM fill + self-healing validation."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from project_brain.brain.manager import BrainManager
from project_brain.brain.schema import GenerationHistoryEntry, ProjectBrain, utc_now
from project_brain.engines.rule_engine import MVVMValidationEngine, Violation
from project_brain.engines.template_engine import TemplateEngine, TemplateEngineV2
from project_brain.llm.adapter import FillFunctionsSpec, FunctionSpec, LLMAdapter, NullAdapter


_MAX_ATTEMPTS = 3


@dataclass
class GenerationResult:
    target_id: str
    template: str
    content: str
    attempts: int
    clean: bool
    violations: list[dict] = field(default_factory=list)
    used_llm: bool = False
    output_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "template": self.template,
            "content": self.content,
            "attempts": self.attempts,
            "clean": self.clean,
            "violations": self.violations,
            "used_llm": self.used_llm,
            "output_path": self.output_path,
        }


class GenerationOrchestrator:
    """Coordinates template rendering, LLM function fill, and self-healing validation."""

    def __init__(
        self,
        brain: ProjectBrain,
        llm: LLMAdapter | None = None,
        engine: TemplateEngine | None = None,
        validator: MVVMValidationEngine | None = None,
        brain_path: str | Path = "PROJECT_BRAIN.json",
    ) -> None:
        self.brain = brain
        self.brain_path = Path(brain_path)
        self.llm: LLMAdapter = llm or NullAdapter()
        self.engine = engine or self._select_engine(brain)
        self.validator = validator or MVVMValidationEngine()

    @staticmethod
    def _select_engine(brain: ProjectBrain) -> TemplateEngine:
        """Use v2 templates when the brain has enriched viewmodel data (Phase 0B output)."""
        has_enriched = any(
            vm.ui_state_type == "data_class" or vm.state_fields or vm.events
            for vm in brain.viewmodels
        )
        return TemplateEngineV2() if has_enriched else TemplateEngine()

    # ── Public generation methods ────────────────────────────────────

    async def generate_viewmodel(self, screen_id: str) -> GenerationResult:
        ctx = self.engine.viewmodel_context(self.brain, screen_id)
        return await self._generate_with_llm("viewmodel.kt.j2", ctx, screen_id)

    async def generate_ui_state(self, screen_id: str) -> GenerationResult:
        ctx = self.engine.uistate_context(self.brain, screen_id)
        return await self._generate_static("uistate.kt.j2", ctx, screen_id)

    async def generate_repository(self, repository_id: str) -> GenerationResult:
        ctx_iface = self.engine.repository_interface_context(self.brain, repository_id)
        ctx_impl = self.engine.repository_impl_context(self.brain, repository_id)
        iface_result = await self._generate_static("repository_interface.kt.j2", ctx_iface, f"{repository_id}_interface")
        impl_result = await self._generate_with_llm("repository_impl.kt.j2", ctx_impl, repository_id)
        combined = iface_result.content + "\n\n" + impl_result.content
        return GenerationResult(
            target_id=repository_id,
            template="repository_interface.kt.j2 + repository_impl.kt.j2",
            content=combined,
            attempts=max(iface_result.attempts, impl_result.attempts),
            clean=iface_result.clean and impl_result.clean,
            violations=iface_result.violations + impl_result.violations,
            used_llm=impl_result.used_llm,
        )

    async def generate_datamodel(self, model_id: str) -> GenerationResult:
        ctx = self.engine.datamodel_context(self.brain, model_id)
        return await self._generate_static("datamodel.kt.j2", ctx, model_id)

    async def generate_screen_scaffold(self, screen_id: str) -> GenerationResult:
        ctx = self.engine.screen_scaffold_context(self.brain, screen_id)
        return await self._generate_static("screen_scaffold.kt.j2", ctx, screen_id)

    async def generate_usecase(self, usecase_name: str) -> GenerationResult:
        ctx = self.engine.usecase_context(self.brain, usecase_name)
        return await self._generate_static("usecase.kt.j2", ctx, usecase_name)

    async def generate_di_module(self, feature_name: str) -> GenerationResult:
        ctx = self.engine.di_module_context(self.brain, feature_name)
        return await self._generate_static("di_module.kt.j2", ctx, feature_name or "app")

    async def generate_nav_route(self, screen_id: str) -> GenerationResult:
        ctx = self.engine.nav_route_context(self.brain, screen_id)
        return await self._generate_static("nav_route.kt.j2", ctx, screen_id)

    async def generate_viewmodel_test(self, screen_id: str) -> GenerationResult:
        ctx = self.engine.viewmodel_test_context(self.brain, screen_id)
        return await self._generate_static("viewmodel_test.kt.j2", ctx, f"{screen_id}_test")

    # ── File writing with backup ─────────────────────────────────────

    def write_result(self, result: GenerationResult, output_path: str | Path) -> GenerationResult:
        from project_brain.generators.roadmap_generator import RoadmapGenerator
        path = Path(output_path)
        if path.exists():
            backup = path.with_suffix(f".brain_backup_{utc_now().replace(':', '').replace('-', '').replace('T', '_').replace('Z', '')}.kt")
            shutil.copy(path, backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.content, encoding="utf-8")
        entry = GenerationHistoryEntry(
            tool=result.template,
            target=result.target_id,
            output_path=str(path),
            status="clean" if result.clean else "violations_present",
            notes=f"attempts={result.attempts}, used_llm={result.used_llm}",
        )
        self.brain.generation_history.append(entry)
        # Update roadmap tracking in-memory before the single save
        rg = RoadmapGenerator()
        rg.update_brain_status(self.brain, result.template, result.target_id, result.clean)
        BrainManager(self.brain_path).save(self.brain)
        # Rewrite ROADMAP.md if it exists alongside the brain
        roadmap_path = self.brain_path.parent / "ROADMAP.md"
        if roadmap_path.exists():
            rg.write(self.brain, roadmap_path)
        return GenerationResult(
            target_id=result.target_id,
            template=result.template,
            content=result.content,
            attempts=result.attempts,
            clean=result.clean,
            violations=result.violations,
            used_llm=result.used_llm,
            output_path=str(path),
        )

    # ── Internal generation loop ─────────────────────────────────────

    async def _generate_with_llm(self, template_name: str, ctx: dict, target_id: str) -> GenerationResult:
        """Generation loop with LLM function fill and self-healing."""
        functions_spec = ctx.pop("_functions_spec", [])
        state_class = ctx.pop("_ui_state_class", "UiState")
        violations_to_avoid: list[str] = []
        used_llm = False

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            # Step 1: Fill function bodies
            if functions_spec:
                fn_specs = [
                    FunctionSpec(
                        name=f.name,
                        params=list(f.params),
                        returns=f.returns,
                        business_rule=f.business_rule,
                    )
                    for f in functions_spec
                ]
                fill_spec = FillFunctionsSpec(
                    functions=fn_specs,
                    architecture=self.brain.meta.architecture,
                    package_name=self.brain.meta.package_name or "com.example.app",
                    state_class_name=state_class,
                    dependencies=[f"{d['param_name']}: {d['type']}" for d in ctx.get("dependencies", [])],
                    business_rules=[rule.description for rule in self.brain.business_rules],
                    violations_to_avoid=violations_to_avoid,
                )
                try:
                    ctx["functions"] = await self.llm.fill_functions(fill_spec)
                    used_llm = not isinstance(self.llm, NullAdapter)
                except Exception:
                    ctx["functions"] = "    // TODO: implement"

            # Step 2: Render template
            content = self.engine.render(template_name, ctx)

            # Step 3: Validate
            report = self.validator.validate_content(content, f"<generated:{target_id}>")

            if report.class_a_count == 0:
                return GenerationResult(
                    target_id=target_id,
                    template=template_name,
                    content=content,
                    attempts=attempt,
                    clean=True,
                    used_llm=used_llm,
                )

            # Step 4: Auto-fix CLASS_A violations
            content = _auto_fix(content, report.violations)
            report = self.validator.validate_content(content, f"<generated:{target_id}>")

            if report.class_a_count == 0:
                return GenerationResult(
                    target_id=target_id,
                    template=template_name,
                    content=content,
                    attempts=attempt,
                    clean=True,
                    used_llm=used_llm,
                )

            # Step 5: Feed violations back for retry
            violations_to_avoid = [v.description for v in report.violations if v.severity == "CLASS_A"]
            ctx["_functions_spec"] = functions_spec

        return GenerationResult(
            target_id=target_id,
            template=template_name,
            content=content,
            attempts=_MAX_ATTEMPTS,
            clean=False,
            violations=[v.to_dict() for v in report.violations],
            used_llm=used_llm,
        )

    async def _generate_static(self, template_name: str, ctx: dict, target_id: str) -> GenerationResult:
        """Zero-LLM generation for deterministic templates."""
        ctx.pop("_functions_spec", None)
        ctx.pop("_ui_state_class", None)
        content = self.engine.render(template_name, ctx)
        report = self.validator.validate_content(content, f"<generated:{target_id}>")
        if report.class_a_count > 0:
            content = _auto_fix(content, report.violations)
            report = self.validator.validate_content(content, f"<generated:{target_id}>")
        return GenerationResult(
            target_id=target_id,
            template=template_name,
            content=content,
            attempts=1,
            clean=report.class_a_count == 0,
            violations=[v.to_dict() for v in report.violations],
            used_llm=False,
        )


def _auto_fix(content: str, violations: list[Violation]) -> str:
    """Apply deterministic fixes for CLASS_A violations."""
    for violation in violations:
        if violation.severity != "CLASS_A":
            continue
        if violation.rule_id == "A001":
            content = re.sub(r"^import\s+android\.content\.Context\s*\n", "", content, flags=re.M)
        elif violation.rule_id == "A002":
            content = re.sub(r"^import\s+androidx\.compose\.[^\n]+\n", "", content, flags=re.M)
        # A003 (business logic in Composable): structural — can't auto-fix safely
        # A004 (StateFlow visibility): templates always produce correct patterns
        # A005 (Repository must have interface): templates produce both files
    return content
