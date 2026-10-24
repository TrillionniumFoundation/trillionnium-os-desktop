// SPDX-License-Identifier: MPL-2.0

//! A physical partition inside the original global allocator.
//!
//! The extent is removed by the original cache/pool allocation before publication.
//! No ordinary allocator can see it until closure and the last frame refund.
//! Lock order: local IRQ guard -> RESERVE -> CPU cache/local pool -> global pool.
//! Ordinary allocation never takes RESERVE; it cannot return a withdrawn extent.
//! No heap allocation, waiting, or approximate free-memory admission occurs here.

use core::alloc::Layout;

use ostd::{
    cpu::PinCurrentCpu,
    irq::{self, DisabledLocalIrqGuard},
    mm::{
        PAGE_SIZE, Paddr,
        frame::{PhysicalReserve, PhysicalReserveSnapshot},
    },
    sync::{LocalIrqDisabled, SpinLock},
};

use super::{TOTAL_FREE_SIZE, cache};

// Fixed metadata bounds the mechanism without allocating its own bookkeeping.
// This is a capacity limit on an explicitly requested reserve, not a reduction
// of the memory available to ordinary callers before a successful withdrawal.
const MAX_FRAMES: usize = 4096;
const BITMAP_WORDS: usize = MAX_FRAMES / u64::BITS as usize;

static RESERVE: SpinLock<ReserveState, LocalIrqDisabled> = SpinLock::new(ReserveState {
    last_identity: 0,
    region: None,
});

struct ReserveState {
    // Never reused, including failed requests. Replaying create with an old
    // typed token cannot reopen a closed partition or mint a second extent.
    last_identity: u64,
    region: Option<Region>,
}

struct Region {
    identity: u64,
    start: Paddr,
    nframes: usize,
    allocated: usize,
    closed: bool,
    used: [u64; BITMAP_WORDS],
}

impl Region {
    fn end(&self) -> Paddr {
        self.start + self.nframes * PAGE_SIZE
    }

    fn is_used(&self, index: usize) -> bool {
        self.used[index / 64] & (1 << (index % 64)) != 0
    }

    fn set_used(&mut self, index: usize, value: bool) {
        let mask = 1 << (index % 64);
        if value {
            self.used[index / 64] |= mask;
        } else {
            self.used[index / 64] &= !mask;
        }
    }

    fn allocate(&mut self, layout: Layout) -> Option<Paddr> {
        if self.closed || !valid_layout(layout) {
            return None;
        }
        let count = layout.size() / PAGE_SIZE;
        if count > self.nframes - self.allocated {
            return None;
        }
        // Bounded first-fit, used only on explicit recovery allocations. Normal
        // frame allocation retains its original cache and buddy complexity.
        let mut start = 0;
        while start + count <= self.nframes {
            let paddr = self.start + start * PAGE_SIZE;
            if !paddr.is_multiple_of(layout.align()) {
                start += 1;
                continue;
            }
            if let Some(used) = (start..start + count).find(|&i| self.is_used(i)) {
                start = used + 1;
                continue;
            }
            for index in start..start + count {
                self.set_used(index, true);
            }
            self.allocated += count;
            return Some(paddr);
        }
        None
    }

    fn refund(&mut self, start: Paddr, end: Paddr) {
        let first = (start - self.start) / PAGE_SIZE;
        let last = (end - self.start) / PAGE_SIZE;
        // The original allocator trait forbids double free. Check the entire
        // range before mutating it so an invalid refund cannot partly succeed.
        assert!(
            (first..last).all(|i| self.is_used(i)),
            "physical reserve double free"
        );
        for index in first..last {
            self.set_used(index, false);
        }
        self.allocated -= last - first;
    }
}

fn valid_layout(layout: Layout) -> bool {
    layout.size() != 0 && layout.size().is_multiple_of(PAGE_SIZE)
}

pub(super) fn create(token: &PhysicalReserve, layout: Layout) -> bool {
    let guard = irq::disable_local();
    let mut state = RESERVE.lock();
    if token.identity() <= state.last_identity {
        return false;
    }
    state.last_identity = token.identity();
    if state.region.is_some() || !valid_layout(layout) || layout.size() / PAGE_SIZE > MAX_FRAMES {
        return false;
    }
    let Some(start) = cache::alloc(&guard, layout) else {
        return false;
    };
    TOTAL_FREE_SIZE.sub(guard.current_cpu(), layout.size());
    state.region = Some(Region {
        identity: token.identity(),
        start,
        nframes: layout.size() / PAGE_SIZE,
        allocated: 0,
        closed: false,
        used: [0; BITMAP_WORDS],
    });
    true
}

pub(super) fn alloc(token: &PhysicalReserve, layout: Layout) -> Option<Paddr> {
    let mut state = RESERVE.lock();
    let region = state.region.as_mut()?;
    if region.identity != token.identity() {
        return None;
    }
    region.allocate(layout)
}

pub(super) fn close(token: &PhysicalReserve) {
    let guard = irq::disable_local();
    let mut state = RESERVE.lock();
    let Some(region) = state.region.as_mut() else {
        return;
    };
    if region.identity != token.identity() {
        return;
    }
    region.closed = true;
    release_if_drained(&guard, &mut state);
}

pub(super) fn snapshot(token: &PhysicalReserve) -> Option<PhysicalReserveSnapshot> {
    let state = RESERVE.lock();
    let region = state.region.as_ref()?;
    if region.identity != token.identity() {
        return None;
    }
    Some(PhysicalReserveSnapshot {
        start: region.start,
        capacity: region.nframes * PAGE_SIZE,
        allocated: region.allocated * PAGE_SIZE,
        closed: region.closed,
    })
}

// Returns whether this call handled any reserve overlap. Legitimate deallocations
// can consist of arbitrary contiguous subranges; split by physical provenance,
// rather than requiring the caller to remember the original allocation shape.
pub(super) fn dealloc(guard: &DisabledLocalIrqGuard, addr: Paddr, size: usize) -> bool {
    let mut state = RESERVE.lock();
    let Some(region) = state.region.as_mut() else {
        return false;
    };
    let end = addr
        .checked_add(size)
        .expect("physical refund range overflow");
    let start_overlap = addr.max(region.start);
    let end_overlap = end.min(region.end());
    if start_overlap >= end_overlap {
        return false;
    }
    assert!(addr.is_multiple_of(PAGE_SIZE) && size.is_multiple_of(PAGE_SIZE));
    region.refund(start_overlap, end_overlap);
    if addr < start_overlap {
        refund_ordinary(guard, addr, start_overlap - addr);
    }
    if end_overlap < end {
        refund_ordinary(guard, end_overlap, end - end_overlap);
    }
    release_if_drained(guard, &mut state);
    true
}

fn release_if_drained(guard: &DisabledLocalIrqGuard, state: &mut ReserveState) {
    if !state
        .region
        .as_ref()
        .is_some_and(|r| r.closed && r.allocated == 0)
    {
        return;
    }
    let region = state.region.take().unwrap();
    refund_ordinary(guard, region.start, region.nframes * PAGE_SIZE);
}

fn refund_ordinary(guard: &DisabledLocalIrqGuard, addr: Paddr, size: usize) {
    TOTAL_FREE_SIZE.add(guard.current_cpu(), size);
    cache::dealloc(guard, addr, size);
}

#[cfg(ktest)]
mod tests;
