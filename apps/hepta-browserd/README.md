# hepta-browserd

**Module registry ID:** `hepta-browserd`  
**Workspace path:** `apps/hepta-browserd`  
**Owner class:** `desktop-runtime`

Product-facing browser daemon composition and self-check boundary.

## Status and claim ceiling

**Current status:** `source_candidate_integrated_foundation`

**Claim ceiling:** compiled side-effect-free D4-D7 policy and coordination source; no integrated-image, external-effect, update, hardware, signing, or release authority.

The status above describes the strongest repository-local statement this module may
make. It does not promote lower-tier source, host, headed-host, or QEMU evidence
into integrated-main, physical-hardware, signing-key-custody, or release facts.

## Responsibilities

- Compose the integrated D0 transport, codec, AgentPort, contract, session, BrowserActor, and product-policy crates without silently widening their authority.
- Expose the deterministic `hepta-browserd --self-check` entry point and aggregate source-level policy, coordinator, and injected-runtime invariants.
- Keep explicit build and plan anchors at the public crate boundary so repository-truth validation can detect drift.

## Non-responsibilities

- It does not start a promoted Servo product session, bind a public listener, resolve external DNS, execute an external effect, write an update slot, hold signing keys, or claim hardware/release qualification.
- The D4-D7 modules compiled here are source integrations. Their real portal, proxy, block-device, browser, and hardware adapters remain separate gates.

## Dependency and call direction

The binary calls the library self-check. The library composes lower-level pure mechanisms and policies; those dependencies must not call back into `hepta-browserd`. Real operating-system authority must be injected through reviewed adapters rather than discovered from ambient process state.

The authoritative workspace membership and review links are recorded in
`manifests/modules.v1.json`. New reverse dependencies, cycles, or authority-bearing
dependencies require an explicit architecture/security review.

## Public API and binaries

Public API is intentionally small: plan/stage constants, `run_self_check`, and the `SelfCheckReport`. Internal modules are `legacy`, `product_policy`, `authority_coordinator`, and `product_runtime`. The only binary is `hepta-browserd` at `src/main.rs`.

Public types and executable names are compatibility surfaces. Rust source remains
the API truth, while this document explains the intended boundary and correct use.
Callers must not infer authority from a type being constructible or a binary being
present in a non-production feature graph.

## Configuration and features

There are no Cargo features. Runtime authority is not selected through hidden environment defaults. Any future executable configuration must be typed, documented, fail closed, and separated by product/development/qualification profile.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

Policy and coordinator self-checks are deterministic and side-effect free. Arithmetic and identity transitions use checked operations and explicit inputs. A failed sub-check aborts the aggregate report; no partial success may be promoted. Real browser or effect adapters must preserve deadline, cancellation, PageOwner, and receipt ordering.

Rejected transitions and failed validation must not leave partial authority,
advanced revisions, committed responses, or invented receipt outcomes. Where a
result may be indeterminate, the caller must preserve that state and follow the
documented reconciliation policy instead of retrying blindly.

## Security invariants

The daemon is the composition boundary, not an authority amplifier. It must preserve AgentPort default-closed behavior, one PageOwner, generation-bound references, authenticated principals, non-replaying receipts, and explicit external-effect denial. A new dependency or module that gains sockets, credentials, devices, update, or signing authority requires a new threat review and gate.

The relevant contracts and architecture documents are listed in the module
registry. A source-only self-check or fixture never proves enforcement by a booted
product image.

## Testing and evidence

Run the workspace Rust checks, all-feature lane, `cargo run --locked -p hepta-browserd -- --self-check`, repository validators, and D4-D9 source workflows. Source-green results do not replace D2I, fixed-hardware, or release evidence.

Minimum local verification:

```bash
python3 tools/validate_module_documentation.py
python3 tools/validate_repository.py
python3 tools/validate_project_truth.py
cargo fmt --all --check
cargo check --workspace --all-targets --all-features --locked
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo test --workspace --all-targets --all-features --locked
```

Interpret every result under the claim ceiling and evidence tier recorded by the
gate registry. A skipped, cancelled, historical, or differently bound run is not
current evidence.

## Operations and troubleshooting

A self-check failure should be diagnosed at the first named sub-report. Record exact commit/tree, Rust toolchain, command, and error. Never make the self-check green by skipping a submodule or converting an authority assertion into a warning.

Troubleshooting must preserve the original files, journals, identities, and exact
Git/build context needed for diagnosis. Do not make a gate pass by deleting a
hostile test, bypassing an admission check, broadening permissions, substituting a
fixture, or editing generated evidence by hand.

## Compatibility and change protocol

Public constants and report fields are contract surfaces. Changes require synchronized Rust tests, machine truth, relevant architecture documents, workflow evidence, and an explicit claim ceiling. No legacy behavior may be removed if a retained evidence parser still depends on it.

Every behavior-changing pull request must update, as applicable: implementation,
contracts/schemas, golden vectors, tests, module registry, this README, architecture
and threat documentation, gate invalidation paths, evidence, and explicit
non-claims. Exact-head review and exact-main reruns remain separate promotion
transactions.
