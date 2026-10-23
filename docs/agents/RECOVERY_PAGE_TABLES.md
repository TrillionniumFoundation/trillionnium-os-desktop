# Explicit recovery page-table allocation

This slice adds fallible physical page-table allocation to the original OSTD
owners. It does not establish a complete recovery service. In particular,
`global_recovery_guarantee=false` remains in force: no recovery VMAR, stack,
heap, IPC buffer, handle slot or durable request budget is installed here.

## Authority and compatibility

`VmSpace::try_new_from(&PhysicalReserve)` allocates its root from the explicitly
supplied partition. `VmSpace::recovery_cursor(..., &PhysicalReserve)` borrows
authority for subsequent mapping operations. No token is stored in `VmSpace`,
the page table, its frames or mapped user data. A root and later branches may
use different explicitly supplied tokens; destruction returns each physical
page to its original allocator partition.

Ordinary `VmSpace::new`, cursors, mapping, copying and allocation retain their
original interfaces and behavior, including panic contracts. They cannot
implicitly acquire reserve authority from a root or shared node. The ordinary
allocator remains the default. Without allocator reserve support, explicit
reserve creation fails with `NoMemory`; there is no automatic fallback.

The new cursor exposes query, jump and tracked user-frame mapping. It does not
expose I/O mapping, huge-page splitting, protection, removal, subtree transfer
or an escape to the underlying infallible cursor. It borrows a token only for
its own lifetime. Closing that token prevents new allocation. Mapping another
user frame into an already prepared leaf requires no further page-table page
and remains valid; this is not permission to allocate after close.

## Allocation and rollback

Cursor construction locks through the original root/range protocol, so it
does not allocate intermediate page-table nodes. Overlapping cursors retain
the original serialization contract. Existing disjoint branches may still be
accessed concurrently; a held root can delay creation of disjoint branches.

Mapping first traverses the already locked existing path, then acquires every
missing page-table page into a fixed-size stack array bounded by the original
page-table depth. No PTE is published until all acquisitions succeed. On
`NoMemory`, ordinary `Frame` destruction refunds the unpublished nodes, the
original input `UFrame` is returned, and the cursor address and all PTEs remain
unchanged. Publication uses the existing node metadata locks and PTE owner.
No new unsafe primitive is introduced; the added unsafe calls stay inside
OSTD and reuse the original lock and mapping contracts.

Each published node owns its child frames through the original metadata.
VM aliases and active page-table references retain those owners normally.
This change neither alters final-reference destruction nor bypasses TLB/RCU
rules. The new API does not remove or overwrite live mappings.

The new root constructor obtains CPU tracking storage before allocating its
root. Up to 128 CPU IDs fit in the original inline representation. Larger
sets use fallible ordinary heap allocation; that heap capacity is not covered
by the physical reserve. This slice does not qualify execution under global
heap exhaustion or guarantee a recovery deadline.

## Required validation

The full default OSTD suite retains all 224 previous tests and adds five real
allocator/page-table regressions, for 229 total. The seven required names
include the previous busy-owner and fatal-entry regressions. All must execute
once, without filtering or soft-skipping. Core remains 295 and the independent
frame-allocator suite remains 20; neither is replaced by these tests.

The new tests require:

- Explicit root charging, exhausted/closed admission rejection, and ordinary
  root allocation outside the reserved extent.
- Failure at every missing-page depth, repeated attempts, unchanged PTEs and
  cursor address, the same returned input frame, and exact immediate refund.
- Separate root, branch and data partitions; real VM aliases retaining all
  owners; original partition refunds only after their final references drop.
- Closed-token mapping of a prepared leaf, rejected new growth, and ordinary
  cursor growth without consuming or inheriting reserve authority.
- Conflict panics preserving the original mapping, correct lock release on
  unwind, invalid ranges and failed jumps with unchanged allocation state.

Host compilation, Clippy and evidence-parser tests do not execute these kernel
tests. Native qualification requires a source-matched OSDK build and the full
unfiltered default QEMU run with raw exit 33, complete denominator and original
retained evidence. No native pass is asserted by this implementation document.
