// SPDX-License-Identifier: MPL-2.0

use crate::{
    mm::{FrameAllocOptions, PAGE_SIZE, Segment, VmIo},
    prelude::*,
};

pub(in crate::arch::iommu) struct Queue {
    segment: Segment<()>,
    queue_size: usize,
    tail: usize,
}

impl Queue {
    pub(in crate::arch::iommu) fn append_descriptor(&mut self, descriptor: u128) {
        self.segment
            .write_val(self.tail * size_of::<u128>(), &descriptor)
            .unwrap();
        // SAFETY: This queue owns the RAM and its exclusive lock excludes
        // other writers. Publish descriptor bytes before the MMIO tail doorbell.
        unsafe {
            super::super::cache::publish_range(
                self.segment.paddr() + self.tail * size_of::<u128>(),
                size_of::<u128>(),
            );
        }
        self.tail = (self.tail + 1) % self.queue_size;
    }

    pub(in crate::arch::iommu) fn tail(&self) -> usize {
        self.tail
    }

    pub(in crate::arch::iommu) fn size(&self) -> usize {
        self.queue_size
    }

    pub(in crate::arch::iommu) fn base_paddr(&self) -> Paddr {
        self.segment.paddr()
    }

    pub(super) fn new() -> Self {
        const DEFAULT_PAGES: usize = 1;
        let segment = FrameAllocOptions::new()
            .alloc_segment(DEFAULT_PAGES)
            .unwrap();
        Self {
            segment,
            queue_size: (DEFAULT_PAGES * PAGE_SIZE) / size_of::<u128>(),
            tail: 0,
        }
    }
}

#[cfg(ktest)]
mod tests {
    use super::*;
    use crate::prelude::ktest;

    #[ktest]
    fn invalidation_queue_tail_wraps_before_hardware_publication() {
        let mut queue = Queue::new();
        for i in 0..queue.size() {
            queue.append_descriptor(i as u128);
            assert!(queue.tail() < queue.size());
        }
        assert_eq!(queue.tail(), 0);
        assert_eq!(queue.segment.read_val::<u128>(0).unwrap(), 0);
        let last = (queue.size() - 1) * size_of::<u128>();
        assert_eq!(queue.segment.read_val::<u128>(last).unwrap(), 255);
        queue.append_descriptor(0x11);
        assert_eq!(queue.tail(), 1);
        assert_eq!(queue.segment.read_val::<u128>(0).unwrap(), 0x11);
    }
}
