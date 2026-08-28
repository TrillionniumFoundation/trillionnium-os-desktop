# D0C-04 connected AgentPort Rust source evidence

**Date:** 2026-08-28  
**Claim level:** source candidate plus static/cross-implementation evidence  
**Merge readiness:** not merge-ready

## Source present

The candidate contains:

- an already-connected AF_UNIX request path;
- authenticated transport composition;
- strict canonical Browser API decoding before dispatch;
- at most one handler invocation and response per connection;
- immutable peer, sequence, request-digest, effect and deadline context;
- response identity copied from the validated request;
- canonical response SHA-256 evidence;
- independent result graph bounds;
- late-result suppression;
- a D0 fixture that permits health only, refuses potential external effects,
  and reports the absent browser runtime honestly;
- no listener, socket path, TCP endpoint, WebDriver endpoint, BrowserActor,
  Servo dependency or external-effect authority.

## Executed evidence inherited by this stack

The independent standard-library references recorded on the parent stack pass:

```text
D0C-02 transport reference: 15/15
D0C-03 codec reference:     27/27
D0C-04 bridge reference:    13/13
```

The D0C-04 Rust source audit verifies workspace/lock integration, the unchanged
registry closure, exactly-one dispatch structure, request-owned response
identity, monotonic deadline conversion, late-result suppression, effect
refusal, handler result bounds and the listener/Servo claim ceiling.

## UNEXECUTED exact-head checks

No trusted Rust 1.93 exact-head execution result is recorded yet. The following
remain **UNEXECUTED**:

```text
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo test --locked -p hepta-agent-port
cargo run --locked -p hepta-browserd -- --self-check
```

The PR must remain Draft until those commands pass against its exact head and
machine-readable evidence is updated atomically.

## Remaining gates

- TaskFlow principal-to-peer mapping;
- BrowserActor request conversion;
- default-disabled systemd socket custody;
- explicit listener enable decision;
- Servo runtime and local fixture dispatch;
- durable receipt journal and crash reconciliation.
