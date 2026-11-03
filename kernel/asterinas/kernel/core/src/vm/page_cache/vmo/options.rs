// SPDX-License-Identifier: MPL-2.0

//! Options for allocating root and child VMOs.

use core::sync::atomic::AtomicUsize;

use align_ext::AlignExt;
use ostd::mm::{FrameAllocOptions, Segment};
use xarray::XArray;

use super::{Vmo, VmoFlags, WritableMappingStatus};
use crate::{
    prelude::*,
    vm::{
        page_cache::{CachePage, CachePageMeta, PageCacheBackend},
        user_memory::{UserMemoryOwner, UserMemoryReservation, current_owner},
        vmar::Rmap,
    },
};

/// Options for allocating a root VMO.
///
/// # Examples
///
/// Creating a generic VMO:
/// ```
/// use ostd::mm::PAGE_SIZE;
///
/// use crate::vm::page_cache::VmoOptions;
///
/// let vmo = VmoOptions::new(PAGE_SIZE).alloc();
/// assert!(vmo.is_ok());
/// ```
///
/// Creating an anonymous page-cache-style VMO:
/// ```
/// use ostd::mm::PAGE_SIZE;
///
/// use crate::vm::page_cache::VmoOptions;
///
/// let vmo = VmoOptions::new_anon(10 * PAGE_SIZE).alloc();
/// assert!(vmo.is_ok());
/// ```
pub(crate) struct VmoOptions {
    size: usize,
    flags: VmoFlags,
    backend: Option<Weak<dyn PageCacheBackend>>,
    memory_owner: UserMemoryOwner,
}

impl VmoOptions {
    /// Creates a default set of options with the specified size of the VMO
    /// (in bytes).
    ///
    /// The size of the VMO will be rounded up to align with the page size.
    ///
    /// This is the low-level builder entry point. Call [`VmoOptions::new_anon`]
    /// for resizable RAM-backed page-cache-style VMOs, or
    /// [`VmoOptions::new_page_cache`] for page-cache VMOs with a backend.
    pub(crate) fn new(size: usize) -> Self {
        Self {
            size,
            flags: VmoFlags::empty(),
            backend: None,
            memory_owner: None,
        }
    }

    /// Creates options for an anonymous resizable VMO.
    pub(crate) fn new_anon(size: usize) -> Self {
        Self::new(size).flags(VmoFlags::RESIZABLE)
    }

    /// Creates options for a page-cache VMO with a backend.
    pub(crate) fn new_page_cache(size: usize, backend: Weak<dyn PageCacheBackend>) -> Self {
        Self::new(size).flags(VmoFlags::RESIZABLE).backend(backend)
    }

    /// Sets the VMO flags.
    ///
    /// The default value is `VmoFlags::empty()`.
    ///
    /// For more information about the flags, see `VmoFlags`.
    pub(crate) fn flags(mut self, flags: VmoFlags) -> Self {
        self.flags = flags;
        self
    }

    /// Fixes the owner for a stopped initial image loaded by a kernel task.
    /// Ordinary file VMOs leave this unset and charge each page's initiator.
    pub(crate) fn memory_owner(mut self, owner: UserMemoryOwner) -> Self {
        self.memory_owner = owner;
        self
    }

    /// Sets the backend for the VMO.
    fn backend(mut self, backend: Weak<dyn PageCacheBackend>) -> Self {
        self.backend = Some(backend);
        self
    }
}

impl VmoOptions {
    /// Allocates the VMO according to the specified options.
    pub(crate) fn alloc(self) -> Result<Arc<Vmo>> {
        let VmoOptions {
            size,
            flags,
            backend,
            memory_owner,
            ..
        } = self;
        let vmo = alloc_vmo(size, flags, backend, memory_owner)?;
        Ok(Arc::new(vmo))
    }
}

fn alloc_vmo(
    size: usize,
    flags: VmoFlags,
    backend: Option<Weak<dyn PageCacheBackend>>,
    memory_owner: UserMemoryOwner,
) -> Result<Vmo> {
    let size = size
        .checked_add(PAGE_SIZE - 1)
        .filter(|size| *size <= isize::MAX as usize)
        .ok_or_else(|| Error::new(Errno::ENOMEM))?
        .align_down(PAGE_SIZE);
    let owner = memory_owner.clone().or_else(current_owner);
    let pages = committed_pages_if_continuous(flags, size, &owner)?;
    let writable_mapping_status = WritableMappingStatus::default();
    let rmap = Rmap::new();
    Ok(Vmo {
        memory_owner,
        backend,
        flags,
        pages,
        size: AtomicUsize::new(size),
        writable_mapping_status,
        rmap: Mutex::new(rmap),
    })
}

fn committed_pages_if_continuous(
    flags: VmoFlags,
    size: usize,
    owner: &UserMemoryOwner,
) -> Result<XArray<CachePage>> {
    if flags.contains(VmoFlags::CONTIGUOUS) {
        // if the vmo is continuous, we need to allocate frames for the vmo
        let frames_num = size / PAGE_SIZE;
        // Admit the entire physical segment before allocation. If the
        // allocator fails, the untouched reservation refunds every page.
        let mut reservation = UserMemoryReservation::new(owner, frames_num)?;
        let segment: Segment<CachePageMeta> = FrameAllocOptions::new()
            .alloc_segment_with(frames_num, |_| {
                CachePageMeta::with_charge(reservation.take_page())
            })?;
        let committed_pages = XArray::new();
        let mut locked_pages = committed_pages.lock();
        let mut cursor = locked_pages.cursor_mut(0);
        for frame in segment {
            cursor.store(frame);
            cursor.next();
        }
        drop(locked_pages);
        Ok(committed_pages)
    } else {
        // otherwise, we wait for the page is read or write
        Ok(XArray::new())
    }
}

#[cfg(ktest)]
mod test {
    use ostd::{mm::VmIo, prelude::*};

    use super::*;

    #[ktest]
    fn contiguous_limit_is_admitted_before_any_page() {
        let account = crate::vm::user_memory::UserMemoryAccount::new(2);
        let error = VmoOptions::new(3 * PAGE_SIZE)
            .flags(VmoFlags::CONTIGUOUS)
            .memory_owner(Some(account.clone()))
            .alloc()
            .err()
            .unwrap();
        assert!(error.is_user_frame_limit());
        assert_eq!(account.current_pages(), 0);
        let vmo = VmoOptions::new(2 * PAGE_SIZE)
            .flags(VmoFlags::CONTIGUOUS)
            .memory_owner(Some(account.clone()))
            .alloc()
            .unwrap();
        assert_eq!(account.current_pages(), 2);
        assert_eq!(vmo.size(), 2 * PAGE_SIZE);
    }

    #[ktest]
    fn shared_vmo_aliases_keep_one_physical_charge() {
        use crate::vm::{page_cache::VmoMapMode, user_memory::UserMemoryAccount};
        let account = UserMemoryAccount::new(2);
        let vmo = VmoOptions::new(3 * PAGE_SIZE)
            .memory_owner(Some(account.clone()))
            .alloc()
            .unwrap();
        let (first, _) = vmo.try_commit_page(0, VmoMapMode::Private).unwrap();
        let (alias, _) = vmo.try_commit_page(0, VmoMapMode::Private).unwrap();
        assert_eq!(account.current_pages(), 1);
        drop(first);
        drop(alias);
        assert_eq!(account.current_pages(), 1); // The VMO still owns the page.
        let (second, _) = vmo.try_commit_page(PAGE_SIZE, VmoMapMode::Private).unwrap();
        assert_eq!(account.current_pages(), 2);
        let error = vmo
            .try_commit_page(2 * PAGE_SIZE, VmoMapMode::Private)
            .err()
            .unwrap();
        assert!(error.pending_index().err().unwrap().is_user_frame_limit());
        assert_eq!(account.current_pages(), 2);
        drop(second);
    }

    #[ktest]
    fn alloc_vmo() {
        let vmo = VmoOptions::new(PAGE_SIZE).alloc().unwrap();
        assert_eq!(vmo.size(), PAGE_SIZE);
        // the vmo is zeroed once allocated
        let mut read_buffer = [0; size_of::<usize>()];
        let mut writer = VmWriter::from(read_buffer.as_mut_slice()).to_fallible();
        vmo.read(0, &mut writer).unwrap();
        assert_eq!(usize::from_ne_bytes(read_buffer), 0);
    }

    #[ktest]
    fn alloc_continuous_vmo() {
        let vmo = VmoOptions::new(10 * PAGE_SIZE)
            .flags(VmoFlags::CONTIGUOUS)
            .alloc()
            .unwrap();
        assert_eq!(vmo.size(), 10 * PAGE_SIZE);
    }

    #[ktest]
    fn write_and_read() {
        let vmo = VmoOptions::new(PAGE_SIZE).alloc().unwrap();
        let val = 42u8;
        // write val
        let mut reader = VmReader::from(core::slice::from_ref(&val)).to_fallible();
        vmo.write(111, &mut reader).unwrap();

        let mut read_buffer = [0];
        let mut writer = VmWriter::from(read_buffer.as_mut_slice()).to_fallible();
        vmo.read(111, &mut writer).unwrap();
        let read_val = read_buffer[0];
        assert_eq!(val, read_val);
        // bit endian
        let mut reader = VmReader::from(&[0x12, 0x34, 0x56, 0x78][..]).to_fallible();
        vmo.write(222, &mut reader).unwrap();

        let mut read_buffer = [0; size_of::<u32>()];
        let mut writer = VmWriter::from(read_buffer.as_mut_slice()).to_fallible();
        vmo.read(222, &mut writer).unwrap();
        let read_val = u32::from_ne_bytes(read_buffer);
        assert_eq!(read_val, 0x78563412)
    }

    #[ktest]
    fn resize() {
        use crate::vm::page_cache::PageCache;

        let mut page_cache = PageCache::new_anon(PAGE_SIZE).unwrap();
        page_cache.write_val(10, &42u8).unwrap();
        page_cache.resize(2 * PAGE_SIZE, page_cache.size()).unwrap();
        assert_eq!(page_cache.size(), 2 * PAGE_SIZE);
        assert_eq!(page_cache.read_val::<u8>(10).unwrap(), 42);
        page_cache.write_val(PAGE_SIZE + 20, &123u8).unwrap();
        page_cache.resize(PAGE_SIZE, page_cache.size()).unwrap();
        assert_eq!(page_cache.read_val::<u8>(10).unwrap(), 42);
    }
}
