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
- The crate sets `doctest = false`; product compile-fail guarantees live in the sealed wrapper.

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
