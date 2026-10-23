// SPDX-License-Identifier: MPL-2.0

//! G1-b: charge the outgoing class-runqueue segment through its handoff.
//!
//! These tests use the actual class queues, cgroups, Process and Task objects
//! with controlled TSC endpoints. They do not replace OSTD's FIFO scheduler or
//! qualify SMP context switching, BOOTTIME windows or native authorization.

use alloc::{boxed::Box, sync::Arc};

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
    process::{
        Process,
        posix_thread::AsPosixThread,
        signal::{
            HandlePendingSignal,
            constants::{SIGKILL, SIGUSR1},
            sig_mask::SigMask,
            signals::kernel::KernelSignal,
        },
        test_util,
    },
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

fn exercise_zero_quota_fatal_cleanup(name: &'static str, process_signal: bool) {
    let fixture = Fixture::new(name);
    // The original init predicate is parent.pid() == 0, not the numeric PID.
    // Publish real parent/child owners so this fixture models a killable child.
    let _parent = test_util::UnstartedParent::new(&fixture.processes[1]);
    assert!(!fixture.processes[1].is_init_process());
    let victim = &fixture.tasks[1];
    let posix = victim.as_posix_thread().unwrap();
    let cpu = owner(fixture.leaves[1].controller());
    reset(&cpu, fixture.start, 0);
    {
        let mut state = cpu.inner.as_ref().unwrap().control().unwrap().max.lock();
        state.max.used_ns = 13;
        state.max.cumulative_ns = 21;
        state.max.carry_debt_ns = 17;
    }
    let mut rq = fixture.runqueue(fixture.start);
    rq.enqueue(victim.clone());
    assert!(rq.pick(&[fixture.start + 1]).is_none());
    assert!(rq.is_throttled(victim));

    // A catchable signal never permits running user handlers at zero quota.
    posix.enqueue_signal(Box::new(KernelSignal::new(SIGUSR1)));
    assert!(rq.pick(&[fixture.start + 2]).is_none());
    assert!(rq.is_throttled(victim));
    assert!(!posix.has_fatal_sigkill());
    assert_eq!(
        posix
            .dequeue_signal(&SigMask::from(0))
            .unwrap()
            .unwrap()
            .num(),
        SIGUSR1
    );
    if process_signal {
        fixture.processes[1].enqueue_signal(Box::new(KernelSignal::new(SIGKILL)));
    } else {
        posix.enqueue_signal(Box::new(KernelSignal::new(SIGKILL)));
    }
    assert_eq!(
        test_util::sigkill_receipts(victim),
        (!process_signal, process_signal)
    );
    assert!(posix.has_fatal_sigkill());
    assert!(
        !fixture.tasks[0]
            .as_posix_thread()
            .unwrap()
            .has_fatal_sigkill()
    );

    let next = rq.pick(&[fixture.start + 10, fixture.start + 11]).unwrap();
    assert!(Arc::ptr_eq(&next, victim));
    assert!(!rq.is_throttled(victim));
    assert_eq!(budget(&cpu).quota_ns(), 0);
    assert_eq!(budget(&cpu).used_ns, 13);
    assert_eq!(budget(&cpu).cumulative_ns, 21);
    assert_eq!(budget(&cpu).carry_debt_ns, 17);

    // Dequeuing the actual signal does not revoke cleanup eligibility mid-exit.
    assert_eq!(
        posix
            .dequeue_signal(&SigMask::from(0))
            .unwrap()
            .unwrap()
            .num(),
        SIGKILL
    );
    assert!(posix.has_fatal_sigkill());
    rq.update(UpdateFlags::Tick, fixture.start + 29);
    assert_eq!(budget(&cpu).quota_ns(), 0);
    assert_eq!(budget(&cpu).used_ns, 31);
    assert_eq!(budget(&cpu).cumulative_ns, 39);
    assert_eq!(budget(&cpu).carry_debt_ns, 17);
    assert_eq!(rq.cfs_runtime(), Some((fixture.start + 29, 18, 18)));
}

#[ktest]
fn zero_quota_thread_sigkill_resumes_only_fatal_cleanup_with_original_debit() {
    exercise_zero_quota_fatal_cleanup("g1b-zero-thread-kill", false);
}

#[ktest]
fn zero_quota_process_sigkill_resumes_only_fatal_cleanup_with_original_debit() {
    exercise_zero_quota_fatal_cleanup("g1b-zero-process-kill", true);
}

#[ktest]
fn fatal_receipts_follow_original_signal_queues_without_constructor_inheritance() {
    // The same accepted original signal remains ineffective for a parentless
    // init process. No fake PID or scheduler-only flag is used for either cut.
    let (init, init_task) = test_util::new_unstarted_process();
    let init_thread = init_task.as_posix_thread().unwrap();
    assert!(init.is_init_process());
    init_thread.enqueue_signal(Box::new(KernelSignal::new(SIGKILL)));
    init.enqueue_signal(Box::new(KernelSignal::new(SIGKILL)));
    assert_eq!(test_util::sigkill_receipts(&init_task), (true, true));
    assert!(init_thread.has_pending_sigkill());
    assert!(!init_thread.has_fatal_sigkill());
    test_util::mark_zombie(&init);

    let (process, tasks) = test_util::new_unstarted_process_with_threads(2);
    let _parent = test_util::UnstartedParent::new(&process);
    assert!(!process.is_init_process());
    let first = tasks[0].as_posix_thread().unwrap();
    let sibling = tasks[1].as_posix_thread().unwrap();
    first.enqueue_signal(Box::new(KernelSignal::new(SIGKILL)));
    assert_eq!(test_util::sigkill_receipts(&tasks[0]), (true, false));
    assert!(first.has_fatal_sigkill());
    assert!(!sibling.has_fatal_sigkill());
    assert_eq!(
        first
            .dequeue_signal(&SigMask::from(0))
            .unwrap()
            .unwrap()
            .num(),
        SIGKILL
    );
    assert!(first.has_fatal_sigkill());
    assert!(!sibling.has_fatal_sigkill());

    process.enqueue_signal(Box::new(KernelSignal::new(SIGKILL)));
    assert_eq!(test_util::sigkill_receipts(&tasks[0]), (true, true));
    assert_eq!(test_util::sigkill_receipts(&tasks[1]), (false, true));
    assert!(first.has_fatal_sigkill() && sibling.has_fatal_sigkill());
    assert_eq!(
        sibling
            .dequeue_signal(&SigMask::from(0))
            .unwrap()
            .unwrap()
            .num(),
        SIGKILL
    );
    assert!(first.has_fatal_sigkill() && sibling.has_fatal_sigkill());
    // The same Process::new and PosixThreadBuilder constructors used by clone
    // initialize new queues. No fatal receipt is copied from a source image.
    let (fresh, fresh_tasks) = test_util::new_unstarted_process_with_threads(2);
    let _fresh_parent = test_util::UnstartedParent::new(&fresh);
    assert!(!fresh.is_init_process());
    for task in fresh_tasks {
        let thread = task.as_posix_thread().unwrap();
        assert_eq!(test_util::sigkill_receipts(&task), (false, false));
        assert!(!thread.has_fatal_sigkill());
    }
}
