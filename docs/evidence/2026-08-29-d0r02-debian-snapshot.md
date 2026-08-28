# D0R-02 signed Debian snapshot evidence

**Date:** 2026-08-29  
**Requested snapshot:** `20260828T000000Z`  
**Status:** `RESOLUTION_PENDING`

The candidate verifies signed `InRelease` files for trixie, trixie-updates and
trixie-security, resolves the complete amd64 dependency closure from an empty
dpkg state, downloads every `.deb` and verifies its apt-metadata size and
SHA-256.

This file must remain pending until the exact PR head has a successful
`debian-snapshot-lock` run and its generated lock has been committed atomically
with `manifests/debian-base.selection.json`, `CURRENT_STATE.md` and
`manifests/repository-state.json`.

No rootfs, disk image, QEMU boot, Wayland surface, Secure Boot or product
readiness is claimed by this checkpoint.
