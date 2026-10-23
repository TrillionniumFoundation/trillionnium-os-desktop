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

The owner-only slice adds five tests to the prior 347; with the fault-reason
regression below, the combined minimum is 353 with 114 required names. Every
earlier required name remains. OSTD 230, allocator 20 and MLSDisk 15 are unchanged. Run
`support/build/verify-source.py`, the complete `support/build/tests` suite and
original `support/build/ktest/run.py` against a clean fully materialized source.
Native completion still requires the original raw QEMU status 33, complete
unfiltered inventories, original 512 MiB/one CPU profile and deadlines.

The [bounded syscall probe](../../tests/workloads/linux/inline_signal/README.md)
uses actual SA_SIGINFO faults, kill/tgkill/group/pidfd wait/reap, denied cross-UID
signals, RT FIFO, signalfd reads and ptrace fault inspection/continuation. Linux
reference results are only a behavioral reference. Native qualification must
bind a newly built ordinary ELF and all source snapshots to this exact source.
Native qualification is bound to the exact combined source below.

## Separate access-error classification correction

The new strict syscall probe on the retained pre-change `d5a21bb7` ordinary ELF
found a pre-existing classification error: a PROT_NONE VMA returned real VMAR
`EACCES`, but x86's absent PTE selected `SEGV_MAPERR`. The baseline observed
SIGSEGV 11, code 1 and the exact fault address; Linux returned `SEGV_ACCERR` 2.
Both baseline failures remain retained; the probe's code/address assertions
were not weakened.

A separate correction preserves the actual VMAR error through the common fault
handler. Only the typed `PermissionDenied` result of the original mapping
permission check selects the existing `FaultSignal(SIGSEGV, SEGV_ACCERR, address)`.
Original user-space/VMAR guards drop
before enqueue. Other errors retain their original architecture classification,
and the kernel-copy fault callback still returns its original unit error.
A sixth real core regression uses original VMA permission denial, absent mapping
and zero-page quota denial to check that boundary. The combined inventory is
353 core tests / 114 required names. This does not classify allocation failure
as an access violation or change the existing quota-failure signal policy.

The first combined native run `bdda4873` passed all five signal-owner tests but
failed the new unmapped-address negative (352/353 core, raw 65). It demonstrated
that the original VMAR also returns EACCES when no mapping exists. That failed
source and ELF remain frozen; its results do not qualify the final correction.

`PageFaultError::{Unmapped, PermissionDenied, Other}` now carries the original
Error from the same VMAR read-locked lookup and permission check. The legacy
`handle_page_fault` API unwraps the unchanged Error for all existing callers.
Only the original VmMapping permission check emits PermissionDenied; device,
VMO, page-table and quota errors emit Other. No errno, string or later lookup
is used to infer the reason. The same negative assertions remain, and the
syscall probe adds a tenth unmapped-address case requiring SEGV_MAPERR.

The next frozen source `ce94ea48` passed the permission and absent-mapping
assertions but failed in the same test's genuine quota-denial diagnostic:
standalone aster-core tests had not bootstrapped the console component.
It remains a failed 352/353 run (raw 65). The fixture now initializes the real
console table through the original `component_init` and `Once`, following the
existing time/device component test setup. Repeated or concurrent calls retain
the same table and existing devices. The helper exists only under `cfg(ktest)`;
production initialization, quota diagnostics and all assertions are unchanged.

## Separate queued-signal syscall gap

Frozen `1d2d20c4` passed core 353, OSTD 230, allocator 20, MLSDisk 15,
ordinary boot/QueryAbi 18 and the same-ELF SGID 30, Unix ownership 12 and
Groups/NoNewPrivs 12 checks. Its signal probe passed the first seven cases,
then `sigqueue` reached missing syscall 129 and returned ENOSYS. Raw QEMU 33
did not turn probe exit 1 into success. The complete source, ELF and failed
serial remain retained; neither ten-case completion nor whole-slice native
qualification is claimed for that source.

The new `rt_sigqueueinfo` handler follows [Linux v6.17 signal.c](https://github.com/torvalds/linux/blob/v6.17/kernel/signal.c)
and the [Linux syscall contract](https://man7.org/linux/man-pages/man2/rt_sigqueueinfo.2.html).
It copies siginfo first, including for signal zero, and takes the delivered
signal number from the syscall argument. Noncurrent-TID sends reject nonnegative
codes and SI_TKILL before target lookup, even for root. Zero/negative PIDs do not
mean a process group. The original PID table resolves a real Thread and retains
its Process while locked; a nonleader TID therefore reaches that process's
shared pending queue. Full signed signal validation follows lookup; negative,
65 and 256 cannot truncate into another signal. Zero performs only the original
permission check and never enqueues.

The original credential/capability/SIGCONT check and process enqueue are shared
with `kill_process`. Payload PID/UID remain data, never authorization. A single
held Thread/Process pair spans validation and dispatch; it is not re-looked-up
after potential PID reuse. RawSignal keeps its dynamic Box and the original RT
FIFO; this adds no reserve, shadow signal queue or pending receipt.

The original core 353 / 114 required inventory is unchanged. Four added syscall
cases make the strict probe fourteen, including an actual pthread nonleader
target, real dropped-UID sender, forged data fields, zero not publishing, and
negative errno ordering. Linux reference results are separate from native
qualification. `rt_tgsigqueueinfo`, compat ABI qualification, unknown siginfo
layout expansion/E2BIG parity, RT allocation failure and RLIMIT_SIGPENDING
accounting are not implemented or qualified by this small slice. Native
qualification of the combined queued-signal correction is bound to the exact
source below.

## Source-bound native qualification

Combined source `6c26e3aeefde05c120944e278299b4925612f3c8`, tree
`6c84a0663441dcbf9629fc2da8f857265baa5fe1`, passed the original complete core
353 / 114 required names, OSTD 230, allocator 20 and MLSDisk 15 suites. All four
raw QEMU exits were 33. OSTD retains the three original TCG VMX skips; the other
three suites have no skips. The source-matched ordinary kernel passed its 18
boot/QueryAbi checks and, on that same ELF, SGID 30, Unix ownership 12, proc
Groups/NoNewPrivs 12, memfd metadata/seals 4 and the fourteen strict signal
syscall cases. The latter include actual nonleader-TID delivery to shared
pending, payload-only PID/UID, a real cross-UID denial, and strict errno order.
Full tracked
source snapshots were unchanged. The original memory, deadlines, inventories
and negative checks were retained.

[The exact receipt](../../results/integration/2026-10-23-audit-closure/inline-signal-6c26.json)
binds all kernel/serial/source hashes and retains both rejected old-kernel
classification baselines. Linux reference success is recorded separately.
The missing-RT-syscall failure from `1d2d20c4` is retained separately; its
partial native probe is not retroactively a pass. The combined source also
uses the original zero-link inode constructor for detached memfd files and
preserves original seal and attribute checks.

These results do not qualify global memory pressure, all signal producers,
complete signalfd information fields or whole-kernel recovery.

An independent, unchanged Root handoff C binary also passed on the same
ordinary ELF under the original 512 MiB KVM profile: Root-created regular
memfd, zero links, mode 0400 and four seals; actual UID 60001 with no
capabilities and NoNewPrivs read the exact content, while write, truncate,
seal modification and ownership change were denied. The same binary had
rejected the old `d5a21bb7` kernel because it reported one link. Both receipts
and the Linux reference remain separate in the linked record. This qualifies
the component handoff, not a production loader or full Root service.
