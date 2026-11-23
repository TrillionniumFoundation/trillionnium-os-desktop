# QSB search case and cleanup controls

The current source exposes `qsb_runtime.execute(c, base_ref, parts, release, resources, source_guard, action_lock)` for a native caller holding the admitted release and original Main resources. The case uses the existing session to enter two public queries and clear the search field, open one observed result, return to the preserved query, close the owned tasks, and read back the blank field after reopening. The terminal record follows host-context retirement and a fresh check of the plan, release, resources, action lock and observations. The scoped offline/error fixture, canonical selector integration and real Android business evidence are outstanding.

The thirteen host controls in `test_search_case.py` exercise the entry, business sequence, launch evidence, cleanup decisions and failure boundaries using modeled device responses.

## Original cleanup repair

The original QSB controller wrote one exclusive `phase-cleanup.json`
journal when it enters cleanup. Its existing reopen path returns to the original
business deadline and permits the second bounded native launch. A later cleanup
then attempts to create the same journal again and fails with `FileExistsError`.

The original cleanup repair changed only the journal name in `Session.begin_cleanup` to include
the existing `native_launches` value. The first and second launch cycles retain
separate `phase-cleanup-1.json` and `phase-cleanup-2.json` receipts. Reentering the
same cycle still fails exclusive creation; no old receipt is overwritten. The
two-launch limit, 600-second business deadline, original absolute 720-second
cleanup deadline, pending-action checks and retirement conditions are unchanged.

`preimage/qsb_runtime.py` preserves the exact local draft, and
the single-line cleanup postimage is reproducible from it using `QSB-CLEANUP.patch`. `source/qsb_runtime.py` is the current business successor. `MANIFEST.json` identifies the historical and current
complete byte sequences, the original snapshot and the source-only boundary.
`ORIGINAL-DRAFT-REVIEW-SCOPE.json` retains the scope of the original review.
The native caller still needs the complete source-bound provider set before
it can invoke the current case on Android.

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

The original cleanup repair left its 2,391-file Rust producer, canonical 14 selection,
adoption records, A08 workflow and publisher inputs unchanged. The draft remains
unadopted. QSB application acceptance, runtime qualification and production
readiness remain false until their original prerequisites are completed.
