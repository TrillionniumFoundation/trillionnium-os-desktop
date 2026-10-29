// SPDX-License-Identifier: MPL-2.0

use ostd::{arch::cpu::context::UserContext, prelude::ktest, task::Task};

use super::*;
use crate::{
    fs::pseudofs::SockFs,
    process::{
        Credentials, Gid, ProcessVm, Uid, UserNamespace,
        posix_thread::{AsPosixThread, PosixThreadBuilder, allocate_posix_tid, derive_thread_name},
        rlimit::new_resource_limits_for_init,
        signal::sig_disposition::SigDispositions,
        test_util,
    },
    vm::vmar::{Vmar, VmarHandle},
};

struct Fixture {
    process: Arc<Process>,
    tasks: Vec<Arc<Task>>,
    vm: VmarHandle,
}

impl Fixture {
    fn new() -> Self {
        crate::time::clocks::init_for_ktest();
        crate::util::random::init();
        let vm = VmarHandle::new(ProcessVm::new(SockFs::new_path()));
        test_util::initialize_vmar_heap_for_fork(&vm, 0x1000_0000);
        Self::build(vm, OomInit::Initial(0))
    }

    fn build(vm: VmarHandle, init: OomInit<'_>) -> Self {
        let mut pid = allocate_posix_tid();
        if pid == INIT_PROCESS_PID {
            pid = allocate_posix_tid();
        }
        let process = Process::new(
            pid,
            vm.clone_arc(),
            new_resource_limits_for_init(),
            init,
            Arc::new(Mutex::new(SigDispositions::default())),
            UserNamespace::get_init_singleton().clone(),
        );
        Self {
            process,
            tasks: Vec::new(),
            vm,
        }
    }

    fn add_writer(&mut self, credentials: Credentials) -> usize {
        let task = PosixThreadBuilder::new(
            if self.tasks.is_empty() {
                self.process.pid()
            } else {
                allocate_posix_tid()
            },
            derive_thread_name("oom-adjustment-regression"),
            Box::new(UserContext::default()),
            credentials,
            self.vm.clone_handle(),
        )
        .process(Arc::downgrade(&self.process))
        .build()
        .unwrap();
        self.process.tasks().lock().insert(task.clone()).unwrap();
        self.tasks.push(task);
        self.tasks.len() - 1
    }

    fn writer(&self, index: usize) -> &PosixThread {
        self.tasks[index].as_posix_thread().unwrap()
    }

    fn fork(&self, flags: CloneFlags) -> Self {
        let vm = if flags.contains(CloneFlags::CLONE_VM) {
            self.vm.clone_handle()
        } else {
            Vmar::fork_from(&self.vm).unwrap()
        };
        let child = Self::build(
            vm,
            OomInit::Fork {
                parent: &self.process,
                flags,
            },
        );
        if flags.contains(CloneFlags::CLONE_VFORK) {
            child.process.status().set_vfork_child(true);
        }
        child
    }

    fn write(&self, value: i32, writer: &PosixThread) -> Result<()> {
        self.process.oom_score_adj().write_from(value, writer)
    }

    fn read(&self) -> i16 {
        self.process.oom_score_adj().read()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        test_util::mark_zombie(&self.process);
    }
}

fn user_credentials() -> Credentials {
    let credentials = Credentials::new_root();
    credentials.set_gid(Gid::new(60001)).unwrap();
    credentials.set_uid(Uid::new(60001)).unwrap();
    assert!(credentials.effective_capset().is_empty());
    credentials
}

#[ktest]
fn unprivileged_writer_returns_to_authorized_floor_but_cannot_cross_it() {
    let mut target = Fixture::new();
    let user = target.add_writer(user_credentials());
    target.write(500, target.writer(user)).unwrap();
    target.write(0, target.writer(user)).unwrap();
    assert_eq!(target.read(), 0);
    assert_eq!(
        target.write(-1, target.writer(user)).unwrap_err().error(),
        Errno::EACCES
    );
    assert_eq!(target.read(), 0);
}

#[ktest]
fn privileged_nonlegacy_write_replaces_the_floor_in_both_directions() {
    let mut target = Fixture::new();
    let root = target.add_writer(Credentials::new_root());
    let user = target.add_writer(user_credentials());
    target.write(200, target.writer(root)).unwrap();
    target.write(500, target.writer(user)).unwrap();
    target.write(200, target.writer(user)).unwrap();
    assert_eq!(
        target.write(199, target.writer(user)).unwrap_err().error(),
        Errno::EACCES
    );
    target.write(-100, target.writer(root)).unwrap();
    target.write(400, target.writer(user)).unwrap();
    target.write(-100, target.writer(user)).unwrap();
    assert_eq!(
        target.write(-101, target.writer(user)).unwrap_err().error(),
        Errno::EACCES
    );
    assert_eq!(target.read(), -100);
}

#[ktest]
fn range_denial_leaves_original_adjustment_and_authorized_floor() {
    let mut target = Fixture::new();
    let root = target.add_writer(Credentials::new_root());
    let user = target.add_writer(user_credentials());
    target.write(-100, target.writer(root)).unwrap();
    for value in [-1001, 1001, i32::MIN, i32::MAX] {
        assert_eq!(
            target
                .write(value, target.writer(root))
                .unwrap_err()
                .error(),
            Errno::EINVAL
        );
        assert_eq!(target.read(), -100);
    }
    assert_eq!(
        target.write(-101, target.writer(user)).unwrap_err().error(),
        Errno::EACCES
    );
}

#[ktest]
fn fork_inherits_the_authorized_floor_even_when_current_was_raised() {
    let mut parent = Fixture::new();
    let root = parent.add_writer(Credentials::new_root());
    let user = parent.add_writer(user_credentials());
    parent.write(-100, parent.writer(root)).unwrap();
    parent.write(500, parent.writer(user)).unwrap();
    let child = parent.fork(CloneFlags::empty());
    assert_eq!(child.read(), 500);
    child.write(-100, parent.writer(user)).unwrap();
    assert_eq!(
        child.write(-101, parent.writer(user)).unwrap_err().error(),
        Errno::EACCES
    );
    parent.write(200, parent.writer(root)).unwrap();
    child.write(0, parent.writer(user)).unwrap();
    assert_eq!(parent.read(), 200);
    assert_eq!(child.read(), 0);
}

#[ktest]
fn writers_in_one_process_share_the_pair_but_each_uses_its_own_authority() {
    let mut target = Fixture::new();
    let root = target.add_writer(Credentials::new_root());
    let user = target.add_writer(user_credentials());
    target.write(-1000, target.writer(root)).unwrap();
    target.write(100, target.writer(user)).unwrap();
    target.write(-1000, target.writer(user)).unwrap();
    target.write(250, target.writer(root)).unwrap();
    assert_eq!(
        target
            .write(-1000, target.writer(user))
            .unwrap_err()
            .error(),
        Errno::EACCES
    );
    assert_eq!(target.read(), 250);
}

#[ktest]
fn separate_clone_vm_processes_share_updates_but_vfork_stays_independent() {
    let mut parent = Fixture::new();
    let root = parent.add_writer(Credentials::new_root());
    let user = parent.add_writer(user_credentials());
    let peer = parent.fork(CloneFlags::CLONE_VM);
    let vfork = parent.fork(CloneFlags::CLONE_VM | CloneFlags::CLONE_VFORK);
    parent.write(200, parent.writer(root)).unwrap();
    assert_eq!(peer.read(), 200);
    assert_eq!(vfork.read(), 0);
    assert_eq!(
        peer.write(199, parent.writer(user)).unwrap_err().error(),
        Errno::EACCES
    );
    vfork.write(100, parent.writer(user)).unwrap();
    assert_eq!(parent.read(), 200);
    assert_eq!(peer.read(), 200);
    vfork.write(0, parent.writer(user)).unwrap();
}

#[ktest]
fn replacement_image_keeps_pair_but_detaches_from_original_vm_peers() {
    let mut parent = Fixture::new();
    let root = parent.add_writer(Credentials::new_root());
    let user = parent.add_writer(user_credentials());
    parent.write(-100, parent.writer(root)).unwrap();
    let peer = parent.fork(CloneFlags::CLONE_VM);
    let replacement = VmarHandle::new(ProcessVm::new(SockFs::new_path()));
    // Exercise exec's real process-VM publication primitive. The unscheduled
    // fixture does not claim to execute a userspace exec syscall.
    let old = peer
        .process
        .lock_vmar()
        .set_vmar(Some(replacement.clone_arc()));
    drop(old);
    parent.write(200, parent.writer(root)).unwrap();
    assert_eq!(peer.read(), -100);
    peer.write(-100, parent.writer(user)).unwrap();
    assert_eq!(
        peer.write(-101, parent.writer(user)).unwrap_err().error(),
        Errno::EACCES
    );
}

#[ktest]
fn exit_vm_unbinding_removes_membership_before_last_process_reference_drops() {
    let mut parent = Fixture::new();
    let root = parent.add_writer(Credentials::new_root());
    parent.write(200, parent.writer(root)).unwrap();
    let peer = parent.fork(CloneFlags::CLONE_VM);
    let old = peer.process.lock_vmar().set_vmar(None);
    drop(old);
    parent.write(300, parent.writer(root)).unwrap();
    assert_eq!(peer.read(), 200);
    assert_eq!(parent.read(), 300);
}

#[ktest]
fn clone_and_privileged_write_publish_one_of_two_complete_authority_cuts() {
    use core::sync::atomic::{AtomicBool, Ordering};

    use ostd::cpu::CpuId;

    use crate::thread::kernel_thread::ThreadOptions;

    let mut parent = Fixture::new();
    let root = parent.add_writer(Credentials::new_root());
    let user = parent.add_writer(user_credentials());
    parent.write(200, parent.writer(root)).unwrap();
    let parent = Arc::new(parent);
    let started = Arc::new([AtomicBool::new(false), AtomicBool::new(false)]);
    let finished = Arc::new([AtomicBool::new(false), AtomicBool::new(false)]);
    let child = Arc::new(Mutex::new(None));
    let transition = TRANSITIONS.lock();
    let workers = (0..2)
        .map(|index| {
            let parent = parent.clone();
            let started = started.clone();
            let finished = finished.clone();
            let child = child.clone();
            ThreadOptions::new(move || {
                started[index].store(true, Ordering::Release);
                if index == 0 {
                    parent.write(-100, parent.writer(root)).unwrap();
                } else {
                    *child.lock() = Some(parent.fork(CloneFlags::empty()));
                }
                finished[index].store(true, Ordering::Release);
            })
            .cpu_affinity(CpuId::current_racy().into())
            .spawn()
        })
        .collect::<Vec<_>>();
    for _ in 0..256 {
        Task::yield_now();
        if started.iter().all(|flag| flag.load(Ordering::Acquire)) {
            break;
        }
    }
    let both_started = started.iter().all(|flag| flag.load(Ordering::Acquire));
    let neither_completed = finished.iter().all(|flag| !flag.load(Ordering::Acquire));
    // This is the actual production transition barrier, not a test-only
    // permission override. Either waiter may win when the barrier opens.
    drop(transition);
    for worker in workers {
        worker.join();
    }
    assert!(both_started);
    assert!(neither_completed);
    assert!(finished.iter().all(|flag| flag.load(Ordering::Acquire)));
    let child = child.lock().take().unwrap();
    let cut = child.read();
    assert!(cut == 200 || cut == -100);
    child.write(i32::from(cut), parent.writer(user)).unwrap();
    assert_eq!(
        child
            .write(i32::from(cut) - 1, parent.writer(user))
            .unwrap_err()
            .error(),
        Errno::EACCES
    );
    assert_eq!(child.read(), cut);
}

#[ktest]
fn last_adjustment_owner_drops_without_waiting_for_the_transition_in_atomic_mode() {
    let fixture = Fixture::new();
    let adjustment = OomScoreAdj::new(
        allocate_posix_tid(),
        &fixture.vm.clone_arc(),
        OomInit::Initial(0),
    );
    let weak = Arc::downgrade(&adjustment.0);
    let transition = TRANSITIONS.lock();
    let irq = ostd::irq::disable_local();
    drop(adjustment);
    assert!(weak.upgrade().is_none());
    drop(irq);
    drop(transition);
}
