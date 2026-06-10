# [Project Name] — Hyperspec PRD

> This is an enriched PRD produced by Phase 0B. All sections are required by the brain generator.
> Annotations:
>   [FROM PRD] — extracted directly from the source document
>   [INFERRED] — derived by the enrichment LLM from domain knowledge
>   [UNKNOWN]  — cannot be determined; developer must fill before running brain init

---

## 1. Project Metadata

- **Package name:** com.example.app
- **Min SDK:** 26
- **Target SDK:** 35
- **Architecture:** MVVM+Hilt+Compose+Firebase
- **Version name:** 1.0.0

---

## 2. User Roles

| id | name | description | app_module |
|---|---|---|---|
| [role_id] | [Role Name] | [Description] | [module] |

---

## 3. Feature ViewModels [ENRICHED]

For each feature, provide the full ViewModel and Repository specification.

### Feature: [FeatureName]

#### ViewModel: [ViewModelName]

##### Inject Dependencies
<!-- List each injected class: ClassName: Type -->
- [paramName]: [ClassName]

##### UI State Type
<!-- Choose: data_class (recommended for complex screens) OR sealed_class (simple 3-state screens) -->
Type: data_class

<!-- If data_class, provide the full data class definition -->
```kotlin
data class [ScreenName]UiState(
    val isLoading: Boolean = false,
    val [field]: [Type] = [default],
    val error: [FeatureName]Error? = null
)
```

##### Error Types
<!-- Sealed class for this feature's error states -->
```kotlin
sealed class [FeatureName]Error {
    data object [ErrorName] : [FeatureName]Error()
    data class Network(val message: String) : [FeatureName]Error()
    
    companion object {
        fun from(throwable: Throwable): [FeatureName]Error = when (throwable) {
            is [SpecificException] -> [ErrorName]
            else -> Network(throwable.message ?: "Unknown error")
        }
    }
}
```

##### Events (one-shot, Channel dispatch)
<!-- These are one-shot UI events: navigation, snackbar, dialogs. Never in UiState. -->
```kotlin
sealed class [FeatureName]Event {
    data object [NavigationEvent] : [FeatureName]Event()
    data class ShowSnackbar(val message: String) : [FeatureName]Event()
}
```

##### Concurrent Guards
<!-- List function names that must be wrapped in Mutex.withLock {} -->
- [functionName]: Mutex [FROM PRD: BR###]

##### SavedState Keys
<!-- List keys stored in SavedStateHandle (survive process death) -->
- [key]: [Type]

##### Functions

###### fun [functionName]([params]): [ReturnType]
- **Validate:** [validation rule, if any]
- **Concurrency:** [Mutex | none]
- **Pre-check:** [early return condition, if any]
- **Effect:** [state before] → [operation] → [state after]
- **On success:** [state update or event]
- **On failure:** [error state update]
- **Business rule:** [BR### reference]
- **Annotation:** [INFERRED] or [FROM PRD]

---

## 4. Repository Contracts [ENRICHED]

### Repository: [RepositoryName]

#### Interface Methods

| Signature | Return | Pattern | Source |
|---|---|---|---|
| `suspend fun [name]([params])` | `Result<[T]>` | runCatching | [FROM PRD / INFERRED] |
| `fun [name]([params])` | `Flow<[T]>` | callbackFlow | [FROM PRD / INFERRED] |

#### Implementation Data Sources
<!-- Exact injected types -->
- [paramName]: [ExactType]  [INFERRED / FROM PRD]

#### Firebase Patterns Used
- [ ] Firebase Auth (`firebaseAuth.signIn*().await()`)
- [ ] Firestore (`firestore.collection().document().get().await()`)
- [ ] Firebase Storage
- [ ] DataStore (`dataStore.edit {}`)

---

## 5. Use Case Contracts [ENRICHED]

For each use case, define the exact `invoke()` signature.

### UseCase: [UseCaseName]

```kotlin
// operator fun invoke signature:
suspend operator fun invoke([params]): Result<[T]>

// Business rule enforced: [BR###]
// Delegated repository method: [RepositoryName].[methodName]
```

---

## 6. Data Models [ENRICHED]

### Model: [ModelName]

```kotlin
@Keep
data class [ModelName](
    @PropertyName("[firestore_field]")
    val [fieldName]: [Type] = [default],
    // ...
)
```

| field | type | nullable | default | firestore_field |
|---|---|---|---|---|
| [field] | [Type] | false | [value] | [field_name] |

#### Firestore Collection
- Path: `/[collection]/{id}`
- Consistency rules:
  - [rule description]

---

## 7. State Machines [ENRICHED]

### StateMachine: [EntityName]

```
States: [State1] | [State2] | [State3]

Transitions:
[State1] ──[trigger]──> [State2]
  required_updates: [Firestore path], [DataStore key]
  side_effects: [what happens]

[State2] ──[trigger]──> [State3]
  required_updates: [Firestore path]
```

---

## 8. Business Rules [ENRICHED]

For each rule, specify where it is enforced and how.

### BR[###]: [Short Title]

- **Description:** [Full rule text]
- **Enforcement layer:** [ViewModel | UseCase | Repository]
- **Enforcing class:** [ClassName]
- **Enforcing function:** [functionName]
- **Implementation pattern:**
  ```kotlin
  // Exact code pattern to enforce this rule
  ```
- **Source:** [FROM PRD] or [INFERRED]

---

## 9. Navigation Flow [ENRICHED]

```
[ScreenA]
  on [Event]: navigate to [ScreenB]
  nav args passed: [arg1: Type, arg2: Type]

[ScreenB]
  receives: [arg1] via SavedStateHandle
```

<!-- All navigation events must flow through the event Channel, never NavController in ViewModel -->

---

## 10. Phase Breakdown

### Phase [N]: [Name]

- **Screens:** [Screen1], [Screen2]
- **Completion criteria:**
  - [ ] [Criterion]
  - [ ] No CLASS_A violations
  - [ ] 80%+ test coverage

---

## 11. Design System [ENRICHED]

| Token | Value | Usage |
|---|---|---|
| [ColorName] | `#[HEX]` | [where used] |
| [TypographyName] | [size/weight] | [where used] |

---

## 12. Inferences Log

The enrichment LLM made the following inferences. **Review before running `brain init`.**

| # | Inference | Basis | Confidence | Accept? |
|---|---|---|---|---|
| 1 | [What was inferred] | [Why — domain pattern or PRD implication] | High/Med/Low | [ ] |

Items marked **Low confidence** require developer confirmation before proceeding.
