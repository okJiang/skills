#!/usr/bin/env python3
"""Unit tests for the PD shadow-review batch harness."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "prepare_shadow_review_batch.py"
if str(SCRIPT_PATH.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("prepare_shadow_review_batch", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class LoadShadowCorpusTests(unittest.TestCase):
    def test_load_shadow_corpus_merges_duplicate_prs_and_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_path = pathlib.Path(tmpdir) / "shadow.jsonl"
            corpus_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "category": "schedule-config",
                                "number": 101,
                                "title": "schedule change",
                                "url": "https://example.test/101",
                                "merged_at": "2026-03-20T00:00:00Z",
                                "files": ["pkg/schedule/config.go"],
                            }
                        ),
                        json.dumps(
                            {
                                "category": "bugfix",
                                "number": 101,
                                "title": "schedule change",
                                "url": "https://example.test/101",
                                "merged_at": "2026-03-20T00:00:00Z",
                                "files": ["pkg/schedule/config.go", "tests/config_test.go"],
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            records = MODULE.load_shadow_corpus(corpus_path)

        self.assertEqual(1, len(records))
        self.assertEqual(101, records[0]["pr_number"])
        self.assertEqual(["schedule-config", "bugfix"], records[0]["categories"])
        self.assertEqual(
            ["pkg/schedule/config.go", "tests/config_test.go"],
            records[0]["files"],
        )


class SelectShadowRecordsTests(unittest.TestCase):
    def test_select_pr_records_prefers_explicit_prs_and_deduplicates(self) -> None:
        corpus_records = [
            {
                "pr_number": 101,
                "title": "schedule change",
                "url": "https://example.test/101",
                "merged_at": "2026-03-20T00:00:00Z",
                "files": ["pkg/schedule/config.go"],
                "categories": ["schedule-config"],
                "source": "shadow-corpus",
            },
            {
                "pr_number": 202,
                "title": "test fix",
                "url": "https://example.test/202",
                "merged_at": "2026-03-20T00:00:00Z",
                "files": ["tests/foo_test.go"],
                "categories": ["tests-ci"],
                "source": "shadow-corpus",
            },
        ]

        selected = MODULE.select_pr_records(
            corpus_records=corpus_records,
            requested_prs=[202, 303],
            categories=["tests-ci"],
            corpus_limit=1,
        )

        self.assertEqual([202, 303], [record["pr_number"] for record in selected])
        self.assertEqual("shadow-corpus", selected[0]["source"])
        self.assertEqual("explicit-pr", selected[1]["source"])


class PrepareRunBundleTests(unittest.TestCase):
    def test_prepare_run_bundle_writes_templates_and_manifest(self) -> None:
        record = {
            "pr_number": 404,
            "title": "shadow batch test",
            "url": "https://example.test/404",
            "merged_at": "2026-03-20T00:00:00Z",
            "files": ["pkg/schedule/foo.go"],
            "categories": ["schedule-config"],
            "source": "shadow-corpus",
        }
        plan = {
            "selected_lanes": [
                "metadata",
                "tests",
            ],
            "suggested_checks": ["go test ./pkg/schedule/..."],
            "risk_map": {"command_budget": 2},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = pathlib.Path(tmpdir) / "pr-404"
            entry = MODULE.prepare_run_bundle(run_dir=run_dir, record=record, plan=plan)

            self.assertTrue((run_dir / "source-record.json").exists())
            self.assertTrue((run_dir / "plan.json").exists())
            self.assertTrue(
                (run_dir / "lane-results" / "metadata.template.json").exists()
            )
            self.assertTrue(
                (run_dir / "lane-results" / "tests.template.json").exists()
            )
            self.assertTrue((run_dir / "arbiter" / "dry-run-command.txt").exists())
            self.assertTrue((run_dir / "arbiter" / "capture-decision-command.txt").exists())
            self.assertTrue((run_dir / "arbiter" / "decision.template.json").exists())
            self.assertTrue((run_dir / "arbiter" / "final-proposed-comments.md").exists())
            self.assertTrue((run_dir / "evaluation" / "manual-score.csv").exists())
            self.assertTrue((run_dir / "evaluation" / "case-summary.md").exists())
            self.assertIn(
                "leave `model_finding_ref`, `claimed_severity`, and `skill_status` blank",
                (run_dir / "evaluation" / "README.md").read_text(encoding="utf-8"),
            )
            self.assertTrue((run_dir / "notes" / "shadow-summary.md").exists())
            self.assertTrue((run_dir / "notes" / "manual-comparison.md").exists())
            self.assertEqual(
                ["metadata", "tests"],
                entry["review_lanes"],
            )
            self.assertTrue(entry["manual_score_path"].endswith("/evaluation/manual-score.csv"))


if __name__ == "__main__":
    unittest.main()
