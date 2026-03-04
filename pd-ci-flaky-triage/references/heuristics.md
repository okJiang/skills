# Flaky Heuristics

## Evidence Priority

1. Existing flaky issue match (`type/ci`) takes precedence.
2. Cross-PR reproduction within scan window (`distinct_pr_count >= 2`).
3. Same-SHA fail/pass flapping evidence (when history provides both states).
4. Otherwise classify as likely PR regression / insufficient evidence.

## Failure Signature Extraction

Use these signatures from logs:
- `DATA_RACE`: `WARNING: DATA RACE`
- `POTENTIAL_DEADLOCK`: `POTENTIAL DEADLOCK`
- `TIMEOUT_PANIC`: `panic: test timed out`
- `GOLEAK`: lines containing `goleak` (excluding `go: downloading ... goleak`)
- `CONDITION_NEVER_SATISFIED`: `Condition never satisfied`
- `PANIC`: generic `panic:`
- `UNKNOWN_FAILURE`: no known signature found

## Test Name Extraction

Extract in this order (collect all unique matches):
1. `--- FAIL: <TestName>`
2. `=== NAME <TestName>`
3. `Test: <Suite/Test>`
4. `running tests:` block (`panic: test timed out` context)
5. Stack-style names (`pkg.TestFoo`, `suite.TestFoo/SubCase`)

If no test name is found, use signature-based key (`signature::<name>`).

## Stack Extraction

- Extract full stack *blocks* by failure type, not just keyword lines:
  - timeout panic: include goroutine dump block
  - data race: include read/write sections up to separator
  - potential deadlock: include deadlock report block
  - goleak: include unexpected goroutine block

This supports downstream high-confidence issue matching.

## Issue Matching Priority

For each failure key:
1. Open issues first, then closed issues.
2. Score by title/body match:
- exact test token in title
- test token in body
- signature phrase in title/body
 - stack token overlap (`*.go` paths and `Test*` tokens)
3. Break ties by latest `updatedAt`.

Guardrails:
- `UNKNOWN_FAILURE` must not match solely on generic words like `flaky`.
- If no confident match is found, route to triage inbox issue.

## Idempotency

- Never comment the same CI link twice on the same issue.
- Never create more than one new issue for the same failure key in one run.
- In dry-run mode, do not mutate GitHub state.
