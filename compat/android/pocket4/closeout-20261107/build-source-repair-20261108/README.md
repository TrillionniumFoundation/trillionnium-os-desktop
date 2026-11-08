# Pocket4 Android build source repair

**State: `BUILD_SOURCE_REPAIR_IN_PROGRESS_NOT_DEPLOYED`.** The common source snapshot and native capacity/recipe repair are reconstructable and their focused checks passed. Audio is included only through its immutable `fc90abf` prerequisite. The final audio repair and complete native/ART and audio APEX builds remain pending. Final deployment and original whole-application acceptance remain **false and 0/45**.

## Why this package is needed

The native builder rejected the original CTS source selection because it contains 279 sparse cones while the reader allowed only 256. Earlier companion patches also depended on local builder inputs that could not be fetched from the public upstream by their cited commit. This package supplies the exact retained text inputs and separates reconstruction from runtime qualification.

## Contents

- [Source prerequisites](source-prerequisites/README.md): a 385-file text base plus separate native and audio prerequisite patches. The base preserves the Cargo workspace, Cargo.lock and licenses; it excludes operator data, Git metadata and a documentation screenshot. Native and audio chains each start from an empty directory.
- [Native sparse capacity and frozen recipe](native-sparse-capacity/README.md): the final three-file repair, full source inventory and compact results for 25 library, 6 recipe and 11 generated-pair checks. The generated-pair tests use their separately recorded source hashes.
- [Audio status](audio-source-projection/README.md): exact `fc90abf` inputs only. No unfinished provider repair or intermediate 18-test result is promoted into this package.
- [Current continuation](../continuation/state.json) and [attempt 12 reconciliation](../continuation/native-attempt12-reconciliation.json): the actual failed Soong outcome, completed retirement observations and remaining gates.

## Verification and limits

New isolated directories on Pocket4 and Mac independently replayed the patches and compared every retained file's bytes and executable mode: 385 common-base files, 444 native prerequisite files, 446 native final files and 395 audio prerequisite files. This proves source reconstruction, including the inputs actually used for the native candidate.

The native focused controls passed with no Soong invocation and no active builder/source-lock mutation. The first recipe replay failure is retained in the result summary. Native attempt 12 remains FAILED because Soong could not resolve `PermissionUtils`; its authoritative process outcome and cleanup were reconciled, without converting failure into success or inventing continuous absence proof.

AOSP projects must still be obtained from their pinned source locks, and Cargo dependencies from Cargo.lock. The repository's existing A08 source-integrity gate checks source presence and syntax; it does not replace the actual Rust controls or establish Android acceptance. Complete native/ART and audio APEX builds, coherent installation, a fresh runtime generation and original application acceptance are still required.

Previous public failure and unknown observations are preserved byte-for-byte in [continuation history](../continuation/history/state-20261107-093339.json). Private runtime identities, device/account data, raw private logs and application user data are not included.
