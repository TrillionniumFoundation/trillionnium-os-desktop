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

- D0T-01/D0T-02 machine truth and immutable CI inputs;
- Rust 2024 workspace pinned to Rust 1.93.0;
- product-boundary and exact Cargo dependency locks;
- signed Debian snapshot/package input closure;
- strict Browser API contracts, layered session/document/snapshot revisions,
  deterministic Agent/human arbitration, and bounded queues;
- authenticated bounded AF_UNIX connected-stream transport;
- canonical bounded JSON Browser API codec;
- exactly-one request-bound connected AgentPort core;
- default-disabled systemd socket custody and peer attestation;
- product AgentPort fixture separation and fail-closed activation until D3;
- durable, crash-consistent receipt journal with no execution or replay API;
- exact-pin Servo compile compatibility only.

D0A-02 headed-host automation has produced passing exact-head runs, but the
independent review still requires stronger causal process-death evidence,
generation-bound callback isolation, measured WebView/process cardinality, and
clipboard evidence. D0A-02 is therefore not integrated truth and cannot unlock
D2I or D3.

Not integrated or claimed:

- a review-accepted product-owned headed Servo runtime;
- headed Servo inside the Debian/QEMU product image;
- Debian/Wayland/QEMU boot on current main;
- BrowserActor/PageOwner dispatch or TaskFlow semantic-principal binding;
- external navigation, credentials, capabilities, or external effects;
- signed applications, controlled egress, signed update/rollback, fixed
  hardware, or production release.

The active D1 reconstruction is PR #32 on branch
`codex/d1-01-current-main-v2`. PRs #23 and #29 are historical and superseded.
D1 must pass on its exact PR head and again on the reviewed merged `main` tree
before it can be promoted.

## Canonical truth and plan

- [`manifests/project-state.v1.json`](manifests/project-state.v1.json) — single
  committed machine status snapshot
- [`manifests/gates.v1.json`](manifests/gates.v1.json) — gates, evidence tiers,
  required commands, review classes, and invalidation inputs
- [`docs/DESKTOP_PLAN-2026-08-29-d6.md`](docs/DESKTOP_PLAN-2026-08-29-d6.md) —
  active development plan
- [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) — integrated state summary

Live PR/check state is read from GitHub. Committed candidate entries are
evidence snapshots and must not be interpreted as substitutes for current
GitHub status.

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
