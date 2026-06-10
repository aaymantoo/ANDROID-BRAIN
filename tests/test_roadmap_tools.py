"""Tests for roadmap MCP tools — session context, next task, feature status, project roadmap."""

from __future__ import annotations

from unittest import TestCase

from project_brain.brain.schema import Feature, GenerationStatus, Meta, ProjectBrain, Screen
from project_brain.tools.roadmap_tools import (
    get_feature_status,
    get_next_task,
    get_project_roadmap,
    get_session_context,
)


def _brain(screens: list[str], features: list[Feature] | None = None) -> ProjectBrain:
    brain = ProjectBrain(
        meta=Meta(project_name="TestApp", entry_point="prd"),
        screens=[Screen(id=s) for s in screens],
        features=features or [],
    )
    for s in screens:
        brain.generation_status.append(GenerationStatus(screen_id=s))
    return brain


def _feature(fid, name, screens, priority=1, deps=None):
    return Feature(id=fid, name=name, screens=screens, priority=priority, feature_dependencies=deps or [])


class TestGetSessionContext(TestCase):
    def test_empty_brain_returns_no_last_session(self):
        brain = _brain(["home"])
        result = get_session_context(brain)
        self.assertIsNone(result["last_session"])

    def test_project_name_in_result(self):
        brain = _brain(["home"])
        result = get_session_context(brain)
        self.assertEqual(result["project"], "TestApp")

    def test_overall_progress_format(self):
        brain = _brain(["home"])
        result = get_session_context(brain)
        self.assertIn("/", result["overall_progress"])
        self.assertIn("%", result["overall_progress"])

    def test_last_session_populated_after_session_log(self):
        from project_brain.brain.schema import SessionEntry
        brain = _brain(["home"])
        brain.session_log.append(
            SessionEntry(date="2026-06-10", components_built=["home.viewmodel"])
        )
        result = get_session_context(brain)
        self.assertIsNotNone(result["last_session"])
        self.assertEqual(result["last_session"]["date"], "2026-06-10")

    def test_blocked_features_listed(self):
        auth = _feature("auth", "Auth", ["login"], priority=1)
        orders = _feature("orders", "Orders", ["order"], priority=2, deps=["auth"])
        brain = _brain(["login", "order"], [auth, orders])
        result = get_session_context(brain)
        blocked_ids = [b["id"] for b in result["blocked_features"]]
        self.assertIn("orders", blocked_ids)
        self.assertNotIn("auth", blocked_ids)

    def test_all_features_listed(self):
        auth = _feature("auth", "Auth", ["login"])
        brain = _brain(["login"], [auth])
        result = get_session_context(brain)
        self.assertEqual(len(result["all_features"]), 1)
        self.assertEqual(result["all_features"][0]["id"], "auth")


class TestGetNextTask(TestCase):
    def test_returns_generate_viewmodel_for_fresh_screen(self):
        brain = _brain(["home"])
        result = get_next_task(brain)
        self.assertFalse(result["done"])
        self.assertIn("generate_viewmodel", result["next_step"])

    def test_returns_done_when_no_screens(self):
        brain = _brain([])
        result = get_next_task(brain)
        self.assertTrue(result["done"])

    def test_feature_name_included(self):
        feat = _feature("auth", "Authentication", ["login"])
        brain = _brain(["login"], [feat])
        result = get_next_task(brain)
        self.assertEqual(result["feature"], "Authentication")

    def test_screen_id_included(self):
        brain = _brain(["login"])
        result = get_next_task(brain)
        self.assertEqual(result["screen"], "login")

    def test_reason_populated(self):
        brain = _brain(["home"])
        result = get_next_task(brain)
        self.assertIsNotNone(result["reason"])
        self.assertIsInstance(result["reason"], str)


class TestGetFeatureStatus(TestCase):
    def test_returns_error_for_unknown_feature(self):
        brain = _brain(["home"])
        result = get_feature_status(brain, "nonexistent")
        self.assertIn("error", result)

    def test_returns_feature_data_by_id(self):
        feat = _feature("auth", "Auth", ["login"])
        brain = _brain(["login"], [feat])
        result = get_feature_status(brain, "auth")
        self.assertEqual(result["feature_id"], "auth")
        self.assertEqual(result["feature_name"], "Auth")

    def test_returns_feature_data_by_name(self):
        feat = _feature("auth", "Authentication", ["login"])
        brain = _brain(["login"], [feat])
        result = get_feature_status(brain, "authentication")
        self.assertEqual(result["feature_id"], "auth")

    def test_screens_listed_with_component_flags(self):
        feat = _feature("auth", "Auth", ["login"])
        brain = _brain(["login"], [feat])
        result = get_feature_status(brain, "auth")
        self.assertEqual(len(result["screens"]), 1)
        screen = result["screens"][0]
        self.assertEqual(screen["screen_id"], "login")
        self.assertFalse(screen["viewmodel"])

    def test_progress_reflects_done_count(self):
        feat = _feature("auth", "Auth", ["login"])
        brain = _brain(["login"], [feat])
        brain.generation_status[0].components.viewmodel = True
        result = get_feature_status(brain, "auth")
        self.assertIn("1/", result["progress"])


class TestGetProjectRoadmap(TestCase):
    def test_returns_project_name(self):
        brain = _brain(["home"])
        result = get_project_roadmap(brain)
        self.assertEqual(result["project"], "TestApp")

    def test_features_sorted_by_priority(self):
        auth = _feature("auth", "Auth", ["login"], priority=1)
        home = _feature("home", "Home", ["home"], priority=2)
        brain = _brain(["login", "home"], [home, auth])  # intentionally reversed
        result = get_project_roadmap(brain)
        self.assertEqual(result["features"][0]["id"], "auth")
        self.assertEqual(result["features"][1]["id"], "home")

    def test_unassigned_screens_listed(self):
        brain = _brain(["orphan"])  # no features
        result = get_project_roadmap(brain)
        orphan_ids = [s["screen_id"] for s in result["unassigned_screens"]]
        self.assertIn("orphan", orphan_ids)

    def test_overall_progress_present(self):
        brain = _brain(["home"])
        result = get_project_roadmap(brain)
        self.assertIn("/", result["overall_progress"])

    def test_session_count_zero_initially(self):
        brain = _brain(["home"])
        result = get_project_roadmap(brain)
        self.assertEqual(result["session_count"], 0)
