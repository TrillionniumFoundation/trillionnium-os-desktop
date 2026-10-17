//! Management-only authority state embedded in one synthetic owner mutex.
//! These are host tests, not process authentication, actual CPU scheduling,
//! kernel lease timers, trusted recovery policy or durable Hepta evidence.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryState, DeliveryStatus, ManagementError,
    ManagementGrantConfig, ManagementGrantId, ManagementGrantSnapshot, ManagementGrantState,
    NativeDeliveryRequest, NativeGrant, NativeTarget, PublishOutcome, PublisherId, RequestBinding,
    ReserveAttempt, ResourceDomainId, StableObjectId, CPU_PERIOD_NS,
};
use std::sync::{Arc, Mutex};

fn config(n: u128) -> ManagementGrantConfig {
    ManagementGrantConfig {
        id: ManagementGrantId::from_u128(n),
        publisher: PublisherId::from_u128(n),
        target: ResourceDomainId::from_u128(3),
        stable_object_id: StableObjectId::from_u128(4),
        epoch: 7,
        issued_at_ns: 10,
        expires_at_ns: 1_000,
        max_cap_ns: 70,
    }
}

fn binding(snapshot: &ManagementGrantSnapshot) -> RequestBinding {
    RequestBinding {
        sequence: 1,
        publisher: snapshot.publisher(),
        target: snapshot.target(),
        stable_object_id: snapshot.stable_object_id(),
        wire_target_slot: 11,
        wire_target_generation: 5,
        expected_revision: 1,
        period_ns: CPU_PERIOD_NS,
        cap_ns: 17,
        grant_epoch: snapshot.epoch(),
        payload_digest: [0x29; 32],
    }
}

#[test]
fn management_snapshot_preserves_all_trusted_terms_and_accepts_boundary_caps() {
    let original = config(1);
    let state = ManagementGrantState::new(original).unwrap();
    let snapshot = state.snapshot().unwrap();
    assert_eq!(snapshot.id(), original.id);
    assert_eq!(snapshot.publisher(), original.publisher);
    assert_eq!(snapshot.target(), original.target);
    assert_eq!(snapshot.stable_object_id(), original.stable_object_id);
    assert_eq!(snapshot.epoch(), original.epoch);
    assert_eq!(snapshot.issued_at_ns(), original.issued_at_ns);
    assert_eq!(snapshot.expires_at_ns(), original.expires_at_ns);
    assert_eq!(snapshot.max_cap_ns(), original.max_cap_ns);
    assert_eq!(snapshot, snapshot.clone());
    assert_eq!(snapshot, state.snapshot().unwrap());
    let mut request = binding(&snapshot);
    for cap in [0, original.max_cap_ns] {
        request.cap_ns = cap;
        assert_eq!(
            state.check(&snapshot, request, original.issued_at_ns),
            Ok(())
        );
    }
    assert!(!state.is_revoked());
    assert_eq!(state.current_epoch(), original.epoch);
    for cap in [0, CPU_PERIOD_NS] {
        let state = ManagementGrantState::new(ManagementGrantConfig {
            max_cap_ns: cap,
            issued_at_ns: 0,
            expires_at_ns: u64::MAX,
            ..original
        })
        .unwrap();
        let snapshot = state.snapshot().unwrap();
        let mut request = binding(&snapshot);
        request.cap_ns = cap;
        assert_eq!(state.check(&snapshot, request, 0), Ok(()));
    }
}

#[test]
fn malformed_management_identities_are_rejected_before_state_creation() {
    let original = config(1);
    let variants = [
        ManagementGrantConfig {
            id: ManagementGrantId::from_u128(0),
            ..original
        },
        ManagementGrantConfig {
            publisher: PublisherId::from_u128(0),
            ..original
        },
        ManagementGrantConfig {
            target: ResourceDomainId::from_u128(0),
            ..original
        },
        ManagementGrantConfig {
            stable_object_id: StableObjectId::from_u128(0),
            ..original
        },
        ManagementGrantConfig {
            epoch: 0,
            ..original
        },
    ];
    for invalid in variants {
        assert_eq!(
            ManagementGrantState::new(invalid).err(),
            Some(ManagementError::InvalidIdentity)
        );
    }
}

#[test]
fn invalid_lease_ranges_and_cap_envelopes_are_rejected() {
    let original = config(1);
    for expiry in [0, original.issued_at_ns - 1, original.issued_at_ns] {
        assert_eq!(
            ManagementGrantState::new(ManagementGrantConfig {
                expires_at_ns: expiry,
                ..original
            })
            .err(),
            Some(ManagementError::InvalidLease)
        );
    }
    assert_eq!(
        ManagementGrantState::new(ManagementGrantConfig {
            max_cap_ns: CPU_PERIOD_NS + 1,
            ..original
        })
        .err(),
        Some(ManagementError::InvalidBudget)
    );
}

#[test]
fn management_admission_uses_inclusive_issue_and_exclusive_expiry_boundaries() {
    let original = config(1);
    let state = ManagementGrantState::new(original).unwrap();
    let snapshot = state.snapshot().unwrap();
    let request = binding(&snapshot);
    assert_eq!(
        state.check(&snapshot, request, original.issued_at_ns - 1),
        Err(ManagementError::NotYetValid)
    );
    assert_eq!(
        state.check(&snapshot, request, original.issued_at_ns),
        Ok(())
    );
    assert_eq!(
        state.check(&snapshot, request, original.expires_at_ns - 1),
        Ok(())
    );
    for now in [original.expires_at_ns, original.expires_at_ns + 1, u64::MAX] {
        assert_eq!(
            state.check(&snapshot, request, now),
            Err(ManagementError::Expired)
        );
    }
    // snapshot() captures terms and deliberately performs no clock check.
    assert_eq!(state.snapshot().unwrap(), snapshot);
    assert!(!state.is_revoked());
}

#[test]
fn management_admission_rejects_changed_binding_and_cap_outside_envelope() {
    let state = ManagementGrantState::new(config(1)).unwrap();
    let snapshot = state.snapshot().unwrap();
    let original = binding(&snapshot);
    let mut variants = [original; 5];
    variants[0].publisher = PublisherId::from_u128(99);
    variants[1].target = ResourceDomainId::from_u128(99);
    variants[2].stable_object_id = StableObjectId::from_u128(99);
    variants[3].grant_epoch += 1;
    variants[4].period_ns -= 1;
    for changed in variants {
        assert_eq!(
            state.check(&snapshot, changed, 100),
            Err(ManagementError::BindingMismatch)
        );
    }
    for cap in [snapshot.max_cap_ns() + 1, CPU_PERIOD_NS + 1, u64::MAX] {
        let request = RequestBinding {
            cap_ns: cap,
            ..original
        };
        assert_eq!(
            state.check(&snapshot, request, 100),
            Err(ManagementError::CapLimit)
        );
    }
}

#[test]
fn every_management_term_is_immutable_in_a_saved_snapshot() {
    let original = config(1);
    let state = ManagementGrantState::new(original).unwrap();
    let snapshot = state.snapshot().unwrap();
    let variants = [
        ManagementGrantConfig {
            id: ManagementGrantId::from_u128(2),
            ..original
        },
        ManagementGrantConfig {
            publisher: PublisherId::from_u128(2),
            ..original
        },
        ManagementGrantConfig {
            target: ResourceDomainId::from_u128(2),
            ..original
        },
        ManagementGrantConfig {
            stable_object_id: StableObjectId::from_u128(2),
            ..original
        },
        ManagementGrantConfig {
            epoch: 8,
            ..original
        },
        ManagementGrantConfig {
            issued_at_ns: 11,
            ..original
        },
        ManagementGrantConfig {
            expires_at_ns: 999,
            ..original
        },
        ManagementGrantConfig {
            max_cap_ns: 69,
            ..original
        },
    ];
    for changed in variants {
        let other = ManagementGrantState::new(changed).unwrap();
        assert_ne!(snapshot, other.snapshot().unwrap());
        assert_eq!(
            other.check(&snapshot, binding(&snapshot), 100),
            Err(ManagementError::SnapshotMismatch)
        );
    }
    assert_eq!(
        state.check(&snapshot.clone(), binding(&snapshot), 100),
        Ok(())
    );
}

#[test]
fn management_revocation_is_idempotent_and_rejects_every_old_snapshot_clone() {
    let mut state = ManagementGrantState::new(config(1)).unwrap();
    let snapshot = state.snapshot().unwrap();
    let clone = snapshot.clone();
    let receipt = state.revoke();
    assert_eq!(receipt.id, snapshot.id());
    assert_eq!(receipt.previous_epoch, snapshot.epoch());
    assert_eq!(receipt.epoch, snapshot.epoch() + 1);
    assert_eq!(state.current_epoch(), receipt.epoch);
    assert!(state.is_revoked());
    for saved in [&snapshot, &clone] {
        assert_eq!(
            state.check(saved, binding(saved), 100),
            Err(ManagementError::Revoked)
        );
    }
    for _ in 0..32 {
        assert_eq!(state.revoke(), receipt);
        assert_eq!(state.snapshot(), Err(ManagementError::Revoked));
        assert_eq!(state.current_epoch(), receipt.epoch);
    }
}

#[test]
fn management_epoch_max_revocation_never_wraps_or_reactivates() {
    for epoch in [u64::MAX - 1, u64::MAX] {
        let mut state =
            ManagementGrantState::new(ManagementGrantConfig { epoch, ..config(1) }).unwrap();
        let snapshot = state.snapshot().unwrap();
        let receipt = state.revoke();
        assert_eq!(receipt.previous_epoch, epoch);
        assert_eq!(receipt.epoch, u64::MAX);
        assert_eq!(state.current_epoch(), u64::MAX);
        assert_eq!(state.revoke(), receipt);
        assert_eq!(state.snapshot(), Err(ManagementError::Revoked));
        assert_eq!(
            state.check(&snapshot, binding(&snapshot), 100),
            Err(ManagementError::Revoked)
        );
    }
}

#[test]
fn fresh_state_with_identical_config_cannot_revive_a_revoked_snapshot() {
    let original = config(1);
    let mut first = ManagementGrantState::new(original).unwrap();
    let saved = first.snapshot().unwrap();
    first.revoke();
    let replacement = ManagementGrantState::new(original).unwrap();
    assert_ne!(saved, replacement.snapshot().unwrap());
    assert_eq!(
        replacement.check(&saved, binding(&saved), 100),
        Err(ManagementError::SnapshotMismatch)
    );
}

#[test]
fn destroyed_state_cannot_be_recreated_to_accept_its_old_snapshot() {
    let original = config(1);
    let saved = ManagementGrantState::new(original)
        .unwrap()
        .snapshot()
        .unwrap();
    let replacement = ManagementGrantState::new(original).unwrap();
    assert_eq!(
        replacement.check(&saved, binding(&saved), 100),
        Err(ManagementError::SnapshotMismatch)
    );
    let fresh = replacement.snapshot().unwrap();
    assert_eq!(fresh, fresh.clone());
    assert_eq!(replacement.check(&fresh, binding(&fresh), 100), Ok(()));
}

#[test]
fn management_errors_map_only_to_existing_hos2_refusal_statuses() {
    for error in [
        ManagementError::Revoked,
        ManagementError::Expired,
        ManagementError::NotYetValid,
        ManagementError::SnapshotMismatch,
    ] {
        assert_eq!(error.delivery_status(), DeliveryStatus::Revoked);
    }
    for error in [ManagementError::BindingMismatch, ManagementError::CapLimit] {
        assert_eq!(error.delivery_status(), DeliveryStatus::PermissionDenied);
    }
    for error in [
        ManagementError::InvalidIdentity,
        ManagementError::InvalidLease,
        ManagementError::InvalidBudget,
    ] {
        assert_eq!(error.delivery_status(), DeliveryStatus::InvalidInput);
    }
}

struct ExistingOwner {
    mutation: Mutex<ExistingState>,
}

struct ExistingState {
    management: [ManagementGrantState; 2],
    // The original owner's sole budget, revision and accounting state.
    revision: u64,
    cap_ns: u64,
    consumed_ns: u64,
    last_boottime_ns: u64,
    effects: usize,
}

impl ExistingOwner {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            mutation: Mutex::new(ExistingState {
                management: [
                    ManagementGrantState::new(config(1)).unwrap(),
                    ManagementGrantState::new(config(2)).unwrap(),
                ],
                revision: 1,
                cap_ns: 100,
                consumed_ns: 0,
                last_boottime_ns: 0,
                effects: 0,
            }),
        })
    }

    fn snapshot(&self, index: usize) -> ManagementGrantSnapshot {
        self.mutation.lock().unwrap().management[index]
            .snapshot()
            .unwrap()
    }

    fn charge(&self, delta: u64, now: u64) -> bool {
        let mut state = self.mutation.lock().unwrap();
        if now < state.last_boottime_ns || delta > state.cap_ns.saturating_sub(state.consumed_ns) {
            return false;
        }
        state.consumed_ns += delta;
        state.last_boottime_ns = now;
        true
    }

    fn apply(
        &self,
        snapshot: &ManagementGrantSnapshot,
        binding: RequestBinding,
        now: u64,
    ) -> PublishOutcome {
        let mut state = self.mutation.lock().unwrap();
        if now < state.last_boottime_ns {
            return PublishOutcome::Failure {
                status: DeliveryStatus::Indeterminate,
            };
        }
        let index = usize::from(binding.publisher == config(2).publisher);
        if let Err(error) = state.management[index].check(snapshot, binding, now) {
            return PublishOutcome::Failure {
                status: error.delivery_status(),
            };
        }
        if binding.expected_revision != state.revision {
            return PublishOutcome::Failure {
                status: DeliveryStatus::Conflict,
            };
        }
        let previous = state.revision;
        state.revision += 1;
        state.cap_ns = binding.cap_ns;
        state.last_boottime_ns = now;
        state.effects += 1;
        PublishOutcome::Success {
            stable_object_id: binding.stable_object_id,
            previous_revision: previous,
            saved_revision: state.revision,
            effective_ns: now,
            consumed_ns: state.consumed_ns,
        }
    }
}

fn target(owner: &Arc<ExistingOwner>) -> NativeTarget {
    NativeTarget::from_owner(
        Arc::clone(owner),
        config(1).target,
        config(1).stable_object_id,
    )
    .unwrap()
}

fn request(
    owner: &Arc<ExistingOwner>,
    snapshot: ManagementGrantSnapshot,
    sequence: u64,
    revision: u64,
) -> NativeDeliveryRequest {
    let grant = NativeGrant::from_management(target(owner), snapshot, vec![3, 7]).unwrap();
    NativeDeliveryRequest::from_wire(sequence, grant, revision, 30, 11, 5).unwrap()
}

fn core() -> ControlCore {
    ControlCore::new(BootId::from_u128(1), CapSpaceId::from_u128(2))
}

#[test]
fn management_only_revoke_preserves_accounting_and_an_independent_manager() {
    let owner = ExistingOwner::new();
    let first = owner.snapshot(0);
    let independent = owner.snapshot(1);
    let core = core();
    let first_token = core
        .reserve_native(request(&owner, first.clone(), 1, 1), first.publisher())
        .unwrap();
    let independent_token = core
        .reserve_native(
            request(&owner, independent.clone(), 2, 1),
            independent.publisher(),
        )
        .unwrap();
    owner.mutation.lock().unwrap().management[0].revoke();
    assert!(
        owner.charge(17, 50),
        "revoking management stopped live-resource accounting"
    );
    let applied = core
        .execute_native_reserved::<ExistingOwner, _>(
            &independent_token,
            independent.publisher(),
            |context| {
                context.owner().apply(
                    context.management_snapshot().unwrap(),
                    context.binding(),
                    100,
                )
            },
        )
        .unwrap();
    assert_eq!(applied.status, Some(DeliveryStatus::Ok));
    assert_eq!(applied.consumed_ns, Some(17));
    let rejected = core
        .execute_native_reserved::<ExistingOwner, _>(&first_token, first.publisher(), |context| {
            context.owner().apply(
                context.management_snapshot().unwrap(),
                context.binding(),
                101,
            )
        })
        .unwrap();
    assert_eq!(rejected.status, Some(DeliveryStatus::Revoked));
    assert_eq!(
        core.execute_native_reserved::<ExistingOwner, _>(
            &first_token,
            first.publisher(),
            |_| panic!("revoked terminal became successful")
        )
        .unwrap(),
        rejected
    );
    assert!(owner.charge(3, 102));
    let state = owner.mutation.lock().unwrap();
    assert_eq!(
        (
            state.revision,
            state.cap_ns,
            state.consumed_ns,
            state.effects
        ),
        (2, 30, 20, 1)
    );
    drop(state);
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap(),
        rejected
    );
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 2).unwrap(),
        applied
    );
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn expired_terminal_requires_a_new_d_and_fresh_owner_authority_to_apply() {
    let owner = ExistingOwner::new();
    let old = owner.snapshot(0);
    let core = core();
    let token = core
        .reserve_native(request(&owner, old.clone(), 1, 1), old.publisher())
        .unwrap();
    let refusal = core
        .execute_native_reserved::<ExistingOwner, _>(&token, old.publisher(), |context| {
            context.owner().apply(
                context.management_snapshot().unwrap(),
                context.binding(),
                old.expires_at_ns(),
            )
        })
        .unwrap();
    assert_eq!(refusal.status, Some(DeliveryStatus::Revoked));
    // Trusted owner replaces its delegation; State itself has no renewal or
    // reactivation API, and an old D keeps its original immutable refusal.
    owner.mutation.lock().unwrap().management[0] =
        ManagementGrantState::new(ManagementGrantConfig {
            epoch: old.epoch() + 1,
            expires_at_ns: old.expires_at_ns() + 1_000,
            ..config(1)
        })
        .unwrap();
    let fresh = owner.snapshot(0);
    assert_eq!(
        core.reserve_native(request(&owner, fresh.clone(), 1, 1), fresh.publisher())
            .err(),
        Some(DeliveryError::Conflict)
    );
    assert_eq!(
        core.execute_native_reserved::<ExistingOwner, _>(&token, old.publisher(), |_| panic!(
            "expired terminal reexecuted"
        ))
        .unwrap(),
        refusal
    );
    let new_token = core
        .reserve_native(request(&owner, fresh.clone(), 2, 1), fresh.publisher())
        .unwrap();
    let applied = core
        .execute_native_reserved::<ExistingOwner, _>(&new_token, fresh.publisher(), |context| {
            context.owner().apply(
                context.management_snapshot().unwrap(),
                context.binding(),
                1_001,
            )
        })
        .unwrap();
    assert_eq!(applied.status, Some(DeliveryStatus::Ok));
    assert_eq!(owner.mutation.lock().unwrap().effects, 1);
}

#[test]
fn same_d_binds_management_origin_terms_and_presence_beyond_request_binding() {
    let owner = ExistingOwner::new();
    let original = owner.snapshot(0);
    let core = core();
    let original_request = request(&owner, original.clone(), 1, 1);
    let canonical = original_request.binding();
    let _token = core
        .reserve_native(original_request, original.publisher())
        .unwrap();
    for changed in [
        ManagementGrantConfig {
            id: ManagementGrantId::from_u128(99),
            ..config(1)
        },
        ManagementGrantConfig {
            max_cap_ns: 69,
            ..config(1)
        },
        ManagementGrantConfig {
            issued_at_ns: 11,
            ..config(1)
        },
        ManagementGrantConfig {
            expires_at_ns: 999,
            ..config(1)
        },
        config(1), // Equal public config, distinct State origin.
    ] {
        let altered = ManagementGrantState::new(changed)
            .unwrap()
            .snapshot()
            .unwrap();
        let changed_request = request(&owner, altered, 1, 1);
        assert_eq!(changed_request.binding(), canonical);
        assert_eq!(
            core.reserve_native(changed_request, original.publisher())
                .err(),
            Some(DeliveryError::Conflict)
        );
    }
    let unmanaged = NativeGrant::from_owner(
        target(&owner),
        original.publisher(),
        original.epoch(),
        vec![3, 7],
    )
    .unwrap();
    let unmanaged_request = NativeDeliveryRequest::from_wire(1, unmanaged, 1, 30, 11, 5).unwrap();
    assert_eq!(unmanaged_request.binding(), canonical);
    assert_eq!(
        core.reserve_native(unmanaged_request, original.publisher())
            .err(),
        Some(DeliveryError::Conflict)
    );
    match core
        .reserve_native_or_get(
            request(&owner, original.clone(), 1, 1),
            original.publisher(),
        )
        .unwrap()
    {
        ReserveAttempt::Existing(observation) => {
            assert_eq!(observation.state, DeliveryState::Reserved)
        }
        ReserveAttempt::Reserved(_) => panic!("cloned management snapshot duplicated D"),
    }
    assert_eq!(core.next_sequence(), 2);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn new_management_state_cannot_authorize_an_old_reserved_native_snapshot() {
    let owner = ExistingOwner::new();
    let old = owner.snapshot(0);
    let core = core();
    let token = core
        .reserve_native(request(&owner, old.clone(), 1, 1), old.publisher())
        .unwrap();
    owner.mutation.lock().unwrap().management[0] = ManagementGrantState::new(config(1)).unwrap();
    let result = core
        .execute_native_reserved::<ExistingOwner, _>(&token, old.publisher(), |context| {
            context.owner().apply(
                context.management_snapshot().unwrap(),
                context.binding(),
                100,
            )
        })
        .unwrap();
    assert_eq!(result.status, Some(DeliveryStatus::Revoked));
    let state = owner.mutation.lock().unwrap();
    assert_eq!(
        (
            state.revision,
            state.cap_ns,
            state.consumed_ns,
            state.effects
        ),
        (1, 100, 0, 0)
    );
}
