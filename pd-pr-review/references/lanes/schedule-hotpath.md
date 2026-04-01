---
name: pd-pr-review-schedule-hotpath
description: Use when a tikv/pd PR touches scheduler logic or hot-path balancing code and needs a high-signal review for behavior, invariants, and performance side effects.
---

# PD PR Review Schedule Hotpath

Focus on `pkg/schedule/**` and related hot-region balancing logic.

## Review Focus

- Decision thresholds or defaults changed without matching tests
- New loops, scans, or extra RPC paths on a known hot path
- State-machine or invariant changes that the PR body does not acknowledge
- Config plumbing that can silently widen scheduler behavior
- Success callbacks, operator hooks, or cache updates attached at the wrong lifecycle boundary

## Hard Rules

- Do not emit generic “this may be slower” comments without diff-based evidence.
- Prefer `go test ./pkg/schedule/...` as the suggested local check.
- Use `blocking` only for concrete invariant or regression-risk gaps.
- When the diff registers callbacks or hooks, explicitly inspect callback ordering, nil/no-op paths, and whether the chosen lifecycle boundary really means “operation complete”.
- If the change is mostly refactor with preserved behavior, return `pass`; if the hot-path evidence is still too thin to make a finding, use `SkillResult.status = needs_more_evidence`.

## Resources

- Question patterns: `schedule-hotpath-question-patterns.md`
