# Pocket4 Android application repair snapshot

## Current continuation — 2026-11-05

**Whole-App production readiness remains 0/45 in the tracked launcher scope.** The [Camera2 checked-disconnect repair](camera/checked-disconnect/README.md) is installed as release08 with exact APK readback and preserved UID/data identity. Its real preview was verified earlier, but the latest trial again found the physical USB source absent; no photo has been taken. [Shared storage has been recovered](shared-storage/storage-fuse08/README.md) through one normal unmount/mount, with subsequent path I/O verified in the same Main. The separate persistent session-lifecycle source fix remains undeployed. [Contacts, WebView, the Clock stopwatch and the local two-field fixture now have scoped functional evidence](acceptance/local-apps-20261105/README.md), including owned close/reopen and exact cleanup. The installed-code storage candidate has been assembled, aligned and verified by the installed ART tools for the exact target class; live lifecycle and deployment remain open, with the inferred boot-extension checksum warning retained. The [final-window QA repair](qa-final-window/README.md) remains separately compiled but not installed. Source/build/runtime recovery and complete App release acceptance remain distinct.

The [complete current 45-App matrix](readiness-20261105/README.md) binds the 2026-11-05 05:46:49 UTC inventory: 186 installed packages, 45 launcher Apps and 44 third-party packages. It retains every original App, including system utilities and QA fixtures, and lists the remaining business checks for each one. Zero fully qualified Apps does not mean every App has reproduced a fault. The original conservative inventory result and its strict completed derivation are preserved separately.

The following original snapshot is retained with its 2026-11-04 scope. New Bilibili runs in [checkpoint 12](continuation-r11/checkpoint-12/README.md) reach DetailsActivity but still observe buffering; the earlier scoped visual playback is not a substitute for the new run. Native candidate07 now has a retained full-host result (3,793 registered, 3,791 executed, 3,788 completed, three skips, two disabled, zero failures) and four passing Android signal cases in its owned runtime. The controller recorded memory-limit events; Main deployment and commercial-App qualification remain open.

## Later actual results — checkpoint7

The independent installed-package audit verified45 package identities and all86
base/split APK signatures. Eleven original badging/manifest-metadata gaps were
resolved from the same hash-bound APKs; the original combined-gate failure and
memory-limit events remain retained. This is installation evidence, not an
actual per-App engine mapping or whole-App pass. The audit observed the original
Clock APK before the later update described below.

Documents11 completed local create/write/read, provider and Files UI rename,
Files open through the system resolver, OPEN_DOCUMENT, persisted-grant reopen,
provider deletion and complete owned cleanup. Gallery rendered the same generated
PNG in two separate launches, with full-image pixel and visual verification.
Its residual directory index and helper were reconciled and removed without
replaying an uncertain provider deletion. Earlier failures remain available.

Clock now has a narrowly changed installed APK that uses a foreground-service
PendingIntent for timer scheduling and cancellation. Its first actual60-second
background trial reached EXPIRED at due+665ms and cold-started a foreground Clock
service. The original trial failed because the notification parser used the wrong
capitalization for the actual dump key. An independent saved-record review verifies
the active notification and full-screen PendingIntent; actual alert presentation
and audible output remain open. Stop/reset/delete returned timer state to empty
and preserved the original alarms. The installation's exact counter/permission
metadata differences are retained separately; it is not described as preserving
every preference byte or permission flag.

The readiness updater now uses independent latest installed-APK observations.
An installation or changed base/split identity invalidates earlier binary-specific
reviews immediately, even when no new review exists. Old Clock stopwatch/timer
core passes remain historical facts and do not qualify the replacement package.
All45 Apps remain tracked; whole-App readiness remains0/45.

## Earlier actual results — checkpoint6

The Clock timer core create/pause/reopen/resume/reset/delete flow passed, and
Clock notifications were enabled through its actual settings page. A subsequent
60-second background timer **failed to expire**, still RUNNING 28.245 seconds
past due. The exact timer was paused/deleted and both owned tasks closed. This
failure remains open despite the successful notification repair.

The Editor Contract QA App completed two actual Unicode/Enter/emoji-delete/clear
rounds and separate launches, with 12 inputs and exact record cleanup. Only its
observed UI and tested lifecycle receive credit; composition, selection and the
remaining release scope are open.

DocumentsUI completed actual create/write/read, provider rename and Files UI
rename with exact byte/hash preservation. Attempt09's following open tap was
acknowledged but its cross-package observation failed. The effect remains
unknown; the own file/directory/temporary package are retained for reconciliation.
Both own tasks closed. See the [current Documents scope](acceptance/local-apps-20261105/documents-saf/CURRENT_STATUS.md).

## Historical snapshot — 2026-11-04

Status: **NO-GO**, observed 2026-11-04. The presenter timing repair and R16 native engine are now deployed to Main and verified. Business acceptance is in progress: Bilibili public search and visual playback passed; Marriott still has a fresh native crash, Beike reaches a blank login router, and Meituan repeatedly exits during startup. LMKD integration remains unqualified.

This directory preserves repair source and dated evidence for Android 17 in DroidLoom on the Pocket4 Linux host. These results do not qualify Android on this repository's Asterinas kernel.

## Delivered repairs

The [Camera delivery](camera/README.md) includes the zero-device/teardown prerequisite, hotplug repair, exact manager source, host regressions, input locks and a conditional unsigned rebuild. Release07 passed actual physical preview and a separate reopen/normal-close trial on the prior R14 epoch. The parent visually confirmed the private image; only public metadata and its hash are included. Photo capture/persistence and the new epoch remain unqualified.

The [presenter bundle](presenter/README.md) preserves the complete public preimage and four-file timing repair. A real zero-timestamp negative control failed as expected; the candidate passed 68 host checks plus two composer controls and produced a pinned release. That exact release is now active in Main.

The [native bridge bundle](native-bridge/README.md) preserves R15 alarm semantics, R16 maps offsets, inherited translator source, the public builder precondition and raw/effective input locks. Reconstruction matched all 906/907/908 translator files and 389 builder files. Both Android engines and full host suites were built. The final [three-arm qualification](native-bridge/qualification/README.md) passed the scoped owned native probes with expected R14/R15 negative controls and the same runner/APK across all arms. Publisher application compatibility remains a separate requirement.

[Main activation](evidence/main-activation-20261104.json) completed verification at 08:55:13 UTC: presenter `47f34d5f…`, R16 engine `c8b9bae4…`, a new framework epoch, 182 packages and 362 existing application directories preserved with UID/data identity and resource limits. OOM counters remained zero. The summary identifies the actual parent verification records used; it is not another runtime execution by the publication agent.

The [LMKD bundle](lmkd/README.md) reconstructs r3/r4/r5 sources, includes scoped controls and retains failed pressure trials. **r4/b099 must not deploy:** a real trial lost its foreground process. Separate r5 is Android-built but has no protocol/pressure canary or Main deployment. Its new-unit `-MD` records improve dependency evidence; four reused objects still have a historical system-header gap. Main currently uses the drain/ACK-only compatibility service, so a file replacement alone cannot establish LMKD integration.

## Current business observations

The current records are bound to the verified post-activation framework epoch. [Business acceptance](acceptance/business-flows/README.md) separates completed subflows from untested behavior.

| App | Current evidence | Remaining gate |
| --- | --- | --- |
| Bilibili | Public Unicode search, matching video, three visually inspected frames showing content progression, actual R16 mapping and normal owned-task close. | Audio, pause/seek, in-app back, reopen and broader App behavior remain untested. |
| Marriott | The original SIGSEGV/unknown launch remains. A separate [qualified metadata diagnostic](evidence/marriott-main-metadata-01.json) observed the virtual maps memfd path, descriptor close and zero-length mprotect before the same loader crash. | This supports an immediate compatibility defect; a corrected-runtime A/B test and actual business success remain unverified. |
| Beike | Exact Chinese query and matching suggestions passed. Selecting the region automatically entered login; an App-originated second login intent removed LoginActivity and left OneLoginRouterActivity blank. | Listing results/details/return are blocked. No login was performed; the reason for the repeated login route is unresolved. |
| Meituan Takeout | One native launch, actual R16 mapping and normal owned-task close were verified. Saved logs explicitly record repeated System.exit(0), with matching EXIT_SELF/0 exit records while the startup task persisted. | Merchant search and menu/details were never reached. The exit caller/trigger and replacement-process start authority are unresolved; no native-signal or pressure cause is inferred. |

| Douyin | Optional login sheet closed normally; public video content visibly changed; related recommendations loaded; a selected video detail and in-app return were verified; normal close preserved Home. | Search was not exercised because no entry was visible in the inspected views. Audio, playback controls, seek and reopen remain unqualified; original helper/audit failures and a separately reconciled unknown click are retained. |

## Acceptance scope

The [framework epoch guard](acceptance/framework-epoch/README.md) binds observations and actions to init, zygote, system_server and SurfaceFlinger identities. Ten real-process regressions and a read-only actual-framework check passed. It is a standalone module and does not replace the installed helper.

[Framework restart evidence](evidence/framework-restart-20261104.json) retains the interrupted Bilibili trial. Unicode search passed in the old epoch; then a zero presentation timestamp caused the composer/framework restart before the later video-open action. That action timed out with unknown outcome and was not replayed. It proves neither playback nor a fresh Bilibili crash or memory-pressure cause.

[readiness-status.json](readiness-status.json) keeps older launches, historical guest tests and later observations separate. Contacts onboarding was observed; create/edit/persist/sync is untested. TextFree's Play-environment alert remains unresolved despite enabled microG services. Static licensing/Integrity references do not prove an attestation cause.

The matrix is an audited subset, not a complete installed-app inventory. Fresh per-app business flows, back/reopen, persistence and actual mapped-engine checks continue in the new epoch. No binary, APK, signing material, account data, private image, raw private UI or commercial crash capture is distributed.
