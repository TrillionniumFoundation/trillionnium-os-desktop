# First Linux Notes destination

This slice provides real, bounded Linux socketpair I/O to the existing native
Rust Notes application. Its operation is **replace the text of one identified
Notes document, subject to a revision comparison**. The explicitly configured
durable mode synchronizes application data before replying; without
`TRILL_NOTES_STATE_DIR`, the existing temporary mode remains. The
[durability and process-recovery manual](NOTES_DURABILITY.md) specifies storage,
crash handling, helper startup and the actual companion probe. This is a small destination adapter, not a compositor,
global keyboard controller, mobile device port, or an Asterinas desktop.

The standalone Session keeps each new destination private and reports
`original_owner_registered: false`. Public Snapshot / Launch / Cancel IPC has
no Notes edit or handle-export command. Shell displays the target incarnation
and channel observation. Its explicit Notes controls can submit a bounded
Objective to the independently configured original host; Shell receives no
private effect handle and cannot directly dispatch the mutation.
An explicit trusted-parent startup mode can hand off the initial Notes
endpoint through a private inherited descriptor. This requires the original
production host to supply its own recovered writer, FinalUse authority and
grant provider; normal Session launch performs no registration.

## Implementation and ownership

| Path | Responsibility |
| --- | --- |
| `ui/core/src/notes.rs` | Bounded wire types, exact-byte hashes, document revision comparison, one pending receipt retained until exact durable-owner ACK |
| `ui/core/src/notes_recovery.rs` | Strict exact receipt retirement request and idempotent response |
| `ui/core/src/notes_private_unix.rs` | Ordered effect-stream/recovery-datagram descriptor handoff and descriptor validation |
| `ui/broker/src/notes.rs` | Private Linux destination handle, synchronous exact-byte I/O, conservative unknown outcomes |
| `ui/app-window/src/notes_organ.rs` | Inherited stdin receiver, bounded worker handoff and presentation projection |
| `ui/app-window/src/notes_worker.rs` | Serialize local revision-CAS edits, effects, receipt retirement and optional durable storage off Draw |
| `ui/core/src/notes_store.rs` | Durable document/receipt store and exclusive incarnation ownership |
| `ui/app-window/src/main.rs` | Notes presentation, user-edit requests and layout-only witness |
| `ui/session/src/main.rs` | Existing child-process owner creates and retains private handles |
| `ui/core/src/notes_bootstrap.rs` | Strict one-time descriptor handoff request and acknowledgement schema |
| `ui/session/src/notes_bootstrap.rs` | Linux inherited datagram sender, SCM_RIGHTS and bounded acknowledgement |
| `ui/shell/src/main.rs` | Bounded Session worker handoff and source-owned observation projection; no private effect handle |
| `ui/shell/src/objective_panel.rs` | Shared Notes Write/Refresh/Cancel actions, original intent navigation, freshness and passive status recovery |
| `ui/shell/src/native_makepad.rs` | Original Makepad Notes port and current-room/editor fences, forwarding to the same shared actions |
| `ui/shell/src/objective_notes_tests.rs`, `native_notes_tests.rs` | Shared recovery/readback regressions and original native callback fences |
| `ui/broker/tests/notes_target.rs` | Real socketpair tests against an explicit application-model fixture |
| `ui/broker/examples/notes_host_probe.rs` | Isolated real-window target probe, separate from a production-owner run |
| `tests/ui/notes-target-v1.json` | Cross-language request, response, payload hash, scope hash and predecessor hash |
| `tests/ui/notes-bootstrap-v2.json` | Exact bootstrap offer and attached/rejected ACK fixtures shared with the owner |
| `tests/ui/notes-recovery-v1.json` | Exact observation, durable receipt ACK and idempotent retirement fixtures shared with the owner |
| `tests/ui/test-notes-bootstrap-ipc.py` | Actual Session/App descriptor handoff with a transport-only parent fixture and read-only query |

The original default-deny broker is reused from PR #210 head
`24dc73185d739695ef755c6bbd9d22ee38acf9be`. Its sessions, admission bounds,
generation checks and denied effect capabilities remain the same. The private
destination module does not give those sessions an effect capability. No new
authority, signer, operation allocator, durable effect ledger or model callback
is introduced in UI code.

## Shared Rust UI and original Notes owner

The egui and original Makepad controls borrow the same retained conversation
draft and `ObjectivePanel`. Write sends literal text through the bounded
Session Objective bridge to the fixed trusted original host. The original
Agentd compiler, durable writer and FinalUse dispatcher then own any operation
and private destination entry. The renderer supplies no issuer, signer, effect
ledger or replacement operation history. The exact paired original source and
native `NativeNotesView` / three callback API are specified by
[DEPENDENCIES.md](DEPENDENCIES.md) and its canonical source contract.

Write preserves text and quoted references. It refuses quoted context rather
than silently dropping it, enforces the 4096-byte Notes bound and checks editor
composition, fresh current-Session readiness, complete retained-ID traversal,
absence of host issues and absence of unfinished original requests. A fresh
document snapshot with `receipt_pending` also requires reconciliation before
another intent can be created. Makepad additionally checks current room and
source epoch, an open window and the visible Conversations page; both the
original renderer and Desktop callback fence actions, and Desktop rechecks
readiness when handling them.

Refresh sends only original availability/status queries. Cancel requests
cancellation once for the current original intent; an unknown cancel is
observed under that identity, never repeated automatically. Rejected queueing
is visible and does not create an accepted local intent. Neither action clears
the draft. Passive status rotation fairly revisits all retained unresolved IDs,
interleaving the current request and separate availability reads within the
128-ID navigation bound. It advances only after the bounded read queue accepts
a query, retains its selection on a full queue and never consumes action
capacity, submits an effect or generates another ID.

This passive query rotation is a UI selection guarantee, not a bound on every
Session response. Session forwards Objective commands through one bounded FIFO
transport worker so a stalled 150 ms exchange does not occupy its lifecycle
loop. Queue wait consumes the accepted peer's original 500 ms allowance; excess
requests receive typed backpressure. The
[isolated read-only queue-delay regression](SESSION_IPC.md#historical-synchronous-delay-and-retained-regression)
retains the previous synchronous failure and checks the changed transport
without an original owner, Notes bootstrap or effect.
The actual original-host/UI combination still needs concurrent-read latency
evidence before its production responsiveness can be accepted. A lost reply
does not establish a failed operation; the existing original-ID observation
and no-automatic-replay rules continue to apply.

The current-document readback is a separate projection containing target
identity, its own observation time, revision, short text digest and pending
receipt status. It does not import document text into the composer. Its own
source and transport freshness must hold before it is shown as current; a run
marked Succeeded is not an exact saved-operation receipt. Terminal publication
and retirement still require the original writer's exact evidence below.
Session migration preserves original intent/run history for passive recovery
but clears the prior document snapshot. A recent old target cannot inherit the
new Session's provenance from its timestamp. Missing or stale readback remains
unavailable until the original source observes it again.

## Required original-owner composition

The production host must explicitly attach the destination to the existing
Hepta `FinalUseProductionOutboxTarget` / production durable writer. Before
target entry, the original owner verifies signed Final-use, consumes its nonce
and maintains its own operation history and generation fences. The private
target handle is a host composition input, never a renderer-deserialized value.

```rust,ignore
NotesTarget::from_private_channels(effect_stream, recovery_datagram, target_identity)?;
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
target. The inherited bootstrap below supplies the same private endpoint to
the original owner through explicit composition. A publicly reachable UDS with
only a UID check would not provide Final-use authority. The default remains
deny until the original owner attaches and authorizes a particular operation.

## Controlled inherited bootstrap

The original production host creates `UnixDatagram::pair()`, keeps one end and
passes the other as stdin when starting `trill-session --notes-bootstrap-stdin`.
It must supply a recovered live-verified writer, the retained FinalUse authority
and its existing grant provider to the original Agentd attachment API. Missing
configuration has no generated issuer or fallback provider. The initial target
attachment does not issue or consume a grant.

Before serving any public IPC request, that explicit Session mode launches one
Build Notes child with task id 1 and a fresh Session/child incarnation. It
consumes its never-contacted `NotesTarget` and sends a **single atomic datagram**
with exactly two ordered `SCM_RIGHTS` descriptors: the private Notes effect
`UnixStream`, then its separate recovery `UnixDatagram`. Bootstrap version 2
rejects version 1 and wrong descriptor counts or types; it never falls back to
observing on an ambiguous effect stream. The ordinary effect framing remains unchanged.
Bootstrap JSON is at most 1024 bytes, without a length prefix:

```json
{
  "schema_version": 2,
  "action": "offer_notes_target",
  "target": {
    "session_instance": "11111111111111111111111111111111",
    "task_id": 1,
    "incarnation": "22222222222222222222222222222222"
  },
  "destination_id": "trill.notes:11111111111111111111111111111111:1:22222222222222222222222222222222"
}
```

The reply has the same `schema_version`, `target` and `destination_id`, action
`notes_target_registration`, and status `attached` or `rejected`. It is one
datagram of at most 1024 bytes with **no descriptors**. Unknown/duplicate fields,
different identity, invalid status, truncation and ancillary ACK data are
rejected. Received unwanted descriptors are closed. Linux checks `AF_UNIX`,
socket type and unnamed connected peers; received descriptors use
`MSG_CMSG_CLOEXEC`. Socket shape is not an authority credential.

The parent must send `attached` only after original-owner validation and fixed
destination composition succeed. The one-shot bootstrap closes afterward.
Session records `original_owner_registered: true` only as this historical
private-parent acknowledgement. This does not assert live authority, a signed
grant, app readiness, a document mutation, pixels or a durable terminal outcome.
Each later effect still passes the original production dispatcher and exact
FinalUse checks. Public Launch creates additional private, unregistered Notes
windows; it cannot replace or export the initial target.

A total two-second handoff deadline applies. Failure disables all duplicate
references to the offered effect endpoint, kills and reaps only the initial
Session-owned Notes process, and fails startup before serving public requests.
A missing ACK remains ambiguous about whether the parent attached; channel
shutdown cannot undo an effect that may already have happened. No offer is
automatically retried. The original host owns operation uncertainty.

The local bootstrap transport fixture can acknowledge attachment for its own
qualification run, but it is explicitly labelled as a fixture and only queries
the actual app read-only. That test is not a production authority run.

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
compares the same identity and revision on the application worker when applying. Local
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
retained operation is refused. If another operation targets the current revision
while this receipt remains pending, it receives `not_applied: receipt_pending`;
the existing receipt is never overwritten to make room. Local edits retain the
pending receipt. The durable mode stores it with the document and last retirement
identity; temporary mode retains it in memory. Neither supplies a second Hepta
history or makes an unknown operation retryable.

## Failure and observation semantics

One private channel is serialized. Concurrent callers fail before writing,
instead of entering an unbounded queue. A total two-second deadline bounds
incremental request writes and response reads. Malformed or misbound requests
write zero destination bytes.

After bytes may have been sent, transport loss, timeout or an unrelated reply
is `Indeterminate`. Transport/framing/correlation failure poisons and shuts
down the channel, preventing silent replay. A lost ack can follow a real
mutation. Timeout and cancellation do not roll it back. The separate recovery datagram remains available if the same application is
still alive. It accepts `observe` and `acknowledge_terminal` only. The UI
receiver rejects `replace_note` on this lane; rejection is enforced before
calling the document mutation method. Every query/reply matches the exact
incarnation, operation id and original raw payload SHA-256. Stale datagrams
are discarded within a total deadline; no effect is replayed.

The app has a bounded four-slot application-worker handoff shared by both lanes
and local edits. Expired
handoffs are discarded before document mutation; a timed-out recovery request
cannot create an unbounded queue. The worker serializes external and local edits.
In durable mode it synchronizes the changed state before an applied reply;
storage failure freezes further writes with an unknown result. The original
production owner still owns durable outcome publication.


### Durable original-owner receipt retirement

The application retains one pending applied receipt. Only the original writer
may acknowledge it after appending its complete terminal evidence to the existing
`cognitive_local_events` chain. Normal dispatch, inherited dispatch settlement
and recovered observation all use the same typed Notes evidence. A failed SQLite
commit leaves the operation indeterminate and emits no retirement ACK.

The writer rebuilds a private, non-serializable `NotesRetirementPermit` from its
verified immutable operation/outbox binding and committed event. It checks the
original live verifier after its SQLite awaits, then sends a metadata-only
`acknowledge_terminal` datagram containing `schema_version: 1`, the exact target,
operation id, original `payload_sha256`, and `receipt_sha256` of the full persisted
application response. No new signer, operation ledger or writer is introduced.

A matching ACK clears the pending receipt and returns `released`. The app retains
one last retirement identity so a lost ACK can return `already_released` on an
exact repeat. Wrong target, operation, payload or receipt hash cannot release
capacity. A late ACK for the prior receipt cannot erase the next pending receipt.
The source remains committed even if retirement fails; its reconciliation pass
retries the latest exact retirement for that incarnation without dispatching text.

The live channel covers a retained application and an original writer reopened
against its authenticated source store. After the old application is reaped,
the explicit [durable recovery helper](NOTES_DURABILITY.md#recovery-process-contract)
can observe and retire the exact old stored receipt through a new private pair.
It does not reconstruct an effect descriptor or make a new incarnation answer
the old operation. Temporary-mode receipts cannot survive application exit.
Production authority and the seven original trust inputs remain external requirements.

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
cargo +1.96.0 test --manifest-path ui/Cargo.toml -p trill-shell --locked objective_panel
cargo +1.96.0 test --manifest-path ui/Cargo.toml -p trill-shell --locked coalesced_poll_does_not_fill_action_queue_or_freeze_gui
cargo +1.96.0 test --manifest-path ui/Cargo.toml -p trill-shell --locked --features hepta-native-makepad native_makepad::notes_tests
cargo +1.96.0 clippy --manifest-path ui/Cargo.toml -p trill-shell --all-targets --locked --features hepta-native-makepad -- -D warnings
cargo +1.96.0 build --manifest-path ui/Cargo.toml -p trill-shell --locked --features hepta-native-makepad
```

The shared controls tests cover same-ID recovery, full-queue fairness, host
issues, pending receipts, readback freshness and Session snapshot invalidation.
The native tests exercise the original port's source/editor fences and the
same bridge without clearing the draft. The actual receiver/helper process
crash tests, input/save-close cases and original-owner acceptance are mapped in
[NOTES_DURABILITY.md](NOTES_DURABILITY.md). Test presence is not a final
source-paired pass; record the selected source, environment and results.

The socketpair tests explicitly use an application-model fixture; they do not
claim a GUI or production-owner run. The Session test sends forged Notes effect
requests and requires rejection before any host task id is allocated.
The existing `tests/ui/headless-weston.sh` CI path also runs the actual Notes
destination probe and private Session bootstrap fixture under its own
compositor, retaining separate JSON/logs. It does not use a live user display.

Within a task-owned isolated Xvfb or Weston, never the user's active display:

```sh
TRILL_NOTES_PROBE_ISOLATED=1 \
  /absolute/path/to/debug/examples/notes_host_probe \
  /absolute/path/to/debug/trill-app-window

TRILL_NOTES_PROBE_ISOLATED=1 \
  python3 tests/ui/test-notes-bootstrap-ipc.py /absolute/path/to/debug
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
production-configured bootstrap and real-authority dispatch through the original owner,
whole-process endpoint recovery (not supplied by this two-lane protocol), and
separately scoped visual/device tests. Current patch test results must be recorded
separately from the historical runs below.

The [2026-10-21 Linux destination evidence](../../tests/ui/evidence/2026-10-21-notes-target/README.md)
records a Rust 1.95.0 workspace run (172 passed, two opt-in host-font tests
ignored), strict IPC rejections, and an owned Xvfb Notes window with exact
mutation receipt, independent query and screenshot. Its source manifest pins
the actual formatted/locked files. It does not claim a production FinalUse or
Asterinas run, and does not cover follow-on bootstrap changes.
