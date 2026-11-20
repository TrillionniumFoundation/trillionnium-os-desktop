# Current application leaf selection

The runtime selected the November 14 preparation while the published current
application plan selected the November 19 IHG 5.111.1/50023808 preparation.
Both IHG London input/readback and the Clock timer route use entry 5. This packet
binds their actual current selector, preparation and source entry together.

The parent is the complete 2,351-file materialization successor
`454a50a52837f80a50d39815da91b0c8cd7a1e4c`. The required tracked-file fix remains
byte-identical. Only `leaf_routes.rs` and `leaf_sources.json` change; a byte-exact
published selection fixture is added. All 37 original application tests remain,
with five tests covering the current source chain and false admissions.

Runtime admission still reads the exact selected files and preserves the original
entry's complete transitive-source, Main epoch, package, display, limits and
cleanup checks. A source selection grants no runtime or production credit.
IHG remains input/readback-only with an unknown business outcome. The 32 required
applications without a selected business executor remain unsupported.

## Reproduce

Use the externally reviewed SHA-256 of `FILES.sha256` as `PIN` below. Reconstruct
the original PR315 capsule and the materialization successor first. Then:

```sh
python3 -I -B verify.py --inventory-sha256 "$PIN" \
  --parent-packet /absolute/vendor-source-materialization-20261120/rust \
  --parent-source /absolute/materialization-successor/producer \
  --output /absolute/new-leaf-successor/producer --report /absolute/new-leaf-replay.json
python3 -I -B run_ci.py --inventory-sha256 "$PIN" \
  --producer /absolute/new-leaf-successor/producer \
  --work /absolute/new-leaf-build --report /absolute/new-leaf-ci.json --jobs 2
```

The replay verifies full parent membership and hashes, applies exact hunks without
offsets or fuzz, copies independent regular files, adds the exact fixture, and
checks the complete successor Git tree. Compilation is locked and offline on
Rust 1.93.0. The checker requires the full 42-test compiled catalog and actual
unfiltered passing terminals, with each child group retired. Its format check
covers the changed Rust file; it makes no claim about pre-existing workspace
formatting failures. Keep at least two logical CPUs free.

## Evidence limits

Source identities come from the published PR315 packet at commit
`765c67ff1113885c98bcf84a31e937f484cc5c35`, recorded in `PUBLIC-SOURCE-PINS.json`.
The current selector was denied to an ordinary account on Pocket4. That read was
not retried or elevated. This static fix does not assert that sealed live inputs
are readable or currently have destination custody. Those runtime gates must be
satisfied by actual later observations; the source fixture is not such evidence.

No Android command, install, source-tree restore, activation or browser ownership
integration is performed by this packet. No release binary from the historical
19-target declarations is repinned or requalified.
