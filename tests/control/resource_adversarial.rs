//! Resource-family adversarial host-model tests. These do not exercise a
//! real kernel scheduler, time source, ioctl path, or runqueue.

use os_control::{
    with_parent, PublisherId, ResourceDomain, ResourceDomainId, ResourceError, StableObjectId,
    CPU_PERIOD_NS,
};
use std::sync::{Arc, Barrier};
use std::thread;

fn root(n: u128, cap: u64) -> ResourceDomain {
    ResourceDomain::new(
        ResourceDomainId::from_u128(n),
        StableObjectId::from_u128(n),
        None,
        cap,
    )
    .unwrap()
}

fn child(parent: &ResourceDomain, n: u128, cap: u64) -> ResourceDomain {
    with_parent(
        ResourceDomainId::from_u128(n),
        StableObjectId::from_u128(n),
        parent,
        cap,
    )
    .unwrap()
}

#[test]
fn descendant_read_usage_prevents_an_ancestor_boottime_rollback() {
    let parent = root(700_000, CPU_PERIOD_NS);
    let leaf = child(&parent, 700_001, CPU_PERIOD_NS);
    let current = CPU_PERIOD_NS + 10;
    leaf.try_usage(current).unwrap();
    assert_eq!(
        parent.try_usage(current - 1),
        Err(ResourceError::ClockRollback),
        "one resource family cannot observe BOOTTIME moving backward after a leaf read"
    );
    assert_eq!(parent.try_usage(current).unwrap().cumulative_cpu_ns, 0);
}

#[test]
fn descendant_cas_prevents_an_ancestor_cas_from_backdating() {
    let parent = root(701_000, CPU_PERIOD_NS);
    let leaf = child(&parent, 701_001, CPU_PERIOD_NS);
    let publisher = PublisherId::from_u128(701_002);
    let current = CPU_PERIOD_NS + 10;
    leaf.install_budget_for_host_model(
        &leaf.grant(publisher).unwrap(),
        1,
        CPU_PERIOD_NS,
        CPU_PERIOD_NS,
        current,
    )
    .unwrap();
    assert_eq!(
        parent.install_budget_for_host_model(
            &parent.grant(publisher).unwrap(),
            1,
            CPU_PERIOD_NS,
            CPU_PERIOD_NS,
            current - 1,
        ),
        Err(ResourceError::ClockRollback),
        "a later descendant budget receipt fences older ancestor receipts"
    );
    assert_eq!(parent.revision(), 1);
}

#[test]
fn descendant_read_usage_prevents_sibling_cpu_from_being_charged_in_the_past() {
    let parent = root(702_000, CPU_PERIOD_NS);
    let observer = child(&parent, 702_001, CPU_PERIOD_NS);
    let runner = child(&parent, 702_002, CPU_PERIOD_NS);
    let current = CPU_PERIOD_NS + 10;
    observer.try_usage(current).unwrap();
    assert_eq!(
        runner.charge_interval_for_host_model(current - 2, current - 1),
        Err(ResourceError::ClockRollback),
        "N0 single-CPU accounting cannot insert execution before a completed family observation"
    );
    assert_eq!(runner.try_usage(current).unwrap().cumulative_cpu_ns, 0);
    assert_eq!(parent.try_usage(current).unwrap().cumulative_cpu_ns, 0);
}

#[test]
fn same_cap_cas_does_not_refund_shared_parent_consumption() {
    let parent = root(703_000, 10);
    let left = child(&parent, 703_001, 10);
    let right = child(&parent, 703_002, 10);
    let publisher = PublisherId::from_u128(703_003);
    left.charge_interval_for_host_model(0, 7).unwrap();
    let receipt = left
        .install_budget_for_host_model(&left.grant(publisher).unwrap(), 1, CPU_PERIOD_NS, 10, 7)
        .unwrap();
    assert_eq!(receipt.consumed_at_apply_ns, 7);
    assert_eq!(parent.try_usage(7).unwrap().window_consumed_ns, 7);
    assert_eq!(
        right.charge_interval_for_host_model(7, 11),
        Err(ResourceError::Exhausted)
    );
    right.charge_interval_for_host_model(7, 10).unwrap();
    assert_eq!(parent.try_usage(10).unwrap().window_consumed_ns, 10);
    assert_eq!(left.try_usage(10).unwrap().window_consumed_ns, 7);
    assert_eq!(right.try_usage(10).unwrap().window_consumed_ns, 3);
}

#[test]
fn period_rollover_cas_preserves_cumulative_parent_charge() {
    let parent = root(704_000, 10);
    let leaf = child(&parent, 704_001, 10);
    let publisher = PublisherId::from_u128(704_002);
    leaf.charge_interval_for_host_model(CPU_PERIOD_NS - 7, CPU_PERIOD_NS + 3)
        .unwrap();
    let receipt = leaf
        .install_budget_for_host_model(
            &leaf.grant(publisher).unwrap(),
            1,
            CPU_PERIOD_NS,
            10,
            CPU_PERIOD_NS + 3,
        )
        .unwrap();
    assert_eq!(receipt.consumed_at_apply_ns, 3);
    let snapshot = parent.try_usage(CPU_PERIOD_NS + 3).unwrap();
    assert_eq!(snapshot.cumulative_cpu_ns, 10);
    assert_eq!(snapshot.window_consumed_ns, 3);
    assert_eq!(snapshot.window_start_ns, CPU_PERIOD_NS);
}

#[test]
fn descendant_sample_fences_every_stale_sibling_mutation_without_partial_charge() {
    let parent = root(705_000, 10);
    let observer = child(&parent, 705_001, 10);
    let runner = child(&parent, 705_002, 10);
    let publisher = PublisherId::from_u128(705_003);
    let current = CPU_PERIOD_NS + 10;
    observer.try_usage(current).unwrap();

    assert_eq!(
        runner.try_usage(current - 1),
        Err(ResourceError::ClockRollback)
    );
    assert_eq!(
        runner.charge_cpu(1, current - 1),
        Err(ResourceError::ClockRollback)
    );
    assert_eq!(
        runner.charge_interval_for_host_model(current - 2, current - 1),
        Err(ResourceError::ClockRollback)
    );
    assert_eq!(
        runner.install_budget_for_host_model(
            &runner.grant(publisher).unwrap(),
            1,
            CPU_PERIOD_NS,
            10,
            current - 1,
        ),
        Err(ResourceError::ClockRollback)
    );
    assert_eq!(runner.revision(), 1);
    let snapshot = runner.try_usage(current).unwrap();
    assert_eq!(snapshot.cumulative_cpu_ns, 0);
    assert_eq!(snapshot.window_consumed_ns, 0);
    assert_eq!(snapshot.event_sequence, 0);
    assert_eq!(parent.try_usage(current).unwrap().cumulative_cpu_ns, 0);
}

#[test]
fn successful_descendant_cas_and_charges_each_advance_the_family_floor() {
    for mode in 0..3_u128 {
        let parent = root(706_000 + mode * 10, 10);
        let left = child(&parent, 706_001 + mode * 10, 10);
        let right = child(&parent, 706_002 + mode * 10, 10);
        let current = CPU_PERIOD_NS + 10;
        match mode {
            0 => {
                left.install_budget_for_host_model(
                    &left.grant(PublisherId::from_u128(706_003)).unwrap(),
                    1,
                    CPU_PERIOD_NS,
                    10,
                    current,
                )
                .unwrap();
            }
            1 => left.charge_cpu(1, current).unwrap(),
            2 => left
                .charge_interval_for_host_model(current - 1, current)
                .unwrap(),
            _ => unreachable!(),
        }
        assert_eq!(
            parent.try_usage(current - 1),
            Err(ResourceError::ClockRollback)
        );
        assert_eq!(
            right.try_usage(current - 1),
            Err(ResourceError::ClockRollback)
        );
        assert_eq!(
            right.charge_cpu(1, current - 1),
            Err(ResourceError::ClockRollback)
        );
        assert_eq!(right.revision(), 1);
    }
}

#[test]
fn rejected_cas_and_exhausted_interval_do_not_advance_family_time() {
    let parent = root(707_000, 10);
    let left = child(&parent, 707_001, 10);
    let right = child(&parent, 707_002, 10);
    let publisher = PublisherId::from_u128(707_003);
    let grant = left.grant(publisher).unwrap();
    let earlier = CPU_PERIOD_NS + 10;
    let rejected_time = CPU_PERIOD_NS + 100;
    assert_eq!(
        left.install_budget_for_host_model(&grant, 2, CPU_PERIOD_NS, 10, rejected_time),
        Err(ResourceError::RevisionConflict {
            expected: 2,
            actual: 1
        })
    );
    right.try_usage(earlier).unwrap();
    assert_eq!(
        left.charge_interval_for_host_model(rejected_time, rejected_time + 11),
        Err(ResourceError::Exhausted)
    );
    let unchanged = parent.try_usage(earlier).unwrap();
    assert_eq!(unchanged.cumulative_cpu_ns, 0);
    assert_eq!(unchanged.window_consumed_ns, 0);
    assert_eq!(unchanged.event_sequence, 0);
    assert_eq!(left.revision(), 1);
}

#[test]
fn inconsistent_accounting_read_and_cas_do_not_advance_family_time() {
    let parent = root(708_000, 10);
    let left = child(&parent, 708_001, 10);
    let right = child(&parent, 708_002, 10);
    // The legacy point-charge seam deliberately allows this unphysical
    // sample; the fallible wire-facing boundaries must reject it atomically.
    left.charge_cpu(10, 5).unwrap();
    assert_eq!(
        left.try_usage(6),
        Err(ResourceError::InconsistentAccounting)
    );
    assert_eq!(
        left.install_budget_for_host_model(
            &left.grant(PublisherId::from_u128(708_003)).unwrap(),
            1,
            CPU_PERIOD_NS,
            10,
            6,
        ),
        Err(ResourceError::InconsistentAccounting)
    );
    assert_eq!(right.try_usage(5).unwrap().sample_boottime_ns, 5);
    assert_eq!(left.revision(), 1);
    let snapshot = parent.try_usage(10).unwrap();
    assert_eq!(snapshot.cumulative_cpu_ns, 10);
    assert_eq!(snapshot.event_sequence, 1);
}

#[test]
fn legacy_usage_clamps_to_the_latest_family_observation() {
    let parent = root(709_000, 10);
    let left = child(&parent, 709_001, 10);
    let right = child(&parent, 709_002, 10);
    let current = CPU_PERIOD_NS + 10;
    left.try_usage(current).unwrap();
    for node in [&parent, &right] {
        let snapshot = node.usage(0);
        assert_eq!(snapshot.sample_boottime_ns, current);
        assert_eq!(snapshot.window_start_ns, CPU_PERIOD_NS);
        assert_eq!(snapshot.window_consumed_ns, 0);
        assert_eq!(snapshot.cumulative_cpu_ns, 0);
    }
}

#[test]
fn child_creation_inherits_a_cousin_observed_family_time() {
    let parent = root(710_000, 10);
    let left = child(&parent, 710_001, 10);
    let right = child(&parent, 710_002, 10);
    let current = CPU_PERIOD_NS + 10;
    left.try_usage(current).unwrap();
    let descendant = child(&right, 710_003, 10);
    assert_eq!(
        descendant.try_usage(current - 1),
        Err(ResourceError::ClockRollback)
    );
    assert_eq!(descendant.usage(0).sample_boottime_ns, current);
}

#[test]
fn concurrent_descendant_and_ancestor_samples_preserve_family_clock_order() {
    for n in 0..64_u128 {
        let parent = root(711_000 + n * 10, 10);
        let leaf = child(&parent, 711_001 + n * 10, 10);
        let start = Arc::new(Barrier::new(2));
        let ancestor_start = Arc::clone(&start);
        let ancestor = parent.clone();
        let later = CPU_PERIOD_NS + 10;
        let earlier = later - 1;
        let ancestor_thread = thread::spawn(move || {
            ancestor_start.wait();
            ancestor.try_usage(earlier)
        });
        start.wait();
        leaf.try_usage(later).unwrap();
        match ancestor_thread.join().unwrap() {
            Ok(snapshot) => assert_eq!(snapshot.sample_boottime_ns, earlier),
            Err(error) => assert_eq!(error, ResourceError::ClockRollback),
        }
        assert_eq!(parent.try_usage(earlier), Err(ResourceError::ClockRollback));
        assert_eq!(parent.try_usage(later).unwrap().sample_boottime_ns, later);
    }
}
