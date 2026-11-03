# Zero-CPU fatal cleanup

## Observed failure

The original six-second watchdog observation succeeded for a zero CPU cap, but
the original 120-second QEMU gate timed out after `G1DW_COMPLETE`: the parent
sent SIGKILL and blocked in `waitpid`. The workload could not run its kernel
exit path because every scheduler eligibility check still rejected its zero
quota. A completion marker alone is not a successful guest result.

An independent diagnostic boot used the unchanged failing kernel ELF
(`59a2ed8f441411bbc1406291eddcdce720c60ccd1d020aaf15fd7e93888f95a1`).
GDB stopped the parent in `process::wait::do_wait` called by `sys_wait4`, then
observed the timer's `PerCpuClassRqSet::replenish_throttled` call
`task_cpu_eligible` twice for the same Task. Both returned false at BOOTTIME
6,516,996,685 and 6,527,248,070 ns. The diagnostic guest was deliberately
terminated after stack capture; it is not a passing gate and does not replace
the original timeout evidence.

## Original owners and entry boundary

`SigQueues` records an irreversible atomic fact only after its original queue
accepts SIGKILL. Dequeue does not clear that fact: an exit path can itself be
preempted, and a sibling can consume a process-directed signal. Thread-directed
receipts belong to that thread's queue; process-directed receipts apply to the
original shared process queue. New process and thread constructors create fresh
queues. A new thread in an already fatally signalled process still observes
that process's receipt; this is shared process state, not copied thread state.

The existing init immunity to default-action signals is preserved. The
effective fatal predicate uses the original `Process::is_init_process()`
observation (`parent.pid() == 0`), not a second numeric-PID rule. Catchable signals do not qualify for
this exception, and neither a manager label nor a recovery request can set it.

The scheduler still observes the original bandwidth owner and clocks. Only an
effective SIGKILL receipt lets an otherwise ineligible task finish fatal kernel
cleanup. This does not change the quota, window, revision, usage or debt.
`CurrentRuntime` continues to debit actual execution to the original retained
CPU owner. The existing no-Process cleanup rule for an already-exited thread is
unchanged.

Admission alone would be unsafe: the original architecture loop executes user
instructions before its ordinary `has_kernel_event` check. All four architecture
entry loops now check a nonblocking fatal hook after `might_preempt` and after
disabling local IRQs, immediately before the existing user-entry preparation.
A fatal event returns `KernelEvent` without running user code. The upper half
then invokes the original `do_exit_group` path. Exec's fatal check and ptrace
wait interruption use the same irreversible fact. No new unsafe block, CPU
budget, signal permission or userspace control operation is introduced.

This repair targets the N0 zero-cap SIGKILL scheduling deadlock. It does not grant CPU
time to a user signal handler, implement trusted user pause intent, or establish
a global memory/IPC recovery reserve. N0 evidence does not qualify SMP races.

## Required evidence

The full core gate retains the 292-test baseline and adds these three named
regressions (295 total):

- `zero_quota_thread_sigkill_resumes_only_fatal_cleanup_with_original_debit`
- `zero_quota_process_sigkill_resumes_only_fatal_cleanup_with_original_debit`
- `fatal_receipts_follow_original_signal_queues_without_constructor_inheritance`

They use real Process/Task/signal queue objects and the original class-runqueue
fixture. They reject SIGUSR1 as a scheduling bypass, keep the zero cap and
positive debt, retain eligibility after actual signal dequeue, and debit the
cleanup interval through the original owner. The constructor test exercises
the real constructors used by clone; it is not a syscall fork qualification.

The first complete 295-test core run executed all tests but passed only 292:
the three new fixtures had no parent, so the original init predicate correctly
kept their accepted SIGKILL receipts ineffective. That failed run is retained.
The corrected fixtures publish the original parent/child links with a real
`UnstartedParent`, assert non-init identity and raw queue receipt, and keep all
original fatal eligibility and accounting assertions. Fresh queues are also
checked with a real parent so init immunity cannot hide accidental inheritance.
A separate parentless process proves that accepted thread/process receipts
remain ineffective for init. No production signal or immunity rule is changed
to accommodate a test fixture.

The full OSTD gate retains 223 tests and adds
`fatal_pre_entry_returns_kernel_event_before_unmapped_user_code` (224 total).
It calls the real `UserMode::execute` entry with an unmapped user context. A
fatal hook must return `KernelEvent` without invoking user preparation; the
ordinary hook must instead enter and report the expected user exception.

The sealed watchdog suite now has six complete boots: the original restore,
healthy, zero, stopped and recovered cases, plus `zerothread`. Zero uses process
SIGKILL; zerothread uses `tgkill`. Both must actually wait/reap the workload,
observe unchanged user heartbeats and read `cpu.max` as zero before and after
cleanup. Each boot checks the original PID 1 signal immunity. Required fatal
and reap records are ordered after the watchdog result; duplicates, missing
records, heartbeat growth, nonzero cap, timeout or any raw exit other than 33
fail the gate. The allocator's separate 20-test gate remains required.

Host parser tests and compilation are not native execution receipts. The fixed
source must be built with the source-matched original OSDK and run through both
full kernel suites and the complete six-boot watchdog gate before this repair
is reported as natively qualified.
