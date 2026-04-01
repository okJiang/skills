# Tests Lane

Judge whether the PR has enough regression evidence for the kind of behavior it changes.

Reuse `../reviewer-rules.md` for shared wording and severity defaults.

## What Counts As Strong Evidence

- State-transition or scheduler logic change with matching package or integration coverage
- Callback, hook, or nil-guard change with tests for both the active path and the no-op / nil path
- TSO or MCS behavior change with targeted function or integration coverage
- Config/API change with tests or a concrete manual verification recipe in the PR body
- Existing red CI that already reproduces the affected area

## Hard Rules

- This lane does not act as a generic coverage bot.
- Check for test-goal drift: the new assertion must still validate the reported trigger, failure path, or root cause.
- `blocking` requires a concrete behavior change plus missing or mismatched validation.
- Distinguish “test added” from “test proves the fix”; if the new test can pass for an easier condition, prefer `blocking` or `question`.
- When the behavior change depends on callbacks, optional hooks, or nil guards, check that the test plan covers both the exercised path and the “nothing registered / nothing fires” path.
- If the right validation exists but has not been run yet, set `status = needs_more_evidence`; keep finding severities limited to `blocking` / `non_blocking` / `question`.
- Prefer existing repo commands such as `go test ./pkg/...` and `make test-tso-function`.
- Do not recommend full `make test` or `make check` in v1.
- Historical flaky failures calibrate the review, but current assertions and touched code are the proof.
