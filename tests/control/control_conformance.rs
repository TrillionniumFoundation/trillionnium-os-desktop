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
    assert_eq!(pending.hos2_saved_status_code(), Ok(0));
}

#[test]
fn invalid_query_delivery_state_status_combinations_fail_closed() {
    let core = ControlCore::new(boot(2018), space(2018));
    let view = core.delivery_view();
    let fresh = core.query_delivery(&view, 1).unwrap();
    assert_eq!(fresh.state, DeliveryState::NotSeen);
    assert_eq!(fresh.hos2_saved_status_code(), Ok(0));

    // No non-terminal observation may carry a saved result or effect fields.
    for state in [
        DeliveryState::Reserved,
        DeliveryState::Retired,
        DeliveryState::NotSeen,
        DeliveryState::HistoryLost,
    ] {
        let clean = os_control::DeliveryObservation { state, ..fresh };
        assert_eq!(clean.hos2_saved_status_code(), Ok(0));

        let forged_status = os_control::DeliveryObservation {
            status: Some(DeliveryStatus::Ok),
            ..clean
        };
        assert_eq!(
            forged_status.hos2_saved_status_code(),
            Err(DeliveryError::InvalidPublish)
        );

        let forged_metadata = os_control::DeliveryObservation {
            consumed_ns: Some(5),
            ..clean
        };
        assert_eq!(
            forged_metadata.hos2_saved_status_code(),
            Err(DeliveryError::InvalidPublish)
        );
    }

    // A missing or forged terminal status is NOT a successful effect.
    let missing_terminal_status = os_control::DeliveryObservation {
        state: DeliveryState::Terminal,
        ..fresh
    };
    assert_eq!(
        missing_terminal_status.hos2_saved_status_code(),
        Err(DeliveryError::InvalidPublish)
    );
    let invented_ok = os_control::DeliveryObservation {
        status: Some(DeliveryStatus::Ok),
        ..missing_terminal_status
    };
    assert_eq!(
        invented_ok.hos2_saved_status_code(),
        Err(DeliveryError::InvalidPublish)
    );
}

#[test]
fn real_terminal_query_delivery_values_are_wire_checked() {
    let core = ControlCore::new(boot(2019), space(2019));
    let target = root(2019, CPU_PERIOD_NS);
    let who = publisher(2019);
    let token = core
        .reserve(request(1, target.grant(who).unwrap(), 1, 10), who)
        .unwrap();
    let success = core.commit(&token, who, 1).unwrap();
    assert_eq!(success.state, DeliveryState::Terminal);
    assert_eq!(success.hos2_saved_status_code(), Ok(0));

    let bad_revision = os_control::DeliveryObservation {
        saved_revision: Some(123),
        ..success
    };
    assert_eq!(
        bad_revision.hos2_saved_status_code(),
        Err(DeliveryError::InvalidPublish)
    );
    let zero_object = os_control::DeliveryObservation {
        stable_object_id: Some(object(0)),
        ..success
    };
    assert_eq!(
        zero_object.hos2_saved_status_code(),
        Err(DeliveryError::InvalidPublish)
    );

    let rejection_core = ControlCore::new(boot(2020), space(2020));
    let rejection_target = root(2020, CPU_PERIOD_NS);
    let rejector = publisher(2020);
    let refusal = rejection_core
        .reserve(
            request(1, rejection_target.grant(rejector).unwrap(), 1, 10),
            rejector,
        )
        .unwrap();
    let denied = rejection_core
        .publish(
            &refusal,
            rejector,
            PublishOutcome::Failure {
                status: DeliveryStatus::PermissionDenied,
            },
        )
        .unwrap();
    assert_eq!(denied.hos2_saved_status_code(), Ok(2));
    let false_resource_data = os_control::DeliveryObservation {
        effective_ns: Some(1),
        ..denied
    };
    assert_eq!(
        false_resource_data.hos2_saved_status_code(),
        Err(DeliveryError::InvalidPublish)
    );
}

#[test]
fn all_hos2_terminal_status_codes_are_exhaustively_mapped() {
    let core = ControlCore::new(boot(2021), space(2021));
    let mut terminal = core.query_delivery(&core.delivery_view(), 1).unwrap();
    terminal.state = DeliveryState::Terminal;

    for (status, wire_code) in [
        (DeliveryStatus::Ok, 0_u16),
        (DeliveryStatus::InvalidInput, 1),
        (DeliveryStatus::PermissionDenied, 2),
        (DeliveryStatus::StaleHandle, 3),
        (DeliveryStatus::Revoked, 4),
        (DeliveryStatus::Conflict, 5),
        (DeliveryStatus::ParentLimit, 5),
        (DeliveryStatus::ResourceExhausted, 6),
        (DeliveryStatus::Unsupported, 7),
        (DeliveryStatus::Indeterminate, 8),
        (DeliveryStatus::Busy, 9),
        (DeliveryStatus::OutOfOrder, 10),
        (DeliveryStatus::Retired, 11),
    ] {
        assert_eq!(status.hos2_code(), wire_code);
        terminal.status = Some(status);
        if status == DeliveryStatus::Ok {
            // Cannot report an invented terminal success without revision
            // and resource-effect fields, even if its code would be zero.
            assert_eq!(
                terminal.hos2_saved_status_code(),
                Err(DeliveryError::InvalidPublish)
            );
        } else {
            assert_eq!(terminal.hos2_saved_status_code(), Ok(wire_code));
        }
    }
}

#[test]
fn out_of_order_does_not_consume_sequence_and_wrong_history_owner_cannot_retire() {
    let core = ControlCore::new(boot(13), space(13));
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
        core.retire_through(&view, wrong_ack),
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
    let core = ControlCore::with_capacity(boot(7), space(7), 4);
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
        core.retire_through(&view, ack(&core, 4)),
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
    let retired = core.retire_through(&view, ack(&core, 4)).unwrap();
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
    let core = ControlCore::with_capacity(boot(8), space(8), 32);
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
        core.retire_through(&view, ack(&core, sequence)).unwrap();
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
    let core = Arc::new(ControlCore::new(boot(500), space(500)));
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
    let retired = core.retire_through(&view, ack(&core, 1)).unwrap();
    assert_eq!(retired.retired_through, 1);
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Retired
    );
}

#[test]
fn query_and_retire_race_has_only_terminal_or_retired_observations() {
    let core = Arc::new(ControlCore::new(boot(600), space(600)));
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
            .retire_through(&retire_view, ack(&retire_core, 1))
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
    let core = ControlCore::new(boot(760), space(760));
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
        core.retire_through(&observer, ack(&core, 1)),
        Err(DeliveryError::PermissionDenied)
    );
    assert_eq!(core.retired_through(), 0);
    let owner_view = core.delivery_view_for(owner(9000)).unwrap();
    assert_eq!(
        core.retire_through(&owner_view, ack(&core, 1))
            .unwrap()
            .retired_through,
        1
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
