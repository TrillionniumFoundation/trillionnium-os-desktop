# G1-d unprivileged workload qualification

This change narrows the experimental three-process G1-d bootstrap. It does not
establish production Hepta integration, SMP qualification, device isolation or
durable delivery history. The ordinary product and G1-c profile are unchanged.
The [guest runner](run_g1d_guest.py) must pass on the actual reviewed kernel;
fixture tests only establish that its verdict refuses missing or inconsistent
evidence.

## Credentials and startup ownership

`process/process/init_proc/trusted_roles.rs` constructs the workload's private
credentials before attaching them to its stopped task. Real, effective, saved
and filesystem UID/GID are all **60001**, distinct from the manager and recovery
UID/GID 0. This fixed profile has exactly one workload; a future allocator for
multiple independent workloads must assign distinct identities itself.

Supplementary groups and all five Linux capability sets are empty: permitted,
effective, inheritable, bounding and ambient. The kernel sets `no_new_privs`,
locks `NOROOT`, and locks `NO_CAP_AMBIENT_RAISE`. Their securebits value is 195.
The temporary root credential object used for initialization is private and is
never attached to a task before all restrictions succeed. Failure aborts the
sealed bootstrap before any user instruction runs.

The workload enters a separate session and process group using the existing
process/session owner. This is necessary because Linux signal permission rules
allow `SIGCONT` within a shared session even with distinct UIDs and no
`CAP_KILL`. Its parent remains the manager, so normal child reaping works.
Manager and recovery retain their original resource domains and root credentials
in this experimental profile. Root service minimization is a separate task.

`/dev/console` is root-only. The manager performs its original first-process
device/console setup, then captures exactly descriptors 0, 1 and 2 before
releasing either stopped child. The workload installs those already-open file
handles in its own file table before its first userspace instruction. It cannot
reopen the root-only device or inherit later manager descriptors. File offsets
and the console object may be shared; mutable descriptor tables are separate.
No file-table/queue lock is held while starting a child task.

## Per-process virtual address-space limit

The same stopped bootstrap allocates the workload with an original
`RLIMIT_AS` soft and hard limit of **268,435,456 bytes (256 MiB)**. Manager and
recovery keep their original limits. The generic initial allocator takes the
already-created `ResourceLimits`; it does not temporarily attach unlimited
limits to a running workload. Because initial loading happens in a kernel
task, the trusted loader also checks the actual loaded VMAR mapping total
against that workload's own limit before constructing or releasing its task.

Enforcement reuses `VmarInner::check_extra_size_fits_rlimit`, and hard-limit
changes use the original capability check for `CAP_SYS_RESOURCE`. No duplicate
mapping counter or new syscall is introduced. Existing Process limits are
copied by fork and retained by exec. The exact build manifest records
`workload_address_space_bytes=268435456`.

The real probe records the complete soft/hard pair before and after refused
changes in its initial workload, fork child and exec child. In all three it
requires an additional 256 MiB `PROT_NONE` mapping to fail with `ENOMEM`, raising
the hard limit to fail with `EPERM`, and setting soft above hard to fail with
`EINVAL`. A normal 4 KiB read/write mapping must still succeed and retain writes
at both endpoints before being unmapped. The runner binds all three records
to the actual workload and fork/exec PIDs and their causal ordering.

This is a **per-process virtual mapping bound**. It is not resident-memory
accounting, `memory.max`, an aggregate process-tree memory budget, or a fork
limit. A set of forked processes can still consume more total memory than one
address-space limit, so recovery-resource survival under aggregate memory
exhaustion remains unqualified. `RLIMIT_NPROC` is not used as an asserted fork
limit because the current clone path does not enforce it.

## Actual syscall observations

The static C image runs the isolation checks in the workload itself. The runner
requires the raw observations in order before accepting the existing HOS2 and
CPU-management results:

| Check | Exact required observation |
| --- | --- |
| Initial credentials | Eight UID/GID fields 60001, no supplementary groups, five capability sets zero, `no_new_privs=1`, securebits 195, SID equals workload PID |
| Cross-role signals | `kill` with signal 0, STOP, TERM, KILL and CONT fails with `EPERM` for each of manager and recovery: ten observations |
| Return to root | `setresuid(0,0,0)`, `setresgid(0,0,0)` and root supplementary-group assignment fail with `EPERM`; filesystem IDs remain 60001 |
| Capability escalation | Raising permitted/effective or ambient `CAP_KILL` fails with `EPERM`; clearing securebits fails with `EPERM`; clearing `no_new_privs` fails with `EINVAL` |
| Process inspection | `PTRACE_ATTACH` returns the profile's existing unsupported `EIO`; supported `PTRACE_POKEDATA` fails with `ESRCH` because neither target is the workload's tracee; opening either trusted process's `/proc/PID/mem` and `/proc/PID/maps` fails with `EACCES` |
| Trusted coordination | Workload cannot rewrite the readiness record or create a forged recovery command (`EACCES`) |
| After denied actions | A second complete credential observation remains unchanged |
| Privileged executable | Workload forks and execs a real root-owned mode-04755 copy of the static probe; its child still reports the complete unprivileged credential state and no bootstrap auxv |

There are seventeen named denial observations in addition to ten signal checks,
three full credential observations, three address-space observations and one privileged-file exec. The runner
requires every record once, exact return values/errnos, actual distinct PIDs,
and causal ordering. `PTRACE_ATTACH` is not implemented by this kernel; its
`EIO` is recorded as an unsupported operation, **not** claimed as an exercised
ptrace authorization check. The supported ptrace write and two proc interfaces
independently exercise existing access checks. This profile does not prove general device, namespace,
network or filesystem isolation.

The guest manager creates the coordination directory mode 0755, precreates and
assigns only the workload heartbeat to UID/GID 60001, and publishes a read-only
readiness record. Recovery command/reply files remain root-only. The guest test
sets `/dev/hepta-control` mode 0666 so the workload can exercise QueryAbi and
receive real HOS2 permission denials; mode bits do not install capability slots.
Only the guest test setup changes these modes, not the default device policy.

## Frozen old-root kernel control

[run_g1d_workload_negative.py](run_g1d_workload_negative.py) first revalidates the
positive run's full source snapshots, actual ELF and raw serial verdicts. It
creates a detached sibling worktree and changes exactly one production line:
the workload branch uses `Credentials::new_root()` again. The source snapshot
gate rejects any additional modified file or dependency. It writes the exact
patch, original/postimage, temporary commit/tree and full before/after snapshots
to evidence. No fixture or probe changes are allowed.

The unchanged runner builds the negative kernel and runs its original three
boots. Its positive oracle must reject the exact-image boot; both altered-image
controls must still reject before starting userspace. The compiled C probe must
be byte-identical to the positive probe, while the kernel must differ. BIOS,
QEMU, original initramfs and generated package lock must stay identical.

The additional negative oracle requires root credentials, full root permitted,
effective and bounding sets, and actual successful `kill(manager,0)` and
`kill(recovery,0)` permission checks. The probe then stops at
`workload_privilege_boundary` **before sending any destructive signal**. The
manager observes the missing heartbeat and powers off at
`workload_really_running`. QEMU must exit 33 without timeout, kernel panic,
other assertion, unexpected success or unrecognized record. An arbitrary
failure does not qualify the negative kernel.

All positive, old-root and altered-image boots use the same `loglevel=warn`
kernel argument. The sealed-loader and role-activation records use unconditional
kernel `println!`; the `G1D_` records use guest writes. These observations,
WARN/ERROR diagnostics and panic detection remain available. Informational
per-syscall tracing is excluded because the unchanged old-root probe waits for
the manager's full 30-second heartbeat deadline, whose 2 ms polling otherwise
can exceed the original 8 MiB serial admission bound. The bound, wait, two exact
failure observations and required QEMU exit 33 remain unchanged. Complete raw
serial is retained; over-limit earlier logs are not trimmed or reclassified as
passing. A logging-profile change requires fresh positive and old-root runs,
including both altered-image controls for each kernel.

CI retains both kernels, unchanged probe, source identities, build records and
all six guest logs. Run the commands in
[the G1-d workflow](../../../.github/workflows/g1d-trusted-control.yml) only in a
disposable build environment. The runner removes only its own clean temporary
worktree without force; unexpected edits are retained for diagnosis.

## Remaining recovery scope

The ordinary management interval remains 300 seconds. A subsequent
[bounded recovery slice](G1D_BOUNDED_RECOVERY.md) permits one narrowly defined
nonzero-budget restoration after manager closure or expiry. It never treats
an unclassified zero cap as permission to resume, and does not clear a process
stopped by `SIGSTOP`. Full explicit user-pause intent remains a protocol task;
the recovery subset does not establish completion of all E isolation work.
