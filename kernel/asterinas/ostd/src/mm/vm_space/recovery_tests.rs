// SPDX-License-Identifier: MPL-2.0

//! Real original frame allocator and page-table owners; no mock allocation path.

use super::*;
use crate::mm::{FrameAllocOptions, PagingConstsTrait};

fn property() -> PageProperty {
    PageProperty::new_user(PageFlags::RW, CachePolicy::Writeback)
}

fn frame() -> UFrame {
    FrameAllocOptions::new().alloc_frame().unwrap().into()
}

fn assert_mapping(cursor: &mut RecoveryCursor<'_>, address: Vaddr, frame: &UFrame) {
    cursor.jump(address).unwrap();
    assert!(matches!(
        cursor.query().unwrap(),
        (range, Some(VmQueriedItem::MappedRam { frame: mapped, prop }))
            if range == (address..address + PAGE_SIZE)
                && mapped.paddr() == frame.paddr() && prop == property()
    ));
}

#[ktest]
fn recovery_root_uses_explicit_reserve_and_closed_root_fails() {
    let reserve = PhysicalReserve::new(1).unwrap();
    let before = reserve.snapshot().unwrap();
    let vm = VmSpace::try_new_from(&reserve).unwrap();
    assert_eq!(vm.pt.root_paddr(), before.start);
    assert_eq!(reserve.snapshot().unwrap().allocated, PAGE_SIZE);
    assert!(matches!(
        VmSpace::try_new_from(&reserve),
        Err(Error::NoMemory)
    ));

    // Ordinary creation does not acquire or inherit authority from the VM root.
    let ordinary = VmSpace::new();
    assert!(!(before.start..before.start + before.capacity).contains(&ordinary.pt.root_paddr()));
    assert_eq!(reserve.snapshot().unwrap().allocated, PAGE_SIZE);
    drop(ordinary);

    reserve.close();
    assert!(matches!(
        VmSpace::try_new_from(&reserve),
        Err(Error::NoMemory)
    ));
    assert_eq!(reserve.snapshot().unwrap().allocated, PAGE_SIZE);
    drop(vm);
    assert!(reserve.snapshot().is_none());
}

#[ktest]
fn recovery_mapping_failure_at_each_missing_level_preserves_input_and_tree() {
    let levels = PagingConsts::NR_LEVELS as usize;
    assert!(levels > 1);
    // Root plus 0, 1, ... missing levels: fail each acquisition cut through
    // the actual global reserve, including the last child-page allocation.
    for capacity in 1..levels {
        let reserve = PhysicalReserve::new(capacity).unwrap();
        let vm = VmSpace::try_new_from(&reserve).unwrap();
        let data = frame();
        let mut input = data.clone();
        let before = reserve.snapshot().unwrap();
        assert_eq!(before.allocated, PAGE_SIZE);
        {
            let guard = disable_preempt();
            let mut cursor = vm
                .recovery_cursor(&guard, &(0..PAGE_SIZE), &reserve)
                .unwrap();
            assert_eq!(reserve.snapshot().unwrap(), before);
            for _ in 0..2 {
                let (error, returned) = cursor.try_map(input, property()).unwrap_err();
                assert_eq!(error, Error::NoMemory);
                assert_eq!(returned.paddr(), data.paddr());
                assert_eq!(returned.reference_count(), 2);
                assert_eq!(cursor.virt_addr(), 0);
                assert!(cursor.query().unwrap().1.is_none());
                assert_eq!(reserve.snapshot().unwrap(), before);
                input = returned;
            }
        }
        drop(input);
        assert_eq!(data.reference_count(), 1);
        reserve.close();
        drop(vm);
        assert!(reserve.snapshot().is_none());
    }
}

#[ktest]
fn recovery_mapping_uses_only_selected_token_and_refunds_last_vm_owner() {
    // The original allocator admits only one live extent. Closing it cannot
    // admit its successor until its original final physical owner drops.
    let old = PhysicalReserve::new(1).unwrap();
    let old_vm = VmSpace::try_new_from(&old).unwrap();
    old.close();
    assert!(matches!(PhysicalReserve::new(1), Err(Error::NoMemory)));
    drop(old_vm);
    assert!(old.snapshot().is_none());

    let reserve = PhysicalReserve::new(PagingConsts::NR_LEVELS as usize + 1).unwrap();
    assert_ne!(old.identity(), reserve.identity());
    assert!(matches!(VmSpace::try_new_from(&old), Err(Error::NoMemory)));
    assert_eq!(reserve.snapshot().unwrap().allocated, 0);
    let vm = Arc::new(VmSpace::try_new_from(&reserve).unwrap());
    let alias = vm.clone();
    let data: UFrame = FrameAllocOptions::new()
        .alloc_frame_from(&reserve)
        .unwrap()
        .into();
    let before = reserve.snapshot().unwrap();
    assert_eq!(before.allocated, 2 * PAGE_SIZE);
    {
        let guard = disable_preempt();
        let mut cursor = vm.recovery_cursor(&guard, &(0..PAGE_SIZE), &old).unwrap();
        let (error, returned) = cursor.try_map(data.clone(), property()).unwrap_err();
        assert_eq!(error, Error::NoMemory);
        assert_eq!(returned.paddr(), data.paddr());
        assert_eq!(cursor.virt_addr(), 0);
        assert!(cursor.query().unwrap().1.is_none());
        assert_eq!(reserve.snapshot().unwrap(), before);
    }
    old.close();
    assert_eq!(reserve.snapshot().unwrap(), before);
    {
        let guard = disable_preempt();
        let mut cursor = vm
            .recovery_cursor(&guard, &(0..PAGE_SIZE), &reserve)
            .unwrap();
        cursor.try_map(data.clone(), property()).unwrap();
        assert_eq!(cursor.virt_addr(), PAGE_SIZE);
        assert_mapping(&mut cursor, 0, &data);
    }
    let allocated = (PagingConsts::NR_LEVELS as usize + 1) * PAGE_SIZE;
    assert_eq!(reserve.snapshot().unwrap().allocated, allocated);
    assert_eq!(data.reference_count(), 2);
    reserve.close();
    drop(vm);
    // A real VM alias retains the actual root, branch and mapped-frame owners.
    assert_eq!(reserve.snapshot().unwrap().allocated, allocated);
    assert_eq!(data.reference_count(), 2);
    assert!(matches!(PhysicalReserve::new(1), Err(Error::NoMemory)));
    drop(alias);
    assert_eq!(reserve.snapshot().unwrap().allocated, PAGE_SIZE);
    assert_eq!(data.reference_count(), 1);
    assert!(matches!(PhysicalReserve::new(1), Err(Error::NoMemory)));
    drop(data);
    assert!(reserve.snapshot().is_none());
    let next = PhysicalReserve::new(1).unwrap();
    assert_eq!(next.snapshot().unwrap().allocated, 0);
}

#[ktest]
fn recovery_mapping_does_not_authorize_ordinary_or_closed_growth() {
    let reserve = PhysicalReserve::new(PagingConsts::NR_LEVELS as usize).unwrap();
    let vm = VmSpace::try_new_from(&reserve).unwrap();
    let data = frame();
    let far = crate::mm::page_size::<UserPtConfig>(2);
    {
        let guard = disable_preempt();
        let mut cursor = vm
            .recovery_cursor(&guard, &(0..far + PAGE_SIZE), &reserve)
            .unwrap();
        cursor.try_map(data.clone(), property()).unwrap();
    }
    let allocated = PagingConsts::NR_LEVELS as usize * PAGE_SIZE;
    assert_eq!(reserve.snapshot().unwrap().allocated, allocated);
    {
        let guard = disable_preempt();
        let mut cursor = vm
            .recovery_cursor(&guard, &(far..far + PAGE_SIZE), &reserve)
            .unwrap();
        let (error, returned) = cursor.try_map(data.clone(), property()).unwrap_err();
        assert_eq!(error, Error::NoMemory);
        assert_eq!(returned.paddr(), data.paddr());
        assert_eq!(cursor.virt_addr(), far);
        assert!(cursor.query().unwrap().1.is_none());
        assert_eq!(reserve.snapshot().unwrap().allocated, allocated);
    }
    reserve.close();
    {
        let guard = disable_preempt();
        let mut cursor = vm
            .recovery_cursor(&guard, &(0..far + PAGE_SIZE), &reserve)
            .unwrap();
        cursor.jump(PAGE_SIZE).unwrap();
        // A prepared leaf needs no authority to allocate additional PT pages.
        cursor.try_map(data.clone(), property()).unwrap();
        cursor.jump(far).unwrap();
        let (error, returned) = cursor.try_map(data.clone(), property()).unwrap_err();
        assert_eq!(error, Error::NoMemory);
        assert_eq!(returned.paddr(), data.paddr());
        assert_eq!(cursor.virt_addr(), far);
        assert!(cursor.query().unwrap().1.is_none());
        assert_eq!(reserve.snapshot().unwrap().allocated, allocated);
    }
    // The original cursor still allocates from its original ordinary owner.
    // A closed reserve cannot silently authorize or pay for this new branch.
    {
        let guard = disable_preempt();
        let mut cursor = vm.cursor_mut(&guard, &(far..far + PAGE_SIZE)).unwrap();
        cursor.map(data.clone(), property());
    }
    assert_eq!(reserve.snapshot().unwrap().allocated, allocated);
    {
        let guard = disable_preempt();
        let mut cursor = vm
            .recovery_cursor(&guard, &(0..far + PAGE_SIZE), &reserve)
            .unwrap();
        for address in [0, PAGE_SIZE, far] {
            assert_mapping(&mut cursor, address, &data);
        }
    }
    drop(vm);
    assert!(reserve.snapshot().is_none());
    assert_eq!(data.reference_count(), 1);
}

#[ktest]
fn recovery_mapping_rejects_conflict_without_replacing_original_frame() {
    let reserve = PhysicalReserve::new(PagingConsts::NR_LEVELS as usize).unwrap();
    let vm = VmSpace::try_new_from(&reserve).unwrap();
    let original = frame();
    let other = frame();
    {
        let guard = disable_preempt();
        let mut cursor = vm
            .recovery_cursor(&guard, &(0..PAGE_SIZE), &reserve)
            .unwrap();
        cursor.try_map(original.clone(), property()).unwrap();
    }
    let before = reserve.snapshot().unwrap();
    let result = crate::panic::catch_unwind(|| {
        let guard = disable_preempt();
        let mut cursor = vm
            .recovery_cursor(&guard, &(0..PAGE_SIZE), &reserve)
            .unwrap();
        cursor.try_map(other.clone(), property()).unwrap();
    });
    let panic = result
        .unwrap_err()
        .downcast::<crate::ktest::PanicInfo>()
        .unwrap();
    assert_eq!(panic.message, "mapping over an already mapped page");
    assert_eq!(other.reference_count(), 1);
    assert_eq!(original.reference_count(), 2);
    assert_eq!(reserve.snapshot().unwrap(), before);
    {
        let guard = disable_preempt();
        assert!(
            vm.recovery_cursor(&guard, &(1..PAGE_SIZE), &reserve)
                .is_err()
        );
        assert!(vm.recovery_cursor(&guard, &(0..0), &reserve).is_err());
        let mut cursor = vm
            .recovery_cursor(&guard, &(0..PAGE_SIZE), &reserve)
            .unwrap();
        assert_mapping(&mut cursor, 0, &original);
        assert!(cursor.jump(2 * PAGE_SIZE).is_err());
        assert_eq!(cursor.virt_addr(), 0);
    }
    assert_eq!(reserve.snapshot().unwrap(), before);
    reserve.close();
    drop(vm);
    assert!(reserve.snapshot().is_none());
    assert_eq!(original.reference_count(), 1);
}

#[ktest]
fn ordinary_no_prealloc_cursor_retains_holes_and_maps_without_reserve_authority() {
    let vm = VmSpace::new();
    let data = frame();
    let far = crate::mm::page_size::<UserPtConfig>(2);
    let empty_range;
    {
        let guard = disable_preempt();
        let mut cursor = vm.cursor_no_prealloc(&guard, &(0..PAGE_SIZE)).unwrap();
        let (range, item) = cursor.query().unwrap();
        assert!(item.is_none());
        assert!(range.len() > PAGE_SIZE);
        empty_range = range;
    }
    // The compatibility API still preallocates even for an empty query. This
    // real contrast proves that the observed hole range detects intermediate
    // page-table creation, without physical exhaustion or failure injection.
    {
        let eager = VmSpace::new();
        let guard = disable_preempt();
        let mut cursor = eager.cursor(&guard, &(0..PAGE_SIZE)).unwrap();
        assert_eq!(cursor.query().unwrap().0, 0..PAGE_SIZE);
    }
    for _ in 0..2 {
        let guard = disable_preempt();
        let mut cursor = vm.cursor_mut_no_prealloc(&guard, &(0..PAGE_SIZE)).unwrap();
        let (range, item) = cursor.query().unwrap();
        assert_eq!(range, empty_range);
        assert!(item.is_none());
    }
    // A live but exhausted reserve must neither fund nor inhibit ordinary growth.
    let reserve = PhysicalReserve::new(1).unwrap();
    let held = FrameAllocOptions::new().alloc_frame_from(&reserve).unwrap();
    let before = reserve.snapshot().unwrap();
    {
        let guard = disable_preempt();
        let mut cursor = vm
            .cursor_mut_no_prealloc(&guard, &(0..far + PAGE_SIZE))
            .unwrap();
        for address in [0, PAGE_SIZE, far] {
            cursor.jump(address).unwrap();
            cursor.try_map(data.clone(), property()).unwrap();
            cursor.jump(address).unwrap();
            assert!(matches!(cursor.query().unwrap(),
                (range, Some(VmQueriedItem::MappedRam { frame, prop }))
                    if range == (address..address + PAGE_SIZE)
                    && frame.paddr() == data.paddr() && prop == property()));
        }
    }
    assert_eq!(reserve.snapshot().unwrap(), before);
    assert_eq!(data.reference_count(), 4);
    drop(vm);
    assert_eq!(data.reference_count(), 1);
    drop(held);
    assert_eq!(reserve.snapshot().unwrap().allocated, 0);
}
