// SPDX-License-Identifier: MPL-2.0

use super::{
    SyscallReturn,
    sched_getattr::{read_linux_sched_attr_from_user, update_sched_attr_with},
    sched_permissions::set_checked_policy,
};
use crate::{
    prelude::*,
    sched::{LinuxSchedPolicy, SchedPolicy},
    thread::Tid,
};

pub(super) fn sys_sched_setattr(
    tid: Tid,
    addr: Vaddr,
    flags: u32,
    ctx: &Context,
) -> Result<SyscallReturn> {
    if addr == 0 {
        return_errno_with_message!(Errno::EINVAL, "invalid user space address");
    }
    if flags != 0 {
        // Linux also has no support for any flags yet.
        return_errno_with_message!(Errno::EINVAL, "invalid flags");
    }

    let attr = read_linux_sched_attr_from_user(addr, ctx)?;
    let linux_policy = LinuxSchedPolicy::try_from(attr.sched_policy)?;
    let policy = SchedPolicy::try_from(attr)?;
    update_sched_attr_with(tid, ctx, |admin, target| {
        set_checked_policy(admin, policy, linux_policy, target, ctx)
    })?;

    Ok(SyscallReturn::Return(0))
}
