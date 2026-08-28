# TrillionniumOS Desktop

TrillionniumOS Desktop is the full product repository for a Debian-based,
AI-native desktop appliance. The product uses one trusted desktop shell and one
Agent/human-shared Servo content surface in a single visible workspace. System
capabilities remain outside the browser process and are exposed through typed,
short-lived permits.

## Current implementation status

The repository is in **D0R/D0C source implementation** under canonical plan
revision `2026-08-28-d5`.

Implemented in source:

- a Rust 2024 workspace and locked Rust toolchain;
- platform-neutral contract primitives;
- browser contract and error types;
- layered session/document/snapshot/mutation revisions;
- deterministic Agent/human arbitration with bounded queues;
- `hepta-agent-transport`, a connected-stream AF_UNIX carrier with
  `SO_PEERCRED`, per-connection nonce binding, bounded SHA-256 frames, strict
  sequences, and absolute deadlines;
- an exact name/version/checksum allowlist for the Cargo registry closure;
- a non-networked `hepta-browserd` self-check source path;
- JSON contracts and golden vectors for browser requests, receipts, permits,
  signed app manifests, and the Agent carrier;
- product-boundary manifests separating this repository from the Android/mobile
  `trillionnium-os` build graph;
- fail-closed repository validation and CI policy.

Validation ceiling for the current D0C-02 candidate:

- static JSON/TOML/source checks were performed;
- Rust formatting, Clippy, tests, and browserd self-check remain **UNEXECUTED**
  for the exact candidate head because no trusted Rust runner was available;
- the candidate is not merge-ready until those exact-head checks pass.

Not implemented and not claimed:

- a filesystem/abstract Unix socket or product Agent listener;
- Browser API dispatch over the carrier;
- Servo embedding or a visible browser window;
- a bootable Debian image or Wayland session;
- external interactive web effects;
- signed app loading, capability services, Secure Boot, or OTA release.

## Start here

- [`docs/DESKTOP_PLAN.md`](docs/DESKTOP_PLAN.md) — stable canonical-plan index
- [`docs/DESKTOP_PLAN-2026-08-28-d5.md`](docs/DESKTOP_PLAN-2026-08-28-d5.md) —
  active implementation-ready plan
- [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) — exact implemented/non-claimed state
- [`docs/evidence/2026-08-28-d0c02-authenticated-uds.md`](docs/evidence/2026-08-28-d0c02-authenticated-uds.md) — D0C-02 evidence ceiling
- [`docs/adr/`](docs/adr/) — locked architecture decisions
- [`contracts/`](contracts/) — machine-readable product contracts
- [`manifests/`](manifests/) — source, dependency, toolchain, boundary, and status locks

## Required checks

```bash
python3 tools/validate_repository.py
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo run --locked -p hepta-browserd -- --self-check
```

`hepta-browserd --self-check` starts no browser, listener, or network operation.
A check listed here is not evidence until it executes successfully against the
exact commit under review.
