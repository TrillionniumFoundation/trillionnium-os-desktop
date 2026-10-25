# trill-app-window

The eframe/egui host application process renders Notes, Calculator and a fixed
allowlist terminal. `src/main.rs` owns the GUI and its local edits;
`src/notes_organ.rs` hands private effect/recovery requests to that GUI thread.
The terminal does not run user-supplied shell commands.

Session-launched Notes uses a private durable document store. A trusted startup
can reopen a document under a new target incarnation; private recovery observes
old receipts without replaying old effects. Direct legacy probes without a
store remain explicitly memory-only. Neither mode authorizes Hepta operations.

From the repository root:

```sh
cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-app-window --locked -j 2
```

Development and technical contracts: [Notes persistence](../../support/ui/NOTES_PERSISTENCE.md),
[original Notes v1 composition](../../support/ui/NOTES_ORGAN.md),
[CJK rendering and separate IME gate](../../support/ui/CJK_RENDERING.md),
[host build and acceptance](../../support/ui/RUN.md). Real GUI recovery requires
its own passing application test; storage unit tests alone do not establish it.
