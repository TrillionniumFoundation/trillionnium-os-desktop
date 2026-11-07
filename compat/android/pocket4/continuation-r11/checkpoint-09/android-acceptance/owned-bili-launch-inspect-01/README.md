# Owned Bilibili launch and inspect 01

This is source for one proposed run, not an Android or application result. The
request has not been submitted by this author. Root reviews and schedules the
device window. All older sources, receipts, failed Install01 and successful
Install02 remain unchanged.

## Exact scope

The new package `org.droidloom.qa.bili.r1` is already installed as UID 10164.
This request does not install, replace, uninstall, grant permissions, change
settings or invoke `local.pocket4.actions.v2`. It uses the actual Build02 signed
APK and Install02 success, including a new parse of the original state command.
Current live package UID, base APK bytes, signer binding and held file identity
must still equal Install02 before any native Bilibili launch.

The fresh flow has four separate, joined processes: original recorder `init`,
a launch worker, an inspection worker, and original recorder `cleanup`. The
original recorder holds `flow.lock` until process exit; this avoids calling two
CLI operations in one process. Each UI worker uses the original action lock.
The launch worker proves the helper identity under that lock, then calls the
unchanged `Flow.launch_locked()`. It does not call `Flow.launch()` and reacquire
the lock. Existing Bilibili tasks cause rejection before native launch and are
preserved. Only the original positive scope for a newly created exact leaf task
can authorize cleanup. No package-wide force-stop or guessed task cleanup exists.

The inspection worker uses the already executed R4 host Session binding and
unchanged QA Session `sequence`: state / inspect / state with three new nonces.
Each phase checks its real command return, finish code, request binding, UID,
lease release and post-Main guard. Foreground package, activity, window and exact
task are checked around inspection. Accessibility restoration requires actual
own-service readback plus the fresh independent state after instrumentation
termination. The historical Install02 state is not a current accessibility
baseline. A failure never becomes a restoration or UI success. Inspection has
no click, text, playback or audio action. It does connect UiAutomation using
`DONT_SUPPRESS_ACCESSIBILITY_SERVICES`; state operations do not connect it.

## Main and provenance

The existing Main 48cb65c9 epoch, fixed activation and verification receipts,
engine/helper sources, three host identities, cell configuration, resource
limits and commercial package scope remain under the original guards. There is
no package-count or stale 182-package assumption. The original 44-file R4 tree
at the actual Install02 source root is read and verified, not copied or edited.
The only earlier R4 transport change validates the helper prefix before `--`
and preserves exact Android suffix arguments; its actual install/state run has
passed. This run cannot bypass any old APK provenance gate or use old v2.

All external input pins are in `INPUTS.json` and production constants. Root's
actual Install02 authoritative job was `1a1a926b70d-fc05-3200`, succeeded, exit
zero, durable. This code independently consumes the pinned stage/coordinator/
worker chain, actual joined worker receipt and state command, then revalidates
the current installed signed APK. It does not manufacture a tool terminal.

## Failures, cleanup and resources

Only the fixed once claim and fresh root/flow are accepted. Unknown or partial
outcomes are retained without a second nonce, action retry or wider selector.
First errors and release/post-guard errors are distinct. A failed inspect or
evidence write still reaches the independent exact-owned cleanup attempt when
the original positive launch scope exists. If launch was attempted but no valid
owned scope exists, cleanup is not authorized: the original failure and the
need for exact reconciliation remain visible. The original cleanup rechecks
task identity, preserves other tasks and requires observed removal/absence.
This is not a promise of arbitrary process-tree retirement or recovery after
controller death. Helper installation is retained for a separately reviewed
next observation/action; no automatic uninstall occurs.

The managed coordinator budget is one CPU, 512 MiB RAM, no swap and 128 tasks.
Only its own exact managed cgroup receives the swap/tasks limits. Main limits
are read only. Phase timeouts are init 25 s, launch 180 s, inspect 180 s and
cleanup 100 s; the outer request is 600 s so serial cleanup has room to finish.
These are ceilings, not sleeps, and original per-command limits are unchanged.
RAM max/OOM counters and source/epoch/artifact changes fail qualification.

## Evidence privacy and interpretation

Raw commercial UI trees, helper assessment bodies, stack lists and command
stdout remain in the new root-owned remote flow. They are not included in the
source tree or exported into Git. Public summaries are restricted to scope,
package/UID, hashes, activity/window identity, node count, non-sensitive state
and exact task cleanup. No account text, recommendations, screenshots, audio,
microphone or unrelated commercial journal is collected for publication.

Even complete execution proves only this launch/inspect/restoration/cleanup
scope. It does not prove search, playback, audio output, reopen behavior,
translation correctness or whole-App production readiness. Navigation must be
chosen from the actual private inspection, not an assumed initial page.

## Interfaces

`owned_inspect.py` with no arguments and `make_request.py` with no arguments are
inert PLAN modes. `make_request.py --write-once --source-manifest-sha256 <pin>
--output <new-file>` creates a request file only. The exact staged entry is
`owned_inspect.py --execute-once --source-manifest-sha256 <pin>`; only the fixed
hash-bound request may stage it at the remote root. No command is authorized by
this document alone. Do not execute the generated request from local tests.
