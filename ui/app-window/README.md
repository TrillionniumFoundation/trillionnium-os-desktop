# trill-app-window

One native host window for Notes, Calculator or the restricted Terminal.
Session normally launches it with the app kind, workspace and task identity.

## Implementation

[main.rs](src/main.rs) owns the egui event loop and local app actions.
[notes_organ.rs](src/notes_organ.rs) connects the private target channel to the
bounded application worker in [notes_worker.rs](src/notes_worker.rs). That worker
serializes local and external Notes edits and storage; Draw consumes its
bounded projection without waiting for filesystem synchronization.

The Notes effect replaces one identified document subject to its revision.
`TRILL_NOTES_STATE_DIR` selects the original durable store; without it, the
explicit temporary mode remains. [Notes durability](../../support/ui/NOTES_DURABILITY.md)
specifies private storage, failure freezing and the recovery-only
[trill-notes-recovery](src/bin/trill-notes-recovery.rs) helper. A layout marker is separate from
compositor pixels, and neither marker nor process exit publishes a Hepta
durable terminal result. A lost reply can follow a real mutation; do not
automatically replay a timed-out request.

When durable storage is enabled, **打开已保存笔记** opens the local document
picker. **打开副本** explicitly copies a closed document's text into a new,
unedited target. The worker rechecks the source revision/digest and current
revision, persists through the original store, and never imports an old effect
or retirement receipt. File scanning and synchronization stay off Draw. See
[reopen and recovery rules](../../support/ui/NOTES_DURABILITY.md#reopen-a-saved-user-document)
for the bounded catalogue, lock/custody checks and race/failure behavior.

The Terminal is an explicit built-in command allowlist; it does not execute
arbitrary user shell commands. Preserve that boundary when adding commands.

## Development and validation

```sh
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-app-window --locked
```

Launch apps through Session and trill-ctl as described in
[Session](../session/README.md). Consult [NOTES_ORGAN](../../support/ui/NOTES_ORGAN.md)
for identity, bounded GUI handoff, revision checks and uncertain outcomes.
Use [RUN](../../support/ui/RUN.md) and [TESTPLAN](../../tests/ui/TESTPLAN.md)
for real process, window and owned-compositor validation.
