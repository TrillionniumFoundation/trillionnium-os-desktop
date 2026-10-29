// SPDX-License-Identifier: MPL-2.0

use ostd::mm::VmIo;

use super::{
    SyscallReturn,
    sched_getattr::{LinuxSchedAttr, update_sched_attr_with},
    sched_permissions::set_checked_policy,
};
use crate::{prelude::*, sched::LinuxSchedPolicy, thread::Tid};

pub(super) fn sys_sched_setscheduler(
    tid: Tid,
    policy: i32,
    addr: Vaddr,
    ctx: &Context,
) -> Result<SyscallReturn> {
    if addr == 0 {
        return_errno_with_message!(Errno::EINVAL, "invalid user space address");
    }

    let prio = ctx.user_space().read_val(addr)?;

    let linux_policy = LinuxSchedPolicy::try_from(policy as u32)?;
    update_sched_attr_with(tid, ctx, |admin, target| {
        let attr = LinuxSchedAttr {
            sched_policy: policy as u32,
            sched_priority: prio,
            sched_nice: admin.nice().value().get().into(),
            ..Default::default()
        };
        set_checked_policy(admin, attr.try_into()?, linux_policy, target, ctx)
    })?;

    Ok(SyscallReturn::Return(0))
}
