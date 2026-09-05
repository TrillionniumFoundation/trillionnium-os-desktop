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
- Cargo module registry: [`manifests/modules.v1.json`](manifests/modules.v1.json)
- Non-Cargo component registry: [`manifests/components.v1.json`](manifests/components.v1.json)
- Component documentation index: [`docs/components/README.md`](docs/components/README.md)
- Current state: [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md)
- Blocker ledger: [`docs/plan/BLOCKER_CLOSURE_LEDGER-2026-08-29.md`](docs/plan/BLOCKER_CLOSURE_LEDGER-2026-08-29.md)

Machine files describe committed snapshots. Live PR heads, checks, reviews,
branch protection, rulesets, environments, and releases must be read from
GitHub at decision time.

## Current convergence candidate

Draft PR **#66**, branch `codex/d6-gap-closure-v1`, is the single active convergence surface.
The committed pre-truth-refresh snapshot observed at `2026-09-04T17:45:12Z` is:

```text
base main:              addaf73a48bae65f19f6bfe91c6264fd2ddb85a1
source head:            ecb8c2ac0ec0e58277b64a5056a10a8262e8e63e
source tree:            f5e5cc16dcd6c088dcef6ed6c3793bd7808b4aa8
prospective merge:      8d9c1de8b3af62eb32f5cd2bca1a0230afc30115
prospective merge tree: f5e5cc16dcd6c088dcef6ed6c3793bd7808b4aa8
```

At that exact object, all 22 permanent pull-request workflows were terminal
success, all 22 review threads were resolved, and one current-head independent
non-author approval was present. The governance contract requires two such
approvals. This truth-refresh commit changes the source head, so that matrix and
approval are historical inputs and must be reacquired on the new exact head.

Live GitHub readback at the same observation time showed `main` unprotected,
with no required status contexts and no repository rulesets. The fail-closed
D0T-03 control transaction (run `33901170417`) executed zero administration
operations and stopped with `ADMIN_TOKEN_MISSING`; it did not partially modify
repository settings. See
[`docs/evidence/2026-09-05-pr66-live-closure-checkpoint.md`](docs/evidence/2026-09-05-pr66-live-closure-checkpoint.md).

The candidate contains the cumulative source closure for transactional session
arbitration, fail-stop transport, canonical codec, request-bound AgentPort,
durable receipts, D0A/D1/D2I candidate lanes, PageOwner/BrowserActor source,
D4-D9 policy/reference implementations, and machine-validated documentation.
Candidate and verifier success remains bounded by each gate's claim ceiling and
is not integrated-main, installed-product, hardware, or signed-release evidence.

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

## D3 development identity boundary

The cross-UID `/proc/<pid>/exe` source blocker is closed without adding
`CAP_SYS_PTRACE`. The explicit development profile binds the compiled,
root-owned, non-symlink `/usr/libexec/hepta-agent` path and reopens and re-hashes
it at admission and dispatch, while retaining live PID/UID/GID, pidfd liveness,
start time, cgroup, and systemd-unit checks. This mechanism is development-only
and is not production authority.

D3 remains blocked on independent security review, a Servo-owned atomic
semantic resolver, and the complete principal/dispatch/receipt/cancellation/
crash corpus inside the exact integrated image.

## Open authority and external-evidence blockers

PR #66 cannot close the following through source authorship alone:

- protected `main`, required checks, organization-team CODEOWNERS, latest-push
  non-author approval, no self-merge, and independent release authority;
- independent review and exact integrated-image qualification of the D3 static
  trusted-path plus live process-identity binding;
- a Servo-owned atomic semantic resolver and exact integrated-image D3
  principal/dispatch/receipt corpus;
- fixed-BOM independent hardware qualification, including long-duration and
  power-loss testing;
- offline HSM key custody, independent release promotion, signed artifacts,
  anti-rollback metadata, and publication controls.

## Explicit non-claims

The repository does not currently claim that:

- PR #66 has obtained the required two current-head independent approvals or been merged;
- its candidate evidence has passed an exact-main rerun;
- a production AgentPort, external navigation, credentials, capabilities, or
  external effects are enabled;
- D3 through D9 are integrated product gates;
- fixed hardware has been qualified;
- production signing keys or a signed release exist.

The D0A-02 headed-host ceiling explicitly retains:

- `no_native_clipboard`;
- `no_clean_teardown`.

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

Higher evidence tiers are produced only by the dedicated immutable GitHub
Actions workflows and must be interpreted under their recorded claim ceilings.
