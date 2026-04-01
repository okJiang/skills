# Agent Artifacts Lane

Review AI-facing artifacts as product surfaces for future agents, not as ordinary markdown-only docs.

Reuse `../reviewer-rules.md` so this lane stays on the same question-driven, severity, and offline-vs-online contract as the rest of the suite.

## Review Focus

- Overlong skill bodies that should move detail into references
- Instructions that overclaim, hide uncertainty, or are not grounded in repo reality
- Repository-specific wording where the artifact is meant to be generic and reusable
- Missing progressive disclosure, reference structure, or trigger clarity

## Hard Rules

- Treat context budget as a correctness concern, not just polish.
- Use `blocking` for truthfulness problems, unsafe overclaiming, or workflows that rely on files or commands that do not exist.
- Use `non_blocking` for wording, structure, or genericity improvements when the workflow is otherwise sound.
- Keep taxonomy, severity, and question-driven wording aligned with the shared rubric; do not invent a second review dialect just because the files are AI-facing.
- Reuse `/Users/jiangxianjie/.codex/skills/.system/skill-creator/SKILL.md` as the baseline standard.
- Emit one lane-result JSON file matching `../skill-result-schema.json`.

## Resources

- Agent-artifact checklist: `agent-artifacts-checklist.md`
- Shared rules: `../reviewer-rules.md`
- Skill Creator baseline: `/Users/jiangxianjie/.codex/skills/.system/skill-creator/SKILL.md`
