# Beike permission service pilot — new source only

This standalone observation requests only the following three Android commands, in order:

1. /system/bin/cmd package help
2. /system/bin/cmd package dump-package com.lianjia.beike
3. /system/bin/cmd appops get --user 0 com.lianjia.beike

The target is the actual current Beike UID 10143 / versionCode 3067100 from the pinned explicit47 scope. All 47 packages remain the before/after protection set. That larger protection set does not authorize service queries about another package.

## Source and identity continuity

The foundation is actual successful current_services_r4, job 1a1b22e95d0-fc05-7cd4. The typed successor runtime, framework epoch, current explicit47 APK/stat/UID/data scope, native CLI and daemon, UID1000 native peer, held namespace root and seven authority descriptors, classpaths, helper source, global action lease, and new independent flow lease are unchanged.

The three native reads remain status, applications, status. Runtime and complete explicit47 checks remain around each command. Meituan's saved location state must remain identical. Original Bili UNKNOWN must remain unchanged. This worker neither imports the Beike Flow nor changes its compiled two-package scope.

Every transport class/function, every nested runtime/native/stream/runner function, and every owned-lifetime function except worker_gate is byte-identical to the actual r4 source. Original empty-stream creation, command-row-before-artifact capture, timeout/error handling, and target/lease/FD cleanup remain. The outer owned-libffi worker retains the exact bootstrap, descriptor identity checks, original child pidfd exit, and parent descriptor restoration. No library FD is manually closed and no unknown descriptor allowance is added.

## Output semantics

The worker saves original stdout and stderr for every executed command before any semantic interpretation. Zero-length command streams are valid original artifacts; an absent artifact or incomplete capture is not. A nonzero command, timeout, guard mismatch, artifact write failure, unjoined child, missing/changed descriptor, or lease cleanup error fails the observation without retry.

The PackageManager dump command has no user filter in the actual supported syntax. Its complete package-level output is captured unchanged; this source does not label every section as user0. The AppOps command explicitly requests user0.

The current package-help response must contain the actual dump-package PACKAGE syntax before the dump is executed. Exact original AppOps-help bytes are staged read-only and checked for the documented get form. That earlier help command returned 255 and its failed outcome remains unchanged; its text supports the syntax only. This source does not infer that get will succeed.

This first pilot deliberately does not parse permission names, user sections, grants, or AppOps modes. In particular, it does not strip the seven leading spaces from the noncanonical Beike permission name, equate missing output to denial, or equate an AppOps default/foreground mode to a permission grant. Effective grants and AppOps modes remain UNKNOWN_PENDING_SERVICE_OUTPUT_INTERPRETATION; roles remain UNKNOWN_NOT_QUERIED. A successful status means complete raw service output and resource retirement, not interpreted effective grants or business readiness.

Existing PM/resolver parser definitions are retained byte-for-byte for a small reviewable diff, but the pilot does not call them and does not claim a new global PM/resolver enumeration. Historical r4 results remain separate.

## New paths and execution boundary

The source stage is /home/alex/work/pocket4-beike-permission-pilot-source-20261106-r1. The independent observation output is /home/alex/work/pocket4-beike-permission-pilot-observation-20261106-r1. Both are new, root-private, non-overwriting paths. The exact process key is sidecar-evidence-20261106-beike-permission-raw-pilot-r1.

The process packet retains the original sudo -n execution channel, 1100-second outer limit, CPU quota 100, 1 GiB memory limit and nice 10. The worker retains its 900-second budget and 30-second per-command limits. The stager contains five exact pinned files, including the 1309-byte original AppOps help text; it invokes the owned wrapper exactly once after readback and stage-FD closure.

No remote job or Main operation has been executed by this preparation. Parent review and a serialized Main window are still required by the current coordination boundary. No install, grant, AppOps mutation, role change, UI action, app launch, input, restart, ADB, old-result rewrite, or production-ready claim is in this candidate.

## Actual local validation

LOCAL_CLOSURE_REVIEW.actual.json records local compilation, exact unchanged definitions, the pinned actual47 target identity, both actual help inputs and two missing-syntax negative checks, and complete stage/request/source hash closure. Local process FD count is unchanged. No runtime/helper/Android execution occurred. The prior real timeout and empty-stream controls were not rerun and are not claimed as new tests.
