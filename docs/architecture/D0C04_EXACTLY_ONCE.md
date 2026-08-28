# D0C-04 exactly-one dispatch

Exactly-one in this checkpoint means one admitted request frame produces at
most one handler invocation within one connected stream. It does not claim
exactly-once execution of arbitrary browser or external effects. Those effects
remain disabled, and indeterminate outcomes are never replayed automatically.
