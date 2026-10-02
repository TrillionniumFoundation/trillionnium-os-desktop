# `hepta-browser-actor-simulation` technical development contract

This unpublished crate contains the generic mechanisms used to verify BrowserActor state, request custody, callback completion and engine-thread ownership without making those generics part of the product API. It is implementation-internal and not a product entry point. It supports deterministic and test adapters and must never be installed or treated as a product authority surface.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `internal_unpublished_browser_actor_simulation_and_dispatch_core`  
Claim ceiling: `unpublished generic actor, deterministic fixture runtime, engine-thread/callback bridges and hostile test support only; no product runtime selection, listener, real Servo integration, external effect, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Implement principal/mechanism binding checks and the generic `BrowserActor<R>` state machine.
- Provide the deterministic local runtime and exhaustive hostile tests.
- Provide bounded synchronous engine-thread and nonblocking callback completion bridges.
- Bind cancellation, deadline and peer custody through queued and callback work.
- Model receipt admission, dispatch, terminal/indeterminate facts and session incarnation.

## Non-responsibilities

- Do not be linked as a production daemon API or accept network/listener authority.
- Do not claim that a generic `PageRuntime` implementation is a reviewed product engine.
- Do not expose a coordinate/JavaScript/text-search fallback for semantic actions.
- Do not retry uncertain effects or deliver late buffered success after identity revocation.

## Dependency and call direction

The sealed product `hepta-browser-actor` wraps this crate with one internally selected runtime. Tests and future concrete adapter crates may consume engine-dispatch mechanisms, but product applications must not accept arbitrary generic implementations. Dependencies point toward AgentPort, codec, peer attestation, session core and contract core only.

Relevant architecture:

- `docs/architecture/BROWSER_ACTOR_AUTHORITY_BOUNDARY.md`
- `docs/architecture/ENGINE_THREAD_DISPATCH.md`
- `docs/architecture/EVENT_LOOP_COMPLETION.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- Generic verification types include `BrowserActor<R>`, `PageRuntime`, `BrowserActorMessage`, `RequestControl`, `RuntimeReply` and `RuntimeFailure`.
- Engine bridges include `EngineThreadRuntime`, `EngineThreadOwner`, `CallbackPageRuntime`, `CallbackEngineOwner`, `EngineCompletion` and pump results.
- `DeterministicLocalRuntime`, principal/binding helpers, incarnation and receipt observer support tests.
- `preflight_attested` supplies side-effect-free semantic admission before receipts; it retires cancellation registration on refusal. Concrete execution repeats custody/control validation after durable intent. Unknown completion of any operation that may change local or external state is recorded as indeterminate.
- Simulation doctests validate its examples and thread/ownership constraints; product authority compile-fail guarantees also live in the sealed wrapper.

This library registers no binary target. Cargo binary auto-discovery and package build scripts are disabled.

## Configuration and features

There are no Cargo features. Queue capacity and cancellation polling are fixed bounded constants. Runtime implementations are injected only in tests/internal composition; this is precisely why the crate is unpublished and separated from the product facade.

Registered Cargo features: none.

## State, concurrency, and failure semantics

The generic actor owns one PageOwner and one active request namespace. Engine endpoints allow one pending slot and one active call. Callback completions are single-use, retain the original control, and retire the pair on uncertain failure, dropped receiver, wrong thread or peer revocation. Owner objects are neither `Send` nor `Sync`.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- Queueing is never reported as execution or durable success.
- Callbacks must recheck current peer and live retained node immediately before action.
- No separate resolve-then-act path may create a TOCTOU window.
- Dropped, duplicated, late or panicking callbacks retire the runtime and cannot duplicate dispatch.
- Product code must use the sealed wrapper or a separately reviewed concrete adapter.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop_tests.rs`
- `tests/test_s06_browser_actor.py`

Applicable workflows:

- `.github/workflows/s06-browser-actor.yml`

Contract references:

- `contracts/browser-actor.v1.json`
- `contracts/engine-thread-dispatch.v1.json`
- `contracts/event-loop-completion.v1.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run S06 actor tests and all engine-dispatch/event-loop corpora.
- Use the deterministic runtime only for fixtures; never package it as product BrowserActor.
- A retired bridge is permanently unusable and must be reconstructed with a fresh session incarnation.
- Debug logs must not include mechanism/session secrets.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Generic mechanisms may evolve only with corresponding product compile-fail guards and hostile tests. Any relaxation of thread affinity, queue cardinality, completion single-use, atomic PageAct or request custody requires a new security review and evidence packet.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.


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


`retire_prepared_request(&mut self, &str) -> Result<(), AgentPortError>` is
additive on the actor and concrete facade. It checks the actor creator PID
before mutation, cancels an existing shared token and removes only that request's
registration and cancellation marker. It creates no token, receipt, authority,
new deadline or replay grant. Controlled preflight refusals/errors and every
controlled handler return retire preparation, including successful preflight
followed by custodian revocation or expiry. The product handler also retires on
its own early cancellation, identity, replay and storage refusals. A retained
token clone is cancelled even when the original legacy handler already removed
the registration. Successful preflight keeps preparation for actual dispatch.
The private product handler also owns preparation until Drop, so lifecycle or
deadline errors that skip handle after preflight retire the same request. The
added four source-callback cuts (including actual fork refusal before token
mutation with unchanged parent FDs), ten product-refusal cases and actual observer
failure followed by handler Drop prove this
source lifecycle with actual control custody or explicitly synthetic Agent
metadata as labeled; they do not execute Servo or qualify installed effects.

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
