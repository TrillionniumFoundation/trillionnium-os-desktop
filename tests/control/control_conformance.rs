//! Host-model conformance and adversarial tests for A03.
//!
//! These tests exercise the Rust state core only.  They do not exercise a
//! kernel, HOS2 copyin/copyout, credentials, scheduler accounting, fsync, or
//! crash recovery.

use os_control::{
    with_parent, BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryRequest, DeliveryState,
    DeliveryStatus, HistoryAck, Id16, LogicalOperationId, OperationBinding, OwnerId, OwnerReceipt,
    PublishOutcome, PublisherId, ReserveAttempt, ResourceDomain, ResourceDomainId, ResourceError,
    StableObjectId, CPU_PERIOD_NS,
};
use std::sync::{Arc, Barrier};
use std::thread;

fn boot(n: u128) -> BootId {
    BootId::from_u128(n)
}

fn space(n: u128) -> CapSpaceId {
    CapSpaceId::from_u128(n)
}

fn domain(n: u128) -> ResourceDomainId {
    ResourceDomainId::from_u128(n)
}

fn object(n: u128) -> StableObjectId {
    StableObjectId::from_u128(n)
}

fn publisher(n: u128) -> PublisherId {
    PublisherId::from_u128(n)
}

fn owner(n: u128) -> OwnerId {
    OwnerId::from_u128(n)
}

fn ack(core: &ControlCore, through: u64) -> HistoryAck {
    HistoryAck::from_owner_receipt(
        core.identity(),
        through,
        OwnerReceipt::new(owner(9000), [0xA5; 32]),
    )
    .unwrap()
}

fn root(n: u128, cap: u64) -> ResourceDomain {
    ResourceDomain::new(domain(n), object(n), None, cap).unwrap()
}

fn request(
    sequence: u64,
    grant: os_control::Grant,
    expected_revision: u64,
    cap: u64,
) -> DeliveryRequest {
    DeliveryRequest::new(sequence, grant, expected_revision, cap)
}

#[test]
fn same_d_target_cap_revision_and_cross_target_are_conflicts() {
    let core = ControlCore::new(boot(1), space(1));
    let first = root(1, CPU_PERIOD_NS);
    let second = root(2, CPU_PERIOD_NS);
    let owner_a = publisher(10);
    let grant_a = first.grant(owner_a).unwrap();
    let grant_b = second.grant(owner_a).unwrap();
    let token = core
        .reserve(request(1, grant_a.clone(), 1, 10), owner_a)
        .unwrap();

    // The first reservation is still pending, so an identical D is busy.
    assert!(matches!(
        core.reserve(request(1, grant_a.clone(), 1, 10), owner_a),
        Err(DeliveryError::Busy)
    ));
    // Every canonical request field is bound, including cap and expected revision.
    assert!(matches!(
        core.reserve(request(1, grant_a.clone(), 1, 11), owner_a),
        Err(DeliveryError::Conflict)
    ));
    assert!(matches!(
        core.reserve(request(1, grant_a.clone(), 2, 10), owner_a),
        Err(DeliveryError::Conflict)
    ));
    // The global sequence table catches a target change before either target lock.
    assert!(matches!(
        core.reserve(request(1, grant_b, 1, 10), owner_a),
        Err(DeliveryError::Conflict)
    ));
    assert_eq!(
        core.commit(&token, owner_a, 7).unwrap().status,
        Some(DeliveryStatus::Ok)
    );
    assert!(matches!(
        core.reserve(request(1, grant_a, 1, 10), owner_a),
        Err(DeliveryError::TerminalImmutable)
    ));
}

#[test]
fn request_digest_and_publisher_identity_are_bound() {
    let core = ControlCore::new(boot(12), space(12));
    let target = root(12, CPU_PERIOD_NS);
    let good = publisher(120);
    let bad = publisher(121);
    let grant = target.grant(good).unwrap();
    let first = request(1, grant.clone(), 1, 10).with_payload_digest([1; 32]);
    core.reserve(first, good).unwrap();
    let changed = request(1, grant.clone(), 1, 10).with_payload_digest([2; 32]);
    assert!(matches!(
        core.reserve(changed, good),
        Err(DeliveryError::Conflict)
    ));
    assert!(matches!(
        core.reserve(request(2, grant, 1, 10), bad),
        Err(DeliveryError::PermissionDenied)
    ));
    assert!(matches!(
        core.reserve(request(2, target.grant(good).unwrap(), 1, 10), bad),
        Err(DeliveryError::PermissionDenied)
    ));
}

#[test]
fn logical_k_is_value_only_and_never_replaces_boot_local_d() {
    let core = ControlCore::new(boot(16), space(16));
    let k = LogicalOperationId::new(Id16::from_u128(1), Id16::from_u128(2)).unwrap();
    let d = os_control::DeliveryId::new(core.identity(), 1).unwrap();
    let binding = OperationBinding::new(k, d);
    assert_eq!(binding.logical, k);
    assert_eq!(binding.delivery, d);

    let other_boot = ControlCore::new(boot(17), space(16));
    let other_d = os_control::DeliveryId::new(other_boot.identity(), 1).unwrap();
    assert_ne!(binding.delivery, other_d);
    assert_eq!(core.next_sequence(), 1);
}

#[test]
fn control_states_map_to_hos2_codes_without_importing_the_wire_crate() {
    assert_eq!(DeliveryStatus::Ok.hos2_code(), 0);
    assert_eq!(DeliveryStatus::ParentLimit.hos2_code(), 5);
    assert_eq!(DeliveryStatus::Retired.hos2_code(), 11);
    assert_eq!(DeliveryState::Reserved.hos2_code(), 0);
    assert_eq!(DeliveryState::Terminal.hos2_code(), 1);
    assert_eq!(DeliveryState::HistoryLost.hos2_code(), 4);

    let core = ControlCore::new(boot(18), space(18));
    let pending = core.query_delivery(&core.delivery_view(), 1).unwrap();
    assert_eq!(pending.hos2_saved_status_code(), 0);
}

#[test]
fn out_of_order_does_not_consume_sequence_and_wrong_history_owner_cannot_retire() {
    let (core, owner_authority) =
        ControlCore::with_original_owner(boot(13), space(13), owner(1300)).unwrap();
    let target = root(13, CPU_PERIOD_NS);
    let who = publisher(130);
    assert!(matches!(
        core.reserve(request(2, target.grant(who).unwrap(), 1, 10), who),
        Err(DeliveryError::OutOfOrder {
            expected: 1,
            got: 2
        })
    ));
    assert_eq!(core.next_sequence(), 1);
    let token = core
        .reserve(request(1, target.grant(who).unwrap(), 1, 10), who)
        .unwrap();
    core.commit(&token, who, 1).unwrap();
    let view = core.delivery_view_for(owner(1300)).unwrap();
    let wrong_ack =
        HistoryAck::from_owner_receipt(core.identity(), 1, OwnerReceipt::new(owner(1301), [3; 32]))
            .unwrap();
    assert_eq!(
        core.retire_through(&view, wrong_ack, &owner_authority),
        Err(DeliveryError::PermissionDenied)
    );
}

#[test]
fn wrong_publisher_cannot_publish_and_terminal_rejection_is_immutable() {
    let core = ControlCore::new(boot(2), space(2));
    let target = root(2, CPU_PERIOD_NS);
    let good = publisher(21);
    let bad = publisher(22);
    let grant = target.grant(good).unwrap();
    let token = core.reserve(request(1, grant, 1, 20), good).unwrap();
    let rejected = PublishOutcome::Failure {
        status: DeliveryStatus::PermissionDenied,
    };
    assert_eq!(
        core.publish(&token, bad, rejected),
        Err(DeliveryError::PermissionDenied)
    );
    let view = core.delivery_view();
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Reserved
    );
    let terminal = core.publish(&token, good, rejected).unwrap();
    assert_eq!(terminal.status, Some(DeliveryStatus::PermissionDenied));
    // A terminal refusal cannot later be changed to success.
    let success = PublishOutcome::Success {
        stable_object_id: target.stable_object_id(),
        previous_revision: 1,
        saved_revision: 2,
        effective_ns: 8,
        consumed_ns: 0,
    };
    assert_eq!(core.publish(&token, good, success).unwrap(), terminal);
}

#[test]
fn copyout_failure_retry_reuses_terminal_result_without_second_effect() {
    let core = ControlCore::new(boot(14), space(14));
    let target = root(14, CPU_PERIOD_NS);
    let who = publisher(140);
    let token = core
        .reserve(request(1, target.grant(who).unwrap(), 1, 20), who)
        .unwrap();
    let first = core.commit(&token, who, 1).unwrap();
    let revision = target.revision();
    // The caller treats its copyout as EFAULT; the effect remains terminal.
    match core.reserve_or_get(request(1, target.grant(who).unwrap(), 1, 20), who) {
        Ok(ReserveAttempt::Existing(observed)) => assert_eq!(observed, first),
        _ => panic!("same D retry must return the immutable terminal result"),
    }
    assert_eq!(target.revision(), revision);
}

#[test]
fn invalid_history_sequence_is_rejected_before_and_after_history_loss() {
    let core = ControlCore::new(boot(90_000), space(90_000));
    let view = core.delivery_view();
    for invalid in [0, u64::MAX] {
        assert_eq!(
            core.query_delivery(&view, invalid),
            Err(DeliveryError::InvalidSequence)
        );
    }
    core.lose_history();
    for invalid in [0, u64::MAX] {
        assert_eq!(
            core.query_delivery(&view, invalid),
            Err(DeliveryError::InvalidSequence)
        );
    }
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::HistoryLost
    );
}

#[test]
fn history_loss_fences_old_reserved_token() {
    let core = ControlCore::new(boot(15), space(15));
    let target = root(15, CPU_PERIOD_NS);
    let who = publisher(150);
    let token = core
        .reserve(request(1, target.grant(who).unwrap(), 1, 20), who)
        .unwrap();
    core.lose_history();
    assert_eq!(core.commit(&token, who, 1), Err(DeliveryError::HistoryLost));
    assert_eq!(target.revision(), 1);
}

#[test]
fn revoke_before_commit_rejects_and_commit_before_revoke_stays_admitted() {
    let core = ControlCore::new(boot(3), space(3));
    let first = root(3, CPU_PERIOD_NS);
    let who = publisher(30);
    let grant = first.grant(who).unwrap();
    let token = core.reserve(request(1, grant, 1, 30), who).unwrap();
    first.revoke();
    let denied = core.commit(&token, who, 1).unwrap();
    assert_eq!(denied.status, Some(DeliveryStatus::Revoked));
    assert_eq!(first.revision(), 1);

    let second = root(4, CPU_PERIOD_NS);
    let grant2 = second.grant(who).unwrap();
    let token2 = core.reserve(request(2, grant2, 1, 31), who).unwrap();
    let applied = core.commit(&token2, who, 2).unwrap();
    assert_eq!(applied.status, Some(DeliveryStatus::Ok));
    second.revoke();
    assert_eq!(second.revision(), 2);
}

#[test]
fn same_cap_update_preserves_consumption_and_cap_zero_is_not_pause() {
    let target = root(5, CPU_PERIOD_NS);
    target.charge_cpu(17, 17).unwrap();
    let who = publisher(50);
    let grant = target.grant(who).unwrap();
    let receipt = target
        .install_budget_for_host_model(&grant, 1, CPU_PERIOD_NS, CPU_PERIOD_NS, 20)
        .unwrap();
    assert_eq!(receipt.consumed_at_apply_ns, 17);
    assert_eq!(target.usage(21).cumulative_cpu_ns, 17);
    assert!(!target.user_paused());
    target.set_user_paused(true);
    assert!(target.user_paused());
    let zero = target
        .install_budget_for_host_model(&target.grant(who).unwrap(), 2, CPU_PERIOD_NS, 0, 22)
        .unwrap();
    assert_eq!(zero.consumed_at_apply_ns, 17);
    assert!(target.usage(23).active_cap_ns == 0);
    assert!(target.user_paused());
}

#[test]
fn cpu_usage_rolls_to_a_new_fixed_period_without_resetting_cumulative_usage() {
    let target = root(501, 40);
    target.charge_cpu(30, 10).unwrap();
    let first = target.usage(50);
    assert_eq!(first.window_start_ns, 0);
    assert_eq!(first.window_consumed_ns, 30);
    assert_eq!(first.cumulative_cpu_ns, 30);

    let next = target.usage(CPU_PERIOD_NS);
    assert_eq!(next.window_start_ns, CPU_PERIOD_NS);
    assert_eq!(next.window_consumed_ns, 0);
    assert_eq!(next.cumulative_cpu_ns, 30);
    target.charge_cpu(5, CPU_PERIOD_NS + 1).unwrap();
    let after = target.usage(CPU_PERIOD_NS + 2);
    assert_eq!(after.window_consumed_ns, 5);
    assert_eq!(after.cumulative_cpu_ns, 35);
}

#[test]
fn revoked_ancestor_fences_child_grants_and_pending_commit() {
    let parent = root(75_000, 80);
    let child = with_parent(domain(75_001), object(75_001), &parent, 60).unwrap();
    let who = publisher(75_002);
    let old_grant = child.grant(who).unwrap();
    let core = ControlCore::new(boot(75_000), space(75_000));
    let token = core.reserve(request(1, old_grant.clone(), 1, 55), who).unwrap();
    parent.revoke();
    assert!(matches!(child.grant(who), Err(ResourceError::Revoked)));
    let denied = core.commit(&token, who, 10).unwrap();
    assert_eq!(denied.status, Some(DeliveryStatus::Revoked));
    assert_eq!(child.revision(), 1);
    assert_eq!(parent.revision(), 1);
    assert_eq!(
        child.install_budget_for_host_model(&old_grant, 1, CPU_PERIOD_NS, 50, 11),
        Err(ResourceError::Revoked)
    );
    match core.reserve_or_get(request(1, old_grant, 1, 55), who) {
        Ok(ReserveAttempt::Existing(observed)) => assert_eq!(observed, denied),
        _ => panic!("same D terminal rejection must be retrievable"),
    }
}

#[test]
fn child_commit_admitted_before_ancestor_revoke_is_immutable() {
    let grandparent = root(76_000, 80);
    let parent = with_parent(domain(76_001), object(76_001), &grandparent, 70).unwrap();
    let child = with_parent(domain(76_002), object(76_002), &parent, 60).unwrap();
    let who = publisher(76_003);
    let grant = child.grant(who).unwrap();
    let core = ControlCore::new(boot(76_000), space(76_000));
    let token = core.reserve(request(1, grant.clone(), 1, 50), who).unwrap();
    let admitted = core.commit(&token, who, 1).unwrap();
    assert_eq!(admitted.status, Some(DeliveryStatus::Ok));
    grandparent.revoke();
    assert!(matches!(child.grant(who), Err(ResourceError::Revoked)));
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap(),
        admitted
    );
    assert_eq!(child.revision(), 2);
}

#[test]
fn parent_domain_caps_child_budget() {
    let parent = root(6, 40);
    let child = with_parent(domain(7), object(7), &parent, 20).unwrap();
    let who = publisher(60);
    let grant = child.grant(who).unwrap();
    assert_eq!(
        child.install_budget_for_host_model(&grant, 1, CPU_PERIOD_NS, 41, 1),
        Err(ResourceError::ParentConstraint)
    );
    // The direct resource API reports the actual parent constraint.
    assert!(child
        .install_budget_for_host_model(&grant, 1, CPU_PERIOD_NS, 40, 2)
        .is_ok());
}

#[test]
fn duplicate_sibling_id_cannot_hide_a_larger_child_budget() {
    let parent = root(910, 90);
    let first = with_parent(domain(911), object(911), &parent, 80).unwrap();
    assert_eq!(
        with_parent(domain(911), object(912), &parent, 10).err(),
        Some(ResourceError::DuplicateDomainId)
    );
    assert_eq!(
        with_parent(domain(910), object(913), &parent, 10).err(),
        Some(ResourceError::DuplicateDomainId)
    );
    let grant = parent.grant(publisher(910)).unwrap();
    assert_eq!(
        parent.install_budget_for_host_model(&grant, 1, CPU_PERIOD_NS, 10, 1),
        Err(ResourceError::ParentConstraint)
    );
    assert_eq!(first.budget().cap_ns, 80);
    assert_eq!(parent.budget().cap_ns, 90);
}

#[test]
fn child_registration_and_parent_cap_update_cannot_cross() {
    for i in 0..128_u128 {
        let parent = root(920 + i, 90);
        let child_parent = parent.clone();
        let reduce_parent = parent.clone();
        let who = publisher(920 + i);
        let barrier = Arc::new(Barrier::new(3));
        let create_barrier = Arc::clone(&barrier);
        let shrink_barrier = Arc::clone(&barrier);
        let create = thread::spawn(move || {
            create_barrier.wait();
            with_parent(domain(1100 + i), object(1100 + i), &child_parent, 80)
        });
        let shrink = thread::spawn(move || {
            let grant = reduce_parent.grant(who).unwrap();
            shrink_barrier.wait();
            reduce_parent.install_budget_for_host_model(&grant, 1, CPU_PERIOD_NS, 10, 1)
        });
        barrier.wait();
        let child = create.join().unwrap();
        let reduced = shrink.join().unwrap();
        match (child, reduced) {
            (Ok(child), Err(ResourceError::ParentConstraint)) => {
                assert_eq!(child.budget().cap_ns, 80);
                assert_eq!(parent.budget().cap_ns, 90);
            }
            (Err(ResourceError::ParentConstraint), Ok(receipt)) => {
                assert_eq!(receipt.revision, 2);
                assert_eq!(parent.budget().cap_ns, 10);
            }
            _ => panic!("parent cap and child registration must linearize"),
        }
    }
}

#[test]
fn budget_update_at_period_boundary_reports_current_window_consumption() {
    let target = root(909, 90);
    target.charge_cpu(60, 10).unwrap();
    let who = publisher(909);
    let grant = target.grant(who).unwrap();
    let applied = target
        .install_budget_for_host_model(&grant, 1, CPU_PERIOD_NS, 90, CPU_PERIOD_NS + 7)
        .unwrap();
    assert_eq!(applied.consumed_at_apply_ns, 0);
    assert_eq!(target.usage(CPU_PERIOD_NS + 8).window_consumed_ns, 0);
    assert_eq!(target.usage(CPU_PERIOD_NS + 8).cumulative_cpu_ns, 60);
    target.charge_cpu(25, CPU_PERIOD_NS + 9).unwrap();
    let same_cap = target
        .install_budget_for_host_model(&target.grant(who).unwrap(), 2, CPU_PERIOD_NS, 90, CPU_PERIOD_NS + 10)
        .unwrap();
    assert_eq!(same_cap.consumed_at_apply_ns, 25);
    assert_eq!(target.usage(CPU_PERIOD_NS + 11).window_consumed_ns, 25);
}

#[test]
fn child_cpu_charge_is_counted_once_in_each_ancestor_and_parent_exhaustion_is_atomic() {
    let parent = root(601, 10);
    let child = with_parent(domain(602), object(602), &parent, 10).unwrap();
    child.charge_cpu(7, 1).unwrap();
    assert_eq!(child.usage(1).window_consumed_ns, 7);
    assert_eq!(parent.usage(1).window_consumed_ns, 7);
    assert_eq!(child.usage(1).cumulative_cpu_ns, 7);
    assert_eq!(parent.usage(1).cumulative_cpu_ns, 7);

    // The parent has only 3ns left in this fixed window.  A rejected child
    // charge must not increment either domain or leave a half-applied charge.
    assert_eq!(child.charge_cpu(4, 2), Err(ResourceError::Exhausted));
    assert_eq!(child.usage(2).window_consumed_ns, 7);
    assert_eq!(parent.usage(2).window_consumed_ns, 7);
}

#[test]
fn hanging_prefix_blocks_retire_but_read_and_full_window_recovery_remain_available() {
    let (core, owner_authority) =
        ControlCore::with_capacity_for_owner(boot(7), space(7), 4, owner(9000)).unwrap();
    let target = root(8, CPU_PERIOD_NS);
    let who = publisher(70);
    let view = core.delivery_view_for(owner(9000)).unwrap();
    let mut first = None;
    for sequence in 1..=4 {
        let grant = target.grant(who).unwrap();
        let token = core
            .reserve(request(sequence, grant, target.revision(), 20), who)
            .unwrap();
        if sequence == 1 {
            first = Some(token);
        } else {
            core.publish(
                &token,
                who,
                PublishOutcome::Failure {
                    status: DeliveryStatus::InvalidInput,
                },
            )
            .unwrap();
        }
    }
    assert!(matches!(
        core.reserve(
            request(5, target.grant(who).unwrap(), target.revision(), 20),
            who
        ),
        Err(DeliveryError::ResourceExhausted)
    ));
    assert_eq!(core.window_len(), 4);
    assert_eq!(
        core.query_delivery(&view, 2).unwrap().state,
        DeliveryState::Terminal
    );
    assert_eq!(
        core.retire_through(&view, ack(&core, 4), &owner_authority),
        Err(DeliveryError::PendingPrefix)
    );
    first.as_ref().map(|token| {
        core.publish(
            token,
            who,
            PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            },
        )
        .unwrap()
    });
    let retired = core.retire_through(&view, ack(&core, 4), &owner_authority).unwrap();
    assert_eq!(retired.retired_through, 4);
    let token5 = core
        .reserve(
            request(5, target.grant(who).unwrap(), target.revision(), 20),
            who,
        )
        .unwrap();
    assert_eq!(
        core.commit(&token5, who, 5).unwrap().status,
        Some(DeliveryStatus::Ok)
    );
}

#[test]
fn ten_thousand_writes_are_bounded_and_old_sequences_do_not_reappear() {
    let (core, owner_authority) =
        ControlCore::with_capacity_for_owner(boot(8), space(8), 32, owner(9000)).unwrap();
    let target = root(9, CPU_PERIOD_NS);
    let who = publisher(80);
    let view = core.delivery_view_for(owner(9000)).unwrap();
    for sequence in 1..=10_000_u64 {
        let grant = target.grant(who).unwrap();
        let token = core
            .reserve(request(sequence, grant, target.revision(), 30), who)
            .unwrap();
        assert_eq!(
            core.commit(&token, who, sequence).unwrap().status,
            Some(DeliveryStatus::Ok)
        );
        core.retire_through(&view, ack(&core, sequence), &owner_authority)
            .unwrap();
    }
    assert_eq!(core.retired_through(), 10_000);
    assert_eq!(core.window_len(), 0);
    assert_eq!(
        core.query_delivery(&view, 10_000).unwrap().state,
        DeliveryState::Retired
    );
    let late = request(10_000, target.grant(who).unwrap(), target.revision(), 30);
    assert!(matches!(
        core.reserve(late, who),
        Err(DeliveryError::Retired)
    ));
}

#[test]
fn boot_and_capspace_identity_isolation_and_history_loss_are_explicit() {
    let first = ControlCore::new(boot(9), space(9));
    let second = ControlCore::new(boot(10), space(10));
    let target = root(10, CPU_PERIOD_NS);
    let who = publisher(90);
    let token = first
        .reserve(request(1, target.grant(who).unwrap(), 1, 10), who)
        .unwrap();
    first.commit(&token, who, 1).unwrap();
    let second_view = second.delivery_view();
    assert_eq!(
        second.query_delivery(&second_view, 1).unwrap().state,
        DeliveryState::NotSeen
    );
    assert_eq!(
        first.query_delivery(&second_view, 1),
        Err(DeliveryError::PermissionDenied)
    );
    let first_view = first.delivery_view();
    first.lose_history();
    assert_eq!(
        first.query_delivery(&first_view, 1).unwrap().state,
        DeliveryState::HistoryLost
    );
    assert!(matches!(
        first.reserve(request(2, target.grant(who).unwrap(), 1, 10), who),
        Err(DeliveryError::HistoryLost)
    ));
}

#[test]
fn concurrent_same_d_has_one_effect_and_query_never_sees_partial_terminal() {
    let core = Arc::new(ControlCore::new(boot(11), space(11)));
    let target = Arc::new(root(11, CPU_PERIOD_NS));
    let who = publisher(110);
    let grant = target.grant(who).unwrap();
    let request = request(1, grant, 1, 30);
    let barrier = Arc::new(Barrier::new(33));
    let mut handles = Vec::new();
    for _ in 0..32 {
        let core = Arc::clone(&core);
        let barrier = Arc::clone(&barrier);
        let request = request.clone();
        handles.push(thread::spawn(move || {
            barrier.wait();
            match core.reserve(request, who) {
                Ok(token) => Some(core.commit(&token, who, 1).unwrap()),
                Err(DeliveryError::Busy | DeliveryError::TerminalImmutable) => None,
                _ => panic!("unexpected same-D result"),
            }
        }));
    }
    barrier.wait();
    let mut committed = 0;
    for handle in handles {
        if handle.join().unwrap().is_some() {
            committed += 1;
        }
    }
    assert_eq!(committed, 1);
    assert_eq!(target.revision(), 2);
    let view = core.delivery_view();
    let final_state = core.query_delivery(&view, 1).unwrap();
    assert_eq!(final_state.state, DeliveryState::Terminal);
    assert_eq!(final_state.status, Some(DeliveryStatus::Ok));
}

#[test]
fn concurrent_revoke_and_commit_linearizes_to_one_terminal_result() {
    for iteration in 0..100_u128 {
        let core = Arc::new(ControlCore::new(
            boot(100 + iteration),
            space(100 + iteration),
        ));
        let target = Arc::new(root(100 + iteration, CPU_PERIOD_NS));
        let who = publisher(200 + iteration);
        let token = core
            .reserve(request(1, target.grant(who).unwrap(), 1, 30), who)
            .unwrap();
        let barrier = Arc::new(Barrier::new(2));
        let commit_core = Arc::clone(&core);
        let commit_barrier = Arc::clone(&barrier);
        let commit_handle = thread::spawn(move || {
            commit_barrier.wait();
            commit_core.commit(&token, who, 1).unwrap()
        });
        let revoke_target = Arc::clone(&target);
        let revoke_barrier = Arc::clone(&barrier);
        let revoke_handle = thread::spawn(move || {
            revoke_barrier.wait();
            revoke_target.revoke()
        });
        let outcome = commit_handle.join().unwrap();
        revoke_handle.join().unwrap();
        assert_eq!(outcome.state, DeliveryState::Terminal);
        assert!(matches!(
            outcome.status,
            Some(DeliveryStatus::Ok | DeliveryStatus::Revoked)
        ));
        assert!(target.revision() == 1 || target.revision() == 2);
    }
}

#[test]
fn concurrent_query_publish_and_retire_observe_whole_states() {
    let (control, owner_authority) =
        ControlCore::with_original_owner(boot(500), space(500), owner(9000)).unwrap();
    let core = Arc::new(control);
    let target = root(500, CPU_PERIOD_NS);
    let who = publisher(501);
    let token = core
        .reserve(request(1, target.grant(who).unwrap(), 1, 30), who)
        .unwrap();
    let view = core.delivery_view_for(owner(9000)).unwrap();
    let barrier = Arc::new(Barrier::new(2));
    let query_core = Arc::clone(&core);
    let query_view = view.clone();
    let query_barrier = Arc::clone(&barrier);
    let query = thread::spawn(move || {
        query_barrier.wait();
        let mut saw_reserved = false;
        for _ in 0..1000 {
            let observation = query_core.query_delivery(&query_view, 1).unwrap();
            assert!(matches!(
                observation.state,
                DeliveryState::Reserved | DeliveryState::Terminal
            ));
            if observation.state == DeliveryState::Reserved {
                saw_reserved = true;
            }
            if observation.state == DeliveryState::Terminal {
                break;
            }
        }
        saw_reserved
    });
    let publish_core = Arc::clone(&core);
    let publish_barrier = Arc::clone(&barrier);
    let publish = thread::spawn(move || {
        publish_barrier.wait();
        publish_core.commit(&token, who, 1).unwrap()
    });
    let published = publish.join().unwrap();
    query.join().unwrap();
    assert_eq!(published.status, Some(DeliveryStatus::Ok));
    let retired = core.retire_through(&view, ack(&core, 1), &owner_authority).unwrap();
    assert_eq!(retired.retired_through, 1);
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Retired
    );
}

#[test]
fn query_and_retire_race_has_only_terminal_or_retired_observations() {
    let (control, owner_authority) =
        ControlCore::with_original_owner(boot(600), space(600), owner(9000)).unwrap();
    let core = Arc::new(control);
    let target = root(600, CPU_PERIOD_NS);
    let who = publisher(601);
    let token = core
        .reserve(request(1, target.grant(who).unwrap(), 1, 30), who)
        .unwrap();
    core.commit(&token, who, 1).unwrap();
    let view = core.delivery_view_for(owner(9000)).unwrap();
    let barrier = Arc::new(Barrier::new(2));
    let query_core = Arc::clone(&core);
    let query_view = view.clone();
    let query_barrier = Arc::clone(&barrier);
    let query = thread::spawn(move || {
        query_barrier.wait();
        for _ in 0..1000 {
            let state = query_core.query_delivery(&query_view, 1).unwrap().state;
            assert!(matches!(
                state,
                DeliveryState::Terminal | DeliveryState::Retired
            ));
        }
    });
    let retire_core = Arc::clone(&core);
    let retire_view = view.clone();
    let retire_barrier = Arc::clone(&barrier);
    let retire = thread::spawn(move || {
        retire_barrier.wait();
        retire_core
            .retire_through(&retire_view, ack(&retire_core, 1), &owner_authority)
            .unwrap();
    });
    query.join().unwrap();
    retire.join().unwrap();
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Retired
    );
}

#[test]
fn same_identity_different_core_instances_cannot_use_each_others_tokens() {
    let first = ControlCore::new(boot(700), space(700));
    let second = ControlCore::new(boot(700), space(700));
    let target = root(700, CPU_PERIOD_NS);
    let who = publisher(701);
    let token = first
        .reserve(request(1, target.grant(who).unwrap(), 1, 20), who)
        .unwrap();
    assert_eq!(
        second.commit(&token, who, 1),
        Err(DeliveryError::PermissionDenied)
    );
    assert_eq!(
        second.publish(
            &token,
            who,
            PublishOutcome::Failure {
                status: DeliveryStatus::Revoked
            }
        ),
        Err(DeliveryError::PermissionDenied)
    );
}

#[test]
fn same_d_different_authorized_publisher_is_a_conflict() {
    let core = ControlCore::new(boot(750), space(750));
    let target = root(750, CPU_PERIOD_NS);
    let first = publisher(751);
    let second = publisher(752);
    let token = core
        .reserve(request(1, target.grant(first).unwrap(), 1, 50), first)
        .unwrap();
    assert_eq!(
        core.reserve(request(1, target.grant(second).unwrap(), 1, 50), second)
            .err(),
        Some(DeliveryError::Conflict)
    );
    assert_eq!(
        core.reserve_or_get(request(1, target.grant(second).unwrap(), 1, 50), second)
            .err(),
        Some(DeliveryError::Conflict)
    );
    assert_eq!(
        core.commit(&token, first, 1).unwrap().status,
        Some(DeliveryStatus::Ok)
    );
    assert_eq!(target.revision(), 2);
}

#[test]
fn read_only_history_view_cannot_advance_the_ack_frontier() {
    let (core, owner_authority) =
        ControlCore::with_original_owner(boot(760), space(760), owner(9000)).unwrap();
    let target = root(760, CPU_PERIOD_NS);
    let who = publisher(761);
    let token = core
        .reserve(request(1, target.grant(who).unwrap(), 1, 20), who)
        .unwrap();
    core.commit(&token, who, 1).unwrap();
    let observer = core.delivery_view();
    assert_eq!(
        core.query_delivery(&observer, 1).unwrap().state,
        DeliveryState::Terminal
    );
    assert_eq!(
        core.retire_through(&observer, ack(&core, 1), &owner_authority),
        Err(DeliveryError::PermissionDenied)
    );
    assert_eq!(core.retired_through(), 0);
    let owner_view = core.delivery_view_for(owner(9000)).unwrap();
    assert_eq!(
        core.retire_through(&owner_view, ack(&core, 1), &owner_authority)
            .unwrap()
            .retired_through,
        1
    );
}

#[test]
fn forged_ack_or_foreign_owner_handle_cannot_retire_terminal_history() {
    let (core, original_owner) =
        ControlCore::with_original_owner(boot(940), space(940), owner(9000)).unwrap();
    let (_, alien_owner) =
        ControlCore::with_original_owner(boot(940), space(940), owner(9000)).unwrap();
    let target = root(940, CPU_PERIOD_NS);
    let who = publisher(940);
    let token = core
        .reserve(request(1, target.grant(who).unwrap(), 1, 30), who)
        .unwrap();
    core.commit(&token, who, 1).unwrap();
    let view = core.delivery_view_for(owner(9000)).unwrap();
    assert_eq!(
        core.retire_through(&view, ack(&core, 1), &alien_owner),
        Err(DeliveryError::PermissionDenied)
    );
    let forged = HistoryAck::from_owner_receipt(
        core.identity(), 1, OwnerReceipt::new(owner(9001), [1; 32]),
    ).unwrap();
    assert_eq!(
        core.retire_through(&view, forged, &original_owner),
        Err(DeliveryError::PermissionDenied)
    );
    assert_eq!(core.window_len(), 1);
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Terminal
    );
    assert_eq!(
        core.retire_through(&view, ack(&core, 1), &original_owner)
            .unwrap()
            .retired_through,
        1
    );
    core.lose_history();
    assert_eq!(
        core.retire_through(&view, ack(&core, 1), &original_owner),
        Err(DeliveryError::HistoryLost)
    );
}

#[test]
fn namespace_loss_and_commit_race_never_reports_lost_after_mutation() {
    for n in 0..128_u128 {
        let core = Arc::new(ControlCore::new(boot(800 + n), space(800 + n)));
        let target = root(800 + n, CPU_PERIOD_NS);
        let who = publisher(2000 + n);
        let token = core
            .reserve(request(1, target.grant(who).unwrap(), 1, 20), who)
            .unwrap();
        let start = Arc::new(Barrier::new(3));
        let commit_core = Arc::clone(&core);
        let commit_barrier = Arc::clone(&start);
        let commit = thread::spawn(move || {
            commit_barrier.wait();
            commit_core.commit(&token, who, 1)
        });
        let loss_core = Arc::clone(&core);
        let loss_barrier = Arc::clone(&start);
        let loss = thread::spawn(move || {
            loss_barrier.wait();
            loss_core.lose_history();
        });
        start.wait();
        let outcome = commit.join().unwrap();
        loss.join().unwrap();
        match outcome {
            Ok(observed) => {
                assert_eq!(observed.status, Some(DeliveryStatus::Ok));
                assert_eq!(target.revision(), 2);
            }
            Err(DeliveryError::HistoryLost) => assert_eq!(target.revision(), 1),
            _ => panic!("unexpected post-loss result"),
        }
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1).unwrap().state,
            DeliveryState::HistoryLost
        );
    }
}
#[test]
fn stale_boottime_samples_never_replenish_window_budget() {
    // A 100ns cap with 30ns used leaves 70ns, so a 71ns charge must fail.
    let target = root(40_000, 100);
    let who = publisher(40_001);
    target.charge_cpu(30, CPU_PERIOD_NS + 30).unwrap();
    assert_eq!(target.charge_cpu(20, 20), Err(ResourceError::ClockRollback));
    let grant = target.grant(who).unwrap();
    assert_eq!(
        target.install_budget_for_host_model(&grant, 1, CPU_PERIOD_NS, 20, 20),
        Err(ResourceError::ClockRollback)
    );
    assert_eq!(target.try_usage(20), Err(ResourceError::ClockRollback));
    let clamped = target.usage(10);
    assert_eq!(clamped.sample_boottime_ns, CPU_PERIOD_NS + 30);
    assert_eq!(clamped.window_start_ns, CPU_PERIOD_NS);
    assert_eq!(clamped.window_consumed_ns, 30);
    assert_eq!(target.revision(), 1);
    assert_eq!(
        target.charge_cpu(71, CPU_PERIOD_NS + 31).unwrap_err(),
        ResourceError::Exhausted
    );
}

#[test]
fn budget_installation_advances_only_on_real_period_boundaries() {
    let target = root(50_000, 90);
    let who = publisher(50_001);
    target.charge_cpu(40, 40).unwrap();
    let grant = target.grant(who).unwrap();
    let unchanged = target
        .install_budget_for_host_model(&grant, 1, CPU_PERIOD_NS, 90, 50)
        .unwrap();
    assert_eq!(unchanged.consumed_at_apply_ns, 40);
    let next = target
        .install_budget_for_host_model(
            &grant, 2, CPU_PERIOD_NS, 20, CPU_PERIOD_NS + 1
        )
        .unwrap();
    assert_eq!(next.consumed_at_apply_ns, 0);
    assert_eq!(target.usage(CPU_PERIOD_NS + 2).window_consumed_ns, 0);
    assert_eq!(target.usage(CPU_PERIOD_NS + 2).cumulative_cpu_ns, 40);
}

#[test]
fn concurrent_publish_observe_never_yields_partial_terminal_metadata() {
    let core = Arc::new(ControlCore::new(boot(60_000), space(60_000)));
    let target = root(60_000, CPU_PERIOD_NS);
    let who = publisher(60_001);
    let token = core.reserve(request(1, target.grant(who).unwrap(), 1, 30), who).unwrap();
    let view = core.delivery_view();
    let start = Arc::new(Barrier::new(3));
    let query_start = Arc::clone(&start);
    let query_core = Arc::clone(&core);
    let query = thread::spawn(move || {
        query_start.wait();
        for _ in 0..20_000 {
            let observed = query_core.query_delivery(&view, 1).unwrap();
            match observed.state {
                DeliveryState::Reserved => {
                    assert_eq!(observed.status, None);
                    assert_eq!(observed.saved_revision, None);
                    assert_eq!(observed.effective_ns, None);
                }
                DeliveryState::Terminal => {
                    assert_eq!(observed.status, Some(DeliveryStatus::Ok));
                    assert_eq!(observed.stable_object_id, Some(object(60_000)));
                    assert_eq!(observed.previous_revision, Some(1));
                    assert_eq!(observed.saved_revision, Some(2));
                    assert_eq!(observed.effective_ns, Some(77));
                    assert_eq!(observed.consumed_ns, Some(9));
                    return;
                }
                _ => panic!("no retire/loss in this publication race"),
            }
            thread::yield_now();
        }
    });
    let publish_start = Arc::clone(&start);
    let publish_core = Arc::clone(&core);
    let publish = thread::spawn(move || {
        publish_start.wait();
        publish_core.publish(&token, who, PublishOutcome::Success {
            stable_object_id: object(60_000),
            previous_revision: 1,
            saved_revision: 2,
            effective_ns: 77,
            consumed_ns: 9,
        })
    });
    start.wait();
    let terminal = publish.join().unwrap().unwrap();
    query.join().unwrap();
    assert_eq!(terminal.consumed_ns, Some(9));
    let final_observation = core.query_delivery(&core.delivery_view(), 1).unwrap();
    assert_eq!(final_observation, terminal);
}

#[test]
fn copyout_retry_racing_with_retirement_never_reopens_a_delivery() {
    for n in 0..96_u128 {
        let (control, authority) = ControlCore::with_original_owner(
            boot(61_000 + n), space(61_000 + n), owner(9000),
        ).unwrap();
        let core = Arc::new(control);
        let target = root(61_000 + n, CPU_PERIOD_NS);
        let who = publisher(62_000 + n);
        let grant = target.grant(who).unwrap();
        let token = core.reserve(request(1, grant.clone(), 1, 30), who).unwrap();
        core.commit(&token, who, 1).unwrap();
        let view = core.delivery_view_for(owner(9000)).unwrap();
        let start = Arc::new(Barrier::new(3));
        let retry_start = Arc::clone(&start);
        let retry_core = Arc::clone(&core);
        let retry = thread::spawn(move || {
            retry_start.wait();
            retry_core.reserve_or_get(request(1, grant, 1, 30), who)
        });
        let retire_start = Arc::clone(&start);
        let retire_core = Arc::clone(&core);
        let retire = thread::spawn(move || {
            retire_start.wait();
            retire_core.retire_through(&view, ack(&retire_core, 1), &authority)
        });
        start.wait();
        match retry.join().unwrap() {
            Ok(ReserveAttempt::Existing(observed)) => {
                assert_eq!(observed.state, DeliveryState::Terminal);
            }
            Err(DeliveryError::Retired) => {}
            _ => panic!("retry must observe terminal or permanent retirement"),
        }
        assert_eq!(retire.join().unwrap().unwrap().retired_through, 1);
        assert_eq!(target.revision(), 2);
        assert_eq!(core.window_len(), 0);
    }
}

#[test]
fn cross_branch_domain_and_object_id_reuse_are_rejected() {
    let root = root(80_000, 90);
    let left = with_parent(domain(80_001), object(80_001), &root, 80).unwrap();
    let right = with_parent(domain(80_002), object(80_002), &root, 80).unwrap();
    let grandchild = with_parent(domain(80_003), object(80_003), &left, 70).unwrap();

    // The original per-parent children map misses cousins. A family-wide
    // registry must reject both a duplicate ResourceDomainId and a distinct
    // ResourceDomainId masquerading as the same stable resource object.
    assert_eq!(
        with_parent(domain(80_003), object(80_004), &right, 10).err(),
        Some(ResourceError::DuplicateDomainId)
    );
    assert_eq!(
        with_parent(domain(80_004), object(80_003), &right, 10).err(),
        Some(ResourceError::DuplicateObjectId)
    );
    assert_eq!(grandchild.stable_object_id(), object(80_003));
    let real = with_parent(domain(80_004), object(80_004), &right, 20).unwrap();
    assert_eq!(real.budget().cap_ns, 20);
    let who = publisher(80_005);
    assert_eq!(
        root.install_budget_for_host_model(
            &root.grant(who).unwrap(), 1, CPU_PERIOD_NS, 79, 1
        ),
        Err(ResourceError::ParentConstraint)
    );
}

#[test]
fn concurrent_cousin_registration_same_identity_has_one_winner() {
    for n in 0..64_u128 {
        let root = root(90_000 + n, 90);
        let left = with_parent(domain(100_000 + n), object(100_000 + n), &root, 70).unwrap();
        let right = with_parent(domain(110_000 + n), object(110_000 + n), &root, 70).unwrap();
        let start = Arc::new(Barrier::new(3));
        let one_start = Arc::clone(&start);
        let two_start = Arc::clone(&start);
        let one = thread::spawn(move || {
            one_start.wait();
            with_parent(domain(120_000 + n), object(120_000 + n), &left, 50)
        });
        let two = thread::spawn(move || {
            two_start.wait();
            with_parent(domain(120_000 + n), object(120_000 + n), &right, 50)
        });
        start.wait();
        let a = one.join().unwrap();
        let b = two.join().unwrap();
        assert_eq!((a.is_ok() as usize) + (b.is_ok() as usize), 1);
        let rejected = if a.is_err() { a.err() } else { b.err() };
        assert_eq!(rejected, Some(ResourceError::DuplicateDomainId));
    }
}

#[test]
fn failed_ancestor_charge_never_advances_descendant_clock_or_counters() {
    let parent = root(130_000, 10);
    let busy = with_parent(domain(130_001), object(130_001), &parent, 10).unwrap();
    let idle = with_parent(domain(130_002), object(130_002), &parent, 10).unwrap();
    busy.charge_cpu(8, 100).unwrap();
    assert_eq!(idle.charge_cpu(5, 200), Err(ResourceError::Exhausted));
    let unchanged = idle.try_usage(0).unwrap();
    assert_eq!(unchanged.sample_boottime_ns, 0);
    assert_eq!(unchanged.cumulative_cpu_ns, 0);
    assert_eq!(unchanged.window_consumed_ns, 0);
    assert_eq!(unchanged.event_sequence, 0);
    idle.charge_cpu(2, 150).unwrap();
    assert_eq!(parent.usage(200).window_consumed_ns, 10);
    assert_eq!(idle.usage(200).window_consumed_ns, 2);
    assert_eq!(parent.usage(200).event_sequence, 2);
}

#[test]
fn exhausted_grandparent_does_not_modify_either_descendant() {
    let grandparent = root(140_000, 10);
    let competitor =
        with_parent(domain(140_001), object(140_001), &grandparent, 10).unwrap();
    let parent = with_parent(domain(140_002), object(140_002), &grandparent, 10).unwrap();
    let leaf = with_parent(domain(140_003), object(140_003), &parent, 10).unwrap();

    competitor.charge_cpu(9, 100).unwrap();
    assert_eq!(leaf.charge_cpu(2, 200), Err(ResourceError::Exhausted));
    assert_eq!(leaf.try_usage(0).unwrap().event_sequence, 0);
    assert_eq!(parent.try_usage(0).unwrap().event_sequence, 0);
    leaf.charge_cpu(1, 150).unwrap();
    assert_eq!(grandparent.usage(200).window_consumed_ns, 10);
    assert_eq!(parent.usage(200).window_consumed_ns, 1);
    assert_eq!(leaf.usage(200).window_consumed_ns, 1);
}

#[test]
fn concurrent_siblings_never_double_spend_shared_parent_quota() {
    let parent = root(150_000, 20);
    let left = with_parent(domain(150_001), object(150_001), &parent, 20).unwrap();
    let right = with_parent(domain(150_002), object(150_002), &parent, 20).unwrap();
    let start = Arc::new(Barrier::new(65));
    let mut workers = Vec::new();
    for i in 0..64 {
        let child = if i % 2 == 0 { left.clone() } else { right.clone() };
        let ready = Arc::clone(&start);
        workers.push(thread::spawn(move || {
            ready.wait();
            child.charge_cpu(1, 10)
        }));
    }
    start.wait();
    let successes = workers.into_iter().map(|handle| handle.join().unwrap())
        .filter(Result::is_ok).count();
    assert_eq!(successes, 20);
    let p = parent.usage(11);
    let l = left.usage(11);
    let r = right.usage(11);
    assert_eq!(p.window_consumed_ns, 20);
    assert_eq!(p.event_sequence, 20);
    assert_eq!(p.window_consumed_ns, l.window_consumed_ns + r.window_consumed_ns);
    assert_eq!(p.cumulative_cpu_ns, l.cumulative_cpu_ns + r.cumulative_cpu_ns);
}
