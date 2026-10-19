# G1-b: account the scheduler handoff tail

The original class runqueue previously settled an outgoing task, selected the
next task using another clock observation, and started its new runtime using
a third observation. The outgoing interval between settlement and replacement
was discarded. Selection could also advance a common ancestor's quota window
before that interval was charged, losing the previous window's overrun debt.
On the OSTD wait and exit paths, `dequeue_current` discarded the old runtime
before selection and possible retries completed.

This slice closes those intervals in the existing class runqueue and charges
the same original `CpuMax`. The accounting units remain scheduler TSC clocks;
the paired BOOTTIME clock work is a separate dependency, and `CpuMax` has not
yet been converted to nanosecond windows. Native effects remain closed.

## Production changes

The implementation is in the original
[class runqueue](../../kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs).
It does not replace OSTD's scheduler, introduce an accounting service, or add
another quota, cumulative counter or configuration revision.

Each selection attempt first settles the outgoing segment. Candidate lookup
and replenishment reuse that settled timestamp. After selection, a fresh
timestamp defines the handoff cut. The outgoing owner is charged through the
cut **before** checking the candidate's current eligibility, and the incoming
runtime starts at exactly the same cut. If the debit exhausts a shared
ancestor, the candidate is parked and selection continues while the outgoing
segment retains ownership. This prevents eligibility from erasing an unpaid
part of a quota window.

The existing `CurrentRuntime` is moved into `PerCpuClassRqSet::dequeued` when
the task waits or exits. Runnable `current()` becomes `None` immediately, as
the original OSTD contract requires. The moved segment retains its exact
controller and ancestor references, and its existing accounted-through cursor
continues across selection retries. At most one of `current` and `dequeued`
owns a segment. A successful selection settles and releases the dequeued
segment before installing the next segment. No budget or usage is copied.

Ticks, configuration checkpoints and owner publication checkpoints settle the
retained segment too. A tick with no runnable current task does not extend the
old CFS slice. Handoff and dequeue settlements do not update CFS's raw TSC
`start`, `delta` or `period_delta`; their original scheduling-class updates
remain in their existing paths. All production observations still use the
original `sched_clock`, and all runqueue changes retain the local IRQ and
runqueue-lock ordering established by the scheduler.

The cut is the class scheduler's accounting handoff. This does not instrument
OSTD's later physical context-switch instruction, resolve its separately
documented scheduler-decision/context-switch race, or qualify cross-CPU
rendezvous. The N0 scope remains a single vCPU. Invalid clock samples must
still fail closed when the separate nanosecond accounting integration is made.

## Four actual-runqueue regressions

The tests are in
[scheduler_handoff_regressions.rs](../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/scheduler_handoff_regressions.rs).
`CpuRunQueueFixture` owns an actual `PerCpuClassRqSet`, including its original
fair and idle queues. Production selection receives `sched_clock`; only the
standalone fixture supplies deterministic observations. The fixture checks
that every supplied observation is consumed exactly once. Its real POSIX
tasks are never injected into OSTD's running FIFO test scheduler.

| Test suffix | Required result |
| --- | --- |
| `outgoing_tail_ends_at_the_incoming_segment_start` | An initial settlement at 11 and handoff at 29 charge all 29 clocks to the old leaf; a tick at 47 charges 18 to the new leaf and 47 total to their common ancestors. The incoming CFS slice starts at 29 with zero deltas. |
| `handoff_debits_the_old_window_before_rechecking_a_shared_ancestor` | Selection begins while the shared parent is eligible, then crosses a window. The old interval spends twice the quota in that window, leaving one full quota of positive debt. The initially selected fair candidate is parked, the idle fallback outside the parent is selected, and the new window retains its exact suffix usage. |
| `waiting_dequeue_retains_its_owner_through_selection_retries` | Wait/update at 11, dequeue at 19, unsuccessful selection at 29, a tick at 31 and handoff at 41 all remain charged to the outgoing leaf. A tick at 53 charges only the next 12 clocks to the incoming leaf. The dequeued CFS slice stays at its original 11-clock update. |
| `exiting_dequeue_retains_its_owner_through_selection_retries` | The same sequence after the actual task exit flag and process cgroup detachment preserves the original owner through the final 41-clock prefix. |

The fixtures use actual cgroup hierarchies and Process/Task constructors. They
restore the original root budget, release retained task bindings and remove
their nodes. These assertions validate the original owners and runqueue
transitions; controlled timestamps are not evidence of live SMP or a new
clock domain.

## Frozen negative controls

Apply each patch separately to a fresh checkout of the final integration
candidate. Every expected failure has the prefix
`aster_core::fs::fs_impls::cgroupfs::controller::cpu::scheduler_handoff_regressions::`.

| Patch | Deliberate defect | Exact expected failed suffixes |
| --- | --- | --- |
| [cpu_handoff_drop_tail_negative.patch](cpu_handoff_drop_tail_negative.patch) | Omit the outgoing debit at the incoming segment's start | All four tests above |
| [cpu_handoff_eligibility_first_negative.patch](cpu_handoff_eligibility_first_negative.patch) | Check/advance the candidate before charging the outgoing segment | `handoff_debits_the_old_window_before_rechecking_a_shared_ancestor` |
| [cpu_dequeue_drop_owner_negative.patch](cpu_dequeue_drop_owner_negative.patch) | Drop the original segment at dequeue instead of retaining it through selection | `waiting_dequeue_retains_its_owner_through_selection_retries`; `exiting_dequeue_retains_its_owner_through_selection_retries` |

The original core gate is:

```sh
python3 -I -B support/build/ktest/run.py \
  --crate aster-core --skip-osdk-install --output /absolute/new/output
```

Use a fresh output directory outside the source tree. The negative checkouts
are intentionally modified and must retain their actual source snapshots,
modified file hashes, ELF bytes, original serial output and process result.
Do not filter test names or weaken warnings. Expected RED completion is the
normal ktest failure exit, QEMU 65, with exactly the stated four, one or two
failures. A compile error, boot failure, timeout, missing summary or another
failure set does not satisfy the control.

The unmodified integration candidate must pass the full original core and
OSTD gate, followed by the ordinary-kernel CPU configuration probes on the same
published kernel ELF. Source parsing and patch applicability alone do not
establish that this slice passed the kernel gate or that G1-b is complete.
