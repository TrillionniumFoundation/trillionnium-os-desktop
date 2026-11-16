# Native643 complete715 Cuttlefish provider source

This capsule contains the entire tested Native producer. Its two source catalogs authenticate every Git blob and mode and reconstruct both complete root trees:

| Generation | Commit | Full root tree | Files |
| --- | --- | --- | ---: |
| Parent | `2f91fe5f81886ca24c4c562ce9491f16e17261d5` | `d30800eda1b2be36ac636913171195551cfefd38` | 647 |
| Current | `3450f2591faec153dbab06477d0a00e95120321f` | `af2c7788ca297e8cf499a4f18a0aa3d278d3b419` | 715 |

The delta changes three producer files and adds 68 original graphics provenance fixtures. The other 644 files are byte-for-byte and Git-mode identical. `producer/` contains all 715 current files; `preimages/` contains the three changed parent files. Full raw parent and current commit bodies authenticate the two tree roots and the single parent relationship. This supersedes the earlier publication's compilation-only file selection without changing the producer.

## Production source change

The source lock preserves the same 643 pinned projects and revisions and appends only `tests/graphics/hotplug` to the existing `device/google/cuttlefish` project. The normal source transaction selected the three original files, totaling 6,021 bytes, needed by `CuttlefishDisplayHotplugHelperApp`. The complete 57-file graphics tree and the original provider definitions are retained as provenance. The 49 previously materialized graphics/provider inputs remain exact; the 11 unrelated display files remain unselected.

The corresponding producer validation authenticates the original Git graph, the selected source set, and the complete old validation chain. The Native source policy remains 643 selected projects, `MAX_PROJECTS = 643.div_ceil(16) * 16 = 656`, and `MAX_SPARSE_PATHS = 336`. Audio has a separate producer and is not modified by this capsule. The value 656 is the actual source bound; earlier publication metadata described it incorrectly as 672.

## Original qualification evidence

`evidence/` preserves all 154 captured qualification records, controls, and original logs. The original a46 ordinary execution passed 92 different tests with 98 executions across 29 commands. It produced two actual test harnesses and two normal CLI binaries. The independent a54 retirement verified 66 complete logs, 43 original PIDs, three absent cgroups, the full 647 and 715 producer inputs, and the source/index/projection boundaries. The verifier parses the original Rust and Cargo terminals and joins the original process identity, approved request, inner/outer results, command receipts, logs, and independent retirement.

The a5f capture refusal remains a failed original record. The successful follow-up copied files with their original Git checkout modes while preserving the original physical source permissions. No historical failed build or capture is upgraded by this package.

The current updater CLI was compiled with `fresh: false` during the first `cargo test --no-run` invocation and then reported `fresh: true` during the final `cargo build` in the same new target. The verifier requires that exact original fresh origin. Fresh CI applies the same rule: a cached Cargo message is accepted only when its complete artifact identity has an earlier fresh compilation in that invocation's newly created target and its ELF identity remains unchanged. It never accepts a historical binary or a cached artifact from another target.

## Verify and replay

The caller must supply the expected SHA-256 of `FILES.sha256` from an external fixed workflow or reviewed release record. A value calculated from the capsule at runtime is not an external pin.

```sh
python3 -I -B "$CAPSULE/test_verifier.py"
python3 -I -B "$CAPSULE/verify.py" \
  --inventory-sha256 "$NATIVE715_INVENTORY_SHA256" \
  --output "$FRESH_ROOT/producer" \
  --report "$FRESH_ROOT/replay.json"
```

The output and report must be absent canonical paths outside all inputs. Replay copies all current source files into independent inodes, skips only a source-root `.git` directory, constructs private Git metadata, and performs reverse/check/apply twice. Every intermediate state must reproduce its entire original Git root. Git children use umask `0022`; a caller may retain umask `0077` for its private output. The maintained repository's hooks or configuration are never changed. Complete input F9, including nanosecond modification/change time and file and directory membership, is checked before and after.

## Fresh CI

```sh
python3 -I -B "$CAPSULE/run-normal-controls.py" \
  --inventory-sha256 "$NATIVE715_INVENTORY_SHA256" \
  --workspace "$FRESH_ROOT/producer" \
  --output "$FRESH_ROOT/normal"
python3 -I -B "$CAPSULE/verify.py" \
  --inventory-sha256 "$NATIVE715_INVENTORY_SHA256" \
  --producer "$FRESH_ROOT/producer" \
  --report "$FRESH_ROOT/source-after.json"
```

CI creates a new Cargo target, compiles both actual harnesses, executes 53 Native pair controls, 26 source controls, seven v2 permission controls, six journal regressions, and six repeated focused pair controls. It then verifies two current normal CLI entry points and their exact source lock/plan. This is 92 different tests, 98 executions, and 23 actual commands. Cargo uses one job. All four executable identities and all 715 producer file/directory identities are checked after the run. Raw command logs and a complete result remain available on failure. `--offline` may be supplied only when the caller has provisioned the required registry inputs.

Python verifier controls and original a46 evidence do not count as fresh CI success. The new job must run these actual Rust commands. The existing maintained workflow should replace only its Native producer job with this full715 job and preserve the other independently qualified producers.

## Qualification boundary

This is a complete source and ordinary producer qualification package. It starts no AOSP source writer, Android full build, Android runtime, VM, device install, signing operation, or host policy change. Native full-build, Android runtime, and production readiness remain false. Subsequent full-build and runtime evidence must come from their actual current executions and recovery/retirement records.
