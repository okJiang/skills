---
name: pd-pr-review-observability-and-docs
description: Use when a tikv/pd PR adds behavior that should be debuggable in production and needs review for metrics, logs, labels, and intent comments.
---

# PD PR Review Observability And Docs

Check whether the new behavior can be understood and debugged by operators after it ships.

## Review Focus

- Metrics that are missing, duplicated, or under-labeled
- Logs that are too noisy, too weak, or missing context needed for diagnosis
- New behavior whose intent is hard to infer without comments
- API or operational contract changes whose docs drift from the code

## Hard Rules

- Do not ask for metrics or logs generically; point to the concrete runtime behavior that needs visibility.
- Use `blocking` for objective API-doc drift or a real observability gap that can hide production failures.
- Use `non_blocking` for comment or clarity improvements when the runtime behavior is already observable enough.
- If the code is self-explanatory and operationally visible, return `pass` instead of inventing docs work.
- Emit one `SkillResult` JSON file matching `../skill-result-schema.json`.

## Resources

- Shared rules: `../reviewer-rules.md`
- Review checklist: `observability-and-docs-checklist.md`
