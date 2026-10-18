//! Embedded resource metadata exercised through native delivery on a host.
//!
//! Each synthetic owner has one mutex containing its sole quota, settled CPU
//! usage and metadata. No host ResourceDomain, scheduler, capability resolver,
//! boot clock, parent registry or persistent Hepta ledger is created here.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryObservation, DeliveryState,
    DeliveryStatus, HistoryAck, ManagementGrantConfig, ManagementGrantId, ManagementGrantSnapshot,
    ManagementGrantState, NativeDeliveryRequest, NativeGrant, NativeResourceError,
    NativeResourceState, NativeResourceUpdate, NativeTarget, OwnerId, PublishOutcome, PublisherId,
    RequestBinding, ReserveToken, ResourceDomainId, StableObjectId, CPU_PERIOD_NS,
};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::{Arc, Mutex, MutexGuard, PoisonError};

fn publisher() -> PublisherId {
    PublisherId::from_u128(1_800_001)
}

fn history_owner() -> OwnerId {
    OwnerId::from_u128(1_800_002)
}

struct Owner {
    mutation: Mutex<OwnerState>,
}

struct OwnerState {
    metadata: NativeResourceState,
    management: Option<ManagementGrantState>,
    period_ns: u64,
    quota_ns: Option<u64>,
    used_ns: u64,
    effects: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct OwnerObservation {
    revision: u64,
    fenced: bool,
    invalidated: bool,
    indeterminate: bool,
    period_ns: u64,
    quota_ns: Option<u64>,
    used_ns: u64,
    effects: u64,
}

impl Owner {
    fn new(id: u128, cap_ns: u64, used_ns: u64, management: bool) -> Arc<Self> {
        let target = ResourceDomainId::from_u128(id);
        let object = StableObjectId::from_u128(id + 1);
        let management = management.then(|| {
            ManagementGrantState::new(ManagementGrantConfig {
                id: ManagementGrantId::from_u128(id + 2),
                publisher: publisher(),
                target,
                stable_object_id: object,
                epoch: 7,
                issued_at_ns: 10,
                expires_at_ns: 100,
                max_cap_ns: 30,
            })
            .unwrap()
        });
        Arc::new(Self {
            mutation: Mutex::new(OwnerState {
                metadata: NativeResourceState::new(target, object).unwrap(),
                management,
                period_ns: CPU_PERIOD_NS,
                quota_ns: Some(cap_ns),
                used_ns,
                effects: 0,
            }),
        })
    }

    fn lock(&self) -> MutexGuard<'_, OwnerState> {
        // Unwinding can poison this host lock. Recovery must retain the
        // embedded metadata fence, not grant another mutation attempt.
        self.mutation.lock().unwrap_or_else(PoisonError::into_inner)
    }

    fn observe(&self) -> OwnerObservation {
        let state = self.lock();
        OwnerObservation {
            revision: state.metadata.revision(),
            fenced: state.metadata.is_fenced(),
            invalidated: state.metadata.is_invalidated(),
            indeterminate: state.metadata.is_indeterminate(),
            period_ns: state.period_ns,
            quota_ns: state.quota_ns,
            used_ns: state.used_ns,
            effects: state.effects,
        }
    }

    fn request(
        self: &Arc<Self>,
        sequence: u64,
        expected_revision: u64,
        cap_ns: u64,
    ) -> NativeDeliveryRequest {
        self.request_with_identity(sequence, expected_revision, cap_ns, None)
    }

    fn request_with_identity(
        self: &Arc<Self>,
        sequence: u64,
        expected_revision: u64,
        cap_ns: u64,
        identity: Option<(ResourceDomainId, StableObjectId)>,
    ) -> NativeDeliveryRequest {
        let (id, object, management) = {
            let state = self.lock();
            let (id, object) =
                identity.unwrap_or((state.metadata.id(), state.metadata.stable_object_id()));
            let management = state
                .management
                .as_ref()
                .map(|grant| grant.snapshot().unwrap());
            (id, object, management)
        };
        let target = NativeTarget::from_owner(Arc::clone(self), id, object).unwrap();
        let grant = match management {
            Some(snapshot) => NativeGrant::from_management(target, snapshot, Vec::new()),
            None => NativeGrant::from_owner(target, publisher(), 1, Vec::new()),
        }
        .unwrap();
        NativeDeliveryRequest::from_wire(sequence, grant, expected_revision, cap_ns, 7, 13)
            .unwrap()
            .with_payload_digest([0xc7; 32])
    }

    fn apply(
        &self,
        binding: RequestBinding,
        snapshot: Option<&ManagementGrantSnapshot>,
        now_ns: u64,
        panic_after_effect: bool,
    ) -> PublishOutcome {
        let mut state = self.lock();
        // The fixture is a root owner, so there are no ancestor constraints.
        // A real owner settles its runtime and validates hierarchy/clock
        // under this same lock before the metadata/effect transition.
        if let Some(management) = state.management.as_ref() {
            let Some(snapshot) = snapshot else {
                return PublishOutcome::Failure {
                    status: DeliveryStatus::PermissionDenied,
                };
            };
            if let Err(error) = management.check(snapshot, binding, now_ns) {
                return PublishOutcome::Failure {
                    status: error.delivery_status(),
                };
            }
        } else if binding.publisher != publisher() || binding.grant_epoch != 1 {
            return PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            };
        }
        let OwnerState {
            metadata,
            period_ns,
            quota_ns,
            used_ns,
            effects,
            ..
        } = &mut *state;
        let mut mutation = || {
            *period_ns = binding.period_ns;
            *quota_ns = Some(binding.cap_ns);
            *effects += 1;
            if panic_after_effect {
                panic!("injected unwind after the sole owner budget changed");
            }
        };
        match metadata.apply(
            NativeResourceUpdate::from(binding),
            now_ns,
            *used_ns,
            &mut mutation,
        ) {
            Ok(receipt) => receipt.into_publish_outcome(),
            Err(error) => PublishOutcome::Failure {
                status: error.delivery_status(),
            },
        }
    }

    fn configure_from_linux(
        &self,
        next_period_ns: u64,
        next_quota_ns: Option<u64>,
    ) -> Result<(u64, u64), NativeResourceError> {
        let mut state = self.lock();
        let OwnerState {
            metadata,
            period_ns,
            quota_ns,
            effects,
            ..
        } = &mut *state;
        let mut mutation = || {
            *period_ns = next_period_ns;
            *quota_ns = next_quota_ns;
            *effects += 1;
        };
        metadata
            .apply_owner_configuration(&mut mutation)
            .map(|change| (change.previous_revision(), change.revision()))
    }

    fn charge_for_host_fixture(&self, delta_ns: u64) -> bool {
        let mut state = self.lock();
        let next = state.used_ns.checked_add(delta_ns).unwrap();
        if state.quota_ns.is_some_and(|quota| next > quota) {
            return false;
        }
        state.used_ns = next;
        true
    }
}

fn core(id: u128) -> (ControlCore, os_control::OriginalOwnerAuthority) {
    ControlCore::with_capacity_for_owner(
        BootId::from_u128(id),
        CapSpaceId::from_u128(id + 1),
        8,
        history_owner(),
    )
    .unwrap()
}

fn execute(
    core: &ControlCore,
    token: &ReserveToken,
    now_ns: u64,
) -> Result<DeliveryObservation, DeliveryError> {
    core.execute_native_reserved::<Owner, _>(token, publisher(), |context| {
        assert!(context.ancestor_epochs().is_empty());
        context.owner().apply(
            context.binding(),
            context.management_snapshot(),
            now_ns,
            false,
        )
    })
}

#[test]
fn distinct_deliveries_share_one_revision_cas_and_a_refusal_never_becomes_success() {
    let (core, _) = core(1_810_000);
    let owner = Owner::new(1_810_100, 20, 7, false);
    let first = core
        .reserve_native(owner.request(1, 1, 30), publisher())
        .unwrap();
    let committed = execute(&core, &first, 50).unwrap();
    assert_eq!(committed.saved_revision, Some(2));
    assert_eq!(committed.consumed_ns, Some(7));

    let stale = core
        .reserve_native(owner.request(2, 1, 40), publisher())
        .unwrap();
    let before = owner.observe();
    let refusal = execute(&core, &stale, 60).unwrap();
    assert_eq!(refusal.status, Some(DeliveryStatus::Conflict));
    assert_eq!(owner.observe(), before);

    let current = core
        .reserve_native(owner.request(3, 2, 40), publisher())
        .unwrap();
    assert_eq!(
        execute(&core, &current, 70).unwrap().saved_revision,
        Some(3)
    );
    assert_eq!(owner.observe().effects, 2);
    assert_eq!(execute(&core, &stale, 80).unwrap(), refusal);
    assert_eq!(owner.observe().effects, 2);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn linux_configuration_advances_the_same_revision_without_hos2_budget_restrictions() {
    let (core, _) = core(1_820_000);
    let owner = Owner::new(1_820_100, 20, 7, false);
    let stale = core
        .reserve_native(owner.request(1, 1, 30), publisher())
        .unwrap();

    assert_eq!(owner.configure_from_linux(37_000_000, None), Ok((1, 2)));
    let unlimited = owner.observe();
    assert_eq!(unlimited.period_ns, 37_000_000);
    assert_eq!(unlimited.quota_ns, None);
    assert_eq!(unlimited.used_ns, 7);
    assert_eq!(unlimited.effects, 1);
    assert_eq!(
        execute(&core, &stale, 50).unwrap().status,
        Some(DeliveryStatus::Conflict)
    );
    assert_eq!(owner.observe(), unlimited);

    // Linux allows quota greater than period. The generic revision path
    // does not impose the separate fixed-period HOS2 InstallBudget profile.
    assert_eq!(
        owner.configure_from_linux(17_000_000, Some(2 * CPU_PERIOD_NS)),
        Ok((2, 3))
    );
    assert_eq!(owner.observe().used_ns, 7);
    let native = core
        .reserve_native(owner.request(2, 3, 30), publisher())
        .unwrap();
    assert_eq!(execute(&core, &native, 60).unwrap().saved_revision, Some(4));
    let native_state = owner.observe();
    assert_eq!(native_state.period_ns, CPU_PERIOD_NS);
    assert_eq!(native_state.quota_ns, Some(30));
    assert_eq!(native_state.used_ns, 7);
    assert_eq!(native_state.effects, 3);
}

#[test]
fn same_cap_updates_preserve_the_only_usage_counter_and_never_recharge_quota() {
    let (core, _) = core(1_830_000);
    let owner = Owner::new(1_830_100, 30, 19, false);
    for sequence in 1..=2 {
        let token = core
            .reserve_native(owner.request(sequence, sequence, 30), publisher())
            .unwrap();
        let result = execute(&core, &token, 50).unwrap();
        assert_eq!(result.status, Some(DeliveryStatus::Ok));
        assert_eq!(result.consumed_ns, Some(19));
        assert_eq!(owner.observe().used_ns, 19);
    }
    assert!(!owner.charge_for_host_fixture(12));
    assert_eq!(owner.observe().used_ns, 19);
    assert!(owner.charge_for_host_fixture(11));
    assert_eq!(owner.observe().used_ns, 30);

    let token = core
        .reserve_native(owner.request(3, 3, 30), publisher())
        .unwrap();
    assert_eq!(execute(&core, &token, 60).unwrap().consumed_ns, Some(30));
    assert!(!owner.charge_for_host_fixture(1));
    assert_eq!(owner.observe().used_ns, 30);
    assert_eq!(owner.observe().effects, 3);
    assert_eq!(owner.observe().revision, 4);
}

#[test]
fn wrong_identity_and_unrepresentable_receipt_are_refused_before_owner_effect() {
    let (core, _) = core(1_840_000);
    let owner = Owner::new(1_840_100, 20, 7, false);
    let correct_id = ResourceDomainId::from_u128(1_840_100);
    let correct_object = StableObjectId::from_u128(1_840_101);
    for (sequence, id, object) in [
        (1, ResourceDomainId::from_u128(1_840_999), correct_object),
        (2, correct_id, StableObjectId::from_u128(1_840_999)),
    ] {
        let request = owner.request_with_identity(sequence, 1, 30, Some((id, object)));
        let token = core.reserve_native(request, publisher()).unwrap();
        let before = owner.observe();
        assert_eq!(
            execute(&core, &token, 50).unwrap().status,
            Some(DeliveryStatus::PermissionDenied)
        );
        assert_eq!(owner.observe(), before);
    }
    let token = core
        .reserve_native(owner.request(3, 1, 30), publisher())
        .unwrap();
    let before = owner.observe();
    let refusal = execute(&core, &token, 6).unwrap();
    assert_eq!(refusal.status, Some(DeliveryStatus::Indeterminate));
    assert_eq!(owner.observe(), before);
    assert!(!owner.observe().fenced);

    let current = core
        .reserve_native(owner.request(4, 1, 30), publisher())
        .unwrap();
    assert_eq!(
        execute(&core, &current, 50).unwrap().saved_revision,
        Some(2)
    );
    assert_eq!(execute(&core, &token, 60).unwrap(), refusal);
    assert_eq!(owner.observe().effects, 1);
}

#[test]
fn unwind_after_effect_fences_new_deliveries_and_owner_writes_without_resetting_pending_d() {
    let (core, authority) = core(1_850_000);
    let owner = Owner::new(1_850_100, 20, 7, false);
    let interrupted = core
        .reserve_native(owner.request(1, 1, 30), publisher())
        .unwrap();
    assert!(catch_unwind(AssertUnwindSafe(|| {
        core.execute_native_reserved::<Owner, _>(&interrupted, publisher(), |context| {
            context
                .owner()
                .apply(context.binding(), context.management_snapshot(), 50, true)
        })
    }))
    .is_err());
    let after_unwind = owner.observe();
    assert_eq!(after_unwind.revision, 1);
    assert!(after_unwind.fenced);
    assert!(!after_unwind.invalidated);
    assert!(after_unwind.indeterminate);
    assert_eq!(after_unwind.quota_ns, Some(30));
    assert_eq!(after_unwind.used_ns, 7);
    assert_eq!(after_unwind.effects, 1);
    assert_eq!(execute(&core, &interrupted, 60), Err(DeliveryError::Busy));
    {
        let mut state = owner.lock();
        state.metadata.invalidate();
        state.metadata.invalidate();
    }
    assert_eq!(owner.observe(), after_unwind);

    for (sequence, revision) in [(2, 1), (3, 2)] {
        let token = core
            .reserve_native(owner.request(sequence, revision, 40), publisher())
            .unwrap();
        assert_eq!(
            execute(&core, &token, 70).unwrap().status,
            Some(DeliveryStatus::Indeterminate)
        );
        assert_eq!(owner.observe(), after_unwind);
    }
    assert_eq!(
        owner.configure_from_linux(37_000_000, None),
        Err(NativeResourceError::Indeterminate)
    );
    assert_eq!(owner.observe(), after_unwind);
    let view = core.delivery_view_for(history_owner()).unwrap();
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Reserved
    );
    let ack = authority.history_ack(3, [0xc7; 32]).unwrap();
    assert_eq!(
        core.retire_through(&view, ack, &authority),
        Err(DeliveryError::PendingPrefix)
    );
    assert_eq!(core.retired_through(), 0);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn management_snapshot_is_rechecked_under_the_same_owner_lock_as_metadata_and_quota() {
    let (core, _) = core(1_860_000);
    let owner = Owner::new(1_860_100, 20, 7, true);
    let first = core
        .reserve_native(owner.request(1, 1, 20), publisher())
        .unwrap();
    assert_eq!(execute(&core, &first, 50).unwrap().saved_revision, Some(2));
    let denied = core
        .reserve_native(owner.request(2, 2, 25), publisher())
        .unwrap();
    {
        let mut state = owner.lock();
        state.management.as_mut().unwrap().revoke();
    }
    let before = owner.observe();
    let refusal = execute(&core, &denied, 60).unwrap();
    assert_eq!(refusal.status, Some(DeliveryStatus::Revoked));
    assert_eq!(owner.observe(), before);
    assert_eq!(before.revision, 2);
    assert_eq!(before.effects, 1);
    assert_eq!(before.used_ns, 7);
    assert!(!before.fenced);
    assert_eq!(execute(&core, &denied, 70).unwrap(), refusal);
    assert_eq!(execute(&core, &first, 80).unwrap().saved_revision, Some(2));
    assert_eq!(owner.observe(), before);
}

#[test]
fn invalidating_the_original_pinned_owner_fences_pending_and_new_d_but_keeps_prior_terminal() {
    let (core, _) = core(1_870_000);
    let owner = Owner::new(1_870_100, 20, 7, false);
    let first = core
        .reserve_native(owner.request(1, 1, 30), publisher())
        .unwrap();
    let prior_terminal = execute(&core, &first, 50).unwrap();
    assert_eq!(prior_terminal.status, Some(DeliveryStatus::Ok));
    let pending = core
        .reserve_native(owner.request(2, 2, 40), publisher())
        .unwrap();
    let before = owner.observe();
    {
        // This simulates detachment under the original owner's mutex, not
        // actual Asterinas RCU replacement or its IRQ/lock ordering.
        let mut state = owner.lock();
        state.metadata.invalidate();
        state.metadata.invalidate();
    }
    let invalidated = owner.observe();
    assert!(invalidated.fenced);
    assert!(invalidated.invalidated);
    assert!(!invalidated.indeterminate);
    assert_eq!(invalidated.revision, before.revision);
    assert_eq!(invalidated.period_ns, before.period_ns);
    assert_eq!(invalidated.quota_ns, before.quota_ns);
    assert_eq!(invalidated.used_ns, before.used_ns);
    assert_eq!(invalidated.effects, before.effects);

    let refusal = execute(&core, &pending, 60).unwrap();
    assert_eq!(refusal.status, Some(DeliveryStatus::Revoked));
    let fresh = core
        .reserve_native(owner.request(3, 2, 40), publisher())
        .unwrap();
    assert_eq!(
        execute(&core, &fresh, 70).unwrap().status,
        Some(DeliveryStatus::Revoked)
    );
    assert_eq!(owner.observe(), invalidated);
    assert_eq!(
        owner.configure_from_linux(37_000_000, None),
        Err(NativeResourceError::Invalidated)
    );
    assert_eq!(execute(&core, &first, 80).unwrap(), prior_terminal);
    assert_eq!(execute(&core, &pending, 90).unwrap(), refusal);
    assert_eq!(owner.observe(), invalidated);
    core.validate_invariants_for_host_model().unwrap();
}
