# D0A-01 pinned Servo compatibility evidence

**Date:** 2026-08-28  
**Servo commit:** `670ae8a70801b162e186f81cbb5bdd2d59c39108`  
**Claim class:** compile-only source/host qualification

The qualification workflow verifies a clean checkout at the exact commit,
records Cargo.lock/component-manifest SHA-256 values, compiles public embedder
symbol and method probes, compiles the generated aggregate sentinel, and runs
`cargo check --locked` for Servo's headed reference shell package.

The generated machine-readable result is
`manifests/servo-embedder-compat.json`; the exact public API sentinel is
`experiments/servo-embedder-probe/src/main.rs`.

A PASS demonstrates that the current pin supplies the minimum public type and
compile boundary needed to begin the product wrapper. It does not demonstrate a
running Servo process, a window, a rendered frame, input, IME, external
navigation, Debian boot, a production AgentPort or any web side effect.
