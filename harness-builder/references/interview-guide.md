# Harness Builder Interview Guide

Use this guide to run a full interview before generating a Harness Project. Ask one question at a time unless the user explicitly requests a compact intake.

## Completion Rule

Every required domain must end in one of these states:

- Clear: enough concrete detail exists for another agent to act without guessing.
- Deferred: the missing detail is recorded with owner, blocking condition, and fallback.
- Excluded: the user explicitly says the domain is not relevant.

Do not generate the Harness Project while any domain is still vague.

## 1. Task Goal

Clarify:

- What exact outcome the Harness should help agents reach.
- Whether the Harness supports a one-shot task, a repeated loop, or both.
- Who consumes the final result.
- What is explicitly out of scope.

Useful questions:

- What should an agent using this Harness be able to complete?
- What result would make this Harness worth using repeatedly?
- Is this for a single run, a recurring loop, or a project that keeps evolving?
- What should the agent avoid doing even if it seems related?

Completion cue: the goal can be written as "Use this Harness to..." without needing hidden context.

## 2. Context Information

Clarify:

- Background facts and domain assumptions.
- Required systems, tools, accounts, data sources, and repositories.
- Public/private repository URLs or names, without cloning them into the Harness.
- Known constraints from teams, users, business rules, policies, or prior incidents.

Useful questions:

- What context would a capable agent still not know without your help?
- Which repositories, tools, docs, dashboards, APIs, or accounts may be involved?
- Which facts are stable rules, and which are examples or current guesses?
- Are there private resources the agent must ask for or verify access to?

Completion cue: another agent can identify where to look before doing work.

## 3. Evaluation Standards

Clarify:

- Acceptance criteria and evidence requirements.
- How to distinguish complete, partial, failed, and blocked outcomes.
- Quality bar for accuracy, safety, speed, completeness, and human review.
- Tests, checks, reviews, metrics, or artifacts that prove progress.

Useful questions:

- What evidence should the agent provide before saying the task is done?
- What failure modes matter most?
- What does "good enough" mean, and what would be unacceptable?
- Which checks are required, and which are optional?

Completion cue: success can be evaluated from artifacts and evidence, not trust.

## 4. Intermediate Artifacts

Clarify:

- Artifacts produced during each run or loop.
- File names, formats, and review timing.
- Which artifacts are for humans, which are for agent state, and which are final deliverables.
- Whether artifacts should be overwritten, versioned, or appended.

Useful questions:

- What should humans be able to inspect without reading raw logs or code?
- Which interim decisions should be recorded before execution continues?
- Should every run produce the same review bundle?
- Where should agent notes, findings, and unresolved issues live?

Completion cue: the Harness tells the agent exactly what to produce before, during, and after work.

## 5. Human Interaction

Clarify:

- Decisions requiring approval.
- Destructive, externally visible, costly, or sensitive actions.
- Escalation triggers and response format.
- Ways to reduce human interruption without losing control.

Useful questions:

- Which actions must always pause for human approval?
- Which decisions can the agent make using default preferences?
- What should the agent do when the human is unavailable?
- What information should a human receive when approval is requested?

Completion cue: the agent knows when to continue alone and when to stop.

## 6. Constraints

Clarify:

- Hard bans and non-negotiable boundaries.
- Preferred choices under uncertainty.
- Security, privacy, data handling, compliance, budget, time, and tool limits.
- Things that must not be changed.

Useful questions:

- What must the agent never do?
- What defaults should the agent choose when several paths are valid?
- Are there cost, access, privacy, or production safety limits?
- Which files, systems, branches, accounts, or environments are off limits?

Completion cue: the Harness prevents common bad paths without over-constraining valid work.

## 7. Self-Optimization

Clarify:

- What the agent should learn from each run.
- Where to record improvement proposals.
- Which changes can be made automatically, if any.
- Confirmation rules for changing core Harness instructions.

Default:

- Agents may write improvement proposals.
- Agents must request human confirmation before changing `AGENTS.md` or core files under `docs`.

Useful questions:

- What should the Harness learn from failed or inefficient runs?
- Should the agent only propose changes, or may it apply low-risk documentation updates?
- Where should proposals, decisions, and rejected ideas be recorded?
- How should the Harness preserve original intent while improving?

Completion cue: improvement is possible, but the Harness cannot silently drift away from human intent.
