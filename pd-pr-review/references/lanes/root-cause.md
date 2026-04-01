# Root-Cause Lane

Reuse the same evidence bar as `../reviewer-rules.md`, but emit structured JSON instead of prose.

## Workflow

1. Read the linked issue from the orchestrator context.
2. Write down the expected behavior, actual behavior, trigger, and likely root cause.
3. Independently sketch how you would fix it.
4. Compare that against the PR diff.
5. Emit one lane-result JSON file: finding severities stay within `blocking` / `non_blocking` / `question`, while inconclusive reviews use `status = needs_more_evidence`.

## Hard Rules

- No linked issue or explicit bugfix context means no `blocking` finding in v1.
- Compare the claimed failure path against the exact new guard, assertion, or state transition added by the patch.
- Do not approve workaround-only patches as root-cause fixes unless the issue explicitly scopes it that way.
- Every finding must quote evidence from both the issue/problem statement and the diff.
- If the patch narrows symptoms without covering the stated trigger, prefer `blocking` or `question`; do not infer correctness from similar past fixes.
- If confidence is below `0.90`, prefer `question`; if the issue or diff still lacks enough evidence to name a concrete finding, set `status = needs_more_evidence`.
