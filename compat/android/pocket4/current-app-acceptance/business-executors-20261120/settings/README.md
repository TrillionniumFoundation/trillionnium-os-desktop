# Settings read-only page consumer

The original Settings contract has three separate gates: supported pages,
reversible setting change/restore, and permission/account interfaces. This
candidate implements only the supported-page flow. Whole-app acceptance and
the other original gates remain false/pending.

The exact selected CP3A Settings APK was inspected with the previously pinned
SDK 37 aapt2. Its manifest exports the launcher alias and five page components.
The System page does not declare a generic SYSTEM_SETTINGS action; the new
consumer uses its actual exported component. English and Chinese page titles
come from the actual APK resources. An unrecognized locale or missing page
content is refused, not called a pass.

The case requires a fresh Main baseline, actual Settings/helper package
identities, two distinct immutable task scopes, the original native launch and
recorded seven-FD transport, and a dedicated adopted native Settings release.
It opens System, Network, Display, Storage and Applications pages inside the
one proven owned task. Each page needs a complete recorder terminal, the same
Main/window/activity, a matching scoped PNG and visible native controls. It
then normally closes the owned task, reopens Settings in a second fresh scope,
and proves the complete original task set, package grants and CE/DE directory
identity remain intact. No setting, permission, account or package write is
available in this policy.

The limit is 600 seconds plus the original absolute 120-second cleanup reserve,
at most two native launches, five fixed page routes and seven observations.
UNKNOWN outcomes do not authorize automatic cleanup or retries. Cancellation,
incomplete host retirement, failed FD closure or missing cleanup prevent a
partial pass. Source/model controls are not runtime qualification.

The dedicated `native_settings_release.py`, native route enum, service unit,
root adoption and canonical Main source migration are not complete yet. The
entry therefore refuses execute before creating an execution marker when that
exact pinned native module is absent. It does not reuse the Gallery or Calendar
profile. `inspect-source` explicitly reports the missing native binding.

`prepare_source.py` reproduces the isolated source preparation. The candidate
does not modify the 13 selected leaves, CURRENT, the active CI, APKs or userdata.
It is intended for the next complete source cohort after the canonical Main
and native Settings profile are ready.
