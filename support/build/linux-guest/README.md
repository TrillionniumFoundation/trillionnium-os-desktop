# A04 same-ELF guest diagnostics

`isolate.py` runs the 28 C ELF cases from A04 PR #8 commit
`16d672881909a5a9197d82126032b7d962db7d76` in separate A01 guests. It verifies
the fixed A04 source blobs, the exact 17-file rootfs, and the original accepted
A01 kernel/initramfs/SeaBIOS before launch. It calls A04's original pack, serial
parser and QEMU command APIs. It never edits A04 or kernel source.

This is profile `a01-a04-isolated-case-v1`, separate from the original A04
28-case sequential suite. Each selected case gets a new 1-vCPU, 512-MiB,
q35/TCG guest with no network or host data disk. At most two guests run at once;
each has a bounded timeout. A raw QEMU exit of 33 is recorded independently
from whether the ELF exit and full JSON facts match the Linux reference.

Prepare a fresh source directory using the frozen source archive and a fresh
rootfs using the retained current tar:

```sh
EVIDENCE=support/build/evidence/2026-10-16-review/linux-guest
A04_SRC=/absolute/new/a04-source
A04_ROOTFS=/absolute/new/a04-rootfs
mkdir -p "$A04_SRC"
tar -xzf "$EVIDENCE/a04-source.tar.gz" -C "$A04_SRC"
gzip -dc "$EVIDENCE/rootfs.tar.gz" > /absolute/new/a04-rootfs.tar
python3 "$A04_SRC/pr8/support/rootfs/capture.py" --extract-verified \
  --tar /absolute/new/a04-rootfs.tar \
  --manifest "$A04_SRC/pr8/support/rootfs/manifest-debian13-x86_64.json" \
  --root "$A04_ROOTFS"
```

Run the original A04 suite first; its failure remains evidence:

```sh
python3 "$A04_SRC/pr8/tests/workloads/linux/replay_qemu.py" \
  --a01-kernel-gz support/build/evidence/2026-10-16/artifacts/kernel.elf.gz \
  --a01-initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --firmware /usr/share/seabios/bios-256k.bin --qemu /usr/bin/qemu-system-x86_64 \
  --rootfs "$A04_ROOTFS" \
  --rootfs-manifest "$A04_SRC/pr8/support/rootfs/manifest-debian13-x86_64.json" \
  --reference "$A04_SRC/pr8/tests/workloads/linux/baselines/linux-debian13-x86_64.json" \
  --out-dir /absolute/new/a04-original-suite --timeout 180
```

Then diagnose cases independently:

```sh
python3 -I support/build/linux-guest/isolate.py \
  --a04-source-root "$A04_SRC/pr8" --rootfs "$A04_ROOTFS" \
  --a01-kernel-gz support/build/evidence/2026-10-16/artifacts/kernel.elf.gz \
  --a01-initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --firmware /usr/share/seabios/bios-256k.bin --qemu /usr/bin/qemu-system-x86_64 \
  --out-dir /absolute/new/a04-isolated --jobs 2 --timeout 30
```

Use `--case static.fd_limit` or `--case static.scm_rights` for focused
owner-side reproduction. The actual measured result is **24 exact matches,
2 completed failures, 2 timeouts / 28**. The original sequential suite timed
out after 8 matches and 1 completed failure. Neither profile is a full pass.
The three Python cases and Rust/Tokio are four additional unported workloads;
they are excluded from the 28-case denominator. RAMfs SQLite tests do not prove
S1 block persistence, and no Hepta W1 result is claimed.

The evidence report retains the original suite, all independent guest serial
logs, source/input hashes, and same-ELF original Linux controls. Derived
initramfs are reproducible from the retained tar and frozen pack API; their
individual SHA-256 values remain in every guest's manifest.

Each guest's `serial-captured.log.gz` is the canonical complete original
serial byte sequence, read through QEMU's still-open stdout file descriptor.
The runner verifies both its compressed hash and decompressed byte hash.
Later changes to the `serial.log` pathname are reported separately and do not
replace the captured snapshot. Such a pathname change was actually observed
in this environment; its writer and cause remain unknown.

SIGINT and SIGTERM cancel queued work and stop each active direct QEMU child
with terminate, bounded wait, then kill if needed; the child is always reaped.
The signal handler only sets cancellation state, so interruption during child
launch cannot skip ownership cleanup. Partial serial snapshots are retained,
aborted attempts never qualify as matches, and the CLI exits 130 or 143.
`qemu_reaped_exit_code` records actual cleanup termination separately from the
compatibility field's `null` timeout status.

The complete 28-case result above is frozen at commit
`d85b1e091143a9c4f004c024f433a58188455105`. The cancellation fix was checked
with real SCM guests under both signals and a focused positive, completed
failure and timeout case. Those repeated checks are separate from the 28-case
coverage count; see the evidence directory's `cancellation/REPORT.md`.
