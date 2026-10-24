# Ordinary VMAR page-fault allocation

## Ownership and error ordering

The ordinary `VmMapping` fault path previously constructed an allocating page-table
cursor before admitting its user frame. A rejected zero-page family quota could
therefore leave empty intermediate page tables, and missing page-table frames
used an infallible `expect` in `PageTableNode::alloc`.

The three VMAR fault cursor sites now use `VmSpace::cursor_mut_no_prealloc` or its
query counterpart. Under the original RCU and range-lock protocol, traversal
locks existing nodes and stops at the locked parent of the first absent branch.
It does not insert intermediate nodes. Existing branches still descend to the
same original leaf/range guard; the cursor is not a separate mapping owner.

For an absent user page, `prepare_page` or the VMO commit closure first performs
its original family/ancestor admission. `CursorMut::try_map` then prepares all
missing ordinary page-table frames into a depth-bounded stack array, sharing the
existing explicit-reserve transaction implementation. Each ordinary allocation
calls `FrameAllocOptions::alloc_frame_with` and propagates `NoMemory`. No reserve
token is borrowed, retained or inherited. On error the original input frame is
returned, all unpublished nodes drop to their original allocator partition, and
no PTE, cursor address or RSS count is published. Anonymous frames refund their
original metadata account when dropped; a VMO may legitimately retain a committed
cache page even if its later PTE allocation fails. That page remains charged to
its original physical owner, not a second mapping ledger.

On success, the already prepared path is installed under the existing exclusive
range lock, followed by the frame PTE and original RSS update. Concurrent faults
remain serialized. A fault-around error keeps the original successfully mapped
prefix; its fallback query no longer allocates nodes just to observe the faulting
address.

## COW and compatibility boundaries

A single-page cursor over an existing mapping still owns its original leaf.
The COW path admits/duplicates its frame before unmapping, and retains the
original unmap, TLB flush, jump and map sequence. It has not been converted to an
error-returning map after destroying the old mapping. The original ordinary
cursor, device, huge-page, fork and root-creation APIs retain their behavior.
The reserve-specific API and its five complete failure/ownership tests remain
in place with the same explicit authority rules.

This is not complete low-memory recovery: ordinary non-fault cursor queries can
still preallocate; VMAR/map metadata, root creation, fork, device mapping,
huge-page splitting, TLB retention vectors and remaining dynamic signal metadata can still use
infallible allocation. Page-table frames are not charged to `memory.max` by this
slice. Kernel heap coverage and global recovery remain open.

## Regression contract

The original complete suites remain unfiltered. Three core tests increase the
core inventory from 344 to 347 and required names from 105 to 108:

- Actual anonymous and VMO faults with a zero-page original account are rejected
  without changing the original queried empty page-table range, RSS or charge;
  repeated single-page and fault-around/fallback paths are exercised.
- Ordinary anonymous fault and fork/COW preserve the old frame and permissions
  when the original family limit denies a duplicate; after capacity is released,
  COW succeeds, preserves bytes, and the last physical reference refunds once.
- Fault-around retains a successful prefix and original VMO charge, reports an
  error for the still-unmapped fault page, and succeeds for an already mapped
  fault page despite a later surrounding-page error.

One OSTD test increases its inventory from 229 to 230. It observes absent ranges
through both no-preallocation cursor types, maps real ordinary frames across a
new branch while an explicit reserve is exhausted, and verifies the reserve is
unchanged and original frame references release on VM-space destruction.
The original reserve exhaustion tests exercise the shared pending-node transaction
at every missing-level cut. They do not qualify ordinary physical exhaustion.
No global OOM scenario, kernel panic or global allocation-failure flag is added.
At that earlier source, normal small ordinary page-table `NoMemory` under physical
pressure was unqualified. The later physical-pressure qualification is recorded below.

## Source-bound native qualification

The complete source `d5a21bb7e70a22cd022f4275ba2d22a6b726d233` (tree
`799487b33846203ee7b79680adbf6c2f69476024`) passed the original unfiltered
OSTD 230, allocator 20, core 347 (108 required names), and MLSDisk 15 suites.
All four guests exited with the original raw status 33. OSTD retains its three
original TCG VMX soft skips; the other suites have no skips. The source-matched
ordinary kernel then passed its 18 boot/QueryAbi checks, SGID 30, Unix ownership
12, and proc Groups/NoNewPrivs 12 on the same retained ELF. No guest memory,
time limit, inventory, negative assertion or authority boundary was relaxed.

The earlier `689c0131` source passed OSTD 230 and allocator 20 but core 346/347
exited 65: its COW fixture omitted the original heap initialization required by
`Vmar::fork_from`. Its failed ELF, serial, source identity and receipts remain
retained. `d5a21bb7` initializes that real fixture using the existing
`ProcessVm::map_and_init_heap` before fork; it changes no production behavior or
test assertion. Both failure and final result hashes are linked in the
[qualification receipt](../../results/integration/2026-10-23-audit-closure/vmar-fault-d5a21.json).

The actual zero-account rejection and original allocating-cursor comparison
qualify the admission ordering. They do not prove small physical page-table
allocation failure under memory pressure, nor whole-kernel OOM recovery.

## Real ordinary 4 KiB allocation-failure regression

The new `physical_page_table_nomemory_keeps_original_vmar_and_refunds_private_nodes`
core test retains the original N0, 512 MiB and guest deadline. Its VMAR, root
table, existing sentinel mapping, committed VMO page, family/ancestor accounts
and fixed-capacity vector all exist before pressure. The second VMA is in a
different x86 root slot, requiring three new child tables. A VMO read fault
uses its already committed original page; it does not first allocate user data,
perform COW or backend I/O. Its private locks take their uncontended fast paths.

The test holds real ordinary frames through `FrameAllocOptions` until allocation
fails. It then runs three cuts with zero, one and two ordinary frames available,
returning those frames by dropping original owners. Each actual `Vmar` fault must
return non-quota `ENOMEM`, preserve both PTE observations and RSS/ancestor counts,
and return exactly the one or two unpublished child-table frames to that same
allocator. After releasing pressure, the same fault must succeed using the
original VMO page. Actual final-reference destruction and an RCU grace period
verify the original data charges return once.

All observations are stored on the stack while IRQs are disabled. No test
assertion, formatting, log, task switch, vector growth or VMAR destruction occurs
until held frames are released. The original `loglevel=error` suppresses the
fault-path debug formatting. `Frame` metadata occupies boot-created 64-byte
`MetaSlot`s; `Frame<()>` has an empty drop hook, while unpublished empty PT nodes
refund directly through the original allocator. No heap metadata is allocated
by these frame allocation/refund paths. The original pending-node transaction
is a fixed stack array and the untouched TLB flusher does not grow its empty
retention vector.

This means the original ordinary 4 KiB allocation path actually returns
`NoMemory`, not that every physical free byte is zero: its empty local cache
refills in batches of eight pages, and unavailable fragments/other-size caches
may remain. No free counter, quota flag or injected allocation failure is used
to manufacture a cut. Fixed bookkeeping overflow invalidates the test.

The complete core inventory becomes 360 with 121 required names; all earlier
tests remain. OSTD 230, allocator 20 and MLSDisk 15 are unchanged. This test does
not qualify activated-table/TLB
removal, SMP, arbitrary syscall heap exhaustion, page-table resource charging,
physical recovery authority or whole-kernel recovery.

### Source-bound physical-pressure result

The frozen source `180d6dea2da8472faef5876a21f5054197bccd7a` (tree
`aae21dee05f6a0db69272d5f0ff4678fdccae9bd`) passed the complete original
core 360/360 (121 required names), OSTD 230, allocator 20 and MLSDisk 15
suites, each with raw QEMU status 33. OSTD retains only its three original TCG
VMX soft skips. The new test actually held 125186 ordinary frames and exercised
all three 0/1/2-frame windows, exact private-node refunds, unchanged old mappings
and counters, recovery after pressure release, and final-reference refund.

The source-matched ordinary ELF then passed 18 boot/QueryAbi checks and, on that
same ELF, SGID 30, Unix ownership 12, proc Groups/NoNewPrivs 12, memfd 4, signal
22, dumpability lifecycle 164, stat 54, TRACEME 15 and supplementary DAC 6. All
guests completed without timeout and reaped their controlled children. The
complete pipeline took 627.577 seconds; tracked source bytes remained unchanged.
The [receipt](../../results/integration/2026-10-23-audit-closure/ordinary-pt-180d.json)
records every retained ELF, raw serial, source identity, host check, and the two
earlier host inventory-expectation failures. This is a real ordinary page-table
allocation failure qualification within the private, unactivated VMAR fixture;
it does not broaden the remaining heap, SMP, accounting or recovery guarantees.
