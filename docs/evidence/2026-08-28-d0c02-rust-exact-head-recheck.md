# D0C-02 exact-head Rust recheck

**Date:** 2026-08-28  
**Branch:** `codex/d0c02-transport-v2`  
**Checkpoint:** formatted source; exact Rust gate re-triggered

The GitHub-hosted Ubuntu runner is available again and installed the exact
Rust 1.93.0 toolchain. The first real run reached `cargo fmt --all --check`
and reported formatting differences only. A one-shot workflow applied
`cargo fmt --all` and committed the resulting source as
`cbd7a77a673825fdd126efde9135ee9f5f988bd4`.

This checkpoint intentionally re-triggers the permanent desktop CI against the
formatted exact head so that Clippy, workspace tests and the browserd
self-check execute. Their result is not claimed by this document; the PR and
machine-readable evidence must be updated only after the workflow reaches a
terminal result.

No listener, BrowserActor, Servo runtime, visible window, Debian image or
external effect is enabled by this checkpoint.
