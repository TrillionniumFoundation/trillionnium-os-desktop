# Current app acceptance source

The selected official IHG application is version **5.110.0**, version code
**50023496**. The existing final app acceptance source still expected 5.108.1 /
50023219. Its metadata and APK guards therefore rejected the selected updated
application before the real business flow could run.

This capsule contains the complete 31-file app acceptance source packet. The
IHG repair changes four literal values in `app_profiles.py` and
`ihg_artifacts.py`: the version in both modules, and its complete APK size and
SHA-256. The Clock repair below changes `timer_flow.py`. The remaining 28 files
are byte identical to the original preparation. UID, launcher, signer
verification, resource limits, lifecycle checks, Main bindings and business
requirements are preserved. The original preparation remains unchanged.

## Clock creation readback

After one acknowledged Start click, the timer flow previously required the
first persistent model read to contain the running timer. A valid empty
snapshot immediately followed by the correct running timer therefore failed
with `ONE_NEW_TIMER_REQUIRED`; the pending creation prevented further inputs
and cleanup. The host regression reproduces this failure using the exact
original source reconstructed from the recorded changes.

This timing is possible because DeskClock's
[TimerDAO.addTimer/updateTimer](https://android.googlesource.com/platform/packages/apps/DeskClock/+/6ac43d8368e8b09c4d683d6d993e1862b4f09464/src/com/android/deskclock/data/TimerDAO.java)
uses `SharedPreferences.Editor.apply()`. Android documents that
[apply commits to disk asynchronously](https://developer.android.com/reference/android/content/SharedPreferences.Editor#apply()).
These upstream sources explain the race; they do not identify an installed APK
or prove its current behavior on pocket4.

`claim_created()` now reads at most three times, waiting only after a valid
empty timer/stopwatch baseline. The two waits total at most 0.5 seconds and
each is clipped to the remaining original deadline. Reads and uptime checks
must finish before that deadline. The existing held transport also retains
its phase limits. A nonempty observation must immediately satisfy the
original unique timer, duration, state and creation-time checks; ambiguity,
orphan data and read failures are not retried. Start is never dispatched again.
Exhausted reads or deadlines leave creation pending and prohibit cleanup
inputs as before.

## Validation

Run `python3 -I -B test_source.py` from this directory. The suite contains the
15 existing identity/source checks and eight Clock readback tests. The Clock
tests cover the old failure, immediate and delayed persistence, bounded
exhaustion, deadline accounting, ambiguous or wrong timers, invalid empty
states, read failures and the original acknowledgment requirement. All use
synthetic host inputs and a fake clock; they do not communicate with Android
or use a private account. To run just the new behavior tests, use
`python3 -I -B test_source.py TimerCreationReadback`.

`host-result.json` records the earlier, separate IHG pocket4 validation. That run read the
complete official APK, verified its actual aapt2 package/version/launcher and
API 37 v3 signature, and loaded the complete successor with the existing real
preparation validator. It performed zero Android actions and installed no app.

## Adoption

The runtime preparation and new 13-item selector are retained on pocket4; only
selection index 5 changes and all other 12 references remain identical. The
coordinator must compare the original selection SHA before adopting the new
selector in its current checkpoint. `selection-delta.json` identifies both.

Actual application installation, fresh runtime identity observation and the
complete IHG business acceptance still have to run on the accepted Android
cohort. DeskClock remains a separate coherent-OS identity migration. Adopting
the Clock change requires a new preparation binding these reviewed source
bytes through the existing source and Main checks. The historical preparation,
selector and `host-result.json` do not cover this change. The retained
`host-prepare-current-ihg.py` reproduces only the earlier IHG identity repair;
it is not an adoption command for the Clock fix. These source repairs give no
application or production readiness credit.

No APK, account database, credential, user content or signing key is included.
The formal repository destination is
`compat/android/pocket4/current-app-acceptance/business/` in PR #300.
