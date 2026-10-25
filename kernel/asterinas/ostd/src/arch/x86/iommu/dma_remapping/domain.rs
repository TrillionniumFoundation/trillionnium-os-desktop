// SPDX-License-Identifier: MPL-2.0

//! Opt-in requester domains for the restricted legacy VT-d isolation profile.
//! Existing DmaCoherent/DmaStream allocations retain their shared legacy domain.

use alloc::sync::Arc;
use core::mem::ManuallyDrop;

use super::{PAGE_TABLE, PciDeviceLocation};
use crate::{
    arch::{iommu::registers::IOMMU_REGS, irq},
    mm::{
        Daddr, FrameAllocOptions, HasDaddr, HasPaddr, HasPaddrRange, HasSize, Infallible,
        PAGE_SIZE, Segment, VmReader, VmWriter,
        io::util::{HasVmReaderWriter, VmReaderWriterIdentity},
    },
};

/// A PCI requester address, not a claim about ACS isolation groups or aliases.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct DmaRequester {
    /// PCI segment number (only zero in this stage).
    pub segment: u16,
    /// PCI bus number (only the root bus in this stage).
    pub bus: u8,
    /// PCI device number.
    pub device: u8,
    /// PCI function number (only zero in this stage).
    pub function: u8,
}

/// A refused DMA-domain or allocation operation; no direct-DMA fallback.
#[derive(Debug)]
pub enum DmaDomainError {
    /// No enabled DMA remapping unit is available.
    NoIommu,
    /// Platform capabilities or topology fall outside the supported profile.
    UnsupportedPlatform,
    /// Requester address is outside the supported profile.
    UnsupportedRequester,
    /// An outstanding domain already owns the requester.
    AlreadyBound,
    /// Every supported nonzero domain identifier is still reserved.
    DomainIdsExhausted,
    /// A zero or overflowing number of pages was requested.
    InvalidSize,
    /// The physical allocator could not satisfy the request.
    Allocation(crate::Error),
}

/// An independently translated requester. Creation fails rather than falling
/// back to direct DMA or the legacy shared table.
///
/// This first profile accepts only root-bus function-zero requesters behind a
/// single snoop-capable, queued-invalidation VT-d unit with no firmware reservations
/// or additional DMAR structures. It does not qualify PCI alias/ACS groups,
/// peer-to-peer DMA, ATS, PASID, hotplug or physical-device reset behavior.
#[derive(Clone, Debug)]
pub struct DeviceDmaDomain(Arc<Domain>);

#[derive(Debug)]
struct Domain {
    device: PciDeviceLocation,
    id: u16,
}

impl DeviceDmaDomain {
    /// Binds one requester to an empty private domain. Existing mappings for the
    /// requester are revoked synchronously. The caller should stop its driver
    /// before binding; this operation provides no device protocol reset.
    pub fn bind(requester: DmaRequester) -> Result<Self, DmaDomainError> {
        assert!(
            irq::is_local_enabled(),
            "binding a DMA domain requires IRQs enabled"
        );
        if crate::arch::if_tdx_enabled!({ true } else { false }) {
            return Err(DmaDomainError::UnsupportedPlatform);
        }
        if requester.segment != 0
            || requester.bus != 0
            || requester.function != 0
            || requester.device == 0
            || requester.device >= 32
        {
            return Err(DmaDomainError::UnsupportedRequester);
        }
        let table = PAGE_TABLE.get().ok_or(DmaDomainError::NoIommu)?;
        let device = PciDeviceLocation {
            bus: requester.bus,
            device: requester.device,
            function: requester.function,
        };
        let id = table.lock().bind_domain(device)?;
        Ok(Self(Arc::new(Domain { device, id })))
    }

    /// Allocates zeroed untyped physical pages accessible only through this
    /// requester's new table. These allocations are not part of hepta.page.*.
    /// The CPU/device must support coherent accesses in this x86 profile.
    pub fn alloc(&self, nframes: usize) -> Result<DeviceDmaBuffer, DmaDomainError> {
        assert!(
            irq::is_local_enabled(),
            "DMA allocation requires IRQs enabled"
        );
        if nframes == 0 || nframes.checked_mul(PAGE_SIZE).is_none() {
            return Err(DmaDomainError::InvalidSize);
        }
        let segment = FrameAllocOptions::new()
            .alloc_segment(nframes)
            .map_err(DmaDomainError::Allocation)?;
        // IommuPtConfig currently exposes the low canonical half of 39-bit IOVA.
        if segment.paddr_range().end > (1usize << 38) {
            return Err(DmaDomainError::UnsupportedPlatform);
        }
        // If an infallible page-table allocator panics after partial publication,
        // leak the untyped segment rather than retyping DMA-accessible memory.
        let segment = ManuallyDrop::new(segment);
        let mut table = PAGE_TABLE.get().unwrap().lock();
        assert!(table.matches_domain(self.0.device, self.0.id));
        for address in segment.paddr_range().step_by(PAGE_SIZE) {
            // SAFETY: This new, exclusively owned untyped segment remains alive
            // until all entries are revoked and hardware invalidation/draining
            // completes in DeviceDmaBuffer::drop/revoke. Its distinct live frames
            // also ensure that these IOVAs do not replace any existing mapping.
            unsafe { table.map(self.0.device, address as Daddr, address) }.unwrap();
        }
        IOMMU_REGS.get().unwrap().lock().invalidate_dma_cache();
        drop(table);
        Ok(DeviceDmaBuffer {
            domain: self.0.clone(),
            inner: Some(ManuallyDrop::into_inner(segment)),
        })
    }
}

impl Domain {
    fn unmap(&self, segment: &Segment<()>) {
        let mut table = PAGE_TABLE.get().unwrap().lock();
        assert!(table.matches_domain(self.device, self.id));
        for address in segment.paddr_range().step_by(PAGE_SIZE) {
            let fragment = ManuallyDrop::new(table.unmap(self.device, address as Daddr).unwrap());
            // Preserve both removed tables and data pages through the fence.
            IOMMU_REGS.get().unwrap().lock().invalidate_dma_cache();
            drop(ManuallyDrop::into_inner(fragment));
        }
    }
}

impl Drop for Domain {
    fn drop(&mut self) {
        // Every buffer holds an Arc, so all mappings have already been revoked.
        PAGE_TABLE
            .get()
            .unwrap()
            .lock()
            .release_domain(self.device, self.id);
    }
}

/// A coherent buffer whose private IOMMU mapping owns its physical lifetime.
#[derive(Debug)]
pub struct DeviceDmaBuffer {
    domain: Arc<Domain>,
    inner: Option<Segment<()>>,
}

impl DeviceDmaBuffer {
    /// Revokes the device mapping while retaining the physical bytes for CPU use.
    /// An old IOVA is no longer authorized after this returns. Hardware failure
    /// currently stalls this operation rather than releasing an unsafe frame.
    pub fn revoke(mut self) -> RevokedDmaBuffer {
        let segment = ManuallyDrop::new(self.inner.take().unwrap());
        self.domain.unmap(&segment);
        RevokedDmaBuffer(ManuallyDrop::into_inner(segment))
    }
}

impl Drop for DeviceDmaBuffer {
    fn drop(&mut self) {
        if let Some(segment) = self.inner.take() {
            let segment = ManuallyDrop::new(segment);
            self.domain.unmap(&segment);
            drop(ManuallyDrop::into_inner(segment));
        }
    }
}

impl HasDaddr for DeviceDmaBuffer {
    fn daddr(&self) -> Daddr {
        self.inner.as_ref().unwrap().paddr() as Daddr
    }
}

impl HasSize for DeviceDmaBuffer {
    fn size(&self) -> usize {
        self.inner.as_ref().unwrap().size()
    }
}

impl HasVmReaderWriter for DeviceDmaBuffer {
    type Types = VmReaderWriterIdentity;
    fn reader(&self) -> VmReader<'_, Infallible> {
        self.inner.as_ref().unwrap().reader()
    }
    fn writer(&self) -> VmWriter<'_, Infallible> {
        self.inner.as_ref().unwrap().writer()
    }
}

/// CPU-owned bytes with no remaining mapping in their former device domain.
#[derive(Debug)]
pub struct RevokedDmaBuffer(Segment<()>);

impl HasSize for RevokedDmaBuffer {
    fn size(&self) -> usize {
        self.0.size()
    }
}

impl HasVmReaderWriter for RevokedDmaBuffer {
    type Types = VmReaderWriterIdentity;
    fn reader(&self) -> VmReader<'_, Infallible> {
        self.0.reader()
    }
    fn writer(&self) -> VmWriter<'_, Infallible> {
        self.0.writer()
    }
}

#[cfg(all(ktest, feature = "dma-domain-ktest"))]
mod tests;
