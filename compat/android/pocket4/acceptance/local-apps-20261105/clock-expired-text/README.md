# Clock expired notification text and current-binary core

The installed APK is `e4ff4b46a651ff3ac77397705b7b749c7fbaaeb94fe1d00818debb31dea34172`. Its installation observation is independent of the build receipt and is preserved byte for byte in `latest-installed-identity.json`.

## Actual application change

The existing expired timer builder used a custom view without standard notification title/text. The installed Droidloom desktop bridge consumes the standard fields. The candidate adds 13 instructions to only the N-or-later expired builder branch, using exactly the existing localized title and body semantics. Full DEX comparison covers 2,941 classes and 19,738 methods with no other semantic change. All 1,281 ZIP payload members except classes.dex are unchanged. V3 signature, the original certificate, and 16 KiB alignment were actually verified. It keeps the prior foreground-service timer scheduling correction. Channels, pending intents, timer state logic, and ringer code are unchanged by this text patch.

The actual Clock-only update succeeded. UID, app-data directory identity, original disabled alarms, notification permission, and sound state were preserved. The only accepted installation preference delta was the global intent counter from 120 to 121; all other preference bytes were identical. The former plural/singular local-variable shadowing report was withdrawn as a review misreading and is not an application fix.

## Actual current-binary result

The new binary's timer core passed on 2026-11-05 at 14:46:50–14:48:34 UTC: ten inputs, one owned 15-minute timer, pause, normal close/reopen, resume, pause, reset, and delete. Both owned tasks were normally removed; no pending input or timer remained. Original alarm state/digest and the pinned installed identity were preserved. The core result retains scheduler observations and explicitly leaves independent cancellation classification pending.

The following expiry phase failed before any launch, UI input, timer creation, or monitor child. The observer attempted a no-follow regular-file read of `/usr/bin/timeout`, which is a symbolic link. The exact original failure remains in `metadata/expiry03-result-original.json`; it is a collector preflight failure, not an observed Clock expiry failure. The composite process therefore exited 1. Its final guarded snapshot verifies empty timer/stopwatch state and preserved original alarm, notification, sound, task, and Main identities. Before and after full snapshot hashes are identical.

The collector's earlier running-only notification-association defect was separately corrected in source and covered by negative controls. This correction does not itself prove actual notification delivery. No private raw AudioFlinger, full NotificationManager dump, bus payload, or request bundle is included here.

## Remaining scope

A new independent expiry trial is still needed after the canonical monitor-tool input is corrected. The older cc7 binary's expiry evidence is not inherited. Desktop Notify submission, a visible popup, physical speaker audibility, alarm/snooze behavior, and whole-app production readiness remain distinct unqualified scopes. `CURRENT_STATUS.json` and the unchanged original results preserve these limits.
