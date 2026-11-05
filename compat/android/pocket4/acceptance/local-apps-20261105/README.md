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
