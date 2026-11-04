# Isolated signal runtime r4

This is a frozen source revision for review. It has no private Android runtime
verdict yet. Main remains unchanged. The original r1 wrapper has not received
a complete independent review; scoped reviews and controls do not erase that
boundary. Commercial app readiness remains outside this fixture.

## Why r4 exists

The a03 cell booted Android 17 / SDK 37 and passed its first strict framework
capture. Its first, single r2 SVC instrumentation command exited 134 before
creating a Java VM. The owned fresh userdata tombstone matches the exact nonce
and reports empty BOOTCLASSPATH and DEX2OATBOOTCLASSPATH. The old wrapper then
reported a missing claim file, obscuring the earlier command error. This was
not an ARM64 probe verdict. The original failure and exact cleanup are retained
in evidence/a03-report.json with external raw evidence pins.

A separate source review found a check-to-use window in numeric
nsenter --target. No wrong-target action was observed. r4 removes that command
entry path.

## Entry and environment

held_runtime.py holds the original init procdir, pidfd, all six namespace FDs
and root FD. It verifies the process generation around acquisition and before
entry. The shared Rust helper consumes only the seven namespace/root
authorities, marks them CLOEXEC, enters their namespaces and root, forks into
the held PID namespace, and reaps its direct child. The helper source, binary,
and actual parent qualification receipt are separate, mandatory pins.

After the first successful strict private framework capture, r4 reads only
BOOTCLASSPATH and DEX2OATBOOTCLASSPATH from that fixed private zygote's held
procdir. Required keys must be unique and nonempty. Every jar path must be
absolute and canonical. Each file is resolved with openat2 IN_ROOT |
NO_MAGICLINKS against the held private root, then streamed through SHA256.
Absolute APEX symlinks stay inside that root; mount crossings are permitted.
The limits are 256 KiB of environment, 256 distinct paths, 128 MiB per file,
768 MiB total, and 45 seconds. Main's classpath is never substituted.

Only after that admission can env -i launch instrumentation. Package, APK,
UID, nonce, durable report, mapped engine, Main epoch and private epoch checks
remain required. Each case has one invocation. No unknown outcome is retried.

## Failure and teardown

Nonzero instrumentation status is checked before any durable claim/result
read. Bounded failure diagnostics read only the held fresh cell: command
stdout/stderr, a bounded logcat snapshot and nonce/package-matching owned
tombstones. Their failure cannot replace the original command cause.

PDEATHSIG covers the helper's direct relationship only. It can be cleared by
credential changes and is not inherited by forked descendants. The original
command deadlines, exact owned package removal, cell stop, reverse systemd
cleanup and final readback remain required.

After the last Android readback, the loader inserts exactly one call to
release_held_binding(failures) before the original cell/daemon stop. If a
sampler is still alive, or a diagnostic child has not been reaped, admission
closes permanently and authority FDs are retained until controller exit.
The run fails. An external cleanup readback cannot rewrite that original
failure.

The original controller limit is still 10% CPU, 256 MiB, swap 0, TasksMax 128.
All original private-unit limits and preflight checks remain unchanged.

## Verification boundaries

The bundle retains the original a03 failure, the first host control fixture
failure (its own cwd was not /), the corrected 34-control run and source pins,
and the final controls after the unreaped-child hardening. The production
cwd guard was not weakened. The PID-slot control uses actual directory
replacement and held FDs; it is explicitly not a kernel PID-reuse experiment.

The 13 original admission/loader controls pass. A separate control captures
the actual loader AST and proves that all 18 retained functions match the
immutable v5 source after removing the single release call. The actual full
candidate host suite remains the separately qualified 3,793-registration
run; it was not rerun for a Python adapter change.

prepare_runtime.py checks the original host verifier in its actual r1 source
directory, the full host suite receipt, helper qualification and all source
pins before calling the original preparation function. It never starts
services. The new private runtime must still pass its own read-only check and
independent admission review before a fresh cell is started.

RUNTIME.md is the retained parent reference. Use the r4 entry additions listed
in runtime-interface.json; its helper and qualification options are mandatory.
No a04 input, nonce, image or service is created by this source bundle.
