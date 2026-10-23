# Read-only existing-file regression

The current default probe checks 57 real syscall cases in an ordinary Asterinas
guest with a stable read-only mount policy:

- Initially read-only ext2: writable open, O_TRUNC, truncate, xattrs and timestamp
  changes are rejected; bytes, size and the entire disk image stay unchanged.
- MAP_SHARED and MAP_SHARED_VALIDATE write mappings and mprotect upgrades are
  rejected. Private copy-on-write and O_PATH remain usable. Write-only descriptors
  cannot acquire read authority via PROT_NONE followed by mprotect.
- Attempts to weaken the initial read-only mount or strengthen a live writable
  mount fail with EOPNOTSUPP. A failed request preserves the old write policy.
  Remounts retaining the same read-only state remain supported.
- Positive controls include ordinary writes, a nonroot descriptor retained
  across chmod, and device/FIFO I/O through the initially read-only filesystem.

Build a fresh kernel, then run:

```sh
python3 tests/workloads/linux/readonly/run_guest.py \
  --kernel /absolute/path/to/fresh/kernel.elf \
  --initramfs /absolute/path/to/build/initramfs.cpio.gz \
  --output /absolute/path/to/new/evidence-directory
```

The runner builds a static probe and a fresh regular-file ext2 image, adds special
file inodes with debugfs inside that image, and boots QEMU with one CPU and no
network. It never mounts or modifies host block devices. Exact hashes, commands,
raw serial output and complete parsed results are retained. The C probe requires
a dedicated argument and a disposable-guest marker. A negative control can use
`--expect-failure`; incomplete runs, setup failures and timeouts are not accepted.

## Live transition boundary

Changing either the per-mount or filesystem RDONLY state on a live mount is
explicitly unsupported. The remount implementation rejects it before any
filesystem callback or flag update while holding MountTopology's write lock.
No writable mapping is revoked and no dirty page is flushed by the failed
request. This closes false-success behavior; it does not implement a dynamic
read-only transition. Full support needs a shared writer/mapping lifetime and
writeback protocol across aliases, namespaces and filesystem owners.

The separate [remount regression](../remount/README.md) checks retained writable
mappings, MAY_WRITE upgrades, dirty data, bind aliases and a forked mount
namespace. `--retained-map-reproducer` also retains the original one-case
reproducer; the current policy must make it pass by rejecting the transition.
`--legacy-remount` is only for historical kernels and reproduces the earlier
68-case syscall-gate test. It is not the current acceptance mode.

## Historical validation of syscall gates (2026-10-23)

The exact base `39c1d84ebf854958f5829c0118b0c8b92a6b4926` and the patched
source were each freshly built with the pinned nightly toolchain and booted
with QEMU 8.2.2, TCG, one CPU, 512 MiB and no network. Both runs completed
all 68 cases and exited through the guest completion path. The base failed
35 cases and changed the read-only ext2 image. The patched kernel passed
68/68, with the entire disk hash unchanged. A separate retained-mapping
reproducer still failed as expected: a store after remount changed the tmpfs
file to byte 88. That evidence motivated the subsequent fail-closed remount policy; it did not
qualify a safe live transition.

Artifact identities (raw run records retained by the audit):

- Base ELF SHA-256: `87f24bb3cde7b2638b29adce44d0987c8bb6414a698e6e6b8caa76dec882de7b`.
- Patched ELF SHA-256: `3bc14def2c40b0aabd7dc427745dd8dd7f85005bd3f113a54b11b981827af6af`.
- Kernel patch SHA-256: `3f527707c2bcdde53f504f388f819881f54b23374910fe6aa4b594b90e4469cf`.
- Probe source SHA-256: `11b3a0cee4b5132958420610164be9ed8969326bd2de9a2f5766a5152d4246ab`.

Six mmap descriptor/protection controls also passed against the host Linux
kernel using an unprivileged temporary file. Pinned rustfmt and diff whitespace
checks passed. Those results belong to the earlier 68-case source and its stated syscall-only
scope. The current default 57-case stable-policy probe has a different hash;
its patched-kernel validation is pending integration.
