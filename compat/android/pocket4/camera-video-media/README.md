# Camera owned-video decoder component

This candidate implements the missing held-clip/full-decoder component from
`camera-video-recovery-current-draft-20261108-r1`. It does not complete the
Camera video or recovery gate. `code_entrypoints_complete`,
`runtime_qualified`, and `camera_video_verified` remain false.

## r2: precise sealed-write negative control

Ubuntu CI run `42476447626`, job `128718754655`, commit
`5c5ea2665df03ab992ce62cc923eba9846a8d6ae` actually ran all 15 r1 controls.
Fourteen passed, including complete probe/video/PCM/nonce decoding and the
real delayed-child UNKNOWN control. The seals negative control failed at
its final strict identity verification.

A real local memfd experiment confirmed the cause: denied `write`/`pwrite`
returned `EPERM` while changing `st_mtime_ns` and `st_ctime_ns`; size, complete
content SHA-256 and all four seals remained unchanged. Denied shrink/grow
left metadata unchanged in that experiment. Production correctly rejected
the changed complete identity.

r2 changes only that test and its documentation/evidence. All four
production source files retain their r1 hashes. After every denied
operation the test checks the exact errno, content hash/size, all seals,
read-only mode, non-inheritance, FD/path identity and original source.
Only actual mtime/ctime changes are allowed in this negative experiment.
The original identity is never rebased: if it changed, `verify()` must
raise exactly `SAME_READONLY_SEALED_VIDEO_AND_HELD_ORIGINAL`; otherwise it
must succeed. A generic exception cannot pass. The actual Ubuntu rerun of
all 15 r2 controls remains required.

## Source change

`source/camera_video_decode.py` opens only the current typed-policy-owned video
through the already held Main target. It copies at most 128 MiB to one memfd,
adds WRITE/GROW/SHRINK/SEAL seals, reopens it read-only, and checks the original
file identity, read-only descriptor, all seals and complete SHA-256 before and
after the three fixed decoder commands. A final named-source reopen rejects
replacement of the original clip.

The child reads the exact controller `/proc/<getpid>/fd/<fd>` with
`pass_fds=()`. The public recorder's zero-or-seven FD rule is unchanged. No
Main authority FD is passed to ffprobe or ffmpeg. The fixed MOV/MP4 demuxer,
full video framemd5 output, frame count, bounded mono PCM, duration, private
output hashes, empty error stream, zero exit, current guard and actual child
retirement must all agree. The active plan must pin both host decoder files.

Every recorder failure closes the real source-bound recorder bridge and
poisons or seals target admission, preserving the first hold evidence and
the original command observation. If retirement is unproved, the original
argv FD stays open in `recording.decode_held_clip`; ordinary `close()` refuses
to release it. Reusing that descriptor number while a late child could still
open it is forbidden. This bounded hold contains one clip and two data FDs;
it requires explicit reconciliation or controller exit. Known-retired
failure can close the descriptors but still seals admission. No automatic
retry, rollback, Android task removal or UID cleanup is introduced.

`Recording.saved(row, decode, ...)` is replaced by
`Recording.decode_saved(session)`. The state transition requires the actual
decoder entry and checks nonce, URI, file size/hash, scope, phase, epoch,
owned task, descriptor closure and no unknown outcome. Existing fresh
CAMCORDER/HAL/physical-source, negative/decoy, same-URI playback and output
gates remain separate and unchanged. `camera_audio_challenge.py` is byte-for-
byte the original source.

## Integration still required

There is no `camera_video_session.py` in this candidate. The existing photo
Session, `camera_photo` plan and image-only typed policy remain photo-only;
the new entry rejects them before I/O. A real video Session must provide:

- Its source-bound class in `components['camera_video_session.py']`, the same
  `Recording`, the real Camera flow, current phase/epoch and whole-case lock.
- `video_ids_before`, `video_ids_after`, `video_id`, `owned_video`, and
  `owned_video_ref` from actual typed MediaStore reads after known native
  start/stop ACKs. There must be exactly one new completed Camera-owned row.
- `active['video_decoder_tools']`: `ffmpeg` and `ffprobe`, each an exact
  `{path, bytes, sha256}` reference to `/usr/bin/<name>`, admitted by the real
  active plan. CI-runner tool references cannot substitute for Pocket4 pins.
- The existing full `verify_runtime()`/`guard()`, phase-cropped
  `PhaseCommands`, original protected PIDs and current owned-task claim.
  The real `RecorderBridge` may be bare or inside the existing
  `ImageRecorder.real`; only its exact class/flow/binding is trusted.
- Explicit handling of retained unknown decoder FDs during reconciliation.
  A phase timeout does not prove a child retired or authorize automatic FD
  release, task cleanup, or another video attempt.

Actual CAMCORDER input binding, fresh acoustic companion, same-owned-URI
player transition and physical output, permission/provider/orientation
recovery, and whole-case cleanup still require the real video integration.
The Camera UID 1000 Pulse actor (`emit|listen NONCE DEADLINE_NS PARENT_PID FD`)
and the separate UID 1041 main-bound Audio helper
(`record-challenge|capture-only|match-recorded`) are different interfaces;
this component does not substitute one for the other or run either client.

## Mandatory Linux CI gate

Run on the Ubuntu runner with Linux seals, a matching PID/proc namespace,
`/usr/bin/python3`, `/usr/bin/ffmpeg` and `/usr/bin/ffprobe`:

```sh
/usr/bin/python3 -B tests/test_camera_video_decode.py --report /tmp/camera-video-controls.json
```

The script requires **15 tests**, zero failures/errors/skips, and exits
nonzero when environment requirements are missing. The original 13 controls
are retained; two added controls cover an actual delayed child reading the
held descriptor after injected UNKNOWN, and failure-fence/retirement receipt
negative cases. Eleven tests exercise Linux descriptors/actual synthetic
decoding; four are pure rejection controls. Source and runner-tool hashes
are recorded. Temporary H.264/AAC media is generated in `TemporaryDirectory`
and removed; no MP4, PCM, binary, pyc or runtime controller is published.

The local cloud surface cannot run the exact production path: its Python
PID has no corresponding `/proc/<getpid>/fd` directory. The earlier full
attempt failed, and the final four pure controls and all five Python AST
parses passed. `validation/local-controls.json` records these facts without
claiming the Linux gate passed. CI must run all 15 tests; no PID fallback or
successful skip is allowed. macOS may verify source integrity only.

Synthetic host results establish this component's boundaries, never real
microphone, Camera capture, Main, Android playback or Pocket4 qualification.
`origins.json` identifies exact original and integration-contract sources;
`source-manifest.json` gives the strict nine-file text publication set.
