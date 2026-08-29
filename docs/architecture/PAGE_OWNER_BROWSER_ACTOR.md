# PageOwner and BrowserActor control core

`hepta-browser-actor` is the D3 engine-neutral ownership and dispatch boundary.
It does not create a listener or claim that product AgentPort activation is
ready. The default product daemon continues to fail closed until an integrated
browserd adapter is selected by an explicit development profile.

## Principal binding

A `TaskFlowPrincipal` is accepted only when PID/UID/GID, systemd unit, unified
cgroup-v2 path, and executable SHA-256 exactly match the attested mechanism
identity. The transport peer is checked again for every dispatch. Identity
mismatch is a policy failure before runtime work begins.

## One PageOwner

One actor owns at most one active `PageOwner` and one opaque WebView token. Each
bound request must carry the exact session ID and generation. Document,
semantic-snapshot, and mutation revisions are advanced through
`hepta-session-core`; stale element references fail closed rather than being
retargeted.

## Typed dispatch and local-fixture ceiling

The strict Browser API maps to `BrowserActorMessage`. The runtime adapter
receives the effective monotonic deadline and cancellation state. The included
qualification adapter accepts only ephemeral profiles and deterministic
loopback HTTP fixtures. External HTTPS, trusted-app execution, ambient device
access, and external-effect authority remain disabled pending D5/D6.

## Durable receipt ordering

`hepta-agent-port` exposes a lifecycle observer around one admitted operation:

1. `requested` is fsync-committed before dispatch;
2. `dispatched` is fsync-committed immediately before the handler;
3. a canonical response is constructed and hashed;
4. `completed` is committed before the response frame is written.

If work may have started and the path is interrupted, potential external
effects are recorded as `indeterminate`; recovery never automatically replays
them. Journal failure is fail closed. Transport evidence separately records
whether the response frame was committed.

## Claim ceiling

This package proves the host/source PageOwner model, strict operation mapping,
principal binding, cancellation/deadline propagation, local-fixture policy, and
receipt lifecycle. It does not by itself prove a live Servo BrowserActor inside
the D2I image, production activation, controlled external egress, signed apps,
updates, hardware qualification, or release readiness.
