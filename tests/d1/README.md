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

The tar may contain valid UTF-8 pathnames supplied by the exact Debian package
closure. At the pinned e2fsprogs commit, upstream `mke2fs` compiles its
`setlocale(LC_CTYPE, "")` call only when configured with NLS support. D1 therefore
builds that unchanged exact source with the reviewed `--enable-nls` flag and
launches tar-populating `mke2fs` under `C.UTF-8`; this is a build-mode correction,
not a source patch or a relaxation of any image input. A small deterministic tar
containing `路径.txt` must import into ext4 and pass read-only `e2fsck` before the
full Debian builds begin. The probe records the exact commit, configure flag,
runtime locale, zero source-patch count, and `mke2fs` digest in machine evidence.

Sorting remains bytewise `LC_ALL=C`; timestamps, numeric ownership, UUID, hash
seed and all other image inputs remain fixed. An unavailable or non-UTF-8
charmap is a hard failure, not a fallback to locale-dependent decoding. The
standalone pinned-tool builder fingerprints the commit, configure mode, and
runtime locale together, so it cannot reuse an earlier `--disable-nls` prefix.

The host filesystem tools are not taken from the mutable runner image. D1 pins
upstream e2fsprogs `v1.47.2` to commit
`c3cce4a07efefc62bc7fc57a678cb870af27d0f2`, builds it once into an isolated
prefix, verifies the exact source checkout, and records SHA-256 digests for
`mke2fs`, `e2fsck`, and `dumpe2fs`. Before either root build crosses the sudo
boundary, the pipeline resolves canonical absolute paths for all three tools.
The root builder requires those explicit bindings, verifies that they share one
reviewed prefix, verifies that root's constrained PATH resolves to those exact
files, and invokes the bound paths directly. A system-runner fallback is a hard
failure rather than an alternate build mode.

The permanent `d1-final-qualification` workflow runs directly on the tracked
branch head, validates all repository and D1 tests, performs both independent
builds and QEMU acceptance, enforces the claim ceiling, and uploads the complete
machine-readable evidence corpus. Transient dispatch, patch, materialization,
or self-promotion workflows are not part of the candidate tree and cannot be
used as evidence-bearing heads.
