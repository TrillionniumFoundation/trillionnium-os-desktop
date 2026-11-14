# Camera r4 source controls for the single current Camera implementation

The current Camera implementation is
`compat/android/pocket4/closeout-20261107/continuation/camera_video_current`.
This capsule retains its exact 29 production source files as test inputs,
together with source provenance and historical qualification evidence. It is
not a second runtime installation. The portable wrapper requires all 29 names,
byte lengths and SHA256 values to match the canonical source directory and its
fixed reviewed inventory before it imports any test module.

The publication base is commit
`f9c506431b389c941fbb05f5875166fcd8a7b763`. The preceding merged source included the
current owner's sealed UID/GID 1000 input and playback/restore ordering fixes,
the earlier host-support and retirement fixes, and failure-path Android audio
quiet verification. No historical host result is transferred to these merged
bytes. Production admission, actual Pocket4 reaper/UID1000 decoding, runtime
qualification and whole-app business acceptance remain false.

## Production changes and preserved boundaries

Relative to the original owner r4 source inventory, nine files change and 20
are byte-identical. `source-manifest.json` records every current and original
reference. The exact changed names are:

| Source | Change |
| --- | --- |
| `app_common.py`, `camera_entry.py` | Current host-support binding and exact qualification comparison |
| `camera_audio_binding.py` | Current Android AudioFlinger track/session attribution and strict quiet projection |
| `camera_audio_runtime.py` | Existing success-window checks plus one bounded failure-cleanup Android quiet query |
| `camera_case.py` | Preserve the original business error and expose the separate failure-cleanup result |
| `camera_decode.py` | Merge owner sealed read-only input/deadline checks with UNKNOWN, retirement and first-error preservation |
| `camera_video_driver.py` | Invoke the failure-cleanup verifier only after the original known-retirement prerequisites |
| `camera_video_media.py` | Force MOV parsing and complete bounded video/audio decoding |
| `camera_video_state.py` | Accept both valid playback/Photo-restore orders while preserving all final state and retirement gates |

The merged decoder is 16169 bytes with SHA256
`7421cdd38bd45eff8c0697ce11b1372958a4a5f749c8097e3c0203ed5758056b`.
The state file is the owner's exact 21072-byte source with SHA256
`68c6369a068d822b0ea4e849cf2172d0180bbe69b3c576e7aa74ba2f6e7d66fc`.
The owner's sealed-clip helper AST is preserved. It creates a sealed input
owned by UID/GID 1000, sets mode 0400, reopens it read-only, requires all four
seals and bounds both copying and writing by the current deadline. The merged
call path also verifies the held original and latches UNKNOWN before capture
can dispatch. Only strict actual retirement and acquired byte outputs can
clear that latch. A later evidence-write exception cannot replace an earlier
capture or post-guard exception.

Failure cleanup has a narrower claim than successful video acceptance. It
requires the complete preflight, final-cleanup phase, no pending business
effect or unknown host/decoder result, known task cleanup and exact completed
acoustic actor prefixes. Each completed acoustic actor must retain its
original finish receipt, nonce, parent/phase identity, EOF and retirement
proof. The additional query uses the existing typed Session/Flow/Policy path;
raw output is saved before parsing and quiet verification. It observes one
Android AudioFlinger cleanup sample. It does not supply the two successful
business windows or prove host/PipeWire quiet, continuous exclusivity,
inactive-session preservation or audio-focus preservation.

## Actual source-control results

The preceding merged capsule was exercised by a new local 70-control run,
with zero failures, errors or skips and unchanged source/test inputs:

| Family | Count | Execution scope |
| --- | ---: | --- |
| Host-support binding | 10 | Actual source dispatch and inspect-source CLI; inert baseline/collector inputs |
| Android audio projection and quiescence | 31 | Actual parsing and admission methods with fixed text/transport fixtures |
| Failure-path Android quiet cleanup | 18 | Actual Session/Flow/Policy/Driver/Case methods ending at fixture transport |
| Linux decoder component controls | 11 | Retirement fault fixtures plus actual sealed memfd and local synthetic ffprobe/ffmpeg controls |

`validation/union-controls.json`, its stdout/stderr and
`validation/union-source-manifest-tested.json` retain that run's exact inputs
and result. The subsequent manifest edits describe those results; they do not
change the tested production files or tests. The older
`validation/integrated-controls.*` records still describe the earlier
52-control snapshot and are not used as evidence for the merged source.

The portable wrapper explicitly loads 59 controls. The separate Linux decoder
step still requires exactly 11 controls. The canonical source-control runner
executes a separate 38: 11 preparation, 18 display-contract and nine state
controls. Its exact report is in canonical
`review/merged-source-controls.json`. The state controls are counted only
there. They include both valid operation orders and strict missing, foreign,
unretired and unacknowledged state rejection. These source controls do not
open Main, Android, physical audio devices or a live business Session.

The call-boundary decoder fixtures use a real read-only sealed memfd owned by
the current test UID and injected retirement responses. They do not exercise
the production UID1000 constructor or original reaper. Two media controls run
actual local ffprobe/ffmpeg on temporary synthetic content. That is a local
Linux component result, not a Pocket4 binary or camera qualification.

## Environment refusals and historical host evidence

A real nonroot attempt stopped at `setpriv` with exit 127 before Python or any
of the 59 tests started. The namespace maps only UID/GID 0 and denies
setgroups. The original refusal and the explicit mapping observation are kept
in `validation/portable59-nonroot.*` and
`validation/nonroot-admission-environment.json`. No actual nonroot or native
Mac success is claimed. The final 70-control source run used the current local
UID 0; UID-dependent entry conditions in source fixtures are explicitly local
mock boundaries.

An unmocked call to the merged sealed-input helper separately refused
`fchown(1000,1000)` with errno 22 in this namespace. Its record,
`validation/local-sealed-input-observation.json`, confirms that original file
bytes/metadata were unchanged and helper descriptors were closed. Recording
that refusal is not a passing UID1000 control and is not included in the 70.

Zero actual controls are verified for the original eight-control Pocket4
qualification preparation; all eight retain `not_run` in that preparation's
admission state. Its original dispatch remains unknown. The frozen runner,
source packet, stager and public observation under `host-controls/` retain
their original bytes and historical source binding. In particular, their old
decoder pin is not relabeled as the merged decoder. The reconcile observation
that the root was absent and the unit was not found does not prove that the
original dispatch never executed or that cancellation succeeded.

Canonical historical decoder/display receipts likewise retain their original
scope. The new canonical producer and display consumer bind the current
inventory and entry and explicitly refuse to inherit old host qualification.
Fresh source-bound preparation and actual owned execution are still required
before any device or business acceptance.

## Source integrity and use

`FILES-SHA256.json` inventories every capsule file. The portable wrapper pins
that inventory, checks the complete file/directory set and every text digest,
then requires the canonical inventory and source bytes to match. Integrity
and count gates use explicit exceptions and remain active under Python `-O`.
Six additional source-integrity controls passed: the actual complete pair,
rejection of the old canonical inventory, a same-length source byte change,
a missing file, an extra file and a divergent capsule source pin. Their report
is `validation/canonical-source-guard.json`; these are separate from the 70
component controls. Reviewed patches use zero-context unified diff format so
blank context markers do not introduce trailing whitespace. Frozen input
packages and all production/test bytes remain unchanged by that formatting.
The workflow preserves the existing Linux decoder step and adds the exact
canonical 38-control source step. `sudo` in the latter supports real temporary
root-owned preparation construction; it grants no Main or Android action.

The original published manifest remains byte-identical at
`origin-source-manifest.json`. The failure-quiet suite explicitly requires
five changes relative to that a355 snapshot and pins the new decoder/state.
The host-binding suite separately requires nine changes and 20 unchanged
files relative to original owner r4. The two comparisons describe different
baselines and are both deliberate. `provenance/owner-merge-inputs.json`, the
owner decoder patch and the complete r4 patch record their source lineage.

This is a source publication and test-evidence capsule. Full Camera video
entry admission, physical input/output and same-owned-URI playback, current
display lease, recovery, complete full dumpsys ABI and whole-app business
acceptance remain pending. No success dictionary, missing-dependency bypass,
stub, relaxed retirement gate or removed negative control supplies those
results.

## Current guest-credential successor

The four credential-observation modules now match the canonical successor
`12c7591d2491d346cda679cd1f314cba375f54e6bab7809e6ab7352c4ec18181`.
Camera/Gallery host directory ownership and audio-process/socket credentials
are mapped through the held Main UID/GID namespaces. No identity fallback
is added to production. The existing quiescence fixture declares its identity
map explicitly; the canonical suite separately exercises mapped and negative
cases. All 29 modules must still match the canonical bytes before import.

The canonical gate now expects 59 controls in four suites. This capsule
still expects 59 portable controls plus 11 Linux decoder controls. Older
reports above keep their original source bindings. The immutable original
AST pins remain in place; a separate fixture records the reviewed credential
successor after removing only the already-tested failure-cleanup additions.
Current tests continue to exercise the failure path, its bounds and denial
behavior. These checks provide no Android, hardware or whole-app acceptance.
