"""Jinja2 template engine and brain context builders for Phase 4 code generation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined

from project_brain.brain.schema import (
    DataModel,
    ProjectBrain,
    Repository,
    Screen,
    ViewModel,
)


_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "v1"
_TEMPLATES_DIR_V2 = Path(__file__).parent.parent.parent / "templates" / "v2"

_NAV_TYPE_MAP: dict[str, str] = {
    "String": "StringType",
    "Int": "IntType",
    "Long": "LongType",
    "Boolean": "BoolType",
    "Float": "FloatType",
}

_DEFAULT_VALUE_MAP: dict[str, str] = {
    "String": '""',
    "Int": "0",
    "Long": "0L",
    "Double": "0.0",
    "Float": "0f",
    "Boolean": "false",
}


class TemplateEngine:
    def __init__(self, templates_dir: str | Path = _TEMPLATES_DIR) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        template = self._env.get_template(template_name)
        return template.render(**context)

    # ── Context builders ────────────────────────────────────────────

    def viewmodel_context(self, brain: ProjectBrain, screen_id: str) -> dict[str, Any]:
        screen = _require_screen(brain, screen_id)
        viewmodel = _find_viewmodel(brain, screen.viewmodel)
        pkg = brain.meta.package_name or "com.example.app"
        feature = _feature_name(screen_id)
        vm_name = viewmodel.id if viewmodel else f"{screen_id.replace('Screen', '')}ViewModel"
        ui_state = (viewmodel.ui_state_class if viewmodel else None) or f"{screen_id.replace('Screen', '')}UiState"
        deps = _dependency_list(brain, viewmodel.inject_dependencies if viewmodel else [], pkg)
        functions_spec = viewmodel.functions if viewmodel else []
        extra_flows = [
            {"name": sf, "type": "Any"}
            for sf in (screen.stateflows or [])
            if sf != "uiState"
        ]
        return {
            "package_name": pkg,
            "feature_name": feature,
            "viewmodel_name": vm_name,
            "ui_state_class": ui_state,
            "dependencies": deps,
            "extra_stateflows": extra_flows,
            "extra_imports": [],
            "functions": "    // TODO: implement",
            "_functions_spec": functions_spec,
            "_ui_state_class": ui_state,
        }

    def uistate_context(self, brain: ProjectBrain, screen_id: str) -> dict[str, Any]:
        screen = _require_screen(brain, screen_id)
        pkg = brain.meta.package_name or "com.example.app"
        feature = _feature_name(screen_id)
        state_name = f"{screen_id.replace('Screen', '')}UiState"
        primary_model = _primary_model(brain, screen)
        extra = [
            f"data object {s} : {state_name}()"
            for s in (screen.ui_states or [])
            if s not in {"Loading", "Success", "Error"}
        ]
        return {
            "package_name": pkg,
            "feature_name": feature,
            "state_class_name": state_name,
            "data_type": primary_model,
            "extra_states": extra,
        }

    def repository_interface_context(self, brain: ProjectBrain, repository_id: str) -> dict[str, Any]:
        repo = _require_repository(brain, repository_id)
        pkg = brain.meta.package_name or "com.example.app"
        interface_name = repo.interface or f"I{repository_id}"
        methods = [
            f"suspend fun {m.name}({', '.join(m.params)}): {m.returns or 'Unit'}"
            for m in repo.methods
        ] or ["suspend fun getAll(): List<Any>"]
        return {
            "package_name": pkg,
            "interface_name": interface_name,
            "methods": methods,
        }

    def repository_impl_context(self, brain: ProjectBrain, repository_id: str) -> dict[str, Any]:
        repo = _require_repository(brain, repository_id)
        pkg = brain.meta.package_name or "com.example.app"
        impl_name = repo.implementation or f"{repository_id}Impl"
        interface_name = repo.interface or f"I{repository_id}"
        method_stubs = "\n".join(
            f"\n    override suspend fun {m.name}({', '.join(m.params)}): {m.returns or 'Unit'} {{\n        // TODO: implement\n    }}"
            for m in repo.methods
        ) or "\n    // TODO: implement methods"
        return {
            "package_name": pkg,
            "impl_name": impl_name,
            "interface_name": interface_name,
            "implementations": method_stubs,
        }

    def datamodel_context(self, brain: ProjectBrain, model_id: str) -> dict[str, Any]:
        model = _require_model(brain, model_id)
        pkg = brain.meta.package_name or "com.example.app"
        fields = [
            {
                "name": f.name,
                "type": f.type,
                "nullable": f.nullable,
                "default": "null" if f.nullable else _DEFAULT_VALUE_MAP.get(f.type, '""'),
            }
            for f in model.fields
        ]
        return {
            "package_name": pkg,
            "model_name": model_id,
            "fields": fields,
        }

    def screen_scaffold_context(self, brain: ProjectBrain, screen_id: str) -> dict[str, Any]:
        screen = _require_screen(brain, screen_id)
        viewmodel = _find_viewmodel(brain, screen.viewmodel)
        pkg = brain.meta.package_name or "com.example.app"
        feature = _feature_name(screen_id)
        vm_name = viewmodel.id if viewmodel else f"{screen_id.replace('Screen', '')}ViewModel"
        ui_state = (viewmodel.ui_state_class if viewmodel else None) or f"{screen_id.replace('Screen', '')}UiState"
        primary_model = _primary_model(brain, screen)
        return {
            "package_name": pkg,
            "feature_name": feature,
            "screen_name": screen_id,
            "viewmodel_name": vm_name,
            "ui_state_class": ui_state,
            "data_type": primary_model,
            "nav_args": screen.nav_args or [],
        }

    def usecase_context(self, brain: ProjectBrain, usecase_name: str) -> dict[str, Any]:
        pkg = brain.meta.package_name or "com.example.app"
        repo_type = _infer_usecase_repository(brain, usecase_name)
        invoke_sig = f"suspend operator fun invoke(): Any?"
        if "Get" in usecase_name or "Fetch" in usecase_name:
            param = _snake(usecase_name.replace("Get", "").replace("UseCase", "").replace("Fetch", ""))
            invoke_sig = f"suspend operator fun invoke({param}Id: String): Any?"
        return {
            "package_name": pkg,
            "usecase_name": usecase_name,
            "repository_type": repo_type,
            "invoke_signature": invoke_sig,
        }

    def di_module_context(self, brain: ProjectBrain, feature_name: str) -> dict[str, Any]:
        pkg = brain.meta.package_name or "com.example.app"
        bindings = [
            {
                "interface": repo.interface or f"I{repo.id}",
                "implementation": repo.implementation or f"{repo.id}Impl",
            }
            for repo in brain.repositories
            if feature_name.lower() in repo.id.lower() or not feature_name
        ]
        if not bindings and brain.repositories:
            bindings = [
                {
                    "interface": repo.interface or f"I{repo.id}",
                    "implementation": repo.implementation or f"{repo.id}Impl",
                }
                for repo in brain.repositories
            ]
        module_name = f"{feature_name.title().replace('_', '')}Module" if feature_name else "AppModule"
        return {
            "package_name": pkg,
            "module_name": module_name,
            "bindings": bindings,
        }

    def nav_route_context(self, brain: ProjectBrain, screen_id: str) -> dict[str, Any]:
        screen = _require_screen(brain, screen_id)
        pkg = brain.meta.package_name or "com.example.app"
        route_str = screen.route or _snake(screen_id.replace("Screen", ""))
        route_base = route_str.split("/{")[0] if "/{" in route_str else route_str
        # Prefer explicit nav_args; fall back to extracting from route pattern
        if screen.nav_args:
            args = _parse_nav_args(screen.nav_args)
        else:
            args = _args_from_route(route_str)
        route_object = screen_id.replace("Screen", "Route")
        route_name = screen_id.replace("Screen", "")
        return {
            "package_name": pkg,
            "route_object": route_object,
            "route_name": route_name,
            "route_string": route_str,
            "route_base": route_base,
            "args": args,
        }

    def viewmodel_test_context(self, brain: ProjectBrain, screen_id: str) -> dict[str, Any]:
        ctx = self.viewmodel_context(brain, screen_id)
        return {
            "package_name": ctx["package_name"],
            "feature_name": ctx["feature_name"],
            "viewmodel_name": ctx["viewmodel_name"],
            "ui_state_class": ctx["ui_state_class"],
            "dependencies": ctx["dependencies"],
            "functions": ctx["_functions_spec"],
        }


# ── Helpers ─────────────────────────────────────────────────────────────────


def _require_screen(brain: ProjectBrain, screen_id: str) -> Screen:
    screen = next((s for s in brain.screens if s.id == screen_id), None)
    if not screen:
        raise KeyError(f"Screen not found in brain: {screen_id}")
    return screen


def _require_repository(brain: ProjectBrain, repository_id: str) -> Repository:
    repo = next((r for r in brain.repositories if r.id == repository_id), None)
    if not repo:
        raise KeyError(f"Repository not found in brain: {repository_id}")
    return repo


def _require_model(brain: ProjectBrain, model_id: str) -> DataModel:
    model = next((m for m in brain.data_models if m.id == model_id), None)
    if not model:
        raise KeyError(f"Data model not found in brain: {model_id}")
    return model


def _find_viewmodel(brain: ProjectBrain, viewmodel_id: str | None) -> ViewModel | None:
    if not viewmodel_id:
        return None
    return next((v for v in brain.viewmodels if v.id == viewmodel_id), None)


def _feature_name(screen_id: str) -> str:
    return _snake(screen_id.replace("Screen", ""))


def _snake(value: str) -> str:
    text = re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "feature"


def _dependency_list(brain: ProjectBrain, dep_names: list[str], pkg: str) -> list[dict]:
    result: list[dict] = []
    for name in dep_names:
        param = name[0].lower() + name[1:]
        import_path = _guess_import(name, pkg)
        result.append({"param_name": param, "type": name, "import_path": import_path})
    return result


def _guess_import(class_name: str, pkg: str) -> str | None:
    if class_name.endswith("Repository"):
        return f"{pkg}.data.repository.{class_name}"
    if class_name.endswith("UseCase"):
        return f"{pkg}.domain.usecase.{class_name}"
    if class_name.endswith("StateHolder"):
        return f"{pkg}.data.{class_name}"
    return None


def _primary_model(brain: ProjectBrain, screen: Screen) -> str:
    if screen.models:
        return screen.models[0]
    return "Any"


def _infer_usecase_repository(brain: ProjectBrain, usecase_name: str) -> str:
    for screen in brain.screens:
        if usecase_name in screen.use_cases:
            if screen.repository:
                return screen.repository
    for vm in brain.viewmodels:
        if usecase_name in vm.use_cases:
            if vm.repository:
                return vm.repository
    return "Repository"


def _parse_nav_args(nav_args: list[str]) -> list[dict]:
    result: list[dict] = []
    for arg in nav_args:
        parts = arg.split(":")
        if len(parts) != 2:
            continue
        name = parts[0].strip()
        type_ = parts[1].strip().rstrip("?")
        nav_type = _NAV_TYPE_MAP.get(type_, "StringType")
        const_name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()
        result.append({"name": name, "type": type_, "nav_type": nav_type, "const_name": const_name})
    return result


class TemplateEngineV2(TemplateEngine):
    """Enterprise v2 template engine: data-class state, Channel events, Result<T>, @Singleton.

    Falls back to v1 templates for any template not present in v2 (e.g. nav_route).
    """

    def __init__(self) -> None:
        # TemplateEngine.__init__ builds the basic env; we replace the loader to add fallback.
        super().__init__(templates_dir=_TEMPLATES_DIR_V2)
        self._env = Environment(
            loader=ChoiceLoader([
                FileSystemLoader(str(_TEMPLATES_DIR_V2)),
                FileSystemLoader(str(_TEMPLATES_DIR)),
            ]),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )

    def viewmodel_context(self, brain: ProjectBrain, screen_id: str) -> dict[str, Any]:
        screen = _require_screen(brain, screen_id)
        viewmodel = _find_viewmodel(brain, screen.viewmodel)
        pkg = brain.meta.package_name or "com.example.app"
        feature = _feature_name(screen_id)
        vm_name = viewmodel.id if viewmodel else f"{screen_id.replace('Screen', '')}ViewModel"
        ui_state = (viewmodel.ui_state_class if viewmodel else None) or f"{screen_id.replace('Screen', '')}UiState"
        deps = _dependency_list(brain, viewmodel.inject_dependencies if viewmodel else [], pkg)
        functions_spec = viewmodel.functions if viewmodel else []
        has_mutex = viewmodel.has_mutex if viewmodel else any(f.concurrent for f in functions_spec)
        event_class = (viewmodel.event_class if viewmodel else None) or f"{screen_id.replace('Screen', '')}Event"
        has_events = bool(viewmodel.events if viewmodel else False)
        return {
            "package_name": pkg,
            "feature_name": feature,
            "viewmodel_name": vm_name,
            "ui_state_class": ui_state,
            "event_class": event_class if has_events else None,
            "has_mutex": has_mutex,
            "has_saved_state": viewmodel.has_saved_state if viewmodel else False,
            "dependencies": deps,
            "extra_imports": [],
            "functions": "    // TODO: implement",
            "_functions_spec": functions_spec,
            "_ui_state_class": ui_state,
        }

    def uistate_context(self, brain: ProjectBrain, screen_id: str) -> dict[str, Any]:
        screen = _require_screen(brain, screen_id)
        viewmodel = _find_viewmodel(brain, screen.viewmodel)
        pkg = brain.meta.package_name or "com.example.app"
        feature = _feature_name(screen_id)
        state_name = (viewmodel.ui_state_class if viewmodel else None) or f"{screen_id.replace('Screen', '')}UiState"
        if viewmodel and viewmodel.state_fields:
            state_fields = [
                {"name": f.name, "type": f.type, "nullable": f.nullable, "default": f.default}
                for f in viewmodel.state_fields
            ]
        else:
            state_fields = [
                {"name": "isLoading", "type": "Boolean", "nullable": False, "default": "false"},
                {"name": "error", "type": "String", "nullable": True, "default": "null"},
            ]
        return {
            "package_name": pkg,
            "feature_name": feature,
            "state_class_name": state_name,
            "state_fields": state_fields,
        }

    def repository_interface_context(self, brain: ProjectBrain, repository_id: str) -> dict[str, Any]:
        repo = _require_repository(brain, repository_id)
        pkg = brain.meta.package_name or "com.example.app"
        interface_name = repo.interface or f"{repository_id}"
        methods = [
            {
                "name": m.name,
                "params": m.params,
                "returns": m.returns or "Unit",
                "result_wrapped": m.result_wrapped,
                "result_type": m.result_type or m.returns or "Unit",
                "is_flow": m.is_flow,
                "flow_type": m.flow_type or "Any",
            }
            for m in repo.methods
        ]
        if not methods:
            methods = [{"name": "getAll", "params": [], "returns": "List<Any>",
                        "result_wrapped": False, "result_type": "List<Any>",
                        "is_flow": False, "flow_type": "Any"}]
        return {"package_name": pkg, "interface_name": interface_name, "methods": methods}

    def repository_impl_context(self, brain: ProjectBrain, repository_id: str) -> dict[str, Any]:
        repo = _require_repository(brain, repository_id)
        pkg = brain.meta.package_name or "com.example.app"
        impl_name = repo.implementation or f"{repository_id}Impl"
        interface_name = repo.interface or f"{repository_id}"
        if repo.typed_data_sources:
            data_sources = [
                {"param_name": ds.param_name, "type": ds.type}
                for ds in repo.typed_data_sources
            ]
        else:
            data_sources = [{"param_name": "firestore", "type": "FirebaseFirestore"}]
        method_stubs = "\n".join(
            _build_result_stub(m)
            for m in repo.methods
        ) or "\n    // TODO: implement methods"
        # collect all type references for domain import resolution
        type_refs = [m.returns or "" for m in repo.methods] + [m.result_type or "" for m in repo.methods]
        domain_imports = _resolve_domain_imports(type_refs, pkg)
        return {
            "package_name": pkg,
            "impl_name": impl_name,
            "interface_name": interface_name,
            "data_sources": data_sources,
            "extra_imports": _infer_repo_imports(repo, pkg) + domain_imports,
            "implementations": method_stubs,
        }

    def screen_scaffold_context(self, brain: ProjectBrain, screen_id: str) -> dict[str, Any]:
        screen = _require_screen(brain, screen_id)
        viewmodel = _find_viewmodel(brain, screen.viewmodel)
        pkg = brain.meta.package_name or "com.example.app"
        feature = _feature_name(screen_id)
        vm_name = viewmodel.id if viewmodel else f"{screen_id.replace('Screen', '')}ViewModel"
        ui_state = (viewmodel.ui_state_class if viewmodel else None) or f"{screen_id.replace('Screen', '')}UiState"
        event_class = (viewmodel.event_class if viewmodel else None) or f"{screen_id.replace('Screen', '')}Event"
        has_events = bool(viewmodel.events if viewmodel else False)
        events = []
        for e in (viewmodel.events if viewmodel else []):
            if e.has_data and e.data:
                args = ", ".join(
                    f"event.{part.split(':')[0].strip().lstrip('val').strip()}"
                    for part in e.data.split(",")
                    if ":" in part
                )
                handler = f"on{e.name}({args})"
            else:
                handler = f"on{e.name}()"
            events.append({"name": e.name, "handler": handler})
        nav_callbacks = []
        for e in (viewmodel.events if viewmodel else []):
            if e.has_data and e.data:
                # extract types from "val foo: Bar, val baz: Qux" → "(Bar, Qux) -> Unit"
                types = ", ".join(
                    part.split(":")[-1].strip()
                    for part in e.data.split(",")
                    if ":" in part
                )
                nav_callbacks.append(f"on{e.name}: ({types}) -> Unit")
            else:
                nav_callbacks.append(f"on{e.name}: () -> Unit")
        functions = viewmodel.functions if viewmodel else []
        return {
            "package_name": pkg,
            "feature_name": feature,
            "screen_name": screen_id,
            "viewmodel_name": vm_name,
            "ui_state_class": ui_state,
            "event_class": event_class if has_events else None,
            "events": events,
            "nav_callbacks": nav_callbacks,
            "nav_args": screen.nav_args or [],
            "viewmodel_functions": [{"name": f.name, "params": f.params} for f in functions],
            "extra_imports": [],
        }


def _build_result_stub(m: Any) -> str:
    params = ", ".join(m.params)
    if m.is_flow:
        return f"\n    override fun {m.name}({params}): Flow<{m.flow_type or 'Any'}> {{\n        // TODO: implement\n        return kotlinx.coroutines.flow.emptyFlow()\n    }}"
    elif m.result_wrapped:
        return f"\n    override suspend fun {m.name}({params}): Result<{m.result_type or 'Unit'}> = runCatching {{\n        // TODO: implement\n    }}"
    return f"\n    override suspend fun {m.name}({params}): {m.returns or 'Unit'} {{\n        // TODO: implement\n    }}"


def _infer_repo_imports(repo: Any, pkg: str) -> list[str]:
    imports = []
    has_flow = any(m.is_flow for m in repo.methods)
    has_result = any(m.result_wrapped for m in repo.methods)
    if has_flow:
        imports.append("kotlinx.coroutines.flow.emptyFlow")
    if has_result:
        imports.append("kotlinx.coroutines.tasks.await")
    for ds in (repo.typed_data_sources or []):
        if "FirebaseFirestore" in ds.type:
            imports.append("com.google.firebase.firestore.FirebaseFirestore")
        elif "FirebaseAuth" in ds.type:
            imports.append("com.google.firebase.auth.FirebaseAuth")
        elif "DataStore" in ds.type:
            imports.append("androidx.datastore.core.DataStore")
            imports.append("androidx.datastore.preferences.core.Preferences")
        elif ds.import_path:
            imports.append(ds.import_path)
    return imports


def _resolve_domain_imports(type_refs: list[str], pkg: str) -> list[str]:
    """Derive import paths for domain types referenced in method signatures.

    Handles: Result<User?>, Flow<Order?>, AppResult<X>, and bare model names.
    Unknown types are mapped to {pkg}.domain.model.{TypeName}.
    """
    known: dict[str, str] = {
        "Result": "",  # stdlib, no import
        "Flow": "kotlinx.coroutines.flow.Flow",
        "Unit": "",
        "String": "",
        "Int": "",
        "Boolean": "",
        "Long": "",
        "Double": "",
        "Float": "",
        "Any": "",
        "List": "",
        "Map": "",
    }
    imports = []
    all_tokens: set[str] = set()
    for ref in type_refs:
        # extract bare type names from generic params: "Result<User?>" → ["Result", "User"]
        for token in re.findall(r"[A-Z][A-Za-z0-9]+", ref):
            all_tokens.add(token)
    for token in all_tokens:
        if token in known:
            if known[token]:
                imports.append(known[token])
        else:
            # heuristic: domain models → domain.model, error types → domain.util
            if token.endswith("Error") or token.endswith("Result") or token == "AppResult":
                imports.append(f"{pkg}.domain.util.{token}")
            else:
                imports.append(f"{pkg}.domain.model.{token}")
    return sorted(set(imp for imp in imports if imp))


def _args_from_route(route: str) -> list[dict]:
    """Extract nav args from route path parameters like order_tracking/{orderId}."""
    result: list[dict] = []
    for match in re.finditer(r"\{(\w+)\}", route):
        name = match.group(1)
        const_name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()
        result.append({"name": name, "type": "String", "nav_type": "StringType", "const_name": const_name})
    return result
