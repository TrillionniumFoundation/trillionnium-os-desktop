# Desktop and original Hepta product dependencies

The product uses one immutable original Hepta source for the shared Rust UI
presenter, Agentd, Objective compiler, operations, durable writer and carried
dependency patches. The canonical identity and source hashes are in
[HEPTA_SHARED_PRESENTER.json](HEPTA_SHARED_PRESENTER.json). The literal Notes
compiler is part of that source contract, so a source that lacks the required
API cannot be advertised as the current product combination.
The same contract includes the original native Notes port, bounded UI worker
and exact shared document-readback fixture. Both repositories decode
`notes-document-observation-v1.json`; a mismatched fixture is rejected before
Cargo runs. The snapshot is separate from an operation's terminal receipt.

The current combination is selected by `HEPTA_SHARED_PRESENTER.json`, which
records the complete original Hepta commit, tree and its reviewed file hashes.
The actual Desktop commit and tree belong to the build receipt. The earlier
PR265 / `489f7096` build remains historical evidence and supplies no test result
to this combination. All product compilation uses Rust 1.96.0; the common
resolution is serde 1.0.229, serde_json 1.0.154, tokio 1.53.3 and libc 0.2.191.
The UI and Session host Cargo roots carry the original AWS configuration patch
together with the other original dependency security patches. Full verification
covers the six lock roots listed below. The Notes model fixture, document
readback fixture and prepared SDK helper must match that same source.

## Selected source and current qualification (2026-10-27)

The selected Hepta source is [`de0ddaa41bd91c4f46a2f1b6034d25fa84c4469c`](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/de0ddaa41bd91c4f46a2f1b6034d25fa84c4469c), tree `004702e28244eb15a90ac0fa5d5a94e259dace8b`. Desktop [`94234e6a63858dcf7312025f6e20c85e00cc07f6`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/94234e6a63858dcf7312025f6e20c85e00cc07f6), tree `13b211835e776adf0aa450d168b40a97fa39b842`, completed and committed the six-lock convergence. Full source-byte and critical dependency-graph verification passed against the original de0 checkout; this is no longer a pending lock-generation task. The actual clean Desktop commit/tree, selected features and binary hashes still belong to each build receipt.

The canonical SDK helper and prepared SDK tree `6b422b3120f5f9b5c7ada579b55f647d51bd7fcf` remain selected. Ordinary Git SDK locks and the explicit `trill-shell/hepta-native-preedit-sdk` prepared lock stay separate. The earlier `baf73bf0` / FD convergence returned zero for all 14 Cargo commands and verified six graphs, 123 required source files and 219 original manifests; those observations remain tied to that earlier pair.

The exact 942/de0 combination completed three GitHub workflows successfully:
[native UI 40464606453](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/40464606453),
[Session host 40464584916](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/40464584916)
and [release source profile 40464413024](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/40464413024).
Native UI recorded 394 Rust passes and five ignored tests across its UI,
native-text and product-root invocations, built all five debug UI programs,
checked Clippy and ran the prepared SDK component. Its retained artifacts are
logs, metadata and binary hashes, not an installed release package. The
optimized distribution build, real login/model/Notes operation and installed
input/accessibility checks remain separate execution gates.

On original FD `fd6d8d3fcd9aee36711381adf74b6ba7162cda1b`, type checking, strict Clippy, 26 custody/stream/recovery tests, four original Supervisor tests, the complete 475 ordinary Agentd tests and 17 Memory tests passed. Two original ignored Root-preparation tests separately passed under actual UID0. The scoped `just fix` zero in 94.159 seconds without source changes and `just fmt` zero also belong to FD. These results do not qualify a successor installation or production Notes effect.

The FD cloud contract-gate failure exposed stale implementation-map ancestry/source observations. `00d173380e2d1425f83040fae848773ac0a440aa` migrated only 37 navigation/state metadata files, preserving Rust, Cargo and verifier scripts; its two original production-qualification phases returned zero. Current de0 adds one test-fixture line so the original removed-symbol negative exercises the intended capability branch, without restoring the production capability or changing its verifier. Its 20 Lane D tests passed; the completed successor qualification remains bound to its own final receipts.

The old a9/H8d UI pipeline finished all 16 actual commands with zero return codes. The e964 static counts (103/26/24 tests, 84 documents and 858 links) and H8d Session coexistence negative (effects=0) remain historical. Windows original failures, the unrecovered Android signer and the open Native link/guest/product gates remain separately tracked. No source-pin or documentation pass supplies installed-product, real Root/Notes, IME or accessibility qualification. See [current capabilities](../../docs/CURRENT_CAPABILITIES.md).

## Development and source checks

The shared source contract covers the original dependency manifests and all five ordinary product lock roots and the explicit prepared lock:

- `ui/Cargo.toml`: original patches including the four AccessKit packages.
- `ui/core/Cargo.toml`: original shared model and presenter dependencies.
- `services/hepta-session-host/Cargo.toml`: original Objective, operations,
  memory, Agentd and text worker, with the original runtime patches.
- `ui/Cargo.lock` and `services/hepta-session-host/Cargo.lock`: Cargo-generated
  full resolutions, including the Root, Fleet, Supervisor and original Core
  dependencies used by `product-root`.
- `services/hepta-os/Cargo.toml` and its lock: common wire package versions.
- `support/ui/Cargo.lock` and `tests/ui/Cargo.lock`: the two independent UI
  contract roots.
- `support/ui/preedit-sdk/Cargo.lock`: the separate Cargo-generated prepared
  SDK variant. The ordinary UI lock stays on the original Git SDK; the product
  builder verifies the declared variant in a disposable source copy and
  records its actual lock hash. Do not rewrite source strings in a lockfile.

Run from the Desktop root:

```sh
python3 support/ui/verify_product_dependencies.py --hepta-root /absolute/hepta
python3 -m unittest discover -s support/ui -p test_product_dependencies.py -v
cargo +1.96.0 metadata --manifest-path ui/Cargo.toml --locked --format-version 1 \
  --features trill-shell/hepta-shared-presenter > /absolute/shared-metadata.json
python3 tests/ui/verify_shared_presenter.py --metadata /absolute/shared-metadata.json
cargo +1.96.0 test --manifest-path services/hepta-session-host/Cargo.toml \
  --locked --all-targets --profile dev-small
```

The dependency verifier rejects mixed revisions, missing original owner
packages, local owner substitution, drift in the preedit profile and changed
source bytes. `codex-rs/Cargo.lock` is part of the original source contract:
full verification checks its actual Git regular-file blob, bytes and hash
before using it as the only reference for all six Desktop locks. Bindgen and
prettyplease must retain the original parser edges and agree on the same Syn
package identity; an unrelated Syn version used by another macro is allowed.
Every zstd, zstd-safe and zstd-sys node and chain must match that reference,
including source and checksum. A second obsolete version cannot hide beside
an accepted version. The check also reads the original owners' tracked Cargo
manifests and binds their mandatory incoming edges to that exact lock. It
validates every original owner's complete name, version, Git source and
checksum identity before selecting edges. Mandatory original path/workspace
bridges are checked as well as direct critical-family edges: replacing or
deleting an intermediate owner cannot remove its checks. Workspace aliases,
inherited versions, manifests outside `codex-rs` and target build dependencies
are resolved from regular tracked files whose current bytes match Git.
Each consumer's actual local package identity and nonoptional direct original
dependencies anchor that graph, so retaining only the outer UI SDK packages
cannot erase the entire inner owner layer. Optional original dependencies
remain optional; dev dependencies do not become mandatory production edges.
Removing an entire family and its incoming references cannot turn a required
dependency into a successful not-applicable result. Optional dependencies of
external packages still require Cargo's actual locked feature resolution;
the static check does not replace it. Missing or ambiguous edges are refused.

The same reference now covers the complete `aws-*` family. In particular,
carrying an `aws-config` patch table does not prove Cargo selected it: a newer
registry release can bypass the original vendor patch. The full check requires
the actual original Git/vendor package identity, exact SDK/Smithy versions and
checksums, and the original dependency edges. Upstream local vendor identities
map only to the selected downstream Git source. External optional edges may be
absent, but present edges cannot silently switch between reference versions.
This prevents the observed `aws-types`/Smithy schema mismatch in a fresh product
root and rejects an unpatched registry configuration package before compilation.

An early CI job without an original checkout may run
`python3 -I -B support/ui/verify_product_dependencies.py --source-only`.
This is a source preflight with `critical_graph_checked=false`, not a full
dependency result. Full verification requires `--hepta-root`; native source
validation, the prepared SDK component and Root packaging use that full path.
Its result records the reference lock hash and applicable nodes/edges for each
consumer root. Roots without the relevant dependencies remain explicitly
not applicable; the verifier never adds packages to make them applicable.

Full native metadata/resource verification still uses the
existing [text product builder](build_text_product.py) and
[native packaging contract](PRODUCT.md). The source check is deliberately fast
enough to run before either product's CI build.

## Updating the original source

Select and review one original Hepta commit containing every API the Desktop
uses. Run `python3 support/ui/update_product_source.py --hepta-root
/absolute/hepta --commit <full-reviewed-commit>` against that clean checkout.
It updates all three original dependency manifests, canonical file hashes and
preedit helper identity; it neither resolves locks nor grants runtime authority. Run `cargo update --workspace --manifest-path ...`
for each Cargo root to preserve unaffected locked versions where resolution
permits. Verify the actual metadata, original source checkout, all five ordinary locks and the separately generated prepared SDK lock,
then execute the owning packages' tests and native feature build. Preserve
the original logs and the final commit, tree, compiler and binary hashes.

When the reference changes a parser/printer or compression family, use Cargo
to update each affected consumer package ID to the reference version and
then check the actual resolved edges. A successful update command alone does
not establish type compatibility. Do not globally downgrade independent Syn
consumers, hand-edit lock dependencies or substitute the Hepta lock for a
Desktop lock. Generate the prepared SDK lock independently with the existing
controlled source-copy workflow; its path SDK remains distinct from the
ordinary Git SDK lock. The dependency regressions exercise these mismatches,
ambiguous and deleted nodes, source/checksum substitutions and tracked
reference-lock tampering in both normal and optimized Python.

For AWS convergence, first select the reference configuration package with
Cargo's precise update so the original patch is actually used. Then derive the
parent-before-dependency order from the current lock, update only drifting
family nodes to reference versions and reread the lock after each command.
Verify the final Git/vendor identity as well as versions; a successful command
or a present patch declaration alone is insufficient. Generate the prepared
SDK lock independently again after the ordinary roots have converged.

The immutable source selection supplies no production issuer, owner lease,
checkpoint service, Root process or device permission. Runtime readiness comes
from the existing authenticated owner. Unknown effects are reconciled under
their original operation identity; changing a dependency or restarting the UI
does not authorize another effect. Notes document durability is described in
[NOTES_DURABILITY.md](NOTES_DURABILITY.md).

## Native UI and text CI coverage

The `Original Hepta native UI compile coverage` workflow runs on Ubuntu 24.04
for changes to the UI, original Session host, source contracts, release helpers,
UI tests or its own workflow. It complements A10's default/shared-presenter
checks by enabling `trill-shell/hepta-native-makepad` for every UI workspace
target and binary, then exercising the standalone host's `native-text` adapter
tests with the same Rust 1.96.0 compiler, debug profile and temporary target
directory. One build job and disabled debug information/incremental output bound
resource use; the job has a 90-minute timeout.

Before Cargo, the dependency guard regressions run normally and with
Python optimization enabled. Actual native Cargo metadata must then pass
`build_text_product.validate_graph` and `verify_source_caches`; the canonical
source verifier checks the resolved original Hepta checkout, including its
reviewed source files and the mirrored Notes readback contract. The default
product checks keep their original Git SDK. Formatting, full native workspace
tests, native binary builds, all-target Clippy with warnings denied and
`hepta-session-host --features native-text --lib text::tests` are required.

An additional explicit prepared-preedit component creates disposable Desktop,
clean same-pin Hepta helper and SDK sources. The canonical helper generates
the complete 102-crate override from actual original metadata, and Cargo alone
generates the disposable UI path lock. That lock is restored in a `finally`
guard, including on rejected tests or caught termination. The component runs
the actual SDK Window focus scope (4 tests) and TextInput scope (35 tests),
checks named passes rather than accepting Cargo's zero-test success, and
re-verifies helper/SDK/full graph and original source caches. Eight component
guard regressions run normally and under Python optimization. This adds
reviewed SDK regression coverage without changing the default product source
or claiming its binaries were executed with that SDK. See
[PREEDIT_TEXT_PROFILE.md](PREEDIT_TEXT_PROFILE.md) for ownership and commands.

The final gate checks all five ordinary committed product locks, the separate
committed prepared SDK lock, checkout commit/tree,
tracked and untracked source cleanliness, actual native graph/cache identities
and standalone `native-text` resolution again. Artifacts retain logs, metadata,
source identities and ELF SHA256 records from that exact source. The Cargo
target directory and binary files are not uploaded. This workflow qualifies
compilation and tests; it does not start an original Root, install production
authority or claim window, visual, input-method or physical-device acceptance.

## Original live Root administrative sources

`root_admin_sources.py` defines the single mandatory source set used by both
`update_product_source.py` and `verify_product_dependencies.py`. It includes
Root administration, actual-issue observation, strict signed-grant validation,
original two-store revoke/readback, original session retirement, registered-file
custody and explicit-unlock admission, their scoped regressions and caller gate.
Omitting a callee or its gate cannot become an accepted presenter-only profile.
The source set grants no runtime authority or installed-product qualification.

After choosing the final clean compatible Hepta head, run the existing updater
against that exact checkout. It reads real tracked bytes/identities and unions
the mandatory files into `HEPTA_SHARED_PRESENTER.json`. Do not hand-add records,
borrow a foreign Cargo lock, or retain an old source proof for a new API. The
previous pre-admin source profile is expected to fail the new mandatory check.
Regenerate all ordinary/prepared Cargo roots from the selected source, preserve
the exact SDK source and upstream security patches, then run the complete
original dependency/source/manifest checks against that actual Hepta checkout.
[ROOT_PRODUCT.md](ROOT_PRODUCT.md) and the [administrative entry](../../services/hepta-session-host/src/product_root/ADMIN.md)
describe the corresponding product and development limits.
