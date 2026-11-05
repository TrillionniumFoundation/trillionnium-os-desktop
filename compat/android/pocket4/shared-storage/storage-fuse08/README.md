# Pocket4 shared storage recovery and session lifecycle fix

## Verified result

Shared storage was restored in the existing Main instance. Exactly one normal StorageManager unmount and one mount of `emulated;0` were issued. Later checks were read-only; the failed automated qualification did not cause a repeated mount.

The retirement barrier was observed twice: all 66 inspected Main mount namespaces had lost the old emulated FUSE views, connection 158 was absent from fusectl, and MediaProvider had no serving FUSE descriptors or session threads. The next mount created a serving MediaProvider session, with three FUSE descriptors and new session threads. Forty-two retained observations showed that session serving the mounted volume.

At 2026-11-05 07:47:31 UTC, direct directory opens, `stat`, and `statfs` succeeded for both `/storage/emulated/0` and `/sdcard`. The Pictures directory also existed and passed `stat`. The filesystem reported FUSE magic `65735546`, 4096-byte blocks, and 3,750,260 available blocks. Main identity, the existing task set, and lower directory metadata matched the pre-operation records. This verifies shared-storage readability. App-level save and reopen acceptance is a separate result.

`recovery-summary.json` contains the narrow public outcome. Raw action journals, complete process metadata, and private observations remain outside this bundle. There are no user photos, screenshots, filenames from user collections, or file contents here.

## Qualification errors retained

The first recovery runner stopped before either volume operation because a terminal process retained its `/proc` entry after losing its mount namespace. The next runner distinguished the observed terminal state from a live unreadable process and performed the one unmount/mount sequence.

That runner still returned `NEW_FUSE_SESSION_NOT_READY_NO_RETRY`: it incorrectly required the new numerical device identifier to differ. The kernel reused identifier 158 after the old connection had fully disappeared. The subsequent read-only reconciliation uses the observed retirement, fresh session startup, serving descriptors, and successful path I/O. The original failed result is retained rather than changed to success.

A separate path probe opened the directory but incorrectly assumed that its temporary shell descriptor would be inherited by `stat`. Another read-only probe was rejected by the transport's command-label grammar before its first path command. The final probe used valid labels and directly addressed each mounted path; all required commands succeeded.

The existing terminal process was independently observed after recovery with the same birth, state `Z`, one thread according to both `stat` and `status`, and one task entry. This is an **after-only observation**, not retroactive proof of the earlier scan's thread count.

## Minimal source fix

`0001-storage-await-single-session-removal.patch` changes only `StorageSessionController.onVolumeUnmount()`.

The original method invokes `onVolumeRemove()`, which removes the framework session, and then calls `removeSessionAndWait()`. The latter attempts another removal, finds nothing, and returns without sending `endSession()` or waiting for the old daemon to exit. The patch fetches the existing connection without removing the session, then delegates the sole removal and wait to `removeSessionAndWait()`.

The patch preserves supported-volume/reset filtering, clone-profile connection mapping, Binder identity restoration, lock release before waiting, and unrelated sessions. `ExternalStorageService` defines repeated starts of an already starting or started session as having no effect; this patch preserves that contract. It does not change MediaProvider duplicate-session behavior.

The controlled device log contains the same removal sequence followed by `No session found for id: emulated;0`; the selected metadata events are retained in `runtime-lifecycle-events.json`. This establishes that the missing-wait behavior occurs in the installed runtime. It does **not** establish that this race caused the initial disconnected FUSE instance: the earlier failing transition is not available.

The patch has not been built into a complete Android framework or installed in Main. Its exact upstream preimages are listed in `source-pins.json`; all five complete classes were retrieved from the official AOSP mirror and verified against the stated Git blobs.

## Regression evidence

The host regression compiles production Java method bodies extracted verbatim from those full classes. It follows the real controller, `StorageUserConnection` future handling, `ExternalStorageService` callback wrapper, MediaProvider session methods, and `FuseDaemon` Java thread start/run/join code. Android context/Binder transport and the native FUSE loop are boundary substitutes.

The candidate passed all nine cases. The original methods failed the two intended negative controls: no end-session call/wait, and a rapid remount whose new device descriptor was not consumed. Seven compatibility cases passed on both versions, covering repeated starts, the separate non-waiting removal API, other sessions, unsupported/reset volumes, absent connections, error handling/identity restoration, and clone-profile mapping.

This is method-level lifecycle evidence, not a kernel FUSE test or a complete framework build. `regression-summary.json` retains the exact observed exit-code matrix. A clean patch application also produced byte-for-byte the reviewed candidate source. `evidence-digests.json` identifies the retained detailed receipts without including their private contents.

## Primary source locations

- [StorageSessionController.java](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/services/core/java/com/android/server/storage/StorageSessionController.java)
- [StorageUserConnection.java](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/services/core/java/com/android/server/storage/StorageUserConnection.java)
- [ExternalStorageService.java](https://android.googlesource.com/platform/frameworks/base/+/master/core/java/android/service/storage/ExternalStorageService.java)
- [ExternalStorageServiceImpl.java](https://android.googlesource.com/platform/packages/providers/MediaProvider/+/refs/heads/main/src/com/android/providers/media/fuse/ExternalStorageServiceImpl.java)
- [FuseDaemon.java](https://android.googlesource.com/platform/packages/providers/MediaProvider/+/refs/heads/main/src/com/android/providers/media/fuse/FuseDaemon.java)

## Installed framework identity and the Android 17 source variant

A later held-Main read on 2026-11-05 confirmed that the running `framework.jar` is byte-for-byte identical to the m692 base image, while `services.jar` is a separate Wi-Fi API fix override. Its SHA-256 is `f33987e633e476f47ea043af3f7fb94907fd2431fa2b5b49df84cb586bce5c50` (34,542,267 bytes). The exact override mapping was confirmed through the held Main root, mount metadata and matching file device/inode. No raw mount/proc inventory or host source-directory listing is included here.

The installed DEX method table references `onVolumeUnmount(ImmutableVolumeInfo)`, whereas the earlier main-branch reference patch uses `VolumeInfo`. The m600 manifest and actual Git HEAD pin frameworks/base to `94b4c163b7dfe5ce3607f7bb8456f9573f7de57d`; full source files fetched at that pin contain the same double-removal defect and the matching `ImmutableVolumeInfo` interface. **This source pin has not yet been proved to be the Java source commit of the installed override.** Its exact files, hashes, source URLs and limitations are recorded in `source-runtime-provenance.json`.

`0001-storage-await-single-session-removal-immutable.patch` is an alternative against that locked Android 17 source, not a second sequential patch after the main reference patch. It changes only `onVolumeUnmount`. A clean application to the exact preimage produced the recorded complete candidate class. The existing nine-case regression remains qualified only for the main reference variant described above. The new variant has not been deployed or fully compiled against a verified real compiler classpath.

The inspected m692 runtime JARs contain DEX rather than JVM `.class` files. The genuine system SDK contains 8,537 classes, but it lacks required platform/internal dependencies including `IVold`, `VolumeInfo`, `StorageUserConnection` and `ImmutableVolumeInfo`. No hand-written internal stubs are being substituted to claim a full class build. The retained Wi-Fi installation receipt proves the known JAR hash chain only through a ZIP-alignment change; it does not close the Java source/classpath provenance gap. This source investigation does not change the independently verified storage restoration result.

## Packaged reproduction

The delivered reference driver was rerun from this bundle. `validation/results/result.json` records that separate local reproduction with relocated invocation paths; both expected original failures and all nine candidate results matched. `validation/retained-original-result.json` preserves the original run. Extracted production methods, the harness template and complete pinned inputs are included. Generated class files and disposable build trees are excluded. This second run performs zero device actions and adds no full-framework or Android-runtime qualification.
