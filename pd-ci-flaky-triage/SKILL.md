---
name: pd-ci-flaky-triage
description: Use when asked to triage recent tikv/pd CI failures and produce flaky-issue actions; agent orchestrates staged source-specific scripts and generates issue text from raw CI logs.
---

# PD CI Flaky Triage

Run staged flaky triage for recent PD CI failures. `Prow` and `GitHub Actions` stay separate until the final reviewed triage payload is assembled, and the agent orchestrates each stage.

Workflow properties:
- source pipelines are explicit: `prow` and `actions` do not share an early normalized record type
- all stage handoff happens through JSON artifacts
- environment filtering is an agent review stage, not a keyword-only rule engine
- every GitHub action candidate is agent-reviewed before any write

## Hard Rules

1. Never use `debug_only_evidence_summary` as `### Which jobs are failing`.
2. Every create/comment/reopen action must fetch raw CI logs from `links` or `new_links`.
3. `UNKNOWN_FAILURE` never becomes a GitHub action by itself.
4. Environment-filtered cases must be emitted under output JSON `env_filtered[]` only and must not become GitHub writes.
5. Unknown cases must be emitted under output JSON `unknown[]` only.
6. Run `validate_flaky_snippets.py` before any GitHub write operation.
7. If one action fails extraction or validation, stop the whole run immediately.
8. Before any GitHub write, every action candidate must appear in `action_review_decisions.json`.
9. If one env review candidate is missing from `env_review_decisions.json`, stop the run immediately.
10. Memory path is fixed to `/Users/jiangxianjie/.codex/automations/flaky-reporter/memory.md`.
11. Memory is run history only. It must not influence snippet selection.

## Review File Contracts

`env_review_decisions.json` must contain one decision per env review candidate:

```json
{
  "decisions": [
    {
      "candidate_id": "prow:prow-pull-unit-test-next-gen-1-12345:1",
      "decision": "keep",
      "reason": "test failure is specific enough to continue"
    }
  ]
}
```

`action_review_decisions.json` must contain one decision per action review candidate:

```json
{
  "decisions": [
    {
      "candidate_id": "prow::testfoo",
      "final_action": "create",
      "canonical_target": {
        "test_name": "TestFoo",
        "package_name": null
      },
      "reason": "reproduced across PRs"
    }
  ]
}
```

Allowed env review `decision` values are:

- `keep`
- `env_filtered`

Allowed `final_action` values are:

- `create`
- `comment`
- `reopen_and_comment`
- `unknown`
- `drop`

## Workflow

1. Verify GitHub authentication.

```bash
gh auth status
```

Stop if:
- `gh auth status` fails

2. Collect recent failures and fetch raw logs.

```bash
python3 /Users/jiangxianjie/.codex/skills/pd-ci-flaky-triage/scripts/prepare_logs.py \
  --repo tikv/pd \
  --days 1
```

Outputs:
- `/tmp/prow_logs.json`: `Prow` failures with local `log_ref` paths that point to downloaded raw logs
- `/tmp/actions_logs.json`: `GitHub Actions` failures with local `log_ref` paths that point to downloaded raw logs

Intermediate artifact note:
- inspect `/tmp/prow_failures.json` or `/tmp/actions_failures.json` when you need to view the original failure CI metadata
- `/tmp/prow_failures.json`: intermediate `Prow` failure index with source item ids, CI URLs, log URLs, PR/SHA metadata, and Prow-side outcome context
- `/tmp/actions_failures.json`: intermediate `GitHub Actions` failure index with workflow/job identity, CI URLs, run/job ids, and SHA metadata

3. Parse raw logs and extract failure items.

This step reads the source-specific raw logs and extracts the failure items that later review steps use. Each item keeps the candidate test/package target, signatures, evidence lines, and the source-specific CI context.

```bash
python3 /Users/jiangxianjie/.codex/skills/pd-ci-flaky-triage/scripts/build_observations.py \
  --agent-max-log-bytes 8388608
```

Outputs:
- `/tmp/prow_observations.json`: parsed `Prow` observations with candidate ids, targets, signatures, evidence lines, source details, and log refs
- `/tmp/actions_observations.json`: parsed `GitHub Actions` observations with the same observation shape, but preserving Actions-specific source details

4. Build env review candidates and review them before continuing.

```bash
python3 /Users/jiangxianjie/.codex/skills/pd-ci-flaky-triage/scripts/build_env_review_candidates.py \
  --input-json /tmp/prow_observations.json /tmp/actions_observations.json
```

Outputs:
- `/tmp/env_review_candidates.json`: one review item per observation, including candidate id, target, CI link, log ref, signatures, and evidence lines
- `/tmp/env_review_decisions.json`: agent-authored keep-or-filter decisions with reasons

Agent must:
- read `/tmp/env_review_candidates.json`
- write `/tmp/env_review_decisions.json`
- if target identity is too weak or the failure looks like an environment problem, prefer `env_filtered` or stop

Stop if:
- any env review candidate is missing from `/tmp/env_review_decisions.json`
- env review cannot justify either `keep` or `env_filtered`

5. Build issue match candidates.

```bash
python3 /Users/jiangxianjie/.codex/skills/pd-ci-flaky-triage/scripts/build_issue_match_candidates.py \
  --repo tikv/pd \
  --input-json /tmp/prow_observations.json /tmp/actions_observations.json \
  --env-review-payload /tmp/env_review_candidates.json \
  --env-review-decisions /tmp/env_review_decisions.json
```

Outputs:
- `/tmp/issue_match_candidates.json`: grouped kept failures with ranked open/closed issue matches and any selected best match suggestion

6. Build action review candidates and review them before continuing.

```bash
python3 /Users/jiangxianjie/.codex/skills/pd-ci-flaky-triage/scripts/build_action_review_candidates.py \
  --input-json /tmp/prow_observations.json /tmp/actions_observations.json \
  --env-review-payload /tmp/env_review_candidates.json \
  --env-review-decisions /tmp/env_review_decisions.json \
  --issue-match-candidates /tmp/issue_match_candidates.json \
  --issue-labels "type/ci"
```

Outputs:
- `/tmp/action_review_candidates.json`: one grouped candidate per failure key, with links, CI names, signatures, signal summary, issue-match options, and a suggested action
- `/tmp/action_review_decisions.json`: agent-authored final decision file that approves, rewrites, downgrades, or drops every action candidate

Agent must:
- read `/tmp/action_review_candidates.json`
- review every candidate, not just `comment` or `reopen`
- write `/tmp/action_review_decisions.json`
- if any candidate lacks a clear target or the batch looks suspicious, stop before GitHub writes

Stop if:
- any action review candidate is missing from `/tmp/action_review_decisions.json`
- the reviewed batch looks suspicious enough that GitHub writes should not proceed

7. Assemble the final triage payload after review.

```bash
python3 /Users/jiangxianjie/.codex/skills/pd-ci-flaky-triage/scripts/assemble_final_triage.py \
  --action-review-candidates /tmp/action_review_candidates.json \
  --action-review-decisions /tmp/action_review_decisions.json \
  --env-review-payload /tmp/env_review_candidates.json \
  --env-review-decisions /tmp/env_review_decisions.json
```

Outputs:
- `/tmp/final_triage.json`: the final triage result with counts and the five output buckets consumed by later reporting and GitHub write steps

8. Read the final triage payload.

```bash
jq '{window, counts, env_filtered}' /tmp/final_triage.json
```

Stop if:
- batch counts or bucket contents contradict the agent review you just performed

9. Draft GitHub-facing snippets from raw logs.

Rules:
- for `create[]`, fetch evidence from `links`
- for `comment[]` and `reopen_and_comment[]`, fetch evidence from `new_links`
- for `unknown[]` and `env_filtered[]`, report them only; do not draft issue or comment text
- use `references/stack_snippet_guidelines.md`
- use `references/stack_snippet_examples.jsonl`

Outputs:
- `/tmp/pd_ci_flaky_report_draft.md`: draft markdown containing only GitHub-facing flaky report sections

10. Validate the draft.

```bash
python3 /Users/jiangxianjie/.codex/skills/pd-ci-flaky-triage/scripts/validate_flaky_snippets.py \
  --input /tmp/pd_ci_flaky_report_draft.md
```

Outputs:
- `/tmp/pd_ci_flaky_trace.json`: per-snippet traceability data tying draft sections back to source evidence
- `/tmp/pd_ci_flaky_validation_errors.json`: explicit validation failures, if any

Stop if:
- validation reports any error

11. Compose final bodies and optionally write to GitHub.

Outputs:
- final GitHub issue/comment/reopen operations, only if the task explicitly requires writing

## Decision Heuristics

### Flaky Evidence Priority

1. Existing `type/ci` flaky issue match.
2. Cross-PR reproduction within the scan window.
3. Same-SHA fail/pass flapping from prow history.
4. Otherwise treat as likely regression or insufficient flaky evidence.

### Raw Signals

Use raw signals only as hints. Do not map them 1:1 to the final excerpt.

- `DATA_RACE`: `WARNING: DATA RACE`
- `POTENTIAL_DEADLOCK`: `POTENTIAL DEADLOCK`
- `TIMEOUT_PANIC`: `panic: test timed out`
- `GOLEAK`: real goleak lines only, never `go: downloading ... goleak`
- `CONDITION_NEVER_SATISFIED`: `Condition never satisfied`
- `PANIC`: generic panic markers
- `UNKNOWN_FAILURE`: no known signal found

### Target Extraction

Prefer exact identity over suite-level identity.

1. Exact `--- FAIL: <Suite/Subtest>`
2. `=== NAME <Suite/Subtest>`
3. `Test: <Suite/Subtest>`
4. `running tests:` block
5. Package identity from `FAIL github.com/...`

Normalize parameterized subtests back to the root test when the suffix is runtime args only.

## Failure Families

Use the final excerpt shape, not the raw signature, to classify the failure.

1. `assertion / condition`
- Keep the full `Error Trace` + `Error` + `Test` block.
- If `panic: test timed out` appears later but an assertion block already exists, use the assertion block.

2. `timeout-only`
- Use `panic: test timed out` + `running tests:` + the target test frame.

3. `goleak / package`
- Keep the full `goleak: Errors on successful test run: found unexpected goroutines:` block.
- End at `FAIL <package>`.

4. `panic / package`
- Keep the panic headline, embedded stack, and `FAIL <package>`.

5. `deadlock`
- Keep the assertion header and the full deadlock report.

6. `data race / test`
- Keep a test clue plus the full data race block (`Read at`, `Previous write at`, `created at`).

7. `unknown fallback`
- `suite summary` is only a navigation clue.
- If only `--- FAIL: Suite/Subtest` is visible, search the raw log for the stronger failure block.
- If no stronger block exists, emit to `unknown[]` and stop there.

## Unknown Handling

- `UNKNOWN_FAILURE` must never create, reopen, or comment on a GitHub issue.
- Unknown items are direct outputs only.
- Keep them in JSON `unknown[]` so a human can inspect them later.

## Manual Investigation Order

1. Open the raw CI log.
2. Search for the exact test or package first.
3. Treat `--- FAIL:` summary lines as navigation, not final snippet start.
4. Pick the family whose excerpt best supports debugging.
5. If the family is still unknown after scanning the full log, report it in `unknown[]` and do not draft an issue.

## Issue Matching Guardrails

1. Open issues first, then closed issues.
2. Require exact test or package evidence for confident matching.
3. `UNKNOWN_FAILURE` must not match on generic words such as `flaky`.
4. A suite summary alone is not enough evidence for final snippet selection.
5. A matched issue is not enough by itself for `comment[]` or `reopen_and_comment[]`; re-check consistency against the selected failed CI target before writing GitHub.

## Idempotency

- Never comment the same CI link twice on the same issue.
- Never create more than one issue action for the same failure key in one run.
- Unknown items are exempt because they do not create issue actions.

## Body Format

Use this only for `create[]`, `comment[]`, and `reopen_and_comment[]`.

- `## Flaky Test`
- `### Which jobs are failing`
  - fenced code block with the selected excerpt
- `### CI link` or `### New CI link`
- `### Reason for failure (if possible)`
  - leave empty unless a human adds analysis
- `### Anything else`
  - optional short metadata

Do not use `### Stack excerpt`.

## Resources

- Low-level stage helpers only: `scripts/stage_common.py`
- Failure collection and log fetch: `scripts/prepare_logs.py`
- Observation build: `scripts/build_observations.py`
- Review candidate build: `scripts/build_env_review_candidates.py`, `scripts/build_issue_match_candidates.py`, `scripts/build_action_review_candidates.py`
- Final assembly: `scripts/assemble_final_triage.py`
- Legacy compatibility entrypoint: `scripts/triage_pd_ci_flaky.py`
- Validator: `scripts/validate_flaky_snippets.py`
- Snippet guidelines: `references/stack_snippet_guidelines.md`
- Snippet examples: `references/stack_snippet_examples.jsonl`
