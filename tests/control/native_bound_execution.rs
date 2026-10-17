//! Bound native-owner callbacks, exercised only by synthetic host owners.
//!
//! The callback obtains the actual reservation-pinned owner and immutable
//! ancestor snapshot from A03. Its original mutation lock still implements
//! grant revalidation and the only budget/revision state. These tests do not
//! validate real kernel credentials, IRQ locks, copyout or Hepta persistence.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryRequest, DeliveryState, DeliveryStatus,
    HistoryAck, NativeDeliveryRequest, NativeGrant, NativeTarget, OriginalOwnerAuthority, OwnerId,
    OwnerReceipt, PublishOutcome, PublisherId, RequestBinding, ResourceDomain, ResourceDomainId,
    StableObjectId, CPU_PERIOD_NS, MAX_RESOURCE_DEPTH,
};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Barrier, Mutex};
use std::thread;

fn publisher() -> PublisherId {
    PublisherId::from_u128(1_200_001)
}

fn durable_owner() -> OwnerId {
    OwnerId::from_u128(1_200_002)
}

fn core(n: u128) -> (ControlCore, OriginalOwnerAuthority) {
    ControlCore::with_original_owner(
        BootId::from_u128(n),
        CapSpaceId::from_u128(n),
        durable_owner(),
    )
    .unwrap()
}

struct BoundOwner {
    id: ResourceDomainId,
    object: StableObjectId,
    mutation: Mutex<OwnerState>,
}

struct OwnerState {
    revision: u64,
    cap_ns: u64,
    grant_epoch: u64,
    ancestor_epochs: Vec<u64>,
    alive: bool,
    effects: usize,
}

impl BoundOwner {
    fn new(n: u128, ancestor_epochs: Vec<u64>) -> Arc<Self> {
        Arc::new(Self {
            id: ResourceDomainId::from_u128(n),
            object: StableObjectId::from_u128(n),
            mutation: Mutex::new(OwnerState {
                revision: 1,
                cap_ns: CPU_PERIOD_NS,
                grant_epoch: 1,
                ancestor_epochs,
                alive: true,
                effects: 0,
            }),
        })
    }

    fn request(self: &Arc<Self>) -> NativeDeliveryRequest {
        let state = self.mutation.lock().unwrap();
        let target = NativeTarget::from_owner(Arc::clone(self), self.id, self.object).unwrap();
        let grant = NativeGrant::from_owner(
            target,
            publisher(),
            state.grant_epoch,
            state.ancestor_epochs.clone(),
        )
        .unwrap();
        NativeDeliveryRequest::from_wire(1, grant, state.revision, 17, 11, 5)
            .unwrap()
            .with_payload_digest([0x57; 32])
    }

    fn apply(&self, binding: RequestBinding, ancestor_epochs: &[u64]) -> PublishOutcome {
        let mut state = self.mutation.lock().unwrap();
        assert_eq!(binding.target, self.id);
        assert_eq!(binding.stable_object_id, self.object);
        assert_eq!(binding.publisher, publisher());
        assert_eq!(binding.period_ns, CPU_PERIOD_NS);
        if !state.alive
            || state.grant_epoch != binding.grant_epoch
            || state.ancestor_epochs != ancestor_epochs
        {
            return PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            };
        }
        if state.revision != binding.expected_revision {
            return PublishOutcome::Failure {
                status: DeliveryStatus::Conflict,
            };
        }
        let previous = state.revision;
        state.revision += 1;
        state.cap_ns = binding.cap_ns;
        state.effects += 1;
        PublishOutcome::Success {
            stable_object_id: self.object,
            previous_revision: previous,
            saved_revision: state.revision,
            effective_ns: 1_000_000,
            consumed_ns: 0,
        }
    }

    fn revoke(&self) {
        let mut state = self.mutation.lock().unwrap();
        state.alive = false;
        state.grant_epoch += 1;
    }
}

fn ack(core: &ControlCore) -> HistoryAck {
    HistoryAck::from_owner_receipt(
        core.identity(),
        1,
        OwnerReceipt::new(durable_owner(), [0x35; 32]),
    )
    .unwrap()
}

#[test]
fn bound_callback_receives_original_owner_complete_ancestry_binding_and_d() {
    let (core, _) = core(1_210_001);
    let original = BoundOwner::new(1_210_001, vec![3, 7, 11]);
    let other_instance_with_same_ids = BoundOwner::new(1_210_001, vec![3, 7, 11]);
    let request = original.request();
    let binding = request.binding();
    let token = core.reserve_native(request, publisher()).unwrap();
    let terminal = core
        .execute_native_reserved::<BoundOwner, _>(&token, publisher(), |context| {
            assert!(std::ptr::eq(context.owner(), Arc::as_ref(&original)));
            assert!(!std::ptr::eq(
                context.owner(),
                Arc::as_ref(&other_instance_with_same_ids)
            ));
            assert_eq!(context.id(), token.id());
            assert_eq!(context.id().namespace(), core.identity());
            assert_eq!(context.binding(), binding);
            assert_eq!(context.binding().sequence, context.id().sequence());
            assert_eq!(context.ancestor_epochs(), [3, 7, 11]);
            context
                .owner()
                .apply(context.binding(), context.ancestor_epochs())
        })
        .unwrap();
    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
    assert_eq!(original.mutation.lock().unwrap().effects, 1);
    assert_eq!(
        other_instance_with_same_ids
            .mutation
            .lock()
            .unwrap()
            .effects,
        0
    );
    assert_eq!(original.mutation.lock().unwrap().cap_ns, 17);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn bound_callback_uses_pinned_owner_after_all_external_handles_are_dropped() {
    let (core, authority) = core(1_210_002);
    let original = BoundOwner::new(1_210_002, vec![1]);
    let weak_owner = Arc::downgrade(&original);
    let token = core
        .reserve_native(original.request(), publisher())
        .unwrap();
    drop(original);
    let terminal = core
        .execute_native_reserved::<BoundOwner, _>(&token, publisher(), |context| {
            context
                .owner()
                .apply(context.binding(), context.ancestor_epochs())
        })
        .unwrap();
    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
    assert_eq!(
        weak_owner
            .upgrade()
            .unwrap()
            .mutation
            .lock()
            .unwrap()
            .effects,
        1
    );
    let view = core.delivery_view_for(durable_owner()).unwrap();
    core.retire_through(&view, ack(&core), &authority).unwrap();
    assert!(weak_owner.upgrade().is_none());
    assert!(matches!(
        core.execute_native_reserved::<BoundOwner, _>(&token, publisher(), |_| {
            panic!("retired bound owner callback executed")
        }),
        Err(DeliveryError::Retired | DeliveryError::HistoryLost)
    ));
}

#[test]
fn wrong_owner_type_preserves_pending_slot_and_does_not_consume_execution() {
    let (core, authority) = core(1_210_003);
    let original = BoundOwner::new(1_210_003, vec![1]);
    let token = core
        .reserve_native(original.request(), publisher())
        .unwrap();
    assert_eq!(
        core.execute_native_reserved::<AtomicUsize, _>(&token, publisher(), |_| {
            panic!("wrong native owner type entered callback")
        }),
        Err(DeliveryError::InvalidRequest)
    );
    assert_eq!(core.next_sequence(), 2);
    let view = core.delivery_view_for(durable_owner()).unwrap();
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Reserved
    );
    assert_eq!(
        core.retire_through(&view, ack(&core), &authority),
        Err(DeliveryError::PendingPrefix)
    );
    assert_eq!(original.mutation.lock().unwrap().effects, 0);
    let terminal = core
        .execute_native_reserved::<BoundOwner, _>(&token, publisher(), |context| {
            context
                .owner()
                .apply(context.binding(), context.ancestor_epochs())
        })
        .unwrap();
    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
    assert_eq!(original.mutation.lock().unwrap().effects, 1);
}

#[test]
fn generic_native_execution_is_rejected_without_consuming_typed_admission() {
    let (core, _) = core(1_210_009);
    let original = BoundOwner::new(1_210_009, vec![1]);
    let token = core
        .reserve_native(original.request(), publisher())
        .unwrap();
    let callbacks = AtomicUsize::new(0);
    assert_eq!(
        core.execute_reserved(&token, publisher(), |_| {
            callbacks.fetch_add(1, Ordering::SeqCst);
            panic!("generic executor received a native binding without its owner context")
        }),
        Err(DeliveryError::InvalidRequest)
    );
    assert_eq!(callbacks.load(Ordering::SeqCst), 0);
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::Reserved
    );
    let terminal = core
        .execute_native_reserved::<BoundOwner, _>(&token, publisher(), |context| {
            context
                .owner()
                .apply(context.binding(), context.ancestor_epochs())
        })
        .unwrap();
    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
    assert_eq!(original.mutation.lock().unwrap().effects, 1);
}

#[test]
fn host_reservation_is_rejected_before_native_callback_and_still_commits_normally() {
    let (core, _) = core(1_210_004);
    let host = ResourceDomain::new(
        ResourceDomainId::from_u128(1_210_004),
        StableObjectId::from_u128(1_210_004),
        None,
        CPU_PERIOD_NS,
    )
    .unwrap();
    let token = core
        .reserve(
            DeliveryRequest::from_wire(1, host.grant(publisher()).unwrap(), 1, 17, 11, 5).unwrap(),
            publisher(),
        )
        .unwrap();
    assert_eq!(
        core.execute_native_reserved::<BoundOwner, _>(&token, publisher(), |_| {
            panic!("host reservation entered native executor")
        }),
        Err(DeliveryError::InvalidRequest)
    );
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::Reserved
    );
    assert_eq!(host.revision(), 1);
    assert_eq!(
        core.commit(&token, publisher(), 1_000_000).unwrap().status,
        Some(DeliveryStatus::Ok)
    );
    assert_eq!(host.revision(), 2);
}

#[test]
fn wrong_publisher_or_foreign_namespace_never_obtains_bound_owner_context() {
    let (core, _) = core(1_210_005);
    let original = BoundOwner::new(1_210_005, vec![1]);
    let token = core
        .reserve_native(original.request(), publisher())
        .unwrap();
    let foreign = ControlCore::new(core.identity().boot_id(), core.identity().cap_space_id());
    for (executor, principal) in [(&core, PublisherId::from_u128(99)), (&foreign, publisher())] {
        assert_eq!(
            executor.execute_native_reserved::<BoundOwner, _>(&token, principal, |_| {
                panic!("unauthorized executor obtained a bound context")
            }),
            Err(DeliveryError::PermissionDenied)
        );
    }
    assert_eq!(original.mutation.lock().unwrap().effects, 0);
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::Reserved
    );
}

#[test]
fn namespace_loss_fences_bound_callback_and_releases_the_original_owner() {
    let (core, _) = core(1_210_006);
    let original = BoundOwner::new(1_210_006, vec![1]);
    let weak_owner = Arc::downgrade(&original);
    let token = core
        .reserve_native(original.request(), publisher())
        .unwrap();
    drop(original);
    core.lose_history();
    assert!(weak_owner.upgrade().is_none());
    assert_eq!(
        core.execute_native_reserved::<BoundOwner, _>(&token, publisher(), |_| {
            panic!("lost native reservation entered callback")
        }),
        Err(DeliveryError::HistoryLost)
    );
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn bound_callback_preserves_reserved_ancestry_after_ancestor_revoke_and_reactivate() {
    let (core, _) = core(1_210_007);
    let original = BoundOwner::new(1_210_007, vec![5, 9]);
    let token = core
        .reserve_native(original.request(), publisher())
        .unwrap();
    // Only an ancestor changes. The leaf grant epoch, object identity and
    // resource revision remain equal, so inspecting RequestBinding alone
    // cannot detect this stale authorization.
    original.mutation.lock().unwrap().ancestor_epochs[0] = 6;
    let terminal = core
        .execute_native_reserved::<BoundOwner, _>(&token, publisher(), |context| {
            assert_eq!(context.binding().grant_epoch, 1);
            assert_eq!(context.ancestor_epochs(), [5, 9]);
            context
                .owner()
                .apply(context.binding(), context.ancestor_epochs())
        })
        .unwrap();
    assert_eq!(terminal.status, Some(DeliveryStatus::Revoked));
    assert_eq!(original.mutation.lock().unwrap().effects, 0);
    assert_eq!(
        core.execute_native_reserved::<BoundOwner, _>(&token, publisher(), |_| {
            panic!("terminal bound ancestor refusal became executable")
        })
        .unwrap(),
        terminal
    );
}

#[test]
fn bound_context_preserves_every_epoch_of_the_maximum_supported_ancestry() {
    let (core, _) = core(1_210_008);
    let epochs = (1..MAX_RESOURCE_DEPTH as u64).collect::<Vec<_>>();
    let original = BoundOwner::new(1_210_008, epochs.clone());
    let token = core
        .reserve_native(original.request(), publisher())
        .unwrap();
    let terminal = core
        .execute_native_reserved::<BoundOwner, _>(&token, publisher(), |context| {
            assert_eq!(context.ancestor_epochs().len(), MAX_RESOURCE_DEPTH - 1);
            assert_eq!(context.ancestor_epochs(), epochs);
            context
                .owner()
                .apply(context.binding(), context.ancestor_epochs())
        })
        .unwrap();
    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
    for _ in 0..32 {
        assert_eq!(
            core.execute_native_reserved::<BoundOwner, _>(&token, publisher(), |_| {
                panic!("bound terminal retry invoked a second owner callback")
            })
            .unwrap(),
            terminal
        );
    }
    assert_eq!(original.mutation.lock().unwrap().effects, 1);
}

#[test]
fn concurrent_bound_callbacks_on_one_d_invoke_the_original_owner_once() {
    for iteration in 0..32_u128 {
        let (core, _) = core(1_220_000 + iteration);
        let core = Arc::new(core);
        let original = BoundOwner::new(1_220_000 + iteration, vec![1, 2]);
        let token = Arc::new(
            core.reserve_native(original.request(), publisher())
                .unwrap(),
        );
        let callbacks = Arc::new(AtomicUsize::new(0));
        let barrier = Arc::new(Barrier::new(9));
        let mut workers = Vec::new();
        for _ in 0..8 {
            let core = Arc::clone(&core);
            let token = Arc::clone(&token);
            let callbacks = Arc::clone(&callbacks);
            let barrier = Arc::clone(&barrier);
            workers.push(thread::spawn(move || {
                barrier.wait();
                core.execute_native_reserved::<BoundOwner, _>(&token, publisher(), |context| {
                    callbacks.fetch_add(1, Ordering::SeqCst);
                    assert_eq!(context.id(), token.id());
                    context
                        .owner()
                        .apply(context.binding(), context.ancestor_epochs())
                })
                .unwrap()
            }));
        }
        barrier.wait();
        let terminal = workers.remove(0).join().unwrap();
        for worker in workers {
            assert_eq!(worker.join().unwrap(), terminal);
        }
        assert_eq!(callbacks.load(Ordering::SeqCst), 1);
        assert_eq!(original.mutation.lock().unwrap().effects, 1);
        core.validate_invariants_for_host_model().unwrap();
    }
}

#[test]
fn bound_owner_revoke_and_commit_race_revalidates_under_the_original_mutation_lock() {
    for iteration in 0..64_u128 {
        let (core, _) = core(1_230_000 + iteration);
        let core = Arc::new(core);
        let original = BoundOwner::new(1_230_000 + iteration, vec![1]);
        let token = Arc::new(
            core.reserve_native(original.request(), publisher())
                .unwrap(),
        );
        let barrier = Arc::new(Barrier::new(3));
        let executor = {
            let core = Arc::clone(&core);
            let token = Arc::clone(&token);
            let barrier = Arc::clone(&barrier);
            thread::spawn(move || {
                barrier.wait();
                core.execute_native_reserved::<BoundOwner, _>(&token, publisher(), |context| {
                    context
                        .owner()
                        .apply(context.binding(), context.ancestor_epochs())
                })
                .unwrap()
            })
        };
        let revoke = {
            let original = Arc::clone(&original);
            let barrier = Arc::clone(&barrier);
            thread::spawn(move || {
                barrier.wait();
                original.revoke();
            })
        };
        barrier.wait();
        let terminal = executor.join().unwrap();
        revoke.join().unwrap();
        let effects = original.mutation.lock().unwrap().effects;
        match terminal.status {
            Some(DeliveryStatus::Ok) => assert_eq!(effects, 1),
            Some(DeliveryStatus::Revoked) => assert_eq!(effects, 0),
            other => panic!("unexpected bound revoke/commit result: {other:?}"),
        }
        assert_eq!(
            core.execute_native_reserved::<BoundOwner, _>(&token, publisher(), |_| {
                panic!("bound revoke/commit result reexecuted")
            })
            .unwrap(),
            terminal
        );
    }
}
