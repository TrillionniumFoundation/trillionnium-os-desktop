//! Host-only callback lifetime regressions. The native owner below is a test
//! fixture, not an Asterinas scheduler. Cleanup probes use bounded helper
//! threads so an execution-gate regression fails instead of hanging a suite.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryObservation, DeliveryRequest,
    DeliveryState, DeliveryStatus, NativeDeliveryRequest, NativeExecution, NativeGrant,
    NativeTarget, PublishOutcome, PublisherId, ReserveToken, ResourceDomain, ResourceDomainId,
    StableObjectId, WeakControlCore, CPU_PERIOD_NS,
};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

fn publisher() -> PublisherId {
    PublisherId::from_u128(3)
}

struct Owner {
    state: Mutex<OwnerState>,
    effects: AtomicUsize,
}

struct OwnerState {
    revision: u64,
    cap_ns: u64,
}

fn native_fixture(n: u128) -> (ControlCore, Arc<Owner>, ReserveToken) {
    let core = ControlCore::with_capacity(BootId::from_u128(n), CapSpaceId::from_u128(n), 1);
    let owner = Arc::new(Owner {
        state: Mutex::new(OwnerState {
            revision: 1,
            cap_ns: CPU_PERIOD_NS,
        }),
        effects: AtomicUsize::new(0),
    });
    let target = NativeTarget::from_owner(
        owner.clone(),
        ResourceDomainId::from_u128(5),
        StableObjectId::from_u128(6),
    )
    .unwrap();
    let grant = NativeGrant::from_owner(target, publisher(), 1, vec![7, 11]).unwrap();
    let token = core
        .reserve_native(
            NativeDeliveryRequest::from_wire(1, grant, 1, 10, 7, 8).unwrap(),
            publisher(),
        )
        .unwrap();
    (core, owner, token)
}

fn apply(ctx: NativeExecution<'_, Owner>) -> PublishOutcome {
    assert_eq!(ctx.ancestor_epochs(), &[7, 11]);
    let binding = ctx.binding();
    let mut state = ctx.owner().state.lock().unwrap();
    assert_eq!(state.revision, binding.expected_revision);
    assert_eq!(ctx.owner().effects.fetch_add(1, Ordering::SeqCst), 0);
    let previous_revision = state.revision;
    state.revision += 1;
    state.cap_ns = binding.cap_ns;
    PublishOutcome::Success {
        stable_object_id: binding.stable_object_id,
        previous_revision,
        saved_revision: state.revision,
        effective_ns: 1,
        consumed_ns: 0,
    }
}

#[derive(Clone)]
struct CleanupProbe {
    observed: Arc<Mutex<Option<DeliveryObservation>>>,
    completed_before_drop_return: Arc<AtomicBool>,
    worker: Arc<Mutex<Option<JoinHandle<()>>>>,
}

impl CleanupProbe {
    fn new() -> Self {
        Self {
            observed: Arc::new(Mutex::new(None)),
            completed_before_drop_return: Arc::new(AtomicBool::new(false)),
            worker: Arc::new(Mutex::new(None)),
        }
    }

    fn finish(&self) -> DeliveryObservation {
        if let Some(worker) = self.worker.lock().unwrap().take() {
            worker.join().unwrap();
        }
        assert!(
            self.completed_before_drop_return.load(Ordering::SeqCst),
            "capture cleanup waited on an execution gate still held by its caller"
        );
        self.observed
            .lock()
            .unwrap()
            .expect("capture cleanup query")
    }
}

struct Cleanup {
    namespace: WeakControlCore,
    probe: CleanupProbe,
    bytes: Vec<u8>,
}

impl Cleanup {
    fn new(core: &ControlCore, probe: &CleanupProbe) -> Self {
        Self {
            namespace: core.downgrade(),
            probe: probe.clone(),
            bytes: vec![0x42; 1024],
        }
    }
}

impl Drop for Cleanup {
    fn drop(&mut self) {
        let Some(core) = self.namespace.upgrade() else {
            return;
        };
        let observation = core.query_delivery(&core.delivery_view(), 1).ok();
        *self.probe.observed.lock().unwrap() = observation;
        let (complete, completed) = mpsc::channel();
        let Ok(worker) = thread::Builder::new().spawn(move || {
            core.lose_history();
            let _ = complete.send(());
        }) else {
            return;
        };
        *self.probe.worker.lock().unwrap() = Some(worker);
        // If a regression retains the gate, return after the bounded wait so
        // unwinding/publication can release it. finish() then joins the helper
        // and reports the exact gate-order failure, with no stranded thread.
        let finished = completed.recv_timeout(Duration::from_secs(5)).is_ok();
        self.probe
            .completed_before_drop_return
            .store(finished, Ordering::SeqCst);
    }
}

#[test]
fn native_success_publishes_before_owned_capture_cleanup_and_loss() {
    let (core, owner, token) = native_fixture(1_610_001);
    let probe = CleanupProbe::new();
    let cleanup = Cleanup::new(&core, &probe);
    let mut calls = 0;
    let calls_ref = &mut calls;
    let result = core
        .execute_native_reserved::<Owner, _>(&token, publisher(), move |ctx| {
            std::hint::black_box(&cleanup.bytes);
            *calls_ref += 1;
            apply(ctx)
        })
        .unwrap();
    assert_eq!(calls, 1, "FnMut remains a single invocation per D");
    assert_eq!(result.status, Some(DeliveryStatus::Ok));
    assert_eq!(probe.finish(), result);
    assert_eq!(owner.effects.load(Ordering::SeqCst), 1);
    assert_eq!(owner.state.lock().unwrap().revision, 2);
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::HistoryLost
    );
    assert_eq!(
        core.execute_native_reserved::<Owner, _>(&token, publisher(), |_| {
            panic!("lost native callback repeated")
        })
        .err(),
        Some(DeliveryError::HistoryLost)
    );
}

#[test]
fn host_success_releases_gate_before_owned_capture_cleanup() {
    let core = ControlCore::with_capacity(
        BootId::from_u128(1_610_002),
        CapSpaceId::from_u128(1_610_002),
        1,
    );
    let target = ResourceDomain::new(
        ResourceDomainId::from_u128(5),
        StableObjectId::from_u128(6),
        None,
        CPU_PERIOD_NS,
    )
    .unwrap();
    let token = core
        .reserve(
            DeliveryRequest::new(1, target.grant(publisher()).unwrap(), 1, 10),
            publisher(),
        )
        .unwrap();
    let probe = CleanupProbe::new();
    let cleanup = Cleanup::new(&core, &probe);
    let result = core
        .execute_reserved(&token, publisher(), move |binding| {
            std::hint::black_box(&cleanup.bytes);
            PublishOutcome::Success {
                stable_object_id: binding.stable_object_id,
                previous_revision: 1,
                saved_revision: 2,
                effective_ns: 1,
                consumed_ns: 0,
            }
        })
        .unwrap();
    assert_eq!(probe.finish(), result);
    assert_eq!(result.status, Some(DeliveryStatus::Ok));
}

#[test]
fn body_unwind_releases_gate_before_capture_cleanup_and_keeps_one_effect() {
    let (core, owner, token) = native_fixture(1_610_003);
    let probe = CleanupProbe::new();
    let cleanup = Cleanup::new(&core, &probe);
    let unwind = catch_unwind(AssertUnwindSafe(|| {
        core.execute_native_reserved::<Owner, _>(&token, publisher(), move |ctx| {
            std::hint::black_box(&cleanup.bytes);
            let _effect = apply(ctx);
            panic!("injected post-effect callback body panic")
        })
    }));
    assert!(unwind.is_err());
    let observed = probe.finish();
    assert_eq!(observed.state, DeliveryState::Reserved);
    assert_eq!(observed.status, None);
    assert_eq!(owner.effects.load(Ordering::SeqCst), 1);
    assert_eq!(owner.state.lock().unwrap().revision, 2);
    assert_eq!(
        core.execute_native_reserved::<Owner, _>(&token, publisher(), |_| {
            panic!("unwound native callback repeated")
        })
        .err(),
        Some(DeliveryError::HistoryLost)
    );
}

#[test]
fn malformed_outcome_releases_gate_before_capture_cleanup() {
    let (core, owner, token) = native_fixture(1_610_004);
    let probe = CleanupProbe::new();
    let cleanup = Cleanup::new(&core, &probe);
    let result = core.execute_native_reserved::<Owner, _>(&token, publisher(), move |ctx| {
        std::hint::black_box(&cleanup.bytes);
        let _effect = apply(ctx);
        PublishOutcome::Failure {
            status: DeliveryStatus::Ok,
        }
    });
    assert_eq!(result.err(), Some(DeliveryError::InvalidPublish));
    assert_eq!(probe.finish().state, DeliveryState::Reserved);
    assert_eq!(owner.effects.load(Ordering::SeqCst), 1);
}

#[test]
fn terminal_retry_drops_unused_callback_outside_gate_without_invoking_it() {
    let (core, owner, token) = native_fixture(1_610_005);
    let first = core
        .execute_native_reserved::<Owner, _>(&token, publisher(), apply)
        .unwrap();
    let probe = CleanupProbe::new();
    let cleanup = Cleanup::new(&core, &probe);
    let retried = core
        .execute_native_reserved::<Owner, _>(&token, publisher(), move |_| {
            std::hint::black_box(&cleanup.bytes);
            panic!("terminal callback invoked")
        })
        .unwrap();
    assert_eq!(retried, first);
    assert_eq!(probe.finish(), first);
    assert_eq!(owner.effects.load(Ordering::SeqCst), 1);
}

#[test]
fn wrong_type_drops_unused_callback_without_admitting_an_effect() {
    let (core, owner, token) = native_fixture(1_610_006);
    let probe = CleanupProbe::new();
    let cleanup = Cleanup::new(&core, &probe);
    assert_eq!(
        core.execute_native_reserved::<u64, _>(&token, publisher(), move |_| {
            std::hint::black_box(&cleanup.bytes);
            panic!("wrong owner type callback invoked")
        })
        .err(),
        Some(DeliveryError::InvalidRequest)
    );
    assert_eq!(probe.finish().state, DeliveryState::Reserved);
    assert_eq!(owner.effects.load(Ordering::SeqCst), 0);
}

struct PanicCleanup {
    bytes: Vec<u8>,
}

impl Drop for PanicCleanup {
    fn drop(&mut self) {
        panic!("injected capture destructor panic")
    }
}

#[test]
fn capture_destructor_panic_after_success_cannot_erase_terminal_publication() {
    let (core, owner, token) = native_fixture(1_610_007);
    let cleanup = PanicCleanup {
        bytes: vec![0x42; 1024],
    };
    let unwind = catch_unwind(AssertUnwindSafe(|| {
        core.execute_native_reserved::<Owner, _>(&token, publisher(), move |ctx| {
            std::hint::black_box(&cleanup.bytes);
            apply(ctx)
        })
    }));
    assert!(unwind.is_err());
    let saved = core.query_delivery(&core.delivery_view(), 1).unwrap();
    assert_eq!(saved.state, DeliveryState::Terminal);
    assert_eq!(saved.status, Some(DeliveryStatus::Ok));
    assert_eq!(saved.previous_revision, Some(1));
    assert_eq!(saved.saved_revision, Some(2));
    assert_eq!(owner.effects.load(Ordering::SeqCst), 1);
    assert_eq!(
        core.execute_native_reserved::<Owner, _>(&token, publisher(), |_| {
            panic!("capture destructor panic reopened the callback")
        })
        .unwrap(),
        saved
    );
}
