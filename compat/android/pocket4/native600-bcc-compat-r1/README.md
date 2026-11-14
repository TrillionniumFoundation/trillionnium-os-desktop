# Native600: restore the original bcc_compat provider

The actual Native r8 build stopped because `deprecated-renderscript-tools`
depends on `bcc_compat`, whose complete source cone was absent from the sparse
selection. This patch adds `tools/bcc_compat` at the already pinned libbcc
commit, with its original Blueprint and implementation together. It updates the
normal recipe's exact lock identity and the historical failure regressions.

Apply `native600-bcc-compat.patch` only to baseline
`fa3fa7496d9dd79a02bcd1445b1c49888aa493c4`, whose tree is
`95b5934af46dc560be0559d0b5b9edccc6133867`. The independently qualified
candidate commit is `68a334c93b4b42846cd2fe2ef23e46c7021149c0`.

## Validation actually performed

All 28 `ordinary_pair` tests passed, including the regression that reconstructs
the exact r8 lock and rejects its missing provider. The test also rejects a
Blueprint-only selection, an implementation-only selection, an overbroad tools
selection and a changed project revision. Both normal development tools built;
the normal source tool verified 600 exact AOSP projects and eight root links.
The target pair and strict missing-dependency policy are unchanged.

`qualification.json` binds the preimage and resulting source bytes, original
upstream Git blobs, actual command outcomes and prior full-build failure. It
preserves the initial dependency-index and temporary-space failures, and the
later commit-identity error after a successful normal tool build. The passing
tests used the candidate's own temporary directory without deleting unrelated
host files. Build binaries, APKs and local raw journals are not included here.

## Integration and acceptance

The active coordinator still owns the shared AOSP source and its three existing
lock inodes. It must admit this candidate, perform normal source reconciliation
and verify the materialized originals before a fresh full build. No shared
source was reconciled by this patch qualification, and no full Native build or
Android runtime acceptance is claimed.

Native600 already contains the full SDK36 cone. The separate Audio430 failure
on the two system-server ondeviceintelligence API providers does not require a
duplicate SDK selection change in this Native candidate.

Production readiness and complete application acceptance remain false.
The CI inventory check for this capsule verifies publication integrity only;
the actual source tests and normal tool results are the bound host evidence.
