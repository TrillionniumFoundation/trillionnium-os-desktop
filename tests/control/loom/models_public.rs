//! Public-backend host models: every production module, including sync.rs, is
//! copied unchanged. Only this external LockBackend uses Loom mutexes. Standard
//! Arc/Weak reference counts and the actual kernel lock adapter are not modeled.

use loom::sync::{Mutex, MutexGuard};
use loom::thread;
use os_control::*;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

struct PublicLoomMutex<T: Send>(Mutex<T>);

impl<T: Send> ControlMutex for PublicLoomMutex<T> {
    type Value = T;
    type Guard<'a>
        = MutexGuard<'a, T>
    where
        Self: 'a;

    fn lock(&self) -> Self::Guard<'_> {
        self.0.lock().unwrap()
    }
}

struct PublicLoomBackend;

impl LockBackend for PublicLoomBackend {
    type Mutex<T: Send> = PublicLoomMutex<T>;

    fn new<T: Send>(value: T, _role: LockRole) -> Self::Mutex<T> {
        PublicLoomMutex(Mutex::new(value))
    }
}

type Core = ControlCoreWith<PublicLoomBackend>;
type Token = ReserveTokenWith<PublicLoomBackend>;
type Authority = OriginalOwnerAuthorityWith<PublicLoomBackend>;

fn model(name: &str, f: impl Fn() + Send + Sync + 'static) {
    let schedules = Arc::new(AtomicUsize::new(0));
    let count = schedules.clone();
    let mut builder = loom::model::Builder::new();
    builder.max_threads = 4;
    builder.max_branches = 10_000;
    builder.preemption_bound = Some(3);
    builder.max_permutations = None;
    builder.max_duration = None;
    builder.check(move || {
        count.fetch_add(1, Ordering::Relaxed);
        f();
    });
    eprintln!("MODEL {name}: schedules={} max_threads=4 preemption_bound=3 max_branches=10000 max_permutations=none max_duration=none", schedules.load(Ordering::Relaxed));
}

fn publisher() -> PublisherId {
    PublisherId::from_u128(3)
}

fn owner_id() -> OwnerId {
    OwnerId::from_u128(4)
}

struct ModelOwner {
    state: Mutex<OwnerState>,
}

struct OwnerState {
    revoked: bool,
    revision: u64,
    effects: usize,
    cap_ns: u64,
}

fn fixture() -> (Core, Authority, Arc<ModelOwner>, NativeDeliveryRequest) {
    let (core, authority) = Core::with_capacity_for_owner(
        BootId::from_u128(1),
        CapSpaceId::from_u128(2),
        2,
        owner_id(),
    )
    .unwrap();
    let owner = Arc::new(ModelOwner {
        state: Mutex::new(OwnerState {
            revoked: false,
            revision: 1,
            effects: 0,
            cap_ns: CPU_PERIOD_NS,
        }),
    });
    let target = NativeTarget::from_owner(
        owner.clone(),
        ResourceDomainId::from_u128(5),
        StableObjectId::from_u128(6),
    )
    .unwrap();
    let grant = NativeGrant::from_owner(target, publisher(), 1, vec![7, 11]).unwrap();
    let request = NativeDeliveryRequest::from_wire(1, grant, 1, 10, 7, 8).unwrap();
    (core, authority, owner, request)
}

fn apply(ctx: NativeExecution<'_, ModelOwner>) -> PublishOutcome {
    assert_eq!(ctx.ancestor_epochs(), &[7, 11]);
    let binding = ctx.binding();
    let mut state = ctx.owner().state.lock().unwrap();
    if state.revoked {
        return PublishOutcome::Failure {
            status: DeliveryStatus::Revoked,
        };
    }
    assert_eq!(state.revision, binding.expected_revision);
    assert_eq!(state.effects, 0);
    state.effects += 1;
    state.revision += 1;
    state.cap_ns = binding.cap_ns;
    thread::yield_now();
    PublishOutcome::Success {
        stable_object_id: binding.stable_object_id,
        previous_revision: binding.expected_revision,
        saved_revision: state.revision,
        effective_ns: 1,
        consumed_ns: 0,
    }
}

fn execute(core: &Core, token: &Token) -> Result<DeliveryObservation, DeliveryError> {
    core.execute_native_reserved::<ModelOwner, _>(token, publisher(), apply)
}

fn assert_success(terminal: DeliveryObservation) {
    assert_eq!(terminal.state, DeliveryState::Terminal);
    assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
    assert_eq!(
        terminal.stable_object_id,
        Some(StableObjectId::from_u128(6))
    );
    assert_eq!(terminal.previous_revision, Some(1));
    assert_eq!(terminal.saved_revision, Some(2));
    assert_eq!(terminal.effective_ns, Some(1));
    assert_eq!(terminal.consumed_ns, Some(0));
}

#[test]
fn public_backend_same_d_reservation_and_effect_once() {
    model("public_backend_same_d_reservation_and_effect_once", || {
        let (core, _, owner, request) = fixture();
        let worker = |core: Core, request: NativeDeliveryRequest| match core
            .reserve_native_or_get(request, publisher())
            .unwrap()
        {
            ReserveAttemptWith::Reserved(token) => assert_success(execute(&core, &token).unwrap()),
            ReserveAttemptWith::Existing(observation) => assert!(matches!(
                observation.state,
                DeliveryState::Reserved | DeliveryState::Terminal
            )),
        };
        let (a_core, a_request) = (core.clone(), request.clone());
        let a = thread::spawn(move || worker(a_core, a_request));
        let b_core = core.clone();
        let b = thread::spawn(move || worker(b_core, request));
        a.join().unwrap();
        b.join().unwrap();
        assert_eq!(core.window_len(), 1);
        assert_eq!(core.next_sequence(), 2);
        assert_eq!(owner.state.lock().unwrap().effects, 1);
        assert_success(core.query_delivery(&core.delivery_view(), 1).unwrap());
        core.validate_invariants_for_host_model().unwrap();
    });
}

#[test]
fn public_backend_same_token_effect_once() {
    model("public_backend_same_token_effect_once", || {
        let (core, _, owner, request) = fixture();
        let token = Arc::new(core.reserve_native(request, publisher()).unwrap());
        let (a_core, a_token) = (core.clone(), token.clone());
        let a = thread::spawn(move || execute(&a_core, &a_token).unwrap());
        let (b_core, b_token) = (core.clone(), token.clone());
        let b = thread::spawn(move || execute(&b_core, &b_token).unwrap());
        let first = a.join().unwrap();
        assert_eq!(first, b.join().unwrap());
        assert_success(first);
        assert_eq!(owner.state.lock().unwrap().effects, 1);
        core.validate_invariants_for_host_model().unwrap();
    });
}

#[test]
fn public_backend_revoke_and_commit_linearize() {
    model("public_backend_revoke_and_commit_linearize", || {
        let (core, _, owner, request) = fixture();
        let token = core.reserve_native(request, publisher()).unwrap();
        let a_core = core.clone();
        let a = thread::spawn(move || execute(&a_core, &token).unwrap());
        let b_owner = owner.clone();
        let b = thread::spawn(move || {
            b_owner.state.lock().unwrap().revoked = true;
        });
        let terminal = a.join().unwrap();
        b.join().unwrap();
        let state = owner.state.lock().unwrap();
        assert!(state.revoked);
        match terminal.status {
            Some(DeliveryStatus::Ok) => {
                assert_success(terminal);
                assert_eq!((state.effects, state.revision, state.cap_ns), (1, 2, 10));
            }
            Some(DeliveryStatus::Revoked) => {
                assert_eq!(
                    (state.effects, state.revision, state.cap_ns),
                    (0, 1, CPU_PERIOD_NS)
                );
            }
            status => panic!("unexpected terminal status {status:?}"),
        }
        drop(state);
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1).unwrap(),
            terminal
        );
        core.validate_invariants_for_host_model().unwrap();
    });
}

#[test]
fn public_backend_retire_and_query_linearize() {
    model("public_backend_retire_and_query_linearize", || {
        let (core, authority, owner, request) = fixture();
        let replay = request.clone();
        let token = core.reserve_native(request, publisher()).unwrap();
        let terminal = execute(&core, &token).unwrap();
        let view = core.delivery_view_for(owner_id()).unwrap();
        let ack = authority.history_ack(1, [1; 32]).unwrap();
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
            core.reserve_native(replay, publisher()).err(),
            Some(DeliveryError::Retired)
        );
        assert_eq!(owner.state.lock().unwrap().effects, 1);
        core.validate_invariants_for_host_model().unwrap();
    });
}

#[test]
fn public_backend_publish_and_observe_never_tear() {
    model("public_backend_publish_and_observe_never_tear", || {
        let (core, _, owner, request) = fixture();
        let token = core.reserve_native(request, publisher()).unwrap();
        let a_core = core.clone();
        let a = thread::spawn(move || execute(&a_core, &token).unwrap());
        let (b_core, b_owner) = (core.clone(), owner.clone());
        let b = thread::spawn(move || {
            let view = b_core.delivery_view();
            let first = b_core.query_delivery(&view, 1).unwrap();
            thread::yield_now();
            let second = b_core.query_delivery(&view, 1).unwrap();
            for observation in [first, second] {
                assert!(matches!(
                    observation.state,
                    DeliveryState::Reserved | DeliveryState::Terminal
                ));
                if observation.state == DeliveryState::Terminal {
                    assert_success(observation);
                    let state = b_owner.state.lock().unwrap();
                    assert_eq!((state.effects, state.revision, state.cap_ns), (1, 2, 10));
                }
            }
            if first.state == DeliveryState::Terminal {
                assert_eq!(first, second);
            }
        });
        assert_success(a.join().unwrap());
        b.join().unwrap();
        assert_eq!(owner.state.lock().unwrap().effects, 1);
        core.validate_invariants_for_host_model().unwrap();
    });
}

#[test]
fn public_backend_history_loss_and_execution_fence() {
    model("public_backend_history_loss_and_execution_fence", || {
        let (core, _, owner, request) = fixture();
        let replay = request.clone();
        let token = Arc::new(core.reserve_native(request, publisher()).unwrap());
        let (a_core, a_token) = (core.clone(), token.clone());
        let a = thread::spawn(move || execute(&a_core, &a_token));
        let b_core = core.clone();
        let b = thread::spawn(move || b_core.lose_history());
        let result = a.join().unwrap();
        b.join().unwrap();
        let effects = owner.state.lock().unwrap().effects;
        match result {
            Ok(terminal) => {
                assert_success(terminal);
                assert_eq!(effects, 1);
            }
            Err(DeliveryError::HistoryLost) => assert_eq!(effects, 0),
            other => panic!("unexpected loss/execution outcome: {other:?}"),
        }
        assert_eq!(
            core.query_delivery(&core.delivery_view(), 1).unwrap().state,
            DeliveryState::HistoryLost
        );
        assert_eq!(
            core.reserve_native(replay, publisher()).err(),
            Some(DeliveryError::HistoryLost)
        );
        assert_eq!(
            execute(&core, &token).err(),
            Some(DeliveryError::HistoryLost)
        );
        core.validate_invariants_for_host_model().unwrap();
    });
}
