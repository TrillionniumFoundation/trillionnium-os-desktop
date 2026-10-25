# trill-shell

The eframe/egui host Shell displays workspaces, local conversation drafts,
context, task lifecycle and runtime observations. `src/main.rs` renders the
Shell; `conversation.rs` and `local_drafts.rs` manage local content;
`hepta_panel.rs` displays original-runtime observations.

Session owns application processes. Shell requests bounded host actions and
renders observations; it does not own a Hepta writer, create Final-use grants,
execute Notes effects, or submit an authenticated objective. A first egui layout
is not proof that a compositor presented pixels.

From the repository root:

```sh
cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-shell --locked -j 2
```

Development and technical contracts: [chat workspace](../../support/ui/CHAT_WORKSPACE.md),
[runtime observer](../../support/ui/HEPTA_OBSERVER.md),
[integration boundaries](../../support/ui/INTEGRATION_CONTRACTS.md),
[host build and acceptance](../../support/ui/RUN.md).
