# Request-scoped peer custody across engine dispatch

**Plan:** `2026-08-29-d6`<br>
**Gate:** `D3-01`<br>
**Status:** source candidate; local Linux and fixture regression evidence only<br>
**Contract:** `contracts/request-peer-custody.v1.json`

## Scope and non-claims

This mechanism closes the observed gap between actor-side identity refresh and
later execution of a queued request. It retains an already-attested peer rather
than interpreting a copied PID or PageOwner as live authority. It does not
implement a Servo adapter, a native event loop, attested cross-process IPC,
installed systemd/image qualification, a capability service or external effects.
Source presence and local tests do not promote D3, governance, hardware or release.

## Threat and reproduced failure

Previously, `handle_attested` refreshed before `handle_inner`, but an engine queue
carried only a PageOwner, typed request and cancellation/deadline. Changing the
attested cgroup or executable after queueing but before `pump_one` still called
the backend. The regression uses real threads and pidfds with explicitly
synthetic procfs identity facts; it is not a demonstrated systemd compromise.

A second risk is stale success: if identity is lost after the backend has started,
an error must not claim that the operation was safely refused or rolled back.
The AgentPort Dispatched fact conservatively precedes handler/engine entry, so
some requests refused before actual engine execution can also be indeterminate.

## API and ownership

`AttestedPeer::request_custody()` creates one non-cloneable `PeerRequestCustody`.
It duplicates the retained pidfd with `OwnedFd::try_clone` (CLOEXEC), copies the
original snapshot and original live-or-static executable source, and pins the
original ProcfsPeerAttestor configuration. Full revalidation must succeed before
the caller receives custody. This never substitutes a newly opened PID for the
original descriptor. Existing bounded procfs reads can use temporary pidfds for
namespace resolution; one dedicated additional retained pidfd belongs to the
request. No new thread, socket, listener, feature, environment input or dependency
is created by this API.

`custody.verifier()` returns a cloneable, Send+Sync `PeerRequestVerifier`. Clones
retain the same lease state; they do not extend authorization. Explicit revoke,
custody Drop, a liveness failure, or a failed full refresh irreversibly sets a
shared revocation flag. Restoring previously valid bytes cannot revive that lease.
A subsequent independent request needs new custody and fresh validation. A text
request ID is never a means of prolonging custody. Global receipt ID uniqueness
is still enforced by the journal, not by these cloneable handles.

AttestedPeer now remembers its creating attestor. `refresh_snapshot` refuses a
caller-supplied attestor with a different procfs root, even if it would return
identical snapshot data. The existing explicitly selected static executable path
remains static on refresh: it is not silently replaced by a cross-UID procfs exe
read. Static path evidence remains distinct from a live running-image observation.

## Dispatch sequence

1. The actor checks its original deadline, refreshes the attestation, and verifies
   semantic principal/mechanism continuity under the existing binding policy.
2. It creates custody and installs an actor-local verifier slot for this request.
   A drop guard restores the previous slot on every normal or unwinding exit.
3. Normal runtime controls and bounded create-cleanup controls clone this same
   verifier. New cleanup deadlines never create new peer authority.
4. Queue/wait cancellation checks call `ensure_active`: original deadline and
   cancellation, shared lease revocation, and the original pidfd's liveness.
   The wait loop does not read procfs or hash an executable.
5. `EngineThreadOwner::pump_one` calls `ensure_current_peer` immediately before
   backend entry and after backend return, before accepting a reply. This checks
   full identity through the original source and rechecks cancellation/deadline.
   Ordinary Act remains forbidden; PageAct still uses the dedicated atomic hook.
6. Before returning an attested handler result, the actor checks the deadline,
   revalidates identity once more, and checks the deadline again. Custody then
   drops and invalidates all retained controls, including queued/late copies.
   Either final deadline failure invokes the existing late-effect reconciliation:
   unconfirmed creation receives bounded cleanup, and bound effects enter recovery.

The D3 persistent and single-connection development handlers already call
`handle_attested`, so this is active in those source paths without another mode
selector. The existing plain `handle` compatibility path has no peer custody;
it must not be described as authenticated merely because a check returns Ok.

## Failure, uncertainty and recovery

| Boundary | Required behavior |
|---|---|
| Attestation/source/custody failure before dispatch | Fail closed; no engine call |
| Observed queued identity drift | No backend entry; revoke and retire queue |
| Identity loss during/after backend work | Discard success; runtime unavailable; affected PageOwner recovering |
| Potential-effect response after identity loss | Wire `indeterminate`, retry `never_automatic`; journal has no invented outcome or success digest |
| Request cancellation or original deadline expiry | Existing bounded cancellation/deadline behavior; custody still drops |
| Arbitrary backend unwind | Scope restored and verifiers revoked; caller must retire the actor, not assume panic recovery |
| Late retained verifier after request completion | Fails, even with same textual request ID and unchanged live process |

RuntimeFailure gains PeerIdentityRevoked, conservatively mapped to the existing
Browser API `indeterminate` code. No wire error enum or receipt disk version is
changed. No effect, navigation or request is replayed. Revoked identity cannot
obtain new Close authority from the create-reconciliation path. An unconfirmed
close therefore leaves the runtime poisoned until separately controlled recovery.

## Resource and concurrency limits

Full refresh retains the existing bounded stat/status/cgroup/image size limits;
image hashing can still involve substantial disk I/O. Checks before and after
refresh do not interrupt blocked kernel I/O. The 5 ms requested wait poll is not
a real-time guarantee. Real UI integration may need a reviewed nonblocking proof
producer; it must not replace full identity with an unbounded stale cache.

Checks are not atomic with a process exiting, execing, changing cgroup or handing
a socket to another process. A change can occur after the final check and before
an effect, and a transient change can occur between samples. Pidfd detects exit,
not every exec. A kernel-enforced supervisor/IPC/engine commit protocol is still
required for stronger atomic revocation. The current backend must cooperate with
control checks; this mechanism cannot preempt blocking code or undo an effect.

## Configuration, compatibility and operations

No production activation, install layout, daemon profile, default, Servo pin,
patch ledger or dependency lock changes. A different attestor supplied to an
existing AttestedPeer now fails with AttestorSourceChanged; callers must preserve
the original source rather than use a fallback root. After an identity failure,
retire the connection/runtime and inspect durable facts. Do not re-enable the old
lease, rebind a recycled PID, select another process or clear receipts to retry.

Public API documents must distinguish identity continuity from application
permission and DOM freshness. Node identity, native human preemption, source
publication, independent review and exact-image proof remain separate blockers.

## Tests and acceptance

Peer-crate tests use real /proc snapshots, real pidfds, a real child exit,
CLOEXEC inspection, cross-thread verification, revocation/drop and static-source
preservation. Synthetic procfs tests cover immutable source selection and error
latching. Actor tests cover queued credentials/start-time/cgroup/executable drift,
scope cleanup, cancellation, deadlines, late controls and unattested non-claims.

The end-to-end AF_UNIX test runs actual handshake/codec/actor/thread queue/disk
journal for creation and navigation, using a fixture cgroup and fixture backend.
It observes Dispatched on disk before backend entry and, after a post-navigation
identity change, checks six lifecycle records ending in Indeterminate without a
success digest and a recovering PageOwner. No real external navigation is done.

`tools/validate_d3_development_profile.py` reads the exact registered inputs and
checks required call positions, source preservation, failure mapping and test
wiring. Its Python mutation corpus is a structural regression gate, not a Rust
parser, formal proof, live governance check or higher-tier qualification.
