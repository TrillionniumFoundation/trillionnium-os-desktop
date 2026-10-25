// SPDX-License-Identifier: MPL-2.0

use core::{
    ops::Range,
    sync::atomic::{AtomicBool, Ordering},
};

use ostd::{
    cpu::CpuId,
    mm::{HasPaddr, VmIo},
    prelude::ktest,
    sync::RcuDrop,
    task::{Task, disable_preempt},
};

use super::{PageFaultInfo, RssType, Vmar, VmarHandle, VmarMapOffset};
use crate::{
    fs::pseudofs::SockFs,
    prelude::*,
    process::ProcessVm,
    thread::kernel_thread::ThreadOptions,
    vm::{
        page_cache::VmoOptions,
        perms::VmPerms,
        user_memory::{UserMemoryAccount, alloc_user_frame},
    },
};

fn vmar(account: &Arc<UserMemoryAccount>) -> VmarHandle {
    crate::time::clocks::init_for_ktest();
    crate::util::random::init();
    VmarHandle::new_with_owner(ProcessVm::new(SockFs::new_path()), Some(account.clone()))
}

fn hole(vmar: &Vmar, address: Vaddr) -> Range<Vaddr> {
    let guard = disable_preempt();
    let mut cursor = vmar
        .vm_space()
        .cursor_no_prealloc(&guard, &(address..address + PAGE_SIZE))
        .unwrap();
    let (range, item) = cursor.query().unwrap();
    assert!(item.is_none());
    range
}

fn mapped(vmar: &Vmar, address: Vaddr) -> (ostd::mm::UFrame, ostd::mm::PageProperty) {
    let guard = disable_preempt();
    let mut cursor = vmar
        .vm_space()
        .cursor_no_prealloc(&guard, &(address..address + PAGE_SIZE))
        .unwrap();
    let (_, Some(ostd::mm::vm_space::VmQueriedItem::MappedRam { frame, prop })) =
        cursor.query().unwrap()
    else {
        panic!("the successful fault must publish its original frame");
    };
    (frame.clone(), prop)
}

struct Grace(Arc<AtomicBool>);
impl Drop for Grace {
    fn drop(&mut self) {
        self.0.store(true, Ordering::Release);
    }
}
fn grace() {
    let done = Arc::new(AtomicBool::new(false));
    drop(RcuDrop::new(Grace(done.clone())));
    let worker = ThreadOptions::new(|| {})
        .cpu_affinity(CpuId::current_racy().into())
        .spawn();
    for _ in 0..128 {
        Task::yield_now();
        if done.load(Ordering::Acquire) && worker.is_exited() {
            break;
        }
    }
    assert!(done.load(Ordering::Acquire));
    assert!(worker.is_exited());
}

#[ktest]
fn denied_anonymous_and_vmo_faults_leave_original_empty_page_table_ranges() {
    let account = UserMemoryAccount::new(0);
    for with_vmo in [false, true] {
        let vmar = vmar(&account);
        let address = 0x4000_0000;
        let mut options = vmar
            .new_map(2 * PAGE_SIZE, VmPerms::READ | VmPerms::WRITE)
            .offset(VmarMapOffset::FixedNoReplace(address));
        if with_vmo {
            options = options
                .vmo(VmoOptions::new(2 * PAGE_SIZE).alloc().unwrap())
                .handle_page_faults_around();
        }
        assert_eq!(options.build().unwrap(), address);
        let before = hole(&vmar, address);
        assert!(before.len() > PAGE_SIZE);
        for perms in [VmPerms::WRITE, VmPerms::READ, VmPerms::READ] {
            let error = vmar
                .handle_page_fault(&PageFaultInfo::new(address, perms))
                .unwrap_err();
            assert!(error.is_user_frame_limit());
            assert_eq!(hole(&vmar, address), before);
            assert_eq!(account.current_pages(), 0);
            assert_eq!(vmar.get_rss_counter(RssType::Anon), 0);
            assert_eq!(vmar.get_rss_counter(RssType::File), 0);
        }
    }
}

#[ktest]
fn ordinary_fault_and_cow_keep_old_mapping_on_quota_denial_and_refund_last_frame() {
    let account = UserMemoryAccount::new(2);
    let vmar = vmar(&account);
    let address = vmar
        .new_map(PAGE_SIZE, VmPerms::READ | VmPerms::WRITE)
        .build()
        .unwrap();
    vmar.handle_page_fault(&PageFaultInfo::new(address, VmPerms::WRITE))
        .unwrap();
    let (original, _) = mapped(&vmar, address);
    original.write_bytes(0, &[91]).unwrap();
    assert_eq!(account.current_pages(), 1);
    crate::process::test_util::initialize_vmar_heap_for_fork(&vmar, 0x1000_0000);
    let child = Vmar::fork_from(&vmar);
    let (alias, before_prop) = mapped(&child, address);
    assert_eq!(alias.paddr(), original.paddr());
    drop(alias);
    let blocker = alloc_user_frame(&Some(account.clone()), true).unwrap();
    let error = child
        .handle_page_fault(&PageFaultInfo::new(address, VmPerms::WRITE))
        .unwrap_err();
    assert!(error.is_user_frame_limit());
    let (unchanged, prop) = mapped(&child, address);
    assert_eq!(unchanged.paddr(), original.paddr());
    assert_eq!(prop, before_prop);
    assert_eq!(child.get_rss_counter(RssType::Anon), 1);
    drop(unchanged);
    drop(blocker);
    child
        .handle_page_fault(&PageFaultInfo::new(address, VmPerms::WRITE))
        .unwrap();
    let (copy, _) = mapped(&child, address);
    assert_ne!(copy.paddr(), original.paddr());
    let mut byte = [0];
    copy.read_bytes(0, &mut byte).unwrap();
    assert_eq!(byte, [91]);
    assert_eq!(account.current_pages(), 2);
    assert_eq!(child.get_rss_counter(RssType::Anon), 1);
    drop(copy);
    drop(child);
    drop(vmar);
    grace();
    assert_eq!(account.current_pages(), 1);
    drop(original);
    assert_eq!(account.current_pages(), 0);
}

#[ktest]
fn fault_around_keeps_successful_prefix_and_charges_only_original_vmo_frame() {
    let account = UserMemoryAccount::new(1);
    let vmar = vmar(&account);
    let vmo = VmoOptions::new(3 * PAGE_SIZE).alloc().unwrap();
    let address = vmar
        .new_map(3 * PAGE_SIZE, VmPerms::READ)
        .vmo(vmo.clone())
        .handle_page_faults_around()
        .build()
        .unwrap();
    let error = vmar
        .handle_page_fault(&PageFaultInfo::new(address + PAGE_SIZE, VmPerms::READ))
        .unwrap_err();
    assert!(error.is_user_frame_limit());
    assert_eq!(vmar.get_rss_counter(RssType::File), 1);
    assert_eq!(account.current_pages(), 1);
    let (first, _) = mapped(&vmar, address);
    hole(&vmar, address + PAGE_SIZE);
    // An error for a surrounding page must not fail the already mapped fault page.
    vmar.handle_page_fault(&PageFaultInfo::new(address, VmPerms::READ))
        .unwrap();
    assert_eq!(vmar.get_rss_counter(RssType::File), 1);
    assert_eq!(account.current_pages(), 1);
    drop(vmar);
    drop(vmo);
    grace();
    assert_eq!(account.current_pages(), 1);
    drop(first);
    assert_eq!(account.current_pages(), 0);
}

#[derive(Debug, PartialEq)]
struct MappingSnapshot {
    range: Range<Vaddr>,
    mapped: Option<(ostd::mm::Paddr, ostd::mm::PageProperty)>,
}

// No assertion, formatting, allocation, or retained owning reference. The test
// VMAR is private and never activated; queries only lock existing table nodes.
fn mapping_snapshot(vmar: &Vmar, address: Vaddr) -> Option<MappingSnapshot> {
    let guard = disable_preempt();
    let mut cursor = vmar
        .vm_space()
        .cursor_no_prealloc(&guard, &(address..address + PAGE_SIZE))
        .ok()?;
    let (range, item) = cursor.query().ok()?;
    let mapped = match item {
        None => None,
        Some(ostd::mm::vm_space::VmQueriedItem::MappedRam { frame, prop }) => {
            Some((frame.paddr(), prop))
        }
        Some(_) => return None,
    };
    Some(MappingSnapshot { range, mapped })
}

#[ktest]
fn physical_page_table_nomemory_keeps_original_vmar_and_refunds_private_nodes() {
    use ostd::{cpu::num_cpus, irq, mm::FrameAllocOptions};

    use crate::vm::{
        page_cache::VmoMapMode,
        user_memory::hierarchy::{MemoryDomain, test_leaf},
        vmar::PageFaultError,
    };

    // This is the original bounded x86_64 N0 fixture. All heap bookkeeping and
    // user/VMO frames exist before pressure. No quota denial or injected failure.
    assert_eq!(num_cpus(), 1);
    assert!(!ostd::log_enabled!(ostd::log::Level::Debug));
    let parent = test_leaf(8);
    parent.set_delegated(true);
    let leaf = MemoryDomain::child(parent.clone()).unwrap();
    assert!(leaf.set_max(Some(8)));
    let account = UserMemoryAccount::new(8);
    account.move_to(
        leaf.clone(),
        &crate::fs::cgroupfs::CgroupMembership::write_lock(),
    );
    let vmar = vmar(&account);
    let old_address = 0x4000_0000;
    let address = 0x0080_0000_0000;
    vmar.new_map(PAGE_SIZE, VmPerms::READ | VmPerms::WRITE)
        .offset(VmarMapOffset::FixedNoReplace(old_address))
        .build()
        .unwrap();
    vmar.handle_page_fault(&PageFaultInfo::new(old_address, VmPerms::WRITE))
        .unwrap();
    let (old_frame, _) = mapped(&vmar, old_address);
    old_frame.write_bytes(0, &[91]).unwrap();
    let vmo = VmoOptions::new(PAGE_SIZE)
        .memory_owner(Some(account.clone()))
        .alloc()
        .unwrap();
    vmo.commit_on(0, VmoMapMode::Private).unwrap();
    let (data, _) = vmo.try_commit_page(0, VmoMapMode::Private).unwrap();
    data.write_bytes(0, &[37]).unwrap();
    vmar.new_map(PAGE_SIZE, VmPerms::READ)
        .vmo(vmo.clone())
        .offset(VmarMapOffset::FixedNoReplace(address))
        .build()
        .unwrap();
    let before_hole = mapping_snapshot(&vmar, address).unwrap();
    let before_old = mapping_snapshot(&vmar, old_address).unwrap();
    // A different x86 root slot requires all three child tables. Thus windows
    // with 0/1/2 available ordinary frames must fail at distinct real depths.
    assert_eq!(before_hole.range.len(), 1usize << 39);
    assert!(before_hole.mapped.is_none());
    let counters = || {
        [
            account.current_pages(),
            leaf.snapshot().pages,
            parent.snapshot().pages,
            vmar.get_rss_counter(RssType::Anon),
            vmar.get_rss_counter(RssType::File),
        ]
    };
    assert_eq!(counters(), [2, 2, 2, 1, 0]);
    let before_data_refs = data.reference_count();
    // 512 MiB contains at most this many physical pages. Capacity exhaustion is
    // an invalid fixture, never evidence of allocator exhaustion. The vector
    // buffer itself is acquired before disabling IRQs and is never grown.
    let mut pressure = Vec::with_capacity(512 * 1024 * 1024 / PAGE_SIZE + 1024);
    let mut options = FrameAllocOptions::new();
    options.zeroed(false);
    let mut cuts: [_; 3] = core::array::from_fn(|_| None);
    let mut overflow = false;
    let irq_guard = irq::disable_local();
    for nframes in [1, 2, 3, 4, 8] {
        while let Ok(segment) = options.alloc_segment(nframes) {
            if pressure.len() + nframes > pressure.capacity() {
                overflow = true;
                drop(segment);
                break;
            }
            for frame in segment {
                pressure.push(frame);
            }
        }
    }
    let held_count = pressure.len();
    let initially_unavailable = options.alloc_frame().is_err();
    for (available, cut) in cuts.iter_mut().enumerate() {
        let mut released = 0;
        for _ in 0..available {
            if let Some(frame) = pressure.pop() {
                drop(frame);
                released += 1;
            }
        }
        let error =
            match vmar.handle_page_fault_with_reason(&PageFaultInfo::new(address, VmPerms::READ)) {
                Err(PageFaultError::Other(error)) => Some((
                    error.error(),
                    error.is_user_frame_limit(),
                    error.is_cgroup_frame_limit(),
                )),
                _ => None,
            };
        let hole = mapping_snapshot(&vmar, address);
        let old = mapping_snapshot(&vmar, old_address);
        let after_counters = counters();
        let data_refs = data.reference_count();
        // Reacquire returned private nodes through the same real 4 KiB owner.
        // Fixed slots bound this even if a regression returns extra capacity.
        let mut returned = [None, None, None];
        let mut refunded = 0;
        for slot in &mut returned {
            match options.alloc_frame() {
                Ok(frame) => {
                    *slot = Some(frame);
                    refunded += 1;
                }
                Err(_) => break,
            }
        }
        let unavailable_again = options.alloc_frame().is_err();
        for frame in returned.into_iter().flatten() {
            if pressure.len() == pressure.capacity() {
                overflow = true;
                drop(frame);
            } else {
                pressure.push(frame);
            }
        }
        *cut = Some((
            released,
            error,
            hole,
            old,
            after_counters,
            data_refs,
            refunded,
            unavailable_again,
        ));
    }
    // Release the original owners before any assertion, log, scheduler action,
    // VMAR destruction, or heap bookkeeping destruction can run.
    pressure.clear();
    drop(irq_guard);
    drop(pressure);
    assert!(!overflow, "fixed bookkeeping exhausted; no qualification");
    assert!(held_count > 8);
    assert!(initially_unavailable);
    for (available, cut) in cuts.into_iter().enumerate() {
        let (released, error, hole, old, after_counters, data_refs, refunded, unavailable) =
            cut.unwrap();
        assert_eq!(released, available);
        assert_eq!(error, Some((Errno::ENOMEM, false, false)));
        assert_eq!(hole.as_ref(), Some(&before_hole));
        assert_eq!(old.as_ref(), Some(&before_old));
        assert_eq!(after_counters, [2, 2, 2, 1, 0]);
        assert_eq!(data_refs, before_data_refs);
        assert_eq!(refunded, available);
        assert!(unavailable);
    }
    vmar.handle_page_fault(&PageFaultInfo::new(address, VmPerms::READ))
        .unwrap();
    let (mapped_data, _) = mapped(&vmar, address);
    assert_eq!(mapped_data.paddr(), data.paddr());
    assert_eq!(counters(), [2, 2, 2, 1, 1]);
    assert_eq!(mapping_snapshot(&vmar, old_address), Some(before_old));
    let mut byte = [0];
    mapped_data.read_bytes(0, &mut byte).unwrap();
    assert_eq!(byte, [37]);
    old_frame.read_bytes(0, &mut byte).unwrap();
    assert_eq!(byte, [91]);
    drop(mapped_data);
    drop(vmar);
    drop(vmo);
    grace();
    assert_eq!(account.current_pages(), 2);
    drop(data);
    drop(old_frame);
    assert_eq!(account.current_pages(), 0);
    assert_eq!(leaf.snapshot().pages, 0);
    assert_eq!(parent.snapshot().pages, 0);
    ostd::early_println!(
        "VMAR_PHYSICAL_PT_NOMEMORY held_frames={} ordinary_4k_windows=0,1,2 unpublished_nodes_refunded=0,1,2 recovered=true global_recovery_guarantee=false",
        held_count,
    );
}
