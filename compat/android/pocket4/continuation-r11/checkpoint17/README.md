# Pocket4 Android production work — checkpoint 17

**Whole-app production readiness remains 0/45.** This checkpoint preserves repair source, actual scoped successes, original failures, and pending work. It does not authorize a release or claim that the Android apps are ready.

The primary snapshot is **2026-11-06 01:20:18 UTC**. [CUT.json](CUT.json) records the fixed boundary. A separately pinned [addendum](ADDENDUM01.json), fixed at **01:27:34 UTC**, contains BestBuy's five safe follow-up originals and Root review/cleanup, plus R7 installation admission. Later outcomes are not inferred. [status.json](status.json) carries the machine-readable current scope and exact evidence references.

## What changed

| Workstream | Actual result in this checkpoint | Qualification still open |
|---|---|---|
| Native framework | Original normal build failed at its internal 6,100-second child deadline. New source-resume builder467 compiled and passed 18 focused gates across 56 commands. A separate normal resume was admitted once. | Actual source reuse, complete framework Java implementation artifact, Android JNI object/link, and runtime remain unqualified. |
| Owner16–18 | Logging and guest bootstrap directory repair compiled; ordinary controls passed. Actual normal runtimes still failed before ACTIVE. Cleanup was independently checked. | Owner installation, service health, abort cause, and app runtime readiness remain open. |
| Bilibili | R6 attempt05 failed before the pause action because the inspected tree/window changed. R7 static build passed; installation was frozen at the primary cut and admitted in the addendum. | R7 installation/UID, pause/resume playback, and whole-app success are not established by the included admission. |
| IHG | One public Search entry click changed the selected state, with complete before/after reads and exact task retirement. | Hotel results, login, booking, and business completion were not verified. |
| BestBuy | Initial launch/read-only inspection passed. Fresh readiness attempt failed on its third complete-tree read at the helper's depth bound. | Semantic readiness and business success remain false. A complete-depth repair is still required. |
| Amazon / Ticket12306 | Both retain pre-action global-lock admission failures. | No shared lock owner or common failure cause is inferred; these attempts do not qualify app behavior. |

## Native: retain the failure and verify reuse freshly

The [original terminal](evidence/typed-framework-results-read01/decoded01/originals/attempt-01/terminal.json) records builder return code −9 and an internal 6,100-second timeout. The outer job's `timed_out=false` describes a different boundary. Its cleanup reaped 296 owned children; the [outer fence](evidence/typed-framework-results-read01/decoded01/originals/build-fences-01/terminal.json) retains its before/after Main assessment. Neither record proves a network cause or continuous non-interference. The collector's two missing records remain explicit in the [member index](evidence/typed-framework-results-read01/decoded01/member-index.json).

The [fixed staging read](evidence/typed-framework-known-staging-read03/stdout.log) observed all 214 locked project positions, including 145 matching HEAD/origin candidates. Project144 clang had already completed checkout; project146 was partial, with an empty index lock; projects147–214 were absent. These are observations, not a reuse qualification.

The [resume source](source/native/typed-source-resume-freeze03/SOURCE_PINS.json) adds explicit owned staging recovery, fresh commit/origin/sparse/clean checks for every reused project, persistent bounded progress, and the original final manifest verifier and atomic publication. It keeps the normal work/source locks, avoids force-reset/clean or global Git configuration changes, and never promotes partial state to complete. Both Git pipe readers are joined before errors propagate. Autonomous Git maintenance is disabled per command; local two-version reproduction does not retroactively identify the two historical Pocket4 child PIDs.

[Compile03's actual result](evidence/typed-builder467-source-resume-compile03/result.json) proves 56 successful commands, nine updater gates and nine source-resume gates, an actual ELF pin, and no forced or remaining owned children. It is not a Java/JNI or real staging build result. The earlier [compile02 child-gate failure](evidence/typed-builder467-source-resume-compile02/root-actual-review.json), both local binder failures, and earlier source-lock failures remain preserved.

The [normal resume request](source/native/typed-framework-normal-resume-bound01/exact-request.json) binds the real compile03 ELF/result and original failed-build/staging observations. [Root's admission review](evidence/typed-framework-normal-resume01/root-admission-review.json) and [actual admission](evidence/typed-framework-normal-resume01/admission.tool-original.json) record job `1a1ae6b5a97-fc05-5f81`. At the primary cut there is no terminal observation. Its original environment, one build job, CPU2, 10GiB memory, 1GiB own swap, fresh resource gates and Main limits remain part of the reviewed request.

## Owner: failures remain distinct from cleanup

[Owner15](evidence/owner15-normal01-runtime-read01/root-actual-failure-retirement-review.json), [Owner16](evidence/owner16-runtime-read01/root-actual-review.json), [Owner17](evidence/owner17-runtime-read01/root-actual-retirement-review.json), and [Owner18](evidence/owner18-runtime-read01/root-actual-review.json) retain failed normal runtime outcomes. Retirement success does not qualify ACTIVE or installed Owner behavior.

Owner16's bounded capture observed LMKD exec permission failures and repeated hwservicemanager aborts. The [Owner17 bootstrap change](source/android/owner17-bootstrap-mode-source-freeze01/SOURCE_PINS.json) fixes the search mode of two held, owned guest directories while preserving host private directory modes and service umask. [Compilation](evidence/owner17-host-mode-compile01/root-actual-review.json) and [ordinary controls](evidence/owner17-host-ordinary01/root-actual-review.json) passed. The actual Owner17 captured prefix had no LMKD exec permission error, but both LMKD and hwservicemanager still aborted; the cause is not resolved by that absence.

Owner18's crash-buffer reader failed at fixed generation logd ELF metadata qualification, before connecting or requesting a stream. It received zero records. The 96-byte packet-file header is not a crash record. Raw captured logs, `captured_hex` runtime payloads and binary packet bytes are excluded; the safe reviews preserve original byte/SHA pins and failure/retirement facts.

## App coverage

The [Bilibili05 review](evidence/bili-r6-first-search-foreground05-failure-read01/root-actual-review.json) preserves `INSPECTED_TREE_OR_WINDOW_CHANGED` before the pause action. Successful independent after-state checks do not turn the failed sequence's restoration flag true. Task1014 retired and baseline task851 remained. [R7's actual static build](evidence/bili-r7-static-build01/root-actual-review.json) is PASS only for the build: the [frozen install source](source/owner/android-qa-r7-install-state-01/FROZEN_FILES.json) and [post-cut admission](evidence/bili-r7-install-state01/admission.tool-original.json) do not establish the installed helper UID or playback.

[IHG's result](evidence/ihg-public-search-entry01-five-read01/root-actual-review.json) qualifies the public Search selected state: 64 nodes before, 112 after, one acknowledged click and one selected Search node. It retains the inspection's `outcome_unknown` field, and does not claim hotel results or business completion. Owned task1016 retired and task851 remained.

BestBuy's [first launch](evidence/bestbuy-launch-five-results-read01/root-actual-review.json) and [public role read](evidence/bestbuy-launch01-public-roles-read01/root-actual-review.json) observed a complete 12-node tree with all 31 fixed public-role/resource queries zero. That one tree does not identify persistent loading or the page type. The [fresh readiness source](source/native/android-bestbuy-content-readiness-01/FROZEN_FILES.json) uses at most three independent original state/inspect/state sessions at 0/10/20 seconds, a 30-second qualification deadline, and the original cleanup. It retries only a successful complete all-zero observation, never a failed read.

The [BestBuy addendum review](evidence/bestbuy-content-readiness01-five-read01/root-actual-review.json) records two successful 12-node/all-zero rounds followed by `TREE_DEPTH_BOUND` on the third round: depth33 exceeded the bound32, with 41 attempted and 40 emitted nodes. The partial tree was not qualified. Independent after-state completed, disconnected and matched the before-state; the failed restoration-qualification flag stays false. All 13 original Main guard maps matched. Owned task1018 retired, preexisting tasks851 and1017 remained, and semantic/business/whole-app readiness are false.

The [Amazon launch record](evidence/amazon-search-entry03-launch-read01/launch.json) and [Ticket12306 review](evidence/ticket-owned-launch-inspect02-parent-read01/root-actual-review.json) retain `EAGAIN` action-lock failures. Earlier successful lock probes do not guarantee later admission, and neither a lock owner nor a common cause is established.

## Evidence and publication boundaries

All 9,381 payload rows from CP16 are inherited in the same order with identical values. The old root README remains untouched. New source rows include previously verified immutable origins and full local size/SHA256/Git-blob checks; already existing blobs are reused. Pure-source exact requests and stdin carriers remain reproducible. Private complete UI trees, account text, raw captured log/packet data, signing keys, APK/ELF binaries, caches and transport-parts are excluded. Original errors and missing/unknown outcomes are retained.

Main observations are scoped to their individual receipts. The original `pids.max=12288` baseline and other four limits remain explicit; the snapshot does not assert continuous absence of interference. Creating this candidate changes no Git reference, branch, PR, installed runtime, or device state. Root performs the separate final publication decision/CAS.
