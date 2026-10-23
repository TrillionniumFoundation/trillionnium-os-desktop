# IPC physical-frame admission and remaining memory owners

This page records the original 0187 IPC slice. The subsequent
[hierarchical cgroup admission contract](CGROUP_MEMORY_ADMISSION.md) supersedes
its historical `memory.max` stub and immutable-binding descriptions. Its eight
original tests remain required; their old evidence does not qualify new source.

This is a bounded extension of the existing fixed G1-d workload-family account.
It closes uncharged physical backing pages in pipes/FIFOs and Unix stream or
seqpacket connections. It does **not** implement `memory.max`, global memory
isolation, fallible kernel heap allocation, or guaranteed recovery under OOM.

Implementation baseline: `bcf6116f7607e6245dbc975cc7fc1a4e6c66176a` plus this
commit. Exact source `0187bd578f6786c40c812c13976e4889a1aba835` / tree
`335007e4f94114c6a26506d9448faf0d43c4245c` passed the original unfiltered native
core **303/303**, all 64 required names, allocator **20/20**, OSTD **229**
(three original TCG VMX soft skips), and MLSDisk **15/15**. All four raw QEMU
exits were 33; complete tracked inputs matched before and after. The same
OSTD ELF additionally passed actual KVM **229/229 with no soft skips**.
[Full source-bound receipts](../../results/integration/2026-10-23-audit-closure/full-ipc-0187/publication.json),
[separate KVM receipts](../../results/integration/2026-10-23-audit-closure/ostd-kvm-0187/publication.json),
and the [initial sparse-input refusal](../../results/integration/2026-10-23-audit-closure/full-ipc-0187-preflight-failure/publication.json)
are retained separately. These results qualify these exact source bytes, not a
later integrated tree or the complete memory/recovery contract.

## Original owners and admission

[`UserMemoryAccount`](../../kernel/asterinas/kernel/core/src/vm/user_memory.rs)
is the immutable family account already attached to workload Process/VMAR
objects. A reservation increments its original atomic page count before an
allocation. A non-cloneable `UserPageCharge` transfers into each original
`UserPageMeta`; the final `Frame` reference drops that token and refunds one
page. This change adds no counter in a pipe, socket, FD, mapping, or Hepta ledger.

[`RingBuffer<T, M>`](../../kernel/asterinas/kernel/libs/ring-buffer/src/lib.rs)
now accepts untyped frame metadata, with `M = ()` as the unchanged default.
`RingBuffer::new`, `Producer`, `Consumer`, their original aliases, and default
`segment() -> &Segment<()>` remain source-compatible. `from_segment` consumes
an original `Segment<M>` without replacing its metadata. It validates capacity,
item size and available segment bytes before publication; invalid inputs drop
the supplied segment normally. Splitting the buffer creates two Arc references
to one buffer, not two sets of physical pages.

[`new_user_ring_buffer`](../../kernel/asterinas/kernel/core/src/util/ring_buffer.rs)
uses the original allocator with `UserPageMeta`. It checks layout before
calling the ordinary segment allocator, whose pre-existing invalid-layout
panic contract is unchanged. Reservation failure or physical allocation error
returns the original error. No `PhysicalReserve` token is accepted or inherited.
An account-free caller still uses ordinary physical allocation.

| Entry | Physical backing owner | Admission and failure transaction |
| --- | --- | --- |
| Anonymous pipe | Family that first opens the new backing object | `Pipe::open_handle` obtains backing pages before open counts, activation, or handle publication. The syscall's existing Result chain returns ENOMEM. |
| FIFO | Family that first opens an idle FIFO | Subsequent opens reuse the original object and charge. Last open handle releases it; reopening allocates against the new initiator. Sharing with another family does not move or duplicate its original charge. |
| Unix stream/seqpacket `socketpair` | Calling family, both directions | Each original 64 KiB direction costs 16 pages. Both must exist before credentials/endpoints or FDs are published. Failure of the second direction drops and refunds the first. |
| Unix stream/seqpacket `connect` | Connecting family, both directions | `Init::prepare_buffers` runs before consuming the original bound/half-closed state. On failure the original Init returns through `Backlog::push_incoming` and `Takeable::borrow_result`; no connection enters the backlog. Accepting/sharing the connection retains the original charge. |

Sources: [pipe](../../kernel/asterinas/kernel/core/src/fs/pipe/common.rs),
[pipe file creation](../../kernel/asterinas/kernel/core/src/fs/pipe/anon_pipe.rs),
[connection buffers](../../kernel/asterinas/kernel/core/src/net/socket/unix/stream/connected.rs),
[Init transaction](../../kernel/asterinas/kernel/core/src/net/socket/unix/stream/init.rs),
[backlog](../../kernel/asterinas/kernel/core/src/net/socket/unix/stream/listener.rs),
[socketpair syscall](../../kernel/asterinas/kernel/core/src/syscall/socketpair.rs).

Allocation remains contiguous, as in the original ring buffer. Fragmentation
can therefore return ENOMEM even with sufficient total free pages. Metadata
charges follow the physical pages, including segment slices retained after
both buffer halves have been dropped. Transferring a descriptor does not give
the receiving family new allocation authority or reattribute existing memory.
The original diagnostic page count now includes these selected IPC pages.

The existing pipe and connection locks still serialize publication. Admission
uses only the existing atomic account and original non-sleeping frame allocator;
this change introduces no I/O, wait, reclaim, OOM callback or new lock ordering
inside those critical sections. Heap allocations for Arc/object/backlog storage
are still outside this guarantee.

## Native regression contract

All eight tests live in the original `aster-core` suite. No new standalone fake
allocator or host model substitutes for original `Frame`, `Segment`, Pipe, or
VMAR ownership. The tests run with the existing full N0 configuration and
original kernel test runner; do not filter the crate.

| Required test suffix | Observable boundary |
| --- | --- |
| `ipc_buffer_charges_original_pages_until_last_segment_alias` | Exact 16-page charge, real byte write/read, both Arc halves, retained final page alias, denial at limit, final refund, unowned/default negative controls. |
| `ipc_buffer_rejected_layout_and_allocator_failure_refund_owner` | Invalid capacity/size rejects without leaving an already-owned segment charged; valid 16-TiB allocation reaches the original allocator maximum-order rejection and refunds admitted pages (not a global-exhaustion claim). |
| `pipe_production_capacity_uses_current_family_and_refunds_last_endpoint` | Explicit original 65,536-byte production capacity under a real VMAR-associated kernel task; exact 16 pages and last-endpoint refund. |
| `fifo_shared_opens_keep_first_owner_without_double_charge` | Real FIFO open/read/write by two VMAR-associated tasks with different accounts; zero-budget second family may reuse existing pages, and last close refunds the first owner. |
| `pipe_denial_publishes_no_object_or_open_counts` | Anonymous and named paths preserve zero backing references and zero open counters on rejection. |
| `unix_pair_admits_both_directions_or_refunds_the_first` | Limits 0/15/16/31 reject and fully refund; 32 admits both actual segments and data transport; each last half refunds its segment. |
| `denied_connection_keeps_original_bound_and_shutdown_state` | Real Init admission preserves abstract-name registration and both shutdown flags; final Init release removes the name. |
| `unix_socketpair_denial_preserves_current_family_without_endpoints` | Both stream and seqpacket creation call the production path under a real current VMAR owner; first/second allocation failure returns ENOMEM and leaves no charge. |

The pre-existing pipe tests keep their two-byte `cfg(ktest)` capacity. The new
explicit-capacity case is additional; the production size and old tests are
not reduced. The helper uses immutable VMAR association through original
`ThreadOptions`; no current-owner override is installed. A completion assertion
in the parent test catches an assertion panic swallowed by the kernel thread's
normal panic-to-oops wrapper.

[`support/build/ktest/check.py`](../../support/build/ktest/check.py) requires all
64 named core regressions exactly once and the retained full minimum of **303**
(295 + 8). Missing, duplicated, filtered, soft-skipped, or nonzero-exit runs fail.
Original full OSTD 229, allocator 20 and MLSDisk 15 requirements remain separate
and unchanged. Native qualification must retain the exact source identity,
source-matched OSDK, ELF/hash, serial/hash and raw QEMU exit 33 from the original
[`run.py`](../../support/build/ktest/run.py) entry. Host checker fixtures are
anti-forgery tests, not 303 executed kernel tests.

A syscall-level workload with constrained G1-d family credentials and concurrent
FD passing is additional qualification, not claimed by these eight kernel
cases. Ordinary full native Hepta/socket workloads must still be rerun on the
resulting integrated kernel before shipping.

## Scope still open: global memory limits and recovery

| Resource | Actual existing owner | Current limitation / next boundary |
| --- | --- | --- |
| Anonymous user RAM, COW, selected device RAM | Original `Frame<UserPageMeta>` and immutable family account | COW charges a new frame; shared physical aliases do not. This remains a fixed-family admission policy, not a cgroup hierarchy. |
| File/anonymous VMO pages | Original `Frame<CachePageMeta>` in VMO/XArray | Original first allocator or explicit VMO owner is charged; aliases retain that owner. XArray RCU references may delay final refund. Arc and XArray-node heap allocations remain infallible. |
| VMAR / page tables | Original OSTD `VmSpace`/page-table page owners | Explicit `try_new_from` and recovery cursor APIs exist, but ordinary VMAR/fork does not inherit reserve authority. They are not yet a fully fallible recovery process path. |
| Pipe and Unix stream/seqpacket payload buffers | Original typed ring-buffer Segment | Covered by this slice. IPC object/FD storage, ancillary control messages, backlog storage, datagrams, network packets, evdev/TTY/PTY rings remain outside it. |
| Global heap / slab objects | Original heap allocator object caches and frame-backed slabs | A slab page can contain allocations belonging to different requesters. Charging the whole page to each requester would double count; an independent byte counter would not reserve physical memory. Fallible per-allocation ownership and prepared metadata need original allocator design. |
| `memory.max` / `memory.events` / memory statistics | Existing cgroup memory controller | Still TODO with AttributeError paths. It does not own a functioning hierarchical memory account or admission controller. |
| Recovery reserve | Original global frame allocator's one active protected extent, opaque OSTD token | Physical protection and explicit PT APIs exist. Recovery bootstrap, heap, IPC, FD and durable storage admission do not yet share a complete fallible transaction. `global_recovery_guarantee = false`. |

Sources: [VMO](../../kernel/asterinas/kernel/core/src/vm/page_cache/vmo/mod.rs),
[cache metadata](../../kernel/asterinas/kernel/core/src/vm/page_cache/cache_page.rs),
[VMAR](../../kernel/asterinas/kernel/core/src/vm/vmar/handle.rs),
[VmSpace](../../kernel/asterinas/ostd/src/mm/vm_space.rs),
[heap](../../kernel/asterinas/osdk/deps/heap-allocator/src/allocator.rs),
[cgroup memory stub](../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/memory.rs),
[Unix datagrams](../../kernel/asterinas/kernel/core/src/net/socket/unix/datagram/message.rs),
[physical reserve contract](PHYSICAL_RESERVE_MECHANISM.md).

The next memory-controller work must bind hierarchical admission to these
original physical owners and define migration/shared-cache ownership before
publishing a writable `memory.max`. It must preserve existing charges across
shared FDs and mappings, enforce the complete ancestor limit transaction, and
refund through original frame/allocator destructors. Recovery work must use an
explicit authority/budget on the original VMAR/PT/heap/IPC allocation path and
prepare all fallible resources before publishing a runnable recovery task.
Neither an unlimited manager account nor an approximate free-memory observation
is a reserve or a proof that these remaining paths can survive exhaustion.
