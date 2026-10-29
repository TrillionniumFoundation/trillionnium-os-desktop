// SPDX-License-Identifier: MPL-2.0

use ostd::mm::VmIo;

use super::{
    SyscallReturn, sched_get_priority_max::static_to_rt, sched_getattr::update_sched_attr_with,
    sched_permissions::set_checked_policy,
};
use crate::{prelude::*, sched::SchedPolicy, thread::Tid};

pub(super) fn sys_sched_setparam(tid: Tid, addr: Vaddr, ctx: &Context) -> Result<SyscallReturn> {
    if addr == 0 {
        return_errno_with_message!(Errno::EINVAL, "invalid user space address");
    }

    let prio: i32 = ctx.user_space().read_val(addr)?;

    update_sched_attr_with(tid, ctx, |admin, target| {
        // Snapshot under the short policy spinlock, then validate outside it.
        let mut policy = admin.policy();
        let linux_policy = admin.user_policy();
        match &mut policy {
            SchedPolicy::RealTime { rt_prio, .. } => {
                *rt_prio = static_to_rt(prio as u32)?;
            }
            _ if prio != 0 => {
                return_errno_with_message!(Errno::EINVAL, "invalid scheduling priority")
            }
            _ => {}
        }
        set_checked_policy(admin, policy, linux_policy, target, ctx)
    })?;

    Ok(SyscallReturn::Return(0))
}
