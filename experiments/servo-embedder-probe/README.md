# Servo embedder compile probe

This directory contains the compile-only public API sentinel for `TOS-D0A-01`.
The qualification workflow copies `src/main.rs` into the exact pinned Servo
checkout as an example target and compiles it under Servo's own `Cargo.lock` and
`rust-toolchain.toml`.

The probe verifies that a separate crate can name and type-check the builder,
event-loop, WebView, native-input, screenshot, popup-policy, crash and
accessibility surfaces selected by TrillionniumOS Desktop. It is never executed
by D0A-01 and does not prove a visible frame, input delivery, IME behavior,
network navigation or recovery. Those are D0A-02 runtime gates.
