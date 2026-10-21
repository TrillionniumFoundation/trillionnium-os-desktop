# First Linux Notes destination

This slice provides real, bounded Linux socketpair I/O to the existing native
Rust Notes application. Its operation is **replace the in-memory text of one
identified Notes document, subject to a revision comparison**. The document is
not saved to a user file. This is a small destination adapter, not a compositor,
global keyboard controller, mobile device port, or an Asterinas desktop.

The standalone Session keeps each new destination private and reports
`original_owner_registered: false`. Public Snapshot / Launch / Cancel IPC has
no Notes edit or handle-export command. Shell displays the target incarnation
and channel observation; it cannot submit an effect.

## Implementation and ownership

| Path | Responsibility |
| --- | --- |
| `ui/core/src/notes.rs` | Bounded wire types, exact-byte hashes, document revision comparison, one retained app receipt |
| `ui/broker/src/notes.rs` | Private Linux destination handle, synchronous exact-byte I/O, conservative unknown outcomes |
| `ui/app-window/src/notes_organ.rs` | Inherited stdin receiver, bounded handoff to the egui thread |
| `ui/app-window/src/main.rs` | Notes update, user-edit revision changes, layout-only witness |
| `ui/session/src/main.rs` | Existing child-process owner creates and retains private handles |
| `ui/shell/src/main.rs` | Read-only destination observation |
| `ui/broker/tests/notes_target.rs` | Real socketpair tests against an explicit application-model fixture |
| `ui/broker/examples/notes_host_probe.rs` | Isolated real-window target probe, separate from a production-owner run |
| `tests/ui/notes-target-v1.json` | Cross-language request, response, payload hash, scope hash and predecessor hash |

The original default-deny broker is reused from PR #210 head
`24dc73185d739695ef755c6bbd9d22ee38acf9be`. Its sessions, admission bounds,
generation checks and denied effect capabilities remain the same. The private
destination module does not give those sessions an effect capability. No new
authority, signer, operation allocator, durable effect ledger or model callback
is introduced in UI code.

## Required original-owner composition

The production host must explicitly attach the destination to the existing
Hepta `FinalUseProductionOutboxTarget` / production durable writer. Before
target entry, the original owner verifies signed Final-use, consumes its nonce
and maintains its own operation history and generation fences. The private
target handle is a host composition input, never a renderer-deserialized value.

```rust,ignore
NotesTarget::from_private_channel(stream, target_identity)?;
target.enter_exact(original_payload_bytes, &NotesDispatchBinding {
    operation_id,
    destination_id,
    target: target_identity,
    payload_sha256,
});
target.observe(original_operation_id, original_payload_sha256);
```

The synchronous production consumer-entry must call `enter_exact` before
returning a future. It performs the physical write and bounded app reply read
immediately, without returning a deferred effect closure. This does not claim
that every original Final-use issuer lock spans the entire GUI update.

There is no automatic Agentd registration or same-UID socket for exporting the
target. Trusted bootstrap must supply the same private endpoint to the original
owner through explicit in-process composition or controlled descriptor
inheritance. **Standalone Session does not yet implement that bootstrap
handoff.** A publicly reachable UDS with only a UID check would not provide
Final-use authority. The default remains deny until the original owner attaches.

## Frozen wire contract, version 1

Topic: `trill.notes.replace.v1`. Destination:
`trill.notes:{session_instance}:{task_id}:{incarnation}`. Both instance strings
are 32 lowercase hexadecimal characters and task id is a nonzero `u64`.
Session obtains fresh OS randomness for Session and child incarnations. An old
identity must never identify a replacement child. These are generation fences,
not authorization credentials.

Each frame is a four-byte unsigned big-endian length, then exactly that many
UTF-8 JSON bytes. There is no newline delimiter. Requests are at most 8192
bytes, Notes text at most 4096 UTF-8 bytes, and replies at most 2048 bytes.
Unknown or duplicate JSON fields, unknown actions, incorrect identities and
unsupported versions fail closed.

```json
{
  "schema_version": 1,
  "action": "replace_note",
  "operation_id": "original-owner-operation",
  "destination_id": "trill.notes:11111111111111111111111111111111:7:22222222222222222222222222222222",
  "target": {
    "session_instance": "11111111111111111111111111111111",
    "task_id": 7,
    "incarnation": "22222222222222222222222222222222"
  },
  "expected_revision": 0,
  "text": "Notes target / 中文"
}
```

The example is explanatory; the fixture contains exact bytes and hashes.
Whitespace and key order contribute to the payload hash. The target parses to
validate, hashes the supplied bytes, checks operation/destination/target/digest
against the original binding, then sends those original bytes without
reserializing the mutation.

The original `OperationIntentV1` scope must equal the lowercase SHA-256 of this
UTF-8 byte sequence (`\0` means one NUL byte; numbers use canonical decimal):

```text
trill.notes.scope.v1\0{session_instance}\0{task_id}\0{incarnation}
```

`NotesTargetIdentity::scope_sha256` supplies this derivation. The scope pins one
document incarnation; it does not include revision. The original production
adapter recomputes it from the parsed exact payload and compares it with the
original owner's scope before physical entry.

The original `OperationIntentV1` predecessor expectation must also be present
and equal the lowercase SHA-256 of this UTF-8 byte sequence:

```text
trill.notes.predecessor.v1\0{session_instance}\0{task_id}\0{incarnation}\0{expected_revision}
```

`NotesTargetIdentity::predecessor_sha256` supplies this derivation. The original
production adapter compares it with the durable semantic expectation. The app
compares the same identity and revision on the GUI thread when applying. Local
edits increment that same revision, preventing a request with an old expectation
from silently overwriting an intervening user edit.

A complete reply has `schema_version`, `target`, `operation_id`,
`payload_sha256`, and `result`. Results are:

| Status | Other result fields | Meaning |
| --- | --- | --- |
| `applied` | `previous_revision`, `revision`, `text_sha256` | App document changed; current revision is previous + 1 |
| `not_applied` | finite `reason`, `current_revision` | App proves this attempt did not mutate |
| `unknown` | `current_revision` | No matching retained application receipt |

The target checks response identity, exact payload hash, applied predecessor,
new revision and text hash. It cannot turn an unrelated ack into completion.

Read-only requests contain `schema_version: 1`, `action: "observe"`, `target`,
`operation_id`, and `payload_sha256`; no text. The app reports only its one
retained matching applied receipt. A missing receipt is unknown, even if current
text matches. Exact replay of the retained operation and payload returns the
same receipt without repeating the mutation. A conflicting payload for that
retained operation is refused. This volatile last-mutation cache is not durable
history and cannot make older unknown operations retryable.

## Failure and observation semantics

One private channel is serialized. Concurrent callers fail before writing,
instead of entering an unbounded queue. A total two-second deadline bounds
incremental request writes and response reads. Malformed or misbound requests
write zero destination bytes.

After bytes may have been sent, transport loss, timeout or an unrelated reply
is `Indeterminate`. Transport/framing/correlation failure poisons and shuts
down the channel, preventing silent replay. A lost ack can follow a real
mutation. Timeout and cancellation do not roll it back. A poisoned channel's
observer is unavailable; the original owner must retain unknown and seek
independently recovered target evidence if available later.

The app has a bounded one-slot GUI handoff. Expired handoffs are discarded
before document mutation. The GUI thread serializes external and local edits.
An applied reply means its in-memory document changed; the original production
owner still owns durable outcome publication.

After constructing a changed widget layout, the app writes
`TRILL_NOTES_LAYOUT_V1:{revision}:{text_sha256}` to owned stdout. This is an
independent layout witness, not compositor pixel evidence. Screenshots or
compositor observations remain separate. Process exit or this marker cannot
prove a successful Hepta task, persistence, or target-kernel graphics.

## Development and verification

Use the Linux host toolchain from [RUN.md](RUN.md).

```sh
cargo test --manifest-path ui/Cargo.toml -p trill-ui-core -p trill-ui-broker --locked
cargo test --manifest-path ui/Cargo.toml -p trill-session -p trill-app-window --locked
cargo build --manifest-path ui/Cargo.toml --workspace --bins --locked
cargo build --manifest-path ui/Cargo.toml -p trill-ui-broker --example notes_host_probe --locked
python3 tests/ui/test-strict-request-ipc.py /absolute/path/to/built/binaries
```

The socketpair tests explicitly use an application-model fixture; they do not
claim a GUI or production-owner run. The Session test sends forged Notes effect
requests and requires rejection before any host task id is allocated.

Within a task-owned isolated Xvfb or Weston, never the user's active display:

```sh
TRILL_NOTES_PROBE_ISOLATED=1 \
  /absolute/path/to/debug/examples/notes_host_probe \
  /absolute/path/to/debug/trill-app-window
```

This probe creates one disposable Notes process, waits for the first layout,
uses actual Rust `NotesTarget` I/O, checks the mutation ack and changed layout,
then queries the application receipt independently. Cleanup kills and reaps
only its owned child. `TRILL_NOTES_PROBE_CAPTURE_MS` retains the window for at
most ten seconds for an independent screenshot. Its JSON explicitly marks
Final-use, production-owner, compositor-pixel and Asterinas verification false.
It is a destination test without a fabricated grant, signer or ledger.

Test commands and code presence do not assert passes. Record actual tested
commit, environment, commands and results. Remaining acceptance includes
trusted bootstrap, real-authority dispatch through the original owner, durable
history/restart/failure reconciliation, and separately scoped visual/device
tests.

The [2026-10-21 Linux destination evidence](../../tests/ui/evidence/2026-10-21-notes-target/README.md)
records a Rust 1.95.0 workspace run (172 passed, two opt-in host-font tests
ignored), strict IPC rejections, and an owned Xvfb Notes window with exact
mutation receipt, independent query and screenshot. Its source manifest pins
the actual formatted/locked files. It does not claim a production FinalUse or
Asterinas run, and does not cover follow-on bootstrap changes.
