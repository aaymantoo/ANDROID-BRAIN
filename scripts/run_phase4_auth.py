"""Run Phase 4 generation on the enriched bigbaagh auth brain."""

from __future__ import annotations

import asyncio
from pathlib import Path

from project_brain.brain.manager import BrainManager
from project_brain.generators.code_generation import GenerationOrchestrator


BRAIN_PATH = "bigbaagh_auth_enriched_brain.json"
OUTPUT_DIR = Path("generated_v2")


async def main():
    brain = BrainManager(BRAIN_PATH).load()
    orchestrator = GenerationOrchestrator(brain, brain_path=BRAIN_PATH)

    print(f"Template engine: {type(orchestrator.engine).__name__}")
    print()

    OUTPUT_DIR.mkdir(exist_ok=True)

    # Generate PhoneEntry ViewModel + UiState
    r = await orchestrator.generate_viewmodel("PhoneEntryScreen")
    _write(r, "PhoneEntryViewModel.kt")

    r = await orchestrator.generate_ui_state("PhoneEntryScreen")
    _write(r, "PhoneEntryUiState.kt")

    # Generate OTP ViewModel + UiState
    r = await orchestrator.generate_viewmodel("OtpVerificationScreen")
    _write(r, "OtpViewModel.kt")

    r = await orchestrator.generate_ui_state("OtpVerificationScreen")
    _write(r, "OtpUiState.kt")

    # Generate Repository
    r = await orchestrator.generate_repository("AuthRepository")
    _write(r, "AuthRepository.kt")

    # Generate Screens
    r = await orchestrator.generate_screen_scaffold("PhoneEntryScreen")
    _write(r, "PhoneEntryRoute.kt")

    r = await orchestrator.generate_screen_scaffold("OtpVerificationScreen")
    _write(r, "OtpRoute.kt")

    # Generate DI
    r = await orchestrator.generate_di_module("auth")
    _write(r, "AuthModule.kt")

    # Generate nav routes
    r = await orchestrator.generate_nav_route("PhoneEntryScreen")
    _write(r, "PhoneEntryRoute_Nav.kt")

    r = await orchestrator.generate_nav_route("OtpVerificationScreen")
    _write(r, "OtpRoute_Nav.kt")

    # Generate ViewModel tests
    r = await orchestrator.generate_viewmodel_test("PhoneEntryScreen")
    _write(r, "PhoneEntryViewModelTest.kt")

    r = await orchestrator.generate_viewmodel_test("OtpVerificationScreen")
    _write(r, "OtpViewModelTest.kt")

    print(f"\nAll files written to {OUTPUT_DIR}/")


def _write(result, filename: str):
    path = OUTPUT_DIR / filename
    path.write_text(result.content, encoding="utf-8")
    status = "CLEAN" if result.clean else f"VIOLATIONS({len(result.violations)})"
    print(f"  {status}  {filename}")
    if result.violations:
        for v in result.violations:
            print(f"        [{v.get('severity','?')}] {v.get('rule_id','?')}: {v.get('description','?')}")


if __name__ == "__main__":
    asyncio.run(main())
