// SPDX-License-Identifier: MPL-2.0

use aster_systree::{SysBranchNode, SysNode, SysObj};
use ostd::{prelude::ktest, task::Task};

use super::*;
use crate::{
    fs::{
        cgroupfs::{CgroupMembership, CgroupNode, CgroupSysNode, CgroupSystem},
        pseudofs::SockFs,
    },
    prelude::*,
    process::{Process, ProcessVm, posix_thread::AsPosixThread, test_util},
    vm::{
        perms::VmPerms,
        user_memory::{UserMemoryAccount, alloc_user_frame},
        vmar::{Vmar, VmarHandle, VmarMapOffset},
    },
};

struct Fixture {
    root: &'static Arc<CgroupSystem>,
    parent: Arc<CgroupNode>,
    leaf: Arc<CgroupNode>,
    enabled: bool,
}
impl Fixture {
    fn new() -> Self {
        let root = CgroupSystem::singleton();
        let enabled = !root
            .controller()
            .active_set()
            .contains_type(super::super::SubCtrlType::Memory);
        if enabled {
            root.store_attr("cgroup.subtree_control", "+memory")
                .unwrap();
        }
        let parent =
            Arc::downcast::<CgroupNode>(root.create_child("memory-native-regression").unwrap())
                .unwrap();
        parent
            .store_attr("cgroup.subtree_control", "+memory")
            .unwrap();
        let leaf = Arc::downcast::<CgroupNode>(parent.create_child("leaf").unwrap()).unwrap();
        Self {
            root,
            parent,
            leaf,
            enabled,
        }
    }
    fn other(&self) -> Arc<CgroupNode> {
        Arc::downcast::<CgroupNode>(self.parent.create_child("other").unwrap()).unwrap()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        self.leaf
            .mark_as_dead(&mut CgroupMembership::write_lock())
            .unwrap();
        self.parent.remove_child("leaf").unwrap();
        self.parent
            .mark_as_dead(&mut CgroupMembership::write_lock())
            .unwrap();
        self.root.remove_child("memory-native-regression").unwrap();
        if self.enabled {
            self.root
                .store_attr("cgroup.subtree_control", "-memory")
                .unwrap();
        }
    }
}
fn cleanup(process: Arc<Process>, task: Arc<Task>) {
    CgroupMembership::write_lock().move_process_to_root(&process);
    task.as_posix_thread().unwrap().set_cpu_cgroup(None);
    drop((task, process));
    // PosixThread::set_cpu_cgroup publishes through RcuOption. Even this
    // unstarted task can leave CpuCgroupLease references queued for a grace
    // period after migration. Wait for the original RCU destructor queue,
    // without weakening mark_as_dead's final CPU-owner protection below.
    crate::vm::user_memory::hierarchy::test_wait_for_rcu_refunds();
}

#[ktest]
fn memory_files_round_bytes_reject_lowering_and_bound_depth_before_publication() {
    let f = Fixture::new();
    assert_eq!(f.leaf.show_attr("memory.max").unwrap(), "max\n");
    assert_eq!(f.leaf.show_attr("memory.current").unwrap(), "0\n");
    assert!(f.leaf.node_attrs().get("memory.stat").is_none());
    f.leaf.store_attr("memory.max", "1").unwrap();
    assert_eq!(f.leaf.show_attr("memory.max").unwrap(), "4096\n");
    for bad in ["", "-1", "+1", "1 2", "18446744073709551615"] {
        assert!(f.leaf.store_attr("memory.max", bad).is_err());
    }
    let owner = UserMemoryAccount::new(2);
    owner.move_to(
        f.leaf.controller().memory_domain().clone(),
        &CgroupMembership::write_lock(),
    );
    let frame = alloc_user_frame(&Some(owner.clone()), true).unwrap();
    assert!(f.leaf.store_attr("memory.max", "0").is_err());
    assert_eq!(f.leaf.show_attr("memory.max").unwrap(), "4096\n");
    assert!(alloc_user_frame(&Some(owner), true).is_err());
    assert_eq!(f.leaf.show_attr("memory.events").unwrap(), "max 1\n");
    f.parent
        .store_attr("cgroup.subtree_control", "-memory")
        .unwrap();
    assert!(f.leaf.is_attr_absent("memory.max"));
    f.parent
        .store_attr("cgroup.subtree_control", "+memory")
        .unwrap();
    assert_eq!(f.leaf.show_attr("memory.current").unwrap(), "4096\n");
    drop(frame);
    assert_eq!(f.leaf.show_attr("memory.current").unwrap(), "0\n");

    let mut nodes = vec![f.leaf.clone()];
    for _ in 2..64 {
        let node = Arc::downcast::<CgroupNode>(nodes.last().unwrap().create_child("next").unwrap())
            .unwrap();
        nodes.push(node);
    }
    assert!(nodes.last().unwrap().create_child("rejected").is_err());
    assert!(nodes.last().unwrap().children().is_empty());
    while nodes.len() > 1 {
        let last = nodes.pop().unwrap();
        last.mark_as_dead(&mut CgroupMembership::write_lock())
            .unwrap();
        nodes.last().unwrap().remove_child("next").unwrap();
    }
}

#[ktest]
fn migration_changes_only_future_allocations_and_failed_target_preserves_membership() {
    let f = Fixture::new();
    let other = f.other();
    f.leaf.store_attr("memory.max", "4096").unwrap();
    other.store_attr("memory.max", "0").unwrap();
    let (process, task) = test_util::new_unstarted_process();
    CgroupMembership::write_lock()
        .move_process_to_node(process.clone(), &f.leaf)
        .unwrap();
    let owner = process.user_memory_owner().clone();
    let old_frame = alloc_user_frame(&owner, true).unwrap();
    CgroupMembership::write_lock()
        .move_process_to_node(process.clone(), &other)
        .unwrap();
    assert_eq!(f.leaf.show_attr("memory.current").unwrap(), "4096\n");
    assert_eq!(other.show_attr("memory.current").unwrap(), "0\n");
    assert!(
        alloc_user_frame(&owner, true)
            .unwrap_err()
            .is_user_frame_limit()
    );
    assert_eq!(process.cgroup().get().unwrap().id(), other.id());
    // Parent has subtree_control enabled and cannot contain processes. Rejection
    // must leave both the original membership and allocation binding untouched.
    assert!(
        CgroupMembership::write_lock()
            .move_process_to_node(process.clone(), &f.parent)
            .is_err()
    );
    assert_eq!(process.cgroup().get().unwrap().id(), other.id());
    assert!(alloc_user_frame(&owner, true).is_err());
    CgroupMembership::write_lock()
        .try_move_process_to_root(&process)
        .unwrap();
    assert!(process.cgroup().get().is_none());
    drop(alloc_user_frame(&owner, true).unwrap());
    drop(old_frame);
    assert_eq!(f.parent.show_attr("memory.current").unwrap(), "0\n");
    cleanup(process, task);
    other
        .mark_as_dead(&mut CgroupMembership::write_lock())
        .unwrap();
    f.parent.remove_child("other").unwrap();
}

#[ktest]
fn fork_has_independent_binding_and_clone_vm_processes_cannot_split_membership() {
    let f = Fixture::new();
    let other = f.other();
    let owner = UserMemoryAccount::new(4);
    owner.move_to(
        f.leaf.controller().memory_domain().clone(),
        &CgroupMembership::write_lock(),
    );
    let vmar = VmarHandle::new_with_owner(ProcessVm::new(SockFs::new_path()), Some(owner));
    let (first, first_task, second, second_task) = {
        let _membership = CgroupMembership::read_lock();
        let (first, first_task) = test_util::new_unstarted_process_in_vmar(vmar.clone_handle());
        let (second, second_task) = test_util::new_unstarted_process_in_vmar(vmar.clone_handle());
        (first, first_task, second, second_task)
    };
    let mut membership = CgroupMembership::write_lock();
    membership
        .move_process_to_node(first.clone(), &f.leaf)
        .unwrap();
    membership
        .move_process_to_node(second.clone(), &f.leaf)
        .unwrap();
    assert!(
        membership
            .move_process_to_node(first.clone(), &other)
            .is_err()
    );
    assert!(membership.try_move_process_to_root(&first).is_err());
    assert_eq!(first.cgroup().get().unwrap().id(), f.leaf.id());
    assert_eq!(second.cgroup().get().unwrap().id(), f.leaf.id());
    drop(membership);
    test_util::initialize_heap_for_fork(&first, 0x800000);
    const BASE: usize = 0x400000;
    vmar.new_map(PAGE_SIZE, VmPerms::READ | VmPerms::WRITE)
        .offset(VmarMapOffset::FixedNoReplace(BASE))
        .build()
        .unwrap();
    vmar.write_alien(BASE, &mut VmReader::from(&[7u8][..]).to_fallible())
        .unwrap();
    assert_eq!(f.leaf.show_attr("memory.current").unwrap(), "4096\n");
    let child_vmar = {
        let _membership = CgroupMembership::read_lock();
        Vmar::fork_from(&vmar)
    };
    let (child, child_task) = {
        let _membership = CgroupMembership::read_lock();
        test_util::new_unstarted_process_in_vmar(child_vmar)
    };
    CgroupMembership::write_lock()
        .move_process_to_node(child.clone(), &other)
        .unwrap();
    assert_eq!(other.show_attr("memory.current").unwrap(), "0\n");
    child
        .lock_vmar()
        .unwrap()
        .write_alien(BASE, &mut VmReader::from(&[9u8][..]).to_fallible())
        .unwrap();
    assert_eq!(other.show_attr("memory.current").unwrap(), "4096\n");
    assert_eq!(f.leaf.show_attr("memory.current").unwrap(), "4096\n");
    let mut original = [0u8; 1];
    vmar.read_alien(BASE, &mut VmWriter::from(&mut original[..]).to_fallible())
        .unwrap();
    assert_eq!(original, [7]);
    assert_eq!(
        first.user_memory_owner().as_ref().unwrap().current_pages(),
        2
    );
    cleanup(child, child_task);
    cleanup(second, second_task);
    CgroupMembership::write_lock()
        .move_process_to_node(first.clone(), &other)
        .unwrap();
    cleanup(first, first_task);
    drop(vmar);
    crate::vm::user_memory::hierarchy::test_wait_for_rcu_refunds();
    assert_eq!(other.show_attr("memory.current").unwrap(), "0\n");
    assert_eq!(f.leaf.show_attr("memory.current").unwrap(), "0\n");
    other
        .mark_as_dead(&mut CgroupMembership::write_lock())
        .unwrap();
    f.parent.remove_child("other").unwrap();
}
