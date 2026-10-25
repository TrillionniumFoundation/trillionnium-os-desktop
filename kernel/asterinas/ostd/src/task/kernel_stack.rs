// SPDX-License-Identifier: MPL-2.0

use core::sync::atomic::Ordering;

use crate::{
    arch::mm::tlb_flush_addr_range,
    cpu::{AtomicCpuSet, CpuSet, PinCurrentCpu},
    impl_frame_meta_for,
    irq::DisabledLocalIrqGuard,
    mm::{
        FrameAllocOptions, PAGE_SIZE,
        kspace::kvirt_area::KVirtArea,
        page_prop::{CachePolicy, PageFlags, PageProperty, PrivilegedPageFlags},
    },
    prelude::*,
};

/// One physical stack page's owned reservation. Dropping it refunds the page
/// only after the frame's final mapping, CPU and RCU references disappear.
pub trait StackPageCharge: core::fmt::Debug + Send + Sync {}
impl<T: core::fmt::Debug + Send + Sync> StackPageCharge for T {}

/// A whole-stack reservation made before physical allocation. Splitting
/// transfers one page to frame metadata; dropping the unused tail rolls back.
pub trait StackReservation: core::fmt::Debug + Send {
    fn split_page(&mut self) -> Box<dyn StackPageCharge>;
}

/// Reserves the requested byte count before allocating the stack segment.
pub type StackCharger = fn(usize) -> Result<Box<dyn StackReservation>>;

/// A fully allocated and mapped, but not yet runnable, kernel task stack.
/// Consume it when building a task so all fallible allocation precedes task
/// publication or an infallible cyclic-Arc construction.
#[derive(Debug)]
pub struct PreparedTaskStack(pub(super) KernelStack);

impl PreparedTaskStack {
    pub fn try_new(charger: StackCharger) -> Result<Self> {
        Ok(Self(KernelStack::new_with_guard_page(Some(charger))?))
    }
}

/// The kernel stack size of a task, specified in pages.
///
/// By default, we choose a rather large stack size.
/// OSTD users can choose a smaller size by specifying
/// the `OSTD_TASK_STACK_SIZE_IN_PAGES` environment variable
/// at build time.
const STACK_SIZE_IN_PAGES: u32 =
    if let Some(size_str) = option_env!("OSTD_TASK_STACK_SIZE_IN_PAGES") {
        match u32::from_str_radix(size_str, 10) {
            Ok(size) => size,
            Err(_) => panic!(
                "The environment variable `OSTD_TASK_STACK_SIZE_IN_PAGES` \
                    specifies an invalid value"
            ),
        }
    } else {
        DEFAULT_STACK_SIZE_IN_PAGES
    };

/// The default kernel stack size of a task, specified in pages.
const DEFAULT_STACK_SIZE_IN_PAGES: u32 = 128;

const KERNEL_STACK_SIZE: usize = STACK_SIZE_IN_PAGES as usize * PAGE_SIZE;

#[derive(Debug)]
pub(super) struct KernelStack {
    kvirt_area: KVirtArea,
    tlb_coherent: AtomicCpuSet,
    end_vaddr: Vaddr,
}

#[derive(Debug, Default)]
struct KernelStackMeta {
    _charge: Option<Box<dyn StackPageCharge>>,
}

impl_frame_meta_for!(KernelStackMeta);

impl KernelStack {
    /// Generates a kernel stack with guard pages.
    ///
    /// Four additional virtual pages remain unmapped as guards; only the
    /// actual stack pages allocate physical frames.
    //
    // TODO: We map kernel stacks in the kernel virtual areas, which incurs
    // non-negligible TLB and mapping overhead on task creation. This could
    // be improved by caching/reusing kernel stacks with a pool.
    pub(super) fn new_with_guard_page(charger: Option<StackCharger>) -> Result<Self> {
        const { assert!(STACK_SIZE_IN_PAGES > 0) };
        let mut reservation = charger
            .map(|charge| charge(KERNEL_STACK_SIZE))
            .transpose()?;
        let pages = FrameAllocOptions::new().zeroed(false).alloc_segment_with(
            KERNEL_STACK_SIZE / PAGE_SIZE,
            |_| KernelStackMeta {
                _charge: reservation.as_mut().map(|charge| charge.split_page()),
            },
        )?;
        drop(reservation);
        let prop = PageProperty {
            flags: PageFlags::RW,
            cache: CachePolicy::Writeback,
            priv_flags: PrivilegedPageFlags::empty(),
        };
        let new_kvirt_area = KVirtArea::try_map_frames(
            KERNEL_STACK_SIZE + 4 * PAGE_SIZE,
            2 * PAGE_SIZE,
            pages.into_iter(),
            prop,
        )?;
        let mapped_start = new_kvirt_area.range().start + 2 * PAGE_SIZE;
        let mapped_end = mapped_start + KERNEL_STACK_SIZE;
        Ok(Self {
            kvirt_area: new_kvirt_area,
            tlb_coherent: AtomicCpuSet::new(CpuSet::new_empty()),
            end_vaddr: mapped_end,
        })
    }

    /// Flushes the TLB for the current CPU if necessary.
    pub(super) fn flush_tlb(&self, irq_guard: &DisabledLocalIrqGuard) {
        let cur_cpu = irq_guard.current_cpu();
        if !self.tlb_coherent.contains(cur_cpu, Ordering::Relaxed) {
            tlb_flush_addr_range(&self.kvirt_area.range());
            self.tlb_coherent.add(cur_cpu, Ordering::Relaxed);
        }
    }

    pub(super) fn end_vaddr(&self) -> Vaddr {
        self.end_vaddr
    }
}

#[cfg(ktest)]
mod tests {
    use core::sync::atomic::{AtomicUsize, Ordering};

    use super::*;
    use crate::{
        mm::kspace::MappedItemRef,
        task::{Task, TaskOptions},
    };

    static USED: AtomicUsize = AtomicUsize::new(0);
    static LIMIT: AtomicUsize = AtomicUsize::new(0);

    #[derive(Debug)]
    struct Reservation(usize);
    #[derive(Debug)]
    struct Page;
    impl Drop for Reservation {
        fn drop(&mut self) {
            USED.fetch_sub(self.0, Ordering::SeqCst);
        }
    }
    impl Drop for Page {
        fn drop(&mut self) {
            USED.fetch_sub(PAGE_SIZE, Ordering::SeqCst);
        }
    }
    impl StackReservation for Reservation {
        fn split_page(&mut self) -> Box<dyn StackPageCharge> {
            assert!(self.0 >= PAGE_SIZE);
            self.0 -= PAGE_SIZE;
            Box::new(Page)
        }
    }
    fn reserve(bytes: usize) -> Result<Box<dyn StackReservation>> {
        USED.fetch_update(Ordering::SeqCst, Ordering::SeqCst, |used| {
            used.checked_add(bytes)
                .filter(|next| *next <= LIMIT.load(Ordering::SeqCst))
        })
        .map_err(|_| crate::Error::NoMemory)?;
        Ok(Box::new(Reservation(bytes)))
    }
    fn await_used(expected: usize) {
        for _ in 0..1000 {
            if USED.load(Ordering::SeqCst) == expected {
                return;
            }
            // Actual context switches advance the RCU grace period. Do not
            // synthesize a callback or refund at the owning stack's destructor.
            TaskOptions::new(|| {}).spawn().unwrap();
            Task::yield_now();
        }
        assert_eq!(USED.load(Ordering::SeqCst), expected);
    }

    #[ktest]
    fn prepared_stack_budget_and_last_frame_reference() {
        LIMIT.store(KERNEL_STACK_SIZE - PAGE_SIZE, Ordering::SeqCst);
        assert!(matches!(
            PreparedTaskStack::try_new(reserve),
            Err(crate::Error::NoMemory)
        ));
        assert_eq!(USED.load(Ordering::SeqCst), 0);

        LIMIT.store(KERNEL_STACK_SIZE, Ordering::SeqCst);
        let prepared = PreparedTaskStack::try_new(reserve).unwrap();
        assert_eq!(USED.load(Ordering::SeqCst), KERNEL_STACK_SIZE);
        let held = {
            let guard = crate::irq::disable_local();
            let address = prepared.0.end_vaddr - KERNEL_STACK_SIZE;
            let MappedItemRef::Tracked(frame, _) =
                prepared.0.kvirt_area.query(&guard, address).unwrap()
            else {
                panic!("stack must use actual tracked physical frames");
            };
            (*frame).clone()
        };
        drop(prepared);
        await_used(PAGE_SIZE);
        drop(held);
        await_used(0);
    }
}
