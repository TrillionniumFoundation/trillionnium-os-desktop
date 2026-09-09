# `hepta-agent-port` technical development contract

AgentPort composes authenticated transport and the canonical codec. It accepts one already-connected stream, decodes one request, calculates one effective deadline, invokes one typed handler at most once, binds the response to the validated request and commits at most one response frame.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `candidate_exactly_one_agentport_lifecycle`  
Claim ceiling: `one authenticated connected-stream request lifecycle with bounded handler output and lifecycle observation only; no listener, semantic principal, concrete BrowserActor/Servo dispatch, external-effect authorization, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Sample wall and monotonic time once and derive the earlier server/request deadline.
- Build an immutable `DispatchContext` containing peer, sequence, digest, effect class and deadline.
- Invoke one `BrowserRequestHandler` and prevent the handler from authoring wire identity fields.
- Validate bounded handler JSON and expose lifecycle-observer hooks for requested/dispatched/terminal facts.
- Discard late results and classify uncertain outcomes without automatic replay.

## Non-responsibilities

- Do not bind/listen, map peer credentials to a semantic principal, grant capabilities or call Servo directly.
- Do not retry a handler after timeout, disconnect or indeterminate potential effect.
- Do not let fixture success imply a browser runtime or product readiness.

## Dependency and call direction

The crate consumes transport, codec and browser contract types. Daemon/profile code supplies the connected stream and a handler. BrowserActor is a higher-level handler boundary and receipts are supplied through observers; AgentPort itself owns neither product session state nor durable storage.

Relevant architecture:

- `docs/architecture/CONNECTED_AGENT_PORT_BRIDGE.md`
- `docs/architecture/RECEIPT_ADMISSION_IDENTITY.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- `serve_one` and `serve_one_with_observer` execute the bounded lifecycle.
- `DispatchContext`, `HandlerOutcome`, `BrowserRequestHandler`, `OperationLifecycleObserver`, `ServiceEvidence` and `AgentPortError` describe the mechanism.
- `D0FixtureHandler` is a development fixture that permits health only and denies potential effects.
- Handler result limits cap members, depth, aggregate items, key bytes and string bytes.

This library registers no binary target. Cargo binary auto-discovery and package build scripts are disabled.

## Configuration and features

There are no features or listeners. The caller supplies an already-connected `UnixStream`, peer policy and server ceiling. Product profiles must supply an explicit, separately reviewed handler; the default product daemon currently fails before decode.

Registered Cargo features: none.

## State, concurrency, and failure semantics

A call owns one transport connection, one request, at most one handler invocation and at most one response commit. Observer transitions are ordered and bounded. Cancellation/deadline state is checked before and after handler work, but a synchronous handler cannot be forcibly preempted; a late result is discarded and must not be retried.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- Handler output cannot override request/session/transport identity.
- Lifecycle observation records facts but grants no execution authority.
- Potential effects are never automatically retried after uncertain dispatch.
- All response values are revalidated against strict canonical resource bounds.
- The D0 fixture must remain physically and graph-separated from production activation.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `crates/hepta-agent-port/src/lib.rs`
- `tests/test_s04_transport_custody.py`

Applicable workflows:

- `.github/workflows/s04-transport-custody.yml`
- `.github/workflows/ci.yml`

Contract references:

- `contracts/agent-port-bridge.v1.json`
- `contracts/receipt.v1.schema.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Use local socket pairs only for tests; production path ownership belongs to systemd custody.
- Inspect the first typed AgentPort error and discard the connection after any wire uncertainty.
- Run the D0C-04 source audit and complete workspace tests after changing context, observer or result limits.
- Do not diagnose timeouts by disabling deadline checks.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Changes to lifecycle ordering, context fields, handler/observer APIs, result limits or error mapping require contract, source audit, hostile tests and exact-head/prospective-merge evidence. Response identity rules are protocol invariants and cannot be weakened in place.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.
