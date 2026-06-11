"""Phase 3 zero-LLM validation tools."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from project_brain.brain.manager import BrainManager
from project_brain.brain.schema import ProjectBrain
from project_brain.engines.rule_engine import MVVMValidationEngine


def validate_mvvm(file_path: str) -> dict[str, Any]:
    """Validate a Kotlin file for deterministic MVVM rule compliance."""

    return MVVMValidationEngine().validate_file(file_path).to_dict()


def validate_phase(phase: int, brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Validate all known files for a brain phase."""

    return MVVMValidationEngine().validate_phase(phase, brain_path).to_dict()


def validate_firestore_consistency(brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Check brain business rules against Firestore consistency declarations."""

    brain = BrainManager(brain_path).load()
    return validate_firestore_consistency_brain(brain)


def validate_firestore_consistency_brain(brain: ProjectBrain) -> dict[str, Any]:
    collection_rules = " ".join(
        rule for collection in brain.firestore_schema.collections for rule in collection.consistency_rules
    )
    violations = []
    for rule in brain.business_rules:
        if rule.required_updates and not all(update in collection_rules for update in rule.required_updates):
            violations.append(
                {
                    "rule_id": rule.id,
                    "severity": rule.missing_any or "CLASS_A",
                    "description": f"Business rule {rule.id} has required updates not reflected in Firestore consistency rules.",
                    "missing_updates": [update for update in rule.required_updates if update not in collection_rules],
                }
            )
    return {"violations": violations, "violation_count": len(violations), "consistent": not violations}


def validate_state_transitions(entity: str, file_path: str, brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Check that a file contains required updates for an entity's state transitions."""

    brain = BrainManager(brain_path).load()
    return validate_state_transitions_brain(entity, file_path, brain)


def validate_state_transitions_brain(entity: str, file_path: str, brain: ProjectBrain) -> dict[str, Any]:
    content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    machine = next((item for item in brain.state_machines if item.entity.lower() == entity.lower()), None)
    if not machine:
        return {"entity": entity, "violations": [{"severity": "CLASS_A", "description": f"State machine not found: {entity}"}]}
    violations = []
    for transition in machine.transitions:
        missing = [update for update in transition.required_firestore_updates if not update_present(update, content)]
        if missing:
            violations.append(
                {
                    "transition": {"from": transition.from_state, "to": transition.to},
                    "severity": transition.missing_any or "CLASS_A",
                    "missing_updates": missing,
                    "recommended_implementation": transition.recommended_implementation,
                }
            )
    return {"entity": machine.entity, "violations": violations, "valid": not violations}


def validate_design_tokens(file_path: str, brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Check for disallowed design-token usage from brain token rules."""

    brain = BrainManager(brain_path).load()
    return validate_design_tokens_brain(file_path, brain)


def validate_design_tokens_brain(file_path: str, brain: ProjectBrain) -> dict[str, Any]:
    content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    violations = []
    for rule in brain.design_system.token_rules:
        match = re.search(r"Use\s+([A-Za-z0-9_.]+)\s+not\s+([A-Za-z0-9_.]+)", rule, re.I)
        if match and match.group(2) in content:
            violations.append(
                {
                    "severity": "CLASS_B",
                    "description": rule,
                    "found": match.group(2),
                    "expected": match.group(1),
                }
            )
        required = re.search(r"must\s+use\s+([A-Za-z0-9_.]+)", rule, re.I)
        if required and required.group(1) not in content:
            violations.append(
                {
                    "severity": "CLASS_B",
                    "description": rule,
                    "missing": required.group(1),
                }
            )
    return {"file": file_path, "violations": violations, "valid": not violations}


def validate_naming_conventions(file_path: str, brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Check Kotlin naming conventions against brain/MVVM naming."""

    brain = BrainManager(brain_path).load()
    return validate_naming_conventions_brain(file_path, brain)


def validate_naming_conventions_brain(file_path: str, brain: ProjectBrain) -> dict[str, Any]:
    path = Path(file_path)
    content = path.read_text(encoding="utf-8", errors="ignore")
    violations = []
    class_match = re.search(r"\b(?:data\s+)?class\s+(\w+)|\binterface\s+(\w+)", content)
    class_name = next((group for group in class_match.groups() if group), None) if class_match else None
    if class_name and path.stem != class_name:
        violations.append(
            {
                "severity": "CLASS_B",
                "description": "Kotlin file name should match the primary class or interface name.",
                "expected": f"{class_name}.kt",
                "actual": path.name,
            }
        )
    if class_name and class_name.endswith("ViewModel"):
        expected_screen = class_name.replace("ViewModel", "Screen")
        if not any(screen.id == expected_screen for screen in brain.screens):
            violations.append(
                {
                    "severity": "CLASS_B",
                    "description": "ViewModel name should map to a known Screen.",
                    "expected_screen": expected_screen,
                }
            )
    return {"file": file_path, "violations": violations, "valid": not violations}


def update_present(update: str, content: str) -> bool:
    compact_update = re.sub(r"[^A-Za-z0-9_]+", "", update).lower()
    compact_content = re.sub(r"[^A-Za-z0-9_]+", "", content).lower()
    return compact_update in compact_content or all(part.lower() in compact_content for part in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", update))


# ── Phase 5+: validate_generation ───────────────────────────────────────────


def validate_generation(
    feature_id: str | None = None,
    phase: int | None = None,
    brain_path: str = "PROJECT_BRAIN.json",
) -> dict[str, Any]:
    """Compare generated files against Brain spec + ROADMAP.md + source PRD.

    Returns a per-screen completeness report with three verdict columns:
      brain_match    — generated functions/methods match brain spec
      roadmap_match  — generation_status flags are all set for this screen
      prd_match      — screen name referenced in PRD text (if PRD path known)
    """
    brain = BrainManager(brain_path).load()
    return validate_generation_brain(brain, feature_id=feature_id, phase=phase, brain_path=Path(brain_path))


def validate_generation_brain(
    brain: ProjectBrain,
    feature_id: str | None = None,
    phase: int | None = None,
    brain_path: Path | None = None,
) -> dict[str, Any]:
    # Determine which screens to check
    screen_ids: list[str]
    if feature_id:
        feature = next((f for f in brain.features if f.id == feature_id), None)
        screen_ids = feature.screens if feature else []
    elif phase is not None:
        p = next((p for p in brain.phases if p.number == phase), None)
        screen_ids = p.screens if p else []
    else:
        screen_ids = [s.id for s in brain.screens]

    # Load PRD text if available
    prd_text = _load_prd(brain_path)

    screen_reports: list[dict[str, Any]] = []
    total_score = 0
    max_score = 0

    for sid in screen_ids:
        report = _check_screen(sid, brain, prd_text)
        screen_reports.append(report)
        total_score += report["component_score"]
        max_score += report["component_max"]

    completeness_pct = int(100 * total_score / max_score) if max_score else 0
    return {
        "feature_id": feature_id,
        "phase": phase,
        "completeness_pct": completeness_pct,
        "screen_count": len(screen_ids),
        "screens": screen_reports,
    }


def _check_screen(screen_id: str, brain: ProjectBrain, prd_text: str | None) -> dict[str, Any]:
    screen = next((s for s in brain.screens if s.id == screen_id), None)
    vm = next((v for v in brain.viewmodels if v.id == (screen.viewmodel if screen else None)), None)
    repo = next((r for r in brain.repositories if r.id == (screen.repository if screen else None)), None)

    # ── ROADMAP check ────────────────────────────────────────────────
    gen_status = next((gs for gs in brain.generation_status if gs.screen_id == screen_id), None)
    roadmap_flags: dict[str, bool] = {}
    if gen_status:
        c = gen_status.components
        roadmap_flags = {
            "viewmodel": c.viewmodel, "ui_state": c.ui_state,
            "repository": c.repository, "scaffold": c.scaffold,
            "di_module": c.di_module, "nav_route": c.nav_route,
            "tests": c.tests, "validated": c.validated,
        }
    roadmap_match = bool(roadmap_flags) and all(roadmap_flags.values())

    # ── Brain spec check (function/method presence in generated files) ─
    function_coverage: dict[str, str] = {}
    vm_file = _find_generated_file(screen_id, "viewmodel", brain)
    if vm and vm_file:
        content = vm_file.read_text(encoding="utf-8", errors="ignore")
        actual_fns = set(re.findall(r"\bfun\s+([a-z][A-Za-z0-9_]*)\s*\(", content))
        for fn in vm.functions:
            if fn.name in actual_fns:
                body_start = content.find(f"fun {fn.name}(")
                snippet = content[body_start : body_start + 150] if body_start != -1 else ""
                status = "TODO_STUB" if "// TODO" in snippet else "MATCH"
            else:
                status = "MISSING"
            function_coverage[fn.name] = status

    repo_coverage: dict[str, str] = {}
    repo_file = _find_generated_file(screen_id, "repository", brain)
    if repo and repo_file:
        content = repo_file.read_text(encoding="utf-8", errors="ignore")
        actual_fns = set(re.findall(r"\bfun\s+([a-z][A-Za-z0-9_]*)\s*\(", content))
        for m in repo.methods:
            repo_coverage[m.name] = "MATCH" if m.name in actual_fns else "MISSING"

    brain_match = (
        bool(function_coverage)
        and all(v in ("MATCH", "TODO_STUB") for v in function_coverage.values())
        and all(v == "MATCH" for v in repo_coverage.values())
    )

    # ── PRD check (screen name appears in PRD text) ──────────────────
    prd_match: bool | None = None
    if prd_text:
        prd_match = screen_id.replace("Screen", "") in prd_text or screen_id in prd_text

    # ── Score (out of 10) ─────────────────────────────────────────────
    component_score = 0
    component_max = 10
    if roadmap_flags:
        component_score += sum(1 for v in roadmap_flags.values() if v)  # up to 8
    if function_coverage:
        matched = sum(1 for v in function_coverage.values() if v == "MATCH")
        component_score += int(2 * matched / len(function_coverage))  # up to 2

    return {
        "screen_id": screen_id,
        "brain_match": brain_match,
        "roadmap_match": roadmap_match,
        "prd_match": prd_match,
        "roadmap_flags": roadmap_flags,
        "function_coverage": function_coverage,
        "repo_coverage": repo_coverage,
        "component_score": component_score,
        "component_max": component_max,
    }


def _find_generated_file(screen_id: str, component: str, brain: ProjectBrain) -> Path | None:
    """Find the output_path for a given screen + component from generation_history."""
    template_hints = {
        "viewmodel": "viewmodel.kt.j2",
        "repository": "repository_impl.kt.j2",
        "scaffold": "screen_scaffold.kt.j2",
        "ui_state": "uistate.kt.j2",
    }
    hint = template_hints.get(component, "")
    for entry in reversed(brain.generation_history):
        if entry.target == screen_id or entry.target == screen_id.replace("Screen", ""):
            if hint and hint not in entry.tool:
                continue
            if entry.output_path:
                p = Path(entry.output_path)
                if p.exists():
                    return p
    return None


# ── Phase 7: audit_brain ─────────────────────────────────────────────────────


def audit_brain(brain_path: str = "PROJECT_BRAIN.json") -> dict[str, Any]:
    """Load brain from path and run integrity audit."""
    brain = BrainManager(brain_path).load()
    return audit_brain_instance(brain)


def audit_brain_instance(brain: ProjectBrain) -> dict[str, Any]:
    """Pre-generation brain integrity audit (zero-LLM).

    Checks reference integrity, nav circular deps, feature completeness,
    and business rule coverage.  Returns generation_allowed=False if any
    critical issue is found or score < 60.
    """
    critical: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    vm_ids = {v.id for v in brain.viewmodels}
    repo_ids = {r.id for r in brain.repositories}
    screen_ids = {s.id for s in brain.screens}
    route_ids = {r.id for r in brain.navigation_graph.routes}
    rule_ids = {r.id for r in brain.business_rules}

    # ── 1. Reference integrity ─────────────────────────────────────────
    for screen in brain.screens:
        if screen.viewmodel and screen.viewmodel not in vm_ids:
            critical.append({
                "check": "broken_reference",
                "message": f"Screen '{screen.id}' → ViewModel '{screen.viewmodel}' not found",
            })
        if screen.repository and screen.repository not in repo_ids:
            critical.append({
                "check": "broken_reference",
                "message": f"Screen '{screen.id}' → Repository '{screen.repository}' not found",
            })

    for vm in brain.viewmodels:
        if vm.repository and vm.repository not in repo_ids:
            critical.append({
                "check": "broken_reference",
                "message": f"ViewModel '{vm.id}' → Repository '{vm.repository}' not found",
            })

    # ── 2. Navigation integrity ────────────────────────────────────────
    reachable: set[str] = set()
    for route in brain.navigation_graph.routes:
        for dest in route.next:
            reachable.add(dest)
            if dest not in route_ids and dest not in screen_ids:
                critical.append({
                    "check": "dead_nav_route",
                    "message": f"Nav route '{route.id}' → unknown destination '{dest}'",
                })

    # Circular dep via DFS
    adj: dict[str, list[str]] = {r.id: list(r.next) for r in brain.navigation_graph.routes}
    visited: set[str] = set()
    in_stack: set[str] = set()
    cycle_found = False

    def _has_cycle(node: str) -> bool:
        visited.add(node)
        in_stack.add(node)
        for nb in adj.get(node, []):
            if nb not in visited:
                if _has_cycle(nb):
                    return True
            elif nb in in_stack:
                return True
        in_stack.discard(node)
        return False

    for node in list(adj):
        if node not in visited and not cycle_found:
            if _has_cycle(node):
                critical.append({
                    "check": "circular_dependency",
                    "message": f"Circular navigation dependency detected from '{node}'",
                })
                cycle_found = True

    # Orphaned nav nodes (declared but never reachable and not start_destination)
    start = brain.navigation_graph.start_destination
    for route in brain.navigation_graph.routes:
        if route.id != start and route.id not in reachable and route_ids:
            warnings.append({
                "check": "orphaned_nav_node",
                "message": f"Nav route '{route.id}' is unreachable from any other route",
            })

    # ── 3. Feature / roadmap consistency ──────────────────────────────
    for feature in brain.features:
        for sid in feature.screens:
            if sid not in screen_ids:
                critical.append({
                    "check": "missing_screen",
                    "message": f"Feature '{feature.id}' references screen '{sid}' not in brain.screens",
                })
        if not feature.screens:
            warnings.append({
                "check": "empty_feature",
                "message": f"Feature '{feature.id}' has no screens",
            })

    for phase in brain.phases:
        for sid in phase.screens:
            if sid not in screen_ids:
                warnings.append({
                    "check": "roadmap_mismatch",
                    "message": f"Phase {phase.number} references screen '{sid}' not in brain.screens",
                })

    # ── 4. Screen completeness ─────────────────────────────────────────
    for screen in brain.screens:
        if not screen.viewmodel:
            warnings.append({
                "check": "missing_viewmodel",
                "message": f"Screen '{screen.id}' has no ViewModel declared",
            })
        if not screen.repository:
            warnings.append({
                "check": "missing_repository",
                "message": f"Screen '{screen.id}' has no Repository declared",
            })

    # ── 5. Business rule coverage ──────────────────────────────────────
    covered: set[str] = set()
    for vm in brain.viewmodels:
        for fn in vm.functions:
            if fn.business_rule and fn.business_rule in rule_ids:
                covered.add(fn.business_rule)
    for sm in brain.state_machines:
        for t in sm.transitions:
            impl = t.recommended_implementation or ""
            for rid in rule_ids:
                if rid in impl:
                    covered.add(rid)

    for rid in rule_ids - covered:
        warnings.append({
            "check": "uncovered_business_rule",
            "message": f"Business rule '{rid}' not wired to any ViewModel function or state machine",
        })

    # ── 6. Per-feature scores ──────────────────────────────────────────
    feature_scores: dict[str, int] = {}
    for feature in brain.features:
        f_screens = set(feature.screens)
        f_crit = sum(
            1 for i in critical
            if feature.id in i["message"] or any(s in i["message"] for s in f_screens)
        )
        f_warn = sum(
            1 for w in warnings
            if feature.id in w["message"] or any(s in w["message"] for s in f_screens)
        )
        feature_scores[feature.id] = max(0, 100 - f_crit * 15 - f_warn * 5)

    # ── 7. Aggregate score & gate ──────────────────────────────────────
    score = max(0, 100 - len(critical) * 10 - len(warnings) * 3)
    blocking_checks = {"broken_reference", "circular_dependency", "missing_screen"}
    has_blocker = any(i["check"] in blocking_checks for i in critical)
    generation_allowed = not has_blocker and score >= 60

    return {
        "status": "PASS" if generation_allowed else "FAIL",
        "score": score,
        "critical_issues": critical,
        "warnings": warnings,
        "feature_scores": feature_scores,
        "generation_allowed": generation_allowed,
        "summary": {
            "screens": len(brain.screens),
            "viewmodels": len(brain.viewmodels),
            "repositories": len(brain.repositories),
            "business_rules": len(rule_ids),
            "covered_rules": len(covered),
            "critical_count": len(critical),
            "warning_count": len(warnings),
        },
    }


def _load_prd(brain_path: Path | None) -> str | None:
    """Try to load the source PRD from the directory containing the brain file."""
    if brain_path is None:
        return None
    parent = brain_path.parent
    for candidate in sorted(parent.glob("*.md")):
        if candidate.name.lower().startswith(("prd", "enriched", "product")):
            return candidate.read_text(encoding="utf-8", errors="ignore")
    return None
