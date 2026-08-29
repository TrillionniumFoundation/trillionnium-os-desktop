# D1 exact-head runtime gate

The D1 qualification is evidence-bearing rather than a source-presence check.
It consumes the committed signed Debian package closure, creates two independent
root filesystems and ext4 images, compares their normalized artifacts, and boots
the candidate under QEMU without a network device.

A passing run must prove systemd PID 1, udev, D-Bus, logind, the headless Wayland
socket, default-disabled AgentPort custody, authorized and unauthorized peer
behavior, per-connection teardown, kill/recovery, absence of the test-only enable
marker from the release candidate, and clean poweroff. It does not start Servo or
claim a visible desktop frame.

The builder executes target Debian `tmpfiles` with an explicitly mounted and
subsequently unmounted procfs, avoiding host/target systemd version coupling. A
sudo-hosted `mmdebstrap` build may map rootfs directory and symlink metadata to
the invoking runner identity; only that unambiguous metadata is normalized back
to guest `0:0`, while regular and special nodes fail closed.

Both build candidates first produce the same sorted, timestamp-normalized,
numeric-owner rootfs tar. `mke2fs` consumes that tar directly using the fixed
filesystem UUID, directory hash seed, label, epoch, inode size, block size,
journal initialization, and inode-table initialization. The resulting ext4
image must pass read-only `e2fsck`, and its superblock header is retained as
bounded diagnostics. An unpacked directory is not accepted as the ext4
population input because host directory enumeration can perturb inode allocation
despite identical file content.

The host filesystem tools are not taken from the mutable runner image. D1 pins
upstream e2fsprogs `v1.47.2` to commit
`c3cce4a07efefc62bc7fc57a678cb870af27d0f2`, builds it once into an isolated
prefix, verifies the exact source checkout, and records SHA-256 digests for
`mke2fs`, `e2fsck`, and `dumpe2fs`. Both candidates use those same binaries; no
system-wide installation is modified.

The permanent `d1-qemu-substrate` workflow runs directly on the tracked branch
head. Transient dispatch or materialization workflows are not part of the
candidate tree and cannot be used as evidence-bearing heads.
