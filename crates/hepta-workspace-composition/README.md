# `hepta-workspace-composition` technical development contract

This crate models the visible v1 workspace independently of a browser engine or compositor. It enforces exactly one logical content surface, separate trusted chrome, bounded geometry, explicit pointer/keyboard/IME ownership, popup refusal and crash/reconstruction transitions.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `candidate_engine_neutral_trusted_workspace_model`  
Claim ceiling: `deterministic model of one native trusted chrome surface plus one untrusted content surface, input ownership and crash recovery only; no native window, Servo instance, rendered product frame, AgentPort, external effect, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Validate non-zero workspace geometry and derive trusted/content rectangles.
- Track the one content-surface lifecycle and presentable frame generation.
- Route input ownership explicitly and terminate content IME on crash/focus withdrawal.
- Refuse popup/new-window/second-content-surface requests.
- Produce deterministic snapshots/effects for adapter conformance tests.

## Non-responsibilities

- Do not create a native window, draw pixels, start Servo or claim a real event loop.
- Do not share DOM/storage authority between trusted chrome and content.
- Do not authorize external navigation, capabilities or Agent actions.

## Dependency and call direction

The model depends only on contract-core primitives. A headed runtime/compositor adapter must translate real callbacks into `WorkspaceEvent` and render only from authoritative snapshots. Product code must not bypass this model with a second hidden content view.

Relevant architecture:

- `docs/architecture/TRUSTED_WORKSPACE_COMPOSITION.md`
- `docs/architecture/SERVO_EMBEDDER_COMPATIBILITY.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- `WorkspaceConfig`, `WorkspaceState`, `WorkspaceEvent`, `WorkspaceEffect`, `WorkspaceSnapshot`, `CompositionFrame`, `Rect`, `PixelSize`, `ContentSurfaceId`, `InputOwner` and `CompositionError` form the public surface.
- `apply` performs deterministic state transitions; `composition_frame` returns the trusted/content presentation contract.

This library registers no binary target. Cargo binary auto-discovery and package build scripts are disabled.

## Configuration and features

There are no features or OS environment inputs. Geometry is supplied explicitly. `TRUSTED_CHROME_ORIGIN` is a model identity only; actual origin interception and bundle verification are later gates.

Registered Cargo features: none.

## State, concurrency, and failure semantics

One state value owns content lifecycle, generation, frame publication and input owners. Crash removes the old presentable frame, returns keyboard ownership to trusted chrome, clears IME and requires a fresh non-zero generation before content becomes live again. Invalid events leave state unchanged.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- At most one live logical content surface exists.
- External content cannot replace or overlap as trusted chrome authority.
- Stale pixels and input owners are withdrawn on crash/replacement.
- Popup/new-window requests are explicit denials, not ignored side effects.
- Source tests are model evidence only; real pixels/input need headed and installed-image gates.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `crates/hepta-workspace-composition/src/tests.rs`
- `experiments/servo-headed-runtime/src/main.rs`

Applicable workflows:

- `.github/workflows/servo-headed-runtime.yml`
- `.github/workflows/ci.yml`

Contract references:

- `contracts/workspace-composition.v1.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run model/state tests for every event sequence and rollback path.
- When an adapter diverges from the model, stop routing input and present trusted recovery UI.
- Do not manually preserve an old content frame after generation change.
- No service, persistence or migration is owned here.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Event/effect vocabulary, topology cardinality, geometry or generation semantics are security contracts. Adapter and model corpora must change atomically, and a wider multi-window design requires a new ADR and authority model.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.
