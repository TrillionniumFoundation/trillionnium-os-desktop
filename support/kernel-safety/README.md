# Kernel safety increment: authority snapshots and anonymous/COW accounting

Status: development candidate based on main `38227d33fd3ed668f0424bc153e0d3d811731597`. This directory documents the implementation and its acceptance boundaries. The test evidence is generated separately by the commands below; the presence of this document is not a passing result or production qualification.

The [physical page budget](PAGE_MEMORY.md) now includes private/COW and VMO/cache
pages, [user page tables](PAGE_TABLE_MEMORY.md), and [POSIX kernel stack
frames](KERNEL_STACK_MEMORY.md). The `hepta.anon.*` interface and its first-stage
scope below remain unchanged. Neither interface is full Linux `memory.max`.

The following documents each contain development entry points, technical
ownership rules, reproduction commands and explicit qualification boundaries:

- [Requester DMA domains](DMA_DOMAINS.md): private VT-d tables and actual
  cross-requester denial within a restricted topology.
- [Boot identity](BOOT_ID.md): the same HOS2/procfs UUID and missing-entropy refusal.
- [Bounded native executable loader](G2_NATIVE_LOADER.md): immutable input,
  complete LOAD validation and a separate original-application acceptance lane.
- [Proc credential status](PROC_STATUS.md) and [SGID inode creation](SGID_CREATION.md):
  actual retained credentials and pre-publication owner/mode decisions.
- [Group stops and restored waits](GROUP_STOP.md): real task stops, futex and
  semaphore completion, and preserved absolute deadlines.
- [Persistent native storage](NATIVE_PERSISTENCE.md): generated private ext2,
  bind identity, UID isolation and actual VM-process crash/reopen.

These are individual stage contracts. Their presence and independent component
passes do not establish that one final original Hepta/native pair has passed.

## Changes and invariants

### Commoncap process inspection

`security/lsm/modules/capability.rs` now requires a same-identity caller's selected capability set to contain the target's **permitted** set. FSCREDS selects the caller's effective capabilities; REALCREDS selects its permitted capabilities. The CAP_SYS_PTRACE path and stacked LSM checks remain applicable. Dumpability is now a real shared-image property, described below; the old `PR_SET_DUMPABLE` success stub was discovered by the first guest run and is not treated as a working precondition.

The concrete regression uses owned processes in the initial user namespace: all real/effective/saved UID/GID values are 60001; the target is dumpable and retains permitted CAP_CHOWN with an empty effective set; the caller has no capabilities. Reading the target's `/proc/PID/maps` must fail. Once the target drops that permitted capability, the same read must succeed. This is not a claim about unconditional access to arbitrary root processes. New user namespace support will require namespace-aware capability checks throughout this existing LSM.

### Dumpability and coherent authorization

`ProcessVm` owns the dumpable flag. New ordinary images start dumpable; fork copies the value; threads and separate processes sharing the same `CLONE_VM` image share it. `PR_SET_DUMPABLE` accepts 0/1, updates that actual state, and `PR_GET_DUMPABLE` reads it. Changing effective or filesystem UID/GID, or gaining permitted capabilities, clears dumpability. A failed, no-op or query credential operation, a permitted-capability decrease, or changing only real/saved IDs does not spuriously clear it. Exec prepares a new image with its own policy: unequal new real/effective identity, gained permitted capabilities or an unreadable script/ELF/interpreter suppress dumpability; the credential-commit transition may additionally clear it when effective/filesystem IDs change. Exec never restores a flag suppressed by the loader. Failed exec leaves the old image unchanged.

Live credential edits run through a closure transaction holding process VMAR then shared-image policy. Sensitive alien-access checks acquire the target VMAR then the same image policy and retain the authorization guard through the resource capture. This prevents a new identity from becoming visible to a sensitive capture before its matching dumpability reset, including separate `CLONE_VM` processes. No writable credential capability escapes that closure.

Protected `/proc` maps, mem, environ, auxv, exe, fd and namespace paths use this policy; stat sanitizes protected address/exit fields; private proc metadata changes ownership for non-dumpable targets while retaining documented self-access exceptions. An already opened environ/auxv file retains its original image instead of following later exec. Ordinary root/SYS_PTRACE exception semantics remain, so a root caller is not a useful negative test. The same-ID unprivileged guest tests are the negative controls.

Voluntary `PTRACE_TRACEME` uses the actual parent's permitted-capability relationship and records whether that parent originally had SYS_PTRACE. Subsequent peek/poke checks both the original tracer relationship and current target dumpability. A later dumpability toggle is therefore enforced, rather than merely checking the flag at attachment. Lock ordering avoids retaining the parent relation lock across the Yama check.

This is a targeted initial-user-namespace correction; it does not qualify all ptrace operations, user namespaces, core-dump generation or Linux security-module compatibility. Nine additional native regressions cover state ownership, credential transactions and coherent capture, including contention between actual kernel tasks.

### Unix credentials

Socket/message capture stores real and effective PID/UID/GID values and an immutable supplementary-group owner. `setgroups` constructs a replacement `Arc<BTreeSet<Gid>>` before publication. Fork shares the immutable group owner until replacement. Existing peer/message snapshots never observe later ID/group mutations. Only the current thread's credential owner is captured in production; POSIX clone/fork creates a separate mutable credential object.

The VFS permission request still makes its existing owned group-set copy before inode locks. Credential readers elsewhere receive an immutable shared owner. The old mutable group guard API is removed.

### CPU weight

For an active controller exposing `cpu.weight`, every write returns EINVAL. Reading the default value 100 remains supported; an inactive controller retains its existing absent-file behavior. The scheduler currently lacks group-weight competition, so accepting a write would falsely claim an effect. `cpu.max` remains a separate existing bandwidth mechanism; these changes do not qualify its entire scheduler implementation.

### Anonymous/COW budget: explicit private interface

All cgroup nodes, including the root, expose:

| Attribute | Meaning |
| --- | --- |
| `hepta.anon.max` | Read/write byte ceiling; `max` removes this node's ceiling; default `max` |
| `hepta.anon.current` | Read-only charged physical bytes in this node and its descendants |
| `hepta.anon.events` | Read-only `max N`, counting allocation denials at this node |

A successful allocation charges one PAGE_SIZE unit at the leaf and every ancestor. Each check/update shares an IRQ-safe spinlock with limit writes. Only one lock is held at a time; partial hierarchical reservations are conservative and roll back completely if any ancestor refuses. No blocking operations or heap allocation occur while those locks are held. Limits below current usage are rejected; there is no implicit reclaim or OOM-killer algorithm. Non-page-aligned limits are permitted but actual charges remain whole pages.

The account is a stable field of `Controller`, independent of replaceable Linux controller incarnations. Enabling/disabling `+memory` cannot reset it. A metadata owner travels with the actual OSTD Frame, so the last frame reference refunds every original ancestor, including on physical-allocation failure. Fork shares existing pages without charging them twice; a later COW allocates and charges a distinct frame. Unmap/exit refunds only after the last reference, including retained TLB/RCU references, is gone. `munmap` returning does not imply immediate refund: the VM space defers frame release through `RcuDrop`; callbacks require quiescent points from every CPU. Idle CPUs now report a quiescent state in OSTD `task/preempt::halt_cpu` after the existing atomic-mode check plus explicit preemption-count/IRQ checks (which also cover bootstrap exemptions), before disabling interrupts. Progress relies on the CPU being interrupted and returning to the idle loop; the timed QEMU runs exercise that condition. Previously only task switches reported one, so a normally idle SMP CPU could indefinitely postpone all deferred refunds. This correction is confined to OSTD and uses the same read-side preemption invariant as `processor::switch_to_task`. A genuinely stalled CPU can still delay that release, so no wall-clock refund bound is claimed. The guest checks a bounded sequence of scheduling opportunities and reports the observed delay. Deleting an empty cgroup does not destroy accounts still retained by pages.

These files are administrator-configured cgroupfs extensions, not yet a Hepta/HOS2 grant, lease or revision-bound resource ABI. Native capability discovery must not equate them with full memory isolation.

The ownership cut is the allocating process's cgroup snapshot. Migration affects subsequent allocations; previously allocated pages retain their original owner. An administrator must place a process in its budgeted group **before untrusted work begins**, retain the relevant parent ceilings, and prevent untrusted migration/limit changes. Joining a constrained group does not retroactively charge or limit old pages. A foreign mapping fault serviced by another process is charged to that allocating process; delegated services must not be assumed to retain a caller's budget without an explicit ownership protocol.

Actual allocation hooks are in `vm/vmar/vm_mapping.rs`: private anonymous faults, private VMO mappings beyond their valid bytes, direct private-file COW, and shared fork-page COW. The allocation and metadata code is `fs/fs_impls/cgroupfs/controller/anon.rs`.

**Coverage exclusions:** shared-anonymous VMO, page cache, shared file mappings, page tables, kernel heap/stacks, device/DMA buffers and boot allocations without a current process. These interfaces are not Linux `memory.max`, not total RSS, and not full memory isolation. `memory.max` retains its unsupported rejection. Never advertise this extension as complete cgroup memory isolation or as protection from all memory-exhaustion attacks.

A workload subtree can be capped below a parent ceiling while a sibling recovery subtree retains anonymous-page headroom. This is a verified scoped capacity property, not a global recovery reservation: excluded allocation classes can still exhaust physical memory. The monitor and recovery service must stay outside the exhausted workload subtree: a parent inside that same subtree can itself receive SIGSEGV when its next COW fault needs a page before the child's deferred frees complete. The guest pressure observer therefore remains outside the constrained group. Full recovery isolation requires accounting all allocation classes plus explicit non-workload reserves and bounded reclaim/OOM behavior.

## Verification

Run the full real kernel-mode suite (requires the pinned toolchain, source-built OSDK, QEMU, and pinned vDSO):

```sh
VDSO_LIBRARY_DIR=/absolute/path/to/pinned/linux_vdso \
  python3 support/build/ktest/run.py --crate ostd --crate aster-core --output /absolute/new/evidence/ktest
```

Eighteen new native regressions use real credential owners, real Frames, and actual attribute writers: nine dumpability/transaction/access cases; two socket identity/group lifetime cases; six anonymous allocation, hierarchy rollback, COW, recovery sibling, lifetime/limit validation and unsupported-memory.max cases; one CPU weight rejection case. The tests do not substitute a model counter for real frame allocation. Because the idle progress fix touches OSTD, its complete native suite must also run; VMX/EPT cases that report unavailable hardware in TCG are reported separately as soft skips, not exercised virtualization coverage. The physical allocator's global OOM failure branch is covered by RAII structure, not deliberately forced by exhausting the entire guest.

Run the system-call suite on a freshly built ordinary kernel:

```sh
VDSO_LIBRARY_DIR=/absolute/path/to/pinned/linux_vdso \
  python3 tests/kernel/safety/run.py --smp 2 --output /absolute/new/evidence/safety-smp2
```

It compiles five static probes, builds and boots the kernel, then starts a bounded 512 MiB x86-64 QEMU guest with no host disks/network. The ordinary boot check uses one CPU; the safety guest accepts `--smp 1`, `2` or `4`. It records relevant working-file hashes before/after the build and guest, kernel/initramfs/probe hashes, nonce-bound completion markers, raw serial output and the raw QEMU exit. A dirty working tree is explicitly development evidence, never a committed release attestation. A compile failure, setup-unavailable exit, missing marker, false assertion, source change, timeout or abnormal QEMU exit cannot pass.

The A06 workflow reuses its preceding exact-source ordinary QueryAbi product for both safety guests through `--product-evidence`; the reuse gate validates the original source snapshots, boot/QueryAbi evidence and artifact hashes. No extra ordinary kernel build is added. See [the runner instructions](../../tests/kernel/safety/README.md#ci-reuse).

The probes exercise commoncap denial/allowance, SO_PEERCRED/SO_PEERGROUPS before/after credential replacement, dumpability identity/exec/fork/CLONE_VM/proc lifecycle, and ptrace 0→1→0 transitions. Memory checks touch real anonymous pages, both private-file COW routes and the existing private VMO tail route, fork a process tree, wait for final-reference refund, require SIGSEGV plus a new denial event at the anonymous ceiling, then allocate in a recovery sibling. Four pthread workers concurrently fault/unmap real pages while the main thread changes limits and rejects reductions below a pinned page. Successful standard memory.max/cpu.weight writes are still forbidden. The private VMO tail check validates the existing allocator path; it does not assert Linux beyond-EOF/SIGBUS compatibility. They are **guest-only**: do not execute the cgroup probe directly on a production host.

## Remaining work before full memory isolation

1. Extend the implemented private/COW, VMO/cache, user-table and POSIX-stack
   ownership to remaining heap/slab objects, IPC, delegated/system work, shared
   kernel tables, filesystem metadata and DMA. Preserve original owners through
   their real final references; do not relabel the partial budget `memory.max`.
2. Extend migration/reparenting and shared ownership coverage under bounded,
   reviewed lock ordering, including writeback, asynchronous I/O and devices.
3. Establish fixed global/root/recovery reserve pools that workload allocations cannot consume, including metadata and fault-handling memory.
4. Specify bounded reclaim and OOM behavior, safe limit reduction, cancellation, overflow behavior, and observability under pressure.
5. Extend the bounded multithread/SMP and process-tree coverage to long-running contention, group enable/disable/deletion, shared-memory and page-cache bypass attempts, physical OOM rollback, stalled-CPU RCU behavior, and recovery after adversarial pressure.
6. Only expose a successful standard `memory.max` implementation after its declared Linux-compatible coverage and semantics are implemented and tested. Until then, capability discovery must continue to say it is unavailable.

No kernel rewrite is needed for these changes. The remaining work is substantial resource ownership and scheduling engineering; moving to a new Rust kernel would not remove it.
