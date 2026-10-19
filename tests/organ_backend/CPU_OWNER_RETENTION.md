# G1-b: retain the original CPU owner for each running segment

This slice follows `CPU_CONFIG_SETTLEMENT.md`. It changes original cgroup
bandwidth accounting and local lifecycle publication. It does not provide a
BOOTTIME usage snapshot, activate native grants, add an ioctl operation, or
establish SMP migration qualification. `CpuMax` remains the only budget and
bandwidth accounting object; the metadata in its existing lock remains the
only native configuration revision.

## Problem and ownership

The task's cgroup node can outlive a CPU controller replacement. Resolving
`node.controller().cpu` when a pending interval is finally charged therefore
does not identify the incarnation that owned the interval. Its leaf and
ancestor counters may be replaced even though the old management interface
has already been fenced.

`CpuChargeOwner` retains the actual `Arc<SubController<CpuController>>` and a
node charge lease. The retained sub-controller already owns an immutable
chain of ancestor Arcs. Charging uses that chain directly; it never follows
the cgroup node back to its current RCU controller slot. It introduces no
budget, usage counter, clock, authority, or alternative `NativeTarget`.

`CurrentRuntime` captures this reference at the beginning of a running
segment. At settlement it first charges the retained reference, then captures
the next live binding. Its existing accounted-through cursor partitions the
debits; its separate CFS/RT timestamp and full runtime delta remain intact.
An exited thread retains its original reference even after detachment or
reaping. A reference in `PosixThread` preserves that same incarnation if
kernel exit cleanup is preempted and resumes with a fresh runqueue runtime.
The off-CPU interval is not charged. No time cursor or accounting counter is
stored in the thread reference.

The existing membership backup update discards a saved reference to a
different cgroup. It preserves a reference already updated to the new group
at the publication checkpoint. Clearing that reference unconditionally
would reopen a gap between publication and an immediately following exit.

## Publication time and lock order

The existing membership writer serializes controller replacement and live
process migration. Each original CPU RCU publication now has two local
bandwidth checkpoints, at `b` and `e`. Local IRQs remain disabled between
them. If the previous cursor was `a`, the old owner receives `[a, b)` and
`[b, e)`; the next owner begins at `e`. The publication's kernel execution
time belongs to the old owner. A zero-length publication still changes the
next reference without creating usage.

The two intervals join exactly, and each cursor advances only when time
advances. The split does not advance the CFS/RT runtime checkpoint. The
post-publication checkpoint can still charge a fenced old controller:
management closure does not cancel already incurred CPU time.

| Stage | Locks and operations |
| --- | --- |
| Preparation | Existing membership writer and required node locks; allocate new controller, copy persistent statistics, or update the process map before the local IRQ scope |
| First checkpoint | Local IRQ guard, then local runqueue; original leaf/ancestor bandwidth locks, one at a time; release runqueue before publication |
| Publication | Local IRQ guard; close old controller under its bandwidth lock, then release it; existing RCU pointer update and deferred-reclamation registration; no runqueue lock |
| Second checkpoint | Local runqueue, then original bandwidth locks; debit the old suffix; capture the new owner and save the thread reference under its small IRQ-disabling spinlock |
| Remaining membership work | Release local IRQ scope before acquiring the process task-list mutex or changing its backup leases; existing membership writer remains held |

The publication callback must not acquire a sleeping lock, copy user memory,
wait, or recursively publish another CPU binding. All production call sites
limit it to the existing RCU update and, for replacement, the old controller's
short management close.

The pinned OSTD/OSDK implementation was inspected for the callback's actual
allocation and destruction behavior:

- `ostd/src/sync/rcu/mod.rs`: `RcuInner::update` swaps the pointer and registers
  `delay_drop`; it does not wait for a grace period.
- `ostd/src/sync/rcu/monitor.rs`: `after_grace_period` takes an IRQ-disabling
  spinlock and appends the callback. Destructors execute later, when a real
  scheduler quiescent state completes the grace period.
- `osdk/deps/heap-allocator/src/allocator.rs`: callback/queue allocations use
  the existing CPU-local slab cache and IRQ-disabling global pool lock.
  Larger allocations use `HeapSlot::alloc_large` and the original frame
  allocator.
- `osdk/deps/frame-allocator/src/{lib.rs,pools/mod.rs}`: that allocator uses
  IRQ guards, CPU-local pools and a global spinlock. There is no sleeping
  reclaim or allocation wait path.

No OSTD primitive, allocator, unsafe boundary, pin, or build gate is changed.
The local IRQ scope cannot rendezvous with a task already running on another
CPU. Such a task refreshes its reference at its next checkpoint. The exact
publication-time contract here is limited to N0's single CPU.

## Regression coverage and required evidence

`owner_retention_regressions.rs` adds six kernel tests against actual cgroups,
Process/Task objects and the production runtime, with controlled TSC values:

1. A leaf replacement at the two checkpoints retains all 19 old cycles;
   the next 28 cycles reach only the new leaf. The common ancestors receive
   47 cycles once, and the old controller still rejects configuration.
2. Replacing both leaf and parent retains the old ancestor chain. Old and
   new parent counters receive 19 and 28 cycles respectively.
3. Live migration from A to B and then root preserves A's 19 cycles, B's
   22 cycles, the shared parent's 41 cycles and root's 53 cycles. A same-node
   migration does not replay usage; CFS still receives its full delta.
4. An exited task is detached, its leaf/parent replaced, its runtime dropped,
   and its Process reaped. A fresh runtime retains the original incarnation;
   six off-CPU cycles are excluded and both old owners retain 35 cycles.
5. A zero-length replacement charges nothing; subsequent settlement charges
   the new owner once, including repeated identical timestamp observations.
6. A direct owner reference and its clone each keep the actual node busy;
   only the last drop permits the original deletion/management-close path.

These tests do not inject the fixture's POSIX task into OSTD's FIFO test
scheduler. The controller and membership transitions themselves are real;
the controlled runtime timestamps make sub-tick ownership errors observable.
The ordinary CPU configuration guests must also run on the same candidate
ELF, exercising the class scheduler and actual self-migration into a capped
cgroup. Existing timing thresholds remain unchanged.

A targeted negative control, `cpu_owner_current_slot_negative.patch`, changes
only `CpuChargeOwner::charge` to resolve
the retained node's **current** RCU controller, leaving the real controllers,
runtime, tests and gates intact. It must fail the publication, ancestor-chain
and exited/resumed tests. Restore the production code and run the full core
gate; the expected denominator is the preceding 183 tests plus these six.
Preserve both exact source identities, kernel ELFs, raw QEMU identity and exit
status, serial output, gate results and the negative-control patch. A build
failure or timeout is not a successful negative control.

Use the original entry point in separate, identified source checkouts (with
the pinned OSDK, locks, firmware, compiler and QEMU already prepared):

```sh
python3 -I -B support/build/ktest/run.py --crate aster-core --skip-osdk-install --output /absolute/evidence/owner-negative
python3 -I -B support/build/ktest/run.py --skip-osdk-install --output /absolute/evidence/owner-green
```

The maintained A06 workflow runs its ordinary full green gate first, then
`run_cpu_owner_negative.py --green-evidence ... --worktree ... --output ...`.
That entry creates a separate local Git commit containing only the declared
`CpuChargeOwner::charge` mutation. It compares the actual full core test-name
set against the same candidate's green serial stream, requires exactly the
three failures below and raw QEMU 65, and checks both source snapshots,
compiler/OSDK/VDSO/QEMU/firmware identities and the fixed generated Cargo lock.
It retains the original gate's nonzero status, logs and ELF; recognizing the
negative control never turns that original result into a product pass. The
ordinary product and previous compatibility guests then run in the untouched
candidate checkout.

The first command is deliberately nonzero after applying the control patch
in its own checkout. Record the actual dirty source/diff or a distinct local
negative-control commit; never label it as the untouched candidate HEAD.
Do not remove filters, relax warnings, or modify the gate. The expected raw
QEMU result is exit 65, not a timeout, with 186 passed and exactly these three
failed names under
`aster_core::fs::fs_impls::cgroupfs::controller::cpu::owner_retention_regressions`:

- `controller_publication_charges_the_entire_prefix_to_the_old_incarnation`
- `retained_leaf_debits_its_original_ancestor_chain_after_parent_replacement`
- `exited_task_resumes_its_retained_incarnation_after_replacement_and_reap`

The formal candidate checkout must then run the second command without the
control patch. Expect the original full OSTD suite and 189 core tests, with
QEMU exit 33 for each and zero filtered core tests. Preserve real existing
OSTD soft skips instead of counting them as hard passes. These denominators
refer to this slice's base; if another change adds tests before integration,
report the actual combined denominator and retain the same failed-name set
for the negative control.

The first CI attempt exposed an `ArcRef` clone type error; the next candidate
fixed it and passed the original full core suite (189 tests) and OSTD gate.
That second attempt stopped before creating the negative checkout because
the added serial parser incorrectly required each test result on one line.
The original runner prints a name, invokes the test (which may emit device
or expected-panic logs), then prints its outcome. The parser now binds one
terminal outcome to each unique test segment and checks the full denominator.
Its six host regressions reject missing, repeated, ambiguous, filtered and
fatal evidence. It was also checked against the actual 189-pass CI stream
and the preserved earlier 179-pass/4-fail configuration-control stream.
These parser checks are not a new guest run. The original core gate and
the three-failure owner control must still complete on the updated candidate.

At source preparation, the new file and all modified Rust files passed the
fixed nightly rustfmt parser, and `git diff --check` passed. This document does
not claim a new kernel result: exact candidate RED/GREEN and ordinary guest
receipts must be produced by the subsequent validation run. The earlier
183-test result and earlier ordinary guest receipts do not qualify this new
source tree. BOOTTIME origin/remainders, cumulative/window coherent native
usage, trusted authorization and the full G1-b boundary remain open.
