# G2 bounded native Agentd loader stage

This default-off loader stage prepares the original Hepta static executable for
native qualification. It does **not** establish that Root, Agentd, Tokio, SQLite,
HOS2 recovery or durable history have run successfully on Asterinas. The final
native executable and guest qualification are separate inputs and evidence.

## Profile and development entry points

Select `HEPTA_G2_NATIVE_AGENTD=1` and a reviewed
`HEPTA_TRUSTED_INITIAL_ELF` when calling `support/build/kernel.sh kernel`.
The wrapper freezes the input with `prepare-trusted-image.py --profile
g2-native-agentd`, enables the kernel facade/core feature, and records a fixed
3072 MiB build configuration. The three wrapper profile flags are mutually
exclusive; the Cargo feature intentionally depends on `g1d-trusted-control`.
`run_kernel` remains unavailable for trusted profiles: qualification must use a
dedicated runner that verifies the exact inputs and real guest observations.

The G2 build manifest uses schema `hepta-g2-trusted-initial-v1`. It records the
frozen whole-file hash, measured ELF layout, fixed limits, 3072 MiB guest memory,
and a separate 256 MiB maximum kernel artifact size. The latter is a runner
artifact admission limit, not a claim about physical kernel usage. Its
`qualification` field is always `loader-stage-not-native-qualified`; a successful
freezer or build cannot turn it into application evidence.

Candidate limits, pending the final native executable measurement:

| Item | Bound |
| --- | ---: |
| Complete ELF file | 224 MiB |
| Sum of page-rounded LOAD mappings | 224 MiB |
| LOAD segments / program headers | 16 / 64 |
| Static TLS memory / alignment | 64 KiB / 4096 bytes |
| Initial workload role address space | 256 MiB, unchanged |

There are no caller-selected limit overrides. Review and commit any necessary
bound change with the final executable measurements. Existing G1c/G1d retain
their 8 MiB file / 16 MiB LOAD bounds, original loader path and 512 MiB build
configuration. Ordinary builds do not enable any trusted profile. Exact feature
insertions are enumerated in `verify-source.py`; upstream lock files, package
versions and other manifest bytes remain checked.

Core code is in `kernel/asterinas/kernel/core/src/process/program_loader/elf/`:
`g2_profile.rs` owns allocation-free stream equality, LOAD chunk reconstruction
and extra ELF checks; `trusted_initial.rs` applies them to the real file, RAM
VMOs and final VMAR. The rest of the original role construction and control
device authority are unchanged.

## Trust transaction

1. Read the already-opened file in at most 4096-byte requests. Compare every
   returned byte with the same offset in the kernel's immutable `include_bytes!`
   manifest, stored in an eight-byte-aligned static wrapper for the existing
   ELF64 parser. This does not allocate a second file-sized buffer. Short reads
   advance only by their actual count. Zero before the
   expected length, an invalid read count, differing bytes, IO failure or a
   nonempty exact-EOF probe prevent admission.
2. Only after complete comparison and EOF succeed, drop the file and retain a
   private reference to the immutable manifest. This reference is an equal copy
   of the entire sequence actually read. This does not assert that a concurrently
   mutable inode had that complete content at any single instant. Neither later
   inode mutation nor a path, UID or userspace digest can change the loaded bytes.
3. Validate static x86_64 ET_EXEC layout. In addition to the original LOAD range,
   bounds, readable pages, executable entry, W^X and nonoverlap checks, G2 requires
   the **complete**, eight-byte-aligned program header table inside the first
   readable LOAD selected by the actual auxiliary-vector helper, rejects dynamic
   loading and executable-stack requests, and checks an optional PT_PHDR against
   the actual table mapping. A unique PT_TLS must have bounded size/alignment and
   its initialized template must have the matching file-to-virtual mapping in a
   readable LOAD. Its per-thread BSS is not required to occupy a LOAD.
4. Create independent RAM VMOs for each of the three roles. Reconstruct every
   LOAD in 4096-byte chunks, including the original leading file-page prefix,
   file bytes, BSS zeros and final-page zeros. All LOAD pages are still eagerly
   written. This stage does not introduce shared executable VMOs or lazy input
   reads.
5. After boot page, vDSO, stack and heap setup, check complete actual mapping
   coverage and permissions, then read back and compare every LOAD byte in small
   chunks. Verify the boot page and seal the real VMAR before returning the
   existing one-use image token. No initial role runs before all three images,
   grants and original startup claims are prepared.

The maximum LOAD reconstruction buffer is one page; the final LOAD comparison
uses two pages. Other metadata allocations and the boot-page comparison remain
small ordinary allocations. This is not a general kernel allocation-failure
solution: remaining Box/Vec metadata allocations can still fail through the
global allocator. Existing fallible VMO/map/read errors propagate and prevent
initial role publication.

G2 image commit/reject messages use `[hepta-g2]`. Existing role commit and control
activation messages still use `[hepta-g1d]`, because that code and authority
transaction are reused without change. A runner must check exact sequencing and
the same kernel manifest across positive and modified/truncated-file boots.

## Memory accounting and startup limits

For page size P, let F be full ELF bytes, M the sum of each LOAD's
`ceil((vaddr + memsz)/P)*P - floor(vaddr/P)*P`, and L its largest mapped segment.
Before this stage the loader retained an F-sized contiguous snapshot and up to
two L-sized contiguous comparison buffers. G2 removes these transient copies;
it does **not** remove the embedded F bytes, the initramfs/rootfs copy, or the
three independent M-sized physical LOAD images. The compressed boot initrd,
kernel baseline, frame metadata, page tables, kernel/user stacks and application
runtime remain additional memory. Per-frame metadata is currently 64 bytes.

One old original Agentd build measured F=217206752, M=217251840 and L=171724800
bytes (SHA-256 `4742ebee2730f232a03fd74414efd3435e5f4f03f16f0d73828134cc8d8c936f`).
It is **not the final native role-dispatch executable**. At those sizes, three
LOAD images alone consume 621.5625 MiB. `3M + 2F` is about 1035.85 MiB before
the additional components above; it is an estimate, not measured peak RSS or a
reservation. The old snapshot/comparison buffers added another 534.68 MiB and
each large allocation required finding a 256 MiB buddy block. Small chunks
remove those particular large allocation requirements.

Each role maps the complete executable even if its selected branch is simple.
The unchanged workload RLIMIT_AS leaves only about 40.81 MiB after these LOADs
and its 8 MiB initial virtual stack, before vDSO/boot/heap/TLS and later mappings.
Dispatch by the sealed boot-page role before initializing unnecessary application
subsystems. Measure the final executable rather than silently raising that limit.
RLIMIT_AS is virtual address admission, not a complete memory controller. Initial
loading happens in a kernel task; this stage supplies no physical workload cap,
recovery reserve, heap accounting or standard `memory.max` qualification.

For static musl, the loader supplies PHDR/PHNUM/PHENT, PAGESZ, ENTRY, RANDOM and
SECURE auxiliary entries; the normal startup path supplies console descriptors.
The [musl 1.2.5 TLS startup source](https://git.musl-libc.org/cgit/musl/plain/src/env/__init_tls.c?h=v1.2.5)
reads the TLS template through those program headers, allocates per-thread memory
and establishes the thread pointer. This explains the mapping checks; it does
not prove the actual linked libc, Rust TLS, threads or application have run.
ET_EXEC/no interpreter, thread-local isolation, libc startup and actual runtime
syscalls must still be checked with the final native binary. VMAR sealing remains
in force, including its restrictions on executable mappings and mremap aliases.

## Validation

Run host build/ELF cases in `support/build/tests/test_g2_build_profile.py`, including
under Python `-O`, and rerun the original G1c/G1d build tests. The pure Rust
helpers have tests runnable on the host and in the actual core kernel test suite:
short reads, all-byte/tail/EOF mismatch, file changes after reads, LOAD prefix and
zero padding, malformed tables, TLS template/BSS and static TLS-base checks.

Native kernel tests and a G2-feature kernel compilation are required before this
loader stage is delivered. Final application qualification additionally needs
the actual reviewed Root/Agentd executable, source pair, same-kernel file negative
boots, exact three-role ordering, and real HOS2/Root/SQLite recovery observations.
No C probe, host proxy, host-only test or build manifest substitutes for that run.

The first actual 207 MiB input run exposed an alignment assertion in the existing
`xmas-elf`/`zero` parser before any image was committed: an `include_bytes!` slice
alone did not guarantee the required alignment. The G2 aligned static and the
independent host/kernel PHDR-offset check fix that issue without restoring a
file-sized heap copy. The original failed run remains recorded separately.

After that fix, the full native core suite passed 324 tests, including nine G2
helper cases; 20 original/G2 host build cases passed normally and under Python
`-O`. A kernel containing the measured old Agentd above was 225988800 bytes
(SHA-256 `167c8229fbb92a733c758dfe536dc436beb4aa7228877421eca60883511370e4`).
Scanning the final kernel found exactly one complete copy of the 217206752-byte
ELF, and its aligned static symbol satisfied the eight-byte alignment.

Four ordinary QEMU TCG boots used that same kernel and 3072 MiB RAM. The exact
file produced three image commits, three role commits and control activation in
that order. All three processes entered the real Rust program and reported the
expected missing `HEPTA_FLEET_ROOT` configuration; the init process then exited,
ending the guest. Separate changed-last-byte, one-byte-truncated and appended-byte
files were each rejected before any image, role or activation. These are large
loader/basic-startup results for the **old plain Agentd** only. They do not qualify
the final native role dispatcher, Root lanes, durable SQLite writes, HOS2 reply
loss/recovery, or reboot history. The final executable still needs its own layout
measurement and complete application run against the committed source pair.
