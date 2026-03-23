#!/usr/bin/env python3
"""Structural tests for the staged flaky triage workflow."""

from __future__ import annotations

import pathlib
import unittest


SCRIPT_DIR = pathlib.Path(__file__).resolve().parents[1]


class StageStructureTests(unittest.TestCase):
    def test_agent_workflow_module_is_removed(self) -> None:
        self.assertFalse((SCRIPT_DIR / "agent_workflow.py").exists())

    def test_prepare_logs_stage_is_single_entrypoint(self) -> None:
        self.assertTrue((SCRIPT_DIR / "prepare_logs.py").exists())
        self.assertFalse((SCRIPT_DIR / "collect_failures.py").exists())
        self.assertFalse((SCRIPT_DIR / "fetch_prow_logs.py").exists())
        self.assertFalse((SCRIPT_DIR / "fetch_actions_logs.py").exists())
        self.assertFalse((SCRIPT_DIR / "collect_prow_failures.py").exists())
        self.assertFalse((SCRIPT_DIR / "collect_actions_failures.py").exists())

    def test_observation_stage_is_single_entrypoint(self) -> None:
        self.assertTrue((SCRIPT_DIR / "build_observations.py").exists())
        self.assertFalse((SCRIPT_DIR / "build_prow_observations.py").exists())
        self.assertFalse((SCRIPT_DIR / "build_actions_observations.py").exists())

    def test_atomic_stage_scripts_do_not_import_agent_workflow(self) -> None:
        stage_scripts = [
            "prepare_logs.py",
            "build_observations.py",
            "build_env_review_candidates.py",
            "build_issue_match_candidates.py",
            "build_action_review_candidates.py",
            "assemble_final_triage.py",
        ]
        for name in stage_scripts:
            with self.subTest(script=name):
                content = (SCRIPT_DIR / name).read_text(encoding="utf-8")
                self.assertNotIn("agent_workflow", content)


if __name__ == "__main__":
    unittest.main()
