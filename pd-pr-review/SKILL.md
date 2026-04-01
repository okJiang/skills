---
name: pd-pr-review
description: Use when reviewing a tikv/pd pull request end-to-end through one installed skill that plans lanes, dispatches sub-agents, and arbitrates findings.
---

# PD PR Review

This is the single installed PD review skill for `tikv/pd`.

Keep one public entrypoint, but split the actual review into focused internal lanes.

## Inputs

- Local `tikv/pd` checkout
- PR number or URL

## Workflow

1. Verify GitHub auth.

```bash
gh auth status
```

2. Build the normalized review plan.

```bash
python3 scripts/orchestrate_pd_pr_review.py \
  --repo /Users/jiangxianjie/code/pd \
  --pr 12345 \
  --out /tmp/pd_pr_review_plan.json
```

3. Read `/tmp/pd_pr_review_plan.json`, `references/reviewer-rules.md`, and `references/lane-selection.md`.
4. Spawn one review sub-agent per selected lane. Each sub-agent gets:
   - the normalized context JSON,
   - one lane reference from `references/lanes/`,
   - `references/skill-result-schema.json`,
   - file-read access for review,
   - only the lane-specific validation commands explicitly assigned in `lane_suggested_checks`.
5. Save one JSON result per lane under `lane-results/`.
6. Use lane names as the result `lane` values, for example `metadata` or `schedule-hotpath`.
7. Review the returned JSON files locally. Drop duplicate or weak findings before arbitration.
8. Dry-run the arbiter.

```bash
python3 scripts/arbitrate_pd_pr_review.py \
  --context-json /tmp/pd_pr_review_plan.json \
  --result-json /tmp/lane-results/metadata.json \
  --result-json /tmp/lane-results/tests.json
```

9. Post only if the user explicitly asked to publish comments.

## Hard Rules

- This is the only installed PD review skill. Do not invoke legacy `pd-pr-review-*` specialist skills.
- Historical PR data and replay notes are offline calibration only. Do not load pilot or shadow material during routine review.
- Each sub-agent reviews exactly one lane. Do not let one lane drift into another lane's contract.
- `command_budget` is a shared cap for the whole review, not a per-lane allowance.
- A sub-agent may run only the commands explicitly assigned to its lane. No assigned commands means pure read-only review.
- Run `root-cause` only when the plan selected it.
- Respect the returned `command_budget`. `docs-only` PRs get zero runtime checks.
- Never post GitHub comments without explicit user approval.
- Treat `references/normalized-pr-context-schema.json` and `references/skill-result-schema.json` as the source of truth.

## Core Lanes

- `metadata`
- `tests`

## Routed Lanes

- `root-cause`
- `config-and-compat`
- `schedule-hotpath`
- `tso-and-mcs`
- `invariants-and-boundaries`
- `observability-and-docs`
- `abstractions-and-naming`
- `agent-artifacts`

## Resources

- Shared rules: `references/reviewer-rules.md`
- Review principles: `references/review-principles.md`
- Lane selection: `references/lane-selection.md`
- Lanes: `references/lanes/`
- Context schema: `references/normalized-pr-context-schema.json`
- Result schema: `references/skill-result-schema.json`
