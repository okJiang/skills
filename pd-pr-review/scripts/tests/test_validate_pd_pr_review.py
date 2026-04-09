#!/usr/bin/env python3
"""Unit tests for pd-pr-review validation helpers."""

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import sys
import tempfile
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "validate_pd_pr_review.py"
SPEC = importlib.util.spec_from_file_location("validate_pd_pr_review", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ValidatePdPrReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_dir = pathlib.Path(__file__).resolve().parents[2]

    def make_skill_copy(self) -> pathlib.Path:
        temp_root = pathlib.Path(tempfile.mkdtemp())
        copied_skill = temp_root / "pd-pr-review"
        shutil.copytree(
            self.skill_dir,
            copied_skill,
            ignore=shutil.ignore_patterns("benchmark-v1.json", "shadow-pr-corpus.jsonl"),
        )
        (copied_skill / "references/benchmark-v1.json").write_text("{}\n", encoding="utf-8")
        (copied_skill / "references/shadow-pr-corpus.jsonl").write_text("\n", encoding="utf-8")
        self.addCleanup(shutil.rmtree, temp_root)
        return copied_skill

    def test_real_skill_passes_validation(self) -> None:
        issues = MODULE.validate_skill(self.skill_dir)
        self.assertEqual([], issues)

    def test_missing_reference_is_reported(self) -> None:
        copied_skill = self.make_skill_copy()
        (copied_skill / "references/reviewer-rules.md").unlink()

        issues = MODULE.validate_skill(copied_skill)

        self.assertTrue(
            any("references/reviewer-rules.md" in issue for issue in issues),
            issues,
        )

    def test_description_queries_require_both_polarities(self) -> None:
        copied_skill = self.make_skill_copy()
        (copied_skill / "evals/description-queries.json").write_text(
            """
            {
              "skill": "pd-pr-review",
              "queries": [
                {
                  "id": "only-positive-train",
                  "split": "train",
                  "should_trigger": true,
                  "prompt": "review tikv/pd pr #1"
                },
                {
                  "id": "only-positive-validation",
                  "split": "validation",
                  "should_trigger": true,
                  "prompt": "review tikv/pd pr #2"
                }
              ]
            }
            """,
            encoding="utf-8",
        )

        issues = MODULE.validate_skill(copied_skill)

        self.assertTrue(
            any("must include both trigger and non-trigger cases" in issue for issue in issues),
            issues,
        )

    def test_description_queries_reject_duplicate_prompts(self) -> None:
        copied_skill = self.make_skill_copy()
        (copied_skill / "evals/description-queries.json").write_text(
            """
            {
              "skill": "pd-pr-review",
              "queries": [
                {
                  "id": "train-pos-1",
                  "split": "train",
                  "should_trigger": true,
                  "prompt": "review pd pr #1"
                },
                {
                  "id": "train-neg-1",
                  "split": "train",
                  "should_trigger": false,
                  "prompt": "do not trigger train"
                },
                {
                  "id": "train-pos-2",
                  "split": "train",
                  "should_trigger": true,
                  "prompt": "review pd pr #2"
                },
                {
                  "id": "train-neg-2",
                  "split": "train",
                  "should_trigger": false,
                  "prompt": "do not trigger train 2"
                },
                {
                  "id": "validation-pos-1",
                  "split": "validation",
                  "should_trigger": true,
                  "prompt": "review pd pr #1"
                },
                {
                  "id": "validation-neg-1",
                  "split": "validation",
                  "should_trigger": false,
                  "prompt": "do not trigger validation"
                },
                {
                  "id": "validation-pos-2",
                  "split": "validation",
                  "should_trigger": true,
                  "prompt": "review pd pr #3"
                },
                {
                  "id": "validation-neg-2",
                  "split": "validation",
                  "should_trigger": false,
                  "prompt": "do not trigger validation 2"
                },
                {
                  "id": "validation-pos-3",
                  "split": "validation",
                  "should_trigger": true,
                  "prompt": "review pd pr #4"
                },
                {
                  "id": "validation-neg-3",
                  "split": "validation",
                  "should_trigger": false,
                  "prompt": "do not trigger validation 3"
                },
                {
                  "id": "train-pos-3",
                  "split": "train",
                  "should_trigger": true,
                  "prompt": "review pd pr #5"
                },
                {
                  "id": "train-neg-3",
                  "split": "train",
                  "should_trigger": false,
                  "prompt": "do not trigger train 3"
                },
                {
                  "id": "train-pos-4",
                  "split": "train",
                  "should_trigger": true,
                  "prompt": "review pd pr #6"
                },
                {
                  "id": "train-neg-4",
                  "split": "train",
                  "should_trigger": false,
                  "prompt": "do not trigger train 4"
                },
                {
                  "id": "validation-pos-4",
                  "split": "validation",
                  "should_trigger": true,
                  "prompt": "review pd pr #7"
                },
                {
                  "id": "validation-neg-4",
                  "split": "validation",
                  "should_trigger": false,
                  "prompt": "do not trigger validation 4"
                }
              ]
            }
            """,
            encoding="utf-8",
        )

        issues = MODULE.validate_skill(copied_skill)

        self.assertTrue(
            any("duplicate description query prompt" in issue for issue in issues),
            issues,
        )

    def test_review_cases_require_core_lanes(self) -> None:
        copied_skill = self.make_skill_copy()
        (copied_skill / "evals/review-cases.json").write_text(
            """
            {
              "skill": "pd-pr-review",
              "required_sections": [
                "PR Context",
                "Active Lanes",
                "Lane Notes",
                "Consolidated Findings",
                "Open Questions / Needs More Evidence",
                "Draft Review Comments"
              ],
              "cases": [
                {
                  "id": "bad-case",
                  "prompt": "review pd pr",
                  "expected_lanes": ["root-cause"],
                  "forbidden_lanes": [],
                  "must_stop_before_publish": true
                },
                {
                  "id": "bad-case-2",
                  "prompt": "review pd pr 2",
                  "expected_lanes": ["root-cause"],
                  "forbidden_lanes": [],
                  "must_stop_before_publish": true
                },
                {
                  "id": "bad-case-3",
                  "prompt": "review pd pr 3",
                  "expected_lanes": ["root-cause"],
                  "forbidden_lanes": [],
                  "must_stop_before_publish": true
                }
              ]
            }
            """,
            encoding="utf-8",
        )

        issues = MODULE.validate_skill(copied_skill)

        self.assertTrue(
            any("must always include `metadata` and `tests`" in issue for issue in issues),
            issues,
        )


if __name__ == "__main__":
    unittest.main()
