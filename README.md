# TrillionniumOS Desktop

TrillionniumOS Desktop is the full product repository for a Debian-based,
AI-native desktop appliance. The target product is one compositor/native
trusted workspace plus one human/Agent-shared Servo content surface. System,
network, device, credential, update, and signing authority remain outside the
browser content process.

## Current integrated state

The active canonical plan is `2026-08-29-d6`. The integrated main-stage truth is
`D0R_D0C06_D0A01_COMPILE_VALIDATED`.

Integrated and demonstrated at host/source evidence levels:

- Rust 2024 workspace pinned to Rust 1.93.0;
- product-boundary and exact Cargo dependency locks;
- signed Debian snapshot/package input closure;
- strict Browser API contracts, layered session/document/snapshot revisions,
  deterministic Agent/human arbitration, and bounded queues;
- authenticated bounded AF_UNIX connected-stream transport;
- canonical bounded JSON Browser API codec;
- exactly-one request-bound connected AgentPort bridge;
- default-disabled systemd socket custody and peer attestation;
- durable, crash-consistent receipt journal with no execution or replay API;
- exact-pin Servo compile compatibility only.

Not integrated or claimed:

- product-owned headed Servo runtime or visible first frame;
- Debian/Wayland/QEMU boot;
- QEMU PID 1 AgentPort activation;
- BrowserActor/PageOwner dispatch or TaskFlow semantic-principal binding;
- external navigation, credentials, capabilities, or external effects;
- signed applications, controlled egress, signed update/rollback, fixed
  hardware, or production release.

D1 PR #23 is a base-drifted candidate. D0A-02/D2 PR #27 is a candidate whose
headed qualification must pass on its exact head and again on integrated main.
Neither PR is part of the integrated product truth.

## Canonical truth and plan

- [`manifests/project-state.v1.json`](manifests/project-state.v1.json) — single
  machine status
- [`manifests/gates.v1.json`](manifests/gates.v1.json) — gates, evidence tiers,
  review classes, and invalidation inputs
- [`docs/DESKTOP_PLAN-2026-08-29-d6.md`](docs/DESKTOP_PLAN-2026-08-29-d6.md) —
  active development plan
- [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) — integrated state summary
- [`docs/plan/BLOCKER_CLOSURE_LEDGER-2026-08-29.md`](docs/plan/BLOCKER_CLOSURE_LEDGER-2026-08-29.md)
  — candidate blocker snapshot

## Required checks

```bash
python3 tools/validate_repository.py
python3 tools/validate_project_truth.py
cargo fmt --all --check
cargo check --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo run --locked -p hepta-browserd -- --self-check
```

`hepta-browserd --self-check` starts no Servo runtime, product listener, or
external network operation. Evidence is valid only for the exact tested commit,
tree, workflow, inputs, environment, and output digests.
