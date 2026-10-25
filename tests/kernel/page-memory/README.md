# Real physical page budget probes

This suite boots an ordinary x86-64 kernel with 2 or 4 CPUs and tests `hepta.page.*` through actual user syscalls. It is development validation of private/COW, VMO, user page-table and POSIX task-stack pages, not Linux `memory.max`, all-memory isolation, production resource authority or hardware qualification.

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

## M3 user page-table coverage

The same guest probe now checks sparse 512-GiB-separated virtual branches,
actual three-node table growth, fork root and partial-table ENOMEM with cleanup,
exec root rejection preserving the old image, mremap preflight ENOMEM preserving
source bytes followed by a successful retry, migration keeping old nodes on their
original owner while new nodes charge current membership, and SIGSEGV when an
already-committed shared data page cannot acquire its page tables. The four
concurrent workers use sparse 2-MiB-separated ranges while the observer adjusts
the ceiling. The 4096-page stress limit includes retained empty page-table nodes;
negative admission checks use exact ceilings separately.

See [the page-table design](../../../support/kernel-safety/PAGE_TABLE_MEMORY.md)
for ownership, partial allocation and TLB/RCU/active-CPU refund limits. These tests
do not qualify Linux memory.max or a physically reserved recovery pool.

## M4 POSIX task-stack coverage

The observer prefaults independent user stacks outside the workload and uses
`clone(CLONE_VM | SIGCHLD)`, so the child shares the existing user page tables.
A live child measures the real `kernel_stack` increment and verifies zero new
user-table charge. Each negative ceiling is exactly one physical page below
that measured stack requirement: first at the leaf, then at its ancestor.
The probe checks ENOMEM, no child entry, no PID charge leak, full leaf rollback
and an event only at the denying account. A sibling creates and releases a
real task while the original ancestor remains capped. Four live children then
hold four distinct stack segments under an exact ceiling, a fifth is denied,
and all final frame and PID charges must return to baseline.

The earlier fork-root, partial-table, exec, mremap and pure-table fault
negatives retain their original ceilings. They must fail before stack
allocation; increasing their budgets to accommodate a stack would weaken the
original checks. See [the stack design](../../../support/kernel-safety/KERNEL_STACK_MEMORY.md).

The M4 probe also creates a real CLONE_THREAD task in the same process,
requires an additional live PID charge and the same actual stack-frame count,
and waits for its final refund. Both leaf and ancestor negatives repeat with
CLONE_THREAD so the precharged thread-PID reservation's error path is exercised,
not only the new-process path. PID checks first enable the controller and
require an actual creator/live-child count; unavailable attributes cannot pass
as equal sentinel values. Group deletion retries only EBUSY while actual
scheduler switches settle the observer's migration CPU lease.
