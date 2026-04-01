# Question Patterns

- Is this callback or success hook attached to the lifecycle boundary that really means the operator is complete?
- If the hook is optional or nil, what path executes, and is the no-op / nil path still safe?
- Could this registration point fire twice, too early, or after the state that it depends on has already been removed?
- Does a fixed TTL or suppression window encode an async-lag assumption that the diff never proves?
