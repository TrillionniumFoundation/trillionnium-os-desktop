# Pocket4 Android build source repair

**State: `BUILD_SOURCE_REPAIR_IN_PROGRESS_NOT_DEPLOYED`.** The self-contained text base, exact Native and Audio source branches, and their separate combined builder are reconstructable. The combined builder passed its focused Rust controls and normal tool builds. Native 597-project materialization is still pending; the actual Audio full host-r1 build failed at the undefined `junit-params` provider required by `icu4j-tests`. No complete Audio APEX was produced. The minimal original-provider repair now pins 309 projects and passes 13 library checks, two focused regressions, both normal tool builds and an independent Mac source replay. Its source migration and full APEX build remain pending. Full Native/ART and Audio qualification, deployment and runtime acceptance remain pending; whole-application acceptance remains **0/45**.

## Why this package is needed

The native builder originally rejected the CTS selection of 279 sparse cones because its reader allowed only 256. Earlier patches also referred to local builder bases that were not publicly fetchable by their cited commit. This package supplies the retained text build inputs and the precise source chains. The latest integration combines the real Native 597-project/fix18 source and Audio 308-project/provider source without changing their frozen full-build inputs.

## Contents

- [Source prerequisites](source-prerequisites/README.md): the original 385-file text base and separate native/audio prerequisite chains. Cargo.lock and licenses are retained; operator data and Git metadata are excluded.
- [Native sparse capacity and frozen recipe](native-sparse-capacity/README.md): the earlier three-file repair and its original 25 library, 6 recipe and 11 separately generated-pair checks. This historical package and its source identities are unchanged.
- [Integrated builder](integrated-builder/README.md): independent replay chains for 450 frozen Native files, 409 frozen Audio files and 476 combined builder files. The new combined controls cover 29 source-library tests, 6 recipe tests, an actual 597-source render, 58 distinct updater tests and both normal release tools. The real recipe failure and its subsequent historical-fixture repair are retained.
- [Audio prerequisite history](audio-source-projection/README.md): the original `fc90abf` prerequisite record. The new published Audio source candidate is identified separately in the integrated package; the Audio 309 repair has its own exact source and focused results, with full build qualification still pending.
- [Current continuation](../continuation/state.json), [current build observations](integrated-builder/build-observations.json) and [attempt 12 reconciliation](../continuation/native-attempt12-reconciliation.json): actual pending/failed outcomes, exact terminal hashes and the remaining gates.

## Verification and limits

Pocket4 and Mac independently replayed each new chain and compared all retained bytes and executable modes. Both original locks are preserved, with a combined project bound of 608 and a bounded 288 sparse paths. Shared route selection keeps Native strict-provider handling and Audio-only projections separate. These source checks do not establish full AOSP build or Android runtime success.

The combined source controls made no AOSP, Soong, Android or Main invocation. Their owned unit and children fully retired with no source drift. Earlier failures remain in the original files and continuation history, including Native attempt 12's real `PermissionUtils` failure and the newer Audio `icu4j-tests`/`junit-params` failure. Cleanup observations never turn a failed build into a success.

AOSP projects still come from their exact source locks, and Cargo dependencies from Cargo.lock. A08 source integrity verifies repository source presence and syntax. Complete build artifacts, payload qualification, coherent installation, a fresh runtime generation and all original application gates remain necessary. Private runtime identities, account/device data, raw private logs and application user data are excluded.
