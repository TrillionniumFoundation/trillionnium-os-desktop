# D1 qualification example and production graph

## Scope and non-claims

This contract covers source/build isolation of the D1 AgentPort qualification
example. It does not prove an installed QEMU image, product BrowserActor or
Servo dispatch, hardware, external effects, signing or release. The S04
production daemon remains fail-closed and its feature boundary is unchanged.

## Target and dependency direction

`hepta-agent-portd` has an empty default feature set. Its only opt-in `fixture`
feature enables the optional `hepta-agent-port` mechanism. Its two registered
binary targets remain the product daemon and the D0 fixture. Automatic binary
and example discovery and package build scripts are disabled.

The D1 program is an explicit Cargo **example** at
`apps/hepta-agent-portd/examples/hepta-agent-d1-fixture.rs`, selected by
`--no-default-features --features fixture --example hepta-agent-d1-fixture`.
Codec access and the peer-attestation qualification feature are declared only
as dev-dependencies. With the workspace's resolver 3, a selected product-bin
build does not activate those dev-dependencies; tests/examples intentionally
do. A workspace all-target/all-feature build is testing evidence, not a
production-artifact build command.

`tools/validate_d1_qualification_graph.py` is the executable source inventory
contract. It checks the exact normal/dev dependency boundary, fixed S04 feature
map, explicit targets and production install-map exclusion. The unchanged S04
validator remains a separate required gate; its acceptance set is not widened.

## Qualification peer evidence

The product `ServiceEvidence` type does not expose raw process credentials.
The D1 server obtains its original peer tuple from `SO_PEERCRED`, constrains
transport admission to that tuple and the reviewed user/group policy, holds
attestation, and refreshes it after the single request. Only the private D1
result formatter receives that original peer tuple separately. A missing or
zero PID is rejected; it cannot become a made-up zero identity.

The existing D1 result schema and qualification-only/non-product markers are
preserved for its consumers. These fixture-only identifiers must not be added
to product evidence or diagnostics. A fixture pass cannot authorize dispatch,
replace a real product handler or prove product installation.

## Independent build graphs within one host run

`tools/run_d1_final_qualification.sh prove-graphs` validates source isolation
and records normal/build/feature and qualification/dev dependency trees.
`build-binaries` creates distinct temporary Cargo target directories for the
product binary and D1 example. It saves both compiler JSONL streams, requires
one successful terminal record, inspects the actual selected target and
attestation features, and refuses qualification dependencies/features in the
product build before staging either output.

Only the verified product binary is copied to the product staging name. The
explicit example output is separately copied to the D1 qualification staging
name expected by the D1 image builder. That is not a production install-map
entry. Binary strings and separate host self-checks remain additional checks,
not substitutes for compile-graph validation.

Two isolated target directories are **not two independent release builders**.
No S12 reproducibility or administrative independence is claimed here.

## Tests and operation

Run the unchanged S04 source/test gate, the D1 graph validator, top-level Python
discovery, `tests/d1/test_d1_qualification_separation.py`, and locked Rust
format/check/Clippy/test with all targets and features. The new hostile corpus
rejects normal dependency leakage, default feature activation, hidden targets,
unregistered build edges, wrong compiler target kinds, missing/duplicate/failed
completion, static attestation leakage, malformed metadata and raw product
identity regression. The Rust example tests exercise its actual formatter and
invalid peer identity refusal.

The permanent `d1-qualification-graph` workflow tests the exact head and live
prospective merge without modifying tracked files. A bounded Git archive and
source/tree identity are retained for independent failure reproduction; this
capsule is source material, not a successful-test or installed-image receipt.

Failure leaves the candidate unqualified. Do not copy an all-feature workspace
binary into a production image, weaken S04, remove the example from the test
corpus, or relabel a fixture result. Head/base/input changes require fresh
qualification and independent review before any protected promotion.
