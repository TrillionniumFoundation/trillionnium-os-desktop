# `hepta-browserd` technical development contract

The desktop browser daemon package is the product composition point for the bounded contracts, transport, AgentPort, session state and receipt foundations. On this source line its executable remains a deliberately non-listening scaffold: it reports build identity and runs deterministic self-checks, but it does not create a Servo instance or claim that the desktop product is operational.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `integrated_d0_scaffold_with_candidate_actor_contracts`  
Claim ceiling: `deterministic D0 self-check and source composition only; no product Servo runtime, enabled AgentPort, external effect, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Publish the active plan revision and integrated implementation-stage constants used by repository truth checks.
- Compose transport, canonical codec, AgentPort and session-state self-checks without widening their authority.
- Expose one stable command-line surface for build information, deterministic verification and future supervised product startup.
- Remain the eventual owner of one PageOwner and one product browser runtime after the S08 gate is separately reviewed.

## Non-responsibilities

- Do not bind or accept the AgentPort socket; systemd and the connection service own that lifecycle.
- Do not invent a BrowserActor, Servo frame, user consent, capability or external-effect result from a self-check.
- Do not own PID 1, update/signing keys, raw devices, arbitrary filesystem authority or release promotion.

## Dependency and call direction

`hepta-browserd` is an application-layer consumer of `hepta-agent-transport`, `hepta-browser-codec`, `hepta-agent-port`, `hepta-browser-contracts`, `hepta-session-core`, and `trillionnium-contract-core`. Those lower layers must never depend back on this application. The current self-check calls into each mechanism in dependency order and then exercises the engine-neutral session state machine. The future Servo adapter must remain a distinct concrete, reviewed path rather than a generic caller-injected runtime.

Relevant architecture:

- `docs/architecture/RUNTIME_TOPOLOGY_AND_FAILURE_MODEL.md`
- `docs/architecture/BROWSER_ACTOR_AUTHORITY_BOUNDARY.md`
- `docs/architecture/SESSION_STATE_MACHINE.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- `ACTIVE_PLAN_REVISION` and `IMPLEMENTATION_STAGE` are immutable build-truth sentinels.
- `run_self_check()` returns a bounded `SelfCheckReport`; it is development evidence, not readiness.
- Binary `hepta-browserd` supports `--self-check`, `--print-build-info`, and `--help`. Unknown arguments fail with exit status 2.

Registered binaries:

- `hepta-browserd` at `src/main.rs`; required features: `none`.

## Configuration and features

There are currently no Cargo features or runtime configuration files. The package intentionally starts no listener, window, network stack or credential profile. S08 may add an explicit non-default host-integration profile, but production activation must remain fail closed and must not be inferred from source presence.

Registered Cargo features: none.

## State, concurrency, and failure semantics

All current state is local to the self-check call. Session transitions use `SessionMachine`; navigation, human focus, IME, crash and recovery advance typed revisions. No background worker, global mutable runtime, persisted profile or retry loop exists. A future runtime supervisor must bound restart attempts, withdraw stale pixels and input ownership, and enter a visible degraded state rather than restart indefinitely.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- Self-check success cannot be translated into a product or release claim.
- Trusted chrome and untrusted content must never share a DOM authority realm.
- Only one logical PageOwner/content surface may be authoritative in v1.
- External navigation, credentials, capabilities and effects stay closed until their independent gates pass.
- Diagnostic output must contain no raw peer identity, credentials, page content or secret receipt detail.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `apps/hepta-browserd/src/lib.rs`
- `tests/test_s06_browser_actor.py`

Applicable workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/s06-browser-actor.yml`

Contract references:

- `contracts/browser-api.v1.schema.json`
- `contracts/browser-actor.v1.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run `cargo run --locked -p hepta-browserd -- --self-check` after repository validation.
- Use `--print-build-info` to compare the binary with machine truth; a mismatch is a build/repository defect.
- A self-check failure should be investigated at the first named lower-layer error. Do not suppress it or widen the claim ceiling.
- There is no supported service installation or user-data migration on this source line.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Changing the plan/stage constants, dependency graph, command line, self-check sequence or future startup profile requires synchronized updates to machine truth, tests, this document and the module registry. Any runtime adapter or activation change is a new trust boundary and must receive exact-head, prospective-merge and independent review evidence.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.
