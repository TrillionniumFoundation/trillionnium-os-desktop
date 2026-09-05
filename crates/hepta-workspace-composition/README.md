# hepta-workspace-composition

**Module registry ID:** `hepta-workspace-composition`  
**Workspace path:** `crates/hepta-workspace-composition`  
**Owner class:** `trusted-workspace`

Deterministic composition model for trusted chrome and one untrusted content surface.

## Status and claim ceiling

**Current status:** `headed_host_candidate_model`

**Claim ceiling:** engine-neutral trusted-workspace state and invariant model; no window, Servo instance, frame, clipboard, AgentPort, or external effect.

The status above describes the strongest repository-local statement this module may
make. It does not promote lower-tier source, host, headed-host, or QEMU evidence
into integrated-main, physical-hardware, signing-key-custody, or release facts.

## Responsibilities

- Model one compositor/native-owned trusted chrome surface and exactly one logical untrusted content surface.
- Own geometry, focus, pointer/keyboard/IME routing, frame publication, popup refusal, crash placeholder, and replacement generation invariants.
- Fail closed while replacement content is recovering and prevent stale frames or input owners from becoming authoritative.

## Non-responsibilities

- The crate does not create a native window, start Servo, render pixels, access the system clipboard, inject OS input, create an Agent listener, or navigate externally.
- Model tests do not prove headed-host, QEMU, hardware, or product integration.

## Dependency and call direction

This is an engine-neutral model used by the Servo qualification adapter and later trusted shell. It should remain independent of Servo/winit/X11/Wayland and operating-system services.

The authoritative workspace membership and review links are recorded in
`manifests/modules.v1.json`. New reverse dependencies, cycles, or authority-bearing
dependencies require an explicit architecture/security review.

## Public API and binaries

Public model operations apply deterministic workspace events and expose snapshots/refusals/effects. Callers must translate real engine/window callbacks into these events and obey returned ownership/generation decisions.

Public types and executable names are compatibility surfaces. Rust source remains
the API truth, while this document explains the intended boundary and correct use.
Callers must not infer authority from a type being constructible or a binary being
present in a non-production feature graph.

## Configuration and features

Cargo binary auto-discovery and package build scripts are disabled explicitly
with `autobins = false` and `build = false`. Only registered `[[bin]]` targets
may execute as module binaries. Adding a conventional `src/main.rs`, `src/bin`
entrypoint, or `build.rs` without a reviewed inventory change fails the module
gate; this does not disable integration-test discovery.

Surface count and trust topology are invariant, not runtime options. Geometry and generation values are explicit inputs. Additional windows/content surfaces require a new architecture decision and threat model.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

Trusted chrome survives content failure. Content crash clears content input/IME, withdraws the old frame, publishes a trusted placeholder, advances generation, and requires an explicit new non-zero generation plus fresh frame before routing resumes.

Rejected transitions and failed validation must not leave partial authority,
advanced revisions, committed responses, or invented receipt outcomes. Where a
result may be indeterminate, the caller must preserve that state and follow the
documented reconciliation policy instead of retrying blindly.

## Security invariants

Untrusted content cannot overlap/replace trusted identity, share its DOM trust realm, open a second content surface, retain input after crash/navigation, or promote stale pixels. Popup/new-window/external replacement requests fail closed.

The relevant contracts and architecture documents are listed in the module
registry. A source-only self-check or fixture never proves enforcement by a booted
product image.

## Testing and evidence

Run deterministic policy tests, rollback tests, all input owner transitions, crash/recovery and stale-frame cases, plus the headed Servo and D2I runtime corpora that prove real callbacks/pixels/process topology.

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

When composition stalls, inspect current generation, content lifecycle, presentable frame, placeholder, focus/input owner, and last refusal. Do not route input or reuse a frame merely to restore liveness.

Troubleshooting must preserve the original files, journals, identities, and exact
Git/build context needed for diagnosis. Do not make a gate pass by deleting a
hostile test, bypassing an admission check, broadening permissions, substituting a
fixture, or editing generated evidence by hand.

## Compatibility and change protocol

Changing trust topology, surface count, input ownership, or crash generation semantics requires an ADR, contract update, model/property tests, headed runtime evidence, and exact-main rerun.

Every behavior-changing pull request must update, as applicable: implementation,
contracts/schemas, golden vectors, tests, module registry, this README, architecture
and threat documentation, gate invalidation paths, evidence, and explicit
non-claims. Exact-head review and exact-main reruns remain separate promotion
transactions.
