# D0R-02 execution checkpoint — signed Debian input closure

**Plan revision:** `2026-08-28-d5`  
**Work package:** `D0R-02`  
**Checkpoint status:** `INPUT_VALIDATED`  
**Next gate:** `D1-01`

Exact source head `6825f9bd4bd012212559d187315bca285a6ae3d2` passed workflow run
`33196743127`. The generated lock was promoted without editing to
`manifests/debian-snapshot.lock.v1.json` and is regenerated and compared byte-for-byte by the
permanent workflow.

Observable exit: snapshot `20260828T000000Z`; three pinned Debian
13 primary trust roots; three exact signed `InRelease` digests; empty-dpkg,
no-recommends, fail-closed APT resolution; `319`
downloaded and metadata-verified packages; package-set SHA-256
`89918a968afafdbabe03e43794565cb1dc936f3f24a09ec81030be4a4085333a`; and all image/runtime/release claims false.

This closes only D0R-02. D1-01 remains responsible for deterministic rootfs and
image construction, independent rebuild equality, QEMU/systemd/Wayland evidence
and live test-only socket activation.
