# Signed Debian snapshot lock

**Work package:** `TOS-D0R-02`  
**Architecture:** `amd64`  
**Snapshot:** `20260828T000000Z`  
**Status:** input validated  
**Claim class:** signed inputs and package closure only

## Trust and resolution model

The D1 image may not resolve packages from a rolling mirror. For each frozen
source, the gate downloads the exact `InRelease`, requires a valid signature
from an archive-specific pinned Debian 13 primary fingerprint, records all
valid and unknown co-signers, and hashes the exact signed file. Bad, expired,
revoked, missing-data and internal verification states are fatal. An unknown
additional co-signer can never substitute for a required accepted signature.

Package resolution runs against an empty isolated dpkg status database with
`--no-install-recommends`. Every selected package is downloaded and its byte
length and SHA-256 are compared with signed APT metadata.

## Canonical repository lock

`manifests/debian-snapshot.lock.v1.json` is the only D1 package input lock. It contains three exact
signed `InRelease` records, the minimal Debian 13 trust roots, and all
`319` selected packages. The package-set SHA-256 is
`89918a968afafdbabe03e43794565cb1dc936f3f24a09ec81030be4a4085333a`.

The permanent workflow regenerates the lock and requires a byte-for-byte match.
The offline validator independently recomputes the package-set digest and
checks the lock, selection, documentation manifest and repository state.

## Promotion boundary

D0R-02 is input validated. It does not create a rootfs or image and does not
boot QEMU. D1-01 must consume this lock and prove reproducible construction,
systemd/Wayland boot, and the test-only D0C-05 PID 1 activation corpus while
the product image remains default-disabled.
