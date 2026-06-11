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
    StateField,
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
            "_functions_spec": repo.methods,
            "_ui_state_class": impl_name,
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
        method = _infer_usecase_method(brain, usecase_name)
        repo_var = "repository"  # matches the constructor param name in the usecase template
        if method:
            params_sig = ", ".join(method.params or [])
            param_names = [p.split(":")[0].strip() for p in (method.params or [])]
            ret = _repo_method_return(method)
            invoke_sig = f"suspend operator fun invoke({params_sig}): {ret}"
            delegation_call = f"{repo_var}.{method.name}({', '.join(param_names)})"
        else:
            invoke_sig = "suspend operator fun invoke(): Any?"
            delegation_call = f'TODO("implement {usecase_name}")'
        return {
            "package_name": pkg,
            "usecase_name": usecase_name,
            "repository_type": repo_type,
            "invoke_signature": invoke_sig,
            "delegation_call": delegation_call,
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
        screen = _require_screen(brain, screen_id)
        viewmodel = _find_viewmodel(brain, screen.viewmodel)
        state_fields = viewmodel.state_fields if viewmodel else []
        has_saved_state = viewmodel.has_saved_state if viewmodel else False
        # Derive test-friendly field names from the actual state_fields
        loading_field = _find_loading_state_field(state_fields)
        error_field = _find_error_state_field(state_fields)
        # Build SavedStateHandle initial map from the screen's nav_args
        saved_state_initial = _build_saved_state_initial(screen.nav_args or [])
        return {
            "package_name": ctx["package_name"],
            "feature_name": ctx["feature_name"],
            "viewmodel_name": ctx["viewmodel_name"],
            "ui_state_class": ctx["ui_state_class"],
            "dependencies": ctx["dependencies"],
            "functions": ctx["_functions_spec"],
            # v3
            "has_saved_state": has_saved_state,
            "loading_field": loading_field,
            "error_field": error_field,
            "saved_state_initial": saved_state_initial,
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


def _infer_usecase_method(brain: ProjectBrain, usecase_name: str) -> Any | None:
    """Map UseCase name → repository method by stripping 'UseCase' and lowercasing first letter."""
    base = usecase_name.replace("UseCase", "")
    candidate = base[0].lower() + base[1:] if base else ""
    for repo in brain.repositories:
        for method in repo.methods:
            if method.name == candidate:
                return method
    return None


def _repo_method_return(method: Any) -> str:
    """Return type string for a RepositoryMethod (Flow / Result / plain)."""
    if method.is_flow:
        return f"Flow<{method.flow_type or 'Any'}>"
    if method.result_wrapped:
        return f"Result<{method.result_type or 'Unit'}>"
    return method.returns or "Unit"


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
        # v3: private fields, init block, private helpers, computed properties
        private_fields = [
            {"name": f.name, "type": f.type, "default": f.default, "volatile": f.volatile}
            for f in (viewmodel.private_fields if viewmodel else [])
        ]
        init_lines = list(viewmodel.init_lines) if viewmodel else []
        private_functions = [
            {"name": f.name, "signature": f.signature, "return_type": f.return_type, "body_hint": f.body_hint}
            for f in (viewmodel.private_functions if viewmodel else [])
        ]
        computed_properties = [
            {"name": p.name, "type": p.type, "expression": p.expression}
            for p in (viewmodel.computed_properties if viewmodel else [])
        ]
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
            # v3
            "private_fields": private_fields,
            "init_lines": init_lines,
            "private_functions": private_functions,
            "computed_properties": computed_properties,
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
        # v3: infer private fields from firebase_patterns across methods
        private_fields = _infer_repo_private_fields(repo.methods)
        extra_imports = _infer_repo_imports(repo, pkg) + domain_imports + _infer_firebase_pattern_imports(repo.methods)
        return {
            "package_name": pkg,
            "impl_name": impl_name,
            "interface_name": interface_name,
            "data_sources": data_sources,
            "extra_imports": sorted(set(extra_imports)),
            "private_fields": private_fields,
            "implementations": method_stubs,
            "_functions_spec": repo.methods,
            "_ui_state_class": impl_name,
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
        ui_content = _render_ui_components(screen.ui_components or [])
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
            "extra_imports": _screen_component_imports(screen.ui_components or []),
            "ui_content": ui_content,
        }


_FIREBASE_STUBS: dict[str, str] = {
    "auth_state_listener": (
        "\n    override fun {{name}}({{params}}): Flow<{{ret}}> = callbackFlow {{\n"
        "        val listener = firebaseAuth.addAuthStateListener {{ auth ->\n"
        "            trySend(AppResult.Success(null)) // TODO: map auth.currentUser to domain User\n"
        "        }}\n"
        "        firebaseAuth.addAuthStateListener(listener)\n"
        "        awaitClose {{ firebaseAuth.removeAuthStateListener(listener) }}\n"
        "    }}"
    ),
    "phone_auth": (
        "\n    override suspend fun {{name}}({{params}}): {{ret}} = runCatching {{\n"
        "        suspendCancellableCoroutine {{ cont ->\n"
        "            val callbacks = object : PhoneAuthProvider.OnVerificationStateChangedCallbacks() {{\n"
        "                override fun onVerificationCompleted(c: PhoneAuthCredential) {{ cont.resume(Unit) }}\n"
        "                override fun onVerificationFailed(e: FirebaseException) {{ cont.resumeWithException(e) }}\n"
        "                override fun onCodeSent(id: String, t: PhoneAuthProvider.ForceResendingToken) {{\n"
        "                    savedVerificationId = id; cont.resume(Unit)\n"
        "                }}\n"
        "            }}\n"
        "            PhoneAuthProvider.verifyPhoneNumber(\n"
        "                PhoneAuthOptions.newBuilder(firebaseAuth)\n"
        "                    .setPhoneNumber(phoneNumber)\n"
        "                    .setTimeout(60L, java.util.concurrent.TimeUnit.SECONDS)\n"
        "                    .setCallbacks(callbacks).build()\n"
        "            )\n"
        "        }}\n"
        "    }}"
    ),
    "credential_sign_in": (
        "\n    override suspend fun {{name}}({{params}}): {{ret}} = runCatching {{\n"
        "        val credential = PhoneAuthProvider.getCredential(savedVerificationId, otp)\n"
        "        val result = firebaseAuth.signInWithCredential(credential).await()\n"
        "        val uid = result.user?.uid ?: throw IllegalStateException(\"Sign-in returned no user\")\n"
        "        val doc = firestore.collection(\"users\").document(uid).get().await()\n"
        "        // TODO: map doc snapshot to domain model\n"
        "        TODO(\"map Firestore doc to return type\")\n"
        "    }}"
    ),
    "firestore_get": (
        "\n    override suspend fun {{name}}({{params}}): {{ret}} = runCatching {{\n"
        "        val uid = firebaseAuth.currentUser?.uid ?: throw IllegalStateException(\"Not authenticated\")\n"
        "        val doc = firestore.collection(\"{collection}\").document(uid).get().await()\n"
        "        // TODO: map doc snapshot to domain model\n"
        "        TODO(\"map Firestore doc to return type\")\n"
        "    }}"
    ),
    "firestore_update": (
        "\n    override suspend fun {{name}}({{params}}): {{ret}} = runCatching {{\n"
        "        val uid = firebaseAuth.currentUser?.uid ?: throw IllegalStateException(\"Not authenticated\")\n"
        "        val updates = mapOf<String, Any>( /* TODO: populate fields */ )\n"
        "        firestore.collection(\"{collection}\").document(uid).update(updates).await()\n"
        "    }}"
    ),
}

_FIREBASE_PATTERN_IMPORTS: dict[str, list[str]] = {
    "phone_auth": [
        "com.google.firebase.auth.PhoneAuthCredential",
        "com.google.firebase.auth.PhoneAuthOptions",
        "com.google.firebase.auth.PhoneAuthProvider",
        "com.google.firebase.FirebaseException",
        "kotlin.coroutines.resume",
        "kotlin.coroutines.resumeWithException",
        "kotlinx.coroutines.suspendCancellableCoroutine",
    ],
    "credential_sign_in": [
        "com.google.firebase.auth.PhoneAuthProvider",
    ],
    "auth_state_listener": [],
    "firestore_get": [],
    "firestore_update": [],
}


def _build_result_stub(m: Any) -> str:
    params = ", ".join(m.params)
    pattern = getattr(m, "firebase_pattern", None)
    if pattern and pattern in _FIREBASE_STUBS:
        if m.is_flow:
            ret = f"Flow<{m.flow_type or 'Any'}>"
        elif m.result_wrapped:
            ret = f"Result<{m.result_type or 'Unit'}>"
        else:
            ret = m.returns or "Unit"
        collection = (m.firestore_path or "collection_name").strip("/").split("/")[0]
        stub = _FIREBASE_STUBS[pattern]
        stub = stub.replace("{name}", m.name).replace("{params}", params).replace("{ret}", ret)
        stub = stub.replace("{collection}", collection)
        # unescape the double-brace escaping used in the dict literals
        return stub.replace("{{", "{").replace("}}", "}")
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


# ── v3 helpers ───────────────────────────────────────────────────────────────

_LOADING_KEYWORDS = frozenset({"loading", "sending", "verifying", "resending", "fetching", "submitting", "saving"})
_ERROR_KEYWORDS = frozenset({"error", "message", "msg", "failure"})


def _find_loading_state_field(state_fields: list[StateField]) -> str:
    """Return the name of the first boolean loading field, or 'isLoading' as fallback."""
    for f in state_fields:
        if f.type == "Boolean" and any(kw in f.name.lower() for kw in _LOADING_KEYWORDS):
            return f.name
    for f in state_fields:
        if f.type == "Boolean":
            return f.name
    return "isLoading"


def _find_error_state_field(state_fields: list[StateField]) -> str:
    """Return the name of the first nullable String error field, or 'errorMessage' as fallback."""
    for f in state_fields:
        if f.nullable and f.type in {"String", "String?"}:
            if any(kw in f.name.lower() for kw in _ERROR_KEYWORDS):
                return f.name
    for f in state_fields:
        if f.nullable:
            return f.name
    return "errorMessage"


def _build_saved_state_initial(nav_args: list[str]) -> str:
    """Build the mapOf(...) contents for SavedStateHandle in tests, e.g. '"phone" to ""'."""
    pairs = []
    for arg in nav_args:
        parts = arg.split(":")
        if len(parts) != 2:
            continue
        name = parts[0].strip()
        type_ = parts[1].strip().rstrip("?")
        default = _DEFAULT_VALUE_MAP.get(type_, '""')
        pairs.append(f'"{name}" to {default}')
    return ", ".join(pairs) if pairs else '"key" to ""'


def _infer_repo_private_fields(methods: list[Any]) -> list[dict]:
    """Infer ViewModel/Repository private fields needed by firebase_pattern methods."""
    fields: list[dict] = []
    needs_verification_id = any(
        getattr(m, "firebase_pattern", None) in {"phone_auth", "credential_sign_in"}
        for m in methods
    )
    if needs_verification_id:
        fields.append({"name": "savedVerificationId", "type": "String", "default": '""', "volatile": True})
    return fields


def _infer_firebase_pattern_imports(methods: list[Any]) -> list[str]:
    """Collect extra imports required by firebase_pattern stubs."""
    imports: list[str] = []
    for m in methods:
        pattern = getattr(m, "firebase_pattern", None)
        if pattern and pattern in _FIREBASE_PATTERN_IMPORTS:
            imports.extend(_FIREBASE_PATTERN_IMPORTS[pattern])
    return imports


# ── UI component renderer ─────────────────────────────────────────────────────

_UI_COMPONENT_EXTRA_IMPORTS: dict[str, list[str]] = {
    "OtpDigitRow": [
        "androidx.compose.ui.focus.FocusRequester",
        "androidx.compose.ui.focus.focusRequester",
        "androidx.compose.foundation.layout.Row",
        "androidx.compose.foundation.layout.Arrangement",
        "androidx.compose.foundation.text.KeyboardOptions",
        "androidx.compose.ui.text.input.KeyboardType",
        "androidx.compose.ui.text.style.TextAlign",
        "androidx.compose.runtime.remember",
    ],
    "OutlinedTextField": [
        "androidx.compose.material3.OutlinedTextField",
        "androidx.compose.foundation.text.KeyboardOptions",
        "androidx.compose.ui.text.input.KeyboardType",
    ],
    "Button": ["androidx.compose.material3.Button"],
    "TextButton": ["androidx.compose.material3.TextButton"],
    "ErrorText": ["androidx.compose.material3.Text"],
    "OfflineBanner": [
        "androidx.compose.material3.Card",
        "androidx.compose.material3.CardDefaults",
    ],
    "TimerText": ["androidx.compose.material3.Text", "androidx.compose.material3.TextButton"],
}

_COMMON_SCAFFOLD_IMPORTS = [
    "androidx.compose.foundation.layout.Arrangement",
    "androidx.compose.foundation.layout.Column",
    "androidx.compose.foundation.layout.Spacer",
    "androidx.compose.foundation.layout.fillMaxSize",
    "androidx.compose.foundation.layout.fillMaxWidth",
    "androidx.compose.foundation.layout.height",
    "androidx.compose.foundation.layout.padding",
    "androidx.compose.foundation.layout.size",
    "androidx.compose.foundation.layout.imePadding",
    "androidx.compose.material3.CircularProgressIndicator",
    "androidx.compose.material3.MaterialTheme",
    "androidx.compose.material3.Text",
    "androidx.compose.ui.Alignment",
    "androidx.compose.ui.Modifier",
    "androidx.compose.ui.unit.dp",
]


def _screen_component_imports(components: list[Any]) -> list[str]:
    if not components:
        return []
    imports = list(_COMMON_SCAFFOLD_IMPORTS)
    for c in components:
        imports.extend(_UI_COMPONENT_EXTRA_IMPORTS.get(c.type, []))
    return sorted(set(imports))


def _render_ui_components(components: list[Any]) -> str:
    """Render UiComponent list to a Kotlin Column body string."""
    if not components:
        return "    // TODO: implement screen content"
    lines: list[str] = [
        "    Column(",
        "        modifier = Modifier.fillMaxSize().padding(horizontal = 24.dp).imePadding(),",
        "        verticalArrangement = Arrangement.Center,",
        "        horizontalAlignment = Alignment.CenterHorizontally,",
        "    ) {",
    ]
    for c in components:
        lines.extend(_render_component(c))
        lines.append("        Spacer(modifier = Modifier.height(16.dp))")
    lines.append("    }")
    return "\n".join(lines)


def _render_component(c: Any) -> list[str]:  # noqa: PLR0911
    t = c.type
    if t == "OutlinedTextField":
        return _render_text_field(c)
    if t == "Button":
        return _render_button(c)
    if t == "TextButton":
        return _render_text_button(c)
    if t == "ErrorText":
        return _render_error_text(c)
    if t == "OtpDigitRow":
        return _render_otp_digit_row(c)
    if t == "TimerText":
        return _render_timer_text(c)
    if t == "OfflineBanner":
        return _render_offline_banner(c)
    return [f"        // TODO: render {t}"]


def _render_text_field(c: Any) -> list[str]:
    bound = c.bound_to or "value"
    action = c.action or "on${bound.capitalize()}Changed"
    label = c.label or bound
    lines = [
        "        OutlinedTextField(",
        f'            value = uiState.{bound},',
        f"            onValueChange = {action},",
        f'            label = {{ Text("{label}") }},',
    ]
    if c.prefix:
        lines.append(f'            prefix = {{ Text("{c.prefix}") }},')
    lines += [
        "            singleLine = true,",
        "            modifier = Modifier.fillMaxWidth(),",
        "        )",
    ]
    return lines


def _render_button(c: Any) -> list[str]:
    action = c.action or "onClick"
    label = c.label or "Submit"
    lines = ["        Button("]
    lines.append(f"            onClick = {action},")
    if c.enabled_when:
        lines.append(f"            enabled = {c.enabled_when},")
    lines.append("            modifier = Modifier.fillMaxWidth(),")
    lines.append("        ) {")
    if c.loading_when:
        lines += [
            f"            if (uiState.{c.loading_when}) {{",
            "                CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)",
            "            } else {",
            f'                Text("{label}")',
            "            }",
        ]
    else:
        lines.append(f'            Text("{label}")')
    lines.append("        }")
    return lines


def _render_text_button(c: Any) -> list[str]:
    action = c.action or "onClick"
    label = c.label or "Action"
    enabled = f"enabled = !uiState.{c.loading_when}, " if c.loading_when else ""
    return [f'        TextButton(onClick = {action}, {enabled}) {{ Text("{label}") }}']


def _render_error_text(c: Any) -> list[str]:
    field = c.error_field or "errorMessage"
    lines = [
        f"        uiState.{field}?.let {{ msg ->",
        "            Text(text = msg, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)",
    ]
    if c.retry_action:
        lines.append(f'            TextButton(onClick = {c.retry_action}) {{ Text("Retry") }}')
    lines.append("        }")
    return lines


def _render_otp_digit_row(c: Any) -> list[str]:
    count = c.count or 6
    bound = c.bound_to or "digits"
    action = c.action or "onOtpChanged"
    return [
        f"        val focusRequesters = remember {{ List({count}) {{ FocusRequester() }} }}",
        "        Row(",
        "            horizontalArrangement = Arrangement.spacedBy(8.dp),",
        "            modifier = Modifier.fillMaxWidth(),",
        "        ) {",
        f"            uiState.{bound}.forEachIndexed {{ index, digit ->",
        "                OutlinedTextField(",
        "                    value = digit,",
        "                    onValueChange = { raw ->",
        "                        val filtered = raw.filter { it.isDigit() }.take(1)",
        f"                        val updated = uiState.{bound}.toMutableList().also {{ it[index] = filtered }}",
        f"                        {action}(updated)",
        f"                        if (filtered.isNotEmpty() && index < {count - 1}) focusRequesters[index + 1].requestFocus()",
        "                    },",
        "                    singleLine = true,",
        "                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),",
        "                    textStyle = MaterialTheme.typography.titleLarge.copy(textAlign = TextAlign.Center),",
        "                    modifier = Modifier.weight(1f).focusRequester(focusRequesters[index]),",
        "                )",
        "            }",
        "        }",
    ]


def _render_timer_text(c: Any) -> list[str]:
    field = c.bound_to or "resendSecondsRemaining"
    action = c.action or "onResendClicked"
    loading = c.loading_when or "isResending"
    return [
        f"        if (uiState.{field} > 0) {{",
        f'            Text("Resend OTP in ${{uiState.{field}}}s", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)',
        "        } else {",
        f"            TextButton(onClick = {action}, enabled = !uiState.{loading}) {{",
        '                Text("Resend OTP")',
        "            }",
        "        }",
    ]


def _render_offline_banner(c: Any) -> list[str]:
    field = c.bound_to or "isOfflineMode"
    label = c.label or "You are offline. Please check your connection."
    return [
        f"        if (uiState.{field}) {{",
        "            Card(",
        "                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),",
        "                modifier = Modifier.fillMaxWidth(),",
        "            ) {",
        f'                Text("{label}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onErrorContainer, modifier = Modifier.padding(12.dp))',
        "            }",
        "        }",
    ]
