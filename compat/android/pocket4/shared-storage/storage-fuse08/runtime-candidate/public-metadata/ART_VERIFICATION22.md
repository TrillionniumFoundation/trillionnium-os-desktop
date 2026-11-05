# Installed ART verification of the storage candidate

The exact installed ART tools have verified the candidate `StorageSessionController` class containing `onVolumeUnmount(ImmutableVolumeInfo)`. The stored class status is **Verified** and the compilation kind is **NoneCompiled**, as expected for `--compiler-filter=verify`. The candidate has not been installed into Main or exercised through a live volume lifecycle.

This document extends the earlier build/alignment checkpoint. The earlier `README.md`, `offline-candidate.json` and `source-manifest.json` remain historical snapshots; their then-pending ART gate is resolved only to the scope recorded here.

## Actual execution and preserved failure

| Stage | Actual outcome | Meaning |
| --- | --- | --- |
| ART20 | Original compiler and target dump exited 0; wrapper exited 2 with `TARGET_DUMP_NOT_BOUNDED` | The observer matched 938 keyword rows and exceeded its own 128-row limit. No candidate ran. This result remains unchanged. |
| ART21 | Read-only reconciliation exited 0 | Rehashed the existing original outputs, selected the exact outer class and method, and confirmed stored `Verified` status without rerunning ART. |
| ART22 | Candidate-only run exited 0, 2026-11-05 10:48:11–10:48:13 UTC | Reused the pinned original baseline; candidate compiler and target dump completed, joined, and reported the exact target `Verified`. |

The exact target is `Lcom/android/server/storage/StorageSessionController;`, method `void com.android.server.storage.StorageSessionController.onVolumeUnmount(com.android.server.storage.ImmutableVolumeInfo)`. Candidate DEX output contains the reviewed connection lookup under `mLock`, followed by one `removeSessionAndWait` call after leaving the lock. The original `onVolumeRemove` call is absent. This complements the prior comparison of 7,582 classes and 53,839 methods, where only this method changed.

## Input and resource controls

Both inputs use the actual installed ART tools, fixed Main epoch, actual 52-file boot classpath, selected 87-file guest dependency closure, boot image and provider class-loader context. Candidate fresh inputs matched the retained original snapshot, and selected input, boot, APEX, ART and classpath hashes were unchanged afterward. Descriptor identities were checked through the same held-namespace command chain. Only held descriptor numbers and owned output basenames are normalized when comparing commands. Hard and soft verifier errors both abort.

The candidate used a separate unit limited to 2 GiB memory, zero swap, CPUs 20 and 21, two compiler threads, and bounded subprocess/unit lifetimes. Its measured memory peak was 389,500,928 bytes; all recorded memory events, including OOM and OOM-kill, were zero. Original peak was 339,910,656 bytes. Only new owned OAT/VDEX outputs were supplied as writable descriptors; no Main installation, restart, UI action or volume action was requested.

## Warning and observation limits

Both actual ART logs retain the inferred boot-extension checksum warning: `boot-framework-adservices.oat` expected `framework-wifi.jar` checksum `0xd5474ab8`, while the actual JAR checksum was `0x5fde5b38`. Oatdump reported failure to verify that inferred image, then continued dumping with a runtime and exited 0. The complete logs are retained. This target verification does not qualify the entire boot image. The boot, tool and flags were not changed to hide the warning. Worker priority warnings and the embedded command-line-length diagnostic are also preserved; the complete actual argv is retained separately.

ART20 did not collect a runtime-cache census. Its `installed_runtime_writes=false` field described requested command scope and is not evidence of zero writes. ART21 records this correction separately without editing the original result. ART22 added before/after metadata observations for `/data/dalvik-cache` and `/data/misc/apexdata/com.android.art/dalvik-cache`, including observed root existence. No persistent metadata delta was observed in that limited scope. This is not a trace of transient writes or all runtime caches and cannot establish retrospective facts about ART20.

The remaining gates are a separately reviewed runtime deployment and actual lifecycle validation. This is an exact installed-DEX candidate, not a complete Java/AOSP clean build or a whole-App production-readiness result.

## Reviewable evidence

`art-verification22.json` records selected source/input/output hashes, terminal job receipts, exact target status, resource observations, warning details and limits. `art22-source-manifest.json` pins the new summaries, frozen runners, parser regression and existing target evidence. Raw environments, complete process maps, cache filenames, bytecode/JAR binaries and private journals are excluded from this public projection.
