# Pocket4 local App business acceptance — 2026-11-05

Contacts completed an actual local UI create/edit/close/reopen/delete flow. WebView Shell completed an actual controlled local Unicode/JavaScript/storage/history/close/reopen/cleanup flow. These are scoped business results; neither is a whole-App release qualification.

## Actual results

| Run | Observed result | Cleanup |
| --- | --- | --- |
| Contacts09 | Created and edited the owned local contact; provider data survived close/reopen. The adapter could not identify the list row for the next input. | Exact owned provider fallback removed the fixture; both owned tasks closed. No UI-delete pass. |
| Contacts10 | The corrected row touch opened the same edited contact after reopen. More options opened an actual Contacts popup, whose title the adapter did not recognize. | Exact owned provider fallback removed the fixture; both owned tasks closed. The original pending-menu receipt remains retained. |
| Contacts11 | **Complete actual UI flow:** Device-only contact ID3 created, edited, closed, reopened in detail, deleted through the actual menu and confirmed. Ten inputs; no provider-delete fallback. | Empty database and zero owned tombstones verified. Tasks908/909 each closed once; no pending effect. |
| WebView01 | Stopped before page load because the Load URL button had no resource ID matching the adapter's old selector. | Owned task and loopback fixture closed; no page/storage write. |
| WebView02 | Loaded the controlled page and JavaScript; native Unicode readback succeeded. Native Save click acknowledgement produced no observed DOM result. | Owned task and server closed. The key's status was initially unknown and was retained as such. |
| WebView03 | Reopened the **original origin and exact key**, and actually observed that the key was absent. | Zero deletion inputs, no Save replay; server and owned task closed. This does not turn WebView02 into a business pass. |
| WebView04 | **Complete actual local flow:** exact Unicode input event, storage counter1, second-page readback, counter2, history return, normal close/reopen, preserved counter2/value and exact key removal. | Tasks906/907 each closed once, no pending effect, server child reaped and socket closed. |

Contacts11 completed at the process terminal publication timestamp **08:30:11.095 UTC**. Its Contacts and ContactsProvider APK bytes, SHA-256, UID and version were checked both before and after. The fixture had no account fields and no sync operation was performed. Pre-existing account topology was checked privately and preserved. `contacts-crud11.json` contains only the controlled fixture proofs and selected metadata; it contains no account names or types.

WebView04 ran from **08:17:30.088 to 08:18:33.666 UTC**, with 14 inputs and two separate launches. The actual saved DOM observations in `webview-flow04-reviewed.json` show every intermediate value, including `INPUT_AND_STORAGE_OK`, `COUNTER_INCREMENT_OK`, `BACK_READBACK_OK`, `REOPEN_READBACK_OK` and `OWNED_KEY_REMOVED`. The shell APK was fully hashed before and after. The WebView provider was fully hashed before; the final check verified the same complete file metadata fingerprint, selected version and ready/RELRO state. It was not a second full provider stream hash.

## What changed

The Contacts acceptance adapter now supports the actual list row, which has no accessibility click action, by touching the observed exact fixture label within its unique visible row. Its overflow-menu support is admitted only after the owned contact proof and successful native More-options acknowledgement. It binds the actual popup token to the same owned QuickContact task and preserves the native package/focused-window checks. This changes only the private imported adapter instance, not the globally installed helper or Contacts APK.

The WebView acceptance adapter now touches the five exact observed HTML controls through the existing frame/scope/context-bound helper. The original Unicode, DOM, storage, history and cleanup expectations remain unchanged. An input acknowledgement alone never passes a business step. The comparison shows a working touch path after the original native-click path failed to produce a DOM result; it does not establish a defect in the WebView APK.

`contacts-source/` contains the narrow adapter changes and the executed flow/continuation source. The private account-baseline verifier and full adapter containing that baseline are intentionally omitted; their exact source hashes remain in the original receipts and flow pins. These are fixed-Main acceptance tools requiring their retained device inputs, not standalone installers. `webview-source/` retains the exact controlled fixture, failed and successful adapters, same-origin reconciliation sources and local validation result. No binary, image, account data or personal file content is included.

## Remaining qualification

Contacts still needs Search UI, the remaining permission/sync/error paths and repeat/stability coverage. Its successful return to the same record is recorded accurately without silently treating a list-row selection as an exercised Search field.

WebView's composite release checks additionally include HTTPS, images/media and error handling. This local text/JavaScript/form/history/storage trial does not close those checks. Both Apps also retain the common whole-release gates in the [45-App matrix](../../readiness-20261105/README.md). Earlier failed observations remain available beside the later successes.

## Additional actual local flows

[Clock stopwatch](clock-stopwatch/README.md) now has real Start/Pause, stable
paused state, normal close/new-launch persistence, Resume/Pause with increased
elapsed time, and UI Reset. The first adapter failure is retained; the separate
continuation operated only its exact paused 9,170-ms state and reset from
17,817ms to empty. Original alarm templates and notification permission were
preserved. Timer completion, alarm delivery/timezone and sound are separate gates.

[The local two-editor fixture](probe-fixture/README.md) completed two real rounds
and 14 inputs covering Unicode, field isolation, positive and empty confirmation,
clear and normal close/reopen. Its five installed classes were reviewed. Neither
of the two earlier adapter failures is relabeled an App fault or success. The
ambiguous-selector negative case and full release gates remain open.

## Actual timer core flow

[Clock Timer01](clock-timer/README.md) completed an actual 15-minute timer
create/start/pause/normal-close/reopen/resume/pause/reset/delete flow. The paused
891,439-ms value survived normal close and a fresh launch exactly; resume and
pause reduced it to 882,695 ms. Reset restored 900,000 ms, and UI deletion removed
the timer and allocation fields. Eleven inputs and two owned task closes were
recorded. The two existing disabled alarms, zero alarm instances, Clock APK/UID
and notification permission were unchanged. Expiry, alarm delivery and sound
were not exercised, so the composite clock.timer and clock.persist release gates
remain open.

## Clock notification repair

[Notification04](clock-notifications/README.md) enabled Clock notifications
through its exact App notification settings page. The single observed touch
changed POST_NOTIFICATIONS from false to true; final AppOps explicitly reported
`No operations.` and `Default mode: allow`. This is an intended persistent
Clock-only repair. Two original disabled alarm templates, zero instances, an
empty timer/stopwatch state and the installed APK/UID/version were preserved.
The prior Notification03 title-observation failure remains unchanged.

The corrected selector binds the real toolbar and icon descriptions, the exact
All Clock notifications label and its observed clickable parent. Connection
scoped accessibility window IDs are compared within each observation; actual
WindowManager token, geometry, node semantics and snapshot hashes bind the
input across observations. Notification permission is a prerequisite: expiry,
alarm delivery, audio and complete Clock/Settings release coverage remain open.

## Later timer expiry failure

[Expiry01](clock-expiry/README.md) tested a new actual 60-second timer after the
notification repair. It remained RUNNING through 28.245 seconds past due; the
bounded trial failed. Cleanup reopened Clock, paused the exact timer at a stored
remaining -42,145 ms, then deleted it. Both owned tasks closed and timer/stopwatch
state returned to empty, with original alarms unchanged. The core flow and
notification results above remain scoped facts, not a timer-completion pass.

## Editor core and historical Documents09 progress

[Editor03](editor-contract/README.md) completed two actual Unicode/Enter/delete/
clear rounds and independent launches, 12 inputs and two normal closes. Exact
owned record files were removed; identity/permissions remained equal and fresh
diagnostics found no crash or ANR. Original frame and focus-schema failures are
retained with separate exact cleanup. Composition and selection remain open.

[Documents09](documents-saf/CURRENT_STATUS.md) completed CREATE_DOCUMENT save,
single content write/read, provider rename and the actual Files UI rename.
The next open tap was acknowledged but post-observation failed across packages;
it is retained as unknown and was not repeated. Both owned tasks closed, while
the own file/directory/temporary package were retained for reconciliation.
Complete open/grants/reopen/delete and cleanup receive no passing credit.

## Completed Documents11 and Gallery image scope

[Documents11](documents-saf/README.md) subsequently completed the real local
CREATE_DOCUMENT save, content write/read, provider rename, Files UI rename and
open through the system resolver, OPEN_DOCUMENT selection, normal close/reopen
with a persisted grant, and exact provider deletion. Seven readbacks retained the
same87-byte hash. All three owned tasks closed; the helper package, stage, file,
directory and grants were removed. Its23 counted decisions include two explicit
no-effect observations, so they are not described as23 injected inputs. The
original09 unknown outcome was independently reconciled and cleaned before11;
none of the earlier failed receipts was rewritten.

[Gallery image01](gallery-image/README.md) rendered one generated640×480 PNG in
two independent native launches. Four fresh full-window observations and a
hash-verified visual inspection showed the complete image. Both tasks closed.
The original flow correctly failed when its empty directory retained an index
row. A single exact provider deletion returned empty stdout and was retained as
unknown; a separate read-only observation proved both row and directory absent.
That deletion was never replayed. Final cleanup only uninstalled the exact helper
and verified original media metadata, tasks, permissions and Main identity.

These results pass the stated local I/O/render and lifecycle scopes. Files tree
and content routes, copy/move/folder/search, Gallery video/rotation/copy editing,
remaining errors and complete release qualification continue separately.

## Installed Clock background-expiry repair

[The foreground timer candidate](clock-foreground-timer/README.md) changes only
two PendingIntent factory calls in one TimerModel method. It was built, signed
with the same certificate and installed once. The new60-second background timer
actually cold-started Clock as a foreground service and reached EXPIRED665ms after
due. Stop/reset/delete and both normal task closes completed. The original test
failed on a dump-key capitalization mismatch; a separate saved-record review
verifies the active expired notification and full-screen PendingIntent without
rewriting that receipt. Actual heads-up/full-screen presentation and audible
output remain unqualified.

The exact installation retained two metadata deltas: a still-denied storage
permission gained an installer flag and the global alarm intent counter changed
119→120. The rest of that preference file was verified by full-hash reconstruction.
Original alarms, data-directory identity, other permission entries, observed
volume streams and ringtone settings remained the same. New-package core timer
regression, owned alarms/timezone and complete release qualification remain open.
