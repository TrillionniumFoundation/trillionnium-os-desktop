// SPDX-License-Identifier: MPL-2.0

use ostd::{
    impl_untyped_frame_meta_for,
    mm::{FrameAllocOptions, UFrame},
    prelude::ktest,
    task::Task,
};

use super::*;
use crate::thread::kernel_thread::ThreadOptions;

#[derive(Debug)]
struct Charged {
    _charge: PageCharge,
}
impl_untyped_frame_meta_for!(Charged);

fn allocate(owner: &Arc<PageMemoryBudget>, kind: PageKind) -> Result<UFrame> {
    Ok(FrameAllocOptions::new()
        .alloc_frame_with(Charged {
            _charge: owner.charge(kind, PAGE_SIZE)?,
        })?
        .into())
}

fn used(owner: &PageMemoryBudget) -> usize {
    owner.state.lock().current
}

#[ktest]
fn page_budget_combines_three_real_frame_classes_and_refunds_last_reference() {
    let root = PageMemoryBudget::new(None);
    let leaf = PageMemoryBudget::new(Some(root.clone()));
    leaf.set_max(3 * PAGE_SIZE).unwrap();
    let private = allocate(&leaf, PageKind::Private).unwrap();
    let shared = allocate(&leaf, PageKind::AnonymousVmo).unwrap();
    let file = allocate(&leaf, PageKind::FileCache).unwrap();
    assert_eq!(used(&root), 3 * PAGE_SIZE);
    assert_eq!(
        leaf.state.lock().kinds,
        [PAGE_SIZE, PAGE_SIZE, PAGE_SIZE, 0, 0]
    );
    assert!(allocate(&leaf, PageKind::AnonymousVmo).is_err());
    let held = shared.clone();
    drop(shared);
    assert_eq!(used(&leaf), 3 * PAGE_SIZE);
    drop(held);
    assert_eq!(used(&leaf), 2 * PAGE_SIZE);
    assert_eq!(leaf.state.lock().kinds, [PAGE_SIZE, 0, PAGE_SIZE, 0, 0]);
    drop((private, file));
    assert_eq!(used(&root), 0);
    assert_eq!(leaf.state.lock().kinds, [0; 5]);
}

#[ktest]
fn page_budget_ancestor_denial_rolls_back_the_class_and_total() {
    let root = PageMemoryBudget::new(None);
    let leaf = PageMemoryBudget::new(Some(root.clone()));
    root.set_max(PAGE_SIZE).unwrap();
    let held = allocate(&root, PageKind::Private).unwrap();
    assert!(allocate(&leaf, PageKind::FileCache).is_err());
    assert_eq!(used(&leaf), 0);
    assert_eq!(leaf.state.lock().kinds, [0; 5]);
    assert_eq!(root.state.lock().denied, 1);
    drop(held);
    let next = allocate(&leaf, PageKind::FileCache).unwrap();
    assert_eq!(used(&root), PAGE_SIZE);
    drop(next);
    assert_eq!(used(&root), 0);
}

#[ktest]
fn page_budget_partial_segment_metadata_and_unused_tail_refund_exactly_once() {
    let root = PageMemoryBudget::new(None);
    let mut reservation = root.charge(PageKind::AnonymousVmo, 4 * PAGE_SIZE).unwrap();
    let first = FrameAllocOptions::new()
        .alloc_frame_with(Charged {
            _charge: reservation.split_page(),
        })
        .unwrap();
    let second = FrameAllocOptions::new()
        .alloc_frame_with(Charged {
            _charge: reservation.split_page(),
        })
        .unwrap();
    assert_eq!(used(&root), 4 * PAGE_SIZE);
    // The unused tail models early allocator/metadata-construction failure.
    // It does not claim that the physical allocator's global OOM was forced.
    drop(reservation);
    assert_eq!(used(&root), 2 * PAGE_SIZE);
    drop(first);
    assert_eq!(used(&root), PAGE_SIZE);
    drop(second);
    assert_eq!(used(&root), 0);
}

#[ktest]
fn page_budget_survives_owner_deletion_and_rejects_limit_reduction() {
    let root = PageMemoryBudget::new(None);
    let leaf = PageMemoryBudget::new(Some(root.clone()));
    let weak = Arc::downgrade(&leaf);
    let page = allocate(&leaf, PageKind::FileCache).unwrap();
    assert!(leaf.set_max(PAGE_SIZE - 1).is_err());
    for invalid in ["-1", "4096 junk", "184467440737095516160"] {
        let mut reader = VmReader::from(invalid.as_bytes()).to_fallible();
        assert!(leaf.write_attr("hepta.page.max", &mut reader).is_err());
    }
    drop(leaf);
    assert!(weak.upgrade().is_some());
    drop(page);
    assert!(weak.upgrade().is_none());
    assert_eq!(used(&root), 0);
}

#[ktest]
fn page_budget_recovery_sibling_has_capacity_after_mixed_workload_ceiling() {
    let root = PageMemoryBudget::new(None);
    let work = PageMemoryBudget::new(Some(root.clone()));
    let recovery = PageMemoryBudget::new(Some(root.clone()));
    root.set_max(4 * PAGE_SIZE).unwrap();
    work.set_max(3 * PAGE_SIZE).unwrap();
    recovery.set_max(PAGE_SIZE).unwrap();
    let a = allocate(&work, PageKind::Private).unwrap();
    let b = allocate(&work, PageKind::AnonymousVmo).unwrap();
    let c = allocate(&work, PageKind::FileCache).unwrap();
    assert!(allocate(&work, PageKind::Private).is_err());
    let recovered = allocate(&recovery, PageKind::AnonymousVmo).unwrap();
    assert_eq!(used(&root), 4 * PAGE_SIZE);
    drop((a, b, c, recovered));
    assert_eq!(used(&root), 0);
}

#[ktest]
fn page_budget_real_frames_contend_with_limit_updates_without_lost_refunds() {
    let root = PageMemoryBudget::new(None);
    root.set_max(8 * PAGE_SIZE).unwrap();
    let pinned = allocate(&root, PageKind::Private).unwrap();
    let mut workers = Vec::new();
    for kind in [
        PageKind::Private,
        PageKind::AnonymousVmo,
        PageKind::FileCache,
    ] {
        let owner = root.clone();
        workers.push(
            ThreadOptions::new(move || {
                for _ in 0..128 {
                    if let Ok(page) = allocate(&owner, kind) {
                        Task::yield_now();
                        drop(page);
                    }
                    Task::yield_now();
                }
            })
            .spawn(),
        );
    }
    for _ in 0..128 {
        assert!(root.set_max(0).is_err());
        let _ = root.set_max(2 * PAGE_SIZE);
        assert!(used(&root) <= 8 * PAGE_SIZE);
        root.set_max(8 * PAGE_SIZE).unwrap();
        Task::yield_now();
    }
    for _ in 0..10000 {
        if workers.iter().all(|worker| worker.is_exited()) {
            break;
        }
        Task::yield_now();
    }
    assert!(workers.iter().all(|worker| worker.is_exited()));
    assert_eq!(used(&root), PAGE_SIZE);
    drop(pinned);
    assert_eq!(used(&root), 0);
}

#[ktest]
fn page_budget_real_contiguous_segment_retains_each_frame_charge() {
    let owner = PageMemoryBudget::new(None);
    let mut reservation = owner.charge(PageKind::AnonymousVmo, 4 * PAGE_SIZE).unwrap();
    let segment = FrameAllocOptions::new()
        .alloc_segment_with(4, |_| Charged {
            _charge: reservation.split_page(),
        })
        .unwrap();
    drop(reservation);
    let mut frames = segment.into_iter().collect::<Vec<_>>();
    assert_eq!(used(&owner), 4 * PAGE_SIZE);
    let held = frames[0].clone();
    frames.clear();
    assert_eq!(used(&owner), PAGE_SIZE);
    drop(held);
    assert_eq!(used(&owner), 0);
}

#[derive(Debug)]
struct StackCharged {
    _charge: Box<dyn ostd::task::StackPageCharge>,
}
ostd::impl_frame_meta_for!(StackCharged);

#[ktest]
fn page_budget_stack_split_preserves_ancestors_and_final_frame_ownership() {
    let root = PageMemoryBudget::new(None);
    let leaf = PageMemoryBudget::new(Some(root.clone()));
    root.set_max(3 * PAGE_SIZE).unwrap();
    let mut reservation = leaf.charge(PageKind::KernelStack, 3 * PAGE_SIZE).unwrap();
    let frames = FrameAllocOptions::new()
        .alloc_segment_with(2, |_| StackCharged {
            _charge: ostd::task::StackReservation::split_page(&mut reservation),
        })
        .unwrap()
        .into_iter()
        .collect::<Vec<_>>();
    for owner in [&root, &leaf] {
        assert_eq!(used(owner), 3 * PAGE_SIZE);
        assert_eq!(owner.state.lock().kinds, [0, 0, 0, 0, 3 * PAGE_SIZE]);
    }
    // The unused reservation tail is real owned budget, independent of the
    // initialized physical frames. This does not force allocator-global OOM.
    drop(reservation);
    let held = frames[0].clone();
    drop(frames);
    for owner in [&root, &leaf] {
        assert_eq!(used(owner), PAGE_SIZE);
        assert_eq!(owner.state.lock().kinds, [0, 0, 0, 0, PAGE_SIZE]);
    }
    drop(held);
    for owner in [&root, &leaf] {
        assert_eq!(used(owner), 0);
        assert_eq!(owner.state.lock().kinds, [0; 5]);
    }
}
