# Bilibili: exact existing recorder, held entry integration r1

Status: source and **42 actual local controls PASS**; independent review and
this adapter's actual Main admission are **NOT PERFORMED**. No new Bilibili UI,
audio, task launch, task removal, APK install, permission change or engine
deployment was performed while preparing this revision. This is not a
whole-app production qualification.

The original r10 recorder is retained verbatim in
`references/original_recorder.py` (SHA-256
`28103c8cb444d5963eac54ffef6aeda842337e33a892336c49a71cc5b82da20b`).
Its original APP client and BACKEND are distinct pinned sources. Their
`client()` functions differ; their other function ASTs are identical. The
adapter uses the APP client, including its explicit foreground authorization,
and the BACKEND helper, including its original action lock. It never invokes
the BACKEND's less restrictive client entry.

## What changes

`recorder.py` retains the original `begin`, `reconciled`, `saved_step`,
`reconcile`, `stacks`, `selected_task`, `ui`, `cleanup` and `engine_maps` methods
as identical ASTs. The original Main epoch/config/process/limits guard
statements are also intact and reachable. Tests compare these actual methods,
not a separately written model.

The direct Android path now uses R5 `HeldTarget` and the qualified shared
namespace-entry helper. It passes precisely the held root and six namespace
FDs; numeric PID namespace entry is gone from the active recorder. Original
task list/remove and package exit-info commands, task receipt ownership,
asynchronous removal readbacks, global action lock, and no-replay claims stay
in place. The original native `droidloomctl launch` remains the host launch
path. It additionally holds the same action lock and refuses an already
present Bilibili task before claiming or issuing a launch.

The separate UI path still executes the original APP `client()` parsing and
output behavior. Only its exact `sudo BACKEND` child spawn is redirected into
`existing_ui_entry.py`. That child runs the exact BACKEND `helper()` after
replacing its private module's `arun` with the held transport. Its request,
logical argv, physical entry, parent command intent, active flow lock and
one-use child claims must agree. Every direct and indirect call is enumerated
in `CALL_INVENTORY.md`.

`main_binding.py` binds only Main epoch
`48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f`,
package `tv.danmaku.bili`, UID `10117`, user `0`, and the exact r10 activation.
It checks the existing action-runner UID `10125` but does not claim an
unobserved APK hash/source qualification. R5's streamed, two-root classpath
proof compares simultaneously held files from the actual fixed zygote root
and command init root. Distinct valid mount namespaces are allowed; different
backing files are refused. Main environment reads are labelled as Main reads.

## Two precise transport contract corrections

Frozen transport R3 remains unchanged outside this revision. The actual
original `wait_for_removal` calls its reader with `min(3.0, remaining)`.
Consequently this integrated copy accepts finite `0 < timeout <= 70`, keeping
the original `inner = max(1, timeout - 5)`. A control runs the actual task
function against frozen R3 and observes its rejection, then observes the
integrated transport accept the same short read deadline. No removal command
is retried.

The original allowlisted optional environment values may be empty. This copy
preserves them, while the six required Android/classpath keys must be nonempty
and loader variables such as `LD_PRELOAD` remain disallowed.

R3's timeout/return-code first cause, independent lease release and independent
post-command guard remain. The direct recorder runner now hands its observed
command result and secondary evidence errors back to that protocol, so an
evidence write or lease failure cannot replace a known timeout/exit status or
produce PASS. The original process-lifetime `flow.lock` remains held through
the final durable result; only held namespace resources are released before
that result is finalized.

## Privacy and evidence

The direct task/exit-info path retains the original raw command evidence.
The backend's intermediate screenshot and native-tree bytes stay in memory,
as in the original backend. The adapter records their length, hash and status,
not new unscoped raw files. The original backend emits the requested scoped
application observation, which the original recorder saves. A specific
control verifies that opaque intermediate full-frame bytes do not appear in
the new journal. There is no microphone, PCM capture, audio graph change,
volume change or route change in this source.

Commercial raw logs, the full activation/UID inventory, APKs, ELF files and
signing material are not included in this source tree. Runtime evidence must
remain private; a future publication should use scoped summaries and pins.

## Local verification and its limits

Run the same offline controls with:

```sh
python3 -I tests/integration_controls.py
```

They execute the actual frozen task parser/wait/removal code, actual recorder
methods, actual APP argument parsing, actual BACKEND action flock and error
protocol, real local file descriptors/flocks, real openat2 file resolution,
and owned local Python children that are joined after exit or timeout.

Android results, Main identities, namespace entry, zygote `/proc` inputs and
UI responses have explicit local seams. Source loading is checked through
real complete manifests at relocated paths, including changed-dependency and
missing-closure negatives. Two-root tests use real held descriptors to owned
files; equal bytes on different inodes are rejected. These are not real Main
UI, installed action-runner, Android audio or commercial-app tests.

The reported 42-control result and exact source pins are in `evidence/`.
There is no automatic Main execution entry in the test script.

## Next permitted review stage

The parent must independently review the five production files, diff and
source manifest before uploading a create-only copy. The only first runtime
proposal is a new flow `init`, then the explicit `admission` operation. It
reads the fixed metadata/classpaths and performs exactly one held command:

```text
/system/bin/cmd package list packages -U --user 0 tv.danmaku.bili
```

That operation requires exactly `package:tv.danmaku.bili uid:10117` and keeps
`ui_or_audio_action_performed=false` and
`action_runner_apk_source_qualified=false`. The candidate source pin, shared
entry qualification, installed action-runner provenance and actual target
admission must be reviewed before scheduling any new UI step. No admission
or UI action has been run for this revision.

The existing r10 search/visual playback/owned-task close result remains its
historical scoped result. Reopen, continued playback, normal exit on the new
flow, and precise app/output audio attribution are still pending. See
`REOPEN_AUDIO_PLAN.md`; neither the source change nor passing local controls
advances those app gates.
