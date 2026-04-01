#!/usr/bin/env python3
"""Unit tests for orchestrator lane-selection helpers."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "orchestrate_pd_pr_review.py"
if str(SCRIPT_PATH.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("orchestrate_pd_pr_review", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CheckFieldFallbackTests(unittest.TestCase):
    def test_select_check_fields_falls_back_to_available_gh_fields(self) -> None:
        stderr = """Unknown JSON field: "conclusion"
Available fields:
  bucket
  completedAt
  description
  event
  link
  name
  startedAt
  state
  workflow
"""

        self.assertEqual(
            ["name", "state", "bucket", "link", "startedAt", "completedAt", "workflow"],
            MODULE.select_check_fields(stderr),
        )


if __name__ == "__main__":
    unittest.main()
