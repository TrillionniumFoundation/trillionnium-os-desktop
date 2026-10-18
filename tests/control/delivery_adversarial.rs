//! Independent adversarial audit of A03 delivery state, on a Linux host only.
//! These tests do not exercise native credentials, IRQs, ioctl or persistence.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryRequest, DeliveryState, DeliveryStatus,
    HistoryAck, OriginalOwnerAuthority, OwnerId, PublishOutcome, PublisherId, ReserveAttempt,
    ResourceDomain, ResourceDomainId, StableObjectId, CPU_PERIOD_NS, DEFAULT_WINDOW_CAPACITY,
};
use std::sync::{Arc, Barrier};
use std::thread;

fn owner() -> OwnerId {
    OwnerId::from_u128(1)
}

fn publisher() -> PublisherId {
    PublisherId::from_u128(2)
}

fn core(n: u128) -> (ControlCore, OriginalOwnerAuthority) {
    ControlCore::with_original_owner(BootId::from_u128(n), CapSpaceId::from_u128(n), owner())
        .unwrap()
}

fn target(n: u128) -> ResourceDomain {
    ResourceDomain::new(
        ResourceDomainId::from_u128(n),
        StableObjectId::from_u128(n),
        None,
        CPU_PERIOD_NS,
    )
    .unwrap()
}

fn ack(authority: &OriginalOwnerAuthority, sequence: u64) -> HistoryAck {
    authority.history_ack(sequence, [0x81; 32]).unwrap()
}

#[test]
fn full_hos2_window_with_pending_prefix_survives_ten_thousand_deliveries() {
    let (core, authority) = core(700_001);
    let target = target(700_001);
    let grant = target.grant(publisher()).unwrap();
    let view = core.delivery_view_for(owner()).unwrap();
    let prefix = core
        .reserve(DeliveryRequest::new(1, grant.clone(), 1, 7), publisher())
        .unwrap();

    for sequence in 2..=DEFAULT_WINDOW_CAPACITY as u64 {
        let token = core
            .reserve(
                DeliveryRequest::new(sequence, grant.clone(), 1, 7),
                publisher(),
            )
            .unwrap();
        let terminal = core.commit(&token, publisher(), sequence).unwrap();
        assert_eq!(terminal.state, DeliveryState::Terminal);
        assert_eq!(
            terminal.status,
            Some(if sequence == 2 {
                DeliveryStatus::Ok
            } else {
                DeliveryStatus::Conflict
            })
        );
    }
    let next = DEFAULT_WINDOW_CAPACITY as u64 + 1;
    assert_eq!(core.window_len(), DEFAULT_WINDOW_CAPACITY);
    for _ in 0..32 {
        assert_eq!(
            core.reserve(
                DeliveryRequest::new(next, grant.clone(), target.revision(), 7),
                publisher(),
            )
            .err(),
            Some(DeliveryError::ResourceExhausted)
        );
        assert_eq!(
            core.retire_through(&view, ack(&authority, next - 1), &authority),
            Err(DeliveryError::PendingPrefix)
        );
        assert_eq!(
            core.query_delivery(&view, 1).unwrap().state,
            DeliveryState::Reserved
        );
        assert_eq!(
            core.query_delivery(&view, next - 1).unwrap().state,
            DeliveryState::Terminal
        );
        assert_eq!(core.retired_through(), 0);
        assert_eq!(core.next_sequence(), next);
        core.validate_invariants_for_host_model().unwrap();
    }

    // A fenced executor's explicit no-effect refusal releases the prefix;
    // publication alone does not apply or refund a resource budget.
    core.publish(
        &prefix,
        publisher(),
        PublishOutcome::Failure {
            status: DeliveryStatus::Revoked,
        },
    )
    .unwrap();
    core.retire_through(&view, ack(&authority, next - 1), &authority)
        .unwrap();
    for sequence in next..=10_000 {
        let token = core
            .reserve(
                DeliveryRequest::new(sequence, grant.clone(), target.revision(), 7),
                publisher(),
            )
            .unwrap();
        assert_eq!(
            core.commit(&token, publisher(), sequence).unwrap().status,
            Some(DeliveryStatus::Ok)
        );
        core.retire_through(&view, ack(&authority, sequence), &authority)
            .unwrap();
    }
    assert_eq!(core.next_sequence(), 10_001);
    assert_eq!(core.retired_through(), 10_000);
    assert_eq!(core.window_len(), 0);
    assert_eq!(target.revision(), 8_978);
    assert_eq!(
        core.reserve_or_get(DeliveryRequest::new(1, grant, 1, 7), publisher())
            .err(),
        Some(DeliveryError::Retired)
    );
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn same_token_commit_and_explicit_refusal_race_have_one_immutable_outcome() {
    for iteration in 0..128 {
        let (core, _) = core(710_000 + iteration);
        let target = target(710_000 + iteration);
        let token = core
            .reserve(
                DeliveryRequest::new(1, target.grant(publisher()).unwrap(), 1, 7),
                publisher(),
            )
            .unwrap();
        let start = Arc::new(Barrier::new(3));
        thread::scope(|scope| {
            let start_commit = Arc::clone(&start);
            let core_ref = &core;
            let token_ref = &token;
            let commit = scope.spawn(move || {
                start_commit.wait();
                core_ref.commit(token_ref, publisher(), 1).unwrap()
            });
            let start_refusal = Arc::clone(&start);
            let refusal = scope.spawn(move || {
                start_refusal.wait();
                core_ref
                    .publish(
                        token_ref,
                        publisher(),
                        PublishOutcome::Failure {
                            status: DeliveryStatus::Revoked,
                        },
                    )
                    .unwrap()
            });
            start.wait();
            let committed = commit.join().unwrap();
            assert_eq!(committed, refusal.join().unwrap());
            assert_eq!(
                core.query_delivery(&core.delivery_view(), 1).unwrap(),
                committed
            );
            match committed.status {
                Some(DeliveryStatus::Ok) => {
                    assert_eq!(target.revision(), 2);
                    assert_eq!(target.budget().cap_ns, 7);
                }
                Some(DeliveryStatus::Revoked) => {
                    assert_eq!(target.revision(), 1);
                    assert_eq!(target.budget().cap_ns, CPU_PERIOD_NS);
                }
                other => panic!("unexpected final status: {other:?}"),
            }
        });
        core.validate_invariants_for_host_model().unwrap();
    }
}

#[test]
fn identical_public_namespace_bytes_never_transfer_observer_owner_or_publisher_authority() {
    let (core, authority) = core(720_001);
    let (alien, alien_authority) = ControlCore::with_original_owner(
        core.identity().boot_id(),
        core.identity().cap_space_id(),
        owner(),
    )
    .unwrap();
    let other_boot = ControlCore::new(BootId::from_u128(720_002), core.identity().cap_space_id());
    let other_space = ControlCore::new(core.identity().boot_id(), CapSpaceId::from_u128(720_002));
    let target = target(720_001);
    let token = core
        .reserve(
            DeliveryRequest::new(1, target.grant(publisher()).unwrap(), 1, 7),
            publisher(),
        )
        .unwrap();
    let view = core.delivery_view_for(owner()).unwrap();
    let terminal = core.commit(&token, publisher(), 1).unwrap();
    for foreign in [&alien, &other_boot, &other_space] {
        assert_eq!(
            foreign.query_delivery(&view, 1),
            Err(DeliveryError::PermissionDenied)
        );
        assert_eq!(
            foreign.commit(&token, publisher(), 1),
            Err(DeliveryError::PermissionDenied)
        );
        assert_eq!(
            foreign.retire_through(&view, ack(&authority, 1), &authority),
            Err(DeliveryError::PermissionDenied)
        );
    }
    assert_eq!(
        core.query_delivery(&alien.delivery_view(), 1),
        Err(DeliveryError::PermissionDenied)
    );
    assert_eq!(
        core.retire_through(&view, ack(&authority, 1), &alien_authority),
        Err(DeliveryError::PermissionDenied)
    );
    assert_eq!(core.query_delivery(&view, 1).unwrap(), terminal);
    assert_eq!(core.retired_through(), 0);
    assert_eq!(target.revision(), 2);
}

#[test]
fn simultaneous_wrong_publishers_cannot_win_against_reservation_owner() {
    for iteration in 0..32 {
        let (core, _) = core(730_000 + iteration);
        let target = target(730_000 + iteration);
        let token = core
            .reserve(
                DeliveryRequest::new(1, target.grant(publisher()).unwrap(), 1, 7),
                publisher(),
            )
            .unwrap();
        let start = Arc::new(Barrier::new(9));
        thread::scope(|scope| {
            let mut intruders = Vec::new();
            for id in 3..=10 {
                let start = Arc::clone(&start);
                let core = &core;
                let token = &token;
                intruders.push(scope.spawn(move || {
                    start.wait();
                    assert_eq!(
                        core.publish(
                            token,
                            PublisherId::from_u128(id),
                            PublishOutcome::Failure {
                                status: DeliveryStatus::PermissionDenied
                            },
                        ),
                        Err(DeliveryError::PermissionDenied)
                    );
                    assert_eq!(
                        core.commit(token, PublisherId::from_u128(id), 1),
                        Err(DeliveryError::PermissionDenied)
                    );
                }));
            }
            start.wait();
            assert_eq!(
                core.commit(&token, publisher(), 1).unwrap().status,
                Some(DeliveryStatus::Ok)
            );
            for intruder in intruders {
                intruder.join().unwrap();
            }
        });
        assert_eq!(target.revision(), 2);
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1)
                .unwrap()
                .status,
            Some(DeliveryStatus::Ok)
        );
        core.validate_invariants_for_host_model().unwrap();
    }
}

#[test]
fn pending_copyout_retry_and_loss_race_never_grant_a_second_execution() {
    for iteration in 0..128 {
        let (core, _) = core(740_000 + iteration);
        let target = target(740_000 + iteration);
        let request = DeliveryRequest::new(1, target.grant(publisher()).unwrap(), 1, 7);
        let token = core.reserve(request.clone(), publisher()).unwrap();
        let start = Arc::new(Barrier::new(4));
        thread::scope(|scope| {
            let start_commit = Arc::clone(&start);
            let core_ref = &core;
            let commit = scope.spawn(move || {
                start_commit.wait();
                core_ref.commit(&token, publisher(), 1)
            });
            let start_loss = Arc::clone(&start);
            let loss = scope.spawn(move || {
                start_loss.wait();
                core_ref.lose_history();
            });
            let start_retry = Arc::clone(&start);
            let retry = scope.spawn(move || {
                start_retry.wait();
                match core_ref.reserve_or_get(request, publisher()) {
                    Ok(ReserveAttempt::Existing(observation)) => {
                        assert!(matches!(
                            observation.state,
                            DeliveryState::Reserved | DeliveryState::Terminal
                        ));
                    }
                    Err(DeliveryError::HistoryLost) => {}
                    _ => panic!("copyout retry cannot acquire a new execution token"),
                }
            });
            start.wait();
            match commit.join().unwrap() {
                Ok(terminal) => {
                    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
                    assert_eq!(target.revision(), 2);
                }
                Err(DeliveryError::HistoryLost) => assert_eq!(target.revision(), 1),
                other => panic!("unexpected commit/loss order: {other:?}"),
            }
            loss.join().unwrap();
            retry.join().unwrap();
        });
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1).unwrap().state,
            DeliveryState::HistoryLost
        );
        assert_eq!(core.window_len(), 0);
        core.validate_invariants_for_host_model().unwrap();
    }
}

#[test]
fn concurrent_retire_query_and_loss_keep_history_monotonic_and_complete() {
    for iteration in 0..64 {
        let (core, authority) = core(750_000 + iteration);
        let target = target(750_000 + iteration);
        let token = core
            .reserve(
                DeliveryRequest::new(1, target.grant(publisher()).unwrap(), 1, 7),
                publisher(),
            )
            .unwrap();
        let terminal = core.commit(&token, publisher(), 1).unwrap();
        let view = core.delivery_view_for(owner()).unwrap();
        let start = Arc::new(Barrier::new(4));
        thread::scope(|scope| {
            let start_retire = Arc::clone(&start);
            let core_ref = &core;
            let view_ref = &view;
            let retire = scope.spawn(move || {
                start_retire.wait();
                match core_ref.retire_through(view_ref, ack(&authority, 1), &authority) {
                    Ok(receipt) => {
                        assert_eq!(receipt.retired_through, 1);
                        assert_eq!(receipt.next_sequence, 2);
                    }
                    Err(DeliveryError::HistoryLost) => {}
                    other => panic!("unexpected retirement/loss order: {other:?}"),
                }
            });
            let start_loss = Arc::clone(&start);
            let loss = scope.spawn(move || {
                start_loss.wait();
                core_ref.lose_history();
            });
            let start_query = Arc::clone(&start);
            let query = scope.spawn(move || {
                start_query.wait();
                let mut last_rank = 0;
                for _ in 0..128 {
                    let observation = core_ref.query_delivery(view_ref, 1).unwrap();
                    let rank = match observation.state {
                        DeliveryState::Terminal => {
                            assert_eq!(observation, terminal);
                            0
                        }
                        DeliveryState::Retired => 1,
                        DeliveryState::HistoryLost => 2,
                        state => panic!("committed D cannot become {state:?}"),
                    };
                    assert!(rank >= last_rank, "history state regressed");
                    assert_eq!(observation.hos2_saved_status_code(), Some(0));
                    if rank != 0 {
                        assert!(observation.stable_object_id.is_none());
                        assert!(observation.saved_revision.is_none());
                        assert!(observation.previous_revision.is_none());
                        assert!(observation.effective_ns.is_none());
                        assert!(observation.consumed_ns.is_none());
                    }
                    last_rank = rank;
                }
            });
            start.wait();
            retire.join().unwrap();
            loss.join().unwrap();
            query.join().unwrap();
        });
        assert_eq!(target.revision(), 2);
        assert_eq!(core.window_len(), 0);
        assert_eq!(
            core.query_delivery(&view, 1).unwrap().state,
            DeliveryState::HistoryLost
        );
        core.validate_invariants_for_host_model().unwrap();
    }
}

#[test]
fn matching_owner_receipt_without_namespace_tag_cannot_retire_terminal_result() {
    let (core, authority) = core(760_500);
    let target = target(760_500);
    let grant = target.grant(publisher()).unwrap();
    let token = core
        .reserve(DeliveryRequest::new(1, grant, 1, 7), publisher())
        .unwrap();
    core.commit(&token, publisher(), 1).unwrap();
    let view = core.delivery_view_for(owner()).unwrap();
    let forged = HistoryAck::from_owner_receipt(
        core.identity(),
        1,
        os_control::OwnerReceipt::new(owner(), [0xD4; 32]),
    )
    .unwrap();
    assert_eq!(
        core.retire_through(&view, forged, &authority),
        Err(DeliveryError::PermissionDenied)
    );
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Terminal
    );
    core.retire_through(
        &view,
        authority.history_ack(1, [0xD4; 32]).unwrap(),
        &authority,
    )
    .unwrap();
}

#[test]
fn dropped_namespace_receipt_cannot_retire_recreated_namespace() {
    let old_ack = {
        let (_old_core, old_authority) = core(760_501);
        old_authority.history_ack(1, [0xD4; 32]).unwrap()
    };
    // A copied acknowledgement can outlive every handle to its namespace.
    // Reusing those wire identities must not authenticate an old receipt,
    // including when the allocator reuses the old NamespaceState address.
    for _ in 0..32 {
        let (core, authority) = core(760_501);
        let target = target(760_501);
        let token = core
            .reserve(
                DeliveryRequest::new(1, target.grant(publisher()).unwrap(), 1, 7),
                publisher(),
            )
            .unwrap();
        core.commit(&token, publisher(), 1).unwrap();
        let view = core.delivery_view_for(owner()).unwrap();
        assert_eq!(
            core.retire_through(&view, old_ack, &authority),
            Err(DeliveryError::PermissionDenied)
        );
        assert_eq!(
            core.query_delivery(&view, 1).unwrap().state,
            DeliveryState::Terminal
        );
        core.retire_through(&view, ack(&authority, 1), &authority)
            .unwrap();
    }
}
