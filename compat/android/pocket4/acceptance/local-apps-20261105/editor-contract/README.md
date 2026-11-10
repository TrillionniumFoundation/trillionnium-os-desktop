# Actual owned editor input and lifecycle

Editor03 completed two real input rounds on the installed Editor Contract QA
APK. Twelve inputs exercised Chinese text, accented characters and an emoji,
two physical Enter commands per round, one trailing emoji deletion and clear.
Each Enter command produced two editor-action callbacks, for observed counts
0 → 2 → 4. Both owned tasks closed normally; a separate launch used a fresh nonce
as required by the fixture. Both exact record/claim pairs were removed. The APK,
UID, version, Android user, Main epoch and permission state matched before and
after. Fresh exact-UID diagnostics found no crash or ANR and recorded two normal
close exit events.

## Original failures and the narrow correction

Editor01 made one successful Unicode set-text, then stopped before keyboard
dispatch with STALE_FRAME. The saved before/fresh observations have different
pixel/scope digests but the same window context and native editor identity/text.
The cause of the repaint was not established. Keyboard events now bind the
actual focused editor plus fixed window, task, context, geometry and App nonce;
they retain the two fresh captures and final focus checks. Pointer and set-text
snapshot guards were unchanged.

Editor02 then stopped before a key with KeyError(display_id): the adapter had
mistakenly treated a compact WindowManager focus record as full native window
metadata. Editor03 validates those two actual schemas separately. Missing fields
are never fabricated. Earlier local mocks had not represented that compact
schema. The original failed results remain failed. Separate zero-input cleanup
jobs verified the closed tasks, exact APK/UID and own nonce files before deletion.

The installed fixture has no TextWatcher; its journal text_length is updated
only by recorded callbacks. The old zero journal lengths do not contradict the
successful native Unicode readback. All six installed classes and the manifest
were reviewed; their hashes are retained in installed-contract-review.json.

## Reproduction and scope

Run `python test_editor_key03.py` for the packaged eight local boundary tests.
The fixture includes only the actual controlled editor node and selected target
metadata. It contains no screenshot or unrelated window tree. Counterexamples
cover changed context, native field value/focus, second editor, task/window/
geometry changes, forbidden keys and unknown-dispatch non-replay. The executed
runner, initial runner, narrow diff chain and exact cleanup sources are retained.
These fixed-device acceptance sources require their pinned private session
dependencies and are not standalone installers.

Only UI observation and the tested separate-task lifecycle receive gate credit.
IME composition, selection ranges/paste, resize/focus transitions, configuration
recreation and complete signing/engine/resource/stability/release coverage are
still open. Editor Contract QA remains one of the 45 tracked Apps.
