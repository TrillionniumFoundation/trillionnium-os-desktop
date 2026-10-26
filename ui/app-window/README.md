# trill-app-window

One native host window for Notes, Calculator or the restricted Terminal.
Session normally launches it with the app kind, workspace and task identity.

## Implementation

[main.rs](src/main.rs) owns the egui event loop and local app actions.
[notes_organ.rs](src/notes_organ.rs) connects the private target channel to the
bounded application worker in [notes_worker.rs](src/notes_worker.rs). That worker
serializes local and external Notes edits and storage; Draw consumes its
bounded projection without waiting for filesystem synchronization.

[notes_input.rs](src/notes_input.rs) distinguishes transient IME Preedit from
committed native editor transactions. Composition keeps the revision observed
before it began; a concurrent original effect causes a visible conflict rather
than silently rebasing the user's text. The user can explicitly keep the local
edit against the current revision or load the saved content. Input processing
and the close/save barrier have separate
[input](src/notes_input_tests.rs) and [close](src/notes_close_tests.rs) tests.

The Notes effect replaces one identified document subject to its revision.
`TRILL_NOTES_STATE_DIR` selects the original durable store; without it, the
explicit temporary mode remains. [Notes durability](../../support/ui/NOTES_DURABILITY.md)
specifies private storage, failure freezing and the recovery-only
[trill-notes-recovery](src/bin/trill-notes-recovery.rs) helper. A layout marker is separate from
compositor pixels, and neither marker nor process exit publishes a Hepta
durable terminal result. A lost reply can follow a real mutation; do not
automatically replay a timed-out request.

A native close request normally waits for the worker's acknowledgement of the final
accepted local edit, including input transactions still queued by the native
editor. The window shows save progress and closes when the acknowledged
document matches. While waiting, **停止等待并关闭** explicitly permits closing
with the notice that the final changes may not have been saved. It neither
cancels/repeats the pending edit nor rolls back a possibly committed write.
Conflict or unknown persistence retains the visible draft;
**继续编辑** keeps the window, while **关闭并舍弃未保存编辑** explicitly abandons
the unsaved draft. This is a nonblocking renderer decision, not an fsync on Draw
or a guarantee against SIGKILL/power failure. See the
[close and input contract](../../support/ui/NOTES_DURABILITY.md#native-close-and-committed-input).

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

The headless
[process recovery test](tests/notes_recovery_process.rs) starts and kills a real
application-storage child, independently reads its exact persisted receipt via
`trill-notes-recovery`, rejects old mutation replay and a wrong retirement
digest, loses an actual retirement ACK, kills the helper, and checks
`AlreadyReleased` after a second helper starts. The ordinary package test command
above includes it. This exercises process/storage/transport boundaries with
test identities; original Hepta production authority and physical power loss
remain separate qualifications.

The [executed ordinary reopen probe](../../tests/ui/evidence/2026-10-24-notes-reopen/README.md)
records real close/reopen, picker selection, independent AT-SPI readback,
continued editing and unchanged source storage, with exact binaries and
actual window captures. It remains separate from production effect recovery.

The versioned original Session lifetime and Root-required durable storage
contract is specified in [NOTES-LIFETIME](../NOTES-LIFETIME.md).
