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
retain a control-owner verifier at a future engine action boundary when using
the legacy `receive` result. The additive `receive_custodied` path below carries
that verifier to source runtime controls; the native owner still must integrate
and perform the actual final live custody check.

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


## Dual-owner request-custody source successor

The closed additive inventory is `contracts/dual-owner-request-custody.v1.json`.
Linux `AttestedHandoffReceiver::receive_custodied` returns a non-cloneable
`ControlReceivedAcceptedStream`. It duplicates the already held control pidfd
and original snapshot **before** retiring the one-shot control channel. The
private custody constructor accepts only that original fixed default `/proc`
live attestation. No static profile, caller boolean, injected attestor or new
numeric-PID lookup supplies control identity. Existing `receive` is unchanged.

`ControlRequestCustody` has one owner and cloneable `ControlRequestVerifier`
observations. `verifier`/`revoke`, `ensure_alive`/`verify_current`/`deadline`, and
`ensure_pair_alive`/`verify_pair_current` are the explicit methods; the pair
methods verify concrete original `PeerRequestVerifier` objects, never a caller
assertion. Creator-PID checks precede mutation; observed identity failure and
Drop/revoke/cancel cannot be reversed by restoring executable bytes or replacing
a process. Child Drop closes its own FD copies without shutdown or parent unlock.

The opaque received object's `deadline`, `control_verifier`, and consuming
`consume_before` callback carry the original stream, unchanged absolute Instant
and unique custody together. `AcceptedProductConnection::from_control_received`
uses the fixed default live Agent attestor and requires an explicit trusted
`PeerRuntimePolicy` plus canonical lowercase approved Agent executable SHA256.
The pin is compared with actual measured bytes. Runtime policy alone does not
pin that executable; neither an observed digest nor peer/page/model output may
auto-approve production configuration. Invalid pins consume and close custody.
There is no configured approved production policy in this source candidate.

Controlled connection admission, queue submit/dequeue, preflight and handler
recheck both original identities. `preflight_attested_controlled` and
`handle_attested_controlled` are additive on both actor and concrete Servo facade.
`RequestControl` carries the paired concrete verifiers into queued runtime work;
The native owner must call `ServoRuntimeCompletion::ensure_current_peer` for
both identities before and after its actual retained-node/action checks. Observed original-Agent
loss also retires the paired control scope. A possible dispatch followed by
custody loss remains indeterminate and retires the runtime; no replay is granted.

All these steps consume the original accepted absolute deadline and existing
20-second maximum. Receiver control-wait expiry is independent and cannot renew
accepted custody. Queues keep the existing eight-connection ceiling. Procfs/hash
calls are synchronous: late results refuse admission; no preemptive syscall or
all-asynchronous-window guarantee is made.

One-shot sender/receiver channel closure is expected and is **not** custodian
process exit. The same custodian must remain alive throughout the request.
A retained-control terminal-wait/cancel/ack protocol, installed owner startup,
root-owned pathname policy, cross-UID executable-attestation authority and native
final effect integration remain missing. Default binaries and systemd activation
remain closed. A source callback check does not execute Servo.

`apps/hepta-browserd/tests/product_control_custody_kernel.rs` exercises original
stream bytes, three distinct actual same-UID Linux PIDs, default `/proc` identity,
Drop/revoke/cancel, queue overflow, Agent and custodian death/exec before admission
and after queueing, immutable expiry, FD inventory and actual fork refusal while
parent FDs survive. Its positive fixture ceiling is 20 seconds, not a raised
product bound. A separate clearly labeled source-callback group uses synthetic
Agent procfs facts and actual control custody because the host need not expose a
systemd unit; it proves paired completion ordering, never default product
admission, installed service or Servo execution. `tests/test_dual_owner_custody.py`
checks closed source correspondence. Cargo all-targets CI runs the real kernel
target in both exact-head and prospective-merge lanes; source tests cannot stand
in for those kernel runs or higher-tier qualification.
