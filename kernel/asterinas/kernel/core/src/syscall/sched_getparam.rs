// SPDX-License-Identifier: MPL-2.0

use ostd::mm::VmIo;

use super::{
    SyscallReturn,
    sched_getattr::{LinuxSchedAttr, access_sched_attr_with},
};
use crate::{prelude::*, thread::Tid};

pub(super) fn sys_sched_getparam(tid: Tid, addr: Vaddr, ctx: &Context) -> Result<SyscallReturn> {
    if addr == 0 {
        return_errno_with_message!(Errno::EINVAL, "invalid user space address");
    }

    let snapshot = access_sched_attr_with(tid, ctx, |attr| Ok(attr.user_snapshot()))?;
    let rt_prio = LinuxSchedAttr::try_from(snapshot)?.sched_priority;

    ctx.user_space().write_val(addr, &rt_prio)?;

    Ok(SyscallReturn::Return(0))
}
