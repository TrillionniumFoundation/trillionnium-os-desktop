# Pocket4 Android continuation r11 — checkpoint 04

This checkpoint preserves all 373 earlier payload files byte for byte and adds
the next native, signal, supervisor and pressure evidence. Main still runs R16.
No candidate engine, supervisor or LMKD lifecycle hook is deployed here.
Whole-application production qualification remains **0 of 45 launcher apps**.
Owned native probes and isolated pressure controls have the narrower scopes below.

## Actual Android metadata work

The prior r16 supplied-stack approach still failed after a private fork under
`RLIMIT_AS=1`: Bionic owner startup returned `EAGAIN`. All 13 direct children and
the nested child were reaped, and the exact owned package was removed. The old
aggregate `child_reaped=false` also included the failed behavior assertion; it
does not mean that a child was left alive. The original source and failure remain
in the [native checkpoint bundle](native-work/checkpoint-next-native-01/QUALIFICATION.json).
That historical bundle predates r17 device execution and is retained verbatim.

The new r17 experiment uses a fixed raw-syscall metadata worker with a private FD
table and a preallocated stack. Before execution, both the source and the actual
Android ELF were inspected. The complete Worker closure has no libc call, TLS
access, arbitrary callback, stack-canary helper or atomic runtime helper. The
review verifies the exact clone trampoline and its fixed Worker/null entry.
See the [actual ELF audit](native-work/evidence/raw-owner-r17-actual-elf/receipt.json)
and the [independent manual review](native-work/evidence/raw-owner-r17-actual-elf/manual-review.json).

The [r17 Android result](evidence/fd-owner-r17-actual-android-pass.json) records all
eight expected behaviors on app UID 10159, with all eight direct children and
one nested child reaped. The private-fork/AS=1 case successfully started, read
metadata and stopped using the inherited stack. Twenty-four restart rounds
observed kernel clear-TID completion before stack reuse. Installation, execution
and exact package removal all completed with the original Main epoch intact.
The [primary cycle receipt](native-r17-runtime/coordinator-result.json) preserves
the actual instrumentation output and the three runner reports.

The eight expectations include the known `RLIMIT_NOFILE=0 → EMFILE` failure.
This does not turn that limitation into production support. The worker is not
Bionic-pthread registered; credentials, capabilities, root, mounts, namespaces,
zygote/exec and retirement require a qualified lifecycle protocol. Full trusted
factory provenance, actual metadata projection and pathname operations are not
integrated by this experiment. The r17 build-01 coordinator key mismatch is also
retained separately; build-02 and its exact artifact pins are the executed build.

## Actual isolated signal attempt and diagnostic revision

The previously built candidate engine and complete native host suites remain
qualified only as recorded in checkpoint 03. Candidate engine SHA starts
`643db1c5`; the original Main engine remains `c8b9bae4`.

The [first isolated Android attempt](signal-android-canary-device-r1/report.json)
actually reached Android 17 / SDK 37 boot completion with the candidate engine.
It then failed in the original strict framework guard with
`FRAMEWORK_PROCESS_SET_AMBIGUOUS_OR_MISSING`, before any probe installation or
case execution. Its evidence does not identify which role was absent or
duplicated. A transient zygote explanation is a hypothesis, not a finding.
All four owned private services were subsequently absent, the exact init was
dead, their cgroups had no processes, and Main was unchanged. The controller's
original failed state is retained with MainPID 0 and no cgroup. Its memory-max
events are recorded without claiming them as the cause of the role error.

The [r2 source](isolated-signal-canary-runtime-r2/RUNTIME.md) adds a bounded census
of only the owned cgroup and init PID namespace. Before any probe mutation, it
may wait up to 30 seconds for the first successful original strict capture,
retaining each missing/ambiguous-role error and census. Every other epoch error
stops the flow. After the first success, the private epoch stays fixed and cannot
be silently replaced. All existing action, engine mapping and package cleanup
methods are unchanged. The already executed host suite remains bound to the
original r1 wrapper, whose host code, layout and test contract are byte identical.
The [original root review](acceptance-signal-runtime-r2-delta-review-r1/report.json)
covered this diagnostic delta. A later real preparation attempt exposed a loader
origin error: the copied verifier internally resolves its own directory, so it
compares the r2 manifest to the r1 pin. The attempt stopped before invoking data
preparation or starting Android. The [review correction](acceptance-signal-runtime-r2-delta-review-r1/admission-correction.json)
explicitly withdraws r2 runtime admission qualification and records that the
initial review missed this module-directory dependency. The fix must load the
verifier from the already verified r1 directory in both preparation and the new
r3 entry. No native host suite result is changed, and no new Android case was run.
Independent review of the complete original wrapper remains open.

The [actual a02 failure and absence report](signal-android-canary-device-r2/report.json)
confirms that no input receipt, case nonce, image, private runtime or service was
created after that rejected source admission. The [r3 review](acceptance-signal-runtime-r3-delta-review-r1/report.json)
then checks the minimal origin fix in both callers, reproduces the old rejection
using the real local source directories, and verifies the complete original r1
context through the new loader. Its fresh a03 input and source pins are distinct;
actual preparation, entry validation and four-case execution remain later gates.

## LMKD: full positive invocation and retained stale failure

Revision 07 was blocked because its final outer check could miss a live descendant
in another subgroup. Revision 08 additionally requires hierarchical
`pids.current == 1` while the single-threaded driver is still present, after all
children and the broker have retired. The final counters are captured before the
kernel can remove the empty cgroup, then bound to the external unit invocation.

The [actual r08 positive invocation](lmkd-pressure08-actual/pressure/coordinator/02-pressure-once/result.json)
passes the whole owned invocation: real default medium and critical PSI events,
a fresh critical event correlated with the cached victim, native critical kill
diagnostic, protected/foreground survival, final inner and outer resource checks,
exact cleanup and unchanged Main. The external first/final cgroup identity and
driver lifetime are verified. A [root read-only reproduction](acceptance-lmkd-pressure08-actual-root-review-r1/report.json)
checks all exported file hashes, reruns the scoped qualifier and reproduces the
external unit binding. This remains a PIDFD-only minimal-root fixture; it does
not qualify the production cgroup-kill route, PID reuse or installed recovery.

The [r08 stale invocation](lmkd-pressure08-actual/stale/coordinator/02-stale-once/result.json)
failed before its age/resume segment. After pausing its exact owned LMKD, the
fixture exhausted the entire eight-second allocation-ramp deadline while still
trying to reach 416 MiB. It did not produce the required completed phase and
joined broker audit. Exact cleanup and Main preservation passed. This is neither
a stale-event pass nor evidence that a stale event killed a target.

The [r09 source](lmkd-work/host-pressure-freeze-09/owned-relay/PRESSURE.md) stops its
stale ramp after a complete allocation ACK, while above the original high limit
and with sufficient scoped full-pressure accumulation. That total only selects
when to stop allocating. Qualification still requires an actual queued critical
event in the joined audit, sent while LMKD is stopped and strictly expired before
resume, with zero kills and all targets alive. Medium-only events cannot qualify
the critical stale check. The original PSI registrations, eight-second total
ramp deadline, memory limits and swap prohibition are unchanged.
The [independent r09 review](acceptance-lmkd-pressure09-review-r1/report.json)
records the source changes and five bounded controls, including old-pass/new-reject
for a medium-only aged queue. The [actual matching r09 build](lmkd-work/pressure09-device-build/build-result.json)
then passed 20 Rust, seven ordinary IPC and 23 Python controls, plus strict actor
compilation. Its 36 source inputs are unchanged before and after the build. The
broker and driver binaries remain byte identical to r08; the actor has a new
hash. Actual r09 pressure runs remain separate from this build qualification.
The [r09 coordinator review](acceptance-lmkd-pressure09-review-r1/coordinator-review.json)
binds the actual new actor and unchanged driver/broker binaries, new isolated
positive/stale profiles, and three explicit critical-stale qualification flags.
The stale phase requires an externally pinned completed positive invocation of
this same revision, including exact cleanup and unchanged Main.

## Supervisor cleanup source fix

The [supervisor cleanup revision](lmkd-work/supervisor-cleanup-freeze-01/README.md)
is bound to the source that produced the currently installed supervisor. It
retains unfinished cleanup ownership on failure and does not report cleanup
success merely because a retry occurred. The daemon keeps the active retirement
record and refuses a new start while cleanup is incomplete. An explicit later
stop retries only the unfinished work.

The original false-success failure is reproduced. The first build's stale Cargo
target reuse was detected and retained as a failed qualification. A fresh
matching build passed 81 library plus 10 CLI tests and built all three debug
binaries. The [root review](acceptance-supervisor-cleanup01-review-r1/report.json)
checks the compiled sources, exact patch application/reversal and actual build
receipt. No host network mutation or deployment is part of these controls.
The wire response adds `cleanup_failed`, so the three executables must eventually
be released together. Same-daemon retry is covered; recovery across daemon loss,
actual LMKD lifecycle integration and release deployment remain open.

## Evidence policy and remaining work

Historical receipts and source freezes are never rewritten to reflect later
results. The [artifact index](artifact-index.json) provides every copied file's
source, digest and scope, while the delivery manifest includes the full retained
payload. APKs, ELFs, keys, data images, private boot journals, raw commercial logs
and the complete package/UID inventory are excluded.

Required next work includes the fresh isolated signal cases, matching r09
positive and critical-stale runs, production metadata and lifecycle integration,
release qualification, and actual application business-flow acceptance. None of
the source controls above replaces those gates.
