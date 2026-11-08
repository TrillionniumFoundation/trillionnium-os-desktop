# Pocket4 current Camera video integration

This is the complete current Camera video source bundle for the Linux local
Android repair. It contains the 29 modules consumed by `camera_entry.py`, the
source preparation builder, the video/display wrapper and its finite holder,
and focused host controls. It does not install an APK, start Main, open a camera
or audio device, or grant a runtime qualification.

## What is fixed

`source/camera_decode.py` keeps the original root-owned mode-0400 evidence file
and held descriptor unchanged. It checks the full input SHA and identity, seals
an exact private memfd copy, assigns that copy to UID/GID 1000 with mode 0400,
then closes the writable descriptor and reopens a read-only descriptor for the
owned low-privilege decoder children. Copy and invocation stay inside the
existing phase deadlines and owned reaper. No recording, decode, nonce, URI,
audio source, or playback gate was removed.

`source/camera_video_state.py` accepts either valid order of verified playback
and restoration to the original mode. The actual audio/playback receipts,
closed owned task, preserved state and retired host actors still gate success.
The current strict window and decoder/pixel evidence requirements remain.

The r4 source had independently added a sealed memfd decoder. This bundle
strengthens that implementation with the already-tested read-only descriptor,
UID1000 mode-0400 copy and deadline checks, and adds the state fix. Every final
module is byte-identical to the previously tested independent candidate. The
proof and the exact two-file diff are in `review/r4-byte-equivalence.json` and
`review/r4-incremental.diff`. Earlier tests are identified as tests of that
candidate, not as tests run inside shared r4.

`tools/prepare_camera_video.py` verifies the externally pinned 29-file inventory,
copies the exact bytes into a new directory, and creates the existing formal
`pocket4-current-camera-video-preparation-v1` packet. It then calls the actual
entry bootstrap and holds its complete 32-file source/origin witness. All live
references are under the newly created directory. Historical source locations
are documentary metadata only. The existing `camera_plan.source_packet` and
`create/activate` functions remain the only source-packet/scope contract; there
is no additional recovery scope layer.

`display/video_display_wrapper.py` adapts the qualified photo wrapper to the
actual video entry and two-level acoustic owner. It creates the required
`{"base_plan": ...}` execution request, binds the direct root child to
`acoustic-supervisor/parent.json`, and binds the execute-once claim to that
owner's business worker. Both producer terminals, all three acoustic principals,
complete pipe EOF, cancellation commits, context closures, the exact recorded
URI/playback receipts and the physical device identity must agree.

Sixteen display ownership/channel/heartbeat/cancellation/release methods are
byte-identical to the original wrapper. The display lease implementation is
unchanged. The finite holder has exactly two AST constant changes, both 475 to
665, so its fixed deadline accepts the video wrapper budget. The outer budget
is 20 seconds for readiness, 510 for the acoustic supervisor, 90 for graceful
worker/owner cancellation, plus the original release/retirement/observation
reserve. The caller must reserve at least 675 seconds.

## Validation and its scope

| Evidence | Observed result | Scope |
| --- | --- | --- |
| Original decoder host controls | 8/8 passed | Real root:0400 failure, UID1000 exact-byte decoding, seals, original identity, no leaked FDs, negative media/source/nonce cases |
| State regression | 1 test method, 9 scenarios passed | Synthetic public-API observations of the actual state machine |
| Preparation/entry controls | 8/8 passed | Real temporary files/FDs, formal bootstrap, exact 29-file Camera/Player source packets, stale paths/hashes/roles rejected |
| Display consumer controls | 16/16 passed, 0 skipped | Explicitly synthetic terminal receipts plus real source preparation and formal entry rejection of old request shape |
| Existing acoustic supervisor controls on final 29 modules | 7/7 passed | Actual private processes, credentials/channel/reaper; Main and Pulse backend remain fixtures |
| Video/display outer owned controls | 4/4 passed | Actual root/UID1000 children, SCM credentials, pidfds, source-only entry and 29-file source packet, cancellation and FD/tree retirement |

The four outer controls deliberately remain business failures: missing terminal,
child exit 7, holder loss followed by exact SIGINT and child exit 130, and an
incorrect READY identity which never starts the business child. The display
packets, release observation and business backend are explicitly fixtures.
They perform no DBus, Main, Android, physical camera or audio action and do not
claim a successful real video or display lease.

The two actual host jobs completed naturally with exit 0, durable complete
stdout/stderr, no timeout/cancellation, no OOM/swap, unchanged source bytes and
empty owned children/FD sets. Both used 512 MiB, half a CPU, CPU 19, nice 10 and
64 PIDs. A first outer launch was rejected before test execution because its
new private cwd was not traversable; that failed terminal is retained.

## Create a formal source preparation

After copying this complete bundle to a reviewed canonical location, run the
builder from an accessible cwd. `<bundle>` is that location and `<new-dir>`
must not exist. The builder does not start Main or create a runtime plan.

```sh
sudo -n /usr/bin/python3 -I -B <bundle>/tools/prepare_camera_video.py \
  --source <bundle>/source \
  --inventory <bundle>/reviewed-source-inventory.json \
  --expect-inventory-sha256 2444a7f3dcbeace9a3a9c5b86d2fc815a59ae965b626ddb80ba99b6f4d13520f \
  --output <new-dir>
```

Use the exact preparation SHA printed by the builder for both formal entry
source inspection and the outer wrapper. The default mode is inspection.

```sh
sudo -n /usr/bin/python3 -I -B <new-dir>/source/camera_entry.py \
  --preparation <new-dir>/preparation.json \
  --expect-preparation-sha256 <printed-sha> inspect-source

sudo -n /usr/bin/python3 -I -B <bundle>/display/video_display_wrapper.py \
  --preparation <new-dir>/preparation.json \
  --expect-preparation-sha256 <printed-sha> inspect-source
```

The outer execution input retains exactly five keys: `schema`, `plan`,
`source_preparation`, `automatic_retry`, `whole_app_business_accepted`.
Its schema is `pocket4-camera-video-display-input-v1`; the last two values must
be false. The plan must come from the existing fresh video factory after real
baseline, installed Camera/Player/helper and Main epoch inputs qualify. No such
runtime input is fabricated or supplied by this bundle.

## Reproduce source controls

`tests/test_preparation_entry.py` and `tests/test_video_display_contract.py` run
locally with `/usr/bin/python3 -I -B`. Root-only constructor checks are explicitly
marked and must not be counted as passed if skipped. `tests/camera_video_state_test.py`
uses the current state module in this bundle. The original eight decoder controls
in `tests/decoder_host_controls.py` are preserved byte for byte and need root on
Pocket4 plus `--candidate <bundle>/source`,
`--original <bundle>/tests/fixtures/decoder-before-fix`, and a fresh `--work` path.
They were not redundantly rerun during r4 integration.

`tests/run_video_display_owned_controls.py` requires the declared private H job
resource envelope and the original pinned lifecycle helper. The retained host
evidence includes its actual source hash, job/nonce, source snapshots and all
raw case receipts. Do not run it against real display/Android backends.

## Publication and cleanup

`publish-source-manifest.json` lists source, tools, display and tests for Git.
Raw host journals and generated runtime files are not in that publish list.
`upgrade-map.json` identifies the former flat r2 state/test files and their
current replacements. Review references before retiring those old flat paths;
do not keep the r2 state implementation alongside this current bundle.

`source-bundle-index.json` covers every deliverable file. `review/validation-summary.json`
is the compact machine-readable acceptance record. The raw host evidence is
included for independent readback. Old private work directories and transport
archives are not live dependencies of a newly generated preparation and can be
retired after the complete current bundle and evidence are adopted and active
jobs/open references are rechecked.

Real deployment, a fresh Main epoch, the actual locked display lease and normal
release, a new recording, the current acoustic nonce, full decode and same-URI
playback, and whole Camera business/visual review remain pending. Runtime,
whole-app and recovery qualifications remain false.
