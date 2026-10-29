// SPDX-License-Identifier: MPL-2.0

use core::sync::atomic::{AtomicBool, Ordering};

use ostd::{cpu::CpuId, prelude::ktest, task::Task};

use super::*;
use crate::{
    fs::pseudofs::SockFs,
    process::{
        Process, ProcessVm,
        posix_thread::{AsPosixThread, PosixThread, alien_access::AlienAccessMode},
        test_util,
    },
    thread::kernel_thread::ThreadOptions,
    vm::vmar::{Vmar, VmarHandle},
};

struct Fixture {
    process: Arc<Process>,
    task: Arc<Task>,
}
impl Fixture {
    fn new() -> Self {
        let (process, task) = test_util::new_unstarted_process();
        Self { process, task }
    }
    fn in_vmar(vmar: VmarHandle) -> Self {
        let (process, task) = test_util::new_unstarted_process_in_vmar(vmar);
        Self { process, task }
    }
    fn thread(&self) -> &PosixThread {
        self.task.as_posix_thread().unwrap()
    }
    fn dumpable(&self) -> bool {
        *self
            .process
            .lock_vmar()
            .unwrap()
            .process_vm()
            .dumpable()
            .lock()
    }
    fn set_dumpable(&self, value: bool) {
        *self
            .process
            .lock_vmar()
            .unwrap()
            .process_vm()
            .dumpable()
            .lock() = value;
    }
    fn edit<R>(&self, f: impl FnOnce(&Credentials<ReadWriteOp>) -> R) -> R {
        let vmar = self.process.lock_vmar();
        let credentials = self.thread().credentials.dup().restrict();
        let transaction =
            CredentialsEdit::new(&credentials, vmar.unwrap().process_vm().dumpable().lock());
        f(&transaction)
    }
    fn become_user(&self) {
        self.edit(|credentials| {
            credentials.set_gid(Gid::new(60001)).unwrap();
            credentials.set_uid(Uid::new(60001)).unwrap();
        });
        assert!(self.thread().credentials().effective_capset().is_empty());
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        test_util::mark_zombie(&self.process);
    }
}

#[ktest]
fn dumpability_shares_original_vm_but_fork_and_new_image_are_independent() {
    crate::time::clocks::init_for_ktest();
    crate::util::random::init();
    let original = VmarHandle::new(ProcessVm::new(SockFs::new_path()));
    let first = Fixture::in_vmar(original.clone_handle());
    let second = Fixture::in_vmar(original.clone_handle());
    assert!(first.dumpable() && second.dumpable());
    first.set_dumpable(false);
    assert!(!second.dumpable());
    test_util::initialize_vmar_heap_for_fork(&original, 0x1000_0000);
    let fork = Vmar::fork_from(&original).unwrap();
    assert!(!*fork.process_vm().dumpable().lock());
    *fork.process_vm().dumpable().lock() = true;
    assert!(!first.dumpable() && !second.dumpable());
    second.set_dumpable(true);
    assert!(first.dumpable());
    first.set_dumpable(false);
    let replacement = ProcessVm::new(SockFs::new_path());
    assert!(*replacement.dumpable().lock());
    assert!(!first.dumpable());
}

#[ktest]
fn credential_transaction_preserves_dumpability_on_noop_query_and_denial() {
    let target = Fixture::new();
    target.become_user();
    target.set_dumpable(true);
    target.edit(|credentials| {
        assert_eq!(credentials.set_fsuid(None).unwrap(), Uid::new(60001));
        assert_eq!(credentials.set_fsgid(None).unwrap(), Gid::new(60001));
        credentials.set_uid(Uid::new(60001)).unwrap();
        credentials.set_gid(Gid::new(60001)).unwrap();
        credentials.set_resuid(None, None, None).unwrap();
        credentials.set_resgid(None, None, None).unwrap();
        assert_eq!(
            credentials.set_uid(Uid::new(60002)).unwrap_err().error(),
            Errno::EPERM
        );
        assert_eq!(
            credentials.set_gid(Gid::new(60002)).unwrap_err().error(),
            Errno::EPERM
        );
        assert!(credentials.set_fsuid(Some(Uid::new(60002))).is_err());
        assert!(credentials.set_fsgid(Some(Gid::new(60002))).is_err());
    });
    assert!(target.dumpable());
    target.set_dumpable(false);
    target.edit(|credentials| credentials.set_no_new_privs());
    assert!(!target.dumpable());
}

#[ktest]
fn credential_transaction_resets_each_effective_and_filesystem_id_change() {
    for kind in 0..4 {
        let target = Fixture::new();
        target.set_dumpable(true);
        target.edit(|credentials| match kind {
            0 => credentials
                .set_resuid(None, Some(Uid::new(60001)), None)
                .unwrap(),
            1 => credentials
                .set_resgid(None, Some(Gid::new(60001)), None)
                .unwrap(),
            2 => {
                credentials.set_fsuid(Some(Uid::new(60001))).unwrap();
            }
            3 => {
                credentials.set_fsgid(Some(Gid::new(60001))).unwrap();
            }
            _ => unreachable!(),
        });
        assert!(!target.dumpable());
    }
}

#[ktest]
fn credential_transaction_preserves_capability_drop_and_resets_permitted_gain() {
    let target = Fixture::new();
    let old = target.thread().credentials().permitted_capset();
    let reduced = old - CapSet::SYS_ADMIN;
    target.edit(|credentials| {
        credentials.set_effective_capset(reduced);
        credentials.set_permitted_capset(reduced);
    });
    assert!(target.dumpable());
    // Exercise the same original owner used by prepared exec, without claiming
    // that the capset syscall lets an unprivileged caller add permissions.
    target.edit(|credentials| credentials.set_permitted_capset(old));
    assert!(!target.dumpable());
}

#[ktest]
fn alien_capture_respects_dumpability_same_group_and_original_capability() {
    let target = Fixture::new();
    let caller = Fixture::new();
    let root = Fixture::new();
    target.become_user();
    caller.become_user();
    target.set_dumpable(true);
    let vmar = target.process.lock_vmar();
    let access = target
        .thread()
        .check_alien_access_from(caller.thread(), AlienAccessMode::READ_WITH_FS_CREDS, &vmar)
        .unwrap();
    assert!(vmar.unwrap().process_vm().dumpable().try_lock().is_none());
    drop(access);
    *vmar.unwrap().process_vm().dumpable().lock() = false;
    assert_eq!(
        target
            .thread()
            .check_alien_access_from(caller.thread(), AlienAccessMode::READ_WITH_FS_CREDS, &vmar,)
            .err()
            .unwrap()
            .error(),
        Errno::EPERM
    );
    drop(
        target
            .thread()
            .check_alien_access_from(
                target.thread(),
                AlienAccessMode::ATTACH_WITH_REAL_CREDS,
                &vmar,
            )
            .unwrap(),
    );
    drop(
        target
            .thread()
            .check_alien_access_from(root.thread(), AlienAccessMode::READ_WITH_FS_CREDS, &vmar)
            .unwrap(),
    );
    drop(vmar);
}

#[ktest]
fn shared_vm_credential_writer_waits_for_real_alien_capture() {
    crate::time::clocks::init_for_ktest();
    crate::util::random::init();
    let original = VmarHandle::new(ProcessVm::new(SockFs::new_path()));
    let target = Fixture::in_vmar(original.clone_handle());
    let peer = Fixture::in_vmar(original);
    let caller = Fixture::new();
    target.become_user();
    caller.become_user();
    target.set_dumpable(true);
    let vmar = target.process.lock_vmar();
    let access = target
        .thread()
        .check_alien_access_from(caller.thread(), AlienAccessMode::READ_WITH_FS_CREDS, &vmar)
        .unwrap();
    let started = Arc::new(AtomicBool::new(false));
    let finished = Arc::new(AtomicBool::new(false));
    let started_worker = started.clone();
    let finished_worker = finished.clone();
    let worker = ThreadOptions::new(move || {
        started_worker.store(true, Ordering::Release);
        peer.edit(|credentials| {
            credentials.set_fsuid(Some(Uid::new(60002))).unwrap();
        });
        finished_worker.store(true, Ordering::Release);
    })
    .cpu_affinity(CpuId::current_racy().into())
    .spawn();
    for _ in 0..128 {
        Task::yield_now();
        if started.load(Ordering::Acquire) {
            break;
        }
    }
    assert!(started.load(Ordering::Acquire));
    assert!(!finished.load(Ordering::Acquire));
    drop(access);
    for _ in 0..256 {
        Task::yield_now();
        if worker.is_exited() {
            break;
        }
    }
    assert!(finished.load(Ordering::Acquire));
    assert!(worker.is_exited());
    assert!(!*vmar.unwrap().process_vm().dumpable().lock());
    drop(vmar);
}

#[ktest]
fn alien_capture_commoncap_selects_effective_or_permitted_under_original_image_guard() {
    let target = Fixture::new();
    let caller = Fixture::new();
    target.become_user();
    caller.become_user();
    target.edit(|credentials| credentials.set_permitted_capset(CapSet::CHOWN));
    target.set_dumpable(true);
    for mode in [
        AlienAccessMode::READ_WITH_FS_CREDS,
        AlienAccessMode::READ_WITH_REAL_CREDS,
    ] {
        let vmar = target.process.lock_vmar();
        assert_eq!(
            target
                .thread()
                .check_alien_access_from(caller.thread(), mode, &vmar)
                .err()
                .unwrap()
                .error(),
            Errno::EPERM
        );
    }
    caller.edit(|credentials| credentials.set_permitted_capset(CapSet::CHOWN));
    let vmar = target.process.lock_vmar();
    let access = target
        .thread()
        .check_alien_access_from(
            caller.thread(),
            AlienAccessMode::READ_WITH_REAL_CREDS,
            &vmar,
        )
        .unwrap();
    assert!(vmar.unwrap().process_vm().dumpable().try_lock().is_none());
    drop(access);
    assert_eq!(
        target
            .thread()
            .check_alien_access_from(caller.thread(), AlienAccessMode::READ_WITH_FS_CREDS, &vmar)
            .err()
            .unwrap()
            .error(),
        Errno::EPERM
    );
    caller.edit(|credentials| credentials.set_effective_capset(CapSet::CHOWN));
    drop(
        target
            .thread()
            .check_alien_access_from(caller.thread(), AlienAccessMode::READ_WITH_FS_CREDS, &vmar)
            .unwrap(),
    );
    drop(vmar);
    target.edit(|credentials| credentials.set_permitted_capset(CapSet::empty()));
    caller.edit(|credentials| {
        credentials.set_effective_capset(CapSet::empty());
        credentials.set_permitted_capset(CapSet::empty());
    });
    let vmar = target.process.lock_vmar();
    drop(
        target
            .thread()
            .check_alien_access_from(caller.thread(), AlienAccessMode::READ_WITH_FS_CREDS, &vmar)
            .unwrap(),
    );
}

#[ktest]
fn commoncap_consent_preserves_distinct_identity_policy_and_real_ptrace_exception() {
    let target = Fixture::new();
    let caller = Fixture::new();
    target.edit(|credentials| {
        credentials.set_gid(Gid::new(60002)).unwrap();
        credentials.set_uid(Uid::new(60002)).unwrap();
        credentials.set_permitted_capset(CapSet::CHOWN);
    });
    caller.become_user();
    caller.edit(|credentials| credentials.set_permitted_capset(CapSet::CHOWN));
    target.set_dumpable(true);
    let vmar = target.process.lock_vmar();
    // A capability superset alone cannot bypass the ordinary UID/GID condition.
    assert_eq!(
        target
            .thread()
            .check_alien_access_from(
                caller.thread(),
                AlienAccessMode::READ_WITH_REAL_CREDS,
                &vmar
            )
            .err()
            .unwrap()
            .error(),
        Errno::EPERM
    );
    drop(vmar);
    target.set_dumpable(false);
    // Consent uses the parent's permitted set, without ordinary UID/dump gates.
    assert!(
        !target
            .thread()
            .check_traceme_access_from(caller.thread())
            .unwrap()
    );
    caller.edit(|credentials| credentials.set_permitted_capset(CapSet::empty()));
    assert_eq!(
        target
            .thread()
            .check_traceme_access_from(caller.thread())
            .unwrap_err()
            .error(),
        Errno::EPERM
    );
    caller.edit(|credentials| {
        credentials.set_permitted_capset(CapSet::SYS_PTRACE);
        credentials.set_effective_capset(CapSet::SYS_PTRACE);
    });
    assert!(
        target
            .thread()
            .check_traceme_access_from(caller.thread())
            .unwrap()
    );
    let vmar = target.process.lock_vmar();
    drop(
        target
            .thread()
            .check_alien_access_from(caller.thread(), AlienAccessMode::READ_WITH_FS_CREDS, &vmar)
            .unwrap(),
    );
}

#[ktest]
fn traceme_parent_capability_snapshot_waits_for_original_credential_publication() {
    let parent = Arc::new(Fixture::new());
    let child = Fixture::new();
    parent.become_user();
    child.become_user();
    parent.edit(|credentials| credentials.set_permitted_capset(CapSet::CHOWN));
    child.edit(|credentials| credentials.set_permitted_capset(CapSet::CHOWN));
    let vmar = parent.process.lock_vmar();
    let image = vmar.unwrap().process_vm().dumpable().lock();
    let started = Arc::new(AtomicBool::new(false));
    let finished = Arc::new(AtomicBool::new(false));
    let started_worker = started.clone();
    let finished_worker = finished.clone();
    let parent_worker = parent.clone();
    let worker = ThreadOptions::new(move || {
        started_worker.store(true, Ordering::Release);
        assert_eq!(
            child
                .thread()
                .check_traceme_access_from(parent_worker.thread())
                .unwrap_err()
                .error(),
            Errno::EPERM
        );
        finished_worker.store(true, Ordering::Release);
    })
    .cpu_affinity(CpuId::current_racy().into())
    .spawn();
    for _ in 0..128 {
        Task::yield_now();
        if started.load(Ordering::Acquire) {
            break;
        }
    }
    assert!(started.load(Ordering::Acquire));
    assert!(!finished.load(Ordering::Acquire));
    // Finish the real credential transaction before the waiting check can read it.
    let credentials = parent.thread().credentials.dup().restrict();
    let transaction = CredentialsEdit::new(&credentials, image);
    transaction.set_permitted_capset(CapSet::empty());
    drop(transaction);
    drop(vmar);
    for _ in 0..256 {
        Task::yield_now();
        if worker.is_exited() {
            break;
        }
    }
    assert!(finished.load(Ordering::Acquire));
    assert!(worker.is_exited());
}
