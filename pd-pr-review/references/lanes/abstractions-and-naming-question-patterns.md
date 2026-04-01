# Question Patterns

- Does the type or helper name match the actual runtime responsibility?
- Would extracting this helper hide a boundary or precondition that should stay visible?
- Is this a real reuse win, or a new layer over existing watcher or middleware infrastructure?
- Does this option or interface name imply broader behavior than the code actually supports?
- Is duplication being reduced without making debugging or ownership harder?
