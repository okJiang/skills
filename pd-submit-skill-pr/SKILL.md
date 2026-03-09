---
name: pd-submit-skill-pr
description: Use when a local skill needs to be upstreamed into tikv/pd, especially when copying from a local skills directory into the repo, aligning with `.agents/skills/`, updating `AGENTS.md`, validating the copied skill, and opening a PR with the correct issue reference and generic skill wording.
---

# PD Submit Skill PR

## Overview

Upstream an existing local skill into `tikv/pd`.
Verify the repo's skill conventions first, then copy only the files that belong in the repo and submit a clean PR.

## 1. Gather source and target context

- Start from the local skill directory, usually under `~/.codex/skills/<skill-name>`.
- Inspect the source skill files before copying anything. Do not assume every local metadata file belongs in the repo.
- In the target `tikv/pd` worktree, read `AGENTS.md` and inspect existing repo-local skills.
- Use the repo's conventions, not the local skill repo's conventions.

For `tikv/pd`, verify these facts before copying:

- skills live under `.agents/skills/`
- the skill catalog is listed in `AGENTS.md`
- repo-local skills usually contribute `SKILL.md`, not local UI metadata like `agents/openai.yaml`

## 2. Prepare a clean PR branch

- Do not reuse an unrelated branch such as a release cherry-pick branch.
- Fetch `upstream/master`.
- Create a fresh `codex/...` branch from `upstream/master`.
- Confirm the target repo is clean before copying files.

## 3. Copy the skill into the repo

- Copy the skill into `.agents/skills/<skill-name>/SKILL.md`.
- Keep the repo version generic. Do not describe it as a "Codex skill" in the repo unless the repo already uses that wording.
- Do not copy `agents/openai.yaml` into `tikv/pd` unless the repo already stores skill UI metadata there.
- If the repo keeps a skill index in `AGENTS.md`, add the new skill entry there with:
  - skill name
  - one-sentence purpose
  - prerequisites
  - docs link

## 4. Validate the copied skill

- Run the skill validator against the copied repo-local skill directory.
- If the system Python lacks `PyYAML`, create a temporary virtualenv, install `PyYAML` there, run the validator, and keep the workaround outside the repo.
- Inspect the final diff and confirm it contains only:
  - the new `.agents/skills/<skill-name>/SKILL.md`
  - any required `AGENTS.md` index update
  - no stray `.codex/` files

## 5. Choose the right issue reference

- Do not reuse an unrelated functional issue just because the workflow was inspired by it.
- Search for open issues related to skills or `AGENTS.md`:

```bash
gh issue list --repo tikv/pd --state open --search 'skill in:title,body' --limit 50
gh issue list --repo tikv/pd --state open --search 'AGENTS.md in:title,body' --limit 50
```

- Prefer the issue that directly tracks adding or improving skills.
- For general skill additions in `tikv/pd`, `#10159` is a better fit than unrelated behavior bugs because it explicitly tracks supplementing `SKILL.md`.

## 6. Commit and open the PR

- Use a broad commit message with `*:` when the change spans repo metadata and skill docs.
- Add `Signed-off-by` with `git commit -s`.
- Push to the fork branch.
- Open the PR to `tikv/pd:master`.
- In the PR title and body, call it a generic skill.
- In the PR body:
  - reference the chosen skill-related issue
  - mention the repo path under `.agents/skills/`
  - mention the `AGENTS.md` update if present
  - list validation as manual/no-code verification

## Common mistakes

- Copying the skill into `.codex/skills/` instead of `.agents/skills/`
- Including `agents/openai.yaml` from the local skill repo in `tikv/pd`
- Forgetting to update the skill table in `AGENTS.md`
- Using an unrelated issue number in the PR body
- Describing the repo change as "Codex-specific" instead of a generic skill addition
- Opening the PR from an unrelated working branch
