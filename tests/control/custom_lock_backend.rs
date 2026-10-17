//! Public-backend host tests. No private synchronization module is replaced.
//! The backend deliberately is not Clone. Its role counters identify each
//! delivery lock, and thread-local depth checks distinguish long execution
//! gates from short table/result guards. This does not implement IRQ masking.

use os_control::*;
use std::cell::{Cell, RefCell};
use std::ops::{Deref, DerefMut};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Barrier, Mutex, MutexGuard};
use std::time::{Duration, Instant};

const DEADLINE: Duration = Duration::from_secs(5);

thread_local! {
    static TRACE: RefCell<Option<Arc<Trace>>> = const { RefCell::new(None) };
    static HELD: Cell<[usize; 4]> = const { Cell::new([0; 4]) };
}

fn index(role: LockRole) -> usize {
    match role {
        LockRole::NamespaceTable => 0,
        LockRole::SlotState => 1,
        LockRole::SlotExecution => 2,
        LockRole::HistoryLoss => 3,
    }
}

fn held() -> [usize; 4] {
    HELD.with(Cell::get)
}

struct Trace {
    created: [AtomicUsize; 4],
    acquired: [AtomicUsize; 4],
}

impl Trace {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            created: std::array::from_fn(|_| AtomicUsize::new(0)),
            acquired: std::array::from_fn(|_| AtomicUsize::new(0)),
        })
    }

    fn snapshot(&self) -> [usize; 4] {
        self.acquired
            .each_ref()
            .map(|count| count.load(Ordering::SeqCst))
    }

    fn created(&self) -> [usize; 4] {
        self.created
            .each_ref()
            .map(|count| count.load(Ordering::SeqCst))
    }
}

struct InstallTrace;

impl InstallTrace {
    fn new(trace: &Arc<Trace>) -> Self {
        assert_eq!(held(), [0; 4]);
        TRACE.with(|slot| assert!(slot.borrow_mut().replace(Arc::clone(trace)).is_none()));
        Self
    }
}

impl Drop for InstallTrace {
    fn drop(&mut self) {
        assert_eq!(held(), [0; 4]);
        TRACE.with(|slot| drop(slot.borrow_mut().take()));
    }
}

// No Clone implementation: namespaces/tokens/views must clone their Arc,
// without imposing an accidental Clone requirement on the backend type.
struct RecordingBackend;

struct RecordingMutex<T> {
    inner: Mutex<T>,
    role: LockRole,
    trace: Arc<Trace>,
}

struct RecordingGuard<'a, T> {
    inner: Option<MutexGuard<'a, T>>,
    role: LockRole,
}

impl<T> Deref for RecordingGuard<'_, T> {
    type Target = T;

    fn deref(&self) -> &T {
        self.inner.as_ref().unwrap()
    }
}

impl<T> DerefMut for RecordingGuard<'_, T> {
    fn deref_mut(&mut self) -> &mut T {
        self.inner.as_mut().unwrap()
    }
}

impl<T> Drop for RecordingGuard<'_, T> {
    fn drop(&mut self) {
        // Depth covers the actual unlock; payload/capture cleanup after this
        // guard is destroyed must observe no remaining internal guard.
        drop(self.inner.take());
        HELD.with(|held| {
            let mut depth = held.get();
            depth[index(self.role)] -= 1;
            held.set(depth);
        });
    }
}

impl<T: Send> ControlMutex for RecordingMutex<T> {
    type Value = T;
    type Guard<'a>
        = RecordingGuard<'a, T>
    where
        Self: 'a;

    fn lock(&self) -> Self::Guard<'_> {
        let inner = self.inner.lock().unwrap_or_else(|error| error.into_inner());
        self.trace.acquired[index(self.role)].fetch_add(1, Ordering::SeqCst);
        HELD.with(|held| {
            let mut depth = held.get();
            depth[index(self.role)] += 1;
            held.set(depth);
        });
        RecordingGuard {
            inner: Some(inner),
            role: self.role,
        }
    }
}

impl LockBackend for RecordingBackend {
    type Mutex<T: Send> = RecordingMutex<T>;

    fn new<T: Send>(value: T, role: LockRole) -> Self::Mutex<T> {
        assert_eq!(
            held(),
            [0; 4],
            "backend lock constructed under a backend guard"
        );
        let trace = TRACE.with(|slot| Arc::clone(slot.borrow().as_ref().unwrap()));
        trace.created[index(role)].fetch_add(1, Ordering::SeqCst);
        RecordingMutex {
            inner: Mutex::new(value),
            role,
            trace,
        }
    }
}

type Core = ControlCoreWith<RecordingBackend>;
type Token = ReserveTokenWith<RecordingBackend>;
type Authority = OriginalOwnerAuthorityWith<RecordingBackend>;

fn publisher() -> PublisherId {
    PublisherId::from_u128(1)
}

fn owner_id() -> OwnerId {
    OwnerId::from_u128(2)
}

fn core(capacity: usize) -> (Core, Authority) {
    Core::with_capacity_for_owner(
        BootId::from_u128(3),
        CapSpaceId::from_u128(4),
        capacity,
        owner_id(),
    )
    .unwrap()
}

fn request<T: Send + Sync + 'static>(owner: Arc<T>, sequence: u64) -> NativeDeliveryRequest {
    let target = NativeTarget::from_owner(
        owner,
        ResourceDomainId::from_u128(5),
        StableObjectId::from_u128(6),
    )
    .unwrap();
    let grant = NativeGrant::from_owner(target, publisher(), 1, vec![9, 10]).unwrap();
    NativeDeliveryRequest::from_wire(sequence, grant, 1, 17, 7, 11).unwrap()
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

fn ack(core: &Core, through: u64) -> HistoryAck {
    HistoryAck::from_owner_receipt(
        core.identity(),
        through,
        OwnerReceipt::new(owner_id(), [1; 32]),
    )
    .unwrap()
}

fn deny(core: &Core, token: &Token) {
    core.publish(
        token,
        publisher(),
        PublishOutcome::Failure {
            status: DeliveryStatus::Revoked,
        },
    )
    .unwrap();
}

fn assert_routes(trace: &Trace, before: [usize; 4], required: &[LockRole]) {
    let after = trace.snapshot();
    for role in required {
        assert!(
            after[index(*role)] > before[index(*role)],
            "operation bypassed the supplied {role:?} lock"
        );
    }
    assert_eq!(held(), [0; 4]);
}

#[test]
fn namespace_lock_roles_route_every_native_operation() {
    let trace = Trace::new();
    let _installed = InstallTrace::new(&trace);
    let (core, authority) = core(1);
    assert_eq!(trace.created(), [1, 0, 0, 1]);
    let original = request(Arc::new(AtomicUsize::new(0)), 1);
    let before = trace.snapshot();
    let token = core.reserve_native(original.clone(), publisher()).unwrap();
    assert_routes(&trace, before, &[LockRole::NamespaceTable]);
    assert_eq!(trace.created(), [1, 1, 1, 1]);

    let view = core.delivery_view_for(owner_id()).unwrap();
    let before = trace.snapshot();
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Reserved
    );
    assert_routes(
        &trace,
        before,
        &[LockRole::NamespaceTable, LockRole::SlotState],
    );
    assert_eq!(trace.snapshot()[2..], before[2..]);
    assert_eq!(
        core.reserve_native(original.clone(), publisher()).err(),
        Some(DeliveryError::Busy)
    );
    assert_eq!(
        core.reserve_native(request(Arc::new(()), 2), publisher())
            .err(),
        Some(DeliveryError::ResourceExhausted)
    );
    assert_eq!(trace.created(), [1, 1, 1, 1]);

    let before = trace.snapshot();
    core.execute_native_reserved::<AtomicUsize, _>(&token, publisher(), |context| {
        assert_eq!(held(), [0, 0, 1, 0]);
        assert_eq!(context.ancestor_epochs(), &[9, 10]);
        context.owner().fetch_add(1, Ordering::SeqCst);
        success(context.binding())
    })
    .unwrap();
    assert_routes(
        &trace,
        before,
        &[
            LockRole::NamespaceTable,
            LockRole::SlotState,
            LockRole::SlotExecution,
        ],
    );
    let before = trace.snapshot();
    deny(&core, &token);
    assert_routes(
        &trace,
        before,
        &[
            LockRole::NamespaceTable,
            LockRole::SlotState,
            LockRole::SlotExecution,
        ],
    );
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().status,
        Some(DeliveryStatus::Ok)
    );
    let before = trace.snapshot();
    core.retire_through(&view, ack(&core, 1), &authority)
        .unwrap();
    assert_routes(
        &trace,
        before,
        &[LockRole::NamespaceTable, LockRole::SlotState],
    );

    let pending = core
        .reserve_native(request(Arc::new(()), 2), publisher())
        .unwrap();
    let before = trace.snapshot();
    core.lose_history();
    assert_routes(
        &trace,
        before,
        &[
            LockRole::NamespaceTable,
            LockRole::SlotState,
            LockRole::SlotExecution,
            LockRole::HistoryLoss,
        ],
    );
    assert_eq!(trace.created(), [1, 2, 2, 1]);
    assert_eq!(
        core.query_delivery(&view, 2).unwrap().state,
        DeliveryState::HistoryLost
    );
    assert_eq!(
        core.publish(&pending, publisher(), success(pending.binding())),
        Err(DeliveryError::HistoryLost)
    );
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn custom_backend_concurrent_same_d_has_one_effect() {
    let trace = Trace::new();
    let _installed = InstallTrace::new(&trace);
    let (core, _) = core(2);
    let owner = Arc::new(AtomicUsize::new(0));
    let original = request(Arc::clone(&owner), 1);
    let start = Barrier::new(9);
    std::thread::scope(|scope| {
        for _ in 0..8 {
            let core = core.clone();
            let request = original.clone();
            let trace = Arc::clone(&trace);
            let start = &start;
            scope.spawn(move || {
                let _installed = InstallTrace::new(&trace);
                start.wait();
                match core.reserve_native_or_get(request, publisher()).unwrap() {
                    ReserveAttemptWith::Reserved(token) => {
                        core.execute_native_reserved::<AtomicUsize, _>(
                            &token,
                            publisher(),
                            |context| {
                                assert_eq!(held(), [0, 0, 1, 0]);
                                assert_eq!(context.owner().fetch_add(1, Ordering::SeqCst), 0);
                                std::thread::yield_now();
                                success(context.binding())
                            },
                        )
                        .unwrap();
                    }
                    ReserveAttemptWith::Existing(observation) => assert!(matches!(
                        observation.state,
                        DeliveryState::Reserved | DeliveryState::Terminal
                    )),
                }
            });
        }
        start.wait();
    });
    assert_eq!(owner.load(Ordering::SeqCst), 1);
    assert_eq!(core.next_sequence(), 2);
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1)
            .unwrap()
            .status,
        Some(DeliveryStatus::Ok)
    );
    assert!(core.downgrade().upgrade().is_some());
    core.validate_invariants_for_host_model().unwrap();
}

struct ReleaseCallback(Option<mpsc::Sender<()>>);

impl Drop for ReleaseCallback {
    fn drop(&mut self) {
        if let Some(release) = self.0.take() {
            let _ = release.send(());
        }
    }
}

#[test]
fn custom_backend_loss_waits_for_effect_without_holding_table_or_result() {
    let trace = Trace::new();
    let _installed = InstallTrace::new(&trace);
    let (core, _) = core(2);
    let token = core
        .reserve_native(request(Arc::new(()), 1), publisher())
        .unwrap();
    let (entered_send, entered_recv) = mpsc::channel();
    let (release_send, release_recv) = mpsc::channel();
    let (loss_send, loss_recv) = mpsc::channel();
    std::thread::scope(|scope| {
        let release = ReleaseCallback(Some(release_send));
        let trace_for_execute = Arc::clone(&trace);
        let core_ref = &core;
        let executor = scope.spawn(move || {
            let _installed = InstallTrace::new(&trace_for_execute);
            core_ref
                .execute_native_reserved::<(), _>(&token, publisher(), |context| {
                    assert_eq!(held(), [0, 0, 1, 0]);
                    entered_send.send(()).unwrap();
                    release_recv.recv_timeout(DEADLINE).unwrap();
                    success(context.binding())
                })
                .unwrap()
        });
        entered_recv.recv_timeout(DEADLINE).unwrap();
        let before_loss = trace.snapshot()[3];
        let trace_for_loss = Arc::clone(&trace);
        let loss = scope.spawn(move || {
            let _installed = InstallTrace::new(&trace_for_loss);
            core_ref.lose_history();
            loss_send.send(()).unwrap();
        });
        let deadline = Instant::now() + DEADLINE;
        while trace.snapshot()[3] == before_loss {
            assert!(
                Instant::now() < deadline,
                "loss never acquired supplied loss lock"
            );
            std::thread::yield_now();
        }
        let (query_send, query_recv) = mpsc::channel();
        let query = scope.spawn(move || {
            query_send
                .send(core_ref.query_delivery(&core_ref.delivery_view(), 1))
                .unwrap();
        });
        let observed = query_recv
            .recv_timeout(DEADLINE)
            .expect("history reader waited for the external callback")
            .unwrap();
        assert_eq!(observed.state, DeliveryState::Reserved);
        assert!(matches!(
            loss_recv.try_recv(),
            Err(mpsc::TryRecvError::Empty)
        ));
        drop(release);
        assert_eq!(executor.join().unwrap().status, Some(DeliveryStatus::Ok));
        loss_recv.recv_timeout(DEADLINE).unwrap();
        query.join().unwrap();
        loss.join().unwrap();
    });
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::HistoryLost
    );
    assert_eq!(held(), [0; 4]);
}

struct Capture {
    drops: Arc<AtomicUsize>,
}

impl Drop for Capture {
    fn drop(&mut self) {
        assert_eq!(
            held(),
            [0; 4],
            "owned callback capture dropped under a backend guard"
        );
        self.drops.fetch_add(1, Ordering::SeqCst);
    }
}

#[test]
fn custom_backend_owned_capture_cleanup_follows_publication_and_unlock() {
    let trace = Trace::new();
    let _installed = InstallTrace::new(&trace);
    let (core, _) = core(1);
    let token = core
        .reserve_native(request(Arc::new(()), 1), publisher())
        .unwrap();
    let drops = Arc::new(AtomicUsize::new(0));
    let capture = Capture {
        drops: Arc::clone(&drops),
    };
    core.execute_native_reserved::<(), _>(&token, publisher(), move |context| {
        std::hint::black_box(&capture);
        assert_eq!(held(), [0, 0, 1, 0]);
        success(context.binding())
    })
    .unwrap();
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    let capture = Capture {
        drops: Arc::clone(&drops),
    };
    core.execute_native_reserved::<(), _>(&token, publisher(), move |_| {
        std::hint::black_box(&capture);
        panic!("terminal retry called effect")
    })
    .unwrap();
    assert_eq!(drops.load(Ordering::SeqCst), 2);
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1)
            .unwrap()
            .status,
        Some(DeliveryStatus::Ok)
    );
}

#[test]
fn custom_backend_unwind_releases_guards_and_preserves_pending_fence() {
    let trace = Trace::new();
    let _installed = InstallTrace::new(&trace);
    let (core, _) = core(1);
    let token = core
        .reserve_native(request(Arc::new(()), 1), publisher())
        .unwrap();
    let drops = Arc::new(AtomicUsize::new(0));
    let capture = Capture {
        drops: Arc::clone(&drops),
    };
    assert!(catch_unwind(AssertUnwindSafe(|| {
        core.execute_native_reserved::<(), _>(&token, publisher(), move |_| {
            std::hint::black_box(&capture);
            assert_eq!(held(), [0, 0, 1, 0]);
            panic!("injected public-backend effect unwind")
        })
    }))
    .is_err());
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    assert_eq!(held(), [0; 4]);
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::Reserved
    );
    assert_eq!(
        core.execute_native_reserved::<(), _>(&token, publisher(), |_| panic!(
            "re-executed pending effect"
        )),
        Err(DeliveryError::Busy)
    );
    core.lose_history();
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::HistoryLost
    );
}

struct ReenterOwner {
    core: WeakControlCoreWith<RecordingBackend>,
    drops: Arc<AtomicUsize>,
}

impl Drop for ReenterOwner {
    fn drop(&mut self) {
        assert_eq!(held(), [0; 4], "native owner dropped under a backend guard");
        if let Some(core) = self.core.upgrade() {
            let state = core.query_delivery(&core.delivery_view(), 1).unwrap().state;
            assert!(matches!(
                state,
                DeliveryState::Retired | DeliveryState::HistoryLost
            ));
        }
        self.drops.fetch_add(1, Ordering::SeqCst);
    }
}

#[test]
fn custom_backend_reclamation_releases_guards_before_owner_destructor() {
    let trace = Trace::new();
    let _installed = InstallTrace::new(&trace);
    for history_loss in [false, true] {
        let (core, authority) = core(1);
        let drops = Arc::new(AtomicUsize::new(0));
        let owner = Arc::new(ReenterOwner {
            core: core.downgrade(),
            drops: Arc::clone(&drops),
        });
        let token = core.reserve_native(request(owner, 1), publisher()).unwrap();
        if history_loss {
            core.lose_history();
        } else {
            deny(&core, &token);
            let view = core.delivery_view_for(owner_id()).unwrap();
            core.retire_through(&view, ack(&core, 1), &authority)
                .unwrap();
        }
        assert_eq!(drops.load(Ordering::SeqCst), 1);
        assert_eq!(held(), [0; 4]);
    }
}
