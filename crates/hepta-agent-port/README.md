# hepta-agent-port

**Module registry ID:** `hepta-agent-port`  
**Workspace path:** `crates/hepta-agent-port`  
**Owner class:** `agent-port-core`

Exactly-one request bridge from authenticated transport to a typed handler.

## Status and claim ceiling

**Current status:** `host_validated_mechanism`

**Claim ceiling:** exactly one authenticated connected-stream Browser API lifecycle; no listener, principal authority, Servo dispatch, or external effect.

The status above describes the strongest repository-local statement this module may
make. It does not promote lower-tier source, host, headed-host, or QEMU evidence
into integrated-main, physical-hardware, signing-key-custody, or release facts.

## Responsibilities

- Authenticate an already-connected stream, decode exactly one canonical Browser API request, and construct at most one request-bound response.
- Freeze immutable dispatch identity and enforce the earlier of server and translated request deadlines.
- Notify a lifecycle observer in fail-closed requested/dispatched/completed or indeterminate order.

## Non-responsibilities

- The crate does not own a socket/listener, systemd unit, TaskFlow principal mapping, browser engine, capability issuer, or effect executor.
- The D0 fixture handles health only and is never a substitute for a production BrowserActor.

## Dependency and call direction

AgentPort composes transport and codec and invokes an injected typed handler/observer. BrowserActor and app binaries depend on this crate; the crate must not depend on application profile or Servo implementation.

The authoritative workspace membership and review links are recorded in
`manifests/modules.v1.json`. New reverse dependencies, cycles, or authority-bearing
dependencies require an explicit architecture/security review.

## Public API and binaries

Public serving functions operate on one connected stream and a handler. Dispatch context fields are authored by the mechanism, not by the handler. Observer APIs bind durable receipt ordering around handler invocation and response commit.

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

Frame and request bounds come from transport/codec contracts. Handler deadline ceilings are explicit inputs. There are no ambient listener addresses, credentials, or retry toggles.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

One connection admits at most one request and one handler call. Late handler results are discarded. Journal/observer failure aborts the response. Potential effects interrupted after dispatch become indeterminate and are never automatically replayed.

Rejected transitions and failed validation must not leave partial authority,
advanced revisions, committed responses, or invented receipt outcomes. Where a
result may be indeterminate, the caller must preserve that state and follow the
documented reconciliation policy instead of retrying blindly.

## Security invariants

Handlers cannot rewrite protocol, request, session, sequence, nonce, or response identity. The bridge must check deadline/cancellation before and after dispatch and must not emit a success before durable terminal facts are committed.

The relevant contracts and architecture documents are listed in the module
registry. A source-only self-check or fixture never proves enforcement by a booted
product image.

## Testing and evidence

Run health fixture, refusal/error mapping, deadline, response identity, observer failure, indeterminate lifecycle, and transport poison tests. Exact-head workspace and receipt-journal workflows are required.

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

Diagnose failures by layer: peer/transport, codec, admission/deadline, observer requested, observer dispatched, handler, observer terminal, response write. Preserve the first authoritative error and response-commit fact.

Troubleshooting must preserve the original files, journals, identities, and exact
Git/build context needed for diagnosis. Do not make a gate pass by deleting a
hostile test, bypassing an admission check, broadening permissions, substituting a
fixture, or editing generated evidence by hand.

## Compatibility and change protocol

Handler and observer traits are security contracts. Signature changes require all app adapters, BrowserActor, receipt tests, schema, and evidence updates. No compatibility shim may bypass identity or journal ordering.

Every behavior-changing pull request must update, as applicable: implementation,
contracts/schemas, golden vectors, tests, module registry, this README, architecture
and threat documentation, gate invalidation paths, evidence, and explicit
non-claims. Exact-head review and exact-main reruns remain separate promotion
transactions.
