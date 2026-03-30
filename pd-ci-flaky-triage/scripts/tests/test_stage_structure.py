#!/usr/bin/env python3
"""Structural tests for the staged flaky triage workflow."""

from __future__ import annotations

import pathlib
import unittest


SCRIPT_DIR = pathlib.Path(__file__).resolve().parents[1]


class StageStructureTests(unittest.TestCase):
    def test_agent_workflow_module_is_removed(self) -> None:
        self.assertFalse((SCRIPT_DIR / "agent_workflow.py").exists())

    def test_active_scripts_match_current_skill(self) -> None:
        self.assertTrue((SCRIPT_DIR / "prepare_logs.py").exists())
        self.assertTrue((SCRIPT_DIR / "triage_pd_ci_flaky.py").exists())

    def test_removed_stage_scripts_stay_removed(self) -> None:
        self.assertFalse((SCRIPT_DIR / "collect_failures.py").exists())
        self.assertFalse((SCRIPT_DIR / "fetch_prow_logs.py").exists())
        self.assertFalse((SCRIPT_DIR / "fetch_actions_logs.py").exists())
        self.assertFalse((SCRIPT_DIR / "collect_prow_failures.py").exists())
        self.assertFalse((SCRIPT_DIR / "collect_actions_failures.py").exists())
        self.assertFalse((SCRIPT_DIR / "build_observations.py").exists())
        self.assertFalse((SCRIPT_DIR / "build_prow_observations.py").exists())
        self.assertFalse((SCRIPT_DIR / "build_actions_observations.py").exists())
        self.assertFalse((SCRIPT_DIR / "build_env_review_candidates.py").exists())
        self.assertFalse((SCRIPT_DIR / "build_issue_match_candidates.py").exists())
        self.assertFalse((SCRIPT_DIR / "build_action_review_candidates.py").exists())
        self.assertFalse((SCRIPT_DIR / "assemble_final_triage.py").exists())
        self.assertFalse((SCRIPT_DIR / "stage_common.py").exists())
        self.assertFalse((SCRIPT_DIR / "validate_flaky_snippets.py").exists())

    def test_prepare_logs_no_longer_uses_stage_common(self) -> None:
        content = (SCRIPT_DIR / "prepare_logs.py").read_text(encoding="utf-8")
        self.assertNotIn("stage_common", content)
        self.assertNotIn("agent_workflow", content)


if __name__ == "__main__":
    unittest.main()
