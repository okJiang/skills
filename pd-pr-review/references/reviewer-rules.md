# Reviewer Rules

## Offline vs Online

- Use historical PR and comment data only to extract experience, guardrails, taxonomy, and benchmarks.
- Review the current PR independently from its own diff, tests, checklist, and linked issue.
- Do not require online review comments to quote or imitate historical reviewer wording.

## Default Comment Shape

- Prefer inline comments on changed lines when one concrete concern maps to one local code region.
- Prefer short, evidence-backed questions or concerns instead of generic verdicts.
- Use a summary only when multiple findings share one root cause or one architectural boundary.
- Avoid style-only comments unless the naming, API shape, or abstraction boundary changes the reader’s semantic expectations.

## Severity Principle

Question form is not low severity by itself.

Classify findings by contract impact and evidence:

- `blocking`: objective or high-confidence correctness / contract / compatibility risk
- `non_blocking`: maintainability, clarity, or future-risk concern with likely-correct behavior today
- `question`: missing rationale, scope clarification, or edge-case probe with incomplete evidence

## Typical `blocking` Triggers

- Wrong-typed input is accepted or silently falls back to a default
- Generic config or API path bypasses specialized validation
- Zero-value, default, rollback, or downgrade semantics are ambiguous
- Handler behavior, swagger, release-note, or checklist claim drifts from implementation
- New tests no longer validate the reported trigger or root cause
- Concurrency, failover, reset, or lifecycle changes create a concrete stale-state or race risk

## Typical `non_blocking` Triggers

- Naming is imprecise but runtime behavior still looks correct
- Responsibility boundaries feel mixed without a proven bug
- Cleanup, extraction, or simplification would reduce future confusion
- Observability, docs, or manual verification detail is helpful but not essential
- AI-facing skill or docs content is mostly true but too tool-specific or too verbose

## Typical `question` Triggers

- The author’s intended scope is unclear
- A new step, branch, or file may be unnecessary
- An edge case may already be handled elsewhere, but the diff does not prove it
- A PR may be directionally right, but more local evidence is needed before escalating

## Evidence Expectations

- `blocking`: cite the current diff plus the violated contract, trigger path, or assertion mismatch
- `non_blocking`: cite the current diff plus the maintainability or clarity reason
- `question`: anchor one precise uncertainty to current changed code or PR text

## Output Heuristics

- If confidence is below `0.90`, bias toward `question` unless the mismatch is objective.
- If one root cause creates several local comments, keep one summary plus the minimum inline anchors.
- Preserve question-shaped wording when it improves collaboration, even for `blocking`.

## Lane Return Shape

Each lane should return one concise note with:

- `Lane`
- `Status`: `pass`, `findings`, or `needs_more_evidence`
- `Checks Run`
- `Findings`: zero or more items with severity, local evidence, and why it matters

If another lane owns the same concern more clearly, hand it off in one sentence instead of duplicating the finding.

## Validation Budget

- Runtime validation is optional and shared across the whole review.
- Prefer zero commands for docs-only or obviously scoped PRs.
- When a command is needed, choose the narrowest repo command that resolves one concrete uncertainty.
- Reuse command results across lanes; do not rerun the same check from multiple lanes.
