# Review Principles

## Core stance

- Treat empirical maintainer behavior as higher-signal than any half-finished local review architecture.
- Use historical PRs and comments to extract guardrails, benchmark cases, and failure modes.
- Do not require online review to quote, mimic, or cite historical comments.

## PD reviewer style

- The dominant pattern is question-driven and inline-comment-first.
- Review tends to converge through evidence-backed questions and concerns, then end in `APPROVED`.
- The absence of `CHANGES_REQUESTED` is not a negative signal.

## Online review loop

1. Read the current PR as if no historical comment existed.
2. Decide which risk family the change most likely belongs to.
3. Raise the highest-value current concerns with diff-level evidence.
4. Escalate severity only from underlying risk, not from tone or punctuation.
5. Give a final verdict late, after the concrete concerns are clear.

## Anti-patterns

- Replaying historical comment wording as if it were a template.
- Emitting generic style feedback before contract or regression risks are addressed.
- Treating “question” as a weak fallback instead of a first-class review move.
