#!/usr/bin/env python3
"""Unit tests for pd CI flaky triage parser heuristics."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "triage_pd_ci_flaky.py"
SPEC = importlib.util.spec_from_file_location("triage_pd_ci_flaky", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class TriageParserTests(unittest.TestCase):
    def test_parse_signatures_ignores_goleak_download_line(self) -> None:
        log_text = "go: downloading go.uber.org/goleak v1.3.0\n"
        signatures = MODULE.parse_signatures(log_text)
        self.assertNotIn("GOLEAK", signatures)
        self.assertEqual(["UNKNOWN_FAILURE"], signatures)

    def test_parse_test_names_covers_running_tests_and_deadlock_stack(self) -> None:
        log_text = """
panic: test timed out after 5m0s
    running tests:
        TestConfigTTLAfterTransferLeader (5m0s)
server_test.go:86 server_test.TestUpdateAdvertiseUrls { err = cluster.RunInitialServers() }
"""
        tests = MODULE.parse_test_names(log_text)
        self.assertIn("TestConfigTTLAfterTransferLeader", tests)
        self.assertIn("TestUpdateAdvertiseUrls", tests)

    def test_extract_stack_blocks_data_race_preserves_context(self) -> None:
        log_text = """
==================
WARNING: DATA RACE
Read at 0x00c0016f8bb8 by goroutine 937:
  github.com/tikv/pd/pkg/mcs/resourcemanager/server.(*keyspaceResourceGroupManager).getServiceLimit()
      /home/prow/go/src/github.com/tikv/pd/pkg/mcs/resourcemanager/server/keyspace_manager.go:284 +0x18d
Previous write at 0x00c0016f8bb8 by goroutine 1387:
  github.com/tikv/pd/pkg/mcs/resourcemanager/server.(*serviceLimiter).setServiceLimit()
      /home/prow/go/src/github.com/tikv/pd/pkg/mcs/resourcemanager/server/service_limit.go:69 +0x205
==================
"""
        blocks = MODULE.extract_stack_blocks(log_text, signatures=["DATA_RACE"])
        self.assertTrue(blocks)
        self.assertIn("Previous write", blocks[0])
        self.assertIn("keyspace_manager.go:284", blocks[0])

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
            stack_tokens=[],
        )
        self.assertEqual(0, score)

    def test_parse_failures_from_log_agent_mode_extracts_full_block(self) -> None:
        log_text = """
panic: test timed out after 5m0s
    running tests:
        TestConfigTTLAfterTransferLeader (5m0s)

goroutine 1 [chan receive, 5 minutes]:
testing.(*T).Run(0xc0002f1c00, {0x64f33ab, 0x20}, 0x6e29400)
    /usr/local/go/src/testing/testing.go:2005 +0x9fe
"""
        record = MODULE.FailureRecord(
            record_id="sample-1",
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
        parsed = MODULE.parse_failures_from_log(
            record=record,
            log_text=log_text,
            raw_log_ref="/tmp/sample.log",
            analysis_mode="agent-full",
            agent_max_log_bytes=1024 * 1024,
            confidence_threshold=0.65,
        )
        self.assertTrue(parsed)
        self.assertEqual("TestConfigTTLAfterTransferLeader", parsed[0].primary_test)
        self.assertGreater(parsed[0].confidence, 0.65)
        self.assertTrue(parsed[0].stack_blocks)

    def test_build_issue_body_moves_triage_metadata_to_anything_else(self) -> None:
        decision = MODULE.FlakyDecision(
            key="testfoo",
            test_name="TestFoo",
            is_flaky=True,
            reason="reproduced_across_prs",
            distinct_pr_count=3,
            distinct_sha_count=4,
            has_existing_issue=False,
            existing_issue_number=None,
            confidence=0.95,
        )
        record = MODULE.FailureRecord(
            record_id="sample-2",
            source="actions",
            ci_name="PD Test",
            ci_url="https://example.invalid/ci",
            log_url="https://example.invalid/log",
            occurred_at="2026-03-03T00:00:00Z",
            pr_number=10200,
            commit_sha="abc123",
            run_id="1",
            job_id=1,
            status="FAILURE",
        )
        body = MODULE.build_issue_body(
            test_name="TestFoo",
            ci_names=["PD Test"],
            links=["https://example.invalid/ci"],
            decision=decision,
            signatures=["DATA_RACE"],
            records=[record],
            evidence_summary="timeout in TestFoo",
            stack_blocks=["stack line 1\nstack line 2"],
        )

        reason_section = body.split("### Reason for failure (if possible)\n", 1)[1].split(
            "\n### Stack excerpt",
            1,
        )[0]
        anything_else_section = body.split("### Anything else\n", 1)[1]

        self.assertEqual("", reason_section.strip())
        for marker in [
            "Auto-triage basis:",
            "Signatures:",
            "Distinct PR count in window:",
            "Distinct commit count in window:",
            "Confidence:",
            "Evidence summary:",
        ]:
            self.assertNotIn(marker, reason_section)
            self.assertIn(marker, anything_else_section)


if __name__ == "__main__":
    unittest.main()
