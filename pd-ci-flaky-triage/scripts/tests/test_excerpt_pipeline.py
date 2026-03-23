#!/usr/bin/env python3
"""Unit tests for excerpt propagation across staged triage artifacts."""

from __future__ import annotations

import pathlib
import sys
import unittest


SCRIPT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import assemble_final_triage as assemble  # type: ignore  # noqa: E402
import build_action_review_candidates as action_candidates  # type: ignore  # noqa: E402


def sample_failure_item() -> dict:
    return {
        "candidate_id": "prow:testfoo:1",
        "group_key": "testfoo",
        "source": "prow",
        "source_item_id": "prow-item-1",
        "target": {"test_name": "TestFoo", "package_name": None},
        "signatures": ["PANIC"],
        "failure_family": "panic",
        "evidence_lines": ["panic: test timed out after 5m0s", "TestFoo"],
        "excerpt_lines": ["panic: test timed out after 5m0s", "running tests:", "  TestFoo (5m0s)"],
        "excerpt_start_line": 120,
        "excerpt_end_line": 122,
        "excerpt_confidence": 0.96,
        "excerpt_reason": "timeout block names the failing test",
        "debug_only_evidence_summary": "type=timeout; test=TestFoo; signatures=PANIC",
        "ci_name": "pull-unit-test-next-gen-1",
        "ci_url": "https://example.invalid/ci/1",
        "log_ref": "/tmp/log-1.txt",
        "occurred_at": "2026-03-23T00:00:00Z",
        "commit_sha": "abc123",
        "status": "FAILURE",
        "pr_number": 101,
        "source_details": {"job_name": "pull-unit-test-next-gen-1"},
    }


class ExcerptPipelineTests(unittest.TestCase):
    def test_action_review_candidates_keep_excerpt_candidates(self) -> None:
        payload = action_candidates.build_action_review_candidates_payload(
            failure_item_payloads=[
                {
                    "source": "prow",
                    "window": {"start": "2026-03-22T00:00:00Z", "end": "2026-03-23T00:00:00Z"},
                    "counts": {"failure_items": 1},
                    "failure_items": [sample_failure_item()],
                    "skipped": [],
                }
            ],
            issue_match_payload={"candidates": []},
        )

        self.assertEqual(1, payload["counts"]["total_candidates"])
        candidate = payload["candidates"][0]
        self.assertEqual(["prow:testfoo:1"], candidate["failure_item_ids"])
        self.assertEqual(1, len(candidate["excerpt_candidates"]))
        excerpt = candidate["excerpt_candidates"][0]
        self.assertEqual("prow:testfoo:1", excerpt["failure_item_id"])
        self.assertEqual("panic", excerpt["failure_family"])
        self.assertEqual(0.96, excerpt["excerpt_confidence"])
        self.assertEqual(
            ["panic: test timed out after 5m0s", "running tests:", "  TestFoo (5m0s)"],
            excerpt["excerpt_lines"],
        )

    def test_final_triage_preserves_excerpt_candidates(self) -> None:
        action_review_candidates = {
            "window": {"start": "2026-03-22T00:00:00Z", "end": "2026-03-23T00:00:00Z"},
            "candidates": [
                {
                    "candidate_id": "testfoo",
                    "group_key": "testfoo",
                    "source": "prow",
                    "canonical_target": {"test_name": "TestFoo", "package_name": None},
                    "issue_labels": ["type/ci"],
                    "issue_matches": {"selected_match": None, "matches": []},
                    "links": ["https://example.invalid/ci/1"],
                    "ci_names": ["pull-unit-test-next-gen-1"],
                    "signatures": ["PANIC"],
                    "excerpt_candidates": [
                        {
                            "failure_item_id": "prow:testfoo:1",
                            "target": {"test_name": "TestFoo", "package_name": None},
                            "ci_name": "pull-unit-test-next-gen-1",
                            "ci_url": "https://example.invalid/ci/1",
                            "log_ref": "/tmp/log-1.txt",
                            "signatures": ["PANIC"],
                            "failure_family": "panic",
                            "excerpt_lines": [
                                "panic: test timed out after 5m0s",
                                "running tests:",
                                "  TestFoo (5m0s)",
                            ],
                            "excerpt_start_line": 120,
                            "excerpt_end_line": 122,
                            "excerpt_confidence": 0.96,
                            "excerpt_reason": "timeout block names the failing test",
                        }
                    ],
                    "debug_only_evidence_summary": "type=timeout; test=TestFoo; signatures=PANIC",
                }
            ],
        }
        action_review_decisions = {
            "decisions": [
                {
                    "candidate_id": "testfoo",
                    "final_action": "create",
                    "canonical_target": {"test_name": "TestFoo", "package_name": None},
                    "reason": "reproduced across PRs",
                }
            ]
        }

        payload = assemble.assemble_final_triage_payload(
            action_review_candidates=action_review_candidates,
            action_review_decisions=action_review_decisions,
            env_review_payload={"window": action_review_candidates["window"], "items": []},
            env_review_decisions={"decisions": []},
        )

        self.assertEqual(1, payload["counts"]["create"])
        create_entry = payload["create"][0]
        self.assertEqual(1, len(create_entry["excerpt_candidates"]))
        excerpt = create_entry["excerpt_candidates"][0]
        self.assertEqual("prow:testfoo:1", excerpt["failure_item_id"])
        self.assertEqual("https://example.invalid/ci/1", excerpt["ci_url"])
        self.assertEqual("timeout block names the failing test", excerpt["excerpt_reason"])


if __name__ == "__main__":
    unittest.main()
