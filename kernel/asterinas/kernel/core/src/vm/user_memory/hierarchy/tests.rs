// SPDX-License-Identifier: MPL-2.0

use core::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

use ostd::{cpu::CpuId, prelude::ktest, sync::RcuDrop, task::Task};

use super::*;
use crate::{
    thread::kernel_thread::ThreadOptions,
    vm::{
        page_cache::{VmoMapMode, VmoOptions},
        user_memory::{
            UserMemoryAccount, UserMemoryReservation, alloc_user_frame, alloc_user_segment,
            test_with_current_owner,
        },
    },
};

#[ktest]
fn hierarchical_frame_admission_refunds_family_and_every_ancestor_once() {
    let parent = test_leaf(2);
    parent.set_delegated(true);
    let leaf = MemoryDomain::child(parent.clone()).unwrap();
    assert!(leaf.set_max(Some(3)));
    let owner = UserMemoryAccount::new(3);
    owner.move_to(
        leaf.clone(),
        &crate::fs::cgroupfs::CgroupMembership::write_lock(),
    );
    let frame = alloc_user_frame(&Some(owner.clone()), true).unwrap();
    let alias = frame.clone();
    let reservation = UserMemoryReservation::new(&Some(owner.clone()), 1).unwrap();
    assert!(
        alloc_user_frame(&Some(owner.clone()), true)
            .unwrap_err()
            .is_cgroup_frame_limit()
    );
    assert_eq!(owner.current_pages(), 2);
    assert_eq!(leaf.snapshot().pages, 2);
    assert_eq!(parent.snapshot().pages, 2);
    assert_eq!(parent.snapshot().max_events, 1);
    assert_eq!(leaf.snapshot().max_events, 0);
    drop(reservation);
    drop(frame);
    assert_eq!(leaf.snapshot().pages, 1);
    drop(alias);
    assert_eq!(leaf.snapshot().pages, 0);
    assert_eq!(parent.snapshot().pages, 0);
    assert_eq!(owner.current_pages(), 0);

    // Independent family limit still wins even with available cgroup quota.
    let family = UserMemoryAccount::new(0);
    family.move_to(
        leaf.clone(),
        &crate::fs::cgroupfs::CgroupMembership::write_lock(),
    );
    let family_error = alloc_user_frame(&Some(family), true).unwrap_err();
    assert!(family_error.is_user_frame_limit());
    assert!(!family_error.is_cgroup_frame_limit());
    assert_eq!(leaf.snapshot().pages, 0);
}

#[ktest]
fn disabled_domains_keep_live_charges_and_deleted_identity_cannot_escape() {
    let parent = test_leaf(8);
    parent.set_delegated(true);
    let leaf = MemoryDomain::child(parent.clone()).unwrap();
    assert!(leaf.set_max(Some(1)));
    let owner = UserMemoryAccount::new(8);
    owner.move_to(
        leaf.clone(),
        &crate::fs::cgroupfs::CgroupMembership::write_lock(),
    );
    let first = alloc_user_frame(&Some(owner.clone()), true).unwrap();
    assert!(!leaf.set_max(Some(0)));
    assert_eq!(leaf.snapshot().max_pages, Some(1));
    parent.set_delegated(false);
    let second = alloc_user_frame(&Some(owner.clone()), true).unwrap();
    assert_eq!(leaf.snapshot().pages, 2);
    parent.set_delegated(true);
    assert!(alloc_user_frame(&Some(owner.clone()), true).is_err());
    assert_eq!(leaf.snapshot().pages, 2);
    leaf.close();
    assert!(!owner.can_move_to(&leaf, &crate::fs::cgroupfs::CgroupMembership::write_lock()));
    assert!(alloc_user_frame(&Some(owner.clone()), true).is_err());
    let replacement = MemoryDomain::child(parent.clone()).unwrap();
    owner.move_to(
        replacement.clone(),
        &crate::fs::cgroupfs::CgroupMembership::write_lock(),
    );
    let new_frame = alloc_user_frame(&Some(owner.clone()), true).unwrap();
    assert_eq!(replacement.snapshot().pages, 1);
    assert_eq!(parent.snapshot().pages, 3);
    drop((first, second));
    assert_eq!(leaf.snapshot().pages, 0);
    assert_eq!(replacement.snapshot().pages, 1);
    assert_eq!(parent.snapshot().pages, 1);
    drop(new_frame);
    assert_eq!(parent.snapshot().pages, 0);
}

#[ktest]
fn physical_allocator_error_rolls_back_complete_hierarchical_precharge() {
    let pages = 1usize << 32; // Actual allocator max order is smaller than 16 TiB.
    let parent = test_leaf(pages);
    parent.set_delegated(true);
    let leaf = MemoryDomain::child(parent.clone()).unwrap();
    let owner = UserMemoryAccount::new(pages);
    owner.move_to(
        leaf.clone(),
        &crate::fs::cgroupfs::CgroupMembership::write_lock(),
    );
    let error = alloc_user_segment(&Some(owner.clone()), pages).unwrap_err();
    assert_eq!(error.error(), Errno::ENOMEM);
    assert!(!error.is_user_frame_limit());
    assert_eq!(owner.current_pages(), 0);
    assert_eq!(leaf.snapshot().pages, 0);
    assert_eq!(parent.snapshot().pages, 0);
    drop(alloc_user_segment(&Some(owner.clone()), 2).unwrap());
    assert_eq!(owner.current_pages(), 0);
    assert_eq!(parent.snapshot().pages, 0);
}

#[ktest]
fn concurrent_sibling_allocators_cannot_both_cross_ancestor_limit() {
    let parent = test_leaf(1);
    parent.set_delegated(true);
    let started = Arc::new(AtomicUsize::new(0));
    let start_gate = Arc::new(ostd::sync::WaitQueue::new());
    let ready = Arc::new(AtomicBool::new(false));
    let attempted = Arc::new(AtomicUsize::new(0));
    let successes = Arc::new(AtomicUsize::new(0));
    let completed = Arc::new(AtomicUsize::new(0));
    let mut workers = Vec::new();
    for _ in 0..2 {
        let leaf = MemoryDomain::child(parent.clone()).unwrap();
        let owner = UserMemoryAccount::new(1);
        owner.move_to(leaf, &crate::fs::cgroupfs::CgroupMembership::write_lock());
        let (started, attempted, successes, completed) = (
            started.clone(),
            attempted.clone(),
            successes.clone(),
            completed.clone(),
        );
        let start_gate = start_gate.clone();
        let ready = ready.clone();
        workers.push(
            ThreadOptions::new(move || {
                start_gate.wait_until(|| ready.load(Ordering::Acquire).then_some(()));
                started.fetch_add(1, Ordering::Release);
                for _ in 0..128 {
                    if started.load(Ordering::Acquire) == 2 {
                        break;
                    }
                    Task::yield_now();
                }
                assert_eq!(started.load(Ordering::Acquire), 2);
                let held = alloc_user_frame(&Some(owner.clone()), true);
                if held.is_ok() {
                    successes.fetch_add(1, Ordering::Relaxed);
                }
                attempted.fetch_add(1, Ordering::Release);
                for _ in 0..128 {
                    if attempted.load(Ordering::Acquire) == 2 {
                        break;
                    }
                    Task::yield_now();
                }
                assert_eq!(attempted.load(Ordering::Acquire), 2);
                drop(held);
                assert_eq!(owner.current_pages(), 0);
                completed.fetch_add(1, Ordering::Release);
            })
            .spawn(),
        );
    }
    ready.store(true, Ordering::Release);
    start_gate.wake_all();
    for worker in workers {
        worker.join();
    }
    assert_eq!(
        completed.load(Ordering::Acquire),
        2,
        "worker panic must not pass its parent"
    );
    assert_eq!(successes.load(Ordering::Relaxed), 1);
    assert_eq!(parent.snapshot().pages, 0);
    assert_eq!(parent.snapshot().max_events, 1);
}

struct Grace(Arc<AtomicBool>);
impl Drop for Grace {
    fn drop(&mut self) {
        self.0.store(true, Ordering::Release);
    }
}
pub(super) fn grace() {
    let done = Arc::new(AtomicBool::new(false));
    drop(RcuDrop::new(Grace(done.clone())));
    let worker = ThreadOptions::new(|| {})
        .cpu_affinity(CpuId::current_racy().into())
        .spawn();
    for _ in 0..128 {
        Task::yield_now();
        if done.load(Ordering::Acquire) && worker.is_exited() {
            break;
        }
    }
    assert!(done.load(Ordering::Acquire));
    assert!(worker.is_exited());
}

#[ktest]
fn explicit_vmar_fault_owner_overrides_loader_fallback_without_recharging_shared_pages() {
    let original = test_leaf(1);
    let migrated = test_leaf(1);
    let parent = UserMemoryAccount::new(3);
    parent.move_to(
        original.clone(),
        &crate::fs::cgroupfs::CgroupMembership::write_lock(),
    );
    let child = parent.fork_binding();
    child.move_to(
        migrated.clone(),
        &crate::fs::cgroupfs::CgroupMembership::write_lock(),
    );
    let vmo = VmoOptions::new(3 * PAGE_SIZE)
        .memory_owner(Some(parent.clone()))
        .alloc()
        .unwrap();
    // Loader write remains destination-owned even with no current Process.
    vmo.write(0, &mut VmReader::from(&[7u8][..]).to_fallible())
        .unwrap();
    assert_eq!(original.snapshot().pages, 1);
    vmo.commit_on_for_owner(0, VmoMapMode::Private, &Some(child.clone()))
        .unwrap();
    assert_eq!(migrated.snapshot().pages, 0); // Existing physical page is shared.
    vmo.commit_on_for_owner(1, VmoMapMode::Private, &Some(child.clone()))
        .unwrap();
    assert_eq!(migrated.snapshot().pages, 1);
    assert_eq!(parent.current_pages(), 2);
    assert_eq!(child.current_pages(), 2); // Same original family budget.
    assert!(
        vmo.commit_on_for_owner(2, VmoMapMode::Private, &Some(child))
            .is_err()
    );
    drop(vmo);
    grace();
    assert_eq!(parent.current_pages(), 0);
    assert_eq!(original.snapshot().pages, 0);
    assert_eq!(migrated.snapshot().pages, 0);
}

#[ktest]
fn unix_stream_and_seqpacket_partial_buffer_admission_refund_ancestor() {
    use crate::{net::socket::unix::UnixStreamSocket, util::net::SockType};
    let leaf = test_leaf(31); // Each direction is 16 actual pages.
    let owner = UserMemoryAccount::new(usize::MAX);
    owner.move_to(
        leaf.clone(),
        &crate::fs::cgroupfs::CgroupMembership::write_lock(),
    );
    let observed = leaf.clone();
    let account = owner.clone();
    test_with_current_owner(Some(owner), move || {
        for kind in [SockType::SOCK_STREAM, SockType::SOCK_SEQPACKET] {
            assert!(
                UnixStreamSocket::new_pair(true, kind)
                    .err()
                    .unwrap()
                    .is_user_frame_limit()
            );
            assert_eq!(account.current_pages(), 0);
            assert_eq!(observed.snapshot().pages, 0);
        }
    });
    assert_eq!(leaf.snapshot().pages, 0);
    assert_eq!(leaf.snapshot().max_events, 2);
}
