# FAIR execution intervals (W1 prerequisite)

## Status and scope

W1 closes a scheduler accounting prerequisite. It does **not** implement
hierarchical cgroup shares. `cpu.weight` still rejects every write; multiplying
thread nice weights, using bandwidth quotas or passing these tests must never
be reported as cgroup-weight scheduling.

Before W1, `try_pick_next_with_clock` advanced the outgoing class slice before
selection but never consumed that new delta in `FairAttr.vruntime`. Replacing
the runtime discarded direct-preemption and handoff tails. Wait/Exit also
retained their original bandwidth owner through dispatch retries while FAIR
accounting stopped at the earlier class event. A later group entity cannot
reliably charge aggregate execution on this foundation.

## Implementation and locking

`CurrentRuntime` now owns a separate `FairRuntime` cursor. Each checkpoint
charges only cycles above its previous high-water mark to the original task's
FAIR attribute using the class and nice weight retained at the previous cut.
It then snapshots the complete policy for the next interval. A concurrent
policy/nice update does not reprice already executed cycles. These are
checkpoint semantics, not a remote instantaneous scheduler rendezvous.

The common settlement runs at timer/yield/wait/exit events, direct selection,
each selection retry, dequeue, and the actual incoming runtime's start. It
also runs at the existing local CPU-configuration/membership checkpoints.
`FairClassRq::update_current` only evaluates preemption and reads the already
charged vruntime; it no longer charges the same interval again.

The class slice's `start`, `delta` and `period_delta` remain independent.
Configuration settlement does not reset them. A dequeued Wait/Exit slice stays
finished while its separate execution cursor retains the final dispatcher
tail. The existing BOOTTIME bandwidth owner and debit cursor remain separate
and keep their original charging/fault/overrun rules.

All production queue operations retain their IRQ-disabled local runqueue lock.
The new cursor allocates nothing, performs no I/O and acquires no cgroup lock.
Its next-policy snapshot uses the existing policy spinlock: local runqueue →
policy. Policy writers update their attributes without entering a runqueue.
No remote queue lock, new unsafe code or new user permission is introduced.

## Development and acceptance

Build the source-tree OSDK and use the existing fixed-lock native test runner:

```sh
python3 -I -B support/build/ktest/run.py --crate aster-core \
  --skip-osdk-install --output /new/core-evidence
python3 -I -B tests/kernel/fair-runtime/run.py --smp 1 --output /new/cpu-evidence
python3 -I -B tests/kernel/safety/run.py --smp 4 --output /new/safety-evidence
```

The seven new native tests use actual Task objects and the production class
queues with controlled cycle endpoints, without injecting them into OSTD's
running FIFO scheduler. They cover direct handoff, tick/yield deduplication,
Wait/Exit empty-selection retries, original nice/class attribution and cycle
high-water handling. The direct-handoff test fails on the original code:
outgoing vruntime is 0 instead of the executed 29 cycles. Preserve that raw
failure and the matching after-change evidence.

The ordinary guest additionally compares actual process CPU time under the
original CPUmax owner and verifies unsupported weight writes stay rejected.
Existing core bandwidth settlement/owner/carry-debt regressions and safety
tests remain required. Controlled queue transitions do not prove SMP context
switch races; CPUmax timing does not prove cgroup share ratios.

## Remaining hierarchy stages

W2 needs stable group entities with parent/child runnable queues, group
vruntime and active descendant counts, plus original group capture across
membership/controller-generation changes, sleep/wakeup and last-reference
retirement. Nice applies within a leaf; each runnable sibling group competes
once regardless of thread count. Group weight changes must preserve virtual
debt instead of recreating entities or granting fresh credit.

W3 needs a real SMP ownership/migration/load-balancing protocol. The current
scheduler reuses `last_cpu`, and `sched_setaffinity` explicitly does not migrate
already running/queued tasks. Independent per-CPU group heaps alone do not
establish global group shares. No old queue lock may be held while acquiring
another queue in the reverse order, and OSTD must never run one Task on two
CPUs. Original CPUmax settlement must retain its owner across those handoffs.

Before enabling weight writes, run actual CPU-time tests for equal groups with
1 versus 8 runnable threads, nested unequal sibling weights, nice changes
inside a leaf, sleep/wakeup, weight updates, membership changes, teardown,
affinity constraints and SMP 1/2/4. Work conservation and supported RT/idle
behavior must remain explicit. W1 is only the first prerequisite.
