# Notes persistence: development and technical contract

Session-launched Notes now stores real document text, revision and application
receipts in one atomic Linux store. `ui/core/src/notes/persistence.rs` owns the
store; `ui/app-window/src/notes_organ.rs` bridges private channels to the GUI
thread; Session supplies the path and fresh target incarnation. This is
application persistence. The original Hepta issuer, Final-use checks and
durable operation writer remain owned by Hepta.

## Document and process identity

The trusted launcher supplies an absolute directory path. A new document gets
a random stable `document_id`, empty text and revision zero. Reopen loads the
same document and requires a previously unused
`(session_instance, task_id, incarnation)`. The history is bounded to 1024
incarnations; exhaustion refuses further reopen instead of reusing identity.

The v1 Notes effect payload and its destination/scope/predecessor derivation
are unchanged. Document paths are never inserted into that identity or accepted
from a renderer/effect payload. Old effect bytes cannot be rebound to a newly
opened target. A new process can only observe an old target's saved receipt
through private recovery. A normal launch creates a new document; reopen is
currently a trusted startup operation, not a file picker or task adoption UI.

## Atomic storage and lifetime

The store directory is owned by the effective user and mode 0700. Directory
components are opened relative to directory descriptors with `O_NOFOLLOW`;
relative paths and parent traversal are refused. State and lock files must be
owned regular single-link 0600 files. The writer holds an exclusive nonblocking
`flock` on `writer.lock` for its lifetime and checks the lock inode before
committing. Path replacement cannot redirect an already held directory handle.
These checks are not an isolation boundary against a fully privileged process
or an arbitrary process with the same user's filesystem authority.

For an edit or application effect, the GUI-owned store performs:

1. Validate bounded next state and revision, retaining the exact application reply.
2. Create `.state.pending` exclusively and write the complete state.
3. Sync the pending file, rename it to `state.json`, then sync the directory.
4. Publish the new in-memory state and return Applied only after all steps succeed.

Text is at most 4096 UTF-8 bytes and the encoded store is at most 512 KiB.
Only the latest committed file is loaded. An interrupted pre-rename pending
file is validated as a private regular file and discarded, never promoted.
Invalid, oversized or inconsistent state refuses reopening; it is not silently
reset. Any commit failure poisons the writer. It then refuses effects and
recovery results until an explicit reopen resolves the on-disk outcome; it
must not turn uncertain storage into `not_applied`.

Local edits use the same commit sequence and increment the revision only for
changed text. An external replace compares `expected_revision`; a mismatch
does not modify the document. The GUI thread remains the sole document owner.
Storage I/O can delay that GUI thread, so an elapsed transport deadline may
leave an unknown outcome that must be observed, not replayed as a new effect.

## Exact receipts and bounded retirement

One unacknowledged Applied application receipt is retained. Text, revision and
that receipt commit together. Repeating the same operation and exact payload
on its active target returns the original UTF-8 reply bytes. A different
payload for that retained operation is rejected. A new operation while the
receipt is retained receives `receipt_pending`; it cannot evict the receipt.
Local edits may advance the document while preserving that earlier receipt.

The original owner persists its own terminal result before requesting
`acknowledge_terminal` over recovery. The request binds schema version 1,
target, operation ID, payload SHA-256 and receipt SHA-256. The receipt digest
is over the actual original reply bytes, not reserialized or canonical JSON.
After a matching ACK the store atomically releases the receipt and records
one retirement tombstone. Status is `released`, `already_released` or
`unknown`; a wrong binding never releases another receipt. Only the most
recent retirement is remembered. Older evicted retirement acknowledgements
and absent receipt observations return unknown.

This application cache does not replace Hepta's nonce consumption, operation
uniqueness or durable terminal journal. Once a receipt is retired, the original
owner must continue to prevent an operation from being submitted again. Lost
ACKs can be retried idempotently against the retained retirement tombstone.

## Private channels and compatibility

Legacy bootstrap v1 passes one unnamed `SOCK_STREAM` effect endpoint and has
no independent recovery after the stream is closed. Direct legacy app probes
without storage configuration remain explicitly memory-only.

Bootstrap v2 uses the same offer fields with `schema_version: 2` and exactly
two `SCM_RIGHTS` descriptors in this order: unnamed effect `SOCK_STREAM`, then
unnamed recovery `SOCK_DGRAM`. The parent's `attached`/`rejected` ACK must also
use version 2 and carry no descriptors. It is an acknowledgement of attachment,
not proof of a grant, an application edit, pixels or an owner terminal result.
See [NOTES_ORGAN.md](NOTES_ORGAN.md) for the original v1 composition contract.

Effect framing remains a four-byte big-endian length and the original v1 JSON.
After the first byte, the whole prefix plus body has a one-second deadline;
the complete reply has a separate one-second deadline. Recovery is one bounded
JSON request per datagram. Recovery accepts only these operations:

| Request | Result |
| --- | --- |
| `observe`, schema 1, original target, operation ID, payload SHA-256 | Original exact Applied reply if retained; otherwise Unknown bound to the queried identity |
| `acknowledge_terminal`, schema 1, same binding plus receipt SHA-256 | Bound `released`, `already_released` or `unknown` status; no action field in response |
| `read_document_state`, schema 1, active target, 32 lowercase hex `request_id` | `document_state` with the same target/request ID, current revision and text SHA-256; no document text |

The recovery channel cannot submit `replace_note`. The inherited recovery
descriptor is typed, checked and owned once by the child. Both channels hand
off through a queue of at most eight requests; each expires after one second
and the GUI polls at most eight per frame. Expired unexecuted requests are
discarded. A timed-out caller must treat a possibly executed request as unknown.
Notes also schedules a 100 ms repaint fallback so the GUI continues polling
private requests when an idle host does not deliver the requested repaint.
Every effect-worker exit shuts down its socket, including the original stdin
alias, so a timeout or invalid frame cannot leave the owner waiting on an open
but unserved effect endpoint. Recovery remains independent. Once document
commit has begun, a delayed fsync can outlast the reply deadline; EOF or timeout
therefore remains an unknown outcome to reconcile, never permission to replay.

## Development and acceptance

From the repository root:

```sh
cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-ui-core --locked -j 2
cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-session --locked -j 2
python3 tests/ui/test-notes-persistence-ipc.py ui/target/debug /absolute/test-output
```

The last test requires Weston and actual built binaries. It owns a separate
compositor/runtime and uses a transport-only parent fixture, never a substitute
Hepta signer or writer. Its acceptance includes independent hash
readback, repeated effects, lost reply, receipt capacity and ACK, app SIGKILL,
fresh target reopen and observation of the original exact receipt. The original
Hepta chain must pass its own separate integration tests.

The active `.github/workflows/a10-host.yml` runs this probe after its existing
Weston lifecycle check, using the binaries already built by the host gate and
the installed Weston dependencies. It writes `a10/notes-persistence/result.json`
and compositor/Session logs into the existing always-uploaded CI evidence.
The probe starts and cleans up its own compositor; no additional UI build is
performed by this persistence step.

Storage tests exercise actual files and process SIGKILL at file-sync, rename
and directory-sync checkpoints. They also cover fresh incarnation, revision
conflicts, second writer, malformed state, symlink/hardlink and lock replacement.
SIGKILL on a running host does not simulate power loss or prove every storage
device's cache guarantees.

The cross-repository fixtures are
[`notes-bootstrap-v2.json`](../../tests/ui/notes-bootstrap-v2.json) and
[`notes-recovery-v1.json`](../../tests/ui/notes-recovery-v1.json). The first
pins the real offer/ACK bytes and descriptor order; Session's physical
descriptor-transfer test consumes it. The second drives the actual persistent
store through apply, observe, retirement and document-state reads. An equivalent
JSON receipt with different whitespace has a different digest and cannot retire
the original receipt. Invalid identities, request IDs and extra fields are
rejected through the product parsers. Matching Hepta fixtures must remain
byte-identical and be consumed by its original-owner tests.

The initial 2026-10-25 Weston attempt timed out on the first independent recovery
read after the first egui layout. Those failed logs remain evidence of that
earlier checkpoint. After the 100 ms GUI polling fallback, a fresh actual-binary
Weston run passed application apply, exact duplicate, receipt capacity, terminal
ACK, lost reply, independent hash readback, owned-app SIGKILL and reap, new-target
reopen, old-target exact reconciliation, old-effect refusal and idempotent
retirement. Its local implementation receipt is
`work/implementation-logs/ui-notes-native-progress/result.json`; it observed
revision 2 and the same text hash before kill and after reopen.

Later root-disk runs intermittently timed out on the first effect reply.
Failure diagnostics found the effect worker had exited while stdin retained
the socket; read-only recovery returned the exact Applied receipt and revision
1. The worker shutdown fix above closes that stale endpoint. A separate run
using `/data/codex-organ-tmp-01a1729f-20261025` on physical ext4 passed all eleven
steps (`work/implementation-logs/ui-final/notes-persistence-ssd-diagnostic`).
Its fsync trace measured about 1–14 ms per call, while a successful root-disk
comparison measured about 46–413 ms. This shows differing storage latency, not
proof that storage was the sole cause of every earlier timeout. Failure logs
and those environmental limits remain part of the qualification record.
After the shutdown fix, the final actual binaries passed all eleven steps on
the same independent SSD. The receipt at
`work/implementation-logs/ui-final/notes-persistence-final-ssd/result.json`
records both executable hashes, the storage device, fresh target identities,
and equal revision/text hash across app kill and reopen. A successful run does
not promise that every storage commit will finish within the bounded deadline.

The original Hepta writer has also passed its separately scoped test-issuer
integration against actual Session/App, including lost-reply reconciliation,
receipt retirement and App SIGKILL followed by writer clean reopen. Its local
receipts are `work/implementation-logs/hepta-real-notes.json` and
`work/implementation-logs/hepta-real-notes-crash.json`; both retain
`production_authority: false`.

That pass establishes the application/transport fixture lane. It does not
establish the original Hepta production authority chain, power-loss durability,
kernel boot or pixels. The original-owner lane and final committed source pair
need their own receipts. Per-run CI evidence must identify tested source and
binaries separately from this development contract.
