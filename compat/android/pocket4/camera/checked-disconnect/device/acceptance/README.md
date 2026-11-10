# Camera release08 acceptance runner

This directory contains the reviewed acceptance runner and its executed
revisions. The default invocation prints an inert plan. The original preparation
record remains under `validation-r3/previous-source-manifest.json`.

The latest actual revision03 trial ran at 07:48:15–07:48:19 UTC after shared
storage had recovered. It launched once, observed the Camera connection-error
dialog with the physical USB source absent, pressed no shutter, and normally
closed its owned task. This is a failed current preview and blocked photo flow.
The earlier revision02 live preview remains historical evidence; no trial has
taken a photo. See `../../evidence/camera-accept03-device-unavailable.json`.

`accept_camera.py` requires the separately reviewed `CameraSession` transport in
`camera-install08/camera_transaction.py`, frozen at SHA-256
`b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470`.
It checks the installed Camera APK is the signed release08 artifact:
`0218041bc46f49c0c9622196e2a3610c641e0cc8f12386f23cdd88dc3a3ce18e`,
11,892,407 bytes. It does not install or roll back an APK.

## Actual acceptance sequence

1. Hold the existing nonblocking global UI action lock for the whole trial.
   Enter the fixed current Main session with held namespace/root descriptors.
   Verify the installed APK, package/data identity, diagnostic grammar, and
   photo-mode preference before any UI action.
2. Read only the preexisting MediaStore image IDs and Android task topology.
   Refuse to operate an already existing Camera task. Record the provider's
   existing owner-lock identity without acquiring or modifying that lock.
3. Launch Camera as host user `alex` through the existing native control socket.
   Require a successful receipt for a new task and an exact Camera freeform leaf.
   Save one private, scoped preview and require one enabled semantic shutter.
4. Recheck the current photo mode and owned-task topology. Click the semantic
   `com.android.camera2:id/shutter_button` exactly once. The mode proof reads only
   `camera.startup_module == "0"` from Camera's default preferences through the
   held root; it never changes preferences. Source evidence identifies the
   actual `Keys`, `SettingsManager`, `CameraActivity`, and photo-mode resource.
5. Poll read-only for exactly one new image ID while preserving all old IDs.
   Require a completed JPEG row owned by Camera, a fresh date, and a path inside
   its DCIM/Camera directory or the provider's default Pictures directory in
   revision03. Read only that new file through the held root,
   fully decode it with the already installed Pillow, and record its byte hash.
6. Normally remove only the newly created Camera task once. Verify other tasks
   remain, inspect new provider journal events after this phase's cursor, and
   require actual physical and producer frame counts. Verify the new image's
   row and decoded bytes persist after close.
7. Open one new Camera task again, capture another scoped preview, and recheck
   the same new image row and byte hash. Close only that owned task. Confirm the
   final MediaStore delta, task set, current Main, provider owner, installed APK,
   permissions, and package-data directory identities remain as expected.
8. Compare new Camera UID crash output, package crash/ANR events, and exit info
   against the pre-trial baseline. Unknown diagnostic syntax is a failure, not
   evidence of no crashes. Write a compact summary with actual action counts.

Native launch, shutter, and removal effects are never automatically replayed
after uncertainty. A successful cleanup does not erase an earlier uncertain
shutter. Any terminal exception, including session-exit or cleanup errors,
withdraws success.
Qualification also requires two acknowledged task removals with successful
readback and exactly one shutter. A task that exits by itself is left alone but
cannot pass the normal-close lifecycle check.

## Invocation

Safe local preparation and regression commands:

```sh
python3 -I accept_camera.py
python3 -I test_acceptance.py
```

The root operator may run the following only after the separately reviewed
installation is verified and the source files are staged on Pocket4. Substitute
the actual staged absolute paths and a new, nonexistent private output directory:

```sh
sudo -n /usr/bin/python3 -I /ABS/accept_camera.py --execute \
  --transaction /ABS/camera_transaction.py \
  --output /ABS/new-private-acceptance-directory
```

The transaction hash defaults to the frozen value above; an alternative value
is rejected. The held-runtime reference must remain next to that transaction
module as required by its own reviewed loader. Existing output directories are
not reused. Running requires root for held namespace entry; the native launch
itself uses the verified `alex` caller prefix from the transaction module.

## Evidence and remaining limits

All output is created with private directory/file permissions. PNG previews,
raw UI trees, logs, MediaStore identifiers, and `new-test-photo.jpg` stay in the
private output directory and must not be added to Git. The script never reads
old image bytes or deletes/modifies old images. The one new test photo remains
in Android storage for persistence verification; it is not automatically deleted.

`public-summary.json` contains hashes, dimensions, counts, and verdicts rather
than image bytes or private image paths. Even on machine-check success,
`production_ready` remains false and `visual_review_required` remains true.
The parent must inspect the actual private previews/photo and assess any wider
Camera flows before assigning production readiness.

The provider parser uses the observed JSON grammar from the prior real
`pocket4-live-camera.service` records: `physical_camera_open`,
`physical_camera_closed` with frames/exit, and matching producer
`source_connected` / `source_closed` session messages. Each phase currently
requires one ordered open/close pair. If the new still-capture path legitimately
reconfigures multiple sessions, that observation fails this conservative parser
and must be reviewed from its actual new journal window. No unobserved provider
format or counter is inferred. Historical R14 references are never executed or
used as the current epoch.

`test_acceptance.py` runs 13 local regressions on synthetic records and fake
transport. It covers task ownership, mismatched/uncertain launch receipts,
MediaStore ambiguity and preservation, real JPEG decoding/corruption, actual
provider counts and event ordering, unknown/fresh crash diagnostics, exact
photo-mode typing, no removal replay, and preservation of uncertain shutter
state through cleanup. A self-exited task is preserved but does not qualify as
a normally closed task. The tests do not claim device execution.

`accept_camera_ready02.py` adds a bounded read-only wait for an observed disabled
shutter. Missing controls and actual error dialogs still fail immediately.
`accept_camera_ready03.py` additionally accepts the two exact image directories
above, retaining the ownership, date, single-new-ID and complete JPEG checks.
`test_image_path03.py` runs all 19 inherited and new local controls. The packaged
sources passed those controls in 0.315 seconds; this does not turn the failed
hardware-dependent trial into a pass.

Only the runner, tests, this README, the source-evidence JSON, and the local
validation/manifest are intended as reviewable source deliverables. The
historical files under `reference/` are implementation references, not runtime
dependencies or new execution evidence.
