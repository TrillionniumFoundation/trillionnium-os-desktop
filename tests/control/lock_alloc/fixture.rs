//! Native namespace scenarios. No host ResourceDomain or alternate policy
//! database is created. Bootstrap/caller allocations outside A03 locks are
//! deliberately outside the zero-allocation-under-internal-lock requirement.

use lock_trace::{
    counts, fail_next_allocation, injected_failures, lock_depth, lock_unpoisoned, Counts, Mutex,
    TrackingAllocator,
};
use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryState, DeliveryStatus, HistoryAck,
    NativeDeliveryRequest, NativeGrant, NativeTarget, OriginalOwnerAuthority, OwnerId,
    OwnerReceipt, PublishOutcome, PublisherId, ReserveAttempt, ReserveToken, ResourceDomainId,
    StableObjectId,
};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

#[global_allocator]
static GLOBAL: TrackingAllocator = TrackingAllocator;

fn emit(event: &str, name: &str, values: Counts) {
    println!("{{\"event\":\"{event}\",\"name\":\"{name}\",\"alloc\":{},\"realloc\":{},\"dealloc\":{},\"allocated_bytes\":{},\"reallocated_bytes\":{},\"deallocated_bytes\":{}}}",
        values.alloc, values.realloc, values.dealloc, values.allocated_bytes,
        values.reallocated_bytes, values.deallocated_bytes);
}

fn instrument_controls() {
    assert_eq!(lock_depth(), 0);
    let before = counts();
    {
        let mutex = Mutex::new(());
        let _guard = lock_unpoisoned(&mutex);
        assert_eq!(lock_depth(), 1);
        let mut allocation = Vec::<u8>::with_capacity(1);
        allocation.push(1);
        allocation.reserve_exact(4096);
        std::hint::black_box(&allocation);
        drop(allocation);
    }
    assert_eq!(lock_depth(), 0);
    let positive = counts().since(before);
    assert!(
        positive.alloc > 0 && positive.realloc > 0 && positive.dealloc > 0,
        "allocator instrumentation positive control did not detect all three operations"
    );
    emit("control", "allocator_positive", positive);

    // Failed allocations must also count as allocator calls under a lock.
    // Returning null cannot turn an attempted under-lock allocation into zero.
    let failures = injected_failures();
    let before = counts();
    {
        let mutex = Mutex::new(());
        let _guard = lock_unpoisoned(&mutex);
        let mut allocation = Vec::<u8>::new();
        fail_next_allocation();
        assert!(allocation.try_reserve_exact(16).is_err());
    }
    assert_eq!(lock_depth(), 0);
    assert_eq!(injected_failures(), failures + 1);
    let failed_call = counts().since(before);
    assert_eq!(failed_call.alloc, 1);
    assert_eq!(failed_call.realloc, 0);
    assert_eq!(failed_call.dealloc, 0);
    emit("control", "failed_allocator_call_under_lock", failed_call);

    let before = counts();
    let mut outside = Vec::<u8>::with_capacity(1);
    outside.push(1);
    outside.reserve_exact(4096);
    std::hint::black_box(&outside);
    drop(outside);
    assert_eq!(
        counts(),
        before,
        "allocation outside an internal lock was incorrectly counted"
    );

    let mutex = Mutex::new(());
    assert!(catch_unwind(AssertUnwindSafe(|| {
        let _guard = lock_unpoisoned(&mutex);
        assert_eq!(lock_depth(), 1);
        panic!("injected instrumentation poison control");
    }))
    .is_err());
    assert!(mutex.is_poisoned());
    assert_eq!(lock_depth(), 0);
    {
        let _recovered = lock_unpoisoned(&mutex);
        assert_eq!(lock_depth(), 1);
    }
    assert_eq!(lock_depth(), 0);

    std::thread::spawn(|| {
        assert_eq!(lock_depth(), 0);
        let first = Mutex::new(());
        let second = Mutex::new(());
        {
            let _one = lock_unpoisoned(&first);
            assert_eq!(lock_depth(), 1);
            {
                let _two = lock_unpoisoned(&second);
                assert_eq!(lock_depth(), 2);
            }
            assert_eq!(lock_depth(), 1);
        }
        assert_eq!(lock_depth(), 0);
    })
    .join()
    .unwrap();
    assert_eq!(lock_depth(), 0);
    println!("{{\"event\":\"control\",\"name\":\"depth_tls_poison_unwind\",\"passed\":true}}");
}

fn measure<T>(name: &str, operation: impl FnOnce() -> T) -> (T, Counts) {
    assert_eq!(lock_depth(), 0);
    let before = counts();
    let result = operation();
    let delta = counts().since(before);
    assert_eq!(lock_depth(), 0);
    emit("scenario", name, delta);
    (result, delta)
}

fn publisher() -> PublisherId {
    PublisherId::from_u128(1)
}
fn owner_id() -> OwnerId {
    OwnerId::from_u128(2)
}
fn core(n: u128, capacity: usize) -> (ControlCore, OriginalOwnerAuthority) {
    ControlCore::with_capacity_for_owner(
        BootId::from_u128(n),
        CapSpaceId::from_u128(n),
        capacity,
        owner_id(),
    )
    .unwrap()
}
struct Owner {
    effects: AtomicUsize,
}
fn owner() -> Arc<Owner> {
    Arc::new(Owner {
        effects: AtomicUsize::new(0),
    })
}
fn request(owner: Arc<Owner>, sequence: u64) -> NativeDeliveryRequest {
    let target = NativeTarget::from_owner(
        owner,
        ResourceDomainId::from_u128(3),
        StableObjectId::from_u128(4),
    )
    .unwrap();
    // Nonempty owned ancestry detects accidental vector clones/drops moved
    // under a delivery lock; an empty Vec would hide those regressions.
    let grant = NativeGrant::from_owner(target, publisher(), 1, vec![5, 6]).unwrap();
    NativeDeliveryRequest::from_wire(sequence, grant, 1, 17, 7, 11).unwrap()
}
fn ack(core: &ControlCore, through: u64) -> HistoryAck {
    HistoryAck::from_owner_receipt(
        core.identity(),
        through,
        OwnerReceipt::new(owner_id(), [1; 32]),
    )
    .unwrap()
}
fn deny(core: &ControlCore, token: &ReserveToken) {
    core.publish(
        token,
        publisher(),
        PublishOutcome::Failure {
            status: DeliveryStatus::Revoked,
        },
    )
    .unwrap();
}

fn fallible_allocation_controls() {
    // Current implementation reserves its ring before Arc::new. Historical
    // controls deliberately do not run these injected failures.
    let before = counts();
    let failures = injected_failures();
    fail_next_allocation();
    let result =
        ControlCore::try_with_capacity(BootId::from_u128(20), CapSpaceId::from_u128(20), 1);
    assert_eq!(result.err(), Some(DeliveryError::ResourceExhausted));
    assert_eq!(injected_failures(), failures + 1);

    let (core, authority) = core(21, 1);
    let view = core.delivery_view_for(owner_id()).unwrap();
    let token = core
        .reserve_native(request(owner(), 1), publisher())
        .unwrap();
    deny(&core, &token);
    let acknowledgement = ack(&core, 1);
    fail_next_allocation();
    assert_eq!(
        core.retire_through(&view, acknowledgement, &authority),
        Err(DeliveryError::ResourceExhausted)
    );
    assert_eq!(injected_failures(), failures + 2);
    assert_eq!(core.retired_through(), 0);
    assert_eq!(core.window_len(), 1);
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Terminal
    );
    core.retire_through(&view, acknowledgement, &authority)
        .unwrap();
    assert_eq!(core.retired_through(), 1);
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Retired
    );
    core.validate_invariants_for_host_model().unwrap();
    let delta = counts().since(before);
    emit("control", "fallible_ring_and_retirement", delta);
    assert!(delta.is_zero());
    println!("{{\"event\":\"failure_control\",\"injected_failures\":2,\"frontier_atomic\":true,\"history_usable\":true}}");
}

fn main() {
    instrument_controls();
    if std::env::args()
        .skip(1)
        .any(|argument| argument == "--allocation-failure-controls")
    {
        fallible_allocation_controls();
    }
    // Instrumentation controls are excluded from the production scenario sum.
    let scenario_start = counts();
    let mut scenario_count = 0;
    macro_rules! case {
        ($name:literal, $body:expr) => {{
            scenario_count += 1;
            measure($name, $body).0
        }};
    }
    let (first, authority) = core(10, 1);
    let owner = owner();
    let original = request(owner.clone(), 1);
    let token = case!("reserve_new", || first
        .reserve_native(original.clone(), publisher()))
    .unwrap();
    let view = first.delivery_view_for(owner_id()).unwrap();
    assert_eq!(
        case!("query_reserved", || first.query_delivery(&view, 1))
            .unwrap()
            .state,
        DeliveryState::Reserved
    );
    assert_eq!(
        case!("duplicate_reserved", || first
            .reserve_native(original.clone(), publisher()))
        .err(),
        Some(DeliveryError::Busy)
    );
    assert_eq!(
        case!("native_wrong_type", || first
            .execute_native_reserved::<u64, _>(
                &token,
                publisher(),
                |_| unreachable!()
            )),
        Err(DeliveryError::InvalidRequest)
    );
    case!("execute_native", || first
        .execute_native_reserved::<Owner, _>(
            &token,
            publisher(),
            |context| {
                assert_eq!(context.ancestor_epochs(), &[5, 6]);
                context.owner().effects.fetch_add(1, Ordering::SeqCst);
                PublishOutcome::Success {
                    stable_object_id: context.binding().stable_object_id,
                    previous_revision: 1,
                    saved_revision: 2,
                    effective_ns: 1,
                    consumed_ns: 0,
                }
            }
        ))
    .unwrap();
    assert_eq!(owner.effects.load(Ordering::SeqCst), 1);
    assert_eq!(
        case!("query_terminal", || first.query_delivery(&view, 1))
            .unwrap()
            .state,
        DeliveryState::Terminal
    );
    assert!(matches!(
        case!("duplicate_terminal", || first
            .reserve_native_or_get(original.clone(), publisher()))
        .unwrap(),
        ReserveAttempt::Existing(_)
    ));
    case!("publish_terminal_retry", || first.publish(
        &token,
        publisher(),
        PublishOutcome::Failure {
            status: DeliveryStatus::Revoked
        }
    ))
    .unwrap();
    case!("retire_terminal", || first.retire_through(
        &view,
        ack(&first, 1),
        &authority
    ))
    .unwrap();
    assert_eq!(
        case!("query_retired", || first.query_delivery(&view, 1))
            .unwrap()
            .state,
        DeliveryState::Retired
    );

    let (capture_core, _) = core(14, 1);
    let capture_token = capture_core
        .reserve_native(request(owner.clone(), 1), publisher())
        .unwrap();
    let captured_bytes = vec![123u8; 4096];
    let captured_owner = Arc::new(AtomicUsize::new(17));
    case!("callback_capture_drop", || capture_core
        .execute_native_reserved::<Owner, _>(
            &capture_token,
            publisher(),
            move |context| {
                // No allocation, explicit destruction or reentry in the
                // callback body. The borrowed owned captures must be dropped
                // after the internal execution gate has been released.
                std::hint::black_box(&captured_bytes);
                assert_eq!(captured_owner.load(Ordering::SeqCst), 17);
                context.owner().effects.fetch_add(1, Ordering::SeqCst);
                PublishOutcome::Failure {
                    status: DeliveryStatus::Revoked,
                }
            }
        ))
    .unwrap();
    assert_eq!(
        capture_core
            .query_delivery(&capture_core.delivery_view(), 1)
            .unwrap()
            .state,
        DeliveryState::Terminal
    );

    let (full, _) = core(11, 2);
    full.reserve_native(request(owner.clone(), 1), publisher())
        .unwrap();
    full.reserve_native(request(owner.clone(), 2), publisher())
        .unwrap();
    assert_eq!(
        case!("full_window_rejection", || full
            .reserve_native(request(owner.clone(), 3), publisher()))
        .err(),
        Some(DeliveryError::ResourceExhausted)
    );
    case!("loss_full_window", || full.lose_history());

    let (hanging, authority) = core(12, 4);
    let prefix = hanging
        .reserve_native(request(owner.clone(), 1), publisher())
        .unwrap();
    for sequence in 2..=4 {
        let token = hanging
            .reserve_native(request(owner.clone(), sequence), publisher())
            .unwrap();
        deny(&hanging, &token);
    }
    let view = hanging.delivery_view_for(owner_id()).unwrap();
    assert_eq!(
        case!("hanging_prefix_query", || hanging.query_delivery(&view, 1))
            .unwrap()
            .state,
        DeliveryState::Reserved
    );
    assert_eq!(
        case!("hanging_prefix_retire", || hanging.retire_through(
            &view,
            ack(&hanging, 4),
            &authority
        )),
        Err(DeliveryError::PendingPrefix)
    );
    assert_eq!(
        case!("hanging_prefix_full", || hanging
            .reserve_native(request(owner.clone(), 5), publisher()))
        .err(),
        Some(DeliveryError::ResourceExhausted)
    );
    case!("publish_pending", || deny(&hanging, &prefix));
    case!("retire_released_prefix", || hanging.retire_through(
        &view,
        ack(&hanging, 4),
        &authority
    ))
    .unwrap();

    let (long, authority) = core(13, 1);
    let view = long.delivery_view_for(owner_id()).unwrap();
    case!("ten_thousand_writes", || {
        for sequence in 1..=10_000 {
            let token = long
                .reserve_native(request(owner.clone(), sequence), publisher())
                .unwrap();
            deny(&long, &token);
            long.retire_through(&view, ack(&long, sequence), &authority)
                .unwrap();
        }
    });
    assert_eq!(long.retired_through(), 10_000);
    assert_eq!(long.next_sequence(), 10_001);
    assert_eq!(long.window_len(), 0);
    first.validate_invariants_for_host_model().unwrap();
    hanging.validate_invariants_for_host_model().unwrap();
    long.validate_invariants_for_host_model().unwrap();

    let total = counts().since(scenario_start);
    emit("summary", "all_native_namespace_scenarios", total);
    println!("{{\"event\":\"acceptance\",\"scenario_count\":{scenario_count},\"zero\":{},\"controls_ok\":true}}", total.is_zero());
    assert!(
        total.is_zero(),
        "native namespace allocated/reallocated/deallocated under an internal lock"
    );
}
