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

The strict Browser API maps to typed `BrowserActor` runtime calls. Ordinary
operations use `BrowserActorMessage`; `page_act` uses the dedicated semantic
resolution hook described below. The runtime adapter
receives the effective monotonic deadline and cancellation state. The included
qualification adapter accepts only ephemeral profiles and deterministic
loopback HTTP fixtures. External HTTPS, trusted-app execution, ambient device
access, and external-effect authority remain disabled pending D5/D6.

### Semantic PageAct resolution boundary

`page_act` is not safe to implement by forwarding the generic `Act` message:
the element reference's frame and structural fingerprint are claims supplied
by the caller, not a re-resolution result. `PageRuntime::dispatch_page_act` is
therefore the only admission hook for an action. A real engine adapter must
resolve the target in the current frame, reject ambiguity or material
structure/role/name drift, retain the resolved node, and apply the action as
one bounded operation. The hook's default implementation returns
`unsupported`, so a runtime without a DOM/accessibility resolver cannot
silently act on an unverified target. `DeterministicLocalRuntime` intentionally
has no DOM model and consequently does not claim `page_act` execution. The
Servo adapter and its resolver corpus remain a prerequisite for promoting D3
semantic-action dispatch.

Every Agent observation, including `page_wait`, acquires the session's
`AgentObserving` control before runtime dispatch and releases it on success,
cancellation, deadline, or runtime failure. Agent navigation likewise requires
`Ready` plus `Idle` control before entering `NavigationPending`; it owns the
explicit `AgentNavigating` control state until commit/failure, so a human lease
or another Agent operation cannot be admitted in the pending interval.
Human/system navigation remains an adapter-owned transition for D4. Control or
phase conflicts are returned before runtime dispatch. `session_close` is
terminal cleanup and intentionally remains available in any live phase so it
can clear the PageOwner and lease safely. If the runtime cannot acknowledge a
close because it crashed, was cancelled, or exceeded its deadline, the actor
still applies the local terminal transition and releases the owner; the wire
response preserves the original runtime failure rather than claiming that the
browser close succeeded.

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

The D3 development adapter currently opens a single active journal segment. If
the core journal has been rotated, reopening a successor segment without its
ordered predecessors would lose the global receipt-progress map and could
admit a replayed receipt identifier. `hepta-agent-port-developmentd` therefore
rejects any segment whose header number is greater than one with a fail-closed
error. Rotation remains available to the core journal, but a future
development-service implementation must call the complete-chain
inspection/import API before serving requests from a rotated store.

## Explicit development activation

The source-level activation is an opt-in binary,
`hepta-agent-port-developmentd`, compiled only with the Cargo `development`
feature.  Its systemd socket uses the separate
`/run/hepta/browserd/agent-development.sock` path and is conditioned on the
administrator-created `/etc/hepta/enable-agent-port-development` marker plus
the explicit `--profile development` argument.  The profile also requires an
exact `HEPTA_D3_EXPECTED_EXECUTABLE_SHA256` configuration value; the binary
attests the connected peer before constructing `PrincipalBinding::bind_attested`.

The development service receives an already-connected socket from systemd and
executes one request through `BrowserActor<DeterministicLocalRuntime>` and
`serve_one_with_observer`.  It is not included in the production Debian install
map, and the production `hepta-agent-portd` remains default-disabled and
fail-closed.  The development runtime accepts only ephemeral loopback fixtures;
it does not create a listener or grant external-effect authority.

Live activation of this development profile is explicitly blocked upstream by
the service identity split: systemd runs the connection service as
`hepta-browserd`, while the expected attested peer is `hepta-agent`.  Linux
`PTRACE_MODE_READ_FSCREDS` consequently denies the cross-UID
`/proc/<pid>/exe` refresh used by strict peer attestation; the unit intentionally
grants no `CAP_SYS_PTRACE`, and its `hepta-agent` supplementary group does not
change that rule.  The contract records this as
`BLOCKED_UPSTREAM_CROSS_UID_PROCFS`, with `development_source_wiring_only` true
and `development_static_attestation_available` false for the D3 live profile
(the static API remains scoped to D1 qualification, as recorded by
`development_static_attestation_scope`).  Resuming live activation requires an
approved fixed root-owned executable path/API or a same-UID service architecture,
followed by the integrated-image principal/dispatch/receipt corpus; adding
ptrace capability or weakening procfs checks is not an approved closure.

Its `--self-check` is source-wiring evidence, not a live service claim: the
report marks `development_only`, `browser_actor_wired`, and
`browser_actor_dispatch_exercised` true, while
`browser_actor_connected`, `receipt_observer_connected`,
`attestation_exercised`, `journal_exercised`, and
`integrated_image_qualified` remain false. The explicit `scope` is
`source_wiring_only`.

## Claim ceiling

This package proves the host/source PageOwner model, strict operation mapping,
principal binding, cancellation/deadline propagation, local-fixture policy, and
receipt lifecycle. It does not by itself prove a live Servo BrowserActor inside
the D2I image, production activation, controlled external egress, signed apps,
updates, hardware qualification, or release readiness.
