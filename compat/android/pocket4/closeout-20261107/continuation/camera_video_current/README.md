# Pocket4 current Camera video: combined source

This is the canonical Camera video source for Pocket4's Linux local Android repair.
It combines the current-host and audio/decoder admission changes from `a355e81`
with the sealed read-only decoder input and state restoration changes in `f9c5064`.
It also includes the bounded Android quiet check on a failed business operation.
The guest-credential successor changes four runtime modules to compare host
observations with IDs mapped from the held Android Main. The other 25 modules
retain their preceding bytes. The 29 modules in `source/` are one exact inventory. The r4 test capsule must
contain the same 29 bytes; its CI entry refuses a divergent canonical source.

**This is source integration. Android deployment, current Main, real display and
audio operation, Camera recovery, and whole-app acceptance remain unqualified.**
A source preparation is not permission to execute a runtime plan.

## Combined repairs

- The common/entry support binding accepts the exact current host cohort while
  still rejecting an old cohort or altered qualification. Both Camera and Player
  role packets must consume every current source byte.
- The decoder copies the original held root-owned evidence into a private sealed
  memfd, assigns the copy UID/GID 1000 and mode 0400, closes its writer and reopens
  a read-only descriptor. The original evidence and its descriptor stay unchanged.
  Copy/write deadlines, all four seals, full SHA, original identity and explicit
  descriptor inheritance gates remain. Dispatch starts with UNKNOWN latched;
  only complete output and actual owned retirement can clear it. The first
  capture error is retained rather than replaced by a later success assumption.
- Media admission rejects ambiguous/nonfinite JSON and requires the exact owned
  MOV/MP4 recording streams. Decoding, the fresh acoustic nonce and same-owned-URI
  playback still have to prove the actual case.
- Android audio checks preserve bounded raw dumps before parsing, require all-UID
  quiet observations at the idle boundaries and the expected active UID/PID
  during recording/playback. After a failed operation, a single bounded quiet
  query is allowed only after all started acoustic actors are confirmed retired,
  no pending/unknown owner remains, and the existing cleanup budget allows it.
  The query is consumed before dispatch, is never retried, and cannot promote a
  failed business operation into success. Complete actual dump ABI, PipeWire
  quiet state and continuous exclusivity still require live qualification.
- The state machine accepts either verified-playback/restoration order. Audio,
  nonce, epoch, exact URI, preserved state and retired owned-task gates remain.

Relative to the original shared r4 modules, nine files change and twenty retain
identical bytes. Relative to `f9c5064`'s canonical folder, eight files change and
21 retain their bytes. The state module itself is exactly the owner's validated
`68c6369a...` source; the merged decoder has a new hash and inherits no previous
host qualification.

## Guest and observer credentials

Android package and AudioFlinger IDs remain guest IDs. Host `/proc`, file-owner
observations and the audio helper's socket credentials use the observing
namespace. Previously, the Camera/Gallery owner checks and audio process scan
compared these different IDs directly. A map `0 200000 100000` makes Camera
10062 appear as 210062 and the audio HAL 1041 appear as 201041 to the host.

The current implementation reads both maps through the held Main's proc
directory, pins its process generation with an owned pidfd, and holds both user
namespaces. It handles independent and segmented UID/GID ranges, rejects holes,
overlap, overflow, missing maps and namespace drift, and never guesses an
identity mapping. For the same user namespace, map column two describes the
parent namespace, so the observer keeps the original guest ID. See the
[Linux user namespace mapping contract](https://man7.org/linux/man-pages/man7/user_namespaces.7.html).

These independent handles survive the normal Camera-to-Player scope transition;
the next scope must prove that it still holds the same Main proc inode. Existing
guest PID, pidfd liveness, namespace, executable, package, root and cgroup checks
remain. Camera/Gallery directory checks still require the exact observed CE/DE
inodes and compare their owners against the mapped UID and GID separately.

The helper must share the verifier's user and PID namespaces. Protocol checks
receive explicit observer UID/GID values for the held HAL; Android track checks
continue using 1041/10062/10064 where appropriate. This follows Linux's
[`cred_to_ucred` conversion through `current_user_ns()`](https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/bfe8eb3b85c571f7e94e1039f59b462505b8e0fc/net/core/sock.c).
An old deployment lifecycle that still specifies host peer/socket IDs 1041
fails admission when the held guest maps those IDs elsewhere. This repair does
not modify services, socket ownership, subordinate-ID grants or production data.

The focused controls reproduce the old process-scan and directory-owner failures
against the original source. Foreign namespace/proc trees are explicit fixtures;
same-namespace observation, file descriptors, directory metadata, pidfds and
owned child exit are real Linux operations. They do not qualify an actual mapped
Android process or a live audio socket. Final Main, helper deployment, actual
recording/playback, recovery and all application acceptance remain pending.

## Formal source preparation and display consumer

`tools/prepare_camera_video.py` verifies the externally pinned inventory, copies
all 29 files into a fresh exclusive directory and constructs the existing
`pocket4-current-camera-video-preparation-v1` packet. Its real bootstrap checks
all 32 live source/origin files under that new directory. The provenance names
both source parents, explicitly records that the old tested archive is not an
exact-byte match, and keeps previous runtime/host authority untransferred.

The display wrapper's only changes from `f9c5064` are its inventory SHA and entry
size/SHA constants. All other AST nodes match; holder and lease files remain
byte-identical. The adapter reproduces the same current constants. The existing
20-second readiness, 510-second acoustic owner and 90-second cancellation
budgets, release checks, three-principal identity checks and owned retirement
requirements remain. `review/display-union-pin-adaptation.json` records the exact
comparison. This structural proof is not a new actual display-host execution.

The current inventory is 5281 bytes, SHA256
`12c7591d2491d346cda679cd1f314cba375f54e6bab7809e6ab7352c4ec18181`.
Use a new output root; the consumed earlier `c1` preparation is not updated or
replayed. A reviewer-approved preparation can be created with:

```sh
sudo -n /usr/bin/python3 -I -B <bundle>/tools/prepare_camera_video.py \
  --source <bundle>/source \
  --inventory <bundle>/reviewed-source-inventory.json \
  --expect-inventory-sha256 12c7591d2491d346cda679cd1f314cba375f54e6bab7809e6ab7352c4ec18181 \
  --output <new-directory>
```

The printed preparation SHA must be passed to the formal entry and display
consumer. Their default source inspection does not start Main. Any runtime
request must still come from the existing fresh plan factory after actual
baseline, installed Camera/Player/helper identities, Main epoch and display
lease admission. No such runtime request is supplied by this bundle.

## Current source controls

`tests/run_current_source_controls.py` runs four exact suites and rejects a
missing test or any skip. The checked-in source report binds before/after hashes
of every input used by those suites.

| Suite | Expected tests | What it checks |
| --- | ---: | --- |
| Formal preparation and entry | 11 | Exact real temporary files/FDs, both role packets, stale source/inventory/role rejection, create-only behavior, no transfer of historical host authority |
| Display contract and source entry | 18 | Actual source constructor/rejection and explicitly synthetic terminal contracts, old entry/inventory refusal, unchanged ownership/release methods and budgets |
| State public API | 9 | Both valid restoration orders, seven failed-state cases, 28 binding-negative subcases, and exact reproduction of the old restoration-order regression |
| Guest/observer credentials | 21 | Mapped UID/GID ranges, unmapped and malformed IDs, namespace/Main drift, scope changes, real pidfd exit and directory ownership, and explicit socket credentials |

These 59 controls use no Main, Android UI, physical camera, physical audio or real
display lease. The original owner state fixture remains exact under `tests/fixtures/`;
its old one-method wrapper is not counted again. The r4 capsule separately
contains current-host, quiescence, failure-cleanup and Linux decoder controls.
Do not add overlapping state counts together as independent coverage.

Run source controls on Linux with the permissions needed by the actual root-only
source constructors; a non-root skip is a failure of this complete gate:

```sh
sudo -n /usr/bin/python3 -I -B <bundle>/tests/run_current_source_controls.py \
  --report <new-report-path>
```

A real local attempt to execute the merged sealed-copy helper could not assign
UID/GID 1000 in the scratch user namespace (`EINVAL`; only UID/GID 0 are mapped).
It did verify rejection cleanup without changing the original input. It is not
counted as a UID1000 decoder pass. That boundary requires the actual Pocket4 host.

## Prior canonical Pocket4 host controls

The following receipts retain their original inventory and source bindings.
They do not qualify the changed credential modules or a new display wrapper.
A fresh preparation and current host/runtime admission are still required.

The exact merged decoder now passed eight real host controls on Pocket4 in a
bounded root-to-UID-1000 execution. These cover full synthetic video/audio
decode and nonce checks, the two inherited descriptors and read-only UID1000
input, all four seals, malformed input, actual timeout and bounded-output
retirement, an adopted descendant, and a real reaper-finish fault that must
keep UNKNOWN latched. No Main, Android, physical camera or audio device ran.

The actual qualifier, pinned source packet, exact executed staging sources and
compact result are in `host-controls/current_decoder/`. The formal canonical
execution passed all 38 source controls on Pocket4 Python 3.14.4, created and
inspected the formal preparation, and repeated these same eight decoder
controls at the current canonical location. Repeating them adds no distinct
coverage. Its 18,264-byte private decoder qualification has SHA256
`16787707174712310782752387105a1f3de323b9df7b296fa7ce22271d83b5ac`.
The 9,271-byte formal preparation has SHA256
`a6c00462565e55035339457f40b6209d696b3879307c27c7f4d2e669688bb40c`.
The owned unit ended successfully, all descriptors and child processes retired,
and no memory, swap or task limit event occurred. This is fresh evidence for
these decoder/capture components. Four current display-wrapper negative
process controls also passed: missing terminal, worker exit seven, lost holder,
and wrong physical-ready response. The actors, UID1000 credentials, pidfds,
source packet and retirement were real; the display protocol, independent
display observation and business child were explicitly fixtures. The
55,240-byte result is pinned by
`150d07b1cb87200dd43bda2932d6349fcb79fb44da92a7fecd861de52cfaf6e5`.
Both bounded units are gone and their descriptors/children are retired. The
remaining real display, supervisor, Main, audio, Camera recovery and whole-app
gates are unchanged.

The seal attack uses a distinct copy from the same production helper, keeping
the production read-only input unchanged. The test's temporary writable copy
exists only to exercise real sealed-write failures. It is never a decoder
factory input. The previous unknown legacy dispatch remains separately
recorded and receives no terminal or runtime credit from this successful job.

## Historical evidence and remaining work

The unchanged earlier `provenance/decoder-host-result-r2.json`,
`review/validation-summary.json`, `review/final-owned-source-binding.json`,
`review/r4-byte-equivalence.json` and original supervisor/display/preparation
receipts belong to the previous canonical inventory
`2444a7f3...` at `f9c5064`. Their source hashes do not match the merged source.
They remain audit history and grant no current host or runtime qualification.
The original decoder host script also remains historical until rebound and
executed with a reviewed current host packet; do not treat its retained result
as a merged-decoder pass.

`source-bundle-index.json` describes the files actually in this Git bundle.
`publish-source-manifest.json` records the exact current deliverable bytes;
previous host journals that were never published are not falsely listed as
present files. `review/merged-source-validation.json` and the previous 38-control
report describe the preceding inventory; they do not admit this credential
successor. All historical summaries retain their original result and bindings.

Before final acceptance the owner must maintain the separate disposition of
the prior unknown experiment, qualify the owned supervisor/display path, create
a fresh runtime plan consuming the current preparation, run the real capture/audio/decode/
same-URI playback flow, review its visual behavior, and close the original app
contracts. Obsolete live directories can retire only after their active
references are replaced and their jobs/open references are freshly checked.
Account data and the protected Android images are not cleanup inputs.

The state test's semantic AST pin now uses typed recursive fields instead of
version-dependent `ast.dump` text. It normalizes only absent empty
`type_params` and absent type-parameter `default_value=None`; all other fields
and scalar types remain pinned. The expected value was derived from the
independently byte-verified original owner decoder. The actual first canonical
attempt failed that old representation on Python 3.14 before any host unit;
the new source test and fresh full preparation passed without production
module changes. Historical failed attempts retain their original outcomes.
