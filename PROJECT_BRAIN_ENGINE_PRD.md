# PROJECT BRAIN ENGINE
## Product Requirements Document v1.0
### Android Project Intelligence & Code Generation MCP Server

---

> **Document Status:** Final Draft  
> **Author:** AAY ZEE  
> **Target:** Solo Android developers building production apps with MVVM + Hilt + Compose + Firebase  
> **Build Mode:** Solo developer, phased delivery, each phase ships real value

---

## TABLE OF CONTENTS

1. [Vision & Problem Statement](#1-vision--problem-statement)
2. [Core Design Principles](#2-core-design-principles)
3. [System Architecture](#3-system-architecture)
4. [Project Brain JSON Schema](#4-project-brain-json-schema)
5. [Phase 1 — Brain Generation](#5-phase-1--brain-generation)
6. [Phase 2 — MCP Server & Core Tools](#6-phase-2--mcp-server--core-tools)
7. [Phase 3 — Rule Engine & Validation](#7-phase-3--rule-engine--validation)
8. [Phase 4 — Code Generation Engine](#8-phase-4--code-generation-engine)
9. [Phase 5 — Predictive Bug Engine](#9-phase-5--predictive-bug-engine)
10. [Phase 6 — Self-Healing & Sync](#10-phase-6--self-healing--sync)
11. [PRD Template Specification](#11-prd-template-specification)
12. [MCP Tool Catalogue](#12-mcp-tool-catalogue)
13. [Template Engine Specification](#13-template-engine-specification)
14. [Critical Gaps & Mitigations](#14-critical-gaps--mitigations)
15. [What Will Break & Pre-Fixes](#15-what-will-break--pre-fixes)
16. [Non-Goals & Explicit Exclusions](#16-non-goals--explicit-exclusions)
17. [Tech Stack](#17-tech-stack)
18. [Build Order & Milestones](#18-build-order--milestones)
19. [Success Metrics](#19-success-metrics)

---

## 1. VISION & PROBLEM STATEMENT

### The Problem

Every LLM-powered code generation tool suffers from the same four failures:

| Failure | Impact |
|---|---|
| Context loss between sessions | Developer re-explains architecture every session |
| Inconsistent pattern application | MVVM drift across phases |
| No business logic awareness | Production bugs that only appear at runtime |
| LLM model dependency | Output quality varies with model updates |

No existing tool — Claude Code, Cursor, aider, Copilot — solves all four. They are all stateless, pattern-blind, and LLM-dependent.

### The Vision

**Project Brain Engine** is a self-hosted MCP server that acts as the permanent architectural memory and code quality enforcer for any Android project.

```
Developer feeds PRD or existing codebase ONCE
           ↓
Engine generates PROJECT_BRAIN.json
           ↓
MCP server goes live on localhost
           ↓
Any LLM tool (Claude Code, aider, Continue.dev)
connects to MCP and gets:
  - Full architecture context always
  - Deterministic MVVM validation
  - Production-ready code generation
  - Business logic bug forecasting
  - Phase completion tracking
```

### Who This Is For

- Solo Android developers building multi-phase apps
- Developers using Claude Code or any MCP-compatible CLI tool
- Developers who want production-quality output regardless of LLM model day-to-day variance

---

## 2. CORE DESIGN PRINCIPLES

These principles are non-negotiable. Every feature must comply.

### P1: Determinism First
All validation, rule-checking, and structural decisions must produce **identical output for identical input**, regardless of LLM model, version, or API response variance.

```
Rule: ViewModel must not import Context
Result for violating file: ALWAYS CLASS_A violation
No LLM involved in this decision. Ever.
```

### P2: LLM Does Language, Engine Does Architecture
LLM is allowed to:
- Fill business logic function bodies
- Write comments and documentation
- Parse natural language PRD text (one time)
- Explain bugs in plain English

LLM is **never** allowed to:
- Decide file structure
- Choose MVVM patterns
- Determine state machine transitions
- Make compliance decisions

### P3: MCP-Native from Day 1
Every capability is exposed as an MCP tool. No capabilities exist only as internal functions. This ensures any CLI tool can use the engine.

### P4: No Regression
Every code generation pass runs through the full rule engine before returning output. It is impossible to generate a non-compliant file. Self-healing retries handle LLM variance.

### P5: Graceful Degradation
If LLM adapter is unavailable, all read and validation tools still work. Code generation degrades to template-only output with slots marked `// TODO: implement`. Engine never crashes due to LLM failure.

### P6: Single Source of Truth
`PROJECT_BRAIN.json` is the only source of architecture truth. No other file, no runtime state, no LLM memory. Everything derives from the brain.

---

## 3. SYSTEM ARCHITECTURE

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PROJECT BRAIN ENGINE                      │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                  MCP SERVER LAYER                    │   │
│  │         (stdio transport — MCP spec compliant)       │   │
│  │  Tools: 30+ callable tools via MCP protocol          │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │               ORCHESTRATOR LAYER                     │   │
│  │  Routes tool calls to correct engine                 │   │
│  │  Manages retry logic and self-healing                │   │
│  │  Handles conflict resolution                         │   │
│  └──┬──────────┬──────────┬──────────┬──────────────────┘   │
│     │          │          │          │                      │
│  ┌──▼──┐  ┌───▼───┐  ┌───▼───┐  ┌───▼──────────────────┐   │
│  │RULE │  │TEMPL  │  │STATE  │  │   BRAIN MANAGER      │   │
│  │ENGI │  │ENGINE │  │TRANSI │  │ read/write/sync      │   │
│  │ NE  │  │       │  │TION   │  │ PROJECT_BRAIN.json   │   │
│  │     │  │       │  │ENGINE │  │                      │   │
│  └──┬──┘  └───┬───┘  └───┬───┘  └──────────────────────┘   │
│     │         │           │                                  │
│  ┌──▼─────────▼───────────▼──────────────────────────────┐  │
│  │                  LLM ADAPTER LAYER                    │  │
│  │   Claude / GPT / Gemini / Local — hot-swappable       │  │
│  │   Called ONLY for: function body fill, explanations   │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              PROJECT_BRAIN.json                     │    │
│  │          (single source of truth)                   │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
   Claude Code                    Any MCP client
   (stdio MCP)               (aider, Continue.dev, etc.)
```

### Transport Layer Decision

**Use stdio transport only.**  

Reason: MCP stdio is the universal standard. HTTP/SSE transport requires a running server process which breaks on developer machines after reboot, creates port conflicts, and adds network security complexity. stdio launches on demand, requires no port management, and is what Claude Code natively uses.

```json
// claude_desktop_config.json / .claude/config
{
  "mcpServers": {
    "project-brain": {
      "command": "python",
      "args": ["-m", "project_brain.server"],
      "env": {
        "BRAIN_PATH": "./PROJECT_BRAIN.json"
      }
    }
  }
}
```

### Data Flow for Code Generation

```
1. Claude Code: "generate OrderTrackingViewModel"
2. MCP tool called: generate_viewmodel("OrderTrackingScreen")
3. Orchestrator: reads brain → finds screen dependencies
4. Template Engine: loads ViewModel template, fills structure slots
5. LLM Adapter: fills business logic functions only
6. Rule Engine: validates output (max 3 attempts)
7. Auto-fixer: fixes any remaining violations
8. Returns: compliant .kt file content
9. Claude Code: writes file to project
10. Brain Manager: marks screen ViewModel as generated
```

---

## 4. PROJECT BRAIN JSON SCHEMA

This is the canonical schema. All tools read and write to this structure.

```json
{
  "meta": {
    "project_name": "KPorter",
    "version": "1.0.0",
    "created_at": "2026-01-01T00:00:00Z",
    "last_synced": "2026-06-09T10:00:00Z",
    "entry_point": "prd|codebase",
    "architecture": "MVVM+Hilt+Compose+Firebase",
    "package_name": "com.example.kporter",
    "min_sdk": 26,
    "target_sdk": 35,
    "brain_version": "1.0"
  },

  "design_system": {
    "name": "Deep Orchard",
    "primary_color": "#1B4332",
    "accent_color": "#F4A200",
    "font_heading": "Fraunces",
    "font_body": "DM Sans",
    "token_rules": [
      "Use colors.statusCompleted not colors.success",
      "FAB must use BigbaaghFloatingActionButton",
      "Chemical screens must include ProductAdvisoryDisclaimer"
    ]
  },

  "user_roles": [
    {
      "id": "customer",
      "name": "Customer",
      "description": "Books porter for delivery",
      "app_module": "customer"
    },
    {
      "id": "porter",
      "name": "Porter",
      "description": "Fulfills delivery orders",
      "app_module": "porter"
    }
  ],

  "data_models": [
    {
      "id": "Porter",
      "fields": [
        {"name": "id", "type": "String", "nullable": false},
        {"name": "isAvailable", "type": "Boolean", "nullable": false},
        {"name": "activeRideId", "type": "String", "nullable": true},
        {"name": "currentLat", "type": "Double", "nullable": true},
        {"name": "currentLng", "type": "Double", "nullable": true},
        {"name": "totalEarnings", "type": "Double", "nullable": false}
      ],
      "firestore_collection": "/porters/{porterId}",
      "consistency_links": [
        {"field": "isAvailable", "linked_to": "Order.status", "rule": "isAvailable=false when Order.status=ASSIGNED"}
      ]
    }
  ],

  "state_machines": [
    {
      "entity": "Order",
      "states": ["PENDING", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"],
      "transitions": [
        {
          "from": "IN_PROGRESS",
          "to": "COMPLETED",
          "required_firestore_updates": [
            "order.status = COMPLETED",
            "order.completedAt = ServerTimestamp",
            "porter.isAvailable = true",
            "porter.activeRideId = null",
            "porter.totalEarnings += order.fare",
            "user.activeOrderId = null"
          ],
          "recommended_implementation": "Cloud Function trigger",
          "missing_any": "CLASS_A_PRODUCTION_BUG"
        }
      ]
    }
  ],

  "screens": [
    {
      "id": "OrderTrackingScreen",
      "route": "order_tracking/{orderId}",
      "phase": 2,
      "status": "pending",
      "mvvm_compliant": null,
      "viewmodel": "OrderTrackingViewModel",
      "repository": "OrderRepository",
      "use_cases": ["GetOrderUseCase", "TrackPorterLocationUseCase"],
      "models": ["Order", "Porter", "PorterLocation"],
      "parent_screen": "HomeScreen",
      "child_screens": ["RideCompletionScreen"],
      "nav_args": ["orderId: String"],
      "ui_states": ["Loading", "Active", "Completed", "Error"],
      "stateflows": ["uiState", "porterLocation"],
      "firestore_listeners": ["orders/{orderId}", "porters/{porterId}"],
      "design_tokens_used": ["colors.primary", "BigbaaghFloatingActionButton"],
      "generated": false,
      "file_path": null,
      "last_generated": null
    }
  ],

  "viewmodels": [
    {
      "id": "OrderTrackingViewModel",
      "screen": "OrderTrackingScreen",
      "repository": "OrderRepository",
      "use_cases": ["GetOrderUseCase"],
      "inject_dependencies": ["OrderRepository", "LocationStateHolder"],
      "ui_state_class": "OrderTrackingUiState",
      "functions": [
        {
          "name": "startTracking",
          "params": ["orderId: String"],
          "returns": "Unit",
          "business_rule": "Subscribe to Firestore order and porter location updates"
        }
      ],
      "generated": false,
      "mvvm_compliant": null,
      "file_path": null
    }
  ],

  "repositories": [
    {
      "id": "OrderRepository",
      "interface": "IOrderRepository",
      "implementation": "OrderRepositoryImpl",
      "data_sources": ["FirebaseFirestore"],
      "methods": [
        {
          "name": "getOrder",
          "params": ["orderId: String"],
          "returns": "Flow<Order?>",
          "firestore_path": "/orders/{orderId}"
        }
      ],
      "generated": false,
      "file_path": null
    }
  ],

  "navigation_graph": {
    "start_destination": "splash",
    "routes": [
      {
        "id": "splash",
        "screen": "SplashScreen",
        "next": ["login", "home"]
      }
    ]
  },

  "firestore_schema": {
    "collections": [
      {
        "path": "/porters/{porterId}",
        "fields": ["id", "isAvailable", "activeRideId", "currentLat", "currentLng"],
        "consistency_rules": [
          "isAvailable must be reset to true when linked order reaches COMPLETED"
        ]
      }
    ]
  },

  "phases": [
    {
      "number": 1,
      "name": "Core Authentication",
      "status": "complete",
      "screens": ["SplashScreen", "LoginScreen", "RegisterScreen"],
      "completion_criteria": [
        "All screens generated",
        "All ViewModels MVVM compliant",
        "Firebase Auth integrated",
        "No CLASS_A violations"
      ]
    }
  ],

  "business_rules": [
    {
      "id": "BR001",
      "description": "Porter must be marked available after ride completion",
      "trigger": "Order.status → COMPLETED",
      "required_updates": [
        "porter.isAvailable = true",
        "porter.activeRideId = null"
      ],
      "missing_any": "CLASS_A",
      "enforcement": "StateTransitionEngine"
    }
  ],

  "known_violations": [],

  "generation_history": []
}
```

---

## 5. PHASE 1 — BRAIN GENERATION

**Goal:** Given PRD.md OR existing codebase → produce valid `PROJECT_BRAIN.json`  
**Deliverable:** CLI tool `brain init`  
**LLM Used:** Yes (PRD parsing only). Codebase scanning is zero-LLM.

### 5.1 Entry Point A: PRD Parser

#### PRD Completeness Scorer (runs before parsing)

Before any parsing, score the PRD for completeness. Reject if score < 80.

```
Scoring dimensions:
  User roles defined         → 10 pts
  All screens listed         → 15 pts
  State machines defined     → 20 pts
  Firestore schema present   → 15 pts
  Business rules explicit    → 20 pts
  Phase breakdown present    → 10 pts
  Data models defined        → 10 pts
  ────────────────────────────────────
  Total                      → 100 pts
  Minimum to proceed         → 80 pts
```

If score < 80:
```
PRD Score: 62/100
Missing sections:
  ❌ State machines (20 pts) — add state transitions for each entity
  ❌ Business rules (18 pts) — add explicit "when X happens, Y must update"
Cannot generate brain until score ≥ 80.
Run: brain validate-prd ./PRD.md for detailed guidance.
```

#### PRD Parsing Flow

```python
def parse_prd(prd_path: str) -> ProjectBrain:
    
    # Step 1: Score completeness
    score = prd_scorer.score(prd_path)
    if score.total < 80:
        raise IncompletePRDError(score)
    
    # Step 2: LLM extracts structured data
    # Prompt is deterministic — same prompt every time
    extraction_prompt = load_prompt("prd_extraction_v1")
    raw = llm.extract(prd_path, extraction_prompt)
    
    # Step 3: Validate LLM output schema (zero-LLM)
    validated = schema_validator.validate(raw, BrainSchema)
    
    # Step 4: Fill confidence scores
    brain = confidence_scorer.score(validated)
    
    # Step 5: Flag low-confidence items for review
    review_items = [item for item in brain.all_items 
                    if item.confidence < 0.85]
    
    if review_items:
        interactive_review(review_items)  # CLI prompts developer
    
    return brain
```

#### LLM Extraction Prompt (deterministic, versioned)

The extraction prompt is stored in `prompts/prd_extraction_v1.txt` and never modified after release. New versions get new filenames.

```
You are a PRD parser. Extract the following from the PRD below.
Return ONLY valid JSON matching this exact schema: {schema}
Do not add fields not in the schema.
Do not infer state transitions not explicitly stated.
Mark confidence as 0.0-1.0 for each extracted item.
If a field cannot be extracted, set it to null, never guess.

PRD:
{prd_content}
```

### 5.2 Entry Point B: Codebase Scanner

Zero-LLM. Pure file system and regex/heuristic analysis.

#### Scanner Strategy (No Kotlin AST Library)

**Critical design decision:** No mature Python Kotlin AST library exists. Using regex + structural heuristics is the right approach with confidence scoring.

```python
class KotlinFileAnalyzer:
    
    # Patterns are compiled once, reused
    VIEWMODEL_PATTERN = re.compile(
        r'class\s+(\w+ViewModel)\s+@Inject\s+constructor'
    )
    HILT_VIEWMODEL_PATTERN = re.compile(
        r'@HiltViewModel\s+class\s+(\w+ViewModel)'
    )
    STATEFLOW_PATTERN = re.compile(
        r'val\s+(\w+):\s+StateFlow<(\w+)>'
    )
    COMPOSABLE_PATTERN = re.compile(
        r'@Composable\s+fun\s+(\w+Screen)'
    )
    INJECT_PATTERN = re.compile(
        r'private\s+val\s+(\w+):\s+(\w+Repository|\w+UseCase)'
    )
    FIRESTORE_PATTERN = re.compile(
        r'\.collection\("([^"]+)"\)'
    )
    
    def analyze(self, file_path: str) -> FileAnalysis:
        content = read_file(file_path)
        return FileAnalysis(
            viewmodels=self.HILT_VIEWMODEL_PATTERN.findall(content),
            screens=self.COMPOSABLE_PATTERN.findall(content),
            stateflows=self.STATEFLOW_PATTERN.findall(content),
            dependencies=self.INJECT_PATTERN.findall(content),
            firestore_calls=self.FIRESTORE_PATTERN.findall(content),
            confidence=self.calculate_confidence(content)
        )
    
    def calculate_confidence(self, content: str) -> float:
        # Higher confidence if standard patterns found
        # Lower if unusual structure detected
        score = 1.0
        if "@Composable" not in content and "ViewModel" not in content:
            score = 0.3  # Likely a utility file
        if content.count("class ") > 3:
            score *= 0.7  # Multiple classes — ambiguous
        return score
```

#### Relationship Mapping

```python
def map_relationships(analyses: List[FileAnalysis]) -> RelationshipMap:
    
    relationships = []
    
    for screen_file in analyses.screens:
        # Find ViewModel by naming convention first
        expected_vm = screen_file.name.replace("Screen", "ViewModel")
        vm = find_by_name(analyses.viewmodels, expected_vm)
        
        if vm:
            confidence = 0.95  # Name match = high confidence
        else:
            # Fallback: find ViewModel injected in same file
            vm = find_injected_viewmodel(screen_file)
            confidence = 0.75
        
        if not vm:
            confidence = 0.0  # Unknown — flag for manual review
        
        relationships.append(Relationship(
            screen=screen_file.name,
            viewmodel=vm.name if vm else None,
            confidence=confidence
        ))
    
    return RelationshipMap(relationships)
```

#### Scanner Output Report

```
KPorter Codebase Scan Complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 18 screens found
✅ 14 ViewModels mapped (confidence >85%)
✅ 9 Repositories found
✅ 26 data models found
✅ Firestore collections: /porters, /orders, /users, /rides
✅ Navigation routes: 22 extracted

⚠️  NEEDS REVIEW (confidence <85%):
   - AdminDashboardScreen → ViewModel: unclear (58%)
   - ReportsScreen → no ViewModel found (0%)

❌ GAPS DETECTED:
   - 2 screens have no ViewModel (CLASS_A)
   - 3 Repositories missing interface (CLASS_B)
   - 1 business logic found in Composable (CLASS_A)

Run: brain review to resolve flagged items interactively
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Brain written to: ./PROJECT_BRAIN.json
```

### 5.3 Brain CLI Commands

```bash
# New project from PRD
brain init --from-prd ./PRD.md

# Existing project
brain init --from-code ./app/src/main/kotlin

# Validate PRD completeness before init
brain validate-prd ./PRD.md

# Interactive review of low-confidence items
brain review

# Show brain summary
brain status

# Incremental sync after adding new files
brain sync --project ./app/src/main/kotlin

# Start MCP server
brain serve
```

---

## 6. PHASE 2 — MCP SERVER & CORE TOOLS

**Goal:** MCP server running, read tools working, Claude Code can connect  
**Transport:** stdio (not HTTP — see architecture decision above)  
**LLM Used:** No (read tools are zero-LLM)

### 6.1 MCP Server Setup

```python
# project_brain/server.py
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server

app = Server("project-brain")

@app.list_tools()
async def list_tools():
    return ALL_TOOL_DEFINITIONS  # loaded from tools/registry.py

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    tool = tool_registry.get(name)
    if not tool:
        raise ValueError(f"Unknown tool: {name}")
    return await tool.execute(arguments)

async def main():
    brain = BrainManager.load(os.environ["BRAIN_PATH"])
    tool_registry.initialize(brain)
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
```

### 6.2 Read Tools (Phase 2, Zero-LLM)

```
get_project_context()
  Returns: project name, phase summary, architecture, design system
  Used by: Claude Code on session start for instant full context

get_screen_graph(screen_id: str)
  Returns: screen + ViewModel + Repository + Models + nav relationships
  Used by: before generating any screen

get_phase_status(phase: int)
  Returns: completion %, screens done/pending, violations blocking completion
  Used by: phase audit prompts

get_all_screens()
  Returns: all screens with status, phase, compliance state
  Used by: overview and planning

get_dependencies(screen_id: str)
  Returns: what must exist before this screen can be built
  Used by: build order planning

get_firestore_schema()
  Returns: all collections, fields, consistency rules
  Used by: before writing any Firestore code

get_business_rules()
  Returns: all BR entries with trigger/required-updates
  Used by: before implementing any state transition

get_state_machine(entity: str)
  Returns: full state machine for entity with all transitions
  Used by: before implementing ride/order completion flows

get_design_tokens()
  Returns: all token rules for the project's design system
  Used by: before generating any screen UI

get_navigation_graph()
  Returns: full nav graph with routes and arguments
  Used by: before adding new navigation
```

### 6.3 CLAUDE.md Integration Template

Every project using Brain Engine adds this to their CLAUDE.md:

```markdown
## PROJECT BRAIN ENGINE

MCP Server: project-brain (stdio)
Brain File: ./PROJECT_BRAIN.json

### MANDATORY: Before every code generation task

1. Call get_project_context() — load full architecture
2. Call get_screen_graph({screen}) — load screen dependencies  
3. Call get_business_rules() — load relevant business rules
4. Call get_design_tokens() — load design system rules

### MANDATORY: Before writing any Firestore code

Call get_firestore_schema() and get_state_machine({entity})

### MANDATORY: After generating any file

Call mark_generated({screen_id}, {file_path})

### NEVER

- Deviate from returned template structure
- Add imports not present in dependency graph
- Skip state transition required_updates
- Use design token names not in get_design_tokens() response
```

---

## 7. PHASE 3 — RULE ENGINE & VALIDATION

**Goal:** Deterministic MVVM compliance checking. Zero LLM involvement.  
**Deliverable:** `validate_mvvm` and related tools  

### 7.1 Rule Categories

#### Category A: MVVM Layer Violations (CLASS A — blocks generation)

```python
MVVM_RULES = {
    "A001": MVVMRule(
        id="A001",
        description="ViewModel must not import android.content.Context",
        check=lambda ast: "android.content.Context" not in ast.imports,
        fix="Remove Context import. Use Application context via @ApplicationContext if needed.",
        severity="CLASS_A"
    ),
    "A002": MVVMRule(
        id="A002",
        description="ViewModel must not import androidx.compose",
        check=lambda ast: not any("androidx.compose" in i for i in ast.imports),
        fix="No Compose imports in ViewModel. Move UI logic to Composable.",
        severity="CLASS_A"
    ),
    "A003": MVVMRule(
        id="A003",
        description="Business logic must not be in @Composable function",
        check=lambda ast: not ast.composable_has_business_logic(),
        fix="Extract business logic to ViewModel function.",
        severity="CLASS_A"
    ),
    "A004": MVVMRule(
        id="A004",
        description="StateFlow must be private mutable, public immutable",
        check=lambda ast: ast.stateflows_have_correct_visibility(),
        fix="Use: private val _state = MutableStateFlow; val state = _state.asStateFlow()",
        severity="CLASS_A"
    ),
    "A005": MVVMRule(
        id="A005",
        description="Repository must have interface",
        check=lambda ast: ast.repository_has_interface(),
        fix="Create I{RepositoryName} interface.",
        severity="CLASS_A"
    ),
}
```

#### Category B: Pattern Violations (CLASS B — warning, non-blocking)

```
B001: ViewModel function does not return value (should use StateFlow)
B002: Repository method not suspend or Flow
B003: Data class missing @Keep annotation for Firestore
B004: Missing loading state in UI state sealed class
B005: Hardcoded string in Composable (should use stringResource)
B006: Direct Firestore call from ViewModel (should go via Repository)
```

#### Category C: Quality Warnings (CLASS C — informational)

```
C001: Function longer than 30 lines
C002: Missing KDoc comment on public function
C003: Magic number in business logic
C004: TODO comment older than current phase
```

### 7.2 Validation Engine

```python
class MVVMValidationEngine:
    
    def validate_file(self, file_path: str) -> ValidationReport:
        content = read_file(file_path)
        file_type = detect_file_type(content)  # ViewModel/Repository/Screen
        
        applicable_rules = self.get_rules_for_type(file_type)
        ast = KotlinAnalyzer.parse(content)
        
        violations = []
        for rule in applicable_rules:
            if not rule.check(ast):
                violations.append(Violation(
                    rule_id=rule.id,
                    severity=rule.severity,
                    description=rule.description,
                    fix=rule.fix,
                    line=ast.find_violation_line(rule)
                ))
        
        return ValidationReport(
            file=file_path,
            file_type=file_type,
            violations=violations,
            class_a_count=len([v for v in violations if v.severity == "CLASS_A"]),
            class_b_count=len([v for v in violations if v.severity == "CLASS_B"]),
            class_c_count=len([v for v in violations if v.severity == "CLASS_C"]),
            mvvm_compliant=len([v for v in violations if v.severity == "CLASS_A"]) == 0
        )
    
    def validate_phase(self, phase: int) -> PhaseValidationReport:
        brain = BrainManager.load()
        phase_screens = brain.get_phase_screens(phase)
        
        reports = []
        for screen in phase_screens:
            if screen.file_path:
                reports.append(self.validate_file(screen.file_path))
                if screen.viewmodel_path:
                    reports.append(self.validate_file(screen.viewmodel_path))
                if screen.repository_path:
                    reports.append(self.validate_file(screen.repository_path))
        
        return PhaseValidationReport(phase, reports)
```

### 7.3 MCP Validation Tools

```
validate_mvvm(file_path: str)
  Returns: ValidationReport with violations and fixes
  LLM: No

validate_phase(phase: int)
  Returns: PhaseValidationReport for all files in phase
  LLM: No

validate_firestore_consistency()
  Returns: list of consistency violations across Firestore writes
  LLM: No

validate_state_transitions(entity: str, file_path: str)
  Returns: missing required updates for each transition
  LLM: No

validate_design_tokens(file_path: str)
  Returns: token violations against design system rules
  LLM: No

validate_naming_conventions(file_path: str)
  Returns: naming violations against brain conventions
  LLM: No
```

---

## 8. PHASE 4 — CODE GENERATION ENGINE

**Goal:** Generate production-ready .kt files from brain spec  
**LLM Used:** Yes (function bodies only, constrained by templates)

### 8.1 Template Engine

Templates are Jinja2. Structure is fixed. Only `{{ FUNCTIONS }}` slot is LLM-filled.

#### ViewModel Template

```kotlin
// templates/viewmodel.kt.j2
package {{ package_name }}.presentation.{{ feature_name }}

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
{% for import in extra_imports %}
import {{ import }}
{% endfor %}
import javax.inject.Inject

@HiltViewModel
class {{ viewmodel_name }} @Inject constructor(
{% for dep in dependencies %}
    private val {{ dep.param_name }}: {{ dep.type }}{% if not loop.last %},{% endif %}
{% endfor %}
) : ViewModel() {

    private val _uiState = MutableStateFlow<{{ ui_state_class }}>({{ ui_state_class }}.Loading)
    val uiState: StateFlow<{{ ui_state_class }}> = _uiState.asStateFlow()

{% for flow in extra_stateflows %}
    private val _{{ flow.name }} = MutableStateFlow<{{ flow.type }}?>(null)
    val {{ flow.name }}: StateFlow<{{ flow.type }}?> = _{{ flow.name }}.asStateFlow()

{% endfor %}
    // ── Functions ────────────────────────────────────────────────
{{ functions }}
    // ─────────────────────────────────────────────────────────────
}
```

#### UI State Template

```kotlin
// templates/uistate.kt.j2
sealed class {{ state_class_name }} {
    data object Loading : {{ state_class_name }}()
    data class Success(val data: {{ data_type }}) : {{ state_class_name }}()
    data class Error(val message: String) : {{ state_class_name }}()
{% for extra in extra_states %}
    {{ extra.definition }}
{% endfor %}
}
```

#### Repository Interface Template

```kotlin
// templates/repository_interface.kt.j2
package {{ package_name }}.data.repository

import kotlinx.coroutines.flow.Flow

interface {{ interface_name }} {
{% for method in methods %}
    {{ method.signature }}
{% endfor %}
}
```

#### Repository Implementation Template

```kotlin
// templates/repository_impl.kt.j2
package {{ package_name }}.data.repository

import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import javax.inject.Inject

class {{ impl_name }} @Inject constructor(
    private val firestore: FirebaseFirestore
) : {{ interface_name }} {

{{ implementations }}
}
```

### 8.2 Self-Healing Generation Loop

```python
def generate_with_healing(
    template_name: str,
    context: dict,
    max_attempts: int = 3
) -> GenerationResult:
    
    for attempt in range(max_attempts):
        
        # Step 1: Fill template structure (zero-LLM)
        code = template_engine.render(template_name, context)
        
        # Step 2: LLM fills function bodies only
        if context.get("functions"):
            filled_functions = llm_adapter.fill_functions(
                context["functions"],
                context["business_rules"],
                context["conventions"]
            )
            code = code.replace("{{ functions }}", filled_functions)
        
        # Step 3: Validate (zero-LLM)
        report = rule_engine.validate_string(code, template_name)
        
        if report.class_a_count == 0:
            return GenerationResult(code=code, attempts=attempt+1, clean=True)
        
        # Step 4: Auto-fix CLASS A violations
        code = auto_fixer.fix(code, report.violations)
        
        # Step 5: Re-validate after fix
        report = rule_engine.validate_string(code, template_name)
        if report.class_a_count == 0:
            return GenerationResult(code=code, attempts=attempt+1, clean=True)
        
        # Retry with stronger LLM constraint prompt
        context["violations_to_avoid"] = report.violations
    
    # If still failing after max_attempts, return with violations marked
    return GenerationResult(
        code=code, 
        attempts=max_attempts, 
        clean=False,
        violations=report.violations
    )
```

### 8.3 Generation Rollback

Every generated file is versioned before overwrite:

```python
def write_generated_file(file_path: str, content: str):
    # Backup existing file
    if os.path.exists(file_path):
        backup_path = f"{file_path}.brain_backup_{timestamp()}"
        shutil.copy(file_path, backup_path)
        brain.generation_history.append({
            "file": file_path,
            "backup": backup_path,
            "timestamp": timestamp()
        })
    
    write_file(file_path, content)
    brain.save()
```

```
# CLI rollback
brain rollback --file OrderViewModel.kt
# Restores last backup and updates brain
```

### 8.4 MCP Generation Tools

```
generate_viewmodel(screen_id: str)
  Input: screen_id from brain
  Process: template + LLM fill + rule validation + self-heal
  Output: compliant .kt content
  LLM: Yes (function bodies only)
  Writes file: Yes (with backup)

generate_repository(repository_id: str)
  Same flow as above for Repository + Interface

generate_datamodel(model_id: str)
  Zero-LLM. Data classes are fully deterministic from brain schema.

generate_ui_state(screen_id: str)
  Generates sealed class from brain ui_states list

generate_screen_scaffold(screen_id: str)
  Generates Composable scaffold with correct ViewModel injection
  LLM fills: preview function, basic layout structure

generate_usecase(usecase_id: str)
  Generates UseCase class with invoke() operator

generate_di_module(feature_name: str)
  Generates Hilt module for feature

generate_nav_route(screen_id: str)
  Generates type-safe navigation route from brain spec

generate_test(file_path: str)
  Generates ViewModel test or Repository test scaffold
  LLM fills: test case descriptions and assertions
```

---

## 9. PHASE 5 — PREDICTIVE BUG ENGINE

**Goal:** Forecast production bugs before writing code  
**LLM Used:** Explanation only. Detection is zero-LLM.

### 9.1 Bug Categories

#### State Transition Bugs

```python
class StateTransitionBugDetector:
    
    def detect(self, file_path: str, brain: ProjectBrain) -> List[Bug]:
        content = read_file(file_path)
        bugs = []
        
        for machine in brain.state_machines:
            for transition in machine.transitions:
                # Check if transition is handled in this file
                if self.handles_transition(content, machine.entity, 
                                          transition.from_state, 
                                          transition.to_state):
                    # Check all required updates are present
                    for required in transition.required_firestore_updates:
                        if not self.update_present(content, required):
                            bugs.append(Bug(
                                type="MISSING_STATE_UPDATE",
                                severity="CLASS_A",
                                entity=machine.entity,
                                transition=f"{transition.from_state}→{transition.to_state}",
                                missing=required,
                                forecast="Porter will remain unavailable after ride. "
                                        "Order pool shrinks with every completed ride. "
                                        "Production failure within first 10 rides.",
                                fix=f"Add: {required} in {transition.to_state} handler"
                            ))
        return bugs
```

#### Firestore Consistency Bugs

```python
class FirestoreConsistencyDetector:
    
    def detect(self, brain: ProjectBrain) -> List[Bug]:
        bugs = []
        
        for model in brain.data_models:
            for link in model.consistency_links:
                # Check if any screen updates one field without the other
                for screen in brain.screens:
                    if self.updates_field(screen, link.field):
                        if not self.updates_linked_field(screen, link.linked_to):
                            bugs.append(Bug(
                                type="FIRESTORE_CONSISTENCY",
                                severity="CLASS_A",
                                description=f"{link.field} updated without {link.linked_to}",
                                forecast="Orphaned document. Data inconsistency in production.",
                                affected_screen=screen.id,
                                fix=f"Always update {link.linked_to} when updating {link.field}"
                            ))
        return bugs
```

#### Race Condition Detector

```python
RACE_CONDITION_PATTERNS = [
    {
        "pattern": "read-then-write without transaction",
        "detect": lambda content: (
            ".get()" in content and 
            ".set(" in content and 
            "runTransaction" not in content and
            "batch" not in content
        ),
        "severity": "CLASS_A",
        "forecast": "Two users can read same value simultaneously. "
                   "Double-booking / double-assignment in production.",
        "fix": "Use Firestore transaction: runTransaction { ... }"
    }
]
```

#### Client-Side Earnings Leak Detector

```python
def detect_revenue_integrity(content: str, brain: ProjectBrain) -> List[Bug]:
    bugs = []
    
    # Earnings calculation in ViewModel = revenue leak risk
    if "earnings" in content.lower() and "ViewModel" in content:
        if "viewModelScope" in content:
            bugs.append(Bug(
                type="REVENUE_INTEGRITY",
                severity="CLASS_A",
                forecast="If app crashes between earnings calculation and Firestore write, "
                        "porter loses earned money. Legal/trust risk.",
                fix="Move earnings calculation to Cloud Function triggered by order completion."
            ))
    return bugs
```

### 9.2 MCP Bug Forecasting Tools

```
forecast_bugs(screen_id: str)
  Runs all detectors against brain spec for this screen
  Returns: prioritised bug list with forecasts and fixes
  LLM: explanations only

detect_race_conditions(feature: str)
  Scans Firestore write patterns for concurrent access risks
  LLM: No

detect_orphaned_documents()
  Checks all consistency_links in brain for missing update coverage
  LLM: No

detect_revenue_leaks()
  Scans for client-side financial calculations
  LLM: No

simulate_edge_case(scenario: str)
  Scenarios: "app_killed_mid_ride", "network_drop_at_completion",
             "double_booking", "porter_cancels"
  Returns: which code paths fail and why
  LLM: Yes (scenario reasoning)

audit_production_readiness(phase: int)
  Full pre-launch check: state machines, consistency, race conditions, revenue
  LLM: No (detection) + Yes (summary report)
```

---

## 10. PHASE 6 — SELF-HEALING & SYNC

**Goal:** Brain stays in sync as project grows. Never stale.

### 10.1 Incremental Sync

```python
def sync(project_root: str, brain: ProjectBrain) -> SyncReport:
    
    # Find files changed since last sync
    changed_files = git_diff_since(brain.meta.last_synced)
    
    added = []
    modified = []
    deleted = []
    
    for file in changed_files:
        if is_kotlin_file(file):
            if file.status == "ADDED":
                new_item = scanner.analyze_file(file.path)
                brain.add_item(new_item)
                added.append(new_item)
            
            elif file.status == "MODIFIED":
                updated = scanner.analyze_file(file.path)
                conflicts = brain.detect_conflicts(updated)
                if conflicts:
                    conflict_resolver.resolve_interactive(conflicts)
                brain.update_item(updated)
                modified.append(updated)
            
            elif file.status == "DELETED":
                brain.remove_item(file.path)
                deleted.append(file.path)
    
    brain.meta.last_synced = now()
    brain.save()
    
    return SyncReport(added, modified, deleted)
```

### 10.2 Conflict Resolution

When brain says one thing and code says another:

```
CONFLICT DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Brain says: OrderScreen → OrderViewModel
Code shows: OrderScreen uses OrderViewModel + CartViewModel

Options:
  [1] Trust brain — CartViewModel usage is wrong, remove it
  [2] Trust code — update brain to add CartViewModel dependency  
  [3] Skip — resolve manually later

Choice: _
```

### 10.3 Multi-Module Support

Brain handles module boundaries:

```json
{
  "modules": [
    {
      "name": "porter-app",
      "package": "com.example.kporter.porter",
      "screens": ["PorterHomeScreen", "ActiveRideScreen"]
    },
    {
      "name": "customer-app", 
      "package": "com.example.kporter.customer",
      "screens": ["CustomerHomeScreen", "OrderTrackingScreen"]
    },
    {
      "name": "shared",
      "package": "com.example.kporter.shared",
      "models": ["Order", "Porter", "User"],
      "repositories": ["OrderRepository", "PorterRepository"]
    }
  ]
}
```

Cross-module dependency validation:
```
validate_cross_module_deps()
  Ensures customer-app never imports porter-app classes directly
  All sharing goes through shared module
```

---

## 11. PRD TEMPLATE SPECIFICATION

This is the official PRD template. Fill this for any new project. Brain is generated from it.

```markdown
# PRD: [Project Name]

## Document Control
- Version: 1.0
- Status: Draft | Review | Final
- PRD Score Target: 80+

---

## 1. Project Overview
- **Platform:** Android (Kotlin + Jetpack Compose)
- **Architecture:** MVVM + Hilt + Jetpack Compose + Firebase
- **Backend:** Firebase (Firestore / Auth / Storage / Functions)
- **Design System Name:** [name]
- **Primary Color:** [hex]
- **Accent Color:** [hex]
- **Heading Font:** [font]
- **Body Font:** [font]
- **Package Name:** com.example.[appname]
- **Min SDK:** 26
- **Target SDK:** 35

---

## 2. User Roles
| Role | Description | App Module |
|---|---|---|
| [Role 1] | [what they do] | [module name] |
| [Role 2] | [what they do] | [module name] |

---

## 3. Features & Screens

### Feature: [Feature Name]
**Screens:**
- [ScreenName]: [one line description]
- [ScreenName]: [one line description]

**Business Rules:**
- When [trigger] → [what must happen]
- [Entity] can only [constraint]

---

## 4. Data Models

### [ModelName]
| Field | Type | Nullable | Notes |
|---|---|---|---|
| id | String | No | Firestore document ID |
| [field] | [type] | [Yes/No] | [notes] |

**Firestore Path:** /[collection]/{documentId}

**Consistency Rules:**
- [field] must always be updated together with [other.field]

---

## 5. State Machines

### [Entity] States
**States:** STATE_1 → STATE_2 → STATE_3 → STATE_4

**Transitions:**
#### STATE_X → STATE_Y
When this transition happens, ALL of the following must update:
- [Entity].[field] = [value]
- [OtherEntity].[field] = [value]
- [OtherEntity].[field] = [value]
Recommended implementation: [Cloud Function / client-side transaction]

---

## 6. Firestore Schema

### Collection: /[collection]/{id}
**Fields:** [list all fields]
**Security rules summary:** [who can read/write]
**Indexes needed:** [composite indexes]

---

## 7. Business Rules

| ID | Trigger | Required Updates | Missing = |
|---|---|---|---|
| BR001 | [trigger event] | [list of updates] | CLASS_A |

---

## 8. Navigation Flow

```
[StartScreen] → [Screen2] → [Screen3]
                          ↘ [Screen4]
```

**Nav Arguments:**
- [ScreenName]: receives [argName: Type]

---

## 9. Phase Breakdown

### Phase 1: [Name]
**Screens:** [list]
**Completion criteria:**
- [ ] All screens generated
- [ ] All ViewModels MVVM compliant
- [ ] [feature] integrated
- [ ] No CLASS_A violations

### Phase 2: [Name]
...

---

## 10. Cloud Functions (if any)

| Function | Trigger | Purpose |
|---|---|---|
| [name] | [Firestore trigger / HTTP] | [what it does] |

---

## 11. Known Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| [risk] | High/Med/Low | [impact] | [mitigation] |
```

---

## 12. MCP TOOL CATALOGUE

Complete list of all 32 MCP tools. All use stdio. None require external services beyond LLM adapter.

### Read Tools (Zero-LLM)
| Tool | Input | Output |
|---|---|---|
| `get_project_context` | none | Full project summary |
| `get_screen_graph` | screen_id | Screen + all dependencies |
| `get_phase_status` | phase | Completion % + blocking issues |
| `get_all_screens` | none | All screens with status |
| `get_dependencies` | screen_id | Required pre-conditions |
| `get_firestore_schema` | none | All collections + rules |
| `get_business_rules` | none | All BR entries |
| `get_state_machine` | entity | Full state machine |
| `get_design_tokens` | none | Design system rules |
| `get_navigation_graph` | none | Full nav graph |

### Validation Tools (Zero-LLM)
| Tool | Input | Output |
|---|---|---|
| `validate_mvvm` | file_path | Violations + fixes |
| `validate_phase` | phase | Phase validation report |
| `validate_firestore_consistency` | none | Consistency violations |
| `validate_state_transitions` | entity, file_path | Missing updates |
| `validate_design_tokens` | file_path | Token violations |
| `validate_naming_conventions` | file_path | Naming violations |

### Generation Tools (LLM-assisted)
| Tool | Input | Output |
|---|---|---|
| `generate_viewmodel` | screen_id | .kt file content |
| `generate_repository` | repository_id | Interface + Impl .kt |
| `generate_datamodel` | model_id | Data class .kt |
| `generate_ui_state` | screen_id | Sealed class .kt |
| `generate_screen_scaffold` | screen_id | Composable .kt |
| `generate_usecase` | usecase_id | UseCase .kt |
| `generate_di_module` | feature_name | Hilt module .kt |
| `generate_nav_route` | screen_id | Nav route .kt |
| `generate_test` | file_path | Test file .kt |

### Bug Forecasting Tools (Zero-LLM detection)
| Tool | Input | Output |
|---|---|---|
| `forecast_bugs` | screen_id | Prioritised bug list |
| `detect_race_conditions` | feature | Race condition risks |
| `detect_orphaned_documents` | none | Consistency gaps |
| `detect_revenue_leaks` | none | Financial integrity risks |
| `audit_production_readiness` | phase | Full pre-launch report |

### Brain Management Tools (Zero-LLM)
| Tool | Input | Output |
|---|---|---|
| `mark_generated` | screen_id, file_path | Updated brain |
| `mark_complete` | screen_id | Updated brain |
| `sync_brain` | none | Sync report |
| `rollback_file` | file_path | Restored file |

---

## 13. TEMPLATE ENGINE SPECIFICATION

### Template Versioning
```
templates/
  v1/
    viewmodel.kt.j2
    repository_interface.kt.j2
    repository_impl.kt.j2
    datamodel.kt.j2
    uistate.kt.j2
    screen_scaffold.kt.j2
    usecase.kt.j2
    di_module.kt.j2
    nav_route.kt.j2
    viewmodel_test.kt.j2
    repository_test.kt.j2
  v2/          ← future Compose version updates
    ...
  active → v1  ← symlink, change to upgrade all templates
```

### Template Maintenance Policy
- Templates are frozen after release
- API/library updates get a new version folder
- Developer chooses active version per project in brain meta
- Old templates remain available — no forced upgrades

### LLM Fill Prompt (deterministic, versioned)

```
prompts/function_fill_v1.txt:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You are a Kotlin Android developer filling function bodies.
Architecture: MVVM + Hilt + Coroutines + Flow + Firebase Firestore

STRICT RULES — never violate:
1. Never import android.content.Context in a ViewModel
2. Never use LiveData — only StateFlow/Flow
3. All Firestore calls must be in viewModelScope.launch or flow{}
4. Catch all exceptions, emit Error state
5. Follow these business rules exactly: {business_rules}

Fill ONLY the function bodies below.
Return ONLY the function implementations.
No class wrapper, no imports, no preamble.

Functions to implement:
{function_signatures}

Business context:
{business_context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 14. CRITICAL GAPS & MITIGATIONS

### Gap 1: Kotlin AST Parsing Fragility
**Problem:** No mature Python Kotlin AST library. Regex breaks on complex files.  
**Mitigation:** 
- Regex + structural heuristics with confidence scoring
- Any file with confidence < 85% flagged for manual review
- `brain review` CLI for interactive resolution
- Edge cases (multiple classes per file, nested classes) handled with fallback heuristics
- Future: optional Gradle KSP plugin for 100% accurate scanning

### Gap 2: Template Staleness on Library Updates
**Problem:** Compose 1.8, Hilt updates break templates silently.  
**Mitigation:**
- Versioned template directories
- `brain check-templates` tool verifies templates compile against current dependencies
- Template version pinned in `PROJECT_BRAIN.json` meta section

### Gap 3: PRD Quality Variance
**Problem:** Vague PRD produces weak brain.  
**Mitigation:**
- PRD completeness scorer blocks parsing if score < 80
- PRD validator gives specific missing section guidance
- Official PRD template (Section 11) ensures coverage

### Gap 4: Brain-Code Drift on Large Codebases
**Problem:** Brain goes stale as developer adds files manually.  
**Mitigation:**
- `brain sync` runs incremental diff against last_synced timestamp
- Git-based change detection (no full rescan)
- Conflict resolution CLI for ambiguous cases
- `brain sync` recommended as pre-commit hook

### Gap 5: Multi-Module Complexity
**Problem:** Cross-module dependencies not captured.  
**Mitigation:**
- Modules defined in brain schema from Phase 1
- `validate_cross_module_deps` tool enforces boundaries
- Shared module concept baked into schema

### Gap 6: No Rollback on Bad Generation
**Problem:** Bad generation corrupts codebase.  
**Mitigation:**
- Every write creates `.brain_backup_{timestamp}` automatically
- `rollback_file` MCP tool + `brain rollback` CLI
- Generation history tracked in brain

### Gap 7: Test Coverage Gap
**Problem:** "Production ready" without tests is incomplete.  
**Mitigation:**
- `generate_test` tool generates test scaffold for any generated file
- Phase completion criteria include test generation
- LLM fills test case descriptions, assertions are scaffolded deterministically

### Gap 8: LLM API Unavailability
**Problem:** LLM down → code generation fails.  
**Mitigation:**
- All read and validation tools work without LLM (P5 principle)
- Generation degrades to template-only with `// TODO: implement` slots
- `generate_viewmodel --no-llm` flag for offline use

---

## 15. WHAT WILL BREAK WHILE BUILDING & PRE-FIXES

These are forecast issues during development of the engine itself.

### Break 1: stdio MCP Transport Complexity
**When:** Phase 2 MCP server setup  
**Problem:** stdio transport requires careful async stream handling. Buffering issues cause silent failures.  
**Pre-fix:** Use the official `mcp` Python package (`pip install mcp`). Do not implement transport manually. The package handles all stream buffering.

### Break 2: Jinja2 Kotlin Template Conflicts
**When:** Phase 4 template engine  
**Problem:** Kotlin uses `${}` for string templates. Jinja2 uses `{{ }}`. Conflict in template files.  
**Pre-fix:** Use Jinja2 with custom delimiters for Kotlin templates:
```python
env = jinja2.Environment(
    block_start_string='[%',
    block_end_string='%]',
    variable_start_string='[[',
    variable_end_string=']]'
)
```

### Break 3: Confidence Score False Positives
**When:** Phase 1 codebase scanner  
**Problem:** Utility files and extension files get misidentified as ViewModels.  
**Pre-fix:** Add file path filter — only scan files matching `*ViewModel.kt`, `*Screen.kt`, `*Repository*.kt` patterns. Skip `*Extensions.kt`, `*Utils.kt`, `*Constants.kt`.

### Break 4: LLM Response Inconsistency in Function Fill
**When:** Phase 4 code generation  
**Problem:** LLM sometimes returns markdown-wrapped code, sometimes adds class wrapper, sometimes adds imports.  
**Pre-fix:** Post-process LLM response before inserting into template:
```python
def clean_llm_function_output(raw: str) -> str:
    # Remove markdown code fences
    raw = re.sub(r'```kotlin|```', '', raw)
    # Remove class wrapper if present
    raw = remove_class_wrapper(raw)
    # Remove import statements (template handles imports)
    raw = remove_import_lines(raw)
    return raw.strip()
```

### Break 5: PROJECT_BRAIN.json Corruption on Concurrent Writes
**When:** Phase 2+ if brain sync runs while MCP server is active  
**Problem:** Two processes write brain simultaneously → JSON corruption.  
**Pre-fix:** File locking:
```python
import fcntl

def save_brain(brain: ProjectBrain, path: str):
    with open(path, 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(brain.dict(), f, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)
```

### Break 6: Claude Code Session Context Limits
**When:** Phase 2 CLAUDE.md integration  
**Problem:** get_project_context() returns too much data for context window.  
**Pre-fix:** Implement tiered context responses:
```python
def get_project_context(detail: str = "summary") -> dict:
    if detail == "summary":
        return brain.get_summary()  # ~500 tokens
    elif detail == "phase":
        return brain.get_current_phase_context()  # ~1000 tokens
    elif detail == "full":
        return brain.get_full_context()  # ~3000 tokens
```

### Break 7: Windows Path Separator Issues
**When:** Phase 1 file scanning on Windows  
**Problem:** Scanner uses Unix paths. Windows uses backslash.  
**Pre-fix:** Always use `pathlib.Path` instead of string path concatenation:
```python
from pathlib import Path
project_root = Path(project_root)  # Handles both OS
```

### Break 8: Git Diff Unavailable
**When:** Phase 6 incremental sync  
**Problem:** Some developers don't use Git or brain sync called before first commit.  
**Pre-fix:** Fallback to timestamp comparison:
```python
def get_changed_files(project_root: str, since: datetime) -> List[Path]:
    try:
        return git_diff_since(since)
    except GitNotAvailableError:
        # Fallback: scan all files modified after timestamp
        return [f for f in scan_all_kotlin_files(project_root) 
                if f.stat().st_mtime > since.timestamp()]
```

---

## 16. NON-GOALS & EXPLICIT EXCLUSIONS

These are intentionally out of scope to prevent scope creep.

| Excluded | Reason |
|---|---|
| iOS / Swift support | Android-only tool. Swift has different MVVM conventions. |
| HTTP/SSE MCP transport | stdio is sufficient, HTTP adds operational complexity |
| Cloud-hosted brain | Brain is local. No cloud sync, no accounts, no SaaS. |
| Real-time file watching | `brain sync` is manual or pre-commit hook. Polling adds complexity. |
| IDE plugin (Android Studio) | MCP server is sufficient. IDE plugin is a separate product. |
| Multi-LLM parallel calls | One LLM adapter active at a time. Parallel calls add cost/complexity. |
| Automatic git commits | Engine never commits code. Developer controls version history. |
| Room / SQLite support | Firestore-first. Room support in future version only. |
| Jetpack Compose Multiplatform | Android only in v1. |

---

## 17. TECH STACK

| Layer | Technology | Reason |
|---|---|---|
| Language | Python 3.11+ | Rapid dev, excellent file I/O, MCP SDK available |
| MCP Framework | `mcp` Python package (official) | Handles stdio transport, tool registry, schema |
| Template Engine | Jinja2 | Mature, powerful, custom delimiters supported |
| Schema Validation | Pydantic v2 | Brain JSON validation, type safety |
| CLI | Click | Simple, readable CLI commands |
| LLM Adapter | httpx (async) | Lightweight HTTP client for Anthropic/OpenAI APIs |
| File Parsing | regex + pathlib | No external Kotlin AST dependency |
| Config | python-dotenv | API key management |
| Testing | pytest | Unit tests for all rule engine logic |
| Packaging | pyproject.toml | `pip install project-brain-engine` |

### Dependencies (requirements.txt)
```
mcp>=1.0.0
jinja2>=3.1.0
pydantic>=2.0.0
click>=8.1.0
httpx>=0.27.0
python-dotenv>=1.0.0
pytest>=8.0.0
pathlib2>=2.3.0
```

---

## 18. BUILD ORDER & MILESTONES

### Why This Order

Each phase delivers **immediate value to running projects**. You never build for weeks with nothing usable.

---

### Phase 1 — Brain Generation (Week 1-2)
**Immediate value:** Never explain your architecture to Claude again.

```
Day 1-2:  PROJECT_BRAIN.json schema (final)
Day 3:    PRD completeness scorer
Day 4-5:  PRD parser (LLM-powered)
Day 6-7:  Codebase scanner (regex-based)
Day 8:    brain CLI tool (init, status, review)
Day 9-10: Test with KPorter and Bigbaagh
```

**Done when:** `brain init --from-prd ./PRD.md` produces valid brain in < 30 seconds

---

### Phase 2 — MCP Server & Read Tools (Week 3)
**Immediate value:** Claude Code has full context from token 1.

```
Day 1-2:  MCP server setup (stdio)
Day 3-5:  All 10 read tools implemented
Day 6:    CLAUDE.md template
Day 7:    Test with Claude Code on KPorter
```

**Done when:** Claude Code session starts with full project context via get_project_context()

---

### Phase 3 — Rule Engine & Validation (Week 4)
**Immediate value:** MVVM violations caught before they reach production.

```
Day 1-2:  Rule definitions (20 rules, A/B/C)
Day 3-4:  Kotlin file analyzer (regex-based)
Day 5:    Validation tools (validate_mvvm, validate_phase)
Day 6-7:  Test against KPorter existing files
```

**Done when:** `validate_mvvm` correctly identifies all CLASS_A violations in test files

---

### Phase 4 — Code Generation (Week 5-6)
**Immediate value:** Generate production-ready .kt files in seconds.

```
Week 5 Day 1-2:  Template engine + 5 core templates
Week 5 Day 3-4:  LLM adapter (Claude API)
Week 5 Day 5:    Self-healing loop
Week 6 Day 1-2:  All 9 generation tools
Week 6 Day 3:    Rollback system
Week 6 Day 4-5:  Test generation of KPorter screens
```

**Done when:** `generate_viewmodel("OrderTrackingScreen")` produces compliant .kt file, zero CLASS_A violations

---

### Phase 5 — Predictive Bug Engine (Week 7-8)
**Immediate value:** Production bugs forecasted before writing the screen.

```
Week 7 Day 1-2:  State transition bug detector
Week 7 Day 3-4:  Firestore consistency detector
Week 7 Day 5:    Race condition detector
Week 8 Day 1-2:  Revenue integrity detector
Week 8 Day 3-4:  Edge case simulator
Week 8 Day 5:    audit_production_readiness tool
```

**Done when:** `forecast_bugs("RideCompletionScreen")` correctly predicts porter isAvailable reset failure

---

### Phase 6 — Self-Healing & Sync (Week 9-10)
**Immediate value:** Brain never goes stale.

```
Week 9:   Incremental sync + conflict resolution
Week 10:  Multi-module support + final polish
```

**Done when:** `brain sync` correctly detects and integrates 5 newly added screens without full rescan

---

### Total Timeline: 10 weeks
### Parallel to active projects: Yes — each week produces usable tools

---

## 19. SUCCESS METRICS

| Metric | Target |
|---|---|
| Brain generation time (from PRD) | < 30 seconds |
| Brain generation time (from codebase scan) | < 60 seconds for 50 files |
| Codebase scan confidence > 85% | ≥ 90% of files |
| Code generation compliance rate | 100% zero CLASS_A violations |
| Self-healing success rate | ≥ 95% within 3 attempts |
| False positive rate (bug forecasting) | < 10% |
| Claude Code context load time | < 2 seconds |
| Brain sync time (incremental) | < 5 seconds |
| LLM adapter swap time | < 1 minute (config change only) |

---

## APPENDIX A: FILE STRUCTURE

```
project-brain-engine/
├── project_brain/
│   ├── __init__.py
│   ├── server.py              ← MCP server entry point
│   ├── brain/
│   │   ├── manager.py         ← Brain read/write/sync
│   │   ├── schema.py          ← Pydantic models
│   │   └── validator.py       ← Schema validation
│   ├── engines/
│   │   ├── rule_engine.py     ← MVVM rule checking
│   │   ├── template_engine.py ← Jinja2 template rendering
│   │   ├── state_engine.py    ← State transition validation
│   │   └── bug_engine.py      ← Predictive bug detection
│   ├── generators/
│   │   ├── brain_generator.py ← PRD + codebase → brain
│   │   ├── prd_parser.py      ← LLM-powered PRD parsing
│   │   └── codebase_scanner.py← Zero-LLM file scanning
│   ├── tools/
│   │   ├── registry.py        ← All MCP tool definitions
│   │   ├── read_tools.py
│   │   ├── validation_tools.py
│   │   ├── generation_tools.py
│   │   ├── bug_tools.py
│   │   └── management_tools.py
│   ├── llm/
│   │   ├── adapter.py         ← LLM provider abstraction
│   │   ├── claude.py          ← Anthropic implementation
│   │   └── openai.py          ← OpenAI implementation
│   └── cli/
│       └── commands.py        ← Click CLI
├── templates/
│   └── v1/
│       ├── viewmodel.kt.j2
│       ├── repository_interface.kt.j2
│       ├── repository_impl.kt.j2
│       ├── datamodel.kt.j2
│       ├── uistate.kt.j2
│       ├── screen_scaffold.kt.j2
│       ├── usecase.kt.j2
│       ├── di_module.kt.j2
│       ├── nav_route.kt.j2
│       └── viewmodel_test.kt.j2
├── prompts/
│   ├── prd_extraction_v1.txt
│   └── function_fill_v1.txt
├── rules/
│   ├── mvvm_rules.py
│   ├── firestore_rules.py
│   └── naming_rules.py
├── tests/
│   ├── test_rule_engine.py
│   ├── test_scanner.py
│   ├── test_generation.py
│   └── fixtures/
│       ├── sample_viewmodel.kt
│       ├── sample_repository.kt
│       └── sample_prd.md
├── PRD_TEMPLATE.md            ← The official PRD template
├── pyproject.toml
├── README.md
└── .env.example               ← ANTHROPIC_API_KEY=
```

---

## APPENDIX B: QUICK START (FUTURE README)

```bash
# Install
pip install project-brain-engine

# New project
brain init --from-prd ./PRD.md
brain serve

# Add to claude_desktop_config.json:
{
  "mcpServers": {
    "project-brain": {
      "command": "brain",
      "args": ["serve"],
      "env": { "BRAIN_PATH": "./PROJECT_BRAIN.json" }
    }
  }
}

# Existing project
brain init --from-code ./app/src/main/kotlin
brain review        # resolve flagged items
brain serve

# Daily workflow
brain sync          # keep brain updated
brain status        # see phase progress
```

---

*PRD Version 1.0 — Complete*  
*Next action: Begin Phase 1 — Brain JSON schema implementation*
