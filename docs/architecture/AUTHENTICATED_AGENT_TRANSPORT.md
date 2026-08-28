# Authenticated Agent transport

**Checkpoint:** `TOS-D0C-02`

## Boundary

`hepta-agent-transport` owns only the bounded local carrier. It accepts an
already-connected `AF_UNIX/SOCK_STREAM`; it does not bind a path, select an
Agent, interpret browser operations, issue a capability, or create a public
listener.

## Authentication and replay boundary

Both endpoints verify kernel-provided peer PID/UID/GID against an explicit
`PeerPolicy`. The server then sends a fresh 256-bit nonce obtained from
`/dev/urandom`. Every request and response carries that nonce, the request
sequence, a bounded payload length, and a SHA-256 payload digest. Requests start
at sequence 1 and must arrive strictly in order. A reconnect receives a new
nonce and cannot replay a frame from the previous connection.

The production profile must use separate service identities. Peer credentials
do not distinguish two hostile processes that deliberately share the same UID;
therefore systemd unit/cgroup binding and socket-path custody remain mandatory
before a listener is enabled.

## Framing

The fixed 88-byte big-endian header is defined by
`contracts/agent-transport.v1.json`. The receiver validates the advertised
length before allocation and caps payloads at 262,144 bytes. Header and payload
share one monotonic absolute deadline, preventing a peer from extending a call
indefinitely with partial progress.

The carrier treats the payload as opaque bytes. Browser request JSON remains a
higher-layer responsibility and must still reject duplicate keys, unknown
fields and non-canonical shapes before dispatch.

## Evidence and non-claims

Tests use `UnixStream::pair()` and exercise peer rejection, nonce binding,
sequence replay, digest tampering, oversized frames and deadline exhaustion.
This is real carrier code, but it is not evidence of a production socket, a
running Servo session, systemd integration or remote browser authority.
