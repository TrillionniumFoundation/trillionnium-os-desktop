// SPDX-License-Identifier: MPL-2.0

//! These tests use the installed global allocator and real OSTD frame metadata.
//! The exhaustion case requires N0 and disables local IRQs only while physical
//! memory is exhausted. It is an allocator test, not a claim that infallible heap
//! allocation or arbitrary recovery workloads survive global memory pressure.

use alloc::{sync::Arc, vec::Vec};
use core::{
    alloc::Layout,
    sync::atomic::{AtomicUsize, Ordering},
};

use ostd::{
    cpu::num_cpus,
    impl_frame_meta_for, irq,
    mm::{
        Frame, FrameAllocOptions, HasPaddr, HasSize, PAGE_SIZE, Segment, Split, UniqueFrame,
        frame::{GlobalFrameAllocator, PhysicalReserve},
    },
    prelude::ktest,
    sync::SpinLock,
    task::{Task, TaskOptions},
};

use crate::{FrameAllocator, load_total_free_size};

fn options() -> FrameAllocOptions {
    let mut options = FrameAllocOptions::new();
    options.zeroed(false);
    options
}

#[ktest]
fn reserve_admission_and_stale_authority() {
    assert!(PhysicalReserve::new(0).is_err());
    assert!(PhysicalReserve::new(usize::MAX).is_err());
    assert!(PhysicalReserve::new(super::MAX_FRAMES + 1).is_err());
    let token = PhysicalReserve::new(16).unwrap();
    let snapshot = token.snapshot().unwrap();
    assert_eq!(snapshot.capacity, 16 * PAGE_SIZE);
    assert_eq!(snapshot.allocated, 0);
    assert!(!snapshot.closed);
    assert!(PhysicalReserve::new(16).is_err());
    assert_eq!(token.snapshot(), Some(snapshot));
    let allocator = FrameAllocator;
    let layout = Layout::from_size_align(PAGE_SIZE, PAGE_SIZE).unwrap();
    assert!(!allocator.create_reserve(&token, layout));
    let ordinary = options().alloc_frame().unwrap();
    assert!(!(snapshot.start..snapshot.start + snapshot.capacity).contains(&ordinary.paddr()));
    drop(ordinary);
    token.close();
    token.close();
    assert!(token.snapshot().is_none());
    assert!(options().alloc_frame_from(&token).is_err());
    assert!(!allocator.create_reserve(&token, layout));
    let successor = PhysicalReserve::new(16).unwrap();
    assert_ne!(token.identity(), successor.identity());
    let successor_snapshot = successor.snapshot();
    assert!(allocator.alloc_reserved(&token, layout).is_none());
    allocator.close_reserve(&token);
    drop(token);
    assert_eq!(successor.snapshot(), successor_snapshot);
    drop(successor);
}

#[derive(Debug)]
struct DropObserved;
static METADATA_DROPS: AtomicUsize = AtomicUsize::new(0);
impl Drop for DropObserved {
    fn drop(&mut self) {
        METADATA_DROPS.fetch_add(1, Ordering::Relaxed);
    }
}
impl_frame_meta_for!(DropObserved);

#[ktest]
fn reserve_refunds_original_owner_after_aliases_and_repurpose() {
    METADATA_DROPS.store(0, Ordering::Relaxed);
    let token = PhysicalReserve::new(8).unwrap();
    let segment = options()
        .alloc_segment_from_with(&token, 8, |_| DropObserved)
        .unwrap();
    let alias = segment.slice(&(2 * PAGE_SIZE..6 * PAGE_SIZE));
    let (left, right) = segment.split(4 * PAGE_SIZE);
    drop(left);
    assert_eq!(token.snapshot().unwrap().allocated, 6 * PAGE_SIZE);
    assert_eq!(METADATA_DROPS.load(Ordering::Relaxed), 2);
    drop(right);
    assert_eq!(token.snapshot().unwrap().allocated, 4 * PAGE_SIZE);
    assert_eq!(METADATA_DROPS.load(Ordering::Relaxed), 4);
    let mut frames = alias.into_iter();
    let frame = frames.next().unwrap();
    let alias = frame.clone();
    drop(frame);
    assert_eq!(token.snapshot().unwrap().allocated, 4 * PAGE_SIZE);
    drop(frames);
    assert_eq!(token.snapshot().unwrap().allocated, PAGE_SIZE);
    let unique = UniqueFrame::try_from(alias).unwrap();
    let unique = unique.repurpose(());
    assert_eq!(METADATA_DROPS.load(Ordering::Relaxed), 8);
    assert_eq!(token.snapshot().unwrap().allocated, PAGE_SIZE);
    token.close();
    token.close();
    assert!(token.snapshot().unwrap().closed);
    assert!(options().alloc_frame_from(&token).is_err());
    assert!(PhysicalReserve::new(8).is_err());
    drop(unique);
    assert!(token.snapshot().is_none());
    let successor = PhysicalReserve::new(8).unwrap();
    drop(token);
    assert!(successor.snapshot().is_some());
}

#[ktest]
fn reserve_fragmentation_alignment_and_failed_allocation_refund() {
    let token = PhysicalReserve::new(16).unwrap();
    let segment = options().alloc_segment_from(&token, 16).unwrap();
    let mut iter = segment.into_iter();
    let mut frames: [Option<Frame<()>>; 16] = core::array::from_fn(|_| iter.next());
    for index in (0..16).step_by(2) {
        drop(frames[index].take());
    }
    let before = token.snapshot().unwrap();
    assert_eq!(before.allocated, 8 * PAGE_SIZE);
    assert!(options().alloc_segment_from(&token, 2).is_err());
    assert_eq!(token.snapshot(), Some(before));
    assert!(options().alloc_segment_from(&token, usize::MAX).is_err());
    assert_eq!(token.snapshot(), Some(before));
    for invalid in [
        Layout::from_size_align(0, PAGE_SIZE).unwrap(),
        Layout::from_size_align(PAGE_SIZE - 1, PAGE_SIZE).unwrap(),
    ] {
        assert!(FrameAllocator.alloc_reserved(&token, invalid).is_none());
        assert_eq!(token.snapshot(), Some(before));
    }
    let layout = Layout::from_size_align(PAGE_SIZE, 4 * PAGE_SIZE).unwrap();
    let addr = FrameAllocator.alloc_reserved(&token, layout).unwrap();
    assert_eq!(addr % (4 * PAGE_SIZE), 0);
    let aligned = Frame::from_unused(addr, ()).unwrap();
    assert_eq!(token.snapshot().unwrap().allocated, 9 * PAGE_SIZE);
    drop(aligned);
    assert_eq!(token.snapshot(), Some(before));
    // Free one adjacent odd page: a contiguous two-page allocation now succeeds.
    drop(frames[1].take());
    let pair = options().alloc_segment_from(&token, 2).unwrap();
    assert_eq!(pair.size(), 2 * PAGE_SIZE);
    drop(pair);
    drop(frames);
    assert_eq!(token.snapshot().unwrap().allocated, 0);
    let full = options().alloc_segment_from(&token, 16).unwrap();
    assert_eq!(full.paddr(), before.start);
    drop(full);
}

#[ktest]
fn reserve_metadata_construction_unwind_refunds_prefix_and_raw_tail() {
    let token = PhysicalReserve::new(8).unwrap();
    let start = token.snapshot().unwrap().start;
    let outcome = ostd::panic::catch_unwind(|| {
        let _segment = options().alloc_segment_from_with(&token, 8, |paddr| {
            if paddr == start + 3 * PAGE_SIZE {
                // Inject the same unwinding mechanism as the ktest harness,
                // without printing a misleading unexpected-panic diagnostic.
                ostd::panic::begin_panic(alloc::boxed::Box::new("metadata failure"));
            }
        });
    });
    assert!(outcome.is_err());
    assert_eq!(token.snapshot().unwrap().allocated, 0);
    let full = options().alloc_segment_from(&token, 8).unwrap();
    assert_eq!(full.paddr(), start);
    drop(full);
}

#[ktest]
fn reserve_raw_subranges_and_typed_frames_share_original_refund() {
    let token = PhysicalReserve::new(12).unwrap();
    let layout = Layout::from_size_align(12 * PAGE_SIZE, PAGE_SIZE).unwrap();
    let start = FrameAllocator.alloc_reserved(&token, layout).unwrap();
    // Exercise the original allocator contract: arbitrary partial contiguous
    // refunds in a different order, then real metadata/last-reference refunds.
    FrameAllocator.dealloc(start + 8 * PAGE_SIZE, 4 * PAGE_SIZE);
    FrameAllocator.dealloc(start, 3 * PAGE_SIZE);
    assert_eq!(token.snapshot().unwrap().allocated, 5 * PAGE_SIZE);
    let rest = Segment::from_unused(start + 3 * PAGE_SIZE..start + 8 * PAGE_SIZE, |_| ()).unwrap();
    let first = rest.slice(&(0..PAGE_SIZE));
    drop(rest);
    assert_eq!(token.snapshot().unwrap().allocated, PAGE_SIZE);
    drop(first);
    assert_eq!(token.snapshot().unwrap().allocated, 0);
    let full = options().alloc_segment_from(&token, 12).unwrap();
    assert_eq!(full.paddr(), start);
    drop(full);
}

#[ktest]
fn reserve_concurrent_holders_close_and_final_refund() {
    let token = Arc::new(PhysicalReserve::new(8).unwrap());
    let ready = Arc::new(AtomicUsize::new(0));
    let release = Arc::new(AtomicUsize::new(0));
    let done = Arc::new(AtomicUsize::new(0));
    let addresses = Arc::new(SpinLock::<[usize; 4]>::new([0usize; 4]));
    let mut tasks = Vec::with_capacity(4);
    for index in 0..4 {
        let (token, ready, release, done, addresses) = (
            token.clone(),
            ready.clone(),
            release.clone(),
            done.clone(),
            addresses.clone(),
        );
        tasks.push(
            TaskOptions::new(move || {
                let frame = options().alloc_frame_from(&token).unwrap();
                addresses.lock()[index] = frame.paddr();
                ready.fetch_add(1, Ordering::Release);
                wait_for(&release, 1);
                assert!(options().alloc_frame_from(&token).is_err());
                // Racing close calls neither renew authority nor duplicate a refund.
                token.close();
                drop(frame);
                drop(token);
                done.fetch_add(1, Ordering::Release);
            })
            .data(())
            .spawn()
            .unwrap(),
        );
    }
    wait_for(&ready, 4);
    let values = *addresses.lock();
    for (index, value) in values.iter().enumerate() {
        assert!(!values[..index].contains(value));
    }
    assert_eq!(token.snapshot().unwrap().allocated, 4 * PAGE_SIZE);
    token.close();
    assert!(token.snapshot().unwrap().closed);
    release.store(1, Ordering::Release);
    wait_for(&done, 4);
    assert!(token.snapshot().is_none());
    drop(tasks);
    assert!(options().alloc_frame_from(&token).is_err());
}

#[ktest]
fn reserve_concurrent_creation_publishes_only_one_extent() {
    let start = Arc::new(AtomicUsize::new(0));
    let done = Arc::new(AtomicUsize::new(0));
    let admitted = Arc::new(AtomicUsize::new(0));
    let winner = Arc::new(SpinLock::<Option<PhysicalReserve>>::new(None));
    let mut tasks = Vec::with_capacity(4);
    for _ in 0..4 {
        let (start, done, admitted, winner) = (
            start.clone(),
            done.clone(),
            admitted.clone(),
            winner.clone(),
        );
        tasks.push(
            TaskOptions::new(move || {
                wait_for(&start, 1);
                if let Ok(token) = PhysicalReserve::new(32) {
                    admitted.fetch_add(1, Ordering::Relaxed);
                    let mut slot = winner.lock();
                    assert!(slot.is_none());
                    *slot = Some(token);
                }
                done.fetch_add(1, Ordering::Release);
            })
            .data(())
            .spawn()
            .unwrap(),
        );
    }
    start.store(1, Ordering::Release);
    wait_for(&done, 4);
    assert_eq!(admitted.load(Ordering::Relaxed), 1);
    let token = winner.lock().take().unwrap();
    assert_eq!(token.snapshot().unwrap().capacity, 32 * PAGE_SIZE);
    assert_eq!(token.snapshot().unwrap().allocated, 0);
    drop(token);
    drop(tasks);
    let successor = PhysicalReserve::new(32).unwrap();
    assert!(successor.snapshot().is_some());
}

fn wait_for(counter: &AtomicUsize, value: usize) {
    for _ in 0..100_000 {
        if counter.load(Ordering::Acquire) == value {
            return;
        }
        Task::yield_now();
    }
    panic!("physical reserve test worker timed out");
}

#[ktest]
fn reserve_survives_actual_ordinary_allocator_exhaustion_n0() {
    assert_eq!(
        num_cpus(),
        1,
        "exhaustion fixture requires N0; other tests support SMP"
    );
    // All bookkeeping is allocated before pressure. Its upper bound is used
    // only to size the test Vec, never to authorize a reserve or fake exhaustion.
    let capacity = load_total_free_size() / PAGE_SIZE + 1024;
    let mut pressure = Vec::<Frame<()>>::with_capacity(capacity);
    let token = PhysicalReserve::new(64).unwrap();
    let snapshot = token.snapshot().unwrap();
    let options = options();
    let guard = irq::disable_local();
    let mut escaped = false;
    let mut overflow = false;
    // Drain every ordinary small cache through its real public allocation path,
    // including contiguous sizes and aligned allocations. Stop on real None,
    // not on a fake capacity threshold or a modified allocator free counter.
    for nframes in [1, 2, 3, 4, 8] {
        while let Ok(segment) = options.alloc_segment(nframes) {
            if pressure.len() + nframes > pressure.capacity() {
                overflow = true;
                drop(segment);
                break;
            }
            for frame in segment {
                escaped |=
                    (snapshot.start..snapshot.start + snapshot.capacity).contains(&frame.paddr());
                pressure.push(frame);
            }
        }
    }
    let layout = Layout::from_size_align(PAGE_SIZE, 2 * PAGE_SIZE).unwrap();
    while let Some(addr) = FrameAllocator.alloc(layout) {
        let frame = Frame::from_unused(addr, ()).unwrap();
        if pressure.len() == pressure.capacity() {
            overflow = true;
            drop(frame);
            break;
        }
        escaped |= (snapshot.start..snapshot.start + snapshot.capacity).contains(&addr);
        pressure.push(frame);
    }
    let ordinary_denied = [1, 2, 3, 4, 8]
        .into_iter()
        .all(|n| options.alloc_segment(n).is_err());
    let allocation = options.alloc_segment_from(&token, 64);
    let reserve_succeeded = allocation
        .as_ref()
        .is_ok_and(|s| s.paddr() == snapshot.start);
    let no_fallback = options.alloc_frame_from(&token).is_err();
    drop(allocation);
    let fully_refunded = token.snapshot().is_some_and(|s| s.allocated == 0);
    // Keep ordinary pressure alive through close. The released physical extent
    // must become allocatable by the original ordinary owner exactly once.
    token.close();
    let released = options.alloc_segment(64);
    let released_to_normal = released.as_ref().is_ok_and(|s| s.paddr() == snapshot.start);
    drop(released);
    let count = pressure.len();
    drop(pressure);
    drop(guard);
    assert!(
        !overflow,
        "preallocated bookkeeping insufficient; no exhaustion claim"
    );
    assert!(
        !escaped,
        "ordinary allocation consumed reserved physical memory"
    );
    assert!(count > 64);
    assert!(ordinary_denied);
    assert!(reserve_succeeded);
    assert!(no_fallback);
    assert!(fully_refunded);
    assert!(released_to_normal);
    assert!(token.snapshot().is_none());
    assert!(options.alloc_segment(64).is_ok());
    ostd::early_println!(
        "PHYSICAL_RESERVE_EXHAUSTION ordinary_frames={} reserve_start={:#x} reserve_pages=64 ordinary_denied=true reserved_succeeded=true returned_to_original_owner=true global_recovery_guarantee=false",
        count,
        snapshot.start,
    );
}
