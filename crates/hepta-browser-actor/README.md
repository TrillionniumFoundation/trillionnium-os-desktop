# `hepta-browser-actor` technical development contract

This crate is the narrow product authority wrapper around the internal simulation implementation. It requires a live opaque `AttestedPeer` at construction and at every request, owns the only admitted deterministic runtime for S06, and intentionally exposes no generic runtime parameter or ordinary AgentPort handler implementation.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `candidate_exact_pin_real_servo_host_vertical_slice`  
Claim ceiling: `concrete non-generic ServoBrowserActor bridge plus exact-pin real-Servo host qualification candidate with attested AgentPort, request custody, durable receipts and stale-reference refusal; qualification-only mailbox; no production listener, external-effect authority, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Bind a TaskFlow principal to refreshed pidfd-backed mechanism evidence.
- Construct the S06 deterministic local runtime internally so callers cannot substitute an authority-widening adapter.
- Dispatch one attested request with request-scoped custody.
- Expose bounded principal, PageOwner, cancellation and receipt-observer views.
- Keep mechanism identity and generic simulation internals private from product callers.
- Expose no raw mechanism identity, runtime injection token, file descriptor, engine pointer or mutable session internals.
- Provide the concrete, non-generic `ServoBrowserActor` / `ServoRuntimeOwner` bridge used by S08.
- Carry exactly one typed command from the actor worker to the creator-thread Servo owner and return exactly one completion.
- Recheck deadline, cancellation and pidfd-backed request custody immediately before the real Servo adapter acts.

## Non-responsibilities

- Do not implement the weaker ordinary `BrowserRequestHandler` trait.
- Do not accept a caller-supplied `PageRuntime`, engine bridge or forged principal binding.
- Do not start Servo from the library itself, bind a listener, grant persistent credentials or authorize external effects.
- Do not make the qualification-only atomic mailbox part of the public API or install graph.
- Do not infer systemd, Wayland, Debian/QEMU, hardware, signing or release closure from the exact-pin host test.
- Do not treat receipt observation as authorization.

## Dependency and call direction

The product wrapper consumes AgentPort context, transport peer identity, peer attestation, codec types, session receipts and the internal simulation crate. Application code should depend on this crate, not construct the simulation actor directly. S08 must add a distinct concrete Servo product type rather than generic injection into this wrapper.

Relevant architecture:

- `docs/architecture/BROWSER_ACTOR_AUTHORITY_BOUNDARY.md`
- `docs/architecture/ENGINE_THREAD_DISPATCH.md`
- `docs/architecture/EVENT_LOOP_COMPLETION.md`
- `docs/architecture/SESSION_INCARNATION.md`
- `docs/architecture/RECEIPT_ADMISSION_IDENTITY.md`
- `docs/architecture/S08_SERVO_BROWSER_ACTOR_VERTICAL_SLICE.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- `BrowserActor::from_attested` and `handle_attested` remain the deterministic S06 authority path.
- `ServoBrowserActor::from_attested` admits only the concrete S08 callback bridge; callers cannot supply a generic runtime.
- `ServoBrowserActor::preflight_attested` checks current custody, session/reference binding, arbitration, cancellation and supported operation without dispatching engine work or writing receipts. Refusal retires request cancellation registration; `handle_attested` still rechecks final custody/control after durable intent.
- `servo_runtime_pair` returns one actor endpoint and one creator-thread `ServoRuntimeOwner`.
- `ServoRuntimeCommand` and `ServoRuntimeCompletion` expose bounded operation data and single-use completion without exposing Servo objects.
- `principal`, `page_owner`, cancellation accessors and `receipt_observer` expose bounded views.
- `ReceiptLifecycleObserver` exposes complete-chain deduplication and sealed receipt lookup, and `into_journal` consumes only an idle observer with no nonterminal durable history for explicit actor rebinding.
- Selected codec/attestation/receipt types are re-exported for product integration; principal/mechanism binding constructors are not.
- Compile-fail documentation guards generic runtime injection and ordinary-handler use.

This library registers no binary target. Cargo binary auto-discovery and package build scripts are disabled.

## Configuration and features

There are no Cargo features. The deterministic wrapper remains local-only, while S08 adds a concrete bridge whose real-Servo behavior is enabled only by the permanent qualification workflow. `HEPTA_S08_MAILBOX` is accepted solely by the integration test and must name an absolute private test directory; it is not runtime product configuration. Product activation remains controlled by higher-level profile and systemd custody.

Registered Cargo features: none.

## State, concurrency, and failure semantics

The actor-owned state contains one principal binding, one runtime, optional PageOwner/session incarnation, cancellation tokens and receipt observers. Request peer custody is revalidated before dispatch and final completion. The S08 owner is creator-thread-affine, permits only one pending command and retires on overlap or ambiguity. Runtime uncertainty produces typed interruption/indeterminate outcomes and no automatic replay.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- Opaque attestation, not caller-provided IDs, is required.
- Caller-supplied runtime injection is not representable in the product API.
- Session/WebView/incarnation and layered revisions prevent stale identity reuse.
- Cancellation/deadline/peer revocation are checked at engine/effect boundaries.
- Product-facing error text must be redacted while typed internal classification remains available.
- Real semantic clicks are executed only from a retained, current Servo accessibility node after a final custody check.
- A navigation advances document identity so a pre-navigation element reference is refused before another Servo action command.
- The test mailbox and synthetic procfs fixture never enter product binaries or Debian install maps.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `crates/hepta-browser-actor/src/lib.rs`
- `tests/test_s06_browser_actor.py`
- `crates/hepta-browser-actor/tests/s08_servo_mailbox.rs`
- `tests/test_s08_servo_runtime.py`
- `experiments/servo-s08-runtime/accessibility_server.rs`

Applicable workflows:

- `.github/workflows/s06-browser-actor.yml`
- `.github/workflows/s08-servo-vertical-slice.yml`

Contract references:

- `contracts/browser-actor.v1.json`
- `contracts/engine-thread-dispatch.v1.json`
- `contracts/event-loop-completion.v1.json`
- `contracts/session-incarnation.v1.json`
- `contracts/s08-servo-runtime-bridge.v1.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run compile-fail doctests, S06 hostile tests, S08 source validation, all-feature checks and receipt tests after API changes.
- The exact-pin S08 workflow must run both the real Servo test process and the product integration test against one private mailbox; a skipped environment-gated test is not evidence.
- A peer refresh/binding failure is a request refusal; do not fall back to an unattested handler.
- The deterministic runtime is a development mechanism and cannot be deployed as the real browser.
- No installed service or data migration is owned here.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Exposing a new constructor, runtime type, handler implementation or mechanism field changes the authority surface and requires independent security review. S08 concrete Servo integration preserves the no-generic-injection property, creator-thread engine ownership, exact request/receipt ordering and retained-node action boundary. Any mailbox, Servo pin, patch, operation, claim or install-graph change invalidates the S08 evidence.

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
