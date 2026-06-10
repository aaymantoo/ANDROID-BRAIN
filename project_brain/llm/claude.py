"""Claude LLM adapter using the Anthropic Messages API."""

from __future__ import annotations

import os
from pathlib import Path

import httpx

from project_brain.llm.adapter import FillFunctionsSpec


_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "function_fill_v1.txt"
_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4-5-20251001"


class ClaudeAdapter:
    def __init__(self, api_key: str | None = None, model: str = _MODEL) -> None:
        self._api_key = api_key or os.environ["ANTHROPIC_API_KEY"]
        self._model = model
        self._prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")

    async def complete(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                _API_URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 8192,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            return response.json()["content"][0]["text"].strip()

    async def fill_functions(self, spec: FillFunctionsSpec) -> str:
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
        prompt = self._prompt_template.format(
            architecture=spec.architecture,
            package_name=spec.package_name,
            state_class_name=spec.state_class_name,
            dependencies="\n".join(spec.dependencies) or "none",
            business_rules="\n".join(spec.business_rules) or "none",
            functions_spec=functions_spec + violation_note,
        )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                _API_URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 2048,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            return response.json()["content"][0]["text"].strip()
