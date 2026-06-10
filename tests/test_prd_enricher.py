"""Tests for Phase 0B PRD Enrichment Engine."""

from __future__ import annotations

import asyncio
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock

from project_brain.generators.prd_enricher import PRDEnricher, _detect_patterns
from project_brain.llm.adapter import NullAdapter


_SPARSE_PRD = """\
# My App PRD

## 1. Project Overview
Package: com.example.app

## 2. User Roles
| id | name | description | app_module |
|---|---|---|---|
| user | User | Regular user | app |

## 3. Features & Screens
- Screen: HomeScreen
- Route: home
- ViewModel: HomeViewModel
- Repository: DataRepository

## 5. State Machines
### AppState
- States: LOADING, READY, ERROR
- Transition: LOADING -> READY
- Transition: READY -> ERROR

## 6. Firestore Schema
### Collection: /items/{id}
- Fields: id, name, createdAt

## 7. Business Rules
- BR001: Must validate input before saving.

## 9. Phase Breakdown
### Phase 1
- Screens: HomeScreen
- Completion criteria: home screen shows list

## 4. Data Models
### Item
| name | type | nullable |
|---|---|---|
| id | String | false |
| name | String | false |
"""

_RICH_PRD_EXCERPT = """\
data class HomeUiState(
    val isLoading: Boolean = false,
    val error: HomeError? = null
)

Channel<HomeEvent>(Channel.BUFFERED)

Mutex

SavedStateHandle

sealed class HomeError

Result<Unit>

runCatching

callbackFlow

tasks.await()

DataStore

collectAsStateWithLifecycle

LaunchedEffect

@Singleton

@Keep
"""


class TestDetectPatterns(TestCase):
    def test_detects_data_class_uistate(self):
        text = "data class HomeUiState(val isLoading: Boolean = false)"
        patterns = _detect_patterns(text)
        self.assertIn("P01:data_class_uistate", patterns)

    def test_detects_channel_events(self):
        text = "Channel<HomeEvent>(Channel.BUFFERED)"
        patterns = _detect_patterns(text)
        self.assertIn("P02:channel_events", patterns)

    def test_detects_mutex(self):
        text = "Mutex() ... withLock {}"
        patterns = _detect_patterns(text)
        self.assertIn("P04:mutex", patterns)

    def test_detects_result_wrapper(self):
        text = "Result<Unit> ... runCatching {}"
        patterns = _detect_patterns(text)
        self.assertIn("P07:result_wrapper", patterns)

    def test_detects_keep_annotation(self):
        text = "@Keep\ndata class Item(...)"
        patterns = _detect_patterns(text)
        self.assertIn("P18:keep", patterns)

    def test_detects_all_patterns_in_rich_excerpt(self):
        patterns = _detect_patterns(_RICH_PRD_EXCERPT)
        self.assertGreaterEqual(len(patterns), 10, f"Only detected: {patterns}")


class TestNullAdapterEnricher(TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_null_enricher_returns_result(self):
        enricher = PRDEnricher(llm=NullAdapter())
        result = self._run(enricher.enrich(_SPARSE_PRD))
        self.assertIsNotNone(result.enriched_prd)
        self.assertFalse(result.used_llm)

    def test_null_enricher_preserves_original_prd(self):
        enricher = PRDEnricher(llm=NullAdapter())
        result = self._run(enricher.enrich(_SPARSE_PRD))
        self.assertIn("My App PRD", result.enriched_prd)

    def test_null_enricher_contains_gap_guidance(self):
        enricher = PRDEnricher(llm=NullAdapter())
        result = self._run(enricher.enrich(_SPARSE_PRD))
        self.assertIn("[UNKNOWN", result.enriched_prd)

    def test_enrichment_result_summary(self):
        enricher = PRDEnricher(llm=NullAdapter())
        result = self._run(enricher.enrich(_SPARSE_PRD))
        summary = result.summary()
        self.assertIn("score", summary)
        self.assertIn("used_llm", summary)
        self.assertFalse(summary["used_llm"])


class TestMockedLLMEnricher(TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def _make_mock_llm(self, response: str):
        mock = MagicMock()
        mock.complete = AsyncMock(return_value=response)
        mock.fill_functions = AsyncMock(return_value="    // TODO: implement")
        return mock

    def test_llm_enricher_returns_llm_response(self):
        mock_llm = self._make_mock_llm(_RICH_PRD_EXCERPT)
        enricher = PRDEnricher(llm=mock_llm)
        result = self._run(enricher.enrich(_SPARSE_PRD))
        self.assertEqual(result.enriched_prd, _RICH_PRD_EXCERPT)
        self.assertTrue(result.used_llm)

    def test_llm_enricher_detects_patterns(self):
        mock_llm = self._make_mock_llm(_RICH_PRD_EXCERPT)
        enricher = PRDEnricher(llm=mock_llm)
        result = self._run(enricher.enrich(_SPARSE_PRD))
        self.assertGreater(len(result.patterns_applied), 5)

    def test_llm_enricher_counts_inferences(self):
        enriched_with_inferences = "# Test\n[INFERRED] foo\n[INFERRED] bar\n[UNKNOWN] baz"
        mock_llm = self._make_mock_llm(enriched_with_inferences)
        enricher = PRDEnricher(llm=mock_llm)
        result = self._run(enricher.enrich(_SPARSE_PRD))
        self.assertEqual(result.inferences_count, 2)
        self.assertEqual(result.unknowns_count, 1)

    def test_ready_for_brain_requires_score_90(self):
        mock_llm = self._make_mock_llm(_SPARSE_PRD)
        enricher = PRDEnricher(llm=mock_llm)
        result = self._run(enricher.enrich(_SPARSE_PRD))
        if result.score >= 90:
            self.assertTrue(result.ready_for_brain)
        else:
            self.assertFalse(result.ready_for_brain)

    def test_llm_complete_called_once_for_basic_enrichment(self):
        mock_llm = self._make_mock_llm(_RICH_PRD_EXCERPT)
        enricher = PRDEnricher(llm=mock_llm)
        self._run(enricher.enrich(_SPARSE_PRD, interactive=False))
        mock_llm.complete.assert_called_once()


class TestV2TemplateEngineRouting(TestCase):
    """Verify orchestrator routes to v2 when brain has enriched ViewModel data."""

    def test_selects_v2_engine_for_enriched_brain(self):
        from project_brain.brain.schema import (
            Meta, ProjectBrain, ViewModel, StateField,
        )
        from project_brain.generators.code_generation import GenerationOrchestrator

        brain = ProjectBrain(
            meta=Meta(project_name="test", entry_point="prd"),
            viewmodels=[
                ViewModel(
                    id="TestViewModel",
                    ui_state_type="data_class",
                    state_fields=[StateField(name="isLoading", type="Boolean", default="false")],
                )
            ],
        )
        from project_brain.engines.template_engine import TemplateEngineV2
        engine = GenerationOrchestrator._select_engine(brain)
        self.assertIsInstance(engine, TemplateEngineV2)

    def test_selects_v1_engine_for_plain_brain(self):
        from project_brain.brain.schema import Meta, ProjectBrain, ViewModel
        from project_brain.engines.template_engine import TemplateEngine
        from project_brain.generators.code_generation import GenerationOrchestrator

        brain = ProjectBrain(
            meta=Meta(project_name="test", entry_point="prd"),
            viewmodels=[ViewModel(id="TestViewModel")],
        )
        engine = GenerationOrchestrator._select_engine(brain)
        self.assertIsInstance(engine, TemplateEngine)
        from project_brain.engines.template_engine import TemplateEngineV2
        self.assertNotIsInstance(engine, TemplateEngineV2)
