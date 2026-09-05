# hepta-agent-transport

**Module registry ID:** `hepta-agent-transport`  
**Workspace path:** `crates/hepta-agent-transport`  
**Owner class:** `transport-security`

Fail-stop authenticated framing over an already-connected AF_UNIX stream.

## Status and claim ceiling

**Current status:** `host_validated_mechanism`

**Claim ceiling:** authenticated bounded connected-stream carrier only; no listener, semantic principal, browser dispatch, capability, or external effect.

The status above describes the strongest repository-local statement this module may
make. It does not promote lower-tier source, host, headed-host, or QEMU evidence
into integrated-main, physical-hardware, signing-key-custody, or release facts.

## Responsibilities

- Read kernel peer credentials and establish a fresh connection nonce.
- Encode and decode bounded request/response frames with sequence, kind, length, digest, and one absolute monotonic deadline.
- Permanently poison a public connection after any on-wire/protocol failure while retaining safe reuse after local preflight rejection.

## Non-responsibilities

- The crate does not bind a socket path, start a listener, choose a TaskFlow principal, parse Browser API semantics, dispatch Servo, or authorize effects.
- UID/GID verification is only the first mechanism boundary; service/cgroup/executable attestation is owned by the peer-attestation layer.

## Dependency and call direction

This is a low-level leaf mechanism with only pinned cryptographic/libc dependencies. AgentPort and peer-attestation consume it. It must remain independent of codec, BrowserActor, product policy, systemd configuration, and image assembly.

The authoritative workspace membership and review links are recorded in
`manifests/modules.v1.json`. New reverse dependencies, cycles, or authority-bearing
dependencies require an explicit architecture/security review.

## Public API and binaries

The public facade owns connection state and exposes peer identity plus bounded request/response operations. Raw wire machinery is private. Callers must treat a poisoned connection as permanently unusable and create a new independently authenticated connection.

Public types and executable names are compatibility surfaces. Rust source remains
the API truth, while this document explains the intended boundary and correct use.
Callers must not infer authority from a type being constructible or a binary being
present in a non-production feature graph.

## Configuration and features

Cargo binary auto-discovery and package build scripts are disabled explicitly
with `autobins = false` and `build = false`. Only registered `[[bin]]` targets
may execute as module binaries. Adding a conventional `src/main.rs`, `src/bin`
entrypoint, or `build.rs` without a reviewed inventory change fails the module
gate; this does not disable integration-test discovery.

Maximum payload, header shape, nonce size, sequence rules, and deadline semantics are contract constants, not environment configuration. Any limit change requires a protocol/version review and cross-implementation vectors.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

Connection state is monotonic: preflight → authenticated/live → broken. Sequences begin at one and increase strictly. Partial progress never extends the absolute deadline. After bytes are consumed or emitted, framing/digest/nonce/kind/sequence/deadline errors destroy synchronization and poison the facade.

Rejected transitions and failed validation must not leave partial authority,
advanced revisions, committed responses, or invented receipt outcomes. Where a
result may be indeterminate, the caller must preserve that state and follow the
documented reconciliation policy instead of retrying blindly.

## Security invariants

Reject oversized lengths before allocation; bind canonical payload bytes with SHA-256; reject replay across connections through nonce rotation; hold exact peer credentials; never attempt stream resynchronization after an untrusted framing error. Unsafe code stays isolated to reviewed OS credential calls.

The relevant contracts and architecture documents are listed in the module
registry. A source-only self-check or fixture never proves enforcement by a booted
product image.

## Testing and evidence

Run Rust unit tests, the independent Python reference corpus, malformed/fragmented/tampered frame cases, deadline exhaustion, connection poison tests, and the exact-head transport workflow. Fuzz inputs must have memory/time limits.

Minimum local verification:

```bash
python3 tools/validate_module_documentation.py
python3 tools/validate_repository.py
python3 tools/validate_project_truth.py
cargo fmt --all --check
cargo check --workspace --all-targets --all-features --locked
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo test --workspace --all-targets --all-features --locked
```

Interpret every result under the claim ceiling and evidence tier recorded by the
gate registry. A skipped, cancelled, historical, or differently bound run is not
current evidence.

## Operations and troubleshooting

A broken-pipe result after an earlier wire error is expected fail-stop behavior. Capture the first error, peer identity, nonce/sequence metadata without payload secrets, and exact deadline. Never retry on the same byte stream.

Troubleshooting must preserve the original files, journals, identities, and exact
Git/build context needed for diagnosis. Do not make a gate pass by deleting a
hostile test, bypassing an admission check, broadening permissions, substituting a
fixture, or editing generated evidence by hand.

## Compatibility and change protocol

The wire header and error semantics are versioned contracts. Breaking changes require a new protocol version and golden vectors; silent permissive parsing is forbidden. Dependency checksum or toolchain changes invalidate host evidence.

Every behavior-changing pull request must update, as applicable: implementation,
contracts/schemas, golden vectors, tests, module registry, this README, architecture
and threat documentation, gate invalidation paths, evidence, and explicit
non-claims. Exact-head review and exact-main reruns remain separate promotion
transactions.
