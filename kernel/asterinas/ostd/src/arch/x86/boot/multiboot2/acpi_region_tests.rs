// SPDX-License-Identifier: MPL-2.0

//! The real GRUB/512-MiB guest faulted reading the RSDT beyond 0x1ffdc000.
//! Preserve the same narrow ACPI reservation policy used by Multiboot1/PVH.

use multiboot2::{Builder, FramebufferTag};

use super::*;
use crate::prelude::ktest;

#[ktest]
fn supplied_rsdt_at_reserved_ram_tail_stays_in_the_physical_extent() {
    let address = NonZeroUsize::new(0x1ffe22fb);
    assert_eq!(
        super::super::effective_region_type(
            MemoryRegionType::Reserved,
            0x1ffdc000,
            0x24000,
            address,
        ),
        MemoryRegionType::Reclaimable
    );
    assert_eq!(
        super::super::effective_region_type(
            MemoryRegionType::Reserved,
            0x20000000,
            0x100000,
            address,
        ),
        MemoryRegionType::Reserved
    );
}

#[ktest]
fn missing_or_nonreserved_acpi_regions_do_not_change_the_map() {
    for typ in [MemoryRegionType::Usable, MemoryRegionType::BadMemory] {
        assert_eq!(
            super::super::effective_region_type(
                typ,
                0x1ffdc000,
                0x24000,
                NonZeroUsize::new(0x1ffe22fb),
            ),
            typ
        );
    }
    assert_eq!(
        super::super::effective_region_type(MemoryRegionType::Reserved, 0x1ffdc000, 0x24000, None,),
        MemoryRegionType::Reserved
    );
}

#[ktest]
fn ega_text_cells_are_not_exposed_as_a_pixel_framebuffer() {
    use multiboot2::MaybeDynSized;
    let bytes = Builder::new()
        .framebuffer(FramebufferTag::new(
            0xb8000,
            160,
            80,
            25,
            16,
            FramebufferType::Text,
        ))
        .build();
    // SAFETY: the original Multiboot2 builder supplies a complete aligned
    // immutable information structure. Its owning box outlives this parse.
    let info = unsafe { BootInformation::load(bytes.as_bytes().as_ptr().cast()) }.unwrap();
    assert!(info.framebuffer_tag().is_some());
    assert!(info.framebuffer_arg().is_none());
}
