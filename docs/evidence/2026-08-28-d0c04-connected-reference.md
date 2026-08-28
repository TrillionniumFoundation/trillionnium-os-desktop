# D0C-04 connected AgentPort reference evidence

**Date:** 2026-08-28  
**Claim:** independent standard-library mechanism/reference evidence

The checked-in reference uses a real AF_UNIX socketpair and Linux
`SO_PEERCRED`, the fixed D0C-02 frame, strict canonical JSON, one dispatch
context and one bounded handler result.

Recorded result:

```text
13/13 checks PASS
Python source compilation PASS
product listener created: false
BrowserActor called: false
Servo called: false
external effect authorized: false
```

The checks cover exactly-one dispatch, request/response binding, canonical
request and response digests, peer identity, sequence binding, effect-class
propagation, navigation default denial, response session binding, late-result
suppression, duplicate-member refusal before the handler and invalid handler
shape suppression.

The reference is not the Rust product implementation and does not satisfy the
exact Rust 1.93.0 promotion gate.
