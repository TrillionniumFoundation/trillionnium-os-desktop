// SPDX-License-Identifier: MPL-2.0

//! The physical memory allocator.

use core::{
    alloc::Layout,
    ops::Range,
    sync::atomic::{AtomicU64, Ordering},
};

use align_ext::AlignExt;

use super::{Frame, meta::AnyFrameMeta, segment::Segment};
use crate::{
    boot::memory_region::MemoryRegionType,
    error::Error,
    impl_frame_meta_for,
    mm::{PAGE_SIZE, paddr_to_vaddr},
    prelude::*,
    util::ops::range_difference,
};

/// Explicit authority to allocate from a physical partition of the original allocator.
///
/// Creation withdraws real frames from ordinary allocation before returning this
/// token. The allocator may reject the requested capacity or not support reserves.
/// The token is not clonable or constructible from a numeric identity. An owner
/// may explicitly share it with `Arc`; ordinary frame allocation never inherits it.
///
/// This is a kernel mechanism, not a user capability or a whole-system recovery
/// guarantee. In particular, page tables, heap objects and IPC do not implicitly
/// use this partition. Callers must separately authorize and bound those paths.
#[derive(Debug)]
pub struct PhysicalReserve {
    identity: u64,
}

static NEXT_RESERVE_ID: AtomicU64 = AtomicU64::new(1);

impl PhysicalReserve {
    /// Withdraws `nframes` from the original allocator as one physical reserve.
    ///
    /// Returns `NoMemory` if the allocator cannot admit the reserve, including
    /// when reserve support is disabled. A failed creation publishes no token.
    pub fn new(nframes: usize) -> Result<Self> {
        let layout = segment_layout(nframes)?;
        let identity = NEXT_RESERVE_ID
            .try_update(Ordering::Relaxed, Ordering::Relaxed, |id| id.checked_add(1))
            .map_err(|_| Error::Overflow)?;
        let token = Self { identity };
        if !get_global_frame_allocator().create_reserve(&token, layout) {
            return Err(Error::NoMemory);
        }
        Ok(token)
    }

    /// The stable incarnation used by the implementing allocator for comparison.
    ///
    /// Knowing this number does not construct authority: allocation hooks accept
    /// the token itself. Identities never wrap or repeat during this boot.
    pub fn identity(&self) -> u64 {
        self.identity
    }

    /// Stops new allocations. Repeated calls are harmless.
    ///
    /// Existing frames remain valid. Their original final-reference destruction
    /// refunds this partition; the original allocator returns the entire extent
    /// to normal allocation only after the final outstanding frame is returned.
    pub fn close(&self) {
        get_global_frame_allocator().close_reserve(self);
    }

    /// Observes the original allocator's partition under its ownership lock.
    ///
    /// Returns `None` after the closed partition has been completely returned.
    pub fn snapshot(&self) -> Option<PhysicalReserveSnapshot> {
        get_global_frame_allocator().reserve_snapshot(self)
    }
}

impl Drop for PhysicalReserve {
    fn drop(&mut self) {
        self.close();
    }
}

/// A consistent observation of one physical reserve, not an admission counter.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PhysicalReserveSnapshot {
    /// Start of the extent withdrawn from ordinary caches and pools.
    pub start: Paddr,
    /// Total size of this extent in bytes.
    pub capacity: usize,
    /// Outstanding bytes, including raw frames whose metadata is being initialized.
    pub allocated: usize,
    /// Whether new allocations have been permanently disabled.
    pub closed: bool,
}

fn segment_layout(nframes: usize) -> Result<Layout> {
    if nframes == 0 {
        return Err(Error::InvalidArgs);
    }
    let size = nframes.checked_mul(PAGE_SIZE).ok_or(Error::Overflow)?;
    Layout::from_size_align(size, PAGE_SIZE).map_err(|_| Error::InvalidArgs)
}

/// Options for allocating physical memory frames.
pub struct FrameAllocOptions {
    zeroed: bool,
}

impl Default for FrameAllocOptions {
    fn default() -> Self {
        Self::new()
    }
}

impl FrameAllocOptions {
    /// Creates new options for allocating the specified number of frames.
    pub fn new() -> Self {
        Self { zeroed: true }
    }

    /// Sets whether the allocated frames should be initialized with zeros.
    ///
    /// If `zeroed` is `true`, the allocated frames are filled with zeros.
    /// If not, the allocated frames will contain sensitive data and the caller
    /// should clear them before sharing them with other components.
    ///
    /// By default, the frames are zero-initialized.
    pub fn zeroed(&mut self, zeroed: bool) -> &mut Self {
        self.zeroed = zeroed;
        self
    }

    /// Allocates a single untyped frame without metadata.
    pub fn alloc_frame(&self) -> Result<Frame<()>> {
        self.alloc_frame_with(())
    }

    /// Allocates a single frame with additional metadata.
    pub fn alloc_frame_with<M: AnyFrameMeta>(&self, metadata: M) -> Result<Frame<M>> {
        self.alloc_frame_in(metadata, None)
    }

    /// Allocates a frame using explicit physical-reserve authority.
    pub fn alloc_frame_from(&self, reserve: &PhysicalReserve) -> Result<Frame<()>> {
        self.alloc_frame_from_with(reserve, ())
    }

    /// Allocates a frame with metadata using explicit physical-reserve authority.
    pub fn alloc_frame_from_with<M: AnyFrameMeta>(
        &self,
        reserve: &PhysicalReserve,
        metadata: M,
    ) -> Result<Frame<M>> {
        self.alloc_frame_in(metadata, Some(reserve))
    }

    fn alloc_frame_in<M: AnyFrameMeta>(
        &self,
        metadata: M,
        reserve: Option<&PhysicalReserve>,
    ) -> Result<Frame<M>> {
        let layout = Layout::from_size_align(PAGE_SIZE, PAGE_SIZE).unwrap();
        let allocator = get_global_frame_allocator();
        let paddr = match reserve {
            Some(token) => allocator.alloc_reserved(token, layout),
            None => allocator.alloc(layout),
        }
        .ok_or(Error::NoMemory)?;
        let frame = Frame::from_unused(paddr, metadata).unwrap();

        if self.zeroed {
            let addr = paddr_to_vaddr(frame.paddr()) as *mut u8;
            // SAFETY: The newly allocated frame is guaranteed to be valid.
            unsafe { core::ptr::write_bytes(addr, 0, PAGE_SIZE) }
        }

        Ok(frame)
    }

    /// Allocates a contiguous range of untyped frames without metadata.
    pub fn alloc_segment(&self, nframes: usize) -> Result<Segment<()>> {
        self.alloc_segment_with(nframes, |_| ())
    }

    /// Allocates a contiguous range of frames with additional metadata.
    ///
    /// The returned [`Segment`] contains at least one frame. The method returns
    /// an error if the number of frames is zero.
    pub fn alloc_segment_with<M: AnyFrameMeta, F>(
        &self,
        nframes: usize,
        metadata_fn: F,
    ) -> Result<Segment<M>>
    where
        F: FnMut(Paddr) -> M,
    {
        self.alloc_segment_in(nframes, metadata_fn, None)
    }

    /// Allocates contiguous frames using explicit physical-reserve authority.
    pub fn alloc_segment_from(
        &self,
        reserve: &PhysicalReserve,
        nframes: usize,
    ) -> Result<Segment<()>> {
        self.alloc_segment_from_with(reserve, nframes, |_| ())
    }

    /// Allocates contiguous frames with metadata from a physical reserve.
    pub fn alloc_segment_from_with<M: AnyFrameMeta, F>(
        &self,
        reserve: &PhysicalReserve,
        nframes: usize,
        metadata_fn: F,
    ) -> Result<Segment<M>>
    where
        F: FnMut(Paddr) -> M,
    {
        self.alloc_segment_in(nframes, metadata_fn, Some(reserve))
    }

    fn alloc_segment_in<M: AnyFrameMeta, F>(
        &self,
        nframes: usize,
        metadata_fn: F,
        reserve: Option<&PhysicalReserve>,
    ) -> Result<Segment<M>>
    where
        F: FnMut(Paddr) -> M,
    {
        let layout = segment_layout(nframes)?;
        let allocator = get_global_frame_allocator();
        let start = match reserve {
            Some(token) => allocator.alloc_reserved(token, layout),
            None => allocator.alloc(layout),
        }
        .ok_or(Error::NoMemory)?;
        let mut tail = UninitializedAllocation {
            start,
            end: start + layout.size(),
        };
        let segment =
            Segment::from_unused_with_progress(start..tail.end, metadata_fn, |committed_end| {
                tail.start = committed_end
            })
            .unwrap();

        if self.zeroed {
            let addr = paddr_to_vaddr(segment.paddr()) as *mut u8;
            // SAFETY: The newly allocated segment is guaranteed to be valid.
            unsafe { core::ptr::write_bytes(addr, 0, layout.size()) }
        }

        Ok(segment)
    }
}

// Owns only the part of a raw allocator result not yet represented by frame
// metadata. Segment owns the committed prefix and refunds it independently.
struct UninitializedAllocation {
    start: Paddr,
    end: Paddr,
}

impl Drop for UninitializedAllocation {
    fn drop(&mut self) {
        if self.start < self.end {
            get_global_frame_allocator().dealloc(self.start, self.end - self.start);
        }
    }
}

#[cfg(ktest)]
#[ktest(expect_redundant_test_prefix)]
fn test_alloc_dealloc() {
    // Here we allocate and deallocate frames in random orders to test the allocator.
    // We expect the test to fail if the underlying implementation panics.
    let single_options = FrameAllocOptions::new();
    let mut contiguous_options = FrameAllocOptions::new();
    contiguous_options.zeroed(false);
    let mut remember_vec = Vec::new();
    for _ in 0..10 {
        for i in 0..10 {
            let single_frame = single_options.alloc_frame().unwrap();
            if i % 3 == 0 {
                remember_vec.push(single_frame);
            }
        }
        let contiguous_segment = contiguous_options.alloc_segment(10).unwrap();
        drop(contiguous_segment);
        remember_vec.pop();
    }
}

/// The trait for the global frame allocator.
///
/// OSTD allows a customized frame allocator by the [`global_frame_allocator`]
/// attribute, which marks a static variable of this type.
///
/// The API mimics the standard Rust allocator API ([`GlobalAlloc`] and
/// [`global_allocator`]). However, this trait is much safer. Double free
/// or freeing in-use memory through this trait only messes up the allocator's
/// state rather than causing undefined behavior.
///
/// Whenever OSTD or other modules need to allocate or deallocate frames via
/// [`FrameAllocOptions`], they are forwarded to the global frame allocator.
/// It is not encouraged to call the global allocator directly.
///
/// [`global_frame_allocator`]: crate::global_frame_allocator
/// [`GlobalAlloc`]: core::alloc::GlobalAlloc
pub trait GlobalFrameAllocator: Sync {
    /// Allocates a contiguous range of frames.
    ///
    /// The caller guarantees that `layout.size()` is aligned to [`PAGE_SIZE`].
    ///
    /// When any of the allocated memory is not in use, OSTD returns them by
    /// calling [`GlobalFrameAllocator::dealloc`]. If multiple frames are
    /// allocated, they may be returned in any order with any number of calls.
    fn alloc(&self, layout: Layout) -> Option<Paddr>;

    /// Admits a physical reserve for a newly minted opaque token.
    ///
    /// Implementors must atomically withdraw the extent from ordinary allocation
    /// before success, reject repeated/closed identities, and never depend on
    /// approximate free-memory counters. The default does not support reserves.
    fn create_reserve(&self, _token: &PhysicalReserve, _layout: Layout) -> bool {
        false
    }

    /// Allocates from an admitted, still-open reserve without ordinary fallback.
    ///
    /// Frames are returned through the original `dealloc` hook. Their physical
    /// origin, not a caller-supplied refund label, determines the destination.
    fn alloc_reserved(&self, _token: &PhysicalReserve, _layout: Layout) -> Option<Paddr> {
        None
    }

    /// Permanently closes admission, returning the extent after its final refund.
    fn close_reserve(&self, _token: &PhysicalReserve) {}

    /// Observes the allocator-owned reserve, if its extent is still retained.
    fn reserve_snapshot(&self, _token: &PhysicalReserve) -> Option<PhysicalReserveSnapshot> {
        None
    }

    /// Deallocates a contiguous range of frames.
    ///
    /// The caller guarantees that `addr` and `size` are both aligned to
    /// [`PAGE_SIZE`]. The deallocated memory should always be allocated by
    /// [`GlobalFrameAllocator::alloc`] or [`GlobalFrameAllocator::alloc_reserved`].
    /// If an allocation returns multiple frames, it is possible
    /// that some of them are deallocated before others. The deallocated memory
    /// must never overlap with any memory that is already deallocated or
    /// added, without being allocated in between.
    ///
    /// The deallocated memory can be uninitialized.
    fn dealloc(&self, addr: Paddr, size: usize);

    /// Adds a contiguous range of frames to the allocator.
    ///
    /// The memory being added must never overlap with any memory that was
    /// added before.
    ///
    /// The added memory can be uninitialized.
    fn add_free_memory(&self, addr: Paddr, size: usize);
}

unsafe extern "Rust" {
    /// The global frame allocator's reference exported by
    /// [`crate::global_frame_allocator`].
    static __GLOBAL_FRAME_ALLOCATOR_REF: &'static dyn GlobalFrameAllocator;
}

pub(super) fn get_global_frame_allocator() -> &'static dyn GlobalFrameAllocator {
    // SAFETY: The global frame allocator is set up correctly with the
    // `global_frame_allocator` attribute. If they use safe code only, the
    // up-call is safe.
    unsafe { __GLOBAL_FRAME_ALLOCATOR_REF }
}

/// Initializes the global frame allocator.
///
/// It just does adds the frames to the global frame allocator. Calling it
/// multiple times would be not safe.
///
/// # Safety
///
/// This function should be called only once.
pub(crate) unsafe fn init() {
    // Retire the early allocator.
    let early_allocator = EARLY_ALLOCATOR.lock().take().unwrap();
    let early_allocated_ranges = early_allocator.allocated_regions();

    #[cfg(all(target_arch = "x86_64", feature = "cvm_guest"))]
    let unaccepted_range = crate::if_tdx_enabled!({
        super::unaccepted::init_unaccepted_memory_state(&early_allocated_ranges)
    } else {
        0..0
    });
    #[cfg(not(all(target_arch = "x86_64", feature = "cvm_guest")))]
    let unaccepted_range: Range<Paddr> = 0..0;

    let regions = &crate::boot::EARLY_INFO.get().unwrap().memory_regions;
    let [range_1, range_2] = &early_allocated_ranges;

    for region in regions
        .iter()
        .filter(|region| region.typ() == MemoryRegionType::Usable)
    {
        debug_assert!(region.base().is_multiple_of(PAGE_SIZE));
        debug_assert!(region.len().is_multiple_of(PAGE_SIZE));

        let region_range = region.base()..region.end();
        for free_range in range_difference(&region_range, range_1)
            .flat_map(|range| range_difference(&range, range_2))
            .flat_map(|range| range_difference(&range, &unaccepted_range))
        {
            crate::info!("Adding free frames to the allocator: {:x?}", free_range);
            get_global_frame_allocator().add_free_memory(free_range.start, free_range.len());
        }
    }
}

/// An allocator in the early boot phase when frame metadata is not available.
pub(super) struct EarlyFrameAllocator {
    // We need to allocate from under 4G first since the linear mapping for
    // the higher region is not constructed yet.
    under_4g_range: Range<Paddr>,
    under_4g_end: Paddr,

    // And also sometimes 4G is not enough for early phase. This, if not `0..0`,
    // is the largest region above 4G.
    max_range: Range<Paddr>,
    max_end: Paddr,
}

/// The global frame allocator in the early boot phase.
///
/// It is used to allocate frames before the frame metadata is initialized.
/// The allocated frames are not tracked by the frame metadata. After the
/// metadata is initialized with [`super::meta::init`], the frames are tracked
/// with metadata and the early allocator is no longer used.
///
/// This is protected by the [`spin::Mutex`] rather than [`crate::sync::SpinLock`]
/// since the latter uses CPU-local storage, which isn't available in the early
/// boot phase. So we must make sure that no interrupts are enabled when using
/// this allocator.
pub(super) static EARLY_ALLOCATOR: spin::Mutex<Option<EarlyFrameAllocator>> =
    spin::Mutex::new(None);

impl EarlyFrameAllocator {
    /// Creates a new early frame allocator.
    ///
    /// It uses at most 2 regions, the first is the maximum usable region below
    /// 4 GiB. The other is the maximum usable region above 4 GiB and is only
    /// usable when linear mapping is constructed.
    pub(crate) fn new() -> Self {
        let regions = &crate::boot::EARLY_INFO.get().unwrap().memory_regions;

        let mut under_4g_range = 0..0;
        let mut max_range = 0..0;
        for region in regions.iter() {
            if region.typ() != MemoryRegionType::Usable {
                continue;
            }
            const PADDR4G: Paddr = 0x1_0000_0000;
            if region.base() < PADDR4G {
                let range = region.base()..region.end().min(PADDR4G);
                if range.len() > under_4g_range.len() {
                    under_4g_range = range;
                }
            }
            if region.end() >= PADDR4G {
                let range = region.base().max(PADDR4G)..region.end();
                if range.len() > max_range.len() {
                    max_range = range;
                }
            }
        }

        crate::debug!(
            "Early frame allocator (below 4G) at: {:#x?}",
            under_4g_range
        );
        if !max_range.is_empty() {
            crate::debug!("Early frame allocator (above 4G) at: {:#x?}", max_range);
        }

        Self {
            under_4g_range: under_4g_range.clone(),
            under_4g_end: under_4g_range.start,
            max_range: max_range.clone(),
            max_end: max_range.start,
        }
    }

    /// Allocates a contiguous range of frames.
    pub(super) fn alloc(&mut self, layout: Layout) -> Option<Paddr> {
        let size = layout.size().align_up(PAGE_SIZE);
        let align = layout.align().max(PAGE_SIZE);

        for (tail, end) in [
            (&mut self.under_4g_end, self.under_4g_range.end),
            (&mut self.max_end, self.max_range.end),
        ] {
            let allocated = tail.align_up(align);
            if let Some(allocated_end) = allocated.checked_add(size)
                && allocated_end <= end
            {
                *tail = allocated_end;
                return Some(allocated);
            }
        }

        None
    }

    pub(super) fn allocated_regions(&self) -> [Range<Paddr>; 2] {
        [
            self.under_4g_range.start..self.under_4g_end,
            self.max_range.start..self.max_end,
        ]
    }
}

/// Metadata for frames allocated in the early boot phase.
///
/// Frames allocated with [`early_alloc`] are not immediately tracked with
/// frame metadata. But [`super::meta::init`] will track them later.
#[derive(Debug)]
pub(crate) struct EarlyAllocatedFrameMeta;

impl_frame_meta_for!(EarlyAllocatedFrameMeta);

/// Allocates a contiguous range of frames in the early boot phase.
///
/// The early allocated frames will not be reclaimable, until the metadata is
/// initialized by [`super::meta::init`]. Then we can use [`Frame::from_raw`]
/// to free the frames.
///
/// # Panics
///
/// This function panics if:
///  - it is called before [`init_early_allocator`],
///  - or if is called after [`init`].
pub(crate) fn early_alloc(layout: Layout) -> Option<Paddr> {
    let mut early_allocator = EARLY_ALLOCATOR.lock();
    let paddr = early_allocator.as_mut().unwrap().alloc(layout)?;

    #[cfg(all(target_arch = "x86_64", feature = "cvm_guest"))]
    crate::if_tdx_enabled!({
        // SAFETY: The early allocator only exists in the boot context of the BSP before the APs
        // boot up. Therefore, there are no other concurrent operations that accept pages.
        unsafe { super::unaccepted::accept_early_allocated_range(paddr, layout.size()) };
    });

    Some(paddr)
}

/// Initializes the early frame allocator.
///
/// [`early_alloc`] should be used after this initialization. After [`init`], the
/// early allocator.
///
/// # Safety
///
/// This function should be called only once after the memory regions are ready.
pub(crate) unsafe fn init_early_allocator() {
    let mut early_allocator = EARLY_ALLOCATOR.lock();
    *early_allocator = Some(EarlyFrameAllocator::new());
}
