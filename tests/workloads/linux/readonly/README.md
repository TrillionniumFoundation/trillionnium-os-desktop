# Read-only existing-file regression

This probe checks real syscalls in an ordinary Asterinas guest. It covers:

- An existing ext2 regular file on an initially read-only superblock: writable
  open, O_TRUNC (including O_RDONLY | O_TRUNC), truncate, xattrs, timestamps,
  O_PATH, and
  unchanged bytes and size. A bind alias with its per-mount read-only flag
  cleared must still respect the superblock's read-only flag.
- An already-open writable descriptor after a serial bind remount: write,
  pwrite, ftruncate, fallocate, fsetxattr and fremovexattr are denied. A separate
  writable alias remains usable.
- MAP_SHARED and MAP_SHARED_VALIDATE: direct write mappings and later
  mprotect upgrades are denied. Private copy-on-write mappings remain usable.
  A write-only descriptor must also reject PROT_NONE file mappings, preventing
  later mprotect upgrades from obtaining read access.
- Positive controls: ordinary writes/truncation, non-root writes and ftruncate
  through a descriptor retained across chmod, and device/FIFO I/O on a
  read-only bind mount.

Build a fresh kernel with `support/build/kernel.sh kernel`, then run:

```sh
python3 tests/workloads/linux/readonly/run_guest.py \
  --kernel /absolute/path/to/fresh/kernel.elf \
  --initramfs /absolute/path/to/build/initramfs.cpio.gz \
  --output /absolute/path/to/new/evidence-directory
```

The runner compiles the probe statically, makes a fresh regular-file ext2 image,
adds the probe to a copy of the initramfs, and boots QEMU with one CPU and no
network. It records hashes, commands, raw serial output and a parsed result.
There are no host mounts or host block-device writes. The probe refuses to run
without the dedicated argument and a guest marker. For the unmodified-kernel
negative control, use the exact same probe with `--expect-failure`; a timeout,
setup failure or incomplete run is never a valid negative control.

## Remaining remount boundary

This change checks the mount and superblock flags at syscall entry. It does not
serialize operations against a concurrent remount, flush dirty pages before a
read-only transition, revoke pre-existing writable shared mappings, or prevent
mprotect on mappings that acquired MAY_WRITE before the transition. The mount
implementation does not yet maintain superblock-wide writer and mapping
lifetimes across bind mounts and mount namespaces. An initial read-only mount
with a stable policy is the supported protection boundary for this regression;
the serial remount cases prove subsequent syscall checks only. Do not treat
these results as qualification of a live writable-to-read-only transition.

The `--retained-map-reproducer --expect-failure` mode is a separate negative
reproducer for that remaining boundary: it retains a writable shared mapping,
requests a read-only remount, and checks whether a subsequent store changes the
file. Its result must remain `passed: false` while the gap exists; an exit code
of zero from the runner only confirms that the expected failure was reproduced.

## Recorded native validation (2026-10-23)

The exact base `39c1d84ebf854958f5829c0118b0c8b92a6b4926` and the patched
source were each freshly built with the pinned nightly toolchain and booted
with QEMU 8.2.2, TCG, one CPU, 512 MiB and no network. Both runs completed
all 68 cases and exited through the guest completion path. The base failed
35 cases and changed the read-only ext2 image. The patched kernel passed
68/68, with the entire disk hash unchanged. A separate retained-mapping
reproducer still failed as expected: a store after remount changed the tmpfs
file to byte 88. This is an open blocker, not a passing protection test.

Artifact identities (raw run records retained by the audit):

- Base ELF SHA-256: `87f24bb3cde7b2638b29adce44d0987c8bb6414a698e6e6b8caa76dec882de7b`.
- Patched ELF SHA-256: `3bc14def2c40b0aabd7dc427745dd8dd7f85005bd3f113a54b11b981827af6af`.
- Kernel patch SHA-256: `3f527707c2bcdde53f504f388f819881f54b23374910fe6aa4b594b90e4469cf`.
- Probe source SHA-256: `11b3a0cee4b5132958420610164be9ed8969326bd2de9a2f5766a5152d4246ab`.

Six mmap descriptor/protection controls also passed against the host Linux
kernel using an unprivileged temporary file. Pinned rustfmt and diff whitespace
checks passed. These results qualify only the scope above.
