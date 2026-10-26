# Kernel safety integration on the Desktop #267 baseline

This note describes the local integration based on Desktop #267 (`bee137ed`),
with selected regression inputs and an idle-RCU fix from #268 (`ca0b5592`). It is
an implementation/scope record, not a passing guest receipt or production claim.
Paths below are relative to `kernel/asterinas/` unless stated otherwise.

## Preserve the existing authority implementation

The #267 baseline already contains the following corrections. Importing the
whole #268 kernel would remove later resource-owner, watchdog, successor and
trusted-launcher work. This integration retains those implementations.

- `kernel/core/src/security/lsm/modules/capability.rs` checks that the caller's
  selected capability set contains the target's permitted set, including for
  same-ID callers. FSCREDS selects effective capabilities; REALCREDS selects
  permitted capabilities. Existing SYS_PTRACE exceptions and stacked LSM policy
  still apply. The owned guest case establishes a narrow same-ID denial and
  subsequent allowance; it says nothing about arbitrary root-process access.
- `ProcessVm` owns actual dumpability. Fork copies the image policy; threads and
  separate CLONE_VM processes share it. Credential edits and sensitive target
  capture use the existing VMAR/image-policy transaction. Effective/filesystem
  ID changes and permitted-capability gains reset dumpability; failed/no-op/query
  changes do not. Exec owns a new image policy; failed exec retains the old one.
- Sensitive proc access and ptrace peek/poke recheck current policy. Old proc
  descriptors retain their original image rather than silently following exec.
  The lifecycle and TRACEME probes exercise both denials and allowed transitions
  with owned, same-ID, unprivileged children.
- `kernel/core/src/net/socket/unix/` captures immutable peer/message identity and
  supplementary groups. Mutation replaces the credential's group owner, leaving
  earlier socket snapshots unchanged. The guest checks old and newly created
  socket pairs against actual UID/GID/group changes.

The tests cover these initial-user-namespace paths. They do not qualify every
ptrace request, user namespaces, Linux LSM compatibility or core-dump production.

## Selected physical-frame accounting, with one owner

The retained implementation is `kernel/core/src/vm/user_memory.rs` and
`vm/user_memory/hierarchy.rs`, exposed by
`kernel/core/src/fs/fs_impls/cgroupfs/controller/memory.rs`. It exposes
`memory.current`, `memory.events` and `memory.max` on active non-root cgroups.
The implementation deliberately accounts selected user-data and IPC physical
frames; it is not a complete Linux memcg, total RSS or all-kernel-memory account.

Charge identity belongs to frame metadata. Shared references retain one charge;
COW admits a new frame; the final reference refunds the original family and
ancestor domains. Limit writes and complete hierarchical admission use the same
transaction. Limits below current usage fail with EBUSY; valid byte limits round
up to pages. There is no reclaim or OOM-killer algorithm in this controller.
Migration only changes future allocation binding, so an administrator must place
work in its budgeted domain before execution and control migration/delegation.

Process exit does not by itself imply a zero account. In particular,
`kernel/core/src/process/process_vm/init_stack/mod.rs` creates a VMO-backed initial
stack, and `kernel/core/src/vm/vmar/vm_mapping.rs::MappedVmo::dup` retains the same
VMO across fork. A private write to an uncommitted stack page first commits a
zero base frame in that VMO, then creates a private COW frame. Both admissions
use the initiating owner. The private copy can be refunded at worker exit while
the base frame remains live
through the observer's VMO. Refunding that base early would undercount live
physical memory; its charge ends only after the last physical reference and any
deferred destruction have completed. `memory.current` is consequently not the
RSS of just the currently listed processes.

The frame probe materializes 128 KiB of the observer's initial stack before
forking the measured worker. This covers the worker's existing 64 KiB stack
warmup and its deeper call frame. The worker still exercises real private COW,
anonymous and file mappings, pressure denial and concurrent allocations. The
observer remains outside WORK, and the original zero-refund assertions, budgets
and bounded waits are unchanged. A lifetime diagnosis must also observe the
original charge falling to zero after the last VMO holder exits; prewarming
alone is not evidence that a retained reference was correct or that a release
qualification passed.

The existing owner covers more allocation paths than #268's separate
`hepta.anon.*` prototype, including shared/page-cache paths and selected IPC
storage. Page tables, slab/kernel heap and stacks, ancillary/datagram buffers and
device MMIO remain outside this account. The integration does not introduce a
second anonymous-frame owner or a compatibility alias that could imply broader
coverage. `frame_budget_probe.c` tests only the declared private-fault/COW paths;
other retained suites provide their own distinct evidence.

The memory probe keeps its observer outside the constrained workload subtree. It
requires the pressure child to die with SIGSEGV, a new max event, eventual refund
of the reaped subtree, and a successful allocation in the separate recovery
sibling. This establishes bounded selected-frame headroom, not global recovery
under physical OOM. The existing OSTD `PhysicalReserve` API and trusted native
recovery/watchdog mechanisms remain intact and have separate regression suites;
this ordinary cgroup probe does not establish their authorization or end-to-end
recovery semantics.

The CPU weight boundary is also retained: valid writes, including the neutral
value 100, return EOPNOTSUPP; invalid input returns EINVAL; reads return 100. The
scheduler must not acknowledge a group-weight policy it does not implement. This
has its own native tests in `controller/cpu/config_regressions.rs`; the guest
checks values 1, 100 and 10000 without changing `cpu.max`.

## Idle CPUs must advance deferred destruction

OSTD `ostd/src/task/preempt/mod.rs::halt_cpu` now reports an RCU quiescent state
before disabling interrupts and entering halt. Previously only task switches
reported one. A CPU that remains on its idle task can otherwise hold up deferred
frame destruction and budget refunds on every CPU.

The call checks the raw preemption-guard count and IRQ-enabled state as well as
`might_sleep`: bootstrap callers are exempt from the latter assertion. Both
conditions must exclude a live RCU read-side guard. The existing RCU monitor
releases its lock before running callbacks. The change adds no unsafe code to
the kernel crates and uses the existing OSTD boundary.

Progress still requires each CPU to wake and return through a quiescent point.
A stalled CPU can delay refunds indefinitely. The SMP guest therefore uses a
bounded series of scheduling opportunities and records observations; it does not
promise a wall-clock refund guarantee. The private-file beyond-EOF case checks
Asterinas's existing private-VMO tail allocation path, not Linux SIGBUS behavior.

## Verification and retained negative controls

Run complete OSTD and aster-core ktests with the pinned toolchain, source-built
OSDK and pinned vDSO before qualification:

```sh
VDSO_LIBRARY_DIR=/absolute/path/to/pinned/linux_vdso \
  python3 support/build/ktest/run.py --crate ostd --crate aster-core \
  --output /absolute/new/evidence/ktest
```

Run the five syscall probes at 2 and 4 CPUs against one exact-source ordinary
QueryAbi product using [the guest instructions](../../tests/kernel/safety/README.md).
The runner requires exact successful probe records and retains raw evidence.
A missing prerequisite, compile error, probe exit 77, timeout or changed artifact
fails qualification. Host-side Python checks and static C compilation are
separate evidence and must not be reported as guest execution.

The #267 CPU-clock/handoff and permission-SMP runners and their frozen defect
patches are preserved without lowering suite counts or broadening acceptable
failure signatures. In the reported #268 A06 run 40195053488, job 121173981473,
permission validation stopped at the Python fixture check because its temporary
source tree lacked a root README. That step never ran the permission guest.
The #267 fixture and exact-invocation checks already correct this; the local
`test_permission_attr_smp.py` run has 16 tests. This harness failure is not evidence
of a #267 kernel defect and is not grounds to weaken any frozen negative control.

This integration does not qualify full resource isolation, physical hardware,
GPU/USB/mobile support or production deployment. Those need separate complete
contracts and actual execution evidence.
