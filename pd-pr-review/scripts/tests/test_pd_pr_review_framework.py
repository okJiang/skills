#!/usr/bin/env python3
"""Unit tests for the shared PD PR review framework."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "pd_pr_review_framework.py"
SPEC = importlib.util.spec_from_file_location("pd_pr_review_framework", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


CODEOWNERS = """
# Require review from domain experts when the PR modified significant config files
/conf/config.toml @tikv/pd-configuration-reviewer
/server/config/config.go @tikv/pd-configuration-reviewer
/pkg/schedule/config/config.go @tikv/pd-configuration-reviewer
/pkg/schedule/schedulers/hot_region_config.go @tikv/pd-configuration-reviewer
/pkg/mcs/tso/server/config.go @tikv/pd-configuration-reviewer
""".strip()


PR_BODY = """
### What problem does this PR solve?

Fixes scheduling drift during hot region balancing.

Issue Number: Close #12345

### What is changed and how does it work?

Adjust the scheduler thresholds and thread a safer default through config.

### Check List

Tests

- Unit test
- Manual test (add detailed scripts or steps below)

Code changes

- Has the configuration change
- Has HTTP API interfaces changed (Don't forget to add the declarative for the new API)

Side effects

- Possible performance regression

### Release note

```release-note
Fix scheduler drift when hot region config is tightened.
```
""".strip()


DIFF_TEXT = """
diff --git a/pkg/schedule/schedulers/hot_region_config.go b/pkg/schedule/schedulers/hot_region_config.go
index 0000000..1111111 100644
--- a/pkg/schedule/schedulers/hot_region_config.go
+++ b/pkg/schedule/schedulers/hot_region_config.go
@@ -40,6 +40,8 @@ func buildConfig() {
     oldValue := 1
+    newValue := 2
+    threshold := oldValue + newValue
 }
diff --git a/pkg/mcs/tso/server/config.go b/pkg/mcs/tso/server/config.go
index 0000000..1111111 100644
--- a/pkg/mcs/tso/server/config.go
+++ b/pkg/mcs/tso/server/config.go
@@ -10,0 +11,2 @@ package server
+const defaultMaxResetTSGap = 2
+const defaultProxyTimeout = 3
diff --git a/docs/design/review.md b/docs/design/review.md
index 0000000..1111111 100644
--- a/docs/design/review.md
+++ b/docs/design/review.md
@@ -1,0 +1,2 @@
+line one
+line two
""".strip()


class ParseBodyTests(unittest.TestCase):
    def test_parse_pr_body_sections_extracts_issue_checklists_and_release_note(self) -> None:
        parsed = MODULE.parse_pr_body_sections(PR_BODY)

        self.assertEqual("Close #12345", parsed["issue_number"])
        self.assertIn("Fixes scheduling drift", parsed["problem_statement"])
        self.assertEqual(
            ["Unit test", "Manual test (add detailed scripts or steps below)"],
            parsed["tests"],
        )
        self.assertEqual(
            [
                "Has the configuration change",
                "Has HTTP API interfaces changed (Don't forget to add the declarative for the new API)",
            ],
            parsed["code_changes"],
        )
        self.assertEqual(["Possible performance regression"], parsed["side_effects"])
        self.assertEqual(
            "Fix scheduler drift when hot region config is tightened.",
            parsed["release_note"],
        )

    def test_parse_pr_body_sections_strips_template_html_comments(self) -> None:
        body = """
### What problem does this PR solve?

<!-- explain the issue -->
Issue Number: ref #100

### What is changed and how does it work?

<!-- describe the change -->
Real summary line.

### Release note

```release-note
None.
```
""".strip()

        parsed = MODULE.parse_pr_body_sections(body)

        self.assertEqual("ref #100", parsed["issue_number"])
        self.assertEqual("", parsed["problem_statement"])
        self.assertEqual("Real summary line.", parsed["change_summary"])


class NormalizeContextTests(unittest.TestCase):
    def test_normalize_context_collects_ci_diff_and_codeowner_hits(self) -> None:
        normalized = MODULE.normalize_pr_context(
            pr_number=123,
            pr_payload={
                "number": 123,
                "title": "schedule: tighten hot region config defaults",
                "body": PR_BODY,
                "files": [
                    {"path": "pkg/schedule/schedulers/hot_region_config.go"},
                    {"path": "pkg/mcs/tso/server/config.go"},
                    {"path": "docs/design/review.md"},
                ],
                "baseRefOid": "base-sha",
                "headRefOid": "head-sha",
            },
            issue_payload={
                "number": 12345,
                "title": "scheduler drift during hot region balancing",
                "body": "Hot region scheduling drifts after a config update.",
            },
            diff_text=DIFF_TEXT,
            codeowners_text=CODEOWNERS,
            checks_payload=[
                {"name": "Check PD", "state": "SUCCESS", "conclusion": "success"},
                {"name": "PD Test", "state": "FAILURE", "conclusion": "failure"},
            ],
        )

        self.assertEqual(123, normalized["pr_number"])
        self.assertEqual("base-sha", normalized["base_sha"])
        self.assertEqual("head-sha", normalized["head_sha"])
        self.assertEqual(
            [
                "pkg/schedule/schedulers/hot_region_config.go",
                "pkg/mcs/tso/server/config.go",
                "docs/design/review.md",
            ],
            normalized["changed_files"],
        )
        self.assertEqual(["PD Test"], normalized["ci_status"]["failing"])
        self.assertEqual("scheduler drift during hot region balancing", normalized["issue_summary"]["title"])
        self.assertEqual(
            [11, 12],
            normalized["diff_hunks"]["pkg/mcs/tso/server/config.go"],
        )
        self.assertEqual(
            [
                {
                    "pattern": "/pkg/mcs/tso/server/config.go",
                    "owners": ["@tikv/pd-configuration-reviewer"],
                    "path": "pkg/mcs/tso/server/config.go",
                },
                {
                    "pattern": "/pkg/schedule/schedulers/hot_region_config.go",
                    "owners": ["@tikv/pd-configuration-reviewer"],
                    "path": "pkg/schedule/schedulers/hot_region_config.go",
                },
            ],
            normalized["codeowners_hits"],
        )


class RiskMapTests(unittest.TestCase):
    def test_build_risk_map_selects_domain_skills_and_caps_validation_budget(self) -> None:
        context = MODULE.normalize_pr_context(
            pr_number=123,
            pr_payload={
                "number": 123,
                "title": "schedule: tighten hot region config defaults",
                "body": PR_BODY,
                "files": [
                    {"path": "pkg/schedule/schedulers/hot_region_config.go"},
                    {"path": "pkg/mcs/tso/server/config.go"},
                ],
                "baseRefOid": "base-sha",
                "headRefOid": "head-sha",
            },
            issue_payload={"title": "scheduler drift", "body": "problem"},
            diff_text=DIFF_TEXT,
            codeowners_text=CODEOWNERS,
            checks_payload=[
                {"name": "PD Test", "state": "FAILURE", "conclusion": "failure"},
            ],
        )

        risk_map = MODULE.build_risk_map(context)

        self.assertEqual(2, risk_map["command_budget"])
        self.assertEqual(
            [
                "metadata",
                "tests",
                "root-cause",
                "schedule-hotpath",
                "config-and-compat",
                "tso-and-mcs",
            ],
            risk_map["selected_lanes"],
        )
        self.assertIn("schedule-hotpath", risk_map["risk_tags"])
        self.assertIn("config-change", risk_map["risk_tags"])
        self.assertIn("tso-or-mcs", risk_map["risk_tags"])
        self.assertEqual(
            [
                "go test ./pkg/schedule/...",
                "make test-tso-function",
            ],
            risk_map["suggested_checks"],
        )

    def test_build_risk_map_skips_runtime_checks_for_docs_only_pr(self) -> None:
        context = MODULE.normalize_pr_context(
            pr_number=124,
            pr_payload={
                "number": 124,
                "title": "docs: explain review workflow",
                "body": "### What problem does this PR solve?\n\nDocs only.\n\n### Release note\n\n```release-note\nNone.\n```",
                "files": [{"path": "docs/design/review.md"}],
                "baseRefOid": "base-sha",
                "headRefOid": "head-sha",
            },
            issue_payload=None,
            diff_text="""
diff --git a/docs/design/review.md b/docs/design/review.md
@@ -1,0 +1,1 @@
+line
""".strip(),
            codeowners_text=CODEOWNERS,
            checks_payload=[],
        )

        risk_map = MODULE.build_risk_map(context)

        self.assertEqual(["docs-only"], risk_map["risk_tags"])
        self.assertEqual([], risk_map["suggested_checks"])

    def test_build_risk_map_routes_abstractions_for_config_rollout_ownership_shift(self) -> None:
        context = MODULE.normalize_pr_context(
            pr_number=10334,
            pr_payload={
                "number": 10334,
                "title": "resource_group: add per-keyspace RU version config via ControllerConfig",
                "body": "### What problem does this PR solve?\n\nNeed per-keyspace RU version config.\n\n### Release note\n\n```release-note\nNone.\n```",
                "files": [
                    {"path": "client/resource_group/controller/config.go"},
                    {"path": "client/resource_group/controller/global_controller.go"},
                    {"path": "pkg/mcs/resourcemanager/server/apis/v1/api.go"},
                    {"path": "pkg/mcs/resourcemanager/server/config.go"},
                    {"path": "pkg/mcs/resourcemanager/server/manager.go"},
                ],
                "baseRefOid": "base-sha",
                "headRefOid": "head-sha",
            },
            issue_payload={"title": "resource-group config drift", "body": "problem"},
            diff_text="""
diff --git a/client/resource_group/controller/config.go b/client/resource_group/controller/config.go
@@ -1,0 +1,1 @@
+line
diff --git a/pkg/mcs/resourcemanager/server/apis/v1/api.go b/pkg/mcs/resourcemanager/server/apis/v1/api.go
@@ -1,0 +1,1 @@
+line
diff --git a/pkg/mcs/resourcemanager/server/manager.go b/pkg/mcs/resourcemanager/server/manager.go
@@ -1,0 +1,1 @@
+line
""".strip(),
            codeowners_text="",
            checks_payload=[],
        )

        risk_map = MODULE.build_risk_map(context)

        self.assertIn("config-change", risk_map["risk_tags"])
        self.assertIn("abstractions-and-naming", risk_map["risk_tags"])
        self.assertIn("config-and-compat", risk_map["selected_lanes"])
        self.assertIn("abstractions-and-naming", risk_map["selected_lanes"])


class CommentArbiterTests(unittest.TestCase):
    def test_arbiter_deduplicates_keeps_questions_and_chooses_delivery_mode(self) -> None:
        context = MODULE.normalize_pr_context(
            pr_number=123,
            pr_payload={
                "number": 123,
                "title": "schedule: tighten hot region config defaults",
                "body": PR_BODY,
                "files": [
                    {"path": "pkg/schedule/schedulers/hot_region_config.go"},
                    {"path": "pkg/mcs/tso/server/config.go"},
                ],
                "baseRefOid": "base-sha",
                "headRefOid": "head-sha",
            },
            issue_payload={"title": "scheduler drift", "body": "problem"},
            diff_text=DIFF_TEXT,
            codeowners_text=CODEOWNERS,
            checks_payload=[],
        )

        decision = MODULE.arbitrate_skill_results(
            context=context,
            skill_results=[
                {
                    "skill": "schedule-hotpath",
                    "status": "findings",
                    "confidence": 0.95,
                    "summary": "scheduler issue found",
                    "findings": [
                        {
                            "severity": "blocking",
                            "path": "pkg/schedule/schedulers/hot_region_config.go",
                            "line": 42,
                            "title": "Missing scheduler regression test",
                            "body": "The threshold update changes scheduling behavior without matching regression coverage.",
                            "evidence": [
                                "Scheduler threshold changed in hot_region_config.go",
                                "No schedule regression test changed in the same PR",
                            ],
                            "suggested_check": "go test ./pkg/schedule/...",
                        }
                    ],
                    "checks_run": [
                        {
                            "cmd": "go test ./pkg/schedule/...",
                            "exit_code": 0,
                            "purpose": "validate touched schedule package",
                            "duration_sec": 18,
                        }
                    ],
                },
                {
                    "skill": "tests",
                    "status": "findings",
                    "confidence": 0.93,
                    "summary": "same issue from test coverage angle",
                    "findings": [
                        {
                            "severity": "blocking",
                            "path": "pkg/schedule/schedulers/hot_region_config.go",
                            "line": 42,
                            "title": "Missing scheduler regression test",
                            "body": "The threshold update changes scheduling behavior without matching regression coverage.",
                            "evidence": [
                                "Scheduler threshold changed in hot_region_config.go",
                                "No schedule regression test changed in the same PR",
                            ],
                            "suggested_check": "go test ./pkg/schedule/...",
                        },
                        {
                            "severity": "question",
                            "path": "pkg/mcs/tso/server/config.go",
                            "line": 11,
                            "title": "Should proxy timeout be configurable?",
                            "body": "This looks user facing but the config path is not obvious.",
                            "evidence": ["Touched tso config constant"],
                            "suggested_check": "",
                        },
                    ],
                    "checks_run": [],
                },
                {
                    "skill": "config-and-compat",
                    "status": "findings",
                    "confidence": 0.79,
                    "summary": "low-confidence config suggestion",
                    "findings": [
                        {
                            "severity": "non_blocking",
                            "path": "pkg/mcs/tso/server/config.go",
                            "line": None,
                            "title": "Consider documenting proxy timeout",
                            "body": "The new timeout constant may need release note detail.",
                            "evidence": ["Config file changed"],
                            "suggested_check": "",
                        }
                    ],
                    "checks_run": [],
                },
            ],
        )

        self.assertEqual(2, len(decision["postable_comments"]))
        self.assertEqual(
            ["Missing scheduler regression test", "Should proxy timeout be configurable?"],
            [item["title"] for item in decision["postable_comments"]],
        )
        self.assertEqual(
            ["inline", "inline"],
            [item["delivery"] for item in decision["postable_comments"]],
        )
        self.assertEqual(1, len(decision["local_only_findings"]))
        self.assertEqual(
            {"below-threshold"},
            {item["reason"] for item in decision["local_only_findings"]},
        )

    def test_arbiter_deduplicates_same_root_cause_even_if_severity_differs(self) -> None:
        context = MODULE.normalize_pr_context(
            pr_number=300,
            pr_payload={
                "number": 300,
                "title": "config: tighten rollout validation",
                "body": PR_BODY,
                "files": [{"path": "pkg/mcs/tso/server/config.go"}],
                "baseRefOid": "base-sha",
                "headRefOid": "head-sha",
            },
            issue_payload={"title": "rollout drift", "body": "problem"},
            diff_text=DIFF_TEXT,
            codeowners_text=CODEOWNERS,
            checks_payload=[],
        )

        decision = MODULE.arbitrate_skill_results(
            context=context,
            skill_results=[
                {
                    "skill": "config-and-compat",
                    "status": "findings",
                    "confidence": 0.95,
                    "summary": "compat issue found",
                    "findings": [
                        {
                            "severity": "blocking",
                            "path": "pkg/mcs/tso/server/config.go",
                            "line": 11,
                            "title": "Proxy timeout contract is unclear",
                            "body": "The config path changes behavior without proving rollout semantics.",
                            "evidence": [
                                "Touched tso config constant",
                                "No rollout validation evidence in the PR",
                            ],
                            "suggested_check": "make test-tso-function",
                        }
                    ],
                    "checks_run": [],
                },
                {
                    "skill": "tests",
                    "status": "findings",
                    "confidence": 0.91,
                    "summary": "same root cause from test angle",
                    "findings": [
                        {
                            "severity": "question",
                            "path": "pkg/mcs/tso/server/config.go",
                            "line": 11,
                            "title": "Proxy timeout contract is unclear",
                            "body": "Do we have a test that proves the rollout semantics here?",
                            "evidence": ["No rollout validation evidence in the PR"],
                            "suggested_check": "",
                        }
                    ],
                    "checks_run": [],
                },
            ],
        )

        self.assertEqual(1, len(decision["postable_comments"]))
        comment = decision["postable_comments"][0]
        self.assertEqual("blocking", comment["severity"])
        self.assertEqual("Proxy timeout contract is unclear", comment["title"])
        self.assertEqual("inline", comment["delivery"])
        self.assertEqual(
            [
                "Touched tso config constant",
                "No rollout validation evidence in the PR",
            ],
            comment["evidence"],
        )
        self.assertEqual([], decision["local_only_findings"])

    def test_build_risk_map_adds_agent_artifact_skill_for_agent_files(self) -> None:
        context = MODULE.normalize_pr_context(
            pr_number=200,
            pr_payload={
                "number": 200,
                "title": "agents: add pd review rubric",
                "body": "### What problem does this PR solve?\n\nImprove agent review guidance.\n\n### Release note\n\n```release-note\nNone.\n```",
                "files": [
                    {"path": ".agents/skills/pd-pr-review-rubric/SKILL.md"},
                    {"path": "AGENTS.md"},
                ],
                "baseRefOid": "base-sha",
                "headRefOid": "head-sha",
            },
            issue_payload=None,
            diff_text="""
diff --git a/.agents/skills/pd-pr-review-rubric/SKILL.md b/.agents/skills/pd-pr-review-rubric/SKILL.md
@@ -1,0 +1,2 @@
+new skill
+more lines
diff --git a/AGENTS.md b/AGENTS.md
@@ -1,0 +1,1 @@
+new instruction
""".strip(),
            codeowners_text="",
            checks_payload=[],
        )

        risk_map = MODULE.build_risk_map(context)

        self.assertIn("agent-artifact", risk_map["risk_tags"])
        self.assertIn("agent-artifacts", risk_map["selected_lanes"])
        self.assertNotIn("docs-only", risk_map["risk_tags"])


class ShadowCorpusTests(unittest.TestCase):
    def test_categorize_shadow_pr_matches_planned_buckets(self) -> None:
        self.assertEqual(
            "schedule-config",
            MODULE.categorize_shadow_pr(
                {
                    "title": "schedule: adjust hot region config",
                    "files": [
                        {"path": "pkg/schedule/schedulers/hot_region_config.go"},
                        {"path": "server/config/config.go"},
                    ],
                }
            ),
        )
        self.assertEqual(
            "tso-mcs",
            MODULE.categorize_shadow_pr(
                {
                    "title": "tso: tighten proxy defaults",
                    "files": [{"path": "pkg/mcs/tso/server/config.go"}],
                }
            ),
        )
        self.assertEqual(
            "tests-ci",
            MODULE.categorize_shadow_pr(
                {
                    "title": "tests: deflake tso integration",
                    "files": [{"path": "tests/server/tso/tso_test.go"}],
                }
            ),
        )
        self.assertEqual(
            "refactor-no-code",
            MODULE.categorize_shadow_pr(
                {
                    "title": "docs: explain review workflow",
                    "files": [{"path": "docs/design/review.md"}],
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
