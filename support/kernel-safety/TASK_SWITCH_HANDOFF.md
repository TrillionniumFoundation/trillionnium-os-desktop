# Completed switch ownership prerequisite (W3A)

W3A closes the interval between a scheduling decision and actual context release.
A blocked POSIX Task can subsequently wake on a CPU allowed by its existing
affinity mask. `cpu.weight` writes remain rejected. This is not delivery of live
hierarchical group shares, proactive migration of current/queued/throttled tasks,
dynamic group membership, RT/FAIR group rebinding, or mobile/GPU isolation.

## Production boundaries

`ostd::task::scheduler::reschedule` first checks sleepability and reports an RCU
quiescent state only when the raw preemption count is zero **and** IRQs are
enabled. `Rcu::read` acquires a preemption guard; `read_with` borrows an
`InAtomicMode` guard. That guard is confined to its creating task. Consequently
the two raw checks exclude both reader forms, including bootstrap's
`might_sleep` exemption. This is the same rule as the existing `halt_cpu` path.

The RCU monitor removes callbacks under its state lock, then invokes arbitrary
`FnOnce` destructors after unlocking. They may block or recursively reschedule.
Run them once before the **first** scheduling closure/dequeue, when the logical
current is still intact. Never run them in a Wait/Exit Retry or with IRQs off.
An outer IRQ guard then covers each decision through `processor::switch_to_task`;
the runqueue lock is released before switching. Retry/DoNothing drop that guard.

For a real outgoing Task, `ClassScheduler` retains a `PendingSwitch` containing
its strong Task/Thread references, single original runtime cursor, explicit
disposition and uncommitted FAIR selection. `rq.current` reserves the incoming
entity; its provisional runtime is never charged. Every settlement helper reads
the executing old segment while the switch is pending. The old Task is absent
from every selectable class/throttled queue and keeps its original `cpu` tag.

OSTD reconstructs its previous strong `Arc<Task>` on the incoming stack after
context save. `Scheduler::finish_switch` runs with IRQs off **before**
`switched_to_cpu.store(false, Release)`. Under the source rq lock it settles the
old original CPUmax and FAIR interval through one cut, commits the pending FAIR
selection and starts the incoming runtime at that same cut. No historical owner
or quota is replaced, copied or reset. A failed paired clock still invalidates
the original accounting owner rather than inventing an endpoint.

At this checkpoint the physical switch has already happened. If the old tail
exhausts a shared CPUmax, incoming cannot be cancelled. Request local preemption,
retain its real incoming interval, and consume the request only after switch
cleanup, IRQ restoration and safe drop of the previous strong reference.

After the Release store and existing post-schedule handler, OSTD invokes
`Scheduler::complete_switch` with that strong reference. The store alone is not
an exclusivity token: the source-owned pending slot and absence from selectable
queues prevent premature acquisition. OSTD's existing next-context AcqRel CAS
provides the actual context-writeback fence. Kernel code adds no unsafe block.
The bootstrap path with no class-accounted outgoing Task commits directly; it
does not leave an unfinishable pending selection.

## Wake, publication and lock order

Disposition is `Runnable`, `Waiting { woken }` or `Exiting`, captured under the
same rq lock as the preceding Wait/Exit update. It is not inferred from a
Thread's separately published exit flag. `dequeue_current` retains `cpu=origin`.
Wakes arriving during dequeue/physical switch merge under the source rq lock.
They do not enqueue, allocate a second owner, or request ordinary source-CPU
preemption. Otherwise a low-priority late wake could preempt the reserved RT
incoming task. A no-next Wait Retry consumes its latch by restoring the same
Task/runtime, allowing OSTD's existing pointer-equality DoNothing return; it must
not wait for a physical callback that will never occur. Exit never restores.

Completion requeues a runnable outgoing Task locally, including its original
throttle eligibility. A waiter still asleep or a final Exit publishes `cpu=None`
under the source lock. A woken waiter moves out as a single detached strong token
while retaining `cpu=origin`. Release the source rq lock before selecting and
locking the destination. Publish its new cpu/last_cpu and one queue entry under
the destination lock. The destination's existing policy comparison determines
whether to notify it, after rq unlock; no remote acknowledgement is awaited.

Duplicate wakers see a nonempty cpu tag and merge into the existing owner. If a
waker waited for an old source lock and completion has since published None or
a new CPU, it unlocks and retries fresh routing. It must not CAS None back to a
stale source. At no point are two rq locks held. Prepared non-root membership
is still not admitted to production; this stage adds no root fallback or live
admission shortcut. N0 trusted control's existing single-CPU admission and
observation checks remain intact; this wake path grants no trusted SMP control.

## Authorization prerequisite

Before storing a target's mask, `sched_setaffinity` permits the caller's effective
UID matching the target's real/effective UID; otherwise it invokes the existing
LSM `SYS_NICE` check against the target process's user namespace. There is no
global-root bypass. Release the PID table before that check and retain the
process with a fallible Weak upgrade, so concurrent reap returns `ESRCH` rather
than panicking. Denial publishes no mask or scheduler change.

An accepted mask is used for fresh spawn/blocked-wake routing. This prerequisite
does not promise synchronous enforcement on a running, already queued or
throttled Task. Fork's pre-existing full-mask initialization is unchanged; tests
measure the actual initial CPU and do not assume Linux affinity inheritance.

## Verification and development

The OSTD regression defers a destructor which checks IRQs enabled and logical
rq.current equal to the physical current, then recursively yields. Its old
placement fails that assertion in a real guest. Additional tests reject live
readers and IRQ guards as quiescent states. VMX unavailable cases remain explicit
soft skips, not hardware qualification.

Five controlled Core regressions use real Task, Process, cgroup and original
CPUmax objects with deterministic cuts: physical-tail ownership, one merged wake
token, same-Task Retry restoration, Exit non-resurrection, and shared-quota tail
exhaustion. A sixth Scheduler-trait regression requires a merged waiter wake not
to request source preemption of a reserved RT task. These fixtures do not run
their Task objects in OSTD and are not SMP or share evidence.

The ordinary [authorization probe](../../tests/kernel/affinity-auth/README.md)
checks actual cross-UID `EPERM`, unchanged mask/CPU observation, same-owner update
and restoration, and child cleanup. The ordinary
[handoff probe](../../tests/kernel/task-handoff/README.md) checks actual same-Task
CPU identity across completed waits on SMP 2/4, immediate wake races and real
CPU time under the original `cpu.max`. Existing CPUmax 1/2/4, safety, stop and IPC
lanes remain regression evidence. Exact logs and final source/artifact binding
are retained outside the checkout; development failures are not deleted.

The original `ipc-memory-v1` upstream source guard stays unchanged. Its old pin
does not qualify this composed scheduler/OSTD source. A later composition must
receive a separate strict named profile; a generic IPC pass is not that profile.

Continue with W3B only after freezing this evidence: safe proactive migration and
class reattachment, original incarnation/node leases and membership generation,
then real hierarchical weights and the SMP saturation/oversubscription matrix.
