#!/usr/bin/env python3
"""Workflow-doc tests for the PD CI flaky triage skill."""

from __future__ import annotations

import pathlib
import unittest


SKILL_ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILL_MD = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
OPENAI_YAML = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
SNIPPET_GUIDELINES = (SKILL_ROOT / "references" / "stack_snippet_guidelines.md").read_text(
    encoding="utf-8",
)


class SkillWorkflowDocTests(unittest.TestCase):
    def test_step3_requires_main_agent_merge(self) -> None:
        self.assertIn("top-level `window`, `counts`, `failure_items`", SKILL_MD)
        self.assertNotIn("top-level `source`, `window`, `counts`, `failure_items`", SKILL_MD)
        self.assertIn(
            "Do not let either subagent write the merged output files directly.",
            SKILL_MD,
        )
        self.assertIn(
            "The main agent merges both sources and writes `/tmp/failure_items.json` and `/tmp/env_filtered.json`",
            SKILL_MD,
        )

    def test_issue_search_rules_are_present_in_skill_and_prompt(self) -> None:
        self.assertIn("Search open `type/ci` issues first, then closed `type/ci` issues.", SKILL_MD)
        self.assertIn("excluding PR-local repeats", OPENAI_YAML)
        self.assertIn("search existing `type/ci` issues before writing GitHub updates", OPENAI_YAML)

    def test_removed_workflow_terms_are_gone(self) -> None:
        self.assertNotIn("final reviewed triage payload", SKILL_MD)
        self.assertNotIn("unknown[]", SKILL_MD)
        self.assertNotIn("The validator enforces", SNIPPET_GUIDELINES)
        self.assertIn("## Excerpt Checklist", SNIPPET_GUIDELINES)


if __name__ == "__main__":
    unittest.main()
