# Calendar picker discovery17 and recurrence18 history

Device evidence cutoff: 2026-11-06T00:15:28.272540+00:00. These are independent completed runs on the same installed Calendar11 APK. No installation or readiness registry update is part of this bundle.

## Actual results

Discovery17 captured the real DatePicker, Time zone and Repeat controls, then normally closed task1007 and removed its exact empty LOCAL test calendar. It performed 10 control inputs and 2 lifecycle actions, with zero Event Save calls. This proves the observed picker grammar and cleanup, not recurrence editing or reminder delivery.

Recurrence18 retained its original FAILED state. The first input was not dispatched: six bounded readonly tree samples did not satisfy the two-consecutive-complete condition. It performed only one launch and one normal close of task1013. No calendar/event fixture, standard intent or Provider cleanup was created or dispatched. The saved per-sample diagnosis is later work and is deliberately excluded from this cutoff.

Both original results bind package identities and the same Main guard before/after, restore only task851, record empty UI/business pending state, and end with all eight Provider table counts zero. Diagnostics observed one new process-exit event in each normal-close segment and zero new crash/ANR events; this does not mean all process exits were zero.

## Evidence and scope

Original JSON results, authoritative statuses and handoff/Root terminal reviews are byte-exact copies. The two exact first-open source modules and parent source manifests preserve provenance; this small bundle is not a standalone executable harness. Full original17 contains only the owned zero-baseline test fixture and public picker node labels. No screenshots, account topology, request envelopes, binary payloads or credentials are included.

The prior15/16 failures and Core13 diagnostic FAILED history remain unchanged. This bundle grants no new business or whole-app production qualification.
