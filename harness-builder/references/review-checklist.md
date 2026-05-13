# Harness Builder Review Checklist

Use this checklist before final response.

## Before Generation

- The Harness Project name and target path are known.
- The seven required domains are clear, deferred, or explicitly excluded.
- Human approval gates are explicit.
- Self-optimization policy is explicit and defaults to propose-before-changing if the user did not choose otherwise.
- External repositories are treated as references, not contents to be copied into the Harness directory.

## Generated Files

Required files:

- `AGENTS.md`
- `docs/goal.md`
- `docs/context.md`
- `docs/workflow.md`
- `docs/evaluation.md`
- `docs/artifacts.md`
- `docs/human-interaction.md`
- `docs/constraints.md`
- `docs/self-optimization.md`

## Content Checks

- `AGENTS.md` gives the agent the shortest complete operating instructions.
- `docs/goal.md` states goal, scope, non-goals, and done condition.
- `docs/context.md` lists relevant repositories without cloning or vendoring them.
- `docs/workflow.md` defines the run loop, stop conditions, and failure handling.
- `docs/evaluation.md` makes completion evidence-based.
- `docs/artifacts.md` defines human-reviewable intermediate outputs.
- `docs/human-interaction.md` minimizes interruptions while preserving approval gates.
- `docs/constraints.md` includes hard bans and default preferences.
- `docs/self-optimization.md` records proposals without silent rule drift.

## Directory Safety Checks

Use file inspection before final response:

```bash
rg --files <harness-project>
```

Pass conditions:

- Only `AGENTS.md` and files under `docs/` are present unless the user explicitly requested additional instruction-only files.
- No business source repository is copied into the Harness Project.
- No package manifests, compiled outputs, vendored dependencies, or task implementation files exist in the Harness Project.
- File names are stable and easy for a future agent to find.

## Final Response

State only:

- Created path.
- Files created.
- Validation result.
- Any unresolved inputs that were intentionally deferred.
