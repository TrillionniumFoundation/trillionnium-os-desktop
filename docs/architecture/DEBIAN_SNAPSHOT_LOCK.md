# Signed Debian snapshot lock

**Work package:** `TOS-D0R-02`  
**Architecture:** `amd64`  
**Requested snapshot:** `20260828T000000Z`  
**Claim class:** signed inputs and package closure only

## Trust and resolution model

The D1 image may not resolve packages from a rolling mirror. The snapshot gate
uses three frozen sources:

```text
Debian trixie
Debian trixie-updates
Debian trixie-security
```

For every source, the gate downloads `InRelease`, verifies its OpenPGP
signature using Debian's archive keyring, records every valid signing
fingerprint and hashes the exact signed file.

Package resolution runs against an empty isolated dpkg status database with
`--no-install-recommends`. This prevents packages already installed on the CI
host from disappearing from the selected closure. Every selected package is
then downloaded and its byte length and SHA-256 are compared with signed apt
metadata. A canonical digest covers the complete sorted package closure.

## Frozen-snapshot validity

`Valid-Until` is recorded but not used to reject a historical snapshot. The
signature, suite/codename, package metadata and object digests remain mandatory.
Unauthenticated or downgrade-to-insecure repositories are never allowed.

## Promotion boundary

D0R-02 passes only when the exact workflow head produces:

- three valid signed `InRelease` records;
- archive-keyring version and hash;
- signer fingerprints;
- the complete dependency closure with exact package versions, architectures,
  filenames, sizes and SHA-256 values;
- one package-set SHA-256.

Passing D0R-02 does not create a root filesystem or disk image and does not boot
QEMU. `D1-01` must consume the committed lock and prove a reproducible rootfs,
image manifest, systemd boot and Wayland placeholder session.
