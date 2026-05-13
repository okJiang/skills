# Harness Project Template

Use these templates when generating a Harness Project. Preserve the headings unless the user requested a different instruction-only structure.

## File Tree

```text
<harness-project>/
├── AGENTS.md
└── docs/
    ├── goal.md
    ├── context.md
    ├── workflow.md
    ├── evaluation.md
    ├── artifacts.md
    ├── human-interaction.md
    ├── constraints.md
    └── self-optimization.md
```

## AGENTS.md

```markdown
# Harness Instructions

## Purpose
Use this Harness to <task goal>.

## Operating Model
- Follow the workflow in `docs/workflow.md`.
- Use the evaluation standard in `docs/evaluation.md` before claiming completion.
- Produce the intermediate artifacts defined in `docs/artifacts.md`.
- Follow the human approval rules in `docs/human-interaction.md`.
- Follow all constraints in `docs/constraints.md`.

## External Repositories
- Do not clone, vendor, or maintain source repositories inside this Harness Project.
- Use `docs/context.md` to identify relevant repositories and access assumptions.
- Fetch or update external repositories only in separate workspaces when the active task requires it.

## Human Confirmation Required
- Changing this file.
- Changing core rules under `docs`.
- Taking actions listed as approval-required in `docs/human-interaction.md`.
- Any destructive, externally visible, sensitive, or costly action not already authorized.

## Self-Optimization
- Record observations and proposed improvements using `docs/self-optimization.md`.
- Do not apply core Harness changes without human confirmation.
```

## docs/goal.md

```markdown
# Goal

## Primary Goal
<What the Harness helps agents accomplish.>

## Audience
<Who uses or reviews the outputs.>

## In Scope
- <Included work.>

## Out of Scope
- <Excluded work.>

## Definition of Done
- <Concrete completion condition.>
```

## docs/context.md

```markdown
# Context

## Background
<Task background and domain facts.>

## Relevant Systems
- <System, tool, document, dashboard, or account.>

## External Repositories
| Repository | Access | Purpose | Notes |
| --- | --- | --- | --- |
| <url or name> | <public/private/unknown> | <why it matters> | <checkout or ownership notes> |

## Open Context Gaps
- <Missing information, owner, and blocking condition.>
```

## docs/workflow.md

```markdown
# Workflow

## Run Loop
1. Read `AGENTS.md` and all files under `docs`.
2. Confirm the active task fits the Harness goal.
3. Gather or refresh task-specific context.
4. Produce required intermediate artifacts.
5. Execute the allowed work.
6. Evaluate results against `docs/evaluation.md`.
7. Record unresolved issues and improvement proposals.

## Stop Conditions
- <Condition requiring pause or escalation.>

## Failure Handling
- <How to classify blocked, failed, partial, and retryable outcomes.>
```

## docs/evaluation.md

```markdown
# Evaluation

## Success Criteria
- <Criterion and required evidence.>

## Required Evidence
- <Command output, review artifact, link, document, metric, or human approval.>

## Partial Success
- <How to report incomplete but useful progress.>

## Failure
- <What counts as failure and what must be recorded.>
```

## docs/artifacts.md

```markdown
# Intermediate Artifacts

## Required Artifacts
| Artifact | Format | When Produced | Human Use |
| --- | --- | --- | --- |
| <name> | <markdown/json/table/etc.> | <phase> | <review purpose> |

## Artifact Rules
- Keep artifacts concise and human-reviewable.
- Include evidence links or file paths when relevant.
- Do not require humans to inspect raw logs unless no better summary is possible.
```

## docs/human-interaction.md

```markdown
# Human Interaction

## Approval Required
- <Action or decision.>

## Agent May Decide
- <Decision with default preference.>

## Escalation Format
When asking for human input, include:
- Decision needed.
- Recommended option.
- Alternatives and tradeoffs.
- Consequence of no response.

## Minimize Interruptions
- Batch non-urgent questions.
- Continue with documented defaults when safe.
```

## docs/constraints.md

```markdown
# Constraints

## Hard Rules
- <Non-negotiable rule.>

## Preferences
- <Preferred choice under uncertainty.>

## Forbidden Actions
- <Action the agent must not take.>

## Safety and Access Limits
- <Security, privacy, cost, production, or permission boundary.>
```

## docs/self-optimization.md

```markdown
# Self-Optimization

## Default Policy
Agents may propose improvements but must get human confirmation before changing `AGENTS.md` or core files under `docs`.

## Improvement Log
| Date | Observation | Proposed Change | Evidence | Status |
| --- | --- | --- | --- | --- |
| <date> | <what happened> | <what should change> | <artifact or run evidence> | <proposed/accepted/rejected> |

## Proposal Requirements
- Explain the problem.
- Cite evidence from a run.
- Describe the exact proposed Harness change.
- State the risk of making or not making the change.
```
