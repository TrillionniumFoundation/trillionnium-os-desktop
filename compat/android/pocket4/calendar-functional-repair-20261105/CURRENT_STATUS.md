# Calendar status at checkpoint11 — installed candidate11

Device-observation cutoff: **2026-11-05 21:54:28 UTC**. Later continuation runs
are outside this frozen checkpoint.

**Candidate11 is installed; exact event persistence, UI observation and normal
close/reopen are independently accepted. Complete business qualification remains open.** The one
preserving update completed at 2026-11-05 19:09:22.490884 UTC. The installed APK is
2,635,213 bytes with SHA256
`00cb0b0a3e33a0bf79814a83c3c5900a3c10d9c41719d38e1e146a0ae134a85f`.
It remains com.android.calendar, user 0, UID 10061, version 37 and the original
signing certificate. UID, first-install time, CE/DE directory identities,
permissions, CalendarProvider identity, eight empty tables, task 851 and the same
Main generation were verified before and after this single update. No data clear
or rollback occurred. Full identity evidence is in
[install11-identity](install11-identity/IDENTITY_REVIEW.json).

## Actual fault and repair

On candidate10, Core11 entered New event and explicitly created one local
calendar. That write committed, but the App rejected its returned URI because
the generic validator prohibited query parameters. The installed Provider
returns the new ID appended to the original sync-adapter URI, retaining its
query. Core11 stopped, wrote no event, normally closed task 974 and initially
retained only its exact empty calendar. The original failed result remains a
failure; its final nonempty-baseline check did not reach final guard success.

Candidate11 adds a Calendar-specific receipt path bound to the exact internally
submitted LOCAL URI query. The original generic/event receipt validator is
unchanged, and the App still requires a complete provider readback. The generic
ID parser accepts **nonnegative** decimal integers, including zero; see the
[documentation clarification](extension11-id-domain-addendum.json) for the
frozen extension README's stronger wording. This run's actual owned ID was 1.

The acceptance cleanup independently encoded account-name spaces as `+`.
Actual read-only comparison found no row with that URI and exactly ID 1 with
`%20`, using the same full ownership and no-events predicate. A separate guarded,
single deletion at 19:07:25–19:07:28 UTC restored all eight physical tables to
zero. Its original readback and the original failure are retained separately.

## Verification scope

The real build passed 116 Java checks. Relative to installed10, the original
445 classes/2,327 methods and primary DEX are identical. Of 60 restored classes,
58 remain entirely identical in IR; only one Store call changes and the new
Calendar-specific receipt method is added. Manifest, resources and permissions
remain byte-identical. Same-certificate v3 signing and 16 KiB alignment passed.

Actual installed ART verified all 66 new/modified target classes in the isolated
candidate, with unchanged boot/APEX/classpath inputs, current installed10 bytes
and Main guards. This is an artifact verification result, not a running App
business or process-identity qualification. The full scope and original receipts
are in [extension11](extension11/README.md).

## Retained Core12 failure and cleanup

The extension11 bundle froze before Core12 execution. The separate
[Core12 acceptance bundle](core12-acceptance/README.md) retains its actual
19:37:24–19:49:25 UTC run and original lease failure. LOCAL calendar creation,
Cancel/Discard without an event write, and one UI event Save with exact Provider
and detail readback were observed. Edit Save, close/reopen and UI delete remain
incomplete. Two Save decisions stopped before input at the snapshot guard; a
later transport UNKNOWN remains unchanged and has no original journal entry.
Fresh read-only reconciliation found the original unedited event and no Calendar
Activity. Independent exact Provider cleanup completed at20:01:44 UTC, with one
event delete and one empty-calendar delete, eight empty physical tables, task851,
no pending effect and unchanged Main/package/permission identities. That cleanup
does not pass UI deletion or change the original failed result.

## Actual Core13 and its precise qualification

The [Core13 evidence](core13-acceptance/README.md) covers the actual20:18:00–20:20:31
UTC session on this same installed APK. It observed explicit LOCAL calendar
creation, cancellation without an event write, creation of event2, title editing
of that same event, normal close and separate reopen with its exact edited data,
and deletion through the real App UI. Twenty inputs were used. Tasks987/988 were
normally closed; the exact empty calendar was then removed, all eight tables
returned to zero and no UI, Provider or close effect remained pending.

The original overall result is still **FAILED** with
`CRASH_OBSERVATION_WINDOW_TRUNCATED`. Independent inspection of the saved
diagnostics found that the bounded global log omitted the first7.634 seconds of
the run. The retained suffix contains no new selected Calendar crash, but cannot
prove the missing interval. The final eight commands each have their original
successful guarded receipts; that does not manufacture a missing top-level
final guard or a whole-session stability pass.

Root independently accepted only `calendar.persist`, `ui_observation` and
`lifecycle`. The frozen `calendar.edit` requirement includes dates, timezone and
recurrence: Core13 edited the title and retained a null recurrence rule, so that
composite gate remains pending. Repeated-event instances, reminder delivery,
notification interaction, Snooze/recovery, sync, runtime identity, stability and
the complete release scope remain open. No older binary's business review is
inherited, and the whole App has not been declared production ready.

Earlier actual results remain in [extension10](extension10/README.md),
[extension09](extension09/README.md), and their original installation and
acceptance receipts. All 45 Apps remain tracked by the
[current readiness matrix](../readiness-20261105/README.md).
