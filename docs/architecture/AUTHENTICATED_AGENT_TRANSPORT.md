# Authenticated Agent transport

**Checkpoint:** `TOS-D0C-02`  
**Status:** connected-stream carrier source is implemented; the recorded Rust
host result is `STALE_EVIDENCE` until the permanent reference workflow reruns
the exact locked Rust transport gate on the current candidate head.

## Boundary

`hepta-agent-transport` owns only the bounded local carrier. It accepts an
already-connected `AF_UNIX/SOCK_STREAM`; it does not bind a path, select an
Agent, interpret browser operations, issue a capability, or create a public
listener.

The raw framing implementation is private to the crate. Public callers receive
only the fail-stop connection facade, so a caller cannot bypass poisoned-state
handling after a wire or protocol failure.

## Authentication and replay boundary

Both endpoints verify kernel-provided peer PID/UID/GID against an explicit
`PeerPolicy`. The server then sends a fresh 256-bit nonce obtained from
`/dev/urandom`. Every request and response carries that nonce, the request
sequence, a bounded payload length, and a SHA-256 payload digest. Requests start
at sequence 1 and must arrive strictly in order. A reconnect receives a new
nonce and cannot replay a frame from the previous connection.

The production profile must use separate service identities. Peer credentials
do not distinguish two hostile processes that deliberately share the same UID;
therefore systemd unit/cgroup binding, executable/service provenance, socket
path custody, and a product principal mapping remain mandatory before a
listener is enabled.

## Framing and failure semantics

The fixed 88-byte big-endian header is defined by
`contracts/agent-transport.v1.json`. The receiver validates the advertised
length before allocation and caps payloads at 262,144 bytes. Header and payload
share one monotonic absolute deadline, preventing a peer from extending a call
indefinitely with partial progress.

The carrier treats payloads as opaque bytes. Canonical Browser API decoding,
duplicate-key rejection, effect classification, session binding, and typed
response construction belong to D0C-03/D0C-04.

The raw carrier sequence permits only strictly ordered request frames. The
product dispatch layer is additionally locked to one outstanding request per
accepted connection; the carrier does not itself grant pipelining authority.

Any error after frame I/O begins, and any kind, nonce, sequence, challenge, or
other protocol-state violation discovered after a frame is consumed,
permanently poisons the public connection. The facade immediately drops the
private carrier, closing its owned stream. Every later operation returns a
stable `BrokenPipe` transport error identifying the poisoned connection,
without attempting byte-stream resynchronization.

Pure local preflight rejection, such as a zero timeout or an oversized outbound
value rejected before any byte is written, leaves the stream usable. Sequence
exhaustion is also computed before transmission and cannot desynchronize the
carrier.

## Dependency and unsafe boundary

The two direct registry dependencies are pinned exactly:

```text
libc = 0.2.186
sha2 = 0.10.9
```

The complete transitive closure is name/version/checksum allowlisted. The only
unsafe operation is the reviewed `getsockopt(SO_PEERCRED)` FFI call; it is
isolated beside a safety argument, and no other crate receives the raw file
descriptor or credential buffer.

## Evidence and non-claims

Unit-test source covers peer rejection, nonce binding, sequence replay, digest
tampering, oversized frames, deadline exhaustion, fail-stop poisoning,
subsequent-reuse rejection, the local-preflight distinction, and a local round
trip. The permanent reference workflow installs the repository's locked Rust
1.93 toolchain and runs package-scoped `fmt`, `check`, Clippy, and test commands
on the exact transport crate.

Historical evidence remains stale whenever any declared invalidation input
changes. A fresh exact-head run is therefore required after this facade or its
contract changes.

This source is not evidence of a product socket, a running Servo session,
systemd integration, external browser authority, or merge readiness.
