use loom::sync::atomic::{AtomicUsize, Ordering};
use loom::thread;
use os_control::*;
use std::sync::atomic::{AtomicUsize as HostAtomicUsize, Ordering as HostOrdering};
use std::sync::Arc;

fn model(name: &str, f: impl Fn() + Send + Sync + 'static) {
    let schedules = Arc::new(HostAtomicUsize::new(0));
    let count = schedules.clone();
    let mut builder = loom::model::Builder::new();
    builder.max_threads = 4;
    builder.max_branches = 10_000;
    builder.preemption_bound = Some(3);
    builder.max_permutations = None;
    builder.max_duration = None;
    builder.check(move || {
        count.fetch_add(1, HostOrdering::Relaxed);
        f();
    });
    eprintln!("MODEL {name}: schedules={} max_threads=4 preemption_bound=3 max_branches=10000 max_permutations=none max_duration=none", schedules.load(HostOrdering::Relaxed));
}
fn publisher() -> PublisherId {
    PublisherId::from_u128(3)
}
fn owner() -> OwnerId {
    OwnerId::from_u128(4)
}
fn fixture() -> (
    ControlCore,
    OriginalOwnerAuthority,
    ResourceDomain,
    DeliveryRequest,
) {
    let (core, authority) = ControlCore::with_capacity_for_owner(
        BootId::from_u128(1),
        CapSpaceId::from_u128(2),
        2,
        owner(),
    )
    .unwrap();
    let target = ResourceDomain::new(
        ResourceDomainId::from_u128(5),
        StableObjectId::from_u128(6),
        None,
        CPU_PERIOD_NS,
    )
    .unwrap();
    let request =
        DeliveryRequest::from_wire(1, target.grant(publisher()).unwrap(), 1, 10, 7, 8).unwrap();
    (core, authority, target, request)
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
#[test]
fn same_d_reservation_and_effect_once() {
    model("same_d_reservation_and_effect_once", || {
        let (core, _, _, request) = fixture();
        let count = Arc::new(AtomicUsize::new(0));
        let worker =
            |core: ControlCore, request: DeliveryRequest, count: Arc<AtomicUsize>| match core
                .reserve_or_get(request, publisher())
                .unwrap()
            {
                ReserveAttempt::Reserved(token) => {
                    let out = core
                        .execute_reserved(&token, publisher(), |binding| {
                            assert_eq!(count.fetch_add(1, Ordering::SeqCst), 0);
                            thread::yield_now();
                            success(binding)
                        })
                        .unwrap();
                    assert_eq!(out.state, DeliveryState::Terminal);
                }
                ReserveAttempt::Existing(out) => assert!(matches!(
                    out.state,
                    DeliveryState::Reserved | DeliveryState::Terminal
                )),
            };
        let (a_core, a_request, a_count) = (core.clone(), request.clone(), count.clone());
        let a = thread::spawn(move || worker(a_core, a_request, a_count));
        let (b_core, b_count) = (core.clone(), count.clone());
        let b = thread::spawn(move || worker(b_core, request, b_count));
        a.join().unwrap();
        b.join().unwrap();
        assert_eq!(count.load(Ordering::SeqCst), 1);
        assert_eq!(core.window_len(), 1);
        assert_eq!(core.next_sequence(), 2);
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1)
                .unwrap()
                .status,
            Some(DeliveryStatus::Ok)
        );
        core.validate_invariants_for_host_model().unwrap();
    });
}
#[test]
fn revoke_and_commit_linearize() {
    model("revoke_and_commit_linearize", || {
        let (core, _, target, request) = fixture();
        let token = core.reserve(request, publisher()).unwrap();
        let a_core = core.clone();
        let a = thread::spawn(move || a_core.commit(&token, publisher(), 1).unwrap());
        let b_target = target.clone();
        let b = thread::spawn(move || b_target.revoke());
        let outcome = a.join().unwrap();
        b.join().unwrap();
        assert_eq!(
            target.grant(publisher()).err(),
            Some(ResourceError::Revoked)
        );
        match outcome.status {
            Some(DeliveryStatus::Ok) => {
                assert_eq!(target.revision(), 2);
                assert_eq!(target.budget().cap_ns, 10);
            }
            Some(DeliveryStatus::Revoked) => {
                assert_eq!(target.revision(), 1);
                assert_eq!(target.budget().cap_ns, CPU_PERIOD_NS);
            }
            status => panic!("unexpected terminal status {status:?}"),
        }
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1).unwrap(),
            outcome
        );
        core.validate_invariants_for_host_model().unwrap();
    });
}
#[test]
fn retire_and_query_linearize() {
    model("retire_and_query_linearize", || {
        let (core, authority, _, request) = fixture();
        let token = core.reserve(request, publisher()).unwrap();
        let terminal = core
            .publish(&token, publisher(), success(token.binding()))
            .unwrap();
        let view = core.delivery_view_for(owner()).unwrap();
        let ack =
            HistoryAck::from_owner_receipt(core.identity(), 1, OwnerReceipt::new(owner(), [1; 32]))
                .unwrap();
        let (a_core, a_view) = (core.clone(), view.clone());
        let a = thread::spawn(move || a_core.retire_through(&a_view, ack, &authority).unwrap());
        let (b_core, b_view) = (core.clone(), view.clone());
        let b = thread::spawn(move || b_core.query_delivery(&b_view, 1).unwrap());
        a.join().unwrap();
        let observed = b.join().unwrap();
        assert!(observed == terminal || observed.state == DeliveryState::Retired);
        assert_eq!(
            core.query_delivery(&view, 1).unwrap().state,
            DeliveryState::Retired
        );
        assert_eq!(
            core.reserve(
                DeliveryRequest::from_wire(
                    1,
                    ResourceDomain::new(
                        ResourceDomainId::from_u128(9),
                        StableObjectId::from_u128(10),
                        None,
                        CPU_PERIOD_NS
                    )
                    .unwrap()
                    .grant(publisher())
                    .unwrap(),
                    1,
                    10,
                    7,
                    8
                )
                .unwrap(),
                publisher()
            )
            .err(),
            Some(DeliveryError::Retired)
        );
        core.validate_invariants_for_host_model().unwrap();
    });
}
#[test]
fn publish_and_observe_never_tear() {
    model("publish_and_observe_never_tear", || {
        let (core, _, _, request) = fixture();
        let token = core.reserve(request, publisher()).unwrap();
        let a_core = core.clone();
        let a = thread::spawn(move || {
            a_core
                .publish(&token, publisher(), success(token.binding()))
                .unwrap()
        });
        let b_core = core.clone();
        let b = thread::spawn(move || {
            let view = b_core.delivery_view();
            let first = b_core.query_delivery(&view, 1).unwrap();
            thread::yield_now();
            let second = b_core.query_delivery(&view, 1).unwrap();
            assert!(matches!(
                first.state,
                DeliveryState::Reserved | DeliveryState::Terminal
            ));
            assert!(matches!(
                second.state,
                DeliveryState::Reserved | DeliveryState::Terminal
            ));
            if first.state == DeliveryState::Terminal {
                assert_eq!(first, second);
            }
            assert!(first.hos2_saved_status_code().is_some());
            assert!(second.hos2_saved_status_code().is_some());
            (first, second)
        });
        let terminal = a.join().unwrap();
        let (first, second) = b.join().unwrap();
        if first.state == DeliveryState::Terminal {
            assert_eq!(first, terminal);
        }
        if second.state == DeliveryState::Terminal {
            assert_eq!(second, terminal);
        }
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1).unwrap(),
            terminal
        );
        core.validate_invariants_for_host_model().unwrap();
    });
}
#[test]
fn history_loss_and_callback_fence() {
    model("history_loss_and_callback_fence", || {
        let (core, _, _, request) = fixture();
        let token = Arc::new(core.reserve(request, publisher()).unwrap());
        let count = Arc::new(AtomicUsize::new(0));
        let (a_core, a_token, a_count) = (core.clone(), token.clone(), count.clone());
        let a = thread::spawn(move || {
            a_core.execute_reserved(&a_token, publisher(), |binding| {
                assert_eq!(a_count.fetch_add(1, Ordering::SeqCst), 0);
                thread::yield_now();
                success(binding)
            })
        });
        let b_core = core.clone();
        let b = thread::spawn(move || b_core.lose_history());
        let outcome = a.join().unwrap();
        b.join().unwrap();
        match outcome {
            Ok(terminal) => {
                assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
                assert_eq!(count.load(Ordering::SeqCst), 1);
            }
            Err(DeliveryError::HistoryLost) => assert_eq!(count.load(Ordering::SeqCst), 0),
            _ => panic!("unexpected execution/loss outcome"),
        }
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1).unwrap().state,
            DeliveryState::HistoryLost
        );
        assert_eq!(
            core.execute_reserved(&token, publisher(), |_| panic!("fenced callback ran"))
                .err(),
            Some(DeliveryError::HistoryLost)
        );
        assert_eq!(core.window_len(), 0);
        core.validate_invariants_for_host_model().unwrap();
    });
}

struct NativeModelOwner {
    state: loom::sync::Mutex<NativeOwnerState>,
    effects: AtomicUsize,
}

struct NativeOwnerState {
    revision: u64,
    cap_ns: u64,
    grant_epoch: u64,
    ancestor_epochs: [u64; 2],
}

fn apply_native(
    ctx: NativeExecution<'_, NativeModelOwner>,
    expected_owner_address: usize,
) -> PublishOutcome {
    // The captured address is only an identity assertion. Mutation and admission
    // read exclusively from the typed context, never from a captured owner Arc.
    let actual = ctx.owner();
    assert_eq!(std::ptr::from_ref(actual) as usize, expected_owner_address);
    assert_eq!(ctx.id().sequence(), 1);
    assert_eq!(ctx.id().namespace().boot_id(), BootId::from_u128(1));
    assert_eq!(
        ctx.id().namespace().cap_space_id(),
        CapSpaceId::from_u128(2)
    );
    assert_eq!(ctx.ancestor_epochs(), &[7, 11]);
    let binding = ctx.binding();
    assert_eq!(
        binding,
        RequestBinding {
            sequence: 1,
            publisher: publisher(),
            target: ResourceDomainId::from_u128(5),
            stable_object_id: StableObjectId::from_u128(6),
            wire_target_slot: 7,
            wire_target_generation: 8,
            expected_revision: 1,
            period_ns: CPU_PERIOD_NS,
            cap_ns: 10,
            grant_epoch: 13,
            payload_digest: [0x3c; 32],
        }
    );
    let mut state = actual.state.lock().unwrap();
    assert_eq!(state.revision, binding.expected_revision);
    assert_eq!(state.grant_epoch, binding.grant_epoch);
    assert_eq!(state.ancestor_epochs.as_slice(), ctx.ancestor_epochs());
    assert_eq!(actual.effects.fetch_add(1, Ordering::SeqCst), 0);
    let previous_revision = state.revision;
    state.revision += 1;
    state.cap_ns = binding.cap_ns;
    thread::yield_now();
    PublishOutcome::Success {
        stable_object_id: binding.stable_object_id,
        previous_revision,
        saved_revision: state.revision,
        effective_ns: 1,
        consumed_ns: 0,
    }
}

#[test]
fn native_typed_owner_same_token_effect_once() {
    model("native_typed_owner_same_token_effect_once", || {
        let core = ControlCore::with_capacity(BootId::from_u128(1), CapSpaceId::from_u128(2), 2);
        let owner = Arc::new(NativeModelOwner {
            state: loom::sync::Mutex::new(NativeOwnerState {
                revision: 1,
                cap_ns: CPU_PERIOD_NS,
                grant_epoch: 13,
                ancestor_epochs: [7, 11],
            }),
            effects: AtomicUsize::new(0),
        });
        let owner_address = Arc::as_ptr(&owner) as usize;
        let target = NativeTarget::from_owner(
            owner.clone(),
            ResourceDomainId::from_u128(5),
            StableObjectId::from_u128(6),
        )
        .unwrap();
        let grant = NativeGrant::from_owner(target, publisher(), 13, vec![7, 11]).unwrap();
        let request = NativeDeliveryRequest::from_wire(1, grant, 1, 10, 7, 8)
            .unwrap()
            .with_payload_digest([0x3c; 32]);
        let token = Arc::new(core.reserve_native(request, publisher()).unwrap());
        let (a_core, a_token) = (core.clone(), token.clone());
        let a = thread::spawn(move || {
            a_core
                .execute_native_reserved::<NativeModelOwner, _>(&a_token, publisher(), |ctx| {
                    apply_native(ctx, owner_address)
                })
                .unwrap()
        });
        let (b_core, b_token) = (core.clone(), token.clone());
        let b = thread::spawn(move || {
            b_core
                .execute_native_reserved::<NativeModelOwner, _>(&b_token, publisher(), |ctx| {
                    apply_native(ctx, owner_address)
                })
                .unwrap()
        });
        let first = a.join().unwrap();
        let second = b.join().unwrap();
        assert_eq!(first, second);
        assert_eq!(
            first,
            DeliveryObservation {
                state: DeliveryState::Terminal,
                status: Some(DeliveryStatus::Ok),
                id: token.id(),
                stable_object_id: Some(StableObjectId::from_u128(6)),
                saved_revision: Some(2),
                previous_revision: Some(1),
                effective_ns: Some(1),
                consumed_ns: Some(0),
            }
        );
        assert_eq!(owner.effects.load(Ordering::SeqCst), 1);
        let state = owner.state.lock().unwrap();
        assert_eq!(state.revision, 2);
        assert_eq!(state.cap_ns, 10);
        drop(state);
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1).unwrap(),
            first
        );
        core.validate_invariants_for_host_model().unwrap();
    });
}

#[test]
fn retire_execute_loss_threeway() {
    model("retire_execute_loss_threeway", || {
        let (core, authority, _, request) = fixture();
        let token = Arc::new(core.reserve(request, publisher()).unwrap());
        let effects = Arc::new(AtomicUsize::new(0));
        let (a_core, a_token, a_effects) = (core.clone(), token.clone(), effects.clone());
        let execute = thread::spawn(move || {
            a_core.execute_reserved(&a_token, publisher(), |binding| {
                assert_eq!(a_effects.fetch_add(1, Ordering::SeqCst), 0);
                thread::yield_now();
                success(binding)
            })
        });
        let (b_core, b_view) = (core.clone(), core.delivery_view_for(owner()).unwrap());
        let ack =
            HistoryAck::from_owner_receipt(core.identity(), 1, OwnerReceipt::new(owner(), [1; 32]))
                .unwrap();
        let retire = thread::spawn(move || b_core.retire_through(&b_view, ack, &authority));
        let c_core = core.clone();
        let loss = thread::spawn(move || c_core.lose_history());
        let executed = execute.join().unwrap();
        let retired = retire.join().unwrap();
        loss.join().unwrap();
        match executed {
            Ok(result) => {
                assert_eq!(result.status, Some(DeliveryStatus::Ok));
                assert_eq!(effects.load(Ordering::SeqCst), 1);
            }
            Err(DeliveryError::HistoryLost) => assert_eq!(effects.load(Ordering::SeqCst), 0),
            _ => panic!("unexpected execute result"),
        }
        match retired {
            Ok(receipt) => {
                assert_eq!(receipt.retired_through, 1);
                assert!(executed.is_ok());
                assert_eq!(effects.load(Ordering::SeqCst), 1);
            }
            Err(DeliveryError::PendingPrefix | DeliveryError::HistoryLost) => (),
            _ => panic!("unexpected retire result"),
        }
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1).unwrap().state,
            DeliveryState::HistoryLost
        );
        assert_eq!(
            core.execute_reserved(&token, publisher(), |_| panic!("fenced callback ran"))
                .err(),
            Some(DeliveryError::HistoryLost)
        );
        core.validate_invariants_for_host_model().unwrap();
    });
}

#[test]
fn two_deliveries_same_resource_cas() {
    model("two_deliveries_same_resource_cas", || {
        let (core, _, target, first) = fixture();
        let second =
            DeliveryRequest::from_wire(2, target.grant(publisher()).unwrap(), 1, 20, 7, 8).unwrap();
        let first = core.reserve(first, publisher()).unwrap();
        let second = core.reserve(second, publisher()).unwrap();
        let a_core = core.clone();
        let a = thread::spawn(move || a_core.commit(&first, publisher(), 1).unwrap());
        let b_core = core.clone();
        let b = thread::spawn(move || b_core.commit(&second, publisher(), 1).unwrap());
        let a = a.join().unwrap();
        let b = b.join().unwrap();
        assert_eq!(target.revision(), 2);
        assert_eq!(
            [a.status, b.status]
                .into_iter()
                .filter(|status| *status == Some(DeliveryStatus::Ok))
                .count(),
            1
        );
        assert_eq!(
            [a.status, b.status]
                .into_iter()
                .filter(|status| *status == Some(DeliveryStatus::Conflict))
                .count(),
            1
        );
        assert_eq!(
            target.budget().cap_ns,
            if a.status == Some(DeliveryStatus::Ok) {
                10
            } else {
                20
            }
        );
        let view = core.delivery_view();
        assert_eq!(core.query_delivery(&view, 1).unwrap(), a);
        assert_eq!(core.query_delivery(&view, 2).unwrap(), b);
        core.validate_invariants_for_host_model().unwrap();
    });
}

#[test]
fn malformed_callback_reconcile_and_retry() {
    model("malformed_callback_reconcile_and_retry", || {
        let (core, _, _, request) = fixture();
        let token = Arc::new(core.reserve(request, publisher()).unwrap());
        let effects = Arc::new(AtomicUsize::new(0));
        let (reconcile_tx, reconcile_rx) = loom::sync::mpsc::channel();
        let (retry_tx, retry_rx) = loom::sync::mpsc::channel();
        let (a_core, a_token, a_effects) = (core.clone(), token.clone(), effects.clone());
        let a = thread::spawn(move || {
            let result = a_core.execute_reserved(&a_token, publisher(), |_| {
                assert_eq!(a_effects.fetch_add(1, Ordering::SeqCst), 0);
                thread::yield_now();
                PublishOutcome::Failure {
                    status: DeliveryStatus::Ok,
                }
            });
            assert_eq!(result.err(), Some(DeliveryError::InvalidPublish));
            reconcile_tx.send(()).unwrap();
            retry_tx.send(()).unwrap();
        });
        let (b_core, b_token) = (core.clone(), token.clone());
        let b = thread::spawn(move || {
            reconcile_rx.recv().unwrap();
            b_core
                .publish(&b_token, publisher(), success(b_token.binding()))
                .unwrap()
        });
        let (c_core, c_token) = (core.clone(), token.clone());
        let c = thread::spawn(move || {
            retry_rx.recv().unwrap();
            c_core.execute_reserved(&c_token, publisher(), |_| panic!("callback executed twice"))
        });
        a.join().unwrap();
        let terminal = b.join().unwrap();
        let retried = c.join().unwrap();
        assert!(retried == Ok(terminal) || retried == Err(DeliveryError::Busy));
        assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
        assert_eq!(effects.load(Ordering::SeqCst), 1);
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1).unwrap(),
            terminal
        );
        assert_eq!(
            core.execute_reserved(&token, publisher(), |_| panic!("terminal callback ran"))
                .unwrap(),
            terminal
        );
        core.validate_invariants_for_host_model().unwrap();
    });
}

struct ManagementModelOwner {
    state: loom::sync::Mutex<ManagementOwnerState>,
    effects: AtomicUsize,
}

struct ManagementOwnerState {
    delegation: ManagementGrantState,
    independent: ManagementGrantState,
    revision: u64,
    cap_ns: u64,
    consumed_ns: u64,
    alive: bool,
}

fn management_config(id: u128, epoch: u64) -> ManagementGrantConfig {
    ManagementGrantConfig {
        id: ManagementGrantId::from_u128(id),
        publisher: publisher(),
        target: ResourceDomainId::from_u128(5),
        stable_object_id: StableObjectId::from_u128(6),
        epoch,
        issued_at_ns: 0,
        expires_at_ns: 100,
        max_cap_ns: 100,
    }
}

fn apply_management(ctx: NativeExecution<'_, ManagementModelOwner>, now_ns: u64) -> PublishOutcome {
    let snapshot = ctx
        .management_snapshot()
        .expect("saved management snapshot");
    assert_eq!(ctx.ancestor_epochs(), &[7, 11]);
    let binding = ctx.binding();
    let mut state = ctx.owner().state.lock().unwrap();
    let canonical = if snapshot.id() == ManagementGrantId::from_u128(21) {
        &state.delegation
    } else {
        assert_eq!(snapshot.id(), ManagementGrantId::from_u128(22));
        &state.independent
    };
    match canonical.check(snapshot, binding, now_ns) {
        Ok(()) => {}
        Err(ManagementError::Revoked) => {
            return PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            };
        }
        Err(error) => panic!("unexpected management admission: {error:?}"),
    }
    assert!(state.alive);
    assert_eq!(state.revision, binding.expected_revision);
    let previous_revision = state.revision;
    state.revision += 1;
    state.cap_ns = binding.cap_ns;
    ctx.owner().effects.fetch_add(1, Ordering::SeqCst);
    thread::yield_now();
    PublishOutcome::Success {
        stable_object_id: binding.stable_object_id,
        previous_revision,
        saved_revision: state.revision,
        effective_ns: now_ns,
        consumed_ns: state.consumed_ns,
    }
}

#[test]
fn management_revoke_and_native_commit_share_owner_lock() {
    model(
        "management_revoke_and_native_commit_share_owner_lock",
        || {
            let core =
                ControlCore::with_capacity(BootId::from_u128(1), CapSpaceId::from_u128(2), 2);
            let owner = Arc::new(ManagementModelOwner {
                state: loom::sync::Mutex::new(ManagementOwnerState {
                    delegation: ManagementGrantState::new(management_config(21, 13)).unwrap(),
                    independent: ManagementGrantState::new(management_config(22, 17)).unwrap(),
                    revision: 1,
                    cap_ns: CPU_PERIOD_NS,
                    consumed_ns: 0,
                    alive: true,
                }),
                effects: AtomicUsize::new(0),
            });
            let (snapshot, independent_snapshot) = {
                let state = owner.state.lock().unwrap();
                (
                    state.delegation.snapshot().unwrap(),
                    state.independent.snapshot().unwrap(),
                )
            };
            let target = NativeTarget::from_owner(
                owner.clone(),
                ResourceDomainId::from_u128(5),
                StableObjectId::from_u128(6),
            )
            .unwrap();
            let grant = NativeGrant::from_management(target.clone(), snapshot.clone(), vec![7, 11])
                .unwrap();
            let request = NativeDeliveryRequest::from_wire(1, grant, 1, 10, 7, 8).unwrap();
            let token = Arc::new(core.reserve_native(request, publisher()).unwrap());
            let (a_core, a_token) = (core.clone(), token.clone());
            let commit = thread::spawn(move || {
                a_core
                    .execute_native_reserved::<ManagementModelOwner, _>(
                        &a_token,
                        publisher(),
                        |ctx| apply_management(ctx, 1),
                    )
                    .unwrap()
            });
            let b_owner = owner.clone();
            let revoke = thread::spawn(move || {
                let mut state = b_owner.state.lock().unwrap();
                let receipt = state.delegation.revoke();
                thread::yield_now();
                receipt
            });
            let terminal = commit.join().unwrap();
            let revoked = revoke.join().unwrap();
            assert_eq!(revoked.id, ManagementGrantId::from_u128(21));
            let expected_effects = match terminal.status {
                Some(DeliveryStatus::Ok) => 1,
                Some(DeliveryStatus::Revoked) => 0,
                other => panic!("unexpected management terminal {other:?}"),
            };
            assert_eq!(owner.effects.load(Ordering::SeqCst), expected_effects);
            assert_eq!(
                core.query_delivery(&core.delivery_view(), 1).unwrap(),
                terminal
            );
            let revision = {
                let mut state = owner.state.lock().unwrap();
                assert!(state.delegation.is_revoked());
                assert!(!state.independent.is_revoked());
                assert!(state.alive);
                assert_eq!(state.revision, 1 + expected_effects as u64);
                assert_eq!(
                    state.cap_ns,
                    if expected_effects == 1 {
                        10
                    } else {
                        CPU_PERIOD_NS
                    }
                );
                assert_eq!(
                    state.delegation.check(&snapshot, token.binding(), 2),
                    Err(ManagementError::Revoked)
                );
                // Management revocation preserves the original owner's admitted
                // resource and accounting. Runtime can still be charged to it.
                assert!(state.cap_ns >= 1);
                state.consumed_ns += 1;
                state.revision
            };
            let independent =
                NativeGrant::from_management(target, independent_snapshot.clone(), vec![7, 11])
                    .unwrap();
            let independent_request =
                NativeDeliveryRequest::from_wire(2, independent, revision, 20, 7, 8).unwrap();
            let independent_token = core
                .reserve_native(independent_request, publisher())
                .unwrap();
            let independent_terminal = core
                .execute_native_reserved::<ManagementModelOwner, _>(
                    &independent_token,
                    publisher(),
                    |ctx| apply_management(ctx, 2),
                )
                .unwrap();
            assert_eq!(independent_terminal.status, Some(DeliveryStatus::Ok));
            assert_eq!(independent_terminal.previous_revision, Some(revision));
            assert_eq!(independent_terminal.saved_revision, Some(revision + 1));
            assert_eq!(independent_terminal.consumed_ns, Some(1));
            assert_eq!(owner.effects.load(Ordering::SeqCst), expected_effects + 1);
            let state = owner.state.lock().unwrap();
            assert!(state.alive);
            assert_eq!(state.cap_ns, 20);
            assert_eq!(state.consumed_ns, 1);
            assert!(!state.independent.is_revoked());
            drop(state);
            assert_eq!(
                core.query_delivery(&core.delivery_view(), 1).unwrap(),
                terminal
            );
            assert_eq!(
                core.execute_native_reserved::<ManagementModelOwner, _>(
                    &token,
                    publisher(),
                    |_| panic!("terminal management callback repeated")
                )
                .unwrap(),
                terminal
            );
            core.validate_invariants_for_host_model().unwrap();
        },
    );
}
