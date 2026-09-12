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

Applicable workflows:

- `.github/workflows/agent-transport-reference.yml`
- `.github/workflows/s04-transport-custody.yml`

Contract references:

- `contracts/agent-transport.v1.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run the Rust tests plus `tests/transport/test_agent_transport_reference.py`.
- A `DeadlineExceeded`, `UnexpectedEof` or digest/protocol error requires discarding the connection.
- Do not debug production failures by increasing frame limits or bypassing peer checks; reproduce with a bounded fixture instead.
- Protocol traces must not contain unredacted application payloads.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Protocol magic, header layout, size ceilings, sequence rules or error classification changes require a versioned contract, reference implementation update, golden corpus and compatibility decision. Never reinterpret an existing version in place.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.
