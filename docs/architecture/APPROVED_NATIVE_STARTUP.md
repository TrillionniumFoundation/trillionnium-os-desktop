# Approved immutable native startup candidate

This package composes the retained approved Control/Agent connection with the
existing closed immutable native Servo owner. It is a source candidate. The
installed AgentPort main still returns `ProductHandlerUnavailable`; browserd's
main remains a self-check. No service, policy root, capability, broker or renderer
privilege is provisioned by these APIs.

`ApprovedRetainedAdmission::from_received` consumes an actual retained handoff
and the `ApprovedAgentSelection` from its same root-owned retained policy source.
It stores the old approved connection and its exact private monitor together.
There is no public split, clone, caller principal, observed-hash approval or
replacement attestor. The old default Procfs Agent/Control incarnation, approved
ELF/unit, path custody, cancellation and journal checks remain in the chain.
Non-root reading a root peer's live executable may be denied; this candidate
does not manufacture a cross-UID broker or use static identity as a fallback.

The fixed capacity-one queue consumes whole admissions. Full, expired, changed
policy, retired or foreign-PID input cannot start a monitor, actor worker or
native constructor. On rejection the same original pair is dropped, rather
than returned as fresh admission authority. Dequeue checks the same queue
identity and current actual policy. The concrete native startup uses the first
packet's exact opaque `Instant` as its outer ceiling; later admitted packets
must have an original ceiling no later than that value. Selection, transfer,
queue waiting, thread creation and report waiting never allocate another
accepted 20 seconds. The existing native command limit is still the minimum
of the original request and the first native receipt plus five seconds.

`ApprovedImmutableNativeStartup::start` checks and consumes this complete
admission before invoking `ClosedImmutableNativeOwner::new` with an actual Servo
and rendering context. The native endpoint is made inside that constructor;
the startup API does not accept a `ServoRuntimeEndpoint` or generic PageRuntime.
Native Servo state stays on the creator PID and thread. The non-Send
`ProductRequestCoordinator` is constructed on one actor worker, using the same
approved principal, actual endpoint and moved managed journal lease. Per owner
there is at most one active admission, one queued admission and one diagnostic
result. A full result queue stops further work. Monitor handles are detached,
not joined; their same original deadline remains in force.

The reusable core `ApprovedRetainedAdmission::coordinator` is a generic source
composition API and accepts an endpoint. Its use alone proves no native Servo
execution. The concrete startup's private constructor wiring is the narrower
path. `ApprovedRetainedObservation` exposes service/report/runtime diagnostics
only. A caller cannot construct the coordinator's private terminal seal from
those values. Only the unchanged same-request managed journal chain reread and
terminal phase can produce the existing report. Report enqueue or Control
receipt does not prove Agent delivery, GUI presentation or effect success.

Retirement permanently closes the queue. New denial paths use creator-PID checks
and `try_lock`, never wait for the registry lock. `Requested` means atomic denial
was requested and cleanup can be contended; it is not a completed barrier.
`ActiveCancellationIssued` means the original token cancellation and socket
shutdown were issued where available; it also is not a native effect barrier.
An operation already inside a synchronous native call is not preemptible.
Foreign-process cleanup forgets inherited native/channel state for process exit
without shutdown, unlink, writer unlock or copied-lock access.

This is not a bounded-Drop guarantee for the whole graph. The unchanged old
connection and monitor destructors/public cancellation use mutex waits.
Synchronous procfs executable hashing, filesystem operations, thread creation
and native Servo calls also are not preemptively bounded. Every late authority
return refuses, but C/native calls, return-to-owner handoffs and repeated
cleanup faults are not proved free of every asynchronous interruption window.
The startup Drop requests retirement and never joins; it does not claim that
all old destructors, Servo retirement or report delivery have completed.

The immutable profile supports Health, ephemeral Create, Observe and Snapshot.
Navigate, Act, Extract and Wait are refused before durable admission. Such a
refusal has no terminal durable fact to seal: the retained report can expire
unresolved at its original ceiling. Close preserves the existing possible
effect/indeterminate classification and blocks reconstruction; it is not
promoted to successful pipeline closure. There is no replay, automatic Servo
rebuild or reconciliation shortcut here. Human input, trusted native chrome,
all-protocol renderer confinement and general application effect authority
remain separate obligations.

Required source verification uses `tools/verify_approved_native_startup.py` and
its contract/source mutation tests. Host Rust 1.93 tests run the new
`approved_native_startup_kernel` target with real three independent processes,
SCM_RIGHTS, original kernel credentials, root path custody, default procfs and
own managed journal. Its runtime completions are explicitly synthetic source
callbacks. Two unit regressions hold real mutexes and original socket FDs to
check Requested versus issued cancellation; they do not attest production peers.

The separate `g2-approved-native-startup.yml` workflow assembles pristine Servo
`670ae8a70801b162e186f81cbb5bdd2d59c39108` with the unchanged original native
adapter/target plus the additive startup/fixture/target. Original registry lock
identities and edges use the existing lock verifier. All five Rust sources are
formatted with the exact PIN configuration and compared byte for byte before
compiling with its Rust 1.97.1 toolchain. Fresh-process native cases use an
explicit privileged transient-systemd test policy: unit/UID and a known owned
ELF are pinned before peer launch, not approved from the peer's observed hash.
That test-only root profile is not an installed renderer permission model.

The new exact-PIN native cases are pending until their actual workflow runs on
the exact candidate source. Local source checks, host callbacks and previous
native results cannot be transferred to this package. Large Servo test ELF
hashing can consume the unchanged original budget; a real timeout must remain
a failed object, not be hidden by extending 20 seconds or five seconds. The
contract's production, hardware, broker, signing and release claims remain false.

The prospective source job separately binds the current canonical
`refs/pull/<positive-decimal-number>/head` and full `refs/heads/<base>`
advertisements. Each native Git advertisement must contain exactly one row,
exactly two fields, the exact queried ref and one lowercase 40-byte hexadecimal
object ID. Suffix aliases and ambiguous advertisements refuse. The event head
and base must equal those live objects; the checked-out event merge must have
exactly two parents in live-base/live-head order. Its commit, tree and queried
refs are recorded in the job summary before the unchanged workspace checks.
This verifies source identity at the guard's observation time. Ref drift after
that observation, later runtime qualification and installed authority remain
separate facts; these Git checks create no product permissions.
