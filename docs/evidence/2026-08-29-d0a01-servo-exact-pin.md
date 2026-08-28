# D0A-01 exact-pin Servo qualification

**Date:** 2026-08-29  
**Servo commit:** `670ae8a70801b162e186f81cbb5bdd2d59c39108`  
**Status:** `QUALIFICATION_PENDING`

## Candidate gate

The candidate checks out the exact upstream commit, installs the toolchain
specified by Servo's `rust-toolchain.toml`, installs the package set recorded by
Servo for Ubuntu 24.04 and compiles three locked targets:

```text
servo / winit_minimal
servo / trillionnium_embedder_probe
servoshell / servoshell
```

The workflow also verifies the zero-delta patch ledger, exact source hashes,
required WebView methods and delegate callbacks, and a clean checkout after the
temporary example is removed.

## Promotion rule

This document must not be changed to `PASS` until the exact PR head has a
completed successful `servo-exact-pin` workflow and the generated
`servo-qualification-result.json` has been reviewed and committed atomically
with `CURRENT_STATE.md` and `manifests/repository-state.json`.

## Current non-claims

- Servo has not been started by this checkpoint.
- No window or frame is claimed.
- No native input or IME delivery is claimed.
- No network navigation or WebDriver listener is used.
- No Debian image or product readiness is claimed.
