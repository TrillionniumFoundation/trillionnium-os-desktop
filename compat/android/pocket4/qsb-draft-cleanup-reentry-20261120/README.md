# QSB draft cleanup reentry source repair

The unadopted QSB controller draft writes one exclusive `phase-cleanup.json`
journal when it enters cleanup. Its existing reopen path returns to the original
business deadline and permits the second bounded native launch. A later cleanup
then attempts to create the same journal again and fails with `FileExistsError`.

This capsule changes only the journal name in `Session.begin_cleanup` to include
the existing `native_launches` value. The first and second launch cycles retain
separate `phase-cleanup-1.json` and `phase-cleanup-2.json` receipts. Reentering the
same cycle still fails exclusive creation; no old receipt is overwritten. The
two-launch limit, 600-second business deadline, original absolute 720-second
cleanup deadline, pending-action checks and retirement conditions are unchanged.

`preimage/qsb_runtime.py` preserves the exact local draft, and
`source/qsb_runtime.py` is the one-line postimage. `MANIFEST.json` identifies both
complete byte sequences, the original snapshot and the source-only boundary.
These contextual files do not imply that the complete controller implementation
has been reviewed or integrated. The original review scope remains in
`ORIGINAL-DRAFT-REVIEW-SCOPE.json`: the complete executable entry/orchestration,
the scoped offline/error fixture and actual runtime business evidence remain
outstanding.

The five regression controls execute the real draft `record`, `begin_cleanup`
and `reopen_business` methods against a temporary directory and the original
exclusive file writer. That writer is read from the existing published
`current-canonical-app-main-20261120/bundle/source/shared/app_common.py` after its
complete SHA256 is checked. The four helper bodies used by the test match the
draft helpers exactly. The test models the clock and launch counter explicitly;
it does not construct a live Session or invoke Main, release/resource admission,
host commands, Android transport or a VM.

The independent `pocket4-qsb-cleanup-source.yml` workflow verifies the external
`FILES.sha256` digest and every listed member before running the controls as an
ordinary runner user. Temporary journals and the result go to `RUNNER_TEMP`,
outside this immutable capsule. No saved local result is presented as a GitHub
run. A fresh workflow result is required after publication.

This addition leaves the current 2391-file Rust producer, canonical 14 selection,
adoption records, A08 workflow and publisher inputs unchanged. The draft remains
unadopted. QSB application acceptance, runtime qualification and production
readiness remain false until their original prerequisites are completed.
