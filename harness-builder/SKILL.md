---
name: harness-builder
description: Build task-specific Harness Project environments for AI agents. Use when the user wants to create a Harness, Harness Project, AGENTS.md-based agent workspace, repeatable agent operating environment, task loop, evaluation harness, or project directory that defines goals, context, artifacts, constraints, human review points, and self-optimization rules for future AI agent work.
---

# Harness Builder

Create a standalone Harness Project: a directory of instructions that helps an AI agent reach a task goal predictably. The Harness Project describes the goal, context, process, evidence, constraints, and improvement loop. It does not contain business source code or cloned repositories.

## Operating Rules

1. Use full-interview mode by default. Do not scaffold files until the seven required domains are clear enough to write decision-complete instructions.
2. Ask one high-impact question at a time. Prefer concrete options with pros, cons, and a recommendation when the user must choose between meaningful tradeoffs.
3. Match the user's language in the generated Harness Project unless they request another language.
4. Treat unknowns explicitly. If a required detail is unavailable, record who must provide it, when it blocks execution, and what the agent should do before it is resolved.
5. Keep the Harness Project instruction-only by default. Generate `AGENTS.md` and `docs/*.md`; do not add source repositories, copied codebases, package manifests, generated implementation files, or tool scripts.
6. Default self-optimization mode is "propose before changing": agents may record improvement proposals, but must get human confirmation before changing `AGENTS.md` or core `docs` rules.

## Required Domains

Collect and preserve these seven domains before generation:

1. Task goal: what the Harness exists to accomplish.
2. Context information: background, systems, repositories, data sources, tools, and domain facts needed for execution.
3. Evaluation standards: how success, partial success, failure, and evidence are judged.
4. Intermediate artifacts: reviewable outputs the agent must produce during work.
5. Human interaction: which decisions require human input, and how to minimize interruptions.
6. Constraints: hard bans, boundaries, preferences, security limits, and default choices under uncertainty.
7. Self-optimization: how the Harness records lessons and proposes improvements.

Use `references/interview-guide.md` for question prompts and completion cues.

## Workflow

1. Establish the Harness Project identity: name, target directory, language, and whether it supports one-shot tasks, loops, or both.
2. Run the interview across the seven required domains. Continue until each domain has concrete enough content to guide another agent.
3. Summarize the intended Harness and get confirmation only for high-impact choices, such as automation level, human approval gates, and self-optimization boundary.
4. Load `references/harness-template.md` and generate the Harness Project using the default file layout unless the user explicitly chose a different instruction-only layout.
5. Load `references/review-checklist.md` and verify the generated Harness Project before final response.
6. Final response should state the created path, files created, and validation result. Do not dump full file contents unless the user asks.

## Default Generated File Layout

Generate this structure unless the user has explicitly chosen a different instruction-only layout:

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

## External Repository Policy

Harness Projects may reference many repositories, including public and private repositories, but must not vendor or clone them into the Harness Project directory. Record repository URLs, access assumptions, checkout instructions, and ownership boundaries in `docs/context.md`. Leave fetching and maintenance to the user or to the agent running inside the Harness.

## Resources

- Interview guide: `references/interview-guide.md`
- File templates: `references/harness-template.md`
- Review checklist: `references/review-checklist.md`
