//! Independent host regression for the saved-terminal status boundary.
//! A05 must reject public observations that claim a namespace admission
//! decision was an executed delivery's terminal result. No wire layout,
//! numeric status or real kernel effect is changed by these tests.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryRequest, DeliveryState, DeliveryStatus,
    OwnerId, PublishOutcome, PublisherId, ResourceDomain, ResourceDomainId, StableObjectId,
    CPU_PERIOD_NS,
};

fn reject_impossible_terminal_status(status: DeliveryStatus) {
    let core = ControlCore::new(BootId::from_u128(1), CapSpaceId::from_u128(2));
    let target = ResourceDomain::new(
        ResourceDomainId::from_u128(3),
        StableObjectId::from_u128(4),
        None,
        CPU_PERIOD_NS,
    )
    .unwrap();
    let publisher = PublisherId::from_u128(5);
    let token = core
        .reserve(
            DeliveryRequest::from_wire(1, target.grant(publisher).unwrap(), 1, 17, 11, 5).unwrap(),
            publisher,
        )
        .unwrap();
    // The canonical publisher already refuses these pre-reservation statuses.
    assert_eq!(
        core.publish(&token, publisher, PublishOutcome::Failure { status }),
        Err(DeliveryError::InvalidPublish)
    );
    let mut forged = core.query_delivery(&core.delivery_view(), 1).unwrap();
    assert_eq!(forged.state, DeliveryState::Reserved);
    assert_eq!(forged.hos2_saved_status_code(), Some(0));
    // Public fields may be changed by an adapter. The fallible observation
    // boundary must enforce the same semantic restriction as publication.
    forged.state = DeliveryState::Terminal;
    forged.status = Some(status);
    assert_eq!(forged.hos2_saved_status_code(), None);
}

#[test]
fn out_of_order_is_not_a_serializable_saved_terminal_result() {
    reject_impossible_terminal_status(DeliveryStatus::OutOfOrder);
}

#[test]
fn retired_is_not_a_serializable_saved_terminal_result() {
    reject_impossible_terminal_status(DeliveryStatus::Retired);
}

#[test]
fn actual_retirement_and_legal_terminal_refusals_keep_existing_wire_statuses() {
    let owner = OwnerId::from_u128(9);
    let (core, authority) =
        ControlCore::with_original_owner(BootId::from_u128(1), CapSpaceId::from_u128(2), owner)
            .unwrap();
    let target = ResourceDomain::new(
        ResourceDomainId::from_u128(3),
        StableObjectId::from_u128(4),
        None,
        CPU_PERIOD_NS,
    )
    .unwrap();
    let publisher = PublisherId::from_u128(5);
    let token = core
        .reserve(
            DeliveryRequest::from_wire(1, target.grant(publisher).unwrap(), 1, 17, 11, 5).unwrap(),
            publisher,
        )
        .unwrap();
    let terminal = core
        .publish(
            &token,
            publisher,
            PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            },
        )
        .unwrap();
    assert_eq!(terminal.hos2_saved_status_code(), Some(4));
    let view = core.delivery_view_for(owner).unwrap();
    let ack = authority.history_ack(1, [1; 32]).unwrap();
    core.retire_through(&view, ack, &authority).unwrap();
    let retired = core.query_delivery(&view, 1).unwrap();
    assert_eq!(retired.state, DeliveryState::Retired);
    assert_eq!(retired.hos2_saved_status_code(), Some(0));
    assert_eq!(DeliveryStatus::OutOfOrder.hos2_code(), 10);
    assert_eq!(DeliveryStatus::Retired.hos2_code(), 11);
    assert_eq!(DeliveryState::Retired.hos2_code(), 2);
    core.validate_invariants_for_host_model().unwrap();
}
