# Physical page budget, second isolation stage

This is a development-stage extension of the reviewed private-anonymous/COW budget. It does **not** implement Linux `memory.max`, total RSS, all physical memory isolation, an OOM killer or a global recovery reserve. Standard `memory.max` remains unsupported. A later integrated build must rerun the actual guest tests; this document is not a passing result.

## Interfaces and owners

Every cgroup node exposes `hepta.page.max`, `hepta.page.current`, `hepta.page.events` and `hepta.page.stat`, independently of Linux controller enable/disable. `max` accepts a byte ceiling or the literal `max`; a reduction below current usage is rejected. Charges are whole physical pages, and a denial increments `max N` at the account that rejects the allocation. The existing `hepta.anon.*` interface keeps its prior private-anonymous/COW meaning; private allocations must satisfy both ceilings.

The new combined ceiling accounts these paths:

| Statistic | Actual allocation | Ownership and lifetime |
| --- | --- | --- |
| `private` | Private anonymous faults, private VMO tails, file/fork COW | Allocating process's cgroup; final physical frame reference refunds |
| `anonymous_vmo` | New RAM-backed VMO pages, including shared anonymous maps, memfd and RAM-backed file caches | First committer's cgroup; later shared mappings do not charge again |
| `file_cache` | New backend VMO cache pages for filesystem/block cache I/O | First allocating process's cgroup; mappings, cache entries and in-flight I/O all retain the charge |

`current` is the sum of these categories in the account and its descendants. This is physical allocation ownership, not the sum of mappings or a process's resident set. A VMO page first populated outside a constrained subtree does not become that subtree's charge when reused. Migration affects future allocations; existing pages retain their original accounts. A delegated worker charges its own process, not an implicit caller. Allocations with no current process remain excluded.

The original account is embedded in `CachePageMeta` or private-frame metadata and survives task exit, node deletion, truncate/eviction, mapping removal and asynchronous I/O references. No charge is refunded merely because a task exits or an unmap returns. This includes an inherited private mapping backed by a shared VMO: a child can first populate its backing page, and the parent can retain that physical page after the child exits. The guest probe prefaults the inherited stack from its observer before fork and tests newly allocated frame deltas separately from retained filesystem cache pages. TLB/RCU references can delay final release; CPUs must reach quiescent points. No wall-clock release bound is promised for a stalled CPU.

## Admission and failure rules

`controller/page_memory.rs` reserves the leaf and every ancestor before allocating physical memory. Each account's limit, total and category counters share one IRQ-safe spinlock. Only one account lock is held at a time. No allocator, I/O or sleep occurs under those locks. A later ancestor rejection rolls back all earlier reservations. Temporary in-flight reservations may conservatively deny another allocator, but cannot admit more than the ceiling.

Private pages first reserve the combined budget and then the compatible anonymous budget from the **same membership snapshot**. If either refuses or frame allocation fails, owned reservations roll back. Shared/cache allocation errors propagate through the existing VMO/syscall paths; no success is fabricated. Contiguous VMO allocation reserves the full page span before allocation and splits that reservation into frame metadata without per-page heap allocations; unused reservation tails refund on failure.

VMO page-array locking serializes first allocation, so racing faults or writers cannot create multiple charges for the same retained page. File backend initialization failure may leave an uninitialized cached page available for retry; it remains charged while physically retained. Dropping an inode or task need not immediately evict global filesystem/block metadata caches.

## Recovery boundary and remaining work

A capped workload and a sibling recovery group can retain headroom **for these covered allocation classes** when their parent ceiling leaves enough space. Put the monitor/recovery process outside the exhausted workload before pressure begins, and prevent untrusted migration or limit changes. This is not reserved global memory: page tables, kernel heap/stacks and object metadata, device/DMA buffers, and boot/kernel-thread allocations can still consume physical memory outside this ledger. Shared cached pages owned by other groups also remain usable. This interface must not be advertised as protection from every memory exhaustion route.

A complete controller still needs explicit ownership for page tables and kernel allocations; worker and DMA delegation; global/root/recovery reserve pools; reclaim, writeback and OOM admission; bounded recovery; and migration/reparenting policy. Enabling standard `memory.max` before those semantics and their actual allocation paths pass independent review would be misleading.

## Allocation audit for the next stage

| Remaining owner | Current allocation path | Required next change |
| --- | --- | --- |
| User page tables | OSTD `mm/page_table/node/mod.rs::PageTableNode::alloc` and `node/entry.rs` | Carry a stable address-space account into each node; make node allocation/admission failure propagate through map/fault/fork before publication; refund only at final node release |
| Kernel object/slab memory | `osdk/deps/heap-allocator/src/allocator.rs`, per-CPU caches and global slab pools | Define shared slab versus object ownership, fallible allocation for workload-induced objects, worker delegation and recursion-free accounting; a global byte counter is insufficient |
| Kernel stacks | OSTD task/stack allocation | Charge task-owned stacks before thread publication and retain until task/CPU references are gone; reserve enough scheduler/fault-handler capacity for recovery |
| DMA buffers | OSTD `mm/dma/{dma_coherent,dma_stream,util}.rs` | Explicit driver/request owner plus buffer charge lifetime through hardware completion; independent of IOMMU address authorization |
| Filesystem metadata outside VMO | For example `Ext2::open` directly allocates the group-descriptor segment | Account these direct frames and in-memory inode/extent structures; the new `file_cache` class does not cover every byte induced by file activity |
| Processless work | Boot, IRQs and kernel workers | Explicit system/delegated accounts; no inference from an absent current process |
| Recovery reserve | Current allocator serves all these classes from shared physical memory | Real protected pools for physical frames **and** fault/reclaim/scheduler metadata, plus admission and audited fallback paths; a sibling counter alone is not a physical reserve |

These are implementation dependencies before advertising full `memory.max`, not waived acceptance criteria. In particular, changing the page-table allocator to return a denial without teaching every map/fork path to roll back would turn normal pressure into a panic or partially published mapping.

## Build and verification

Use the pinned toolchain and an OSDK compiled **from this checkout** with `OSDK_LOCAL_DEV=1`. Its generated dependencies embed the build checkout's absolute path. A binary built in another worktree can combine different source trees; do not reuse it silently. Keep per-worktree OSDK installation roots and generated test-base manifests.

Run the full `aster-core` native suite through `support/build/ktest/run.py`. The new tests allocate real Frames and cover combined categories, ancestor rollback, last-reference ownership, partial contiguous reservation cleanup, sibling headroom, and concurrent allocation/refund versus limit updates. The partial-reservation test does not claim that the global physical allocator's OOM was forced.

Run `python3 tests/kernel/page-memory/run.py --smp 2 --output /absolute/new/evidence`, then its `--smp 4 --reuse /absolute/prior/evidence` mode against identical working bytes. The guest receives only a generated 16 MiB ext2 fixture using snapshot writes, no host block devices or network. The probes exercise real shared mmap, memfd, other-group reuse, actual ext2 cold reads/cache writes/truncate, exact-ceiling ENOMEM and SIGSEGV, denial events, and recovery sibling allocations. Failed setup is a failure, never an unavailable skip. Kernel/BIOS/initramfs/probe, source and raw serial hashes are retained. The reuse mode refuses changed source or artifacts. Also rerun `tests/kernel/safety/run.py` to cover the first stage.

Evidence remains development evidence until the tested source is committed and its bytes are bound separately. OSTD code is unchanged in this memory stage; per-device IOMMU work is a separate stage and does not inherit qualification from these tests.

The ext2 guest fixture uses modern-only VirtIO PCI (`disable-legacy=on`). The first default transitional-device run failed: the existing modern transport decodes transitional block ID `0x1001` as network type 1. That retained failure is not treated as memory validation or as working transitional VirtIO support.

## Stage validation recorded locally

The stage's final `aster-core` run executed 301 tests with no test skips. The 2-CPU and 4-CPU ordinary guests each passed 76 assertions, including four simultaneous workers committing and freeing actual shared/memfd pages while the observer changes the budget. Both prior five-probe safety suites also passed on the same ordinary ELF. Host evidence tests passed normally and with Python optimization. These results cover this stage's development bytes; integration still requires the receiving source and artifacts to be verified.

Failed runs remain evidence: the initial transitional VirtIO fixture could not mount; an earlier refund assertion incorrectly assumed the observer no longer retained child-populated inherited-stack backing; and one 4-CPU evidence run rejected a transient build manifest created by a concurrently running ordinary build, despite its 76 guest assertions passing. The final 4-CPU rerun ran without a concurrent build and matched both source snapshots. Source fingerprints must be collected with the build workspace quiescent.
