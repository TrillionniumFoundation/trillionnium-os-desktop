# DocumentsUI / SAF acceptance, continuation r12

**Flow11 completed the scoped SAF and Files business flow, with verified cleanup.** Actual picker Save, one App write/read, provider rename, Files UI rename and open, OPEN_DOCUMENT selection, normal close/reopen persistence, and provider delete all passed. Whole-App production readiness remains **false**. `SCOPED_RESULT.json` and `DOCUMENTS_MATRIX_UPDATE.json` carry the current result; `DOCUMENTS_COMMON_GATE_REVIEW.json` identifies the remaining release work.

## Actual result and cleanup

Job `1a1ab7410f4-fc05-4e04` ran from **2026-11-05 11:24:32.884 to 11:26:26.097 UTC** and finished **succeeded / exit 0**, with complete, durable output and no timeout. Script elapsed time was 110.691 seconds. The original result is `flow11-result.json`; `FLOW11_SCOPED_REVIEW.json` selects its scope, identities and terminal evidence. `FLOW11_VERIFIED_RECEIPTS.json` derives the phase/file/task proofs from 34 byte/hash-verified saved receipts.

The fixture contained one 87-byte Unicode text file. The App performed exactly one ContentResolver write and seven content readbacks. Its content SHA-256 remained `5e8ee8b6e154ade076e1f62e1ff0bc206ae69ba41982ac1c7a048c303f0503e7` through provider rename, Files UI rename, actual VIEW delivery, picker selection and reopen. Provider deletion was followed by independent ENOENT checks for all three permitted filenames and an empty URI-grant section. Host fallback file deletion was **not** used.

Normal removal closed tasks **942, 941 and 943**, preserving the pre-existing task. Pending effects were empty. The empty owned directory was removed; the temporary package, installed as UID **10179**, was uninstalled and verified absent; its staged APK was removed. Cleanup errors were empty. R16 Main/init/epoch and the complete DocumentsUI / ExternalStorageProvider APK, UID/version and CE/DE directory identities matched before and after.

The result's `ui_actions: 23` counts control decisions, including two proven no-effect STALE_FRAME attempts. It does **not** mean 23 injected inputs. Each of those two attempts returned `action_taken:false`; only then did the controller acquire a new complete observation, verify the same owned form and file, and make a new snapshot-bound decision. The third Rename OK decision succeeded. An ACK alone never earned business credit.

## Preserved history

| Attempt | Actual boundary | Disposition |
| --- | --- | --- |
| 01 | URI-grant parser rejected the actual multi-section dump before launch. | Failed; zero UI; exact fixture/package cleanup passed. |
| 02 | Original transport admission/cancellation remained uncertain. | Durable exclusive first-entry fence retained; no claim that the job was killed. |
| 03 | Actual picker Save and 87-byte App write/read passed; old held-directory enumeration did not refresh. | Failed; task closed, file/package retained. Fresh same-inode handles independently found the correct file. |
| 04 | An identity timestamp had been rounded through JavaScript JSON. | Failed before UI; original fixture retained. |
| 05 | The original 1,200-second lease was insufficient. | Business failed; exact cleanup separately passed with zero UI. |
| 06 | Create/write/read and provider rename passed; file card had no observed long-click capability. | Failed safely; exact fixture/package/tasks cleaned. |
| 07 | Select all selected the sole file; two More nodes were present. | Failed before ambiguous input; exact cleanup passed. |
| 08 | Real toolbar containers resolved More and reached Rename; only connection-scoped accessibility window IDs differed. | Failed before text dispatch; exact cleanup passed. |
| 09 | Files UI rename passed; open reached the system Resolver, whose package `android` the helper rejected. | Original failed/pending receipt retained. Separate read-only reconciliation proved no VIEW delivery; exact cleanup passed. |
| 10 | Rename text readback passed; Rename OK snapshot validation returned STALE_FRAME with `action_taken:false`. | Failed without an unknown effect; exact cleanup passed. Cause of the digest change is not established. |
| 11 | Full scoped flow completed, including real VIEW and OPEN_DOCUMENT results, reopen and provider deletion. | Succeeded; all owned test state clean. |

No historical failed result is rewritten as success. `FLOW09_RECONCILED_CLEANUP.json` separates original09 uncertainty from the later zero-UI cleanup. Flow03 evidence does not claim FUSE data loss. Raw JSON is saved as UTF-8 bytes and parsed with Python integers; public nanoseconds use decimal strings. The original02 entry fence remains in place.

## Exact package and build pins

| Package | UID / versionCode | APK SHA-256 |
| --- | --- | --- |
| com.android.documentsui | 10022 / 37 | 757feffc32440dd371eaab4fb91f45273a621ee45b848e2dc734b386ac6e2086 |
| com.android.externalstorage | 10024 / 37 | 50d1e6f2be950e049cdc898dd812c8e609f421cc167013d4ee2c795dcdc0e5ea |

The independent 45-App audit verified this same DocumentsUI APK's v3 signature: certificate SHA-256 `c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8`. Its audit collected no running engine mappings; absent embedded native libraries alone do not qualify that gate.

`harness02/` is the complete temporary client source. Build02 job `1a1aaf03182-fc05-48dd` succeeded with 15 Java classes and all 11 build/verification steps; `BUILD_PROVENANCE.json` preserves the exact receipts and dependencies. The 16,588-byte APK SHA-256 is `3b2b8d01b551f68256a25c351b34f2a6c74f74cbfc9b44b226ea708dba9fffe6`, certificate SHA-256 `f772d334443bb5cd71abcc179d04e21ee3e70d424290df69828b94e42bc448f2`. Build limits were one CPU / 512 MiB, peak 345,993,216 bytes, no OOM.

The test-only client requests no permissions and has no launcher, service, receiver, provider or native library. Its single Activity accepts VIEW only for the exact final fixture URI. It is excluded from the tracked 45 Apps. Installation requires prior global package absence and actual `pm install -R -t --user 0`; retained device help proves that `-R` forbids replacement. Each fresh trial has a new request/output directory, installation identity and exclusive empty-directory birth. The same verified APK was reused only after confirmed prior cleanup.

## Source fixes and limits

Current successful sources are `run_saf11.py`, `ui_adapter03.py` and `stage_run11.py`. The patch chain retains three distinct observer fixes: exclude only valid connection-scoped accessibility IDs from cross-dump node equality; admit the exact UID1000 system Resolver only after an acknowledged owned Files open in the adopted task; allow at most two new full observations after explicit no-effect snapshot rejection. All pointer frame/scope/context checks, task ownership and native readback requirements remain.

The flow is bounded to 720 seconds / 36 decisions, takes the shared UI lock and uses the frozen b227 held-session transport. Host setup creates only an empty exclusive directory, earning no App creation credit. Reads and writes are restricted to the exact generated URI and payload. Unknown inputs or package/provider mutations preserve their inputs for reconciliation. Normal close sends one remove, followed by bounded read-only convergence.

This result covers **one generated text file in the primary ExternalStorageProvider**. It proves provider delete, not Files UI delete, and normal task close/reopen, not process death or reboot. Copy/move, multiple files, tree grants, archives, removable/remote providers and complete error paths remain unqualified. The actual manifest declares GET_CONTENT, OPEN_DOCUMENT_TREE, Downloads and archive routes, and a separate file-operation service; the release checklist must resolve those supported paths rather than treating one successful flow as the whole App.

## Publication and regression evidence

`CHECKPOINT7_DELTA_MANIFEST.json` selects the additions/replacements after checkpoint6 commit `7f0fb48da7566b37c2bf8f12b8134898a798594c`. It references the existing original01 source, harness/build provenance, retained01–09 results and earlier patch chain without repeating them. The immutable `publication-through08/` snapshot is unchanged. Full environment/PackageManager dumps, raw full UI trees/PNGs, repeated intermediate runners, encoded launch requests and signing material remain excluded.

The saved local regressions exercise real controller methods: six connection-ID cases, seven exact Resolver cases, and six no-effect fresh-decision cases. They preserve negative controls for foreign task/UID/activity, semantic or geometry changes, unknown outcomes, and the maximum decision count. These tests verify the tool fixes; only actual11 qualifies the App business scope. No additional optional Docs UI trial is scheduled.
