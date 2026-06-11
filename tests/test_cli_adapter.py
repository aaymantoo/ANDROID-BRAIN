"""Tests for CLI-based LLM adapters."""

from __future__ import annotations

import asyncio
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from project_brain.llm.adapter import NullAdapter, create_adapter, describe_adapter
from project_brain.llm.cli_adapter import (
    ClaudeCodeCLIAdapter,
    GeminiCLIAdapter,
    LLMCLIAdapter,
    OllamaCLIAdapter,
    detect_cli_adapter,
    list_available_cli_adapters,
)


class TestCLIAdapterDetection(TestCase):
    def test_claude_code_cli_command(self):
        self.assertEqual(ClaudeCodeCLIAdapter.CLI_COMMAND, "claude")

    def test_gemini_cli_command(self):
        self.assertEqual(GeminiCLIAdapter.CLI_COMMAND, "gemini")

    def test_llm_cli_command(self):
        self.assertEqual(LLMCLIAdapter.CLI_COMMAND, "llm")

    def test_ollama_cli_command(self):
        self.assertEqual(OllamaCLIAdapter.CLI_COMMAND, "ollama")

    def test_is_available_returns_false_for_fake_command(self):
        class FakeAdapter(ClaudeCodeCLIAdapter):
            CLI_COMMAND = "__nonexistent_binary_brain_test__"
        self.assertFalse(FakeAdapter.is_available())

    def test_detect_returns_none_when_nothing_available(self):
        with patch("shutil.which", return_value=None):
            result = detect_cli_adapter()
            self.assertIsNone(result)

    def test_detect_returns_claude_when_available(self):
        def fake_which(cmd):
            return "/usr/local/bin/claude" if cmd == "claude" else None
        with patch("shutil.which", side_effect=fake_which):
            result = detect_cli_adapter()
            self.assertIsInstance(result, ClaudeCodeCLIAdapter)

    def test_detect_prefers_claude_over_gemini(self):
        def fake_which(cmd):
            return f"/usr/local/bin/{cmd}" if cmd in ("claude", "gemini") else None
        with patch("shutil.which", side_effect=fake_which):
            result = detect_cli_adapter()
            self.assertIsInstance(result, ClaudeCodeCLIAdapter)

    def test_detect_falls_back_to_gemini_when_no_claude(self):
        def fake_which(cmd):
            return "/usr/local/bin/gemini" if cmd == "gemini" else None
        with patch("shutil.which", side_effect=fake_which):
            result = detect_cli_adapter()
            self.assertIsInstance(result, GeminiCLIAdapter)

    def test_detect_falls_back_to_ollama(self):
        def fake_which(cmd):
            return "/usr/local/bin/ollama" if cmd == "ollama" else None
        with patch("shutil.which", side_effect=fake_which):
            result = detect_cli_adapter()
            self.assertIsInstance(result, OllamaCLIAdapter)

    def test_list_available_empty_when_nothing_installed(self):
        with patch("shutil.which", return_value=None):
            result = list_available_cli_adapters()
            self.assertEqual(result, [])

    def test_list_available_shows_installed(self):
        def fake_which(cmd):
            return "/usr/local/bin/claude" if cmd == "claude" else None
        with patch("shutil.which", side_effect=fake_which):
            result = list_available_cli_adapters()
            self.assertEqual(len(result), 1)
            self.assertIn("claude", result[0])


class TestCreateAdapterPriority(TestCase):
    def test_cli_adapter_takes_priority_over_api_key(self):
        """Claude Code CLI wins over ANTHROPIC_API_KEY — Pro subscription needs no API key."""
        def fake_which(cmd):
            return "/usr/local/bin/claude" if cmd == "claude" else None

        import os
        original = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-key"
        try:
            with patch("shutil.which", side_effect=fake_which):
                adapter = create_adapter()
                self.assertIsInstance(adapter, ClaudeCodeCLIAdapter)
        finally:
            if original is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = original

    def test_falls_back_to_null_when_nothing_available(self):
        import os
        with patch("shutil.which", return_value=None):
            env_backup = {k: os.environ.pop(k, None) for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
            try:
                adapter = create_adapter()
                self.assertIsInstance(adapter, NullAdapter)
            finally:
                for k, v in env_backup.items():
                    if v is not None:
                        os.environ[k] = v

    def test_describe_adapter_null(self):
        result = describe_adapter(NullAdapter())
        self.assertIn("NullAdapter", result)

    def test_describe_adapter_cli(self):
        result = describe_adapter(ClaudeCodeCLIAdapter())
        self.assertIn("claude", result.lower())


class TestLLMCLIAdapterArgs(TestCase):
    def test_llm_cli_no_model(self):
        adapter = LLMCLIAdapter()
        self.assertEqual(adapter._args(), ["llm"])

    def test_llm_cli_with_model(self):
        adapter = LLMCLIAdapter(model="claude-3-5-sonnet")
        self.assertEqual(adapter._args(), ["llm", "-m", "claude-3-5-sonnet"])

    def test_ollama_default_model(self):
        adapter = OllamaCLIAdapter()
        self.assertIn("llama3.2", adapter._args())

    def test_ollama_custom_model(self):
        adapter = OllamaCLIAdapter(model="mistral")
        self.assertIn("mistral", adapter._args())

    def test_claude_args(self):
        adapter = ClaudeCodeCLIAdapter()
        self.assertIn("--print", adapter._args())
