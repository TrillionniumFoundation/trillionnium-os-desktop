//! Synthetic host owners exercising the native delivery seam.
//!
//! The owner below is the sole mutable revision/cap state for these tests;
//! no host ResourceDomain stands in for it. Mutexes and atomics simulate an
//! already existing resource owner, not Asterinas IRQ locks, scheduling,
//! credentials, usercopy, durable Hepta state, or a real kernel integration.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryRequest, DeliveryState, DeliveryStatus,
    HistoryAck, NativeDeliveryRequest, NativeGrant, NativeTarget, OriginalOwnerAuthority, OwnerId,
    OwnerReceipt, PublishOutcome, PublisherId, RequestBinding, ReserveAttempt, ResourceDomain,
    ResourceDomainId, ResourceError, StableObjectId, CPU_PERIOD_NS, MAX_RESOURCE_DEPTH,
};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Barrier, Mutex};
use std::thread;
use std::time::Duration;

const TARGET_SLOT: u64 = 7;
const TARGET_GENERATION: u64 = 11;

fn publisher() -> PublisherId {
    PublisherId::from_u128(9_001)
}

fn durable_owner() -> OwnerId {
    OwnerId::from_u128(9_002)
}

fn core(n: u128) -> (ControlCore, OriginalOwnerAuthority) {
    ControlCore::with_original_owner(
        BootId::from_u128(n),
        CapSpaceId::from_u128(n),
        durable_owner(),
    )
    .unwrap()
}

struct FakeNativeOwner {
    mutation: Mutex<()>,
    revision: AtomicU64,
    cap_ns: AtomicU64,
    epoch: AtomicU64,
    alive: AtomicBool,
    effects: AtomicUsize,
}

impl FakeNativeOwner {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            mutation: Mutex::new(()),
            revision: AtomicU64::new(1),
            cap_ns: AtomicU64::new(CPU_PERIOD_NS),
            epoch: AtomicU64::new(1),
            alive: AtomicBool::new(true),
            effects: AtomicUsize::new(0),
        })
    }

    fn apply(&self, binding: RequestBinding) -> PublishOutcome {
        // The real owner's mutation lock protects authority revalidation and
        // its existing state. The delivery library never writes these atomics.
        let _mutation = self.mutation.lock().unwrap();
        if !self.alive.load(Ordering::Acquire)
            || self.epoch.load(Ordering::Acquire) != binding.grant_epoch
        {
            return PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            };
        }
        let previous = self.revision.load(Ordering::Acquire);
        if previous != binding.expected_revision {
            return PublishOutcome::Failure {
                status: DeliveryStatus::Conflict,
            };
        }
        assert_eq!(binding.publisher, publisher());
        assert_eq!(binding.period_ns, CPU_PERIOD_NS);
        assert!(binding.cap_ns <= CPU_PERIOD_NS);
        self.cap_ns.store(binding.cap_ns, Ordering::Release);
        self.revision.store(previous + 1, Ordering::Release);
        self.effects.fetch_add(1, Ordering::SeqCst);
        PublishOutcome::Success {
            stable_object_id: binding.stable_object_id,
            saved_revision: previous + 1,
            previous_revision: previous,
            effective_ns: 1_000_000,
            consumed_ns: 0,
        }
    }

    fn revoke(&self) {
        let _mutation = self.mutation.lock().unwrap();
        self.alive.store(false, Ordering::Release);
        self.epoch.fetch_add(1, Ordering::AcqRel);
    }
}

fn target(owner: &Arc<FakeNativeOwner>, n: u128) -> NativeTarget {
    NativeTarget::from_owner(
        Arc::clone(owner),
        ResourceDomainId::from_u128(n),
        StableObjectId::from_u128(n),
    )
    .unwrap()
}

fn request(owner: &Arc<FakeNativeOwner>, n: u128) -> NativeDeliveryRequest {
    request_with_grant(
        NativeGrant::from_owner(target(owner, n), publisher(), 1, Vec::new()).unwrap(),
    )
}

fn request_with_grant(grant: NativeGrant) -> NativeDeliveryRequest {
    NativeDeliveryRequest::from_wire(1, grant, 1, 17, TARGET_SLOT, TARGET_GENERATION)
        .unwrap()
        .with_payload_digest([0x42; 32])
}

fn ack(authority: &OriginalOwnerAuthority, through: u64) -> HistoryAck {
    authority.history_ack(through, [0x33; 32]).unwrap()
}

#[test]
fn native_owner_executes_without_any_host_resource_domain_or_shadow_budget() {
    let (core, _) = core(920_001);
    let owner = FakeNativeOwner::new();
    let request = request(&owner, 920_001);
    let canonical = request.binding();
    let token = core.reserve_native(request, publisher()).unwrap();
    assert_eq!(token.binding(), canonical);
    assert_eq!(owner.revision.load(Ordering::Acquire), 1);
    assert_eq!(owner.effects.load(Ordering::SeqCst), 0);
    let terminal = core
        .execute_native_reserved::<FakeNativeOwner, _>(&token, publisher(), |context| {
            context.owner().apply(context.binding())
        })
        .unwrap();
    assert_eq!(terminal.state, DeliveryState::Terminal);
    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
    assert_eq!(terminal.saved_revision, Some(2));
    assert_eq!(owner.revision.load(Ordering::Acquire), 2);
    assert_eq!(owner.cap_ns.load(Ordering::Acquire), 17);
    assert_eq!(owner.effects.load(Ordering::SeqCst), 1);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn same_real_owner_rewrapped_dedupes_but_equal_ids_on_other_arc_conflict() {
    let (core, _) = core(920_002);
    let owner = FakeNativeOwner::new();
    let other_owner = FakeNativeOwner::new();
    let token = core
        .reserve_native(request(&owner, 920_002), publisher())
        .unwrap();
    // Each request rebuilds a distinct NativeTarget wrapper around the same
    // actual owner Arc. Wrapper identity must not defeat exactly-once replay.
    assert_eq!(
        core.reserve_native(request(&owner, 920_002), publisher())
            .err(),
        Some(DeliveryError::Busy)
    );
    assert_eq!(
        core.reserve_native(request(&other_owner, 920_002), publisher())
            .err(),
        Some(DeliveryError::Conflict)
    );
    let terminal = core
        .execute_native_reserved::<FakeNativeOwner, _>(&token, publisher(), |context| {
            context.owner().apply(context.binding())
        })
        .unwrap();
    match core
        .reserve_native_or_get(request(&owner, 920_002), publisher())
        .unwrap()
    {
        ReserveAttempt::Existing(observed) => assert_eq!(observed, terminal),
        ReserveAttempt::Reserved(_) => panic!("native replay allocated another result"),
    }
    assert_eq!(
        core.reserve_native_or_get(request(&other_owner, 920_002), publisher())
            .err(),
        Some(DeliveryError::Conflict)
    );
    assert_eq!(owner.effects.load(Ordering::SeqCst), 1);
    assert_eq!(other_owner.effects.load(Ordering::SeqCst), 0);
}

#[test]
fn native_d_binds_full_request_publisher_epoch_and_ancestor_snapshot() {
    let (core, _) = core(920_003);
    let owner = FakeNativeOwner::new();
    let original = request(&owner, 920_003);
    let _token = core.reserve_native(original.clone(), publisher()).unwrap();
    let mut changed_cap = original.clone();
    changed_cap.cap_ns += 1;
    let mut changed_revision = original.clone();
    changed_revision.expected_revision += 1;
    let changed_digest = original.clone().with_payload_digest([0x43; 32]);
    let grant =
        || NativeGrant::from_owner(target(&owner, 920_003), publisher(), 1, vec![]).unwrap();
    let changed_slot = NativeDeliveryRequest::from_wire(1, grant(), 1, 17, 8, TARGET_GENERATION)
        .unwrap()
        .with_payload_digest([0x42; 32]);
    let changed_generation = NativeDeliveryRequest::from_wire(1, grant(), 1, 17, TARGET_SLOT, 12)
        .unwrap()
        .with_payload_digest([0x42; 32]);
    let changed_target = request(&owner, 920_004);
    let changed_epoch = request_with_grant(
        NativeGrant::from_owner(target(&owner, 920_003), publisher(), 2, vec![]).unwrap(),
    );
    let changed_ancestor = request_with_grant(
        NativeGrant::from_owner(target(&owner, 920_003), publisher(), 1, vec![1]).unwrap(),
    );
    for request in [
        changed_cap,
        changed_revision,
        changed_digest,
        changed_slot,
        changed_generation,
        changed_target,
        changed_epoch,
        changed_ancestor,
    ] {
        assert_eq!(
            core.reserve_native(request, publisher()).err(),
            Some(DeliveryError::Conflict)
        );
    }
    let foreign_publisher = PublisherId::from_u128(9_099);
    let foreign_request = request_with_grant(
        NativeGrant::from_owner(target(&owner, 920_003), foreign_publisher, 1, vec![]).unwrap(),
    );
    assert_eq!(
        core.reserve_native(foreign_request, foreign_publisher)
            .err(),
        Some(DeliveryError::Conflict)
    );
    assert_eq!(owner.effects.load(Ordering::SeqCst), 0);
    assert_eq!(core.next_sequence(), 2);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn native_constructor_rejects_invalid_owner_binding_and_static_wire_fields() {
    let owner = FakeNativeOwner::new();
    let id = ResourceDomainId::from_u128(920_005);
    let object = StableObjectId::from_u128(920_005);
    assert_eq!(
        NativeTarget::from_owner(Arc::clone(&owner), ResourceDomainId::from_u128(0), object).err(),
        Some(ResourceError::InvalidIdentity)
    );
    assert_eq!(
        NativeTarget::from_owner(Arc::clone(&owner), id, StableObjectId::from_u128(0)).err(),
        Some(ResourceError::InvalidIdentity)
    );
    for (who, epoch, ancestors) in [
        (PublisherId::from_u128(0), 1, vec![]),
        (publisher(), 0, vec![]),
        (publisher(), 1, vec![1, 0]),
    ] {
        assert_eq!(
            NativeGrant::from_owner(target(&owner, 920_005), who, epoch, ancestors).err(),
            Some(ResourceError::InvalidIdentity)
        );
    }
    assert_eq!(
        NativeGrant::from_owner(
            target(&owner, 920_005),
            publisher(),
            1,
            vec![1; MAX_RESOURCE_DEPTH],
        )
        .err(),
        Some(ResourceError::Exhausted)
    );
    let max_grant = NativeGrant::from_owner(
        target(&owner, 920_005),
        publisher(),
        1,
        vec![1; MAX_RESOURCE_DEPTH - 1],
    )
    .unwrap();
    assert_eq!(max_grant.principal(), publisher());
    assert_eq!(max_grant.epoch(), 1);
    let grant =
        || NativeGrant::from_owner(target(&owner, 920_005), publisher(), 1, vec![]).unwrap();
    for sequence in [0, u64::MAX] {
        assert_eq!(
            NativeDeliveryRequest::from_wire(sequence, grant(), 1, 17, 7, 11).err(),
            Some(DeliveryError::InvalidSequence)
        );
    }
    for (revision, cap, slot, generation) in [
        (0, 17, 7, 11),
        (u64::MAX, 17, 7, 11),
        (1, CPU_PERIOD_NS + 1, 7, 11),
        (1, 17, 0, 11),
        (1, 17, 7, 0),
    ] {
        assert_eq!(
            NativeDeliveryRequest::from_wire(1, grant(), revision, cap, slot, generation).err(),
            Some(DeliveryError::InvalidRequest)
        );
    }
    assert_eq!(owner.effects.load(Ordering::SeqCst), 0);
}

#[test]
fn mutated_native_payload_is_validated_again_without_consuming_d() {
    let (core, _) = core(920_006);
    let owner = FakeNativeOwner::new();
    let valid = request(&owner, 920_006);
    let mut invalid = Vec::new();
    let mut changed = valid.clone();
    changed.period_ns -= 1;
    invalid.push(changed);
    let mut changed = valid.clone();
    changed.cap_ns = CPU_PERIOD_NS + 1;
    invalid.push(changed);
    for revision in [0, u64::MAX] {
        let mut changed = valid.clone();
        changed.expected_revision = revision;
        invalid.push(changed);
    }
    for changed in invalid {
        assert_eq!(
            core.reserve_native(changed, publisher()).err(),
            Some(DeliveryError::InvalidRequest)
        );
        assert_eq!(core.next_sequence(), 1);
    }
    for sequence in [0, u64::MAX] {
        let mut changed = valid.clone();
        changed.sequence = sequence;
        assert_eq!(
            core.reserve_native(changed, publisher()).err(),
            Some(DeliveryError::InvalidSequence)
        );
        assert_eq!(core.next_sequence(), 1);
    }
    core.reserve_native(valid, publisher()).unwrap();
    assert_eq!(core.next_sequence(), 2);
}

#[test]
fn wrong_native_publisher_cannot_reserve_or_execute_external_mutation() {
    let (core, _) = core(920_007);
    let owner = FakeNativeOwner::new();
    let request = request(&owner, 920_007);
    let wrong = PublisherId::from_u128(9_099);
    assert_eq!(
        core.reserve_native(request.clone(), wrong).err(),
        Some(DeliveryError::PermissionDenied)
    );
    assert_eq!(core.next_sequence(), 1);
    let token = core.reserve_native(request, publisher()).unwrap();
    let callbacks = AtomicUsize::new(0);
    assert_eq!(
        core.execute_native_reserved::<FakeNativeOwner, _>(&token, wrong, |context| {
            callbacks.fetch_add(1, Ordering::SeqCst);
            context.owner().apply(context.binding())
        }),
        Err(DeliveryError::PermissionDenied)
    );
    assert_eq!(callbacks.load(Ordering::SeqCst), 0);
    assert_eq!(owner.effects.load(Ordering::SeqCst), 0);
    assert_eq!(owner.revision.load(Ordering::Acquire), 1);
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::Reserved
    );
}

#[test]
fn host_commit_cannot_consume_a_native_callback_or_mutate_native_owner() {
    let (core, _) = core(920_008);
    let owner = FakeNativeOwner::new();
    let token = core
        .reserve_native(request(&owner, 920_008), publisher())
        .unwrap();
    assert_eq!(
        core.commit(&token, publisher(), 1_000_000),
        Err(DeliveryError::InvalidRequest)
    );
    assert_eq!(owner.effects.load(Ordering::SeqCst), 0);
    assert_eq!(owner.revision.load(Ordering::Acquire), 1);
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::Reserved
    );
    let terminal = core
        .execute_native_reserved::<FakeNativeOwner, _>(&token, publisher(), |context| {
            context.owner().apply(context.binding())
        })
        .unwrap();
    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
    assert_eq!(owner.effects.load(Ordering::SeqCst), 1);
}

#[test]
fn native_copyout_retry_reuses_original_result_without_second_owner_cas() {
    let (core, _) = core(920_009);
    let owner = FakeNativeOwner::new();
    let request = request(&owner, 920_009);
    let token = core.reserve_native(request.clone(), publisher()).unwrap();
    let terminal = core
        .execute_native_reserved::<FakeNativeOwner, _>(&token, publisher(), |context| {
            context.owner().apply(context.binding())
        })
        .unwrap();
    // Discarding the response models a lost copyout, not a real EFAULT.
    for _ in 0..64 {
        assert_eq!(
            core.execute_native_reserved::<FakeNativeOwner, _>(&token, publisher(), |_| {
                panic!("copyout retry entered a second native callback")
            })
            .unwrap(),
            terminal
        );
        match core
            .reserve_native_or_get(request.clone(), publisher())
            .unwrap()
        {
            ReserveAttempt::Existing(result) => assert_eq!(result, terminal),
            ReserveAttempt::Reserved(_) => panic!("copyout retry reserved a second effect"),
        }
    }
    assert_eq!(owner.effects.load(Ordering::SeqCst), 1);
    assert_eq!(owner.revision.load(Ordering::Acquire), 2);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn native_callback_rechecks_revocation_and_terminal_refusal_never_becomes_success() {
    let (core, _) = core(920_010);
    let owner = FakeNativeOwner::new();
    let request = request(&owner, 920_010);
    let token = core.reserve_native(request.clone(), publisher()).unwrap();
    owner.revoke();
    let terminal = core
        .execute_native_reserved::<FakeNativeOwner, _>(&token, publisher(), |context| {
            context.owner().apply(context.binding())
        })
        .unwrap();
    assert_eq!(terminal.status, Some(DeliveryStatus::Revoked));
    assert_eq!(owner.effects.load(Ordering::SeqCst), 0);
    {
        let _mutation = owner.mutation.lock().unwrap();
        owner.alive.store(true, Ordering::Release);
        owner.epoch.store(1, Ordering::Release);
    }
    assert_eq!(
        core.execute_native_reserved::<FakeNativeOwner, _>(&token, publisher(), |_| panic!(
            "refusal became executable"
        ))
        .unwrap(),
        terminal
    );
    match core.reserve_native_or_get(request, publisher()).unwrap() {
        ReserveAttempt::Existing(result) => assert_eq!(result, terminal),
        ReserveAttempt::Reserved(_) => panic!("terminal native refusal reopened"),
    }
    assert_eq!(owner.effects.load(Ordering::SeqCst), 0);
}

#[test]
fn native_commit_before_revoke_preserves_admitted_original_result() {
    let (core, _) = core(920_011);
    let owner = FakeNativeOwner::new();
    let token = core
        .reserve_native(request(&owner, 920_011), publisher())
        .unwrap();
    let terminal = core
        .execute_native_reserved::<FakeNativeOwner, _>(&token, publisher(), |context| {
            context.owner().apply(context.binding())
        })
        .unwrap();
    owner.revoke();
    assert_eq!(
        core.execute_native_reserved::<FakeNativeOwner, _>(&token, publisher(), |_| panic!(
            "terminal success reexecuted"
        ))
        .unwrap(),
        terminal
    );
    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
    assert_eq!(owner.effects.load(Ordering::SeqCst), 1);
    assert_eq!(owner.cap_ns.load(Ordering::Acquire), 17);
}

#[test]
fn native_retirement_releases_owner_even_with_stale_token_retained() {
    let (core, authority) = core(920_012);
    let owner = FakeNativeOwner::new();
    let weak_owner = Arc::downgrade(&owner);
    let token = core
        .reserve_native(request(&owner, 920_012), publisher())
        .unwrap();
    core.execute_native_reserved::<FakeNativeOwner, _>(&token, publisher(), |context| {
        context.owner().apply(context.binding())
    })
    .unwrap();
    drop(owner);
    assert!(
        weak_owner.upgrade().is_some(),
        "unretired result lost its owner pin"
    );
    let view = core.delivery_view_for(durable_owner()).unwrap();
    core.retire_through(&view, ack(&authority, 1), &authority)
        .unwrap();
    assert!(
        weak_owner.upgrade().is_none(),
        "stale token retained the owner after retirement"
    );
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Retired
    );
    let calls = AtomicUsize::new(0);
    assert!(core
        .execute_native_reserved::<FakeNativeOwner, _>(&token, publisher(), |_| {
            calls.fetch_add(1, Ordering::SeqCst);
            panic!("retired native token executed")
        })
        .is_err());
    assert_eq!(calls.load(Ordering::SeqCst), 0);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn native_and_host_requests_with_equal_public_binding_never_share_d() {
    for native_first in [false, true] {
        let (core, _) = core(920_013 + u128::from(native_first));
        let owner = FakeNativeOwner::new();
        let native = request(&owner, 920_013);
        // Only this kind-isolation negative creates a host model target.
        let host_target = ResourceDomain::new(
            ResourceDomainId::from_u128(920_013),
            StableObjectId::from_u128(920_013),
            None,
            CPU_PERIOD_NS,
        )
        .unwrap();
        let host = DeliveryRequest::from_wire(
            1,
            host_target.grant(publisher()).unwrap(),
            1,
            17,
            TARGET_SLOT,
            TARGET_GENERATION,
        )
        .unwrap()
        .with_payload_digest([0x42; 32]);
        assert_eq!(native.binding(), host.binding());
        if native_first {
            core.reserve_native(native, publisher()).unwrap();
            assert_eq!(
                core.reserve(host, publisher()).err(),
                Some(DeliveryError::Conflict)
            );
        } else {
            core.reserve(host, publisher()).unwrap();
            assert_eq!(
                core.reserve_native(native, publisher()).err(),
                Some(DeliveryError::Conflict)
            );
        }
        assert_eq!(owner.effects.load(Ordering::SeqCst), 0);
        core.validate_invariants_for_host_model().unwrap();
    }
}

#[test]
fn concurrent_same_native_d_reserves_and_commits_one_original_owner_effect() {
    for iteration in 0..32_u128 {
        let (core, _) = core(930_000 + iteration);
        let core = Arc::new(core);
        let owner = FakeNativeOwner::new();
        let request = request(&owner, 930_000 + iteration);
        let barrier = Arc::new(Barrier::new(9));
        let mut workers = Vec::new();
        for _ in 0..8 {
            let core = Arc::clone(&core);
            let request = request.clone();
            let barrier = Arc::clone(&barrier);
            workers.push(thread::spawn(move || {
                barrier.wait();
                core.reserve_native(request, publisher())
            }));
        }
        barrier.wait();
        let mut winner = None;
        for worker in workers {
            match worker.join().unwrap() {
                Ok(token) => assert!(winner.replace(token).is_none()),
                Err(error) => assert_eq!(error, DeliveryError::Busy),
            }
        }
        let token = Arc::new(winner.expect("native reservation had no winner"));
        let barrier = Arc::new(Barrier::new(9));
        let mut executors = Vec::new();
        for _ in 0..8 {
            let core = Arc::clone(&core);
            let token = Arc::clone(&token);
            let barrier = Arc::clone(&barrier);
            executors.push(thread::spawn(move || {
                barrier.wait();
                core.execute_native_reserved::<FakeNativeOwner, _>(&token, publisher(), |context| {
                    context.owner().apply(context.binding())
                })
                .unwrap()
            }));
        }
        barrier.wait();
        let terminal = executors.remove(0).join().unwrap();
        for executor in executors {
            assert_eq!(executor.join().unwrap(), terminal);
        }
        assert_eq!(owner.effects.load(Ordering::SeqCst), 1);
        assert_eq!(owner.revision.load(Ordering::Acquire), 2);
        core.validate_invariants_for_host_model().unwrap();
    }
}

#[derive(Clone, Copy)]
enum DropAction {
    ReadNamespace,
    LoseHistory,
}

struct DropReport {
    called: AtomicUsize,
    completed_before_return: AtomicBool,
    observed_next_sequence: AtomicU64,
    worker: Mutex<Option<thread::JoinHandle<()>>>,
}

impl DropReport {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            called: AtomicUsize::new(0),
            completed_before_return: AtomicBool::new(false),
            observed_next_sequence: AtomicU64::new(0),
            worker: Mutex::new(None),
        })
    }

    fn join_after_owner_release(&self) {
        // Join only after the outer retire/loss returned. On the broken
        // implementation Drop's timeout releases the library's lock first,
        // letting the worker finish instead of hanging the test process.
        let worker = self.worker.lock().unwrap().take();
        worker
            .expect("owner Drop did not launch its worker")
            .join()
            .unwrap();
    }
}

struct ReenteringNativeOwner {
    core: ControlCore,
    action: DropAction,
    report: Arc<DropReport>,
}

impl Drop for ReenteringNativeOwner {
    fn drop(&mut self) {
        self.report.called.fetch_add(1, Ordering::SeqCst);
        let core = self.core.clone();
        let action = self.action;
        let report = Arc::clone(&self.report);
        let (complete_tx, complete_rx) = mpsc::channel();
        let worker = thread::spawn(move || {
            // ReadNamespace detects a namespace table guard held by retire.
            // LoseHistory detects the outer lose_history retaining loss_gate
            // while destroying the last actual native-owner Arc.
            if matches!(action, DropAction::LoseHistory) {
                core.lose_history();
            }
            report
                .observed_next_sequence
                .store(core.next_sequence(), Ordering::Release);
            let _ = complete_tx.send(());
        });
        *self.report.worker.lock().unwrap() = Some(worker);
        self.report.completed_before_return.store(
            complete_rx.recv_timeout(Duration::from_secs(5)).is_ok(),
            Ordering::Release,
        );
        // A timeout is recorded and Drop returns normally. The caller joins
        // the worker and fails its assertion after library guards can drop.
    }
}

fn reserve_reentering_owner(
    core: &ControlCore,
    n: u128,
    action: DropAction,
    report: &Arc<DropReport>,
) -> os_control::ReserveToken {
    let owner = Arc::new(ReenteringNativeOwner {
        core: core.clone(),
        action,
        report: Arc::clone(report),
    });
    let target = NativeTarget::from_owner(
        Arc::clone(&owner),
        ResourceDomainId::from_u128(n),
        StableObjectId::from_u128(n),
    )
    .unwrap();
    let request =
        request_with_grant(NativeGrant::from_owner(target, publisher(), 1, vec![]).unwrap());
    let token = core.reserve_native(request, publisher()).unwrap();
    // The bounded delivery slot now owns the only strong owner reference.
    // Keeping the returned token alive must not preserve another owner pin.
    drop(owner);
    assert_eq!(report.called.load(Ordering::SeqCst), 0);
    token
}

#[test]
fn native_owner_drop_during_retirement_can_read_same_namespace_before_return() {
    let (core, authority) = core(940_001);
    let report = DropReport::new();
    let token = reserve_reentering_owner(&core, 940_001, DropAction::ReadNamespace, &report);
    core.execute_native_reserved::<ReenteringNativeOwner, _>(&token, publisher(), |context| {
        PublishOutcome::Failure {
            status: if context.binding().publisher == publisher() {
                DeliveryStatus::Revoked
            } else {
                DeliveryStatus::PermissionDenied
            },
        }
    })
    .unwrap();
    let view = core.delivery_view_for(durable_owner()).unwrap();
    let receipt = core.retire_through(&view, ack(&authority, 1), &authority);
    report.join_after_owner_release();
    assert_eq!(receipt.unwrap().retired_through, 1);
    assert_eq!(report.called.load(Ordering::SeqCst), 1);
    assert!(
        report.completed_before_return.load(Ordering::Acquire),
        "native-owner destructor ran while retirement held the namespace table lock"
    );
    assert_eq!(report.observed_next_sequence.load(Ordering::Acquire), 2);
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Retired
    );
    core.validate_invariants_for_host_model().unwrap();
    drop(token);
    assert_eq!(report.called.load(Ordering::SeqCst), 1);
}

#[test]
fn native_owner_drop_during_history_loss_can_reenter_loss_gate_before_return() {
    let (core, _) = core(940_002);
    let report = DropReport::new();
    // A pending slot also pins the true owner and must release it after loss
    // has fenced execution. No terminal effect is fabricated for cleanup.
    let token = reserve_reentering_owner(&core, 940_002, DropAction::LoseHistory, &report);
    let view = core.delivery_view();
    core.lose_history();
    report.join_after_owner_release();
    assert_eq!(report.called.load(Ordering::SeqCst), 1);
    assert!(
        report.completed_before_return.load(Ordering::Acquire),
        "native-owner destructor ran while history loss held its loss gate or namespace table"
    );
    assert_eq!(report.observed_next_sequence.load(Ordering::Acquire), 2);
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::HistoryLost
    );
    assert_eq!(core.window_len(), 0);
    assert_eq!(
        core.execute_native_reserved::<ReenteringNativeOwner, _>(&token, publisher(), |_| panic!(
            "fenced native owner reexecuted"
        )),
        Err(DeliveryError::HistoryLost)
    );
    core.validate_invariants_for_host_model().unwrap();
}
