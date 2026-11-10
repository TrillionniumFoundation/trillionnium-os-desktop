# Calendar 07: recover only real user snoozes

This is an additive, uninstalled Calendar repair candidate. The previously frozen build04, build05, build06 and checkpoint8 artifacts are unchanged. Build07 completed against the actual pinned SDK and toolchain, passed 82 host checks, and produced the same-certificate APK `3feed84a217f333639bdb14ac42c70b0bcf0a48b8b3458ebc5183bfc6f7596fd` (2,631,117 bytes). This result is not Android runtime or whole-app production qualification.

## Actual defect and repair

The captured CalendarProvider APK and DEX show that its reset path deletes every scheduled CalendarAlerts row (`state=0`), including a future user snooze with `minutes=0`. Its ordinary reminder search derives alarm times from Instances and Reminders; that search cannot reconstruct a user's arbitrary ten-minute delay. Candidate06 had a row and a one-shot alarm but no independent persisted user request. The exact selected methods, source hashes and host-only SQL counterexample are retained under `provider-methods/` and `evidence/installed-provider-snooze-findings.json`. No reboot or live provider reset was performed to obtain this evidence, and the complete asynchronous boot/job chain was not independently decoded.

Build07 adds a private authorization journal created only by an authenticated Snooze action or the existing non-exported legacy Snooze service contract. Each request binds a random nonce, event and occurrence, a hash of the original event/calendar snapshot, the original fired alert's complete identity, and the requested absolute due time. The request is committed before the provider change. Ordinary future reminders remain the existing CalendarProvider's responsibility.

The initial provider batch asserts the unchanged event, calendar and source alert, asserts absence of the actual unique target key, inserts the snooze and dismisses the original alert in one no-yield transaction. A wakeup can adopt one exact existing target or reconstruct a previously confirmed request after a scheduled-row reset. It does not repeat an unconfirmed initial mutation. Unknown acknowledgements are reconciled by exact provider state, including creation time. The compound case in which an initial batch commits, its target is reset, and confirmation has not yet been persisted stays explicitly unknown; the code does not invent a successful request.

Recovery intents are explicit, immutable, bound to both the private action token and a live private nonce record, and carry no caller-chosen event or timing instructions. Changed/deleted events cancel recovery. A missing source cannot authorize reconstruction; cancellation of a remaining target requires its previously confirmed ID and full identity. Cancellation is persisted before the provider update so a delayed wakeup cannot resurrect it.

An alert's `FIRED` state alone does not retire the recovery record. The same confirmed target must have an active app notification, and the source/event identities must still match. This covers interruption between promotion of the row and publication. The existing notification cap cannot silently retire an unpublished snooze. Repeated wakeups use the same PendingIntent identity, and due recovery is bounded. Exhaustion or ambiguity produces a status notification rather than repeated uncontrolled writes.

## Build and preservation evidence

The real host job `1a1ac8a5de4-fc05-551d` finished successfully on 2026-11-05, from 16:28:41 to 16:28:56 UTC. `evidence/build07-observed.json` binds the original full receipt by hash and includes the actual command outcomes, dependency hashes and resource events. The tests comprised 22 event-draft checks, 17 event-reference checks, 12 provider-receipt checks and 31 snooze-policy/publication checks. The latter execute the production pure decision policy; they are not Android provider, boot, AlarmManager or notification-delivery tests.

All 445 original classes and 2,327 methods were compared through a complete smali assemble/disassemble round trip. Only the previously reviewed 13 target methods and the EventInfoActivity superclass change remain in the original DEX. The additional implementation lives in the new DEX. All non-DEX payloads among the original 663 retained ZIP entries are byte-identical, including the manifest and resources. The APK passed the original certificate's v3 signature verification and 16 KiB ZIP alignment. Build input and tool hashes were checked again at completion.

The host build used one CPU (20), 768 MiB maximum memory, zero swap and 128 tasks. Peak memory was 597,774,336 bytes; memory max and OOM events were zero. It executed no Android command, installation, UI input or provider mutation.

## Prepared execution, not executed qualification

`execution07/` contains an inert-by-default update controller and the first-use/single-event UI controller. The narrow execution diff binds the exact build07 APK and the separately approved runtime profile (`e65a47…` transport and `91c7a4…` activation). The original transport and guard sources remain unchanged. The profile follows the coordinator's measured 6144-task configuration; no script in this bundle changes Main limits.

The installer performs one same-certificate update and exact readback, preserving app/provider identity, existing permissions, zero provider baseline and task set. An unresolved install is not retried or automatically rolled back. The UI round covers an explicitly created LOCAL calendar in the normal zero-calendar first-use screen, cancellation of an unsaved event, creation/edit/details/close/reopen/UI deletion of one owned event, and exact empty-calendar cleanup. Its 14 host checks passed, but the controller has not run on Android. It holds the common UI lock and held runtime descriptors, requires current observed controls, and never replays an unknown Save/Delete.

Recurrence, authentic reminder actions, ten-minute Snooze, actual host delivery/audio and boot/reset recovery still require separate scoped device evidence. The pending boundaries are recorded in `SCOPE.json`. Data preservation claims concern verified identity and the stated provider baseline, not all private preference bytes.
