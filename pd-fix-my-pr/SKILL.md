---
name: pd-fix-my-pr
description: Fix okJiang-owned pull requests in tikv/pd when they fail GitHub Actions Check PD / statics or are blocked by merge conflicts against the base branch. Use when the user asks to repair their PD PRs, resolve statics errors, fix branch conflicts, run narrow verification, and push the repaired branch back to origin without a separate planning step.
---

# PD Fix My PR

## Overview

Repair `okJiang`'s open `tikv/pd` PRs directly.
Identify broken PRs first, inspect the exact failure or conflict state, fix each branch in a dedicated worktree, run the narrowest credible verification, then push the repair back to the original PR branch.

## Quick Start

- Verify GitHub CLI auth:
  - `gh auth status`
- Discover broken PRs for `okJiang`:
  - `python3 "/Users/jiangxianjie/.codex/skills/pd-fix-my-pr/scripts/inspect_my_pd_prs.py" --repo "."`
- Inspect one PR only:
  - `python3 "/Users/jiangxianjie/.codex/skills/pd-fix-my-pr/scripts/inspect_my_pd_prs.py" --repo "." --pr 10444`
- Add `--json` when machine-readable output is easier.

## Workflow

1. Confirm repo and auth
   - Run inside a `tikv/pd` clone or worktree.
   - Run `gh auth status`.
   - Stop if `gh` is unauthenticated or the repo is not `tikv/pd`.

2. Discover target PRs
   - If the user gave a PR number or URL, inspect only that PR.
   - Otherwise run `inspect_my_pd_prs.py` to find open `okJiang` PRs with either:
     - failed `statics`
     - merge conflict indicators
   - Process all matching PRs one by one.

3. Prepare a safe worktree
   - Keep the current worktree clean before switching.
   - Prefer reusing an existing entry from `git worktree list` when the PR branch is already checked out.
   - Otherwise fetch `origin/<headRefName>` and create a dedicated worktree for that branch.
   - Never edit the user's unrelated dirty worktree.

4. If the problem is `statics`
   - Run `gh pr checks <pr> --json name,state,link` and isolate the `statics` check.
   - Extract the run id from the `statics` link and fetch logs with `gh run view <run-id> --log`.
   - Fix the exact linter failure first. Do not guess from the filename alone.
   - Common PD cases:
     - `gci`
     - `staticcheck`
     - `gofmt`
     - `goimports`
     - `leakcheck`
   - If the first static fix exposes a second local static failure, fix that before pushing.

5. If the problem is `conflict`
   - Read the base branch with:
     - `gh pr view <pr> --json baseRefName,headRefName,url`
   - For `okJiang`-owned branches, prefer rebasing onto the latest base branch:
     - `git fetch upstream <baseRefName>`
     - `git rebase upstream/<baseRefName>`
   - If a rebase is risky or the branch already has merge-style repair work in progress, use:
     - `git merge --no-edit upstream/<baseRefName>`
   - Resolve conflicts carefully. Preserve both:
     - the PR's intended behavior
     - required base-branch changes
   - After resolving, search for leftover markers:
     - `rg -n '<<<<<<<|=======|>>>>>>>'`

6. Verify narrowly but credibly
   - For `statics`, run the smallest package-level lint or `make static PACKAGE_DIRECTORIES=...` that proves the fix.
   - Run at least one targeted `go test` when behavior changed.
   - Follow PD failpoint discipline if the touched tests rely on failpoints.
   - Before committing, check:
     - `git status --short --branch`
     - `git diff -- <touched-files>`

7. Commit and push
   - Use focused signed commits.
   - For ordinary edits:
     - `git push origin <headRefName>`
   - After a rebase:
     - `git push --force-with-lease origin <headRefName>`
   - Do not rewrite unrelated branches.

8. Report the result
   - Include:
     - PR number and URL
     - root cause
     - files touched
     - verification commands run and their result
     - push result
     - whether GitHub checks re-triggered

## Conflict Notes

- GitHub can briefly report `mergeable` as `UNKNOWN`. Re-check once before assuming the PR is clean.
- Prefer `rebase` for `okJiang`'s own branches because the skill is meant to repair personal PR branches directly.
- If the conflict is large and a clean rebase is clearly riskier than a merge, use `merge` and say so in the report.

## Reporting Boundaries

- Ignore non-code external systems when they are not actionable from local code, but report the URL.
- If no PRs match, say so explicitly.
- If a push fails, stop and report the exact push error instead of inventing a fallback branch plan.

## Bundled Resource

### scripts/inspect_my_pd_prs.py
List `okJiang`'s open `tikv/pd` PRs and flag:
- failed `statics`
- merge conflict indicators
- branch and base info needed for direct repair
