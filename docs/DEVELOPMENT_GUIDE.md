# Development guide and implementation coverage

**Plan revision:** `2026-08-29-d6`  
**Scope:** source maintenance and acceptance navigation; not a qualification record

Read the [active plan](DESKTOP_PLAN-2026-08-29-d6.md),
[non-claims](NON_CLAIMS.md) and [closure plan](plan/IMPLEMENTATION_CLOSURE_PLAN.md)
first. `CURRENT_STATE.md` records the earlier integrated qualification baseline.
`source-state.v1.json`, `Cargo.toml` and the [module index](modules/README.md)
describe the current source workspace, including later merged BrowserActor code.
A merged implementation and a fresh qualified product are different observations.

## Technical documentation that exists

Every Cargo member has a technical README and a module registry entry. The
contracts include API entry points, call/dependency direction, configuration,
state/concurrency, security invariants, failure behavior, tests and operations.
The architecture documents describe the transport, actor/event loop, receipts,
Linux adapters, image, update and release boundaries. `contracts/` contains
versioned machine contracts and schemas; `docs/adr/` records authority decisions.

The documentation gate checks structural coverage, exact Cargo binary/feature
inventory, references and claim projection. The coherence gate checks generated
index bytes, plan precedence and concrete storage permissions. These gates do
not check every public method's arguments and errors, execute every example or
prove all application requirements. API signatures and method documentation in
Rust/Python source remain part of the development contract. During each change,
update the affected signatures, schemas/vectors, runnable examples and hostile
tests together; do not substitute a minimum README size for those checks.

## Source, integration and acceptance map

The table maps product requirements to actual source and the next acceptance
boundary. It records no percentage, success observation or independent approval.

| Plan requirement | Source entry point and technical contract | Present source behavior | Missing product acceptance |
| --- | --- | --- | --- |
| D0 contracts and wire admission | `trillionnium-contract-core`, `hepta-browser-contracts`, `hepta-browser-codec`; module READMEs and Browser API schemas | Bounded IDs/revisions, typed browser operations, canonical encoding and parsing | Exhaustive domain/wire conversion parity and versioned executable API examples |
| D0 local custody and request lifecycle | `hepta-agent-transport`, `hepta-peer-attestation`, `hepta-agent-port`; connected bridge and request-peer contracts | Bounded authenticated connected streams, live peer custody, one request per connection | Production principal policy, global resource/backpressure limits and installed dispatch |
| D3 BrowserActor and Servo | `hepta-browser-actor`, separate simulation crate, `experiments/servo-s08-runtime`; S08 architecture | Concrete callback bridge, creator-thread owner, retained-node qualification path, receipt observation | Installed daemon IPC from attested AgentPort to real Servo and durable response; qualification mailbox cannot substitute |
| D3 runtime crash/recovery | `apps/hepta-browserd/src/servo_product_runtime.rs`; S08 product supervision | Checked generations, explicit reconstruction, bounded crash loop, no automatic replay | Wire the supervisor into product startup, process custody, trusted recovery UI and durable reconciliation |
| D3 receipts | `hepta-session-core`; journal, managed store and fault-model contracts | Durable chained lifecycle facts, recovery, bounded records, rotation and redacted export | Installed crash/disk-full matrix, archival/quota policy and independently protected rollback anchor |
| D4 collaboration and input | Session machine and `hepta-workspace-composition`; session/composition architecture | Human/Agent arbitration and deterministic trusted/untrusted surface model | Real compositor focus/input/clipboard/scaling and Chinese IME; trusted approval and handoff UX |
| D1/D2I and S10 image | `packaging/debian/image/`, `tools/run_d1_final_qualification.sh`, `tools/run_d2i_integrated_image.sh`; D1/D2I architecture | Locked image builders, qualification overlays, guest runners and offline evidence checks | Current immutable image builds and guest runs, review and exact-main regression; production binary still disabled |
| S09 Linux mechanisms | `platform/linux/adapters.py` and its README | Descriptor-confined files, clock/entropy/procfs, retained Wayland endpoint, pure HTTPS/address policy | Native rendering/input, actual resolver/TLS/socket enforcement and installed mechanism coverage |
| D5 trusted apps | `docs/adr/0004-trusted-app-origin-model.md`, product architecture | Synthetic HTTPS origin/storage design | Signed bundle runtime, trust-root rotation/revocation, CSP/CORS, partitioned storage, upgrade/migration/uninstall |
| D6 capabilities, TaskFlow and egress | Threat/control matrices, capability/egress plan; `services/README.md`, `workers/README.md` | Requirements and some low-level policy helpers; service directories remain design placeholders | Trusted consent/typed permits, task budgets/cancellation, complete egress enforcement and bypass corpus |
| D7 / S11 update and recovery | `platform/update_recovery.py`; S11 architecture and contract | Host A/B state coordination, image/source binding, boot/health transitions and reconciliation | External signature verifier/trust root before staging, installed boot/rollback/recovery fault matrix and recovery tooling |
| D8/D9 / S12 release | Release architecture, `tools/verify_s12_release_qualification.py` | Offline packet/signature/role/subject consistency verifier | Independent builders, fixed hardware, actual endurance/power cuts, key custody, protected signing/promotion/publication |
| D0T governance | `docs/governance/BRANCH_PROTECTION_REQUIRED.md`, gate registry and workflows | Source policy and workflow definitions | Live enforced branch/ruleset/environment settings, actual independent identities/review; source files cannot supply them |

Source and specification coverage is substantial for the security foundations.
An operational installed desktop remains incomplete: executable `hepta-browserd`
still starts its scaffold/self-check, and the product AgentPort rejects activation
without a promoted handler. The complete request/recovery acceptance path is
defined in [REQUEST_EXECUTION_AND_RECOVERY.md](architecture/REQUEST_EXECUTION_AND_RECOVERY.md)
and remains a product integration gate.

## Reproducible local verification

Use Python 3.11 or newer (`tomllib` is required) and the exact Rust 1.93.0
toolchain in `rust-toolchain.toml`, including rustfmt and Clippy. Cargo commands
use the committed lockfile; do not regenerate dependencies to hide a failure.
Run the aggregate source checks:

```sh
make check
```

`tools/validate_d0c04_rust_product.py` preserves the historical seven-package
D0C-04 snapshot criteria. It intentionally rejects the current twelve-package
workspace and is not an active source gate; use the contract-foundation and
project-truth checks in `make check` for current source. Do not widen historical
qualification criteria to manufacture a current success record.

Run all Python discovery roots when auditing the full repository. Discovery in
`tests/` alone does not include every D1 and transport corpus:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s tests/d1 -p 'test_*.py' -v
python3 -m unittest discover -s tests/transport -p 'test_*.py' -v
```

The daemon's supported commands provide build identity and bounded self-checks:

```sh
cargo run --locked -p hepta-browserd -- --print-build-info
cargo run --locked -p hepta-browserd -- --self-check
cargo run --locked -p hepta-agent-portd --bin hepta-agent-portd -- --self-check
```

D1's separate inherited-stream fixture uses the actual Cargo example target:

```sh
cargo build --release --locked -p hepta-agent-portd --no-default-features --features fixture --example hepta-agent-d1-fixture
target/release/examples/hepta-agent-d1-fixture --mode self-check
```

This fixture is qualification infrastructure. It is absent from the product
install map and is not a BrowserActor or browser-readiness result. Image and
Servo workflows have additional controlled dependencies and environments;
consult their scripts and architecture contracts before executing them.
The permanent D1 and D2I workflows cover actual prospective merges and main
pushes. S10's manual workflow retains its real dispatch event and cannot
promote exact-head diagnostics into authoritative main evidence.
Environment-gated or skipped real-Servo tests do not establish runtime success.

## Product data, operations and change protocol

Managed receipt/state directories use `0700`, files use `0600` and the owning
service identity stays fixed. Provision authority-bearing parents in reviewed
image metadata. Retain opened directory/inode custody and one authoritative
writer; avoid recursive ownership repair or creating a fresh history after
corruption. Investigate indeterminate publication/dispatch by reading the exact
durable facts before any new action. Clearing a replay latch does not rerun an
operation or implicitly reconstruct the browser.

Record actual failures, skipped cases and environment limitations separately.
Each accepted gap binds requirement, public API/configuration, exact hostile
test names, source/tree, workflow/input/image digests, evidence tier, reviewer
and non-claims. Source, prospective-merge, installed-image, hardware and release
evidence have separate prerequisites. Old evidence becomes historical after its
invalidation inputs change; an edited JSON record cannot replace a rerun.

Follow the [closure plan](plan/IMPLEMENTATION_CLOSURE_PLAN.md) for ordering:
repair source/test coherence, complete the installed runtime/input path, qualify
its current image, then close capability/apps/egress and update acceptance before
hardware and signing. Add performance measurements for first frame, input,
observe/act, journal sync, recovery, RSS/FD/PID and queue growth. The project does
not yet provide an accepted product SLO or a measured full-load capacity result.
