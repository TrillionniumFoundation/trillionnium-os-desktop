# Pocket4 Android application repair snapshot

Status: **NO-GO**, observed 2026-11-04.

This directory preserves a Camera2 repair increment and a dated application evidence ledger for Android 17 running in DroidLoom on the Pocket4 Linux host. These results do not qualify Android on the repository's Asterinas kernel.

The [Camera source delivery](camera/README.md) includes the zero-device/teardown prerequisite, the hotplug fix, the exact reviewed manager source, an executable host regression suite, pinned build inputs and a conditional unsigned rebuild recipe. The full baseline application build is not reproducible from this checkout alone; its missing inputs are enumerated explicitly.

[readiness-status.json](readiness-status.json) separates old launch observations, historical guest business tests and the newer manual runtime results. The latest automated baseline completed all 13 entries in its remaining batch, but performed no business-flow verification. Contacts now passes launch/onboarding. Camera release07 is installed and handles the missing-device failure, while preview/photo use remains blocked by provider connection.

The application matrix is an audited subset, not a complete installed-package inventory. Fresh native failures, environment/login gates, actual business flows and lifecycle qualification remain open. Nothing in this directory changes the whole-project release gate to GO.
