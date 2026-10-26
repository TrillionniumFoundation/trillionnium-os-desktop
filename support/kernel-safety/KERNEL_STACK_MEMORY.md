# POSIX task kernel-stack physical frames (M4)

This stage extends `hepta.page.*` with `kernel_stack`; it does not enable
standard Linux `memory.max`. It covers the actual physical kernel stack of a
new POSIX task when created by a current process. It does not account the
user-space stack twice, and does not substitute virtual-size/RLIMIT_AS limits
for physical allocation ownership.

## Creation and ownership

`PosixThreadBuilder::build` first calls OSTD `PreparedTaskStack::try_new`.
The callback in `controller/page_memory.rs` captures the creating process's
current cgroup once and reserves the full stack bytes against its leaf and
all ancestors using the existing checked, IRQ-safe page ledger. An ancestor
rejection refunds every earlier reservation. OSTD defaults to 128
physical pages (512 KiB); the ordinary kernel Makefile selects 64 pages
(256 KiB), as measured by the guest. `OSTD_TASK_STACK_SIZE_IN_PAGES` can select
another nonzero build-time size. Four additional virtual guard pages stay unmapped.

`FrameAllocOptions::alloc_segment_with` acquires the actual contiguous physical
segment. A split token is moved into each `KernelStackMeta`; the unused tail
of the owned whole-stack reservation refunds on error. Physical allocation
failure returns `NoMemory`. The callback and every split may allocate small
Box/Arc metadata on the existing global heap; that heap remains infallible and
outside this ledger. This is not protection from global heap exhaustion.

`KVirtArea::try_map_frames` returns a virtual-range or page-table allocation
failure instead of unwrapping it. A local area owns every already published
mapping; cursor guards drop before the area's destructor removes a partial
prefix and releases its virtual range. Unconsumed physical frames and the
published prefix retain their tokens until their actual final references
release. Shared kernel page-table nodes allocated for these mappings remain
outside this process ledger.

Only after successful preparation does `Arc::new_cyclic` build the thread and
consume `PreparedTaskStack` through `TaskOptions::build_with_stack`. No fallible
stack allocation is hidden inside the cyclic closure. The builder returns
`Result`; clone/fork and initial/trusted-role construction propagate ENOMEM.
A failed clone has not published the child PID/process/thread, and its owned
PID reservation is released. Prior fork user-page-table preparation may have
created an unpublished child table; its existing RAII cleanup still applies.

An existing stack's owner never changes on cgroup migration, setuid or exec.
The creating process's account pays a new child's stack, even if the child
migrates immediately. Kernel/system tasks using `TaskOptions::build` keep their
existing uncharged path; processless initial tasks also have no inferred owner.
Delegated worker ownership requires a separate explicit design.

The later [Binder file-transfer stage](../android/BINDER_BYTES.md) adds the
specific `ThreadOptions::try_build` path: it prepares a stack using this same
source-account charger before publishing each retained file cleanup task.
Those frames keep their original charge through final Task/RCU destruction.
Its 256 admitted-file permits bound logical cleanup ownership, not all physical
stack tails: a permit can be refunded before the exited Task's final stack
reference is reclaimed. Other `TaskOptions::build` users remain uncharged;
this exception does not establish general worker delegation or a global reserve.

## Release and recovery limits

Each real physical frame carries its original charge independently. Dropping
Task or PreparedTaskStack removes stack mappings but is not itself the refund
point: CPU/task references and OSTD RCU may retain the physical frames. A held
reference to one frame keeps exactly that page charged after the rest of its
stack is destroyed. There is no immediate-unmap, task-exit or wall-clock refund
promise. Existing CPU-switch stack/TLB rules remain in force.

A sibling outside an exhausted subtree can still admit a task if its own and
common ancestor budgets have headroom and the global allocators have physical
capacity. This is not a physically protected reserve. Kernel heap and object
metadata, system stacks, shared kernel tables, DMA, direct filesystem metadata
and processless/delegated work remain excluded. Reclaim/OOM policy and protected
recovery capacity are still required for a complete controller.

## Verification

The OSTD test allocates a real prepared stack, denies one-page-short admission,
and holds an extra reference to one actual mapped stack Frame. Real scheduler
context switches advance RCU; only the held page stays charged after stack
removal, and releasing that last reference refunds it. A second native test
requests more than the entire kernel virtual range and requires a returned
NoMemory plus release of the supplied actual Frame. These tests do not force
global physical allocator exhaustion or inject a kernel page-table allocator
failure; their Result/RAII paths are reviewed, not claimed runtime fault proof.

The ordinary 2-/4-CPU page-memory guest uses prefaulted distinct user stacks and
CLONE_VM to isolate new kernel-stack allocation from user page-table growth.
It measures the real live stack charge, checks leaf and ancestor rejection at
one page below the required bytes, verifies denying-level events, PID cleanup
and complete leaf rollback, demonstrates sibling task creation while the
workload remains capped, and holds four real stack segments at an exact ceiling
before denying a fifth. The M3 pure-table/root/partial-fork negative limits stay
unchanged. Refund checks wait for observed final release within the test run;
passing tests do not establish a universal time bound.

Run full `ostd` and `aster-core` native suites, `tests/kernel/page-memory/run.py`
with 2 and 4 CPUs, preceding `tests/kernel/safety/run.py` on the same ordinary
ELF, and `tests/kernel/dma-domain/run.py` because legacy DMA also uses KVirtArea.
Use this worktree's pinned source-built OSDK and keep source unchanged across
the serialized build/guest batch. Each result must retain source/artifact hashes
and raw guest logs; an integration build must repeat the combined checks.

The M4 probe also creates a real CLONE_THREAD task in the same process,
requires an additional live PID charge and the same actual stack-frame count,
and waits for its final refund. Both leaf and ancestor negatives repeat with
CLONE_THREAD so the precharged thread-PID reservation's error path is exercised,
not only the new-process path. PID checks first enable the controller and
require an actual creator/live-child count; unavailable attributes cannot pass
as equal sentinel values. Group deletion retries only EBUSY while actual
scheduler switches settle the observer's migration CPU lease.
