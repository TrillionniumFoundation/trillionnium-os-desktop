# `hepta-peer-attestation` technical development contract

The peer-attestation crate strengthens `SO_PEERCRED` with bounded procfs, pidfd, PID namespace, cgroup-v2, systemd unit and trusted executable evidence. It can issue one-owner request custody and cloneable non-authoritative verifiers whose revocation is latched.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `candidate_request_scoped_linux_peer_custody`  
Claim ceiling: `Linux process, namespace, cgroup, service-unit and trusted-executable continuity plus revocable request custody only; no semantic principal, browser authorization, product activation, external effect, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Read bounded `/proc/<pid>` status, stat, cgroup, namespace and executable information without following untrusted paths.
- Hold a pidfd and verify process liveness before and after policy evaluation.
- Resolve reviewed service account names and compare exact IDs, cgroup, unit and executable digest.
- Detect process identity drift and namespace ambiguity.
- Provide request-scoped custody/verifier objects that fail permanently after revocation or mismatch.

## Non-responsibilities

- Do not infer user intent, TaskFlow identity or capability authority from mechanism identity.
- Do not create sockets, decode Browser API requests or dispatch a browser engine.
- Do not substitute a caller-provided executable digest for an actual live executable measurement.

## Dependency and call direction

Transport supplies the kernel peer tuple. AgentPort daemon and BrowserActor consume attestation/custody. The crate depends on transport identity plus exact `libc`/`sha2` and must remain independent of codec, Servo, UI and release policy.

Relevant architecture:

- `docs/architecture/SYSTEMD_AGENT_PORT_CUSTODY.md`
- `docs/architecture/REQUEST_PEER_CUSTODY.md`
- `docs/architecture/AGENT_PORT_PATHNAME_CUSTODY.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- `ProcfsPeerAttestor`, `PeerRuntimePolicy`, `PeerRuntimeSnapshot`, `AttestedPeer`, `TrustedExecutableDigest`, `PeerRequestCustody`, `PeerRequestVerifier` and `AttestationError` are the main types.
- Qualification/development static digest paths are feature-gated; `default` contains neither.
- Account resolution and executable hashing are explicit fallible helpers.

This library registers no binary target. Cargo binary auto-discovery and package build scripts are disabled.

## Configuration and features

Cargo features are `qualification-static-attestation` and `development-static-attestation`; both are opt-in and must not become product defaults. Procfs root can be replaced only for controlled tests. Account, unit, cgroup and executable values belong in reviewed policy, not environment text.

Registered Cargo features: `default`, `qualification-static-attestation`, `development-static-attestation`

## State, concurrency, and failure semantics

An `AttestedPeer` owns a pidfd and last verified snapshot. A request custody object has one authoritative owner and derived verifiers; revocation is monotonic. Revalidation compares the exact process incarnation. Read, parse, hash, liveness or identity ambiguity is terminal for that request.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- Same numeric PID after reuse is not the same process; start time, pidfd and namespace identity are required.
- Uniform real/effective/saved/filesystem IDs are required.
- Cgroup and unit strings are bounded and canonical; traversal or multiple unified entries fail.
- Executable evidence is hashed from a trusted descriptor/path policy rather than untrusted prose.
- Raw PID/UID/GID/session values must not be emitted in product diagnostics.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `crates/hepta-peer-attestation/src/lib.rs`
- `tests/test_s04_transport_custody.py`
- `crates/hepta-peer-attestation/tests/control_owner_kernel.rs`
- `tests/test_control_owner_handoff.py`

Applicable workflows:

- `.github/workflows/s04-transport-custody.yml`
- `.github/workflows/agent-port-custody.yml`

Contract references:

- `contracts/agent-port-custody.v1.json`
- `contracts/request-peer-custody.v1.json`
- `contracts/control-owner-handoff.v1.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run the S04 hostile procfs/cgroup/namespace/path corpus after Linux identity changes.
- Unsupported kernels/platforms fail with a typed error; do not silently downgrade to UID-only admission.
- Account lookup or executable mismatch should be treated as deployment/configuration failure and the request refused.
- Keep procfs byte limits and no-follow rules intact when adding fields.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Kernel API, namespace mapping, cgroup/unit interpretation, account lookup, digest policy or feature changes require a platform compatibility matrix and installed-image tests. Existing attestation evidence becomes stale when any identity input changes.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.


## Live control-custodian successor

Linux `ControlOwnerPolicy`, `ControlOwnerError`, `AttestedHandoffSender` and
`AttestedHandoffReceiver` wrap the existing accepted-stream protocol. They own
already connected `OwnedFd` seqpacket controls and read the actual kernel peer.
An explicit trusted-owner policy supplies matching kernel/runtime UID/GID,
optional exact PID, exact cgroup/unit and a canonical approved executable pin.
The pin is compared to the fixed default `/proc` live image hash. No configurable
procfs source, injected attestor, static feature path, peer JSON, environment,
approval boolean or page/model output can supply the measured identity.
There is no default policy. Authenticating and provisioning that policy remains
an external installed-owner obligation; accepting a policy argument does not
prove that provisioning occurred.

| API | Ownership and result |
| --- | --- |
| `ControlOwnerPolicy::new(kernel, runtime, approved_executable_sha256)` | Validate explicit consistent policy, retain private immutable configuration |
| `AttestedHandoffSender::from_accepted(control, accepted, path, policy, budget)` | Consume original accepted stream and control; fix entry deadline and conservative `capture_before` before any control attestation; construct one-shot sender |
| `AttestedHandoffReceiver::from_control(control, policy, path, budget)` | Consume control under an independent fixed entry wait deadline; attest actual peer before challenge publication |
| `ensure_current(&mut self)` | Refresh original live pidfd-backed snapshot under same ceiling; failure retires this owner; successful result is the unchanged local deadline |
| Sender `send(&mut self)` | Take replay custody before first possible native send; refresh before/after; success means packet enqueue only; retire on every result |
| Receiver `receive(&mut self)` | Use remaining original control wait, refresh before/after, validate returned original deadline; postcheck failure drops received custody; retire on every result |
| `cancel(&mut self)` | One-way local retirement and original descriptor close; foreign creating PID refuses before mutation |

Both owners are non-cloneable, one-shot and fail-stop. Cancellation needs an
exclusive mutable borrow and cannot concurrently interrupt a running call.
Blocking control wait is bounded by the original wait deadline; synchronous
procfs hashing is not preemptively timed out. Late results refuse and close
owned resources. Any low-level Duration clock resample is bounded by the fixed
outer Instant checks; neither receiver control wait nor sender attestation
starts a fresh accepted-transaction deadline. The sender's native monotonic
wire ceiling and receiver's conservative Instant remain no later than the
sender entry ceiling. The old duration capture API remains unchanged.

No owner method calls `shutdown`, acquires a copied mutex or creates a listener.
Inherited calls fail before mutation; ordinary Rust destruction closes only the
child's descriptor copies. Success neither attests the original application
peer nor issues a principal: `AcceptedProductConnection::from_received` still
performs original-Agent live admission. These wrappers do not automatically
retain a control-owner verifier at a future engine action boundary. The native
owner must integrate that final live custody check separately.

Run `cargo test --locked -p hepta-peer-attestation --test control_owner_kernel`,
`cargo test --locked -p hepta-agent-transport --test accepted_handoff_kernel`
and `python3 -m unittest discover -s tests -p test_control_owner_handoff.py`.
The new single-thread host corpus uses actual independent same-UID processes,
seqpacket/SCM_RIGHTS, fixed default `/proc`, actual executable pins/exec drift,
pidfd death, original-peer traffic, deadline delay, cancellation, malformed
packets, actual fork and FD inventories. Its five-second positive fixture
budget does not change the twenty-second product ceiling. A real earlier
500-ms constructor overrun is retained as a failed diagnostic; it is not a
qualification success. Existing CI head/merge all-targets lanes execute the
registered kernel target, and the product listener guard still scans all
agent-portd Rust code and peer-attestation source while excluding documentation
and legitimate test-only listener creation. This finite source-token check
is not evidence of kernel isolation or absence of all possible socket paths.

Installed systemd control-FD provisioning, approved template-unit policy,
root-owned endpoint custody, the cross-UID live-attestation broker, trusted
principal policy, native Servo owner/final control check and installed fault
qualification remain missing. Main binaries, service units, default features,
activation marker and all product readiness claims remain unchanged and closed.
