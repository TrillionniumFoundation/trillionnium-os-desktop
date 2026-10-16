# A03 host-model API contract

`os-control` is the Rust control state core for HOS2 0.3. It is a Linux host
model. It does not implement an ioctl, a kernel scheduler, credentials,
copyin/copyout, crash durability, or a second Hepta database. The existing
Hepta owner remains responsible for persistent logical operation identity `K`.
This crate only models the boot-local delivery identity `D`:

```text
D = (BootId, CapSpaceId, sequence)
```

The HOS2 wire layout remains owned by A02 and is not represented by a Rust
memory-layout cast here.

For A05 conversion, `DeliveryStatus::hos2_code` and
`DeliveryState::hos2_code` expose the fixed numeric HOS2 0.3 values without a
dependency on the wire crate. `ParentLimit` maps to wire `Conflict` because
HOS2 0.3 has no separate parent-constraint status. The fallible
`DeliveryObservation::hos2_saved_status_code` returns `Some(0)` only for a
consistent non-terminal observation without a stored terminal outcome, and
`Some(code)` for a terminal with a saved outcome. It returns `None` for
terminal-without-status or nonterminal-with-status rather than forging an
`Ok` result. A05 must not emit a response on `None`; A02 separately checks
the complete wire payload's metadata invariants.

## A05: kernel ioctl and CapSpace

1. Construct `ControlCore::new(boot_id, cap_space_id)` after trusted boot
   identity and CapSpace binding. `with_capacity` is the bounded host-model
   variant; the HOS2 default is 1024 non-retired writes.
2. Resolve a kernel ResourceDomain and a publisher-bound `Grant`. Build a
   `DeliveryRequest` with sequence, expected revision, fixed 100ms period,
   cap, stable target identity, grant epoch, and optional payload digest.
3. Call `reserve`. Sequence allocation is global across all targets. A second
   target, cap, expected revision, grant epoch, or payload digest for the same
   D is `Conflict`; a duplicate pending D is `Busy`; a duplicate terminal D
   cannot allocate a new effect. `reserve_or_get` is the copyout-retry helper.
4. After the resource mutation, call `publish(token, publisher, outcome)`.
   `commit(token, publisher, now_ns)` combines the ResourceDomain CAS mutation
   and terminal result publication. The token and namespace instance are
   checked, so a same-byte identity from another `ControlCore` cannot use it.
5. Create an exact `DeliveryView` for history observation. Query is read-only;
   it never grants execution. `DeliveryState::Reserved` is pending,
   `NotSeen` is unknown in a live namespace, and `HistoryLost` is an explicit
   loss of proof. `Retired` is a permanent no-replay tombstone.

The kernel must add real process-start/exec-epoch/session credentials around
this API. Possession of a host-model token is not a kernel credential.

## A06: CPU scheduler and ResourceDomain

`ResourceDomain` exposes stable `ResourceDomainId` and `StableObjectId`, a
revision-CAS budget update, `usage`, `revoke`, explicit `user_paused` state,
and the host-model `charge_cpu` primitive. `install_budget_for_host_model` is
the seam to replace with the scheduler's mutation path.

Invariants:

- period is exactly `CPU_PERIOD_NS` (100 ms); cap is within the period;
- expected revision must match and successful updates increment revision;
- cumulative and current-window CPU usage are retained across cap updates;
- a same-value update does not reset usage or create budget;
- child cap cannot exceed the parent cap, and parent cap cannot be lowered
  below any registered child cap;
- revoke and commit linearize on the same domain mutation gate; a revoke that
  wins first rejects the grant, while an already admitted commit remains
  terminally successful;
- cap zero is a budget value and never implies `user_paused`.

`charge_cpu` is still a host accounting model. Real tick accounting,
runqueue lock order, timer wakeup, and parent scheduling remain A06/kernel
work.

## A07: Hepta persistent confirmation and retirement

A07 records `K` and its association with this crate's D in the existing Hepta
owner ledger. A03 does not create, reconcile, or persist K. After the owner
has durably confirmed a contiguous terminal prefix, it creates an opaque
`OwnerReceipt`/`HistoryAck` and calls `retire_through`. A plain caller boolean
is not accepted. The namespace validates exact boot/space, optional owner
binding on `delivery_view_for`, contiguous terminal state, and monotonic
frontier. Retiring a prefix releases result slots but keeps the frontier so a
late sequence can only return `Retired`.

`LogicalOperationId` and `OperationBinding` are value-only handoff types for
the K↔D association. They do not create a K index, persistence record, or
execution authority; A07 remains the owner of the existing Hepta K ledger.

`lose_history` models a reboot or namespace-loss boundary. Old views observe
`HistoryLost`, old reserved tokens are fenced, and a new `ControlCore` must
use a new boot/CapSpace identity. This is not a persistence implementation.

## Lock and result invariants

The namespace mutex reserves a slot and its canonical request before any
resource mutation. Commit then holds only the result slot while entering the
resource mutation gate; it never acquires the namespace table lock in the
reverse direction. Query/retire never enter the resource gate. Result payload
is written under the slot mutex before its state becomes `Terminal`, so a
reader observes either a complete `Reserved` result or a complete terminal
result.

The Rust tests under `tests/control` are host-model evidence only. They do not
claim native kernel capability, real copyout fault handling, power-loss
durability, scheduler correctness, or A05/A06 integration.

## A03 hardening: namespace loss and view rights

The namespace owns the canonical request **including its publisher**. A
duplicate D from another authorized principal conflicts even when target,
period, revision, cap and digest happen to match.

An observation-only `delivery_view()` may query but cannot retire. The
`delivery_view_for(owner)` host-model view must be minted *only after* A05
verifies an actual history.ack capability, and A07 must validate that the
owner's receipt represents a durable contiguous confirmation. The
`OwnerReceipt` digest is opaque model evidence, **not a cryptographic
signature or a capability**, and a host-model caller can manufacture one.

`lose_history` fences reserved result slots under the same per-slot lock
that serializes `commit` and `publish`. An already linearized commit
completes before loss obtains that lock; a token not yet admitted returns
`HistoryLost` with no new mutation. Any effect handed off to an *external*
kernel executor before `publish` still requires A05's own fencing and
effect-journal discipline: the host model cannot cancel arbitrary external
effects or prove power-loss persistence.
