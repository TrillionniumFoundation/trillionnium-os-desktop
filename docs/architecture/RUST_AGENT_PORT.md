# Rust connected AgentPort

**Checkpoint:** `TOS-D0C-04`  
**Status:** source implemented; exact-head Rust execution pending

`hepta-agent-port` is the product-owned boundary between an authenticated,
already-connected AF_UNIX stream and a future BrowserActor handler.

## Request path

```text
already-connected UnixStream
  -> SO_PEERCRED policy, nonce, sequence and SHA-256 transport binding
  -> one bounded request frame
  -> strict canonical Browser API decoding
  -> immutable DispatchContext
  -> at most one typed handler invocation
  -> request-bound canonical response
  -> same sequence and nonce transport commit
```

The crate does not bind a socket path and does not contain a listener. Socket
custody, service identity, cgroup binding and systemd activation remain a later
checkpoint.

## Dispatch context

The handler receives only mechanism facts:

- peer PID, UID and GID supplied by the kernel carrier;
- authenticated transport sequence;
- canonical request SHA-256;
- operation effect class;
- monotonic acceptance time;
- effective monotonic deadline.

The context does not contain a hidden authorization decision. Effect policy is
owned above the mechanism layer.

## Exactly-one boundary

Each accepted connection carries one request and permits at most one handler
invocation. A duplicate-member, non-canonical, over-bounded, session-invalid or
transport-invalid request fails before the handler is called.

The handler may return one bounded JSON object or one normative typed error. It
may not author protocol, request ID, session ID, session generation, transport
sequence or connection nonce. Those fields are copied from the validated
request and authenticated connection.

## Deadline model

At connection acceptance, the server ceiling is converted to a monotonic
instant. A request wall-clock deadline, when present, is converted once using
the acceptance wall/monotonic pair. The effective deadline is the earlier
instant.

A result returned after the effective deadline is discarded. No response is
committed and no automatic retry is issued.

## Handler-output bounds

Before response construction, the result/error detail tree is checked against:

- 1,024 members per object;
- 4,096 aggregate container items;
- depth 16;
- 128-byte object keys;
- 131,072-byte string values.

The canonical codec then enforces the final 256 KiB wire bound.

## D0 fixture behavior

The temporary mechanism-only handler:

- returns health with `browser_runtime_available=false`;
- refuses navigation and click/type/press/select as `policy_denied`;
- returns `unsupported` for operations requiring the absent BrowserActor/Servo
  runtime.

This fixture prevents the control path from simulating browser success.

## Claim boundary

This checkpoint proves source structure and the independently executed reference
vectors only. Until exact Rust 1.93.0 format, Clippy, tests and browserd
self-check pass against the candidate head, it is not a host-validated product
AgentPort.
