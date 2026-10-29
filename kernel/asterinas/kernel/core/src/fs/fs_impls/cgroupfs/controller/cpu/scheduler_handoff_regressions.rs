// SPDX-License-Identifier: MPL-2.0

//! G1-b: charge the outgoing class-runqueue segment through its handoff.
//!
//! These tests use the actual class queues, cgroups, Process and Task objects
//! with controlled TSC endpoints. They do not replace OSTD's FIFO scheduler or
//! qualify SMP context switching, BOOTTIME windows or native authorization.

use alloc::sync::Arc;

use aster_systree::{SysBranchNode, SysNode};
use ostd::{
    prelude::ktest,
    task::{Task, scheduler::UpdateFlags},
};

use super::{
    super::{Controller, SubController, SubCtrlType},
    CpuController, CpuMax,
};
use crate::{
    fs::cgroupfs::{CgroupMembership, CgroupNode, CgroupSysNode, CgroupSystem},
    process::{Process, posix_thread::AsPosixThread, test_util},
    sched::{CpuRunQueueFixture, SchedPolicy},
    thread::AsThread,
};

struct Fixture {
    root: &'static Arc<CgroupSystem>,
    parent: Arc<CgroupNode>,
    leaves: [Arc<CgroupNode>; 2],
    processes: [Arc<Process>; 3],
    tasks: [Arc<Task>; 3],
    original_root_budget: CpuMax,
    enabled_root_cpu: bool,
    name: &'static str,
    start: u64,
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
        let leaves = ["outgoing", "candidate"]
            .map(|name| Arc::downcast::<CgroupNode>(parent.create_child(name).unwrap()).unwrap());
        let original_root_budget = budget(&owner(root.controller()));
        let period = CpuMax::us_to_ns(100_000).max(1);
        let start = (aster_time::try_read_monotonic_sample()
            .unwrap()
            .checked_nanos()
            .unwrap()
            / period
            + 2)
            * period;
        for controller in [
            root.controller(),
            parent.controller(),
            leaves[0].controller(),
            leaves[1].controller(),
        ] {
            reset(&owner(controller), start, u64::MAX);
        }
        let objects = core::array::from_fn::<_, 3, _>(|_| test_util::new_unstarted_process());
        let processes = core::array::from_fn(|i| objects[i].0.clone());
        let tasks = core::array::from_fn(|i| objects[i].1.clone());
        for i in 0..2 {
            CgroupMembership::write_lock()
                .move_process_to_node(processes[i].clone(), &leaves[i])
                .unwrap();
        }
        Self {
            root,
            parent,
            leaves,
            processes,
            tasks,
            original_root_budget,
            enabled_root_cpu,
            name,
            start,
        }
    }

    fn runqueue(&self, start: u64) -> CpuRunQueueFixture {
        CpuRunQueueFixture::new(self.tasks[0].clone(), start)
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        for (process, task) in self.processes.iter().zip(&self.tasks) {
            CgroupMembership::write_lock().move_process_to_root(process);
            task.as_posix_thread().unwrap().set_cpu_cgroup(None);
        }
        self.parent.remove_child("outgoing").unwrap();
        self.parent.remove_child("candidate").unwrap();
        self.root.remove_child(self.name).unwrap();
        owner(self.root.controller())
            .inner
            .as_ref()
            .unwrap()
            .control()
            .unwrap()
            .max
            .lock()
            .max = self.original_root_budget;
        if self.enabled_root_cpu {
            self.root
                .store_attr("cgroup.subtree_control", "-cpu")
                .unwrap();
        }
    }
}

fn owner(controller: &Controller) -> Arc<SubController<CpuController>> {
    controller.cpu.read().get().clone()
}

fn budget(owner: &SubController<CpuController>) -> CpuMax {
    owner
        .inner
        .as_ref()
        .unwrap()
        .control()
        .unwrap()
        .max
        .lock()
        .max
}

fn reset(owner: &SubController<CpuController>, start: u64, quota_usec: u64) {
    owner
        .inner
        .as_ref()
        .unwrap()
        .control()
        .unwrap()
        .max
        .lock()
        .max = CpuMax {
        quota_usec,
        quota_sub_usec_ns: 0,
        period_usec: 100_000,
        window_start_ns: start,
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
}

#[ktest]
fn outgoing_tail_ends_at_the_incoming_segment_start() {
    let fixture = Fixture::new("g1b-handoff-tail");
    let mut rq = fixture.runqueue(fixture.start);
    rq.enqueue(fixture.tasks[1].clone());
    let next = rq.pick(&[fixture.start + 11, fixture.start + 29]).unwrap();
    assert!(Arc::ptr_eq(&next, &fixture.tasks[1]));
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 29);
    assert_eq!(budget(&owner(fixture.leaves[1].controller())).used_ns, 0);
    assert_eq!(rq.cfs_runtime(), Some((fixture.start + 29, 0, 0)));
    rq.update(UpdateFlags::Tick, fixture.start + 47);
    assert_eq!(rq.cfs_runtime(), Some((fixture.start + 47, 18, 18)));
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 29);
    assert_eq!(budget(&owner(fixture.leaves[1].controller())).used_ns, 18);
    assert_eq!(budget(&owner(fixture.parent.controller())).used_ns, 47);
    assert_eq!(budget(&owner(fixture.root.controller())).used_ns, 47);
}

#[ktest]
fn handoff_debits_the_old_window_before_rechecking_a_shared_ancestor() {
    let fixture = Fixture::new("g1b-handoff-quota");
    let parent = owner(fixture.parent.controller());
    reset(&parent, fixture.start, 1_000);
    let period = CpuMax::us_to_ns(100_000).max(1);
    let quota = CpuMax::us_to_ns(1_000);
    assert!(quota >= 4 && 2 * quota < period);
    let quarter = quota / 4;
    let boundary = fixture.start + period;
    let mut rq = fixture.runqueue(boundary - 2 * quota);
    rq.enqueue(fixture.tasks[1].clone());
    // This real task is outside the limited parent. The kernel-only idle
    // policy makes it the fallback after the fair candidate is parked.
    fixture.tasks[2]
        .as_thread()
        .unwrap()
        .sched_attr()
        .set_policy(SchedPolicy::Idle);
    rq.enqueue(fixture.tasks[2].clone());
    let cut = boundary + quarter;
    let next = rq
        .pick(&[boundary - quota - quarter, cut, cut + 5])
        .unwrap();
    assert!(Arc::ptr_eq(&next, &fixture.tasks[2]));
    assert!(rq.is_throttled(&fixture.tasks[1]));
    assert!(rq.is_throttled(&fixture.tasks[0]));
    let state = budget(&parent);
    assert_eq!(state.window_start_ns, boundary);
    assert_eq!(state.carry_debt_ns, quota);
    assert_eq!(state.used_ns, quarter + 5);
    assert_eq!(
        budget(&owner(fixture.leaves[0].controller())).used_ns,
        quarter + 5
    );
    assert_eq!(budget(&owner(fixture.leaves[1].controller())).used_ns, 0);
    assert_eq!(
        budget(&owner(fixture.root.controller())).used_ns,
        quarter + 5
    );
    assert_eq!(rq.cfs_runtime(), Some((cut + 5, 0, 0)));
}

fn exercise_dequeue(name: &'static str, flag: UpdateFlags) {
    let fixture = Fixture::new(name);
    let mut rq = fixture.runqueue(fixture.start);
    rq.update(flag, fixture.start + 11);
    assert_eq!(rq.cfs_runtime(), Some((fixture.start + 11, 11, 11)));
    if flag == UpdateFlags::Exit {
        test_util::mark_zombie(&fixture.processes[0]);
        CgroupMembership::write_lock().move_process_to_root(&fixture.processes[0]);
    }
    let outgoing = rq.dequeue(fixture.start + 19).unwrap();
    assert!(Arc::ptr_eq(&outgoing, &fixture.tasks[0]));
    assert!(!rq.has_current());
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 19);
    // OSTD can retry selection with current() == None. The same old segment
    // remains the bandwidth owner, without extending CFS's finished slice.
    assert!(rq.pick(&[fixture.start + 29]).is_none());
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 29);
    assert!(!rq.update(UpdateFlags::Tick, fixture.start + 31));
    assert_eq!(rq.cfs_runtime(), Some((fixture.start + 11, 11, 11)));
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 31);
    rq.enqueue(fixture.tasks[1].clone());
    let next = rq.pick(&[fixture.start + 37, fixture.start + 41]).unwrap();
    assert!(Arc::ptr_eq(&next, &fixture.tasks[1]));
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 41);
    assert_eq!(rq.cfs_runtime(), Some((fixture.start + 41, 0, 0)));
    rq.update(UpdateFlags::Tick, fixture.start + 53);
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 41);
    assert_eq!(budget(&owner(fixture.leaves[1].controller())).used_ns, 12);
    assert_eq!(budget(&owner(fixture.parent.controller())).used_ns, 53);
    assert_eq!(budget(&owner(fixture.root.controller())).used_ns, 53);
}

#[ktest]
fn waiting_dequeue_retains_its_owner_through_selection_retries() {
    exercise_dequeue("g1b-handoff-wait", UpdateFlags::Wait);
}

#[ktest]
fn exiting_dequeue_retains_its_owner_through_selection_retries() {
    exercise_dequeue("g1b-handoff-exit", UpdateFlags::Exit);
}

#[ktest]
fn completed_switch_keeps_the_original_owner_through_the_physical_tail() {
    let fixture = Fixture::new("w3a-physical-tail");
    let mut rq = fixture.runqueue(fixture.start);
    rq.enqueue(fixture.tasks[1].clone());
    let next = rq
        .pick_switch(&[fixture.start + 11, fixture.start + 29])
        .unwrap();
    assert!(Arc::ptr_eq(&next, &fixture.tasks[1]));
    assert_eq!(rq.queued_count(), 0);
    assert!(rq.pick(&[fixture.start + 37]).is_none());
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 37);
    assert_eq!(budget(&owner(fixture.leaves[1].controller())).used_ns, 0);
    assert!(!rq.finish_switch(&fixture.tasks[0], fixture.start + 47));
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 47);
    assert_eq!(rq.cfs_runtime(), Some((fixture.start + 47, 0, 0)));
    assert_eq!(rq.queued_count(), 0);
    assert!(
        rq.complete_switch(&fixture.tasks[0], fixture.start + 53)
            .is_none()
    );
    assert_eq!(rq.queued_count(), 1);
    rq.update(UpdateFlags::Tick, fixture.start + 61);
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 47);
    assert_eq!(budget(&owner(fixture.leaves[1].controller())).used_ns, 14);
    assert_eq!(budget(&owner(fixture.parent.controller())).used_ns, 61);
}

#[ktest]
fn completed_wait_merges_late_wakes_into_one_detached_token() {
    let fixture = Fixture::new("w3a-late-wake");
    let mut rq = fixture.runqueue(fixture.start);
    rq.update(UpdateFlags::Wait, fixture.start + 11);
    rq.dequeue(fixture.start + 19).unwrap();
    rq.enqueue(fixture.tasks[1].clone());
    rq.pick_switch(&[fixture.start + 23, fixture.start + 29])
        .unwrap();
    assert!(rq.wake_outgoing(&fixture.tasks[0]));
    assert_eq!(rq.queued_count(), 0);
    rq.finish_switch(&fixture.tasks[0], fixture.start + 41);
    assert!(rq.wake_outgoing(&fixture.tasks[0]));
    let token = rq
        .complete_switch(&fixture.tasks[0], fixture.start + 47)
        .unwrap();
    assert!(Arc::ptr_eq(&token, &fixture.tasks[0]));
    assert_eq!(rq.queued_count(), 0);
    assert!(
        rq.complete_switch(&fixture.tasks[0], fixture.start + 53)
            .is_none()
    );
    assert!(!rq.wake_outgoing(&fixture.tasks[0]));
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 41);
    assert_eq!(budget(&owner(fixture.leaves[1].controller())).used_ns, 6);
}

#[ktest]
fn waiting_retry_can_restore_the_same_task_without_a_switch_callback() {
    let fixture = Fixture::new("w3a-wait-restore");
    let mut rq = fixture.runqueue(fixture.start);
    rq.update(UpdateFlags::Wait, fixture.start + 11);
    rq.dequeue(fixture.start + 19).unwrap();
    assert!(rq.pick(&[fixture.start + 23]).is_none());
    assert!(rq.wake_outgoing(&fixture.tasks[0]));
    let restored = rq.pick(&[fixture.start + 29]).unwrap();
    assert!(Arc::ptr_eq(&restored, &fixture.tasks[0]));
    assert_eq!(rq.queued_count(), 0);
    rq.update(UpdateFlags::Tick, fixture.start + 41);
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 41);
    assert_eq!(budget(&owner(fixture.parent.controller())).used_ns, 41);
}

#[ktest]
fn completed_exit_never_becomes_runnable_after_a_late_wake() {
    let fixture = Fixture::new("w3a-exit-wake");
    let mut rq = fixture.runqueue(fixture.start);
    rq.update(UpdateFlags::Exit, fixture.start + 11);
    rq.dequeue(fixture.start + 19).unwrap();
    assert!(rq.wake_outgoing(&fixture.tasks[0]));
    assert!(rq.pick(&[fixture.start + 23]).is_none());
    rq.enqueue(fixture.tasks[1].clone());
    rq.pick_switch(&[fixture.start + 29, fixture.start + 31])
        .unwrap();
    assert!(rq.wake_outgoing(&fixture.tasks[0]));
    rq.finish_switch(&fixture.tasks[0], fixture.start + 41);
    assert!(
        rq.complete_switch(&fixture.tasks[0], fixture.start + 47)
            .is_none()
    );
    assert_eq!(rq.queued_count(), 0);
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 41);
}

#[ktest]
fn physical_tail_exhaustion_requests_preemption_after_committing_incoming() {
    let fixture = Fixture::new("w3a-tail-quota");
    let parent = owner(fixture.parent.controller());
    reset(&parent, fixture.start, 1);
    let mut rq = fixture.runqueue(fixture.start);
    rq.enqueue(fixture.tasks[1].clone());
    rq.pick_switch(&[fixture.start + 11, fixture.start + 29])
        .unwrap();
    assert!(rq.finish_switch(&fixture.tasks[0], fixture.start + 1001));
    assert_eq!(rq.cfs_runtime(), Some((fixture.start + 1001, 0, 0)));
    assert_eq!(budget(&owner(fixture.leaves[0].controller())).used_ns, 1001);
    assert_eq!(budget(&owner(fixture.leaves[1].controller())).used_ns, 0);
    assert!(
        rq.complete_switch(&fixture.tasks[0], fixture.start + 1003)
            .is_none()
    );
    assert!(rq.is_throttled(&fixture.tasks[0]));
    assert_eq!(budget(&parent).used_ns, 1003);
}
