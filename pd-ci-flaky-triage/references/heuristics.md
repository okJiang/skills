# Flaky Heuristics

## Evidence Priority

1. Existing `type/ci` flaky issue match.
2. Cross-PR reproduction within the scan window.
3. Same-SHA fail/pass flapping from prow history.
4. Otherwise treat as likely regression or insufficient flaky evidence.

## Signature Extraction

Use signatures only as raw hints. Do not map them 1:1 to final excerpt shape.

- `DATA_RACE`: `WARNING: DATA RACE`
- `POTENTIAL_DEADLOCK`: `POTENTIAL DEADLOCK`
- `TIMEOUT_PANIC`: `panic: test timed out`
- `GOLEAK`: real goleak lines only, never `go: downloading ... goleak`
- `CONDITION_NEVER_SATISFIED`: `Condition never satisfied`
- `PANIC`: generic panic markers
- `UNKNOWN_FAILURE`: no known signature found

## Target Extraction

Prefer exact identity over suite-level identity.

1. Exact `--- FAIL: <Suite/Subtest>`
2. `=== NAME <Suite/Subtest>`
3. `Test: <Suite/Subtest>`
4. `running tests:` block
5. Package identity from `FAIL github.com/...`

Normalize parameterized subtests back to the root test when the suffix is runtime args only.

## Failure Families

Classify by the best excerpt shape:

1. `assertion / condition`
- Use the full `Error Trace` + `Error` + `Test` block.

2. `timeout-only`
- Use `panic: test timed out` + `running tests:` + the target frame.

3. `goleak / package`
- Keep the full unexpected goroutines block through `FAIL <package>`.

4. `panic / package`
- Keep the panic headline, embedded stack, and `FAIL <package>`.

5. `deadlock`
- Keep the assertion header and the full deadlock report.

6. `data race / test`
- Keep the test clue plus the full race block.

7. `unknown fallback`
- Use suite summary only to locate the failing subtest.
- If no stronger block exists, emit to `unknown[]`.

## Unknown Handling

- `UNKNOWN_FAILURE` must never create, reopen, or comment on a GitHub issue.
- Unknown items are direct outputs only.
- Keep them in JSON `unknown[]` so a human can inspect them later.

## Issue Matching Guardrails

1. Open issues first, then closed issues.
2. Require exact test or package evidence for confident matching.
3. `UNKNOWN_FAILURE` must not match on generic words such as `flaky`.
4. A suite summary alone is not enough evidence for final snippet selection.

## Idempotency

- Never comment the same CI link twice on the same issue.
- Never create more than one issue action for the same failure key in one run.
- Unknown items are exempt because they do not create issue actions.
