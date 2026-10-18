//! Host simulations for the A05 one-shot kernel handoff API.
//!
//! Atomic counters stand in for external effects. No callback invokes a real
//! kernel, re-enters ControlCore, proves credentials or persists a Hepta K.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryRequest, DeliveryState, DeliveryStatus,
    HistoryAck, OriginalOwnerAuthority, OwnerId, PublishOutcome, PublisherId,
    RequestBinding, ReserveAttempt, ResourceDomain, ResourceDomainId, StableObjectId,
    CPU_PERIOD_NS,
};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Barrier};
use std::thread;

fn publisher() -> PublisherId {
    PublisherId::from_u128(8_001)
}

fn owner() -> OwnerId {
    OwnerId::from_u128(8_002)
}

fn core(n: u128) -> (ControlCore, OriginalOwnerAuthority) {
    ControlCore::with_original_owner(BootId::from_u128(n), CapSpaceId::from_u128(n), owner())
        .unwrap()
}

fn request(n: u128) -> DeliveryRequest {
    let target = ResourceDomain::new(
        ResourceDomainId::from_u128(n),
        StableObjectId::from_u128(n),
        None,
        CPU_PERIOD_NS,
    )
    .unwrap();
    DeliveryRequest::from_wire(1, target.grant(publisher()).unwrap(), 1, 17, 9, 11)
        .unwrap()
        .with_payload_digest([0x22; 32])
}

fn success(binding: RequestBinding) -> PublishOutcome {
    PublishOutcome::Success {
        stable_object_id: binding.stable_object_id,
        previous_revision: binding.expected_revision,
        saved_revision: binding.expected_revision + 1,
        effective_ns: 1,
        consumed_ns: 0,
    }
}

fn ack(authority: &OriginalOwnerAuthority) -> HistoryAck {
    authority.history_ack(1, [0x55; 32]).unwrap()
}

#[test]
fn duplicate_handoff_invokes_once_and_receives_exact_canonical_binding() {
    let (core, _) = core(810_001);
    let request = request(810_001);
    let expected = request.binding();
    let token = core.reserve(request.clone(), publisher()).unwrap();
    let effects = AtomicUsize::new(0);
    let terminal = core
        .execute_reserved(&token, publisher(), |binding| {
            assert_eq!(binding, expected);
            assert_eq!(binding.wire_target_slot, 9);
            assert_eq!(binding.wire_target_generation, 11);
            assert_eq!(binding.payload_digest, [0x22; 32]);
            assert_eq!(effects.fetch_add(1, Ordering::SeqCst), 0);
            success(binding)
        })
        .unwrap();
    assert_eq!(terminal.state, DeliveryState::Terminal);
    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
    for _ in 0..32 {
        assert_eq!(
            core.execute_reserved(&token, publisher(), |_| {
                effects.fetch_add(1, Ordering::SeqCst);
                panic!("terminal retry invoked external executor")
            })
            .unwrap(),
            terminal
        );
        match core.reserve_or_get(request.clone(), publisher()).unwrap() {
            ReserveAttempt::Existing(observation) => assert_eq!(observation, terminal),
            ReserveAttempt::Reserved(_) => panic!("retry granted another executor"),
        }
    }
    assert_eq!(effects.load(Ordering::SeqCst), 1);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn simultaneous_handoffs_of_same_token_invoke_exactly_one_callback() {
    for iteration in 0..64 {
        let (core, _) = core(820_000 + iteration);
        let core = Arc::new(core);
        let token = Arc::new(
            core.reserve(request(820_000 + iteration), publisher())
                .unwrap(),
        );
        let effects = Arc::new(AtomicUsize::new(0));
        let start = Arc::new(Barrier::new(9));
        let mut executors = Vec::new();
        for _ in 0..8 {
            let core = Arc::clone(&core);
            let token = Arc::clone(&token);
            let effects = Arc::clone(&effects);
            let start = Arc::clone(&start);
            executors.push(thread::spawn(move || {
                start.wait();
                core.execute_reserved(&token, publisher(), |binding| {
                    assert_eq!(effects.fetch_add(1, Ordering::SeqCst), 0);
                    thread::yield_now();
                    success(binding)
                })
                .unwrap()
            }));
        }
        start.wait();
        let terminal = executors.remove(0).join().unwrap();
        for executor in executors {
            assert_eq!(executor.join().unwrap(), terminal);
        }
        assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
        assert_eq!(effects.load(Ordering::SeqCst), 1);
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1).unwrap(),
            terminal
        );
        core.validate_invariants_for_host_model().unwrap();
    }
}

#[test]
fn wrong_publisher_and_foreign_namespace_never_enter_callback() {
    let (core, _) = core(830_001);
    let foreign = ControlCore::new(core.identity().boot_id(), core.identity().cap_space_id());
    let token = core.reserve(request(830_001), publisher()).unwrap();
    let effects = AtomicUsize::new(0);
    let wrong = PublisherId::from_u128(8_099);
    for (executor, principal) in [(&core, wrong), (&foreign, publisher())] {
        assert_eq!(
            executor.execute_reserved(&token, principal, |binding| {
                effects.fetch_add(1, Ordering::SeqCst);
                success(binding)
            }),
            Err(DeliveryError::PermissionDenied)
        );
    }
    assert_eq!(effects.load(Ordering::SeqCst), 0);
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::Reserved
    );
    assert_eq!(
        core.execute_reserved(&token, publisher(), success)
            .unwrap()
            .status,
        Some(DeliveryStatus::Ok)
    );
}

#[test]
fn namespace_loss_before_handoff_fences_external_callback() {
    let (core, _) = core(840_001);
    let token = core.reserve(request(840_001), publisher()).unwrap();
    let effects = AtomicUsize::new(0);
    core.lose_history();
    assert_eq!(
        core.execute_reserved(&token, publisher(), |binding| {
            effects.fetch_add(1, Ordering::SeqCst);
            success(binding)
        }),
        Err(DeliveryError::HistoryLost)
    );
    assert_eq!(effects.load(Ordering::SeqCst), 0);
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::HistoryLost
    );
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn handoff_entered_before_namespace_loss_finishes_one_effect_then_history_is_lost() {
    let (core, _) = core(850_001);
    let token = core.reserve(request(850_001), publisher()).unwrap();
    let effects = AtomicUsize::new(0);
    let (entered_send, entered_recv) = mpsc::channel();
    let (release_send, release_recv) = mpsc::channel();
    let (loss_started_send, loss_started_recv) = mpsc::channel();
    thread::scope(|scope| {
        let core_ref = &core;
        let effects_ref = &effects;
        let execute = scope.spawn(move || {
            core_ref.execute_reserved(&token, publisher(), |binding| {
                entered_send.send(()).unwrap();
                release_recv.recv().unwrap();
                effects_ref.fetch_add(1, Ordering::SeqCst);
                success(binding)
            })
        });
        entered_recv.recv().unwrap();
        let loss = scope.spawn(move || {
            loss_started_send.send(()).unwrap();
            core_ref.lose_history();
        });
        loss_started_recv.recv().unwrap();
        release_send.send(()).unwrap();
        let terminal = execute.join().unwrap().unwrap();
        assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
        loss.join().unwrap();
    });
    assert_eq!(effects.load(Ordering::SeqCst), 1);
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::HistoryLost
    );
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn panicking_callback_preserves_pending_prefix_and_cannot_be_executed_again() {
    let (core, authority) = core(860_001);
    let request = request(860_001);
    let token = core.reserve(request.clone(), publisher()).unwrap();
    let effects = AtomicUsize::new(0);
    assert!(catch_unwind(AssertUnwindSafe(|| {
        core.execute_reserved(&token, publisher(), |_| {
            effects.fetch_add(1, Ordering::SeqCst);
            panic!("injected failure after simulated external effect")
        })
    }))
    .is_err());
    let view = core.delivery_view_for(owner()).unwrap();
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Reserved
    );
    assert_eq!(
        core.retire_through(&view, ack(&authority), &authority),
        Err(DeliveryError::PendingPrefix)
    );
    assert_eq!(core.retired_through(), 0);
    assert_eq!(
        core.execute_reserved(&token, publisher(), |binding| {
            effects.fetch_add(1, Ordering::SeqCst);
            success(binding)
        }),
        Err(DeliveryError::Busy)
    );
    assert_eq!(
        core.commit(&token, publisher(), 1),
        Err(DeliveryError::Busy)
    );
    match core.reserve_or_get(request, publisher()).unwrap() {
        ReserveAttempt::Existing(observation) => {
            assert_eq!(observation.state, DeliveryState::Reserved)
        }
        ReserveAttempt::Reserved(_) => panic!("panic recovery granted another effect"),
    }
    assert_eq!(effects.load(Ordering::SeqCst), 1);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn invalid_callback_receipts_stay_pending_and_never_allow_another_effect() {
    for case in 0..7_u128 {
        let (core, authority) = core(870_000 + case);
        let token = core.reserve(request(870_000 + case), publisher()).unwrap();
        let effects = AtomicUsize::new(0);
        assert_eq!(
            core.execute_reserved(&token, publisher(), |binding| {
                effects.fetch_add(1, Ordering::SeqCst);
                match case {
                    0 => PublishOutcome::Success {
                        stable_object_id: StableObjectId::from_u128(999_999),
                        previous_revision: 1,
                        saved_revision: 2,
                        effective_ns: 1,
                        consumed_ns: 0,
                    },
                    1 => PublishOutcome::Success {
                        stable_object_id: binding.stable_object_id,
                        previous_revision: 2,
                        saved_revision: 3,
                        effective_ns: 1,
                        consumed_ns: 0,
                    },
                    2 => PublishOutcome::Success {
                        stable_object_id: binding.stable_object_id,
                        previous_revision: 1,
                        saved_revision: 3,
                        effective_ns: 1,
                        consumed_ns: 0,
                    },
                    3 => PublishOutcome::Success {
                        stable_object_id: binding.stable_object_id,
                        previous_revision: 1,
                        saved_revision: 2,
                        effective_ns: 1,
                        consumed_ns: 2,
                    },
                    4 => PublishOutcome::Failure {
                        status: DeliveryStatus::Ok,
                    },
                    5 => PublishOutcome::Failure {
                        status: DeliveryStatus::OutOfOrder,
                    },
                    6 => PublishOutcome::Failure {
                        status: DeliveryStatus::Retired,
                    },
                    _ => unreachable!(),
                }
            }),
            Err(DeliveryError::InvalidPublish)
        );
        let view = core.delivery_view_for(owner()).unwrap();
        assert_eq!(
            core.query_delivery(&view, 1).unwrap().state,
            DeliveryState::Reserved
        );
        assert_eq!(
            core.retire_through(&view, ack(&authority), &authority),
            Err(DeliveryError::PendingPrefix)
        );
        assert_eq!(
            core.execute_reserved(&token, publisher(), |binding| {
                effects.fetch_add(1, Ordering::SeqCst);
                success(binding)
            }),
            Err(DeliveryError::Busy)
        );
        assert_eq!(
            core.commit(&token, publisher(), 1),
            Err(DeliveryError::Busy)
        );
        assert_eq!(effects.load(Ordering::SeqCst), 1);
        assert_eq!(core.retired_through(), 0);
        core.validate_invariants_for_host_model().unwrap();
    }
}

#[test]
fn trusted_external_fence_can_publish_recovered_receipt_without_reexecuting() {
    let (core, authority) = core(880_001);
    let token = core.reserve(request(880_001), publisher()).unwrap();
    let effects = AtomicUsize::new(0);
    assert!(catch_unwind(AssertUnwindSafe(|| {
        core.execute_reserved(&token, publisher(), |_| {
            effects.fetch_add(1, Ordering::SeqCst);
            panic!("external execution acknowledged through independent trusted recovery")
        })
    }))
    .is_err());
    // The host simulated executor has exited and the test has independently
    // observed its counter. This is the trusted fence/receipt precondition;
    // a caller-supplied HOS2 boolean would not establish it in a real kernel.
    assert_eq!(effects.load(Ordering::SeqCst), 1);
    let terminal = core
        .publish(&token, publisher(), success(token.binding()))
        .unwrap();
    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
    assert_eq!(
        core.execute_reserved(&token, publisher(), |_| panic!("recovered effect replayed"))
            .unwrap(),
        terminal
    );
    assert_eq!(core.commit(&token, publisher(), 1).unwrap(), terminal);
    let view = core.delivery_view_for(owner()).unwrap();
    assert_eq!(
        core.retire_through(&view, ack(&authority), &authority)
            .unwrap()
            .retired_through,
        1
    );
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Retired
    );
    assert_eq!(effects.load(Ordering::SeqCst), 1);
    core.validate_invariants_for_host_model().unwrap();
}
