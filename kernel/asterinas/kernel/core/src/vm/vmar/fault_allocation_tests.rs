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
