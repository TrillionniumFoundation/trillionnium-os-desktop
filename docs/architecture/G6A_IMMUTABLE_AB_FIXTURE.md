# G6a installed immutable A/B qualification fixture

This additive executable profile starts an actual Debian kernel and userland in
QEMU, mounts a dm-verity protected root, and tests guest-selected A/B attempts
and fallback. It is a minimal installation fixture, not the accepted desktop
image or production update owner. D1, D2I and all prior qualifications retain
their exact historical recipes and claim ceilings.

## Boot chain and its limit

The host validates the exact build artifact sizes and digests, then uses the
same direct kernel, initramfs, command line and five-device ordering on every
boot. The guest `/init` mounts the separate writable state disk. The selector
chooses A or B from bounded persistent attempt state; the host supplies no
`root=slot`, mutable root digest or booted-image assertion.

The fixed initramfs contains a disposable fixture public key. Actual OpenSSL
verification uses three sealed memfds and a separate G6a signature domain. The
closed descriptor authenticates the slot, generation, complete data and hash
image sizes/digests, dm-verity geometry, root hash and salt. The descriptor
contains no verifier command, optional integrity-bypass flags or health fields.
This extends the source mechanisms' custody design without promoting a v1/v2
pending journal or reconstructing an old coordinator ticket.

The selector reads every data and hash block, runs actual userspace
`veritysetup verify`, creates a read-only kernel mapping, checks its actual
table against the authenticated descriptor and fixed block-device identities,
then reads every mapped data block through the kernel. The immutable root is
mounted `ro,noload`. After `switch_root`, a probe verifies the actual `/` mount
device, read-only mount and mapping flags, immutable slot marker and unchanged
kernel boot ID, and observes a real `EROFS` when opening the marker for write.

Linux specifies that dm-verity's root hash needs a trusted chain; its `V` status
only covers checks already performed. This recipe therefore checks complete
images and mapping reads rather than treating status as a full image check.
See the [Linux dm-verity documentation](https://docs.kernel.org/admin-guide/device-mapper/verity.html)
and Debian's packaged [veritysetup manual](https://manpages.debian.org/trixie/cryptsetup-bin/veritysetup.8.en.html).
An initramfs `/init` is responsible for root setup before normal userland; see
the [Linux early userspace documentation](https://www.kernel.org/doc/Documentation/early-userspace/README).

The test harness is the fixed boot entry's trust boundary. This profile has no
UEFI authenticated boot, protected time, protected monotonic floor or hardware
root. Replacing the whole host artifact tuple or resetting mutable state is
outside its guarantee. It supplies no firmware or whole-directory rollback
qualification. A production successor needs an independently provisioned
boot/root policy and a protected monotonic anchor.

## Actual commands

Resolve the independent minimal Debian closure using the existing fixed Debian
13 primary fingerprints and signed 20260828 snapshot:

```sh
python3 tools/resolve_g6a_inputs.py \
  --requirements manifests/debian-g6a.requirements.v1.json \
  --output /tmp/g6a-resolved-lock.json \
  --work-dir /tmp/g6a-resolution --logs /tmp/g6a-resolution-logs
```

The builder requires the exact reviewed committed lock and every downloaded
package hash/size. It extracts the package closure without claiming configured
package transactions or a desktop. Run it as root inside a dedicated builder;
the output directory must be new:

```sh
sudo python3 tools/build_g6a_fixture.py \
  --lock manifests/debian-g6a.lock.v1.json \
  --packages-dir /tmp/g6a-resolution/downloads \
  --output-dir /tmp/g6a-built
python3 tests/qemu/run_g6a_qualification.py \
  --artifacts /tmp/g6a-built/artifacts --output-dir /tmp/g6a-qemu
python3 -m unittest tests.test_g6a_immutable_ab -v
```

The generated private key remains in the isolated build directory and is never
part of the shipped artifact directory. Both its creation and use are explicitly
fixture-only. It approves no production signer, root operator or release.
The host needs QEMU, debugfs and Python; the builder additionally needs
dpkg-deb, chroot, cpio, e2fsprogs, veritysetup and OpenSSL. Missing tools fail.
Package extraction uses a fresh sealed memfd whose size and SHA256 match the
signed index. Replacing a downloaded path after the initial inventory cannot
change the bytes consumed by `dpkg-deb`.

## Persistent attempts and faults

A pending B operation permits two guest boot attempts. The attempt is persisted
before mapping activation. Reaching an immutable root is an observation, not a
health commit: after the two attempts, the guest selects the exact verified A
source. Failure to authenticate A refuses all activation. An invalid B signature
or substituted target image selects A with a bounded refusal cause. Corrupt
state and orphan publication files refuse; the code does not remove or repair
them. Fixture history has a fixed 32-boot capacity.

The finite 17-case matrix includes source boot, same-disk B/B/A selection, two
actual failed B boots, forged rehashed signature, missing signature, data/hash
corruption, source corruption, corrupt state, retained orphan, actual ext4
ENOSPC, and abrupt running-VM termination at each of six state publication
boundaries. The harness directly reboots the exact interrupted disk without an
offline write, deletion or repair; a fixture pause expires naturally if reached
again. Before directory fsync, startup may refuse or observe the exact valid old
or new attempt state. The killed boot has not activated a root. A fresh verified
boot from old state can therefore consume its first attempt; preserved new
state must consume the second. After directory fsync, the second attempt must
be observed. Orphans always refuse and remain for explicit recovery. Root disks
are attached read-only and state uses `cache=none`; VM SIGKILL is emulator
interruption evidence, not physical power removal or device-cache qualification.

Per-boot serial bytes, exact argv, actual installed receipts and state-image
digests are retained. Serial and durable receipts must agree. Distinct boots
need distinct kernel boot IDs. A result exists only after all selected cases
actually pass; there are no skipped or synthesized guest passes.

## Remaining G6b/G6c chain

`UpdateCoordinator.record_booted_image`, `record_health`, `rollback` and
`reconcile_startup` accept scalar source facts; they must not receive UI claims
as installation authority. `commit` changes memory only. The new installed owner
must independently reverify exact signed descriptors and persistent signatures,
bind the actual mount namespace/root/mapping and approved boot attempt, measure
health with a monotonic clock and actual native/session services, and persist
every effect intent and readback result. It must not hydrate old v1/v2 tickets.

Health must cover the actual G2/G3 session and browser entry, journal recovery and
required service continuity for at least the planned 60 seconds. Any service,
boot identity, mapping, policy, floor or time change invalidates the measurement.
No caller `stable_seconds`, receipt digest or `health=true` authorizes commit.
Bootloader blessing, protected floor advance and durable commit need a defined
order and explicit reconciliation for interruption between each side effect.
Rollback must prove the exact floor-permitted source on its actual next boot.

Integrating the accepted desktop source/image/input tuple changes the image and
requires fresh G4/G6 installed qualification. Default product activation remains
disabled. Firmware trust, protected floor/time, actual release signing custody,
hardware power cuts and long-duration testing remain separately provisioned
and measured facts.
