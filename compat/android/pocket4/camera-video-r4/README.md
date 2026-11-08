# Camera r4 source repair

This source publication snapshot contains all 29 production sources: exactly seven
changes from the owner r4 source manifest, with 22 original files preserved byte
for byte. It composes the frozen current-host migration, r4 decoder corrections,
and independently reviewed Android active-track admission overlay. None of the
three frozen input packages or Pocket4 owner/canonical files was modified.
This package remains reviewable; it is not a final freeze or production device
preparation.

## Source admission and qualification boundaries

The exact 29-source set and the local source-inspection branch passed the
combined local controls. The metadata therefore records:

- `source_admission=true` and `source_inspection_entry_complete=true`.
- `code_entrypoints_complete=false` and `production_preparation_present=false`.
- `runtime_qualified=false`, `whole_app_business_accepted=false`, and
  `device_execution_authorized=false`.
- Actual production reaper and production UID 1000 decoder qualification false.
- Full host PipeWire quiescence, continuous exclusivity, failure-path final
  audio quiescence, inactive-session/audio-focus preservation, and complete
  actual dumpsys ABI qualification false.

The source-inspection tests build temporary local packets with explicitly
synthetic provenance. A synthetic packet's required source-branch flag does
not complete the real Camera entry, recovery preparation, display lease, or
runtime qualification. No production `preparation.json` is included. Fresh
fixed host support, the actual Audio APEX cohort, Main/display leases, real
Camera recording, acoustic challenge, same-URI physical playback, and complete
runtime cleanup still require separately qualified owner work.

## Exact production delta

The original owner manifest is
`/home/alex/work/pocket4-android-final/qualification/camera-video-recovery-current-draft-20261108-r4/manifest.json`,
8308 bytes, SHA-256
`963b8724906da54e70147b3a3268dd29640a85b45b947274fda7d5e61a55c5c4`.
Every production row in `source-manifest.json` includes the original reference,
new length/SHA, change status, and component attribution.

| Changed production file | Bytes | SHA-256 |
| --- | ---: | --- |
| `source/app_common.py` | 38256 | `6003e96be02cd0c6328340865bbb2962d39967f2b823656af258ed5a48f598d0` |
| `source/camera_audio_binding.py` | 18775 | `c8c0c123153a83a2397595d2efcf6ba3b40f60916362403348d1f6f6a57a4754` |
| `source/camera_audio_runtime.py` | 26272 | `b480c7e99cd44bd9ff79e7d95fb87e80f7634c843e8e9c77f3f38ea8ab9f8cee` |
| `source/camera_case.py` | 7576 | `19f015a8dcf836e6aa8160af9566abc04923b1fe9d5fad34bd98e89ec9d883d7` |
| `source/camera_decode.py` | 14597 | `7a42785a9d5d16fbc4644d0db961acd965b42f79dc9a75b2f101d88ab51574a4` |
| `source/camera_entry.py` | 9811 | `55607f576146c9adc8792fdeb510c1992512ac4d782ccd0efcb75415c81ac4f9` |
| `source/camera_video_media.py` | 9197 | `58c5b6508fe23532fe4282c38446e75dfc25800ed6b063691da80bd431f74190` |

The common/entry pair fixes the host-support binding and entry pin while
retaining strict qualification/cohort comparisons. Decoder/case changes latch
UNKNOWN before dispatch, clear it only after proven retirement and complete
outputs, preserve the primary error across evidence-write failures, and carry
UNKNOWN into case cleanup. Media parsing rejects duplicate/non-finite JSON;
probe and decode use the MOV demuxer for the held clip.

The active-track overlay requires a nonempty, complete recognized current
AudioFlinger thread set with exact table counts. It rejects unsupported/unknown
thread kinds, malformed current framing, orphan effects, and inconsistent
active lists. Before and after the successful business path, every parsed
Android input/output track must be inactive. Each recording/playback sample
must have exactly one globally active track, matching the expected UID/PID and
direction, before held-process adoption. Existing process-generation, source,
route, mute, frame-progress, and HAL/helper protocol checks remain.

The 22 unchanged sources include the planner, typed Session, policy, driver,
supervisor, transport, sound preservation, and app profiles. The original
Camera/Player/Camera flow, task ownership, current nonce, source chain,
420/60/510-second budgets, nine-action UI cap, and cleanup gates are preserved.
`camera-video-r4-integrated.patch` is the complete seven-file production delta.

## Raw observations and the limits of the new gate

Bounded raw dumps are saved in the private case evidence directory before
parsing/admission: `audio-flinger-before.txt`, the four
`record-first`, `record-second`, `playback-first`, `playback-second` samples
with `-flinger.txt`, and `audio-flinger-after.txt`. Rejected samples retain
those bytes; an admission JSON receipt is written only after successful checks.

`verify_final()` runs on the successful business path after task/provider
closure. The existing failure-only `Driver.finish()` does not collect another
all-UID quiet dump. An earlier failure cannot report business success, but
`owned_task_cleanup_verified` is not proof of audio quiescence after a failed
run. This separate gate remains false.

AudioFlinger dumps its thread tables sequentially. The observation is not one
atomic snapshot of all track activity, and does not reserve audio or prove
exclusivity between observations. It covers parsed Android active tracks, not
all PipeWire clients, inactive sessions, or audio-focus state. Unrecognized
current top-level output is deliberately rejected rather than counted as idle.

## Fixed C++ basis and projection fixtures

The writer basis is `platform/frameworks/av` commit
`475269ec44acec82792be6b01fb8e16357d4d2c8`. Exact references and source URLs for
`services/audioflinger/Threads.cpp`, `Tracks.cpp`, and `AudioFlinger.cpp` are in
`provenance/audioflinger-fixed-writers.json`; all three local source lengths and
digests were checked during integration. The source establishes the current
thread section, table counts/rows, local-log boundary, and separate historical
thread prefix.

The eleven `.txt` fixtures are minimal text projections of these writers,
with exact hashes and omissions in `tests/fixtures/origin.json`. They are not
captured full dumpsys output. External SimpleLog/getLogHeader formatting and
opaque HAL/FastCapture/effect/scheduler bodies are not completely fixed by the
three C++ files. Passing these controls does not qualify the complete actual
dumpsys ABI or physical audio. The independent peer review and the unchanged
component handoff preserve these boundaries under `provenance/`.

## Tests and exact preservation

The combined run contains exactly **52 tests**:

| Layer | Module/classes | Count | Actual scope |
| --- | --- | ---: | --- |
| Portable host/source | `test_host_support_binding.CameraHostBinding` | 10 | Exact host binding, qualification/cohort rejection, source pins, AST preservation, inert real local source-inspection CLI |
| Portable active-track admission | `test_camera_audio_quiescence.RawAdmission` and `RuntimeAdmission` | 31 | Minimal raw writer projections and real parser/admission methods with a fake Session |
| Linux decoder | `test_camera_r4_decode` | 11 | Eight capture-boundary fault controls and three media controls, including actual local two-FD synthetic MOV probe/video/PCM |

The ten host controls now explicitly fix all seven changed lengths/SHAs,
validate all 29 production rows, and require exactly 22 rows to retain their
original r4 bytes. No permissive exception set replaces the exact pins. The
cumulative test port is in `provenance/host-support-test-port.patch`.

The 31-test quiescence module and its 12 fixture files are byte-identical to the
frozen overlay. Its prior standalone 31/31 receipt is retained as
`provenance/quiescence-component-controls.json` and is not counted again as an
extra run. The 11-test decoder module and business_commands fixture are also
byte-identical to the frozen decoder component. No candidate source, test, or
fixture changed during the new combined run.

The independent actual Pocket4 decoder host controls being prepared elsewhere
are not included in 52, and do not gain qualification from this result. The
prior separate Camera r2 15-test workflow and four out-of-package UNKNOWN
probes are also not part of this count.

## Actual local combined validation

From this directory on Linux with native Python memfd/seal support and
`/usr/bin/ffmpeg` plus `/usr/bin/ffprobe` installed:

```sh
/usr/bin/python3 -I -B -m unittest discover -s tests -p 'test_*.py' -v
```

This command was executed once for the seven-source revision in the local Linux
workspace: **52 tests, zero failures, errors, skips, expected failures or
unexpected successes; exit 0**. The native interpreter was Python 3.12.3,
`/usr/bin/python3` resolving to `/usr/bin/python3.12`, with real memfd support
and all six Linux seal constants. No constants were fabricated, no controls
were skipped, and this is not a Pocket4 result.

`validation/integrated-controls.json` records the actual command, 10/31/11
module counts, output hashes, test/fixture/source pins, and unchanged production
table. `validation/runtime-prerequisites.json` pins the actual interpreter and
ffmpeg/ffprobe tools. Only result metadata was finalized after the run; the
production table, all test sources, and all fixtures remained unchanged.

## Repository test integration

The repository wrapper and required-file registration are included in this change.
Actual native Mac and Git CI results are recorded separately after execution:

1. The portable required wrapper must load only the host module/class (10) and
   the quiescence module's two test classes (31), requiring exactly **41** tests.
   Do not import the Linux decoder module in this portable wrapper.
2. The Linux workflow runs the unchanged decoder entry after installing its real
   prerequisites, and checks exactly **11** tests with zero failures/errors/skips
   and `passed=true`:

   ```sh
   /usr/bin/python3 -I -B tests/test_camera_r4_decode.py --report /tmp/camera-r4-decoder-controls.json
   ```

The report destination must be new. The standalone quiescence entry also uses
exclusive report creation if a separate 31-test execution is needed. Default
portable discovery must not fail or falsely claim decoder qualification on a
platform without Linux memfd/sealing. Required-file registration should include
all three test modules and their fixture dependencies so deletion cannot
silently reduce the executed suite. This package itself makes no Mac or Git CI
success claim.

## Inventory and provenance

`provenance/integration-inputs.json` binds all three frozen components. The
quiescence manifest, original 31-test receipt, fixed C++ references, and compact
peer-review findings are included. `FILES-SHA256.json` lists every package file
except itself and records 29 production files, seven changes, and 22 retained
original files. It freezes this source publication snapshot. The complete production entry
and device preparation remain unqualified.

The package contains UTF-8 source, code-only fixtures, patches, source
references, and compact validation. It contains no APK, binary, media capture,
screenshot, application data, or runtime image.

## Pocket4 host-control dispatch remains unknown

`host-controls/qualifier/` retains the exact five-file actual-host qualifier.
It uses the frozen production decoder and real owned process capture, with
eight distinct controls, a one-CPU / 512 MiB / zero-swap budget, and a separate
systemd deadline. The reviewed stager and manager-readback review are retained.
The qualifier's source inspection passed; it does not supply eight host passes.

The attempted Pocket4 dispatch returned `launch_unknown`. An identical request
with the same idempotency key returned the original job with
`status_unavailable`; the formal cancellation remained `cancel_unknown`. A
separate completed read-only observation found no staging root and no inner
unit at that observation point. This does not supply an authoritative terminal
for the original job, prove that a delayed dispatch cannot occur, or qualify
any control. The public observation records **zero verified host controls**,
with all eight still `not_run` in the preparation's admission state.

Do not execute the archived stager as a fresh-key retry, delete/recreate its
exclusive root, or convert the absent unit's default result into a passing
run. Reconcile the original action through supported process control before
admitting another execution. The original dispatch/cancellation uncertainty
is preserved. Production reaper, UID-1000 decode, live Session, physical audio,
whole application and Android runtime qualification all remain false.
