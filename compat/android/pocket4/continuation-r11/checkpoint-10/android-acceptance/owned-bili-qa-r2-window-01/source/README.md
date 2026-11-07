# Owned Bili QA r2: explicit display readiness and independent post-state

This is an uninstalled candidate in the independent package
`org.droidloom.qa.bili.r2`, protocol `pocket4-owned-bili-qa-v2`. The existing r1
package, UID 10164, APK, claims and failed launch/inspect01 are unchanged. This
source does not acquire r1's build, signer, UID or Android qualification. New
actual build/APK/signer and fresh installation evidence are required before any
r2 instrumentation. No device request has been dispatched by this author.

The new protocol requires an explicit `scope.display = 0`. This is the requested
target display, verified again by the helper's actual window selection. The
unchanged host foreground parser still binds the original activity/window token;
its flattened `dumpsys window displays` record does not independently prove a
display ID. That limit is not presented as a new platform diagnosis.

## Actual trigger and limits of the diagnosis

The original run successfully launched Bilibili task 874 from a state with only
Home task 851. Its before-state finished successfully. Inspect finished with
code 0, error `NO_FOCUSED_APPLICATION_WINDOW`, after 10 ms; its own service flags
were read back as restored, but the host sequence aborted before independent
after-state. Exact-task cleanup succeeded and Main stayed at the pinned 48cb
epoch. The aggregate run remains FAIL. These scoped findings do not qualify
Bilibili playback or audio. Private raw command output and UI data are excluded
from this source tree; the parent holds the original receipts.

The old host foreground parser identifies one unique `mCurrentFocus` token,
package and activity across `dumpsys window displays`; it does not retain the
display section. The Java helper used context-associated `getWindows()` and
then required display 0. The failure recorded neither the returned list nor
its display/focus metadata. Accordingly, neither a display mismatch nor an
accessibility readiness race is claimed as the proved root cause.

Android documents that `UiAutomation.getWindows()` uses the display associated
with its context, while `getWindowsOnAllDisplays()` returns lists keyed by
display. The latter is available since API 30. We now explicitly select display
0; no other display, active-only window or non-focused window becomes eligible.

Official references (not a claim that these exact public revisions are the
installed framework source):

- https://developer.android.com/reference/android/app/UiAutomation#getWindows()
- https://developer.android.com/reference/android/app/UiAutomation#getWindowsOnAllDisplays()
- https://android.googlesource.com/platform/frameworks/base/+/HEAD/core/java/android/app/UiAutomation.java
- https://android.googlesource.com/platform/frameworks/base/+/b52353b790b08147b6d63a9669790162b769166a/services/accessibility/java/com/android/server/accessibility/AbstractAccessibilityServiceConnection.java

The AOSP service connection has an `ensureWindowsAvailableTimedLocked` path.
That supports treating window availability as an observable condition, but
does not prove why the Pocket4 sample lacked an eligible window.

## Narrow Java changes

The helper queries `getWindowsOnAllDisplays()` and accepts exactly one focused
application window on display 0, then verifies its root belongs to Bilibili.
All original target UID, host activity/window attestation, full-tree identity,
fresh click target and single-action checks remain. A click still requires a
fresh complete tree matching the successful inspection and remains a separate
authorized operation; this build request performs no UI action.

Window availability may be observed for at most two seconds within the original
eight-second operation budget. The helper subscribes only to window-change
event types, never event text/source. An event serial closes the query-to-wait
gap. Waiting uses a bounded monitor wait awakened by events or the deadline;
there is no fixed sleep or replay of an action. The outer watchdog stays at
twelve seconds. IPC returning too late fails the readiness/overall deadline.

First/last census contain only display IDs, connection-scoped window IDs, type,
focus/active/accessibility-focus booleans, layer, counts and timings. They have
no titles, node text, accounts or recommendations. Bounds are eight displays,
32 windows per display, 128 total windows, 64 queries and at most 32768 bytes of
census. A new bounded snapshot is checked before replacing the prior one, so a
census bound error still has a small failure envelope. The overall result cap
stays 262144 bytes; the tree reserves 65536 bytes for non-tree metadata. Node,
depth and child limits are unchanged. Service flags and the event listener
have independent finally cleanup, retaining the original error on failure.

## Host failure and restoration changes

The host still requires the unique successful instrumentation finish code -1.
A separate failure-only decoder can explain an exact finish(0) envelope after
checking canonical bytes, request hash, nonce, operation and helper UID. It
returns only bounded failure/window metadata and never a qualified assessment.
The original parser error remains primary; failed-assessment write errors are
notes, not replacements. No raw inspection tree enters the failure summary.

Once the state sequence begins, its finally path attempts exactly one fresh
after-state even if before-state, inspection, foreground validation or a click
fails. The same held transport, source, Main and installed identity guards
remain. A poisoned transport may safely refuse that after-state attempt; such
refusal is a secondary error, not an excuse to bypass the transport guard.

Original exceptions are retained. Independent after-state, foreground, task
and installed identity errors cannot replace them. An after-state alone cannot
qualify an unsuccessful inspection/action or overwrite its failure. Successful
restoration requires the original real own-service readback plus unchanged
fresh before/after state. For an action error, the earlier successful inspect
is not substituted as the action's restoration evidence.

The host adapter explicitly binds the actual R4 recorder manifest
`52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1`.
It has no old-v2 fallback. The r2 helper UID is still unknown and must come from
its own actual install; the adapter rejects old r1 UID 10164.

## Build-only qualification

The same pinned JDK21, SDK31 public `android.jar`, D8/R8, aapt, zipalign and
apksigner inputs from the actual r1 build are used. Compile API is 31; min API
31 and target API 33 are distinct and unchanged. No Activity, native library,
service, receiver, provider, dangerous permission or network permission is
introduced. It is non-debuggable, testOnly, no-backup self-instrumentation, with
only Bilibili package visibility. No shell permission adoption, settings write,
grant or touch-exploration request is added.

The build source/output roots are fresh `pocket4-owned-bili-qa-r2-source-01`
and `pocket4-owned-bili-qa-r2-build-01`. The generated request is build-only,
one CPU, 512 MiB, swap 0, Tasks 128, 300 seconds. Default entry/generator modes
remain PLAN_ONLY. Actual tool, source, signer, APK and receipt checks are the
unchanged builder gates. No installation or business action is authorized by a
successful compile alone.

Old/new host controls use explicit synthetic Session seams to exercise the
actual Python sequence error/finally code; they are not Android runtime tests.
Private original wire is never embedded in those fixtures. Actual compilation,
window readiness, event delivery and the new package's runtime behavior remain
unqualified until the device produces their receipts.
