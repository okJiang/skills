---
name: pd-pr-review
description: Review tikv/pd pull requests end-to-end by routing the current PD PR through focused review lanes, checking issue or root-cause coverage, test strength, and lane-specific risks, then drafting local review comments before anything is posted to GitHub. Use when the user asks to review a PD PR, verify whether a PD fix truly solves the reported issue, inspect regression or test coverage on a tikv/pd pull request, or prepare review comments from a PD PR number or URL.
---

# PD PR Review

Review a tikv/pd pull request end-to-end by routing the current PR through focused internal lanes, then consolidating evidence-backed findings into a local draft before any GitHub comment is posted.

## Inputs

- Local `tikv/pd` checkout
- PR number or URL
- Optional user intent: local draft only, or publish after approval

## Shared Runtime Resources

Load these before lane selection:

- `references/reviewer-rules.md`
- `references/review-principles.md`
- `references/lane-selection.md`

Lane resources:

- Load exactly one primary lane file from `references/lanes/` for each active lane.
- Load an optional `*-question-patterns.md` or `*-checklist.md` helper only when that lane is active and the current PR needs deeper prompts or a finishing checklist.

Offline-only calibration:

- `references/offline-calibration.md`
- `references/benchmark-v1.json`
- `references/shadow-pr-corpus.jsonl`
- `evals/description-queries.json`
- `evals/review-cases.json`
- `scripts/validate_pd_pr_review.py`

Do not load offline calibration files during routine review.

## Workflow

1. Verify prerequisites.
   - Run `gh auth status`.
   - Run `git rev-parse --show-toplevel`.
   - Stop if GitHub auth is invalid or the checkout is not `tikv/pd`.
2. Collect PR context.
   - Read `gh pr view` output.
   - Read `gh pr diff` output.
   - Read `gh pr checks` output.
   - If the PR links an issue, flaky report, or explicit incident, read that before lane selection.
3. Select lanes.
   - Always include `metadata` and `tests`.
   - Add routed lanes only when the current diff, touched paths, PR body, or linked issue clearly matches the lane trigger.
   - Record one short reason per selected lane.
4. Spawn one subagent per active lane.
   Each lane gets only:
   - the PR identifier
   - the minimum diff or file context needed for that lane
   - the shared reviewer rules
   - one primary lane file
   - one optional helper file, only if needed
5. Collect lane notes.
   Each lane note must contain:
   - `Lane`
   - `Status`
   - `Checks Run`
   - `Findings`
6. Consolidate locally.
   - Deduplicate overlapping findings.
   - Keep each concern in the lane with the clearest contract ownership.
   - Drop weak or speculative findings.
   - Reuse command output across lanes instead of rerunning the same check.
7. Draft the local review.
   - Fill the output contract below.
   - Keep GitHub comment drafts local.
8. Publish gate.
   - Never post GitHub comments unless the user explicitly approves the exact local draft in this session.
   - If the user only asked for review, stop at the local draft.
9. Runtime validation.
   - Treat commands as a shared budget across the whole review.
   - Choose the narrowest repo command that resolves one concrete uncertainty.
   - `docs-only` PRs stay read-only unless the user explicitly asked for deeper validation.

## Local Output Contract

Produce these sections in order:

1. `PR Context`
2. `Active Lanes`
3. `Lane Notes`
4. `Consolidated Findings`
5. `Open Questions / Needs More Evidence`
6. `Draft Review Comments`

## Hard Rules

- This is the only installed PD review skill. Do not invoke legacy `pd-pr-review-*` specialist skills.
- Do not rely on runtime orchestration scripts. The main agent routes lanes and arbitrates findings directly.
- Each subagent reviews exactly one lane.
- `root-cause` is conditional. Use it only for explicit bugfix, regression, flaky-fix, or another concrete failure path.
- `agent-artifacts` can apply even to markdown-only or AI-facing changes.
- Historical PR material is offline calibration only. Do not load it during routine review.
- `references/reviewer-rules.md` and `references/lane-selection.md` are the runtime source of truth.
- Never post GitHub comments without explicit approval of the exact local draft.

## Active Lanes

Core lanes:

- `metadata`
- `tests`

Routed lanes:

- `root-cause`
- `config-and-compat`
- `schedule-hotpath`
- `tso-and-mcs`
- `invariants-and-boundaries`
- `observability-and-docs`
- `abstractions-and-naming`
- `agent-artifacts`

## Skill Maintenance

Use the eval fixtures and validator only when refining `pd-pr-review` itself:

- Trigger boundary checks: `evals/description-queries.json`
- Output-contract checks: `evals/review-cases.json`
- Static validator: `scripts/validate_pd_pr_review.py`
