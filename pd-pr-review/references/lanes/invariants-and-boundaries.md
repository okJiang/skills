---
name: pd-pr-review-invariants-and-boundaries
description: Use when a tikv/pd PR changes locks, retries, nil/error handling, background jobs, watchers, or subtle runtime guards and needs reviewer-style invariant and boundary analysis.
---

# PD PR Review Invariants And Boundaries

Review current diff behavior, not abstract code style, and explain what invariant or boundary condition the code is relying on.

## Review Focus

- Nil, empty, retry, or error branches with ambiguous caller-visible behavior
- Locks, duplicate guards, or boolean gates whose invariant is unclear
- Background jobs, callbacks, watchers, or loops with weak lifecycle ownership
- Callback or hook registration that assumes non-nil handlers or a single execution order
- Names or options that hide the true precondition or invert the logic

## Hard Rules

- Every finding must name the invariant or precondition and explain what breaks if it is wrong.
- Use `blocking` only for concrete boundary or invariant risks.
- Question wording does not lower severity.
- Historical questions are calibration only; ground the finding in the current diff.
- Emit one `SkillResult` JSON file matching `../skill-result-schema.json`.

## Resources

- Shared rules: `../reviewer-rules.md`
- Question patterns: `invariants-and-boundaries-question-patterns.md`
