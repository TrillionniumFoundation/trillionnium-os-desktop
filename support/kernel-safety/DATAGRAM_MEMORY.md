# Physical Unix datagram payloads (M6)

The Organ resource-isolation audit found that Unix datagrams still used an
infallible `vec![0; len]` outside the physical-page ledger. This successor changes
the actual `MessageQueue::try_send`/`MessageReceiver::try_recv` path. It is source
work awaiting pinned-toolchain compilation and ordinary guest validation; no
new kernel execution is claimed here. The separate 6487/7673 host combination
does not acquire this successor's changes or qualifications.

Each queued payload now owns a real `USegment` obtained from the existing
`alloc_ipc_segment` allocator. `hepta.page.stat` classifies these frames as `ipc`.
The charge belongs to the sending process's cgroup captured at allocation,
including all ancestors. Its size is `ceil(max(payload_length, 1) / PAGE_SIZE)`
pages. Even a zero-byte datagram retains one actual physical page, so empty
messages cannot bypass a configured page ceiling. This deliberately introduces
page rounding for small messages; it is not a claim of unchanged allocation
cost or measured datagram performance.

The original 65536-byte message and receive-payload capacity remain unchanged.
Capacity continues to measure payload bytes, while the independent page ceiling
measures actual backing, including empty datagrams and page rounding. This is
not a Linux `memory.max` implementation and does not bound every queue object's
heap or ancillary metadata. The standard memory controller remains unsupported.

## Admission and publication

Lock order is the existing destination queue's sleeping mutex, followed by one
page-account lock at a time. No page-account lock spans allocation, user copy,
waiting or I/O. Physical allocation occurs only after all ancestor reservations
succeed. Each real frame embeds its charge token; an allocator error refunds
uninitialized reservation tails and any already constructed frames through the
existing allocator's RAII path.

The deque reserves its next metadata slot fallibly before taking auxiliary
ownership or publishing a packet. Metadata reservation failure returns ENOMEM.
This metadata remains heap memory outside the page ledger; a reservation can
leave reusable deque capacity even if a later payload allocation/copy fails.
The change does not claim all allocations for credentials, addresses, control
messages or socket objects are fallible or accounted.

After page admission, the sender copies exactly the original payload length.
A fault or an unexpected internal short copy drops the unpublished segment and
returns EFAULT without changing the queue's payload total or taking the caller's
auxiliary data. Only a complete copy permits credentials, source address and
message publication. The physical tail is never sent to the receiver: both
readers and writers are limited to the original message length. No zero-filled
heap staging buffer remains in this path.

## Lifetime and receive semantics

MSG_PEEK keeps the original payload and charge. Ordinary or truncated receive
consumes one entire datagram after a successful user copy; MSG_TRUNC still
reports the original packet length when requested. A user-copy fault leaves the
whole original datagram for retry. A zero-length receive of a zero-length packet
consumes exactly one packet. Existing shutdown and closed-queue errors remain.

Receiver migration, descriptor inheritance and sender exit never transfer or
refund queued frames. Dropping the actual receiver clears its queue even if a
peer still holds the queue Arc. A separately retained physical segment/frame
continues to own its original charge until the final physical reference drops.
The native queue tests cover actual segments and packet behavior; the ordinary
guest separately covers real current POSIX process/cgroup attribution.

## Development and required verification

Use the exact pinned nightly and a source-built OSDK from this checkout, with
external targets. Keep full source snapshots before and after. Run the complete
Core and OSTD native suites through the original ktest runner, and the new
[ordinary datagram guest](../../tests/kernel/datagram-memory/README.md) on 2 and
4 CPUs. The eight new native tests include real packet bytes, the physical tail,
zero messages, original capacity, truncation, failed source/destination copies,
closed receivers and a deliberately contract-violating short internal source.
That last fixture tests defensive initialization handling, not a real user fault.

The guest keeps the inherited 60-second static compiler, 120-second QEMU and
45-second probe budgets. It checks leaf and ancestor ENOMEM, the rejecting
account's event, exact real IPC deltas, rollback, zero-message exhaustion,
receiver migration, inherited receivers after sender exit, user-copy faults,
peek/truncation, receiver closure and the original 64-KiB capacity. Setup failures
are failures. It attaches no host storage or network and must never run on the
host. Preserve the prior uncharged-payload failure as a separate negative run;
do not label an older kernel or a synthetic queue as a passing successor.

The shared AF_UNIX and page-allocator paths also require the original IPC, safety
and socket/descriptor guest regressions. No actual suite totals are predicted
as passing results. Kernel heap/slab ownership, worker/DMA delegation, shared
kernel tables, protected physical/metadata recovery reserves and reclaim/OOM
policy remain required work before full memory isolation can be advertised.
