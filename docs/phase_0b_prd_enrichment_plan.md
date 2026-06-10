# Phase 0B: PRD Enrichment Engine — Implementation Plan

> **Status: COMPLETE** — All files implemented and 86 tests passing. See `docs/status.md` for the full verification record.

## 1. Executive Summary

Phase 0B inserts an LLM-powered enrichment step between a developer's raw PRD and Phase 1 brain generation. It transforms any plaintext product description — however sparse, prose-heavy, or informally structured — into a **hyperspec PRD** that carries everything the code generator needs to produce 10/10 enterprise-grade Android code.

**Root cause it fixes:** The bigbaagh auth comparison (Phase 4 demo) showed generated code scoring 2.5/10. The templates and orchestrator were correct; the brain was empty because the PRD parser extracted high-level names but no behavioral specifications. Phase 0B fills that gap at the source.

---

## 2. Problem Statement: Evidence from the Bigbaagh Comparison

| Field | Bigbaagh production | Phase 4 generated | Gap |
|---|---|---|---|
| ViewModel constructor | 7 injected use cases | empty | PRD had no inject_dependencies |
| ViewModel functions | `requestOtp`, `verifyOtp`, `resendOtp`, countdown | `// TODO: implement` | PRD had no function specs |
| Repository methods | `requestOtp`, `verifyOtp`, `getAuthState()`, `logout()` | `getAll(): List<Any>` | PRD had no method signatures |
| UI state type | `data class OtpUiState` | `sealed class Loading/Success/Error` | PRD had no state type hint |
| Events | `SharedFlow<AuthEvent>` | absent | PRD had no event spec |
| Mutex guard | `verifyMutex.withLock {}` | absent | business rule not in function spec |
| Countdown timer | `ticker(1000ms)` | absent | no function behavior spec |
| Error type | `sealed class AuthError` | `message: String` | PRD had no error class spec |

**Conclusion:** Every gap traces back to missing PRD data — not template limitations. Enrich the PRD, and the same templates produce production-quality code.

---

## 3. Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Phase 0B: Enrichment Pipeline                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Raw PRD (any format / any completeness level)                     │
│        │                                                             │
│        ▼                                                             │
│   ┌─────────────────────────────────────────────┐                   │
│   │  Stage 1 — Structural Extraction            │                   │
│   │  • Parse existing sections                  │                   │
│   │  • Detect what is present vs missing        │                   │
│   │  • Build gap report for LLM context         │                   │
│   └─────────────────────────────────────────────┘                   │
│        │                                                             │
│        ▼                                                             │
│   ┌─────────────────────────────────────────────┐                   │
│   │  Stage 2 — LLM Enrichment                   │                   │
│   │  • Persona: Principal Android Engineer @    │                   │
│   │    Google (NiA, Jetpack, MVVM guide)        │                   │
│   │  • Output: hyperspec PRD                    │                   │
│   │  • Applies 20 enterprise patterns           │                   │
│   │  • Marks [INFERRED] vs [FROM PRD]           │                   │
│   │  • Marks [UNKNOWN] gaps for user input      │                   │
│   └─────────────────────────────────────────────┘                   │
│        │                                                             │
│        ▼                                                             │
│   ┌─────────────────────────────────────────────┐                   │
│   │  Stage 3 — Validation & Scoring             │                   │
│   │  • PRDCompletenessScorer on output          │                   │
│   │  • Target: ≥ 90/100                         │                   │
│   └─────────────────────────────────────────────┘                   │
│        │                   │                                         │
│        │ score ≥ 90        │ score < 90 + --interactive             │
│        │                   ▼                                         │
│        │        ┌──────────────────────────┐                        │
│        │        │ Stage 4 — Gap Fill Loop  │                        │
│        │        │ • Targeted Q&A per gap   │                        │
│        │        │ • Re-enrich with answers │                        │
│        │        │ • Max 3 iterations       │                        │
│        │        └──────────────────────────┘                        │
│        │                   │                                         │
│        ▼                   ▼                                         │
│   Hyperspec PRD (score ≥ 90, human-reviewed)                        │
│        │                                                             │
│        ▼                                                             │
│   Phase 1 — Brain Generation                                        │
└─────────────────────────────────────────────────────────────────────┘
```

**Critical safeguard:** The enriched PRD is a human-readable markdown file the developer reviews before running `brain init`. LLM inferences are clearly marked. The developer edits freely before proceeding. This prevents hallucination from entering the brain silently.

---

## 4. Enterprise Pattern Catalog

The enrichment LLM is instructed to apply all 20 patterns. Patterns are also enforced by updated v2 templates.

### ViewModel Patterns

| # | Pattern | Anti-pattern | Implementation |
|---|---|---|---|
| P01 | `data class UiState` with boolean flags | `sealed class Loading/Success/Error` | `data class XUiState(val isLoading: Boolean = false, ...)` |
| P02 | `Channel<Event>` for one-shot events | Navigation inside ViewModel | `private val _events = Channel<XEvent>(Channel.BUFFERED)` |
| P03 | `_uiState.update { it.copy(...) }` | `_uiState.value = ...` | Atomic, thread-safe state mutation |
| P04 | `Mutex` for concurrent guards | No guard | `private val _mutex = Mutex()` + `_mutex.withLock {}` |
| P05 | `SavedStateHandle` for nav args | Constructor params | `savedStateHandle.get<String>("key")` |
| P06 | `sealed class FeatureError` | `message: String` | Per-feature error hierarchy with `from(Throwable)` factory |

### Repository Patterns

| # | Pattern | Anti-pattern | Implementation |
|---|---|---|---|
| P07 | `suspend fun x(): Result<T>` | `suspend fun x(): T` (throws) | `runCatching { }.getOrElse { ... }` |
| P08 | `Flow<T>` for streams | callbacks | `callbackFlow { awaitClose { listener.remove() } }` |
| P09 | `tasks.await()` | `.addOnSuccessListener {}` | Coroutine-first Firebase |
| P10 | `DataStore<Preferences>` | `SharedPreferences` | `dataStore.edit {}`, `dataStore.data.map {}` |

### Composable / Screen Patterns

| # | Pattern | Anti-pattern | Implementation |
|---|---|---|---|
| P11 | `collectAsStateWithLifecycle()` | `collectAsState()` | Lifecycle-aware; no leaks |
| P12 | `LaunchedEffect(Unit)` for events | `collectAsState` on events | `viewModel.events.collect { handle(it) }` |
| P13 | Nav callbacks as lambda params | `NavController` injection | `onNavigateToHome: () -> Unit` |
| P14 | `@Stable` on UiState | unAnnotated | Compose compiler optimization |
| P15 | Content function `XContent(uiState, callbacks)` | Logic in root Composable | Separation of stateful/stateless |

### Architecture Patterns

| # | Pattern | Anti-pattern | Implementation |
|---|---|---|---|
| P16 | `@Singleton` on all repositories | Per-component scope | Shared state, single source of truth |
| P17 | Use cases as single-function classes | Logic in ViewModel | `operator fun invoke()` delegation |
| P18 | `@Keep` on all Firestore models | Bare data class | ProGuard serialization safety |
| P19 | `@SerializedName` / `@PropertyName` | Field name == Firestore key | Explicit Firestore field mapping |
| P20 | Sealed error class with `companion object { fun from(t: Throwable) }` | `when (e)` scattered | Centralised error mapping |

---

## 5. Hyperspec Template: Output Format

The enrichment LLM targets `templates/hyperspec_template.md`. Key additions over the current PRD template:

### ViewModel Section (Hyperspec)
```markdown
### ViewModel: AuthViewModel

#### Inject Dependencies
- requestOtpUseCase: RequestOtpUseCase [INFERRED]
- verifyOtpUseCase: VerifyOtpUseCase [INFERRED]
- savedStateHandle: SavedStateHandle [INFERRED]

#### UI State Type: data class
    data class OtpUiState(
        val isLoading: Boolean = false,
        val isVerifying: Boolean = false,
        val countdown: Int = 0,
        val error: AuthError? = null
    )

#### Events (one-shot, Channel dispatch)
- NavigateToHome [INFERRED from auth success flow]
- ShowSnackbar(message: String) [INFERRED]

#### Functions

##### fun requestOtp(phoneNumber: String): Unit
- Validate: INDIA_MOBILE_REGEX [FROM PRD: BR001]
- Effect: isLoading true → requestOtpUseCase(phone) → isLoading false
- On success: send NavigateToOtp(phone) event
- On failure: error = AuthError.InvalidPhone or AuthError.Network

##### fun verifyOtp(otp: String): Unit
- Concurrency: Mutex [FROM PRD: BR002]
- Effect: isVerifying true → verifyOtpUseCase → isVerifying false
- On success: send NavigateToHome
- On failure: error = AuthError.OtpInvalid

##### fun resendOtp(): Unit
- Pre-check: countdown > 0 → early return [FROM PRD: BR001]
- On success: startCountdown(30)

##### private fun startCountdown(seconds: Int): Unit
- Launches ticker in viewModelScope
- Decrements countdown every 1000ms [INFERRED]
- Emits Cooldown UiState updates [INFERRED]
```

### Repository Section (Hyperspec)
```markdown
### Repository: AuthRepository

#### Interface Methods
- suspend fun requestOtp(phoneNumber: String): Result<Unit>
- suspend fun verifyOtp(phoneNumber: String, otp: String): Result<AuthUser>
- suspend fun resendOtp(phoneNumber: String): Result<Unit>
- fun getAuthState(): Flow<AuthState>
- suspend fun logout(): Result<Unit>
- suspend fun ensureUserDocument(user: AuthUser): Result<Unit>

#### Implementation Data Sources
- firebaseAuth: FirebaseAuth [INFERRED from Firebase Auth usage]
- firestore: FirebaseFirestore [FROM PRD: Firestore schema]
- dataStore: DataStore<Preferences> [FROM PRD: BR004]
- mutex: Mutex [FROM PRD: BR002]
```

---

## 6. Implementation Files

### New Files

| File | Purpose |
|---|---|
| `templates/hyperspec_template.md` | Canonical target format for enrichment output |
| `prompts/prd_enrichment_v1.txt` | LLM enrichment prompt (versioned) |
| `project_brain/generators/prd_enricher.py` | PRDEnricher class, EnrichmentResult dataclass |
| `templates/v2/viewmodel.kt.j2` | Enterprise ViewModel: data class state + Channel events + Mutex |
| `templates/v2/uistate.kt.j2` | Enterprise UiState: data class + error sealed class |
| `templates/v2/events.kt.j2` | Sealed events class |
| `templates/v2/repository_interface.kt.j2` | Repository interface with Result<T> methods |
| `templates/v2/repository_impl.kt.j2` | Enterprise impl: runCatching, callbackFlow, tasks.await |
| `templates/v2/usecase.kt.j2` | Use case with Result<T> passthrough |
| `templates/v2/screen_scaffold.kt.j2` | Lifecycle-aware screen: collectAsStateWithLifecycle + LaunchedEffect |
| `templates/v2/di_module.kt.j2` | Same structure as v1, no changes needed |
| `templates/v2/datamodel.kt.j2` | @Keep + @PropertyName + defaults |
| `tests/test_prd_enricher.py` | Enricher unit tests |

### Modified Files

| File | Change |
|---|---|
| `project_brain/brain/schema.py` | Add `ui_state_type`, `event_class`, `has_mutex`, `has_saved_state` to ViewModel; `concurrent` to ViewModelFunction; `result_wrapped`, `is_flow` to RepositoryMethod |
| `project_brain/llm/adapter.py` | Add `complete(prompt)` and `enrich_prd(raw_prd, template, patterns)` to adapter protocol |
| `project_brain/llm/claude.py` | Implement `complete()` |
| `project_brain/llm/openai.py` | Implement `complete()` |
| `project_brain/engines/template_engine.py` | Pick v1 vs v2 templates based on `ui_state_type` field; build enriched contexts |
| `project_brain/generators/code_generation.py` | Route to v2 templates when brain has enriched ViewModel data |
| `project_brain/cli/commands.py` | Add `brain enrich-prd` command |
| `CLAUDE.md` | Document Phase 0B |

---

## 7. CLI Interface

```bash
# Basic enrichment — outputs enriched PRD
brain enrich-prd ./rough_notes.md

# Save enriched output to file (then review before init)
brain enrich-prd ./rough_notes.md --output ./enriched_prd.md

# Interactive gap-fill: asks targeted questions for score < 90
brain enrich-prd ./rough_notes.md --output ./enriched_prd.md --interactive

# Full workflow
brain enrich-prd ./rough_notes.md --output ./enriched_prd.md
# → developer reviews and edits enriched_prd.md
brain init --from-prd ./enriched_prd.md
```

---

## 8. Before/After: Bigbaagh Auth at Phase 4

### Before (current state, no enrichment)
```kotlin
// Generated AuthViewModel — score: 2.5/10
@HiltViewModel
class AuthViewModel @Inject constructor(
    // EMPTY — no use cases injected
) : ViewModel() {
    private val _uiState = MutableStateFlow<PhoneInputUiState>(PhoneInputUiState.Loading)
    val uiState: StateFlow<PhoneInputUiState> = _uiState.asStateFlow()
    // TODO: implement
}
```

### After Phase 0B enrichment
```kotlin
// Generated AuthViewModel — target score: 8+/10
@HiltViewModel
class AuthViewModel @Inject constructor(
    private val requestOtpUseCase: RequestOtpUseCase,
    private val verifyOtpUseCase: VerifyOtpUseCase,
    private val resendOtpUseCase: ResendOtpUseCase,
    private val savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PhoneInputUiState())
    val uiState: StateFlow<PhoneInputUiState> = _uiState.asStateFlow()

    private val _events = Channel<AuthEvent>(Channel.BUFFERED)
    val events = _events.receiveAsFlow()

    private val _verifyMutex = Mutex()

    fun requestOtp(phoneNumber: String) {
        if (!INDIA_MOBILE_REGEX.matches(phoneNumber)) {
            _uiState.update { it.copy(error = AuthError.InvalidPhoneNumber) }
            return
        }
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            requestOtpUseCase(phoneNumber)
                .onSuccess { _events.send(AuthEvent.NavigateToOtp(phoneNumber)) }
                .onFailure { _uiState.update { s -> s.copy(isLoading = false, error = AuthError.from(it)) } }
            _uiState.update { it.copy(isLoading = false) }
        }
    }

    fun verifyOtp(otp: String) {
        viewModelScope.launch {
            _verifyMutex.withLock {
                _uiState.update { it.copy(isVerifying = true, error = null) }
                verifyOtpUseCase(savedStateHandle["phoneNumber"] ?: "", otp)
                    .onSuccess { _events.send(AuthEvent.NavigateToHome) }
                    .onFailure { _uiState.update { s -> s.copy(isVerifying = false, error = AuthError.OtpInvalid) } }
            }
        }
    }

    fun resendOtp() {
        if (_uiState.value.countdown > 0) return
        viewModelScope.launch {
            resendOtpUseCase(savedStateHandle["phoneNumber"] ?: "")
                .onSuccess { startCountdown(30) }
                .onFailure { _uiState.update { s -> s.copy(error = AuthError.from(it)) } }
        }
    }

    private fun startCountdown(seconds: Int) {
        viewModelScope.launch {
            (seconds downTo 0).forEach { remaining ->
                _uiState.update { it.copy(countdown = remaining) }
                if (remaining > 0) delay(1_000)
            }
        }
    }
}
```

**Score projection after Phase 0B:** 8–9/10 (missing only device-specific edge cases and deep UI logic that no generator can infer without UX mocks).

---

## 9. Quality Benchmarks

| Metric | Before Phase 0B | After Phase 0B |
|---|---|---|
| ViewModel constructor completeness | 0% (empty) | 90%+ |
| Function bodies (LLM quality) | `// TODO` stub | Business-rule-aware implementation |
| Repository method coverage | 1 stub method | All domain methods |
| Enterprise pattern adoption | 0/20 | 16–18/20 |
| PRD→Brain fidelity | ~30% | ~85% |
| Generated code quality score | 2.5/10 | 8–9/10 |

---

## 10. Degradation Behaviour (No API Key)

When no LLM is available (`NullAdapter`):
1. Raw PRD is preserved as-is
2. Hyperspec template sections are appended with `[TODO: fill this section]` markers
3. Score report shows exactly which sections need manual completion
4. Developer fills the gaps manually and runs `brain init`

The system never blocks — it just guides.
