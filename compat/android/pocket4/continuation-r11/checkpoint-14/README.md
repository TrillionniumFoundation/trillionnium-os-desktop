# Checkpoint 14: framework crash diagnosis and sensor listener fix

**All 45 tracked Apps remain in scope. CP13's 1/45 result is historical. The replacement framework has not been adopted or granted whole-App qualification.** The frozen CP13 matrix and its original receipts remain unchanged.

## Active platform blocker

The old `system_server` aborted at 04:42:33 UTC on 2026-11-06 on a weak-reference safety assertion during sensor client registration. The original init, surface and host launcher context survived while zygote and system-server identities changed. Clock's next trial rejected that changed epoch before any App launch, UI input or alarm effect.

Read-only diagnostics correlated the fatal log with the exact old system-server tombstone, then bound the three relevant current mapped libraries to the same Build IDs. Saved-file disassembly confirms that installed SensorService keys its listener map by interface-wrapper address. Different wrappers for one Binder can bypass duplicate detection and retain more recipients. The fatal temporary reference was taken on the current Binder object; its normal release path is present.

The [Binder identity patch and reproducible regression](../../framework-stability/sensor-listener-identity/README.md) change the map's hash and equality together. The original reproduces four expected defects; the candidate satisfies 17 contracts, including concurrency and removal/re-registration. The newly exported portable runner has also completed successfully. These are source and host results. A complete Android library build, ABI checks, isolated runtime qualification and Main deployment remain open.

The diagnostic guard has not been rewritten to treat the new framework as the old one. App UI trials and installations remain held while platform recovery is completed. The assertion threshold is unchanged. Private raw tombstones, memory, complete maps and binary snapshots are not published.

## App work retained after CP13

| App | Completed work | Remaining boundary |
|---|---|---|
| Calendar | Core21 passed nine scoped LOCAL calendar workflows including persistence, timezone/recurrence and UI cleanup; all eight Provider tables returned to their empty owned baseline. | This is old-framework scoped evidence. The natural reminder trial is prepared but has never run. Account sync and whole release are not granted. |
| WebView shell | The tracing callback guard is actually installed. A later local business regression passed Unicode/storage/history/normal close and reopen, with owned key and task cleanup. | The original install failure and added installer-exemption metadata are preserved, with separate reconciliation. Media, HTTPS, error-path and stability qualification remain open; the prepared next trial has not run. |
| Gallery | The two-method candidate is built with the original signer. Saved complete ART output reconciles 2,055 unique Verified classes on the old framework. A preserving installer is prepared, including all 29 permission rows. | Candidate is not installed. Installer has no current context or executable install request. External JNI/ABI and fresh runtime closure are still required. |
| Clock | The prepared alarm trial failed its epoch guard with zero control/alarm effects. Earlier narrow timer/expiry results remain historical. | The failed operation key is not replayed. Real Open/Dismiss, audio and whole release remain open. |
| Other Apps | All existing evidence and original failures are retained. | Hardware, user/account-dependent business flows, native correctness, stability and release gates are not waived. |

[status.json](status.json) records these narrow states and the original evidence hashes. The [45-App matrix](../../readiness-20261105/README.md) continues to describe CP13's frozen historical result; no new readiness count is inferred from this checkpoint.
