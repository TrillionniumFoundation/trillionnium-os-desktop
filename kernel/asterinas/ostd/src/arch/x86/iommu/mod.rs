// SPDX-License-Identifier: MPL-2.0

//! The IOMMU support.

// Set this module's log prefix for `ostd::log`.
macro_rules! __log_prefix {
    () => {
        "iommu: "
    };
}

mod cache;
mod dma_remapping;
pub use dma_remapping::domain::{
    DeviceDmaBuffer, DeviceDmaDomain, DmaDomainError, DmaRequester, RevokedDmaBuffer,
};
mod fault;
mod interrupt_remapping;
mod invalidate;
mod registers;

pub(crate) use dma_remapping::{IommuPtConfig, has_dma_remapping, map, unmap};
pub(in crate::arch) use interrupt_remapping::{
    IrtEntryHandle, alloc_irt_entry, has_interrupt_remapping,
};

use crate::{io::IoMemAllocatorBuilder, mm::page_table::PageTableError};

/// An enumeration representing possible errors related to IOMMU.
#[derive(Debug)]
pub(crate) enum IommuError {
    /// No IOMMU is available.
    NoIommu,
    /// The requested device address has no mapping.
    NotMapped,
    /// Error encountered during modification of the page table.
    #[expect(dead_code)]
    ModificationError(PageTableError),
}

pub(crate) fn init(io_mem_builder: &IoMemAllocatorBuilder) -> Result<(), IommuError> {
    registers::init(io_mem_builder)?;
    invalidate::init();
    dma_remapping::init();
    interrupt_remapping::init();
    Ok(())
}
