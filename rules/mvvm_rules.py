"""Deterministic MVVM rule definitions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Literal, Protocol


Severity = Literal["CLASS_A", "CLASS_B", "CLASS_C"]
FileTypeName = Literal["ViewModel", "Repository", "Screen", "DataModel", "Unknown", "Any"]


class KotlinAnalysisProtocol(Protocol):
    content: str
    imports: list[str]
    file_type: str

    def has_import_containing(self, needle: str) -> bool: ...

    def composable_has_business_logic(self) -> bool: ...

    def stateflows_have_correct_visibility(self) -> bool: ...

    def repository_has_interface(self) -> bool: ...

    def has_direct_firestore_call(self) -> bool: ...

    def line_for_pattern(self, pattern: str) -> int | None: ...


@dataclass(frozen=True)
class MVVMRule:
    id: str
    description: str
    severity: Severity
    file_types: tuple[FileTypeName, ...]
    check: Callable[[KotlinAnalysisProtocol], bool]
    fix: str
    line_finder: Callable[[KotlinAnalysisProtocol], int | None]


def line(pattern: str) -> Callable[[KotlinAnalysisProtocol], int | None]:
    return lambda analysis: analysis.line_for_pattern(pattern)


MVVM_RULES: list[MVVMRule] = [
    MVVMRule(
        id="A001",
        description="ViewModel must not import android.content.Context",
        severity="CLASS_A",
        file_types=("ViewModel",),
        check=lambda analysis: "android.content.Context" not in analysis.imports,
        fix="Remove Context import. Use Application context via @ApplicationContext if needed.",
        line_finder=line(r"import\s+android\.content\.Context"),
    ),
    MVVMRule(
        id="A002",
        description="ViewModel must not import androidx.compose",
        severity="CLASS_A",
        file_types=("ViewModel",),
        check=lambda analysis: not analysis.has_import_containing("androidx.compose"),
        fix="No Compose imports in ViewModel. Move UI logic to Composable.",
        line_finder=line(r"import\s+androidx\.compose"),
    ),
    MVVMRule(
        id="A003",
        description="Business logic must not be in @Composable function",
        severity="CLASS_A",
        file_types=("Screen",),
        check=lambda analysis: not analysis.composable_has_business_logic(),
        fix="Extract business logic to ViewModel function.",
        line_finder=line(r"(@Composable|\.collection\s*\(|\.addSnapshotListener\s*\(|\.launch\s*\{)"),
    ),
    MVVMRule(
        id="A004",
        description="StateFlow must be private mutable, public immutable",
        severity="CLASS_A",
        file_types=("ViewModel",),
        check=lambda analysis: analysis.stateflows_have_correct_visibility(),
        fix="Use: private val _state = MutableStateFlow; val state = _state.asStateFlow()",
        line_finder=line(r"(MutableStateFlow|StateFlow<)"),
    ),
    MVVMRule(
        id="A005",
        description="Repository must have interface",
        severity="CLASS_A",
        file_types=("Repository",),
        check=lambda analysis: analysis.repository_has_interface(),
        fix="Create I{RepositoryName} interface or a matching Repository interface.",
        line_finder=line(r"class\s+\w*Repository"),
    ),
    MVVMRule(
        id="B001",
        description="ViewModel public functions should update StateFlow instead of returning data directly",
        severity="CLASS_B",
        file_types=("ViewModel",),
        check=lambda analysis: "fun " not in analysis.content or "StateFlow" in analysis.content,
        fix="Expose screen data through StateFlow-backed UI state.",
        line_finder=line(r"fun\s+\w+\s*\("),
    ),
    MVVMRule(
        id="B002",
        description="Repository methods should be suspend or return Flow",
        severity="CLASS_B",
        file_types=("Repository",),
        check=lambda analysis: not bool(re.search(r"fun\s+\w+\s*\([^)]*\)\s*:\s*(?!Flow|Unit)", analysis.content)),
        fix="Use suspend functions for one-shot work or Flow for streams.",
        line_finder=line(r"fun\s+\w+\s*\("),
    ),
    MVVMRule(
        id="B003",
        description="Firestore data class should use @Keep annotation",
        severity="CLASS_B",
        file_types=("DataModel",),
        check=lambda analysis: "data class" not in analysis.content or "@Keep" in analysis.content,
        fix="Add @Keep to Firestore model classes.",
        line_finder=line(r"data\s+class"),
    ),
    MVVMRule(
        id="B004",
        description="UI state sealed class should include Loading state",
        severity="CLASS_B",
        file_types=("Any",),
        # v2 enriched brains use data-class UiState with isLoading: Boolean — skip for those
        check=lambda analysis: (
            "UiState" not in analysis.content
            or "Loading" in analysis.content
            or (bool(re.search(r"@Immutable", analysis.content)) and bool(re.search(r"data class \w+UiState", analysis.content)))
        ),
        fix="Add a Loading state to the UI state model (or use isLoading: Boolean field for data-class UiState).",
        line_finder=line(r"UiState"),
    ),
    MVVMRule(
        id="B005",
        description="Composable should avoid hardcoded user-facing strings",
        severity="CLASS_B",
        file_types=("Screen",),
        check=lambda analysis: "Text(\"" not in analysis.content,
        fix="Use stringResource for user-facing strings.",
        line_finder=line(r"Text\(\""),
    ),
    MVVMRule(
        id="B006",
        description="ViewModel should not call Firestore directly",
        severity="CLASS_B",
        file_types=("ViewModel",),
        check=lambda analysis: not analysis.has_direct_firestore_call(),
        fix="Move Firestore access behind Repository.",
        line_finder=line(r"\.collection\s*\("),
    ),
    MVVMRule(
        id="C001",
        description="Function longer than 30 lines",
        severity="CLASS_C",
        file_types=("Any",),
        check=lambda analysis: not has_long_function(analysis.content, 30),
        fix="Split long functions into smaller private helpers.",
        line_finder=line(r"fun\s+\w+\s*\("),
    ),
    MVVMRule(
        id="C002",
        description="Public function missing KDoc comment",
        severity="CLASS_C",
        file_types=("Any",),
        check=lambda analysis: not public_function_missing_kdoc(analysis.content),
        fix="Add concise KDoc to public functions.",
        line_finder=line(r"^\s*fun\s+\w+\s*\("),
    ),
    MVVMRule(
        id="C003",
        description="Magic number in business logic",
        severity="CLASS_C",
        file_types=("Any",),
        check=lambda analysis: not bool(re.search(r"(?<![\w.])(?:[2-9]\d{1,}|1\d{2,})(?![\w.])", analysis.content)),
        fix="Replace magic numbers with named constants.",
        line_finder=line(r"(?<![\w.])(?:[2-9]\d{1,}|1\d{2,})(?![\w.])"),
    ),
    MVVMRule(
        id="C004",
        description="TODO comment should be tracked in project gaps",
        severity="CLASS_C",
        file_types=("Any",),
        check=lambda analysis: "TODO" not in analysis.content,
        fix="Move TODO context to docs/STUBS_AND_TODO.md or resolve it.",
        line_finder=line(r"TODO"),
    ),
]


def has_long_function(content: str, max_lines: int) -> bool:
    lines = content.splitlines()
    for index, text in enumerate(lines):
        if "fun " not in text:
            continue
        depth = 0
        seen_body = False
        for inner_index in range(index, len(lines)):
            depth += lines[inner_index].count("{")
            if "{" in lines[inner_index]:
                seen_body = True
            depth -= lines[inner_index].count("}")
            if seen_body and depth <= 0:
                if inner_index - index + 1 > max_lines:
                    return True
                break
    return False


def public_function_missing_kdoc(content: str) -> bool:
    lines = content.splitlines()
    for index, text in enumerate(lines):
        stripped = text.strip()
        if not stripped.startswith("fun "):
            continue
        previous = "\n".join(lines[max(0, index - 3) : index])
        if "/**" not in previous:
            return True
    return False
