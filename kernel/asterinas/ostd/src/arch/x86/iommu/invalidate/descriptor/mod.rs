// SPDX-License-Identifier: MPL-2.0

pub(in crate::arch::iommu) struct InterruptEntryCache(pub u128);

impl InterruptEntryCache {
    const INVALIDATION_TYPE: u128 = 4;

    pub(in crate::arch::iommu) fn global_invalidation() -> Self {
        Self(Self::INVALIDATION_TYPE)
    }
}

pub(in crate::arch::iommu) struct InvalidationWait(pub u128);

impl InvalidationWait {
    const INVALIDATION_TYPE: u128 = 5;

    pub(in crate::arch::iommu) fn with_interrupt_flag() -> Self {
        Self(Self::INVALIDATION_TYPE | 0x10)
    }
}

/// Legacy context-cache invalidation, VT-d 5.0 section 6.5.2.1.
pub(in crate::arch::iommu) struct ContextCache(pub u128);

impl ContextCache {
    pub(in crate::arch::iommu) const fn global() -> Self {
        Self(1 | (1 << 4))
    }
}

/// IOTLB and paging-structure-cache invalidation, VT-d 5.0 section 6.5.2.3.
pub(in crate::arch::iommu) struct Iotlb(pub u128);

impl Iotlb {
    /// A following wait must complete before releasing formerly mapped memory.
    /// This drains untranslated requests only; ATS device-TLBs are not covered.
    pub(in crate::arch::iommu) const fn global_with_drain() -> Self {
        Self(2 | (1 << 4) | (1 << 6) | (1 << 7))
    }
}

#[cfg(ktest)]
mod tests {
    use super::*;
    use crate::prelude::ktest;

    #[ktest]
    fn dma_invalidation_encodes_global_scope_and_both_drains() {
        assert_eq!(ContextCache::global().0, 0x11);
        assert_eq!(Iotlb::global_with_drain().0, 0xd2);
        assert_eq!(InvalidationWait::with_interrupt_flag().0, 0x15);
    }
}
