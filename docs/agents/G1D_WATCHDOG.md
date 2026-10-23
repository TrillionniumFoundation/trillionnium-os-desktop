# G1-d independent CPU recovery watchdog

This is a fixed single-CPU qualification policy. Ordinary builds do not acquire
this capability. It does not qualify a physical memory reserve, trusted user
pause intent, SMP, production devices or durable Hepta delivery.

## Ownership and authority

The sealed, stopped bootstrap registers one original OSTD hardware-timer
callback before any role's first instruction. Its captures retain the actual
manager binding and a read-only handle to the original Process status allocation.
They do not retain the workload Process, VMAR or TaskSet and do not delay
Process destruction or pidfile HUP. Registration allocates once; the tick
allocates nothing, does not block, does not print, and does no userspace copy.

The callback first checks the fixed deadline and terminal state under the
original bandwidth lock. A healthy, not-yet-due or terminal tick never takes
the runqueue lock or advances accounting. Only a possible restoration releases
that lock, settles the current local running interval under the existing
runqueue lock, then reacquires the original CPU owner's bandwidth lock and
revalidates the entire policy before applying. The
Process job-stop check reads the original atomic status while local interrupts
are disabled. No image, TaskSet or Process lock is nested under the runqueue.
The watchdog never calls resume or sends SIGCONT. The shared observer points at the original status, not a copied
job-control flag. Ordinary builds keep their embedded Process status; only the
G1-d/ktest configuration uses this shared original allocation.

The CPU owner already holds the two canonical grants, current quota, accounting,
resource identity and revision. The watchdog adds one registration flag, a bounded diagnostic tick counter,
a read-only original-status reference, and one immutable terminal result. It
uses `NativeResourceState::apply` under the same owner lock to restore the
immutable pre-delegation cap. The resulting receipt is copied from that original
apply; it does not mint a D request or claim a durable Hepta commit.

## Fixed finite policy

A healthy manager retains authority. The first reliable manager-image close,
or the original 300-second lease expiry, starts a five-second delay. Duplicate
close notifications cannot move it. The timer may act only before the existing
30-second recovery endpoint. All intervals are compile-time constants set
before first run, not caller-selected leases.

The only automatic effect restores a **positive** manager-originated reduction
to the original 50 ms per 100 ms cap. It preserves settled consumed CPU and
positive carry debt and consumes the **same one-effect recovery allowance**
as the existing recovery role. Later ticks return the saved terminal result
without another revision. A later recovery request cannot repeat this effect.

Zero quota, any other budget source, an already used recovery, a real job stop,
a dead workload or detached/fenced owner prevents restoration. A missing or
backward clock, unknown close cut, invalid accounting or tick arriving at/after
the recovery endpoint fails closed permanently for this watchdog. No future
clock sample or SIGCONT can renew its terminal decision. This is deliberately
conservative and may leave a workload throttled; it cannot claim availability
when the timer, clock, allocator or scheduler has failed.

## Read-only observations

The existing `cpu.stat` includes bounded `hepta_*` fields only on the admitted
owner. These are diagnostic observations, not authorization or an HOS2 ABI
extension. `hepta_job_stopped` reads the original Process status after the CPU
lock is released; its observation is not atomic with the saved historical
receipt. `hepta_job_stop_available=0` means no live original status is available
(the workload has become zombie or no observer was bound).
`hepta_user_pause_intent_available=0` explicitly records the absent trusted
user-intent ingress. `ReadUsage.user_paused` stays false and is not synthesized
from POSIX stop or a caller's label; the present wire response has no such bit.

`hepta_watchdog_status` is 0 pending, 1 restored, 2 ineligible, 3 job stopped,
4 late, 5 clock unavailable/rollback, 6 closed, or 7 accounting/admission fault.
`due_ns` and `expires_ns` describe the original finite window; zero means its
close cut is unavailable. `evaluated_ns` is the terminal observation time (zero
when unavailable). Only status 1 includes the original receipt's stable ID
(low/high 64 bits), previous/current revision, effective time and consumed CPU.
No error result fabricates success fields. The saturating `hepta_watchdog_ticks`
counts real callback entries under the original owner lock so the native probe
can distinguish a repeated callback from elapsed wall time alone. It is not a
resource revision or UsageSnapshot event sequence. Reads do not mutate any CPU budget.

## Validation

The new owner ktests use real cgroups, Process status, native resource metadata
and original D cores with explicit clock-cut fixtures. They cover healthy and
first-close boundaries, one-use receipt replay, consumption/debt preservation,
original-status observation without Process retention, no-settlement poll admission,
zero quota, real job stop, explicit resume, competing recovery, normal lease
expiry, unknown/backward clock and a late tick. These fault-cut fixtures are
not physical clock-failure evidence.

`tests/kernel/control/run_g1d_watchdog_guest.py` builds a frozen ordinary
`ActionChoice::Run` G1-d kernel with the exact `g1d_watchdog.c` snapshot. Five
separate boots exercise manager exec revocation and independent timer recovery,
healthy-manager refusal, zero-cap refusal, SIGSTOP preservation followed by an
explicit SIGCONT, and an earlier recovery-role effect. The probe reads the
original quota/usage, compares the original receipt's stable identity, waits
through the real five-second interval, proves repeated ticks do not change the
receipt/revision, and verifies a denied late D request replays identical bytes.
The recovery process issues no install in the automatic-restoration scenario
until after observing the timer receipt. The parser requires complete, exact
markers, original sealed-image evidence, clean QEMU exit and unchanged inputs.

At implementation time the C probe compiles with strict warnings; kernel
compilation, owner ktests and this new native gate are **pending**. Record exact
source/ELF identities and actual results before claiming closure. The gate
never claims physical clock-fault injection, full memory reserve, trusted pause
intent, hardware readiness or Hepta durability.

## Remaining F04 work

1. Add trusted user-action capability ingress, tied to its original image,
   principal and revocation lifecycle. Only then can an authorized pause intent
   and its epoch live beside the CPU policy. POSIX stop remains a separate
   observation. An arbitrary manager Boolean is insufficient authority.
2. Implement atomic physical reservation in the original global frame allocator,
   across per-CPU caches and all allocation paths. The current aggregate user
   data-page owner excludes page tables, slabs, sockets and device allocations;
   manager/recovery being outside that quota is not a reserve.
3. Bind reserved kernel work and management stacks to an explicit emergency
   allocation authority, bound/refund all consumers, and prove exhaustion,
   fragmentation, concurrent allocations and recovery. A free-memory check
   followed by an ordinary allocation has a race and is insufficient.
4. Qualify real timer/clock failure and SMP settlement separately. This slice's
   late/unknown cut tests establish fail-closed owner behavior only.
