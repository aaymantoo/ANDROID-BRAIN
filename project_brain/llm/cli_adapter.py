"""CLI-based LLM adapters — use locally installed AI tools instead of API keys.

Priority order in create_adapter():
  1. claude   — Claude Code CLI  (user already authenticated, free with subscription)
  2. gemini   — Google Gemini CLI
  3. llm      — Simon Willison's universal LLM CLI (works with any model)
  4. ollama   — local models, fully free, no auth needed
  5. ANTHROPIC_API_KEY → ClaudeAdapter
  6. OPENAI_API_KEY    → OpenAIAdapter
  7. NullAdapter       — TODO stubs (no LLM available)

All CLI adapters use asyncio subprocess with stdin pipe — no shell=True, no injection risk,
no argument-length limits for long prompts.
"""

from __future__ import annotations

import asyncio
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from project_brain.llm.adapter import FillFunctionsSpec


_PROMPT_PATH_V1 = Path(__file__).parent.parent.parent / "prompts" / "function_fill_v1.txt"
_PROMPT_PATH_V2 = Path(__file__).parent.parent.parent / "prompts" / "function_fill_v2.txt"
_CLI_TIMEOUT = 180  # seconds — CLI calls are slower than direct API
_DETERMINISTIC_CONFIDENCE_THRESHOLD = 0.75  # skip LLM when deterministic confidence >= this


class CLIAdapter(ABC):
    """Subprocess-based adapter. Subclasses declare CLI_COMMAND and _args()."""

    CLI_COMMAND: str = ""

    # ── Public interface ────────────────────────────────────────────

    @classmethod
    def is_available(cls) -> bool:
        return bool(shutil.which(cls.CLI_COMMAND))

    async def complete(self, prompt: str) -> str:
        """Send prompt via stdin, return response from stdout."""
        cmd = self._args()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")),
                timeout=_CLI_TIMEOUT,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"{self.CLI_COMMAND} timed out after {_CLI_TIMEOUT}s")

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")[:600]
            raise RuntimeError(f"{self.CLI_COMMAND} exited {proc.returncode}: {err}")

        return stdout.decode("utf-8", errors="replace").strip()

    async def fill_functions(self, spec: FillFunctionsSpec) -> str:
        # Try deterministic generation first — saves LLM call for 80-90% of cases
        from project_brain.generators.deterministic_body_filler import DeterministicFunctionBodyGenerator
        det_result, confidence = DeterministicFunctionBodyGenerator().fill(spec)
        if confidence >= _DETERMINISTIC_CONFIDENCE_THRESHOLD:
            return det_result

        prompt_path = _PROMPT_PATH_V2 if spec.ui_state_type == "data_class" else _PROMPT_PATH_V1
        prompt_template = prompt_path.read_text(encoding="utf-8")
        functions_spec = "\n\n".join(
            f"fun {fn.name}({', '.join(fn.params)}): {fn.returns}"
            + (f"\n// Business rule: {fn.business_rule}" if fn.business_rule else "")
            for fn in spec.functions
        )
        violation_note = (
            "\n\nPrevious attempt had these violations — avoid them:\n"
            + "\n".join(f"- {v}" for v in spec.violations_to_avoid)
            if spec.violations_to_avoid
            else ""
        )
        prompt = prompt_template.format(
            architecture=spec.architecture,
            package_name=spec.package_name,
            state_class_name=spec.state_class_name,
            dependencies="\n".join(spec.dependencies) or "none",
            business_rules="\n".join(spec.business_rules) or "none",
            functions_spec=functions_spec + violation_note,
        )
        return await self.complete(prompt)

    # ── Subclass contract ───────────────────────────────────────────

    @abstractmethod
    def _args(self) -> list[str]:
        """Return the command + flags list. Prompt arrives via stdin."""


# ── Concrete adapters ───────────────────────────────────────────────────────


class ClaudeCodeCLIAdapter(CLIAdapter):
    """Uses the `claude` CLI (Claude Code).

    Requires Claude Code to be installed and logged in.
    No API key needed — uses the existing Claude Code session/subscription.

    Install: https://claude.ai/code
    """

    CLI_COMMAND = "claude"

    def _args(self) -> list[str]:
        # --print: non-interactive, output response to stdout and exit
        return ["claude", "--print"]

    def __repr__(self) -> str:
        return "ClaudeCodeCLIAdapter(claude --print)"


class GeminiCLIAdapter(CLIAdapter):
    """Uses the `gemini` CLI (Google Gemini).

    Install: pip install google-generativeai  (provides `gemini` entry point)
    Or: https://ai.google.dev/gemini-api/docs/quickstart
    """

    CLI_COMMAND = "gemini"

    def _args(self) -> list[str]:
        return ["gemini"]

    def __repr__(self) -> str:
        return "GeminiCLIAdapter(gemini)"


class LLMCLIAdapter(CLIAdapter):
    """Uses Simon Willison's `llm` CLI.

    Works with Claude, GPT, Gemini, Mistral, Ollama, and more via plugins.
    Install: pip install llm
    Docs:    https://llm.datasette.io
    """

    CLI_COMMAND = "llm"

    def __init__(self, model: str | None = None) -> None:
        self._model = model

    def _args(self) -> list[str]:
        args = ["llm"]
        if self._model:
            args += ["-m", self._model]
        return args

    def __repr__(self) -> str:
        model_part = f" -m {self._model}" if self._model else ""
        return f"LLMCLIAdapter(llm{model_part})"


class OllamaCLIAdapter(CLIAdapter):
    """Uses Ollama for fully local, free, offline LLM generation.

    Install: https://ollama.com
    Pull a model first: ollama pull llama3.2
    """

    CLI_COMMAND = "ollama"
    DEFAULT_MODEL = "llama3.2"

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self._model = model

    def _args(self) -> list[str]:
        return ["ollama", "run", self._model]

    def __repr__(self) -> str:
        return f"OllamaCLIAdapter(ollama run {self._model})"


# ── Detection helpers ───────────────────────────────────────────────────────


def detect_cli_adapter() -> CLIAdapter | None:
    """Return the first available CLI adapter, or None if none found."""
    candidates: list[CLIAdapter] = [
        ClaudeCodeCLIAdapter(),
        GeminiCLIAdapter(),
        LLMCLIAdapter(),
        OllamaCLIAdapter(),
    ]
    for adapter in candidates:
        if adapter.is_available():
            return adapter
    return None


def list_available_cli_adapters() -> list[str]:
    """Return names of all installed CLI adapters (for `brain doctor`)."""
    candidates = [
        ClaudeCodeCLIAdapter(),
        GeminiCLIAdapter(),
        LLMCLIAdapter(),
        OllamaCLIAdapter(),
    ]
    return [repr(a) for a in candidates if a.is_available()]
