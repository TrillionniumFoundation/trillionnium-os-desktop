# Pocket4 Android application repair snapshot

Status: **NO-GO**, observed 2026-11-04.

This directory preserves repair source and a dated application evidence ledger for Android 17 running in DroidLoom on the Pocket4 Linux host. These results do not qualify Android on the repository's Asterinas kernel.

The [Camera source delivery](camera/README.md) includes the zero-device/teardown prerequisite, the hotplug fix, the exact reviewed manager source, an executable host regression suite, pinned build inputs and a conditional unsigned rebuild recipe. The full baseline application build is not reproducible from this checkout alone; its missing inputs are enumerated explicitly.

The [presenter timing source bundle](presenter/README.md) preserves the complete public preimage and the four-file timing repair. Its release build and 70 scoped checks passed; Main deployment and fresh application acceptance remain separate gates.

The [framework epoch guard](acceptance/framework-epoch/README.md) binds acceptance observations and actions to init, zygote, system_server and SurfaceFlinger identities. Ten real-process Linux regressions and a read-only check of the actual Android framework passed. This standalone module supports new acceptance workflows; it does not replace the installed action helper.

[Framework restart evidence](evidence/framework-restart-20261104.json) explains the interrupted Bilibili trial. Public Unicode search passed in the prior framework epoch. Before the later video-open attempt, a zero presentation timestamp caused the composer service to exit and init to restart the Android framework. The later action timed out with unknown outcome; playback did not pass. This is not evidence of a fresh Bilibili crash or proof of a memory-pressure cause.

[readiness-status.json](readiness-status.json) separates old launch observations, historical guest business tests and newer manual results. Contacts launch/onboarding was observed successfully. Camera release07 was installed with data preserved and handled the missing-device failure, while preview/photo use remained blocked by provider connection. These observations preceded the framework restart and require fresh epoch qualification for continuation.

The application matrix is an audited subset, not a complete installed-package inventory. Native failures, environment/login gates, actual business flows and lifecycle qualification remain open. Nothing in this directory changes the whole-project release gate to GO.
