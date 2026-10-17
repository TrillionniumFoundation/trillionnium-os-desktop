# Candidate Linux ELF rootfs (A04)

`capture.py` stages trusted ELF bytes and their **observed host loader / ldd**
closure, plus glibc NSS modules, UTC, public CA trust, synthetic passwd/group,
localhost and an intentionally unconfigured external resolver. It records every
file's SHA-256 and mode, pinned distro package versions, PT_INTERP and DT_NEEDED.
It never changes the system root, installs packages, invokes chroot, mounts or
writes to production state. The generated `rootfs.tar` has sorted entries,
uid/gid=0 and mtime=0, making it byte-stable for identical source bytes.

The checked-in `manifest-debian13-x86_64.json` freezes **17** observed files,
including the four A04 host-test ELF binaries; `qualified_hepta=false`.
This is **not** a complete bootable rootfs or a real Hepta closure. Guest init
must mount `/proc`, `/dev` and a separate writable `/work` (and set system
clock/entropy); the staging directory's file modes alone are not a readonly
mount. Host Python cases additionally need a separately pinned Python runtime
in the guest. External DNS is intentionally disabled until an explicit,
reviewed resolver is part of the deployment profile.

From repository root on Debian 13 with the pinned gcc, glibc and sqlite3-dev:

```sh
python3 tests/workloads/linux/run.py --output /tmp/a04-reference.json \
  --binary-dir /tmp/a04-binaries --rust auto
python3 support/rootfs/capture.py --root /tmp/a04-rootfs \
  --manifest /tmp/a04-rootfs-manifest.json --tar /tmp/a04-rootfs.tar \
  --binary /tmp/a04-binaries/probe_dynamic \
  --binary /tmp/a04-binaries/probe_static \
  --binary /tmp/a04-binaries/sqlite_dynamic \
  --binary /tmp/a04-binaries/sqlite_static
python3 support/rootfs/capture.py --root /tmp/a04-rootfs \
  --manifest /tmp/a04-rootfs-manifest.json --verify
```

A rootfs image with a different digest is a **different profile**; don't
silently replace checked-in hashes. `ldd` is executed only on trusted/pinned
ELFs and does **not** discover runtime `dlopen` / data/service dependencies.
A real Agentd trace is required before any Hepta rootfs qualification.

## A04 expanded host profile and A01 guest image handoff

The refreshed same-ELF manifest still has 17 files but pins the **expanded**
C probe ELF (31 host-pass cases, 1 Tokio not-run). Repaired **extractable** USTAR digest on our Debian 13 build host:
`df8df2e3cdcd308ef62a59268a4519e2923c9ff78145e46f26a4092725e80797`.
This new tar includes the expanded C ELF; the earlier correctly typed tar
`8c7522ac9a7aed75b7a27d73c8ba71dfd1baf875912b9bf47fcc6effe2d9c746`
remains valid *only for the prior ELF manifest*.
The previously reported `7ee7becc2261ffec1df01bfa770b5d8b248d6982c5566fb477b996af3f0af140`
is **deprecated/broken**: its tar directory entries used `REGTYPE` despite names
ending in /`, so Python `tarfile.extractall()` failed with `NotADirectoryError`.
The pinned **17 file bytes, modes and manifest are unchanged**; only the tar
entry types differ. Rebuild the image from the manifest-pinned source bytes.
Different compiler, distribution or package bytes change the manifest and
require a separately reviewed reference; don't claim they're identical.

`tests/workloads/linux/guest.py pack` checks all staged file modes and hashes
against this rootfs manifest and per-ELF hashes against the actual Linux
baseline. It verifies A01's original initramfs SHA-256, preserves the existing
boot checks, creates a **separate** initramfs, then tests 28 pinned C ELF cases.
The guest's `/tmp` is volatile initramfs storage. No real virtio-blk ext2 S1
power-loss/fsync durability guarantee is claimed. See the Linux workload README
for complete guest execution and serial/errno/result comparison commands.

Host staged-loader verification (not new-kernel or isolated rootfs):

```sh
python3 tests/workloads/linux/staged_rootfs.py \
  --rootfs /tmp/a04-rootfs --manifest /tmp/a04-rootfs-manifest.json \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --output /tmp/a04-staged-result.json
```

Actual Debian 13 result: **28 C ELF passes, 0 failures**, with the staged
interpreter and `LD_LIBRARY_PATH` pointing to the hashed staged libraries.
This verifies the narrow ELF runtime set on that host; it does not validate
new-kernel syscalls, guest boot, Hepta or durable S1 block-media recovery.

## Correct USTAR and strictly verified extraction (real host regression)

The writer now sets explicit `DIRTYPE` and `REGTYPE`. The hardened extractor
rejects links, special files, duplicate/traversal names, non-canonical
file/directory closure, mismatched mode/size/hash and the old malformed tar.
Unlike default `tarfile` data-filter extraction (which may add write bits),
this restores **exact pinned read-only file modes** after verifying bytes:

```sh
python3 support/rootfs/capture.py --extract-verified \
  --tar /path/to/a04-rootfs-fixed.tar \
  --manifest support/rootfs/manifest-debian13-x86_64.json \
  --root /tmp/a04-rootfs-from-tar-NEW
python3 support/rootfs/capture.py --verify \
  --manifest support/rootfs/manifest-debian13-x86_64.json \
  --root /tmp/a04-rootfs-from-tar-NEW
python3 -m unittest discover -s tests/workloads/linux -p 'test_rootfs_tar.py' -v
```

Actual Debian 13 result: **17/17 file hashes and permissions**, real
strict extract roundtrip and **4/4 tar safety regression tests passed**.
No guest mount or S1 durability qualification is implied.


## Stronger host-only isolation: chroot execution

The **corrected** tar was independently verified and executed via
`tests/workloads/linux/chroot_replay.py`. Actual Debian 13 results were 17/17
manifest files verified and 28/28 original C ELF workload cases passing after
UID/GID 65534 transition inside chroot. It resolves the dynamic loader and
SQLite/glibc from the image, rather than relying on the original Linux host
`LD_LIBRARY_PATH`. One disposable `/tmp/a04` area is writable; the captured
ELF and library files remain read-only. chroot does not isolate network, PID
space or the original Linux kernel; do not label this Asterinas or Hepta W1.

## Current expanded binary pins (2026-10-16)

`probe_dynamic`: `36a021aa7877170aedda535fff2a6ab2fc51cdb4b48d04c8c90ff873a40f4324`

`probe_static`: `edd3063a60c3f5c23679de3ab13e71955f7155be619f191468800931d101b078`

The SQLite ELF hashes did not change. **17/17** rootfs files verified,
**28/28** real Linux chroot C cases passed. Rootfs is still only a candidate
for the C probe workload; no complete Hepta service closure or guest mount
has been qualified.
