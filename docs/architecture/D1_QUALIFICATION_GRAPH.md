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
attestation, and refreshes it immediately before fixture dispatch. Only the private D1
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

## Cross-UID guest admission and failure diagnosis

The D1 client and connection service deliberately have different service UIDs.
Their status, start-time and cgroup snapshots do not imply permission to read
`/proc/<peer>/exe`. The qualification server therefore uses the existing
`qualification-static-attestation` mechanism and the fixed root-owned installed
path `/usr/libexec/hepta-agent-d1-fixture`. The binding is never selected by
request, CLI, environment or an arbitrary digest. It identifies the reviewed
qualification service executable source; it does not claim that live procfs
executable identity was observed. No production feature, product daemon,
service user, ptrace capability or installed product map is changed.

The private `AttestedFixtureHandler` compares the original socket peer, refreshes
the original attestor/path-bound custody, and checks the deadline immediately
before forwarding to `D0FixtureHandler`. A mismatch, expired deadline, changed
attestor, exited process or refresh failure invokes no fixture handler. Existing
potential-effect refusal remains intact. No new browser or external-effect
authority is introduced. A client may exit normally after receiving its result;
a late post-response identity check cannot retroactively define dispatch safety.

The guest failure path captures only the three qualification AgentPort unit
journals, bounded to 160 lines, 64 KiB and five seconds. After QEMU terminates,
`tools/collect_d1_guest_failure.sh` reads only the fixed acceptance and AgentPort
journal paths with bounded read/time and diagnostic-prefixed output names. Empty,
failed, timed-out or oversized reads are omitted, never presented as complete
receipts. Missing diagnostics do not change the original failing exit status.
This export is for a credential-free qualification image, not a general product
journal export or a substitute for privacy-reviewed operational tools.

Run `python3 -m unittest tests.test_d1_guest_custody -v`, the unchanged graph/S04
gates and all existing D1 tests. Locked all-target/all-feature Rust checks must
execute the example's new live-custody/deadline/process-exit tests. Finally rerun
the exact D1/QEMU guest: normal authorized health, unauthorized refusal, killed
connection and recovery must all pass. A local Linux cross-UID diagnostic or a
mocked debugfs test cannot establish that installed guest result. The full S10
product BrowserActor/Servo/receipt path remains a separate unresolved gate.
