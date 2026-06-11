"""Click commands for Phase 1 brain generation."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from project_brain.brain.manager import BrainManager
from project_brain.generators.brain_generator import BrainGenerator
from project_brain.generators.prd_parser import IncompletePRDError
from project_brain.generators.prd_scorer import PRDCompletenessScorer


@click.group()
def cli() -> None:
    """Project Brain Engine CLI."""


@cli.command("enrich-prd")
@click.argument("prd_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--output", "-o", type=click.Path(dir_okay=False, path_type=Path), default=None, help="Write enriched PRD to this file.")
@click.option("--interactive", is_flag=True, help="Ask targeted questions to fill remaining gaps.")
def enrich_prd(prd_path: Path, output: Path | None, interactive: bool) -> None:
    """Convert a sparse PRD into a hyperspec PRD using LLM enrichment.

    The enriched PRD is suitable as input to `brain init --from-prd`.
    Review the [INFERRED] and [UNKNOWN] markers before proceeding.
    """
    import asyncio

    from project_brain.generators.prd_enricher import PRDEnricher
    from project_brain.llm.adapter import create_adapter, describe_adapter

    adapter = create_adapter()
    click.echo(f"LLM adapter: {describe_adapter(adapter)}")

    enricher = PRDEnricher(llm=adapter)
    result = asyncio.run(enricher.enrich_file(prd_path, output_path=output, interactive=interactive))

    click.echo(f"\nEnrichment complete")
    click.echo(f"  Score:         {result.score}/100 {'✓' if result.ready_for_brain else '✗ (target: 90)'}")
    click.echo(f"  Used LLM:      {result.used_llm}")
    click.echo(f"  Inferences:    {result.inferences_count}")
    click.echo(f"  Unknowns:      {result.unknowns_count} (require developer input)")
    click.echo(f"  Patterns:      {len(result.patterns_applied)}/20 enterprise patterns detected")

    if result.unknowns_count:
        click.echo(f"\n  Search the output for [UNKNOWN] and fill those sections before running brain init.")

    if output:
        click.echo(f"\n  Output: {output}")
        if result.ready_for_brain:
            click.echo(f"  Ready: brain init --from-prd {output}")
    else:
        click.echo("\n" + result.enriched_prd)

    if not result.ready_for_brain and not interactive:
        click.echo(f"\n  Tip: run with --interactive to answer gap-fill questions automatically.")


@cli.command("validate-prd")
@click.argument("prd_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def validate_prd(prd_path: Path) -> None:
    """Score PRD completeness before brain generation."""

    score = PRDCompletenessScorer().score_file(prd_path)
    click.echo(f"PRD Score: {score.total}/100")
    for dimension in score.dimensions:
        status = "PASS" if dimension.earned == dimension.points else "MISSING"
        click.echo(f"- {status}: {dimension.name} ({dimension.earned}/{dimension.points})")
        if dimension.earned < dimension.points:
            click.echo(f"  Guidance: {dimension.guidance}")
    if not score.can_proceed:
        raise click.ClickException("Cannot generate brain until score is at least 80.")


@cli.command("init")
@click.option("--from-prd", "from_prd", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Generate brain from a PRD markdown file.")
@click.option("--from-code", "from_code", type=click.Path(exists=True, file_okay=False, path_type=Path), help="Generate brain from a Kotlin source tree.")
@click.option("--output", type=click.Path(dir_okay=False, path_type=Path), default=Path("PROJECT_BRAIN.json"), show_default=True)
def init(from_prd: Path | None, from_code: Path | None, output: Path) -> None:
    """Create PROJECT_BRAIN.json from PRD or existing code."""

    if bool(from_prd) == bool(from_code):
        raise click.ClickException("Provide exactly one of --from-prd or --from-code.")

    generator = BrainGenerator()
    try:
        brain = generator.from_prd(from_prd) if from_prd else generator.from_code(from_code)
    except IncompletePRDError as exc:
        click.echo(f"PRD Score: {exc.score.total}/100")
        for missing in exc.score.missing:
            click.echo(f"- MISSING: {missing.name} ({missing.points} pts) - {missing.guidance}")
        raise click.ClickException("Cannot generate brain until PRD score is at least 80.") from exc

    path = generator.write(brain, output)
    click.echo(f"Brain written to: {path}")
    click.echo(json.dumps(brain.summary(), indent=2))


@cli.command("status")
@click.option("--brain-path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
def status(brain_path: Path | None) -> None:
    """Show PROJECT_BRAIN.json summary."""

    manager = BrainManager(brain_path or os.environ.get("BRAIN_PATH", "PROJECT_BRAIN.json"))
    brain = manager.load()
    click.echo(json.dumps(brain.summary(), indent=2))


@cli.command("review")
@click.option("--brain-path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--clear-review", is_flag=True, help="Mark NEEDS_REVIEW items as resolved.")
def review(brain_path: Path | None, clear_review: bool) -> None:
    """List or resolve low-confidence review items."""

    manager = BrainManager(brain_path or os.environ.get("BRAIN_PATH", "PROJECT_BRAIN.json"))
    brain = manager.load()
    review_items = [item for item in brain.known_violations if item.severity == "NEEDS_REVIEW" and not item.resolved]
    if not review_items:
        click.echo("No review items found.")
        return

    if clear_review:
        for item in review_items:
            item.resolved = True
        manager.save(brain)
        click.echo(f"Marked {len(review_items)} review item(s) resolved.")
        return

    click.echo("Review items:")
    for item in review_items:
        confidence = f" confidence={item.confidence:.2f}" if item.confidence is not None else ""
        location = f" location={item.location}" if item.location else ""
        click.echo(f"- {item.id}:{confidence}{location} - {item.message}")


@cli.command("rollback")
@click.argument("file_path", type=click.Path(exists=False))
@click.option("--brain-path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
def rollback(file_path: str, brain_path: Path | None) -> None:
    """Restore the most recent .brain_backup_ for FILE_PATH."""

    import glob as glob_mod

    backups = sorted(glob_mod.glob(f"{file_path}.brain_backup_*.kt"), reverse=True)
    if not backups:
        raise click.ClickException(f"No backups found for {file_path}")
    latest = backups[0]
    import shutil

    shutil.copy(latest, file_path)
    click.echo(f"Restored: {latest} → {file_path}")

    manager = BrainManager(brain_path or os.environ.get("BRAIN_PATH", "PROJECT_BRAIN.json"))
    if manager.exists():
        brain = manager.load()
        note = f"Rolled back {file_path} from {latest}"
        from project_brain.brain.schema import GenerationHistoryEntry

        brain.generation_history.append(
            GenerationHistoryEntry(tool="rollback", target=file_path, status="rolled_back", notes=note)
        )
        manager.save(brain)


@cli.command("doctor")
def doctor() -> None:
    """Show which LLM adapter brain will use and what is installed."""
    import shutil
    from project_brain.llm.adapter import create_adapter, describe_adapter
    from project_brain.llm.cli_adapter import list_available_cli_adapters
    from project_brain.llm.adapter import NullAdapter

    adapter = create_adapter()
    click.echo(f"Active adapter:  {describe_adapter(adapter)}")

    if isinstance(adapter, NullAdapter):
        click.echo("\n  No LLM available. brain enrich-prd will produce placeholder stubs.")
        click.echo("  Install one of the following to enable LLM enrichment:")
        click.echo("    claude code  →  https://claude.ai/code  (recommended — free with subscription)")
        click.echo("    gemini cli   →  pip install google-generativeai")
        click.echo("    llm cli      →  pip install llm")
        click.echo("    ollama       →  https://ollama.com  (local, free, offline)")
        click.echo("    API key      →  set ANTHROPIC_API_KEY or OPENAI_API_KEY")
    else:
        click.echo("  LLM enrichment is available.")

    click.echo()
    available = list_available_cli_adapters()
    if available:
        click.echo("Installed CLI tools:")
        for a in available:
            click.echo(f"  {a}")
    else:
        click.echo("No AI CLI tools found in PATH.")

    click.echo()
    click.echo("API keys:")
    click.echo(f"  ANTHROPIC_API_KEY: {'set' if os.environ.get('ANTHROPIC_API_KEY') else 'not set'}")
    click.echo(f"  OPENAI_API_KEY:    {'set' if os.environ.get('OPENAI_API_KEY') else 'not set'}")


@cli.command("roadmap")
@click.option("--brain-path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--update", is_flag=True, help="Regenerate ROADMAP.md from current brain state.")
@click.option("--feature", "feature_id", default=None, help="Show detail for one feature only.")
def roadmap(brain_path: Path | None, update: bool, feature_id: str | None) -> None:
    """Print the project roadmap or regenerate ROADMAP.md."""
    from project_brain.generators.roadmap_generator import RoadmapGenerator
    from project_brain.tools.roadmap_tools import get_feature_status, get_project_roadmap

    manager = BrainManager(brain_path or os.environ.get("BRAIN_PATH", "PROJECT_BRAIN.json"))
    brain = manager.load()
    rg = RoadmapGenerator()

    if update:
        brain_file = Path(brain_path or os.environ.get("BRAIN_PATH", "PROJECT_BRAIN.json"))
        roadmap_path = brain_file.parent / "ROADMAP.md"
        rg.write(brain, roadmap_path)
        click.echo(f"ROADMAP.md updated: {roadmap_path}")
        return

    if feature_id:
        result = get_feature_status(brain, feature_id)
        click.echo(json.dumps(result, indent=2))
        return

    click.echo(rg.generate(brain))


@cli.command("build")
@click.option("--prd", "prd_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None, help="Sparse PRD to enrich and init before building.")
@click.option("--output", "-o", type=click.Path(path_type=Path), required=True, help="Directory to write generated Kotlin files.")
@click.option("--brain-path", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--phase", type=int, default=None, help="Limit build to a single phase number.")
@click.option("--screen", "screen_id", default=None, help="Limit build to a single screen id.")
@click.option("--resume", is_flag=True, help="Continue from where the last session stopped (default behaviour).")
@click.option("--design-system", "design_system_dir", type=click.Path(path_type=Path), default=None, help="Path to design system dir (ui/theme + components) for UI design pass.")
def build(
    prd_path: Path | None,
    output: Path,
    brain_path: Path | None,
    phase: int | None,
    screen_id: str | None,
    resume: bool,
    design_system_dir: Path | None,
) -> None:
    """Drive the full project build loop via the brain-build-agent in Claude Code.

    This command prepares the brain (enriching and initialising from a PRD when
    --prd is given) and then starts the MCP stdio server so Claude Code can run
    the autonomous 13-step build agent.

    Typical usage:

    \b
    # Full pipeline from a sparse PRD:
    brain build --prd ./rough.md --output ./app/src/main/kotlin

    \b
    # Build from an existing brain:
    brain build --output ./app/src/main/kotlin

    \b
    # Build a single phase or screen:
    brain build --output ./app/src/ --phase 1
    brain build --output ./app/src/ --screen login

    After the server starts, invoke the agent in Claude Code:
    "Use the brain-build-agent to build my project to <output>"
    """
    import asyncio

    resolved_brain = Path(brain_path or os.environ.get("BRAIN_PATH", "PROJECT_BRAIN.json"))

    # ── Step 1: enrich + init if --prd given and brain does not yet exist ──
    if prd_path and not resolved_brain.exists():
        from project_brain.generators.prd_enricher import PRDEnricher
        from project_brain.llm.adapter import create_adapter, describe_adapter

        adapter = create_adapter()
        click.echo(f"LLM adapter: {describe_adapter(adapter)}")

        enriched_path = prd_path.with_suffix(".enriched.md")
        click.echo(f"Enriching PRD: {prd_path} → {enriched_path}")
        enricher = PRDEnricher(llm=adapter)
        result = asyncio.run(enricher.enrich_file(prd_path, output_path=enriched_path))
        click.echo(f"Enrichment score: {result.score}/100")

        if not result.ready_for_brain:
            click.echo("Warning: enrichment score < 90. Review [UNKNOWN] markers before continuing.")

        from project_brain.generators.brain_generator import BrainGenerator
        from project_brain.generators.prd_parser import IncompletePRDError

        generator = BrainGenerator()
        try:
            brain = generator.from_prd(enriched_path)
        except IncompletePRDError as exc:
            raise click.ClickException(f"PRD score {exc.score.total}/100 — must be ≥ 80.") from exc

        generator.write(brain, resolved_brain)
        click.echo(f"Brain written to: {resolved_brain}")

    elif prd_path and resolved_brain.exists():
        click.echo(f"Brain already exists at {resolved_brain} — skipping PRD init.")

    if not resolved_brain.exists():
        raise click.ClickException(
            f"No brain found at {resolved_brain}. "
            "Run: brain init --from-prd <prd>  OR  provide --prd to auto-init."
        )

    # ── Step 2: print agent invocation instructions ──
    scope_flags = ""
    if phase is not None:
        scope_flags += f" --phase {phase}"
    if screen_id:
        scope_flags += f" --screen {screen_id}"
    if design_system_dir:
        scope_flags += f" --design-system {design_system_dir}"

    click.echo()
    click.echo("=" * 60)
    click.echo("Brain Engine is ready. MCP server starting now.")
    click.echo()
    click.echo("In your Claude Code session, type:")
    click.echo()
    click.echo(f'  Use the brain-build-agent to build my project to {output}{scope_flags}')
    click.echo()
    click.echo("Or for a specific feature:")
    click.echo(f'  Use brain-build-agent: build feature auth to {output}')
    click.echo("=" * 60)
    click.echo()

    os.environ["BRAIN_PATH"] = str(resolved_brain)

    from project_brain.server import main as server_main

    server_main()


@cli.command("sync")
def sync() -> None:
    """Reserved for Phase 6 incremental sync."""

    raise click.ClickException("brain sync is scheduled for Phase 6.")


@cli.command("serve")
def serve() -> None:
    """Start the Phase 2 MCP stdio server."""

    from project_brain.server import main as server_main

    server_main()


if __name__ == "__main__":
    cli()
