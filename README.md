# TrillionniumOS Desktop

TrillionniumOS Desktop is a Debian-based, AI-native desktop appliance under
active development. The architecture combines one compositor-owned trusted
workspace, one logical untrusted Servo content surface, a shared PageOwner for
human and Agent interaction, explicit system capabilities, durable receipts,
controlled egress, immutable updates, and evidence-gated release promotion.

This repository is a **full product source repository**, but it is **not a
released desktop operating system**. Source, host, headed-host, QEMU image,
integrated-image, hardware, and signed-release evidence are separate tiers.
Passing a lower tier never implies a higher one.

## Canonical truth

- Active plan: [`docs/DESKTOP_PLAN-2026-08-29-d6.md`](docs/DESKTOP_PLAN-2026-08-29-d6.md)
- Plan revision: `2026-08-29-d6`
- Integrated-main stage: `D0R_D0C06_D0A01_COMPILE_VALIDATED`
- Machine truth: [`manifests/project-state.v1.json`](manifests/project-state.v1.json)
- Gate registry: [`manifests/gates.v1.json`](manifests/gates.v1.json)
- Current state: [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md)
- Blocker ledger: [`docs/plan/BLOCKER_CLOSURE_LEDGER-2026-08-29.md`](docs/plan/BLOCKER_CLOSURE_LEDGER-2026-08-29.md)

Machine files describe committed snapshots. Live PR heads, checks, reviews,
branch protection, rulesets, environments, and releases must be read from
GitHub at decision time.

## Current convergence candidate

Draft PR **#60**, branch `codex/d6-gap-closure-v1`, is the single active
convergence surface. Its recorded pre-truth-refresh source snapshot is:

```text
base main:     78888fac3bee7974138ab1c5e4807511bee7fcbb
source head:   e87c63f257c9f660bc0fc104633efb39bcaca320
source tree:   e3fae0714a12b2876a07e8d332d82bb51907b750
synthetic merge: 56f7a021bddbc3f9349c9afd2206670a7765853c
```

That snapshot removed every self-modifying closure bootstrap workflow, restored
a fixed review object, made session transitions transactional, closed retained
human-lease Agent-admission paths, added bounded state-space exploration, and
made authenticated transport fail-stop after wire/protocol failure.

The snapshot passed the repository/Rust/codec/transport/receipt/custody and
D4-D9 source/verifier checks. It also produced candidate-only evidence for:

- exact-pin Servo compile compatibility;
- headed-host Servo local-fixture input and causal content-process recovery;
- two byte-identical D1 builds plus Q35/TCG PID 1, Wayland placeholder,
  default-disabled qualification AgentPort, negative peer cases, recovery, and
  clean shutdown;
- one byte-identical D2I integrated QEMU image with no network device and the
  bounded local-fixture claim ceiling.

The source snapshot and its artifacts are **not integrated-main evidence**.
This truth refresh changes the PR head and therefore requires a fresh exact-head
matrix before independent review and promotion.

## Integrated foundation

Integrated `main` still claims only the D0 foundation and exact-pin Servo
compile baseline represented by `D0R_D0C06_D0A01_COMPILE_VALIDATED`. The source
repository contains substantially more candidate code, including PageOwner,
BrowserActor, trusted-app, capability/egress, update/reconciliation, hardware
qualification, and release-promotion models, but those later gates remain
unpromoted until their prerequisite evidence tiers are met.

The local control path is designed as:

```text
systemd-owned AF_UNIX connection
  -> kernel peer identity and runtime attestation
  -> fail-stop bounded transport
  -> canonical Browser API codec
  -> exactly-one AgentPort request lifecycle
  -> semantic TaskFlow principal binding
  -> PageOwner / BrowserActor
  -> durable requested / dispatched / terminal receipt facts
```

The production AgentPort remains default-disabled and fails closed without a
real promoted BrowserActor binding. Test, qualification, development, and
production binaries are physically separated.

## Open authority and external-evidence blockers

PR #60 cannot close the following through source authorship alone:

- protected `main`, required checks, organization-team CODEOWNERS, latest-push
  non-author approval, no self-merge, and independent release authority;
- a reviewed solution for cross-UID live executable attestation in the D3
  development service without granting broad ptrace authority;
- a Servo-owned atomic semantic resolver and exact integrated-image D3
  principal/dispatch/receipt corpus;
- fixed-BOM independent hardware qualification, including long-duration and
  power-loss testing;
- offline HSM key custody, independent release promotion, signed artifacts,
  anti-rollback metadata, and publication controls.

## Explicit non-claims

The repository does not currently claim that:

- PR #60 has been independently approved or merged;
- its candidate evidence has passed an exact-main rerun;
- a production AgentPort, external navigation, credentials, capabilities, or
  external effects are enabled;
- D3 through D9 are integrated product gates;
- fixed hardware has been qualified;
- production signing keys or a signed release exist.

## Local verification

```bash
python3 tools/validate_repository.py
python3 tools/validate_project_truth.py
cargo fmt --all --check
cargo check --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo run --locked -p hepta-browserd -- --self-check
```

Higher evidence tiers are produced only by the dedicated immutable GitHub
Actions workflows and must be interpreted under their recorded claim ceilings.
