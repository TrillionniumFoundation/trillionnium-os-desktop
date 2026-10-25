# Real physical page budget probes

This suite boots an ordinary x86-64 kernel with 2 or 4 CPUs and tests `hepta.page.*` through actual user syscalls. It is development validation of private/COW and VMO pages, not Linux `memory.max`, all-memory isolation, production resource authority or hardware qualification.

`probe.c` checks shared anonymous pages, memfd, cross-group reuse, last-reference refunds, ext2 cold cache reads and shared writes, truncate/cache lifetime, exact-budget ENOMEM/SIGSEGV and denial events, plus actual sibling recovery allocations. The observer remains outside the exhausted group. The only disk is a generated 16 MiB ext2 fixture attached with snapshot writes. No host block device, personal data or network is exposed. Do not execute the probe directly on the host.

Use the pinned toolchain, system GCC 13, QEMU, `/usr/sbin/mke2fs`, a source-built local OSDK, and the pinned vDSO:

```sh
CARGO_HOME=/absolute/worktree-specific-cargo-home \
VDSO_LIBRARY_DIR=/absolute/pinned/linux-vdso \
python3 tests/kernel/page-memory/run.py --smp 2 --output /absolute/new/evidence-smp2

python3 tests/kernel/page-memory/run.py --smp 4 \
    --reuse /absolute/evidence-smp2 --output /absolute/new/evidence-smp4
```

Build `cargo-osdk` with `OSDK_LOCAL_DEV=1` from this exact worktree: it embeds source-directory paths. Reusing a binary compiled in a different checkout can mix dependency sources. `--reuse` accepts only a completed successful run whose source snapshots, ordinary artifact hashes and raw nonce-bound guest evidence match, and uses the same QEMU binary. Both runs retain raw output, fixture inputs, kernel/initramfs/probe hashes and current working-source fingerprints. No setup failure is converted into a passing skip.

`python3 -I tests/kernel/page-memory/test_runner.py` and the same command with `-O` verify evidence parsing and guest packaging without running any probe on the host. Those host checks do not replace the real guest runs. Run the complete `aster-core` native suite and the preceding [safety suite](../safety/README.md) as regressions.

See [ownership, failure and recovery boundaries](../../../support/kernel-safety/PAGE_MEMORY.md) for allocation coverage and exclusions. In particular, filesystem cache pages can remain charged after the creating process exits; mapping removal alone is not a refund guarantee.

The observer prefaults its stack before fork: otherwise a child may first populate inherited VMO backing that the observer still retains. Refund checks compare new allocations with retained-cache baselines, require private child frames to return to zero, and separately verify the exact last-reference releases of shared anonymous mappings and memfd. Unmount is not assumed to evict every global block metadata page.
