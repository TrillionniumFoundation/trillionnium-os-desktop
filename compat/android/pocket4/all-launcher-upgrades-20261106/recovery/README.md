# Pocket4 native owner lifecycle recovery candidate

## Status and intended result

This is an executable recovery candidate prepared locally. No target-machine
restart or successor qualification has been executed by this work. The local
Linux controls exercise real pidfds, flock contention, descriptor closure,
equal-content inode replacement, bounded child termination, source pins, and
failure gates. They are not Android runtime acceptance tests.

The intended transition retires the actual current Android cell through its
existing native lifecycle API, proves the old composer owner has died using
the pidfd acquired before the request, and independently qualifies the new
runtime. It does not repair the deployed native implementation's response to a
later framework-only crash. That remains a production gate.

The observed Bilibili operation already has an Android side effect: task 873
exists as `tv.danmaku.bili/tv.danmaku.bili.MainActivityV2`, user 0. Its original
launch result remains unknown and has no launch-scope receipt. This recovery
does not turn that operation into a successful launch, replay it, remove task
873 by task ID, or claim its native object.

## Files

| File | Purpose |
|---|---|
| `successor_runtime.py` | Read-only preflight; explicit native cell restart; actual predecessor and successor collection; new immutable baseline and guard factory |
| `resume_successor_qualification.py` | Read-only completion of a failed qualification for the exact recorded successor, without another restart or process rediscovery |
| `observe_successor_scope.py` | Fresh App byte/data observation on a pinned successor, plus actual inputs for a newly built QA flow |
| `framework_epoch.py` | Unmodified CP20 double process capture/reference reader |
| `held_runtime_r5.py` | Unmodified CP20 root-relative openat2 and classpath reader; no namespace-entry method is called by this recovery |
| `readonly_abx.py` | Root-audited readonly collector dependency; only its bounded XML/ABX parsing and certificate digest functions are called |
| `SOURCE_PINS.json` | Complete six-file executable source closure; pass its actual SHA256 at invocation |
| `targets-45-plus-actions-reference.json` | Forty-five observed native launcher package names plus `local.pocket4.actions.v2`; a roster reference, not a new resolver enumeration |
| `test_successor_runtime.py` | Local negative controls; no Pocket4 actions |

The roster must be reviewed after the independent Beike update has settled.
Preflight reads the actual current APK bytes when invoked. It does not freeze
the old Beike version from the earlier inventory. If other non-launcher QA
packages must be retained across the restart, include their exact names in a
new pinned target file. Do not invent names or infer a package's presence from
an old build directory.

## Native source evidence and exact operation

The relevant old native API is `ControlServer::restart`: validate the request's
spec against the caller UID, stop the currently owned cell, then start that
same authorized specification. `DevelopmentCell::stop` signals its held child,
waits, and joins it; it does not select a foreign process by task ID. The composer
task registry is in memory in `TaskCoordinator`, not a registry file.

Reviewed source references:

- [Old composer ownership guard](https://github.com/denialwm/droidloom/blob/246bae669a4d8f7dacc8824e927db144f4362347/graphics/droidloom-composer-service/src/control.rs)
- [Native daemon control and restart](https://github.com/denialwm/droidloom/blob/246bae669a4d8f7dacc8824e927db144f4362347/runtime/droidloom-supervisor/src/control.rs)
- [Native CLI, including hidden global `--cell`](https://github.com/denialwm/droidloom/blob/246bae669a4d8f7dacc8824e927db144f4362347/runtime/droidloom-supervisor/src/bin/droidloomctl.rs)
- [Owned cell lifecycle](https://github.com/denialwm/droidloom/blob/246bae669a4d8f7dacc8824e927db144f4362347/runtime/droidloom-supervisor/src/development.rs)
- [CP20 predecessor qualifier](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/df9465b6a899fbbd9f8e40294f14185f70880c4f/compat/android/pocket4/continuation-r11/checkpoint20/packages/app_baseline01-source_tree/android-main-current-baseline-01/source/qualify_baseline.py)

The actual installed daemon/composer build lineage is not fully proved by
these source references. The live composer hash and old error markers are
known; m579's composer control source matches the old registry implementation.
Before deployment, review the live CLI hash/help, active units, and small build
provenance receipts. Preflight independently requires the supplied exact CLI
hash, accepts its actual `--cell --json --help`, and matches actual native
status to the predecessor's launcher PID.

The only mutating argv implemented is:

```text
/usr/bin/sudo -n -u #1000 -- /usr/bin/env
  XDG_RUNTIME_DIR=/run/user/1000
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
  /usr/bin/droidloomctl --cell --json restart --spec /etc/droidloom/cell.json
```

This is passed as an argument array, without a shell. Default
`droidloomctl restart` has different session lifecycle behavior and returns a
different receipt; it is not substituted here. The system daemon must remain
the same generation. The user presenter may remain the same or be replaced
through its own unit, but a replacement requires the original presenter's
pidfd to show death and the new presenter's actual unit PID and executable to
match the qualified lineage.

## Preflight request

`successor_runtime.py` accepts a closed, externally pinned JSON plan:

```json
{
  "schema": "pocket4-owned-cell-recovery-plan-v1",
  "old_guard": {
    "path": "/home/alex/work/pocket4-main-current-baseline-01/current_baseline_guard.py",
    "sha256": "0ee54ef97c073857609aedb4670395db084ceacc7d28558315647ab2ffbef679"
  },
  "old_epoch_sha256": "734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2",
  "old_composer": {
    "host_pid": 3588896,
    "start_ticks": 80797154,
    "sha256": "a657ac25be3e64ce0b639313cf392747589a946314744b0b65c1f98415d7a06b",
    "bytes": 286656
  },
  "native_cli": {"path": "/usr/bin/droidloomctl", "sha256": "f81e0223f6b256584d07a5e8fbc72f3f4c764ab53a88469b45b587c101e12c79", "bytes": 1705648},
  "cell_config_sha256": "f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc",
  "targets": {"path": "ACTUAL_ABSOLUTE_TARGET_JSON_PATH", "sha256": "ACTUAL_TARGET_SHA256"},
  "drain": {"path": "ACTUAL_ABSOLUTE_DRAIN_RECEIPT_PATH", "sha256": "ACTUAL_DRAIN_SHA256"},
  "unknown_evidence": [{"path": "ACTUAL_ORIGINAL_UNKNOWN_RESULT_PATH", "sha256": "ACTUAL_RESULT_SHA256"}],
  "output_root": "/home/alex/work/pocket4-cell-successor-EXCLUSIVE_NEW_NAME"
}
```

The placeholders deliberately fail validation. Do not replace them with
guessed values. No executable target plan has been filled or deployed here.

`drain` has schema `pocket4-owned-worker-drain-v1`, with exactly these fields:

- `boot_id`: actual host boot ID.
- `reviewed_monotonic_ns`: actual host monotonic time of the coordinated review;
  it must still be within five minutes immediately before restart.
- `unresolved_start_attempts`: must be empty. A timed-out connector start
  without a reconciled job identity/result does not satisfy this requirement.
- `workers`: exact known worker `{host_pid, start_ticks}` identities. Any
  still-live original generation blocks. An unreadable process or zombie is
  not treated as proven absent.
- `flow_locks`: exact owned `{path, identity:{st_dev,st_ino}}` records. The
  existing root-owned, single-link locks must be available with
  `LOCK_EX | LOCK_NB` and remain on the same inode.
- `source_receipts`: pinned real terminal job/status/result evidence. The code
  pins the evidence, while the coordinator's review determines its completeness.
- `review_scope`: exactly
  `all-known-pocket4-UI-install-observer-restart-jobs`.

The drain review is an explicit coordinator fact, not a claim that scanning
`/proc` discovers every possible asynchronous job. The existing global action
lock remains held across the transition, observation, and publication. The
independent Beike installer must finish before creating this drain receipt.

Run the first target invocation in preflight mode:

```text
python3 -B -I /ABSOLUTE/SOURCE/successor_runtime.py preflight
  --plan /ABSOLUTE/PLAN.json
  --plan-sha256 ACTUAL_PLAN_SHA256
  --source-manifest-sha256 ACTUAL_SOURCE_PINS_SHA256
```

Preflight performs identity/status/service reads, file hashing, and lock
acquisition. It performs no native restart and writes no successor output
directory. It rechecks the original guard before returning. Review any failure
before considering the explicit `execute-native-cell-restart` mode. That mode
reruns the entire preflight; a previous preflight result is not reused as live
authority.

## Qualification and generated guard

Before the native request, the controller freezes actual old runtime, APK, and
top-level app data directory identities in a fresh private directory. It writes
an immutable attempted marker before spawning exactly one native client. All
old root, executable, and proc-directory FDs are released at this boundary to
avoid pinning retired mounts or image references; all original pidfds remain
held. It then requires actual death of the launcher, Android init, zygote,
system_server, SurfaceFlinger, and composer. The original unknown launch's
files are rehashed unchanged.

The new launcher comes from the real native receipt. New Android roles must
belong to that launcher's cell ancestry and namespace, have the expected UID,
executable, parent, and cgroup relationship, and be unique. The collector then
holds all eight new process/root/executable identities. The engine, all eight
executables, complete selected classpaths in both actual init and zygote
roots, configuration, service lineage, resource limits, APK bytes, UIDs, and
data-directory identities are independently collected.

The initial post-restart App scope must match the actual pre-restart scope in
package UID/version/code path, signing-certificate metadata, complete APK set
bytes, and data-directory device/inode/UID/GID. APK hashing is bounded to
512 MiB per APK, 16 GiB across the explicitly selected all-app set, and
180 seconds per collection. The larger total bound is explicit because this
scope now includes all native launcher apps; the earlier eight-app collector's
4 GiB bound is unchanged. Classpaths retain their original 256-path,
128 MiB/file, 768 MiB total, 45-second bounds.

Three double process observations span 10–90 seconds after the expensive
content reads. A final observation, file/path recheck, service/status check,
and complete descriptor retirement are required before publication. The
generated guard is then loaded from its actual just-published bytes and run.

The new guard rechecks fixed identities and never discovers replacement
processes. It checks eight roles including composer, all namespace/root/file
identities, classpath values and both root views, config, native units, engine,
and cgroup limits. Its schema is intentionally new:
`pocket4-successor-main-guard-v1`. It does not pretend to be the old fixed
baseline or the old historical deployment.

## App upgrades and new QA binding

The runtime baseline does not include mutable installed package versions.
`app-scope-01.private.json` is a separate pinned document. A legitimate
independently admitted upgrade invalidates that App's prior scope while leaving
the runtime identity guard intact.

`observe_successor_scope.py` can collect a fresh scope after the installer has
settled. Its request schema is
`pocket4-successor-app-observation-request-v1`, with fields `guard`, `packages`,
`parent_app_scope`, `install_or_signature_evidence`, `output_scope`, and
`output_binding`. References use `{path,sha256,bytes?}`. Output paths must be
new files in an already prepared private directory.

The output includes actual APK hashes, package UID/version/signing metadata,
data directory identities, standard four-role `framework_epoch`, actual
launcher status PID, complete held init identity, selected classpath values,
and the new runtime/App scope pins. It makes no claim of fresh cryptographic
signature validation and does not interpret external receipt policy. The
separate installer/verifier must establish successful signed upgrade
acceptance from its own actual receipts.

The R9 `MainBinding` and recorder cannot directly reuse their old
`source_contract.py`, fixed `MAIN_EPOCH`, guard pin, or helper qualification.
Create a new source closure that explicitly accepts the new typed runtime
baseline and App scope, builds QA with the actual new epoch, verifies/installs
that helper through the admitted path, and re-runs its admission controls.
The projection is build input, not a QA PASS. Until those steps complete,
every generated artifact states `UI_or_install_runtime_admitted: false` and
`production_ready: false`.

## A failed qualification after the real restart

The controller preserves a successful actual native receipt and original
pidfd death evidence in `retired-lifecycle.private.json`. Once the actual new
roles are discovered and held, it writes
`successor-candidate.private.json` before further collection. This is the
only candidate that the resume path may use.

If `result.json` is terminal, unsuccessful, has `outcome_unknown: false`, and
the candidate exists, `resume_successor_qualification.py` can complete the
same qualification without another native lifecycle operation. It requires:

- A pinned candidate and matching pinned failed result from the same output
  directory.
- Their actual complete native restart command/stdout hash, predecessor,
  attempted marker, and old pidfd death chain.
- The identical source manifest and a new coordinated drain receipt.
- The exact recorded eight-role process identities, roots, namespace handles,
  executable files, service lineage, and actual native owner still present.
- The same runtime byte checks, unchanged App scope, three double samples,
  final checks, and descriptor closure as the original path.

Request schema: `pocket4-resume-fixed-successor-qualification-v1`; fields:
`candidate`, `failed_result`, `fresh_drain`, and `output_root`. Output goes into
a different fresh private root. The entry point takes `--request`,
`--request-sha256`, and `--source-manifest-sha256`.

If no candidate was recorded, the native receipt is incomplete, the prior job
is still unresolved, or any recorded process generation changed, this resume
path refuses. Preserve the attempted transition and diagnose through readonly
host/native status; do not rerun the restart or edit expected PIDs. A further
lifecycle change requires a new concrete recovery design for the actual
state, not an automatic replay of this plan.

## Persistent native fix remains separate

Upstream commit `3306069cb47f434a388e07d1d49bb1fee46781d0` introduces genuine
framework task incarnations and a paired system_server task backend/protocol.
Commit `ad5d63893329d072a114d61c30ca748f01026c21` adds authenticated framework
subscription adoption and normal orphan retirement on framework replacement.
These are not CLI reset operations. The latter cannot safely be transplanted
alone into the live legacy launcher/control protocol, which lacks that
subscription authority.

The small diagnostic build provenance receipts under
`/opt/p4-media-composer-diagnostic-20261102-chat2-r5/provenance/` still need to
close live binary → build source lineage before preparing a deployable paired
upgrade. No registry file deletion, ownership-guard removal, forged
launch-scope, borrowed Bilibili cleanup authority, or direct reassignment of
task 873 is a recovery step here.
