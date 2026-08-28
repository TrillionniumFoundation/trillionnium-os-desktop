# TrillionniumOS Desktop

TrillionniumOS Desktop is a full product repository for a Debian-based,
AI-native desktop appliance. The product uses one trusted desktop shell and one
Agent/human-shared Servo content surface in a single visible workspace. System
capabilities remain outside the browser process and are exposed through typed,
short-lived permits.

## Current implementation status

The repository has entered **D0R/D0C foundation implementation** under the
canonical plan revision `2026-08-28-d5`.

Implemented in the current baseline:

- a Rust 2024 workspace and locked Rust toolchain;
- platform-neutral contract primitives;
- browser contract and error types;
- layered session/document/snapshot/mutation revisions;
- a deterministic Agent/human arbitration state machine with bounded queues;
- a non-networked `hepta-browserd` self-check scaffold;
- JSON schemas and golden vectors for browser requests, receipts, capability
  permits, and signed app manifests;
- product-boundary manifests separating this repository from the Android/mobile
  `trillionnium-os` build graph;
- repository validation and CI policy.

Not implemented and not claimed:

- Servo embedding or a visible browser window;
- an authenticated UDS listener;
- a bootable Debian image or Wayland session;
- external interactive web effects;
- signed app loading, capability services, Secure Boot, or OTA release.

## Start here

- [`docs/DESKTOP_PLAN.md`](docs/DESKTOP_PLAN.md) — stable canonical-plan index
- [`docs/DESKTOP_PLAN-2026-08-28-d5.md`](docs/DESKTOP_PLAN-2026-08-28-d5.md) —
  active implementation-ready plan
- [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) — exact implemented/non-claimed state
- [`docs/adr/`](docs/adr/) — locked architecture decisions
- [`contracts/`](contracts/) — machine-readable product contracts
- [`manifests/`](manifests/) — source, toolchain, product-boundary, and status locks

## Local checks

```bash
python3 tools/validate_repository.py
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
cargo run -p hepta-browserd -- --self-check
```

`hepta-browserd --self-check` is a deterministic D0 contract/state-machine
check. It deliberately starts no browser, listener, or network operation.
