# trill-shell

The native egui/eframe presentation process. Workspace/Chat is the default
entry; Tasks, Context and Console are workspace views.

## Ownership and code map

[main.rs](src/main.rs) owns presentation and the bounded worker handoff.
[conversation.rs](src/conversation.rs) renders typed drafts and context;
[local_drafts.rs](src/local_drafts.rs) implements explicit private export/restore.
[hepta_panel.rs](src/hepta_panel.rs) presents runtime observations.
[objective_panel.rs](src/objective_panel.rs) presents bounded original-owner
Objective status, cancellation and navigation recovery.

Session restart preserves the existing caller IDs and queries them through the
new trusted transport. Shell process restart reads navigation IDs from the
original owner's availability projection; restored cards begin Unknown and
cannot resend their requests. New IDs carry a workspace navigation prefix;
legacy IDs retain an unknown workspace. Neither classification supplies scope
or authority. A fresh complete traversal is required before enabling new writes,
and an unfinished/unknown request prevents minting a replacement ID. The previous
request list only selects which original status to query. Cancellation controls
are bound to the selected intent identity and remain stable when history appears.

Unsaved drafts are local state. The current mainline chat is not a submitted
Hepta Objective. Never infer an owner receipt from a local animation, a queued
UI action, a first-frame marker or a running host PID. The original owner must
provide operation outcomes and reconciliation.

## Failure and input handling

Follow [OBSERVATION_FRESHNESS](OBSERVATION_FRESHNESS.md) for stale/unknown
projection. Keep transport work off the rendering path and distinguish failure
to enqueue from a request whose result is unknown.

IME composition, confirmation keys and semantic widget activation require
separate handling. Follow [X11_IME](../../support/ui/X11_IME.md) and
[CJK_RENDERING](../../support/ui/CJK_RENDERING.md); font coverage and a headless
layout test do not establish a working input method or accessibility bridge.

## Development

```sh
RUSTUP_TOOLCHAIN=1.88.0 cargo test --manifest-path ui/Cargo.toml -p trill-shell --locked
```

See [workspace setup](../README.md), [Chat contract](../../support/ui/CHAT_WORKSPACE.md)
and [host test plan](../../tests/ui/TESTPLAN.md) for owned-window and compositor
checks. If CARGO_TARGET_DIR is set, use its debug directory for the binaries.
