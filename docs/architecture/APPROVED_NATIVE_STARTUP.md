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
identities and edges use the existing lock verifier. This additive target has
one direct workspace `libc` dev dependency for its Linux credential/FD fixture;
the approved profile permits exactly that one Servo dependency edge and requires
the existing precise `libc` 0.2.186 registry identity and checksum. The original
owner profile retains its original dependency edge guard. All five Rust sources are
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

## Private composition scope successor

The additive [approved composition scope profile](../../contracts/approved-composition-scope.v1.json)
keeps the existing public API and its complete live executable readback. Four
internal helpers return only the captured original `Instant` or the same
cancellation token. They cannot supply a peer snapshot, runtime permission,
durable terminal fact or report seal. Their checks begin with the creator PID,
then use the retained root policy/path, the actual original Control and Agent
pidfds, cancellation and the queue's fixed ceiling. The temporary session
metadata used to check that pair does not extend either lifetime. No ELF digest
is cached or accepted as evidence that current executable bytes stayed equal.

`try_submit` retains full checks before and after local queue association. The
coordinator constructor retains its own complete admission checks and the
return check. `serve` retains full checks at entry, immediately before the
monitor thread starts, and after it starts before the coordinator consumes the
connection. Only denial-token borrowing and local queue/worker preparation
between those checks use the private scope. Existing actor rebind, dispatch,
completion and report checks keep their full readback. The public deadline,
cancellation and retained polling bodies are preserved.

`tools/verify_approved_composition_scope.py` pins the finite helper bodies,
retained root/pidfd sources and complete boundary order; mutation tests remove
root gates and post-spawn checks, attempt public exposure and substitute
literal/comment decoys. These are structural source checks. Existing actual
default-proc kernel cases remain required, as do a fresh exact-pin native run
of all original six cases with unchanged 20-second accepted and 5-second
native budgets. The profile is disabled by default and supplies no installed,
long-lived service, hardware, production policy or release qualification.

## Private constructor route successor

The additive [private constructor profile](../../contracts/approved-constructor-route.v1.json)
preserves every public constructor body. The approved public wrapper performs
the full original Agent and Control readback before passing the same privately
held connection and binding through local field borrowing to the private
constructor. Only that adjacent repeated check uses a private denial gate.
The raw `None` branch retains its full readback. The actual approved actor
factory, principal comparison, and final constructor full readback still run.

The gate checks its creator before descriptor access, cancellation and the
original `Instant`, the actual Agent pidfd and original Control custody, and
the root-selected opaque binding's policy/path and original pair. It compares
the original pair's captured peer fields and ceiling with the same factory's
held connection. This comparison grants no authority to caller snapshots or
principal fields. Failure revokes that connection's original custody. The gate
returns only `Result<()>`; it supplies no live snapshot, runtime permit or
report seal and caches no executable bytes across calls.

`tools/verify_approved_constructor_route.py` binds this finite route, the sole
approved caller, the unchanged public bodies and full actor/return boundaries.
Its mutation corpus removes creator, root, pidfd, original custody, ceiling and
final full checks and attempts caller authority, visibility and literal decoys.
Those checks are source correspondence. The existing real default-proc kernel
groups and a fresh exact-pin run of all original six native cases remain
required with the original 20-second accepted and 5-second native limits.
There is no measured speedup, installed activation or production qualification
claim from merging this private duplicate alone.


## Versioned Control idle-wait successor

The additive [retained Control readiness profile](RETAINED_CONTROL_READINESS.md)
changes only explicitly approved private monitor routing. Its creation-time
Control identity and reporting-only idle scope preserve original full message,
report and effect checks and the first twenty-second ceiling. Legacy raw
methods remain byte exact; finite inverse transfer reconstructs changed source
for the original contracts. New default-proc host and transport corpora do not
replace the unchanged original six-case native qualification. Product startup,
installed policy and the separate sixty-second health gate remain open.
