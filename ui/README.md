# Rust desktop workspace

This workspace builds the Linux host Shell, Session and application windows. The
renderer is egui/eframe; native window creation does not qualify Asterinas
graphics, a web build, a compositor, or a mobile device.

## Modules

| Module | Responsibility |
| --- | --- |
| [core](core/README.md) | Typed host messages, identity, observations and Notes wire data |
| [session](session/README.md) | Process lifecycle, bounded IPC and Hepta observation |
| [shell](shell/README.md) | Chat/workspace presentation and local drafts |
| [app-window](app-window/README.md) | Notes, Calculator and restricted Terminal windows |
| [broker](broker/README.md) | Bounded admission and trusted-owner/target seams |

## Build and verify

Run from the repository root with the pinned Linux host dependencies in
[RUN](../support/ui/RUN.md). The blocking host workflow uses Rust 1.88.0; a
result on another toolchain is a separate development observation.

```sh
RUSTUP_TOOLCHAIN=1.88.0 cargo build --manifest-path ui/Cargo.toml --workspace --bins --locked
RUSTUP_TOOLCHAIN=1.88.0 cargo test --manifest-path ui/Cargo.toml --workspace --locked
bash tests/ui/check-host.sh
bash tests/ui/headless-weston.sh
```

The two scripts have additional host prerequisites documented in RUN; they are
not interchangeable with the package tests. A first-layout marker does not
prove composited pixels. Keep ignored CJK/IME checks and physical display
qualification separate from headless results.

## State and trust

[BOUNDARIES](../support/ui/BOUNDARIES.md) defines the same-UID prototype boundary;
workspace names are presentation labels, not security domains.
[CHAT_WORKSPACE](../support/ui/CHAT_WORKSPACE.md) owns draft/context semantics;
[NOTES_ORGAN](../support/ui/NOTES_ORGAN.md) owns target execution and uncertain
outcomes. The original Hepta owner retains durable operation authority.
Current product qualification is recorded in [STATUS](../docs/STATUS.md).
