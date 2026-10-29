// SPDX-License-Identifier: MPL-2.0

#![expect(dead_code)]

use alloc::collections::BTreeMap;
use core::mem::ManuallyDrop;

use super::{domain::DmaDomainError, second_stage::IommuPtConfig};
use crate::{
    arch::iommu::{
        cache::{publish_range, publish_second_level},
        dma_remapping::PciDeviceLocation,
        registers::IOMMU_REGS,
    },
    debug,
    mm::{
        Daddr, Frame, FrameAllocOptions, HasPaddr, PAGE_SIZE, Paddr, PageFlags, PageTable, VmIo,
        page_prop::{CachePolicy, PageProperty, PrivilegedPageFlags as PrivFlags},
        page_table::{PageTableError, PageTableFrag},
    },
    task::disable_preempt,
};

/// Bit 0 is `Present` bit, indicating whether this entry is present.
/// Bit 63:12 is the context-table pointer pointing to this bus's context-table.
#[repr(C)]
#[derive(Clone, Copy, Pod)]
struct RootEntry(u128);

impl RootEntry {
    const fn is_present(&self) -> bool {
        // Bit 0
        (self.0 & 0b1) != 0
    }

    const fn addr(&self) -> u64 {
        (self.0 & 0xFFFF_FFFF_FFFF_F000) as u64
    }
}

pub(in crate::arch::iommu) struct RootTable {
    /// Total 256 bus, each entry is 128 bits.
    root_frame: Frame<()>,
    // TODO: Use radix tree instead.
    context_tables: BTreeMap<Paddr, ContextTable>,
    domains: BTreeMap<PciDeviceLocation, u16>,
}

#[derive(Debug)]
pub(super) enum ContextTableError {
    InvalidDeviceId,
    NotMapped,
    /// Error when modifying the page table
    ModificationError(PageTableError),
}

impl RootTable {
    pub(in crate::arch::iommu) fn root_paddr(&self) -> Paddr {
        self.root_frame.paddr()
    }

    pub(super) fn publish_initial(&self) {
        for context in self.context_tables.values() {
            // SAFETY: Initial construction owns every context and tree, before
            // hardware translation starts. Shared copies remain owned as well.
            unsafe {
                for table in context.page_tables.values() {
                    publish_second_level(table.root_paddr(), 3);
                }
                publish_range(context.entries_frame.paddr(), PAGE_SIZE);
            }
        }
        // SAFETY: This root frame is owned and not yet visible to hardware.
        unsafe { publish_range(self.root_frame.paddr(), PAGE_SIZE) };
    }

    pub(super) fn new() -> Self {
        Self {
            root_frame: FrameAllocOptions::new().alloc_frame().unwrap(),
            context_tables: BTreeMap::new(),
            domains: BTreeMap::new(),
        }
    }

    pub(super) fn bind_domain(&mut self, device: PciDeviceLocation) -> Result<u16, DmaDomainError> {
        if self.domains.contains_key(&device) {
            return Err(DmaDomainError::AlreadyBound);
        }
        let limit = IOMMU_REGS
            .get()
            .unwrap()
            .lock()
            .isolated_domain_limit(device.device)
            .ok_or(DmaDomainError::UnsupportedPlatform)?;
        let id = (1..limit)
            .find(|id| !self.domains.values().any(|used| usize::from(*used) == *id))
            .ok_or(DmaDomainError::DomainIdsExhausted)? as u16;
        // Reserve the ID before any hardware publication. A later allocation
        // panic may leak capacity, but must never permit reuse of a live DID.
        self.domains.insert(device, id);
        let page_table = PageTable::<IommuPtConfig>::empty();
        self.get_or_create_context_table(device)
            .install_domain(device, id, page_table);
        Ok(id)
    }

    pub(super) fn matches_domain(&self, device: PciDeviceLocation, id: u16) -> bool {
        self.domains.get(&device) == Some(&id)
    }

    pub(super) fn release_domain(&mut self, device: PciDeviceLocation, id: u16) {
        assert!(self.matches_domain(device, id));
        self.get_or_create_context_table(device)
            .release_domain(device);
        self.domains.remove(&device);
    }

    /// Mapping device address to physical address.
    ///
    /// # Safety
    ///
    /// User must ensure the given paddr is a valid one.
    pub(super) unsafe fn map(
        &mut self,
        device: PciDeviceLocation,
        daddr: Daddr,
        paddr: Paddr,
    ) -> Result<(), ContextTableError> {
        if device.device >= 32 || device.function >= 8 {
            return Err(ContextTableError::InvalidDeviceId);
        }

        let isolated = self.domains.contains_key(&device);
        let context_table = self.get_or_create_context_table(device);
        // SAFETY: The safety is upheld by the caller.
        unsafe { context_table.map(device, daddr, paddr, isolated)? };

        Ok(())
    }

    pub(super) fn unmap(
        &mut self,
        device: PciDeviceLocation,
        daddr: Daddr,
    ) -> Result<PageTableFrag<IommuPtConfig>, ContextTableError> {
        if device.device >= 32 || device.function >= 8 {
            return Err(ContextTableError::InvalidDeviceId);
        }
        self.get_or_create_context_table(device)
            .unmap(device, daddr)
    }

    /// Specifies the device page table instead of creating a page table if not exists.
    ///
    /// This will be useful if we want all the devices to use the same page table.
    /// The original page table will be overwritten.
    pub(super) fn specify_device_page_table(
        &mut self,
        device_id: PciDeviceLocation,
        page_table: PageTable<IommuPtConfig>,
    ) {
        let context_table = self.get_or_create_context_table(device_id);

        let bus_entry = context_table
            .entries_frame
            .read_val::<ContextEntry>(
                (device_id.device as usize * 8 + device_id.function as usize)
                    * size_of::<ContextEntry>(),
            )
            .unwrap();

        if bus_entry.is_present() {
            panic!("existing device page tables should not be overridden");
        }

        // Activate page table.
        let address = page_table.root_paddr();
        context_table.page_tables.insert(address, page_table);
        let entry = ContextEntry(address as u128 | 1 | 0x1_0000_0000_0000_0000);
        context_table
            .entries_frame
            .write_val::<ContextEntry>(
                (device_id.device as usize * 8 + device_id.function as usize)
                    * size_of::<ContextEntry>(),
                &entry,
            )
            .unwrap();
    }

    fn get_or_create_context_table(&mut self, device_id: PciDeviceLocation) -> &mut ContextTable {
        let bus_entry = self
            .root_frame
            .read_val::<RootEntry>(device_id.bus as usize * size_of::<RootEntry>())
            .unwrap();

        if !bus_entry.is_present() {
            let table = ContextTable::new();
            let address = table.paddr();
            self.context_tables.insert(address, table);
            let entry = RootEntry(address as u128 | 1);
            self.root_frame
                .write_val::<RootEntry>(device_id.bus as usize * size_of::<RootEntry>(), &entry)
                .unwrap();
            self.context_tables.get_mut(&address).unwrap()
        } else {
            self.context_tables
                .get_mut(&(bus_entry.addr() as usize))
                .unwrap()
        }
    }
}

/// Context Entry in the Context Table, used in Intel iommu.
///
/// The format of context entry:
/// ```
/// 127--88: Reserved.
/// 87---72: Domain Identifier.
/// 71---71: Reserved.
/// 70---67: Ignored.
/// 66---64: Address Width.
/// 63---12: Second Stage Page Translation Pointer.
/// 11----4: Reserved.
/// 3-----2: Translation Type.
/// 1-----1: Fault Processing Disable.
/// 0-----0: Present
/// ```
///
#[repr(C)]
#[derive(Clone, Copy, Pod)]
pub(super) struct ContextEntry(u128);

impl ContextEntry {
    /// Identifier for the domain to which this context-entry maps. Hardware may use the domain
    /// identifier to tag its internal caches
    pub(super) const fn domain_identifier(&self) -> u64 {
        // Bit 87-72
        ((self.0 & 0xFF_FF00_0000_0000_0000_0000) >> 72) as u64
    }

    pub(super) const fn address_width(&self) -> AddressWidth {
        // Bit 66-64
        let value = ((self.0 & 0x7_0000_0000_0000_0000) >> 64) as u64;
        match value {
            1 => AddressWidth::Level3PageTable,
            2 => AddressWidth::Level4PageTable,
            3 => AddressWidth::Level5PageTable,
            _ => AddressWidth::Reserved,
        }
    }

    /// Gets the second stage page translation pointer.
    ///
    /// This function will not right shift the value after the `and` operation.
    pub(super) const fn second_stage_pointer(&self) -> u64 {
        // Bit 63~12
        (self.0 & 0xFFFF_FFFF_FFFF_F000) as u64
    }

    /// This field is applicable only for requests-without-PASID, as hardware blocks all requests-with
    /// PASID in legacy mode before they can use context table
    pub(super) const fn translation_type(&self) -> u64 {
        // Bit 3~2
        ((self.0 & 0b1100) >> 2) as u64
    }

    /// Whether need to record/report qualified non-recoverable faults.
    pub(super) const fn need_fault_process(&self) -> bool {
        // Bit 1
        (self.0 & 0b10) == 0
    }

    pub(super) const fn is_present(&self) -> bool {
        // Bit 0
        (self.0 & 0b1) != 0
    }
}

#[derive(Debug)]
pub(super) enum AddressWidth {
    /// 000b, 100b~111b
    Reserved,
    /// 001b
    Level3PageTable,
    /// 010b
    Level4PageTable,
    /// 011b
    Level5PageTable,
}

pub(super) struct ContextTable {
    /// Total 32 devices, each device has 8 functions.
    entries_frame: Frame<()>,
    page_tables: BTreeMap<Paddr, PageTable<IommuPtConfig>>,
}

impl ContextTable {
    fn new() -> Self {
        Self {
            entries_frame: FrameAllocOptions::new().alloc_frame().unwrap(),
            page_tables: BTreeMap::new(),
        }
    }

    fn paddr(&self) -> Paddr {
        self.entries_frame.paddr()
    }

    fn context_offset(device: PciDeviceLocation) -> usize {
        (usize::from(device.device) * 8 + usize::from(device.function)) * size_of::<ContextEntry>()
    }

    /// Replaces the legacy context only after revoking cached references. The
    /// caller exclusively owns the requester in the root table's domain registry.
    fn install_domain(
        &mut self,
        device: PciDeviceLocation,
        id: u16,
        table: PageTable<IommuPtConfig>,
    ) {
        let offset = Self::context_offset(device);
        // Clear Present in the low half before changing any other context bits.
        self.entries_frame.write_val(offset, &0u64).unwrap();
        // SAFETY: Exclusive root-table ownership; publish revocation first.
        unsafe { publish_range(self.entries_frame.paddr(), PAGE_SIZE) };
        IOMMU_REGS.get().unwrap().lock().invalidate_dma_cache();
        let address = table.root_paddr();
        // SAFETY: This newly allocated, still private tree is fully owned.
        unsafe { publish_second_level(address, 3) };
        self.page_tables.insert(address, table);
        // VT-d 5.0 section 9.3: AW=1 (39 bits), unique DID in bits 87:72,
        // TT=00 (untranslated requests only). Publish Present last.
        self.entries_frame
            .write_val(offset + 8, &((u64::from(id) << 8) | 1))
            .unwrap();
        core::sync::atomic::fence(core::sync::atomic::Ordering::SeqCst);
        self.entries_frame
            .write_val(offset, &((address as u64) | 1))
            .unwrap();
        // SAFETY: Context publication is serialized by the root-table lock.
        unsafe { publish_range(self.entries_frame.paddr(), PAGE_SIZE) };
        IOMMU_REGS.get().unwrap().lock().invalidate_dma_cache();
        // Legacy shared tables remain owned; other requesters can still use them.
    }

    fn release_domain(&mut self, device: PciDeviceLocation) {
        let offset = Self::context_offset(device);
        let entry = self.entries_frame.read_val::<ContextEntry>(offset).unwrap();
        self.entries_frame.write_val(offset, &0u64).unwrap();
        // SAFETY: The exclusive context must be visible as absent before drain.
        unsafe { publish_range(self.entries_frame.paddr(), PAGE_SIZE) };
        IOMMU_REGS.get().unwrap().lock().invalidate_dma_cache();
        self.entries_frame.write_val(offset + 8, &0u64).unwrap();
        // The removed table and its nodes outlive the hardware cache/drain fence.
        self.page_tables
            .remove(&(entry.second_stage_pointer() as usize))
            .unwrap();
        // Leave the requester blocked. Never restore the broad legacy domain.
    }

    fn get_or_create_page_table(
        &mut self,
        device: PciDeviceLocation,
    ) -> &mut PageTable<IommuPtConfig> {
        let bus_entry = self
            .entries_frame
            .read_val::<ContextEntry>(
                (device.device as usize * 8 + device.function as usize) * size_of::<ContextEntry>(),
            )
            .unwrap();

        if !bus_entry.is_present() {
            let table = PageTable::<IommuPtConfig>::empty();
            let address = table.root_paddr();
            self.page_tables.insert(address, table);
            let entry = ContextEntry(address as u128 | 3 | 0x1_0000_0000_0000_0000);
            self.entries_frame
                .write_val::<ContextEntry>(
                    (device.device as usize * 8 + device.function as usize)
                        * size_of::<ContextEntry>(),
                    &entry,
                )
                .unwrap();
            self.page_tables.get_mut(&address).unwrap()
        } else {
            self.page_tables
                .get_mut(&(bus_entry.second_stage_pointer() as usize))
                .unwrap()
        }
    }

    /// # Safety
    ///
    /// User must ensure that the given physical address is valid.
    unsafe fn map(
        &mut self,
        device: PciDeviceLocation,
        daddr: Daddr,
        paddr: Paddr,
        isolated: bool,
    ) -> Result<(), ContextTableError> {
        if device.device >= 32 || device.function >= 8 {
            return Err(ContextTableError::InvalidDeviceId);
        }

        debug!(
            "Mapping Daddr: {:x?} to Paddr: {:x?} for device: {:x?}",
            daddr, paddr, device
        );

        let from = daddr..daddr + PAGE_SIZE;
        let prop = PageProperty {
            flags: PageFlags::RW,
            cache: if isolated {
                CachePolicy::Writeback
            } else {
                CachePolicy::Uncacheable
            },
            priv_flags: PrivFlags::empty(),
        };

        let pt = self.get_or_create_page_table(device);
        let preempt_guard = disable_preempt();
        let mut cursor = pt.cursor_mut(&preempt_guard, &from).unwrap();

        // SAFETY: The safety is upheld by the caller.
        unsafe { cursor.map((paddr, 1, prop)) };
        drop(cursor);
        // SAFETY: The root-table lock excludes updates to this owned tree.
        unsafe { publish_second_level(pt.root_paddr(), 3) };

        Ok(())
    }

    fn unmap(
        &mut self,
        device: PciDeviceLocation,
        daddr: Daddr,
    ) -> Result<PageTableFrag<IommuPtConfig>, ContextTableError> {
        if device.device >= 32 || device.function >= 8 {
            return Err(ContextTableError::InvalidDeviceId);
        }

        debug!("Unmapping Daddr: {:x?} for device: {:x?}", daddr, device);

        let pt = self.get_or_create_page_table(device);
        let preempt_guard = disable_preempt();
        let mut cursor = pt
            .cursor_mut(&preempt_guard, &(daddr..daddr + PAGE_SIZE))
            .unwrap();

        // SAFETY: The caller retains the returned fragment and the untyped target
        // until synchronous IOTLB invalidation/draining has completed.
        let fragment = ManuallyDrop::new(
            unsafe { cursor.take_next(PAGE_SIZE) }.ok_or(ContextTableError::NotMapped)?,
        );
        drop(cursor);
        // SAFETY: The remaining tree is owned; removed fragments are retained
        // by the caller until the hardware invalidation/drain completes.
        unsafe { publish_second_level(pt.root_paddr(), 3) };
        Ok(ManuallyDrop::into_inner(fragment))
    }
}
