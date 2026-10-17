// SPDX-License-Identifier: MPL-2.0
//! No-alloc DMA/IOVA alias transition model; not a driver or authority.
//! A01 owns real pinning, DMA barriers, IOTLB invalidation and quiescence.
//! A05 owns canonical PCI/device-instance/CapSpace admissions, A06 real quotas.
//! Neither this book nor its receipts can prove hardware access or recovery.

use crate::{DeviceHandle, DeviceState, DmaDirection, MemoryObject, ResourceDomainId};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AliasError {
    WrongDevice,
    WrongOwner,
    InvalidMemory,
    InvalidRange,
    CpuAlias,
    IovaOverlap,
    MemoryOverlap,
    MemoryInstanceReused,
    Exhausted,
    SequenceOverflow,
    Fenced,
    StaleReceipt,
    InvalidBookIdentity,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MappingState { Reserved, UnknownEffect }

#[derive(Debug, PartialEq, Eq)]
pub struct MappingReceipt {
    sequence: u64,
    book_instance: u64,
}
impl MappingReceipt {
    pub const fn sequence(&self) -> u64 { self.sequence }
    /// A05's already-existing kernel registry must issue unique book incarnations.
    /// This value is metadata, not a capability or authentication token.
    pub const fn book_instance(&self) -> u64 { self.book_instance }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Entry {
    sequence: u64,
    memory_id: u64,
    memory_instance: u64,
    offset: usize,
    offset_end: usize,
    iova: u64,
    iova_end: u64,
    direction: DmaDirection,
    state: MappingState,
}

/// Fixed-capacity local metadata only. Two independent books do NOT enforce
/// unique IOMMU-group ownership. A05 must store this under its real registry.
#[derive(Debug, PartialEq, Eq)]
pub struct DmaAliasBook<const N: usize> {
    owner: ResourceDomainId,
    pci_bdf: u32,
    group: u32,
    instance: u64,
    generation: u64,
    // Issued by the canonical A05 registry, distinct across close/reopen,
    // process exec and hotplug. Never minted by this state model.
    book_instance: u64,
    entries: [Option<Entry>; N],
    next_sequence: u64,
    fenced: bool,
}

impl<const N: usize> DmaAliasBook<N> {
    pub fn new(
        device: &DeviceHandle,
        owner: ResourceDomainId,
        book_instance: u64,
    ) -> Result<Self, AliasError> {
        if !owner.is_nonzero() { return Err(AliasError::WrongOwner); }
        if book_instance == 0 { return Err(AliasError::InvalidBookIdentity); }
        if device.instance_id() == 0 || device.state() != DeviceState::Assigned(owner) {
            return Err(AliasError::WrongDevice);
        }
        Ok(Self {
            owner, pci_bdf: device.pci_bdf(), group: device.iommu_group(),
            instance: device.instance_id(), generation: device.generation(),
            book_instance, entries: [None; N], next_sequence: 1, fenced: false,
        })
    }

    pub const fn book_instance(&self) -> u64 { self.book_instance }
    pub fn active(&self) -> usize { self.entries.iter().filter(|e| e.is_some()).count() }
    pub const fn is_fenced(&self) -> bool { self.fenced }
    fn same_attachment(&self, d: &DeviceHandle) -> bool {
        d.pci_bdf() == self.pci_bdf
            && d.iommu_group() == self.group && d.instance_id() == self.instance
    }
    fn admits(&self, d: &DeviceHandle) -> bool {
        self.same_attachment(d) && d.generation() == self.generation
            && d.state() == DeviceState::Assigned(self.owner)
    }

    /// Record a mapping after trusted A01/A05 checks. CPU alias presence MUST
    /// be established by kernel mapping inventory, not an untrusted guest flag.
    /// Conservatively disallow ALL concurrent overlapping ranges, even reads.
    #[allow(clippy::too_many_arguments)]
    pub fn reserve_after_kernel_checks(
        &mut self, device: &DeviceHandle, memory: &MemoryObject,
        memory_instance: u64, iova: u64, offset: usize, len: usize,
        direction: DmaDirection, cpu_writable_alias: bool,
    ) -> Result<MappingReceipt, AliasError> {
        if self.fenced { return Err(AliasError::Fenced); }
        if !self.admits(device) { return Err(AliasError::WrongDevice); }
        if memory.owner() != self.owner { return Err(AliasError::WrongOwner); }
        if memory.id() == 0 || memory_instance == 0 { return Err(AliasError::InvalidMemory); }
        if cpu_writable_alias { return Err(AliasError::CpuAlias); }
        let end_offset = offset.checked_add(len).ok_or(AliasError::InvalidRange)?;
        if len == 0 || end_offset > memory.len() { return Err(AliasError::InvalidRange); }
        let end_iova = iova.checked_add(u64::try_from(len).map_err(|_| AliasError::InvalidRange)?)
            .ok_or(AliasError::InvalidRange)?;
        for e in self.entries.iter().flatten() {
            if iova < e.iova_end && e.iova < end_iova {
                return Err(AliasError::IovaOverlap);
            }
            if memory.id() == e.memory_id {
                if memory_instance != e.memory_instance {
                    return Err(AliasError::MemoryInstanceReused);
                }
                if offset < e.offset_end && e.offset < end_offset {
                    return Err(AliasError::MemoryOverlap);
                }
            }
        }
        let slot = self.entries.iter().position(Option::is_none).ok_or(AliasError::Exhausted)?;
        let seq = self.next_sequence;
        let next = seq.checked_add(1).ok_or(AliasError::SequenceOverflow)?;
        // Never mutate on a failed reservation.
        self.entries[slot] = Some(Entry {
            sequence: seq, memory_id: memory.id(), memory_instance,
            offset, offset_end: end_offset, iova, iova_end: end_iova,
            direction, state: MappingState::Reserved,
        });
        self.next_sequence = next;
        Ok(MappingReceipt { sequence: seq, book_instance: self.book_instance })
    }

    fn index(&self, receipt: &MappingReceipt) -> Option<usize> {
        // A sequence repeats when a book is recreated. A receipt from the
        // previous book must NEVER select a slot in a new book.
        if receipt.book_instance != self.book_instance { return None; }
        self.entries.iter().position(|e| e.map(|x| x.sequence == receipt.sequence).unwrap_or(false))
    }
    pub fn state(&self, receipt: &MappingReceipt) -> Option<MappingState> {
        self.entries.get(self.index(receipt)?)?.map(|e| e.state)
    }
    pub fn direction(&self, receipt: &MappingReceipt) -> Option<DmaDirection> {
        self.entries.get(self.index(receipt)?)?.map(|e| e.direction)
    }

    /// A timeout/cancel is NOT GPU reset. All affected ranges stay reserved.
    pub fn mark_unknown_effect(&mut self, receipt: &MappingReceipt) -> Result<(), AliasError> {
        let i = self.index(receipt).ok_or(AliasError::StaleReceipt)?;
        if let Some(e) = self.entries[i].as_mut() { e.state = MappingState::UnknownEffect; }
        Ok(())
    }

    /// VM loss retains EVERY mapping as unknown and forbids new admissions.
    pub fn fence_all_on_vm_loss(&mut self) {
        self.fenced = true;
        for entry in self.entries.iter_mut().flatten() { entry.state = MappingState::UnknownEffect; }
    }

    /// Only a real A01/A05 kernel adapter may call after verified GPU DMA
    /// quiescence, IOTLB invalidation, CPU cache sync and CPU alias retirement.
    /// This method itself does NOT verify any hardware effect.
    pub fn release_after_platform_quiescence(
        &mut self, device: &DeviceHandle, receipt: &MappingReceipt,
    ) -> Result<(), AliasError> {
        // Generation may have advanced under fencing; incarnation must match.
        if !self.same_attachment(device) { return Err(AliasError::WrongDevice); }
        let i = self.index(receipt).ok_or(AliasError::StaleReceipt)?;
        self.entries[i] = None;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const D: ResourceDomainId = ResourceDomainId::from_u128(99);
    const OTHER: ResourceDomainId = ResourceDomainId::from_u128(100);

    fn setup() -> (DeviceHandle, MemoryObject, DmaAliasBook<2>) {
        let mut device = DeviceHandle::new(0x300, 27, 43).unwrap();
        device.assign_after_kernel_checks(D).unwrap();
        let memory = MemoryObject::new(1, D, 16384);
        let book = DmaAliasBook::<2>::new(&device, D, 710).unwrap();
        (device, memory, book)
    }
    fn reserve(book: &mut DmaAliasBook<2>, d: &DeviceHandle,
               m: &MemoryObject, iova: u64, off: usize, len: usize)
        -> Result<MappingReceipt, AliasError> {
        book.reserve_after_kernel_checks(
            d, m, 3, iova, off, len, DmaDirection::ToDevice, false)
    }

    #[test]
    fn adjacent_ranges_allowed_but_slots_bounded() {
        let (d, m, mut b) = setup();
        let one = reserve(&mut b, &d, &m, 0x1000, 0, 4096).unwrap();
        let two = reserve(&mut b, &d, &m, 0x2000, 4096, 4096).unwrap();
        assert_eq!(b.active(), 2);
        assert_eq!(b.direction(&one), Some(DmaDirection::ToDevice));
        assert_eq!(b.state(&two), Some(MappingState::Reserved));
        assert_eq!(reserve(&mut b, &d, &m, 0x3000, 8192, 1024), Err(AliasError::Exhausted));
    }
    #[test]
    fn iova_overlap_across_different_memories_is_blocked() {
        let (d, m, mut b) = setup();
        reserve(&mut b, &d, &m, 0x1000, 0, 4096).unwrap();
        let other = MemoryObject::new(2, D, 8192);
        assert_eq!(reserve(&mut b, &d, &other, 0x1fff, 0, 4096), Err(AliasError::IovaOverlap));
        assert_eq!(b.active(), 1);
    }
    #[test]
    fn same_memory_range_cannot_map_twice_at_different_iova() {
        let (d, m, mut b) = setup();
        reserve(&mut b, &d, &m, 0x1000, 0, 4096).unwrap();
        assert_eq!(reserve(&mut b, &d, &m, 0x9000, 1024, 512), Err(AliasError::MemoryOverlap));
        assert_eq!(b.active(), 1);
    }
    #[test]
    fn active_memory_id_reuse_is_an_aba_error() {
        let (d, m, mut b) = setup();
        let old = reserve(&mut b, &d, &m, 0x1000, 0, 4096).unwrap();
        assert_eq!(b.reserve_after_kernel_checks(
            &d, &m, 4, 0x8000, 8192, 512, DmaDirection::FromDevice, false
        ), Err(AliasError::MemoryInstanceReused));
        b.release_after_platform_quiescence(&d, &old).unwrap();
        let new_lease = b.reserve_after_kernel_checks(
            &d, &m, 4, 0x1000, 0, 4096, DmaDirection::Bidirectional, false
        ).unwrap();
        assert!(new_lease.sequence() > old.sequence());
    }
    #[test]
    fn cpu_writable_alias_is_rejected() {
        let (d, m, mut b) = setup();
        assert_eq!(b.reserve_after_kernel_checks(
            &d, &m, 3, 0x1000, 0, 4096, DmaDirection::FromDevice, true
        ), Err(AliasError::CpuAlias));
        assert_eq!(b.active(), 0);
    }
    #[test]
    fn zero_length_invalid_offset_and_iova_overflow_fail_without_charges() {
        let (d, m, mut b) = setup();
        for (iova, off, len) in [
            (0x1000, 0, 0), (u64::MAX, 0, 4096),
            (0x1000, usize::MAX, 100), (0x1000, 16000, 500),
        ] {
            assert_eq!(reserve(&mut b, &d, &m, iova, off, len), Err(AliasError::InvalidRange));
        }
        assert_eq!(b.active(), 0);
    }
    #[test]
    fn reject_other_domains_and_missing_memory_instance() {
        let (d, m, mut b) = setup();
        let x = MemoryObject::new(2, OTHER, 4096);
        assert_eq!(reserve(&mut b, &d, &x, 0x1000, 0, 4096), Err(AliasError::WrongOwner));
        assert_eq!(b.reserve_after_kernel_checks(
            &d, &m, 0, 0x1000, 0, 4096, DmaDirection::ToDevice, false
        ), Err(AliasError::InvalidMemory));
    }
    #[test]
    fn attachment_instance_and_generation_are_not_interchangeable() {
        let (mut d, m, mut b) = setup();
        let mut replacement = DeviceHandle::new(d.pci_bdf(), d.iommu_group(), 44).unwrap();
        replacement.assign_after_kernel_checks(D).unwrap();
        assert_eq!(reserve(&mut b, &replacement, &m, 0x1000, 0, 4096), Err(AliasError::WrongDevice));
        let generation = d.generation();
        d.fence(generation).unwrap();
        assert_eq!(reserve(&mut b, &d, &m, 0x1000, 0, 4096), Err(AliasError::WrongDevice));
    }
    #[test]
    fn cancellation_retains_mapping_and_all_alias_exclusion() {
        let (d, m, mut b) = setup();
        let receipt = reserve(&mut b, &d, &m, 0x1000, 0, 4096).unwrap();
        b.mark_unknown_effect(&receipt).unwrap();
        assert_eq!(b.state(&receipt), Some(MappingState::UnknownEffect));
        assert_eq!(reserve(&mut b, &d, &m, 0x1000, 0, 4096), Err(AliasError::IovaOverlap));
        assert_eq!(reserve(&mut b, &d, &m, 0x9000, 0, 4096), Err(AliasError::MemoryOverlap));
        assert_eq!(b.active(), 1);
    }
    #[test]
    fn vm_loss_fences_future_work_but_not_automatic_resource_refund() {
        let (d, m, mut b) = setup();
        let receipt = reserve(&mut b, &d, &m, 0x1000, 0, 4096).unwrap();
        b.fence_all_on_vm_loss();
        assert_eq!(b.state(&receipt), Some(MappingState::UnknownEffect));
        assert_eq!(b.active(), 1);
        assert_eq!(reserve(&mut b, &d, &m, 0x3000, 4096, 4096), Err(AliasError::Fenced));
        b.release_after_platform_quiescence(&d, &receipt).unwrap();
        assert!(b.is_fenced());
        assert_eq!(reserve(&mut b, &d, &m, 0x1000, 0, 4096), Err(AliasError::Fenced));
    }
    #[test]
    fn stale_receipt_never_releases_new_iova_reuse() {
        let (d, m, mut b) = setup();
        let old = reserve(&mut b, &d, &m, 0x1000, 0, 4096).unwrap();
        b.release_after_platform_quiescence(&d, &old).unwrap();
        let next = reserve(&mut b, &d, &m, 0x1000, 0, 4096).unwrap();
        assert_eq!(b.release_after_platform_quiescence(&d, &old), Err(AliasError::StaleReceipt));
        assert_eq!(b.active(), 1);
        b.release_after_platform_quiescence(&d, &next).unwrap();
        assert_eq!(b.release_after_platform_quiescence(&d, &next), Err(AliasError::StaleReceipt));
    }
    #[test]
    fn wrong_rebound_device_cannot_release_old_mapping() {
        let (d, m, mut b) = setup();
        let receipt = reserve(&mut b, &d, &m, 0x1000, 0, 4096).unwrap();
        let mut rebound = DeviceHandle::new(d.pci_bdf(), d.iommu_group(), 44).unwrap();
        rebound.assign_after_kernel_checks(D).unwrap();
        assert_eq!(b.release_after_platform_quiescence(&rebound, &receipt), Err(AliasError::WrongDevice));
        assert_eq!(b.active(), 1);
    }
    #[test]
    fn sequence_overflow_never_changes_book() {
        let (d, m, mut b) = setup();
        b.next_sequence = u64::MAX;
        assert_eq!(reserve(&mut b, &d, &m, 0x1000, 0, 4096), Err(AliasError::SequenceOverflow));
        assert_eq!(b.active(), 0);
    }

    #[test]
    fn book_instance_is_nonzero_and_never_confused_with_permission() {
        let (dev, _, _) = setup();
        assert_eq!(
            DmaAliasBook::<2>::new(&dev, D, 0),
            Err(AliasError::InvalidBookIdentity)
        );
        let book = DmaAliasBook::<2>::new(&dev, D, 722).unwrap();
        assert_eq!(book.book_instance(), 722);
    }

    #[test]
    fn two_books_same_device_with_same_sequence_reject_cross_book_replay() {
        let (dev, memory, mut first) = setup();
        let mut second = DmaAliasBook::<2>::new(&dev, D, 711).unwrap();
        let first_receipt = reserve(&mut first, &dev, &memory, 0x1000, 0, 4096).unwrap();
        let second_receipt = reserve(&mut second, &dev, &memory, 0x1000, 0, 4096).unwrap();
        assert_eq!(first_receipt.sequence(), second_receipt.sequence());
        assert_ne!(first_receipt.book_instance(), second_receipt.book_instance());
        assert_eq!(second.state(&first_receipt), None);
        assert_eq!(second.mark_unknown_effect(&first_receipt), Err(AliasError::StaleReceipt));
        assert_eq!(
            second.release_after_platform_quiescence(&dev, &first_receipt),
            Err(AliasError::StaleReceipt)
        );
        assert_eq!(second.active(), 1);
        assert_eq!(second.state(&second_receipt), Some(MappingState::Reserved));
    }

    #[test]
    fn book_recreation_cannot_release_old_generation_even_at_same_bdf_iova() {
        let (dev, memory, mut old) = setup();
        let stale = reserve(&mut old, &dev, &memory, 0x1000, 0, 4096).unwrap();
        old.fence_all_on_vm_loss();
        let mut new = DmaAliasBook::<2>::new(&dev, D, 712).unwrap();
        let current = reserve(&mut new, &dev, &memory, 0x1000, 0, 4096).unwrap();
        assert_eq!(new.release_after_platform_quiescence(&dev, &stale), Err(AliasError::StaleReceipt));
        assert_eq!(new.state(&stale), None);
        assert_eq!(new.active(), 1);
        new.release_after_platform_quiescence(&dev, &current).unwrap();
        assert_eq!(new.active(), 0);
    }

    #[test]
    fn zero_capacity_never_admits() {
        let (d, m, _) = setup();
        let mut b = DmaAliasBook::<0>::new(&d, D, 720).unwrap();
        assert_eq!(b.reserve_after_kernel_checks(
            &d, &m, 3, 0x1000, 0, 4096, DmaDirection::ToDevice, false
        ), Err(AliasError::Exhausted));
    }
}
