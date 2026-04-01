# PD PR Shadow Review Playbook

## Goal

Collect a stable historical PR set, run the local PD PR review skill in dry-run mode, and measure whether auto-postable comments stay within the precision targets.

## Build the Corpus

Run:

```bash
python3 scripts/build_shadow_corpus.py \
  --repo /Users/jiangxianjie/code/pd \
  --limit 250 \
  --per-category 10 \
  --out-jsonl references/shadow-pr-corpus.jsonl
```

Target buckets:

- `bugfix`
- `schedule-config`
- `tso-mcs`
- `tests-ci`
- `refactor-no-code`

## Prepare the Batch Bundle

Run:

```bash
python3 scripts/prepare_shadow_review_batch.py \
  --repo /Users/jiangxianjie/code/pd \
  --corpus-jsonl references/shadow-pr-corpus.jsonl \
  --category schedule-config \
  --category tso-mcs \
  --limit 6 \
  --out-dir /tmp/pd-shadow-batch \
  --overwrite
```

This writes:

- `batch-manifest.json` with one entry per selected PR
- `pr-<number>/plan.json` from the orchestrator
- `pr-<number>/lane-results/*.template.json` for each selected review lane
- `pr-<number>/arbiter/dry-run-command.txt` plus `capture-decision-command.txt`
- `pr-<number>/evaluation/manual-score.csv` and `pr-<number>/evaluation/case-summary.md`
- `pr-<number>/notes/` placeholders for shadow summary and narrative comparison notes

See `references/shadow-review-bundle-template.md` for the stable artifact layout.

## Per-PR Workflow

1. Prepare the batch bundle and inspect `batch-manifest.json`.
2. Fill each selected lane output as one lane-result JSON file next to its `.template.json` starter.
3. Run the arbiter capture command so `arbiter/decision.json` is recorded for the PR bundle.
4. Score the run in `evaluation/manual-score.csv` using the shared scorecard contract.
   - For unmatched `miss` rows, leave `model_finding_ref`, `claimed_severity`, and `skill_status` blank.
5. Write the case-level verdict in `evaluation/case-summary.md` and record any extra notes in `notes/`.

## Exit Criteria

- `blocking` precision >= `0.90`
- `non_blocking` precision >= `0.80`
- no duplicate comments for the same root cause
- every auto-postable comment includes path or rule anchor plus evidence
- no run exceeds the default budget of 2 local validation commands
