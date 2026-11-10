# Pocket4 Clock foreground timer checkpoint 7

The Clock candidate is actually installed. Its independent live identity is in `latest-installed-identity.json`, bound to the 2026-11-05 12:31:28.202376 UTC held APK readback and certificate verification. It is not inferred from the build artifact. The APK changed, so earlier reviews of the factory binary do not qualify the new binary.

## What changed and what the actual device did

The app patch changes exactly two `PendingIntent.getService` calls to `getForegroundService` in the installed TimerModel scheduling method: the existing-alarm lookup/cancellation path and new-alarm creation path use the same PendingIntent type. The actual build compared 2,941 classes and 19,738 methods. Exactly one method and two instructions changed; zero other semantic changes were found. All 1,281 non-signature payload members were checked, with only classes.dex changed. The original certificate, v3 verification and 16 KiB alignment passed. Full proof hashes and remote artifact provenance remain in the exact build result.

Install01 stopped before any install dispatch at the signer symlink check. Install02 executed the single real update and read back the new APK, but its strict original result remains POST_INSTALL_STATE_DIFFERS. Independent review found only denied READ_EXTERNAL_STORAGE adding INSTALLER_EXEMPT and the global alarm intent counter changing 119 to 120. The private post-install XML was compared by hash-verified offline reconstruction; its body is excluded here. UID/data-directory identity, original alarm contents, notification state, all observed volume streams and ringtone settings remained the same. No reinstall or counter restoration was performed.

Expiry02 retains its original failed/1 result and notification_posted_verified=false. During that actual run, normal removal of the first own task killed Clock. At the scheduled expiry, TimerService cold-started in PID 642653 and entered foreground service; the first EXPIRED observation was due + 665 ms. The sole timer was actually stopped/reset and deleted, both own tasks were normally closed, no pending effect remained, and the original task set was restored.

The saved active notification contained fullscreenIntent=PendingIntent, while the original test parser searched for fullScreenIntent. A separate read-only review recognizes one active Clock/user0/UID10063 timer notification carrying a full-screen PendingIntent. Nine offline cases reproduce the old rejection and check the actual key, identity, active-list boundaries, missing/null PendingIntent, other channel and similarly named fields. This does not rewrite the original result or prove an actual heads-up/full-screen window or audible output. No extra expiry run was performed merely to change the exit code.

## Boundaries and next work

The candidate still needs a new bounded pause/resume/persistence/reset/cancel regression. The original APK's core-timer and stopwatch results are historical evidence, not current-binary qualification. Owned alarm behavior, audible output and stability remain open. No whole-app production-ready claim is made.

A separate exact USB observation at 12:36:00 UTC found camera usb3-4 absent and no matching video nodes. The existing provider remained active with PID 3253584/birth 79790547. This is a fresh observation, not reuse of the earlier absence; no physical cause is inferred. There were zero device opens, sysfs writes, restarts or owner-lock acquisitions.

## Reproducibility and publication

Run the saved-schema check with `python3 source/test_notification_schema02.py`. It is entirely local and performs no device operation. Original controllers remain default inert. Source pins reference the already frozen shared session and UI helpers; this checkpoint does not replace those dependencies. The included reconstruction script needs private XML retained outside this public package, and its existing hash-only proof is included here.

Exact original build/install/expiry results are copied without rewriting. The independent review, current identity and current-status files are separate derived evidence. SOURCE_MANIFEST.json pins every included file. No private preferences XML, original alarm labels/times, raw global audio log, credential or signing key is included.
