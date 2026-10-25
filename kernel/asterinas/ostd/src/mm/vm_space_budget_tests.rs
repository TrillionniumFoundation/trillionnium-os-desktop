// SPDX-License-Identifier: MPL-2.0

use core::sync::atomic::AtomicUsize;

use super::*;
use crate::{mm::FrameAllocOptions, prelude::ktest};

static USED: AtomicUsize = AtomicUsize::new(0);
static LIMIT: AtomicUsize = AtomicUsize::new(0);

#[derive(Debug)]
struct Charge;
impl Drop for Charge {
    fn drop(&mut self) {
        assert!(USED.fetch_sub(1, Ordering::SeqCst) > 0);
    }
}

fn charge() -> Result<Box<dyn PageTableCharge>> {
    USED.try_update(Ordering::SeqCst, Ordering::SeqCst, |value| {
        (value < LIMIT.load(Ordering::SeqCst)).then_some(value + 1)
    })
    .map_err(|_| Error::NoMemory)?;
    Ok(Box::new(Charge))
}

#[ktest]
fn user_page_table_budget_rejects_allocation_without_retry_or_lifetime_leak() {
    LIMIT.store(0, Ordering::SeqCst);
    assert!(matches!(
        VmSpace::try_new_with_page_table_charger(charge),
        Err(Error::NoMemory)
    ));
    assert_eq!(USED.load(Ordering::SeqCst), 0);
    LIMIT.store(1, Ordering::SeqCst);
    let space = VmSpace::try_new_with_page_table_charger(charge).unwrap();
    assert_eq!(USED.load(Ordering::SeqCst), 1);
    {
        let guard = disable_preempt();
        let mut cursor = space
            .cursor_mut(&guard, &(PAGE_SIZE..2 * PAGE_SIZE))
            .unwrap();
        let prop = PageProperty::new_user(PageFlags::RW, CachePolicy::Writeback);
        assert!(cursor.query().unwrap().1.is_none());
        assert!(cursor.protect_next(PAGE_SIZE, |_, _| {}).is_none());
        cursor.jump(PAGE_SIZE).unwrap();
        assert_eq!(cursor.unmap(PAGE_SIZE), 0);
        cursor.jump(PAGE_SIZE).unwrap();
        assert_eq!(USED.load(Ordering::SeqCst), 1);
        assert_eq!(
            cursor.try_map(FrameAllocOptions::new().alloc_frame().unwrap().into(), prop),
            Err(Error::NoMemory)
        );
        assert_eq!(USED.load(Ordering::SeqCst), 1);
    }
    LIMIT.store(4, Ordering::SeqCst);
    let prop = PageProperty {
        flags: PageFlags::RW,
        cache: CachePolicy::Writeback,
        priv_flags: PrivilegedPageFlags::empty(),
    };
    {
        let guard = disable_preempt();
        let mut cursor = space
            .cursor_mut(&guard, &(PAGE_SIZE..2 * PAGE_SIZE))
            .unwrap();
        cursor
            .try_map(FrameAllocOptions::new().alloc_frame().unwrap().into(), prop)
            .unwrap();
    }
    assert_eq!(USED.load(Ordering::SeqCst), 4);
    // Lock a large range at the root. try_map, not cursor creation, must now
    // allocate a new branch; budget failure must preserve the existing mapping.
    {
        let guard = disable_preempt();
        let mut cursor = space.cursor_mut(&guard, &(0..(1usize << 40))).unwrap();
        cursor.jump(1usize << 39).unwrap();
        assert_eq!(
            cursor.try_map(FrameAllocOptions::new().alloc_frame().unwrap().into(), prop),
            Err(Error::NoMemory)
        );
        assert_eq!(USED.load(Ordering::SeqCst), 4);
    }
    // An admitted intermediate node preceding a later denial stays owned and
    // charged; dropping the space must refund it and every live tree node.
    LIMIT.store(5, Ordering::SeqCst);
    {
        let guard = disable_preempt();
        let mut cursor = space
            .cursor_mut(&guard, &((1usize << 39)..(1usize << 39) + PAGE_SIZE))
            .unwrap();
        assert_eq!(
            cursor.try_map(FrameAllocOptions::new().alloc_frame().unwrap().into(), prop),
            Err(Error::NoMemory)
        );
    }
    assert_eq!(USED.load(Ordering::SeqCst), 5);
    drop(space);
    assert_eq!(USED.load(Ordering::SeqCst), 0);

    // Exercise failure after a real untracked-I/O PTE has been published.
    // This address is not accessed and lies beyond the guest's physical RAM.
    // The owner must survive the error until the VmSpace is destroyed.
    LIMIT.store(4, Ordering::SeqCst);
    let space = VmSpace::try_new_with_page_table_charger(charge).unwrap();
    let io_base = 0x200_000_000_000;
    let io = IoMem::acquire(io_base..io_base + 2 * PAGE_SIZE).unwrap();
    let huge = 2 * 1024 * 1024;
    {
        let guard = disable_preempt();
        let mut cursor = space
            .cursor_mut(&guard, &(huge - PAGE_SIZE..huge + PAGE_SIZE))
            .unwrap();
        let prop = PageProperty::new_user(PageFlags::RW, CachePolicy::Uncacheable);
        assert_eq!(
            cursor.try_map_iomem(io, prop, 2 * PAGE_SIZE, 0),
            Err(Error::NoMemory)
        );
        cursor.jump(huge - PAGE_SIZE).unwrap();
        assert!(matches!(cursor.query().unwrap().1,
            Some(VmQueriedItem::MappedIoMem { paddr, .. }) if paddr == io_base));
        cursor.jump(huge).unwrap();
        assert!(cursor.query().unwrap().1.is_none());
        assert!(cursor.find_iomem_by_paddr(io_base).is_some());
        // Inspect actual retained owner storage. IoMem's global acquisition
        // range is not recycled even on Drop, so reacquisition cannot test
        // whether the VmSpace kept this particular owner alive.
        assert_eq!(space.iomems.lock().len(), 1);
    }
    drop(space);
    assert_eq!(USED.load(Ordering::SeqCst), 0);
    // Do not assert that global IoMem reservation recycling is implemented.
}
