# TSO And MCS Lane

Review `pkg/mcs/**`, TSO-related tests, and nearby client paths with TSO semantics in mind.

Reuse `../reviewer-rules.md` for shared wording and severity defaults.

## Review Focus

- Default values or timing constants that alter failover or reset behavior
- Config values that look user-facing but are not threaded through the config surface
- Tests that miss proxy, failover, or keyspace-group specific behavior
- Changes that should trigger `make test-tso-function`

## Hard Rules

- Do not generalize TSO findings from non-TSO code paths.
- Explicitly check reset or reinit on live loops, failover behavior, and background-goroutine races when allocator or leadership flow changes.
- Prefer exact evidence from the touched files and existing TSO tests.
- Treat zero-value or default shifts and user-facing config exposure as contract review, not mere refactor noise.
- `blocking` requires a concrete semantic or compatibility risk, not just unfamiliar code.
- If the change only touches tests under `tests/server/tso/**`, bias toward `non_blocking` or `pass`.
