# Retained ready-player control metadata, revision 1

This is a fixed read-only collector for the third successful capture transaction
from `pocket4-bilibili-r5-player-fresh-before-01`. It does not open an App, enter a
namespace, run Android commands, make a screenshot, install anything or select a
UI target. The original task 936 was retired and Home task 851 was preserved.
The observations can guide a later reviewed fresh flow; they cannot authorize an
action in any current or future window.

## Exact evidence and scope

The collector reads eleven fixed files. Nine have full external SHA-256 and
byte-count pins: coordinator, stage, navigation, cleanup, source manifest,
original QA contract, original viewport module and two complete helper
assessments. The two exact request filenames are bounded to 4 KiB each; their
decoded objects must equal the retained protocol, nonce, operation and scope,
and their canonical SHA-256 must equal the already hash-bound helper wire's
request digest. The allowlist does not include screenshots or additional trees.

The two assessments are the successful `before_observation` and
`after_observation` around capture 3. They each contain 153 nodes, have the same
complete tree/window hashes, and have separately successful state restoration
and command completion evidence. The original QA parser verifies each complete
tree, own-connection cache-clear/window evidence and traversal counters. The
original pure viewport predicate is then rerun and must reproduce the exact
stored proof, including the two differently sized SurfaceViews and the absolute
scope. This collector does not change that predicate or its geometry rules.

Original coordinator-to-worker, stage-to-coordinator and cleanup links are
checked. All original success, Main identity, source, helper, retirement and
business-unknown fields remain required. In particular, the successful
navigation's `outcome_unknown=true` is preserved; the collector cannot promote
it to playback, audio or whole-App success.

## Limited output

Only visible, non-password nodes within the already verified `video_area`
subtree are reported. Output includes node/parent hashes, bounds, the original
boolean flags, exact Bili resource identifiers matching an explicit identifier
grammar and a fixed list of public Android widget classes. Other class/resource
strings are hash-only. Unknown text and content descriptions are never emitted;
only an explicit small list of public control labels such as `Pause`, `Play`,
`暂停` and `播放` can be returned literally. A standalone time format is reported
as a boolean without returning its value. All output is checked against raw UI
field names before emission.

This helper version records `clickable` and `supports_set_text` but does **not**
record the complete accessibility action list, range information or
`ACTION_SET_PROGRESS` support. The output states that those capabilities were
not observed. A SeekBar class or a public label alone is not proof of an
authorized or functioning pause/resume/seek operation. All controls would need
a new fresh inspection and the existing whole-tree/window/action chain before
any later mutation.

Each path component is opened with `O_NOFOLLOW`; each leaf is a regular,
single-link file with the fixed expected owner, held metadata stable before and
after reading, and the required pin. Each file is at most 1 MiB, total reads at
most 3 MiB, with an 8-second read deadline. At most 128 player rows per retained
assessment are emitted and the entire output must fit 128 KiB. No partial list
is reported as success. The request has a 30-second outer timeout, one CPU and
128 MiB memory.

## Validation performed locally

Ten controls passed. Two use the four original safe receipts and exact pinned
summary metadata. The others use explicitly synthetic helper-schema rows to
check unknown-text suppression, exact public labels, slash path boundaries,
password/invisible handling, unsafe resource/class strings, full-list bounds,
the distinction between SeekBar class and unobserved progress support, and the
raw-output-key tripwire. No commercial assessment or pixel was read locally;
no `collect()` or remote request was executed. Default PLAN mode and syntax
checks also passed. Synthetic rows do not establish device control availability.

`make_request.py --write-once --output <new-file>` creates a hash-bound request
only. Its stable key is
`pocket4-bilibili-r5-retired-player-controls-readback-01-20261105`. Root must
review and dispatch that exact request. No reference is updated by this source
freeze; it belongs to the next additive checkpoint.
