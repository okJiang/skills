---
name: pd-ci-flaky-triage
description: Use when asked to triage recent tikv/pd CI failures and produce flaky-issue actions; agent orchestrates staged source-specific scripts and generates issue text from raw CI logs.
---

# PD CI Flaky Triage

Run staged flaky triage for recent PD CI failures. `Prow` and `GitHub Actions` stay separate until the final reviewed triage payload is assembled, and the agent orchestrates each stage.

Workflow properties:
- source pipelines are explicit: `prow` and `actions` do not share an early normalized record type
- all stage handoff happens through JSON artifacts

## Hard Rules

1. Every create/comment/reopen action must format `### Which jobs are failing` from the reviewed excerpt data selected in step 3. Re-open raw CI logs only when excerpt confidence is too low or validation fails.
2. `UNKNOWN_FAILURE` never becomes a GitHub action by itself.
3. Environment-filtered cases must be emitted under output JSON `env_filtered[]` only and must not become GitHub writes.
4. Unknown cases must be emitted under output JSON `unknown[]` only.
5. If one action fails extraction or validation, stop the whole run immediately.

## Review File Contracts

`/tmp/failure_items.json` is an agent-written artifact from step 3. The file must contain:

- top-level `source`, `window`, `counts`, `failure_items`
- one `failure_items[]` item per extracted failure item
- for each failure item:
  - `candidate_id`
  - `group_key`
  - `source`
  - `source_item_id`
  - `target.test_name`
  - `target.package_name`
  - `signatures`
  - `evidence_lines`
  - `debug_only_evidence_summary`
  - `ci_name`
  - `ci_url`
  - `log_ref`
  - `occurred_at`
  - `commit_sha`
  - `status`
  - `pr_number`
  - `source_details`
  - `failure_family`
  - `excerpt_lines`
  - `excerpt_start_line`
  - `excerpt_end_line`
  - `excerpt_confidence`
  - `excerpt_reason`

## Workflow

1. Verify GitHub authentication.

```bash
gh auth status
```

Stop if:
- `gh auth status` fails

2. Collect recent failures and fetch raw logs.

```bash
python3 scripts/prepare_logs.py \
  --repo tikv/pd \
  --days 1
```

Outputs:
- `/tmp/prow_logs.json`: `Prow` failures with local `log_ref` paths that point to downloaded raw logs
- `/tmp/actions_logs.json`: `GitHub Actions` failures with local `log_ref` paths that point to downloaded raw logs

Intermediate artifact note:
- Inspect `/tmp/prow_failures.json` or `/tmp/actions_failures.json` when you need to view the original failure CI metadata
- `/tmp/prow_failures.json`: intermediate `Prow` failure index with source item ids, CI URLs, log URLs, PR/SHA metadata, and Prow-side outcome context
- `/tmp/actions_failures.json`: intermediate `GitHub Actions` failure index with workflow/job identity, CI URLs, run/job ids, and SHA metadata

3. Parse raw logs, extract failure items, and select GitHub-facing excerpts.

You should delegate the work to two subagents (one for `Prow` and one for `GitHub Actions`). For each subagent:
  1. Read the corresponding `logs.json` artifact to get the list of failures and their `log_ref` paths(`/tmp/prow_logs.json` and `/tmp/actions_logs.json`)
  2. Open each `log_ref` file directly, extract the failure items, and choose the excerpt. Use `references/stack_snippet_guidelines.md` and `references/stack_snippet_examples.jsonl` as guidelines and examples for excerpt selection.
  3. When three or more test failures appear simultaneously in a single log file, we should categorize all of them as environmental factors and exclude them from further consideration. We are saving these test failures in the `/tmp/env_filtered.json` file for future reference, and don't record them in the `/tmp/failure_items.json` file.
  4. Write `/tmp/failure_items.json`. Store the chosen excerpt on each failure item as `failure_family`, `excerpt_lines`, `excerpt_start_line`, `excerpt_end_line`, `excerpt_confidence`, and `excerpt_reason`. If the exact test name is unclear, keep the best package-level or unknown target you can defend, but still preserve signatures and evidence lines

Outputs:
- `/tmp/failure_items.json`: failure items with source context, excerpt fields, and stable candidate ids
- `/tmp/env_filtered.json`: failure items filtered out due to environmental issues

4. Read the `/tmp/failure_items.json` file and check all items. Attempt to identify which failure tests are flaky tests. Note:

- If an identical test appears three or more times within this file, it is highly likely to be a flaky test.
- If a failed test appears multiple times within a single Pull Request and no errors occurred in other pull requests, it is likely caused by specific commits in that Pull Request rather than being a genuine flaky test. In such cases, you should not identify it as a flaky test.

Outputs:
- `/tmp/flaky_tests.json`: A file containing all of the flaky tests.

5. Based on the identified flaky tests, you need to create a corresponding issue for each one. 

If an issue already exists, you should follow these steps:
1. If the issue is currently open, reply in the thread with the link where the error occurred.
2. If the issue has already been closed, you need to reopen it and then reply with the link to the error.

For every failed flaky test, you need to assign a dedicated sub-agent to handle the corresponding operations independently.

When creating a new issue, use stored `excerpt_lines` directly as the `### Which jobs are failing` code block body

## Unknown Handling

- `UNKNOWN_FAILURE` must never create, reopen, or comment on a GitHub issue.
- Unknown items are direct outputs only.
- Keep them in JSON `unknown[]` so a human can inspect them later.

## Issue Matching Guardrails

1. Open issues first, then closed issues.
2. Require exact test or package evidence for confident matching.
3. `UNKNOWN_FAILURE` must not match on generic words such as `flaky`.
4. A suite summary alone is not enough evidence for final snippet selection.
5. A matched issue is not enough by itself; re-check consistency against the selected failed CI target before writing GitHub.

## Idempotency

- Never comment the same CI link twice on the same issue.
- Never create more than one issue action for the same failure key in one run.
- Unknown items are exempt because they do not create issue actions.

## Body Format

Use this only for creating a new issue.

- `## Flaky Test`
- `### Which jobs are failing`
  - fenced code block with the selected excerpt
- `### CI link` or `### New CI link`
- `### Reason for failure (if possible)`
  - leave empty unless a human adds analysis
- `### Anything else`
  - optional short metadata

## Resources

- Failure collection and log fetch: `scripts/prepare_logs.py`
- Legacy CI collection and raw-log helpers: `scripts/triage_pd_ci_flaky.py`
- Excerpt guidelines: `references/stack_snippet_guidelines.md`
- Excerpt examples: `references/stack_snippet_examples.jsonl`
