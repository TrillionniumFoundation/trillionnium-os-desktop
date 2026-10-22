# G1-d retained-task boundary

This slice adds a workload-only `pids.max=16` to the existing, opt-in, single-CPU
G1-d bootstrap. The same original hierarchical pids controller accounts forks,
threads, and unreaped process leaders. It does not create another authority,
budget store, HOS2 operation, or grant provider. Manager and recovery stay in the
root cgroup, outside the finite workload leaf, before any role resumes.

The candidate requires a real product build and native qualification. Passing
the host parser tests or compiling the static C probe does not establish kernel
correctness. The existing CPU history, cap-zero stop, manager-exec revocation,
independent recovery, and explicit user-pause checks remain mandatory.

## Accounting and release points

The membership lock is the transaction boundary. Fork and `CLONE_THREAD` reserve
one slot in every active ancestor before fallible construction. Their original
RAII precharge guard rolls every reservation back on failure. Publication of the
new process/thread commits the reservation before the task can run.

`TaskSet::pids_count` includes the retained dead leader. Controller activation
and process migration hold the membership writer and count every TaskSet entry;
they never infer thread counts from the process-map length. Explicit migration
may exceed a destination limit, as documented by the [cgroup-v2 PID controller
contract](https://docs.kernel.org/admin-guide/cgroup-v2.html#pid); subsequent fork
and thread creation still enforce every applicable limit.

For a nonleader exit, the membership reader spans TaskSet removal, release of the
TaskSet lock, removal from the PID table, and refund. This preserves the lock
order used by exec and completes the refund before `clear_child_tid` wakes a
joiner. A tracer may retain an `Arc<Thread>` afterward; that does not retain the
PID-table entry. The existing `Thread` owns a `Weak<Task>`, and the numeric TID
allocator is monotonic with an existing recycling FIXME. This slice bounds
charged tasks/PID entries; it does not bound all retained tracing metadata or
fix numeric PID recycling.

An exited leader remains charged until a consuming wait reaps the process, or
until a nonleader exec replaces the retained leader. `WNOWAIT` and orphan
reparenting do not refund the charge. Reap takes membership before the parent's
children lock and PID table. Nonleader exec takes membership before PID table,
tracer state, and TaskSet; it refunds the replaced leader after the PID-table
replacement.

The original node process map retains zombie entries as the charge index.
Zombie processes are hidden from `cgroup.procs`, do not contribute to
`cgroup.events` population, and do not block the no-internal-process rule.
Publishing zombie state and removing its live population contribution occur in
one membership-writer transaction. Reap removes the hidden entry without
decrementing population again. Controller activation still sees its retained
charge through the same map.

Removal of a cgroup with retained tasks remains conservatively `EBUSY` until
reap. Existing deferred CPU charge leases also pin such nodes. Supporting Linux
removal of zombie-only groups requires a separate, reviewed tombstone/charge
lifecycle; this slice does not claim that behavior.

## Native acceptance cases

`g1d_pids.c` is included in the original sealed `g1d_init.c` probe. The build
uses static pthread support and freezes the included source as an execution
input. The bounded cases run in the disposable native guest:

| Case | Required observation |
| --- | --- |
| Late activation | A process with three tasks joins an inactive descendant; activation starts its count at three. |
| Leaf and ancestor rejection | Both fork and thread creation return `EAGAIN`; failed ancestor precharges roll back the leaf; the refunded slot can be reused. |
| Whole-process migration | All three charged TIDs move, including a retained dead leader; moving to root removes the original hierarchy's count. |
| Zombie visibility | `WNOWAIT` leaves one charged leader, no visible `cgroup.procs` member, and `populated 0`; controller activation remains possible. |
| Invalid clone copyout | Two fork and two thread `CLONE_PARENT_SETTID` faults return `EFAULT`; current count remains one. |
| Descendant saturation | One workload, one child, and fourteen grandchildren reach sixteen; fork and thread creation from the workload and its child return `EAGAIN`. |
| Independent role capacity | At actual workload count sixteen, the original manager and recovery each fork and reap a root-cgroup child successfully. |
| Zombie saturation | Fifteen exited children remain unreaped, keeping current count sixteen; repeated `WNOWAIT` cannot release capacity. One consuming wait releases one reusable slot. |
| Thread saturation | Fifteen pthreads plus the workload reach sixteen; both clone kinds are denied; join releases a reusable slot and cleanup returns to one. |
| Nonleader exec | A workload child execs from its nonleader thread; the new image observes only workload plus child, proving the old leader was refunded exactly once. |
| Low-privilege controls | The workload cannot open its `pids.max`, membership, root migration, or controller-disable paths for writing (`EACCES`). |

The existing guest oracle requires each fixed record exactly once, exact role
identities, ordered saturation/reserve/refund observations, and the existing
native CPU results. Unknown records, alternate errno values, missing cases,
duplicate evidence, timeouts, or panics fail qualification. The source-pinned
root-credential negative control continues to require its exact unsafe
observations with this same C probe.

## Validation commands

Use the ordinary repository commands and the existing G1-d runner from a clean,
reviewed head/tree:

```sh
python3 -I -B tests/kernel/control/test_g1d_guest.py
python3 -I -O -B tests/kernel/control/test_g1d_guest.py
python3 -I -B tests/kernel/control/run_g1d_guest.py \
  --expected-source-head <reviewed-head> --expected-source-tree <reviewed-tree> \
  --target-dir <fresh-target-outside-source> --output <fresh-evidence-directory>
```

Run the full required core gate and the existing SMP gate on the same runtime
source. No new ktest is added and the expected core test count is unchanged.
Retain the static probe digest, product kernel digest, source snapshots, raw
serial, exact-image result, and both altered-image rejection results.

## Minimal semantic negative controls

These are isolated, local mutant builds of the frozen positive source. They
must use the byte-identical C probe and oracle. A panic or unrelated failure is
never a successful negative control.

1. **Thread admission bypass with correct accounting.** In the mutant only,
   duplicate the original `Controller::pre_charge_pids` as
   `pre_charge_thread_without_limit`, replacing its `try_charge_hierarchy()?`
   with `charge_hierarchy(1)` while retaining the same RAII guard. Change only
   the `CLONE_THREAD` call to this method; fork stays unchanged. Thus creation,
   rollback, and exit still balance and the mutant cannot win by underflow.
   The first threaded leaf-limit check must print
   `G1D_PIDS_THREAD_LIMIT_UNSAFE rc=0 expected=11 pid=<accounting-child> parent=1`,
   fail exactly at `pids_thread_must_return_eagain`, and fail the positive
   oracle. The manager then observes pipe closure and powers off after its
   exact `pids_pipe_read` failure. No completed accounting or workload marker
   may appear, and no panic/timeout qualifies.
2. **Premature zombie refund.** In the mutant only, insert
   `cgroup.controller.uncharge_pids(1)` in `hide_zombie_process`, before its
   population update. The accounting child retains its dead leader while two
   threads run, then exits fully. The original `WNOWAIT` case must print
   `G1D_PIDS_ZOMBIE_RETAINED current=0 ancestor=0 wnowait=1` and PID 1 must fail
   exactly at `pids_zombie_charge_retained`. The probe powers off before a
   consuming wait, so a later double-refund cannot masquerade as the oracle.
   No completed accounting/workload marker, panic, or timeout qualifies.

## Scope that remains open

`memory.max` is still a stub. The existing 256 MiB `RLIMIT_AS` is per process,
not an aggregate memory controller. Kernel memory, retained tracer metadata,
filesystem cache, and allocation pressure need separate accounting and recovery
work. Being outside the workload pids leaf preserves manager/recovery pids
capacity; it does not reserve physical memory or guarantee scheduling latency.
The manager and recovery still have their existing privileged Linux identities;
this is a low-privilege workload boundary, not a new confinement policy for root.

This slice does not qualify native Hepta production authority, disk durability,
automatic manager-failure/lease recovery beyond the existing G1-d checks, SMP
trusted control, hardware, or the complete E milestone.
