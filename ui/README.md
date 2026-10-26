# Rust desktop workspace

This workspace builds the Linux host Shell, Session and application windows. The
default renderer is egui/eframe. The explicit `hepta-native-makepad` Shell
feature composes the original pinned Hepta Robrix/Makepad app, shared
ChatWorkspace and authenticated Agentd text worker. Both renderers use Rust
native windows. Each Asterinas display/input or mobile target requires its own
execution evidence.

The original UI/core, Agentd host dependencies and all four original AccessKit
patches resolve from Hepta `760363e06c5f4a115de039ffa7bd7e7767bd1fd9`
(tree `87bcc851d794c89ede183353e7493461b931ebed`). The patch entries live in
this workspace's Cargo root because Cargo does not inherit dependency-workspace
patches. The [fixed source map](../docs/SOURCES.md#hepta-native-organ) links the
same original modules and their development contracts.
The current [dependency contract](../support/ui/DEPENDENCIES.md) describes both
Cargo roots, source checks and lock updates. Results from the historical
`7ea3df4` combination remain attached to that older source.

Normal `hepta-native-makepad` keeps original SDK 337566c8 and the 54-file bundle.
The separate `hepta-native-clipboard-sdk` feature requires the exact all-SDK
override, a separate candidate worktree/lock and the 61-file bundle; only that
candidate advertises native PasteText. See [the two profiles](../support/ui/PRODUCT.md#explicit-original-sdk-clipboard-candidate).
Latest original UI 43/43 and AccessKit 54/54 results are scoped default-SDK
package tests, not a full Desktop workspace, release or real window result;
their [exact execution record](../results/integration/2026-10-24-original-owner-product/text-native-v10-v11/README.md)
does not qualify the clipboard candidate or installed production.

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
[RUN](../support/ui/RUN.md). The integrated product uses Rust 1.96.0 to match
the original Hepta runtime dependencies. Earlier Rust 1.88 receipts remain
historical evidence for their recorded source and binaries.

```sh
RUSTUP_TOOLCHAIN=1.96.0 cargo build --manifest-path ui/Cargo.toml --workspace --bins --locked
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml --workspace --locked
RUSTUP_TOOLCHAIN=1.96.0 cargo build --manifest-path ui/Cargo.toml --locked \
  --workspace --bins --features trill-shell/hepta-native-makepad
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
