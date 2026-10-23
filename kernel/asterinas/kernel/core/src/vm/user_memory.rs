// SPDX-License-Identifier: MPL-2.0

//! Physical user-data and selected IPC frame admission for families and cgroups.
//!
//! A charge belongs to physical frame metadata, never to a mapping or a frame
//! handle. Fork and shared mappings retain one charge; COW charges its new
//! frame; the final physical-frame reference refunds it. This deliberately is
//! a selected-frame cgroup controller: page tables, slabs, ancillary/datagram buffers
//! and device MMIO are outside this account; there is no reclaim, OOM killer or reserve.

use core::sync::atomic::{AtomicUsize, Ordering};

use ostd::{
    impl_untyped_frame_meta_for,
    mm::{Frame, FrameAllocOptions, Segment, UFrame},
};

use crate::{prelude::*, process::Process, thread::kernel_thread};

pub(crate) type UserMemoryOwner = Option<Arc<UserMemoryAccount>>;

pub(crate) mod hierarchy;
use hierarchy::{MemoryDomain, transaction};

/// The fixed workload-family limit is independent of cgroup migration. Fork
/// retains this budget, but gets a distinct binding for future allocations.
#[derive(Debug)]
struct FamilyBudget {
    limit_pages: usize,
    current_pages: AtomicUsize,
    denied: AtomicUsize,
}

#[derive(Debug)]
pub(crate) struct UserMemoryAccount {
    family: Arc<FamilyBudget>,
    domain: SpinLock<Arc<MemoryDomain>>,
    processes: AtomicUsize,
}

impl UserMemoryAccount {
    pub(crate) fn new(limit_pages: usize) -> Arc<Self> {
        Arc::new(Self {
            family: Arc::new(FamilyBudget {
                limit_pages,
                current_pages: AtomicUsize::new(0),
                denied: AtomicUsize::new(0),
            }),
            domain: SpinLock::new(MemoryDomain::root()),
            processes: AtomicUsize::new(0),
        })
    }

    pub(crate) fn fork_binding(&self) -> Arc<Self> {
        let domain = {
            let _tx = transaction();
            self.domain.lock().clone()
        };
        Arc::new(Self {
            family: self.family.clone(),
            domain: SpinLock::new(domain),
            processes: AtomicUsize::new(0),
        })
    }

    pub(crate) fn limit_pages(&self) -> usize {
        self.family.limit_pages
    }
    pub(crate) fn current_pages(&self) -> usize {
        self.family.current_pages.load(Ordering::Acquire)
    }
    pub(crate) fn report_denial(&self) -> bool {
        self.family.denied.fetch_add(1, Ordering::Relaxed) < 16
    }

    /// The membership writer excludes new Process leases and competing moves.
    /// Separate CLONE_VM processes cannot be migrated independently yet.
    pub(crate) fn can_move_to(
        &self,
        target: &Arc<MemoryDomain>,
        _membership: &crate::fs::cgroupfs::CgroupMembership,
    ) -> bool {
        let tx = transaction();
        !target.is_closed(&tx)
            && (Arc::ptr_eq(&self.domain.lock(), target)
                || self.processes.load(Ordering::Relaxed) <= 1)
    }

    /// Only after target-node validation, while holding membership. Existing
    /// frames retain their captured domain; no page is transferred or recharged.
    pub(crate) fn move_to(
        &self,
        target: Arc<MemoryDomain>,
        _membership: &crate::fs::cgroupfs::CgroupMembership,
    ) {
        let old = {
            let tx = transaction();
            let mut domain = self.domain.lock();
            assert!(!target.is_closed(&tx));
            assert!(Arc::ptr_eq(&domain, &target) || self.processes.load(Ordering::Relaxed) <= 1);
            core::mem::replace(&mut *domain, target)
        };
        // Destruction of the last old domain/ancestor Arc can free heap memory.
        // It must happen after leaving the IRQ-disabled transaction.
        drop(old);
    }
}

/// One lease per Process, rather than per thread or VmarHandle. Fork/clone holds
/// original membership before constructing this lease; migration holds writer.
#[derive(Debug)]
pub(crate) struct ProcessMemoryOwner(UserMemoryOwner);
impl ProcessMemoryOwner {
    pub(crate) fn new(owner: UserMemoryOwner) -> Self {
        if let Some(owner) = &owner {
            let _tx = transaction();
            owner.processes.fetch_add(1, Ordering::Relaxed);
        }
        Self(owner)
    }
    pub(crate) fn owner(&self) -> &UserMemoryOwner {
        &self.0
    }
}
impl Drop for ProcessMemoryOwner {
    fn drop(&mut self) {
        if let Some(owner) = &self.0 {
            let _tx = transaction();
            let old = owner.processes.fetch_sub(1, Ordering::Relaxed);
            debug_assert!(old > 0);
        }
    }
}

/// Captured at admission; never reads a subsequently migrated binding.
#[derive(Debug, Clone)]
struct CapturedOwner {
    family: Arc<FamilyBudget>,
    domain: Arc<MemoryDomain>,
}
impl CapturedOwner {
    fn refund(&self, pages: usize) {
        let tx = transaction();
        let old = self
            .family
            .current_pages
            .fetch_sub(pages, Ordering::Release);
        debug_assert!(old >= pages);
        self.domain.refund(pages, &tx);
    }
}

/// A precharge for an allocation which has not yet produced all its frames.
pub(crate) struct UserMemoryReservation {
    owner: Option<CapturedOwner>,
    remaining: usize,
}
impl UserMemoryReservation {
    pub(crate) fn new(owner: &UserMemoryOwner, pages: usize) -> Result<Self> {
        let captured = if let Some(owner) = owner {
            let tx = transaction();
            let current = owner.family.current_pages.load(Ordering::Relaxed);
            let next = current
                .checked_add(pages)
                .filter(|next| *next <= owner.family.limit_pages)
                .ok_or_else(Error::user_frame_limit)?;
            let domain = owner.domain.lock();
            domain.admit(pages, &tx)?;
            owner.family.current_pages.store(next, Ordering::Release);
            Some(CapturedOwner {
                family: owner.family.clone(),
                domain: domain.clone(),
            })
        } else {
            None
        };
        Ok(Self {
            owner: captured,
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
pub(crate) struct UserPageCharge(CapturedOwner);
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
/// The binding Arc is stable; reading it does not lock the process VMAR.
/// Admission snapshots its current domain under the memory transaction.
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
