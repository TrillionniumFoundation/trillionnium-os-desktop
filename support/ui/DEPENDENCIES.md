# Desktop and original Hepta product dependencies

The product uses one immutable original Hepta source for the shared Rust UI
presenter, Agentd, Objective compiler, operations, durable writer and carried
dependency patches. The canonical identity and source hashes are in
[HEPTA_SHARED_PRESENTER.json](HEPTA_SHARED_PRESENTER.json). The literal Notes
compiler is part of that source contract, so a source that lacks the required
API cannot be advertised as the current product combination.

The integration baseline is Desktop PR265 `4db81c63037f54c2a107c822d2cbc436150d8134`
and original Hepta `9600de28f5295c1758dd7e19bcac743fe5cfc082`, tree
`5cf15149d0e0d2ef1ae7d1d2784ea55c99b9a658`. The Desktop build commit must be
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
