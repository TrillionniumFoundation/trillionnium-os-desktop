# Camera r4: Android active-track admission overlay

## Outcome

This independent candidate changes only `source/camera_audio_binding.py` and
`source/camera_audio_runtime.py`. It closes the observed source defect in which
an active foreign Android UID could coexist with the Camera/Gallery admission,
and a dump with no recognized current thread could be treated as idle. The r4
originals are unchanged. `camera_sound_preservation.py` is unchanged.

This is an Android **current active-track observation** gate. It does not close
the whole existing-audio-session preservation requirement. Host PipeWire
quiescence, inactive-session/audio-focus preservation, and continuous exclusive
ownership between observations remain unqualified. No Main, Android, host audio,
shared controller, CURRENT, or remote operation was performed by these controls.

`verify_final()` runs on the successful business path. The existing failure
cleanup in `Driver.finish` does not collect another all-UID quiet dump. This
does not permit a failed run to report business success, but
`owned_task_cleanup_verified` must not be interpreted as proof that Android
audio became quiet after a failed run. That failure-path observation remains
outside this two-file change.

## Source changes

1. Require unique, exact, ordered current-section markers and at least one
   complete current thread header. Every current top-level line must match the
   pinned ThreadBase header. An indented Input/Output thread header also fails.
   Current rows cannot be taken from the historical thread log. Unknown thread
   kinds, mismatched direction/kind, MMAP, BIT_PERFECT, orphan effects, and the
   active-list/table-inconsistency warning are refused.
2. Preserve exact per-thread total/active row counts, unique IO handles, and the
   existing row, mute, source, frame-progress and process-generation checks.
   `active_tracks()` traverses all parsed Input and Output tables for every UID.
   `quiescent()` refuses any active row; `owned_track()` requires the entire
   active set to contain exactly the expected app's single row. Both samples
   passed to `advancing()` therefore carry the same all-UID restriction.
3. Preflight and final observation use `quiescent()`. A recording/playback
   snapshot rejects competing rows before guest-process adoption/helper reads,
   then retains the existing held app/HAL identity checks. No business action
   or additional dumpsys invocation was added.
4. Preserve each bounded raw dump before parsing/admission, including refusals.
   Final observation now also has a raw dump receipt. Records bind the raw SHA
   and collection start/end times and explicitly leave host-audio, continuous
   exclusivity and runtime qualification false. Failed samples cannot become a
   positive admission record.

`HeldProcess`, `find_guest`, the helper journal parser and the HAL/helper protocol
window are AST-identical to r4. No signaling, volume writes, session stopping,
or ownership transfer was added.

## Authoritative source basis

Framework commit: `475269ec44acec82792be6b01fb8e16357d4d2c8`.

| Pinned file | Bytes | SHA-256 |
| --- | ---: | --- |
| services/audioflinger/Threads.cpp | 490438 | a5416ff05a3683712075ca1a383a73ebfb9331b18e88bfadfbc6aba2b62a13bc |
| services/audioflinger/Tracks.cpp | 154428 | 420040347f18e8708e2faeec1991c06238a467558190435788492b8e1648b6e2 |
| services/audioflinger/AudioFlinger.cpp | 209703 | 4906b0655b008b9fdb5584bca19128ecbe0beee3ec1105a103f17b4ce06e1a76 |

All three local source files were read and their exact lengths/digests verified.
`AudioFlinger::dump` emits all playback, record and mmap threads before orphan
effects and ThreadLog. `ThreadBase::dump` supplies the common unindented header
and the Local log boundary. `PlaybackThread::dumpTracks_l` and
`RecordThread::dumpTracks_l` emit the total/active counts and four-space row
prefix. `Track::appendDump` and `RecordTrack::appendDump` supply the row formats.
`AudioFlinger::dumpToThreadLog_l` uses the separate `- ` prefix for historical
thread text.

The outer AudioFlinger lock fixes the thread collection while each table is
read under that thread's lock. This is not one atomic snapshot of every track's
activity, and it does not reserve audio against another client starting later.
The recorded collection interval and false continuous-exclusivity flag are
intentional limits.

## Local controls

Executed with bytecode writes disabled:

```sh
python -I -B tests/test_camera_audio_quiescence.py --report validation/controls-run-1.json
```

The actual run completed with exit 0: **31 tests, 0 failures, 0 errors, 0 skips,
0 expected failures, 0 unexpected successes**. The script's main requires all
31 tests and zero skips/expected failures before returning success. A report
path is created exclusively; a rerun must choose a fresh report filename.

The controls cover raw all-UID capture/playback rows, simultaneous foreign
activity in either direction, a second UID or PID, zero/malformed/unknown
headers, unsupported thread types, invalid section order, missing thread ends,
count mismatches, historical exclusion, advancing frames with exclusive first
and second samples, and real preflight/snapshot/final methods with a fake
read-only session. They also check that failure dumps are retained, positive
records are withheld, existing qualification/Main-generation checks remain,
and held app/HAL checks still run for an accepted sample.

The eleven committed `.txt` files are **minimal raw-text projections of the
pinned writers**, not captured full dumps. `tests/fixtures/origin.json` records
each raw file's digest and exactly what is omitted. In particular, the three
available C++ files do not define the complete SimpleLog formatter,
IAfTrack/IAfRecordTrack getLogHeader strings, or all HAL/FastCapture/effect/
scheduler writers. The fixtures omit those opaque bodies rather than guess
their ABI. Numeric thread-type tokens are illustrative; these controls do not
validate an enum-number ABI.

Accordingly, these results are not complete real dumpsys ABI qualification,
physical sound qualification, app acceptance, or proof of an idle host.
Unrecognized current top-level output is deliberately refused. A real dump
containing such output can therefore fail even if its device is otherwise
usable; extending support requires the exact corresponding writer/source and
new raw controls, without treating an unparsed section as idle.

## Exact overlay and preservation

| File | r4 original SHA-256 | Candidate SHA-256 |
| --- | --- | --- |
| camera_audio_binding.py | 865c1dcef9559f69062b0430e585eb85cc8131396a614dd51c709f5d8ef968dd | c8c0c123153a83a2397595d2efcf6ba3b40f60916362403348d1f6f6a57a4754 |
| camera_audio_runtime.py | 00e4643c544b6d6771772b8830f84f865282013379941e1da83e52df08fe59f9 | b480c7e99cd44bd9ff79e7d95fb87e80f7634c843e8e9c77f3f38ea8ab9f8cee |

`audio-quiescence.patch`: 12485 bytes,
SHA-256 `e8f3dc1be9f12f10851539e8a63fc99dcf424a0c5c65ba049e071a48c56ef9a9`.

`validation/source-review.json` records original preservation, three C++ pin
checks, the unchanged ownership/protocol ASTs, and zero `.pyc` derivatives.
This is a two-file overlay, not a complete 29-file Camera publication package.
The parent must compose it with the independently reviewed decoder and
common/entry work, retain the whole-app blockers, and bind the resulting exact
source set before any separate runtime qualification.

## Independent review

The runtime acceptance agent independently read the same two candidate hashes
and the three fixed C++ writers, checked remaining consumers across the 29-file
Camera set, and compiled that composed set in memory without importing it or
accessing Main. It found no false-idle/foreign-active admission or API-compatibility
blocker within the fixed-writer assumptions. It did not rerun the 31 controls.
The review records the failure-cleanup boundary above and the complete-dumpsys
ABI limitations, rather than claiming them closed.

Review evidence:
`/workspace/scratch/347ef2dfe9ad/runtime-acceptance-audit/camera-audio-quiescence-peer-review/review.json`,
SHA-256 `37a47878e3d7e64d7f52bb54da0f8a78cd0a94bd46374e999a6ac70f21a4fb34`.
