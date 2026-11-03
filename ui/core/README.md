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
  Notes identity, bounded messages and trusted bootstrap v2 data.
- [calculator.rs](src/calculator.rs) and [desktop_startup.rs](src/desktop_startup.rs):
  the separate candidate Calculator identity, checked integer state/receipt model
  and versioned joint reservation. [Calculator protocol](CALCULATOR_PROTOCOL.md)
  defines exact bytes, one pending receipt, recovery, lifecycle and acceptance scope.
- [notes_recovery.rs](src/notes_recovery.rs) and
  [notes_private_unix.rs](src/notes_private_unix.rs): separately inherited
  recovery datagrams, exact acknowledgement and private descriptor checks.
- [notes_checkpoint.rs](src/notes_checkpoint.rs) and [notes_store.rs](src/notes_store.rs):
  application-owned durable document/receipt validation, incarnation locking
  and synchronized storage; see [Notes durability](../../support/ui/NOTES_DURABILITY.md).
  The saved-document catalogue offers bounded text selections; explicit restore
  creates a local edit in a new target and does not rebind the original receipts.

## Invariants to preserve

Public host IPC includes Snapshot/Launch/Cancel and the separately configured
[typed Objective bridge](../session/OBJECTIVE_BRIDGE.md). A workspace label or
same-UID peer is not an A05 capability. Cancellation requests do not prove the
task has stopped; a stale observation cannot become a new successful observation.
Keep operation outcome publication with the original Hepta owner.

Wire changes affect all workspace consumers. Check old/new Session/Shell
behavior, frame bounds, identity and unknown outcomes rather than changing
only the renderer. Notes' temporary in-memory mode and explicit durable store
have separate persistence boundaries; an application reply alone does not
establish the original Hepta writer's durable terminal state.

## Development

```sh
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-ui-core --locked
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-ui-core --locked \
  emit_cross_repository_wire_fixture_from_app_serialization -- --nocapture
```

See [workspace setup](../README.md), [integration contracts](../../support/ui/INTEGRATION_CONTRACTS.md),
[Chat contract](../../support/ui/CHAT_WORKSPACE.md) and
[Notes contract](../../support/ui/NOTES_ORGAN.md). These documents specify
the wire, authority and persistence boundaries; package tests do not replace
the complete host/owned-compositor checks.

The emitted Calculator golden fixture comes from this shared Rust serializer and
model. Its explicit `MODEL_SERIALIZATION_ONLY` scope excludes original Core,
FinalUse, native window and production effect qualification. Existing Notes wire
and receipt history are not migrated into the Calculator namespace.
