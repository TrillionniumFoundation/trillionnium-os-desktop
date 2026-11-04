# LMKD source-r5: bounded pending high evidence

Status: source candidate only; not Android-built, not run under real pressure,
not deployed to Main, and not production ready. The r7 foreground death and r8
global-PSI guard abort remain separate failed acceptance results. This change
does not explain either failure or authorize deployment of r4/b099.

## Defect and narrow change

The real r4 Reader advances its accounting baseline on every successful read.
A medium event or poll can observe a new `memory.events.high` increment before
an actual critical PSI notification. The critical read then sees the same
counter, loses the increment, and incorrectly takes the no-scan early return.
The frozen r4 test compiles the actual Reader and no-scan source; both medium
and poll arms compile and fail the exact missing-evidence assertion.

r5 keeps the accounting delta unchanged and adds a separate pending token to
the Reader's pinned FD lifetime. Only a coherent new high increment above the
same finite high budget can create it. Repeated reads cannot extend its age.
The existing PSI monitor window bounds that age, measured by the actual
monotonic clock in nanoseconds. No pressure threshold or window is changed.

Only the existing actual-critical-PSI condition consumes a token, once, before
the reclaim guard. A critical decision using ordinary reclaim also consumes
it, so a later no-scan event cannot reuse that same evidence. Medium, polling,
vendor, and host-mode paths do not consume a cell token. Original AOSP
watermarks, critical-PSI policy, process ranking, watchdog, pending-kill checks,
kill timeout, signal delivery, and OOM scores remain unchanged.

Pending evidence is cleared by a failed read, counter rollback, usage at or
below high, an unlimited high, any changed high/max/swap budget or mode,
invalid or changed monitor window, expiry, monotonic clock failure/rollback,
explicit invalidation, attempted Open, Close, and monitor teardown. Close
releases every acquired FD and clears the accounting generation. Reopening
the same numeric descriptor does not preserve a prior token. FD pinning
prevents path replacement from transferring evidence to a new cgroup.

Additional required-input failures in the LMKD handler explicitly invalidate
pending evidence. A failed accounting read still publishes no partial
snapshot. Read failure does not erase counter rollback detection. The token
uses fixed storage with no heap allocation, string formatting, or logging.
The r4 pre-kill diagnostic remains byte-identical for the separately frozen
r9 syscall/FD experiment; this candidate does not combine a logging change.

## Source controls

Run `review-r5/run_controls.py` with explicit `--source-dir`, `--baseline-dir`,
`--r4-tests-dir`, and a new `--out-dir`. It requires C++17, a C++ compiler, Python
3, and the frozen r4 test sources. Descriptor and clock substitutes are used;
no live process is registered, signalled, assigned an OOM score, or moved into
a cgroup, and no live memory pressure is generated.

The current local run preserves 57 accounting/parser assertions and 20 real
Reader I/O assertions, and adds 326 lifecycle/state-transition assertions.
Those include one-nanosecond clock rollback, exact expiry boundaries, invalid
and changed windows, stale count reuse after consumption, every budget field,
both finite/unlimited transitions, below-high recovery, all required-file
read failures, malformed counters, concurrent budget change, permanent
counter-rollback failure, Open/Close/destructor cleanup, and new generations.
The count includes setup and intermediate-state assertions, not 326 distinct
test scenarios.

The actual-source sequence harness compiles the r4 and r5 Reader plus their
actual no-scan guards and, for r5, the actual critical-consume block. The r4
medium/poll binaries each exit 2 at the intended final assertion. Each r5 arm
passes 18 assertions, including a repeat critical event, ordinary-reclaim
consumption, vendor and host exclusions, and unchanged reclaim/refault paths.

Fifteen existing selection/registration controls pass. Six AOSP selection,
registration, kill, watchdog, and record-claim functions remain byte-identical
to r4; the r4 publication pins their identity to upstream LMKD commit
`c3601e823bd07c9c190f67e2f9bc7486e4978328`. Property expressions for the original
PSI, stall, pending-kill, and post-kill policy are also compared unchanged.
These controls cannot prove foreground survival during a real stalled daemon.

## Next gates

Keep fixed r9 diagnostics on b099 and obtain parent coordination for any new
owned trial. r5 needs an isolated Android build and its own immutable binary,
source/dependency manifest, fresh freeze, protocol test, and actual canary.
Do not replace any existing run or infer an earlier result for this source.

Acceptance still requires exactly one cached-process kill with a genuine
notification, foreground/protected/sentinel survival, zero OOM, recovered
owned-domain usage, empty owned-unit cleanup, unchanged Main host/init plus
zygote/system_server/surfaceflinger identities, and all original host/Main
admission and health guards. No threshold, limit, workload size, process
placement, OOM score, or protected-process rule may be changed to make it pass.

The existing Android build depends on frozen toolchain, dependency records,
support objects, CRT inputs, and platform DSOs. Source tests alone do not make
that build hermetic. No Android binary or key material is included here.
