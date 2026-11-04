# Pocket4 Android application repair snapshot

Status: **NO-GO**, observed 2026-11-04. The presenter timing repair and R16 native engine are now deployed to Main and verified. Business acceptance is in progress: Bilibili public search and visual playback passed; Marriott still has a fresh native crash, Beike reaches a blank login router, and Meituan repeatedly exits during startup. Douyin has a verified public-browsing subset; StreetEasy remains blocked by a connection alert and JD.COM by login after query. Amazon verified query suggestions and return, but product search did not complete. CEAir stayed in flight-query loading; Air China exited on SIGKILL and Hyatt failed JNI loading. WeChat showed populated home content, with interaction still unqualified. A later Pinduoduo attempt was stopped before launch by a conservative audit resource gate. LMKD integration remains unqualified.

This directory preserves repair source and dated evidence for Android 17 in DroidLoom on the Pocket4 Linux host. These results do not qualify Android on this repository's Asterinas kernel.

## Delivered repairs

The [Camera delivery](camera/README.md) includes the zero-device/teardown prerequisite, hotplug repair, exact manager source, host regressions, input locks and a conditional unsigned rebuild. Release07 passed actual physical preview and a separate reopen/normal-close trial on the prior R14 epoch. The parent visually confirmed the private image; only public metadata and its hash are included. Photo capture/persistence and the new epoch remain unqualified.

The [presenter bundle](presenter/README.md) preserves the complete public preimage and four-file timing repair. A real zero-timestamp negative control failed as expected; the candidate passed 68 host checks plus two composer controls and produced a pinned release. That exact release is now active in Main.

The [native bridge bundle](native-bridge/README.md) preserves R15 alarm semantics, R16 maps offsets, inherited translator source, the public builder precondition and raw/effective input locks. Reconstruction matched all 906/907/908 translator files and 389 builder files. Both Android engines and full host suites were built. The final [three-arm qualification](native-bridge/qualification/README.md) passed the scoped owned native probes with expected R14/R15 negative controls and the same runner/APK across all arms. Publisher application compatibility remains a separate requirement.

[Main activation](evidence/main-activation-20261104.json) completed verification at 08:55:13 UTC: presenter `47f34d5f…`, R16 engine `c8b9bae4…`, a new framework epoch, 182 packages and 362 existing application directories preserved with UID/data identity and resource limits. OOM counters remained zero. The summary identifies the actual parent verification records used; it is not another runtime execution by the publication agent.

The [LMKD bundle](lmkd/README.md) reconstructs r3/r4/r5 sources, includes scoped controls and retains failed pressure trials. **r4/b099 must not deploy:** a real trial lost its foreground process. Separate r5 is Android-built but has no protocol/pressure canary or Main deployment. Its new-unit `-MD` records improve dependency evidence; four reused objects still have a historical system-header gap. Main currently uses the drain/ACK-only compatibility service, so a file replacement alone cannot establish LMKD integration.

## Additional isolated host contracts

The [pressure relay bundle](lmkd/pressure-relay/README.md) separates registration controls, one real bounded host PSI event, and the later expected-process-birth repair. The actual old-library negative proves that the earlier owner could accept a different same-class process. The new owner has host identity controls but no PSI requalification. These stages do not compose into Android LMKD qualification; the r7 foreground-survival failure and b099 deployment prohibition remain.

The [proc-FD host receipt](native-bridge/proc-provenance/README.md) preserves real factory/accounting, C++ metadata and nested-namespace controls plus a full-FD-table regression. A separate [owned worker-lifecycle receipt](native-bridge/proc-provenance/evidence/worker-lifecycle-03/result-public.json) verifies actual parent exit/PDEATHSIG and delayed waitpid-result reconciliation for a normally exited worker. It does not cover real D-state, production peer authority or Android lifecycle. Final Android source/build and App A/B gates remain separate.

## Current business observations

The current records are bound to the verified post-activation framework epoch. [Business acceptance](acceptance/business-flows/README.md) separates completed subflows from untested behavior.

| App | Current evidence | Remaining gate |
| --- | --- | --- |
| Bilibili | Public Unicode search, matching video, three visually inspected frames showing content progression, actual R16 mapping and normal owned-task close. | Audio, pause/seek, in-app back, reopen and broader App behavior remain untested. |
| Marriott | The original SIGSEGV/unknown launch remains. A separate [qualified metadata diagnostic](evidence/marriott-main-metadata-01.json) observed the virtual maps memfd path, descriptor close and zero-length mprotect before the same loader crash. | This supports an immediate compatibility defect; a corrected-runtime A/B test and actual business success remain unverified. |
| Beike | Exact Chinese query and matching suggestions passed. Selecting the region automatically entered login; an App-originated second login intent removed LoginActivity and left OneLoginRouterActivity blank. | Listing results/details/return are blocked. No login was performed; the reason for the repeated login route is unresolved. |
| Meituan Takeout | One native launch, actual R16 mapping and normal owned-task close were verified. Saved logs explicitly record repeated System.exit(0), with matching EXIT_SELF/0 exit records while the startup task persisted. | Merchant search and menu/details were never reached. The exit caller/trigger and replacement-process start authority are unresolved; no native-signal or pressure cause is inferred. |
| Douyin | Optional login sheet closed normally; public video content visibly changed; related recommendations loaded; a selected video detail and in-app return were verified; normal close preserved Home. | Search was not exercised because no entry was visible in the inspected views. Audio, playback controls, seek and reopen remain unqualified; original helper/audit failures and a separately reconciled unknown click are retained. |
| StreetEasy | One native launch and actual R16 mapping passed. The connection-error dialog was visually confirmed; one explicit Try again after the known error returned the same error. Normal close preserved Home. | Property query/results/details were never reached. The generic alert and empty UID log capture do not establish an offline-host, TLS or service cause. |
| JD.COM | Exact 笔记本电脑 readback, matching suggestions and search-submit acknowledgment passed. The App then presented phone-login semantics; normal close preserved Home. | Product results/detail/return were not verified. LoginActivity was visible and SECURE; the inspected capture was all black, recorded as a protected-capture limitation without bypass or a rendering-failure claim. |
| Amazon | Exact query and matching suggestions; actual R16 mapping; Back returns to populated home; owned close. | Two acknowledged suggestion-delivery methods did not produce observed results. Product details and the cause remain unqualified. |
| Hertz | One acknowledged native launch on the current epoch; fresh exact-app exit evidence. | SIGSEGV shortly after startup; no business flow, no causal stack in the captured buffers. |
| CEAir | Home and calendar visibly rendered; the selected future date was verified; actual R16 mapping and normal owned close passed. | One Shanghai–Beijing query remained on a loading dialog through 270.355 seconds. Results/details and cause remain unqualified. The original notification unknown remains, with separate current-state reconciliation. |
| Air China | One launch attempt; fresh exact-package and lifecycle evidence; only Home remained without a cleanup mutation. | SIGKILL during startup before a completed-task receipt. Sender/cause are unknown; zero Main OOM does not identify them. |
| Hyatt | Fresh exact startup exception and the installed base plus two split APK hashes were retained. | JNI_OnLoad from libdexprotector.so returned -500. The internal reason, Android correction and same-APK private A/B remain unqualified. |
| WeChat | A populated main screen and navigation were visually confirmed; normal owned close restored memory headroom. | The accessibility root exposed no semantic nodes. No search, chat, message or call was tested. A :support SIGKILL is separate from the resumed main process. |
| Pinduoduo | A prelaunch audit admission record only. | The wrapper required 8 GiB host-available memory and observed slightly less. No flow initialization or App launch occurred; this is not an App failure. |

## Acceptance scope

The [framework epoch guard](acceptance/framework-epoch/README.md) binds observations and actions to init, zygote, system_server and SurfaceFlinger identities. Ten real-process regressions and a read-only actual-framework check passed. It is a standalone module and does not replace the installed helper.

[Framework restart evidence](evidence/framework-restart-20261104.json) retains the interrupted Bilibili trial. Unicode search passed in the old epoch; then a zero presentation timestamp caused the composer/framework restart before the later video-open action. That action timed out with unknown outcome and was not replayed. It proves neither playback nor a fresh Bilibili crash or memory-pressure cause.

[readiness-status.json](readiness-status.json) keeps older launches, historical guest tests and later observations separate. Contacts onboarding was observed; create/edit/persist/sync is untested. TextFree's Play-environment alert remains unresolved despite enabled microG services. Static licensing/Integrity references do not prove an attestation cause.

The matrix is an audited subset, not a complete installed-app inventory. Fresh per-app business flows, back/reopen, persistence and actual mapped-engine checks continue in the new epoch. No binary, APK, signing material, account data, private image, raw private UI or commercial crash capture is distributed.
