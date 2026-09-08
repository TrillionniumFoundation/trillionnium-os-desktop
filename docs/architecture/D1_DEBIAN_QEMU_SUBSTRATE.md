# D1 Debian/QEMU substrate

**Checkpoint:** `D1-01`
**Promotion unit:** one signed Debian closure, two byte-identical normalized builds, one no-network QEMU PID 1 acceptance run, and exact Git/evidence identities

D1 qualifies the base operating-system substrate before integrated Servo image
work. It is not a release image, does not enable the product AgentPort, and does
not import fixture authority into the production daemon.

## Signed input custody

`manifests/debian-d1.selection.json` selects Debian 13 `trixie`, `amd64`, a
fixed snapshot timestamp, and the exact committed
`manifests/debian-d1.lock.v1.json`. The resolver verifies the selected
`InRelease` objects against pinned Debian 13 trust roots and records metadata,
package size, package SHA-256, signer identity, and one canonical package-set
digest. Unsigned Release data, a moving mirror, or a package outside the exact
lock fails closed.

The permanent workflow derives source identity from the checked-out Git object.
For a pull request it requires an exact two-parent merge object, records
`HEAD`, `HEAD^{tree}`, `HEAD^1`, and `HEAD^2`, and verifies that the second parent
is the exact PR head. For a push it records the exact pushed commit and parent.
Webhook base metadata is never treated as the tested Git identity.

## Product/qualification AgentPort separation

The production binary remains `/usr/libexec/hepta-agent-portd`. Its default
Cargo graph excludes `hepta-agent-port`, the D0 fixture handler, and the Browser
codec, and product activation fails closed. The D3 BrowserActor source profile
is compiled separately and is not a product activation; only a promoted,
integrated D3 qualification can change this boundary.

D1 compiles a separate `hepta-agent-d1-fixture` binary only with the explicit,
non-default `d1-qualification` feature. That binary provides both the bounded
qualification client and an inherited-stream qualification server. It never
creates a listener. An image-local systemd drop-in replaces the per-connection
`ExecStart` with `hepta-agent-d1-fixture --mode server` only inside the D1
qualification image. The drop-in and qualification binary are absent from the
production Debian install map.

The qualification server runs as `hepta-browserd` while its fixture client runs
as `hepta-agent`. Linux gates a live `/proc/<peer>/exe` read across those UIDs,
so the qualification-only path binds the digest of the fixed,
root-owned `/usr/libexec/hepta-agent-d1-fixture` image file through
`attest_with_static_executable_digest`. PID/UID/GID/start-time/cgroup/unit and
pidfd checks remain live and are compared before and after the request. The
production and D3 development daemons retain the strict live-procfs executable
digest path; this qualification accommodation does not authorize a production
principal or activation.

Host and guest gates prove both sides of the boundary:

- the product daemon self-check reports no connected product handler and no
  linked fixture handler;
- the default product dependency tree contains no fixture/codec graph;
- the qualification tree is enabled explicitly and separately;
- QEMU acceptance inspects the effective systemd command and records that all
  requests were served by the qualification-only binary, not the product
  daemon.

## Reproducible image (same-run qualification scope)

`packaging/debian/image/build-d1-image.sh` creates a minimal rootfs with
`mmdebstrap`, applies the repository-owned overlay, normalizes timestamps and
metadata, serializes the rootfs in a deterministic order, and populates a fixed
ext4 filesystem. The exact upstream e2fsprogs source is built in an isolated
prefix with the reviewed UTF-8/NLS contract; no mutable runner filesystem tool
may substitute for the bound `mke2fs`, `e2fsck`, or `dumpe2fs` binaries.

Two independent builds must produce byte-identical package locks, rootfs
archives, ext4 images, kernels, and initrds. Any mismatch blocks promotion.
The current gate claim is bounded to that same-run comparison under the fully
recorded runner and toolchain. It does not claim cross-run output identity or a
hermetic host environment; those remain unproven until the host image and every
image-producing input are content-addressed and independently reproduced.

## QEMU acceptance

D1 uses Q35/TCG direct kernel/initrd boot and `-nic none`. The guest starts
systemd PID 1, udev, D-Bus, logind, and a supervised headless Weston instance,
then proves:

- AgentPort is disabled without the unshipped marker;
- an unauthorized filesystem peer is denied;
- the exact qualification client identity can complete one bounded health
  request;
- one accepted connection maps to one short-lived service process;
- killing that connection process does not kill the systemd socket custodian;
- a subsequent request succeeds;
- the marker and socket are removed before poweroff;
- the candidate powers off cleanly and emits both serial and disk receipts.

The guest receipt includes digests for the product self-check, qualification
unit, Wayland evidence, responses, and journal. The permanent workflow binds
those outputs, the workflow digest, every critical input digest, the exact
commit/tree topology, and the claim ceiling into one uploaded evidence package.

## Deliberate non-claims

D1 does not prove a Servo frame, BrowserActor dispatch, product AgentPort
activation, external networking or effects, UEFI/Secure Boot, hardware support,
production signing, update/rollback, or release readiness. Those remain later
D2I through D9 gates.
