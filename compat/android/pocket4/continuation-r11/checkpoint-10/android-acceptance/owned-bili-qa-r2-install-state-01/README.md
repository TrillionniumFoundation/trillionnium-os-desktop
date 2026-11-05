# R2 owned QA install plus state, candidate 01

This candidate installs only `org.droidloom.qa.bili.r2` from the actual r2
build01 receipt. It runs one fresh `state` request which never calls
UiAutomation. It does not launch or inspect Bilibili. UID is unknown until the
actual package readback; UID 10164, commercial UID 10117 and legacy helper UID
10125 are rejected. The r1 helper and legacy v2 are not replaced or invoked.

The source/stage/APK/signer values in INPUTS.json are actual root-readback
values, independently checked locally against the full build and stage
receipts. The new source/protocol did not inherit r1 qualification. Its
compiler uses API 31 headers and target SDK 33.

## Narrow delta from actual Install02

The original held R4 transport, all 44 recorder copy pins, Main fence,
action lock, independent CLI ownership and joined command observations remain.
The only operational function change in install_state.py is the rejection of
old r1 UID 10164. The original `cmd package install -R -t --user 0 --pkg` and
cross-user `list packages -u` absence check remain. No unsupported-option
fallback, permission grant, replacement, automatic retry or automatic uninstall
is added. The Main guard does not import a historical package count.

The old host Session shim expected the original adapter's R3 dependency.
The actual r2 adapter already declares R4, so the new short session_binding.py
checks that exact source/R4/package combination and directly constructs its
Session. It overrides no Session method.

Build, stage, package, flow, step and two nonces are newly bound. The original
r1 sources, receipts and failed flows are immutable. Root performs any actual
execution after reviewing the final source manifest and exact request.

## Retention and cleanup

Before installing, the new package must be absent across all actual users,
including uninstalled retained records. The staged signed APK is created in an
exact new held-root directory; cleanup removes only the held file/directory
identities. There is one install command and one state nonce. The installed
base APK is streamed through the held root and checked against actual signed
bytes before/after state, with UID readback and an all-users check. Successful
installation retains this owned QA package for separately admitted UI work.
An unknown or failed outcome is preserved without reinstall/uninstall retry.

No raw commercial UI, feed/account text, microphone, audio, journal, APK bytes
or private signing material is included in this source tree. The supplied
state result exposes accessibility mode booleans and enabled-service digest
and count, not other service names. Whole-App readiness remains unqualified.
