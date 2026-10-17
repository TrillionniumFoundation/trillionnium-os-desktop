//! Resource lifetime and accounting regressions for the Rust host model.
//! These tests do not exercise kernel process teardown, IRQ locks or a
//! scheduler, and their owner receipts do not prove durable Hepta commits.

use os_control::{
    with_parent, BootId, CapSpaceId, ControlCore, DeliveryRequest, HistoryAck, OwnerId,
    OwnerReceipt, PublisherId, ResourceDomain, ResourceDomainId, ResourceError, StableObjectId,
    CPU_PERIOD_NS, MAX_RESOURCE_DEPTH,
};
use std::sync::{Arc, Barrier};
use std::thread;

fn root(id: u128, cap: u64) -> ResourceDomain {
    ResourceDomain::new(
        ResourceDomainId::from_u128(id),
        StableObjectId::from_u128(id),
        None,
        cap,
    )
    .unwrap()
}

fn child(parent: &ResourceDomain, id: u128, cap: u64) -> ResourceDomain {
    with_parent(
        ResourceDomainId::from_u128(id),
        StableObjectId::from_u128(id),
        parent,
        cap,
    )
    .unwrap()
}

fn reduce(parent: &ResourceDomain, expected_revision: u64, cap: u64, now: u64) {
    let grant = parent.grant(PublisherId::from_u128(800_000)).unwrap();
    parent
        .install_budget_for_host_model(&grant, expected_revision, CPU_PERIOD_NS, cap, now)
        .unwrap();
}

fn assert_child_constraint(parent: &ResourceDomain, cap: u64, now: u64) {
    let grant = parent.grant(PublisherId::from_u128(800_000)).unwrap();
    assert_eq!(
        parent.install_budget_for_host_model(&grant, 1, CPU_PERIOD_NS, cap, now),
        Err(ResourceError::ParentConstraint)
    );
    assert_eq!(parent.revision(), 1);
}

#[test]
fn ordinary_clone_drop_preserves_constraint_until_the_last_handle_drops() {
    let parent = root(801_000, 20);
    let leaf = child(&parent, 801_001, 10);
    let retained_clone = leaf.clone();
    drop(leaf);
    assert_child_constraint(&parent, 9, 10);
    assert_eq!(retained_clone.budget().cap_ns, 10);
    drop(retained_clone);
    reduce(&parent, 1, 9, 10);
    assert_eq!(parent.budget().cap_ns, 9);
}

#[test]
fn retained_grant_keeps_the_child_constraint_until_the_grant_drops() {
    let parent = root(802_000, 20);
    let leaf = child(&parent, 802_001, 10);
    let retained_grant = leaf.grant(PublisherId::from_u128(802_002)).unwrap();
    drop(leaf);
    assert_child_constraint(&parent, 9, 10);
    drop(retained_grant);
    reduce(&parent, 1, 9, 10);
}

#[test]
fn final_descendant_drop_releases_the_whole_unreferenced_parent_chain() {
    let parent = root(803_000, 20);
    let intermediate = child(&parent, 803_001, 10);
    let leaf = child(&intermediate, 803_002, 10);
    drop(intermediate);
    assert_child_constraint(&parent, 9, 10);
    drop(leaf);
    reduce(&parent, 1, 9, 10);
}

#[test]
fn terminal_history_retains_the_target_until_contiguous_retirement() {
    let parent = root(804_000, 20);
    let leaf = child(&parent, 804_001, 10);
    let who = PublisherId::from_u128(804_002);
    let owner = OwnerId::from_u128(804_003);
    let (core, authority) = ControlCore::with_original_owner(
        BootId::from_u128(804_004),
        CapSpaceId::from_u128(804_005),
        owner,
    )
    .unwrap();
    let view = core.delivery_view_for(owner).unwrap();
    let token = core
        .reserve(
            DeliveryRequest::new(1, leaf.grant(who).unwrap(), 1, 10),
            who,
        )
        .unwrap();
    core.commit(&token, who, 10).unwrap();
    drop(leaf);
    drop(token);
    assert_child_constraint(&parent, 9, 10);

    let ack = HistoryAck::from_owner_receipt(core.identity(), 1, OwnerReceipt::new(owner, [1; 32]))
        .unwrap();
    core.retire_through(&view, ack, &authority).unwrap();
    reduce(&parent, 1, 9, 10);
    assert_eq!(core.retired_through(), 1);
}

#[test]
fn a_retired_reservation_token_still_preserves_its_resource_memory_lifetime() {
    let parent = root(805_000, 20);
    let leaf = child(&parent, 805_001, 10);
    let who = PublisherId::from_u128(805_002);
    let owner = OwnerId::from_u128(805_003);
    let (core, authority) = ControlCore::with_original_owner(
        BootId::from_u128(805_004),
        CapSpaceId::from_u128(805_005),
        owner,
    )
    .unwrap();
    let view = core.delivery_view_for(owner).unwrap();
    let token = core
        .reserve(
            DeliveryRequest::new(1, leaf.grant(who).unwrap(), 1, 10),
            who,
        )
        .unwrap();
    core.commit(&token, who, 10).unwrap();
    drop(leaf);
    let ack = HistoryAck::from_owner_receipt(core.identity(), 1, OwnerReceipt::new(owner, [1; 32]))
        .unwrap();
    core.retire_through(&view, ack, &authority).unwrap();
    assert_child_constraint(&parent, 9, 10);
    drop(token);
    reduce(&parent, 1, 9, 10);
}

#[test]
fn child_destruction_does_not_refund_already_consumed_parent_cpu() {
    let parent = root(806_000, 20);
    let leaf = child(&parent, 806_001, 10);
    leaf.charge_interval_for_host_model(0, 7).unwrap();
    drop(leaf);
    let grant = parent.grant(PublisherId::from_u128(806_002)).unwrap();
    let receipt = parent
        .install_budget_for_host_model(&grant, 1, CPU_PERIOD_NS, 5, 7)
        .unwrap();
    assert_eq!(receipt.consumed_at_apply_ns, 7);
    let snapshot = parent.try_usage(7).unwrap();
    assert_eq!(snapshot.cumulative_cpu_ns, 7);
    assert_eq!(snapshot.window_consumed_ns, 7);
    assert_eq!(snapshot.active_cap_ns, 5);
    assert_eq!(snapshot.event_sequence, 1);
    assert_eq!(parent.charge_cpu(1, 8), Err(ResourceError::Exhausted));
    assert_eq!(parent.try_usage(7).unwrap(), snapshot);
}

#[test]
fn destroyed_child_releases_only_active_cap_metadata_not_identity_tombstones() {
    let parent = ResourceDomain::root_with_capacity_for_host_model(
        ResourceDomainId::from_u128(807_000),
        StableObjectId::from_u128(807_000),
        20,
        2,
    )
    .unwrap();
    let leaf = child(&parent, 807_001, 10);
    drop(leaf);
    reduce(&parent, 1, 9, 10);

    assert_eq!(
        with_parent(
            ResourceDomainId::from_u128(807_001),
            StableObjectId::from_u128(807_002),
            &parent,
            1,
        )
        .err(),
        Some(ResourceError::DuplicateDomainId)
    );
    assert_eq!(
        with_parent(
            ResourceDomainId::from_u128(807_002),
            StableObjectId::from_u128(807_001),
            &parent,
            1,
        )
        .err(),
        Some(ResourceError::DuplicateObjectId)
    );
    assert_eq!(
        with_parent(
            ResourceDomainId::from_u128(807_002),
            StableObjectId::from_u128(807_002),
            &parent,
            1,
        )
        .err(),
        Some(ResourceError::Exhausted)
    );
    assert_eq!(parent.budget().cap_ns, 9);
    assert_eq!(parent.revision(), 2);
}

#[test]
fn last_child_drop_and_parent_reduction_have_one_legal_serial_order() {
    for n in 0..64_u128 {
        let parent = root(808_000 + n * 10, 20);
        let leaf = child(&parent, 808_001 + n * 10, 10);
        let start = Arc::new(Barrier::new(2));
        let drop_start = Arc::clone(&start);
        let dropper = thread::spawn(move || {
            drop_start.wait();
            drop(leaf);
        });
        let grant = parent.grant(PublisherId::from_u128(808_002)).unwrap();
        start.wait();
        let raced = parent.install_budget_for_host_model(&grant, 1, CPU_PERIOD_NS, 9, 10);
        dropper.join().unwrap();
        match raced {
            Ok(receipt) => assert_eq!(receipt.revision, 2),
            Err(ResourceError::ParentConstraint) => reduce(&parent, 1, 9, 10),
            other => panic!("unexpected destruction/CAS order: {other:?}"),
        }
        assert_eq!(parent.budget().cap_ns, 9);
        assert_eq!(parent.revision(), 2);
    }
}

#[test]
fn depth_limit_rejection_preserves_child_metadata_and_identity_capacity() {
    let parent = root(809_000, 20);
    let mut leaf = parent.clone();
    for level in 2..=MAX_RESOURCE_DEPTH {
        leaf = child(&leaf, 809_000 + level as u128, 10);
    }
    let rejected_id = 809_000 + MAX_RESOURCE_DEPTH as u128 + 1;
    assert_eq!(
        with_parent(
            ResourceDomainId::from_u128(rejected_id),
            StableObjectId::from_u128(rejected_id),
            &leaf,
            1,
        )
        .err(),
        Some(ResourceError::Exhausted)
    );
    // Rejection did not create a hidden child-cap constraint on the leaf.
    reduce(&leaf, 1, 0, 0);
    assert_eq!(leaf.budget().cap_ns, 0);
    // Neither ID was consumed: the same pair remains usable at legal depth.
    let replacement = child(&parent, rejected_id, 1);
    assert_eq!(replacement.parent_id(), Some(parent.id()));
    assert_eq!(replacement.budget().cap_ns, 1);
    assert_eq!(parent.try_usage(0).unwrap().cumulative_cpu_ns, 0);
}

#[test]
fn maximum_depth_parent_chain_drops_on_a_bounded_host_thread_stack() {
    // This is a host stack regression, not a claim about an Asterinas
    // kernel stack or its native object destruction machinery.
    thread::Builder::new()
        .stack_size(64 * 1024)
        .spawn(|| {
            let mut leaf = root(810_000, 10);
            for level in 2..=MAX_RESOURCE_DEPTH {
                leaf = child(&leaf, 810_000 + level as u128, 10);
            }
            drop(leaf);
        })
        .unwrap()
        .join()
        .unwrap();
}
