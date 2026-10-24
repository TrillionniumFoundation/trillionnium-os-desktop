# trill-app-window

One native host window for Notes, Calculator or the restricted Terminal.
Session normally launches it with the app kind, workspace and task identity.

## Implementation

[main.rs](src/main.rs) owns the egui event loop and local app actions.
[notes_organ.rs](src/notes_organ.rs) connects the private target channel to the
GUI thread. The GUI thread serializes local and external Notes edits.

The Notes effect replaces one identified in-memory document subject to its
revision. It does not save a user file. A layout marker is separate from
compositor pixels, and neither marker nor process exit publishes a Hepta
durable terminal result. A lost reply can follow a real mutation; do not
automatically replay a timed-out request.

The Terminal is an explicit built-in command allowlist; it does not execute
arbitrary user shell commands. Preserve that boundary when adding commands.

## Development and validation

```sh
RUSTUP_TOOLCHAIN=1.88.0 cargo test --manifest-path ui/Cargo.toml -p trill-app-window --locked
```

Launch apps through Session and trill-ctl as described in
[Session](../session/README.md). Consult [NOTES_ORGAN](../../support/ui/NOTES_ORGAN.md)
for identity, bounded GUI handoff, revision checks and uncertain outcomes.
Use [RUN](../../support/ui/RUN.md) and [TESTPLAN](../../tests/ui/TESTPLAN.md)
for real process, window and owned-compositor validation.
