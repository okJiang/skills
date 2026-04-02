# Abstractions And Naming Lane

Check whether the new abstraction makes the behavior clearer, or only moves complexity around.

## Review Focus

- Responsibility mismatch between new state and the type that stores it
- Config or rollout changes that split responsibility across API, controller, manager, or policy layers
- Helper extraction that hides important semantics
- Naming that overstates or understates the true runtime scope
- New watchers, middleware, or redirect layers that duplicate existing plumbing

## Hard Rules

- Do not emit generic “rename this” feedback without explaining the semantic mismatch.
- Prefer `blocking` only when the abstraction obscures real behavior or increases contract risk.
- Use `non_blocking` for cleanup, naming precision, or deduplication suggestions once behavior is otherwise sound.
- If the refactor is behavior-preserving and makes ownership clearer, return `pass`.

## Resources

- Shared rules: `../reviewer-rules.md`
- Question patterns: `abstractions-and-naming-question-patterns.md`
