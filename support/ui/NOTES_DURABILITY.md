# Notes application durability and process recovery

## Implemented boundary

`TRILL_NOTES_STATE_DIR` enables durable application data in the original
`trill-app-window`. The directory must be absolute, private to the application
account, and have an existing parent. The product launcher provisions that
parent. Without this setting the existing explicitly temporary mode remains.

The application stores its text, CAS revision, one pending effect receipt and
the last exact retirement acknowledgement together. This is application data,
not a second Hepta operation ledger. The original production writer retains
authorization, operation identity, policy generation and durable terminality.

A newly launched application gets a new target identity and a fresh document.
It cannot adopt an old effect capability by opening a file. The ordinary Notes
window now provides **重新打开已保存的笔记** and **刷新已保存的笔记**. Choose an entry
in a new, unchanged empty Notes window to copy its saved text and continue
editing. This uses the same application state directory and worker. The old
incarnation and its pending/retired receipt remain intact; the new window saves
only the text under its own target and local revision. Hepta's explicit predecessor
composition now attaches an old recovery helper to its original retained source
operation; final trusted deployment inputs and evidence must match the two-repo
source pair. No production readiness or
whole-machine recovery is implied by these application changes.

## Implementation and invariants

| Owner / module | Responsibility |
| --- | --- |
| `ui/core/src/notes.rs` | Exact effect bytes, revision CAS, one pending receipt, independent observations and exact retirement |
| `ui/core/src/notes_checkpoint.rs` | Bounded versioned snapshot validation; rejects a different Session, task or incarnation, inconsistent content digests and malformed receipts |
| `ui/core/src/notes_store.rs` | Private directory/file custody, exclusive incarnation lock, atomic replacement and file/directory synchronization |
| `ui/core/src/notes_catalog.rs` | Bounded, read-only discovery of the existing checkpoints and complete-snapshot selection fencing; no new catalog file or ledger |
| `ui/app-window/src/notes_worker.rs` | One bounded background worker serializes application state and storage; Draw never waits for filesystem synchronization |
| `ui/app-window/src/notes_organ.rs` | Existing private effect/recovery channels plus a bounded presentation projection; local typing is coalesced and revision checked |
| `ui/app-window/src/notes_input.rs` | Original egui editor transaction: preedit stays transient, committed input retains its starting CAS revision, rejected oversized replacement preserves text/selection/undo |
| `ui/app-window/src/bin/trill-notes-recovery.rs` | Separate process exposing only the original incarnation's observation and exact retirement over an inherited private datagram pair |

Each incarnation lives under
`<state>/<session_instance>-<task_id>-<incarnation>/`. Its identity components
are validated before use as names. The snapshot is limited to 16 KiB; Notes
text remains limited to 4096 UTF-8 bytes, requests to 8192 bytes, replies to
2048 bytes. Opening data and lock files rejects symlinks, nonregular files,
hard links, foreign ownership and group/world permissions.

Creation is exclusive. An existing incarnation directory, including one left
by interrupted initialization, is never reset or silently adopted. A process
holds the incarnation's `flock` throughout its lifetime. A competing recovery
process is refused while that lock is held.

For a changed state the worker writes a separate file, synchronizes it,
atomically renames it to `document.json`, and synchronizes the containing
directory. Only then does it publish the new projection and return an effect
or retirement receipt. A storage error freezes further changes: a failed sync
does not prove that the previous bytes were never committed. Independent
recovery must read the original persisted state after the old owner exits.

Local edits use the same revision domain as external effects. If an external
effect wins while a local edit is queued, the stale local edit is rejected and
the unsaved draft remains visible with a conflict notice. It is not silently
reapplied against a newer revision, including when the user continues typing.
The user can explicitly select **确认保留我的编辑** to submit that draft against
the latest observed revision, or **放弃未保存编辑，加载已保存内容** to load the saved
text without writing. Concurrent changes still fail the worker's revision CAS.
The worker queue and unsent edit are bounded.

## Reopen a note in the ordinary UI

Open a new Notes window from the existing Shell, expand **重新打开已保存的笔记**,
and select **刷新已保存的笔记**. The list shows the first 48 displayable characters
and revision of each closed, noninitial checkpoint, newest first. Select **打开**
on the desired note. Current text or any earlier local/external revision disables
replacement; use a new Notes window instead of discarding an active document.
The editor is briefly disabled while the existing worker performs that request.

The list is a transient projection of existing `document.json` files. It uses
the store's already-open directory descriptor, an independent `openat(".")`
directory cursor and validated identity components. A root path replacement
cannot redirect a running application's discovery. It never follows links or
creates a missing source lock. Enumeration refuses more than 1024 directory
entries rather than returning a falsely complete list. Each source still obeys
the 16 KiB snapshot bound. Live/locked, corrupt and custody-invalid checkpoints
remain untouched and are counted as unavailable. Close the original window or
wait for its actual supervisor-confirmed exit before refreshing. A recovery
helper can also temporarily hold the original lock.

Opening reacquires the original incarnation lock and checks the entire selected
checkpoint's digest and revision. A source modified or retired since listing
requires a refresh. The same worker serializes this action with new-window local
edits and external effects; if a new-window effect wins first, reopening refuses
without overwriting it. The copied text is an ordinary local edit, never a saved
request replay, predecessor grant, receipt acknowledgement or original-owner
terminal result. Old effects remain independently reconcilable through the
unchanged recovery helper. If the new save fails, the new store freezes and the
old bytes are retained for independent recovery.

The locked egui 0.31 editor mutates its visible text during IME `Preedit` and
`Commit`. Notes therefore keeps preedit out of the worker and checkpoint. Empty
preedit can precede a later commit, so it does not rebase the saved revision.
Cancellation restores the committed editor text and selection. A final commit
uses its original revision; a concurrent external update leaves that local
commit visible but unsaved with the existing conflict notice. A complete input
over 4096 UTF-8 bytes is refused atomically with its prior selection and undo
history preserved. These are application editor guarantees; synthetic native
widget tests do not qualify actual OS IME candidate positioning or physical input.

## Original Hepta observation contract

The existing recovery channel now also accepts the original Hepta
`read_document_state` request and correlates its 128-bit nonce, fixed target,
revision, text digest and pending-receipt state. Observation conveys neither
admission nor an effect grant.

`read_previous_receipt` returns a present `pending_receipt: null` for a fresh
document with no attached predecessor. It does not scan unrelated saved
documents, guess an old owner, or claim that other incarnations have no pending
operations. A deployed owner must attach the exact old recovery endpoint using
its existing retained operation and target identity.

## Recovery process contract

The trusted host starts `trill-notes-recovery` with:

```
--state-dir <absolute-private-root>
--notes-session <original-32-hex-session>
--task-id <original-task-id>
--notes-incarnation <original-32-hex-incarnation>
```

Standard input must be one end of a connected, unnamed Unix datagram pair.
There is no socket listener or endpoint discovery. The caller keeps the other
end and sends the existing `observe` / `acknowledge_terminal` messages. The
helper does not accept an effect channel, signer, grant or replacement request.
Even a byte-identical `replace_note` frame is refused. Exact repeated retirement
survives another helper restart and returns `already_released`.

After exclusively locking and validating the old snapshot, the helper writes
`TRILL_NOTES_RECOVERY_READY_V1` plus newline to stdout. The trusted parent waits
for this bounded startup signal before service readiness. It proves only that
this child opened that incarnation; it is not an effect receipt or permission.
The original Hepta process composition validates the caller-selected old target
and operation against its retained source, verifies the helper hash, seals its
executable bytes, and passes only the private recovery pair. A Linux
parent-death signal prevents a helper orphan from retaining the data lock.

The host must first observe the predecessor process's completed reap through
its original supervisor. Merely sending SIGKILL or seeing `/proc/<pid>/exe`
disappear does not prove that every old descriptor has been released. An early
recovery attempt may return `WouldBlock`; the correct response is to wait for
the same predecessor's observed exit, never unlink its lock or create a new
effect identity. The real-window probe initially failed at this boundary and
was corrected to wait for the original Session's terminal child state.

## Development and validation

From the repository root, using the UI's Rust 1.96 baseline:

```
cargo +1.96.0 test --locked --manifest-path ui/Cargo.toml -p trill-ui-core -p trill-app-window
cargo +1.96.0 clippy --locked --manifest-path ui/Cargo.toml -p trill-ui-core -p trill-app-window --all-targets -- -D warnings
cargo +1.96.0 build --locked --manifest-path ui/Cargo.toml -p trill-session -p trill-app-window --bins
```

The ordinary user path has a separate real-window fixture:

```sh
/usr/bin/python3 -B tests/ui/test-notes-reopen-window.py \
  --binary-dir /absolute/matching-binary-directory \
  --hepta-root /absolute/exact-pinned-hepta-checkout \
  --font /absolute/real-host-CJK-font.ttc \
  --output /absolute/new-notes-window-evidence
```

It requires Xvfb, `dbus-run-session`, `xdotool`, libX11/libXRes and system Python
GI bindings for GTK/AT-SPI. It copies and hashes the supplied binaries, creates
its own display/bus/state, verifies the Session-owned child and server-side XRes
PID before input, pastes CJK/combining/emoji text through the actual clipboard,
closes the original window through WM_DELETE_WINDOW, and uses the ordinary
saved-note controls in a new window. Checkpoint readback and a separate recovery
helper verify fresh identity/revisions and preservation of the old pending
receipt. Its JSON, screenshots and logs remain in the new output directory.
Synthetic keyboard/clipboard automation is not physical IME qualification;
the fixture does not run a production Hepta authority or claim writer finality.
Repeat it against the actual final binary hashes when claiming that source pair.

Run `tests/ui/test-notes-crash-recovery.py <absolute-binary-directory>` only
inside a task-owned Xvfb/Weston with `TRILL_NOTES_PROBE_ISOLATED=1`.
It launches the real Session and Notes window, sends one complete effect frame,
discards the effect reply, waits for the application's actual saved bytes,
kills only its owned Notes child, waits for Session to reap it, then launches
two successive recovery processes. It checks the exact original receipt,
mutation rejection, persisted retirement and unchanged document revision.

The probe's parent is an isolated transport fixture. Its result explicitly
reports `production_authority=false`, `original_writer_terminal=false` and
`compositor_pixels=false`. Combining this with the original Hepta writer,
actual Root authority, revocation and installed recovery remains required
before the production Notes blocker can be closed. The separate Hepta
`notes_actual_app_crash_original_owner_reopen_and_helper_ack_restart` test
adds original SQLite owner close/exact-cut reopen and real helper retirement
reply loss/restart. It must be run against this exact companion build; its
source authority and issuer remain explicitly test-only. Its recipe is in
Hepta [NOTES_RECOVERY_QUALIFICATION](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/main/codex-rs/hepta-agentd/NOTES_RECOVERY_QUALIFICATION.md);
read it at the exact companion source-profile commit when executing the probe.
