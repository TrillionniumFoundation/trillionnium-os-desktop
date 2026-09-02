# hepta-browser-actor

**Module registry ID:** `hepta-browser-actor`  
**Workspace path:** `crates/hepta-browser-actor`  
**Owner class:** `browser-actor-security`

One-PageOwner BrowserActor admission, dispatch, semantic-action, and receipt boundary.

## Status and claim ceiling

**Current status:** `d3_source_candidate`

**Claim ceiling:** engine-neutral PageOwner/principal/dispatch/receipt core with deterministic local runtime; no promoted Servo adapter, production AgentPort, external effect, or integrated-image authority.

The status above describes the strongest repository-local statement this module may
make. It does not promote lower-tier source, host, headed-host, or QEMU evidence
into integrated-main, physical-hardware, signing-key-custody, or release facts.

## Responsibilities

- Bind an attested mechanism identity to an exact TaskFlow semantic principal and revalidate it before each dispatch.
- Own at most one active PageOwner/WebView token, enforce session/revision/control state, and map validated Browser API operations to typed runtime calls.
- Require `page_act` to use a dedicated atomic semantic resolver hook and wrap admitted operations in durable requested/dispatched/terminal or indeterminate receipts.

## Non-responsibilities

- The crate does not create a listener, own systemd activation, hold browser DOM nodes itself, issue capabilities, provide external network authority, or promote a release.
- The deterministic local runtime has no real DOM and intentionally cannot claim semantic `page_act` execution.

## Dependency and call direction

BrowserActor composes AgentPort, transport identity, codec models, peer attestation, session admission/journal, and neutral contracts. A concrete engine runtime implements the downward `PageRuntime` boundary; it must not call around the actor to mutate PageOwner state.

The authoritative workspace membership and review links are recorded in
`manifests/modules.v1.json`. New reverse dependencies, cycles, or authority-bearing
dependencies require an explicit architecture/security review.

## Public API and binaries

Principal binding, actor construction, PageOwner lifecycle, typed dispatch, cancellation/deadline inputs, lifecycle observer integration, and `PageRuntime::dispatch_page_act` are key surfaces. The default semantic-action hook is unsupported to prevent unsafe fallback.

Public types and executable names are compatibility surfaces. Rust source remains
the API truth, while this document explains the intended boundary and correct use.
Callers must not infer authority from a type being constructible or a binary being
present in a non-production feature graph.

## Configuration and features

Runtime/profile policy and identity expectations are injected. No ambient browser handle, credentials, external URL allowlist, or production activation is discovered from environment. Development configuration is owned by the separate D3 app.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

Every operation validates principal, session, generation, phase/control, cancellation, and deadline before runtime work. Observation/mutation/navigation acquire explicit control and release on all terminal paths. Close performs local terminal cleanup even if runtime acknowledgement fails.

Rejected transitions and failed validation must not leave partial authority,
advanced revisions, committed responses, or invented receipt outcomes. Where a
result may be indeterminate, the caller must preserve that state and follow the
documented reconciliation policy instead of retrying blindly.

## Security invariants

One PageOwner, no hidden second page, exact principal/mechanism binding, dispatch-time re-attestation, stale reference refusal, atomic current-frame semantic resolution, exactly-once action cardinality, durable receipt-before-response ordering, and no automatic potential-effect replay are mandatory.

The relevant contracts and architecture documents are listed in the module
registry. A source-only self-check or fixture never proves enforcement by a booted
product image.

## Testing and evidence

Run actor unit/state tests, hostile principal/revision/control/deadline/cancellation/runtime-failure cases, semantic resolver reference and Rust fixture, D3 profile corpus, journal recovery, and eventually the complete exact D2I Servo adapter corpus.

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

Classify failures before runtime dispatch versus after dispatch. Preserve requested/dispatched/terminal/indeterminate receipt status, response-commit status, principal snapshot, PageOwner revisions, cancellation/deadline, and engine error without page secrets.

Troubleshooting must preserve the original files, journals, identities, and exact
Git/build context needed for diagnosis. Do not make a gate pass by deleting a
hostile test, bypassing an admission check, broadening permissions, substituting a
fixture, or editing generated evidence by hand.

## Compatibility and change protocol

Trait changes affect all runtimes and security proofs. New operation mappings must be added to contracts, codec, actor admission, runtime trait, receipts, tests, and claim ceilings. `page_act` may never be routed through a generic unverified action fallback.

Every behavior-changing pull request must update, as applicable: implementation,
contracts/schemas, golden vectors, tests, module registry, this README, architecture
and threat documentation, gate invalidation paths, evidence, and explicit
non-claims. Exact-head review and exact-main reruns remain separate promotion
transactions.
