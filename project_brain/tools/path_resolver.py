"""Android output path resolver.

Given an output_base (e.g., ``app/src/main/kotlin``), derives the full
on-disk path for each generated artifact so that it lands exactly where
Android / Gradle expects it — matching the package declaration inside
the file.

Usage from generation tools::

    from project_brain.tools.path_resolver import resolve_android_path
    path = resolve_android_path(output_base, brain, "viewmodel", "PhoneEntryScreen")
    # → app/src/main/kotlin/com/bigbaagh/app/presentation/phone_entry/PhoneEntryViewModel.kt
"""

from __future__ import annotations

import re
from pathlib import Path

from project_brain.brain.schema import ProjectBrain


def resolve_android_path(
    output_base: str,
    brain: ProjectBrain,
    artifact_type: str,
    identifier: str,
) -> str:
    """Return the full output path for one artifact.

    Args:
        output_base: Root of the Kotlin source set, e.g.
            ``app/src/main/kotlin`` or ``app/src/test/kotlin`` for tests.
            When *None* is passed the caller must handle path resolution itself.
        brain: Loaded ``ProjectBrain`` (used for ``package_name``).
        artifact_type: One of ``viewmodel``, ``ui_state``, ``scaffold``,
            ``repository_interface``, ``repository_impl``, ``usecase``,
            ``datamodel``, ``di_module``, ``nav_route``, ``test``.
        identifier: screen_id, repository_id, usecase_name, model_id, or
            feature_name depending on ``artifact_type``.

    Returns:
        Absolute-or-relative path string the file should be written to.
    """
    pkg = (brain.meta.package_name or "com.example.app").strip()
    pkg_path = pkg.replace(".", "/")
    base = Path(output_base)

    artifact_type = artifact_type.lower()

    if artifact_type == "viewmodel":
        feature = _feature_name(identifier)
        filename = identifier.replace("Screen", "ViewModel") + ".kt"
        return str(base / pkg_path / "presentation" / feature / filename)

    if artifact_type in ("ui_state", "uistate"):
        feature = _feature_name(identifier)
        filename = identifier.replace("Screen", "") + "UiState.kt"
        return str(base / pkg_path / "presentation" / feature / filename)

    if artifact_type in ("scaffold", "screen"):
        feature = _feature_name(identifier)
        filename = identifier + ".kt"
        return str(base / pkg_path / "presentation" / feature / filename)

    if artifact_type in ("events", "uieffect"):
        feature = _feature_name(identifier)
        filename = identifier.replace("Screen", "") + "UiEffect.kt"
        return str(base / pkg_path / "presentation" / feature / filename)

    if artifact_type == "nav_route":
        filename = identifier.replace("Screen", "") + "Route.kt"
        return str(base / pkg_path / "navigation" / filename)

    if artifact_type == "repository_interface":
        filename = identifier + ".kt"
        return str(base / pkg_path / "domain" / "repository" / filename)

    if artifact_type == "repository_impl":
        impl_name = identifier if identifier.endswith("Impl") else identifier + "Impl"
        filename = impl_name + ".kt"
        return str(base / pkg_path / "data" / "repository" / filename)

    if artifact_type == "usecase":
        filename = identifier + ".kt"
        return str(base / pkg_path / "domain" / "usecase" / filename)

    if artifact_type == "datamodel":
        filename = identifier + ".kt"
        return str(base / pkg_path / "data" / "model" / filename)

    if artifact_type == "di_module":
        module_name = _title(identifier) + "Module"
        filename = module_name + ".kt"
        return str(base / pkg_path / "di" / filename)

    if artifact_type == "test":
        feature = _feature_name(identifier)
        filename = identifier.replace("Screen", "ViewModel") + "Test.kt"
        return str(base / pkg_path / "presentation" / feature / filename)

    raise ValueError(f"Unknown artifact_type: {artifact_type!r}")


def resolve_all_paths(output_base: str, brain: ProjectBrain) -> dict[str, str]:
    """Return a mapping of every artifact the pipeline will generate to its
    correct on-disk path.  Useful for displaying the expected file tree before
    generation starts.

    The returned dict keys are ``"{screen_or_repo_id}/{artifact_type}"``.
    """
    paths: dict[str, str] = {}
    src = output_base
    test_base = _test_base(output_base)

    for screen in brain.screens:
        sid = screen.id
        paths[f"{sid}/viewmodel"] = resolve_android_path(src, brain, "viewmodel", sid)
        paths[f"{sid}/ui_state"] = resolve_android_path(src, brain, "ui_state", sid)
        paths[f"{sid}/scaffold"] = resolve_android_path(src, brain, "scaffold", sid)
        paths[f"{sid}/nav_route"] = resolve_android_path(src, brain, "nav_route", sid)
        paths[f"{sid}/test"] = resolve_android_path(test_base, brain, "test", sid)

    for repo in brain.repositories:
        rid = repo.id
        paths[f"{rid}/interface"] = resolve_android_path(src, brain, "repository_interface", rid)
        paths[f"{rid}/impl"] = resolve_android_path(src, brain, "repository_impl", rid)

    for uc in brain.use_cases if hasattr(brain, "use_cases") else []:
        paths[f"{uc.name}/usecase"] = resolve_android_path(src, brain, "usecase", uc.name)

    for model in brain.data_models:
        if model.firestore_collection:  # only persist-able models get a data class file
            paths[f"{model.id}/datamodel"] = resolve_android_path(src, brain, "datamodel", model.id)

    seen_features: set[str] = set()
    for screen in brain.screens:
        feat = _feature_name(screen.id)
        if feat not in seen_features:
            seen_features.add(feat)
            paths[f"{feat}/di_module"] = resolve_android_path(src, brain, "di_module", feat)

    return paths


# ── helpers ────────────────────────────────────────────────────────────────────

def _feature_name(screen_id: str) -> str:
    return _snake(screen_id.replace("Screen", ""))


def _snake(value: str) -> str:
    text = re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "feature"


def _title(value: str) -> str:
    return "".join(w.capitalize() for w in re.split(r"[_\s]+", value))


def _test_base(src_base: str) -> str:
    """Swap ``src/main/kotlin`` → ``src/test/kotlin`` for test output."""
    p = src_base.replace("\\", "/")
    if "src/main/kotlin" in p:
        return p.replace("src/main/kotlin", "src/test/kotlin")
    return src_base + "_test"
