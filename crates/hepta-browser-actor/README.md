# hepta-browser-actor

**Module registry ID:** `hepta-browser-actor`  
**Workspace path:** `crates/hepta-browser-actor`  
**Owner class:** browser-runtime-security

This is the product-facing authority wrapper for one PageOwner/BrowserActor. It intentionally contains very little mechanism code: its purpose is to make the safe entry path the only public entry path.

## Authority inputs

Construction requires all of the following:

- a semantic `TaskFlowPrincipal`;
- the kernel-derived `PeerIdentity` tuple;
- an opaque `AttestedPeer` retaining the admitted process by pidfd;
- the same `ProcfsPeerAttestor`/trusted-path source used for bounded refresh;
- a `PageRuntime` implementation.

`from_attested` refreshes start time, cgroup v2 path, systemd unit, and executable digest before the private principal/mechanism binding is created. A caller-written `MechanismIdentity` is not accepted or exported.

## Request path

Every product request must call `handle_attested`. That method delegates to the retained implementation only after the live attestation is refreshed. The implementation then:

1. checks the original absolute deadline;
2. verifies exact peer and process-start continuity;
3. creates one non-cloneable request custody owner;
4. propagates its verifier through engine queue/callback controls;
5. rechecks custody before and after runtime work;
6. refuses stale work or reports an uncertain effect as indeterminate;
7. drops custody when the request returns or unwinds.

The wrapper does **not** implement `BrowserRequestHandler`, has no ordinary `handle` method, and does not export `PrincipalBinding` or `MechanismIdentity`.

## State and cancellation

The wrapper exposes bounded state inspection, cancellation-token bridging, session-state transitions, and durable receipt observation. These operations do not grant dispatch authority. Receipt entries record lifecycle facts and never authorize or automatically replay an external effect.

## Implementation isolation

The complete state machine, callback bridge, deterministic runtime, and hostile tests live in `hepta-browser-actor-simulation`. Rust consumers cannot name transitive crates unless they add a direct dependency; repository validation rejects any direct dependent other than this wrapper. The simulation package is unpublished and is not an application or installable binary.

## Failure semantics

- missing, stale, reused, or revoked peer identity: fail closed before runtime, or indeterminate after a possible effect;
- attestation refresh failure: policy-denied response;
- deadline/cancellation: no late success release;
- callback loss or runtime panic: retire the runtime pair;
- session-incarnation entropy failure: latch failure and reconstruct the actor;
- receipt storage uncertainty: recovery required, never automatic replay.

## Claim ceiling

This module can establish a source/test product API in which authenticated custody is structurally mandatory. It does not establish a listener, product activation, Servo adapter, installed image, physical hardware, HSM signing, publication, or release readiness.
