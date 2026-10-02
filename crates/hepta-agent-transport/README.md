# `hepta-agent-transport` technical development contract

The transport crate owns the lowest local AgentPort carrier boundary. It authenticates the kernel peer on an already-connected Unix stream, establishes a fresh connection nonce, frames bounded payloads, enforces sequence and digest integrity, and permanently poisons a connection after an on-wire or protocol failure.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `candidate_fail_stop_authenticated_connected_stream`  
Claim ceiling: `authenticated, bounded and fail-stop already-connected AF_UNIX framing only; no socket listener, semantic principal, BrowserActor, capability, external effect, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Validate PID/UID/GID against an explicit `PeerPolicy` before accepting application bytes.
- Generate or consume a non-zero 256-bit connection nonce and bind it into every frame.
- Encode and decode the fixed 88-byte protocol header under a single absolute operation deadline.
- Reject oversized payloads before allocation, out-of-order sequences, reserved flags, digest mismatches and stale nonces.
- Expose fail-stop client/server facades that prevent reuse after uncertain wire failure.

## Non-responsibilities

- Do not bind a socket path, listen, select a semantic principal or inspect Browser API payloads.
- Do not grant pipelining, retry, replay or exactly-once external-effect semantics.
- Do not map systemd/cgroup/executable identity; that belongs to peer attestation and product custody.

## Dependency and call direction

This is a low-level leaf mechanism with exact `libc` and `sha2` dependencies. AgentPort and peer-attestation consume it. It must remain independent of codec, BrowserActor, product policy, systemd configuration, image assembly and release code. The public facade hides raw frame mutation from higher layers.

Relevant architecture:

- `docs/architecture/AUTHENTICATED_AGENT_TRANSPORT.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- `PeerIdentity`, `PeerPolicy`, `ServerConnection`, `ClientConnection`, `ReceivedRequest` and `TransportError` form the product facade.
- Protocol constants define magic, version, header/nonce/digest sizes and the 256 KiB payload ceiling.
- `self_check()` performs a local authenticated request/response round trip without creating a listener.
- Nonce injection is restricted to reviewed test paths; product acceptance uses the OS source.

The Linux-only `accepted_handoff` source API is separate from HEPTA framing.
Its closed contract is `contracts/accepted-stream-handoff.v1.json`; existing
application frame bytes, framing nonce sources and transport golden vectors do
not change. It provides these consuming custody interfaces:

| API | Arguments and result |
| --- | --- |
| `AcceptedStreamCustody::capture_before` | Consume an original stream under one fixed local `Instant`; sample native monotonic before remaining Instant duration for a conservative wire ceiling; refuse expiry or more than 20 seconds remaining |
| `AcceptedStreamCustody::capture` | Own one `UnixStream`, trusted exact local `Path`, and positive budget up to 20 seconds; return opaque non-cloneable custody |
| `HandoffReceiver::from_control` | Own an already connected `OwnedFd` AF_UNIX seqpacket control, explicit `PeerPolicy`, and trusted original local `Path`; publish a private OS-entropy challenge |
| `HandoffSender::from_control` | Own the matching control descriptor, explicit `PeerPolicy`, and bounded challenge-wait budget; authenticate the kernel peer and consume its challenge |
| `HandoffSender::send` | Consume one captured custody; enqueue one descriptor packet or permanently retire this sender, with no returned socket or automatic retry |
| `HandoffReceiver::receive` | Wait within the explicit control-wait budget; return one opaque `ReceivedAcceptedStream` with its original deadline or retire the receiver |
| `ReceivedAcceptedStream::deadline` | Check process, clock namespace, socket identity and expiry; return the same fixed `Instant` |
| `ReceivedAcceptedStream::consume_before` | Consume once into an explicit `FnOnce(UnixStream, Instant)` dispatch function; always supply original stream and fixed deadline together |

Both control endpoints require connected AF_UNIX `SOCK_SEQPACKET`, validate
actual `SO_PEERCRED` against explicit policy and retain that original peer.
Descriptor-bearing packets additionally require actual kernel
`SCM_CREDENTIALS` equal to that peer; inheriting or forwarding a control FD to
another writer does not preserve its message credentials. The sender's initial
challenge authenticates the original connection peer; it can be queued before
that endpoint enables per-message credential delivery. No caller PID, digest,
boolean, request JSON or semantic grant is accepted as kernel evidence.

`capture` reads actual `CLOCK_MONOTONIC`, boot ID and the calling thread's
actual time-namespace descriptor identity. The packet binds them to one fixed
deadline. Receiver checks the same boot and namespace, rejects future start
times, intervals over 20 seconds and expiry, and samples `Instant` before its
later monotonic sample to conservatively preserve the remaining time. Transfer,
challenge waiting and local receiver queue residence cannot renew this custody
budget. This cannot infer kernel accept time or cover time before first capture;
the future trusted service custodian must capture at its earliest ownership.

One actual `SCM_RIGHTS` fd must match the original socket's kernel `SO_COOKIE`
and descriptor device/inode, be a connected AF_UNIX `SOCK_STREAM` with the exact
configured local pathname, and expose valid kernel peer credentials. A listener,
pipe, socketpair, different pathname/socket, extra/missing rights, truncation,
unknown packet layout, wrong challenge, sequence/cookie replay or clock mismatch
refuses admission. Delivered `SCM_RIGHTS` and kernel-created `SCM_PIDFD` descriptors
are immediately adopted as `OwnedFd` under `MSG_CMSG_CLOEXEC`; refusal closes both
descriptor types while continuing ancillary parsing. `SCM_PIDFD`, including when
an inherited control option enables it, always refuses the challenge/submission
and never supplies authorization. Linux closes rights
that could not fit a truncated ancillary buffer. Replay memory is bounded to 64
accepted original sockets per control instance. Exhaustion closes that instance.

There is no custody renewal, clone, raw-stream extraction, public packet/nonce
mutation or resend API. Sender success proves packet enqueue only, not receiver
acceptance, durable execution or response delivery. Error after possible enqueue
is ambiguous and consumes local custody; it must not become an automatic retry.
Every authority entry checks its creator PID; fork children may close only their
descriptor copies. Drop never calls socket shutdown on a shared inherited socket.

This is a low-level source mechanism, not a sandbox for trusted Rust code that
duplicates raw descriptors or ignores supplied deadlines. It does not establish
live PID/executable/unit continuity, root-owned pathname custody, a principal,
installed service handoff, native Servo, or product authorization. A subsequent
identity broker/attestor and final effect boundary must perform live refresh;
the separate Linux `AcceptedProductConnection::from_received` source consumer
now passes that exact Instant into product live admission and queue residence.
Its checks refuse a late result after synchronous procfs observation or clone
setup; they do not preempt a blocking syscall. Actual same-UID host bridge tests
establish source descriptor/deadline continuity only. Approved cross-UID broker,
principal policy, installed process handoff and native owner remain separate.
There is no daemon or activation change in this addition.

This library registers no binary target. Cargo binary auto-discovery and package build scripts are disabled.

## Configuration and features

There are no Cargo features, environment variables or network addresses. Timeouts are supplied per operation and zero durations fail immediately. The protocol is Linux/Android peer-credential aware; unsupported platforms return a typed error rather than silently omitting authentication.

Registered Cargo features: none.

## State, concurrency, and failure semantics

A connection tracks one nonce, expected sequence and poison flag. Header and payload share one monotonic deadline. Any partial wire write/read, malformed frame, digest failure or uncertain response state poisons the facade; purely local preflight rejection before I/O may leave it reusable. No background task or automatic retry exists.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- Length is checked before allocation and payload digests bind canonical bytes.
- Sequence and nonce prevent cross-connection replay but do not replace semantic authorization.
- Peer credentials alone do not distinguish hostile same-UID processes.
- Errors after possible wire activity are fail stop; callers must not retry potential effects automatically.
- The narrow unsafe `SO_PEERCRED` call must remain isolated with an explicit safety argument.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `crates/hepta-agent-transport/src/facade.rs`
- `tests/transport/test_agent_transport_reference.py`
- `crates/hepta-agent-transport/tests/accepted_handoff_kernel.rs` (19 actual kernel cases, single-thread descriptor inventory, required real SO_PASSPIDFD challenge/submission cleanup and fork entry)
- `tests/test_accepted_stream_handoff.py` (closed-contract/source API correspondence)

Applicable workflows:

- `.github/workflows/agent-transport-reference.yml`
- `.github/workflows/s04-transport-custody.yml`

Contract references:

- `contracts/agent-transport.v1.json`
- `contracts/accepted-stream-handoff.v1.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run the Rust tests plus `tests/transport/test_agent_transport_reference.py`.
- Run `cargo test --locked -p hepta-agent-transport --test accepted_handoff_kernel`
  and `python3 -m unittest discover -s tests -p test_accepted_stream_handoff.py`.
  The actual same-UID corpus does not skip and checks complete FD inventory after
  each case. Its distinct-process handoff is not a cross-UID live attestation
  result; no installed/native or new-namespace execution result is claimed.
- A `DeadlineExceeded`, `UnexpectedEof` or digest/protocol error requires discarding the connection.
- Do not debug production failures by increasing frame limits or bypassing peer checks; reproduce with a bounded fixture instead.
- Protocol traces must not contain unredacted application payloads.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Protocol magic, header layout, size ceilings, sequence rules or error classification changes require a versioned contract, reference implementation update, golden corpus and compatibility decision. Never reinterpret an existing version in place.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.

The higher-level Linux live control-custodian wrapper is documented in
[`hepta-peer-attestation`](../hepta-peer-attestation/README.md). Its use of
`capture_before` fixes the original transaction before any control attestation.
The legacy duration `capture` body and kernel protocol remain unchanged.
