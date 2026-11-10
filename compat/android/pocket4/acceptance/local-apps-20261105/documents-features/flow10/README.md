# Documents features flow10: all twelve scoped checks completed

The original durable worker `1a1ad53b421-fc05-5972` succeeded with exit 0, complete and durable output, no stderr and no timeout. The exact 27,623-byte result is retained with SHA256 `59860aba0b6e576b271566c92133e2233a1d3f14383a6183b1536c9198720853`. The session ran from **2026-11-05 20:08:30.798913 to 20:14:00.941483 UTC**, with 58 counted UI actions.

## Actual business coverage

All twelve declared checks passed. The first six reconfirmed GET_CONTENT cancellation, tree-picker cancellation, a single exact owned tree grant, Files UI new-folder creation, copying two generated files and moving both original files. The remaining six now have actual evidence: Files UI deletion of the two copies, content verification after normal close/reopen, denial of an existing URI after releasing its tree grant and reopening, GET_CONTENT selection and exact content readback with no prior tree grant, final Files UI deletion of the four remaining owned entries, and an empty final URI-grant section.

The two generated payloads are 59 and 118 bytes. Their complete hashes and the physical file identities are in the original result. The helper created the initial fixtures through the granted provider contract; that setup receives no Files UI-create credit. Files itself created the destination directory, selected the two documents, copied them, moved them and deleted them. The successful deletion gates require the selected files to be physically absent and the remaining owned contents to match their full hashes. Host fallback file unlinks were **zero**.

The flow09 failure was an acceptance-script mismatch with the real confirmation dialog. Flow10 changes only that confirmation branch: the actual Appcompat title is `Delete forever?`, the positive button is `OK`, and the message must specify exactly the selected count. The completed host-only export preserves both real dialogs, including **two items** for the first deletion and **four items** for the final deletion. Both confirmation inputs were sent once. Acknowledgements alone do not supply the deletion result; the later exact filesystem readbacks do. The original flow09 failed/unknown result and its independent cleanup remain unchanged.

## Identity, lifecycle and cleanup

The saved before/after records independently match DocumentsUI UID 10022 / version 37 / APK `757feffc32440dd371eaab4fb91f45273a621ee45b848e2dc734b386ac6e2086`, and ExternalStorageProvider UID 10024 / version 37 / APK `50d1e6f2be950e049cdc898dd812c8e609f421cc167013d4ee2c795dcdc0e5ea`. Their permission states also match. The exact raw selected records and their original per-record hashes are included; the export invoked no Main or Android commands.

Three native helper launches and two source-bound Files tasks resulted in five normal task removals: 983, 982, 984, 986 and 985. Only original Home task 851 remained. UI, helper, file-operation, install and uninstall pending states were empty, and outcome_unknown was false. The temporary helper UID 10193, its CE/DE data, all URI grants, staged APK, generated files, two child directories and owned root were removed. The runtime sampler was joined, and the original strict b227/7e49 Main identity matched before and after. Calendar Core13 received the UI window only after the full terminal and cleanup evidence was checked.

## Limits and preserved history

This is a completed, bounded feature session, not a whole-App production-ready verdict. Search and sort remain deferred; name-conflict behavior was not tested. The negative path here is an actual SecurityException for a still-existing file after revocation, checked before any new GET_CONTENT grant could mask the denial.

The sampler observed the DocumentsUI activity process, its file-operation service and ExternalStorageProvider over 633 samples and five process generations. It recorded bounded resources and no sampler errors. The original stable_complete_mapping_samples remains zero; complete executable/JIT/engine qualification and long-duration stability are not granted. No new crash or ANR was observed in the bounded diagnostics, while incomplete historical exit/log retention remains explicitly recorded.

SCOPED_GATE_RESULTS10 is additive to the earlier Documents11 IO/persistence/lifecycle evidence. It does not erase failed attempts, create a global unpassed cutoff, or include the temporary helper in the 45-launcher denominator. Prepared source-review documents are named PREPARED_* to distinguish pre-execution statements from the actual result. No default-picker screenshot, full maps, raw PackageManager dump, request/base64 payload or user document content is included.
