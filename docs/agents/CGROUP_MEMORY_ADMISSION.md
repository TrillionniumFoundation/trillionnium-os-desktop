# Hierarchical admission for original physical-frame owners

This slice replaces the cgroup memory stub with **selected physical-page
admission**, on base `0187bd578f6786c40c812c13976e4889a1aba835`. It is not a
complete Linux memory controller or a global recovery guarantee. The core
implementation, original owner regressions, and strict native inventory are
part of the same change. A source-matched unfiltered native run passed at
`2c7a8543ea49e7d87e8915f2b3463f5d2119c020`, after correcting test teardown
of original deferred CPU owners; see the exact execution record below. Previous
0187 results are not reused as execution evidence for this change.

## User-visible contract

Non-root active memory controllers expose `memory.current` (read-only),
`memory.max` (read/write), and `memory.events` (read-only). The old unusable
`memory.stat` placeholder is not advertised. `memory.current` is the byte count
of admitted covered pages charged to that node and its descendants. It includes
in-flight physical-allocation reservations; failed or unused reservations refund
through their original owner. It is not instantaneous RSS. Each covered frame is counted once at its leaf and once in each ancestor's aggregate;
extra mappings, FDs, `Frame` clones, forked aliases and socket endpoints do not
create extra physical charges.

`memory.max` defaults to `max`. Decimal byte values are rounded upward to the
original 4096-byte page size; invalid input and rounding overflow are rejected.
Zero is a valid limit. A write below current usage fails with EAGAIN and leaves
the previous limit unchanged, in the same transaction as admission/refund.
There is no reclaim, OOM kill, or asynchronous convergence. `memory.events`
currently contains only `max N`: denied cgroup admissions at this node and
its descendants. The independent G1-d family-limit failure and ordinary
physical allocator failure do not increment this cgroup counter.

Linux also rounds limits to pages and keeps existing memory charged to its
original cgroup when a process migrates. Linux additionally implements reclaim,
OOM and substantially more memory classes; its lower-than-current limit update
is different from this implementation's explicit rejection. See the
[upstream cgroup v2 memory contract](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html#memory).
Do not describe this subset as Linux memcg parity.

## Stable identities, admission and refund

The original owners are
[`UserMemoryReservation` / `UserPageCharge`](../../kernel/asterinas/kernel/core/src/vm/user_memory.rs),
[`UserPageMeta`](../../kernel/asterinas/kernel/core/src/vm/user_memory.rs), and
[`CachePageMeta`](../../kernel/asterinas/kernel/core/src/vm/page_cache/cache_page.rs).
A successful reservation captures the original family budget and one immutable
[`MemoryDomain`](../../kernel/asterinas/kernel/core/src/vm/user_memory/hierarchy.rs)
identity. That identity retains its ancestor chain. The linear charge moves
into original physical frame metadata; unused reservation pages and failed
physical allocations refund through the same owners. The final actual frame
reference refunds the captured family and every ancestor. XArray/RCU references
can delay that point. Neither migration nor dropping a mapping refunds early.
There is no per-FD counter, approximate free-memory ledger, or Hepta shadow bill.

A `MemoryDomain` belongs to a stable cgroup identity. The
[`Controller`](../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/mod.rs)
retains its memory subcontroller rather than replacing it with each RCU
activation update. All covered pages are counted while `+memory` is disabled.
Disabling hides the child interface and suspends that child's limit; it does
not erase counts or limits. Re-enabling enforces the saved limit against all
live pages. If disabled-period allocations exceeded it, future allocations
fail until usage falls below the limit or an authorized larger limit is set.
This does not revoke existing mappings or free their pages.

Removing an empty cgroup closes its domain against new allocation. Retained
physical references may outlive the directory; their old identity and ancestor
charges remain until final refund. A new node at the same path has a distinct
identity and cannot erase or borrow the old charges. Root is depth zero, at
most 64 non-root levels are admitted, and creation of level 65 is rejected
before the new node is constructed or published.

The IRQ-safe memory transaction lock serializes the complete ancestor check
and increment, family-budget check/increment, limit update, delegation change,
closure, binding swap and refund. It walks at most 65 retained nodes without
allocating, sleeping, user-memory copying, logging, reclaim, I/O, or taking
membership/tree/VMAR locks. Per-domain state locks are private and only taken
inside this transaction, one at a time. Account binding follows transaction
then binding lock. Arc construction happens before the transaction; replacing
an old binding returns its Arc and drops it after the transaction, so final
metadata/ancestor destruction is not performed inside the IRQ-disabled lock.

## Processes, fork, shared address spaces and migration

Every original VMAR has an allocation binding, including ordinary processes
that have no finite G1-d family limit. Process retains that same binding through
exec. Fork makes a distinct binding sharing the immutable family budget and
current cgroup snapshot. Existing shared physical pages retain old tokens;
new child COW/pages use the child's binding. The original G1-d family quota
still applies across its descendants and cannot be expanded through migration.
No recovery reserve authority is copied by fork or this memory controller.
The original family-limit page-fault diagnostic is preserved; a distinct
cgroup-error provenance prints a cgroup denial without mislabeling family
counters or a later migrated snapshot as the rejecting limit.

A real `ProcessMemoryOwner` lease counts original Process objects sharing the
binding, not threads, mappings or arbitrary Arc references. Different Processes
created with CLONE_VM cannot currently migrate to different cgroups; the
checked entry rejects before either membership or binding changes. Same-node
no-op migration remains allowed. Multiple threads within one Process still
have one lease. Exec currently retains this binding: it does not silently
unlock the independently shared-Process migration restriction. A later change
may implement an explicit, safe binding split; this slice does not claim it.

The original membership writer serializes user migration with fork/clone,
which already hold the membership reader while creating Process/VMAR objects.
Target liveness, shared-binding restrictions and the no-internal-processes rule
are checked before publication. After target validation and map insertion, no fallible
operation remains: the allocation binding swaps, then original cgroup/CPU/pids
ownership is published. A concurrent allocation captures the complete old or
new memory domain. Existing pages stay charged to their original group, even
when the new group has a zero limit. The checked root-migration entry follows
the same rule and preserves original trusted-CPU migration restrictions.

Internal zombie/reap cleanup removes membership without reattributing any
retained VMO/frame owners. It is not an alternative user migration entry.
See [membership and node lifecycle](../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs),
[Process lease](../../kernel/asterinas/kernel/core/src/process/process/mod.rs),
[fork](../../kernel/asterinas/kernel/core/src/vm/vmar/vmar_impls/fork.rs), and
[exec](../../kernel/asterinas/kernel/core/src/process/execve.rs).

The VMO's explicit stopped-loader owner remains the destination for ordinary
loader writes, without relying on an ambient current Process. Explicit VMAR
fault APIs use their initiating VMAR owner first, then the loader owner only
as fallback. This prevents a forked/migrated address space's new page fault
from charging its parent's old binding while preserving stopped-image charging.
Existing committed VMO pages are never recharged. The exact selection lives in
[VMO commit/read/write](../../kernel/asterinas/kernel/core/src/vm/page_cache/vmo/mod.rs).

## Covered paths and deliberately open owners

| Resource | Charge owner and current boundary |
| --- | --- |
| Anonymous user RAM, COW, selected user-visible device RAM | Original `Frame<UserPageMeta>`; allocation's family plus stable cgroup chain. MMIO is not RAM and is excluded. |
| Anonymous/file VMO pages | Original `Frame<CachePageMeta>`; first allocating initiator or explicit stopped-loader destination. Shared page cache keeps that first charge. Boot/kernel allocations made without any Process/VMAR owner remain outside process attribution. |
| Pipe/FIFO backing | Original typed Segment from the first opening initiator. Shared opens retain that charge; last physical reference refunds it. |
| Unix stream/seqpacket payloads | Original two typed ring-buffer Segments from the connecting initiator. Second-direction failure refunds the first; no endpoint is published. |
| Ordinary page-table pages | Original OSTD PageTable/VmSpace owners; not charged by this controller. Explicit PhysicalReserve PT APIs remain separate. |
| Kernel heap/slab and object/FD/backlog allocations | Original heap/slab owners; not made fallible or attributed here. A slab page may serve several requesters and cannot be charged once per requester. |
| Ancillary data, datagrams, TCP/IP packets, other TTY/device rings | Separate original buffer owners; still open. |
| Recovery bootstrap, heap, IPC and durable I/O | No unified fallible recovery transaction is supplied. `global_recovery_guarantee = false`. |

The [IPC physical-owner handbook](IPC_PHYSICAL_FRAME_ACCOUNT.md) explains the
existing first-owner/shared-FD and connection publication contracts. A finite
`memory.max` therefore limits the covered classes, not all memory a process
can induce the kernel to allocate. It is not currently sufficient for an
adversarial whole-kernel OOM containment claim.

## Development and source-bound acceptance

No new unsafe code, allocator pool, allocation bypass, feature-default change,
Cargo dependency, test capacity, QEMU timeout, or filtered test path is added.
The 10 additions stay inside the original unfiltered `aster-core` suite:

| New regression | What is actually exercised |
| --- | --- |
| `hierarchical_frame_admission_refunds_family_and_every_ancestor_once` | Original Frame and retained alias, ancestor denial without partial charge, unused reservation refund, preserved separate family cap. |
| `disabled_domains_keep_live_charges_and_deleted_identity_cannot_escape` | Actual live frames through disable/enable, saved cap, deletion, new identity and old-frame final refunds. |
| `physical_allocator_error_rolls_back_complete_hierarchical_precharge` | Valid 16-TiB segment request reaches the original allocator's maximum-order rejection after admission; no mocked allocator or fake exhaustion. |
| `concurrent_sibling_allocators_cannot_both_cross_ancestor_limit` | Two real Core threads race sibling allocations under one-page parent limit and hold the winning frame until both attempts finish. Worker completion is asserted separately to catch panic-to-oops. N0 scheduling interleaving is not an SMP stress qualification. |
| `explicit_vmar_fault_owner_overrides_loader_fallback_without_recharging_shared_pages` | Actual VMO loader write, original committed-page sharing, new fault in a distinct binding, family conservation, real RCU grace and exact final refund. |
| `unix_stream_and_seqpacket_partial_buffer_admission_refund_ancestor` | Original socketpair entry rejects its second physical direction under a real VMAR-associated thread; no endpoint or residual first-direction charge. |
| `memory_files_round_bytes_reject_lowering_and_bound_depth_before_publication` | Actual SysNode attributes, byte parsing, unchanged rejected update, activation visibility, live usage, level-65 unpublished rejection. |
| `migration_changes_only_future_allocations_and_failed_target_preserves_membership` | Original unstarted Process/Task, node migration, retained old physical frame, new zero-cap denial, failed target rollback, checked root migration. |
| `fork_has_independent_binding_and_clone_vm_processes_cannot_split_membership` | Original VMAR fork, original Process constructors sharing one VMAR, real leases, migration refusal, actual child COW with unchanged parent bytes, final RCU refund, and ability to move after shared Process destruction. |
| `pipe_and_fifo_backing_obey_hierarchical_limit_with_unlimited_family` | Original explicit 64-KiB pipe backing, exact hierarchy usage, pipe/FIFO denial, both endpoint drops, subsequent FIFO success. |

The production pipe capacity and existing small-buffer legacy tests remain
unchanged. The strict checker preserves all original 303 core tests and 64
required names, adds these 10 names, and requires at least **313 core / 74
required** tests, all exactly once and without filter/soft-skip. OSTD **229**,
original allocator **20**, and MLSDisk **15** remain independent complete
inventories. Other branches' additions must be merged by exact name and source,
not counted as already executed.

Development checks (from repository root; all build targets/TMP on `/data`):

```sh
python3 -I support/build/verify-source.py
python3 -I -m unittest discover -s support/build/tests -p '*ktest*.py' -v
CARGO_NET_OFFLINE=true CARGO_TARGET_DIR=/data/cgroup-memory-check \
  cargo +nightly-2026-07-21 check --offline --locked \
  --manifest-path kernel/asterinas/Cargo.toml -p aster-core --target x86_64-unknown-none
```

The configured VDSO directory must contain the retained verified VDSO, as in the
existing native workflow. Repeat check/Clippy with `RUSTFLAGS='--cfg ktest'` for
all new cases. These are compile/host checks, not kernel executions. Native
acceptance must use source-built OSDK matching the frozen checkout and the
original full runner, coordinated with other users of the global OSDK binary:

```sh
python3 -I support/build/ktest/run.py --crate aster-core --crate ostd \
  --crate osdk-frame-allocator --crate aster-mlsdisk --output /data/NEW-FROZEN-RECEIPT
```

The original runner/checker must retain full source blobs before/after,
Cargo/OSDK identities, ELF, raw serial and hashes, and actual QEMU exit **33**
for every suite. No filtered/soft-skipped substitute, unchanged ELF from 0187,
or synthetic host fixture qualifies this source. Ordinary integrated native
Hepta workloads and user-level cgroup/mmap/IPC stress remain further acceptance
work; this document does not claim they have run.

### First native execution and deferred-owner teardown

The full unfiltered four-crate run at `5015b949258cc0ec07aafc68f388c1085ed2796b`
(the memory slice plus the boot-ID slice) passed OSTD 229 and allocator 20, then
failed strictly in core before a complete result. QEMU returned raw 0, which the
original checker rejected; MLSDisk was not run. This is not a passing core run.
The failed ELF and complete original logs remain frozen separately.

A private debugger session using that same retained ELF stopped at the first
`panic_fmt` in the migration test. Its original `Location` is `memory/tests.rs:169`:
`mark_as_dead` rejected deletion because the cgroup still held deferred CPU
accounting leases. The migration's quota assertions had completed. Clearing an
unstarted task's original `RcuOption<CpuCgroupLease>` queues the old owner until
RCU grace; dropping the Process and Task alone is not a grace-period barrier.
A subsequent fixture-unwind panic obscured this first error and exhausted the
unwinder stack. The repair waits on the existing real `RcuDrop` witness and a
bounded original task yield after releasing the test Process/Task, before the
unchanged strict deletion checks. It does not clear lease counters, bypass
`mark_as_dead`, change a quota assertion, or alter the guest deadline.

### Source-bound completed native execution

The corrected source `2c7a8543ea49e7d87e8915f2b3463f5d2119c020`, tree
`ebdc1bcea26f26834d2735ddc9caee7e2b8a78e6`, completed the original unfiltered
four-crate runner. OSDK was rebuilt from that checkout and its installed binary
was retained. The original 512-MiB, SMP-1 TCG profile and 300-second guest
deadline were unchanged. Every guest returned raw QEMU 33; the original runner
and the outer source/ELF-retention wrapper both returned 0.

| Original suite | Declared / passed | Failed / filtered | Soft skips | Specific result |
| --- | --- | --- | --- | --- |
| OSTD | 229 / 229 | 0 / 0 | 3 | Original TCG VMX/EPT unavailable skips; 226 exercised lower bound. No new KVM qualification is implied. |
| Physical allocator | 20 / 20 | 0 / 0 | 0 | Actual exhaustion of 127099 ordinary frames, reserved 64-page extent usable, final refund to original allocator. |
| Core | 316 / 316 | 0 / 0 | 0 | All 77 exact required names, including all 10 memory additions and 3 boot-ID additions, occurred exactly once. |
| MLSDisk | 15 / 15 | 0 / 0 | 0 | Original 512-MiB guest and 256-MiB memory-disk capacity retained; no media-power-loss claim. |

The evidence directory is `cgroup-memory-native-2c7-01` under the local audit
build root. The four retained ELF SHA-256 values are:

| Crate | Retained ELF SHA-256 |
| --- | --- |
| OSTD | `5bfad537c6d9210e665af173086ee7bb58951ac429226f3ead765733fb8081ae` |
| Physical allocator | `84bf3a9ff70e35030ec33775d0260ce33cd2490ea51e5dc901db04844406292e` |
| Core | `cc01f45c4449fd4caf14e32fa27092ca59255a87446366013222a01d65d3d329` |
| MLSDisk | `b5b443a0463c6f817d880672b2369e17e6aafbd3c7fec4bb8fff90d4c9b7f2c1` |

The complete tracked-source snapshots before and after execution are identical,
both SHA-256 `6f89bcb74d607583a33f234d2b6da2f9dbbad7df14a8f7a977371930181a13ae`.
`outer-result.json` has SHA-256
`bfa106295dd97f7de07190102c72e787fa3e230361791a3b3483e5294953a866`;
`retention.json` has SHA-256
`0e3d9c8ad441a659fb21325e5a8578471b6ee231301536ccd18ec941a708d47a`.
The first failed 5015 source, ELF, raw-QEMU record, serial and same-ELF debugger
diagnosis remain separate. Nothing relabels that failed run as successful.

Host anti-forgery checks also passed 44 tests, and the original source verifier
passed all 118 path boundaries. Changed-file formatting passed; full-workspace
format checking still reports pre-existing differences outside this slice.
These host checks are not counted as native tests. This run establishes the
selected physical-frame admission contract under the original N0 profile;
it does not establish new ordinary-userland, SMP-stress, KVM, full-memory,
heap/IPC recovery, or production-device qualification.
