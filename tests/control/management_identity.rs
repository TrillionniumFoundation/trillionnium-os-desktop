//! Public-API identity regressions for embedded management delegations.
//!
//! The synthetic owner below keeps its only budget and delegation under one
//! host mutex. It is not a kernel capability, scheduler, lease clock or Hepta
//! durable owner. Snapshot identity must survive ordinary value copies without
//! allowing independently constructed authority states to become aliases.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryState, DeliveryStatus, ManagementError,
    ManagementGrantConfig, ManagementGrantId, ManagementGrantSnapshot, ManagementGrantState,
    NativeDeliveryRequest, NativeGrant, NativeTarget, PublishOutcome, PublisherId, RequestBinding,
    ReserveAttempt, ResourceDomainId, StableObjectId, CPU_PERIOD_NS,
};
use std::sync::{Arc, Mutex};

fn config(id: u128) -> ManagementGrantConfig {
    ManagementGrantConfig {
        id: ManagementGrantId::from_u128(id),
        publisher: PublisherId::from_u128(id + 1),
        target: ResourceDomainId::from_u128(id + 2),
        stable_object_id: StableObjectId::from_u128(id + 3),
        epoch: 7,
        issued_at_ns: 10,
        expires_at_ns: 100,
        max_cap_ns: 20,
    }
}

fn binding(config: ManagementGrantConfig, sequence: u64, cap_ns: u64) -> RequestBinding {
    RequestBinding {
        sequence,
        publisher: config.publisher,
        target: config.target,
        stable_object_id: config.stable_object_id,
        wire_target_slot: 11,
        wire_target_generation: 5,
        expected_revision: 1,
        period_ns: CPU_PERIOD_NS,
        cap_ns,
        grant_epoch: config.epoch,
        payload_digest: [0x71; 32],
    }
}

#[test]
fn independent_states_with_identical_config_cannot_use_each_others_snapshots() {
    let config = config(1_510_000);
    let first = ManagementGrantState::new(config).unwrap();
    let second = ManagementGrantState::new(config).unwrap();
    let first_snapshot = first.snapshot().unwrap();
    let second_snapshot = second.snapshot().unwrap();
    assert_ne!(first_snapshot, second_snapshot);
    assert_eq!(
        first.check(&first_snapshot, binding(config, 1, 12), 30),
        Ok(())
    );
    assert_eq!(
        second.check(&second_snapshot, binding(config, 1, 12), 30),
        Ok(())
    );
    assert_eq!(
        second.check(&first_snapshot, binding(config, 1, 12), 30),
        Err(ManagementError::SnapshotMismatch)
    );
    assert_eq!(
        first.check(&second_snapshot, binding(config, 1, 12), 30),
        Err(ManagementError::SnapshotMismatch)
    );
}

#[test]
fn revoke_then_reconstruct_same_config_does_not_reactivate_the_old_snapshot() {
    let config = config(1_510_100);
    let mut original = ManagementGrantState::new(config).unwrap();
    let saved = original.snapshot().unwrap();
    let receipt = original.revoke();
    assert_eq!(receipt.previous_epoch, config.epoch);
    assert_eq!(receipt.epoch, config.epoch + 1);
    assert_eq!(original.revoke(), receipt);
    assert_eq!(
        original.check(&saved, binding(config, 1, 12), 30),
        Err(ManagementError::Revoked)
    );

    let replacement = ManagementGrantState::new(config).unwrap();
    let fresh = replacement.snapshot().unwrap();
    assert_ne!(saved, fresh);
    assert_eq!(
        replacement.check(&saved, binding(config, 1, 12), 30),
        Err(ManagementError::SnapshotMismatch)
    );
    assert_eq!(
        replacement.check(&fresh, binding(config, 1, 12), 30),
        Ok(())
    );
}

#[test]
fn snapshot_after_state_destruction_is_metadata_and_cannot_authorize_a_new_state() {
    let config = config(1_510_200);
    let saved = {
        let state = ManagementGrantState::new(config).unwrap();
        state.snapshot().unwrap()
    };
    assert_eq!(saved.id(), config.id);
    assert_eq!(saved.epoch(), config.epoch);
    assert_eq!(saved.issued_at_ns(), config.issued_at_ns);
    assert_eq!(saved.expires_at_ns(), config.expires_at_ns);
    assert_eq!(saved.max_cap_ns(), config.max_cap_ns);
    let replacement = ManagementGrantState::new(config).unwrap();
    assert_ne!(saved, replacement.snapshot().unwrap());
    assert_eq!(
        replacement.check(&saved, binding(config, 1, 12), 30),
        Err(ManagementError::SnapshotMismatch)
    );
}

#[test]
fn modifying_the_input_config_copy_does_not_change_saved_terms_or_live_authority() {
    let mut input = config(1_510_300);
    let original = input;
    let state = ManagementGrantState::new(input).unwrap();
    let saved = state.snapshot().unwrap();
    input.max_cap_ns = 90;
    input.expires_at_ns = 1_000;
    input.epoch += 1;

    assert_eq!(state.current_epoch(), original.epoch);
    assert_eq!(saved.max_cap_ns(), original.max_cap_ns);
    assert_eq!(saved.expires_at_ns(), original.expires_at_ns);
    assert_eq!(saved.epoch(), original.epoch);
    assert_eq!(
        state.check(&saved, binding(original, 1, original.max_cap_ns + 1), 30),
        Err(ManagementError::CapLimit)
    );
    assert_eq!(
        state.check(&saved, binding(original, 1, 12), original.expires_at_ns),
        Err(ManagementError::Expired)
    );
    let other = ManagementGrantState::new(input).unwrap();
    assert_eq!(
        other.check(&saved, binding(original, 1, 12), 30),
        Err(ManagementError::SnapshotMismatch)
    );
}

struct OwnerState {
    management: ManagementGrantState,
    revision: u64,
    cap_ns: u64,
    effects: usize,
    last_error: Option<ManagementError>,
}

struct Owner {
    mutation: Mutex<OwnerState>,
}

impl Owner {
    fn new(config: ManagementGrantConfig) -> Arc<Self> {
        Arc::new(Self {
            mutation: Mutex::new(OwnerState {
                management: ManagementGrantState::new(config).unwrap(),
                revision: 1,
                cap_ns: 5,
                effects: 0,
                last_error: None,
            }),
        })
    }

    fn snapshot(&self) -> ManagementGrantSnapshot {
        self.mutation.lock().unwrap().management.snapshot().unwrap()
    }

    fn request(self: &Arc<Self>, snapshot: ManagementGrantSnapshot) -> NativeDeliveryRequest {
        let target = NativeTarget::from_owner(
            Arc::clone(self),
            snapshot.target(),
            snapshot.stable_object_id(),
        )
        .unwrap();
        NativeDeliveryRequest::from_wire(
            1,
            NativeGrant::from_management(target, snapshot, Vec::new()).unwrap(),
            1,
            12,
            11,
            5,
        )
        .unwrap()
        .with_payload_digest([0x71; 32])
    }

    fn apply(&self, saved: &ManagementGrantSnapshot, binding: RequestBinding) -> PublishOutcome {
        let mut state = self.mutation.lock().unwrap();
        if let Err(error) = state.management.check(saved, binding, 30) {
            state.last_error = Some(error);
            // This synthetic owner's policy maps stale authority to Revoked.
            return PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            };
        }
        if binding.expected_revision != state.revision {
            return PublishOutcome::Failure {
                status: DeliveryStatus::Conflict,
            };
        }
        let previous = state.revision;
        state.cap_ns = binding.cap_ns;
        state.revision += 1;
        state.effects += 1;
        PublishOutcome::Success {
            stable_object_id: binding.stable_object_id,
            previous_revision: previous,
            saved_revision: state.revision,
            effective_ns: 30,
            consumed_ns: 0,
        }
    }
}

#[test]
fn replacing_state_inside_the_same_owner_cannot_reauthorize_a_reserved_old_d() {
    let config = config(1_510_400);
    let owner = Owner::new(config);
    let old_snapshot = owner.snapshot();
    let old_request = owner.request(old_snapshot.clone());
    let core = ControlCore::new(
        BootId::from_u128(1_510_450),
        CapSpaceId::from_u128(1_510_451),
    );
    let token = core
        .reserve_native(old_request.clone(), config.publisher)
        .unwrap();

    let original_state = {
        let mut state = owner.mutation.lock().unwrap();
        std::mem::replace(
            &mut state.management,
            ManagementGrantState::new(config).unwrap(),
        )
    };
    // Both states have identical public terms; only the issuance instance
    // differs. The old snapshot remains valid solely for the original state.
    assert_eq!(
        original_state.check(&old_snapshot, token.binding(), 30),
        Ok(())
    );
    let fresh_snapshot = owner.snapshot();
    let fresh_request = owner.request(fresh_snapshot);
    assert_eq!(old_request.binding(), fresh_request.binding());
    assert_eq!(
        core.reserve_native(fresh_request.clone(), config.publisher)
            .err(),
        Some(DeliveryError::Conflict)
    );
    let terminal = core
        .execute_native_reserved::<Owner, _>(&token, config.publisher, |context| {
            context.owner().apply(
                context
                    .management_snapshot()
                    .expect("managed snapshot was not retained"),
                context.binding(),
            )
        })
        .unwrap();
    assert_eq!(terminal.state, DeliveryState::Terminal);
    assert_eq!(terminal.status, Some(DeliveryStatus::Revoked));
    {
        let state = owner.mutation.lock().unwrap();
        assert_eq!(state.last_error, Some(ManagementError::SnapshotMismatch));
        assert_eq!((state.revision, state.cap_ns, state.effects), (1, 5, 0));
    }
    assert_eq!(
        core.execute_native_reserved::<Owner, _>(&token, config.publisher, |_| {
            panic!("terminal authority refusal was executed again")
        })
        .unwrap(),
        terminal
    );
    match core
        .reserve_native_or_get(old_request, config.publisher)
        .unwrap()
    {
        ReserveAttempt::Existing(result) => assert_eq!(result, terminal),
        ReserveAttempt::Reserved(_) => panic!("old D acquired a second reservation"),
    }
    assert_eq!(
        core.reserve_native(fresh_request, config.publisher).err(),
        Some(DeliveryError::Conflict)
    );
    assert_eq!(owner.mutation.lock().unwrap().effects, 0);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn repeated_snapshots_of_one_state_keep_identity_and_native_retry_is_idempotent() {
    let config = config(1_510_500);
    let owner = Owner::new(config);
    let first = owner.snapshot();
    let second = owner.snapshot();
    assert_eq!(first, first.clone());
    assert_eq!(first, second);
    let first_request = owner.request(first);
    let retry = owner.request(second);
    let core = ControlCore::new(
        BootId::from_u128(1_510_550),
        CapSpaceId::from_u128(1_510_551),
    );
    let token = core
        .reserve_native(first_request, config.publisher)
        .unwrap();
    assert_eq!(
        core.reserve_native(retry.clone(), config.publisher).err(),
        Some(DeliveryError::Busy)
    );
    let terminal = core
        .execute_native_reserved::<Owner, _>(&token, config.publisher, |context| {
            context
                .owner()
                .apply(context.management_snapshot().unwrap(), context.binding())
        })
        .unwrap();
    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
    match core.reserve_native_or_get(retry, config.publisher).unwrap() {
        ReserveAttempt::Existing(result) => assert_eq!(result, terminal),
        ReserveAttempt::Reserved(_) => panic!("snapshot copy defeated native deduplication"),
    }
    let state = owner.mutation.lock().unwrap();
    assert_eq!((state.revision, state.cap_ns, state.effects), (2, 12, 1));
}
