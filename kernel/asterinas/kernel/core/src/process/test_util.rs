// SPDX-License-Identifier: MPL-2.0

//! Real, unscheduled POSIX objects for kernel lifecycle regression tests.

use ostd::{arch::cpu::context::UserContext, task::Task};

use super::{
    Credentials, Process, ProcessVm, UserNamespace,
    posix_thread::{AsPosixThread, PosixThreadBuilder, allocate_posix_tid, derive_thread_name},
    rlimit::new_resource_limits_for_init,
    signal::sig_disposition::SigDispositions,
};
use crate::{
    fs::{cgroupfs::CgroupMembership, pseudofs::SockFs},
    prelude::*,
    sched::Nice,
    thread::AsThread,
    time::clocks,
    util::random,
    vm::vmar::VmarHandle,
};

/// Builds a POSIX process and its main task without adding either to the PID table
/// or scheduling userspace. All constructors and cgroup/task fields are real.
pub(crate) fn new_unstarted_process() -> (Arc<Process>, Arc<Task>) {
    let (process, mut tasks) = new_unstarted_process_with_threads(1);
    (process, tasks.pop().unwrap())
}

/// Reads the original thread/process queue facts without changing signal state.
/// Keeps private signal queues private outside the process module in production.
pub(crate) fn sigkill_receipts(task: &Task) -> (bool, bool) {
    let thread = task.as_posix_thread().unwrap();
    (
        thread.sig_queues().has_received_sigkill(),
        thread.process().sig_queues().has_received_sigkill(),
    )
}

/// Initializes the real heap required by the VMAR fork path. Lifecycle-only
/// fixtures intentionally remain unmapped until a test requests this step.
pub(crate) fn initialize_heap_for_fork(process: &Process, heap_base: Vaddr) {
    let locked_vmar = process.lock_vmar();
    let vmar = locked_vmar.unwrap();
    vmar.process_vm()
        .map_and_init_heap(vmar, 0, heap_base)
        .unwrap();
}

/// Builds a real task set whose threads all share one Process and VMAR. The
/// caller owns cleanup; no task is registered in the PID table or scheduled.
pub(crate) fn new_unstarted_process_with_threads(count: usize) -> (Arc<Process>, Vec<Arc<Task>>) {
    assert!(count > 0);
    clocks::init_for_ktest();
    random::init();

    let pid = allocate_posix_tid();
    let vmar = VmarHandle::new(ProcessVm::new(SockFs::new_path()));
    let process = Process::new(
        pid,
        vmar.clone_arc(),
        new_resource_limits_for_init(),
        Nice::default(),
        0,
        Arc::new(Mutex::new(SigDispositions::default())),
        UserNamespace::get_init_singleton().clone(),
    );
    let mut tasks = Vec::with_capacity(count);
    for index in 0..count {
        let tid = if index == 0 {
            pid
        } else {
            allocate_posix_tid()
        };
        let task = PosixThreadBuilder::new(
            tid,
            derive_thread_name("a06-charge-regression"),
            Box::new(UserContext::default()),
            Credentials::new_root(),
            vmar.clone_handle(),
        )
        .process(Arc::downgrade(&process))
        .build();
        process.tasks().lock().insert(task.clone()).unwrap();
        tasks.push(task);
    }
    (process, tasks)
}

/// Publishes the same zombie/population transaction as `exit_process`.
/// This does not execute the syscall exit or scheduler exit path.
pub(crate) fn mark_zombie(process: &Process) {
    let mut membership = CgroupMembership::write_lock();
    for task in process.tasks().lock().as_slice() {
        task.as_thread().unwrap().exit();
    }
    if !process.status().is_zombie() {
        process.status().set_zombie();
        membership.hide_zombie_process(process);
    }
}

/// A real, unscheduled parent for lifecycle tests that call Process::stop/resume.
///
/// Holds both original parent/child links while notifications are exercised.
/// These fixtures have no PID-table entries; detaching the zombie below releases
/// the original children-map owner, but does not claim syscall wait/reap coverage.
pub(crate) struct UnstartedParent {
    process: Arc<Process>,
    _task: Arc<Task>,
    child_pid: super::Pid,
}

impl UnstartedParent {
    pub(crate) fn new(child: &Arc<Process>) -> Self {
        let (process, task) = new_unstarted_process();
        {
            // Same order as parent publication: children -> child's parent.
            let mut children = process.children().lock();
            let mut parent = child.parent().lock();
            assert!(parent.process().upgrade().is_none());
            assert!(
                children
                    .as_mut()
                    .unwrap()
                    .insert(child.pid(), child.clone())
                    .is_none()
            );
            parent.set_process(&process);
        }
        Self {
            process,
            _task: task,
            child_pid: child.pid(),
        }
    }

    pub(crate) fn process(&self) -> &Process {
        &self.process
    }

    pub(crate) fn detach_zombie_child(&self) {
        let child = self
            .process
            .children()
            .lock()
            .as_mut()
            .unwrap()
            .remove(&self.child_pid)
            .unwrap();
        assert!(child.status().is_zombie());
        drop(child);
    }
}

impl Drop for UnstartedParent {
    fn drop(&mut self) {
        // Also clean up after an assertion unwinds. Release the children lock
        // before the membership transaction in mark_zombie.
        let child = self
            .process
            .children()
            .lock()
            .as_mut()
            .unwrap()
            .remove(&self.child_pid);
        if let Some(child) = child {
            mark_zombie(&child);
        }
        mark_zombie(&self.process);
    }
}
