# Prepared FAIR group entities (W2A internal stage)

## Status

W2A supplies reusable per-CPU parent/child queues and selection transactions.
It is **not delivered `cpu.weight` support**. The ordinary scheduler uses the
same `GroupTree` implementation's legacy root leaf, replacing its former
standalone task heap. No ordinary cgroup is routed into a non-root scheduling
entity yet. Every `cpu.weight` write still fails.

W4A adds a cold lifecycle lease to every prepared POSIX Task binding. This
prevents controller replacement or node deletion while the original route is
still retained. It does not connect ordinary cgroup membership to these queues
or qualify live relative weights.

Prepared non-root topologies are exercised using original CPU-controller
incarnations, actual POSIX Task objects and the production class-runqueue
selection/settlement path in native kernel tests. They are internal controlled
queue evidence, not live CPU-share, unequal-weight or SMP qualification. There
is no new trusted bootstrap, management capability or test authorization.

## Preparation and identity

`CpuSchedulingGroup` retains the actual CPU `SubController` incarnation and its
immutable ancestor chain. Identity never follows a node's later RCU slot or a
reused cgroup path. Inactive CPU controllers normalize into an active ancestor.
The descriptor exposes identity/parent/weight reads only: it is not a budget,
membership binding, native authority or cgroup-node lifetime lease.

The separate move-only `CpuSchedulingRoute` owns the original raw CPU leaf and
every raw ancestor, including inactive levels that normalize to an active
scheduling group. Capture holds the existing membership read lock and reads the
live Process binding directly. It refuses exited Tasks or an unavailable
Process; the old final-charge fallback remains available to accounting only.
Each prepared binding keeps its route until the whole prepared tree is retired.
Unused group descriptors without a prepared descendant binding do not acquire
an independent node lease.

All route counters live on the original CPU controller even when its optional
CPU control is absent. Checked acquisition refunds only its successful prefix
on overflow. Partial preparation, duplicate admission and invalid bindings
refund all captured routes through normal ownership. The existing
`CpuChargeOwner` supplies the node's deferred-accounting lease without creating
another budget or modifying CPUmax debt.

CPU activation and deactivation hold the membership writer and check affected
direct children before changing the active set or replacing any controller.
This checks the whole affected subtree: a strictly current raw route pins each
original ancestor, so any pinned descendant also pins its current direct
ancestor. The read/write membership cut excludes capture during subtree
replacement. A nonzero counter returns `EBUSY`; unrelated branches remain
modifiable. Existing node deletion rejects the retained original node lease.

The cold `GroupTree::prepare` constructor rejects atomic context, malformed
parent chains, duplicate incarnations, stale owner bindings and duplicate task
slots. New node, sorted weak-task binding and heap storage is reserved fallibly
before publication. Preparation failure drops the partial metadata. A prepared
queue refuses an unknown Task and returns its original `Arc` without changing
the queue. It never silently moves that Task to root.

All prepared group and task slots have fixed admitted counts. Child activation,
enqueue, select, commit/cancel and ancestor accounting grow no group, path or
task containers. Selection walks parents/children without allocating a path.
The internal fixture also reserves the existing throttled vector beforehand.
The production legacy root task heap and unprepared throttled-vector growth
remain existing allocation gaps; W2A does not claim a globally allocation-free
scheduler or complete kernel-heap accounting.

## Runtime and locking

Each node has its own task queue, child-group queue, active/current state,
virtual runtime and period. A parent sees one runnable child entity independent
of its descendant thread count. Nice weights divide service within a leaf.
The running ancestor path is separate from queued entities; switching tasks
inside a subtree preserves its ancestor's period/debt instead of resetting it.
Reactivation clamps old debt to the parent's virtual-time floor without idle
credit.

The original scheduler now selects a move-only FAIR token. Both existing
CPUmax eligibility checks cancel that token when rejecting a candidate. Only
the actual successful handoff commits the new current path. Cancellation
restores remaining runnable group paths while keeping the old current owner;
the candidate accrues no CPU time. A selected, not-yet-committed candidate still
participates in virtual-time minima during the outgoing handoff tail.

W1's high-water settlement charges the original task and current ancestors
through the exact incoming cut. CPUmax retains its separate original owner,
BOOTTIME cursor, fault and overrun-debt rules. Configuration checkpoints settle
the whole class queue before applying the existing bandwidth callback. The
class slice counters are not reset by these checkpoints.

All runtime tree mutations belong to the existing IRQ-disabled local runqueue
lock. They acquire no sleeping membership/node lock and no remote runqueue.
The existing policy snapshot lock order remains runqueue → policy. Group
descriptors never grant permission to mutate an original CPU owner.

Route capture and prepared-tree construction are cold operations. Their lock
order is membership read → short RCU owner observation; topology changes use
membership writer → existing node/controller locks. Scheduling selection and
settlement do not acquire membership or allocate route metadata. A nonempty
prepared tree must be moved outside every runqueue lock and IRQ-disabled scope
before its final destruction: releasing the final owner Arc can destroy old
controller/node metadata. Current nonempty prepared clients are controlled
cold fixtures; no live production tree retirement is enabled by W4A.

## Why live non-root routing remains disabled

A prepared binding is immutable metadata, not an acknowledged live membership
generation. Existing migration publishes a process binding and later updates
final-charge backups; it does not rekey queued tasks or rendezvous with remote
current tasks. Controller replacement and a running non-root RT/FAIR class
transition likewise need explicit admission/handoff. Prepared clients must not
perform those live transitions. The ordinary root class transition remains
supported and has a dedicated regression.

Before connecting ordinary memberships, add dynamic fallible slot admission,
a coherent admitted membership generation, and generation-aware
queued/current/throttled rebinding. The existing completed-switch protocol must
be extended to the non-root route; OSTD's `switched_to_cpu=false` cut still must
precede publishing a task remotely. W4A's prepared route lease is a lifecycle
pin, not this live transaction. Group-aware SMP load balancing and affinity
migration are also required. No descriptor
lookup, per-thread multiplier or token quota substitutes for that work.

A standalone atomic membership counter would not make separately read RCU
membership and generation coherent. The next live admission stage must publish
an immutable pinned generation with its node/incarnation and acknowledge every
affected Task before committing a process-wide move. Fork, class changes,
CPUmax throttling and node/controller retirement must participate in that
transaction. The W3 root-only migration guards remain unchanged and reject
prepared non-root layouts rather than silently routing them through root.

## Development and acceptance

Run the source-built OSDK with the existing fixed-lock native runner:

```sh
python3 -I -B support/build/ktest/run.py --crate aster-core \
  --skip-osdk-install --output /new/native-evidence
python3 -I -B tests/kernel/fair-runtime/run.py --smp 4 --output /new/cpu-evidence
```

The internal entity tests cover the original P(a,b)/Q hierarchy with one a
Task and eight b Tasks, original CPU-incarnation replacement, bad/stale/duplicate
admission, unknown Task retention, and CPUmax rejection before and after the
handoff cut followed by replenishment into the same leaf. They check fixed
container capacities and both ancestor and candidate debits. The root
RT-to-FAIR regression excludes the preceding RT execution from FAIR runtime.

Retain full core, ordinary CPUmax SMP 1/2/4, safety and stop/wakeup regressions.
Their default-root results do not qualify non-root routing. Final weight
acceptance still requires actual CPU-time ratios, unequal/nested weights,
thread-count invariance, sleep/wakeup, dynamic weight/membership/affinity
changes, clean retirement and SMP work conservation. See
[W1 and the remaining stages](FAIR_RUNTIME.md).

The W4A regressions retain actual original Task/Process objects and the same
`CpuRunQueueFixture::with_groups` production queue path. Before the lease fix,
the original 396 Core tests pass and all three new lifetime cases fail: active
CPU replacement, inactive raw-level activation and empty-node deletion. The
same cases must pass after the fix, and retiring the final prepared queue must
allow the operation again. Additional controls cover a deeper inactive raw
descendant, rejection before any partial subtree update, unrelated topology,
duplicate/failed admission, checked-counter prefix rollback and unavailable
Process capture. These are lifecycle/queue evidence; they are not actual
multi-CPU share measurements or public `cpu.weight` qualification.
