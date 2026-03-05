# Stack Snippet Guidelines (Reference-Driven)

## Objective
Generate a short failure excerpt for issue body section `### Which jobs are failing`.
The excerpt must let reviewers identify, within ~30 seconds:
- failing target (`test` or `package`)
- failure class (`timeout`, `assertion`, `data race`, `deadlock`, `panic`, `goleak`)
- strongest evidence line

This replaces script-generated stack blocks. The triage script now only outputs structured actions.

## Source of Truth
Build retrieval features from:
- `tikv/pd` historical `type/ci` issue bodies
- `../pd-flaky-fix/references/flaky-pr-corpus.jsonl` (test/package semantics and fix-pattern hints)

Do not rely on a fixed hardcoded anchor whitelist as the only matching criterion.

## Output Contract
1. Put excerpt only under `### Which jobs are failing` fenced code block.
2. Keep `### Reason for failure (if possible)` empty unless human investigation adds context.
3. Prefer a single excerpt window; only include two windows when one cannot carry target + error.
4. Never dump raw long logs.

## Target Normalization
1. Parameterized subtests collapse to root test when parameter suffix is pure runtime args.
Example: `TestQPS/concurrency=1000,reserveN=10,limit=400000` -> `TestQPS`.
2. For goleak failures, prefer package identity from `FAIL <package> <duration>`.
Title should be package-oriented (for example: `GOLEAK detected in github.com/tikv/pd/client package tests`).

## Length Buckets by Failure Type
| Failure type | Recommended lines | Must include | Must remove |
|---|---:|---|---|
| timeout | 3-8 | `panic: test timed out`, `running tests`, test name | unrelated goroutine dump |
| assertion / condition | 5-12 | `Error:` + `Test:` line | repetitive `Error Trace` fan-out |
| panic | 8-20 | panic headline + 1-4 top frames + target clue | full goroutine census |
| data race | 12-30 | `WARNING: DATA RACE` + first read/write pair + target frame | repeated middleware / framework frames |
| deadlock | 12-28 | `POTENTIAL DEADLOCK` + lock holder/waiter + target frame | full lock inventory |
| goleak | 6-16 | goleak headline + first goroutine frame + `FAIL <package>` | timestamp prefixes on every line |

## Noise Filters
Drop lines matching these classes unless they are the only evidence:
- CI timestamp prefix only (`YYYY-MM-DDTHH:MM:SS...Z`)
- dependency download lines (`go: downloading ...`)
- lifecycle/info spam (`run all tasks takes`, progress bars, pass-only lines)
- repeated stack frames from generic libraries (`gin`, `grpc`, `testing`) after first 1-2 frames

## Candidate Window Scoring
Given a log, build candidate windows around learned feature clusters and score:
1. target hit score: test/package exact hit > root test hit > leaf token hit
2. evidence strength: panic/data-race/deadlock/goleak/assertion key lines
3. noise penalty: timestamp-only ratio, framework-frame ratio, repeated lines
4. compactness reward: shortest window that still keeps target + trigger + one context frame

Pick highest score; then enforce bucket line cap.

## Good vs Bad Patterns
Good:
- test/package identity and failure trigger appear in first 3-5 lines
- excerpt is self-contained without scrolling multiple pages

Bad:
- excerpt moved to `CI link`/`Reason` sections instead of `Which jobs are failing`
- 100+ line dumps where signal is diluted by middleware or repeated stack frames
- missing target identity (no `Test:` or package `FAIL` line)

## Typical Good Skeletons
Timeout:
```text
panic: test timed out after 5m0s
running tests:
  TestXxx (5m0s)
```

Condition never satisfied:
```text
Error: Condition never satisfied
Test:  TestXxx
```

Goleak package:
```text
goleak: Errors on successful test run: found unexpected goroutines:
...top goroutine frame...
FAIL github.com/tikv/pd/<pkg> 11.642s
```
