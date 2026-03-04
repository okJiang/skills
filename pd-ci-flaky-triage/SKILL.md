---
name: pd-ci-flaky-triage
description: Scan tikv/pd CI failures from the last 1 days (PR and push), extract concrete failing tests from Prow and GitHub Actions logs, classify flaky-vs-regression with evidence-first rules, and automatically reopen/comment/create flaky-test issues. Use when asked to triage recent PD test CI failures, especially pull-unit-test-next-gen-* and PD Test failures.
---

# PD CI Flaky Triage

Run a deterministic triage workflow for PD test CI failures and sync findings to GitHub issues.

## Workflow

1. Verify GitHub authentication with `gh auth status`.
2. Run the triage script:

```bash
python3 scripts/triage_pd_ci_flaky.py \
  --repo tikv/pd \
  --days 1 \
  --scope pr+push \
  --ci-scope test-all \
  --mode auto \
  --analysis-mode agent-full \
  --agent-max-log-bytes 8388608 \
  --inbox-issue-title "[CI triage inbox] unresolved flaky candidates" \
  --inbox-issue-labels "type/ci" \
  --flaky-policy evidence-first \
  --reopen-closed true \
  --out-json /tmp/pd_ci_flaky_triage.json
```

3. Read stdout sections in order:
- `Scanned window`
- `Failures found`
- `Flaky decisions`
- `Issue actions`
- `Skipped/Unknown`

4. If `--mode dry-run` was used, rerun with `--mode auto` to apply issue updates.

## Analysis Stages

The script now runs in two analysis stages:
- `coarse-only`: collect failure records + coarse anchors (`anchor_signatures`, `anchor_offsets`, `raw_log_ref`).
- `agent-full`: extract full stack blocks, infer `primary_test`, compute confidence, and mark `needs_inbox_fallback`.

When `agent-full` cannot confidently map a failure to a specific flaky issue, it comments into an inbox issue (auto-created if absent).

## Decision Rules

Follow evidence-first logic:
- Treat as flaky when a matching flaky issue already exists.
- Treat as flaky when the same test reproduces across multiple PRs.
- Treat as flaky when the same SHA shows fail/pass flapping in available history.
- Otherwise classify as likely PR regression (do not create flaky issue).

For matching issue behavior:
- Search open `type/ci` issues first.
- If not found, search closed `type/ci` issues.
- If closed issue matches and `--reopen-closed true`, reopen then comment.

## Operational Defaults

- Time window: rolling last 1 days.
- Scope: `pr+push`.
- CI scope: `test-all`.
- Mode: `auto`.
- Flaky policy: `evidence-first`.
- Issue language: English.

## Permissions Requirement

When running this skill inside Codex, run all commands in this workflow with sandbox escalation by default (`sandbox_permissions: require_escalated`).

This includes, but is not limited to:
- `gh` commands (auth, run/query, issue operations)
- `curl` commands (Prow pages and raw build logs)
- Any helper shell command executed during triage or validation

## Resources

- Script: `scripts/triage_pd_ci_flaky.py`
- Heuristics reference: `references/heuristics.md`
