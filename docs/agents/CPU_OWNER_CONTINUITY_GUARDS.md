# CPU owner identity across future delegation changes

These guards close two prerequisites for continuing the original CPU owner
across management generations. They do not implement a successor launcher,
renew a lease or complete persistent native G2. The current initial manager
and recovery still have their original 300-second lease, 30-second recovery
grace and independent 5-second watchdog. No HOS2 operation or capability
ceiling changes.

## Canonical delegation identity

`ManagementGrantState` owns the original private instance tag inside the CPU
owner's existing `CpuMax` lock. A `ManagementGrantSnapshot` only retains that
identity and immutable terms. The new `owns_snapshot` predicate remains usable
after revocation; it cannot authorize an effect. `revoke_for_snapshot` returns
the original idempotent receipt only for that same state instance.

`NativeCpuManager` retains its actual snapshot. Read and close paths check its
private origin against the current array entry under the original owner lock.
A delayed close from an old Process therefore cannot revoke a new delegation
merely because it occupies array position 0 or 1. Recreating identical public
IDs, lease terms and epoch does not pass this check. Effect admission continues
to use the existing full `ManagementGrantState::check` and original saved D.
Old terminal D results remain independently queryable.

## One watchdog callback for the CPU owner

The registration flag lives in `CpuBandwidthState`, outside its replaceable
management policy. The permanent callback captures the stable original
`NativeCpuObserver`; it does not retain a manager or a per-generation grant.
Each tick captures the armed policy's actual snapshot and original workload
status view. After entering the existing runqueue settlement path, it checks
the same private origin again under the CPU owner lock before changing any
budget or terminal watchdog receipt.

Replacing a policy between those lock cuts makes the old tick inert. A later
policy can reuse the one registered callback. Repeated arming of one policy
still fails. Clock failures, explicit job stop, zero or non-manager-owned
budgets, recovery consumption, finite deadlines, accounting and original
effect receipts retain their existing behavior. Ticks allocate no memory and
take no Process/TaskSet/image lock.

## Verification and remaining work

The additional os-control integration tests exercise original-instance
closure, identical-public-config replacement and 512 repeated replacements.
The additional original kernel tests use the real cgroup CPU owner and OSTD
delivery backend to check stale image close/read, a callback delayed between
its two owner-lock cuts, and 128 replacement policies requesting only one
registration. They preserve prior D history and verify a current matching
policy still restores its allowed cap. Their explicit clock cuts and internal
replacement fixture are fault injection, not a runtime activation API.

Run the existing complete os-control suite and the original complete kernel
suite, and retain the separate physical watchdog guest test. Compilation and
test sources alone are not execution receipts. New native successor and
multi-generation qualification must also exercise the actual original Root,
Supervisor, writer, FinalUse and durable retirement path.

The subsequent trusted successor transaction must still prepare a fresh real
Process from the original frozen image, fence the predecessor, preserve bounded
old history until the original writer confirms it, install fresh canonical
delegations and only then publish/resume. It must also bound pending processes,
retained namespaces and failure retries. Increasing a timeout, inheriting a
control FD through ordinary fork/exec or resetting a state array is not that
transaction.
