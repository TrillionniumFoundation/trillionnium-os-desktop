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
codec, and product activation fails closed until D3 connects a real
BrowserActor.

D1 compiles the separate `hepta-agent-d1-fixture` example only with the explicit,
non-default `fixture` feature. The host artifact is
`target/release/examples/hepta-agent-d1-fixture`; it is installed as
`/usr/libexec/hepta-agent-d1-fixture` only in the qualification image.
That executable provides both the bounded
qualification client and an inherited-stream qualification server. It never
creates a listener. An image-local systemd drop-in replaces the per-connection
`ExecStart` with `hepta-agent-d1-fixture --mode server` only inside the D1
qualification image. The drop-in and qualification binary are absent from the
production Debian install map.

The two qualification services keep distinct UIDs. Linux denies unprivileged
cross-UID reads of `/proc/<pid>/exe`; the browser service receives no ptrace
capability. This image-only profile therefore retains live pidfd, credentials,
start-time and cgroup checks while hashing the fixed root-owned qualification
executable path. Its receipt explicitly records
`live_process_executable_observed: false` and
`peer_executable_binding: root_owned_qualification_path`. This is a limited
qualification identity check, not proof of the peer's running executable.
Production live-executable attestation across those UIDs still requires a
separately reviewed custody/broker design; the default product attestor must
not silently use this qualification fallback.

Host and guest gates prove both sides of the boundary:

- the product daemon self-check reports no connected product handler and no
  linked fixture handler;
- the default product dependency tree contains no fixture/codec graph;
- the qualification tree is enabled explicitly and separately;
- QEMU acceptance inspects the effective systemd command and records that all
  requests were served by the qualification-only binary, not the product
  daemon.

## Reproducible image

`packaging/debian/image/build-d1-image.sh` creates a minimal rootfs with
`mmdebstrap`, applies the repository-owned overlay, normalizes timestamps and
metadata, serializes the rootfs in a deterministic order, and populates a fixed
ext4 filesystem. The exact upstream e2fsprogs source is built in an isolated
prefix with the reviewed UTF-8/NLS contract; no mutable runner filesystem tool
may substitute for the bound `mke2fs`, `e2fsck`, or `dumpe2fs` binaries.

Two independent builds must produce byte-identical package locks, rootfs
archives, ext4 images, kernels, and initrds. Any mismatch blocks promotion.

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
Failed acceptance preserves bounded service journal and acceptance records
before guest poweroff. Failure uploads contain evidence and capped log tails;
they exclude the multi-gigabyte guest disks and cannot promote a failed run.

## Portable reader semantics

The source reader uses the closed
[`d1-portable-evidence.v1.json`](../../contracts/d1-portable-evidence.v1.json)
profile and
[`d1_evidence_semantics.py`](../../tools/d1_evidence_semantics.py).
It performs these checks after verifying the complete output digest inventory:

- Fixture separation stays exact: the default product graph is fixture-free,
  the qualification example uses `fixture`, the fixed test server command is
  preserved, and no connected product handler or production install-map claim
  is admitted. The reproducibility scope permits only the same-run two builds;
  cross-run and hermetic-host qualifications remain false.
  The carried product/qualification Cargo-tree exports and binary-string exports
  must also satisfy the producer's existing separation checks. These are
  exported records, not a fresh binary disassembly or a new Cargo build.
- Every required pipeline stage, including the overall stage, has an exact
  integer zero exit status and `PASS`; failed stage is null, finish follows
  start, and the pipeline's release/network/Secure Boot/Servo ceilings stay
  false. A summary status cannot hide a failed subordinate stage.
- Both carried rootfs manifests are parsed and their canonical entries digest,
  exact count, unique canonical paths and object metadata are checked. The
  `.` entry must be an explicit directory, and every nonroot entry has an
  explicit directory parent; file or symlink parents and missing ancestors
  are inconsistent records. Each declared hardlink group has one self-naming
  head at the byte-lexicographic minimum carried member, matching metadata and
  no more carried members than its declared `nlink`. The producer may observe
  additional links outside the root, so equality with `nlink` is not required.
  This checks carried-manifest consistency, without claiming a complete inode
  inventory or inspection of the omitted filesystem payload. The
  product and qualification binary records bind the corresponding rootfs SHA,
  size, root ownership, ordinary executable mode and single-link entries in
  both builds. This links the recorded binaries to the recorded image contents;
  the reader does not execute a binary or independently inspect an omitted
  filesystem image.
- Both actual carried package-lock byte streams match the prepared expected
  lock, count and digest. Build/prepared/reproducibility records bind the same
  prepared-input bytes, selected package set and fixed build invariants. The
  reproducibility comparison table binds each build's artifact digest and
  length, requires equality and an empty semantic rootfs diff, and recomputes
  the carried manifest/package digests and lengths from their original bytes.
- The boot record binds the declared tested image digest and package lock,
  exact zero QEMU exit and disabled network, plus the SHA of the actual carried
  acceptance bytes. Acceptance binds the same image identity and package set.
  Its actual PID 1, active services and AgentPort default/denial/request/recovery
  facts must agree with the boot claims, and its product self-check digest binds
  the actual carried self-check bytes.

Parsing and hashing use the same bounded, retained regular-file descriptor.
The reader rejects symlinks and hard links, verifies named identity and caches
the inspected bytes. Its final readback retains all inspected descriptors
through a final identity check, so a predecessor changed during a later read
cannot yield a stale successful result. The finalizer invokes this same reader
before leaving a success receipt. This source check supplies no activation or
external authority from caller-provided JSON.

The portable packet contains the rootfs **manifest**, not the multi-gigabyte
ext4 disk, rootfs tar, kernel or initrd payloads. For those omitted payloads the
reader checks the build/comparison/boot record relationships; it cannot claim
to have rehashed their complete bytes. Actual creation and same-run comparison
remain responsibilities of the recorded build/QEMU producer. Ordinary decoder
fixtures and rewritten negative packets exercise the source reader; they are
not new guest executions, signing approvals, installed qualification or release
authorization.

## Deliberate non-claims

D1 does not prove a Servo frame, BrowserActor dispatch, product AgentPort
activation, external networking or effects, UEFI/Secure Boot, hardware support,
production signing, update/rollback, or release readiness. Those remain later
D2I through D9 gates.
