# Persistent native guest fixture

This test creates one private 64 MiB ext2 file, boots the actual ordinary
kernel twice with that same file attached by modern virtio-blk, and checks
persistence across an actual SIGKILL of the first QEMU process.
It does not create a Root issuer, task ledger, SQLite replacement or fake
checkpoint.

The first guest mounts its generated `/dev/vda`, creates the real directories
and binds the original root-owned 0700 directory to `/var/lib/hepta-native`.
The probe verifies `/proc/self/mountinfo` column 5, the filesystem/source
fields, and source/bind `st_dev` and `st_ino` equality.
UID 60002 cannot read the Root directory; UID 60001 cannot read any private
state directory.
UID 60002 can write and read its two own 0700 directories.

For each file the actual guest executes write, file `fsync`, rename within
the same directory, then directory `fsync`.
Only after all checks and child processes pass does it emit a nonce-bound
`HEPTA_NATIVE_DURABLE` marker and wait without unmounting.
The runner then sends SIGKILL to its own QEMU child and requires exit `-9`.
The second independent QEMU boots the same kernel and the same disk inode
with `snapshot=off`, reads exact original bytes from the actual filesystem,
and verifies that the kernel boot ID changed.
It then unmounts cleanly.
There are 26 required check records in the first guest and 24 in the second.

```sh
CARGO_HOME=/absolute/source-bound/cargo-home \
VDSO_LIBRARY_DIR=/absolute/verified/vdso \
OSDK_LOCAL_DEV=1 CARGO_BUILD_JOBS=2 \
  python3 -I -B tests/kernel/native-persistence/run.py \
  --output /absolute/new/private-evidence-directory
```

Build cargo-osdk from this worktree with `OSDK_LOCAL_DEV=1` also set at
installation; its source path is embedded in that executable.
Keep its target directory separate from other active worktrees.
The evidence directory must not exist and must be outside the checkout.
The runner does not accept an existing disk path, and never attaches a host
block device or network interface.
Only the generated file receives writes.

The directory retains source snapshots, the compiled probe, kernel, BIOS,
each initramfs and QEMU argument list, original serial logs, disk inode/size,
and the disk SHA256 before the first boot, after SIGKILL and after reopening.
A failed run keeps its disk and logs; use a new output directory for a rerun.
The guest deadline remains bounded at 120 seconds per boot.

See [the native persistence contract](../../../support/kernel-safety/NATIVE_PERSISTENCE.md)
for the paths made available to the original Hepta owner and the limits of
this result.
A successful fixture check is not a successful SQLite or Hepta G2 qualification.
