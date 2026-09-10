# D1 exact-head runtime gate

D1 is evidence-bearing rather than a source-presence check. It consumes the
committed signed Debian package closure, creates two independent rootfs/ext4
builds, compares all normalized artifacts, and boots the candidate under QEMU
without a network device.

A passing run proves systemd PID 1, udev, D-Bus, logind, a supervised headless
Wayland compositor, AgentPort default-disabled custody, authorized and
unauthorized peer behavior, per-connection teardown, kill/recovery, absence of
the test-only enable marker from the immutable candidate, and clean poweroff.
It does not start Servo or claim a visible desktop frame.

## Exact source identity

The permanent workflow never copies a webhook base SHA into the receipt. A
pull-request run must execute an exact two-parent tested merge object and bind
`HEAD`, `HEAD^{tree}`, `HEAD^1`, and `HEAD^2`, with the second parent equal to
the live PR head. A push run binds the exact pushed commit and its parent. Any
unexpected topology fails before construction begins.

## Qualification-only AgentPort path

The production `hepta-agent-portd` remains fixture-free and fails closed before
request decoding until D3 supplies a real BrowserActor. D1 builds
`hepta-agent-d1-fixture` only with the explicit, non-default
`d1-qualification` feature. The qualification binary contains both client
modes and an inherited-stream server mode; it never binds or listens.

Only the D1 rootfs overlay supplies a systemd drop-in that changes the
per-connection command to `hepta-agent-d1-fixture --mode server`. Static tests,
Cargo-tree evidence, binary-string evidence, the production install map, host
self-checks, the effective guest unit, and the guest acceptance receipt must
all agree that the product daemon did not serve qualification requests.

## Deterministic filesystem construction

The builder executes target Debian `tmpfiles` with an explicitly mounted and
subsequently unmounted procfs. Ambiguous regular or special nodes fail closed;
only unambiguous builder-owned directory and symlink metadata is normalized to
guest root ownership.

Both build candidates first produce the same sorted, timestamp-normalized,
numeric-owner rootfs tar. A pinned, isolated upstream e2fsprogs toolchain
imports that tar into ext4 using fixed label, UUID, hash seed, epoch, inode size,
block size, and eager journal/inode-table initialization. A deterministic UTF-8
tar import probe containing `路径.txt` must pass before either full image build.
The pipeline passes canonical absolute paths for `mke2fs`, `e2fsck`, and
`dumpe2fs` across the sudo boundary and forbids a system-runner fallback.

The full package lock, rootfs archive, ext4 image, kernel, and initrd must match
byte-for-byte across the two builds. A mismatch is a hard failure.

## Receipt ceiling

The final evidence binds exact Git identities, workflow digest, critical input
and output digests, host tool identities, product/qualification graph evidence,
reproducibility, QEMU boot, guest acceptance, and explicit false claims for
Servo, a visible window, networking, Secure Boot, product AgentPort activation,
and release authorization.
