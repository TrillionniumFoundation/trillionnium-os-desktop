# Timestamp authorization regression

`utimensat`, `futimens` and the legacy time syscalls must authorize the caller
against current inode ownership. An open descriptor is not timestamp authority.
The operation uses the existing inode-owned permission transaction: the decision
and timestamp commit share one metadata lock. Credentials and supplementary
memberships are captured outside that lock; capability hooks run outside it and
retry against fresh inode attributes. `UTIME_OMIT` leaves the field untouched
inside the transaction instead of restoring a stale pre-lock timestamp.

The 38 scenarios cover owner, nonowner, mode bits, primary and supplementary
groups, group precedence, filesystem UID, retained descriptors, FOWNER versus
DAC_OVERRIDE, root without capabilities, omitted timestamps, symlinks, O_PATH,
and all four syscall families. The guest runs every scenario on tmpfs and ext2
(76 cases); failed operations must preserve all three timestamps. Positive
operations must actually change the requested fields and preserve omitted ones.
Three additional inode ktests cover alias ownership change, omitted timestamp
freshness and ext2 persistence after reopening the filesystem.

Run the same semantic controls on Linux in a disposable container:

```sh
python3 tests/workloads/linux/utimens/run_linux_reference.py \
  --output /absolute/path/to/new/linux-evidence
```

The Linux runner uses an already installed Ubuntu image pinned by local image
ID, a new tmpfs, no network and a read-only container filesystem. It mounts only
the compiled probe read-only. The C probe refuses this mode outside a container.

Build a fresh kernel, then run real guest syscalls:

```sh
python3 tests/workloads/linux/utimens/run_guest.py \
  --kernel /absolute/path/to/fresh/kernel.elf \
  --initramfs /absolute/path/to/build/initramfs.cpio.gz \
  --output /absolute/path/to/new/guest-evidence
```

Both runners record source/artifact hashes, commands, complete output and parsed
results. The guest uses a fresh regular-file ext2 image, no host mounts and no
network. `--expect-failure` validates a completed failing negative control; it
does not turn its `passed: false` result into success evidence.

## Backend boundary

Ext2, ramfs/tmpfs/memfd and the generic metadata-backed inode implementations
that already support permission transactions commit timestamp changes under
their existing owning lock. Backends with no such transaction now return
`EOPNOTSUPP` for timestamp changes. This deliberately includes virtiofs, overlayfs,
exfat and procfs templates with dynamic ownership. Their server/stacked/synthetic
ownership contracts need separate ports before timestamp mutation is supported;
a split permission check followed by unchecked setters would preserve a race.
This change does not add mount-idmapped permissions or a live remount lifetime
protocol. The existing two-UTIME_OMIT no-op behavior remains unchanged.

## Validation record (2026-10-23)

Linux reference: 38/38 passed against the real host kernel in an isolated
container. The preceding read-only-only kernel, freshly built from base
`39c1d84ebf854958f5829c0118b0c8b92a6b4926` plus `1dc3b3a2`, completed 76 cases
with 32 failures: unauthorized timestamp changes actually occurred on both
tmpfs and ext2. Its ELF SHA-256 was
`3bc14def2c40b0aabd7dc427745dd8dd7f85005bd3f113a54b11b981827af6af`.
Patched-kernel compilation, the 76-case positive run and new inode ktests remain
pending integration validation; this record does not claim they have passed.

Semantics reference: [Linux utimensat manual](https://man7.org/linux/man-pages/man2/utimensat.2.html).
