# Scheduling write permissions

## Contract and implementation

`sched_setattr`, `sched_setscheduler` and `sched_setparam` retain the original
target-identity gate: caller effective UID must match the target's real/effective
UID, or the original LSM `SYS_NICE` check must authorize the target namespace.
A strong target Process survives the entire update; the PID table is released
before credentials, namespace authorization and writer administration. The
three scheduling getters keep their original cross-user authorization behavior.

The authorized writer then obtains `SchedAttr::administer()`. This sleepable
per-thread mutex serializes all live policy writers and retains static nice
across RT policy changes. It also records an explicitly requested user Idle
policy. The copyable `UserSchedSnapshot` supplies `policy()`, `linux_policy()`,
`nice()` and `static_priority()`. All three public getters read this same coherent
snapshot, so ordinary Normal nice 19 is distinct from declared Idle, RT static
nice is retained, and `sched_getparam` reports Linux rather than reversed internal
RT priority. `SchedAttr::from_user_snapshot` constructs an unpublished attribute
for the actual fork/CLONE_THREAD inheritance path described below; it does not
change a live task or grant authority. The rq hot path does not use this snapshot mutex.

The writer copies the old policy through the short policy spinlock, releases
that lock, reads the actual target soft limits and validates the change. Zero
`RLIMIT_RTPRIO` prevents entry into RT or changing FIFO/RR class. A nonzero limit
permits a priority up to the larger of that limit and the current Linux static
priority. Same-class RT decreases and unchanged priorities remain allowed.
Nice decreases require `20 - requested_nice <= RLIMIT_NICE`. Exiting declared
Idle additionally checks the retained static nice. When a resource check
requires privilege, the existing target-namespace `SYS_NICE` hook is used.
UID 0 without that capability receives no exception.

`sched_setparam` converts Linux static priority through `static_to_rt`; internal
RT ordering is reversed and cannot be compared with Linux limits directly.
`sched_setscheduler` supplies the retained nice instead of parser default zero.
Unknown `sched_flags` return `EINVAL`; currently unimplemented known flags
return `EOPNOTSUPP` without mutation. No reset-on-fork, keep-policy/parameters or
utilization-clamp success is fabricated.

The rq hot path never takes the administration mutex. Its readers continue to
take only the existing short policy spinlock. Lock order is administration →
short policy snapshot → release spinlock → target limits/credential/LSM checks
→ short policy publication. A policy-update callback must not acquire sleeping
locks. Raw policy mutation is private; controlled non-running queue fixtures
retain a `cfg(ktest)` construction seam.

## Development and verification

Build OSDK from this exact worktree with **compile-time** `OSDK_LOCAL_DEV=1`.
Setting it only while running an already-built tool does not select local
OSTD dependencies. A separate Cargo target may share dependency caches; never
copy another worktree's `cargo-osdk` executable.

`tests/kernel/sched-policy-limits/run.py` compiles its C probe and executes it
only in an ordinary owned QEMU guest. Each scenario gets a separate process,
real target soft limits and an explicit all-capabilities drop. Results check
both return codes and the actual scheduling state after refusal. The test-only
before commit leaves P1 kernel bytes unchanged. Its 58 assertions actually
reported 30 failures, including unauthorized RT/nice changes, priority 5 being
reported as 95, nice 8 resetting to zero and ignored flags returning success. The first P2 after run passed Core 345 and
all 9 groups, but did not cover the legacy getter defect. A subsequent frozen
probe-only stage added 160 assertions and actually found 21 readback failures.
Those failures remain separate evidence; no test success is inferred from the
internal state alone.

Run the same probe on the changed source, plus `aster-core` kernel tests,
`sched-policy-auth`, `affinity-auth`, and `fair-runtime` on supported SMP
profiles. Use exact-source ordinary product receipts; retain failed runs and
separate source manifests. Controlled kernel tests are not physical CPU
migration, real-time latency, phone hardware or production-authority evidence.

## Per-thread priority and inheritance

`setpriority` and `getpriority` select a real TID for PRIO_PROCESS; zero means
this calling thread. PGRP collects actual group threads. USER filters each
thread's real UID, including different UIDs within a thread group. Selection
retains strong Thread and Process identities, then releases the PID table,
process-group and TaskSet locks before credentials, snapshots or administration.
There is no process-local nice shadow.

Every mutation checks target real/effective owner or the original target-user-
namespace SYS_NICE hook before administration. An unauthorized owner receives
EPERM. Under administration, an increase checks the target's full-width soft
RLIMIT_NICE using `20 - requested_nice`; lack of the required privilege returns
EACCES. SYS_NICE permits otherwise disallowed increases. Each permitted target
is updated even if another target fails; a later success does not erase an
error, and the last failure wins, matching Linux v6.17 `set_one_prio`.

Normal nice updates publish the actual Fair state and weight. RT and declared
Idle updates change only static nice, preserving class and RT priority. Query
and `/proc/<pid>/task/<tid>/stat` obtain the same canonical read snapshot. The
proc read takes it before any VMAR guard and after earlier temporary locks end.
`user_snapshot` takes only the short administration-state mutex and policy
spinlock directly; it never calls writer `administer` or waits for a pending
placement request. The rq hot path remains unchanged.

Fork and CLONE_THREAD capture a copyable UserSchedSnapshot before cgroup,
TaskSet, PID-table or TSYNC locks. POSIX construction installs it into a fresh,
unpublished SchedAttr. This inherits declared class, static nice and RT
parameters, not a live mutex, pending placement, affinity generation, last CPU,
runqueue state or accumulated CPU debt. The kernel-thread constructor continues
to build a new attribute from its explicit policy.

The separate `priority-inheritance` guest probe checks normal/RT/Idle parents,
real pthread inheritance, non-leader selection, group/user partial success,
UID 0 without capabilities, nonzero/infinite limits and proc/query consistency.
Its first frozen probe-only stage retained P2 kernel bytes and actually reported
106 failed assertions out of 184. These failures remain before evidence;
implementation success requires running the same probe on the changed source.

Priority API reference: [Linux v6.17 sys.c](https://github.com/torvalds/linux/blob/v6.17/kernel/sys.c)
and [getpriority/setpriority](https://man7.org/linux/man-pages/man2/setpriority.2.html).

Scheduling policy references: [sched(7)](https://man7.org/linux/man-pages/man7/sched.7.html)
and [Linux v6.17 scheduling syscalls](https://github.com/torvalds/linux/blob/v6.17/kernel/sched/syscalls.c).
