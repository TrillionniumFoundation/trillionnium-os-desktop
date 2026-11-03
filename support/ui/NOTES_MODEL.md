# Original Notes model and compatibility

The canonical interoperability bytes are owned by Hepta memory at
`codex-rs/hepta-memory/tests/fixtures/notes-model-v1.json`. Desktop keeps the
reviewed byte-identical [copy](../../tests/ui/notes-model-v1.json); Agentd keeps
the same copy in its test fixtures. The contract is data for typed conformance
tests, not a second document owner or an authority provider.

| Domain | Current contract | Meaning |
| --- | --- | --- |
| Document target | Session instance / task / application incarnation | The exact original target; destination, scope and predecessor hashes retain their version-one derivation |
| Effect, observation and receipt | Wire schema 1, `trill.notes.replace.v1` | Exact original request bytes and original operation identity |
| Application checkpoint | Format `trill.notes.checkpoint`, schema 2 | Bounded text, revision and required nullable pending/retired receipt fields |
| Descriptor bootstrap | Schema 2 | Initial task 1, effect stream followed by recovery datagram; an attachment ACK grants no effect |
| Root startup reservation | Schema 1 | Exact original target and fresh nonce; activation transfers no descriptors or authority |

These domains have independent versions. Changing the checkpoint does not
change wire bytes, the operation topic, Root policy, the bootstrap deadline or
the original owner's retained operation schema.

## Legacy checkpoint rule

New checkpoints write the named schema-two format. A complete legacy schema-one
checkpoint without a `format` field can still be recovered for the exact same
target. Merely opening it or observing its receipt does not rewrite its bytes,
inode or modification time. The next legitimate state-changing commit, such as
exact original-owner receipt retirement, persists schema two with the same
target, revision, text and original receipt identities.

Unknown formats/versions, mixed version/format pairs, duplicate fields, missing
receipt fields, malformed receipts and different target identities fail closed.
JSON null is required when a receipt is absent; a missing field is not evidence
of absence. Opening a saved note in a fresh window copies text only, with a fresh
target and revision domain. It never imports an old receipt or effect capability.

## Verification

`ui/core/src/notes_checkpoint_tests.rs` parses the common contract through the
real effect, checkpoint, bootstrap and startup types. The migration integration
test in `ui/core/tests/notes_migration.rs` retains an original pending receipt,
proves legacy open/observation are read-only, performs exact retirement and checks
schema-two persistence, idempotent retirement and a fresh receipt-free copy.
The original recovery helper and Hepta owner continue to use wire schema one;
actual companion/owner tests must additionally qualify the final built binaries.

Run the focused model/store suites with Rust 1.96:

```sh
cargo test --manifest-path ui/Cargo.toml --locked -p trill-ui-core --all-targets
cargo clippy --manifest-path ui/Cargo.toml --locked -p trill-ui-core --all-targets -- -D warnings
```

The model tests do not install production Root authority, control a device or
qualify process/power-loss behavior beyond their executed evidence.
