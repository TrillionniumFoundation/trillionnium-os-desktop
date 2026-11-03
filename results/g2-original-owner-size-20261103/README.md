# Original G2 owner: retained size rejection and resource-profile review

## Result and scope

The original Hepta G2 owner compiled and its original packaging script completed. The packaged executable did **not** pass the existing `g2-trusted-daemon` image profile. This directory preserves that failure, the preceding packaging failure, and read-only ELF diagnostics. No original-owner guest execution is established by these records.

The execution source is Desktop `4dcd02d8058005b92b75b4e997ec4de08833e01d` (tree `504d5850df75de8697dfb56572cc8745dcc59f13`) with Hepta `a39a0871d9601ffccb5e0d95d8f39d54b3a63360` (tree `e03f9b3eca364222029298496d3e4f1f5e1bf5de`). The parent of this evidence-only commit is `bf15a519e9192b063071e8b9b61ef3319bed416e`; that parent is an archival base, not a substitute execution identity.

The v3 result records `built=true`, `packaged=true`, `source_inputs_unchanged=true`, and `static_profile_passed=false`. Native execution, original-role runtime behavior, persistent CPU effects, recovery, G2 completion, and production qualification remain false. The source features, original release profile, and original size limits were not changed to obtain this result.

## What actually ran

Main durable job `1a1a28bafa9-96a-741e` ran from `2026-11-03T17:54:16.561080Z` to `2026-11-03T18:00:03.477961Z`. Its output directory is `/data/trill-organ-20261103-f1-build/g2-owner-build-v3`.

The original entry is `codex-rs/hepta-agentd/src/bin/hepta-g2-native-owner.rs`. Its SHA-256 is `802d736f5f36e0181b49f44b503802339a56f2309a9b39a3a2ae6ca68f668e40`. That small entry delegates to original `native_g2_entry` modules; the builder's full before/after source snapshots bind the transitive source, rather than treating the entry file alone as the implementation.

The actual command used Rust 1.96.0, original Cargo.lock, and `cargo build --locked --offline --release --target x86_64-unknown-linux-gnu -p codex-hepta-agentd --bin hepta-g2-native-owner -j1`. The existing release profile uses four codegen units, thin LTO, line-table debug information, and no Cargo stripping. The unchanged flags were `-C target-feature=+crt-static -C relocation-model=static -C link-arg=-no-pie`. The lock SHA-256 is `5bd3faaf16a79eb12bcdcb89054e93da388bbd858f36439b9d6bcfb72f77d522`; the original toolchain manifest SHA-256 is `e8b379eaa492bf59d35187de269afd1c4f55d85e0322f6fea32803a3fec1a380`.

The warm-cache Cargo command exited 0 in 2.959 seconds; the original Hepta archive/strip script exited 0 in 4.762 seconds. Source snapshots and evidence collection account for additional wall time. The subsequent static inspection raised `ValueError: static initial ELF size out of bounds`.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Original unstripped owner | 102,836,712 | `b16eb4663f5b6661314091af5ad5ec40c5de65b0ae3f3f5544a5700b6ad9c4ac` |
| Original packaged owner | 20,138,584 | `6ce96a0785b2cbb51bb71fabb2973c1e04d93e213d56694b42b4d717ed55a454` |
| Existing file budget | 8,388,608 | Fixed legacy profile |
| Existing mapped LOAD budget per image | 16,777,216 | Fixed legacy profile |

The preceding v2 build used Desktop `e1f3898ff6c2181a6da27de9f9b0f5d1ec03123d` and the same Hepta source. Its actual original release compilation exited 0 after 5,554.231 seconds (about 92 minutes 33 seconds). Packaging then failed because the builder had frozen its private packaged copy to mode 0555 before invoking in-place `strip`. The raw permission error and v2 result are retained here. The v3 runner keeps only that private copy writable during packaging, then restores 0555 in `finally`; the original compiler output and unstripped frozen copy remain unchanged. The v2 and v3 unstripped SHA-256 values are identical.

The separate ordinary-user packaging regression was run by UID/EUID/GID/EGID 1000 against a private copy of a normal host ELF. Both normal success and failure lifecycle checks passed. That helper regression is not an original-owner or G2 execution result. The implementation is in the [published builder at 4dcd02d](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/4dcd02d8058005b92b75b4e997ec4de08833e01d/tests/workloads/hepta_cpu_control/build_original_entry.py).

## Independent ELF size diagnosis

The file-size refusal occurred first, so the original static inspector did not proceed to award a LOAD result. Separate read-only `readelf`, `size`, and `nm` commands on the same SHA-bound artifact establish the following layout.

| PT_LOAD | Virtual address | File bytes | Memory bytes | Page-rounded mapped bytes |
| --- | ---: | ---: | ---: | ---: |
| Read-only | 2,097,152 | 4,724,464 | 4,724,464 | 4,726,784 |
| Read/execute | 6,825,728 | 15,318,448 | 15,318,448 | 15,323,136 |
| Read/write | 22,148,272 | 37,240 | 39,760 | 40,960 |
| Read/write | 22,189,632 | 49,088 | 74,568 | 77,824 |
| Total | | 20,129,240 | 20,157,240 | **20,168,704** |

The current artifact therefore exceeds both original budgets. Reaching the file budget requires removing 11,749,976 bytes, approximately 58.35% of the packaged file. The 102 MB unstripped file is not the file tested by this budget; the original stripping step has already reduced it to 20,138,584 bytes.

The packaged `.text` is 15,317,833 bytes and `.rodata` is 2,270,348 bytes. `.gcc_except_table`, `.eh_frame_hdr`, and `.eh_frame` together occupy 2,447,940 bytes. Removing all of those sections would still not close the file-size gap, and changing panic/unwind behavior is not an approved substitution for the original owner's behavior.

Read-only text-symbol interval grouping attributes roughly 2,051,039 bytes to `codex_hepta_memory`, 1,360,198 to `starlark`, 662,286 to `codex_hepta_agentd`, and 336,332 to the native owner entry namespace. Leading demangled names are not a complete dependency accounting method: generic code and C symbols can be unattributed, aliases overlap, and section padding and nonsymbol bytes remain. The raw grouping records its interval-union method and caveats.

Several large logical functions have distinct emitted bodies: `ProductionDurableWriter::dispatch_final_use_target_with_owner` has three leading bodies of 82,856, 81,222, and 81,078 bytes; original store verification and owner execution also have repeated large bodies. This motivates source review of monomorphization and assembly boundaries. It does not establish that any of those bodies, Starlark, the original durable writer, outbox, or SQLite can be removed while preserving the original contract.

## Why the legacy budget is specific to this loader

The [trusted initial loader](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/4dcd02d8058005b92b75b4e997ec4de08833e01d/kernel/asterinas/kernel/core/src/process/program_loader/elf/trusted_initial.rs) describes a deliberately narrow, compile-time selected G1-c image profile. The G1-d and `g2-trusted-daemon` features inherit that loader and its 8 MiB file / 16 MiB mapped limits. Ordinary `exec` uses the general ELF loader. These limits are not a demonstrated universal maximum for Asterinas Linux executables.

The trusted path embeds `EXPECTED_ELF` in the kernel, reads the opened executable exactly once into an immutable snapshot, rejects extra/truncated/different bytes, and drops the opened file. Each role gets independent RAM-backed LOAD VMOs. The loader checks static ET_EXEC structure, segment bounds and alignment, nonoverlap, executable entry, readable mappings, and absence of writable-executable mappings. It creates stack, heap, boot page, and VDSO before reading mappings back and sealing the initial image. A versioned experiment must preserve all these bindings.

The [four-role bootstrap](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/4dcd02d8058005b92b75b4e997ec4de08833e01d/kernel/asterinas/kernel/core/src/process/process/init_proc/trusted_daemon.rs) uses one original snapshot to prepare Root, Manager, Workload, and Recovery sequentially. Each maps the same owner executable privately. Root is the actual PID 1 parent; kernel boot pages determine role and grants. Workload UID 60002 remains distinct from protected Host UID 60001. Splitting this into four independently supplied executables would require a new image/role/generation design, rather than being a packaging-only optimization.

The successful original CognitiveStore lifecycle uses the ordinary-OS profile, a 4,096 MiB guest, the original `dev-small` fixture and its libraries. Its 31,484,800-byte fixture and 10 lifecycle checks do not satisfy or supersede this separate trusted G2 profile. Its successful legacy writer/WAL checks also do not establish original G2 authority recovery.

## Fixed 512 MiB guest: image accounting and remaining gap

Let F be the packaged file length, L the sum of page-rounded LOAD ranges per role, S the largest page-rounded LOAD range, P one 4 KiB boot page, and T the 8 MiB initial stack mapping. The concrete artifact has F = 20,138,584, L = 20,168,704, and S = 15,323,136 bytes.

The kernel-embedded bytes and one immutable snapshot coexist. The [launcher](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/4dcd02d8058005b92b75b4e997ec4de08833e01d/kernel/asterinas/kernel/core/src/process/process/init_proc/trusted_launcher.rs) retains that snapshot for original-owner successors; it is not dropped after boot. Four private LOAD images account for 4L. During final segment verification, one `expected` vector and one `actual` readback vector coexist, accounting for up to 2S while the four images are already present. Role loading is sequential, so four simultaneous pairs of verification buffers are not assumed.

| Known image-related component | Bytes |
| --- | ---: |
| Embedded original ELF + shared snapshot: 2F | 40,277,168 |
| Four independent private LOAD images: 4L | 80,674,816 |
| Largest simultaneous expected + readback buffers: 2S | 30,646,272 |
| Four mapped boot pages: 4P | 16,384 |
| Image/verification subtotal | **151,614,640 (144.59 MiB)** |
| Four initial stack capacities: 4T | 33,554,432 |
| Subtotal if all stack pages are touched | **185,169,072 (176.59 MiB)** |

This is a payload/capacity calculation, **not a measured whole-guest peak or an allocator reservation**. Stack VMOs are initially populated on access; 32 MiB here conservatively counts full stack touching, not observed initial RSS. Byte vectors and the embedded file also incur allocator/page rounding and metadata not represented by their byte lengths.

The calculation excludes kernel text/data and other embedded inputs; retained initramfs and extracted executable/file cache; VDSO; page tables, slabs, VMO metadata and allocation fragmentation; kernel/task stacks; owner threads, heaps, SQLite/WAL and caches; controller/history/device buffers; and allocation overlap during successor retirement. The existing successor path checks previous children have been reaped before preparation, but this arithmetic alone is not evidence of a whole-system physical-memory bound across all transitions.

Current workload admission is a 64 MiB selected-user-frame family budget and a 256 MiB virtual-address-space limit. Root, Manager, and Recovery use `allocate_initial_process(..., None)` and have no equivalent fixed account in this path. The [user-memory implementation](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/4dcd02d8058005b92b75b4e997ec4de08833e01d/kernel/asterinas/kernel/core/src/vm/user_memory.rs) expressly excludes several kernel allocation classes. Existing accounting therefore cannot be described as a four-role aggregate RSS cap or a production global reserve.

A future experimental qualification should record kernel allocator free-memory low water and slab usage, each role's selected-frame current/peak/denial counts, and process RSS with its accounting limitations, at snapshot creation, each completed load, buffer verification, final sealing, original writer/outbox startup, both finite runtime cases, and successor retirement. `/proc/meminfo` currently reports allocator free bytes as both MemFree and MemAvailable; it is not a reclaim estimate. Sampling alone may miss a transient peak, so allocation-path low-water/peak counters or explicit phase observations are needed. New admission controls require separately reviewed ownership/refund behavior and must not call selected-frame limits a complete kernel memory guarantee.

## Two source-review options

### A. Keep the legacy 8 MiB / 16 MiB profile

Review an explicitly named original-owner release profile or source-level component boundary while retaining original writer, outbox, SQLite, target, authority, and panic semantics. Compiler size settings and monomorphization boundaries may be assessed in a new manifest; changed settings must not be recorded as the unchanged original release. Shared source components should remain the same implementation used by Agentd, rather than a copied fixture.

This route preserves the existing loader envelope. Its cost is a substantial reduction target (58.35% of file bytes), possible cross-crate refactoring and semantic regression risk, plus new builds and runtime qualification. The measured 92-minute original release build is useful scheduling evidence, not an estimate that any proposed optimization will succeed. The symbol inventory provides investigation targets but no demonstrated reduction sufficient for this route.

### B. Add an exact, separately versioned original-owner image experiment

Create a distinct profile for this source-reviewed original owner. Bind it to the Hepta source/tree, original entry and lock identity, complete packaged SHA-256, exact F/L/S values, role count, and the kernel's independently checked embedded bytes. Do not accept file/mapping budgets from arbitrary command-line or review JSON input. Existing G1-c, G1-d, and `g2-trusted-daemon` selectors keep their 8/16 MiB limits and refusal results.

The first candidate should use the measured F/L/S values above rather than inventing a 24/32 or 32/32 MiB guarantee. A separately approved envelope could later replace these exact values, with its own source/version review and new results. Even a 24/24 MiB envelope would imply up to 224.02 MiB for the corresponding embedded/snapshot/private-image/verification/full-stack subtotal before the omitted allocations, so selecting a round envelope does not prove a 512 MiB guest has sufficient margin.

The concrete change surface is a new explicit feature/selector in the kernel and build support; kernel-side fixed original-owner constants and digest check while preserving the loader's one-read/private-RAM/readback/sealing behavior; host inspector and source-review cross-checks for the same fixed descriptor; and separate build/runtime manifests, schema/tests, and runbook. The original four-role bootstrap, UID/capability boundaries, source snapshots, and hashes remain binding. Tests must show the original file still fails the legacy profile and that arbitrary image/profile mismatches are refused by the new selector, without executing over-budget images.

This route preserves the measured original owner's functionality and has a smaller semantic change surface than removing large parts of its dependency graph. It adds a new experimental qualification obligation: kernel build, exact-profile admission, original writer/outbox/store/runtime lifecycle, finite recovery cases, and measured 512 MiB resource headroom. It does not turn the retained legacy failure into a pass. No new kernel compilation or guest execution is represented in this archival directory.

## Provenance and review boundary

`evidence-index.json` records the complete bytes/SHA-256 of each raw file and its main-host source path. `result.json`, `previous-packaging-failure.json`, and `previous-packaging-error.txt` are original runner outputs; `load-and-largest-symbols.json`, `section-sizes.txt`, and `text-symbol-groups.json` are original read-only diagnostic outputs. Their whitespace is retained. `memory-budget-derived.json` and this README are derived review material, explicitly separated from executed receipts.

All old failures remain failures. `native_execution_verified`, `g2_complete`, production qualification, whole-guest peak verification, and global memory reserve remain false. An implementation or result for a future image profile must be recorded under its own source and profile identity.
