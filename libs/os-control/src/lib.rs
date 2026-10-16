//! A03 HOS2 control state core.
//!
//! This crate is a Linux host model for the control state machine.  It is
//! intentionally independent of the HOS2 wire codec and of the kernel.  In
//! particular, a passing test here proves only the model's state invariants;
//! it does not prove ioctl, credentials, scheduler, copyout, or persistence
//! behaviour in a real kernel.

use std::collections::BTreeMap;
use std::fmt;
use std::sync::{Arc, Mutex, MutexGuard};

pub const CPU_PERIOD_NS: u64 = 100_000_000;
pub const DEFAULT_WINDOW_CAPACITY: usize = 1024;

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
    pub boot_id: BootId,
    pub cap_space_id: CapSpaceId,
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
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct DeliveryId {
    pub namespace: NamespaceIdentity,
    pub sequence: u64,
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
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum IdentityError {
    ZeroIdentity,
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
    state: Mutex<DomainState>,
    parent: Option<ResourceDomain>,
    children: Mutex<BTreeMap<ResourceDomainId, u64>>,
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
    event_sequence: u64,
    dropped_events: u64,
    alive: bool,
    grant_epoch: u64,
    user_paused: bool,
}

#[derive(Clone)]
pub struct Grant {
    domain: ResourceDomain,
    pub principal: PublisherId,
    epoch: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RevokeReceipt {
    pub domain: ResourceDomainId,
    pub epoch: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ResourceError {
    InvalidIdentity,
    InvalidBudget,
    InvalidRevision,
    RevisionConflict { expected: u64, actual: u64 },
    ParentConstraint,
    Revoked,
    GrantEpochMismatch,
    Exhausted,
    Overflow,
    MissingParent,
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
            let parent_state = parent.snapshot_state();
            if initial_cap_ns > parent_state.budget.cap_ns {
                return Err(ResourceError::ParentConstraint);
            }
            let inner = Arc::new(ResourceDomainInner {
                gate: Arc::clone(&parent.inner.gate),
                state: Mutex::new(DomainState {
                    id,
                    stable_object_id,
                    parent: Some(parent_state.id),
                    revision: 1,
                    budget,
                    consumed_ns: 0,
                    window_consumed_ns: 0,
                    window_start_ns: 0,
                    event_sequence: 0,
                    dropped_events: 0,
                    alive: true,
                    grant_epoch: 1,
                    user_paused: false,
                }),
                parent: Some(parent.clone()),
                children: Mutex::new(BTreeMap::new()),
            });
            lock_unpoisoned(&parent.inner.children).insert(id, initial_cap_ns);
            return Ok(Self { inner });
        }
        Ok(Self {
            inner: Arc::new(ResourceDomainInner {
                gate: Arc::new(Mutex::new(())),
                state: Mutex::new(DomainState {
                    id,
                    stable_object_id,
                    parent: None,
                    revision: 1,
                    budget,
                    consumed_ns: 0,
                    window_consumed_ns: 0,
                    window_start_ns: 0,
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
        let state = self.snapshot_state();
        if !state.alive {
            return Err(ResourceError::Revoked);
        }
        if !principal.is_nonzero() {
            return Err(ResourceError::InvalidIdentity);
        }
        Ok(Grant {
            domain: self.clone(),
            principal,
            epoch: state.grant_epoch,
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
        state.alive = true;
        state.grant_epoch = state
            .grant_epoch
            .checked_add(1)
            .ok_or(ResourceError::Overflow)?;
        Ok(())
    }

    pub fn set_user_paused(&self, paused: bool) {
        let _gate = lock_unpoisoned(&self.inner.gate);
        lock_unpoisoned(&self.inner.state).user_paused = paused;
    }

    pub fn user_paused(&self) -> bool {
        self.snapshot_state().user_paused
    }

    pub fn usage(&self, sample_boottime_ns: u64) -> UsageSnapshot {
        let _gate = lock_unpoisoned(&self.inner.gate);
        let mut state = lock_unpoisoned(&self.inner.state);
        let window_start_ns =
            (sample_boottime_ns / state.budget.period_ns) * state.budget.period_ns;
        if window_start_ns != state.window_start_ns {
            state.window_start_ns = window_start_ns;
            state.window_consumed_ns = 0;
        }
        UsageSnapshot {
            stable_object_id: state.stable_object_id,
            revision: state.revision,
            sample_boottime_ns,
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

    /// Charge actual CPU execution to this domain and each ancestor once.
    /// This is a host-model accounting primitive; it is not a scheduler hook.
    pub fn charge_cpu(&self, delta_ns: u64, now_ns: u64) -> Result<(), ResourceError> {
        let _gate = lock_unpoisoned(&self.inner.gate);
        self.charge_locked(delta_ns, now_ns)
    }

    fn charge_locked(&self, delta_ns: u64, now_ns: u64) -> Result<(), ResourceError> {
        let parent = self.inner.parent.clone();
        {
            let mut state = lock_unpoisoned(&self.inner.state);
            let new_window_start = (now_ns / state.budget.period_ns) * state.budget.period_ns;
            if new_window_start != state.window_start_ns {
                state.window_start_ns = new_window_start;
                state.window_consumed_ns = 0;
            }
            if !state.alive
                || delta_ns > state.budget.cap_ns.saturating_sub(state.window_consumed_ns)
            {
                return Err(ResourceError::Exhausted);
            }
            if state.consumed_ns.checked_add(delta_ns).is_none()
                || state.window_consumed_ns.checked_add(delta_ns).is_none()
                || state.event_sequence.checked_add(1).is_none()
            {
                return Err(ResourceError::Overflow);
            }
        }
        if let Some(parent) = parent {
            parent.charge_locked(delta_ns, now_ns)?;
        }
        let mut state = lock_unpoisoned(&self.inner.state);
        state.consumed_ns = state
            .consumed_ns
            .checked_add(delta_ns)
            .ok_or(ResourceError::Overflow)?;
        state.window_consumed_ns = state
            .window_consumed_ns
            .checked_add(delta_ns)
            .ok_or(ResourceError::Overflow)?;
        state.event_sequence = state
            .event_sequence
            .checked_add(1)
            .ok_or(ResourceError::Overflow)?;
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
        if let Some(parent) = &grant.domain.parent_domain_for_model() {
            let parent_state = parent.snapshot_state();
            if cap_ns > parent_state.budget.cap_ns {
                return Err(ResourceError::ParentConstraint);
            }
        }
        if self
            .inner
            .children
            .lock()
            .map(|children| children.values().any(|child_cap| *child_cap > cap_ns))
            .unwrap_or(false)
        {
            return Err(ResourceError::ParentConstraint);
        }
        let previous_revision = state.revision;
        state.revision = state
            .revision
            .checked_add(1)
            .ok_or(ResourceError::Overflow)?;
        state.budget = Budget { period_ns, cap_ns };
        if let Some(parent) = &grant.domain.parent_domain_for_model() {
            lock_unpoisoned(&parent.inner.children).insert(state.id, cap_ns);
        }
        let consumed_at_apply_ns = state.window_consumed_ns;
        Ok(BudgetReceipt {
            previous_revision,
            revision: state.revision,
            effective_boottime_ns: now_ns,
            consumed_at_apply_ns,
        })
    }

    fn parent_domain_for_model(&self) -> Option<ResourceDomain> {
        self.inner.parent.clone()
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
    let budget = Budget::new(initial_cap_ns)?;
    let parent_state = parent.snapshot_state();
    if initial_cap_ns > parent_state.budget.cap_ns {
        return Err(ResourceError::ParentConstraint);
    }
    if !id.is_nonzero() || !stable_object_id.is_nonzero() {
        return Err(ResourceError::InvalidIdentity);
    }
    let child = ResourceDomain {
        inner: Arc::new(ResourceDomainInner {
            gate: Arc::clone(&parent.inner.gate),
            state: Mutex::new(DomainState {
                id,
                stable_object_id,
                parent: Some(parent_state.id),
                revision: 1,
                budget,
                consumed_ns: 0,
                window_consumed_ns: 0,
                window_start_ns: 0,
                event_sequence: 0,
                dropped_events: 0,
                alive: true,
                grant_epoch: 1,
                user_paused: false,
            }),
            parent: Some(parent.clone()),
            children: Mutex::new(BTreeMap::new()),
        }),
    };
    lock_unpoisoned(&parent.inner.children).insert(id, initial_cap_ns);
    Ok(child)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RequestBinding {
    pub sequence: u64,
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

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeliveryState {
    Reserved,
    Terminal,
    Retired,
    NotSeen,
    HistoryLost,
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

#[derive(Debug)]
struct Slot {
    binding: RequestBinding,
    publisher: PublisherId,
    state: Mutex<SlotState>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum SlotState {
    Reserved,
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
    InvalidIdentity,
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

    pub fn with_capacity(boot_id: BootId, cap_space_id: CapSpaceId, capacity: usize) -> Self {
        assert!(
            boot_id.is_nonzero() && cap_space_id.is_nonzero(),
            "HOS2 identities must be non-zero"
        );
        assert!(capacity > 0, "delivery capacity must be non-zero");
        let identity = NamespaceIdentity {
            boot_id,
            cap_space_id,
        };
        Self {
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
        }
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
                if slot.binding == request.binding() {
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
                if observation.state == DeliveryState::Reserved
                    || observation.state == DeliveryState::Terminal
                        && observation.id.sequence == binding.sequence
                {
                    Ok(ReserveAttempt::Existing(observation))
                } else {
                    Err(DeliveryError::Conflict)
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
        let ns = lock_unpoisoned(&self.namespace.state);
        let id = DeliveryId {
            namespace: self.identity(),
            sequence,
        };
        if ns.history_lost || view.generation != ns.generation {
            return Ok(DeliveryObservation::history_lost(id));
        }
        if sequence == 0 || sequence == u64::MAX {
            return Err(DeliveryError::InvalidSequence);
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
    ) -> Result<RetireReceipt, DeliveryError> {
        if view.identity != self.identity()
            || ack.namespace != self.identity()
            || !Arc::ptr_eq(&view.namespace, &self.namespace)
            || view
                .owner
                .map(|owner| owner != ack.receipt.owner)
                .unwrap_or(false)
        {
            return Err(DeliveryError::PermissionDenied);
        }
        let mut ns = lock_unpoisoned(&self.namespace.state);
        if ns.history_lost || view.generation != ns.generation {
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
            SlotState::Terminal(_) => {
                return Ok(observation_from_published(
                    self.identity(),
                    token.id().sequence,
                    match *slot_state {
                        SlotState::Terminal(result) => result,
                        SlotState::Reserved => unreachable!(),
                    },
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
        if let SlotState::Terminal(result) = *slot_state {
            return Ok(observation_from_published(
                self.identity(),
                token.id().sequence,
                result,
            ));
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
                || previous_revision != binding.expected_revision
                || previous_revision.checked_add(1) != Some(saved_revision)
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
        ResourceError::RevisionConflict { .. } => DeliveryStatus::Conflict,
        ResourceError::ParentConstraint => DeliveryStatus::ParentLimit,
        ResourceError::Exhausted => DeliveryStatus::ResourceExhausted,
        ResourceError::InvalidBudget
        | ResourceError::InvalidRevision
        | ResourceError::InvalidIdentity => DeliveryStatus::InvalidInput,
        ResourceError::Overflow | ResourceError::MissingParent => DeliveryStatus::Indeterminate,
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
    fn basic_commit_and_observation() {
        let (boot, space, domain_id, object, publisher, owner) = ids(1);
        let core = ControlCore::new(boot, space);
        let domain = ResourceDomain::new(domain_id, object, None, 50).unwrap();
        let grant = domain.grant(publisher).unwrap();
        let token = core
            .reserve(DeliveryRequest::new(1, grant, 1, 25), publisher)
            .unwrap();
        let observed = core.commit(&token, publisher, 10).unwrap();
        assert_eq!(observed.state, DeliveryState::Terminal);
        assert_eq!(observed.status, Some(DeliveryStatus::Ok));
        assert_eq!(observed.saved_revision, Some(2));
        let view = core.delivery_view();
        assert_eq!(core.query_delivery(&view, 1).unwrap(), observed);
        let ack =
            HistoryAck::from_owner_receipt(core.identity(), 1, OwnerReceipt::new(owner, [1; 32]))
                .unwrap();
        core.retire_through(&view, ack).unwrap();
        assert_eq!(
            core.query_delivery(&view, 1).unwrap().state,
            DeliveryState::Retired
        );
    }
}
