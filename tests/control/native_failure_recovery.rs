//! Native-owner failure recovery on host threads. These deliberately bounded
//! schedules do not enumerate all interleavings or exercise a real kernel,
//! scheduler, ioctl, interrupt lock, device or durable Hepta owner.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryObservation, DeliveryState,
    DeliveryStatus, HistoryAck, NativeDeliveryRequest, NativeGrant, NativeTarget,
    OriginalOwnerAuthority, OwnerId, OwnerReceipt, PublishOutcome, PublisherId, RequestBinding,
    ReserveToken, ResourceDomainId, StableObjectId, CPU_PERIOD_NS,
};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Barrier, Mutex, MutexGuard};
use std::thread;

fn publisher() -> PublisherId {
    PublisherId::from_u128(1_500_001)
}

fn owner_id() -> OwnerId {
    OwnerId::from_u128(1_500_002)
}

struct OwnerState {
    revision: u64,
    cap_ns: u64,
    effects: usize,
}

struct NativeOwner {
    id: ResourceDomainId,
    object: StableObjectId,
    mutation: Mutex<OwnerState>,
    drops: Arc<AtomicUsize>,
    panic_on_drop: bool,
}

impl NativeOwner {
    fn new(n: u128, panic_on_drop: bool) -> (Arc<Self>, Arc<AtomicUsize>) {
        let drops = Arc::new(AtomicUsize::new(0));
        (
            Arc::new(Self {
                id: ResourceDomainId::from_u128(n),
                object: StableObjectId::from_u128(n),
                mutation: Mutex::new(OwnerState {
                    revision: 1,
                    cap_ns: CPU_PERIOD_NS,
                    effects: 0,
                }),
                drops: Arc::clone(&drops),
                panic_on_drop,
            }),
            drops,
        )
    }

    fn state_after_fence(&self) -> MutexGuard<'_, OwnerState> {
        self.mutation
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    fn effect_then_panic(&self, binding: RequestBinding) -> PublishOutcome {
        let mut state = self.mutation.lock().unwrap();
        assert_eq!(binding.target, self.id);
        assert_eq!(binding.stable_object_id, self.object);
        assert_eq!(binding.expected_revision, state.revision);
        assert_eq!(state.effects, 0);
        state.cap_ns = binding.cap_ns;
        state.revision += 1;
        state.effects += 1;
        // The real mutation and its count are already committed, but no
        // delivery receipt has been returned. This poisons the owner's own
        // mutex as well as the delivery's one-shot execution gate on std.
        panic!("injected native failure after one external effect");
    }

    fn recover_receipt_after_fence(&self, binding: RequestBinding) -> PublishOutcome {
        // The test joined/caught the original synchronous executor before
        // taking this snapshot. Recovering the poisoned lock never retries
        // the resource mutation or guesses a no-effect refusal.
        let state = self.state_after_fence();
        assert_eq!(binding.target, self.id);
        assert_eq!(binding.stable_object_id, self.object);
        assert_eq!(state.revision, binding.expected_revision + 1);
        assert_eq!(state.cap_ns, binding.cap_ns);
        assert_eq!(state.effects, 1);
        PublishOutcome::Success {
            stable_object_id: self.object,
            previous_revision: binding.expected_revision,
            saved_revision: state.revision,
            effective_ns: 1,
            consumed_ns: 0,
        }
    }
}

impl Drop for NativeOwner {
    fn drop(&mut self) {
        self.drops.fetch_add(1, Ordering::SeqCst);
        if self.panic_on_drop {
            panic!("injected native-owner destructor failure");
        }
    }
}

fn fixture(n: u128) -> (ControlCore, OriginalOwnerAuthority) {
    ControlCore::with_original_owner(BootId::from_u128(n), CapSpaceId::from_u128(n), owner_id())
        .unwrap()
}

fn reserve(core: &ControlCore, owner: Arc<NativeOwner>, sequence: u64) -> ReserveToken {
    let target = NativeTarget::from_owner(Arc::clone(&owner), owner.id, owner.object).unwrap();
    let grant = NativeGrant::from_owner(target, publisher(), 1, vec![1]).unwrap();
    let request = NativeDeliveryRequest::from_wire(sequence, grant, 1, 17, 7, 11).unwrap();
    core.reserve_native(request, publisher()).unwrap()
}

fn ack(core: &ControlCore, through: u64) -> HistoryAck {
    HistoryAck::from_owner_receipt(
        core.identity(),
        through,
        OwnerReceipt::new(owner_id(), [0x59; 32]),
    )
    .unwrap()
}

fn assert_without_saved_result(observation: DeliveryObservation, state: DeliveryState) {
    assert_eq!(observation.state, state);
    assert!(observation.status.is_none());
    assert!(observation.stable_object_id.is_none());
    assert!(observation.saved_revision.is_none());
    assert!(observation.previous_revision.is_none());
    assert!(observation.effective_ns.is_none());
    assert!(observation.consumed_ns.is_none());
    assert_eq!(observation.hos2_saved_status_code(), Some(0));
}

#[test]
fn poisoned_native_effect_recovers_or_loses_history_without_second_effect_in_64_schedules() {
    for iteration in 0..64_u128 {
        let (core, authority) = fixture(1_510_000 + iteration);
        let (owner, _) = NativeOwner::new(1_520_000 + iteration, false);
        let token = reserve(&core, Arc::clone(&owner), 1);
        assert!(catch_unwind(AssertUnwindSafe(|| {
            core.execute_native_reserved::<NativeOwner, _>(&token, publisher(), |context| {
                assert_eq!(context.ancestor_epochs(), &[1]);
                context.owner().effect_then_panic(context.binding())
            })
        }))
        .is_err());
        assert!(owner.mutation.is_poisoned());
        {
            let state = owner.state_after_fence();
            assert_eq!(state.effects, 1);
            assert_eq!(state.revision, 2);
            assert_eq!(state.cap_ns, 17);
        }
        let view = core.delivery_view_for(owner_id()).unwrap();
        assert_without_saved_result(
            core.query_delivery(&view, 1).unwrap(),
            DeliveryState::Reserved,
        );
        assert_eq!(
            core.retire_through(&view, ack(&core, 1), &authority),
            Err(DeliveryError::PendingPrefix)
        );
        assert_eq!(core.retired_through(), 0);
        assert_eq!(
            core.execute_native_reserved::<NativeOwner, _>(&token, publisher(), |_| {
                panic!("poison recovery reentered the resource executor")
            }),
            Err(DeliveryError::Busy)
        );

        let start = Barrier::new(4);
        thread::scope(|scope| {
            let recover = scope.spawn(|| {
                start.wait();
                let receipt = owner.recover_receipt_after_fence(token.binding());
                core.publish(&token, publisher(), receipt)
            });
            let loss = scope.spawn(|| {
                start.wait();
                core.lose_history();
            });
            let inspect = scope.spawn(|| {
                start.wait();
                let observation = core.query_delivery(&view, 1).unwrap();
                match observation.state {
                    DeliveryState::Reserved | DeliveryState::HistoryLost => {
                        assert_without_saved_result(observation, observation.state);
                    }
                    DeliveryState::Terminal => {
                        assert_eq!(observation.status, Some(DeliveryStatus::Ok));
                        assert_eq!(observation.stable_object_id, Some(owner.object));
                        assert_eq!(observation.previous_revision, Some(1));
                        assert_eq!(observation.saved_revision, Some(2));
                        assert_eq!(observation.effective_ns, Some(1));
                        assert_eq!(observation.consumed_ns, Some(0));
                    }
                    other => panic!("unretired reserved D became {other:?}"),
                }
                let retirement = core.retire_through(&view, ack(&core, 1), &authority);
                match observation.state {
                    DeliveryState::Reserved => assert!(matches!(
                        retirement,
                        Ok(_) | Err(DeliveryError::PendingPrefix | DeliveryError::HistoryLost)
                    )),
                    DeliveryState::Terminal => assert!(matches!(
                        retirement,
                        Ok(_) | Err(DeliveryError::HistoryLost)
                    )),
                    DeliveryState::HistoryLost => {
                        assert_eq!(retirement, Err(DeliveryError::HistoryLost));
                    }
                    _ => unreachable!(),
                }
                if let Ok(receipt) = retirement {
                    assert_eq!(receipt.retired_through, 1);
                    assert_eq!(receipt.next_sequence, 2);
                }
            });
            start.wait();
            let recovered = recover.join().unwrap();
            assert!(matches!(recovered, Ok(_) | Err(DeliveryError::HistoryLost)));
            if let Ok(observation) = recovered {
                assert_eq!(observation.state, DeliveryState::Terminal);
                assert_eq!(observation.status, Some(DeliveryStatus::Ok));
                assert_eq!(observation.saved_revision, Some(2));
            }
            loss.join().unwrap();
            inspect.join().unwrap();
        });
        {
            let state = owner.state_after_fence();
            assert_eq!(state.effects, 1);
            assert_eq!(state.revision, 2);
            assert_eq!(state.cap_ns, 17);
        }
        assert_eq!(
            core.execute_native_reserved::<NativeOwner, _>(&token, publisher(), |_| {
                panic!("lost poisoned native D obtained a second execution")
            }),
            Err(DeliveryError::HistoryLost)
        );
        assert_without_saved_result(
            core.query_delivery(&view, 1).unwrap(),
            DeliveryState::HistoryLost,
        );
        assert_eq!(core.window_len(), 0);
        assert_eq!(core.next_sequence(), 2);
        core.validate_invariants_for_host_model().unwrap();
    }
}

#[test]
fn retirement_drop_panic_preserves_frontier_and_releases_remaining_retired_owners() {
    let (core, authority) = fixture(1_530_001);
    let (first, first_drops) = NativeOwner::new(1_530_011, true);
    let first_token = reserve(&core, first, 1);
    let (second, second_drops) = NativeOwner::new(1_530_012, false);
    let second_token = reserve(&core, second, 2);
    let (pending, pending_drops) = NativeOwner::new(1_530_013, false);
    let _pending_token = reserve(&core, pending, 3);
    for token in [&first_token, &second_token] {
        core.publish(
            token,
            publisher(),
            PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            },
        )
        .unwrap();
    }
    let view = core.delivery_view_for(owner_id()).unwrap();
    assert!(catch_unwind(AssertUnwindSafe(|| {
        core.retire_through(&view, ack(&core, 2), &authority)
    }))
    .is_err());
    assert_eq!(first_drops.load(Ordering::SeqCst), 1);
    assert_eq!(second_drops.load(Ordering::SeqCst), 1);
    assert_eq!(pending_drops.load(Ordering::SeqCst), 0);
    assert_eq!(core.retired_through(), 2);
    assert_eq!(core.next_sequence(), 4);
    assert_eq!(core.window_len(), 1);
    for sequence in 1..=2 {
        assert_without_saved_result(
            core.query_delivery(&view, sequence).unwrap(),
            DeliveryState::Retired,
        );
    }
    assert_without_saved_result(
        core.query_delivery(&view, 3).unwrap(),
        DeliveryState::Reserved,
    );
    assert_eq!(
        core.retire_through(&view, ack(&core, 2), &authority)
            .unwrap()
            .retired_through,
        2
    );
    core.validate_invariants_for_host_model().unwrap();
    core.lose_history();
    assert_eq!(pending_drops.load(Ordering::SeqCst), 1);
    assert_without_saved_result(
        core.query_delivery(&view, 3).unwrap(),
        DeliveryState::HistoryLost,
    );
}

#[test]
fn loss_drop_panic_keeps_history_lost_releases_remaining_owners_and_is_idempotent() {
    let (core, authority) = fixture(1_540_001);
    let (first, first_drops) = NativeOwner::new(1_540_011, true);
    let first_token = reserve(&core, first, 1);
    let (second, second_drops) = NativeOwner::new(1_540_012, false);
    let second_token = reserve(&core, second, 2);
    let (third, third_drops) = NativeOwner::new(1_540_013, false);
    let third_token = reserve(&core, third, 3);
    let view = core.delivery_view_for(owner_id()).unwrap();
    assert!(catch_unwind(AssertUnwindSafe(|| core.lose_history())).is_err());
    for drops in [&first_drops, &second_drops, &third_drops] {
        assert_eq!(drops.load(Ordering::SeqCst), 1);
    }
    assert_eq!(core.window_len(), 0);
    assert_eq!(core.next_sequence(), 4);
    assert_eq!(core.retired_through(), 0);
    for sequence in 1..=3 {
        assert_without_saved_result(
            core.query_delivery(&view, sequence).unwrap(),
            DeliveryState::HistoryLost,
        );
    }
    core.lose_history();
    assert_eq!(
        core.retire_through(&view, ack(&core, 3), &authority),
        Err(DeliveryError::HistoryLost)
    );
    for token in [&first_token, &second_token, &third_token] {
        assert_eq!(
            core.execute_native_reserved::<NativeOwner, _>(token, publisher(), |_| {
                panic!("owner Drop panic reopened a lost native D")
            }),
            Err(DeliveryError::HistoryLost)
        );
    }
    for drops in [&first_drops, &second_drops, &third_drops] {
        assert_eq!(drops.load(Ordering::SeqCst), 1);
    }
    core.validate_invariants_for_host_model().unwrap();
}
