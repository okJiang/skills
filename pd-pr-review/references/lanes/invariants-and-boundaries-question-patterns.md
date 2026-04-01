# Question Patterns

- What invariant makes this lock, guard, or branch necessary?
- What happens on `nil`, empty, stale, or invalid input?
- What happens if the callback, hook, or observer is `nil`, unset, or registered late?
- Do error and nil returns have different caller behavior?
- Is this boolean a real state boundary or a workaround for unclear ownership?
- What is the shutdown, retry, or background-job lifecycle?
- Can this callback fire twice, after teardown, or before the state it assumes is actually committed?
- Does the naming reveal the true precondition, or force a reader to mentally invert the logic?
