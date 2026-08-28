# D1 Debian QEMU substrate

**Checkpoint:** `TOS-D1-01`  
**Promotion unit:** one signed snapshot, exact package lock, reproducible ext4 image and no-network QEMU acceptance

D1 proves the base operating-system substrate before Servo integration. It is
not a release image and does not use the developer host as the product rootfs.

## Input custody

`manifests/debian-d1.selection.json` selects Debian 13 `trixie`, `amd64` and a
preferred timestamped snapshot. `tools/resolve_debian_d1_lock.py` downloads
only the selected `InRelease` files, verifies them with the Debian archive
keyring and records every metadata digest and valid signer fingerprint.
Unsigned `Release`, rolling mirrors and an unresolved point-release label are
not accepted.

The package intent is listed in
`packaging/debian/image/d1-packages.txt`. The build records the complete
installed binary package, version and architecture closure as a sorted TSV.

## Reproducible image

`packaging/debian/image/build-d1-image.sh` creates a minimal rootfs with
`mmdebstrap`, applies the repository-owned overlay, rebuilds the initramfs and
normalizes timestamps to the snapshot epoch. The rootfs is serialized in
sorted order and populated into an ext4 image with fixed label, UUID, hash
seed, eager inode-table initialization and eager journal initialization.

The qualification workflow creates two independent rootfs/image builds. The
package lock, normalized rootfs archive, ext4 image, kernel and initrd must all
match byte-for-byte. A mismatch is evidence of non-reproducibility and blocks
promotion; it is not hidden by selecting one build.

## QEMU acceptance

D1 uses direct kernel/initrd boot with a virtio ext4 root disk on Q35/TCG. The
QEMU command contains `-nic none`; the guest has no network device during the
acceptance run.

The guest boots the dedicated
`trillionnium-d1-acceptance.target`, which requires systemd, udev, D-Bus and
logind, starts a supervised headless Weston compositor, waits for the Wayland
socket, runs `wayland-info`, writes persistent acceptance evidence to the root
filesystem, prints a unique serial PASS marker and powers off cleanly.

The host requires both evidence channels:

1. the serial PASS marker with no FAIL marker; and
2. a valid `/var/lib/trillionnium-d1/acceptance.json` extracted from the booted
   disk with `debugfs`.

A screenshot or a process existing in the source tree is not D1 completion.

## Deliberate non-claims

D1 does not prove:

- UEFI or Secure Boot;
- a visible GPU-backed desktop;
- Servo or a BrowserActor;
- native pointer, keyboard or IME integration;
- audio, suspend, bare-metal drivers or multi-monitor support;
- update signing, A/B rollback or release readiness.

Those remain D2, D7 and D8 gates.
