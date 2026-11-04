# Pocket4 Android application repair snapshot

Status: **NO-GO**, observed 2026-11-04. The presenter timing repair and R16 native engine are now deployed to Main and verified. Application business flows and LMKD integration still need acceptance.

This directory preserves repair source and dated evidence for Android 17 in DroidLoom on the Pocket4 Linux host. These results do not qualify Android on this repository's Asterinas kernel.

## Delivered repairs

The [Camera delivery](camera/README.md) includes the zero-device/teardown prerequisite, hotplug repair, exact manager source, host regressions, input locks and a conditional unsigned rebuild. Release07 passed actual physical preview and a separate reopen/normal-close trial on the prior R14 epoch. The parent visually confirmed the private image; only public metadata and its hash are included. Photo capture/persistence and the new epoch remain unqualified.

The [presenter bundle](presenter/README.md) preserves the complete public preimage and four-file timing repair. A real zero-timestamp negative control failed as expected; the candidate passed 68 host checks plus two composer controls and produced a pinned release. That exact release is now active in Main.

The [native bridge bundle](native-bridge/README.md) preserves R15 alarm semantics, R16 maps offsets, inherited translator source, the public builder precondition and raw/effective input locks. Reconstruction matched all 906/907/908 translator files and 389 builder files. Both Android engines and full host suites were built. The final [three-arm qualification](native-bridge/qualification/README.md) passed the scoped owned native probes with expected R14/R15 negative controls and the same runner/APK across all arms. Publisher application compatibility remains a separate requirement.

[Main activation](evidence/main-activation-20261104.json) completed verification at 08:55:13 UTC: presenter `47f34d5f…`, R16 engine `c8b9bae4…`, a new framework epoch, 182 packages and 362 existing application directories preserved with UID/data identity and resource limits. OOM counters remained zero. The summary identifies the actual parent verification records used; it is not another runtime execution by the publication agent.

The [LMKD bundle](lmkd/README.md) reconstructs r3/r4/r5 sources, includes scoped controls and retains failed pressure trials. **r4/b099 must not deploy:** a real trial lost its foreground process. Separate r5 is Android-built but has no protocol/pressure canary or Main deployment. Its new-unit `-MD` records improve dependency evidence; four reused objects still have a historical system-header gap. Main currently uses the drain/ACK-only compatibility service, so a file replacement alone cannot establish LMKD integration.

## Acceptance scope

The [framework epoch guard](acceptance/framework-epoch/README.md) binds observations and actions to init, zygote, system_server and SurfaceFlinger identities. Ten real-process regressions and a read-only actual-framework check passed. It is a standalone module and does not replace the installed helper.

[Framework restart evidence](evidence/framework-restart-20261104.json) retains the interrupted Bilibili trial. Unicode search passed in the old epoch; then a zero presentation timestamp caused the composer/framework restart before the later video-open action. That action timed out with unknown outcome and was not replayed. It proves neither playback nor a fresh Bilibili crash or memory-pressure cause.

[readiness-status.json](readiness-status.json) keeps older launches, historical guest tests and later observations separate. Contacts onboarding was observed; create/edit/persist/sync is untested. TextFree's Play-environment alert remains unresolved despite enabled microG services. Static licensing/Integrity references do not prove an attestation cause.

The matrix is an audited subset, not a complete installed-app inventory. Fresh per-app business flows, back/reopen, persistence and actual mapped-engine checks continue in the new epoch. No binary, APK, signing material, account data, private image, raw private UI or commercial crash capture is distributed.
