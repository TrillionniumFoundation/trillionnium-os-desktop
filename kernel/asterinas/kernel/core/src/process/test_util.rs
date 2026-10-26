// SPDX-License-Identifier: MPL-2.0

//! Real, unscheduled POSIX objects for kernel lifecycle regression tests.

use ostd::{arch::cpu::context::UserContext, task::Task};

use super::{
    Credentials, Process, ProcessVm, UserNamespace,
    posix_thread::{PosixThreadBuilder, allocate_posix_tid, derive_thread_name},
    rlimit::new_resource_limits_for_init,
    signal::sig_disposition::SigDispositions,
};
use crate::{
    fs::{cgroupfs::CgroupMembership, pseudofs::SockFs},
    prelude::*,
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

/// Initializes the real heap required by the VMAR fork path. Lifecycle-only
/// fixtures intentionally remain unmapped until a test requests this step.
pub(crate) fn initialize_heap_for_fork(process: &Process, heap_base: Vaddr) {
    let locked_vmar = process.lock_vmar();
    let vmar = locked_vmar.unwrap();
    initialize_vmar_heap_for_fork(vmar, heap_base);
}

pub(crate) fn initialize_vmar_heap_for_fork(vmar: &crate::vm::vmar::Vmar, heap_base: Vaddr) {
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

    let vmar = VmarHandle::new(ProcessVm::new(SockFs::new_path()));
    new_unstarted_process_with_vmar_and_threads(vmar, count)
}

pub(crate) fn new_unstarted_process_in_vmar(vmar: VmarHandle) -> (Arc<Process>, Arc<Task>) {
    clocks::init_for_ktest();
    random::init();
    let (process, mut tasks) = new_unstarted_process_with_vmar_and_threads(vmar, 1);
    (process, tasks.pop().unwrap())
}

fn new_unstarted_process_with_vmar_and_threads(
    vmar: VmarHandle,
    count: usize,
) -> (Arc<Process>, Vec<Arc<Task>>) {
    let pid = allocate_posix_tid();
    let process = Process::new(
        pid,
        vmar.clone_arc(),
        new_resource_limits_for_init(),
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
        .build()
        .unwrap();
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
