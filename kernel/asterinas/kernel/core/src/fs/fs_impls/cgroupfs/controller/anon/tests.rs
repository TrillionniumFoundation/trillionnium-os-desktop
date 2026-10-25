// SPDX-License-Identifier: MPL-2.0

use ostd::{
    mm::{HasPaddr, io::util::HasVmReaderWriter},
    prelude::ktest,
};

use super::*;

fn used(budget: &AnonBudget) -> usize {
    budget.state.lock().current
}

#[ktest]
fn anon_real_frame_sharing_and_last_reference_refund() {
    let root = AnonBudget::new(None);
    let leaf = AnonBudget::new(Some(root.clone()));
    leaf.set_max(PAGE_SIZE).unwrap();
    let frame = allocate(Some(&leaf), true).unwrap();
    assert_eq!(used(&root), PAGE_SIZE);
    assert_eq!(used(&leaf), PAGE_SIZE);
    let child_mapping = frame.clone();
    drop(frame);
    assert_eq!(used(&leaf), PAGE_SIZE);
    assert!(allocate(Some(&leaf), true).is_err());
    drop(child_mapping);
    assert_eq!(used(&root), 0);
    assert_eq!(used(&leaf), 0);
    let next = allocate(Some(&leaf), true).unwrap();
    assert_eq!(used(&leaf), PAGE_SIZE);
    drop(next);
    assert_eq!(used(&leaf), 0);
}

#[ktest]
fn anon_ancestor_denial_rolls_back_descendant_reservations() {
    let root = AnonBudget::new(None);
    let middle = AnonBudget::new(Some(root.clone()));
    let leaf = AnonBudget::new(Some(middle.clone()));
    root.set_max(PAGE_SIZE).unwrap();
    let held = allocate(Some(&middle), true).unwrap();
    assert!(allocate(Some(&leaf), true).is_err());
    assert_eq!(used(&leaf), 0);
    assert_eq!(used(&middle), PAGE_SIZE);
    assert_eq!(used(&root), PAGE_SIZE);
    assert_eq!(root.state.lock().denied, 1);
    drop(held);
    let frame = allocate(Some(&leaf), true).unwrap();
    assert_eq!(used(&root), PAGE_SIZE);
    assert_eq!(used(&middle), PAGE_SIZE);
    drop(frame);
    assert_eq!(used(&root), 0);
    assert_eq!(used(&middle), 0);
    assert_eq!(used(&leaf), 0);
}

#[ktest]
fn anon_cow_allocates_distinct_page_and_keeps_origin_charge() {
    let root = AnonBudget::new(None);
    let parent = AnonBudget::new(Some(root.clone()));
    let child = AnonBudget::new(Some(parent.clone()));
    let original = allocate(Some(&parent), true).unwrap();
    original
        .writer()
        .write(&mut VmReader::from(&[0x3a_u8; 16][..]));
    let shared = original.clone();
    child.set_max(PAGE_SIZE).unwrap();
    let copy = allocate(Some(&child), false).unwrap();
    copy.writer().write(&mut shared.reader());
    assert_ne!(copy.paddr(), original.paddr());
    let mut bytes = [0_u8; 16];
    copy.reader().read(&mut VmWriter::from(&mut bytes[..]));
    assert_eq!(bytes, [0x3a; 16]);
    assert_eq!(used(&parent), 2 * PAGE_SIZE);
    assert_eq!(used(&child), PAGE_SIZE);
    drop(original);
    assert_eq!(used(&parent), 2 * PAGE_SIZE);
    drop(shared);
    assert_eq!(used(&parent), PAGE_SIZE);
    drop(copy);
    assert_eq!(used(&root), 0);
}

#[ktest]
fn anon_workload_exhaustion_preserves_sibling_recovery_capacity() {
    let root = AnonBudget::new(None);
    let workload = AnonBudget::new(Some(root.clone()));
    let recovery = AnonBudget::new(Some(root.clone()));
    root.set_max(3 * PAGE_SIZE).unwrap();
    workload.set_max(PAGE_SIZE).unwrap();
    recovery.set_max(2 * PAGE_SIZE).unwrap();
    let work = allocate(Some(&workload), true).unwrap();
    assert!(allocate(Some(&workload), true).is_err());
    let recovery_a = allocate(Some(&recovery), true).unwrap();
    let recovery_b = allocate(Some(&recovery), true).unwrap();
    assert_eq!(used(&root), 3 * PAGE_SIZE);
    assert!(allocate(Some(&recovery), true).is_err());
    drop((work, recovery_a, recovery_b));
    assert_eq!(used(&root), 0);
}

#[ktest]
fn anon_limits_reject_invalid_updates_and_survive_owner_release() {
    let root = AnonBudget::new(None);
    let leaf = AnonBudget::new(Some(root.clone()));
    let weak = Arc::downgrade(&leaf);
    let frame = allocate(Some(&leaf), true).unwrap();
    let mut reader = VmReader::from(&b"0"[..]).to_fallible();
    assert!(leaf.write_attr("hepta.anon.max", &mut reader).is_err());
    assert_eq!(leaf.state.lock().max, usize::MAX);
    for invalid in ["-1", "4096 garbage", "184467440737095516160"] {
        let mut reader = VmReader::from(invalid.as_bytes()).to_fallible();
        assert!(leaf.write_attr("hepta.anon.max", &mut reader).is_err());
    }
    let mut reader = VmReader::from(&b"4096\n"[..]).to_fallible();
    assert_eq!(leaf.write_attr("hepta.anon.max", &mut reader).unwrap(), 5);
    assert_eq!(leaf.state.lock().max, PAGE_SIZE);
    drop(leaf);
    assert!(weak.upgrade().is_some());
    drop(frame);
    assert!(weak.upgrade().is_none());
    assert_eq!(used(&root), 0);
}

#[ktest]
fn linux_memory_max_does_not_claim_partial_anon_coverage() {
    use super::super::{SubControl, SubControlStatic, memory::MemoryController};
    let memory = MemoryController::new(false, true);
    let mut reader = VmReader::from(&b"4096"[..]).to_fallible();
    assert!(memory.write_attr("memory.max", &mut reader).is_err());
}

#[ktest]
fn anon_compatibility_denial_rolls_back_combined_page_budget() {
    let anon = AnonBudget::new(None);
    let pages = PageMemoryBudget::new(None);
    let read_total = || {
        let mut bytes = [0_u8; 64];
        let length = pages
            .read_attr_at(
                "hepta.page.current",
                0,
                &mut VmWriter::from(&mut bytes[..]).to_fallible(),
            )
            .unwrap();
        core::str::from_utf8(&bytes[..length])
            .unwrap()
            .trim()
            .parse::<usize>()
            .unwrap()
    };
    anon.set_max(0).unwrap();
    assert!(allocate_accounted(&anon, &pages, true).is_err());
    assert_eq!(read_total(), 0);
    anon.set_max(PAGE_SIZE).unwrap();
    let frame = allocate_accounted(&anon, &pages, true).unwrap();
    assert_eq!(used(&anon), PAGE_SIZE);
    assert_eq!(read_total(), PAGE_SIZE);
    drop(frame);
    assert_eq!(used(&anon), 0);
    assert_eq!(read_total(), 0);
}
