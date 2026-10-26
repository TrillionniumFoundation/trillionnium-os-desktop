# Forced affinity transfer (W3B2)

This stage connects the ordinary POSIX `sched_setaffinity` setter to the existing
class scheduler. It moves actual current, physically queued, and CPUmax-throttled
Tasks between admitted legacy-root CPU queues. It does not enable non-root FAIR
group admission or `cpu.weight`. Unadmitted prepared group layouts return
`EOPNOTSUPP` before effects; there is no fallback to root. The trusted N0
single-CPU restriction is unchanged. `memory.max` remains unsupported.

## Development entry points and failure boundary

`sys_sched_setaffinity` copies and checks the complete nonempty CPU mask before
calling `set_thread_affinity`. A nonself target is held by a strong Thread and
Process; the caller must own its real/effective UID or pass the existing LSM
`SYS_NICE` check in the target user namespace. The PID-table guard does not span
those checks or administration. Getters retain their separate read path. This
stage preserves the independent P1 target identity gate; P2/P3 priority limit
and user-policy snapshot changes require a later combined-source integration.

The sleepable administration view serializes writers. Cold preparation chooses
an allowed destination and reserves physical FAIR/RT and throttle slots using
[W3B1](AFFINITY_CAPACITY.md). It prepares a fallible request Arc and, for an
external caller, a fallible direct waiter/waker. ENOMEM, overflow, stale capacity
or closed route errors precede mask publication and task detachment. An attempt
generation may advance on a failed cold allocation; it grants no authority.

The request and complete mask are published under one short slot spinlock. The
controller disables local IRQs through releasing administration, so a remotely
published RT Task cannot strand the control thread while it owns that mutex.
A live request pins policy/priority until actual ownership publication. Later
writers release administration before waiting, then reacquire and retry. They
use their original ordinary CPU budget; no protected recovery budget is created.

## Actual ownership and synchronization

A queued FAIR/RT or throttle entry is removed by Arc identity, retaining a slot
in its original physical container. `QueuedRemoval` restores the exact owner
when dropped before publication. Destination publication disarms rollback before
updating the CPU tag or enqueueing; afterwards Drop only refunds the source slot.
It never holds source and destination runqueue locks together.

A current, reserved incoming, dequeued Wait/Exit retry, or physical outgoing Task
cannot be removed as a queued Task. The source tick/yield recognizes its pending
request and requests a real switch. W3A settles the original runtime owner through
the pre-release physical tail; only after OSTD clears `switched_to_cpu` with
Release ordering does its strong previous-Task callback publish the old Task.
An incoming request forces the next safe decision after cleanup. An unwoken
sleeper acknowledges its new mask without becoming runnable; every future
None-to-owned wake synchronizes with the request slot and revalidates the mask
under the actual destination lock. Concurrent duplicate wakeups retain one owner.

The sole detached owner claims the capacity once. A non-owner cannot acknowledge
a claimed request; completion follows publication. Exact destination rq identity
and original source rq identity are checked, not just CPU numbers. FAIR positive
relative debt is rebased to the destination floor; copying another CPU's historical
floor or resetting debt is forbidden. The original Task CPUmax owner and budget
remain intact. Eligibility is checked after settling the destination's current
runtime; an exhausted Task enters its prepared throttle slot without fresh quota.

Lock order is administration mutex, at most one rq, then the existing short
policy or request locks. Slot installation never acquires an rq. Both request
state and slot use `LocalIrqDisabled`, because IRQ/tick readers may otherwise
interrupt the same controller while its default preemption-only lock is held.
Completion takes the controller waker out of state, releases the state lock,
then notifies. A terminal request owns neither capacity nor controller Task;
retiring its last Arc in a hot path cannot destroy controller data there. Source
reservation cancellation and retired storage destruction occur outside all rqs.
No new kernel `unsafe` is introduced.

Forced publication relies on the existing per-CPU timer for dispatch and does
not allocate a new remote IPI closure. It grants no new hard latency guarantee.
Ordinary spawn/wake/requeue growth remains; this stage is not a proof that all
scheduler paths are allocation-free. Queue removal/installation can scan O(n)
items with IRQs disabled, so bounded IRQ latency still needs a different queue
index. Static CPU topology and the private stable rq allocation remain required;
CPU hotplug or layout replacement needs an explicit incarnation protocol.

## Acceptance and limits

The immutable `probe.c` in `tests/kernel/forced-affinity` is byte-identical to the
frozen W3A before oracle. On that old retained ELF, SMP2 and SMP4 each have 21
passing setup/control checks and exactly three failing migration checks. The
new source must pass all 24 checks on the same C and static guest executable:
current busy-loop getcpu, a real FAIR entry queued behind a live FIFO hog, and
a real CPUmax-throttled entry. The last must receive no new budget when moved,
then recover on the destination after its original owner is legitimately unbound.
All children are reaped and both cgroups removed.

The separate RT management probe checks that a second CPU can lower the migrated
FIFO Task to NORMAL while that Task actually runs on the destination, then joins
all workers and watchdog. Whether the affinity caller had returned before the
rescue is a diagnostic, not a required scheduling order or proof of every
pre-return RT preemption window. An initial stricter fixture incorrectly required
that order; its failed receipt is retained separately. Static lock ownership and
request pinning remain necessary parts of the review.

Controlled kernel tests check real queue cancellation/refund, claimed request
acknowledgement exclusion, and terminal controller release. They do not substitute
for the ordinary SMP tests. Final acceptance additionally rebuilds the ordinary
non-ktest product from one clean committed source and reruns W3A wake, affinity
permission, CPUmax SMP1/2/4, safety, stop, IPC and Binder regressions using that
exact ELF. Old `ipc-memory-v1` source validation remains unchanged and rejects
this composition; generic IPC/Binder regression is not that locked Unix profile.

Dynamic non-root group membership/leases, group generation changes, hierarchical
FAIR shares and their real thread-count/ancestor/SMP CPU-time matrix remain open.
There is no public group-weight delivery in this stage.
