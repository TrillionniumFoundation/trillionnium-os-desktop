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

The current exact-head run additionally verifies that target Debian `tmpfiles`
executes with an explicitly mounted and subsequently unmounted procfs, avoiding
host/target systemd version coupling during rootfs construction. A sudo-hosted
`mmdebstrap` build may map rootfs directory and symlink metadata to the invoking
runner identity; the builder now normalizes only that unambiguous metadata back
to guest `0:0`, installs the repository overlay explicitly as `0:0`, refuses to
rewrite regular or special nodes, rejects guest UID/GID collisions, and asserts
trusted rootfs path ownership before target `sysusers` and `tmpfiles` execute.
