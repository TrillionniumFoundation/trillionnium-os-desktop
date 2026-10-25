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
The user can explicitly open saved text as a copy in that new document; the old
effect capability, revision domain, pending receipt and retirement acknowledgement
are never adopted. Hepta's explicit predecessor composition attaches an old
recovery helper to its original retained source operation independently of this
local document action. Final trusted deployment inputs and evidence must match
the two-repo source pair. No production readiness or whole-machine recovery is
implied by these application changes.

## Reopen a saved user document

Launch a new Notes window through the existing Session, select **打开已保存笔记**
(open saved notes), then **打开副本** (open a copy). No terminal command or old
target identity needs to be entered. The picker shows a bounded first-line
preview and save age for closed, valid documents in this account's configured
Notes directory. These workspaces are local presentation groups, not separate
security containers. Empty windows that were never edited are omitted.

The application worker scans at most 4096 directory entries and returns at most
64 saved documents, sorted by checkpoint modification time. A truncated list
is labelled as such; it does not claim to enumerate the complete archive. Live
applications/recovery helpers retain their locks, and locked, malformed,
incomplete, symlinked or improperly owned entries are unavailable. Closing an
old window and refreshing can make its saved document available. No original
checkpoint is repaired, retired, deleted or rewritten by this picker.

Selection only describes source text; it grants no external effect authority.
On explicit open, the worker obtains the old incarnation lock again, validates
the complete bounded checkpoint, and compares the selected revision and text
digest. It accepts the copy only while the current document is still fresh
(`revision == 0`, empty text, a different target). Any intervening local or Hepta
edit makes the operation fail instead of overwriting that edit. The new model
is constructed with the current target, then receives only the saved UTF-8 text
as a local edit using the existing durable commit path. An empty saved text is
a local no-op; a nonempty copy starts at revision 1. Source receipts remain with
their original target and can still be independently reconciled/retired.

The picker and restore run on the existing bounded worker queue; Draw does not
scan files or wait for fsync. Editing is disabled while an accepted restore is
pending. A changed/busy source leaves the current document unchanged; a failed
destination write freezes that incarnation under the existing storage-ambiguity
rule. There is no automatic restore or retry. Abrupt process death can still
lose edits after the last successful checkpoint; the save status distinguishes
pending edits from completed local persistence.

The targeted regression commands are:

```sh
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-ui-core --test notes_store --locked
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-app-window --locked notes_organ::worker::tests
```

They exercise text-only import/new identity, unchanged original checkpoint and
receipt, old effect rejection, stale selections, live/symlink custody, bounded
UTF-8 previews, failed destination writes, actual restoring-process SIGKILL and
an intervening original effect on the worker queue. They do not by themselves
qualify a real compositor window, physical power failure, or production Hepta
authorization.

## Native close and committed input

With durable storage enabled, a native close request is checked after the
editor has processed the current frame. A final accepted edit and a close in
that same frame cannot automatically bypass the worker acknowledgement. While the local edit,
explicit restore, or a native editor transaction is pending, the close is
cancelled temporarily and the window shows **正在保存最后的编辑，保存完成后将关闭窗口。**
The renderer polls the bounded projection and requests another frame; it does
not wait for filesystem synchronization. Once the acknowledged saved text
matches and no accepted work remains, the pending close may complete.

While saving, the user may explicitly select **停止等待并关闭**; the dialog
states **停止等待时，最后的修改可能尚未保存。** This permits a close even if the
worker has stopped replying or synchronization is stalled, while the ordinary
close continues to wait for the acknowledgement. It does not cancel a command,
reissue an edit, infer that nothing was written, or roll back a possible commit.
The original incarnation's persisted state remains available for independent
recovery. **继续编辑** clears the pending close without changing the operation.

A CAS conflict or ambiguous storage result leaves the current draft visible.
The close dialog offers **继续编辑** and, only as an explicit user choice,
**关闭并舍弃未保存编辑**. Discarding the draft does not roll back a possible
committed application write, retire an original receipt, or clear a frozen
incarnation. It merely permits this window to close. SIGKILL, a process crash
or power loss bypasses this user interface; only the last successful checkpoint
is available for independent recovery.

[notes_input.rs](../../ui/app-window/src/notes_input.rs) handles native editor
transactions before the same storage path. IME Preedit is display-only; only a
confirmed Commit becomes a local durable edit. Composition retains its original
revision, so an intervening external effect cannot silently become its new CAS
base. A conflict offers **确认保留我的编辑** (an explicit new local edit against the
current revision) and **放弃未保存编辑，加载已保存内容**. These controls are disabled
during composition; failed storage remains frozen. A bounded native input queue
preserves already accepted transactions and rejects an overflowing new batch
without deleting the saved document or previously accepted input.

Source-level regressions are in
[notes_close_tests.rs](../../ui/app-window/src/notes_close_tests.rs) and
[notes_input_tests.rs](../../ui/app-window/src/notes_input_tests.rs). They exercise
the actual egui frame/input path and store-worker acknowledgement. The close
suite also checks a stalled save: explicit close releases the UI without
cancelling or repeating the queued edit. Real IME,
compositor pixels and physical input qualification still use the separate
[input guide](X11_IME.md) and [test plan](../../tests/ui/TESTPLAN.md).

## Implementation and invariants

| Owner / module | Responsibility |
| --- | --- |
| `ui/core/src/notes.rs` | Exact effect bytes, revision CAS, one pending receipt, independent observations and exact retirement |
| `ui/core/src/notes_checkpoint.rs` | Bounded versioned snapshot validation; rejects a different Session, task or incarnation, inconsistent content digests and malformed receipts |
| `ui/core/src/notes_store.rs` | Private directory/file custody, exclusive incarnation lock, atomic replacement and file/directory synchronization |
| `ui/app-window/src/notes_worker.rs` | One bounded background worker serializes application state and storage; Draw never waits for filesystem synchronization |
| `ui/app-window/src/notes_organ.rs` | Existing private effect/recovery channels plus a bounded presentation projection; local typing is coalesced and revision checked |
| `ui/app-window/src/notes_input.rs` | Bounded committed native input transactions, preedit isolation and original revision preservation |
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
reapplied against a newer revision. The worker queue and unsent edit are bounded.

## Headless process-crash and lost-ACK regression

[notes_recovery_process.rs](../../ui/app-window/tests/notes_recovery_process.rs)
contains `process_crash_and_lost_retirement_ack_recover_without_replaying_the_effect`.
It launches a real child that persists one exact test effect and is killed before
its receipt can be handed to the caller. A separate real `trill-notes-recovery`
process obtains the original incarnation lock, observes the exact operation and
payload digest, and returns the persisted receipt for independent comparison.
The recovery descriptor refuses the old mutation bytes; a wrong receipt digest
cannot release the pending receipt.

The fixture then drops the helper's actual successful retirement reply, kills
that helper and starts another. Repeating only the exact retirement
acknowledgement yields `AlreadyReleased`; observing the retired operation is unknown at revision 1,
while the document text and revision remain unchanged. This exercises durable
retirement and application receipts, without granting the fixture original
Hepta terminal authority. A real embedding still needs its authorized original
writer to reconcile and retain that outcome before it acknowledges retirement.

Run the process test and normal application tests from the repository root:

```sh
cargo +1.96.0 test --manifest-path ui/Cargo.toml -p trill-app-window --locked
```

The test needs no display server. It verifies actual Linux subprocess death,
private datagrams, exclusive locks, synchronized app storage and exact readback;
it does not simulate power failure, storage hardware loss or a production grant.

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
