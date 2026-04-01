# Lane Selection

Use this file to map the current PR onto internal review lanes.

## Core Lanes

### `metadata`

- Review the stable PR contract: issue link, checklist declarations, release note, and written scope.

### `tests`

- Review whether the patch has regression proof for the claimed behavior, trigger path, or root cause.

### `root-cause`

- Add this lane only when the plan has a linked issue or a concrete problem statement that can be checked against the diff.

## Routed Lanes

### `config-and-compat`

- Trigger shape: config defaults, HTTP APIs, persistent data, zero-values, rollback, downgrade, status-code changes.

### `schedule-hotpath`

- Trigger shape: `pkg/schedule/**`, hot-region balancing, callback ordering, TTL assumptions, operator lifecycle boundaries.

### `tso-and-mcs`

- Trigger shape: `pkg/mcs/**`, TSO tests, failover logic, reset or reinit flows, user-facing TSO defaults.

### `invariants-and-boundaries`

- Trigger shape: state machines, nil/error/retry branches, locks, guards, callbacks, watchers, lifecycle ownership.

### `observability-and-docs`

- Trigger shape: metrics, logs, labels, release notes, API annotations, operational comments, manual verification recipes.

### `abstractions-and-naming`

- Trigger shape: helper extraction, middleware, watcher reuse, API/controller/manager ownership shifts, naming that may hide runtime scope.

### `agent-artifacts`

- Trigger shape: `.agents/skills/**`, `AGENTS.md`, prompt scaffolding, and other AI-facing review assets.

## Selection Rules

- Use history only as calibration. The current diff decides the active lanes.
- If a config or rollout PR crosses API plus controller or manager ownership boundaries, add `abstractions-and-naming` alongside `config-and-compat`.
- If a scheduler change also touches callback ordering, nil/no-op paths, or lifecycle boundaries, add `invariants-and-boundaries` alongside `schedule-hotpath`.
- If a TSO or MCS change also shifts user-facing defaults or config exposure, add `config-and-compat` alongside `tso-and-mcs`.
- If an AI-facing change is markdown-only, it can still require `agent-artifacts`; do not suppress it as `docs-only`.
- If one finding spans multiple lanes, keep it in the lane with the clearest contract surface and mention any crossover in the evidence.
