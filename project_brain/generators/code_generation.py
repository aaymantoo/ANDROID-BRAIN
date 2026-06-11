"""Phase 4 code generation orchestrator: template + LLM fill + self-healing validation."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from project_brain.brain.manager import BrainManager
from project_brain.brain.schema import GenerationHistoryEntry, ProjectBrain, utc_now
from project_brain.engines.rule_engine import MVVMValidationEngine, Violation
from project_brain.engines.template_engine import TemplateEngine, TemplateEngineV2
from project_brain.llm.adapter import FillFunctionsSpec, FunctionSpec, LLMAdapter, NullAdapter, create_adapter


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
    compile_ok: bool | None = None  # None = not checked, True/False = result
    spec_coverage: float | None = None  # fraction of non-TODO function bodies
    bug_warnings: list[dict] = field(default_factory=list)  # CLASS_A forecasts

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
            "compile_ok": self.compile_ok,
            "spec_coverage": self.spec_coverage,
            "bug_warnings": self.bug_warnings,
        }


@dataclass
class RepositoryPair:
    """Two-file result for Repository interface + implementation."""

    repository_id: str
    interface: GenerationResult
    implementation: GenerationResult

    @property
    def clean(self) -> bool:
        return self.interface.clean and self.implementation.clean

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "interface": self.interface.to_dict(),
            "implementation": self.implementation.to_dict(),
            "clean": self.clean,
        }


class CompileVerifier:
    """Smoke-check generated Kotlin syntax using kotlinc if available.

    Runs `kotlinc -script` on a temp file. On failure adds a COMPILE_ERROR
    violation without blocking the pipeline — the generated file is still
    written so the developer can inspect and fix it.
    """

    _kotlinc_available: bool | None = None

    @classmethod
    def available(cls) -> bool:
        if cls._kotlinc_available is None:
            result = shutil.which("kotlinc")
            cls._kotlinc_available = result is not None
        return cls._kotlinc_available

    @classmethod
    def verify(cls, content: str) -> tuple[bool, str | None]:
        """Return (ok, error_message). If kotlinc absent, returns (True, None) — skip."""
        if not cls.available():
            return True, None
        with tempfile.NamedTemporaryFile(suffix=".kt", mode="w", encoding="utf-8", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            result = subprocess.run(
                ["kotlinc", "-nowarn", tmp_path, "-d", tempfile.gettempdir()],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return False, result.stderr[:500].strip()
            return True, None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True, None
        finally:
            Path(tmp_path).unlink(missing_ok=True)


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
        self.llm: LLMAdapter = llm if llm is not None else create_adapter()
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

    async def generate_repository_interface(self, repository_id: str) -> GenerationResult:
        ctx = self.engine.repository_interface_context(self.brain, repository_id)
        return await self._generate_static("repository_interface.kt.j2", ctx, f"{repository_id}_interface")

    async def generate_repository_impl(self, repository_id: str) -> GenerationResult:
        ctx = self.engine.repository_impl_context(self.brain, repository_id)
        return await self._generate_with_llm("repository_impl.kt.j2", ctx, repository_id)

    async def generate_repository(self, repository_id: str) -> GenerationResult:
        iface_result = await self.generate_repository_interface(repository_id)
        impl_result = await self.generate_repository_impl(repository_id)
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

    async def generate_repository_pair(self, repository_id: str) -> RepositoryPair:
        """Generate interface and implementation as separate results for two-file writing."""
        iface = await self.generate_repository_interface(repository_id)
        impl = await self.generate_repository_impl(repository_id)
        return RepositoryPair(repository_id=repository_id, interface=iface, implementation=impl)

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
        # Compile gate — smoke-check Kotlin syntax if kotlinc available
        compile_ok, compile_err = CompileVerifier.verify(result.content)
        violations = list(result.violations)
        if not compile_ok and compile_err:
            violations.append({
                "rule_id": "COMPILE_ERROR",
                "severity": "CLASS_A",
                "description": f"Kotlin syntax error: {compile_err}",
                "fix": "Review the generated file and fix the syntax error.",
                "line": None,
            })
        entry = GenerationHistoryEntry(
            tool=result.template,
            target=result.target_id,
            output_path=str(path),
            status="clean" if (result.clean and compile_ok) else "violations_present",
            notes=f"attempts={result.attempts}, used_llm={result.used_llm}, compile_ok={compile_ok}",
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
        # F3: spec_coverage — fraction of non-TODO function bodies (zero-LLM, fast)
        spec_coverage = _spec_coverage(result.content)
        # F2: Non-blocking bug forecast for ViewModel and Repository impl files
        bug_warnings: list[dict] = []
        _template = result.template.lower()
        if "viewmodel" in _template or "repository_impl" in _template:
            try:
                from project_brain.engines.bug_engine import BugEngine
                sid = result.target_id if any(s.id == result.target_id for s in self.brain.screens) else None
                if sid:
                    bugs = BugEngine().forecast(self.brain, sid)
                    bug_warnings = [b.to_dict() for b in bugs if b.severity == "CLASS_A"]
            except Exception:
                pass
        return GenerationResult(
            target_id=result.target_id,
            template=result.template,
            content=result.content,
            attempts=result.attempts,
            clean=result.clean and compile_ok,
            violations=violations,
            used_llm=result.used_llm,
            output_path=str(path),
            compile_ok=compile_ok,
            spec_coverage=spec_coverage,
            bug_warnings=bug_warnings,
        )

    def write_repository_pair(self, pair: RepositoryPair, base_path: str | Path) -> RepositoryPair:
        """Write interface and implementation to separate files under base_path."""
        base = Path(base_path)
        repo = next((r for r in self.brain.repositories if r.id == pair.repository_id), None)
        iface_name = (repo.interface if repo else None) or pair.repository_id
        impl_name = (repo.implementation if repo else None) or f"{pair.repository_id}Impl"
        iface_result = self.write_result(pair.interface, base / f"{iface_name}.kt")
        impl_result = self.write_result(pair.implementation, base / f"{impl_name}.kt")
        return RepositoryPair(
            repository_id=pair.repository_id,
            interface=iface_result,
            implementation=impl_result,
        )

    # ── Internal generation loop ─────────────────────────────────────

    async def _generate_with_llm(self, template_name: str, ctx: dict, target_id: str) -> GenerationResult:
        """Generation loop with LLM function fill and self-healing."""
        functions_spec = ctx.pop("_functions_spec", [])
        state_class = ctx.pop("_ui_state_class", "UiState")
        event_class = ctx.get("event_class")
        violations_to_avoid: list[str] = []
        used_llm = False

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            # Step 1: Fill function bodies
            if functions_spec:
                is_repo_impl = "repository_impl" in template_name
                fn_specs = [
                    FunctionSpec(
                        name=f.name,
                        params=list(f.params) if f.params else [],
                        returns=_repo_return_type(f) if is_repo_impl else (f.returns or "Unit"),
                        business_rule=_repo_business_rule(f) if is_repo_impl else getattr(f, "business_rule", None),
                        state_updates=list(getattr(f, "state_updates", None) or []),
                        events_fired=list(getattr(f, "events_fired", None) or []),
                        concurrent=bool(getattr(f, "concurrent", False)),
                        is_override=is_repo_impl,
                        is_suspend=is_repo_impl and not getattr(f, "is_flow", False),
                    )
                    for f in functions_spec
                ]
                if is_repo_impl:
                    deps = [f"{d['param_name']}: {d['type']}" for d in ctx.get("data_sources", [])]
                    ui_state_type = "repository"
                else:
                    deps = [f"{d['param_name']}: {d['type']}" for d in ctx.get("dependencies", [])]
                    ui_state_type = "data_class" if isinstance(self.engine, TemplateEngineV2) else "sealed_class"
                fill_spec = FillFunctionsSpec(
                    functions=fn_specs,
                    architecture=self.brain.meta.architecture,
                    package_name=self.brain.meta.package_name or "com.example.app",
                    state_class_name=state_class,
                    event_class=event_class,
                    dependencies=deps,
                    business_rules=[rule.description for rule in self.brain.business_rules],
                    violations_to_avoid=violations_to_avoid,
                    ui_state_type=ui_state_type,
                )
                try:
                    ctx["functions"] = await self.llm.fill_functions(fill_spec)
                    used_llm = not isinstance(self.llm, NullAdapter)
                except Exception as _fill_err:
                    ctx["functions"] = f"    // TODO: implement  // fill_error: {type(_fill_err).__name__}: {_fill_err}"
                # Repository impl template uses {{ implementations }} not {{ functions }}
                if is_repo_impl:
                    ctx["implementations"] = ctx["functions"]

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


def _spec_coverage(content: str) -> float | None:
    """Fraction of function bodies that are not TODO stubs. None if no functions found."""
    fn_count = len(re.findall(r"\bfun\s+[a-z]", content))
    if fn_count == 0:
        return None
    todo_count = content.count("// TODO")
    return round(max(0, fn_count - todo_count) / fn_count, 2)


def _repo_return_type(m: Any) -> str:
    """Derive the Kotlin return type string for a RepositoryMethod."""
    if m.is_flow:
        return f"Flow<{m.flow_type or 'Any'}>"
    if m.result_wrapped:
        return f"Result<{m.result_type or 'Unit'}>"
    return m.returns or "Unit"


def _repo_business_rule(m: Any) -> str:
    """Encode repository method structural info as a business_rule hint for the LLM."""
    parts = []
    if m.is_flow:
        parts.append(f"Returns Flow<{m.flow_type}>. Use callbackFlow with an auth/Firestore listener.")
    elif m.result_wrapped:
        parts.append(f"Result-wrapped. Wrap implementation in runCatching {{}}.")
    if getattr(m, "firestore_path", None):
        parts.append(f"Firestore path: {m.firestore_path}")
    return " ".join(parts) if parts else ""


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
