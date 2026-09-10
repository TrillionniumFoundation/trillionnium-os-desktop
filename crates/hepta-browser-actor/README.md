# `hepta-browser-actor` technical development contract

This crate is the narrow product authority wrapper around the internal simulation implementation. It requires a live opaque `AttestedPeer` at construction and at every request, owns the only admitted deterministic runtime for S06, and intentionally exposes no generic runtime parameter or ordinary AgentPort handler implementation.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `candidate_sealed_product_browser_actor`  
Claim ceiling: `sealed product-facing BrowserActor with attested principal binding, request custody, deterministic local runtime and receipt observation only; no caller-injected runtime, product listener, real Servo adapter, external effect, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Bind a TaskFlow principal to refreshed pidfd-backed mechanism evidence.
- Construct the S06 deterministic local runtime internally so callers cannot substitute an authority-widening adapter.
- Dispatch one attested request with request-scoped custody.
- Expose bounded principal, PageOwner, cancellation and receipt-observer views.
- Keep mechanism identity and generic simulation internals private from product callers.
- Expose no raw mechanism identity, runtime injection token, file descriptor, engine pointer or mutable session internals.

## Non-responsibilities

- Do not implement the weaker ordinary `BrowserRequestHandler` trait.
- Do not accept a caller-supplied `PageRuntime`, engine bridge or forged principal binding.
- Do not start Servo, a listener, network access, persistent credentials or external effects.
- Do not treat receipt observation as authorization.

## Dependency and call direction

The product wrapper consumes AgentPort context, transport peer identity, peer attestation, codec types, session receipts and the internal simulation crate. Application code should depend on this crate, not construct the simulation actor directly. S08 must add a distinct concrete Servo product type rather than generic injection into this wrapper.

Relevant architecture:

- `docs/architecture/BROWSER_ACTOR_AUTHORITY_BOUNDARY.md`
- `docs/architecture/ENGINE_THREAD_DISPATCH.md`
- `docs/architecture/EVENT_LOOP_COMPLETION.md`
- `docs/architecture/SESSION_INCARNATION.md`
- `docs/architecture/RECEIPT_ADMISSION_IDENTITY.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- `BrowserActor::from_attested` and `handle_attested` are the primary authority path.
- `principal`, `page_owner`, cancellation accessors and `receipt_observer` expose bounded views.
- Selected codec/attestation/receipt types are re-exported for product integration; principal/mechanism binding constructors are not.
- Compile-fail documentation guards generic runtime injection and ordinary-handler use.

This library registers no binary target. Cargo binary auto-discovery and package build scripts are disabled.

## Configuration and features

There are no features or runtime configuration. The runtime is always deterministic/local on this gate. Product activation remains controlled by higher-level profile and systemd custody.

Registered Cargo features: none.

## State, concurrency, and failure semantics

The actor-owned state contains one principal binding, one runtime, optional PageOwner/session incarnation, cancellation tokens and receipt observers. Request peer custody is revalidated before dispatch and final completion. Runtime uncertainty produces typed interruption/indeterminate outcomes and no automatic replay.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- Opaque attestation, not caller-provided IDs, is required.
- Caller-supplied runtime injection is not representable in the product API.
- Session/WebView/incarnation and layered revisions prevent stale identity reuse.
- Cancellation/deadline/peer revocation are checked at engine/effect boundaries.
- Product-facing error text must be redacted while typed internal classification remains available.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `crates/hepta-browser-actor/src/lib.rs`
- `tests/test_s06_browser_actor.py`

Applicable workflows:

- `.github/workflows/s06-browser-actor.yml`

Contract references:

- `contracts/browser-actor.v1.json`
- `contracts/engine-thread-dispatch.v1.json`
- `contracts/event-loop-completion.v1.json`
- `contracts/session-incarnation.v1.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run compile-fail doctests, S06 hostile tests, all-feature checks and receipt tests after API changes.
- A peer refresh/binding failure is a request refusal; do not fall back to an unattested handler.
- The deterministic runtime is a development mechanism and cannot be deployed as the real browser.
- No installed service or data migration is owned here.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Exposing a new constructor, runtime type, handler implementation or mechanism field changes the authority surface and requires independent security review. S08 concrete Servo integration must preserve the no-generic-injection property and exact request/receipt ordering.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.
