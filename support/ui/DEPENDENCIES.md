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

The integration baseline is Desktop PR265 `4db81c63037f54c2a107c822d2cbc436150d8134`
and original Hepta `489f7096b0e5754968a30fa4477bb4417d24834f`, tree
`4731de9117065bd773b2fcee92c815ff896b8488`. The Desktop build commit must be
recorded separately by the actual build receipt; this document does not grant
later source edits the baseline's test results. Both product Cargo roots use
Rust 1.96.0. The prior `7ea3df4` combination remains historical evidence.

## Development and source checks

The shared source contract covers these manifests and both Cargo roots:

- `ui/Cargo.toml`: original patches including the four AccessKit packages.
- `ui/core/Cargo.toml`: original shared model and presenter dependencies.
- `services/hepta-session-host/Cargo.toml`: original Objective, operations,
  memory, Agentd and text worker, with the original runtime patches.
- `ui/Cargo.lock` and `services/hepta-session-host/Cargo.lock`: Cargo-generated
  full resolutions. Do not rewrite source strings in a lockfile by hand.

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
source bytes. Full native metadata/resource verification still uses the
existing [text product builder](build_text_product.py) and
[native packaging contract](PRODUCT.md). The source check is deliberately fast
enough to run before either product's CI build.

## Updating the original source

Select and review one original Hepta commit containing every API the Desktop
uses. Update all three manifests, the canonical file hashes and applicable
resource profiles together. Run `cargo update --workspace --manifest-path ...`
for each Cargo root to preserve unaffected locked versions where resolution
permits. Verify the actual metadata, original source checkout and both locks,
then execute the owning packages' tests and native feature build. Preserve
the original logs and the final commit, tree, compiler and binary hashes.

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

Before Cargo, the nine dependency guard regressions run normally and with
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

The final gate checks both committed product locks, checkout commit/tree,
tracked and untracked source cleanliness, actual native graph/cache identities
and standalone `native-text` resolution again. Artifacts retain logs, metadata,
source identities and ELF SHA256 records from that exact source. The Cargo
target directory and binary files are not uploaded. This workflow qualifies
compilation and tests; it does not start an original Root, install production
authority or claim window, visual, input-method or physical-device acceptance.
