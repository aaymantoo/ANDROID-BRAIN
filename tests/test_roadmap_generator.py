"""Tests for RoadmapGenerator — ROADMAP.md generation and in-memory status tracking."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from project_brain.brain.schema import (
    Feature,
    GenerationStatus,
    Meta,
    ProjectBrain,
    Screen,
)
from project_brain.generators.roadmap_generator import RoadmapGenerator, _TEMPLATE_TO_COMPONENT


def _brain(screens: list[str], features: list[Feature] | None = None) -> ProjectBrain:
    brain = ProjectBrain(
        meta=Meta(project_name="TestApp", entry_point="prd"),
        screens=[Screen(id=s) for s in screens],
        features=features or [],
    )
    # Initialise generation_status entries
    from project_brain.brain.schema import GenerationStatus
    for s in screens:
        brain.generation_status.append(GenerationStatus(screen_id=s))
    return brain


def _feature(
    fid: str,
    name: str,
    screens: list[str],
    priority: int = 1,
    deps: list[str] | None = None,
) -> Feature:
    return Feature(id=fid, name=name, screens=screens, priority=priority, feature_dependencies=deps or [])


class TestTemplateToComponentMapping(TestCase):
    def test_viewmodel_template_maps(self):
        self.assertEqual(_TEMPLATE_TO_COMPONENT["viewmodel.kt.j2"], "viewmodel")

    def test_uistate_template_maps(self):
        self.assertEqual(_TEMPLATE_TO_COMPONENT["uistate.kt.j2"], "ui_state")

    def test_combined_repository_template_maps(self):
        self.assertEqual(
            _TEMPLATE_TO_COMPONENT["repository_interface.kt.j2 + repository_impl.kt.j2"],
            "repository",
        )

    def test_scaffold_template_maps(self):
        self.assertEqual(_TEMPLATE_TO_COMPONENT["screen_scaffold.kt.j2"], "scaffold")

    def test_test_template_maps(self):
        self.assertEqual(_TEMPLATE_TO_COMPONENT["viewmodel_test.kt.j2"], "tests")


class TestGenerateContent(TestCase):
    def setUp(self):
        self.rg = RoadmapGenerator()

    def test_generate_includes_project_name(self):
        brain = _brain(["home"])
        md = self.rg.generate(brain)
        self.assertIn("TestApp", md)

    def test_generate_includes_progress_bar(self):
        brain = _brain(["home"])
        md = self.rg.generate(brain)
        self.assertIn("[", md)
        self.assertIn("] 0%", md)

    def test_generate_shows_screen_in_table(self):
        brain = _brain(["login"], [_feature("auth", "Auth", ["login"])])
        md = self.rg.generate(brain)
        self.assertIn("login", md)

    def test_generate_shows_feature_name(self):
        brain = _brain(["home"], [_feature("home_feat", "Home Feed", ["home"])])
        md = self.rg.generate(brain)
        self.assertIn("Home Feed", md)

    def test_generate_shows_blocked_feature(self):
        auth = _feature("auth", "Auth", ["login"], priority=1)
        orders = _feature("orders", "Orders", ["order_list"], priority=2, deps=["auth"])
        brain = _brain(["login", "order_list"], [auth, orders])
        md = self.rg.generate(brain)
        self.assertIn("Blocked by", md)

    def test_generate_flat_section_when_no_features(self):
        brain = _brain(["splash", "home"])
        md = self.rg.generate(brain)
        self.assertIn("All Screens", md)

    def test_generate_session_log_section(self):
        brain = _brain(["home"])
        md = self.rg.generate(brain)
        self.assertIn("Session Log", md)

    def test_write_creates_file(self):
        brain = _brain(["home"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ROADMAP.md"
            self.rg.write(brain, path)
            self.assertTrue(path.exists())
            self.assertIn("TestApp", path.read_text())


class TestUpdateBrainStatus(TestCase):
    def setUp(self):
        self.rg = RoadmapGenerator()

    def test_viewmodel_flag_set_on_success(self):
        brain = _brain(["login"])
        self.rg.update_brain_status(brain, "viewmodel.kt.j2", "login", success=True)
        status = brain.generation_status[0]
        self.assertTrue(status.components.viewmodel)
        self.assertFalse(status.components.ui_state)

    def test_no_update_on_failure(self):
        brain = _brain(["login"])
        self.rg.update_brain_status(brain, "viewmodel.kt.j2", "login", success=False)
        status = brain.generation_status[0]
        self.assertFalse(status.components.viewmodel)

    def test_unknown_template_is_ignored(self):
        brain = _brain(["login"])
        self.rg.update_brain_status(brain, "some_other.kt.j2", "login", success=True)
        status = brain.generation_status[0]
        self.assertFalse(status.components.viewmodel)

    def test_feature_becomes_in_progress_after_first_component(self):
        feat = _feature("auth", "Auth", ["login"])
        brain = _brain(["login"], [feat])
        self.rg.update_brain_status(brain, "viewmodel.kt.j2", "login", success=True)
        self.assertEqual(brain.features[0].status, "in_progress")

    def test_feature_becomes_complete_when_all_generated(self):
        feat = _feature("auth", "Auth", ["login"])
        brain = _brain(["login"], [feat])
        # Screen-level templates use screen_id; di_module uses feature_id
        for tmpl, target in [
            ("viewmodel.kt.j2", "login"),
            ("uistate.kt.j2", "login"),
            ("repository_interface.kt.j2 + repository_impl.kt.j2", "login"),
            ("screen_scaffold.kt.j2", "login"),
            ("di_module.kt.j2", "auth"),   # feature id
            ("nav_route.kt.j2", "login"),
            ("viewmodel_test.kt.j2", "login"),
        ]:
            self.rg.update_brain_status(brain, tmpl, target, success=True)
        self.assertEqual(brain.features[0].status, "complete")

    def test_session_log_appended(self):
        brain = _brain(["home"])
        self.rg.update_brain_status(brain, "viewmodel.kt.j2", "home", success=True)
        self.assertEqual(len(brain.session_log), 1)
        self.assertIn("home.viewmodel", brain.session_log[0].components_built)

    def test_session_log_same_day_is_merged(self):
        brain = _brain(["home"])
        self.rg.update_brain_status(brain, "viewmodel.kt.j2", "home", success=True)
        self.rg.update_brain_status(brain, "uistate.kt.j2", "home", success=True)
        self.assertEqual(len(brain.session_log), 1)
        self.assertEqual(len(brain.session_log[0].components_built), 2)

    def test_di_module_marks_all_feature_screens(self):
        feat = _feature("auth", "Auth", ["phone_entry", "otp"])
        brain = _brain(["phone_entry", "otp"], [feat])
        self.rg.update_brain_status(brain, "di_module.kt.j2", "auth", success=True)
        for sid in ["phone_entry", "otp"]:
            status = next(s for s in brain.generation_status if s.screen_id == sid)
            self.assertTrue(status.components.di_module)


class TestNextStep(TestCase):
    def setUp(self):
        self.rg = RoadmapGenerator()

    def test_next_step_is_viewmodel_for_fresh_screen(self):
        brain = _brain(["home"])
        call = self.rg.next_step(brain)
        self.assertIn("generate_viewmodel", call)
        self.assertIn("home", call)

    def test_next_step_respects_feature_priority(self):
        auth = _feature("auth", "Auth", ["login"], priority=1)
        home = _feature("home", "Home", ["home"], priority=2)
        brain = _brain(["login", "home"], [auth, home])
        call = self.rg.next_step(brain)
        self.assertIn("login", call)

    def test_next_step_skips_blocked_feature(self):
        auth = _feature("auth", "Auth", ["login"], priority=1)
        home = _feature("home", "Home", ["home"], priority=2, deps=["auth"])
        brain = _brain(["login", "home"], [auth, home])
        # Auth not complete — home is blocked
        # login viewmodel is still next (from auth feature)
        call = self.rg.next_step(brain)
        self.assertIn("login", call)

    def test_next_step_returns_none_when_all_done(self):
        brain = _brain([])  # no screens
        result = self.rg.next_step(brain)
        self.assertIsNone(result)

    def test_next_step_progresses_through_components(self):
        brain = _brain(["home"])
        # Mark viewmodel done
        brain.generation_status[0].components.viewmodel = True
        call = self.rg.next_step(brain)
        self.assertIn("generate_ui_state", call)
