# Physical stream and pipe buffers (M5)

This stage adds `ipc` to `hepta.page.stat`. It closes one real allocation path
outside the prior page and POSIX-stack budget: AF_UNIX stream/seqpacket rings
and anonymous/named pipe rings allocated by a current process. It does not
implement Linux `memory.max`, kernel-object accounting or a protected recovery
pool. `memory.max` and writes to the unenforced `cpu.weight` remain refused.

## Allocation and lifetime

The shared ring-buffer crate already used physical OSTD segments; these bytes
were not heap byte vectors. Its original constructor unwrapped allocation
failure. It now offers checked `storage_bytes`, fallible `try_new` and an owned
`USegment` constructor. The latter preserves metadata on every physical frame.
Existing cloned segment handles may alias those bytes, as with the existing
`segment()` accessor; callers coordinate byte access with their intended SPSC
protocol. No exclusive physical ownership is inferred from a handle.

The kernel's `new_ipc_ring_buffer` reserves the page-rounded physical size
through the original page ledger before allocating a real contiguous segment.
It captures one current membership for that ring and splits the reservation
into a `PageCharge` on every actual frame. Ancestor rejection rolls back earlier
accounts. Physical allocation failure drops the whole unused reservation.
Segment geometry/overflow is checked before allocation. The two rings of a
connection are independent allocation points: concurrent migration may give
them different original owners. Migration after allocation never transfers a
charge, and using a peer's already allocated ring does not charge it again.

Buffer sizes remain 64 KiB per stream direction and 64 KiB per pipe in the
ordinary product. A stream/seqpacket connection therefore retains 128 KiB.
Tiny native pipe fixtures still allocate their actual page-rounded physical
storage. No buffer size or throughput limit was reduced to make a test pass.
The private/COW-only `hepta.anon.*` counter is not charged for IPC frames.

Producer and consumer handles share the ring object. Both sides of a socket
or pipe can retain the physical segment; closing only one end must not refund
it. Forked or transferred descriptors also retain these original objects. Frame
metadata refunds only on the real final reference, including an extra kernel
segment/frame handle after all endpoint objects are gone. A deleted cgroup's
original account remains retained by its frame tokens.

## Failure and publication

`Connected::prepare_buffers` finishes both ring allocations before constructing
the connection. Failure of the second allocation drops the first ring. A
connecting socket returns its original `Init` state on admission failure, and
the listener publishes no pending endpoint. The same socket may retry later.
`socketpair` propagates ENOMEM before installing user descriptors. Later output
copy or FD-reservation errors drop both unpublished endpoints and their buffers.

`PipeInner` only publishes its weak `PipeObj` reference after successful ring
creation. Both anonymous pipe creation and the first named-FIFO open propagate
ENOMEM. A failed first open does not publish a pipe object or increment the
reader/writer counters. Existing active FIFO handles reuse their original
physical backing; later users do not infer a new account.

Lock order remains the existing socket state/backlog or pipe mutex, then one
page-account lock at a time. No page-account lock spans physical allocation,
I/O or a wait. Buffer preparation may occur under an existing backlog spinlock;
it performs only budget reservation, frame allocation and local construction,
with no user copy or sleeping operation. Heap allocations for Arc/queue/object
metadata remain outside this frame ledger and may still be infallible.

## Scope and unfinished isolation

The legacy infallible ring constructor remains for other existing callers.
TTY/PTY/event-device rings, datagram payload vectors, auxiliary FD queues and
other kernel heap/slab objects are not covered here. System/processless callers
still have no inferred workload account. Filesystem metadata, DMA, shared kernel
tables, delegated workers and global allocation/reclaim/OOM policy remain open.
An outside recovery group's counter is not a physical or metadata reserve.

[M6](DATAGRAM_MEMORY.md) separately changes actual Unix datagram payloads to
fallible, charged physical segments. It awaits its own pinned-toolchain and
ordinary guest qualification; no historical M5 result is relabelled as M6.

The new fallible constructors make these covered failures ordinary syscall
errors; they do not guarantee that every other allocation required by that
syscall can survive global OOM. A complete controller must address all those
paths before enabling standard `memory.max` or claiming bounded recovery.

## Development and verification

Use the pinned nightly, a source-built OSDK from this exact checkout and
separate external Cargo targets. No dependency manifests or lockfiles change;
the existing source-derived manifest verifier remains enabled. Do not share an
OSDK embedding another worktree. Keep the source fixed during a serialized
ordinary/native build batch.

Run complete `aster-core`/OSTD native suites and the actual IPC guest described
in `tests/kernel/ipc-memory/README.md` on 2 and 4 CPUs. Also run the existing
page-memory, socket/FD, Binder, stop/continuation and safety guests because the
ring crate and pipe constructors are shared. Bind raw logs, source snapshots
and kernel/probe/firmware hashes to the final committed source; component tests
do not qualify a different integration commit.

Native cases use actual physical segments and ring endpoints. They retain an
extra page handle after both endpoints drop, check original leaf/ancestor
classification and final refund, reject the second buffer's reservation, and
release a supplied segment when its geometry is wrong. The fixed 512 MiB
native guest also refuses a single 1 TiB physical-segment request and refunds
its whole reservation. This does not exhaust global memory or claim a universal
OOM/recovery bound.

The guest checks real stream/seqpacket/pipe bytes, exact physical deltas,
one-end retention, migration, inherited descriptors, exact leaf/ancestor
ceilings, second-ring rollback, FD/output publication failures, named-FIFO retry
and a real listener whose backlog stays empty after failed connect. Its
inheritance check uses an eventfd barrier, not a sleep to assume ordering.
Unavailable controls, setup failures and unexpected errors are failures.

## CPU weight dependency

The current fair runqueue is a per-CPU heap of tasks keyed only by each task's
virtual runtime and nice weight. It has no cgroup scheduling entity. Multiplying
each thread's nice weight by `cpu.weight` would let a group buy more aggregate
share by creating threads; it would not implement the requested controller.

A real implementation needs stable per-CPU group entities with child queues,
hierarchical selection and runtime charging through every ancestor. Thread nice
weights apply within a leaf; sibling group weights apply between groups.
Migration and weight updates must settle the old running interval and preserve
virtual-time debt before requeueing, with the original CPU-account owner and
quota checks retained. Group deletion cannot destroy an entity still referenced
by a runnable task or CPU interval. SMP placement and balancing must preserve
work conservation and eligible affinity without turning task count into weight.

Required evidence includes equal-weight one-thread versus many-thread groups,
unequal/nested group shares, concurrent weight changes and migration, quota
interaction, blocked/waking groups, affinity and 1-/2-/4-CPU actual workloads.
That scheduler change is broader than this concrete physical allocation hole.
Until those entities and checks exist, `cpu.weight` must keep rejecting writes.
