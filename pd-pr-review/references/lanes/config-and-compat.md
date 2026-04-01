# Config And Compat Lane

Compare the PR checklist, changed files, and release note against actual config and compatibility impact.

Reuse `../reviewer-rules.md` for shared wording and severity defaults.

## Review Focus

- New or changed config defaults
- HTTP API request or response shape changes
- Persistent data schema or serialization changes
- Upgrade, downgrade, or rollback compatibility impact

## Hard Rules

- Use PR checklist declarations as claims, not proof.
- Always check zero-values, wrong-type input handling, generic update paths, and status-code or swagger drift when config or API behavior changes.
- `blocking` requires an objective contract mismatch or an undeclared compatibility impact.
- `non_blocking` can cover documentation or release-note gaps once the contract risk is already clear.
- Use CODEOWNERS hits as supporting evidence, not as the only reason for a finding.
- Historical review patterns may guide suspicion, but only the current diff and contract surface can support the finding.
