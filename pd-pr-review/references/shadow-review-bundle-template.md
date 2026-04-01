# Shadow Review Bundle Template

Use this as the canonical layout for a Phase 3 shadow-review artifact bundle.

## Top-level layout

- `batch-manifest.json`
  - generated timestamp
  - repo path
  - selected corpus filter or explicit PR list
  - one manifest entry per PR bundle
- `README.md`
  - operator-facing usage notes for the batch
- `pr-<number>/`
  - one directory per selected PR

## Per-PR layout

- `source-record.json`
  - corpus-derived category metadata or direct-selection metadata
- `plan.json`
  - output of `scripts/orchestrate_pd_pr_review.py`
- `lane-results/`
  - `<lane>.template.json` starter payload for every review lane in the plan
  - `<lane>.json` actual completed result file written by the operator or agent
  - `README.md` listing the selected lanes for the PR
- `arbiter/`
  - `dry-run-command.txt` prints the arbiter decision
  - `capture-decision-command.txt` writes the decision to `decision.json`
  - `decision.template.json` reserves the raw arbiter-output shape
  - `final-proposed-comments.md` summarizes the postable comments for human review
- `evaluation/`
  - `manual-score.csv` uses the shared scorecard header from `/Users/jiangxianjie/.slock/agents/f873b63d-f306-4f48-aeb1-420921233381/handoff/pd-review-shadow-pilot/pd-shadow-review-scorecard-v1-2026-03-20.md`
    - unmatched `miss` rows should leave `model_finding_ref`, `claimed_severity`, and `skill_status` blank
  - `case-summary.md` records the case-level verdict (`pass` / `soft fail` / `precision fail` / `artifact retry`)
- `notes/shadow-summary.md`
  - concise narrative summary for the PR-level shadow run
- `notes/manual-comparison.md`
  - free-form narrative notes that should not redefine the formal scorecard taxonomy

## Ground rules

- Do not create a second plan format beside `plan.json`.
- Keep lane-result payloads grounded in the current PR; historical review data remains offline calibration only.
- Treat the manual comparison notes as narrative only; the formal row schema lives in the shared scorecard contract.
