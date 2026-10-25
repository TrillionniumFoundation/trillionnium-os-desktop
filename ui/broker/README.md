# trill-ui-broker

`src/lib.rs` implements a bounded default-deny renderer broker: peer sessions,
observations, offline drafts and reconciliation caches. Submit/cancel effect
capabilities remain denied. Its process caches are not a durable Hepta ledger.

The separate Linux `src/notes.rs` is a private destination handle for explicit
original-owner composition. It performs bounded synchronous exact-byte socket
I/O; the renderer broker neither calls it nor exports its handle. The original
Hepta owner must validate authority and journal the operation independently.

`src/desktop.rs` and `src/desktop/x11.rs` provide a separately bootstrapped
Linux display-domain destination with real XTEST input and bounded XGetImage
capture. Its exact live receipts are not a durable ledger or an application
business result. [Desktop X11 contract](../../support/ui/DESKTOP_X11.md).

From the repository root:

```sh
cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-ui-broker --locked -j 2
```

Development and technical contracts: [original Notes composition](../../support/ui/NOTES_ORGAN.md),
[persistent target and recovery](../../support/ui/NOTES_PERSISTENCE.md),
[integration boundaries](../../support/ui/INTEGRATION_CONTRACTS.md),
[host build and acceptance](../../support/ui/RUN.md). Socketpair model tests and
the isolated `notes_host_probe` example are not a production-owner acceptance run.
