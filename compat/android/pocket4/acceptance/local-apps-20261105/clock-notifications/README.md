# Clock notification repair, Pocket4 R16

The single-App notification prerequisite was repaired through the actual Clock notification settings page. Trial04 performed one observed touch, read POST_NOTIFICATIONS as granted, and independently read AppOps as `No operations.` followed by `Default mode: allow`. The latter is the service's explicit default-mode report. The original permission and AppOps values are retained in the selected result.

The repair is persistent and authorized. The two original alarm templates remain disabled, their complete contents digest is unchanged, there are no alarm instances, and timer/stopwatch state remains empty. No default ringtone, global volume, account or synchronization setting changed. The Clock APK, UID, version and Main epoch remained the same.

## Actual attempts

| Trial | Outcome | Setting inputs | Owned lifecycle | Interpretation |
| --- | --- | ---: | --- | --- |
| 03 | Failed at `ACTUAL_CLOCK_APP_HEADER_REQUIRED` | 0 | Task923 normally closed; pending null | The new Settings task and exact-task Intent succeeded. This was an observation-schema mismatch, not an App crash or notification write failure. |
| 04 | Notification enable verified | 1 | Task926 normally closed; pending null | Actual permission and independent AppOps reads prove the intended change. |

Trial03 ran from 2026-11-05T10:21:30.780451Z to 10:21:38.466350Z. Trial04 ran from 10:30:08.551645Z to 10:30:23.239481Z. Both remote jobs reached complete, durable terminal output. The exact original result hashes are embedded in the selected projections.

## Narrow correction

The real page exposes Clock through the `collapsing_toolbar` and `entity_header_icon` content descriptions. It does not expose a text node equal to Clock. The visible switch label is exactly `All Clock notifications`; the Switch is unchecked and has `clickable=false`. Its unique innermost clickable `main_switch_bar` contains the actual label and Switch. The controller retains these native facts and uses one snapshot-bound touch at the observed label.

Each observation requires its header, label, Switch and parent to belong to the same native window. Native accessibility window IDs are scoped to a connection, so only that ID field is removed when comparing two complete node bindings. The same WindowManager token, all other node semantics/state/geometry, and the original frame/scope/context hashes remain required. No installed helper was modified.

The actual installed ActivityManager task-option proof is pinned separately. It establishes `--task` parsing and propagation into ActivityOptions; it does not replace runtime topology checks. The controller still creates one new Settings task, targets only the Clock package and UID, verifies the exact notification Activity and owned task, and preserves all preexisting tasks. It performs no `pm grant`, blind settings write, force-stop, task-overlay or lock-task action.

## Qualification limits

This evidence establishes the Clock notification prerequisite and its controlled repair. It does not establish timer expiry delivery, alarm firing/dismissal, audible output, whole Clock readiness, or whole Settings readiness. Those remain separate runtime qualifications. A touch acknowledgement alone is not treated as business success; the final permission and AppOps reads supply that evidence.

The original trial03 failure is retained. Unknown actions are never replayed. Raw native trees and screenshots remain private evidence; this bundle contains the selected actual control facts and hashes needed to understand the change. Frozen held-session, Clock reader, stopwatch helper and timer reader dependencies are identified by their exact hashes in the controller.
