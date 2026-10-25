# trill-ui-core

The private display protocol in `src/desktop.rs` defines the X11 destination
identity, bounded input/capture schemas and cross-repository golden digests.
See [Desktop X11](../../support/ui/DESKTOP_X11.md); it grants no authority.

Shared host UI types and bounded protocols. `src/lib.rs` defines task snapshots
and Session requests; `conversation.rs` defines local drafts and context;
`hepta.rs` and `observation.rs` represent read-only observations. These types do
not issue Hepta authority or define the HOS2 kernel ABI.

`notes.rs` defines exact-byte Notes requests, revisions and application receipts.
The Linux `notes/persistence.rs` stores document state and receipts atomically;
`notes_bootstrap.rs` defines the private v1/v2 descriptor offer. Application
receipts are distinct from the original Hepta owner's durable operation journal.

From the repository root:

```sh
cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-ui-core --locked -j 2
```

Development and technical contracts: [Notes persistence](../../support/ui/NOTES_PERSISTENCE.md),
[Session IPC](../../support/ui/SESSION_IPC.md),
[chat workspace](../../support/ui/CHAT_WORKSPACE.md),
[host build and acceptance](../../support/ui/RUN.md).
