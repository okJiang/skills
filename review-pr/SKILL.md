---
name: review-pr
description: Review GitHub pull requests by tracing linked issues to root cause, checking whether PR description and code changes align, and evaluating solution quality (correctness, performance, readability/reusability, complexity, and test coverage). Use when a user asks to review a PR, verify if a fix truly resolves an issue, evaluate workaround vs root-cause fix, or prepare high-quality review comments before posting to GitHub.
---

# Review PR

## Overview

Perform issue-driven PR review with root-cause validation first, then quality review, and enforce local approval before any GitHub comment is posted.

## Inputs

Collect these inputs before reviewing:

- PR identifier (URL or number)
- Repository context
- Linked issue(s) or explicit problem statement
- Optional user preferences: strictness, latency sensitivity, backward compatibility constraints

If linked issue is missing, request it. If unavailable, write an explicit assumed problem statement and mark confidence.

## Workflow

### 1. Build Problem Context from Issue

- Read the linked issue title, body, and relevant discussion.
- Extract expected behavior, actual behavior, trigger conditions, and impact scope.
- Infer and state the most likely root cause.
- If root cause confidence is low, stop and discuss hypotheses with the user before final judgment.

Output section:

- `Issue Summary`
- `Root Cause Hypothesis`
- `Confidence (high/medium/low)`
- `Open Questions`

### 2. Propose an Independent Fix Direction

Before judging the PR, state how to fix the issue independently.

- Outline 1-2 feasible approaches.
- Prefer direct root-cause fixes over workaround-only patches.
- Identify likely touch points (modules/APIs/tests).

Output section:

- `My Fix Direction`
- `Tradeoffs`

### 3. Compare PR Description with Actual Diff

- Read PR title/body and extract claimed intent.
- Inspect changed files and key hunks.
- Check whether description matches implementation and constraints.
- Flag mismatches, missing rationale, or hidden behavior changes.

Output section:

- `PR Claim`
- `What Changed`
- `Consistency Check (match/partial/mismatch)`

### 4. Validate Root-Cause Coverage

Judge whether the PR actually addresses the real cause.

- If PR does not solve root cause, provide concrete modification suggestions.
- If PR is a workaround, ask whether contributor should proceed with workaround now and schedule root-cause follow-up.
- If uncertain, state uncertainty and discuss before approving.

Output section:

- `Root Cause Coverage (yes/partial/no)`
- `Gap Analysis`
- `Required Changes`

### 5. Deep Technical Review (Only if Root Cause Coverage is Yes)

Review the patch on five dimensions:

- Correctness: edge cases, state transitions, concurrency, error handling, backward compatibility.
- Performance: hot-path overhead (CPU, allocation, lock contention, network/IO amplification).
- Readability/Reusability: naming, structure, duplication, abstraction fit.
- Complexity: whether design is over-engineered; propose simpler alternatives if possible.
- Tests: missing cases, regression coverage, negative-path and stress/perf cases.

Output section:

- `Findings` (ordered by severity)
- `Risk Assessment`
- `Test Gaps`

## Comment Drafting and Approval Gate

Never post review comments to GitHub before local approval.

### Local Draft Phase (mandatory)

- Draft all review comments locally first.
- Use the structure in [references/comment-template.md](references/comment-template.md).
- Separate comments into:
  - blocking issues
  - non-blocking improvements
  - open questions

### Approval Checkpoint (mandatory)

Before any `gh` comment command:

- Present the full draft to the user.
- Ask explicit approval: `Approve posting these comments to GitHub? (yes/no)`.
- If `no`, revise locally and repeat checkpoint.
- If `yes`, post comments.

### Posting Phase

- Post only approved comments.
- Keep GitHub comments concise, actionable, and traceable to files/lines.
- After posting, summarize what was posted and any unresolved threads.

## Output Contract

For every PR review, produce this report in order:

1. `Issue Summary`
2. `Root Cause Hypothesis`
3. `My Fix Direction`
4. `PR Claim vs What Changed`
5. `Root Cause Coverage Verdict`
6. `Technical Findings` (if coverage is yes)
7. `Local Comment Draft`
8. `Approval Status` (pending/approved)
9. `Posted Comments Summary` (only after approval)

## Review Principles

- Prioritize true problem resolution over superficial diff acceptance.
- Make uncertainty explicit; discuss instead of guessing.
- Tie each finding to evidence in issue text, PR text, or code.
- Prefer minimal, correct, and maintainable fixes.
- Treat performance risk as first-class on hot paths.
