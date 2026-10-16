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
`DeliveryObservation::hos2_saved_status_code()` returns `Some(0)` only
for a consistent nonterminal observation with no saved outcome or resource
metadata, `Some(status)` for a terminal whose status and CAS metadata agree,
and `None` for any malformed pair, missing/forged success receipt,
erroneous metadata, or invalid D sequence. A05 must refuse to serialize
`None` rather than default it to Ok. A02 independently validates the
actual HOS2 byte layout and payload.

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

## A06 time and parent hierarchy hardening (host model)

Child registration now takes the same shared resource mutation gate as a
concurrent parent cap reduction. Direct sibling and ancestor ID collisions
are rejected; the kernel integration must guarantee unique IDs across roots
and unrelated branches.

`try_usage(boottime_ns)`, `charge_cpu(delta, now)` and budget CAS reject
BOOTTIME rollback. Compatibility `usage` clamps old timestamps to the last
observed time and returns the effective sample, never a newly credited
earlier window. The budget CAS advances a 100ms window only after a real
period boundary. Reactivation fails closed on epoch overflow.

A06 remains responsible for runtime settlement, exact boundary-crossing
CPU slicing, all scheduler classes, parent gate integration, IRQ lock order
and timer wakeups. `charge_cpu` is **host-only** single-window accounting,
not native scheduler enforcement.

## Hierarchy linearization and identity collisions

Child creation shares the root family's mutation gate with parent cap changes.
Duplicate sibling ResourceDomain IDs or an ID equal to an ancestor are rejected
rather than overwriting the parent's child-cap registry. Installing a budget
in a later 100ms period advances window accounting at apply time; same-window
updates retain already consumed runtime even when the cap value is unchanged.

## Original-owner history retirement authority

For namespaces with retirement, A05 trusted bootstrap creates the pair from
`ControlCore::with_original_owner` or `with_capacity_for_owner`.
The non-Clone `OriginalOwnerAuthority` binds the original owner to the
specific in-memory namespace instance and its generation. The
`retire_through(&view, ack, &authority)` API rejects arbitrary observer
views, invented owner receipts, foreign same-byte namespaces and stale
generations. A07 must *separately* validate its existing durable K ledger
and fsync before invoking retirement; no new persistent database is created.

## Ancestor revocation

Child grant issuance and child budget CAS both check the liveness of every
ResourceDomain ancestor under the shared family mutation gate. If any
ancestor revoke precedes admission, child mutation publishes terminal
`Revoked`; if the child mutation wins, its already published result remains
immutable after ancestor revoke. The real A05/A06 kernel must bind this to
its actual grant epoch, capability lifetime and scheduler domain lock order.

## Family-wide resource identity retention

ResourceDomain family members now share a mutation-gate-protected set of
stable domain IDs and stable object IDs. A child cannot register a duplicate
ID **anywhere in its root family**, including a cousin in another subtree.
IDs are retained for the life of the family instead of being reused after a
handle drops. This is a bounded-by-object-creation **host-model** registry,
not a duplicate Hepta ledger or a new global kernel object database. The
actual kernel must use its preexisting stable object owner/registry to enforce
uniqueness **across distinct root families** and to bound/retire the registry
safely during namespace destruction. The family gate serializes simultaneous
cousin registration and parent budget changes.

## Atomic host ancestry charging

`charge_cpu(delta_ns, now_ns)` now uses a two-phase, family-gate-serialized
transaction: stage current-window, cumulative and event-sequence changes
against **every ancestor**, rejecting overflow, revoked/exhausted ancestor or
clock rollback before touching any node; then publish the validated updates.
This closes an observable failure mode where a rejected parent's quota left a
child window/time advanced, blocking a legitimate earlier later retry and
claiming false progress. The 3-level rejection and 64-thread sibling quota
races are in Rust tests. Unlike a real scheduler, this compatibility host
method places the entire delta in the window of `now_ns`, so A06 still needs
exact CPU interval slicing at true boundary-crossing runtime settlement.

## Instance-bound D target and ancestor creation fence

Global D replay compares both canonical resource identity fields and the
original in-memory ResourceDomain instance. An independently created root
with colliding public identity bytes conflicts rather than retrieving the
other object's terminal result. The bounded slot holds the instance until
retirement. Descendant creation checks every ancestor's liveness; a revoked
grandparent cannot be bypassed through a still-live parent. A05 must still
guarantee global stable IDs for real kernel resources across distinct roots.

## Exact cross-period host model seam for A06

`ResourceDomain::charge_interval_for_host_model(start_ns, end_ns)` accepts a
strict non-empty monotonic CPU execution span `[start, end)`, correctly
splits it at fixed 100ms boundaries, checks the consumed first window, any
complete intermediate windows, and the final partial window against the
resource and every ancestor. The entire interval is atomic: invalid,
clock-reversed, over-limit or overflowing intervals change no resource,
cumulative accounting, event counter or BOOTTIME floor. A full intermediate
window can only be consumed at a full-period cap, so no unused quota credit
is carried into the next window. Exact endpoint boundaries and near-u64-max
arithmetic are tested. The older `charge_cpu(delta, now)` method remains for
legacy caller compatibility but **does not slice intervals**. Neither one is
actual scheduler enforcement; A06 must settle real per-CPU runtime before
calling into a shared resource gate and implement timer preemption/recovery.

## Pre-reservation validation

A05 must parse/check the HOS2 transport and static InstallBudget payload
before reserving D. The host core also rejects invalid expected revision
(0 or u64::MAX), non-100ms period, or out-of-range cap via
`DeliveryError::InvalidRequest`, without consuming the next sequence or
allocating a result slot. Post-reservation grant/CAS/parent/clock denials
are stored as immutable terminal outcomes. A05 maps structural validation
to its protocol error path, not to an invented terminal effect.

## Bounded resource-family identity namespace

The host-model family ID and stable-object-ID tombstone registry now has an
explicit default limit of `DEFAULT_FAMILY_ID_CAPACITY = 65_536` including
the root. Attempts to create another domain fail with `ResourceError::Exhausted`
without overwriting an existing child or consuming an identity. For adversarial
tests, `ResourceDomain::root_with_capacity_for_host_model(..., family_capacity)`
can use a tiny limit. Dropped resource handles do not revive a previously
used stable ID: unlike transient slot numbers, a stable identity is never
silently reassigned. **This is only a host-model lifetime bound**; an actual
kernel requires bounded residual-domain reclamation and a globally scoped
object-ID registry across roots. A03 does not implement a new persistent
ledger or substitute its in-memory registry for A05/A06's lifecycle owner.

## Ancestor authorization epoch / reactivation ABA fencing

A grant captures the immutable epoch chain from its ResourceDomain through
its ancestors at issuance. A revoke followed by trusted reactivation of any
ancestor changes that chain, so an *old child grant remains invalid* even if
the ancestor is now alive again and its numeric CPU cap is unchanged.
`install_budget_for_host_model` compares each saved ancestor epoch under
the shared mutation gate and publishes a terminal `Revoked` result on stale
D submission. The reservation slot additionally binds the saved epoch chain:
a fresh grant cannot claim the *same* previously reserved D even when all
public HOS2 request bytes are equal; it returns `Conflict`. A genuinely new
post-recovery action must use a new D and fresh Hepta K authorization as
appropriate. No new wire field or independent K ledger is introduced.

## A02 wire-success equivalence (cross-crate hardening)

The independent A02 HOS2 decoder rejects an allegedly successful
`QueryDelivery` result when `consumed_ns > effective_ns % CPU_PERIOD_NS`,
even when object identity and revision CAS metadata match. A03 now applies
the same fail-closed predicate in both
`DeliveryObservation::hos2_saved_status_code() -> Option<u16>` and external
`publish(..., PublishOutcome::Success)`. A05 must reject `None`, never
substitute a success code.

`ResourceDomain::apply_budget` also preflights the current period elapsed
time before any revision/window mutation. If the simplified legacy host
`charge_cpu` has produced impossible running-time accounting, the reserved
D publishes an immutable `Indeterminate` refusal rather than a wire-invalid
success. It does not refund prior consumption, advance CAS or turn the
original D into a later success. A subsequent **new** D may be evaluated at
a later consistent sample. A06 must supply settled real runtime in the
actual kernel and A07 must preserve original K history.

## Pinned durable Hepta K identity (A07 handoff)

The pinned real `hepta-private-ci@f8c9419df6ddeb36ff8b522a50219981fb8d9345`
`codex-rs/hepta-operations/src/durable_model.rs::OperationIntentV1`
has `scope_id: StableId` and `operation_id: StableId` as the persistent
operation identity. The production `durable_store.rs` loads and tombstones
rows with `WHERE scope_id = ? AND operation_id = ?`; `payload_digest`,
`expected_predecessor`, and `owner_generation` are **not part of K's
lookup key** (the owner still checks semantic digests and fences generations).
This is distinct from the non-durable *reference* `OperationKey` type.

A03 `LogicalOperationId::new(scope_id, operation_id)` therefore stores the
entire independent StableId strings losslessly (each 1..=128 ASCII bytes,
letters/digits/`.`/`_`/`-`/`:`) rather than truncating them into two
16-byte integers or hashing away collisions. It is a value-only carrier,
not an owner ledger and not authority to dispatch. `OperationBinding(K,D)`
continues to tie it to one boot-local kernel delivery without ever
replacing the original owner. Public namespace and D fields are
constructor-validated and accessed read-only; neither value proves
kernel boot entropy, credentials, or the rights of its caller.

## Publisher immutability and revoked-vs-exhausted status

The host `Grant.principal` value is no longer externally mutable; callers
can only inspect `Grant::principal()`. A05 must still authenticate the
publisher and authorize the grant against the actual kernel session.
Host `charge_cpu` and `charge_interval_for_host_model` now return
`ResourceError::Revoked` for a revoked leaf or ancestor, reserving
`Exhausted` for genuine CPU cap exhaustion. Both failures are atomic and
leave all cumulative usage/event counters unchanged.

## Fail-closed namespace window bootstrap

For HOS2 0.3 the maximum in-memory unretired delivery window is 1024.
`ControlCore::try_with_capacity(boot, space, capacity)` rejects zero
identities and capacities outside `1..=DEFAULT_WINDOW_CAPACITY` before
creating a namespace, returning `InvalidIdentity` or `InvalidCapacity`.
The owner-bearing `with_capacity_for_owner` now propagates the same
validation instead of panicking. Legacy `with_capacity` remains a trusted
compatibility constructor; configurable A05 callers must use the fallible
entry point. The reservation path still returns `ResourceExhausted`
without consuming the next D when the valid bounded window fills.

## End-of-range rollover (host model)

The final allowed write D is `sequence=u64::MAX-1`, after which
`next_sequence=u64::MAX` is a non-writeable exhausted sentinel and must
never wrap to 1. Retiring the last terminal result preserves that frontier.
The last legal revision CAS is `previous=u64::MAX-1` to
`saved_revision=u64::MAX`, whose terminal outcome remains immutable on
retry; attempts to propose `expected_revision=u64::MAX` are structurally
invalid and do not consume another D. Unit tests construct synthetic
late-life private frontiers to verify the arithmetic without simulating
2^64 operations or pretending to prove real kernel persistence.

## A02 independent codec compatibility tests (A03 dev-only dependency)

The A03 Cargo crate has a **dev-only path dependency** on A02's separately
owned `hos2-os-abi` no_std codec. New Rust integration tests in
`tests/control/control_conformance.rs` convert actual A03 Reserved,
Terminal/Ok, Terminal/Revoked, NotSeen, Retired and HistoryLost observations
to A02's typed `QueryDeliveryResponse` and require successful
`encode_response` + `decode_response`. The negative test demonstrates
that both A03's fallible status conversion and A02's *independent* encoder
reject an impossible elapsed-CPU success; zero previous revision is also
rejected. This adds no wire layout of A03's own, no generated golden edits,
and no production dependency on the wire crate. Lockfile pins the path-only
dev dependency. Exact-head Cargo execution is still required; test source
presence is not a passed result.

## A02 history-sequence MAX compatibility

HOS2 InstallBudget uses strictly executable D sequences
`1..=u64::MAX-1`; write `u64::MAX` is permanently reserved as the
non-executable next-sequence sentinel and never allocates a slot. The
**separate history QueryDelivery/RetireThrough wire payload** permits any
nonzero sequence, including `u64::MAX`. A read-only QueryDelivery for
this sentinel returns `NotSeen` in a live namespace or `HistoryLost`
after namespace loss, *not* a terminal/retired result. A03's fallible
wire observation converter permits these two states at MAX but refuses
to serialize forged Reserved/Terminal/Retired MAX observations. A02's
independent no_std codec is the test oracle for the MAX history response.

## Executable bounded-window invariant audit (host only)

`ControlCore::validate_invariants_for_host_model()` inspects the live
namespace and each result slot with the same namespace->slot lock order as
query/retire. It checks monotonic `next_sequence` and `retired_through`,
the **complete contiguous** unretired window (no missing sequence hidden by
result reclamation), bounded slot count, publisher/request binding, terminal
HOS2 result metadata shape, and absence of fenced slots in a still-live
namespace. After explicit history loss, no slots may remain. Errors use
`DeliveryInvariantError`; the check never creates new authority, touches a
Hepta K ledger, or performs a resource effect.

New Rust tests exercise the diagnostic across a permanently pending first
sequence + exhausted eight-slot window, its eventual contiguous retirement,
a 10,000-delivery bounded sequence, and an observer concurrently auditing
512 producer CAS commits/retirements. This is **O(window)** host diagnostic
work, not an IRQ-safe or production scheduler operation and not loom proof.
