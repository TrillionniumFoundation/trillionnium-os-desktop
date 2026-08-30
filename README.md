# TrillionniumOS Desktop

TrillionniumOS Desktop is the full product repository for a Debian-based,
AI-native desktop appliance. The target product is one compositor/native
trusted workspace plus one human/Agent-shared Servo content surface. System,
network, device, credential, update, and signing authority remain outside the
browser content process.

## Current integrated state

The active canonical plan is `2026-08-29-d6`. The integrated main-stage truth is
`D0R_D0C06_D0A01_COMPILE_VALIDATED`.

The canonical d6 baseline is `bf6bba2ea1c49b36e11754bf27dc0c56e3da3bd1`.
The committed candidate snapshot was observed from GitHub at
`2026-08-30T10:47:03Z` with `origin/main` at
`afd42c0f90d254dfb7b04d9c45216e879840f95e`; live PR state must still be read
from GitHub.

Integrated and demonstrated at host/source evidence levels:

- D0T-01/D0T-02 machine-truth and immutable-CI-input foundations (their prior
  exact-main evidence is pending refresh after invalidating changes);
- Rust 2024 workspace pinned to Rust 1.93.0;
- product-boundary and exact Cargo dependency locks;
- signed Debian snapshot/package input closure;
- strict Browser API contracts, layered session/document/snapshot revisions,
  deterministic Agent/human arbitration, and bounded queues;
- authenticated bounded AF_UNIX connected-stream transport;
- canonical bounded JSON Browser API codec;
- exactly-one request-bound connected AgentPort core;
- default-disabled systemd socket custody and peer attestation;
- product AgentPort fixture separation and fail-closed activation pending a
  promoted, integrated D3 implementation;
- durable, crash-consistent receipt journal with no execution or replay API;
- exact-pin Servo compile compatibility only.

The current D0A-02 candidate is PR #33 on
`codex/d0a02-proof-soundness-v4`, head
`f29e0989335654dfc52ca1dbd049ae1f128d4c59`, with headed-host artifact
`9729987669` (`sha256:bcac5c08dcc4af839b0da3da52d73b0e59e8d80be5767750a243fdaff280e290`).
It proves one native trusted window, one logical local-fixture Servo content
surface, bounded native input/basic IME, popup/navigation refusal, and causal
content-process crash recovery on the tested X11/Xvfb runner. Native clipboard
is intentionally outside this headed-host gate and remains a D4
ownership/lease/drag-drop requirement. Bounded clean Servo teardown and child
reaping are also outside this gate; the candidate claim ceiling retains
`no_native_clipboard` and `no_clean_teardown`. It remains a
`MODULE_CLOSED_CANDIDATE`: independent review, settings evidence, merge, and
an exact-main rerun are still required.

A D3 source foundation is present only in the opt-in development profile: it
contains the engine-neutral BrowserActor/PageOwner boundary, attested principal
binding, receipt observation, and a loopback-fixture runtime. This source
profile is not connected to the production daemon, is not a promoted D3 gate,
and has no integrated-image or exact-main evidence.

Not integrated or claimed:

- headed Servo inside the Debian/QEMU product image;
- Debian/Wayland/QEMU boot on current main;
- integrated-image BrowserActor/PageOwner dispatch or production TaskFlow
  semantic-principal binding (the development-only source profile is not an
  integrated claim);
- external navigation, credentials, capabilities, or external effects;
- signed applications, controlled egress, signed update/rollback, fixed
  hardware, or production release.

The current D1 candidate is PR #32 on
`codex/d1-01-current-main-v2`, head
`ec5e8b2caaac8981d6cdf73dae8b3c4004e6ebd0`; it remains `BASE_DRIFT` until
rebased/reconstructed on the latest main and rerun. PR #29 and PR #23 are
historical, superseded candidates. PR #35 (`codex/d2i-current-main-v1`) is a
source-only D2I composition and remains `BLOCKED_UPSTREAM`.

PR #27 (merged at `e25c42ef69fc2968ac2d1b002cc53f15de2e9e0f`) is retained only
as historical provenance and is superseded by PR #33. D1 must be rebuilt after
product/fixture separation so QEMU qualification traffic cannot substitute a
fixture handler into the production daemon.

## Canonical truth and plan

- [`manifests/project-state.v1.json`](manifests/project-state.v1.json) — single
  committed machine status snapshot
- [`manifests/gates.v1.json`](manifests/gates.v1.json) — gates, evidence tiers,
  required commands, review classes, and invalidation inputs
- [`docs/DESKTOP_PLAN-2026-08-29-d6.md`](docs/DESKTOP_PLAN-2026-08-29-d6.md) —
  active development plan
- [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) — integrated state summary
- [`docs/evidence/2026-08-30-d0a02-headed-runtime.md`](docs/evidence/2026-08-30-d0a02-headed-runtime.md)
  — headed-host candidate evidence

Live PR/check state is read from GitHub. The committed candidate entries are
evidence snapshots and must not be interpreted as a substitute for current
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
