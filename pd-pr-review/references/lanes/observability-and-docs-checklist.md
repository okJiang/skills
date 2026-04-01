# Observability Checklist

- If this behavior fails in production, which metric or log would identify the failing scope?
- Do metric names and labels distinguish the new behavior from existing signals?
- Could the new log path flood normal operation?
- Is there a missing comment where the control flow or key format is not recoverable from code alone?
- If the PR changes API status codes or contract surface, were annotations and generated docs kept in sync?
