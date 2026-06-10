"""LLM adapter abstraction for Phase 4 code generation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class FunctionSpec:
    name: str
    params: list[str] = field(default_factory=list)
    returns: str = "Unit"
    business_rule: str | None = None


@dataclass
class FillFunctionsSpec:
    functions: list[FunctionSpec]
    architecture: str
    package_name: str
    state_class_name: str
    dependencies: list[str] = field(default_factory=list)
    business_rules: list[str] = field(default_factory=list)
    violations_to_avoid: list[str] = field(default_factory=list)
    ui_state_type: str = "sealed_class"  # "sealed_class" | "data_class"


class LLMAdapter(Protocol):
    async def fill_functions(self, spec: FillFunctionsSpec) -> str: ...
    async def complete(self, prompt: str) -> str: ...


class NullAdapter:
    """Returns TODO stubs when no API key is configured (graceful degradation)."""

    async def fill_functions(self, spec: FillFunctionsSpec) -> str:
        stubs: list[str] = []
        for fn in spec.functions:
            params = ", ".join(fn.params)
            stubs.append(
                f"    fun {fn.name}({params}): {fn.returns} {{\n"
                f"        // TODO: implement\n"
                f"    }}"
            )
        return "\n\n".join(stubs) if stubs else "    // TODO: implement"

    async def complete(self, prompt: str) -> str:
        return prompt


def create_adapter() -> LLMAdapter:
    """Return the best available LLM adapter.

    Detection order (first match wins):
      1. claude  CLI — Claude Code installed and logged in (no API key needed)
      2. gemini  CLI — Google Gemini CLI
      3. llm     CLI — Simon Willison's universal LLM CLI
      4. ollama  CLI — local models, fully offline
      5. ANTHROPIC_API_KEY env var → direct Anthropic API
      6. OPENAI_API_KEY    env var → direct OpenAI API
      7. NullAdapter       → TODO stubs (no LLM available)
    """
    from project_brain.llm.cli_adapter import detect_cli_adapter

    cli = detect_cli_adapter()
    if cli is not None:
        return cli  # type: ignore[return-value]

    if os.environ.get("ANTHROPIC_API_KEY"):
        from project_brain.llm.claude import ClaudeAdapter

        return ClaudeAdapter()
    if os.environ.get("OPENAI_API_KEY"):
        from project_brain.llm.openai import OpenAIAdapter

        return OpenAIAdapter()
    return NullAdapter()


def describe_adapter(adapter: LLMAdapter) -> str:
    """Human-readable description of the active adapter (for `brain doctor`)."""
    name = type(adapter).__name__
    if hasattr(adapter, "__repr__"):
        return repr(adapter)
    return name
