//! Synthetic host owners using weak namespace backreferences. This prevents
//! this particular ownership cycle; arbitrary strong Arc cycles are still a
//! caller lifecycle error, and no test establishes native kernel authority.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryState, DeliveryStatus, HistoryAck,
    NativeDeliveryRequest, NativeGrant, NativeTarget, OriginalOwnerAuthority, OwnerId,
    PublishOutcome,
    PublisherId, ReserveToken, ResourceDomainId, StableObjectId, WeakControlCore,
};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::Duration;

fn publisher() -> PublisherId {
    PublisherId::from_u128(1_300_001)
}

fn owner_id() -> OwnerId {
    OwnerId::from_u128(1_300_002)
}

#[derive(Clone, Copy)]
enum Action {
    Read,
    Lose,
}

struct DropReport {
    called: AtomicUsize,
    upgraded: AtomicBool,
    finished_before_return: AtomicBool,
    next_sequence: AtomicU64,
    worker: Mutex<Option<thread::JoinHandle<()>>>,
}

impl DropReport {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            called: AtomicUsize::new(0),
            upgraded: AtomicBool::new(false),
            finished_before_return: AtomicBool::new(false),
            next_sequence: AtomicU64::new(0),
            worker: Mutex::new(None),
        })
    }

    fn join(&self) {
        self.worker
            .lock()
            .unwrap()
            .take()
            .expect("native owner was not destroyed")
            .join()
            .unwrap();
    }
}

struct WeakBacklinkedOwner {
    namespace: WeakControlCore,
    report: Arc<DropReport>,
    action: Action,
}

impl Drop for WeakBacklinkedOwner {
    fn drop(&mut self) {
        self.report.called.fetch_add(1, Ordering::SeqCst);
        let weak = self.namespace.clone();
        let report = Arc::clone(&self.report);
        let action = self.action;
        let (done_send, done_recv) = mpsc::channel();
        let worker = thread::spawn(move || {
            if let Some(core) = weak.upgrade() {
                report.upgraded.store(true, Ordering::Release);
                if matches!(action, Action::Lose) {
                    core.lose_history();
                }
                report
                    .next_sequence
                    .store(core.next_sequence(), Ordering::Release);
            }
            let _ = done_send.send(());
        });
        *self.report.worker.lock().unwrap() = Some(worker);
        // Record a lock-order regression and return normally, so the outer
        // method can release its guards before the test joins this worker.
        self.report.finished_before_return.store(
            done_recv.recv_timeout(Duration::from_secs(1)).is_ok(),
            Ordering::Release,
        );
    }
}

fn reserve_owner(
    core: &ControlCore,
    n: u128,
    action: Action,
    report: &Arc<DropReport>,
) -> (ReserveToken, std::sync::Weak<WeakBacklinkedOwner>) {
    let owner = Arc::new(WeakBacklinkedOwner {
        namespace: core.downgrade(),
        report: Arc::clone(report),
        action,
    });
    let weak = Arc::downgrade(&owner);
    let target = NativeTarget::from_owner(
        Arc::clone(&owner),
        ResourceDomainId::from_u128(n),
        StableObjectId::from_u128(n),
    )
    .unwrap();
    let grant = NativeGrant::from_owner(target, publisher(), 1, Vec::new()).unwrap();
    let request = NativeDeliveryRequest::from_wire(1, grant, 1, 17, 7, 11).unwrap();
    let token = core.reserve_native(request, publisher()).unwrap();
    drop(owner);
    (token, weak)
}

fn ack(authority: &OriginalOwnerAuthority) -> HistoryAck {
    authority.history_ack(1, [0x49; 32]).unwrap()
}

#[test]
fn weak_owner_backlink_and_retained_token_do_not_keep_namespace_or_owner_alive() {
    let core = ControlCore::new(
        BootId::from_u128(1_310_001),
        CapSpaceId::from_u128(1_310_001),
    );
    let weak_core = core.downgrade();
    let report = DropReport::new();
    let (token, weak_owner) = reserve_owner(&core, 1_310_001, Action::Read, &report);
    let binding = token.binding();
    assert!(weak_owner.upgrade().is_some());
    drop(core);
    report.join();
    assert!(weak_core.upgrade().is_none());
    assert!(weak_owner.upgrade().is_none());
    assert_eq!(report.called.load(Ordering::SeqCst), 1);
    assert!(!report.upgraded.load(Ordering::Acquire));
    assert!(report.finished_before_return.load(Ordering::Acquire));
    assert_eq!(token.binding(), binding);
    assert_eq!(token.publisher(), publisher());
}

#[test]
fn retired_owner_drop_can_upgrade_weak_core_and_read_namespace_without_a_lock_cycle() {
    let (core, authority) = ControlCore::with_original_owner(
        BootId::from_u128(1_320_001),
        CapSpaceId::from_u128(1_320_001),
        owner_id(),
    )
    .unwrap();
    let report = DropReport::new();
    let (token, weak_owner) = reserve_owner(&core, 1_320_001, Action::Read, &report);
    core.publish(
        &token,
        publisher(),
        PublishOutcome::Failure {
            status: DeliveryStatus::Revoked,
        },
    )
    .unwrap();
    let view = core.delivery_view_for(owner_id()).unwrap();
    core.retire_through(&view, ack(&authority), &authority).unwrap();
    report.join();
    assert!(weak_owner.upgrade().is_none());
    assert!(report.upgraded.load(Ordering::Acquire));
    assert!(report.finished_before_return.load(Ordering::Acquire));
    assert_eq!(report.next_sequence.load(Ordering::Acquire), 2);
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Retired
    );
}

#[test]
fn lost_owner_drop_can_upgrade_weak_core_and_reenter_loss_without_a_lock_cycle() {
    let core = ControlCore::new(
        BootId::from_u128(1_330_001),
        CapSpaceId::from_u128(1_330_001),
    );
    let report = DropReport::new();
    let (token, weak_owner) = reserve_owner(&core, 1_330_001, Action::Lose, &report);
    core.lose_history();
    report.join();
    assert!(weak_owner.upgrade().is_none());
    assert!(report.upgraded.load(Ordering::Acquire));
    assert!(report.finished_before_return.load(Ordering::Acquire));
    assert_eq!(report.next_sequence.load(Ordering::Acquire), 2);
    assert_eq!(core.window_len(), 0);
    assert_eq!(
        core.execute_native_reserved::<WeakBacklinkedOwner, _>(&token, publisher(), |_| {
            panic!("lost D executed")
        }),
        Err(DeliveryError::HistoryLost)
    );
}

#[test]
fn weak_upgrade_lifetime_follows_real_view_and_owner_authority_references() {
    let (core, authority) = ControlCore::with_original_owner(
        BootId::from_u128(1_340_001),
        CapSpaceId::from_u128(1_340_001),
        owner_id(),
    )
    .unwrap();
    let weak = core.downgrade();
    let weak_clone = weak.clone();
    let view = core.delivery_view();
    drop(core);
    assert!(
        weak.upgrade().is_some(),
        "view and original authority retain history"
    );
    drop(view);
    assert!(
        weak.upgrade().is_some(),
        "original authority still retains history"
    );
    drop(authority);
    assert!(weak.upgrade().is_none());
    assert!(weak_clone.upgrade().is_none());
}

#[test]
fn upgraded_core_neither_replays_old_d_nor_substitutes_a_foreign_retirement_authority() {
    let boot = BootId::from_u128(1_350_001);
    let space = CapSpaceId::from_u128(1_350_001);
    let (core, authority) = ControlCore::with_original_owner(boot, space, owner_id()).unwrap();
    let (_, foreign_authority) = ControlCore::with_original_owner(boot, space, owner_id()).unwrap();
    let weak = core.downgrade();
    let report = DropReport::new();
    let (token, _) = reserve_owner(&core, 1_350_001, Action::Read, &report);
    let terminal = core
        .publish(
            &token,
            publisher(),
            PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            },
        )
        .unwrap();
    let view = core.delivery_view_for(owner_id()).unwrap();
    let upgraded = weak.upgrade().unwrap();
    assert_eq!(
        upgraded.retire_through(&view, ack(&authority), &foreign_authority),
        Err(DeliveryError::PermissionDenied)
    );
    assert_eq!(upgraded.query_delivery(&view, 1).unwrap(), terminal);
    upgraded
        .retire_through(&view, ack(&authority), &authority)
        .unwrap();
    report.join();
    let callbacks = AtomicUsize::new(0);
    assert_eq!(
        upgraded.execute_native_reserved::<WeakBacklinkedOwner, _>(&token, publisher(), |_| {
            callbacks.fetch_add(1, Ordering::SeqCst);
            panic!("retired D replayed through upgraded weak context")
        }),
        Err(DeliveryError::HistoryLost)
    );
    core.lose_history();
    let still_lost = weak.upgrade().unwrap();
    assert_eq!(
        still_lost.query_delivery(&view, 1).unwrap().state,
        DeliveryState::HistoryLost
    );
    assert_eq!(
        still_lost.retire_through(&view, ack(&authority), &authority),
        Err(DeliveryError::HistoryLost)
    );
    assert_eq!(
        still_lost.execute_native_reserved::<WeakBacklinkedOwner, _>(&token, publisher(), |_| {
            callbacks.fetch_add(1, Ordering::SeqCst);
            panic!("lost D replayed through upgraded weak context")
        }),
        Err(DeliveryError::HistoryLost)
    );
    assert_eq!(callbacks.load(Ordering::SeqCst), 0);
}
