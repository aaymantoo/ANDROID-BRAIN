"""Zero-LLM function body generator that derives implementations from brain spec fields.

Covers ~80-90% of ViewModel function bodies using:
  - state_updates  → .update { it.copy(...) } patterns
  - events_fired   → _events.trySend(EventClass.Name(...))
  - concurrent     → mutex.withLock { ... }
  - use_cases      → useCase(params) in viewModelScope.launch
  - returns Flow   → direct delegation to repository

LLM is only needed when business_rule contains complex validation logic
that cannot be pattern-matched from structured brain fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from project_brain.llm.adapter import FillFunctionsSpec


_LOADING_PATTERN = re.compile(r"^is[A-Z]|Loading$|Sending$|Verifying$|Fetching$")
_ERROR_FIELD_PATTERN = re.compile(r"^error[A-Z]?|[Ee]rrorMessage$")
_INDENT = "    "


@dataclass
class FilledBody:
    function_name: str
    body: str
    confidence: float


def _camel_to_field(name: str) -> str:
    return name[0].lower() + name[1:]


def _find_loading_field(state_updates: list[str]) -> str | None:
    return next((f for f in state_updates if _LOADING_PATTERN.match(f)), None)


def _find_error_field(state_updates: list[str]) -> str | None:
    return next((f for f in state_updates if _ERROR_FIELD_PATTERN.match(f)), None)


def _build_simple_state_update(state_updates: list[str], params: list[str], fn_name: str) -> str:
    """Pure state mutation: no async, no events. Direct .update { it.copy(...) }."""
    if not state_updates:
        return f"{_INDENT * 2}// TODO: implement"
    assignments = []
    param_names = {p.split(":")[0].strip() for p in params}
    for field in state_updates:
        if field in param_names:
            assignments.append(f"{field} = {field}")
        elif _ERROR_FIELD_PATTERN.match(field):
            assignments.append(f"{field} = null")
        elif _LOADING_PATTERN.match(field):
            assignments.append(f"{field} = false")
        else:
            assignments.append(f"{field} = {_camel_to_field(field)}")
    if len(assignments) == 1:
        return f"{_INDENT * 2}_uiState.update {{ it.copy({assignments[0]}) }}"
    inner = ",\n".join(f"{_INDENT * 3}{a}" for a in assignments)
    return f"{_INDENT * 2}_uiState.update {{\n{_INDENT * 3}it.copy(\n{inner},\n{_INDENT * 3})\n{_INDENT * 2}}}"


def _build_async_body(
    fn_name: str,
    params: list[str],
    state_updates: list[str],
    events_fired: list[str],
    event_class: str | None,
    use_case_name: str | None,
    concurrent: bool,
    ui_state_class: str,
) -> tuple[str, float]:
    """Async viewModelScope.launch body with loading/error/event pattern."""
    loading_field = _find_loading_field(state_updates)
    error_field = _find_error_field(state_updates)

    param_names = [p.split(":")[0].strip() for p in params]
    use_case_call_params = ", ".join(f"uiState.value.{p}" if p not in {p.split(":")[0].strip() for p in params} else p for p in param_names)
    # simplify: pass raw params directly
    use_case_call_params = ", ".join(param_names)

    lines: list[str] = []
    base = _INDENT * 2

    if concurrent:
        lines.append(f"{base}viewModelScope.launch {{")
        lines.append(f"{base}    _mutex.withLock {{")
        inner = "        "
    else:
        lines.append(f"{base}viewModelScope.launch {{")
        inner = "    "

    if loading_field:
        lines.append(f"{base}{inner}_uiState.update {{ it.copy({loading_field} = true{', ' + error_field + ' = null' if error_field else ''}) }}")

    if use_case_name:
        uc_var = _camel_to_field(use_case_name)
        call = f"{base}{inner}runCatching {{ {uc_var}({use_case_call_params}) }}"
        lines.append(call)
        success_parts = []
        if loading_field:
            success_parts.append(f"{loading_field} = false")
        if events_fired and event_class:
            for ev in events_fired:
                ev_args = ""
                if param_names:
                    ev_args = f"uiState.value.{param_names[0]}"
                lines_success = "".join(f"\n{base}{inner}    _events.trySend({event_class}.{ev}({ev_args}))" for ev in events_fired if event_class)
                break
            success_block = (
                f"\n{base}{inner}    .onSuccess {{"
                + ("".join(f"\n{base}{inner}        _uiState.update {{ it.copy({', '.join(success_parts)}) }}" if success_parts else ""))
                + ("".join(f"\n{base}{inner}        _events.trySend({event_class}.{ev}({', '.join(param_names)}))" for ev in events_fired) if event_class else "")
                + f"\n{base}{inner}    }}"
                + f"\n{base}{inner}    .onFailure {{ e ->"
                + (f"\n{base}{inner}        _uiState.update {{ it.copy({', '.join(f + ' = false' if _LOADING_PATTERN.match(f) else f + ' = e.message ?: \"Unknown error\"' for f in state_updates if f == loading_field or f == error_field)}) }}" if (loading_field or error_field) else f"\n{base}{inner}        _uiState.update {{ it.copy(errorMessage = e.message ?: \"Unknown error\") }}")
                + f"\n{base}{inner}    }}"
            )
            lines[-1] = lines[-1] + success_block
        else:
            lines[-1] = (
                lines[-1]
                + f"\n{base}{inner}    .onSuccess {{"
                + (f"\n{base}{inner}        _uiState.update {{ it.copy({', '.join(success_parts)}) }}" if success_parts else f"\n{base}{inner}        // success")
                + f"\n{base}{inner}    }}"
                + f"\n{base}{inner}    .onFailure {{ e ->"
                + (f"\n{base}{inner}        _uiState.update {{ it.copy({error_field} = e.message ?: \"Unknown error\"{', ' + loading_field + ' = false' if loading_field else ''}) }}" if error_field else f"\n{base}{inner}        _uiState.update {{ it.copy(errorMessage = e.message ?: \"Unknown error\") }}")
                + f"\n{base}{inner}    }}"
            )
    else:
        # no use case — direct state update
        if loading_field:
            other = [f for f in state_updates if f != loading_field]
            lines.append(f"{base}{inner}_uiState.update {{ it.copy({', '.join([loading_field + ' = false'] + [f + ' = null' if _ERROR_FIELD_PATTERN.match(f) else f + ' = ' + _camel_to_field(f) for f in other])}) }}")
        for ev in events_fired:
            if event_class:
                lines.append(f"{base}{inner}_events.trySend({event_class}.{ev}({', '.join(param_names)}))")

    if concurrent:
        lines.append(f"{base}    }}")
    lines.append(f"{base}}}")

    body = "\n".join(lines)
    confidence = 0.80
    if not use_case_name and not events_fired:
        confidence = 0.55
    return body, confidence


class DeterministicFunctionBodyGenerator:
    """Generate Kotlin function bodies deterministically from brain spec fields.

    Returns (filled_bodies_string, confidence) where confidence is 0.0-1.0.
    Confidence >= 0.75 means LLM call can be skipped.
    """

    def fill(self, spec: FillFunctionsSpec, extra_context: dict[str, Any] | None = None) -> tuple[str, float]:
        ctx = extra_context or {}
        event_class = ctx.get("event_class")
        ui_state_class = spec.state_class_name

        # Infer use cases from dependencies list (type names ending in UseCase)
        use_cases = {
            dep.split(":")[1].strip() if ":" in dep else dep
            for dep in spec.dependencies
            if dep.strip().endswith("UseCase")
        }

        bodies: list[FilledBody] = []
        total_confidence = 0.0

        for fn in spec.functions:
            body, confidence = self._fill_one(fn, use_cases, event_class, ui_state_class, spec.ui_state_type)
            total_confidence += confidence
            bodies.append(FilledBody(fn.name, body, confidence))

        avg_confidence = total_confidence / len(bodies) if bodies else 0.0

        result = "\n\n".join(
            f"{_INDENT}fun {b.function_name}({self._params_str(spec, b.function_name)})"
            f"{self._return_str(spec, b.function_name)} {{\n{b.body}\n{_INDENT}}}"
            for b in bodies
        )
        return result, avg_confidence

    def _fill_one(
        self,
        fn: Any,
        use_cases: set[str],
        event_class: str | None,
        ui_state_class: str,
        ui_state_type: str,
    ) -> tuple[str, float]:
        params = list(fn.params) if fn.params else []
        state_updates = list(fn.state_updates) if fn.state_updates else []
        events_fired = list(fn.events_fired) if fn.events_fired else []
        concurrent = bool(fn.concurrent)
        returns = fn.returns or "Unit"

        # Flow return — direct delegation
        if returns.startswith("Flow<"):
            body = f"{_INDENT * 2}return repository.{_camel_to_field(fn.name)}({', '.join(p.split(':')[0].strip() for p in params)})"
            return body, 0.85

        # Simple synchronous state update (no async, no events)
        has_loading = any(_LOADING_PATTERN.match(f) for f in state_updates)
        matched_uc = next((uc for uc in use_cases if any(
            keyword in fn.name.lower() for keyword in [uc.replace("UseCase", "").lower()[:4]]
        )), None)
        is_async = has_loading or bool(events_fired) or matched_uc is not None

        if not is_async and state_updates:
            body = _build_simple_state_update(state_updates, params, fn.name)
            return body, 0.90

        if is_async:
            body, conf = _build_async_body(
                fn.name, params, state_updates, events_fired, event_class, matched_uc, concurrent, ui_state_class
            )
            return body, conf

        # Fallback: cannot determine pattern
        return f"{_INDENT * 2}// TODO: implement", 0.0

    def _params_str(self, spec: FillFunctionsSpec, fn_name: str) -> str:
        fn = next((f for f in spec.functions if f.name == fn_name), None)
        if not fn or not fn.params:
            return ""
        return ", ".join(fn.params)

    def _return_str(self, spec: FillFunctionsSpec, fn_name: str) -> str:
        fn = next((f for f in spec.functions if f.name == fn_name), None)
        ret = (fn.returns if fn else None) or "Unit"
        return f": {ret}" if ret != "Unit" else ""
