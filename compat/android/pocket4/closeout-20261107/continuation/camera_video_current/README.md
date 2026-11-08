# Pocket4 current Camera video: combined source

This is the canonical Camera video source for Pocket4's Linux local Android repair.
It combines the current-host and audio/decoder admission changes from `a355e81`
with the sealed read-only decoder input and state restoration changes in `f9c5064`.
It also includes the bounded Android quiet check on a failed business operation.
The 29 modules in `source/` are one exact inventory. The r4 test capsule must
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

The current inventory is 5173 bytes, SHA256
`28e61371c50638a3ac33d4e28b0466754bc2b81c9f5d015f262d43e60243dd00`.
Use a new output root; the consumed earlier `c1` preparation is not updated or
replayed. A reviewer-approved preparation can be created with:

```sh
sudo -n /usr/bin/python3 -I -B <bundle>/tools/prepare_camera_video.py \
  --source <bundle>/source \
  --inventory <bundle>/reviewed-source-inventory.json \
  --expect-inventory-sha256 28e61371c50638a3ac33d4e28b0466754bc2b81c9f5d015f262d43e60243dd00 \
  --output <new-directory>
```

The printed preparation SHA must be passed to the formal entry and display
consumer. Their default source inspection does not start Main. Any runtime
request must still come from the existing fresh plan factory after actual
baseline, installed Camera/Player/helper identities, Main epoch and display
lease admission. No such runtime request is supplied by this bundle.

## Current source controls

`tests/run_current_source_controls.py` runs three exact suites and rejects a
missing test or any skip. The checked-in source report binds before/after hashes
of every input used by those suites.

| Suite | Expected tests | What it checks |
| --- | ---: | --- |
| Formal preparation and entry | 11 | Exact real temporary files/FDs, both role packets, stale source/inventory/role rejection, create-only behavior, no transfer of historical host authority |
| Display contract and source entry | 18 | Actual source constructor/rejection and explicitly synthetic terminal contracts, old entry/inventory refusal, unchanged ownership/release methods and budgets |
| State public API | 9 | Both valid restoration orders, seven failed-state cases, 28 binding-negative subcases, and exact reproduction of the old restoration-order regression |

These 38 controls use no Main, Android UI, physical camera, physical audio or real
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
present files. `review/merged-source-validation.json` is the current source-only
summary. Old summaries remain explicitly historical.

Before final acceptance the owner must resolve the prior unknown host dispatch,
qualify the exact merged decoder and owned supervisor/display path, create a
fresh current preparation and runtime plan, run the real capture/audio/decode/
same-URI playback flow, review its visual behavior, and close the original app
contracts. Obsolete live directories can retire only after their active
references are replaced and their jobs/open references are freshly checked.
Account data and the protected Android images are not cleanup inputs.
