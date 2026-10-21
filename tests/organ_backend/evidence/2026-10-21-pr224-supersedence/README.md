# PR #224 source preservation review

This packet compares PR #224 head `49e5582db15493eed60d62fb16b4c85fc7408307` (tree `62ec286c44deb7b37001dd091e9adce3caef9186`) with merged main `22a3284a14069f79c784e6bf33bb3c6035b9765f` (tree `4f2fe03e4a7847e9ef3273dac4474a6691da7db4`). It records source preservation; it does not qualify native execution or replace a failed result.

All 59 paths in the original PR were compared by Git blob identity and mode. Forty-eight are identical. Each of the eleven changed paths is explained in `source-equivalence-reviewed.json`; the full-tree comparison has twelve changed paths because main also corrects the G1-d documentation's test denominator. Both complete trees have 7,531 tracked blobs, with 7,519 identical blob-and-mode entries. Root reviewed the complete textual difference and the independent reviewer's mapping.

Main retains the original permission transactions, G1-c/G1-d declarations, ExFAT inode correction, frozen negative patches, full core minimum of 262 and all 24 required names, and the permission SMP denominator of 265. Its credential observer has a stronger bounded, EINTR-aware single-write implementation; its formatter exception is narrower. The SeaBIOS framing regression is present through #227. Existing #230 separately restores real-child formatter coverage. Those changes must be preserved rather than replaced by the older candidate.

The only executable assertion unique to #224 is the explicit check that the generated G1-d feature forwards to `aster-core/g1d-trusted-control`. This follow-up restores those two lines without changing the feature generator, production source, frozen controls, test denominator, or any original assertion. The follow-up descends from #231 head `17afb302cd351b116830e61b97bb34da3daa0d2b`, which adds running-kernel ExFAT module preparation without altering the original native oracle.

## Actual host validation

The original `TestBaseManifest` class executed two tests under `python -I -B` and the same two under `python -I -B -O`. Both runs passed. The class reads the actual fixed source manifests and the original manifest generator; no manifest or generator mock was supplied. All nine materialized source inputs matched their Git blob identities before the two-line edit. This was Python host validation in the available isolated environment; it did not compile or run a kernel, mount ExFAT, or qualify a physical device.

## Native qualification remains separate

Main 22a's original A06 run `39590054181`, job `119188464418`, failed its Linux ExFAT mount with errno 19 before observations. Its guest and frozen old-mode control did not execute. Earlier #225/#227 successes on another hosted kernel remain historical results. #231's complete original A06 run and this descendant's original required checks must finish on their own exact inputs before their respective native blockers can be closed. Closing the stale #224 as superseded is not a statement that these remaining native gates have passed.

No ABI, authorization, persistence, device attachment, or production enablement changes are introduced by this follow-up.

