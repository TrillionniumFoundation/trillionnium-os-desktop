# Native cloud evidence — final

This frozen phase retains exact command/controller logs, results, serial streams, source bindings and separately deduplicated actual input bytes. Runtime source: `d879a9d2ffae8d0eb0df441370da54f9e3a38431`; derived kernel tree: `6b3cab110aa6d30d5b89f99c4389c9c3e01022da`; fixed toolchain: `nightly-2026-07-21`.

Source S full matrix: **22/22 passed, 0 failed, 0 blocked, 1 VMX soft skip; 11 raw-33/wrapper-33 guests**. All 23 private input mappings (11 kernel, 11 BIOS, 1 original EM62 coverage symbol), 13 unique exact raw artifacts, are retained and verified before/after each guest. Real coverage GDB/merge/show returned 0. Pre/post source verification each checked 118 inputs with 0 errors and clean Git status. Shared compilation cache reuse is explicit; this is not a cold build.

`raw/manifest.json` binds every original regular raw-evidence member and its absolute source path/stat; ordered `raw/part-*` concatenate to a gzip tar. Compiled targets and raw guest artifact directories are excluded from that archive. `artifacts/manifest.json` independently binds every actual guest kernel/BIOS and coverage EM62 symbol to ordered lossless chunks. There are no reconstructed historical payloads.

Run `python3 -I verify.py .` and `python3 -I -O verify.py .` from this directory for full offline integrity, gzip/raw hashes and result denominators. To reconstruct one original input into a **new** directory: `python3 -I artifacts/reassemble.py artifacts/manifest.json RAW_SHA NEW_DIRECTORY`. It fails on any part/whole/decompressed identity difference. Every published file is at most 2 MiB.

Storage was atomically moved from unpublished local input-retention staging, leaving original capture facts unchanged; `artifacts/storage-migration.json` records custody. Full local gzip originals remain external and are optional, not required for reconstruction. Complete compiler/tool binaries and build caches are not duplicated; source Git objects and environment/command records identify them. The two observer drafts were never executed. This phase does not claim a complete desktop or full Asterinas acceptance from OSDK example tests.

`consumed-source.tar.gz` additionally exports every original runtime input enumerated in the captured environment (94 exact Git files); every digest was compared with that run. `independent-native-review.json` independently checks both historical limits and source-S final results. `reassemble-validation.json` records actual new-directory reconstruction under both Python modes.

Before first publication, the static source export list was corrected from the nonexistent `capture-coverage.py` candidate to actual `capture.py`, already retained in `consumed-source.tar.gz`. Every listed path now has an exact runtime Git blob and frozen-member binding in `source-binding.json`. Original raw archive candidate exclusions remain historical facts; no raw logs, artifact chunks or consumed-source bytes changed.
