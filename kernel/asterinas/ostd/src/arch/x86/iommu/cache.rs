// SPDX-License-Identifier: MPL-2.0

//! Publish software-owned VT-d structures even when ECAP.C is clear.

use core::{
    arch::x86_64::{__cpuid, _mm_clflush},
    sync::atomic::{Ordering, fence},
};

use crate::mm::{PAGE_SIZE, Paddr, paddr_to_vaddr};

/// Writes back and invalidates every cache line intersecting an owned region.
///
/// # Safety
/// The range must be mapped physical RAM owned by the caller for this call;
/// concurrent software writers must be excluded. Never pass arbitrary MMIO.
pub(super) unsafe fn publish_range(paddr: Paddr, len: usize) {
    let cpu = __cpuid(1);
    assert!(
        cpu.edx & (1 << 19) != 0,
        "VT-d publication requires CLFLUSH"
    );
    let line = ((cpu.ebx >> 8) & 0xff) as usize * 8;
    assert!(line.is_power_of_two());
    fence(Ordering::SeqCst);
    for address in (paddr & !(line - 1)..paddr + len).step_by(line) {
        // SAFETY: The caller owns the RAM range. Cache-line rounding is exactly
        // the architectural CLFLUSH granularity, including coherent CPU caches.
        unsafe { _mm_clflush(paddr_to_vaddr(address) as *const u8) };
    }
    fence(Ordering::SeqCst);
}

/// Publishes a complete live legacy second-level tree, children before parents.
///
/// # Safety
/// The caller owns this tree under the root-table lock; all present non-leaf
/// entries are live, owned page-table frames. No huge pages or hardware-written
/// accessed/dirty bits are used by IommuPtConfig.
pub(super) unsafe fn publish_second_level(paddr: Paddr, level: usize) {
    assert!((1..=3).contains(&level));
    if level > 1 {
        for index in 0..512 {
            // SAFETY: The frame is owned and locked; 512 aligned u64 entries
            // fill one page. Only present non-leaf pointers are followed.
            let entry = unsafe { ((paddr_to_vaddr(paddr) as *const u64).add(index)).read() };
            if entry & 3 != 0 {
                assert_eq!(entry & (1 << 7), 0, "unexpected VT-d huge page");
                unsafe { publish_second_level((entry & 0xffff_ffff_f000) as usize, level - 1) };
            }
        }
    }
    // SAFETY: The tree ownership above includes this table frame.
    unsafe { publish_range(paddr, PAGE_SIZE) };
}
