# Owned R4 install and state, once

This is a narrow binding of the already used R3 install/state controller to the
actual newly built `org.droidloom.qa.bili.r4` package. It retains the frozen R4
held namespace transport, original Main guard and action lock, create-only
source/flow/staging, explicit `cmd package install -R -t --user 0 --pkg` and the
same no-UiAutomation state operation. No application launch, UI action, audio,
permission grant, settings write, commercial-data change or old-helper fallback
is included. Older helper packages are untouched and their UIDs are rejected.

All nine QA sources, actual build/stage SHA, eleven successful joined commands,
unchanged tool records, actual signed APK and signer are bound. Compile SDK is
31, minSdk 31, targetSdk 33. The source fix changes condition wait scheduling;
actual Android readiness and Bili playback are not qualified by this build.
The new helper UID must be observed after the exact installation, never guessed.

Installation first requires package absence across every user, including retained
uninstalled records. `-R` explicitly forbids replacement; lack of `-r` alone is
not the contract. Unsupported flags or any command failure remain original
failures without fallback or retry. The installed base APK is read through the
held Main root, matched byte-for-byte to this actual signed artifact and checked
again after the one state operation. The expected inventory change is this
single new owned package; no arbitrary package-count bypass is introduced.

The helper state operation connects no UiAutomation. Exact finish -1, returncode
0, nonce, UID, signed APK and post-command Main fence are mandatory. The original
worker and coordinator finally paths retain first errors, close held descriptors
and the action lock, and retire only the inode-bound temporary APK/directory.
The installed helper is retained for a separately admitted fresh functional flow.
A failed/unknown install is never automatically repeated or uninstalled.

The actual build is `1a1aa29568a-fc05-3e75`; its source manifest is
`e54c6f0a2838f4332287224048c58f2884878b4c7bc7b3fd25be415cd0085c17`.
The independent original R3 buffer failure remains FAIL. Whole-App, playback and
audio qualification remain false. This source/request has not executed Android.
