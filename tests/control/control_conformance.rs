//! Host-model conformance and adversarial tests for A03.
//!
//! These tests exercise the Rust state core only.  They do not exercise a
//! kernel, HOS2 copyin/copyout, credentials, scheduler accounting, fsync, or
//! crash recovery.

use os_control::{
    with_parent, BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryRequest, DeliveryState,
    DeliveryStatus, HistoryAck, LogicalOperationId, NamespaceIdentity, OperationBinding, OwnerId, OwnerReceipt,
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
    let k = LogicalOperationId::new(
        "scope:workspace.owner",
        "operation:long-running-resume-across-boot",
    )
    .unwrap();
    let d = os_control::DeliveryId::new(core.identity(), 1).unwrap();
    let binding = OperationBinding::new(k.clone(), d);
    assert_eq!(binding.logical, k);
    assert_eq!(binding.delivery, d);
    assert_eq!(binding.logical.scope_id(), "scope:workspace.owner");
    assert_eq!(
        binding.logical.operation_id(),
        "operation:long-running-resume-across-boot"
    );

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
    assert_eq!(pending.hos2_saved_status_code(), Some(0));
}

#[test]
fn malformed_public_delivery_observations_fail_closed_for_wire_status() {
    let core = ControlCore::new(boot(195_000), space(195_000));
    let original = core.query_delivery(&core.delivery_view(), 1).unwrap();
    for state in [
        DeliveryState::Reserved,
        DeliveryState::Retired,
        DeliveryState::NotSeen,
        DeliveryState::HistoryLost,
    ] {
        let mut observation = original;
        observation.state = state;
        observation.status = None;
        assert_eq!(observation.hos2_saved_status_code(), Some(0));
        observation.status = Some(DeliveryStatus::Revoked);
        assert_eq!(observation.hos2_saved_status_code(), None);
    }
    let mut terminal = original;
    terminal.state = DeliveryState::Terminal;
    terminal.status = None;
    assert_eq!(terminal.hos2_saved_status_code(), None);
    let target = root(195_000, CPU_PERIOD_NS);
    let who = publisher(195_001);
    let token = core
        .reserve(request(1, target.grant(who).unwrap(), 1, 40), who)
        .unwrap();
    let successful = core.commit(&token, who, 42).unwrap();
    assert_eq!(successful.hos2_saved_status_code(), Some(0));
    let mut malformed = successful;
    malformed.saved_revision = None;
    assert_eq!(malformed.hos2_saved_status_code(), None);
    malformed = successful;
    malformed.saved_revision = Some(900);
    assert_eq!(malformed.hos2_saved_status_code(), None);
    // The final representable CAS is previous=MAX-1, saved=MAX.
    let mut last_revision = successful;
    last_revision.previous_revision = Some(u64::MAX - 1);
    last_revision.saved_revision = Some(u64::MAX);
    assert_eq!(last_revision.hos2_saved_status_code(), Some(0));
    malformed = terminal;
    malformed.status = Some(DeliveryStatus::Revoked);
    malformed.consumed_ns = Some(0);
    assert_eq!(malformed.hos2_saved_status_code(), None);
    malformed = original;
    malformed.saved_revision = Some(2);
    assert_eq!(malformed.hos2_saved_status_code(), None);
    malformed = original;
    // Invalid public D fields can no longer be forged with struct syntax.
    // The checked constructor rejects zero and the reserved MAX sequence.
    assert_eq!(
        os_control::DeliveryId::new(core.identity(), 0),
        Err(DeliveryError::InvalidSequence)
    );
    assert_eq!(
        os_control::DeliveryId::new(core.identity(), u64::MAX),
        Err(DeliveryError::InvalidSequence)
    );
    for (status, code) in [
        (DeliveryStatus::Ok, 0),
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
        let mut observation = if status == DeliveryStatus::Ok {
            successful
        } else {
            terminal
        };
        observation.status = Some(status);
        assert_eq!(observation.hos2_saved_status_code(), Some(code));
    }
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
fn malformed_install_budget_is_rejected_before_consuming_global_sequence() {
    let (core, authority) =
        ControlCore::with_capacity_for_owner(boot(145_000), space(145_000), 1, owner(9000))
            .unwrap();
    let target = root(145_000, CPU_PERIOD_NS);
    let who = publisher(145_001);
    let grant = target.grant(who).unwrap();
    let mut bad_requests = [
        request(1, grant.clone(), 0, 20),
        request(1, grant.clone(), u64::MAX, 20),
        request(1, grant.clone(), 1, CPU_PERIOD_NS + 1),
        request(1, grant.clone(), 1, 20),
    ];
    bad_requests[3].period_ns = CPU_PERIOD_NS + 1;
    for bad in bad_requests {
        assert_eq!(core.reserve(bad, who).err(), Some(DeliveryError::InvalidRequest));
        assert_eq!(core.next_sequence(), 1);
        assert_eq!(core.window_len(), 0);
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1).unwrap().state,
            DeliveryState::NotSeen
        );
    }
    // Static rejection did not poison D, so a valid payload can claim it.
    let token = core.reserve(request(1, grant.clone(), 1, 20), who).unwrap();
    assert_eq!(core.next_sequence(), 2);
    assert_eq!(core.window_len(), 1);
    let first = core.commit(&token, who, 1).unwrap();
    assert_eq!(first.status, Some(DeliveryStatus::Ok));
    // A full unretired window denies new D without consuming its sequence.
    assert_eq!(
        core.reserve(request(2, grant.clone(), 1, 20), who).err(),
        Some(DeliveryError::ResourceExhausted)
    );
    assert_eq!(core.next_sequence(), 2);
    let view = core.delivery_view_for(owner(9000)).unwrap();
    core.retire_through(&view, ack(&core, 1), &authority).unwrap();
    // Once a syntactically valid D is reserved, a stale CAS revision is an
    // immutable semantic rejection, not another structural parse error.
    let stale = core.reserve(request(2, grant.clone(), 1, 20), who).unwrap();
    let rejected = core.commit(&stale, who, 2).unwrap();
    assert_eq!(rejected.status, Some(DeliveryStatus::Conflict));
    assert_eq!(target.revision(), 2);
    match core.reserve_or_get(request(2, grant.clone(), 1, 20), who) {
        Ok(ReserveAttempt::Existing(observed)) => assert_eq!(observed, rejected),
        _ => panic!("semantic refusal must be immutable"),
    }
    assert_eq!(
        core.reserve(request(2, grant, 2, 20), who).err(),
        Some(DeliveryError::Conflict)
    );
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
fn old_child_grant_never_revives_after_ancestor_revoke_and_reactivate() {
    let grandparent = root(201_000, CPU_PERIOD_NS);
    let parent = with_parent(domain(201_001), object(201_001), &grandparent, 80).unwrap();
    let child = with_parent(domain(201_002), object(201_002), &parent, 70).unwrap();
    let who = publisher(201_003);
    let stale = child.grant(who).unwrap();

    grandparent.revoke();
    assert!(matches!(child.grant(who), Err(ResourceError::Revoked)));
    grandparent.reactivate_for_host_model().unwrap();
    assert_eq!(
        child.install_budget_for_host_model(&stale, 1, CPU_PERIOD_NS, 60, 1),
        Err(ResourceError::GrantEpochMismatch)
    );
    assert_eq!(child.revision(), 1);
    // A genuinely new grant is permitted only after trusted reactivation.
    let fresh = child.grant(who).unwrap();
    let receipt = child
        .install_budget_for_host_model(&fresh, 1, CPU_PERIOD_NS, 60, 2)
        .unwrap();
    assert_eq!(receipt.revision, 2);
    assert_eq!(
        child.install_budget_for_host_model(&stale, 2, CPU_PERIOD_NS, 50, 3),
        Err(ResourceError::GrantEpochMismatch)
    );

    parent.revoke();
    parent.reactivate_for_host_model().unwrap();
    assert_eq!(
        child.install_budget_for_host_model(&fresh, 2, CPU_PERIOD_NS, 50, 4),
        Err(ResourceError::GrantEpochMismatch)
    );
}

#[test]
fn same_d_with_new_ancestor_grant_conflicts_and_old_d_rejects_terminally() {
    let root_domain = root(202_000, CPU_PERIOD_NS);
    let child = with_parent(domain(202_001), object(202_001), &root_domain, 80).unwrap();
    let who = publisher(202_002);
    let stale_grant = child.grant(who).unwrap();
    let core = ControlCore::new(boot(202_000), space(202_000));
    let original = core
        .reserve(request(1, stale_grant.clone(), 1, 60), who)
        .unwrap();

    root_domain.revoke();
    root_domain.reactivate_for_host_model().unwrap();
    let fresh_grant = child.grant(who).unwrap();
    assert_eq!(
        core.reserve(request(1, fresh_grant.clone(), 1, 60), who).err(),
        Some(DeliveryError::Conflict)
    );
    assert!(matches!(
        core.reserve_or_get(request(1, fresh_grant.clone(), 1, 60), who),
        Err(DeliveryError::Conflict)
    ));
    let denied = core.commit(&original, who, 1).unwrap();
    assert_eq!(denied.status, Some(DeliveryStatus::Revoked));
    assert_eq!(child.revision(), 1);
    match core.reserve_or_get(request(1, stale_grant, 1, 60), who) {
        Ok(ReserveAttempt::Existing(observed)) => assert_eq!(observed, denied),
        _ => panic!("old D must remain terminally rejected"),
    }
    let new_token = core.reserve(request(2, fresh_grant, 1, 60), who).unwrap();
    assert_eq!(
        core.commit(&new_token, who, 2).unwrap().status,
        Some(DeliveryStatus::Ok)
    );
    assert_eq!(child.revision(), 2);
}

#[test]
fn concurrent_ancestor_revoke_and_child_commit_preserve_epoch_fence() {
    // The family gate must admit exactly one of the two orderings; after
    // ancestor recovery the pre-revocation grant must still be invalid.
    for n in 0..128_u128 {
        let root_domain = root(203_000 + n, CPU_PERIOD_NS);
        let child = with_parent(
            domain(204_000 + n), object(204_000 + n), &root_domain, 80,
        )
        .unwrap();
        let who = publisher(205_000 + n);
        let old_grant = child.grant(who).unwrap();
        let core = Arc::new(ControlCore::new(boot(203_000 + n), space(203_000 + n)));
        let token = core
            .reserve(request(1, old_grant.clone(), 1, 60), who)
            .unwrap();
        let barrier = Arc::new(Barrier::new(3));
        let commit_core = Arc::clone(&core);
        let commit_barrier = Arc::clone(&barrier);
        let commit = thread::spawn(move || {
            commit_barrier.wait();
            commit_core.commit(&token, who, 1).unwrap()
        });
        let revoke_root = root_domain.clone();
        let revoke_barrier = Arc::clone(&barrier);
        let revoke = thread::spawn(move || {
            revoke_barrier.wait();
            revoke_root.revoke();
        });
        barrier.wait();
        let terminal = commit.join().unwrap();
        revoke.join().unwrap();
        match terminal.status {
            Some(DeliveryStatus::Ok) => assert_eq!(child.revision(), 2),
            Some(DeliveryStatus::Revoked) => assert_eq!(child.revision(), 1),
            unexpected => panic!("unlinearized revoke/commit result: {unexpected:?}"),
        }
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1).unwrap(),
            terminal
        );

        root_domain.reactivate_for_host_model().unwrap();
        assert_eq!(
            child.install_budget_for_host_model(
                &old_grant, child.revision(), CPU_PERIOD_NS, 50, 2,
            ),
            Err(ResourceError::GrantEpochMismatch)
        );
        let fresh_grant = child.grant(who).unwrap();
        let token2 = core
            .reserve(request(2, fresh_grant, child.revision(), 50), who)
            .unwrap();
        assert_eq!(
            core.commit(&token2, who, 3).unwrap().status,
            Some(DeliveryStatus::Ok)
        );
    }
}

#[test]
fn concurrent_ancestor_revoke_and_child_grant_issuance_fails_closed() {
    // If issuance linearizes first, the returned grant becomes invalid
    // after revoke and reactivation. If revoke wins, issuance must fail.
    for n in 0..128_u128 {
        let root_domain = root(206_000 + n, CPU_PERIOD_NS);
        let child = with_parent(
            domain(207_000 + n),
            object(207_000 + n),
            &root_domain,
            70,
        )
        .unwrap();
        let who = publisher(208_000 + n);
        let start = Arc::new(Barrier::new(3));

        let grant_child = child.clone();
        let grant_start = Arc::clone(&start);
        let issue = thread::spawn(move || {
            grant_start.wait();
            grant_child.grant(who)
        });
        let revoke_root = root_domain.clone();
        let revoke_start = Arc::clone(&start);
        let revoke = thread::spawn(move || {
            revoke_start.wait();
            revoke_root.revoke()
        });
        start.wait();
        let issued = issue.join().unwrap();
        revoke.join().unwrap();
        assert!(matches!(
            &issued,
            Ok(_) | Err(ResourceError::Revoked)
        ));
        root_domain.reactivate_for_host_model().unwrap();
        if let Ok(stale) = issued {
            assert_eq!(
                child.install_budget_for_host_model(&stale, 1, CPU_PERIOD_NS, 60, 1),
                Err(ResourceError::GrantEpochMismatch)
            );
        }
        assert_eq!(child.revision(), 1);
        let fresh = child.grant(who).unwrap();
        assert_eq!(
            child
                .install_budget_for_host_model(&fresh, 1, CPU_PERIOD_NS, 60, 2)
                .unwrap()
                .revision,
            2
        );
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
fn identical_stable_ids_in_different_root_instances_cannot_replay_a_delivery() {
    let core = ControlCore::new(boot(140_000), space(140_000));
    let real = root(140_000, 90);
    // Same public identity bytes, different resource instance.
    let alias = root(140_000, 90);
    let who = publisher(140_001);
    let first = core
        .reserve(request(1, real.grant(who).unwrap(), 1, 40), who)
        .unwrap();
    assert_eq!(
        core.reserve(request(1, alias.grant(who).unwrap(), 1, 40), who)
            .err(),
        Some(DeliveryError::Conflict)
    );
    assert!(matches!(
        core.reserve_or_get(request(1, alias.grant(who).unwrap(), 1, 40), who),
        Err(DeliveryError::Conflict)
    ));
    let terminal = core.commit(&first, who, 1).unwrap();
    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
    assert_eq!(real.revision(), 2);
    assert_eq!(alias.revision(), 1);
    match core.reserve_or_get(request(1, real.grant(who).unwrap(), 1, 40), who) {
        Ok(ReserveAttempt::Existing(observed)) => assert_eq!(observed, terminal),
        _ => panic!("real instance must retain its immutable result"),
    }
}

#[test]
fn new_grandchild_cannot_enter_a_revoked_root_family() {
    let grandparent = root(141_000, 90);
    let parent = with_parent(domain(141_001), object(141_001), &grandparent, 70).unwrap();
    grandparent.revoke();
    assert_eq!(
        with_parent(domain(141_002), object(141_002), &parent, 20).err(),
        Some(ResourceError::Revoked)
    );
    // A failed registration cannot consume the identity forever.
    grandparent.reactivate_for_host_model().unwrap();
    let child = with_parent(domain(141_002), object(141_002), &parent, 20).unwrap();
    assert_eq!(child.budget().cap_ns, 20);
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
    // The charge must be no larger than elapsed CPU time in the period.
    target.charge_cpu(25, CPU_PERIOD_NS + 35).unwrap();
    let same_cap = target
        .install_budget_for_host_model(
            &target.grant(who).unwrap(),
            2,
            CPU_PERIOD_NS,
            90,
            CPU_PERIOD_NS + 40,
        )
        .unwrap();
    assert_eq!(same_cap.consumed_at_apply_ns, 25);
    assert_eq!(target.usage(CPU_PERIOD_NS + 41).window_consumed_ns, 25);
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
fn namespace_bootstrap_rejects_zero_id_and_out_of_range_window_capacity() {
    assert_eq!(
        ControlCore::try_with_capacity(boot(0), space(2), 1).err(),
        Some(DeliveryError::InvalidIdentity)
    );
    assert_eq!(
        ControlCore::try_with_capacity(boot(2), space(0), 1).err(),
        Some(DeliveryError::InvalidIdentity)
    );
    for invalid in [0, os_control::DEFAULT_WINDOW_CAPACITY + 1, usize::MAX] {
        assert_eq!(
            ControlCore::try_with_capacity(boot(2), space(3), invalid).err(),
            Some(DeliveryError::InvalidCapacity)
        );
        assert_eq!(
            ControlCore::with_capacity_for_owner(
                boot(2), space(3), invalid, owner(9000),
            ).err(),
            Some(DeliveryError::InvalidCapacity)
        );
    }
    let valid = ControlCore::try_with_capacity(
        boot(2), space(3), os_control::DEFAULT_WINDOW_CAPACITY,
    )
    .unwrap();
    assert_eq!(valid.capacity(), os_control::DEFAULT_WINDOW_CAPACITY);
    assert_eq!(valid.next_sequence(), 1);
    assert_eq!(valid.window_len(), 0);
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

#[test]
fn exact_boundary_crossing_preserves_each_period_cap() {
    let target = root(160_000, 10);
    target
        .charge_interval_for_host_model(CPU_PERIOD_NS - 7, CPU_PERIOD_NS + 7)
        .unwrap();
    let first = target.usage(CPU_PERIOD_NS + 7);
    assert_eq!(first.cumulative_cpu_ns, 14);
    assert_eq!(first.window_start_ns, CPU_PERIOD_NS);
    assert_eq!(first.window_consumed_ns, 7);
    assert_eq!(
        target.charge_interval_for_host_model(
            CPU_PERIOD_NS + 7,
            CPU_PERIOD_NS + 11,
        ),
        Err(ResourceError::Exhausted)
    );
    // A rejected charge is not a time sample or a partial effect.
    assert_eq!(
        target.try_usage(CPU_PERIOD_NS + 7).unwrap().window_consumed_ns,
        7
    );
    target
        .charge_interval_for_host_model(CPU_PERIOD_NS + 7, CPU_PERIOD_NS + 10)
        .unwrap();
    assert_eq!(target.usage(CPU_PERIOD_NS + 10).window_consumed_ns, 10);
    assert_eq!(target.usage(CPU_PERIOD_NS + 10).cumulative_cpu_ns, 17);
}

#[test]
fn multi_period_accounting_has_no_unused_quota_credit() {
    let p = CPU_PERIOD_NS;
    let full = root(170_000, p);
    full.charge_interval_for_host_model(0, 3 * p + 7).unwrap();
    let snapshot = full.usage(3 * p + 7);
    assert_eq!(snapshot.cumulative_cpu_ns, 3 * p + 7);
    assert_eq!(snapshot.window_start_ns, 3 * p);
    assert_eq!(snapshot.window_consumed_ns, 7);
    let limited = root(170_001, p - 1);
    assert_eq!(
        limited.charge_interval_for_host_model(0, p + 1),
        Err(ResourceError::Exhausted)
    );
    assert_eq!(limited.try_usage(0).unwrap().cumulative_cpu_ns, 0);
    assert_eq!(limited.try_usage(0).unwrap().event_sequence, 0);
}

#[test]
fn interval_parent_failure_is_atomic_across_period_boundary() {
    let p = CPU_PERIOD_NS;
    let ancestor = root(180_000, 10);
    let sibling = with_parent(domain(180_001), object(180_001), &ancestor, 10).unwrap();
    let parent = with_parent(domain(180_002), object(180_002), &ancestor, 10).unwrap();
    let leaf = with_parent(domain(180_003), object(180_003), &parent, 10).unwrap();

    sibling.charge_cpu(5, p - 6).unwrap();
    assert_eq!(
        leaf.charge_interval_for_host_model(p - 6, p + 6),
        Err(ResourceError::Exhausted)
    );
    assert_eq!(leaf.try_usage(0).unwrap().event_sequence, 0);
    assert_eq!(parent.try_usage(0).unwrap().event_sequence, 0);
    assert_eq!(ancestor.try_usage(p - 6).unwrap().window_consumed_ns, 5);
    leaf.charge_interval_for_host_model(p - 6, p - 2).unwrap();
    assert_eq!(ancestor.usage(p - 2).window_consumed_ns, 9);
    assert_eq!(leaf.usage(p - 2).window_consumed_ns, 4);
}

#[test]
fn invalid_and_overflow_adjacent_intervals_fail_closed() {
    let target = root(190_000, CPU_PERIOD_NS);
    assert_eq!(
        target.charge_interval_for_host_model(42, 42),
        Err(ResourceError::InvalidInterval)
    );
    assert_eq!(
        target.charge_interval_for_host_model(43, 42),
        Err(ResourceError::InvalidInterval)
    );
    assert_eq!(target.try_usage(0).unwrap().event_sequence, 0);
    target
        .charge_interval_for_host_model(u64::MAX - 3, u64::MAX)
        .unwrap();
    assert_eq!(target.usage(u64::MAX).cumulative_cpu_ns, 3);
    assert_eq!(
        target.charge_interval_for_host_model(0, 1),
        Err(ResourceError::ClockRollback)
    );
}

#[test]
fn resource_identity_registry_has_bounded_capacity_and_no_id_reanimation() {
    assert!(matches!(
        ResourceDomain::root_with_capacity_for_host_model(
            domain(200_000), object(200_000), 50, 0
        ),
        Err(ResourceError::InvalidCapacity)
    ));

    let root = ResourceDomain::root_with_capacity_for_host_model(
        domain(200_000), object(200_000), 50, 2
    ).unwrap();
    let child = with_parent(domain(200_001), object(200_001), &root, 40).unwrap();
    assert_eq!(
        with_parent(domain(200_002), object(200_002), &root, 10).err(),
        Some(ResourceError::Exhausted)
    );
    // Even if the last host handle is dropped, a stable ID must not revive.
    drop(child);
    assert_eq!(
        with_parent(domain(200_001), object(200_003), &root, 1).err(),
        Some(ResourceError::DuplicateDomainId)
    );
    assert_eq!(
        with_parent(domain(200_003), object(200_001), &root, 1).err(),
        Some(ResourceError::DuplicateObjectId)
    );
    assert_eq!(
        with_parent(domain(200_003), object(200_003), &root, 1).err(),
        Some(ResourceError::Exhausted)
    );
    // Exhaustion has not mutated parent cap, revision, or admission counter.
    assert_eq!(root.revision(), 1);
    assert_eq!(root.budget().cap_ns, 50);
    assert_eq!(root.usage(0).event_sequence, 0);
}

#[test]
fn hos2_saved_success_rejects_consumed_time_beyond_period_elapsed() {
    let core = ControlCore::new(boot(210_000), space(210_000));
    let target = root(210_000, CPU_PERIOD_NS);
    let who = publisher(210_001);
    let token = core.reserve(request(1, target.grant(who).unwrap(), 1, 20), who).unwrap();
    let saved = core.commit(&token, who, CPU_PERIOD_NS + 5).unwrap();
    assert_eq!(saved.hos2_saved_status_code(), Some(0));

    let mut fake = saved;
    fake.consumed_ns = Some(6);
    assert_eq!(fake.hos2_saved_status_code(), None);
    fake.consumed_ns = Some(5);
    assert_eq!(fake.hos2_saved_status_code(), Some(0));
    fake.effective_ns = Some(2 * CPU_PERIOD_NS);
    assert_eq!(fake.hos2_saved_status_code(), None);
    fake.consumed_ns = Some(0);
    assert_eq!(fake.hos2_saved_status_code(), Some(0));
}

#[test]
fn external_success_publication_cannot_save_impossible_cpu_accounting() {
    let core = ControlCore::new(boot(210_010), space(210_010));
    let target = root(210_010, CPU_PERIOD_NS);
    let who = publisher(210_011);
    let token = core.reserve(request(1, target.grant(who).unwrap(), 1, 20), who).unwrap();
    let invalid = PublishOutcome::Success {
        stable_object_id: target.stable_object_id(),
        previous_revision: 1,
        saved_revision: 2,
        effective_ns: CPU_PERIOD_NS + 5,
        consumed_ns: 6,
    };
    assert_eq!(core.publish(&token, who, invalid), Err(DeliveryError::InvalidPublish));
    assert_eq!(core.query_delivery(&core.delivery_view(), 1).unwrap().state, DeliveryState::Reserved);
    let valid = PublishOutcome::Success {
        stable_object_id: target.stable_object_id(),
        previous_revision: 1,
        saved_revision: 2,
        effective_ns: CPU_PERIOD_NS + 5,
        consumed_ns: 5,
    };
    let terminal = core.publish(&token, who, valid).unwrap();
    assert_eq!(terminal.hos2_saved_status_code(), Some(0));
    assert_eq!(core.publish(&token, who, invalid).unwrap(), terminal);
}

#[test]
fn incoherent_cpu_charge_cannot_commit_a_wire_invalid_success() {
    let core = ControlCore::new(boot(210_020), space(210_020));
    let target = root(210_020, 100);
    let who = publisher(210_021);
    // The simplified host charge can represent an impossible runtime sample;
    // budget mutation must fail closed instead of exporting a fake success.
    target.charge_cpu(60, 10).unwrap();
    let grant = target.grant(who).unwrap();
    let first = core.reserve(request(1, grant.clone(), 1, 90), who).unwrap();
    let rejected = core.commit(&first, who, 20).unwrap();
    assert_eq!(rejected.status, Some(DeliveryStatus::Indeterminate));
    assert_eq!(target.revision(), 1);
    assert_eq!(target.usage(20).window_consumed_ns, 60);
    assert_eq!(core.commit(&first, who, 60).unwrap(), rejected);
    // The original D is final; a new D can try a later coherent snapshot
    // without creating credit or rewriting the rejection.
    let second = core.reserve(request(2, grant, 1, 90), who).unwrap();
    let applied = core.commit(&second, who, 60).unwrap();
    assert_eq!(applied.status, Some(DeliveryStatus::Ok));
    assert_eq!(applied.consumed_ns, Some(60));
    assert_eq!(applied.hos2_saved_status_code(), Some(0));
    assert_eq!(target.revision(), 2);
}

#[test]
fn durable_hepta_k_is_full_scope_and_operation_stable_id_pair() {
    // Pinned durable_store.rs SELECT/WHERE and tombstone key use two
    // independently bounded StableIds, not Id16, PID, boot, or payload hash.
    let scope = "s".repeat(os_control::MAX_HEPTA_STABLE_ID_BYTES);
    let operation = "o".repeat(os_control::MAX_HEPTA_STABLE_ID_BYTES);
    let k = LogicalOperationId::new(&scope, &operation).unwrap();
    assert_eq!(k.scope_id(), scope);
    assert_eq!(k.operation_id(), operation);
    assert_ne!(
        LogicalOperationId::new("workspace:a", "operation:1").unwrap(),
        LogicalOperationId::new("workspace:b", "operation:1").unwrap()
    );
    assert_ne!(
        LogicalOperationId::new("workspace:a", "operation:1").unwrap(),
        LogicalOperationId::new("workspace:a", "operation:2").unwrap()
    );
    assert_eq!(
        LogicalOperationId::new("workspace:a", "operation:1").unwrap(),
        LogicalOperationId::new("workspace:a", "operation:1").unwrap()
    );
}

#[test]
fn durable_hepta_k_validation_does_not_truncate_or_normalize() {
    let invalid = ["", "unsafe/path", "with space", "Unicode:测试", "nul\0id"];
    for value in invalid {
        assert_eq!(
            LogicalOperationId::new(value, "operation:valid"),
            Err(os_control::IdentityError::InvalidOperationKey)
        );
        assert_eq!(
            LogicalOperationId::new("scope:valid", value),
            Err(os_control::IdentityError::InvalidOperationKey)
        );
    }
    let too_large = "q".repeat(os_control::MAX_HEPTA_STABLE_ID_BYTES + 1);
    assert_eq!(
        LogicalOperationId::new("scope:valid", &too_large),
        Err(os_control::IdentityError::InvalidOperationKey)
    );
    let mut caller = String::from("operation:original");
    let k = LogicalOperationId::new("scope:immutable", &caller).unwrap();
    caller.clear();
    caller.push_str("operation:changed");
    assert_eq!(k.operation_id(), "operation:original");
    assert_ne!(k.operation_id(), caller);
}

#[test]
fn checked_namespace_constructor_is_not_an_identity_authority() {
    assert_eq!(
        NamespaceIdentity::new(boot(0), space(1)),
        Err(os_control::IdentityError::ZeroIdentity)
    );
    assert_eq!(
        NamespaceIdentity::new(boot(1), space(0)),
        Err(os_control::IdentityError::ZeroIdentity)
    );
    let first = NamespaceIdentity::new(boot(123), space(234)).unwrap();
    assert_eq!(first.boot_id(), boot(123));
    assert_eq!(first.cap_space_id(), space(234));
    let d = os_control::DeliveryId::new(first, 1).unwrap();
    assert_eq!(d.namespace(), first);
    assert_eq!(d.sequence(), 1);
    // A05 trusted init supplies the actual nonzero boot/space IDs. A
    // checked value constructor by itself cannot attest their provenance.
}

#[test]
fn revoked_ancestor_is_not_confused_with_exhausted_cpu_quota() {
    let ancestor = root(220_000, CPU_PERIOD_NS);
    let child = with_parent(domain(220_001), object(220_001), &ancestor, 20).unwrap();
    let leaf = with_parent(domain(220_002), object(220_002), &child, 20).unwrap();
    leaf.charge_cpu(5, 10).unwrap();
    let before = leaf.usage(10);
    ancestor.revoke();
    assert_eq!(leaf.charge_cpu(1, 11), Err(ResourceError::Revoked));
    assert_eq!(
        leaf.charge_interval_for_host_model(10, 11),
        Err(ResourceError::Revoked)
    );
    assert_eq!(leaf.usage(11).cumulative_cpu_ns, before.cumulative_cpu_ns);
    assert_eq!(leaf.usage(11).event_sequence, before.event_sequence);
    assert_eq!(ancestor.usage(11).cumulative_cpu_ns, 5);
}

#[test]
fn grant_publisher_field_cannot_be_reassigned_by_external_code() {
    let target = root(221_000, CPU_PERIOD_NS);
    let who = publisher(221_001);
    let grant = target.grant(who).unwrap();
    assert_eq!(grant.principal(), who);
    assert_eq!(grant.clone().principal(), who);
    let core = ControlCore::new(boot(221_000), space(221_000));
    assert_eq!(
        core.reserve(request(1, grant, 1, 20), publisher(221_002)).err(),
        Some(DeliveryError::PermissionDenied)
    );
    assert_eq!(core.window_len(), 0);
    assert_eq!(core.next_sequence(), 1);
}

// Cross-crate oracle: use the separately owned no_std A02 parser/encoder
// rather than hand-writing the wire struct layout in the A03 state core.
fn a02_roundtrip_delivery(
    observation: os_control::DeliveryObservation,
) -> Result<hos2_os_abi::QueryDeliveryResponse, hos2_os_abi::Error> {
    use hos2_os_abi::{
        decode_response, encode_response, DeliveryState as WireState, Opcode,
        QueryDeliveryResponse, Response, ResponsePayload, Status,
    };

    let saved_code = observation
        .hos2_saved_status_code()
        .ok_or(hos2_os_abi::Error::InvalidField)?;
    let payload = QueryDeliveryResponse {
        state: WireState::from_u16(observation.state.hos2_code())?,
        saved_status: Status::from_u16(saved_code)?,
        sequence: observation.id.sequence(),
        stable_object_id: observation
            .stable_object_id
            .map_or([0; 16], |object| object.bytes()),
        saved_revision: observation.saved_revision.unwrap_or(0),
        previous_revision: observation.previous_revision.unwrap_or(0),
        effective_ns: observation.effective_ns.unwrap_or(0),
        consumed_ns: observation.consumed_ns.unwrap_or(0),
    };
    let response = Response {
        opcode: Opcode::QueryDelivery,
        status: Status::Ok,
        request_id: [0xA3; 16],
        boot_id: observation.id.namespace().boot_id().bytes(),
        revision: 0,
        payload: ResponsePayload::QueryDelivery(payload),
    };
    let mut frame = [0u8; 128];
    let used = encode_response(&response, &mut frame)?;
    let decoded = decode_response(&frame[..used])?;
    match decoded.payload {
        ResponsePayload::QueryDelivery(result) => Ok(result),
        _ => Err(hos2_os_abi::Error::InvalidField),
    }
}

#[test]
fn a02_codec_accepts_every_real_a03_delivery_state() {
    use hos2_os_abi::{DeliveryState as WireState, Status};
    let (core, authority) =
        ControlCore::with_original_owner(boot(310_000), space(310_000), owner(9000)).unwrap();
    let target = root(310_000, CPU_PERIOD_NS);
    let who = publisher(310_001);
    let view = core.delivery_view_for(owner(9000)).unwrap();

    let token = core
        .reserve(request(1, target.grant(who).unwrap(), 1, 40), who)
        .unwrap();
    let pending = a02_roundtrip_delivery(core.query_delivery(&view, 1).unwrap()).unwrap();
    assert_eq!(pending.state, WireState::Reserved);
    assert_eq!(pending.saved_status, Status::Ok);
    let applied = core.commit(&token, who, CPU_PERIOD_NS + 7).unwrap();
    let successful = a02_roundtrip_delivery(applied).unwrap();
    assert_eq!(successful.state, WireState::Terminal);
    assert_eq!(successful.saved_status, Status::Ok);
    assert_eq!(successful.previous_revision, 1);
    assert_eq!(successful.saved_revision, 2);
    assert_eq!(successful.consumed_ns, 0);

    let token2 = core
        .reserve(request(2, target.grant(who).unwrap(), 2, 40), who)
        .unwrap();
    let refused = core
        .publish(
            &token2,
            who,
            PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            },
        )
        .unwrap();
    let saved_error = a02_roundtrip_delivery(refused).unwrap();
    assert_eq!(saved_error.state, WireState::Terminal);
    assert_eq!(saved_error.saved_status, Status::Revoked);
    assert_eq!(saved_error.saved_revision, 0);

    let unseen = a02_roundtrip_delivery(core.query_delivery(&view, 3).unwrap()).unwrap();
    assert_eq!(unseen.state, WireState::NotSeen);
    core.retire_through(&view, ack(&core, 2), &authority).unwrap();
    let retired = a02_roundtrip_delivery(core.query_delivery(&view, 1).unwrap()).unwrap();
    assert_eq!(retired.state, WireState::Retired);
    core.lose_history();
    let lost = a02_roundtrip_delivery(core.query_delivery(&view, 1).unwrap()).unwrap();
    assert_eq!(lost.state, WireState::HistoryLost);
}

#[test]
fn a02_rejects_elapsed_cpu_forgery_even_without_a03_conversion_guard() {
    use hos2_os_abi::{
        encode_response, DeliveryState as WireState, Error, Opcode, QueryDeliveryResponse,
        Response, ResponsePayload, Status,
    };
    let core = ControlCore::new(boot(320_000), space(320_000));
    let target = root(320_000, CPU_PERIOD_NS);
    let who = publisher(320_001);
    let token = core
        .reserve(request(1, target.grant(who).unwrap(), 1, 40), who)
        .unwrap();
    let valid = core.commit(&token, who, CPU_PERIOD_NS + 5).unwrap();
    assert!(a02_roundtrip_delivery(valid).is_ok());

    let mut wrong_elapsed = valid;
    wrong_elapsed.consumed_ns = Some(6);
    assert_eq!(wrong_elapsed.hos2_saved_status_code(), None);
    assert_eq!(
        a02_roundtrip_delivery(wrong_elapsed),
        Err(Error::InvalidField)
    );

    let mut without_revision = valid;
    without_revision.previous_revision = Some(0);
    without_revision.saved_revision = Some(1);
    assert_eq!(without_revision.hos2_saved_status_code(), None);
    assert_eq!(
        a02_roundtrip_delivery(without_revision),
        Err(Error::InvalidField)
    );

    // Bypass A03's conversion helper and independently check A02's strict
    // validator: the same byte-model payload must be rejected at encode.
    let bad = Response {
        opcode: Opcode::QueryDelivery,
        status: Status::Ok,
        request_id: [0xA4; 16],
        boot_id: core.identity().boot_id().bytes(),
        revision: 0,
        payload: ResponsePayload::QueryDelivery(QueryDeliveryResponse {
            state: WireState::Terminal,
            saved_status: Status::Ok,
            sequence: 1,
            stable_object_id: target.stable_object_id().bytes(),
            saved_revision: 2,
            previous_revision: 1,
            effective_ns: CPU_PERIOD_NS + 5,
            consumed_ns: 6,
        }),
    };
    assert_eq!(encode_response(&bad, &mut [0u8; 128]), Err(Error::InvalidField));
}
