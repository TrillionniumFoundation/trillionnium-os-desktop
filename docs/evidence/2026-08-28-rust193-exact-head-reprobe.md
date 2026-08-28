# Rust 1.93 exact-head re-probe

**Date:** 2026-08-28

The hosted runner is now available and the branch source was formatted by `cargo fmt` under Rust 1.93.0. This marker commit exists only to trigger the permanent `desktop-ci` workflow against the resulting source tree.

No PASS is recorded here. Promotion requires non-empty runner steps and successful format, Clippy, workspace tests, and `hepta-browserd --self-check` on this exact commit.
