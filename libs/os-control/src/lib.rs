//! A03 HOS2 control state core.
//!
//! This crate is a Linux host model for the control state machine.  It is
//! intentionally independent of the HOS2 wire codec and of the kernel.  In
//! particular, a passing test here proves only the model's state invariants;
//! it does not prove ioctl, credentials, scheduler, copyout, or persistence
//! behaviour in a real kernel.

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::sync::{Arc, Mutex, MutexGuard};

pub const CPU_PERIOD_NS: u64 = 100_000_000;
pub const DEFAULT_WINDOW_CAPACITY: usize = 1024;
/// Host-model resource family identity tombstones. Kernel integration must
/// use its real bounded stable-object registry and lifecycle policy.
pub const DEFAULT_FAMILY_ID_CAPACITY: usize = 65_536;

#[derive(Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Id16([u8; 16]);

impl Id16 {
    pub const fn new(bytes: [u8; 16]) -> Self {
        Self(bytes)
    }

    pub const fn from_u128(value: u128) -> Self {
        Self(value.to_be_bytes())
    }

    pub const fn bytes(self) -> [u8; 16] {
        self.0
    }

    pub const fn is_nonzero(self) -> bool {
        let mut i = 0;
        while i < self.0.len() {
            if self.0[i] != 0 {
                return true;
            }
            i += 1;
        }
        false
    }
}

impl fmt::Debug for Id16 {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "Id16({})",
            self.0
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect::<String>()
        )
    }
}

macro_rules! id_type {
    ($name:ident) => {
        #[derive(Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
        pub struct $name(Id16);

        impl $name {
            pub const fn new(bytes: [u8; 16]) -> Self {
                Self(Id16::new(bytes))
            }

            pub const fn from_u128(value: u128) -> Self {
                Self(Id16::from_u128(value))
            }

            pub const fn bytes(self) -> [u8; 16] {
                self.0.bytes()
            }

            pub const fn is_nonzero(self) -> bool {
                self.0.is_nonzero()
            }
        }

        impl fmt::Debug for $name {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.debug_tuple(stringify!($name)).field(&self.0).finish()
            }
        }
    };
}

id_type!(BootId);
id_type!(CapSpaceId);
id_type!(ResourceDomainId);
id_type!(StableObjectId);
id_type!(PublisherId);
id_type!(OwnerId);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct NamespaceIdentity {
    boot_id: BootId,
    cap_space_id: CapSpaceId,
}

impl NamespaceIdentity {
    pub fn new(boot_id: BootId, cap_space_id: CapSpaceId) -> Result<Self, IdentityError> {
        if !boot_id.is_nonzero() || !cap_space_id.is_nonzero() {
            return Err(IdentityError::ZeroIdentity);
        }
        Ok(Self {
            boot_id,
            cap_space_id,
        })
    }

    pub const fn boot_id(self) -> BootId {
        self.boot_id
    }

    pub const fn cap_space_id(self) -> CapSpaceId {
        self.cap_space_id
    }
}

/// Hepta's *durable* logical operation identity K, not its reference
/// OperationKey. The pinned DurableOperationStore indexes operation rows
/// by (scope_id, operation_id), each a StableId of at most 128 ASCII bytes.
///
/// The semantic/payload digest belongs to the existing owner ledger and is
/// compared on replay. It is not part of K's lookup key. This type stores
/// only a checked value: A03 never indexes, authorizes or persists K.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct LogicalOperationId {
    scope_id: String,
    operation_id: String,
}

pub const MAX_HEPTA_STABLE_ID_BYTES: usize = 128;

fn valid_hepta_stable_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= MAX_HEPTA_STABLE_ID_BYTES
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-' | b':'))
}

impl LogicalOperationId {
    pub fn new(
        scope_id: impl AsRef<str>,
        operation_id: impl AsRef<str>,
    ) -> Result<Self, IdentityError> {
        let scope_id = scope_id.as_ref();
        let operation_id = operation_id.as_ref();
        if !valid_hepta_stable_id(scope_id) || !valid_hepta_stable_id(operation_id) {
            return Err(IdentityError::InvalidOperationKey);
        }
        Ok(Self {
            scope_id: scope_id.to_owned(),
            operation_id: operation_id.to_owned(),
        })
    }

    pub fn scope_id(&self) -> &str {
        &self.scope_id
    }

    pub fn operation_id(&self) -> &str {
        &self.operation_id
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct DeliveryId {
    namespace: NamespaceIdentity,
    sequence: u64,
}

impl DeliveryId {
    pub fn new(namespace: NamespaceIdentity, sequence: u64) -> Result<Self, DeliveryError> {
        if sequence == 0 || sequence == u64::MAX {
            return Err(DeliveryError::InvalidSequence);
        }
        Ok(Self {
            namespace,
            sequence,
        })
    }

    pub const fn namespace(self) -> NamespaceIdentity {
        self.namespace
    }

    pub const fn sequence(self) -> u64 {
        self.sequence
    }
}

/// A value-only association for A07. It is not a persistence record and does
/// not make K a lookup key for a D result.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct OperationBinding {
    pub logical: LogicalOperationId,
    pub delivery: DeliveryId,
}

impl OperationBinding {
    pub fn new(logical: LogicalOperationId, delivery: DeliveryId) -> Self {
        Self { logical, delivery }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum IdentityError {
    ZeroIdentity,
    InvalidOperationKey,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Budget {
    pub period_ns: u64,
    pub cap_ns: u64,
}

impl Budget {
    pub fn new(cap_ns: u64) -> Result<Self, ResourceError> {
        if cap_ns > CPU_PERIOD_NS {
            return Err(ResourceError::InvalidBudget);
        }
        Ok(Self {
            period_ns: CPU_PERIOD_NS,
            cap_ns,
        })
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct UsageSnapshot {
    pub stable_object_id: StableObjectId,
    pub revision: u64,
    pub sample_boottime_ns: u64,
    pub cumulative_cpu_ns: u64,
    pub window_start_ns: u64,
    pub window_consumed_ns: u64,
    pub active_cap_ns: u64,
    pub active_period_ns: u64,
    pub event_sequence: u64,
    pub dropped_events: u64,
    pub user_paused: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BudgetReceipt {
    pub previous_revision: u64,
    pub revision: u64,
    pub effective_boottime_ns: u64,
    pub consumed_at_apply_ns: u64,
}

#[derive(Clone)]
pub struct ResourceDomain {
    inner: Arc<ResourceDomainInner>,
}

struct ResourceDomainInner {
    gate: Arc<Mutex<()>>,
    // Lifetime identity registry is shared by the whole resource family.
    // Entries are deliberately not freed on handle drop: old stable IDs
    // cannot become new children after a resource object is destroyed.
    family: Arc<Mutex<FamilyIdentityRegistry>>,
    state: Mutex<DomainState>,
    parent: Option<ResourceDomain>,
    children: Mutex<BTreeMap<ResourceDomainId, u64>>,
}

struct FamilyIdentityRegistry {
    domain_ids: BTreeSet<ResourceDomainId>,
    object_ids: BTreeSet<StableObjectId>,
    capacity: usize,
}

#[derive(Clone, Copy)]
struct DomainState {
    id: ResourceDomainId,
    stable_object_id: StableObjectId,
    parent: Option<ResourceDomainId>,
    revision: u64,
    budget: Budget,
    consumed_ns: u64,
    window_consumed_ns: u64,
    window_start_ns: u64,
    last_boottime_ns: u64, // monotonic gate timestamp; no clock-rewind refresh
    event_sequence: u64,
    dropped_events: u64,
    alive: bool,
    grant_epoch: u64,
    user_paused: bool,
}

#[derive(Clone)]
pub struct Grant {
    domain: ResourceDomain,
    principal: PublisherId,
    epoch: u64,
    // Parent-first ancestry is not necessary: this captures the immutable
    // immediate-parent -> root epoch chain at grant issuance. Every ancestor
    // revoke/reactivation permanently invalidates the old authorization.
    ancestor_epochs: Vec<u64>,
}

impl Grant {
    /// Stable publisher value captured at grant issuance. Real authority
    /// still comes from an A05 authenticated session, never a host model.
    pub const fn principal(&self) -> PublisherId {
        self.principal
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RevokeReceipt {
    pub domain: ResourceDomainId,
    pub epoch: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ResourceError {
    InvalidIdentity,
    DuplicateDomainId,
    DuplicateObjectId,
    InvalidBudget,
    InvalidCapacity,
    InvalidInterval,
    InvalidRevision,
    RevisionConflict { expected: u64, actual: u64 },
    ParentConstraint,
    Revoked,
    GrantEpochMismatch,
    Exhausted,
    Overflow,
    MissingParent,
    ClockRollback,
    /// Host-only time/accounting inconsistency: never publish a wire-invalid
    /// successful CAS after already accounted CPU exceeds elapsed BOOTTIME.
    InconsistentAccounting,
}

impl ResourceDomain {
    pub fn new(
        id: ResourceDomainId,
        stable_object_id: StableObjectId,
        parent: Option<&ResourceDomain>,
        initial_cap_ns: u64,
    ) -> Result<Self, ResourceError> {
        if !id.is_nonzero() || !stable_object_id.is_nonzero() {
            return Err(ResourceError::InvalidIdentity);
        }
        let budget = Budget::new(initial_cap_ns)?;
        if let Some(parent) = parent {
            // Parent cap reduction and child creation share one mutation gate.
            let _gate = lock_unpoisoned(&parent.inner.gate);
            let parent_state = parent.snapshot_state();
            if !parent_state.alive {
                return Err(ResourceError::Revoked);
            }
            if initial_cap_ns > parent_state.budget.cap_ns {
                return Err(ResourceError::ParentConstraint);
            }
            // A revoked ancestor closes descendant creation even when the
            // immediate parent's alive bit remains true.
            let mut ancestor = Some(parent);
            while let Some(node) = ancestor {
                let ancestor_state = node.snapshot_state();
                if !ancestor_state.alive {
                    return Err(ResourceError::Revoked);
                }
                if ancestor_state.id == id {
                    return Err(ResourceError::DuplicateDomainId);
                }
                ancestor = node.inner.parent.as_ref();
            }
            let mut registry = lock_unpoisoned(&parent.inner.family);
            if registry.domain_ids.contains(&id) {
                return Err(ResourceError::DuplicateDomainId);
            }
            if registry.object_ids.contains(&stable_object_id) {
                return Err(ResourceError::DuplicateObjectId);
            }
            if registry.domain_ids.len() >= registry.capacity {
                return Err(ResourceError::Exhausted);
            }
            let mut children = lock_unpoisoned(&parent.inner.children);
            if children.contains_key(&id) {
                return Err(ResourceError::DuplicateDomainId);
            }
            let inner = Arc::new(ResourceDomainInner {
                gate: Arc::clone(&parent.inner.gate),
                family: Arc::clone(&parent.inner.family),
                state: Mutex::new(DomainState {
                    id,
                    stable_object_id,
                    parent: Some(parent_state.id),
                    revision: 1,
                    budget,
                    consumed_ns: 0,
                    window_consumed_ns: 0,
                    window_start_ns: 0,
                    last_boottime_ns: 0,
                    event_sequence: 0,
                    dropped_events: 0,
                    alive: true,
                    grant_epoch: 1,
                    user_paused: false,
                }),
                parent: Some(parent.clone()),
                children: Mutex::new(BTreeMap::new()),
            });
            children.insert(id, initial_cap_ns);
            registry.domain_ids.insert(id);
            registry.object_ids.insert(stable_object_id);
            return Ok(Self { inner });
        }
        Ok(Self {
            inner: Arc::new(ResourceDomainInner {
                gate: Arc::new(Mutex::new(())),
                family: Arc::new(Mutex::new(FamilyIdentityRegistry {
                    domain_ids: BTreeSet::from([id]),
                    object_ids: BTreeSet::from([stable_object_id]),
                    capacity: DEFAULT_FAMILY_ID_CAPACITY,
                })),
                state: Mutex::new(DomainState {
                    id,
                    stable_object_id,
                    parent: None,
                    revision: 1,
                    budget,
                    consumed_ns: 0,
                    window_consumed_ns: 0,
                    window_start_ns: 0,
                    last_boottime_ns: 0,
                    event_sequence: 0,
                    dropped_events: 0,
                    alive: true,
                    grant_epoch: 1,
                    user_paused: false,
                }),
                parent: None,
                children: Mutex::new(BTreeMap::new()),
            }),
        })
    }

    /// Construct an independent root with a small capacity for negative
    /// host tests. Includes the root itself and never reuses expired IDs.
    pub fn root_with_capacity_for_host_model(
        id: ResourceDomainId,
        stable_object_id: StableObjectId,
        cap_ns: u64,
        family_capacity: usize,
    ) -> Result<Self, ResourceError> {
        if family_capacity == 0 {
            return Err(ResourceError::InvalidCapacity);
        }
        let root = Self::new(id, stable_object_id, None, cap_ns)?;
        lock_unpoisoned(&root.inner.family).capacity = family_capacity;
        Ok(root)
    }

    pub fn id(&self) -> ResourceDomainId {
        self.snapshot_state().id
    }

    pub fn stable_object_id(&self) -> StableObjectId {
        self.snapshot_state().stable_object_id
    }

    pub fn parent_id(&self) -> Option<ResourceDomainId> {
        self.snapshot_state().parent
    }

    pub fn revision(&self) -> u64 {
        self.snapshot_state().revision
    }

    pub fn budget(&self) -> Budget {
        self.snapshot_state().budget
    }

    pub fn grant(&self, principal: PublisherId) -> Result<Grant, ResourceError> {
        // The family mutation gate prevents a parent revoke from racing
        // issuance of a descendant grant. Possession still does not
        // guarantee admission: commit rechecks the same ancestor chain.
        let _gate = lock_unpoisoned(&self.inner.gate);
        let state = self.snapshot_state();
        if !state.alive {
            return Err(ResourceError::Revoked);
        }
        let mut ancestor = self.inner.parent.as_ref();
        let mut ancestor_epochs = Vec::new();
        while let Some(parent) = ancestor {
            let ancestor_state = parent.snapshot_state();
            if !ancestor_state.alive {
                return Err(ResourceError::Revoked);
            }
            ancestor_epochs.push(ancestor_state.grant_epoch);
            ancestor = parent.inner.parent.as_ref();
        }
        if !principal.is_nonzero() {
            return Err(ResourceError::InvalidIdentity);
        }
        Ok(Grant {
            domain: self.clone(),
            principal,
            epoch: state.grant_epoch,
            ancestor_epochs,
        })
    }

    pub fn revoke(&self) -> RevokeReceipt {
        let _gate = lock_unpoisoned(&self.inner.gate);
        let mut state = lock_unpoisoned(&self.inner.state);
        state.alive = false;
        state.grant_epoch = state.grant_epoch.saturating_add(1);
        RevokeReceipt {
            domain: state.id,
            epoch: state.grant_epoch,
        }
    }

    pub fn reactivate_for_host_model(&self) -> Result<(), ResourceError> {
        let _gate = lock_unpoisoned(&self.inner.gate);
        let mut state = lock_unpoisoned(&self.inner.state);
        // Failure to advance epoch must not re-enable authorization.
        let next_epoch = state.grant_epoch.checked_add(1).ok_or(ResourceError::Overflow)?;
        state.grant_epoch = next_epoch;
        state.alive = true;
        Ok(())
    }

    pub fn set_user_paused(&self, paused: bool) {
        let _gate = lock_unpoisoned(&self.inner.gate);
        lock_unpoisoned(&self.inner.state).user_paused = paused;
    }

    pub fn user_paused(&self) -> bool {
        self.snapshot_state().user_paused
    }

    /// Legacy host sampler: never backdate or refresh the quota window.
    /// The returned sample time reflects any monotonic clamp.
    pub fn usage(&self, sample_boottime_ns: u64) -> UsageSnapshot {
        let _gate = lock_unpoisoned(&self.inner.gate);
        let mut state = lock_unpoisoned(&self.inner.state);
        let effective_ns = sample_boottime_ns.max(state.last_boottime_ns);
        Self::snapshot_usage_at(&mut state, effective_ns)
    }

    /// A06 integration should reject stale BOOTTIME samples explicitly.
    pub fn try_usage(&self, sample_boottime_ns: u64) -> Result<UsageSnapshot, ResourceError> {
        let _gate = lock_unpoisoned(&self.inner.gate);
        let mut state = lock_unpoisoned(&self.inner.state);
        if sample_boottime_ns < state.last_boottime_ns {
            return Err(ResourceError::ClockRollback);
        }
        Ok(Self::snapshot_usage_at(&mut state, sample_boottime_ns))
    }

    fn snapshot_usage_at(state: &mut DomainState, now_ns: u64) -> UsageSnapshot {
        let window_start = (now_ns / state.budget.period_ns) * state.budget.period_ns;
        if window_start > state.window_start_ns {
            state.window_start_ns = window_start;
            state.window_consumed_ns = 0;
        }
        state.last_boottime_ns = now_ns;
        UsageSnapshot {
            stable_object_id: state.stable_object_id,
            revision: state.revision,
            sample_boottime_ns: now_ns,
            cumulative_cpu_ns: state.consumed_ns,
            window_start_ns: state.window_start_ns,
            window_consumed_ns: state.window_consumed_ns,
            active_cap_ns: state.budget.cap_ns,
            active_period_ns: state.budget.period_ns,
            event_sequence: state.event_sequence,
            dropped_events: state.dropped_events,
            user_paused: state.user_paused,
        }
    }

    /// Charge each domain of the ancestry atomically under the family gate.
    /// A rejection at an ancestor must not move the child clock, reset its
    /// quota window, or increment a partial event sequence. This simplified
    /// host primitive attributes delta_ns to the single window containing
    /// now_ns; it does not replace A06 scheduler interval slicing.
    pub fn charge_cpu(&self, delta_ns: u64, now_ns: u64) -> Result<(), ResourceError> {
        let _gate = lock_unpoisoned(&self.inner.gate);
        let mut updates = Vec::new();
        let mut cursor = Some(self.clone());

        // Phase 1: read, validate and stage every ancestor without modifying
        // any state. Every node is protected against concurrent mutation by
        // the same family gate, including parent revoke and quota changes.
        while let Some(domain) = cursor {
            let old = domain.snapshot_state();
            if now_ns < old.last_boottime_ns {
                return Err(ResourceError::ClockRollback);
            }
            let window_start =
                (now_ns / old.budget.period_ns) * old.budget.period_ns;
            let previous_in_window = if window_start > old.window_start_ns {
                0
            } else {
                old.window_consumed_ns
            };
            if !old.alive {
                return Err(ResourceError::Revoked);
            }
            if delta_ns > old.budget.cap_ns.saturating_sub(previous_in_window) {
                return Err(ResourceError::Exhausted);
            }
            let cumulative = old
                .consumed_ns
                .checked_add(delta_ns)
                .ok_or(ResourceError::Overflow)?;
            let window_consumed = previous_in_window
                .checked_add(delta_ns)
                .ok_or(ResourceError::Overflow)?;
            let event_sequence = old
                .event_sequence
                .checked_add(1)
                .ok_or(ResourceError::Overflow)?;
            cursor = domain.inner.parent.clone();
            updates.push((
                domain,
                window_start,
                cumulative,
                window_consumed,
                event_sequence,
            ));
        }

        // Phase 2: publish the prevalidated values. No failing arithmetic,
        // admission checks, or callbacks remain in this phase. Readers of
        // usage/try_usage share the gate and cannot see a half-family charge.
        for (domain, window_start, cumulative, window_consumed, event_sequence) in updates {
            let mut state = lock_unpoisoned(&domain.inner.state);
            state.window_start_ns = window_start;
            state.window_consumed_ns = window_consumed;
            state.consumed_ns = cumulative;
            state.event_sequence = event_sequence;
            state.last_boottime_ns = now_ns;
        }
        Ok(())
    }

    /// Deterministic single-CPU interval accounting for the A06 handoff.
    /// Counts [start_ns, end_ns) in its exact fixed-period windows, including
    /// both sides of a boundary. A rejected interval changes no domain.
    /// This is still a host model, not a scheduler or actual runtime meter.
    pub fn charge_interval_for_host_model(
        &self,
        start_ns: u64,
        end_ns: u64,
    ) -> Result<(), ResourceError> {
        if end_ns <= start_ns {
            return Err(ResourceError::InvalidInterval);
        }
        let _gate = lock_unpoisoned(&self.inner.gate);
        let delta = end_ns - start_ns;
        let mut pending = Vec::new();
        let mut cursor = Some(self.clone());

        while let Some(domain) = cursor {
            let previous = domain.snapshot_state();
            if start_ns < previous.last_boottime_ns {
                return Err(ResourceError::ClockRollback);
            }
            if !previous.alive {
                return Err(ResourceError::Revoked);
            }
            let period = previous.budget.period_ns;
            let start_window = (start_ns / period) * period;
            let end_window = (end_ns / period) * period;
            let first_window_used = if previous.window_start_ns == start_window {
                previous.window_consumed_ns
            } else {
                0
            };

            let new_window_used = if start_window == end_window {
                first_window_used
                    .checked_add(delta)
                    .ok_or(ResourceError::Overflow)?
            } else {
                // A crossing may have a partially occupied first window,
                // whole intermediate windows, and a partial final window.
                // A full intermediate window is legal only at 100% cap.
                let first_end = start_window
                    .checked_add(period)
                    .ok_or(ResourceError::Overflow)?;
                let first_used = first_window_used
                    .checked_add(first_end - start_ns)
                    .ok_or(ResourceError::Overflow)?;
                if first_used > previous.budget.cap_ns {
                    return Err(ResourceError::Exhausted);
                }
                let full_periods = (end_window - first_end) / period;
                if full_periods > 0 && previous.budget.cap_ns < period {
                    return Err(ResourceError::Exhausted);
                }
                end_ns - end_window
            };
            if new_window_used > previous.budget.cap_ns {
                return Err(ResourceError::Exhausted);
            }
            let cumulative = previous
                .consumed_ns
                .checked_add(delta)
                .ok_or(ResourceError::Overflow)?;
            let event_sequence = previous
                .event_sequence
                .checked_add(1)
                .ok_or(ResourceError::Overflow)?;
            cursor = domain.inner.parent.clone();
            pending.push((
                domain,
                end_window,
                new_window_used,
                cumulative,
                event_sequence,
            ));
        }

        // The shared family gate excludes mutations and usage observations;
        // the publish phase contains no checks that can partially fail.
        for (domain, window_start, window_used, cumulative, event_sequence) in pending {
            let mut state = lock_unpoisoned(&domain.inner.state);
            state.window_start_ns = window_start;
            state.window_consumed_ns = window_used;
            state.consumed_ns = cumulative;
            state.event_sequence = event_sequence;
            state.last_boottime_ns = end_ns;
        }
        Ok(())
    }

    /// Host-model equivalent of an A06 ResourceDomain budget installation.
    /// The real scheduler must call the same CAS and grant checks from its
    /// mutation path; this helper exists so tests can exercise that contract
    /// without pretending to be a kernel scheduler.
    pub fn install_budget_for_host_model(
        &self,
        grant: &Grant,
        expected_revision: u64,
        period_ns: u64,
        cap_ns: u64,
        now_ns: u64,
    ) -> Result<BudgetReceipt, ResourceError> {
        self.apply_budget(grant, expected_revision, period_ns, cap_ns, now_ns)
    }

    fn apply_budget(
        &self,
        grant: &Grant,
        expected_revision: u64,
        period_ns: u64,
        cap_ns: u64,
        now_ns: u64,
    ) -> Result<BudgetReceipt, ResourceError> {
        let _gate = lock_unpoisoned(&self.inner.gate);
        let mut state = lock_unpoisoned(&self.inner.state);
        if !state.alive {
            return Err(ResourceError::Revoked);
        }
        if grant.epoch != state.grant_epoch {
            return Err(ResourceError::GrantEpochMismatch);
        }
        if now_ns < state.last_boottime_ns {
            return Err(ResourceError::ClockRollback);
        }
        if !Arc::ptr_eq(&grant.domain.inner, &self.inner) {
            return Err(ResourceError::GrantEpochMismatch);
        }
        if period_ns != CPU_PERIOD_NS || cap_ns > CPU_PERIOD_NS {
            return Err(ResourceError::InvalidBudget);
        }
        if expected_revision == 0 || expected_revision == u64::MAX {
            return Err(ResourceError::InvalidRevision);
        }
        if expected_revision != state.revision {
            return Err(ResourceError::RevisionConflict {
                expected: expected_revision,
                actual: state.revision,
            });
        }
        // A revoked ancestor fences child management, even if the
        // numeric parent cap has not changed. Every ancestor shares
        // this family's mutation gate with commit and revoke.
        let mut ancestor = self.inner.parent.as_ref();
        let mut depth = 0;
        while let Some(parent) = ancestor {
            let parent_state = parent.snapshot_state();
            if !parent_state.alive {
                return Err(ResourceError::Revoked);
            }
            // Checking just the current alive flag permits an old child
            // grant to resurrect after an ancestor revoke + reactivation.
            if grant.ancestor_epochs.get(depth) != Some(&parent_state.grant_epoch) {
                return Err(ResourceError::GrantEpochMismatch);
            }
            if cap_ns > parent_state.budget.cap_ns {
                return Err(ResourceError::ParentConstraint);
            }
            depth += 1;
            ancestor = parent.inner.parent.as_ref();
        }
        if grant.ancestor_epochs.len() != depth {
            return Err(ResourceError::GrantEpochMismatch);
        }
        if lock_unpoisoned(&self.inner.children)
            .values()
            .any(|child_cap| *child_cap > cap_ns)
        {
            return Err(ResourceError::ParentConstraint);
        }
        // Preflight the whole wire-visible receipt before publishing any
        // state: A02 requires consumed_at_apply <= elapsed in this period.
        // A rejected/ambiguous accounting sample must not advance revision,
        // clock or the window. Host charge_cpu can otherwise construct a
        // physically impossible sample by attributing delta to one instant.
        let window_start = (now_ns / period_ns) * period_ns;
        let consumed_at_apply_ns = if window_start > state.window_start_ns {
            0
        } else {
            state.window_consumed_ns
        };
        if consumed_at_apply_ns > now_ns - window_start {
            return Err(ResourceError::InconsistentAccounting);
        }
        let next_revision = state
            .revision
            .checked_add(1)
            .ok_or(ResourceError::Overflow)?;
        let previous_revision = state.revision;
        if window_start > state.window_start_ns {
            state.window_start_ns = window_start;
            state.window_consumed_ns = 0;
        }
        state.last_boottime_ns = now_ns;
        state.revision = next_revision;
        state.budget = Budget { period_ns, cap_ns };
        if let Some(parent) = self.inner.parent.as_ref() {
            lock_unpoisoned(&parent.inner.children).insert(state.id, cap_ns);
        }
        Ok(BudgetReceipt {
            previous_revision,
            revision: state.revision,
            effective_boottime_ns: now_ns,
            consumed_at_apply_ns,
        })
    }

    fn snapshot_state(&self) -> DomainState {
        *lock_unpoisoned(&self.inner.state)
    }
}

/// Construct a parent/child pair while retaining the parent handle needed for
/// future constraint checks.  `ResourceDomain::new` remains useful for roots.
pub fn with_parent(
    id: ResourceDomainId,
    stable_object_id: StableObjectId,
    parent: &ResourceDomain,
    initial_cap_ns: u64,
) -> Result<ResourceDomain, ResourceError> {
    ResourceDomain::new(id, stable_object_id, Some(parent), initial_cap_ns)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RequestBinding {
    pub sequence: u64,
    pub publisher: PublisherId,
    pub target: ResourceDomainId,
    pub stable_object_id: StableObjectId,
    pub expected_revision: u64,
    pub period_ns: u64,
    pub cap_ns: u64,
    pub grant_epoch: u64,
    pub payload_digest: [u8; 32],
}

#[derive(Clone)]
pub struct DeliveryRequest {
    pub sequence: u64,
    pub grant: Grant,
    pub expected_revision: u64,
    pub period_ns: u64,
    pub cap_ns: u64,
    pub payload_digest: [u8; 32],
}

impl DeliveryRequest {
    pub fn new(sequence: u64, grant: Grant, expected_revision: u64, cap_ns: u64) -> Self {
        Self {
            sequence,
            grant,
            expected_revision,
            period_ns: CPU_PERIOD_NS,
            cap_ns,
            payload_digest: [0; 32],
        }
    }

    pub fn with_payload_digest(mut self, payload_digest: [u8; 32]) -> Self {
        self.payload_digest = payload_digest;
        self
    }

    pub fn binding(&self) -> RequestBinding {
        RequestBinding {
            sequence: self.sequence,
            publisher: self.grant.principal,
            target: self.grant.domain.id(),
            stable_object_id: self.grant.domain.stable_object_id(),
            expected_revision: self.expected_revision,
            period_ns: self.period_ns,
            cap_ns: self.cap_ns,
            grant_epoch: self.grant.epoch,
            payload_digest: self.payload_digest,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeliveryStatus {
    Ok,
    InvalidInput,
    PermissionDenied,
    StaleHandle,
    Revoked,
    Conflict,
    ResourceExhausted,
    Unsupported,
    Indeterminate,
    Busy,
    OutOfOrder,
    Retired,
    ParentLimit,
}

impl DeliveryStatus {
    /// Numeric HOS2 status value without depending on the A02 codec crate.
    /// ParentLimit is represented by the wire-level Conflict status because
    /// HOS2 0.3 has no separate parent-constraint code.
    pub const fn hos2_code(self) -> u16 {
        match self {
            Self::Ok => 0,
            Self::InvalidInput => 1,
            Self::PermissionDenied => 2,
            Self::StaleHandle => 3,
            Self::Revoked => 4,
            Self::Conflict | Self::ParentLimit => 5,
            Self::ResourceExhausted => 6,
            Self::Unsupported => 7,
            Self::Indeterminate => 8,
            Self::Busy => 9,
            Self::OutOfOrder => 10,
            Self::Retired => 11,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeliveryState {
    Reserved,
    Terminal,
    Retired,
    NotSeen,
    HistoryLost,
}

impl DeliveryState {
    /// Numeric QueryDelivery state value matching HOS2 0.3.
    pub const fn hos2_code(self) -> u16 {
        match self {
            Self::Reserved => 0,
            Self::Terminal => 1,
            Self::Retired => 2,
            Self::NotSeen => 3,
            Self::HistoryLost => 4,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DeliveryObservation {
    pub state: DeliveryState,
    pub status: Option<DeliveryStatus>,
    pub id: DeliveryId,
    pub stable_object_id: Option<StableObjectId>,
    pub saved_revision: Option<u64>,
    pub previous_revision: Option<u64>,
    pub effective_ns: Option<u64>,
    pub consumed_ns: Option<u64>,
}

impl DeliveryObservation {
    /// Validate the entire public QueryDelivery observation before wire use.
    ///
    /// Public fields can be modified by a bridge. A result advertised as
    /// Terminal/Ok without the saved successful CAS receipt must NEVER
    /// become HOS2 saved_status=0. Likewise rejected and nonterminal states
    /// cannot carry successful resource metadata. A05 must reject None.
    pub const fn hos2_saved_status_code(self) -> Option<u16> {
        if self.id.sequence == 0
            || self.id.sequence == u64::MAX
            || !self.id.namespace.boot_id.is_nonzero()
            || !self.id.namespace.cap_space_id.is_nonzero()
        {
            return None;
        }
        let no_metadata = self.stable_object_id.is_none()
            && self.saved_revision.is_none()
            && self.previous_revision.is_none()
            && self.effective_ns.is_none()
            && self.consumed_ns.is_none();
        match (self.state, self.status) {
            (DeliveryState::Terminal, Some(DeliveryStatus::Ok)) => {
                match (
                    self.stable_object_id,
                    self.previous_revision,
                    self.saved_revision,
                    self.effective_ns,
                    self.consumed_ns,
                ) {
                    (
                        Some(object),
                        Some(previous),
                        Some(saved),
                        Some(effective_ns),
                        Some(consumed_ns),
                    ) if object.is_nonzero()
                        && previous > 0
                        && previous < u64::MAX
                        && saved == previous + 1
                        && consumed_ns <= effective_ns % CPU_PERIOD_NS => Some(0),
                    _ => None,
                }
            }
            (DeliveryState::Terminal, Some(status)) if no_metadata => Some(status.hos2_code()),
            (DeliveryState::Terminal, _) => None,
            (_, None) if no_metadata => Some(0),
            _ => None,
        }
    }

    fn reserved(id: DeliveryId) -> Self {
        Self {
            state: DeliveryState::Reserved,
            status: None,
            id,
            stable_object_id: None,
            saved_revision: None,
            previous_revision: None,
            effective_ns: None,
            consumed_ns: None,
        }
    }

    fn retired(id: DeliveryId) -> Self {
        Self {
            state: DeliveryState::Retired,
            status: None,
            id,
            stable_object_id: None,
            saved_revision: None,
            previous_revision: None,
            effective_ns: None,
            consumed_ns: None,
        }
    }

    fn not_seen(id: DeliveryId) -> Self {
        Self {
            state: DeliveryState::NotSeen,
            status: None,
            id,
            stable_object_id: None,
            saved_revision: None,
            previous_revision: None,
            effective_ns: None,
            consumed_ns: None,
        }
    }

    fn history_lost(id: DeliveryId) -> Self {
        Self {
            state: DeliveryState::HistoryLost,
            status: None,
            id,
            stable_object_id: None,
            saved_revision: None,
            previous_revision: None,
            effective_ns: None,
            consumed_ns: None,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PublishOutcome {
    Success {
        stable_object_id: StableObjectId,
        previous_revision: u64,
        saved_revision: u64,
        effective_ns: u64,
        consumed_ns: u64,
    },
    Failure {
        status: DeliveryStatus,
    },
}

struct Slot {
    binding: RequestBinding,
    publisher: PublisherId,
    // Public stable-ID bytes cannot authenticate an in-memory target.
    // Retain the original resource instance until contiguous retirement.
    target_instance: Arc<ResourceDomainInner>,
    // Authoritative grant context, not extra HOS2 wire bytes. An old D
    // cannot be reissued with a fresh post-revocation ancestor grant.
    ancestor_epochs: Vec<u64>,
    state: Mutex<SlotState>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum SlotState {
    Reserved,
    // Namespace destruction fences slots even if a token passed an earlier
    // liveness check.  A fenced reservation can never mutate the resource.
    Fenced,
    Terminal(PublishedResult),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct PublishedResult {
    status: DeliveryStatus,
    stable_object_id: Option<StableObjectId>,
    saved_revision: Option<u64>,
    previous_revision: Option<u64>,
    effective_ns: Option<u64>,
    consumed_ns: Option<u64>,
}

pub struct Reservation {
    id: DeliveryId,
    request: DeliveryRequest,
    slot: Arc<Slot>,
    namespace: Arc<NamespaceState>,
    generation: u64,
}

impl Reservation {
    pub fn id(&self) -> DeliveryId {
        self.id
    }

    pub fn binding(&self) -> RequestBinding {
        self.request.binding()
    }

    pub fn publisher(&self) -> PublisherId {
        self.slot.publisher
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ReserveResult {
    New(ReservationMarker),
    Existing(DeliveryObservation),
}

pub enum ReserveAttempt {
    Reserved(ReserveToken),
    Existing(DeliveryObservation),
}

/// A public marker is deliberately not a publisher credential.  The actual
/// publication token is returned by `reserve` in `ReserveToken`; this marker
/// is used only for ergonomic status reporting when callers use `try_reserve`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ReservationMarker {
    pub id: DeliveryId,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeliveryError {
    InvalidSequence,
    InvalidRequest,
    InvalidIdentity,
    InvalidCapacity,
    OutOfOrder { expected: u64, got: u64 },
    Conflict,
    ResourceExhausted,
    Retired,
    HistoryLost,
    PermissionDenied,
    Busy,
    PendingPrefix,
    NotSeen,
    InvalidAck,
    TerminalImmutable,
    InvalidPublish,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct OwnerReceipt {
    pub owner: OwnerId,
    pub receipt_digest: [u8; 32],
}

impl OwnerReceipt {
    pub const fn new(owner: OwnerId, receipt_digest: [u8; 32]) -> Self {
        Self {
            owner,
            receipt_digest,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct HistoryAck {
    namespace: NamespaceIdentity,
    through: u64,
    receipt: OwnerReceipt,
}

impl HistoryAck {
    pub fn from_owner_receipt(
        namespace: NamespaceIdentity,
        through: u64,
        receipt: OwnerReceipt,
    ) -> Result<Self, DeliveryError> {
        if through == 0 || !receipt.owner.is_nonzero() || receipt.receipt_digest == [0; 32] {
            return Err(DeliveryError::InvalidAck);
        }
        Ok(Self {
            namespace,
            through,
            receipt,
        })
    }

    pub fn through(self) -> u64 {
        self.through
    }
    pub fn owner(self) -> OwnerId {
        self.receipt.owner
    }
}

/// Original Hepta owner capability minted only with a newly initialized
/// namespace. Non-Clone and bound to the in-memory namespace instance.
pub struct OriginalOwnerAuthority {
    namespace: Arc<NamespaceState>,
    owner: OwnerId,
    generation: u64,
}

impl OriginalOwnerAuthority {
    pub const fn owner(&self) -> OwnerId {
        self.owner
    }
}

#[derive(Clone)]
pub struct DeliveryView {
    identity: NamespaceIdentity,
    namespace: Arc<NamespaceState>,
    generation: u64,
    owner: Option<OwnerId>,
}

struct NamespaceState {
    identity: NamespaceIdentity,
    state: Mutex<NamespaceInner>,
}

struct NamespaceInner {
    next_sequence: u64,
    retired_through: u64,
    capacity: usize,
    slots: BTreeMap<u64, Arc<Slot>>,
    history_lost: bool,
    generation: u64,
}

#[derive(Clone)]
pub struct ControlCore {
    namespace: Arc<NamespaceState>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RetireReceipt {
    pub retired_through: u64,
    pub next_sequence: u64,
}

impl ControlCore {
    pub fn new(boot_id: BootId, cap_space_id: CapSpaceId) -> Self {
        Self::with_capacity(boot_id, cap_space_id, DEFAULT_WINDOW_CAPACITY)
    }

    /// The trusted bootstrap must authenticate the existing Hepta owner
    /// before handing it the non-Clone retirement capability.
    pub fn with_original_owner(
        boot_id: BootId,
        cap_space_id: CapSpaceId,
        owner: OwnerId,
    ) -> Result<(Self, OriginalOwnerAuthority), DeliveryError> {
        Self::with_capacity_for_owner(boot_id, cap_space_id, DEFAULT_WINDOW_CAPACITY, owner)
    }

    /// The owner separately proves K journal durability; this memory handle
    /// alone is not an fsync certificate or a kernel credential.
    pub fn with_capacity_for_owner(
        boot_id: BootId,
        cap_space_id: CapSpaceId,
        capacity: usize,
        owner: OwnerId,
    ) -> Result<(Self, OriginalOwnerAuthority), DeliveryError> {
        if !owner.is_nonzero() {
            return Err(DeliveryError::InvalidIdentity);
        }
        let core = Self::try_with_capacity(boot_id, cap_space_id, capacity)?;
        let generation = lock_unpoisoned(&core.namespace.state).generation;
        let authority = OriginalOwnerAuthority {
            namespace: Arc::clone(&core.namespace),
            owner,
            generation,
        };
        Ok((core, authority))
    }

    /// Fallible trusted namespace bootstrap. The first HOS2 version permits
    /// at most DEFAULT_WINDOW_CAPACITY unretired writes, never an unbounded
    /// host override. Reject invalid identity/capacity before allocating.
    pub fn try_with_capacity(
        boot_id: BootId,
        cap_space_id: CapSpaceId,
        capacity: usize,
    ) -> Result<Self, DeliveryError> {
        if !boot_id.is_nonzero() || !cap_space_id.is_nonzero() {
            return Err(DeliveryError::InvalidIdentity);
        }
        if capacity == 0 || capacity > DEFAULT_WINDOW_CAPACITY {
            return Err(DeliveryError::InvalidCapacity);
        }
        let identity = NamespaceIdentity {
            boot_id,
            cap_space_id,
        };
        Ok(Self {
            namespace: Arc::new(NamespaceState {
                identity,
                state: Mutex::new(NamespaceInner {
                    next_sequence: 1,
                    retired_through: 0,
                    capacity,
                    slots: BTreeMap::new(),
                    history_lost: false,
                    generation: 1,
                }),
            }),
        })
    }

    /// Compatibility constructor for already-trusted bootstrap callers.
    /// Use try_with_capacity when handling a configurable capacity.
    pub fn with_capacity(boot_id: BootId, cap_space_id: CapSpaceId, capacity: usize) -> Self {
        Self::try_with_capacity(boot_id, cap_space_id, capacity)
            .expect("HOS2 boot/CapSpace identity and window capacity must be valid")
    }

    pub fn identity(&self) -> NamespaceIdentity {
        self.namespace.identity
    }

    pub fn next_sequence(&self) -> u64 {
        lock_unpoisoned(&self.namespace.state).next_sequence
    }

    pub fn retired_through(&self) -> u64 {
        lock_unpoisoned(&self.namespace.state).retired_through
    }

    pub fn delivery_view(&self) -> DeliveryView {
        self.delivery_view_with_owner(None)
    }

    pub fn delivery_view_for(&self, owner: OwnerId) -> Result<DeliveryView, DeliveryError> {
        if !owner.is_nonzero() {
            return Err(DeliveryError::InvalidIdentity);
        }
        Ok(self.delivery_view_with_owner(Some(owner)))
    }

    fn delivery_view_with_owner(&self, owner: Option<OwnerId>) -> DeliveryView {
        let state = lock_unpoisoned(&self.namespace.state);
        DeliveryView {
            identity: self.identity(),
            namespace: Arc::clone(&self.namespace),
            generation: state.generation,
            owner,
        }
    }

    /// Atomically reserves the global sequence slot.  The returned token is
    /// the only object that can publish that slot, subject to publisher check.
    pub fn reserve(
        &self,
        request: DeliveryRequest,
        publisher: PublisherId,
    ) -> Result<ReserveToken, DeliveryError> {
        if !publisher.is_nonzero() || request.sequence == 0 || request.sequence == u64::MAX {
            return Err(DeliveryError::InvalidSequence);
        }
        // Syntactic/static payload violations are checked *before* the
        // reservation table. They must not burn D or reserve a result slot.
        // Runtime grant/revision/parent/clock failures after reservation do
        // become immutable terminal results.
        if request.expected_revision == 0
            || request.expected_revision == u64::MAX
            || request.period_ns != CPU_PERIOD_NS
            || request.cap_ns > CPU_PERIOD_NS
        {
            return Err(DeliveryError::InvalidRequest);
        }
        if publisher != request.grant.principal {
            return Err(DeliveryError::PermissionDenied);
        }
        let mut ns = lock_unpoisoned(&self.namespace.state);
        if ns.history_lost {
            return Err(DeliveryError::HistoryLost);
        }
        if request.sequence <= ns.retired_through {
            return Err(DeliveryError::Retired);
        }
        if request.sequence < ns.next_sequence {
            if let Some(slot) = ns.slots.get(&request.sequence) {
                // A globally unique D binds the publisher as well as its
                // canonical payload and stable target. Neither another
                // publisher nor another target may claim the saved result.
                if slot.publisher == publisher
                    && slot.binding == request.binding()
                    && Arc::ptr_eq(&slot.target_instance, &request.grant.domain.inner)
                    && slot.ancestor_epochs.as_slice() == request.grant.ancestor_epochs.as_slice()
                {
                    let observation =
                        observation_from_slot(self.identity(), request.sequence, slot);
                    return match observation.state {
                        DeliveryState::Reserved => Err(DeliveryError::Busy),
                        DeliveryState::Terminal => Err(DeliveryError::TerminalImmutable),
                        _ => Err(DeliveryError::Conflict),
                    };
                }
                return Err(DeliveryError::Conflict);
            }
            return Err(DeliveryError::HistoryLost);
        }
        if request.sequence > ns.next_sequence {
            return Err(DeliveryError::OutOfOrder {
                expected: ns.next_sequence,
                got: request.sequence,
            });
        }
        if ns.slots.len() >= ns.capacity {
            return Err(DeliveryError::ResourceExhausted);
        }
        let id = DeliveryId {
            namespace: self.identity(),
            sequence: request.sequence,
        };
        let slot = Arc::new(Slot {
            binding: request.binding(),
            publisher,
            target_instance: Arc::clone(&request.grant.domain.inner),
            ancestor_epochs: request.grant.ancestor_epochs.clone(),
            state: Mutex::new(SlotState::Reserved),
        });
        ns.slots.insert(request.sequence, Arc::clone(&slot));
        ns.next_sequence = ns
            .next_sequence
            .checked_add(1)
            .ok_or(DeliveryError::ResourceExhausted)?;
        Ok(ReserveToken {
            reservation: Reservation {
                id,
                request,
                slot,
                namespace: Arc::clone(&self.namespace),
                generation: ns.generation,
            },
        })
    }

    /// Idempotent retry helper for A05 after a lost copyout.  A duplicate D
    /// returns its immutable observation instead of allocating a second slot;
    /// changed canonical bytes still return `Conflict`.
    pub fn reserve_or_get(
        &self,
        request: DeliveryRequest,
        publisher: PublisherId,
    ) -> Result<ReserveAttempt, DeliveryError> {
        let sequence = request.sequence;
        let binding = request.binding();
        match self.reserve(request, publisher) {
            Ok(token) => Ok(ReserveAttempt::Reserved(token)),
            Err(DeliveryError::Busy | DeliveryError::TerminalImmutable) => {
                let view = self.delivery_view();
                let observation = self.query_delivery(&view, sequence)?;
                if observation.id.sequence != binding.sequence {
                    return Err(DeliveryError::Conflict);
                }
                // Retire/loss may win between reserve and read. Both are
                // permanent no-replay states, never new operations.
                match observation.state {
                    DeliveryState::Reserved | DeliveryState::Terminal => {
                        Ok(ReserveAttempt::Existing(observation))
                    }
                    DeliveryState::Retired => Err(DeliveryError::Retired),
                    DeliveryState::HistoryLost | DeliveryState::NotSeen => {
                        Err(DeliveryError::HistoryLost)
                    }
                }
            }
            Err(error) => Err(error),
        }
    }

    /// Return the immutable result for a D.  This is deliberately separate
    /// from `reserve`: observation never grants execution rights.
    pub fn query_delivery(
        &self,
        view: &DeliveryView,
        sequence: u64,
    ) -> Result<DeliveryObservation, DeliveryError> {
        if view.identity != self.identity() || !Arc::ptr_eq(&view.namespace, &self.namespace) {
            return Err(DeliveryError::PermissionDenied);
        }
        // A structurally invalid query sequence is not a recoverable D,
        // even if this namespace has lost its history.
        if sequence == 0 || sequence == u64::MAX {
            return Err(DeliveryError::InvalidSequence);
        }
        let ns = lock_unpoisoned(&self.namespace.state);
        let id = DeliveryId {
            namespace: self.identity(),
            sequence,
        };
        if ns.history_lost || view.generation != ns.generation {
            return Ok(DeliveryObservation::history_lost(id));
        }
        if sequence <= ns.retired_through {
            return Ok(DeliveryObservation::retired(id));
        }
        match ns.slots.get(&sequence) {
            Some(slot) => Ok(observation_from_slot(self.identity(), sequence, slot)),
            None => Ok(DeliveryObservation::not_seen(id)),
        }
    }

    pub fn retire_through(
        &self,
        view: &DeliveryView,
        ack: HistoryAck,
        owner_authority: &OriginalOwnerAuthority,
    ) -> Result<RetireReceipt, DeliveryError> {
        if view.identity != self.identity()
            || ack.namespace != self.identity()
            || !Arc::ptr_eq(&view.namespace, &self.namespace)
            || !Arc::ptr_eq(&owner_authority.namespace, &self.namespace)
            || owner_authority.owner != ack.receipt.owner
            // An observation-only DeliveryView never grants history.ack.
            || view.owner != Some(ack.receipt.owner)
        {
            return Err(DeliveryError::PermissionDenied);
        }
        let mut ns = lock_unpoisoned(&self.namespace.state);
        if ns.history_lost
            || view.generation != ns.generation
            || owner_authority.generation != ns.generation
        {
            return Err(DeliveryError::HistoryLost);
        }
        if ack.receipt.receipt_digest == [0; 32]
            || !ack.receipt.owner.is_nonzero()
            || ack.through == 0
        {
            return Err(DeliveryError::InvalidAck);
        }
        if ack.through <= ns.retired_through {
            return Ok(RetireReceipt {
                retired_through: ns.retired_through,
                next_sequence: ns.next_sequence,
            });
        }
        if ack.through >= ns.next_sequence {
            return Err(DeliveryError::NotSeen);
        }
        for sequence in (ns.retired_through + 1)..=ack.through {
            let Some(slot) = ns.slots.get(&sequence) else {
                return Err(DeliveryError::PendingPrefix);
            };
            if !matches!(*lock_unpoisoned(&slot.state), SlotState::Terminal(_)) {
                return Err(DeliveryError::PendingPrefix);
            }
        }
        for sequence in (ns.retired_through + 1)..=ack.through {
            ns.slots.remove(&sequence);
        }
        ns.retired_through = ack.through;
        Ok(RetireReceipt {
            retired_through: ns.retired_through,
            next_sequence: ns.next_sequence,
        })
    }

    /// Model a lost namespace after boot/recovery.  Existing D values remain
    /// unknown and can never be replayed through this object.
    pub fn lose_history(&self) {
        let mut ns = lock_unpoisoned(&self.namespace.state);
        // The namespace lock prevents new reservations, while each slot lock
        // serializes this fence against in-flight commit/publish. A commit
        // that already owns its slot finishes before loss takes effect; a
        // commit that has only passed token_is_live observes Fenced instead
        // of applying an effect after loss. No resource lock is taken here.
        for slot in ns.slots.values() {
            let mut state = lock_unpoisoned(&slot.state);
            if matches!(*state, SlotState::Reserved) {
                *state = SlotState::Fenced;
            }
        }
        ns.history_lost = true;
        ns.slots.clear();
        ns.generation = ns.generation.saturating_add(1);
    }

    pub fn window_len(&self) -> usize {
        lock_unpoisoned(&self.namespace.state).slots.len()
    }

    pub fn capacity(&self) -> usize {
        lock_unpoisoned(&self.namespace.state).capacity
    }

    fn token_is_live(&self, token: &ReserveToken) -> bool {
        let ns = lock_unpoisoned(&self.namespace.state);
        !ns.history_lost
            && ns.generation == token.reservation.generation
            && ns
                .slots
                .get(&token.id().sequence)
                .map(|slot| Arc::ptr_eq(slot, &token.reservation.slot))
                .unwrap_or(false)
    }
}

pub struct ReserveToken {
    reservation: Reservation,
}

impl ReserveToken {
    pub fn reservation(&self) -> &Reservation {
        &self.reservation
    }
    pub fn id(&self) -> DeliveryId {
        self.reservation.id()
    }
    pub fn binding(&self) -> RequestBinding {
        self.reservation.binding()
    }
    pub fn publisher(&self) -> PublisherId {
        self.reservation.publisher()
    }
}

impl ControlCore {
    /// Publish an already applied kernel effect.  A05 can use this after its
    /// resource mutation; it must provide the same immutable metadata that the
    /// request bound.  This method never consults or creates a K ledger.
    pub fn publish(
        &self,
        token: &ReserveToken,
        publisher: PublisherId,
        outcome: PublishOutcome,
    ) -> Result<DeliveryObservation, DeliveryError> {
        if !Arc::ptr_eq(&token.reservation.namespace, &self.namespace)
            || token.reservation.id.namespace != self.identity()
            || publisher != token.publisher()
        {
            return Err(DeliveryError::PermissionDenied);
        }
        if !self.token_is_live(token) {
            return Err(DeliveryError::HistoryLost);
        }
        let mut slot_state = lock_unpoisoned(&token.reservation.slot.state);
        match *slot_state {
            SlotState::Fenced => return Err(DeliveryError::HistoryLost),
            SlotState::Terminal(result) => {
                return Ok(observation_from_published(
                    self.identity(),
                    token.id().sequence,
                    result,
                ))
            }
            SlotState::Reserved => {}
        }
        let result = published_result_from_outcome(token.binding(), outcome)?;
        *slot_state = SlotState::Terminal(result);
        Ok(observation_from_published(
            self.identity(),
            token.id().sequence,
            result,
        ))
    }

    /// Atomically applies a budget mutation and publishes its terminal result.
    /// The slot lock is held while the resource gate is taken, but no namespace
    /// table lock is acquired by the resource path; this preserves the
    /// delivery->resource lock direction required by the contract.
    pub fn commit(
        &self,
        token: &ReserveToken,
        publisher: PublisherId,
        now_ns: u64,
    ) -> Result<DeliveryObservation, DeliveryError> {
        if !Arc::ptr_eq(&token.reservation.namespace, &self.namespace)
            || token.reservation.id.namespace != self.identity()
            || publisher != token.publisher()
        {
            return Err(DeliveryError::PermissionDenied);
        }
        if !self.token_is_live(token) {
            return Err(DeliveryError::HistoryLost);
        }
        let mut slot_state = lock_unpoisoned(&token.reservation.slot.state);
        match *slot_state {
            SlotState::Fenced => return Err(DeliveryError::HistoryLost),
            SlotState::Terminal(result) => {
                return Ok(observation_from_published(
                    self.identity(),
                    token.id().sequence,
                    result,
                ));
            }
            SlotState::Reserved => {}
        }
        let binding = token.binding();
        let applied = token.reservation.request.grant.domain.apply_budget(
            &token.reservation.request.grant,
            binding.expected_revision,
            binding.period_ns,
            binding.cap_ns,
            now_ns,
        );
        let result = match applied {
            Ok(receipt) => PublishedResult {
                status: DeliveryStatus::Ok,
                stable_object_id: Some(binding.stable_object_id),
                saved_revision: Some(receipt.revision),
                previous_revision: Some(receipt.previous_revision),
                effective_ns: Some(receipt.effective_boottime_ns),
                consumed_ns: Some(receipt.consumed_at_apply_ns),
            },
            Err(error) => PublishedResult {
                status: map_resource_error(error),
                stable_object_id: None,
                saved_revision: None,
                previous_revision: None,
                effective_ns: None,
                consumed_ns: None,
            },
        };
        *slot_state = SlotState::Terminal(result);
        Ok(observation_from_published(
            self.identity(),
            token.id().sequence,
            result,
        ))
    }
}

fn published_result_from_outcome(
    binding: RequestBinding,
    outcome: PublishOutcome,
) -> Result<PublishedResult, DeliveryError> {
    match outcome {
        PublishOutcome::Failure { status } => {
            if status == DeliveryStatus::Ok {
                return Err(DeliveryError::InvalidPublish);
            }
            Ok(PublishedResult {
                status,
                stable_object_id: None,
                saved_revision: None,
                previous_revision: None,
                effective_ns: None,
                consumed_ns: None,
            })
        }
        PublishOutcome::Success {
            stable_object_id,
            previous_revision,
            saved_revision,
            effective_ns,
            consumed_ns,
        } => {
            if stable_object_id != binding.stable_object_id
                || !stable_object_id.is_nonzero()
                || previous_revision == 0
                || previous_revision != binding.expected_revision
                || previous_revision.checked_add(1) != Some(saved_revision)
                || consumed_ns > effective_ns % CPU_PERIOD_NS
            {
                return Err(DeliveryError::InvalidPublish);
            }
            Ok(PublishedResult {
                status: DeliveryStatus::Ok,
                stable_object_id: Some(stable_object_id),
                saved_revision: Some(saved_revision),
                previous_revision: Some(previous_revision),
                effective_ns: Some(effective_ns),
                consumed_ns: Some(consumed_ns),
            })
        }
    }
}

fn map_resource_error(error: ResourceError) -> DeliveryStatus {
    match error {
        ResourceError::Revoked | ResourceError::GrantEpochMismatch => DeliveryStatus::Revoked,
        ResourceError::RevisionConflict { .. }
        | ResourceError::DuplicateDomainId
        | ResourceError::DuplicateObjectId => DeliveryStatus::Conflict,
        ResourceError::ParentConstraint => DeliveryStatus::ParentLimit,
        ResourceError::Exhausted => DeliveryStatus::ResourceExhausted,
        ResourceError::InvalidBudget
        | ResourceError::InvalidCapacity
        | ResourceError::InvalidInterval
        | ResourceError::InvalidRevision
        | ResourceError::InvalidIdentity => DeliveryStatus::InvalidInput,
        ResourceError::Overflow
        | ResourceError::MissingParent
        | ResourceError::ClockRollback
        | ResourceError::InconsistentAccounting => DeliveryStatus::Indeterminate,
    }
}

fn observation_from_slot(
    namespace: NamespaceIdentity,
    sequence: u64,
    slot: &Arc<Slot>,
) -> DeliveryObservation {
    match *lock_unpoisoned(&slot.state) {
        SlotState::Reserved => DeliveryObservation::reserved(DeliveryId {
            namespace,
            sequence,
        }),
        SlotState::Fenced => DeliveryObservation::history_lost(DeliveryId {
            namespace,
            sequence,
        }),
        SlotState::Terminal(result) => observation_from_published(namespace, sequence, result),
    }
}

fn observation_from_published(
    namespace: NamespaceIdentity,
    sequence: u64,
    result: PublishedResult,
) -> DeliveryObservation {
    DeliveryObservation {
        state: DeliveryState::Terminal,
        status: Some(result.status),
        id: DeliveryId {
            namespace,
            sequence,
        },
        stable_object_id: result.stable_object_id,
        saved_revision: result.saved_revision,
        previous_revision: result.previous_revision,
        effective_ns: result.effective_ns,
        consumed_ns: result.consumed_ns,
    }
}

fn lock_unpoisoned<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ids(
        n: u128,
    ) -> (
        BootId,
        CapSpaceId,
        ResourceDomainId,
        StableObjectId,
        PublisherId,
        OwnerId,
    ) {
        (
            BootId::from_u128(n),
            CapSpaceId::from_u128(n + 1),
            ResourceDomainId::from_u128(n + 2),
            StableObjectId::from_u128(n + 3),
            PublisherId::from_u128(n + 4),
            OwnerId::from_u128(n + 5),
        )
    }

    #[test]
    fn reactivation_epoch_overflow_must_remain_revoked() {
        let (_, _, domain_id, object, publisher, _) = ids(100);
        let target = ResourceDomain::new(domain_id, object, None, CPU_PERIOD_NS).unwrap();
        {
            let mut state = lock_unpoisoned(&target.inner.state);
            state.grant_epoch = u64::MAX;
            state.alive = false;
        }
        assert_eq!(target.reactivate_for_host_model(), Err(ResourceError::Overflow));
        assert!(matches!(target.grant(publisher), Err(ResourceError::Revoked)));
    }

    #[test]
    fn basic_commit_and_observation() {
        let (boot, space, domain_id, object, publisher, owner) = ids(1);
        let (core, owner_authority) = ControlCore::with_original_owner(boot, space, owner).unwrap();
        let domain = ResourceDomain::new(domain_id, object, None, 50).unwrap();
        let grant = domain.grant(publisher).unwrap();
        let token = core
            .reserve(DeliveryRequest::new(1, grant, 1, 25), publisher)
            .unwrap();
        let observed = core.commit(&token, publisher, 10).unwrap();
        assert_eq!(observed.state, DeliveryState::Terminal);
        assert_eq!(observed.status, Some(DeliveryStatus::Ok));
        assert_eq!(observed.saved_revision, Some(2));
        let view = core.delivery_view_for(owner).unwrap();
        assert_eq!(core.query_delivery(&view, 1).unwrap(), observed);
        let ack =
            HistoryAck::from_owner_receipt(core.identity(), 1, OwnerReceipt::new(owner, [1; 32]))
                .unwrap();
        core.retire_through(&view, ack, &owner_authority).unwrap();
        assert_eq!(
            core.query_delivery(&view, 1).unwrap().state,
            DeliveryState::Retired
        );
    }
}
