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

Draft PR **#73**, branch `codex/d6-sensitive-log-redaction-v1`, is the sole active direct-to-`main`
convergence surface. PR **#66** is closed and unmerged; its source, CI and review
records are historical provenance only and do not transfer.

The exact clean object immediately before this truth refresh was:

```text
base main:          addaf73a48bae65f19f6bfe91c6264fd2ddb85a1
pre-refresh head:   ddaf10d6e0172f9c17c04752d0b6d27ebf89a14b
pre-refresh tree:   3a7d7025011c5393f9eac04f2522817a8e89090e
prospective merge:  afcab92e6a06ff58afde83a96b56893b0e334d3e
observed at:        2026-09-07T05:07:35Z
```

This truth-refresh commit necessarily creates a new head, tree and prospective
merge object. It therefore invalidates every pre-refresh exact-head check and
review packet. The final object must complete all permanent workflows, CodeQL,
independent review, governed merge and exact-main reruns without inheriting an
earlier result.

## Integrated foundation

Integrated `main` still claims only the D0 foundation and exact-pin Servo
compile baseline represented by `D0R_D0C06_D0A01_COMPILE_VALIDATED`. The
candidate contains substantially more source, but it is not integrated product,
hardware, signing, promotion, or release evidence.

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
promoted BrowserActor binding. Test, qualification, development, and production
binaries remain physically separated.

## Candidate source closure

The cumulative candidate includes transactional PageOwner arbitration,
authenticated fail-stop transport, strict canonical codec, AgentPort custody,
durable non-replaying receipt facts, bounded D0A/D1/D2I qualification lanes,
D3 principal/dispatch source, D4-D9 policy and verifier surfaces, and hostile
identity-redaction regressions. Each result remains bounded by its declared
evidence tier and invalidation inputs.

## Remaining hard gates

PR #73 cannot close the following through source authorship alone:

- live protected `main`, strict required checks, organization-team CODEOWNERS,
  current-push independent approvals, no-bypass rules and protected release
  environments;
- a reviewed Servo-owned retained-node semantic action path and the complete
  exact integrated-image D3 runtime corpus;
- installed D4-D7 native/OS adapters and their image, network, fault, update and
  recovery qualification environments;
- fixed-BOM independently signed 24/72-hour hardware and raw power-loss corpus;
- offline/HSM dual-control key custody, separated signer/attestor/promoter roles,
  anti-rollback state and protected publication.

## Explicit non-claims

The repository does not claim that PR #73 has final exact-head evidence,
obtained the required independent approvals, passed governed merge or exact-main
reruns, qualified fixed hardware, established production signing custody, or
published a signed release. Production activation, external effects, hardware,
signing, promotion and release authority remain closed.

The D0A-02 headed-host ceiling still retains `no_native_clipboard` and
`no_clean_teardown`.

## Local verification

```bash
python3 tools/validate_repository.py
python3 tools/validate_project_truth.py
python3 tools/validate_module_documentation.py
python3 tools/validate_component_documentation.py
cargo fmt --all --check
cargo check --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo run --locked -p hepta-browserd -- --self-check
```
