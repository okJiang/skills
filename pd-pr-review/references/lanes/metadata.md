# Metadata Lane

Review only the stable PR contract: linked issue, checklist declarations, release note, and whether the written scope matches the diff.

## Inputs

- Normalized review context JSON from `scripts/orchestrate_pd_pr_review.py`
- Result contract: `../skill-result-schema.json`

## What To Check

- Missing or malformed `Issue Number:` line
- Empty `release-note` block on user-facing bugfix or feature PRs
- Checklist declares no config/API/persistent-data impact while touched files clearly say otherwise
- PR summary claims a narrow change but diff spans extra behavior

## Hard Rules

- Only emit `blocking` for objective mismatches that a maintainer can verify from the PR alone.
- Do not comment on wording style, English quality, or formatting nits.
- If the PR body is incomplete and the diff is ambiguous, set `status = needs_more_evidence` instead of guessing or inventing a fourth severity.
- Output one lane-result JSON file, not prose.
