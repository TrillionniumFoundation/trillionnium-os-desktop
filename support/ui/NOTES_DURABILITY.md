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
It cannot adopt an old effect capability by opening a file. Restoring old text
into the normal workspace remains separate work. Hepta's explicit predecessor
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
| `ui/app-window/src/notes_worker.rs` | One bounded background worker serializes application state and storage; Draw never waits for filesystem synchronization |
| `ui/app-window/src/notes_organ.rs` | Existing private effect/recovery channels plus a bounded presentation projection; local typing is coalesced and revision checked |
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
