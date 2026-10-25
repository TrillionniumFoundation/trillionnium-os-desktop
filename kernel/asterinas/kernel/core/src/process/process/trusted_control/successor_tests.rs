// SPDX-License-Identifier: MPL-2.0

//! Real original D namespaces with the production OSTD locking backend.
//! Reservations publish only a refused terminal; these tests claim no CPU
//! effect, durable writer or native FinalUse qualification.

use os_control::{
    DeliveryStatus, NativeGrant, NativeTarget, PublishOutcome, PublisherId, ResourceDomainId,
    StableObjectId,
};
use ostd::prelude::ktest;

use super::*;

fn histories() -> RetainedHistories {
    let owner = OwnerId::from_u128(44);
    let make = |space| {
        let (core, ack) = KernelCore::with_original_owner(
            BootId::from_u128(11),
            CapSpaceId::from_u128(space),
            owner,
        )
        .unwrap();
        Arc::new(HistorySlot {
            view: core.delivery_view_for(owner).unwrap(),
            core,
            ack: Some(ack),
        })
    };
    RetainedHistories {
        slots: [make(22), make(33)],
    }
}

fn reserve(history: &HistorySlot) -> os_control::ReserveTokenWith<KernelControlBackend> {
    // No resource operation occurs. A pinned inert owner supplies a stable
    // reservation identity for testing the real history state transitions.
    let target = NativeTarget::from_owner(
        Arc::new(()),
        ResourceDomainId::from_u128(55),
        StableObjectId::from_u128(66),
    )
    .unwrap();
    let publisher = PublisherId::from_u128(77);
    let grant = NativeGrant::from_owner(target, publisher, 1, Vec::new()).unwrap();
    history
        .core
        .reserve_native(
            NativeDeliveryRequest::from_wire(1, grant, 1, 1_001, 2, 1).unwrap(),
            publisher,
        )
        .unwrap()
}

fn refuse(history: &HistorySlot, token: &os_control::ReserveTokenWith<KernelControlBackend>) {
    history
        .core
        .publish(
            token,
            PublisherId::from_u128(77),
            PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            },
        )
        .unwrap();
}

fn retire(history: &HistorySlot) {
    let owner = history.ack.as_ref().unwrap();
    let ack = owner.history_ack(1, [9; 32]).unwrap();
    history
        .core
        .retire_through(&history.view, ack, owner)
        .unwrap();
}

#[ktest]
fn native_successor_requires_retirement_of_both_original_history_frontiers() {
    let retained = histories();
    assert!(retained.fully_retired());
    let manager = reserve(&retained.slots[0]);
    let recovery = reserve(&retained.slots[1]);
    assert!(!retained.fully_retired());
    refuse(&retained.slots[0], &manager);
    assert!(!retained.fully_retired());
    retire(&retained.slots[0]);
    assert!(!retained.fully_retired());
    refuse(&retained.slots[1], &recovery);
    assert!(!retained.fully_retired());
    retire(&retained.slots[1]);
    assert!(retained.fully_retired());
    for slot in &retained.slots {
        assert_eq!(slot.core.next_sequence(), 2);
        assert_eq!(slot.core.retired_through(), 1);
        assert_eq!(
            slot.core.query_delivery(&slot.view, 1).unwrap().state,
            DeliveryState::Retired
        );
    }
}

#[ktest]
fn native_successor_empty_lost_history_is_not_a_retirement_proof() {
    for lost in 0..2 {
        let retained = histories();
        retained.slots[lost].core.lose_history();
        assert_eq!(retained.slots[lost].core.next_sequence(), 1);
        assert_eq!(retained.slots[lost].core.retired_through(), 0);
        assert!(!retained.fully_retired());
    }
}

#[ktest]
fn native_history_only_image_retains_original_owners_without_effect_namespace() {
    let retained = histories();
    let (process, _task) = crate::process::test_util::new_unstarted_process();
    let key = process.hepta_image.lock().prepare_initial().unwrap();
    let slots = TrustedControlSlots::prepare_history_only(key, &retained);
    assert!(slots.manager.is_none());
    assert!(slots.core.is_none());
    assert!(Arc::ptr_eq(&slots.manager_history, &retained.slots[0]));
    assert!(Arc::ptr_eq(
        slots.recovery_history.as_ref().unwrap(),
        &retained.slots[1]
    ));
    assert_eq!(
        slots.retained_histories().unwrap().spaces(),
        retained.spaces()
    );
    assert!(!retained.spaces().contains(&hepta_image_space_id(key)));
    process
        .hepta_image
        .lock()
        .activate_initial_control(key, slots.clone())
        .unwrap();
    process.hepta_image.lock().consume_initial(key).unwrap();
    let mut request_id = [0u8; 16];
    request_id[..8].copy_from_slice(&1u64.to_le_bytes());
    let request = |opcode, target_slot, payload| wire::Request {
        opcode,
        request_id,
        target_slot,
        target_generation: 1,
        payload,
    };
    let read = request(wire::Opcode::ReadUsage, 1, wire::RequestPayload::ReadUsage);
    assert_eq!(
        process.dispatch_hepta_control(key, &read),
        Err(Status::PermissionDenied)
    );
    let install = request(
        wire::Opcode::InstallBudget,
        2,
        wire::RequestPayload::InstallBudget(wire::InstallBudgetRequest {
            expected_revision: 1,
            period_ns: 100_000_000,
            cap_ns: 1_001,
            reserved: 0,
        }),
    );
    assert_eq!(
        process.dispatch_hepta_control(key, &install),
        Err(Status::PermissionDenied)
    );
    assert_eq!(retained.slots[0].core.next_sequence(), 1);
    assert_eq!(retained.slots[1].core.next_sequence(), 1);
    let token = reserve(&retained.slots[0]);
    refuse(&retained.slots[0], &token);
    let payload = wire::DeliveryRequest {
        history_boot: BootId::from_u128(11).bytes(),
        history_space: retained.spaces()[0],
        sequence: 1,
    };
    let query = request(
        wire::Opcode::QueryDelivery,
        3,
        wire::RequestPayload::QueryDelivery(payload),
    );
    let (_, ResponsePayload::QueryDelivery(observed)) =
        process.dispatch_hepta_control(key, &query).unwrap()
    else {
        panic!("original history query changed its response type")
    };
    assert_eq!(observed.state, wire::DeliveryState::Terminal);
    assert_eq!(observed.saved_status, Status::Revoked);
    let mut wrong = payload;
    wrong.history_space = hepta_image_space_id(key);
    let wrong_query = request(
        wire::Opcode::QueryDelivery,
        3,
        wire::RequestPayload::QueryDelivery(wrong),
    );
    assert_eq!(
        process.dispatch_hepta_control(key, &wrong_query),
        Err(Status::PermissionDenied)
    );
    assert!(!retained.fully_retired());
    let retirement = request(
        wire::Opcode::RetireThrough,
        3,
        wire::RequestPayload::RetireThrough(payload),
    );
    let (_, ResponsePayload::RetireThrough(retired)) =
        process.dispatch_hepta_control(key, &retirement).unwrap()
    else {
        panic!("original retirement changed its response type")
    };
    assert_eq!((retired.retired_through, retired.next_sequence), (1, 2));
    process.begin_hepta_image_close();
    process.revoke_closing_hepta_control();
    process.close_hepta_image();
    assert_eq!(
        process
            .check_hepta_capspace_session(key)
            .unwrap_err()
            .error(),
        Errno::ESTALE
    );
    assert!(retained.fully_retired());
    // Closing the history image does not lose, reinitialize or mutate either D.
    assert_eq!(retained.slots[0].core.next_sequence(), 2);
    assert_eq!(retained.slots[1].core.next_sequence(), 1);
}
