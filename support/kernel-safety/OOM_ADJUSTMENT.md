# OOM adjustment authorization prerequisite

This stage hardens OOM adjustment authority and lifecycle. It does not enable
`memory.max`, implement an OOM killer, or claim full memory isolation.

## Contract

Linux v6.2's [proc write path](https://github.com/torvalds/linux/blob/v6.2/fs/proc/base.c#L1059)
checks `oom_score_adj_min`, an authorized floor. Unprivileged writers can raise
the current value and return to that floor. They cannot cross it. Every
privileged non-legacy write replaces both current and floor, including a
privileged increase. Thus neither the current value nor a historical minimum
is the floor. Range errors remain `EINVAL`; floor denial is `EACCES`.

The [capability](https://github.com/torvalds/linux/blob/v6.2/kernel/capability.c#L448)
is `CAP_SYS_RESOURCE` in the initial user namespace. The actual writer's
capability is checked at each write, before the OOM transition lock. Proc file
DAC and dynamic dumpability/ownership remain independent existing checks.
Same UID alone does not grant a lower floor; `CAP_SYS_PTRACE` does not replace
this capability. New user namespaces remain unsupported.

## Lifecycle and implementation

`process/oom_adjustment.rs` owns a coherent pair, current VM identity and vfork
status. A transition mutex serializes writer propagation, fork inheritance and
process VM publication. A new child registers a copied pair in the same cut,
using the actual constructor called by `clone_child_process`. Shared Process
threads already use one pair. Separate `CLONE_VM` processes propagate current;
only a privileged write propagates the new floor. Global init is excluded from
peer propagation, matching Linux. Vfork is excluded from registration onward,
closing the previous later-flagging window.

A `VmarSnapshot` holds a weak allocation identity. Its control block cannot be
reused while the identity exists, but it does not retain physical VM mappings.
The pair belongs to the Process, not permanently to VMAR. `ProcessVmarGuard`'s
real VM publication changes the VM slot and cohort identity in one transition:
exec keeps the pair but detaches from old peers; exit invalidates the cohort
before zombie publication and before final Process reference release.

Lock order is the existing process VMAR `ostd::sync::Mutex` (if replacing its
VM), the sleeping transition mutex, then one IRQ-safe state spinlock. Writers
capture real authority first and take no VMAR/PID-table/TaskSet/credential lock
under the transition. `activate_vmar` has already left its preemption-disabled
scope before `set_vmar`. State operations never allocate or sleep under their
spinlock. Registry capacity is prepared outside the transition; publication
moves weak references into reserved capacity. Expired weak entries are pruned
when capacity is full. Their destruction frees control storage without invoking
a Process, VM or OOM wrapper destructor. The registry uses no strong Process
reference or strong VM mapping reference.

The OOM wrapper can be released during atomic-context Process teardown. Its
Drop only invalidates its state with the IRQ-safe spinlock, never waiting for the sleeping
transition mutex. A writer cannot restore a removed VM identity. Replaced weak
identities and old VM handles drop after the state/transition guards release.
The existing exit path still drops the old VM after releasing its original
VMAR guard.

Registry backing and Arc/Task metadata still use the existing infallible heap.
This stage deliberately makes no global OOM/recovery guarantee. The owner-aware
fallible kernel heap and physical/metadata reserve remain separate prerequisites
in [PAGE_MEMORY.md](PAGE_MEMORY.md). Dead registry weak storage can remain up
to the registry capacity until pruning; full memory reclaim must include it.

## Development and verification

The extraction commit retains the original unconditional store and original
clone snapshot cut. The next commit adds eight regressions. These tests use
owned, unscheduled real Process, TaskSet, PosixThread, Credentials, VMAR and fork
objects and call the same writer-aware operation as procfs. No test supplies
a privileged boolean, rewrites production authorization, or edits host proc.
The implementation adds a concurrency test using the real transition mutex
and an atomic-mode last-owner test. The first eight regression assertions stay
unchanged; constructor wiring follows the coherent inheritance representation.

Native image replacement/exit tests exercise the actual process-VM publication
primitive. They do not execute userspace exec/exit. Complete qualification needs
actual owned guest syscalls for proc DAC, per-write authority after credential
change/FD transfer, fork/CLONE_THREAD/independent CLONE_VM/vfork, exec and exit,
plus a complete aster-core/OSTD run from the exact source checkout. Preserve
before failures, source/ELF/log hashes and original unsupported-memory.max oracle.
No compilation, native run or ordinary guest result is claimed by this source
preparation. Heavy verification is serialized with the integration owner.

The existing `CLONE_THREAD` fast path does not establish a per-task vfork
handshake when combined with `CLONE_VFORK`. This stage does not claim that
combination is fully Linux compatible or silently turn it into a new supported
mode. Its ordinary shared-Process OOM pair semantics remain the thread path;
independent-Process vfork is the lifecycle covered here. Resolve and qualify the
combination separately before claiming every Linux clone/vfork mode.
