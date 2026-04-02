---
name: pd-pr-review
description: Use when reviewing a tikv/pd pull request end-to-end through one installed skill that routes lanes and coordinates sub-agents directly.
---

# PD PR Review

This is the single installed PD review skill for `tikv/pd`.

Keep one public entrypoint, but split the actual review into focused internal lanes.

Do not rely on runtime orchestration scripts. The main agent collects context, chooses lanes, and arbitrates findings directly.

## Inputs

- Local `tikv/pd` checkout
- PR number or URL

## Workflow

1. Verify GitHub auth.

```bash
gh auth status
```

2. Collect the current PR context directly from GitHub and the local checkout.

```bash
gh pr view 12345 --json number,title,body,author,baseRefName,headRefName,files,commits,labels,url,reviewDecision
gh pr diff 12345 --patch
gh pr checks 12345 --json name,state,bucket,link
```

If the PR links an issue that shapes expected behavior or scope, read that issue directly before routing `metadata` or `root-cause`.

3. Read `references/reviewer-rules.md`, `references/review-principles.md`, and `references/lane-selection.md`.
4. Choose the active lanes from the current PR.
   - Always include `metadata` and `tests`.
   - Add routed lanes only when the current diff, PR body, or linked issue clearly matches that lane.
5. Spawn one review sub-agent per active lane. Each sub-agent gets:
   - the PR number or URL,
   - the relevant files or diff hunks,
   - one lane reference from `references/lanes/`,
   - the shared rules from `references/reviewer-rules.md`.
6. Let each sub-agent inspect the repo and return one concise lane note with:
   - `Lane`
   - `Status`: `pass`, `findings`, or `needs_more_evidence`
   - `Checks Run`
   - `Findings`: zero or more evidence-backed items using `blocking`, `non_blocking`, or `question`
7. Review the returned lane notes locally. Drop duplicate or weak findings before writing review comments.
8. Draft the review locally first. Post only if the user explicitly asked to publish comments.

## Hard Rules

- This is the only installed PD review skill. Do not invoke legacy `pd-pr-review-*` specialist skills.
- Historical PR data and replay notes are offline calibration only. Do not load pilot or shadow material during routine review.
- Each sub-agent reviews exactly one lane. Do not let one lane drift into another lane's contract.
- Treat runtime validation as a shared review budget. Keep it to the minimum needed to resolve concrete uncertainty.
- Reuse command output across lanes instead of rerunning the same check from multiple sub-agents.
- `docs-only` PRs should stay read-only unless the user asked for deeper verification.
- Run `root-cause` only when the current PR clearly presents a bugfix, regression, flaky fix, or another concrete failure path.
- Never post GitHub comments without explicit user approval.
- Treat `references/reviewer-rules.md` and `references/lane-selection.md` as the source of truth.

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
- Offline calibration notes: `references/offline-calibration.md`
