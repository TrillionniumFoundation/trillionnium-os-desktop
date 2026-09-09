# hepta-browser-actor

**Module registry ID:** `hepta-browser-actor`
**Workspace path:** `crates/hepta-browser-actor`
**Owner class:** browser-runtime-security

This crate is the narrow product-facing authority wrapper for one PageOwner and
BrowserActor. It makes the attested entry path the only public request path.

## Authority inputs

Construction requires a semantic `TaskFlowPrincipal`, the kernel-derived
`PeerIdentity`, an opaque pidfd-backed `AttestedPeer`, and the same
`ProcfsPeerAttestor` source used for refresh. A caller-written
`MechanismIdentity`, `PrincipalBinding`, runtime trait, or runtime value is not
accepted or exported.

## Actor-owned runtime boundary

S06 exposes a non-generic `BrowserActor`. `from_attested` constructs the bounded
deterministic local runtime internally. Callers cannot provide a `PageRuntime`
implementation that skips `RequestControl`, hides deferred work, or reports a
terminal success while retaining effect authority. This runtime has no external
HTTPS, trusted-app, listener, installation, or production-effect authority.

A later Servo product adapter must be a distinct concrete reviewed type with its
own exact-pin, custody, callback, crash, and image evidence. It must not reopen a
generic public runtime injection point.

## Request path

Every product request calls `handle_attested`. The implementation checks the
original deadline, verifies peer/start-time continuity, creates one
request-scoped custody owner, propagates its verifier through internal queue and
callback controls, rechecks custody before terminal classification, and drops
custody on return or unwind. Stale custody fails before work or becomes
indeterminate after a possible effect.

The wrapper does not implement `BrowserRequestHandler`, has no ordinary `handle`
method, and does not export the internal mechanism identity or simulation
runtime traits.

## Failure and receipt semantics

Deadline, cancellation, callback loss, panic, browser crash, peer drift, and
receipt failure are fail-closed. Potential external effects are never
automatically replayed. Receipt entries are lifecycle facts, not execution
authority.

## Claim ceiling

This module establishes only a source/test product API with structurally
mandatory attested custody and an actor-owned local fixture runtime. It does not
establish a listener, product activation, Servo adapter, installed image,
physical hardware, signing, publication, or release readiness.
