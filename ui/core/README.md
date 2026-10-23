# trill-ui-core

Shared data and transport contracts for the host UI processes. This crate does
not issue grants, sign requests, own a durable effect journal, or implement HOS2.

## Code map

- [lib.rs](src/lib.rs): workspaces/apps, ephemeral task records, bounded host
  Request/Response frames and Unix request helpers.
- [host_peer.rs](src/host_peer.rs): kernel-reported peer credentials shared by
  Session and clients.
- [conversation.rs](src/conversation.rs): typed draft/context references.
- [observation.rs](src/observation.rs) and [hepta.rs](src/hepta.rs): observation
  identity, freshness and unavailable/unknown state.
- [notes.rs](src/notes.rs) and [notes_bootstrap.rs](src/notes_bootstrap.rs): private
  Notes identity, bounded messages and trusted bootstrap data.

## Invariants to preserve

Public host IPC is Snapshot/Launch/Cancel. A workspace label or same-UID peer
is not an A05 capability. Cancellation requests do not prove the task has
stopped; a stale observation cannot become a new successful observation.
Keep operation outcome publication with the original Hepta owner.

Wire changes affect all workspace consumers. Check old/new Session/Shell
behavior, frame bounds, identity and unknown outcomes rather than changing
only the renderer. Notes replies describe an in-memory document mutation,
not user-file persistence.

## Development

```sh
RUSTUP_TOOLCHAIN=1.88.0 cargo test --manifest-path ui/Cargo.toml -p trill-ui-core --locked
```

See [workspace setup](../README.md), [integration contracts](../../support/ui/INTEGRATION_CONTRACTS.md),
[Chat contract](../../support/ui/CHAT_WORKSPACE.md) and
[Notes contract](../../support/ui/NOTES_ORGAN.md). These documents specify
the wire, authority and persistence boundaries; package tests do not replace
the complete host/owned-compositor checks.
