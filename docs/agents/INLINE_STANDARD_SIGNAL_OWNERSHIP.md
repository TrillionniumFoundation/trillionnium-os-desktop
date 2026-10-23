# Inline standard fault and fatal signal ownership

## Scope and original owners

`thread/exception.rs` previously boxed every `FaultSignal` before enqueueing it.
The fixed `KernelSignal(SIGKILL)` and `UserSignal(SIGKILL)` producers likewise
allocated a box before the original queue could record receipt. This slice
removes those particular allocations. It does not introduce an allocation
reserve or promise that all signal delivery can survive global OOM.

[OwnedSignal](../../kernel/asterinas/kernel/core/src/process/signal/signals/owned.rs)
is a private, closed owner: a standard `FaultSignal`, a kernel SIGKILL, a user
SIGKILL, or the original dynamic box. Its concrete-signal constructor checks
both type and signal number. A nonstandard fault-shaped value remains dynamic;
real-time signals cannot enter an inline variant. Dynamic callers keep their
original box rather than reconstructing a signal from partial information.
`RawSignal`, including the existing pidfd custom-siginfo path, stays dynamic.

The original 31 standard-signal slots now hold this owner directly. Queue
creation still allocates those slots, with a larger bounded element size.
Real-time queues retain their original `VecDeque<Box<dyn Signal>>` representation
and FIFO. The original queue mutex, coalescing of repeated standard signals,
first-arrival siginfo, mask/priority, count, observer notification after unlocking,
and irreversible SIGKILL receipt ordering are unchanged. No second pending-bit
or scheduler-only receipt is introduced.

## Transfer, permissions and lifetime

[DequeuedSignal](../../kernel/asterinas/kernel/core/src/process/signal/pending.rs)
retains both the owner and original process/thread queue origin. Ptrace stop,
wait, continuation and requeue transfer that value. Signal handler delivery,
`rt_sigtimedwait` and `signalfd` consume or borrow the same value; none re-boxes an
inline signal. A tracer's explicit dynamic replacement retains the old dynamic
contract and original origin, and drops the replaced owner once.

Process and PosixThread keep their boxed enqueue interfaces. Both boxed and
prepared-owner entry points reach the same original queue and wake sequence.
Neither enqueue interface grants user permission. The existing `kill`/`tgkill`
boxed interfaces wrap the prepared-owner implementation, whose original target,
credential, namespace capability and SIGCONT checks remain in place. Process
broadcasts use the same `kill_process` checks for each target. No special fatal
permission bypass was added. Exec teardown, sibling exit, ptrace EXITKILL and
PTRACE_KILL prepare the existing fixed SIGKILL information inline.

This changes no signal ABI or information fields. In particular, the existing
signalfd conversion's limited set of populated fields is preserved, not claimed
as complete Linux signalfd compatibility. Pending RT growth, queue initialization,
observer/waker work, arbitrary RawSignal producers, ptrace notification, VMAR
metadata and exit-chain allocations remain separate gaps. The kernel remains
safe Rust; no unsafe block or global failure-injection flag is added.

## Developer regression contract

Five real core regressions are added to the original unfiltered inventory:

- `inline_fault_preserves_first_info_mask_and_original_priority`: actual original
  queues preserve the first fault code/address, mask and fatal priority.
- `dynamic_realtime_keeps_original_fifo_and_drops_each_owner_once`: dynamic RT
  FIFO and duplicate-standard owner destruction; an RT-numbered FaultSignal is
  kept dynamic rather than reaching an impossible inline RT branch.
- `inline_user_kill_keeps_siginfo_and_irreversible_original_receipt`: exact user
  siginfo bytes, SI_USER/SI_TKILL, receipt surviving dequeue/drop, fresh queue false.
- `inline_signal_wakes_original_thread_and_process_without_retaining_them`: real
  POSIX constructors/parent links and original Waiter/Waker objects; thread and
  process delivery wake, sibling fatal observation, final Process Weak expiry.
- Ptrace `ptrace_stop_requeue_keeps_inline_owner_and_dynamic_injection_origin`:
  original StopDeliverySignal pending/wait/requeue and dynamic injection states.

Core minimum is 352 with 113 required names; prior 347 tests and every earlier
required name remain. OSTD 230, allocator 20 and MLSDisk 15 are unchanged. Run
`support/build/verify-source.py`, the complete `support/build/tests` suite and
original `support/build/ktest/run.py` against a clean fully materialized source.
Native completion still requires the original raw QEMU status 33, complete
unfiltered inventories, original 512 MiB/one CPU profile and deadlines.

The [bounded syscall probe](../../tests/workloads/linux/inline_signal/README.md)
uses actual SA_SIGINFO faults, kill/tgkill/group/pidfd wait/reap, denied cross-UID
signals, RT FIFO, signalfd reads and ptrace fault inspection/continuation. Linux
reference results are only a behavioral reference. Native qualification must
bind a newly built ordinary ELF and all source snapshots to this exact source.
Native qualification of this new signal slice is pending.
