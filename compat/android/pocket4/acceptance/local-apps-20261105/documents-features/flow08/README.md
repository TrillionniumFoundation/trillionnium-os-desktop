# Documents features flow08 actual increment

Flow08 ran from 2026-11-05 18:18:31.055 to 18:21:06.870 UTC on the same Main epoch under the original b227/7e49 resource profile. Its durable worker exited 1 with complete stdout and no timeout. The original failure is retained.

Five scoped checks passed: GET_CONTENT cancellation without a returned URI, tree-picker cancellation, an exact owned read/write tree grant, a new folder created through Files UI, and copying two selected files through Files UI. The 59-byte and 118-byte copies were independently read through the held fresh directory and matched the complete source hashes. No copy operation was replayed. This adds actual multiple-copy coverage to the prior evidence.

The next operation stopped with `ControlError: STALE_FRAME`. Its exact saved call site is under separate review; this packet does not classify it as an App crash or infer a successful move or delete. Thirty actions were recorded. The source bound tasks 971 and 972 were each normally removed; final tasks returned to the original 851. All UI, helper and file-effect pending sets are empty, and both install/uninstall pending flags are false.

Cleanup removed exactly the four owned files through the guarded host fallback, then the owned directories, temporary helper and CE/DE data, and staged APK. No original file contents were written by the host. These cleanup deletes receive no Gallery/Files UI-delete credit. Cleanup had no errors, the runtime reader joined, and the Main identity was unchanged.

The active runtime sampler saw DocumentsUI, ExternalStorageProvider and, during the actual copy, `com.android.documentsui:com.android.documentsui.services`. Its bounded resource observations are retained. Complete executable mapping/engine qualification, long-duration stability and full log-history exclusion remain pending; zero newly observed crash/ANR events is scoped to this run.

The source delta contains only the already reviewed destination navigation and the original-profile rebinding. The full runner is current; the five dependency hashes remain those in SOURCE_MANIFEST and the previous packet. No request base64, complete maps, raw PackageManager dump, default-picker screenshot or foreign filename is included.

SCOPED_GATE_RESULTS08 is additive. It must not replace the earlier Documents11 IO/persistence/lifecycle passes, erase the original failed runs, or mark the whole App production-ready.
