# Interruptible waits during a process stop

## Defect and boundary

The native owner crash fixture requires every observed task of its own Agentd
process to be genuinely stopped before the host kills the isolated VM. The
ordinary `bd58bf26` kernel could report a successful process stop to its parent
while sleeping siblings remained `S`. `enqueue_signal` woke them before the stop
was published; after another thread consumed the pending signal, their wait
condition saw no signal and slept again. `Process::stop` did not wake them after
publishing its process-wide condition.

This change joins an **already published** group stop from signal-aware waits.
It does not make delivery of SIGSTOP, the process stop flag, or a parent wait
status an instantaneous quiescence barrier. A task can finish an operation before
joining the stop. The fixture must enumerate the same complete task set twice,
20 ms apart, with every task actually reporting `T`; it never substitutes the
leader's status for that observation. The fixture creates no new tasks during
this interval. This is an ordinary-kernel regression, not evidence of original
Agentd/SQLite/native HOS2 qualification or physical crash durability.

## Implementation

`Process::stop` publishes its original status, then wakes registered signal
waiters. Its task-set → signalled-waker lock order is the existing resume order.
No such lock is held when a task sleeps.

For ordinary `PauseReason::Sleep`, the waiter notices the group-stop condition
independently of the consumed signal. It retains the original waiter, event
registrations and timer, temporarily registers `StopBySignal`, and actually
waits until continuation or a signal requiring the existing signal-handler path.
The existing `/proc` code still requires the scheduler to report the task asleep;
changing the pause reason alone does not report `T`.

A scope guard restores the original pause reason before its registration is
cleared. The nested stop may consume an I/O or timer wake, so continuation forces
a recheck of the original condition and deadline. It does not replace a relative
timeout with a new one. Once a task is in this stop wait, ordinary I/O and timer
wakes cannot execute its original condition while it remains stopped. Condition
completion before the task joins the stop retains the previous behavior.

Futex waiting has an explicit completion condition shared with its queue item.
Only removal by a real futex wake publishes this condition; a signal, timer or
group-stop notification is not itself a successful futex wake. This matters
because the first group-stop implementation (`2dec1dda`) actually passed all-task
stop checks but returned an unintended EINTR from untargeted futex waits after
CONT (four of the 88 original assertions failed). The failed product and complete
serial output are retained. The follow-up keeps the same original deadline and
waits for completion rather than treating a raw notification as completion.

A queued futex also carries its current bucket index. Requeue updates the key and
index while both buckets are locked in their existing index order. Cancellation
locks only the indicated bucket and rechecks the index before removing the exact
waiter; if it moved, cancellation retries without holding either lock. A real
wake that wins this race returns success. Timeout or signal cancellation removes
the item from its current bucket, preventing a retained requeued waiter. Real
wakes publish completion before notifying and count the queue item even if an
unrelated notification has already set the waker bit. The REQUEUE syscall now
preserves a zero wake count and rejects negative wake/requeue counts, matching
[Linux v6.17](https://github.com/torvalds/linux/blob/v6.17/kernel/futex/requeue.c).
It no longer converts a migration-only request into an actual wake. This stage
does not claim a complete futex compatibility audit; the existing REQUEUE return
count, bitset migration, and same-bucket zero-requeue behavior remain separate
compatibility work.

System V semaphore waits likewise use their existing pending-operation status
as a completion condition. Stop/continue does not itself finish or cancel a
queued semop. Its existing signal/timeout cleanup and real status transitions
remain in place. Poller raw notifications retain their original caller-recheck
contract; generic raw notifications are not promoted into operation success.

SIGKILL leaves through the original signal handling and group-exit path. An
unmasked thread-directed SIGCONT may only be visible to this sibling, so it
returns through the original interruptible-syscall/signal-dequeue path. It does
not repeatedly call resume on the level of a pending CONT: an old signal cannot
be reused by this helper to cancel a later stop. The thread that originally
handles a process-directed stop remains in the existing user-return stop loop.

`replace_pause_reason` is only for the current owner of an already registered
wait; the helper restores it with RAII. Ptrace stops, uninterruptible waits,
credential checks, and scheduler accounting are unchanged.

## Explicit limits

This is not a complete Linux job-control implementation. In particular, the
pre-existing generation-time semantics of masked or ignored SIGCONT remain an
independent defect. This stage does not manufacture success for them. The
original syscall return/restart behavior for a thread that actually consumes a
signal also remains in force; a targeted CONT may interrupt that thread's
nanosleep with EINTR. Untargeted sleepers joining the group stop retain their
original waits. A parent wait status still does not acknowledge that all tasks
have joined a stop. Ptrace interactions beyond the existing regressions are not
newly qualified.

## Development and real guest tests

`tests/kernel/group-stop/run.py` reuses the exact-source ordinary product gate,
static probe build, bounded QEMU, source/artifact snapshots, and complete serial
records from the safety runner. The probe executes only in the guest. Run:

```sh
python3 -B tests/kernel/group-stop/run.py --smp 1 \
  --product-evidence /absolute/path/to/exact-product \
  --output /absolute/path/to/new-evidence-directory
```

Repeat with `--smp 4`. Each of twelve scenarios has a leader and five worker threads:
yielding, nanosleep, futex wait (or semaphore wait in its three scenarios), pipe
read, and poll. Readiness is published only
after the startup barrier and immediately before each blocking primitive; the
parent also observes their actual sleeping state and checks that the calls have
not returned. The 200 assertions cover external/self SIGSTOP, stable six-task T
sets, SIGCONT, SIGKILL while stopped, preserving blocked calls, deadline expiry
while stopped, retaining I/O events without consuming them in T, and targeted
CONT followed by a new stop. Three additional scenarios cover actual futex wake
while stopped, requeue while stopped followed by continuation and a wake on the
new address, and requeued timeout expiry with no remaining queued item. Three semaphore
scenarios cover continuation without completion, completion while stopped, and
original-deadline expiry with cancellation cleanup. Children
are reaped, and a child already reaped by
a failed assertion is never signalled again.

Tests report the complete observed task sets. Both positive and failed results
must retain probe source/binary hashes and full raw serial output. Do not reduce
the all-task check to a process flag, loosen the fixture's boundary, or count
this probe as the original native owner chain.
