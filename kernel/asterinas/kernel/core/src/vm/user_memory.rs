// SPDX-License-Identifier: MPL-2.0

//! Physical user-data and selected IPC-buffer frame admission for the fixed G1-d workload family.
//!
//! A charge belongs to physical frame metadata, never to a mapping or a frame
//! handle. Fork and shared mappings retain one charge; COW charges its new
//! frame; the final physical-frame reference refunds it. This deliberately is
//! not a cgroup memory controller: page tables, slabs, ancillary/datagram buffers and device MMIO
//! are outside this account, and there is no reclaim, OOM killer or reserve.

use core::sync::atomic::{AtomicUsize, Ordering};

use ostd::{
    impl_untyped_frame_meta_for,
    mm::{Frame, FrameAllocOptions, Segment, UFrame},
};

use crate::{prelude::*, process::Process, thread::kernel_thread};

pub(crate) type UserMemoryOwner = Option<Arc<UserMemoryAccount>>;

/// One immutable admission limit shared by a workload and all its descendants.
#[derive(Debug)]
pub(crate) struct UserMemoryAccount {
    limit_pages: usize,
    current_pages: AtomicUsize,
    denied: AtomicUsize,
}

impl UserMemoryAccount {
    #[cfg_attr(not(any(ktest, feature = "g1d-trusted-control")), expect(dead_code))]
    pub(crate) fn new(limit_pages: usize) -> Arc<Self> {
        Arc::new(Self {
            limit_pages,
            current_pages: AtomicUsize::new(0),
            denied: AtomicUsize::new(0),
        })
    }

    pub(crate) fn limit_pages(&self) -> usize {
        self.limit_pages
    }

    pub(crate) fn current_pages(&self) -> usize {
        self.current_pages.load(Ordering::Acquire)
    }

    // All reservation operations are bounded, non-sleeping atomic operations.
    // No logging, allocation, process lock or cgroup lock is allowed here.
    fn reserve(&self, pages: usize) -> Result<()> {
        self.current_pages
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |current| {
                current
                    .checked_add(pages)
                    .filter(|next| *next <= self.limit_pages)
            })
            .map(|_| ())
            .map_err(|_| Error::user_frame_limit())
    }

    fn refund(&self, pages: usize) {
        let previous = self.current_pages.fetch_sub(pages, Ordering::AcqRel);
        debug_assert!(previous >= pages);
    }

    /// Limits diagnostics after returning from all VM/allocator locks.
    pub(crate) fn report_denial(&self) -> bool {
        self.denied.fetch_add(1, Ordering::Relaxed) < 16
    }
}

/// A precharge for an allocation which has not yet produced all its frames.
pub(crate) struct UserMemoryReservation {
    owner: UserMemoryOwner,
    remaining: usize,
}

impl UserMemoryReservation {
    pub(crate) fn new(owner: &UserMemoryOwner, pages: usize) -> Result<Self> {
        if let Some(account) = owner {
            account.reserve(pages)?;
        }
        Ok(Self {
            owner: owner.clone(),
            remaining: pages,
        })
    }

    pub(crate) fn take_page(&mut self) -> Option<UserPageCharge> {
        assert!(self.remaining > 0);
        self.remaining -= 1;
        self.owner
            .as_ref()
            .map(|owner| UserPageCharge(owner.clone()))
    }
}

impl Drop for UserMemoryReservation {
    fn drop(&mut self) {
        if let Some(owner) = &self.owner {
            owner.refund(self.remaining);
        }
    }
}

/// Linear token stored in frame metadata; intentionally not Clone.
#[derive(Debug)]
pub(crate) struct UserPageCharge(Arc<UserMemoryAccount>);

impl Drop for UserPageCharge {
    fn drop(&mut self) {
        self.0.refund(1);
    }
}

#[derive(Debug)]
pub(crate) struct UserPageMeta {
    _charge: Option<UserPageCharge>,
}

impl_untyped_frame_meta_for!(UserPageMeta);

pub(crate) fn alloc_user_frame(
    owner: &UserMemoryOwner,
    zeroed: bool,
) -> Result<Frame<UserPageMeta>> {
    let mut reservation = UserMemoryReservation::new(owner, 1)?;
    let metadata = UserPageMeta {
        _charge: reservation.take_page(),
    };
    Ok(FrameAllocOptions::new()
        .zeroed(zeroed)
        .alloc_frame_with(metadata)?)
}

/// Allocates the original contiguous IPC backing pages against their initiator.
///
/// Admission precedes physical allocation. Each charge moves exactly once into
/// original frame metadata, so partial failure and the last physical reference
/// use the same refund path as user RAM. No reserve authority is implied.
pub(crate) fn alloc_user_segment(
    owner: &UserMemoryOwner,
    count: usize,
) -> Result<Segment<UserPageMeta>> {
    let bytes = count
        .checked_mul(PAGE_SIZE)
        .ok_or_else(|| Error::new(Errno::EINVAL))?;
    if count == 0 || core::alloc::Layout::from_size_align(bytes, PAGE_SIZE).is_err() {
        return Err(Error::new(Errno::EINVAL));
    }
    let mut reservation = UserMemoryReservation::new(owner, count)?;
    Ok(FrameAllocOptions::new()
        .zeroed(false)
        .alloc_segment_with(count, |_| UserPageMeta {
            _charge: reservation.take_page(),
        })?)
}

/// Allocates zeroed user-visible device RAM against the caller's family.
///
/// The complete frame count is admitted before allocating the handle vector or
/// any physical frame. A partial allocator failure refunds all frames/tokens.
pub fn allocate_user_frames(count: usize) -> Result<Vec<UFrame>> {
    let mut reservation = UserMemoryReservation::new(&current_owner(), count)?;
    let mut pages = Vec::new();
    pages
        .try_reserve_exact(count)
        .map_err(|_| Error::new(Errno::ENOMEM))?;
    for _ in 0..count {
        let metadata = UserPageMeta {
            _charge: reservation.take_page(),
        };
        pages.push(FrameAllocOptions::new().alloc_frame_with(metadata)?.into());
    }
    Ok(pages)
}

/// Allocation outside a VM fault (e.g. buffered file I/O) uses its initiator.
/// The owner is immutable and reading it does not lock the process VMAR.
pub(crate) fn current_owner() -> UserMemoryOwner {
    if let Some(process) = Process::current() {
        return process.user_memory_owner().clone();
    }
    kernel_thread::current_user_memory_owner()
}

/// Runs a regression with the production immutable VMAR owner lookup.
/// No global override or alternate charge path is installed. The completion
/// flag prevents the kernel thread's panic catcher from turning a failed
/// assertion into a passing parent test.
#[cfg(ktest)]
pub(crate) fn test_with_current_owner<F>(owner: UserMemoryOwner, test: F)
where
    F: FnOnce() + Send + 'static,
{
    use core::sync::atomic::AtomicBool;

    use crate::{
        fs::pseudofs::SockFs, process::ProcessVm, thread::kernel_thread::ThreadOptions,
        vm::vmar::VmarHandle,
    };
    crate::time::clocks::init_for_ktest();
    crate::util::random::init();
    let vmar = VmarHandle::new_with_owner(ProcessVm::new(SockFs::new_path()), owner);
    let completed = Arc::new(AtomicBool::new(false));
    let worker_completed = completed.clone();
    let worker = ThreadOptions::new(move || {
        test();
        worker_completed.store(true, Ordering::Release);
    })
    .vmar(vmar.clone_arc())
    .spawn();
    worker.join();
    assert!(
        completed.load(Ordering::Acquire),
        "IPC owner regression panicked before completing"
    );
    drop(worker);
    drop(vmar);
}

#[cfg(ktest)]
mod tests {
    use ostd::prelude::*;

    use super::*;

    #[ktest]
    fn exact_limit_and_unconsumed_reservation_refund() {
        let account = UserMemoryAccount::new(2);
        let owner = Some(account.clone());
        let mut reservation = UserMemoryReservation::new(&owner, 2).unwrap();
        assert_eq!(account.current_pages(), 2);
        assert!(
            UserMemoryReservation::new(&owner, 1)
                .err()
                .unwrap()
                .is_user_frame_limit()
        );
        let first = reservation.take_page();
        drop(reservation);
        assert_eq!(account.current_pages(), 1);
        drop(first);
        assert_eq!(account.current_pages(), 0);
        assert!(UserMemoryReservation::new(&owner, usize::MAX).is_err());
        assert_eq!(account.current_pages(), 0);
    }

    #[ktest]
    fn shared_frame_charges_once_until_last_reference() {
        let account = UserMemoryAccount::new(1);
        let owner = Some(account.clone());
        let page = alloc_user_frame(&owner, true).unwrap();
        let shared: UFrame = page.clone().into();
        assert_eq!(account.current_pages(), 1);
        drop(page);
        assert_eq!(account.current_pages(), 1);
        assert!(
            alloc_user_frame(&owner, true)
                .err()
                .unwrap()
                .is_user_frame_limit()
        );
        drop(shared);
        assert_eq!(account.current_pages(), 0);
        drop(alloc_user_frame(&owner, true).unwrap());
        assert_eq!(account.current_pages(), 0);
    }

    #[ktest]
    fn independent_owners_do_not_consume_each_others_allowance() {
        let first = UserMemoryAccount::new(1);
        let second = UserMemoryAccount::new(1);
        let page = alloc_user_frame(&Some(first.clone()), true).unwrap();
        let other = alloc_user_frame(&Some(second.clone()), true).unwrap();
        assert_eq!(first.current_pages(), 1);
        assert_eq!(second.current_pages(), 1);
        drop(page);
        assert_eq!(first.current_pages(), 0);
        assert_eq!(second.current_pages(), 1);
        drop(other);
        assert_eq!(second.current_pages(), 0);
    }
}
