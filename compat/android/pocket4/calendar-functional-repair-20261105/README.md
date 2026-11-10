# Calendar functional restoration candidate

This work repairs the exact captured Calendar APK
`7522e88fe03f4997513b0e03591da215b8ebc67f6c933939a73addc3c75495a9`.
Its single DEX is `ad94f4234e06c7b97ff5f4631fadd22ed7fc03f01187ded30f3c5c3125b194d8`.
It contains 445 classes. The manifest names a missing event editor and a missing
SnoozeAlarmsService; its existing AlertReceiver only logs and returns. The
original EventInfoActivity also casts a URI path String to Long. These findings
come from the installed bytecode, not a presumed match to an AOSP branch.

The historical AOSP minimal-calendar change explains the missing feature set,
but an exact installed Java source commit has not been established. New code
uses the observed ABI and the public Android SDK. This is an incremental APK/DEX
build, not a clean AOSP application build.

## Functional scope

The candidate provides an actual event form and detail screen, with user-driven
Save, Cancel, Edit and confirmed Delete. Provider writes use no-yield batches
with original calendar/event/reminder assertions. A response that cannot prove
the result of a write blocks repeat submission. Repeating event exclusions and
existing reminders remain unchanged unless the user explicitly chooses to
replace them.

The zero-calendar screen offers explicit local-calendar creation. It does not
create a Calendar row at installation or in the background. It registers no
AccountManager account or sync adapter. A LOCAL calendar uses the Provider's
normal account-scoped collection API only after the user's confirmation.

Reminder delivery consumes CalendarProvider's existing CalendarAlerts and
EVENT_REMINDER protocol. Notifications use standard title/text plus immutable
Open, Snooze and Dismiss PendingIntents supported by the actual notification
bridge. Ordinary future event reminders are not mirrored by an App timer.
Snooze creates a scheduled CalendarAlerts row and a one-shot reminder intent.
Repeated broadcasts use provider state and stable notification tags. These code
properties are not a substitute for actual delivery, sound or persistence tests.

## Build provenance and current boundaries

Build04's complete original input and real failure are preserved in
`source04-frozen.zip`, `SOURCE_PINS04.json` and `build04-result.json`. Its javac
bootclasspath lacked the real SDK `core-lambda-stubs.jar`; the build stopped
before producing an APK. Build05 uses the independently pinned real compiler
dependency, whose SHA256 is
`48ebd3b6614a8e4367d1dbda1222aed5ffb6b874214922412af5c9fbcd5e877a`.

Build05 completed on 2026-11-05 at 15:12:01 UTC with authoritative exit 0 and
complete durable output. Its exact sources are in `source05-frozen.zip` and
`SOURCE_PINS05.json`. The 17 production draft checks and 12 post-write receipt
checks passed against the real compiled classes. Javac, D8, smali assembly,
roundtrip verification, same-certificate signing and alignment all succeeded.
Across the original 445 classes and 2,327 methods, only the 13 reviewed method
bodies and EventInfoActivity superclass changed. The comparison retains branch
destinations, exception coverage, annotations, fields and method membership.

All non-DEX content of the 663 original payload entries was verified
byte-identical, including the manifest, permissions and resources. The signed
candidate is 2,622,925 bytes with SHA256
`8494f5d860da36182b70f3263d0f5f0488dd97936cda83fb55a7da21e1ca8571`.
It retains certificate
`a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc`,
passes APK v3 verification and 16 KiB alignment, and adds the new code in
classes2.dex. Build05 input/tool postchecks passed; peak memory was 584,015,872
bytes within 768 MiB, with no memory.max or OOM events. Device ART validation,
UI create/edit/cancel/delete, ordinary zero-state use, provider persistence and
reminder delivery remain separate gates.

The compiled Build05 source includes a narrow Snooze ordering correction:
the one-shot system PI is armed before the row transaction, closing the
commit-to-registration process-exit gap. Build04's original input and any result
remain unchanged. Future Snooze recovery across a device reboot still requires
the actual Provider reset/recreation behavior to be accounted for and tested;
a durable alerts row alone does not prove a surviving timer.

No Calendar candidate has been installed and no whole-app production readiness
claim is made by these source or host-build artifacts.

## Build06: occurrence details and retained runtime hold

Independent source review found that Build05's detail route dropped a repeated
event's selected occurrence timestamps and displayed the series start instead.
Build06 retains the actual controller start/end ABI and the existing EventTime
URI input contract. The Provider must confirm the exact event/begin/end tuple
before it is shown. A separate display draft holds that occurrence; the writable
series snapshot is unchanged and the edit button explicitly says “Edit series”.

Build06 completed at 15:20:11 UTC, exit 0 with complete durable output. Its 22
draft, 17 event-reference and 12 post-write-receipt checks passed. The same
445-class/2,327-method roundtrip, 13-method change boundary, 663-entry payload
checks, input postchecks, original-certificate v3 signature and 16 KiB alignment
all passed. The candidate is 2,622,925 bytes, SHA256
`cf06143a7f90aa28607dd32e85a41b897ef4634fc602c50da47a9a1352e095f7`.
Exact sources are frozen in `source06-frozen.zip`; Build05 remains preserved.

The local `calendar_install06.py` prepares one data-preserving update and is
inert by default. It retains the frozen b227 Main guard, requires the actual
original APK/UID/permissions/data directories, a zero Calendar Provider baseline,
no Calendar task, the shared UI lock, fresh signature checks and one durable
install intent. Unknown results are reconciled only by later reads. It neither
clears data nor writes provider rows, and it has no automatic rollback.

No install or UI action is currently scheduled: the coordinator observed
`MAIN_LIMITS_CHANGED` in another flow before Android commands and has held all
new Main operations while investigating. The guard is not bypassed or rewritten.
