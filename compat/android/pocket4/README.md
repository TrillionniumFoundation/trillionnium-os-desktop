# Pocket4 Android application repair snapshot

## Current continuation — 2026-11-05

**Whole-App production readiness remains 0/45 in the tracked launcher scope.** The [Camera2 checked-disconnect repair](camera/checked-disconnect/README.md) is installed as release08 with exact APK readback and preserved UID/data identity. Its real preview was verified earlier, but the latest trial again found the physical USB source absent; no photo has been taken. [Shared storage has been recovered](shared-storage/storage-fuse08/README.md) through one normal unmount/mount, with subsequent path I/O verified in the same Main. The separate persistent session-lifecycle source fix remains undeployed. [Contacts, WebView, the current Clock timer and the local two-field fixture have scoped functional evidence](acceptance/local-apps-20261105/README.md), including owned close/reopen and exact cleanup. The installed-code storage candidate has been assembled, aligned and verified by the installed ART tools for the exact target class; live lifecycle and deployment remain open, with the inferred boot-extension checksum warning retained. The [final-window QA repair](qa-final-window/README.md) remains separately compiled but not installed. Source/build/runtime recovery and complete App release acceptance remain distinct.

The [complete current 45-App matrix](readiness-20261105/README.md) binds the 2026-11-05 05:46:49 UTC inventory: 186 installed packages, 45 launcher Apps and 44 third-party packages. It retains every original App, including system utilities and QA fixtures, and lists the remaining business checks for each one. Zero fully qualified Apps does not mean every App has reproduced a fault. The original conservative inventory result and its strict completed derivation are preserved separately.

The following original snapshot is retained with its 2026-11-04 scope. New Bilibili runs in [checkpoint 12](continuation-r11/checkpoint-12/README.md) reach DetailsActivity but still observe buffering; the earlier scoped visual playback is not a substitute for the new run. Native candidate07 now has a retained full-host result (3,793 registered, 3,791 executed, 3,788 completed, three skips, two disabled, zero failures) and four passing Android signal cases in its owned runtime. The controller recorded memory-limit events; Main deployment and commercial-App qualification remain open.

## Latest recorded results — checkpoint10

This checkpoint covers completed device observations through **2026-11-05
20:14:45 UTC** and their subsequent independent local reviews. Later active
continuation runs are retained separately for the next checkpoint.

[Calendar11](calendar-functional-repair-20261105/CURRENT_STATUS.md) is installed
as00cb0b0a… after116 host checks and actual ART verification of66 target classes.
It fixes the Provider receipt rejection observed after creating a LOCAL calendar:
the exact returned sync-adapter query is validated without weakening the generic
event receipt parser. The single preserving installation finished at19:09:22 UTC.

The [Core12 actual run](calendar-functional-repair-20261105/core12-acceptance/README.md)
verified LOCAL calendar creation, Cancel/Discard without an event write, and one
UI event Save with exact Provider and detail readback. It failed at its original
720-second lease; edit Save, separate reopen and UI delete remain incomplete.
Two Save decisions were rejected before input by the snapshot guard. A later
transport UNKNOWN remains unchanged, with no matching original journal command.
Separate read-only reconciliation found the original unedited event. At20:01:44
UTC, one exact event deletion followed by one exact empty-calendar deletion
restored all eight physical tables and task851, preserving Main and package
identities. Provider cleanup earns no UI delete credit.

[Clock alarm03](acceptance/local-apps-20261105/clock-alarm/attempt03/README.md)
retains an actual due-delivery failure on the current e4ff APK. The owned alarm
was scheduled, but the saved due chain did not reach the firing state or firing
notification. Its separate exact UI cleanup restored the two original disabled
templates and zero instances. This evidence sets only clock.alarm to failed;
the existing timer result on the same binary remains accepted. The exact AMS
rejection point was not retained and is not invented from missing logs.

The [signed Clock dispatch candidate04](acceptance/local-apps-20261105/clock-alarm/candidate04-build/README.md)
uses foreground-service scheduling for the firing transition and the existing
receiver for non-firing transitions. It binds new envelopes to the occurrence,
parent, source state and generation and preserves legacy action contracts.
The actual build compared all2,941 classes/19,744 methods: five original methods
changed, six were added, and the other43 original methods in the four target
classes stayed unchanged. Only classes.dex changed among1,281 ZIP payloads.
Its53 host cases double several App delegates and do not replace device
acceptance. Separate [actual ART04 verification](acceptance/local-apps-20261105/clock-alarm/candidate04-art/README.md)
now confirms all four modified classes as Verified, with the real optional
shared-library context,52 boot-classpath files and87 guest inputs unchanged.
The signed433ff501… candidate is uninstalled at this checkpoint. New-binary alarm
delivery, runtime identity and timer regression remain required.

[Files feature10](acceptance/local-apps-20261105/documents-features/flow10/README.md)
completed all12 declared scoped checks. Copy and Move preserve the generated
59/118-byte hashes. Two actual OK confirmations deleted the two copies and then
four remaining owned entries, with physical readbacks and zero host file-unlink
fallbacks. Close/reopen returned the same content; revoking the tree grant caused
an actual SecurityException for an existing file before any new grant; a later
GET_CONTENT selection returned the exact bytes. All URI grants, five owned tasks,
files/directories and the helper were cleaned. The earlier09 failed/unknown result
remains preserved. The [provider-clause review](acceptance/local-apps-20261105/documents-features/provider-clause-review10.json)
identifies remaining ArchivesProvider and dedicated Downloads navigation evidence.
Search, sort, name-conflict handling and whole release remain separate open work.

[Contacts search preparation](acceptance/local-apps-20261105/contacts-search/preparation01/README.md)
retains the installed search-method review, a bounded owned-contact flow and its
pending-state tests, and the independently reviewed passive runtime observer.
This preparation bundle itself contains no actual search execution or gate pass.
A separate [actual search01 and runtime02 review](acceptance/local-apps-20261105/contacts-search/runtime-identity02/README.md)
preserves the original search-widget mismatch and exact fixture cleanup. Five
stable snapshots across two Contacts process generations bind the unchanged
signed APK and381 full ELF hashes; only observed runtime identity receives new
credit. Search and whole-App readiness remain open. The newer [Bilibili R6 controls observation](acceptance/commercial-apps-20261105/bilibili-controls-r6/README.md)
found visible player controls in a later complete observation. The original
business-success false and unknown-outcome flags remain; advancing video and
audio are still unverified.

All45 Apps remain tracked, with52 installed-package observations and18 retained
reviews. Twelve reviews currently provide scoped statuses, including negative
Camera and Clock results; six older reviews have no current credit. Whole-App
production readiness remains0/45. The original12288 task profile remains in use.

## Earlier actual results — checkpoint9

[Calendar candidate10](calendar-functional-repair-20261105/CURRENT_STATUS.md) is
installed as7872aa56… following actual verification of all66 added/modified
classes by the installed ART tools. The single update finished at18:32:09 UTC
and preserved UID10061, signer, permissions, data identities, Provider identity,
eight empty tables and baseline task851. Candidate09 had fixed the actual08 menu
VerifyError; its subsequent launch automatically opened microG login. That
caller/task chain was independently reconciled and its two owned tasks normally
closed. Candidate10 replaces automatic account setup on an empty calendar list
with local guidance and an explicit Add account action. Actual event/reminder
acceptance for the installed10 APK remains separate.

[Gallery04](acceptance/local-apps-20261105/gallery-video/revision04/README.md)
completed actual video pause/resume and separate reopen:4→9 seconds before
pause, identical paused full-window pixels for4.8648 seconds,18→23 after resume,
and4→9 after reopening. Both tasks and all media/helper state were cleaned.
The [independent runtime identity review](acceptance/local-apps-20261105/gallery-video/runtime-identity04/README.md)
binds the same signed APK to two actual process generations, five stable maps
observations and381 hashed ELF files, including ART and nativebridge/lazy bridge.
The original sampler completeness count remains zero; two name-matched unresolved
paths were explicitly r--s property/resource mappings. JIT/anonymous memory is
not hashed, and no future translation or stress qualification is claimed.
Album enumeration, JPEG rotation, edited-copy persistence, audio and whole-release
scope remain open, including the frozen gallery.open check.

[Files feature08](acceptance/local-apps-20261105/documents-features/flow08/README.md)
completed five scoped checks, now including copying two files through Files UI.
Both59-byte and118-byte copies matched their complete source hashes. A later
input precondition stopped with STALE_FRAME; no move/delete success is inferred.
All owned tasks/files/directories/helper state were cleaned. The four fallback
file unlinks receive no Files UI-delete credit, and the earlier Documents11
I/O/persistence/lifecycle scope remains accepted.

The [Editor lifecycle candidate](editor-lifecycle-candidate-20261105/README.md)
passed43 actual host checks and bytecode roundtrip. It is not signed or installed:
the original signing key is unavailable. The installed editor's earlier Unicode,
callback, clear and separate-launch evidence remains distinct.

The [new Dialer component review](component-audit-20261105/contract-review/dialer-functional-targets01/README.md)
shows that actual call-log polling and voicemail settings reference separately
declared, defined implementation classes. The two extra missing legacy
declarations remain unresolved contracts, not two reproduced business crashes.
The [Gallery camera route](component-audit-20261105/contract-review/gallery-camera-forwarding04/README.md)
forwards to the installed Camera2 launcher; its unused-looking MediaSaveService
declaration is not treated as a proven failure from literal counts alone.

[Original Main resource settings were restored by their owner](runtime-resource-boundary-20261105/return-to-original05/README.md).
Separate actual restoration and post-exit receipts, plus this continuation's
independent read, verify TasksMax/pids.max12288 and unchanged Main identities.
Subsequent jobs use the original b227/7e49 guard. The historical6144 profile and
its rejecting USB04 receipt remain unchanged. At17:57:01 UTC the
[fresh Camera USB05 read](camera/checked-disconnect/device/current-usb05/selected-review.json)
still found the exact physical source absent and no matching video node while
the same provider remained running. No new Camera UI or shutter attempt followed.

All45 launcher Apps remain tracked. There are51 time-ordered installed-package
observations and16 retained reviews, of which10 currently provide scoped credit
and six old reviews do not. Whole-App production readiness remains0/45.

## Earlier actual results — checkpoint8

The [installed Clock text repair](acceptance/local-apps-20261105/clock-expired-text/README.md) adds standard expiry title/body fields for the actual notification bridge. On the exact installed e4ff APK, core03 verified start/pause/reopen/resume/reset/delete and the pending-alarm arm/cancel sequence. A separate expiry05 fixture cold-started the service in the background and reached EXPIRED, delivered the exact expiry text through host Notify, then stopped/deleted and closed both owned tasks. A separate saved-record review identified nonzero HAL power in ongoing rows omitted by the first parser. The original failed/1 receipt remains unchanged. This joint evidence passes the frozen timer check; visible desktop popup, physical speaker audibility, alarm/timezone behavior, engine identity and whole-App release remain open.

[Calendar candidate08](calendar-functional-repair-20261105/CURRENT_STATUS.md) is now installed with exact full-APK readback, the original signer/UID/data identities and all six empty Provider tables preserved. It restores missing event functionality, adds durable genuine-user snooze recovery and binds notification actions to full alert identity to avoid reused-row mistakes. Ninety-one host checks and narrow payload/method comparisons passed. Android CRUD/reminder/recurrence/sync and full release acceptance remain pending. Its first UI controller was held before launch for the shared semantic text-entry repair.

[Gallery03](acceptance/local-apps-20261105/gallery-video/revision03/README.md) rendered the owned full video with a visual timecode advancing4→9 over5.0557 seconds. Three attempts to show the hidden controls were rejected before input because the video frame changed. The task and all fixture state were cleaned; pause/resume/reopen remain pending. [Files feature03](acceptance/local-apps-20261105/documents-features/flow03-delta/README.md) retains three verified grant/cancel cases and its pre-input failure, preserving the earlier Documents11 I/O/persistence scope.

The [14-App installed component audit](component-audit-20261105/README.md) found13 references to12 classes absent from those APK DEX sets. This is a feature/class-loader investigation, not12 reproduced crashes. The [contract review](component-audit-20261105/contract-review/README.md) records instrumentation-supplied test classes and the smaller test-only AOSP Browser2 contract; importing unrelated Chromium test Activities is not treated as a proven packaging repair.

[Main resource diagnosis](runtime-resource-boundary-20261105/README.md) found that a systemd reload made the existing6144 task setting effective, while the original guard expected12288. A separately frozen profile binds6144 with every other activation field and all guard logic unchanged. No resource/configuration write or Main restart occurred. The conflict remains a release concern.

All45 launcher Apps remain tracked. There are49 time-ordered installed-package observations; both Clock and Calendar replacements invalidate old-binary reviews. Fourteen reviews are retained, eight currently accepted scoped reviews remain, and six old reviews have no current credit. Whole-App production readiness remains0/45.

## Earlier actual results — checkpoint7

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
