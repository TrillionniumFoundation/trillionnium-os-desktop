// SPDX-License-Identifier: MPL-2.0
//! Device/queue/buffer *state transition model*, not a GPU driver or security authority.
//!
//! `#![no_std]` and no allocator: this logic can be reviewed for eventual Asterinas
//! integration, but it does not perform HOS2 authentication, budget reservations,
//! MMIO, IOMMU mapping, cache maintenance, IRQ acknowledgement, or hardware reset.
//! Only the canonical A05/A06 kernel owners may call these transitions after
//! their real platform preconditions have completed. A forged `Completion` or
//! externally asserted quiescence is NOT a physical completion proof.
#![no_std]
#![forbid(unsafe_code)]

/// An identifier of the pre-existing A06 ResourceDomainId, never a capability.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ResourceDomainId(pub u64);

/// State-only handle to an exclusive physical device's entire IOMMU group.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DeviceHandle {
    pub pci_bdf: u32,
    pub iommu_group: u32,
    generation: u64,
    state: DeviceState,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeviceState {
    Unassigned,
    Assigned(ResourceDomainId),
    Fenced,
    Quarantined,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Error {
    InvalidState,
    UnauthorizedDomain,
    StaleGeneration,
    QueueFull,
    ArithmeticOverflow,
    InvalidRange,
    InvalidCompletion,
}

impl DeviceHandle {
    /// Creates metadata only. Does not enumerate/claim any real hardware.
    pub const fn new(pci_bdf: u32, iommu_group: u32) -> Self {
        Self { pci_bdf, iommu_group, generation: 1, state: DeviceState::Unassigned }
    }

    pub const fn generation(&self) -> u64 { self.generation }
    pub const fn state(&self) -> DeviceState { self.state }

    /// Model transition. Caller MUST have independently proven A05 admission,
    /// isolated IOMMU group, and exclusive device ownership before calling.
    pub fn assign_after_kernel_checks(&mut self, owner: ResourceDomainId) -> Result<(), Error> {
        if self.state != DeviceState::Unassigned { return Err(Error::InvalidState); }
        self.state = DeviceState::Assigned(owner);
        Ok(())
    }

    /// Stop all new submissions. Bump the generation before any old result is
    /// observable: in-flight buffers remain held by the kernel until proven safe.
    pub fn fence(&mut self, expected_generation: u64) -> Result<(), Error> {
        if self.generation != expected_generation { return Err(Error::StaleGeneration); }
        if !matches!(self.state, DeviceState::Assigned(_)) { return Err(Error::InvalidState); }
        let next = self.generation.checked_add(1).ok_or(Error::ArithmeticOverflow)?;
        self.generation = next;
        self.state = DeviceState::Fenced;
        Ok(())
    }

    /// A failed or unknown-effect device must not be reassigned by this model.
    pub fn quarantine(&mut self) -> Result<(), Error> {
        let next = self.generation.checked_add(1).ok_or(Error::ArithmeticOverflow)?;
        self.generation = next;
        self.state = DeviceState::Quarantined;
        Ok(())
    }

    fn ensure_owner(&self, owner: ResourceDomainId, generation: u64) -> Result<(), Error> {
        if self.generation != generation { return Err(Error::StaleGeneration); }
        if self.state != DeviceState::Assigned(owner) { return Err(Error::UnauthorizedDomain); }
        Ok(())
    }
}

/// Descriptive metadata for frames owned/charged by the *existing* kernel.
/// This does not pin pages or reserve ResourceDomainId memory.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct MemoryObject {
    pub id: u64,
    pub owner: ResourceDomainId,
    pub len: usize,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DmaDirection { ToDevice, FromDevice, Bidirectional }

/// CPU/DMA ownership. "Prepared" and "CpuReady" are assertions that the
/// platform adapter has already performed its required cache and IOMMU work.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BufferPhase {
    CpuOwned,
    Prepared { device_generation: u64 },
    InFlight { device_generation: u64, queue_generation: u64, sequence: u64 },
    NeedsCpuSync,
    UnknownEffect,
    Released,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Buffer {
    pub memory_id: u64,
    pub owner: ResourceDomainId,
    pub offset: usize,
    pub len: usize,
    pub direction: DmaDirection,
    phase: BufferPhase,
}

impl Buffer {
    pub fn new(memory: &MemoryObject, offset: usize, len: usize,
               direction: DmaDirection) -> Result<Self, Error> {
        if len == 0 || offset.checked_add(len).filter(|end| *end <= memory.len).is_none() {
            return Err(Error::InvalidRange);
        }
        Ok(Self { memory_id: memory.id, owner: memory.owner, offset, len,
                  direction, phase: BufferPhase::CpuOwned })
    }
    pub const fn phase(&self) -> BufferPhase { self.phase }

    /// The caller is responsible for real frame pinning, IOVA restrictions,
    /// CPU writable-alias exclusion, DMA sync and memory barriers.
    pub fn prepare_after_dma_map_and_sync(&mut self, device: &DeviceHandle)
        -> Result<(), Error> {
        device.ensure_owner(self.owner, device.generation)?;
        if self.phase != BufferPhase::CpuOwned { return Err(Error::InvalidState); }
        self.phase = BufferPhase::Prepared { device_generation: device.generation };
        Ok(())
    }

    /// Allowed ONLY after real GPU completion, dma_sync_for_cpu, IOTLB and TLB
    /// unmap/invalidation AND no outstanding CPU/device aliases. This method
    /// cannot prove those effects; the real platform adapter must enforce them.
    pub fn sync_for_cpu_after_platform_checks(&mut self) -> Result<(), Error> {
        if self.phase != BufferPhase::NeedsCpuSync { return Err(Error::InvalidState); }
        self.phase = BufferPhase::CpuOwned;
        Ok(())
    }

    /// Pure metadata release; must not be used as a physical DMA unmap proof.
    pub fn release_after_unmap(&mut self) -> Result<(), Error> {
        if self.phase != BufferPhase::CpuOwned { return Err(Error::InvalidState); }
        self.phase = BufferPhase::Released;
        Ok(())
    }
}

/// A queue bound to ONE owner/physical-device generation.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Queue {
    pub id: u64,
    owner: ResourceDomainId,
    device_generation: u64,
    queue_generation: u64,
    capacity: u32,
    outstanding: u32,
    next_sequence: u64,
    fenced: bool,
}

/// Submission handle, not proof of a hardware IRQ, fence or DMA quiescence.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Completion {
    pub memory_id: u64,
    pub queue_id: u64,
    pub device_generation: u64,
    pub queue_generation: u64,
    pub sequence: u64,
}

impl Queue {
    pub fn new(id: u64, device: &DeviceHandle, owner: ResourceDomainId,
               capacity: u32) -> Result<Self, Error> {
        if capacity == 0 { return Err(Error::QueueFull); }
        device.ensure_owner(owner, device.generation)?;
        Ok(Self { id, owner, device_generation: device.generation, queue_generation: 1,
                  capacity, outstanding: 0, next_sequence: 1, fenced: false })
    }

    pub const fn outstanding(&self) -> u32 { self.outstanding }
    pub const fn generation(&self) -> u64 { self.queue_generation }
    pub const fn is_fenced(&self) -> bool { self.fenced }

    /// Caller must have passed a real kernel-owned descriptor through the
    /// canonical device permission and bounded admission path.
    pub fn submit_after_driver_admission(&mut self, device: &DeviceHandle,
                                         buffer: &mut Buffer) -> Result<Completion, Error> {
        device.ensure_owner(self.owner, self.device_generation)?;
        if self.fenced { return Err(Error::InvalidState); }
        if buffer.owner != self.owner { return Err(Error::UnauthorizedDomain); }
        if buffer.phase != (BufferPhase::Prepared { device_generation: self.device_generation }) {
            return Err(Error::InvalidState);
        }
        if self.outstanding >= self.capacity { return Err(Error::QueueFull); }
        let seq = self.next_sequence;
        let next = seq.checked_add(1).ok_or(Error::ArithmeticOverflow)?;
        let outstanding = self.outstanding.checked_add(1).ok_or(Error::ArithmeticOverflow)?;
        self.next_sequence = next;
        self.outstanding = outstanding;
        buffer.phase = BufferPhase::InFlight { device_generation: self.device_generation,
            queue_generation: self.queue_generation, sequence: seq };
        Ok(Completion { memory_id: buffer.memory_id, queue_id: self.id,
            device_generation: self.device_generation, queue_generation: self.queue_generation,
            sequence: seq })
    }

    /// Called ONLY after trusted driver has observed hardware completion and
    /// released memory ownership barriers. Never call on a user-supplied fence.
    pub fn complete_after_hardware_fence(&mut self, device: &DeviceHandle,
                                        buffer: &mut Buffer, tag: Completion) -> Result<(), Error> {
        // Fenced device generation is rejected, leaving buffers quarantinable.
        device.ensure_owner(self.owner, self.device_generation)?;
        if self.fenced || tag.queue_id != self.id || tag.memory_id != buffer.memory_id ||
           tag.queue_generation != self.queue_generation ||
           tag.device_generation != self.device_generation ||
           buffer.owner != self.owner {
            return Err(Error::InvalidCompletion);
        }
        if buffer.phase != (BufferPhase::InFlight {
            device_generation: self.device_generation,
            queue_generation: self.queue_generation, sequence: tag.sequence,
        }) { return Err(Error::InvalidCompletion); }
        let next = self.outstanding.checked_sub(1).ok_or(Error::InvalidState)?;
        self.outstanding = next;
        buffer.phase = BufferPhase::NeedsCpuSync;
        Ok(())
    }

    /// Cancellation is *not* completion. Keep in-flight pages pinned and make
    /// both the queue and buffer unusable until out-of-band DMA quiescence.
    pub fn cancel_unknown_effect(&mut self, buffer: &mut Buffer) -> Result<(), Error> {
        match buffer.phase {
            BufferPhase::InFlight { device_generation, queue_generation, .. }
                if buffer.owner == self.owner && device_generation == self.device_generation &&
                   queue_generation == self.queue_generation => {}
            _ => return Err(Error::InvalidState),
        }
        let next = self.queue_generation.checked_add(1).ok_or(Error::ArithmeticOverflow)?;
        self.queue_generation = next;
        self.fenced = true;
        buffer.phase = BufferPhase::UnknownEffect;
        // outstanding is intentionally still charged, NOT decremented.
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const D: ResourceDomainId = ResourceDomainId(9);
    const OTHER: ResourceDomainId = ResourceDomainId(10);

    fn setup() -> (DeviceHandle, Queue, Buffer) {
        let mut dev = DeviceHandle::new(0x00000300, 27);
        dev.assign_after_kernel_checks(D).unwrap();
        let queue = Queue::new(7, &dev, D, 2).unwrap();
        let mem = MemoryObject { id: 3, owner: D, len: 4096 };
        let buffer = Buffer::new(&mem, 512, 1024, DmaDirection::Bidirectional).unwrap();
        (dev, queue, buffer)
    }

    #[test]
    fn complete_then_sync_then_release() {
        let (dev, mut queue, mut buffer) = setup();
        assert_eq!(buffer.release_after_unmap(), Err(Error::InvalidState));
        buffer.prepare_after_dma_map_and_sync(&dev).unwrap();
        let tag = queue.submit_after_driver_admission(&dev, &mut buffer).unwrap();
        assert_eq!(buffer.release_after_unmap(), Err(Error::InvalidState));
        queue.complete_after_hardware_fence(&dev, &mut buffer, tag).unwrap();
        assert_eq!(queue.outstanding(), 0);
        assert_eq!(buffer.release_after_unmap(), Err(Error::InvalidState));
        buffer.sync_for_cpu_after_platform_checks().unwrap();
        buffer.release_after_unmap().unwrap();
        assert_eq!(buffer.release_after_unmap(), Err(Error::InvalidState));
    }

    #[test]
    fn claim_is_exclusive_and_same_owner() {
        let (mut dev, _, _) = setup();
        assert_eq!(dev.assign_after_kernel_checks(OTHER), Err(Error::InvalidState));
        assert_eq!(Queue::new(6, &dev, OTHER, 1), Err(Error::UnauthorizedDomain));
    }

    #[test]
    fn wrong_domain_cannot_submit_and_failure_is_atomic() {
        let (dev, mut queue, _) = setup();
        let other_mem = MemoryObject { id: 5, owner: OTHER, len: 4096 };
        let mut wrong = Buffer::new(&other_mem, 0, 16, DmaDirection::ToDevice).unwrap();
        assert_eq!(wrong.prepare_after_dma_map_and_sync(&dev), Err(Error::UnauthorizedDomain));
        assert_eq!(queue.submit_after_driver_admission(&dev, &mut wrong),
                   Err(Error::UnauthorizedDomain));
        assert_eq!(queue.outstanding(), 0);
    }

    #[test]
    fn bad_ranges_and_overflow_are_rejected() {
        let mem = MemoryObject { id: 1, owner: D, len: 100 };
        assert_eq!(Buffer::new(&mem, 0, 0, DmaDirection::ToDevice), Err(Error::InvalidRange));
        assert_eq!(Buffer::new(&mem, 90, 11, DmaDirection::ToDevice), Err(Error::InvalidRange));
        assert_eq!(Buffer::new(&mem, usize::MAX, 2, DmaDirection::ToDevice),
                   Err(Error::InvalidRange));
    }

    #[test]
    fn duplicate_and_stale_completions_never_reclaim_twice() {
        let (dev, mut queue, mut buffer) = setup();
        buffer.prepare_after_dma_map_and_sync(&dev).unwrap();
        let tag = queue.submit_after_driver_admission(&dev, &mut buffer).unwrap();
        let mut stale = tag;
        stale.queue_generation += 1;
        assert_eq!(queue.complete_after_hardware_fence(&dev, &mut buffer, stale),
                   Err(Error::InvalidCompletion));
        assert_eq!(queue.outstanding(), 1);
        queue.complete_after_hardware_fence(&dev, &mut buffer, tag).unwrap();
        assert_eq!(queue.complete_after_hardware_fence(&dev, &mut buffer, tag),
                   Err(Error::InvalidCompletion));
    }

    #[test]
    fn cancel_does_not_release_dma_or_charge() {
        let (dev, mut queue, mut buffer) = setup();
        buffer.prepare_after_dma_map_and_sync(&dev).unwrap();
        let tag = queue.submit_after_driver_admission(&dev, &mut buffer).unwrap();
        queue.cancel_unknown_effect(&mut buffer).unwrap();
        assert_eq!(queue.outstanding(), 1);
        assert!(queue.is_fenced());
        assert_eq!(buffer.phase(), BufferPhase::UnknownEffect);
        assert_eq!(queue.complete_after_hardware_fence(&dev, &mut buffer, tag),
                   Err(Error::InvalidCompletion));
        assert_eq!(buffer.sync_for_cpu_after_platform_checks(), Err(Error::InvalidState));
        assert_eq!(buffer.release_after_unmap(), Err(Error::InvalidState));
    }

    #[test]
    fn fence_invalidates_generation_not_completes_work() {
        let (mut dev, mut queue, mut buffer) = setup();
        buffer.prepare_after_dma_map_and_sync(&dev).unwrap();
        let tag = queue.submit_after_driver_admission(&dev, &mut buffer).unwrap();
        let generation = dev.generation();
        dev.fence(generation).unwrap();
        assert_ne!(dev.generation(), generation);
        assert_eq!(queue.complete_after_hardware_fence(&dev, &mut buffer, tag),
                   Err(Error::StaleGeneration));
        assert_eq!(queue.outstanding(), 1);
        assert_eq!(buffer.release_after_unmap(), Err(Error::InvalidState));
    }

    #[test]
    fn stale_fence_cannot_change_state_and_quarantine_is_sticky() {
        let (mut dev, _, _) = setup();
        assert_eq!(dev.fence(999), Err(Error::StaleGeneration));
        assert_eq!(dev.state(), DeviceState::Assigned(D));
        dev.quarantine().unwrap();
        assert_eq!(dev.assign_after_kernel_checks(D), Err(Error::InvalidState));
        assert_eq!(dev.fence(dev.generation()), Err(Error::InvalidState));
    }

    #[test]
    fn queue_capacity_rejection_does_not_consume_sequence() {
        let (dev, mut queue, mut b1) = setup();
        let mem = MemoryObject { id: 4, owner: D, len: 1024 };
        let mut b2 = Buffer::new(&mem, 0, 128, DmaDirection::ToDevice).unwrap();
        b1.prepare_after_dma_map_and_sync(&dev).unwrap();
        b2.prepare_after_dma_map_and_sync(&dev).unwrap();
        // A one-element alternate queue demonstrates exhausted capacity.
        queue.capacity = 1;
        let one = queue.submit_after_driver_admission(&dev, &mut b1).unwrap();
        assert_eq!(queue.submit_after_driver_admission(&dev, &mut b2), Err(Error::QueueFull));
        assert_eq!(b2.phase(), BufferPhase::Prepared { device_generation: dev.generation() });
        queue.complete_after_hardware_fence(&dev, &mut b1, one).unwrap();
        let two = queue.submit_after_driver_admission(&dev, &mut b2).unwrap();
        assert_eq!(two.sequence, one.sequence + 1);
    }

    #[test]
    fn rejects_zero_capacity_queue_and_prepared_double_submit() {
        let (dev, mut queue, mut buffer) = setup();
        assert_eq!(Queue::new(4, &dev, D, 0), Err(Error::QueueFull));
        buffer.prepare_after_dma_map_and_sync(&dev).unwrap();
        queue.submit_after_driver_admission(&dev, &mut buffer).unwrap();
        assert_eq!(queue.submit_after_driver_admission(&dev, &mut buffer), Err(Error::InvalidState));
        assert_eq!(queue.outstanding(), 1);
    }

    #[test]
    fn fence_and_cancel_generation_overflow_have_no_side_effects() {
        let (mut dev, mut queue, mut buffer) = setup();
        dev.generation = u64::MAX;
        assert_eq!(dev.fence(dev.generation()), Err(Error::ArithmeticOverflow));
        assert_eq!(dev.state(), DeviceState::Assigned(D));
        dev.generation = 1;
        buffer.prepare_after_dma_map_and_sync(&dev).unwrap();
        queue.submit_after_driver_admission(&dev, &mut buffer).unwrap();
        queue.queue_generation = u64::MAX;
        buffer.phase = BufferPhase::InFlight {
            device_generation: dev.generation(), queue_generation: u64::MAX,
            sequence: 1,
        };
        assert_eq!(queue.cancel_unknown_effect(&mut buffer), Err(Error::ArithmeticOverflow));
        assert_eq!(queue.outstanding(), 1);
        assert!(!queue.is_fenced());
        assert!(matches!(buffer.phase(), BufferPhase::InFlight { .. }));
    }

    #[test]
    fn sequence_overflow_preserves_queue_and_buffer_state() {
        let (dev, mut queue, mut buffer) = setup();
        buffer.prepare_after_dma_map_and_sync(&dev).unwrap();
        queue.next_sequence = u64::MAX;
        assert_eq!(queue.submit_after_driver_admission(&dev, &mut buffer),
                   Err(Error::ArithmeticOverflow));
        assert_eq!(queue.outstanding(), 0);
        assert_eq!(buffer.phase(), BufferPhase::Prepared { device_generation: 1 });
    }
}
