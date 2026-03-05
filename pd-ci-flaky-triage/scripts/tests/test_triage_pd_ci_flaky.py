#!/usr/bin/env python3
"""Unit tests for pd CI flaky triage parser heuristics."""

from __future__ import annotations

import importlib.util
import io
import pathlib
import re
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "triage_pd_ci_flaky.py"
SPEC = importlib.util.spec_from_file_location("triage_pd_ci_flaky", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SOURCE_TEXT = SCRIPT_PATH.read_text(encoding="utf-8")


def make_record(record_id: str = "sample") -> object:
    return MODULE.FailureRecord(
        record_id=record_id,
        source="prow",
        ci_name="pull-unit-test-next-gen-3",
        ci_url="https://example.invalid/ci",
        log_url="https://example.invalid/log",
        occurred_at="2026-03-03T00:00:00Z",
        pr_number=1,
        commit_sha="abc",
        run_id="1",
        job_id=None,
        status="FAILURE",
    )


class TriageParserTests(unittest.TestCase):
    def test_parse_signatures_ignores_goleak_download_line(self) -> None:
        log_text = "go: downloading go.uber.org/goleak v1.3.0\n"
        signatures = MODULE.parse_signatures(log_text)
        self.assertNotIn("GOLEAK", signatures)
        self.assertEqual(["UNKNOWN_FAILURE"], signatures)

    def test_parse_test_names_prioritizes_explicit_markers_over_stack_noise(self) -> None:
        log_text = """
panic: test timed out after 5m0s
    running tests:
        TestConfigTTLAfterTransferLeader (5m0s)
server_test.go:86 server_test.TestUpdateAdvertiseUrls { err = cluster.RunInitialServers() }
"""
        tests = MODULE.parse_test_names(log_text)
        self.assertIn("TestConfigTTLAfterTransferLeader", tests)
        self.assertNotIn("TestUpdateAdvertiseUrls", tests)

    def test_parse_test_names_falls_back_to_stack_when_explicit_markers_missing(self) -> None:
        log_text = """
server_test.go:86 server_test.TestUpdateAdvertiseUrls { err = cluster.RunInitialServers() }
"""
        tests = MODULE.parse_test_names(log_text)
        self.assertEqual(["TestUpdateAdvertiseUrls"], tests)

    def test_extract_evidence_collects_anchor_lines(self) -> None:
        log_text = """
[2026-03-03T00:00:00Z] INFO bootstrap done
--- FAIL: TestFoo (10.00s)
panic: test timed out after 5m0s
Condition never satisfied
"""
        evidence = MODULE.extract_evidence(log_text)
        self.assertGreaterEqual(len(evidence), 2)
        self.assertTrue(any("--- FAIL:" in line for line in evidence))
        self.assertTrue(any("panic:" in line.lower() for line in evidence))

    def test_score_issue_match_blocks_generic_unknown_flaky_match(self) -> None:
        issue = {
            "title": "some test is flaky",
            "body": "flaky in CI",
            "updatedAt": "2026-03-01T00:00:00Z",
        }
        score = MODULE.score_issue_match(
            issue,
            test_name=None,
            signatures=["UNKNOWN_FAILURE"],
            package_name=None,
        )
        self.assertEqual(0, score)

    def test_score_issue_match_requires_test_token_when_test_name_is_known(self) -> None:
        issue = {
            "title": "Data race in scheduler",
            "body": "panic and data race observed at scheduler.go:42",
            "updatedAt": "2026-03-01T00:00:00Z",
        }
        score = MODULE.score_issue_match(
            issue,
            test_name="TestConfigTTLAfterTransferLeader",
            signatures=["DATA_RACE"],
            package_name=None,
        )
        self.assertEqual(0, score)

    def test_normalize_extracted_tests_prefers_specific_and_collapses_param_subtests(self) -> None:
        tests = [
            "TestQPS/concurrency=1000,reserveN=10,limit=400000",
            "TestQPS",
            "TestTSOKeyspaceGroupManagerSuite",
            "TestTSOKeyspaceGroupManagerSuite/TestWatchFailed",
        ]
        normalized = MODULE.normalize_extracted_tests(tests)
        self.assertEqual(["TestQPS", "TestTSOKeyspaceGroupManagerSuite/TestWatchFailed"], normalized)

    def test_build_refs_match_repo_filters_non_target_repo(self) -> None:
        build = {"Refs": {"org": "pingcap", "repo": "ticdc", "pulls": [{"number": 4263}]}}
        self.assertFalse(MODULE.build_refs_match_repo(build, "tikv/pd"))
        build = {"Refs": {"org": "tikv", "repo": "pd", "pulls": [{"number": 10254}]}}
        self.assertTrue(MODULE.build_refs_match_repo(build, "tikv/pd"))

    def test_parse_failures_from_log_extracts_test_and_confidence(self) -> None:
        log_text = """
panic: test timed out after 5m0s
    running tests:
        TestConfigTTLAfterTransferLeader (5m0s)
"""
        parsed = MODULE.parse_failures_from_log(
            record=make_record("sample-1"),
            log_text=log_text,
            agent_max_log_bytes=1024 * 1024,
        )
        self.assertTrue(parsed)
        self.assertEqual("TestConfigTTLAfterTransferLeader", parsed[0].primary_test)
        self.assertGreater(parsed[0].confidence, 0.65)

    def test_parse_failures_from_log_uses_package_key_for_goleak(self) -> None:
        log_text = """
goleak: Errors on successful test run: found unexpected goroutines:
FAIL\tgithub.com/tikv/pd/client\t8.624s
"""
        parsed = MODULE.parse_failures_from_log(
            record=make_record("sample-2"),
            log_text=log_text,
            agent_max_log_bytes=1024 * 1024,
        )
        self.assertTrue(parsed)
        self.assertEqual("github.com/tikv/pd/client", parsed[0].primary_package)
        self.assertEqual("package::githubcomtikvpdclient", parsed[0].key)
        self.assertIsNone(parsed[0].test_name)

    def test_to_action_payload_schema_excludes_generated_body_fields(self) -> None:
        summary = MODULE.RunSummary(
            scanned_window_start="2026-03-04T00:00:00+00:00",
            scanned_window_end="2026-03-05T00:00:00+00:00",
            prow_records=3,
            actions_records=2,
            parsed_failures=4,
            flaky_true=2,
        )
        create = MODULE.CreateAction(
            key="testfoo",
            test_name="TestFoo",
            package_name=None,
            title="TestFoo is flaky",
            labels=["type/ci"],
            links=["https://example.invalid/ci/1"],
            ci_names=["pull-unit-test-next-gen-3"],
            signatures=["PANIC"],
            evidence_summary="type=panic; test=TestFoo",
        )
        comment = MODULE.CommentAction(
            key="testbar",
            test_name="TestBar",
            package_name=None,
            issue_number=101,
            issue_url="https://github.com/tikv/pd/issues/101",
            new_links=["https://example.invalid/ci/2"],
            ci_names=["PD Test"],
            signatures=["DATA_RACE"],
            evidence_summary="type=data_race; test=TestBar",
        )
        payload = MODULE.to_action_payload(
            summary=summary,
            create_actions=[create],
            comment_actions=[comment],
            reopen_actions=[comment],
        )

        self.assertEqual({"window", "counts", "create", "comment", "reopen_and_comment"}, set(payload.keys()))
        self.assertEqual(1, payload["counts"]["create"])
        self.assertEqual(1, payload["counts"]["comment"])
        self.assertEqual(1, payload["counts"]["reopen_and_comment"])
        self.assertNotIn("body", payload["create"][0])
        self.assertNotIn("comment_body", payload["comment"][0])

    def test_script_has_no_gh_write_issue_ops(self) -> None:
        self.assertIsNone(re.search(r"['\"]issue['\"]\s*,\s*['\"]create['\"]", SOURCE_TEXT))
        self.assertIsNone(re.search(r"['\"]issue['\"]\s*,\s*['\"]comment['\"]", SOURCE_TEXT))
        self.assertIsNone(re.search(r"['\"]issue['\"]\s*,\s*['\"]reopen['\"]", SOURCE_TEXT))

    def test_parse_args_rejects_removed_execution_mode_flag(self) -> None:
        with mock.patch.object(sys, "argv", ["triage_pd_ci_flaky.py", "--mode", "auto"]):
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    MODULE.parse_args()


if __name__ == "__main__":
    unittest.main()
