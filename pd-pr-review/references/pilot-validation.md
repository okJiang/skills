# Pilot Validation

Use this file to connect the installed PD review skill to the benchmark and eval contract before broad rollout.

## Shared rule

- Benchmark cases calibrate what the family should catch.
- Online review must still reason from the current PR independently.
- Passing the pilot means hitting the right concerns with current-diff evidence, not echoing historical wording.

## Benchmark source

- Structured benchmark contract: `benchmark-v1.json`

## Pilot families

### `config-and-compat`

- Primary benchmark cases:
  - `pd-10334-controller-config-rollout`
  - `pd-10246-rm-metadata-handler-api-contract`
  - `pd-10061-release-branch-affinity-rollout`
- Pass rule:
  - surface at least `expected_min_hits`
  - catch zero-value / rollback / status-code / validation-bypass style risks when present
  - keep severity aligned with `reviewer-rules.md`

### `tests`

- Primary benchmark cases:
  - `pd-9785-rm-discovery-rollout`
  - `pd-10103-affinity-stale-cache-ordering`
- Pass rule:
  - surface at least `expected_min_hits`
  - explain whether the proposed validation actually proves the claimed trigger path or regression
  - escalate test-goal drift when the new test can pass for an easier reason

### `agent-artifacts`

- Current pilot mode:
  - checklist-only dry-run using `references/checklist.md`
  - no dedicated benchmark case yet
- Pass rule:
  - catch truthfulness, context-budget, and generic-wording problems from the current diff

## Dry-run flow

1. Pick one lane or family owner.
2. Pick one benchmark case for that family.
3. Review the case or current PR and emit one `SkillResult` JSON file.
4. Check whether the output:
   - hits at least `expected_min_hits`
   - uses current-diff evidence
   - follows `blocking / non_blocking / question` from `reviewer-rules.md`
5. Only then wire the family into broader pilot usage.
