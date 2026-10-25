// SPDX-License-Identifier: MPL-2.0

pub(crate) use cgroup_ns::CgroupNamespace;
#[cfg(feature = "g1d-trusted-control")]
pub(crate) use controller::cpu::NativeCpuManager;
#[cfg(feature = "g1c-trusted-observe")]
pub(crate) use controller::cpu::{CpuUsageError, NativeCpuObserver};
pub(crate) use controller::{
    anon::alloc_anon_frame,
    cpu::{CpuChargeOwner, CpuStatKind, charge_cpu_time, task_cpu_eligible},
    page_memory::{PageCharge as MemoryPageCharge, PageKind, charge_current_pages},
};
use fs::CgroupFsType;
pub(in crate::fs) use systree_node::CgroupSystem;
pub(crate) use systree_node::{CgroupMembership, CgroupNode, CgroupSysNode};

// Set this module's log prefix for `ostd::log`.
macro_rules! __log_prefix {
    () => {
        "cgroup: "
    };
}

mod cgroup_ns;
mod controller;
mod fs;
mod inode;
mod systree_node;

// This method should be called during kernel file system initialization,
// _after_ `aster_systree::init`.
pub(super) fn init() {
    crate::fs::vfs::registry::register(&CgroupFsType).unwrap();
}
