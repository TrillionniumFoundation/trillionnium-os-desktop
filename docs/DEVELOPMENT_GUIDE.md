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
| D3 BrowserActor and Servo | `hepta-browser-actor`, `apps/hepta-browserd/src/product_dispatch.rs`, separate simulation crate; S08 architecture | Original-stream attested coordinator, bounded deadline/queue/cancellation, semantic preflight, concrete actor and durable response ordering | Installed native Servo owner/startup and connection-service handoff; approved cross-UID live executable attestation; qualification mailbox cannot substitute |
| D3 runtime crash/recovery | `apps/hepta-browserd/src/servo_product_runtime.rs`; S08 product supervision | Checked generations, explicit reconstruction, bounded crash loop, no automatic replay | Wire the supervisor into product startup, process custody, trusted recovery UI and durable reconciliation |
| D3 receipts | `hepta-session-core`; journal, managed store and fault-model contracts | Durable chained lifecycle facts, recovery, bounded records, rotation and redacted export | Installed crash/disk-full matrix, archival/quota policy and independently protected rollback anchor |
| D4 collaboration and input | Session machine, `hepta-workspace-composition`, `experiments/servo-headed-runtime`; session/composition architecture | Human/Agent arbitration; native fixture candidate withdraws input on chrome/focus/crash and rejects stale callbacks | Product PageOwner/native integration, compositor scaling/layouts/clipboard and Chinese OS IME; trusted approval and handoff UX |
| D1/D2I and S10 image | `packaging/debian/image/`, `tools/run_d1_final_qualification.sh`, `tools/run_d2i_integrated_image.sh`; D1/D2I architecture | Locked image builders, qualification overlays, guest runners and offline evidence checks | Current immutable image builds and guest runs, review and exact-main regression; production binary still disabled |
| S09 Linux mechanisms | `platform/linux/adapters.py` and its README | Descriptor-confined files, clock/entropy/procfs, retained Wayland endpoint, pure HTTPS/address policy | Native rendering/input, actual resolver/TLS/socket enforcement and installed mechanism coverage |
| D5 trusted apps | `platform/trusted_apps.py`, `docs/architecture/TRUSTED_APP_BUNDLES.md`, ADR 0004 | Real offline Ed25519 verification, complete bounded bundle index, immutable local assets, publisher-scoped root/revocation policy and restrictive headers | Installed origin interception/CSP/CORS/cache and protected root/policy delivery |
| D5 app storage lifecycle | `platform/app_storage.py`, `docs/architecture/APP_STORAGE.md`, app-storage contract | Private leased principal/origin partitions, complete package re-admission, durable version/policy floors, same-schema upgrades, uninstall/data tombstones and no-replay transactions | Native storage and principal binding, authenticated current time, migrations, authorized recovery/archival and independently protected rollback anchor |
| D6 capabilities and TaskFlow | `platform/taskflow.py`; TaskFlow architecture and execution contract | Actual externally signed scoped permits, typed immutable proposals, cancellation/handoff/budgets, durable task reservations and single-use consumption, fork refusal | Trusted approval UX, installed retained-target final effect checks, product terminal receipts and persisted authorized recovery |
| D6 controlled observation egress | `platform/controlled_egress.py`; controlled-egress architecture and contract | Actual approved DoT resolution, all-answer IPv4/IPv6 policy, connected peer and TLS identity, bounded GET response/redirects, session/origin revocation and whole-operation cancellation/deadline | Browser namespace and every load-class intercept, trusted policy delivery, external-effect authority and durable indeterminate reconciliation |
| D7 / S11 update and recovery | `platform/update_recovery.py`; S11 architecture and contract | Real externally rooted offline signature verification, full streamed inactive regular-file image publication, bound durable reconciliation and issuer-scoped health permits | Provisioned production roots/trusted clock, protected monotonic-floor persistence, installed block-slot/boot/health/recovery adapters and fault matrix |
| D7 / S11 durable update owner | `platform/durable_update_owner.py`, `docs/architecture/DURABLE_UPDATE_OWNER.md`, durable-update-owner contract | Complete durable intent before actual regular-file staging, issuer-bound results with complete history/image readback, nonregressing configured time and unclean/unfinished restart quarantine without replay; arming records source policy only | Separate S11 directory-walk interrupted-close/reused-FD correction and joint regressions; installed service/boot/health/commit/rollback, trusted roots/time/floor, protected rollback anchor and installed power-loss acceptance |
| D8/D9 / S12 release | Release architecture, `tools/verify_s12_release_qualification.py` | Offline packet/signature/role/subject consistency verifier | Independent builders, fixed hardware, actual endurance/power cuts, key custody, protected signing/promotion/publication |
| D0T governance | `docs/governance/BRANCH_PROTECTION_REQUIRED.md`, gate registry and workflows | Source policy and workflow definitions | Live enforced branch/ruleset/environment settings, actual independent identities/review; source files cannot supply them |

Source and specification coverage is substantial for the security foundations.
An operational installed desktop remains incomplete: executable `hepta-browserd`
still starts its scaffold/self-check, and the product AgentPort rejects activation
without a promoted handler. The complete request/recovery acceptance path is
defined in [REQUEST_EXECUTION_AND_RECOVERY.md](architecture/REQUEST_EXECUTION_AND_RECOVERY.md)
and remains a product integration gate.

## CI absence checks

S06's sealed-API checks, S07's unforwarded-action check and D2I's source
permission scan distinguish native grep status 0 (forbidden match), 1 (no
match) and other statuses (read failure). Both matches and read failures end
the gate explicitly. A negated command by itself disables Bash errexit for
that command and can lose a failure when a later command succeeds.

`tests/test_ci_absence_guards.py` executes the complete S06 claim-check bodies
with isolated source/contract fixtures, and the actual S07/D2I guard tails with
native grep and Git checks. It preserves the original patterns and scan scopes
and exercises clean inputs, forbidden markers and absent inputs. These tests
prove the source gate's behavior; they do not compile Servo, build an image or
qualify a product runtime.

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

The top-level Python platform candidates also have a closed source inventory in
`manifests/platform-mechanisms.v1.json`. It registers six modules with fixed
requirement and implementation/document/contract/test mappings, including
`durable_update_owner` for G6/D7/S11. It records source-defined public function,
constructor, method and dataclass-field signatures alongside requirement,
technical document, contract and executable test source. Run
`python3 tools/validate_platform_mechanisms.py`; after a reviewed API change,
refresh signatures with `--refresh-api` and review the resulting diff. Contract
profiles require a separate explicit review; refresh cannot change a profile,
default or qualification. The durable owner profile closes every actual nested
contract object and pins its leaves, including null/default-denied admission,
false installed/boot/release claims and source status. This
inventory check imports no mechanism and reports no test execution or acceptance.
Actual hostile tests run separately in both candidate-head and prospective-merge
desktop CI, including stacked review branches.

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

### Exact source tests with live executable custody

Source CI test steps set `CARGO_PROFILE_TEST_DEBUG=0` and
`CARGO_PROFILE_TEST_OPT_LEVEL=1`. Live procfs checks still hash the actual
current executable at their original boundaries. Excluding test-only DWARF
and optimizing the same measurement code avoids spending the original
request ceiling on an unoptimized fixture ELF. The original test bodies,
2/20/3-second limits, assertions, expiry/refusal gates and run commands stay
unchanged. A private unmodified complete control/terminal diagnostic passed
13 real groups, nine explicitly synthetic-Agent cuts and eleven terminal
cases with this profile; it is not timing of an earlier CI failure or fresh
CI qualification.

The settings are local to repository source-test steps, including D1/D2I
source validation. Production binary/image builds, the pinned Servo runtime
and its own library/behavior tests keep their original profiles. Profile
changes require exact source freezing, complete unfiltered source checks,
independent review and fresh exact-object CI. Original failed objects stay
failed; later passes never renew the original request budget.

### Live PR refs in source CI

The update-boot observer and controlled-egress matrices use an independently
validated positive canonical decimal PR number to read exactly
`refs/pull/<number>/head` from `origin`; push lanes still read their exact
`refs/heads/<branch>`. Agent-transport reference and both S04 prospective lanes
also use the PR ref. A same-named origin branch cannot substitute for a missing
or changed fork PR. The resolver requires one exact advertised ref field,
not a pattern suffix match. Prospective objects must have exactly two parents
in live base/head order and still match the expected checked-out object.

Run `python3 -B -m unittest discover -s tests -p test_ci_pr_ref_identities.py -v`
for the complete five Bash identity bodies against private real Git refs.
The reference body retains its fixed `/tmp` output; the test helper uses a
privileged subprocess-only mount namespace and then drops to the fixture
creator's UID/GID before running it. Missing namespace privileges fail the
corpus rather than skip it. These Git/CI source facts grant no product,
principal, runtime, image, signing or release authority. Existing runtime
commands, deadlines, source-test profiles and acceptance thresholds remain
unchanged; fresh exact-object CI must run after a workflow change.
