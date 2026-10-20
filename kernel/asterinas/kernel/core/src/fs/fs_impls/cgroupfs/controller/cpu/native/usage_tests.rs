// SPDX-License-Identifier: MPL-2.0

//! G1-b usage regressions on the original cgroup CPU bandwidth owner.
//!
//! Real, unstarted Process/Task objects exercise the production runtime and
//! owner lock. ClockSource counters or explicit one-cycle/one-nanosecond
//! endpoints are controlled fixtures, not live scheduler or SMP qualification.

use alloc::sync::Arc;
use core::sync::atomic::{AtomicU64, Ordering};

use aster_systree::{Error, Result, SysBranchNode, SysNode};
use aster_time::ClockSource;
use os_control::{CPU_PERIOD_NS, NativeTarget, ResourceDomainId, StableObjectId, UsageSnapshot};
use ostd::{panic, prelude::ktest, task::Task};

use super::{
    super::{
        super::{Controller, SubController, SubCtrlType},
        CpuController, CpuMax, charge_task_cpu,
        max_config::CpuMaxConfig,
    },
    CpuBandwidthState, CpuUsageError,
};
use crate::{
    fs::cgroupfs::{CgroupMembership, CgroupNode, CgroupSysNode, CgroupSystem},
    process::{Process, test_util},
    sched::CpuRuntimeFixture,
};

struct Fixture {
    root: &'static Arc<CgroupSystem>,
    parent: Arc<CgroupNode>,
    leaf: Arc<CgroupNode>,
    process: Option<Arc<Process>>,
    task: Option<Arc<Task>>,
    original_root_budget: CpuMax,
    enabled_root_cpu: bool,
    leaf_removed: bool,
    name: &'static str,
}

/// A second real process bound to the same owner, with independent cleanup.
struct AdditionalProcess {
    process: Option<Arc<Process>>,
    task: Option<Arc<Task>>,
}

impl AdditionalProcess {
    fn new(group: &Arc<CgroupNode>) -> Self {
        let (process, task) = test_util::new_unstarted_process();
        CgroupMembership::write_lock()
            .move_process_to_node(process.clone(), group)
            .unwrap();
        Self {
            process: Some(process),
            task: Some(task),
        }
    }

    fn task(&self) -> &Arc<Task> {
        self.task.as_ref().unwrap()
    }
}

impl Drop for AdditionalProcess {
    fn drop(&mut self) {
        release_process_and_task(&mut self.process, &mut self.task);
    }
}

impl Fixture {
    fn new(name: &'static str) -> Self {
        aster_time::init_for_ktest();
        aster_systree::init_for_ktest();
        let root = CgroupSystem::singleton();
        let enabled_root_cpu = !root
            .controller()
            .active_set()
            .contains_type(SubCtrlType::Cpu);
        if enabled_root_cpu {
            root.store_attr("cgroup.subtree_control", "+cpu").unwrap();
        }
        let parent = Arc::downcast::<CgroupNode>(root.create_child(name).unwrap()).unwrap();
        parent.store_attr("cgroup.subtree_control", "+cpu").unwrap();
        let leaf = Arc::downcast::<CgroupNode>(parent.create_child("leaf").unwrap()).unwrap();
        let original_root_budget = with_state(&owner(root.controller()), |state| state.max);
        // These unstarted tasks have no earlier runtime. Their fixture clock
        // has origin zero; do not mix it with the live calibrated clock origin.
        for controller in [root.controller(), parent.controller(), leaf.controller()] {
            reset(&owner(controller));
        }
        let (process, task) = test_util::new_unstarted_process();
        CgroupMembership::write_lock()
            .move_process_to_node(process.clone(), &leaf)
            .unwrap();
        Self {
            root,
            parent,
            leaf,
            process: Some(process),
            task: Some(task),
            original_root_budget,
            enabled_root_cpu,
            leaf_removed: false,
            name,
        }
    }

    fn owner(&self) -> Arc<SubController<CpuController>> {
        owner(self.leaf.controller())
    }

    fn task(&self) -> &Arc<Task> {
        self.task.as_ref().unwrap()
    }

    fn bind(&self, id: u128) -> NativeTarget {
        self.leaf
            .controller()
            .bind_native_cpu_once_for_owner(
                &self.owner(),
                ResourceDomainId::from_u128(id),
                StableObjectId::from_u128(id + 1),
                &mut CgroupMembership::write_lock(),
            )
            .unwrap()
    }

    fn configure(&self, input: &str, now: Option<u64>) -> Result<()> {
        with_state(&self.owner(), |state| {
            state.reconfigure_at(CpuMaxConfig::parse(input).unwrap(), now)
        })
    }

    fn budget(&self) -> CpuMax {
        with_state(&self.owner(), |state| state.max)
    }

    fn sample(&self, now: u64) -> core::result::Result<UsageSnapshot, CpuUsageError> {
        sample_owner(&self.owner(), now)
    }

    fn checked_sample(&self, now: u64, target: &NativeTarget, revision: u64) -> UsageSnapshot {
        let sample = self.sample(now).unwrap();
        assert_eq!(sample.stable_object_id, target.stable_object_id());
        assert_eq!(sample.revision, revision);
        assert_eq!(sample.sample_boottime_ns, now);
        assert_eq!(sample.active_period_ns, CPU_PERIOD_NS);
        // No event producer or explicit pause owner exists in this slice.
        // Neither a configuration revision nor a throttle count is an event.
        assert_eq!(sample.event_sequence, 0);
        assert_eq!(sample.dropped_events, 0);
        assert!(!sample.user_paused);
        sample
    }

    fn remove_leaf(&mut self) {
        release_process_and_task(&mut self.process, &mut self.task);
        self.leaf
            .mark_as_dead(&mut CgroupMembership::write_lock())
            .unwrap();
        self.parent.remove_child("leaf").unwrap();
        self.leaf_removed = true;
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        if !self.leaf_removed {
            self.remove_leaf();
        }
        self.parent
            .mark_as_dead(&mut CgroupMembership::write_lock())
            .unwrap();
        self.root.remove_child(self.name).unwrap();
        with_state(&owner(self.root.controller()), |state| {
            state.max = self.original_root_budget;
        });
        if self.enabled_root_cpu {
            self.root
                .store_attr("cgroup.subtree_control", "-cpu")
                .unwrap();
        }
    }
}

fn release_process_and_task(process: &mut Option<Arc<Process>>, task: &mut Option<Arc<Task>>) {
    // Runtime fixtures must drop first. Zombie migration retains the thread's
    // current CPU lease instead of retiring it through an RCU update to None.
    // Drop the Process/TaskSet before the final Task so RcuInner::Drop releases
    // that current lease, without manufacturing a grace period for deletion.
    if let Some(process) = process.take() {
        test_util::mark_zombie(&process);
        CgroupMembership::write_lock().move_process_to_root(&process);
        drop(process);
    }
    drop(task.take());
}

fn owner(controller: &Controller) -> Arc<SubController<CpuController>> {
    controller.cpu.read().get().clone()
}

fn with_state<R>(
    owner: &SubController<CpuController>,
    apply: impl FnOnce(&mut CpuBandwidthState) -> R,
) -> R {
    let control = owner.inner.as_ref().unwrap().control().unwrap();
    let mut state = control.max.lock();
    apply(&mut state)
}

fn sample_owner(
    owner: &SubController<CpuController>,
    now: u64,
) -> core::result::Result<UsageSnapshot, CpuUsageError> {
    with_state(owner, |state| state.sample_usage(now))
}

fn reset(owner: &SubController<CpuController>) {
    with_state(owner, |state| {
        state.max = CpuMax {
            quota_usec: 1_000,
            quota_sub_usec_ns: 0,
            period_usec: 100_000,
            window_start_ns: 0,
            used_ns: 0,
            cumulative_ns: 0,
            last_observed_ns: 0,
            accounting_fault: false,
            native_window_valid_from_ns: Some(0),
            carry_debt_ns: 0,
            nr_periods: 0,
            nr_throttled: 0,
            throttled_since_ns: None,
            throttled_ns: 0,
        };
    });
}

fn clock(counter: &Arc<AtomicU64>, frequency: u64) -> ClockSource {
    let counter = counter.clone();
    ClockSource::new(
        frequency,
        10,
        Arc::new(move || counter.load(Ordering::Relaxed)),
    )
}

#[ktest]
fn fragmented_three_ghz_runtime_keeps_absolute_endpoint_precision() {
    let fixture = Fixture::new("g1b-usage-fragments");
    let target = fixture.bind(1_100);
    let counter = Arc::new(AtomicU64::new(0));
    let fragmented = clock(&counter, 3_000_000_000);
    // An unrefreshed original ClockSource is the one-interval reference. It
    // does not share the refreshed source's possibly lost fractional phase.
    let reference = clock(&counter, 3_000_000_000);
    let initial = fragmented.read_sample();
    let mut runtime = CpuRuntimeFixture::new_sample(fixture.task().clone(), initial);
    for cycles in 1..=3_000 {
        counter.store(cycles, Ordering::Relaxed);
        assert_eq!(runtime.update_sample(fragmented.update()), (1, cycles));
    }
    let endpoint = reference.read_sample().checked_nanos().unwrap();
    let elapsed = endpoint - initial.checked_nanos().unwrap();
    assert!((999..=1_000).contains(&elapsed));
    let sample = fixture.checked_sample(endpoint, &target, 1);
    assert_eq!(sample.cumulative_cpu_ns, elapsed);
    assert_eq!(sample.window_consumed_ns, elapsed);
    assert_eq!(sample.window_start_ns, 0);
    assert_eq!(sample.active_cap_ns, 1_000_000);
    assert_eq!(runtime.update_sample(fragmented.read_sample()), (0, 3_000));
    assert_eq!(fixture.checked_sample(endpoint, &target, 1), sample);
}

#[ktest]
fn sampled_configuration_preserves_the_separate_cycle_cursor() {
    let fixture = Fixture::new("g1b-usage-cursor");
    let target = fixture.bind(1_110);
    let counter = Arc::new(AtomicU64::new(0));
    let source = clock(&counter, 3_000_000_000);
    let mut runtime = CpuRuntimeFixture::new_sample(fixture.task().clone(), source.read_sample());
    for cycles in 1..=18 {
        counter.store(cycles, Ordering::Relaxed);
        let sample = source.read_sample();
        let endpoint = sample.checked_nanos().unwrap();
        runtime.configure_sample(sample, |now| {
            assert_eq!(now, Some(endpoint));
            assert_eq!(fixture.budget().cumulative_ns, endpoint);
            fixture.configure("1000 100000", now).unwrap();
        });
        let usage = fixture.checked_sample(endpoint, &target, cycles + 1);
        assert_eq!(usage.cumulative_cpu_ns, endpoint);
        assert_eq!(usage.window_consumed_ns, endpoint);
    }
    // Configuration settled every prefix but did not consume CFS/RT cycles.
    assert_eq!(runtime.update_sample(source.read_sample()), (18, 18));
    assert_eq!(runtime.update_sample(source.read_sample()), (0, 18));
    counter.store(27, Ordering::Relaxed);
    let sample = source.read_sample();
    assert_eq!(runtime.update_sample(sample), (9, 27));
    let endpoint = sample.checked_nanos().unwrap();
    assert_eq!(
        fixture
            .checked_sample(endpoint, &target, 19)
            .cumulative_cpu_ns,
        endpoint
    );
}

#[ktest]
fn crossed_windows_preserve_cumulative_usage_and_separate_debt() {
    let fixture = Fixture::new("g1b-usage-crossing");
    let target = fixture.bind(1_120);
    charge_task_cpu(fixture.task(), 10_000, 760_000);
    let boundary = CPU_PERIOD_NS;
    let mut runtime = CpuRuntimeFixture::new(fixture.task().clone(), boundary - 500_000);
    let now = boundary + 250_000;
    let sample = runtime.configure(now, |now| fixture.checked_sample(now, &target, 1));
    assert_eq!(sample.cumulative_cpu_ns, 1_500_000);
    assert_eq!(sample.window_start_ns, boundary);
    assert_eq!(sample.window_consumed_ns, 250_000);
    assert_eq!(fixture.budget().carry_debt_ns, 250_000);
    drop(runtime);

    // A completed idle window repays debt without subtracting real execution
    // from the cumulative counter or presenting debt as current-window usage.
    let sample = fixture.checked_sample(boundary * 2, &target, 1);
    assert_eq!(sample.cumulative_cpu_ns, 1_500_000);
    assert_eq!(sample.window_start_ns, boundary * 2);
    assert_eq!(sample.window_consumed_ns, 0);
    assert_eq!(fixture.budget().carry_debt_ns, 0);
}

#[ktest]
fn same_value_and_lowered_cap_never_refill_the_original_owner() {
    let fixture = Fixture::new("g1b-usage-cap");
    fixture.configure("2000 100000", Some(0)).unwrap();
    let target = fixture.bind(1_130);
    charge_task_cpu(fixture.task(), 0, 1_500_000);
    fixture.configure("2000 100000", Some(1_500_000)).unwrap();
    let sample = fixture.checked_sample(1_500_000, &target, 2);
    assert_eq!(sample.cumulative_cpu_ns, 1_500_000);
    assert_eq!(sample.window_consumed_ns, 1_500_000);
    assert_eq!(sample.active_cap_ns, 2_000_000);

    fixture.configure("1000 100000", Some(1_500_000)).unwrap();
    assert!(!with_state(&fixture.owner(), |state| state
        .max
        .eligible(1_500_000)));
    let sample = fixture.checked_sample(1_500_000, &target, 3);
    assert_eq!(sample.cumulative_cpu_ns, 1_500_000);
    assert_eq!(sample.window_consumed_ns, 1_500_000);
    assert_eq!(sample.active_cap_ns, 1_000_000);
    assert_eq!(fixture.budget().nr_throttled, 1);

    fixture
        .configure("1000 100000", Some(CPU_PERIOD_NS))
        .unwrap();
    let sample = fixture.checked_sample(CPU_PERIOD_NS, &target, 4);
    assert_eq!(sample.cumulative_cpu_ns, 1_500_000);
    assert_eq!(sample.window_consumed_ns, 0);
    assert_eq!(fixture.budget().carry_debt_ns, 500_000);
    fixture
        .configure("1000 100000", Some(CPU_PERIOD_NS))
        .unwrap();
    assert_eq!(fixture.budget().carry_debt_ns, 500_000);
    assert_eq!(
        fixture
            .checked_sample(CPU_PERIOD_NS, &target, 5)
            .cumulative_cpu_ns,
        1_500_000
    );
}

#[ktest]
fn returning_from_short_period_waits_for_a_complete_native_window() {
    let fixture = Fixture::new("g1b-usage-short-period");
    let target = fixture.bind(1_140);
    charge_task_cpu(fixture.task(), 1_000_000, 2_000_000);
    fixture.configure("1000 10000", Some(15_000_000)).unwrap();
    assert_eq!(
        fixture.sample(15_000_000),
        Err(CpuUsageError::UnsupportedProfile)
    );
    charge_task_cpu(fixture.task(), 20_000_000, 20_500_000);
    fixture.configure("1000 100000", Some(25_000_000)).unwrap();
    assert_eq!(fixture.budget().cumulative_ns, 1_500_000);
    assert_eq!(
        fixture.budget().native_window_valid_from_ns,
        Some(CPU_PERIOD_NS)
    );
    assert_eq!(
        fixture.sample(25_000_000),
        Err(CpuUsageError::UnsupportedProfile)
    );
    fixture.configure("1000 100000", Some(75_000_000)).unwrap();
    assert_eq!(
        fixture.sample(CPU_PERIOD_NS - 1),
        Err(CpuUsageError::UnsupportedProfile)
    );
    let sample = fixture.checked_sample(CPU_PERIOD_NS, &target, 4);
    assert_eq!(sample.window_start_ns, CPU_PERIOD_NS);
    assert_eq!(sample.window_consumed_ns, 0);
    assert_eq!(sample.cumulative_cpu_ns, 1_500_000);
    charge_task_cpu(fixture.task(), CPU_PERIOD_NS, CPU_PERIOD_NS + 250_000);
    let sample = fixture.checked_sample(CPU_PERIOD_NS + 250_000, &target, 4);
    assert_eq!(sample.window_consumed_ns, 250_000);
    assert_eq!(sample.cumulative_cpu_ns, 1_750_000);
}

#[ktest]
fn returning_from_long_period_does_not_expose_pre_window_usage() {
    let fixture = Fixture::new("g1b-usage-long-period");
    let target = fixture.bind(1_150);
    fixture.configure("1000 1000000", Some(0)).unwrap();
    charge_task_cpu(fixture.task(), 10_000_000, 11_000_000);
    charge_task_cpu(fixture.task(), 210_000_000, 210_500_000);
    assert_eq!(
        fixture.sample(210_500_000),
        Err(CpuUsageError::UnsupportedProfile)
    );
    fixture.configure("1000 100000", Some(250_000_000)).unwrap();
    let boundary = CPU_PERIOD_NS * 3;
    assert_eq!(fixture.budget().used_ns, 1_500_000);
    assert_eq!(fixture.budget().native_window_valid_from_ns, Some(boundary));
    assert_eq!(
        fixture.sample(250_000_000),
        Err(CpuUsageError::UnsupportedProfile)
    );
    assert_eq!(
        fixture.sample(boundary - 1),
        Err(CpuUsageError::UnsupportedProfile)
    );
    let sample = fixture.checked_sample(boundary, &target, 3);
    assert_eq!(sample.window_start_ns, boundary);
    assert_eq!(sample.window_consumed_ns, 0);
    assert_eq!(sample.cumulative_cpu_ns, 1_500_000);
    assert_eq!(fixture.budget().carry_debt_ns, 500_000);
    charge_task_cpu(fixture.task(), boundary + 100, boundary + 200);
    let sample = fixture.checked_sample(boundary + 200, &target, 3);
    assert_eq!(sample.window_consumed_ns, 100);
    assert_eq!(sample.cumulative_cpu_ns, 1_500_100);
}

#[ktest]
fn ordinary_linux_caps_outside_n0_never_become_native_snapshots() {
    let fixture = Fixture::new("g1b-usage-profile");
    let target = fixture.bind(1_160);
    fixture.configure("100001 100000", Some(0)).unwrap();
    assert_eq!(fixture.sample(0), Err(CpuUsageError::UnsupportedProfile));
    fixture.configure("max 100000", Some(1)).unwrap();
    assert_eq!(fixture.sample(1), Err(CpuUsageError::UnsupportedProfile));
    assert!(!fixture.budget().accounting_fault);
    fixture.configure("100000 100000", Some(2)).unwrap();
    let sample = fixture.checked_sample(2, &target, 4);
    assert_eq!(sample.active_cap_ns, CPU_PERIOD_NS);
    assert_eq!(sample.window_consumed_ns, 0);
    assert_eq!(sample.cumulative_cpu_ns, 0);
}

#[ktest]
fn real_owner_wrapper_enforces_the_single_cpu_observation_profile() {
    let fixture = Fixture::new("g1b-usage-wrapper");
    let target = fixture.bind(1_270);
    // This empty, unstarted owner has no fixture-time debits. Exercise the
    // actual local-clock wrapper without presenting it as a live task run.
    let result = fixture
        .leaf
        .controller()
        .read_native_cpu_usage_for_owner(&fixture.owner());
    if ostd::cpu::all_cpus().count() != 1 {
        assert_eq!(result, Err(CpuUsageError::UnsupportedProfile));
        return;
    }
    let sample = result.unwrap();
    assert_eq!(sample.stable_object_id, target.stable_object_id());
    assert_eq!(sample.revision, 1);
    assert_eq!(sample.cumulative_cpu_ns, 0);
    assert_eq!(sample.window_consumed_ns, 0);
    assert_eq!(sample.window_start_ns % CPU_PERIOD_NS, 0);
    assert!(sample.sample_boottime_ns - sample.window_start_ns < CPU_PERIOD_NS);
    assert_eq!(sample.active_cap_ns, 1_000_000);
    assert_eq!(sample.active_period_ns, CPU_PERIOD_NS);
    assert_eq!(sample.event_sequence, 0);
    assert_eq!(sample.dropped_events, 0);
    assert!(!sample.user_paused);
}

#[ktest]
fn initial_observer_pin_rejects_a_replaced_real_cpu_owner() {
    let fixture = Fixture::new("g1c-observe-replace");
    let observer = super::NativeCpuObserver {
        node: fixture.leaf.clone(),
        owner: fixture.owner(),
        target: fixture.bind(1_300),
    };
    let first = observer.read_usage();
    if ostd::cpu::all_cpus().count() == 1 {
        let sample = first.unwrap();
        assert_eq!(sample.stable_object_id, observer.target.stable_object_id());
        assert_eq!(sample.revision, 1);
        assert_eq!(sample.cumulative_cpu_ns, 0);
    } else {
        assert_eq!(first, Err(CpuUsageError::UnsupportedProfile));
    }
    fixture.parent.store_attr("cgroup.subtree_control", "-cpu").unwrap();
    fixture.parent.store_attr("cgroup.subtree_control", "+cpu").unwrap();
    assert!(!Arc::ptr_eq(&fixture.owner(), &observer.owner));
    let expected = if ostd::cpu::all_cpus().count() == 1 {
        CpuUsageError::Closed
    } else {
        CpuUsageError::UnsupportedProfile
    };
    assert_eq!(observer.read_usage(), Err(expected));
}

#[ktest]
fn initial_observer_pin_does_not_keep_a_deleted_resource_authorized() {
    let mut fixture = Fixture::new("g1c-observe-delete");
    let observer = super::NativeCpuObserver {
        node: fixture.leaf.clone(),
        owner: fixture.owner(),
        target: fixture.bind(1_310),
    };
    let first = observer.read_usage();
    if ostd::cpu::all_cpus().count() == 1 {
        assert_eq!(first.unwrap().revision, 1);
    } else {
        assert_eq!(first, Err(CpuUsageError::UnsupportedProfile));
    }
    fixture.remove_leaf();
    let expected = if ostd::cpu::all_cpus().count() == 1 {
        CpuUsageError::Closed
    } else {
        CpuUsageError::UnsupportedProfile
    };
    assert_eq!(observer.read_usage(), Err(expected));
}

#[ktest]
fn initial_owner_lease_check_rejects_before_sampling() {
    let fixture = Fixture::new("g1c-observe-lease");
    let target = fixture.bind(1_320);
    let owner = fixture.owner();
    let controller = fixture.leaf.controller();
    let expired = controller.read_native_cpu_usage_for_owner_during(&owner, Some((0, 0)));
    if ostd::cpu::all_cpus().count() != 1 {
        assert_eq!(expired, Err(CpuUsageError::UnsupportedProfile));
        return;
    }
    assert_eq!(expired, Err(CpuUsageError::Expired));
    assert_eq!(fixture.budget().last_observed_ns, 0);
    assert_eq!(fixture.budget().cumulative_ns, 0);
    assert_eq!(
        controller.read_native_cpu_usage_for_owner_during(&owner, Some((u64::MAX - 1, u64::MAX))),
        Err(CpuUsageError::Indeterminate)
    );
    assert_eq!(fixture.budget().last_observed_ns, 0);
    let sample = controller.read_native_cpu_usage_for_owner_during(&owner, Some((0, u64::MAX))).unwrap();
    assert_eq!(sample.stable_object_id, target.stable_object_id());
    assert_eq!(sample.revision, 1);
}

#[ktest]
fn replacement_closes_the_old_snapshot_and_requires_a_new_binding() {
    let fixture = Fixture::new("g1b-usage-replace");
    assert_eq!(fixture.sample(0), Err(CpuUsageError::Unbound));
    let old = fixture.owner();
    let old_target = fixture.bind(1_170);
    fixture.checked_sample(0, &old_target, 1);
    fixture
        .parent
        .store_attr("cgroup.subtree_control", "-cpu")
        .unwrap();
    fixture
        .parent
        .store_attr("cgroup.subtree_control", "+cpu")
        .unwrap();
    let new = fixture.owner();
    assert!(!Arc::ptr_eq(&old, &new));
    assert_eq!(sample_owner(&old, 0), Err(CpuUsageError::Closed));
    assert_eq!(fixture.sample(0), Err(CpuUsageError::Unbound));
    assert!(matches!(
        fixture.leaf.controller().bind_native_cpu_once_for_owner(
            &old,
            ResourceDomainId::from_u128(1_180),
            StableObjectId::from_u128(1_181),
            &mut CgroupMembership::write_lock(),
        ),
        Err(Error::IsDead)
    ));
    // This real wrapper reads the local clock. Its N0 profile guard is tested
    // even when the suite is built/run with more than one configured CPU.
    let error = fixture
        .leaf
        .controller()
        .read_native_cpu_usage_for_owner(&old);
    if ostd::cpu::all_cpus().count() == 1 {
        assert_eq!(error, Err(CpuUsageError::Closed));
    } else {
        assert_eq!(error, Err(CpuUsageError::UnsupportedProfile));
    }
    reset(&new);
    let new_target = fixture.bind(1_190);
    assert_ne!(new_target.stable_object_id(), old_target.stable_object_id());
    let sample = fixture.checked_sample(0, &new_target, 1);
    assert_eq!(sample.cumulative_cpu_ns, 0);
    assert_eq!(sample.window_consumed_ns, 0);
}

#[ktest]
fn deleted_owner_stays_closed_while_its_final_debit_is_retained() {
    let mut fixture = Fixture::new("g1b-usage-delete");
    let target = fixture.bind(1_200);
    let old = fixture.owner();
    let mut runtime = CpuRuntimeFixture::new(fixture.task().clone(), 0);
    assert_eq!(runtime.update(17), (17, 17));
    assert_eq!(fixture.checked_sample(17, &target, 1).cumulative_cpu_ns, 17);
    drop(runtime);
    fixture.remove_leaf();
    assert_eq!(sample_owner(&old, 17), Err(CpuUsageError::Closed));
    with_state(&old, |state| {
        assert_eq!(state.max.cumulative_ns, 17);
        assert_eq!(state.native.as_ref().unwrap().revision(), 1);
    });
    // Closing management does not discard time already owned by this retained
    // incarnation. This is an explicit tail, not a running test task.
    old.charge_bandwidth_hierarchy(17, 29);
    assert_eq!(with_state(&old, |state| state.max.cumulative_ns), 29);
    assert_eq!(sample_owner(&old, 29), Err(CpuUsageError::Closed));
}

#[ktest]
fn indeterminate_metadata_cannot_produce_usage_after_detachment() {
    let mut fixture = Fixture::new("g1b-usage-indeterminate");
    let target = fixture.bind(1_210);
    fixture.checked_sample(0, &target, 1);
    let old = fixture.owner();
    let result = panic::catch_unwind(|| {
        with_state(&old, |state| {
            state
                .native
                .as_mut()
                .unwrap()
                .apply_owner_configuration(&mut || {
                    panic!("g1b expected ambiguous configuration");
                })
                .unwrap();
        });
    });
    assert!(result.is_err());
    assert_eq!(fixture.sample(0), Err(CpuUsageError::Indeterminate));
    fixture.remove_leaf();
    assert_eq!(sample_owner(&old, 0), Err(CpuUsageError::Indeterminate));
}

#[ktest]
fn unavailable_clock_allows_only_unlimited_linux_recovery() {
    let fixture = Fixture::new("g1b-usage-unavailable");
    let target = fixture.bind(1_220);
    let counter = Arc::new(AtomicU64::new(0));
    let source = clock(&counter, 1_000_000_000);
    let mut runtime = CpuRuntimeFixture::new_sample(fixture.task().clone(), source.read_sample());
    counter.store(100, Ordering::Relaxed);
    assert_eq!(runtime.update_sample(source.update()), (100, 100));
    fixture.checked_sample(100, &target, 1);
    counter.store(50, Ordering::Relaxed);
    let failed = source.update();
    assert!(!failed.is_reliable());
    runtime.configure_sample(failed, |now| {
        assert_eq!(now, None);
        assert!(matches!(
            fixture.configure("1000 100000", now),
            Err(Error::ResourceUnavailable)
        ));
    });
    assert_eq!(
        fixture.sample(100),
        Err(CpuUsageError::InconsistentAccounting)
    );
    fixture.configure("max 100000", None).unwrap();
    with_state(&fixture.owner(), |state| {
        assert_eq!(state.native.as_ref().unwrap().revision(), 2);
        assert_eq!(state.max.cumulative_ns, 100);
        assert_eq!(state.max.last_observed_ns, 100);
        assert!(state.max.accounting_fault);
    });
    runtime.configure(300, |now| {
        assert!(matches!(
            fixture.configure("1000 100000", Some(now)),
            Err(Error::ResourceUnavailable)
        ));
    });
    assert_eq!(fixture.budget().cumulative_ns, 100);
    assert_eq!(
        fixture.sample(300),
        Err(CpuUsageError::InconsistentAccounting)
    );
}

#[ktest]
fn reliable_clock_samples_cannot_rewind_the_runtime_endpoint() {
    let fixture = Fixture::new("g1b-usage-endpoint-backwards");
    fixture.bind(1_230);
    let counter = Arc::new(AtomicU64::new(0));
    let source = clock(&counter, 1_000_000_000);
    let mut runtime = CpuRuntimeFixture::new_sample(fixture.task().clone(), source.read_sample());
    counter.store(90, Ordering::Relaxed);
    assert_eq!(runtime.update_sample(source.read_sample()), (90, 90));
    counter.store(60, Ordering::Relaxed);
    // read_sample did not refresh the source's base. The source alone cannot
    // detect a reversal relative to the adapter's more recent endpoint.
    let backwards = source.read_sample();
    assert!(backwards.is_reliable());
    assert_eq!(backwards.checked_nanos(), Some(60));
    runtime.configure_sample(backwards, |now| {
        assert_eq!(now, Some(60));
        assert!(matches!(
            fixture.configure("1000 100000", now),
            Err(Error::ResourceUnavailable)
        ));
    });
    assert_eq!(
        fixture.sample(90),
        Err(CpuUsageError::InconsistentAccounting)
    );
    counter.store(120, Ordering::Relaxed);
    assert_eq!(runtime.update_sample(source.read_sample()), (30, 120));
    assert_eq!(fixture.budget().cumulative_ns, 90);
    fixture.configure("max 100000", Some(120)).unwrap();
    assert_eq!(
        fixture.sample(120),
        Err(CpuUsageError::InconsistentAccounting)
    );
}

#[ktest]
fn backwards_usage_observation_permanently_fences_the_owner() {
    let fixture = Fixture::new("g1b-usage-read-backwards");
    let target = fixture.bind(1_240);
    charge_task_cpu(fixture.task(), 0, 17);
    fixture.checked_sample(17, &target, 1);
    assert_eq!(
        fixture.sample(16),
        Err(CpuUsageError::InconsistentAccounting)
    );
    assert_eq!(
        fixture.sample(18),
        Err(CpuUsageError::InconsistentAccounting)
    );
    assert!(matches!(
        fixture.configure("1000 100000", Some(18)),
        Err(Error::ResourceUnavailable)
    ));
    fixture.configure("max 100000", Some(18)).unwrap();
    assert!(fixture.budget().accounting_fault);
    assert_eq!(fixture.budget().cumulative_ns, 17);
    assert_eq!(
        fixture.sample(18),
        Err(CpuUsageError::InconsistentAccounting)
    );
}

#[ktest]
fn backwards_same_value_configuration_cannot_reopen_an_old_window() {
    let fixture = Fixture::new("g1b-usage-config-backwards");
    let target = fixture.bind(1_260);
    fixture
        .configure("30000 100000", Some(200_000_000))
        .unwrap();
    charge_task_cpu(fixture.task(), 220_000_000, 240_000_000);
    let sample = fixture.checked_sample(250_000_000, &target, 2);
    assert_eq!(sample.window_start_ns, 200_000_000);
    assert_eq!(sample.window_consumed_ns, 20_000_000);
    assert_eq!(sample.cumulative_cpu_ns, 20_000_000);
    assert_eq!(sample.active_cap_ns, 30_000_000);
    if ostd::cpu::all_cpus().count() != 1 {
        // An earlier capture arriving from another CPU is not itself proof of
        // clock failure. The shared-owner path still cannot reopen a window.
        fixture
            .configure("30000 100000", Some(150_000_000))
            .unwrap();
        with_state(&fixture.owner(), |state| {
            assert!(!state.max.accounting_fault);
            assert_eq!(state.max.window_start_ns, 200_000_000);
            assert_eq!(state.max.last_observed_ns, 250_000_000);
            assert_eq!(state.max.used_ns, 20_000_000);
            assert_eq!(state.max.cumulative_ns, 20_000_000);
            assert_eq!(state.native.as_ref().unwrap().revision(), 3);
        });
        return;
    }
    assert!(matches!(
        fixture.configure("30000 100000", Some(150_000_000)),
        Err(Error::ResourceUnavailable)
    ));
    with_state(&fixture.owner(), |state| {
        assert!(state.max.accounting_fault);
        assert_eq!(state.max.window_start_ns, 200_000_000);
        assert_eq!(state.max.last_observed_ns, 250_000_000);
        assert_eq!(state.max.used_ns, 20_000_000);
        assert_eq!(state.max.cumulative_ns, 20_000_000);
        assert_eq!(state.native.as_ref().unwrap().revision(), 2);
        assert!(!state.max.eligible(250_000_000));
    });
    assert!(matches!(
        fixture.configure("30000 100000", Some(250_000_000)),
        Err(Error::ResourceUnavailable)
    ));
    // Removing the Linux cap may recover administrative access; even an old
    // supplied timestamp must retain the accounting window and native fence.
    fixture.configure("max 100000", Some(150_000_000)).unwrap();
    with_state(&fixture.owner(), |state| {
        assert!(state.max.accounting_fault);
        assert_eq!(state.max.window_start_ns, 200_000_000);
        assert_eq!(state.max.last_observed_ns, 250_000_000);
        assert_eq!(state.max.used_ns, 20_000_000);
        assert_eq!(state.max.cumulative_ns, 20_000_000);
        assert_eq!(state.native.as_ref().unwrap().revision(), 3);
    });
    assert_eq!(
        fixture.sample(250_000_000),
        Err(CpuUsageError::InconsistentAccounting)
    );
}

#[ktest]
fn cumulative_overflow_never_wraps_or_recovers_a_native_snapshot() {
    let fixture = Fixture::new("g1b-usage-overflow");
    fixture.bind(1_250);
    // Width-limit fault injection, not a physically reachable N0 history at
    // time zero. The following real debit must detect arithmetic overflow
    // before sample_usage can independently reject inconsistent history.
    with_state(&fixture.owner(), |state| {
        state.max.cumulative_ns = u64::MAX - 5;
    });
    let mut runtime = CpuRuntimeFixture::new(fixture.task().clone(), 0);
    assert_eq!(runtime.update(10), (10, 10));
    assert_eq!(fixture.budget().cumulative_ns, u64::MAX);
    assert!(fixture.budget().accounting_fault);
    assert_eq!(runtime.update(20), (10, 20));
    assert_eq!(fixture.budget().cumulative_ns, u64::MAX);
    assert_eq!(
        fixture.sample(20),
        Err(CpuUsageError::InconsistentAccounting)
    );
    assert!(matches!(
        fixture.configure("1000 100000", Some(20)),
        Err(Error::ResourceUnavailable)
    ));
    fixture.configure("max 100000", Some(20)).unwrap();
    assert_eq!(
        fixture.sample(20),
        Err(CpuUsageError::InconsistentAccounting)
    );
    assert_eq!(fixture.budget().cumulative_ns, u64::MAX);
}

#[ktest]
fn unreliable_clock_sample_cannot_rewind_or_replay_cycle_runtime() {
    let fixture = Fixture::new("g1b-usage-cycle-recovery");
    let target = fixture.bind(1_280);
    let counter = Arc::new(AtomicU64::new(0));
    let source = clock(&counter, 1_000_000_000);
    // A healthy source with the identical controlled origin can supply later
    // samples without resetting the failed original ClockSource or runtime.
    let reference = clock(&counter, 1_000_000_000);
    let mut runtime = CpuRuntimeFixture::new_sample(fixture.task().clone(), source.read_sample());
    counter.store(100, Ordering::Relaxed);
    assert_eq!(runtime.update_sample(source.update()), (100, 100));
    counter.store(150, Ordering::Relaxed);
    assert_eq!(runtime.update_sample(source.read_sample()), (50, 150));
    fixture.checked_sample(150, &target, 1);

    // The counter is older than the retained refresh base, not merely older
    // than the previous read. The failure sample therefore carries base 100
    // while the runtime has already accounted through cycle 150.
    counter.store(50, Ordering::Relaxed);
    let failed = source.read_sample();
    assert!(!failed.is_reliable());
    assert_eq!(failed.cycles(), 100);
    assert_eq!(failed.checked_nanos(), None);
    assert_eq!(runtime.update_sample(failed), (0, 150));
    assert_eq!(runtime.update_sample(failed), (0, 150));
    assert_eq!(fixture.budget().cumulative_ns, 150);
    assert_eq!(
        fixture.sample(150),
        Err(CpuUsageError::InconsistentAccounting)
    );

    counter.store(160, Ordering::Relaxed);
    let next = reference.read_sample();
    assert!(next.is_reliable());
    assert_eq!(runtime.update_sample(next), (10, 160));
    assert_eq!(runtime.update_sample(next), (0, 160));
    counter.store(175, Ordering::Relaxed);
    assert_eq!(runtime.update_sample(reference.read_sample()), (15, 175));
    assert!(!source.read_sample().is_reliable());
    assert_eq!(fixture.budget().cumulative_ns, 150);
    assert_eq!(
        fixture.sample(175),
        Err(CpuUsageError::InconsistentAccounting)
    );
}

#[ktest]
fn late_same_value_reconfigure_preserves_window_usage_and_debt() {
    let fixture = Fixture::new("g1b-usage-late-config");
    fixture
        .configure("30000 100000", Some(100_000_000))
        .unwrap();
    fixture.bind(1_290);
    charge_task_cpu(fixture.task(), 120_000_000, 155_000_000);
    charge_task_cpu(fixture.task(), 220_000_000, 240_000_000);
    with_state(&fixture.owner(), |state| {
        assert!(state.max.eligible(250_000_000));
        assert_eq!(state.max.window_start_ns, 200_000_000);
        assert_eq!(state.max.used_ns, 20_000_000);
        assert_eq!(state.max.cumulative_ns, 55_000_000);
        assert_eq!(state.max.carry_debt_ns, 5_000_000);
        // This is the original shared-owner mutation beneath the single-CPU
        // native admission guard. Model a late lock arrival deterministically;
        // do not infer live SMP scheduling from these ordered fixture calls.
        for revision in [2, 3] {
            state
                .reconfigure(CpuMaxConfig::parse("30000 100000").unwrap(), 150_000_000)
                .unwrap();
            assert!(!state.max.accounting_fault);
            assert_eq!(state.max.last_observed_ns, 250_000_000);
            assert_eq!(state.max.window_start_ns, 200_000_000);
            assert_eq!(state.max.used_ns, 20_000_000);
            assert_eq!(state.max.cumulative_ns, 55_000_000);
            assert_eq!(state.max.carry_debt_ns, 5_000_000);
            assert_eq!(state.native.as_ref().unwrap().revision(), revision);
            assert!(state.max.eligible(150_000_000));
            assert_eq!(state.max.last_observed_ns, 250_000_000);
            assert_eq!(state.max.window_start_ns, 200_000_000);
            assert_eq!(state.max.used_ns, 20_000_000);
            assert_eq!(state.max.carry_debt_ns, 5_000_000);
        }
    });
}

#[ktest]
fn overlapping_owner_intervals_accumulate_without_a_clock_fault() {
    let fixture = Fixture::new("g1b-usage-overlap");
    fixture
        .configure("30000 100000", Some(100_000_000))
        .unwrap();
    fixture.bind(1_300);
    let additional = AdditionalProcess::new(&fixture.leaf);
    let mut first = CpuRuntimeFixture::new(fixture.task().clone(), 100_000_000);
    let mut second = CpuRuntimeFixture::new(additional.task().clone(), 105_000_000);
    assert_eq!(first.update(140_000_000), (40_000_000, 40_000_000));
    // A distinct task's overlapping interval ends before the already-settled
    // task's endpoint. The owner lock can see this order on multiple CPUs.
    assert_eq!(second.update(130_000_000), (25_000_000, 25_000_000));
    assert_eq!(fixture.budget().cumulative_ns, 65_000_000);
    assert_eq!(fixture.budget().used_ns, 65_000_000);
    assert_eq!(fixture.budget().last_observed_ns, 140_000_000);
    assert!(!fixture.budget().accounting_fault);
    assert_eq!(second.update(135_000_000), (5_000_000, 30_000_000));
    assert_eq!(first.update(145_000_000), (5_000_000, 45_000_000));
    with_state(&fixture.owner(), |state| {
        assert_eq!(state.max.cumulative_ns, 75_000_000);
        assert_eq!(state.max.used_ns, 75_000_000);
        assert_eq!(state.max.window_start_ns, 100_000_000);
        assert_eq!(state.max.last_observed_ns, 145_000_000);
        assert!(!state.max.accounting_fault);
        assert!(!state.max.eligible(145_000_000));
        assert!(!state.max.accounting_fault);
    });
    // No single-CPU native snapshot is requested for the two overlapping
    // controlled intervals. The real tasks are unstarted, not live SMP work.
}
