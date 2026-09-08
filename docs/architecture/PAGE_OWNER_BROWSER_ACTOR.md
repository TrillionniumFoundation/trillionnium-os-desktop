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

The persistent `hepta-agent-port-development-sessiond` storage path now accepts
an explicit complete predecessor list and calls the lock-owning
`ReceiptJournal::open_chain` API. It restores global receipt IDs and logical
ordering before active-tail repair or recovery classification, preserving secret
redaction and never replaying an action. The older per-connection
`hepta-agent-port-developmentd` still has no chain-list configuration and rejects
isolated successors before any repair. See
[`D3_JOURNAL_CHAIN_RECOVERY.md`](D3_JOURNAL_CHAIN_RECOVERY.md) for the bounded
configuration, disk-backed tests, and remaining authoritative-head/retention
limitations. This source integration does not promote the exact-image gate.

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

The cross-UID executable-identity source blocker is closed without weakening the
service split.  systemd still runs the connection service as `hepta-browserd`
while the expected peer is `hepta-agent`, and the unit still grants no
`CAP_SYS_PTRACE`.  The explicit development graph instead selects the reviewed
`development-static-attestation` API and the compiled
`/usr/libexec/hepta-agent` path.  Every parent and the executable itself must be
root-owned, non-symlink, and non-writable; the path is reopened and re-hashed
for both admission snapshots and each BrowserActor dispatch.  The same
`AttestedPeer` continues to prove live PID/UID/GID, pidfd liveness, start time,
cgroup, and systemd unit.  BrowserActor calls `AttestedPeer::refresh_snapshot`,
so a static admission cannot silently fall back to the forbidden cross-UID
`/proc/<pid>/exe` read at dispatch.  The contract records
`SOURCE_IMPLEMENTED_AWAITING_D2I_EVIDENCE`, with
`development_static_attestation_available` true and scope
`explicit_development_profile_only`.  This is a reviewed service-mechanism path
binding, not a claim that the live procfs executable link was observed.  Exact
integrated-image principal/dispatch/receipt evidence and independent security
review remain mandatory before activation or promotion.

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

## Receipt admission and response preparation

Duplicate Requested callbacks preserve the original in-flight coordinates.
Journal facts are bound to admission identity, not a later PageOwner snapshot.
The local atomic fixture prepares fallible response fields before committing
consumption. These source-level rules and their negative tests are specified in
[RECEIPT_ADMISSION_IDENTITY.md](RECEIPT_ADMISSION_IDENTITY.md); no Servo or
integrated-image capability is promoted.

## Optional in-process engine-thread dispatch

[ENGINE_THREAD_DISPATCH.md](ENGINE_THREAD_DISPATCH.md) defines the bounded
actor-to-engine scheduling mechanism and real connected-stream/receipt host
corpus. Its engine remains a fixture in tests; the mechanism is not installed
in the product, does not implement cross-process IPC, and does not prove live
Servo node resolution, native input or exact-image D3. Existing topology,
authority and promotion requirements remain unchanged.

## Persistent development engine-thread runner

The persistent `hepta-agent-port-development-sessiond` now uses the main-thread
AtomicFixtureRuntime through EngineThreadRuntime. Its single scoped connection
worker owns the actor and receipt observer, retains the first complete attested
process snapshot (including start_time_ticks), and refuses later identity drift.
Engine retirement stops accept polling and is never an implicit engine restart.
No new configuration, production listener, executable, dependency or Servo API
is added. The old single-connection binary remains unchanged. See
`docs/architecture/D3_SESSION_ENGINE_RUNNER.md` and
`contracts/d3-session-engine-runner.v1.json` for lifecycle, bounds, failure and
source-test evidence. This remains a local fixture, not an installed Servo claim.

## Request-scoped identity across queueing

`AttestedPeer::request_custody` retains the original pidfd and identity source for
one handler lifecycle. All queued RequestControl copies share a revocable
verifier; original attestor selection, engine entry/return and final actor return
are rechecked. Identity loss never becomes a confirmed success or replayable
refusal after an uncertain effect. See
`docs/architecture/REQUEST_PEER_CUSTODY.md` and
`contracts/request-peer-custody.v1.json` for APIs, configuration, failure and
resource limits. No production activation or actual Servo proof is introduced.

## Session reconstruction isolation

Actor creation now lazily obtains an OS-sourced incarnation at the first valid
SessionCreate; session/WebView tokens are namespaced across actor reconstruction.
The atomic fixture scopes frame identity by session and WebView before publishing
a target. Entropy failure has no predictable fallback; deadlines and bounded
opaque Browser API v1 fields remain enforced. No old PageOwner is resurrected
from receipts and no operation is replayed. See
`docs/architecture/SESSION_INCARNATION.md` and
`contracts/session-incarnation.v1.json` for APIs, failure ordering, compatibility,
regressions and limits. This is source/host evidence, not actual Servo, systemd,
image, hardware, anti-rollback, production activation or release proof.

## Callback-shaped engine scheduling

The optional `callback_engine_pair` / `CallbackEngineOwner` path starts an
operation on its creator thread and accepts a single-use `EngineCompletion`
from a later callback. The application continues native events between pumps;
its timer follows the original deadline and bounded cancellation-check schedule.
Ordinary Act never substitutes for the dedicated atomic semantic hook. The
existing request endpoint now wakes on abandonment and Drop as well as enqueue.
Wakes may be coalesced and are not a count of dispatched operations.
See `docs/architecture/EVENT_LOOP_COMPLETION.md` and
`contracts/event-loop-completion.v1.json` for APIs, ordering, tests and limits.
This is source/host fixture evidence only: no Servo/native event loop, process
IPC, installed image or product authority is added. The development daemon
continues selecting its synchronous fixture backend; no activation changes.
