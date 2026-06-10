"""Phase 0B: PRD Enrichment Engine.

Transforms a sparse raw PRD into a hyperspec PRD using an LLM.
The hyperspec drives the brain generator to produce enterprise-grade code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from project_brain.llm.adapter import LLMAdapter, NullAdapter, create_adapter
from project_brain.generators.prd_scorer import PRDCompletenessScorer, CompletenessScore


_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "prd_enrichment_v1.txt"
_HYPERSPEC_PATH = Path(__file__).parent.parent.parent / "templates" / "hyperspec_template.md"

_ENTERPRISE_PATTERNS = """\
P01: data class UiState (not sealed class Loading/Success/Error)
P02: Channel<Event> for one-shot navigation/snackbar events
P03: _uiState.update { it.copy(...) } for atomic mutation
P04: Mutex.withLock {} for duplicate-call guards (BR-specified)
P05: SavedStateHandle for screen parameters surviving process death
P06: sealed class FeatureError with companion fun from(Throwable)
P07: suspend fun x(): Result<T> via runCatching {} for all repository methods
P08: Flow<T> + callbackFlow { awaitClose {} } for reactive Firebase streams
P09: tasks.await() — coroutine-first Firebase, never callback-based
P10: DataStore<Preferences> not SharedPreferences
P11: collectAsStateWithLifecycle() in Composables
P12: LaunchedEffect(Unit) { events.collect {} } for one-shot event handling
P13: Navigation callbacks as lambda parameters — no NavController in ViewModel
P14: @Immutable on UiState data class
P15: XContent() private composable for stateless content layer
P16: @Singleton on all repositories
P17: Single-function use cases with operator fun invoke()
P18: @Keep on all Firestore-serialised data models
P19: @PropertyName for explicit Firestore field name mapping
P20: No-arg constructor on Firestore models for deserialisation
"""


@dataclass
class EnrichmentResult:
    raw_prd: str
    enriched_prd: str
    score: int
    score_result: CompletenessScore
    patterns_applied: list[str] = field(default_factory=list)
    inferences_count: int = 0
    unknowns_count: int = 0
    used_llm: bool = False

    @property
    def ready_for_brain(self) -> bool:
        return self.score >= 90

    def summary(self) -> dict:
        return {
            "score": self.score,
            "ready_for_brain": self.ready_for_brain,
            "patterns_applied": len(self.patterns_applied),
            "inferences": self.inferences_count,
            "unknowns": self.unknowns_count,
            "used_llm": self.used_llm,
        }


class PRDEnricher:
    """Transforms any PRD into a hyperspec PRD using LLM enrichment.

    Usage:
        enricher = PRDEnricher()
        result = await enricher.enrich(raw_prd_text)
        result.enriched_prd  # markdown hyperspec
        result.score          # 0-100, target ≥ 90
    """

    def __init__(self, llm: LLMAdapter | None = None) -> None:
        self._llm = llm or create_adapter()
        self._scorer = PRDCompletenessScorer()
        self._prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
        self._hyperspec_template = _HYPERSPEC_PATH.read_text(encoding="utf-8")

    async def enrich(
        self,
        raw_prd: str,
        interactive: bool = False,
        max_gap_fill_rounds: int = 3,
    ) -> EnrichmentResult:
        """Run the full enrichment pipeline."""

        is_null = isinstance(self._llm, NullAdapter)

        if is_null:
            enriched = self._null_enrich(raw_prd)
        else:
            enriched = await self._call_llm(raw_prd)

        score_result = self._scorer.score_text(enriched)
        patterns = _detect_patterns(enriched)
        inferences = enriched.count("[INFERRED]")
        unknowns = enriched.count("[UNKNOWN")

        result = EnrichmentResult(
            raw_prd=raw_prd,
            enriched_prd=enriched,
            score=score_result.total,
            score_result=score_result,
            patterns_applied=patterns,
            inferences_count=inferences,
            unknowns_count=unknowns,
            used_llm=not is_null,
        )

        if interactive and not is_null and not result.ready_for_brain:
            result = await self._interactive_gap_fill(result, max_gap_fill_rounds)

        return result

    async def enrich_file(
        self,
        prd_path: Path,
        output_path: Path | None = None,
        interactive: bool = False,
    ) -> EnrichmentResult:
        raw_prd = prd_path.read_text(encoding="utf-8")
        result = await self.enrich(raw_prd, interactive=interactive)

        if output_path:
            output_path.write_text(result.enriched_prd, encoding="utf-8")

        return result

    # ── Internal ──────────────────────────────────────────────────────

    async def _call_llm(self, raw_prd: str) -> str:
        prompt = (
            self._prompt_template
            .replace("{raw_prd}", raw_prd)
            .replace("{hyperspec_template}", self._hyperspec_template)
            .replace("{enterprise_patterns}", _ENTERPRISE_PATTERNS)
        )
        return await self._llm.complete(prompt)

    def _null_enrich(self, raw_prd: str) -> str:
        """When no LLM is available: preserve raw PRD and annotate gaps."""
        gap_sections = "\n\n".join([
            "## 3. Feature ViewModels [ENRICHED]",
            "[UNKNOWN — please specify: ViewModel inject dependencies, function signatures, "
            "UI state data class definition, events sealed class, concurrent guards]",
            "## 4. Repository Contracts [ENRICHED]",
            "[UNKNOWN — please specify: repository method signatures with Result<T> returns, "
            "implementation data sources]",
            "## 8. Business Rules [ENRICHED]",
            "[UNKNOWN — please specify: which class enforces each rule and exact implementation pattern]",
        ])
        return (
            f"# Enrichment Placeholder (no LLM key configured)\n\n"
            f"Run `brain enrich-prd` with ANTHROPIC_API_KEY or OPENAI_API_KEY set.\n\n"
            f"---\n\n## Original PRD\n\n{raw_prd}\n\n"
            f"---\n\n## Gaps to Fill Manually\n\n{gap_sections}"
        )

    async def _interactive_gap_fill(
        self, result: EnrichmentResult, max_rounds: int
    ) -> EnrichmentResult:
        """Ask targeted questions for missing sections and re-enrich."""
        for _round in range(max_rounds):
            if result.ready_for_brain:
                break

            gaps = [
                dim.name
                for dim in result.score_result.missing
                if dim.earned < dim.points
            ]
            if not gaps:
                break

            print(f"\nPRD Score: {result.score}/100 — missing: {', '.join(gaps)}")
            answers = []
            for gap in gaps[:3]:
                question = _gap_question(gap)
                answer = input(f"\n{question}\n> ").strip()
                if answer:
                    answers.append(f"Additional context for '{gap}': {answer}")

            if not answers:
                break

            augmented = result.enriched_prd + "\n\n## Developer Additions\n\n" + "\n\n".join(answers)
            enriched = await self._call_llm(augmented)
            score_result = self._scorer.score_text(enriched)
            result = EnrichmentResult(
                raw_prd=result.raw_prd,
                enriched_prd=enriched,
                score=score_result.total,
                score_result=score_result,
                patterns_applied=_detect_patterns(enriched),
                inferences_count=enriched.count("[INFERRED]"),
                unknowns_count=enriched.count("[UNKNOWN"),
                used_llm=True,
            )

        return result


def _detect_patterns(enriched_prd: str) -> list[str]:
    """Detect which enterprise patterns are present in the enriched PRD."""
    checks = {
        "P01:data_class_uistate": "data class" in enriched_prd and "UiState" in enriched_prd,
        "P02:channel_events": "Channel<" in enriched_prd or "Channel.BUFFERED" in enriched_prd,
        "P03:update_idiom": ".update {" in enriched_prd or "update { it.copy" in enriched_prd,
        "P04:mutex": "Mutex" in enriched_prd and "withLock" in enriched_prd,
        "P05:saved_state": "SavedStateHandle" in enriched_prd,
        "P06:sealed_error": "sealed class" in enriched_prd and "Error" in enriched_prd,
        "P07:result_wrapper": "Result<" in enriched_prd or "runCatching" in enriched_prd,
        "P08:callbackflow": "callbackFlow" in enriched_prd,
        "P09:tasks_await": "tasks.await()" in enriched_prd or ".await()" in enriched_prd,
        "P10:datastore": "DataStore" in enriched_prd,
        "P11:lifecycle_collect": "collectAsStateWithLifecycle" in enriched_prd,
        "P12:launched_effect": "LaunchedEffect" in enriched_prd,
        "P16:singleton": "@Singleton" in enriched_prd,
        "P18:keep": "@Keep" in enriched_prd,
    }
    return [name for name, present in checks.items() if present]


def _gap_question(gap_name: str) -> str:
    questions = {
        "State Machines": (
            "I found entities in your PRD but no state transitions. "
            "What states can they be in, and what triggers each transition? "
            "(e.g. 'Order: PENDING → ASSIGNED when porter accepts; ASSIGNED → IN_PROGRESS when pickup confirmed')"
        ),
        "ViewModel Functions": (
            "What actions can the user take on each screen? "
            "List them with any pre-conditions or rate limits. "
            "(e.g. 'submitOtp: validates 6-digit code, blocks duplicate calls')"
        ),
        "Repository Methods": (
            "What data operations does the app need? "
            "(e.g. 'save order to Firestore, stream real-time location updates, authenticate with phone OTP')"
        ),
        "Business Rules": (
            "What business constraints must the code enforce? "
            "(e.g. 'OTP resend has 30s cooldown', 'payment cannot proceed without verified phone')"
        ),
        "Error Types": (
            "What can go wrong in each feature? "
            "(e.g. 'invalid phone format, OTP expired, network timeout, user already exists')"
        ),
    }
    return questions.get(gap_name, f"Can you provide more detail about '{gap_name}'?")
