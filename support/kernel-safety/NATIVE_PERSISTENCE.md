# Persistent guest substrate for original native Hepta

This stage supplies a disposable persistent filesystem for the original Root
and Agentd qualification.
It establishes a filesystem and permission substrate only.
Original Root authorization, signatures, original Agentd admission and original
SQLite/Fleet/FinalUse recovery remain in their existing Hepta implementations.

## Directory and mount contract

The dedicated raw ext2 fixture is exposed as `/dev/vda` through modern
virtio-blk (`disable-legacy=on,disable-modern=off`).
The guest mounts it at `/mnt/hepta-store` with `nosuid,nodev,noexec`.
No host block device, personal disk, network or shared host directory is
exposed to the guest.

| Guest path | Owner and mode | Role |
| --- | --- | --- |
| `/mnt/hepta-store/native-root` | root:root, 0700 | Original Root private durable source |
| `/var/lib/hepta-native` | Same original directory, bind mount | Original Root configured durable mountpoint |
| `/mnt/hepta-store/agent-owner` | 60002:60002, 0700 | Original Agentd/Fleet/SQLite storage |
| `/mnt/hepta-store/consumer-local` | 60002:60002, 0700 | Original local consumer journals |

The source and mountpoint must refer to the same original inode and device.
The probe reads the actual `/proc/self/mountinfo`: column 5 must be the exact
mountpoint, the filesystem root `/native-root`, the filesystem `ext2`, and the
source `/dev/vda`; its major/minor pair must match `stat` of the source.
It does not infer a bind from pathname existence or from the host test JSON.

The mount and source are root-owned 0700.
Non-root Agentd UID 60002 cannot access them, and workload UID 60001 cannot
access either the Root data or the Agentd/consumer data.
Each child clears supplementary groups before dropping GID and UID.
Agentd data is intentionally outside the Root 0700 subtree.
Runtime service sockets may live in a separately controlled `/run` directory;
this test does not place durable data in `/run` or manufacture socket authority.

## Disk and durability boundary

`tests/kernel/native-persistence/run.py` exclusively creates a 64 MiB regular
file inside a fresh host-owned 0700 evidence directory.
The file is mode 0600 with one link, an invariant checked before and after
each boot.
The system mke2fs executable, command, filesystem UUID and initial file hash
are recorded.
The bounded fixture uses 4096-byte blocks and 128-byte inodes with the existing
kernel-supported ext2 feature subset.

Both QEMU instances attach the same raw file with:

```text
-drive file=GENERATED_FIXTURE,if=none,format=raw,id=hepta-store,snapshot=off,cache=writeback
-device virtio-blk-pci,disable-legacy=on,disable-modern=off,drive=hepta-store
```

The probe uses actual file `fsync`, rename and directory `fsync` before its
durable marker.
The runner kills QEMU only after the complete nonce-bound marker is observed,
then requires the actual child status to be SIGKILL.
The next guest independently reads the stored nonce, first boot ID and payload
through the mounted ext2 filesystem, while its current boot ID comes from the
original kernel's procfs/HOS2 owner.
The kernel ELF, BIOS, compiled probe and source snapshot must remain unchanged.
Initramfs images differ only in the recorded phase-specific invocation.

This is a QEMU process/VM crash under a continuously running host.
It is not physical power-loss testing: host page cache, controller cache,
physical media behavior, torn writes and fsync behavior under device failure
have not been qualified.
The mountable ext2 fixture is not a production disk format recommendation.
No SQLx, SQLite journal/WAL, original Root checkpoint or Hepta delivery is
represented by the small fixture files.
Those need separate tests of the actual original owner on this substrate.

## Development and evidence

The [probe README](../../tests/kernel/native-persistence/README.md) describes
reproduction and retained evidence.
The source-built OSDK must belong to this worktree, including its compile-time
`OSDK_LOCAL_DEV=1` setting.
Use isolated targets and at most two compilation jobs.
All probes run inside owned QEMU guests, never as host programs.

A separate invocation of `tests/kernel/control/run_g1d_guest.py` qualifies the
original trusted-role configuration at the boot-ID source commit.
That build enables the real `g1d-trusted-control` call sites and preserves the
existing exact-image, byte-mismatch and truncated-image controls.
The ordinary persistent guest and G1-d profile have separate kernel artifacts
and evidence: success of one does not substitute for success of the other.
The persistent guest itself does not activate trusted roles or original Hepta.

Verification results are recorded in the stage summary after real execution.
A provisional or failed result does not establish this substrate as usable;
failed logs and disks are retained without relaxing the oracle or deadline.

## Verified development checkpoint

`work/goal-logs/native-persistence/persistence-first` completed both actual
guests: 26 first-boot checks passed, followed by SIGKILL/exit -9 at the durable
marker; 24 second-boot checks passed, followed by clean unmount/exit 33.
Both used kernel ELF SHA256
`8d2f22246148c8cc6d2c8802ceab248189bb5673cc732510590b8242b4da6120`.
The original boot ID `2ecf351f-6b12-474d-9bc4-9b2dc036ac8f` was read back from
the actual disk while the new kernel reported
`5eb1dc10-bf30-4135-8636-36f2f38e851b`.
Both source/bind observations reported device 253:0 and inode 12, with the
expected mountinfo fields and real UID permission checks.
Disk before/after hashes, raw serial output and source snapshots are retained
in that run; no fixture failed and no deadline was extended.
The fixture sources were tested as development working bytes before delivery.

The separate G1-d run in `work/goal-logs/native-persistence/g1d-first` used
clean source commit `ca4acd8d6eccd3d539bae97454ea89d540f95416` and real
`g1d-trusted-control` compilation.
Its exact-image control passed with exit 33; byte-mismatch and truncated-image
controls were correctly rejected with exit 65 using the same profile ELF
`0c2645cc40147cc6a80231a0f7215f9a56a0361a5f3e363da5eb76840f6c24ab`.
The complete source snapshot remained unchanged.
This closes the boot-ID change's trusted-role compilation/execution gap;
it does not add persistence to the G1-d memory owner or qualify original SQLite.
