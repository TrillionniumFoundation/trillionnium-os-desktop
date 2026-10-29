// SPDX-License-Identifier: MPL-2.0

use super::{
    SyscallReturn,
    get_priority::{PriorityTarget, PriorityThread, get_priority_threads},
    sched_permissions::{nice_rlimit, require_sys_nice},
};
use crate::{
    prelude::*,
    process::{ResourceType::RLIMIT_NICE, posix_thread::AsPosixThread},
    sched::Nice,
};

pub(super) fn sys_set_priority(
    which: i32,
    who: u32,
    prio: i32,
    ctx: &Context,
) -> Result<SyscallReturn> {
    let targets = get_priority_threads(PriorityTarget::new(which, who, ctx)?)?;
    let new_nice = Nice::try_from(prio.clamp(-20, 19) as i8)
        .expect("clamped nice must be in the supported range");
    // Linux set_one_prio applies every permitted target. A success clears the
    // initial ESRCH only; it never erases a previous target's failure. The last
    // encountered failure wins, independently of subsequent successful writes.
    let mut failure = None;
    for target in targets {
        if let Err(error) = set_one_priority(&target, new_nice, ctx) {
            failure = Some(error);
        }
    }
    if let Some(error) = failure {
        return Err(error);
    }
    Ok(SyscallReturn::Return(0))
}

fn set_one_priority(target: &PriorityThread, nice: Nice, ctx: &Context) -> Result<()> {
    let same_owner = {
        let credentials = target
            .thread
            .as_posix_thread()
            .ok_or(Errno::ESRCH)?
            .credentials();
        let caller = ctx.posix_thread.credentials().euid();
        caller == credentials.ruid() || caller == credentials.euid()
    };
    if !same_owner && require_sys_nice(&target.process, ctx).is_err() {
        return_errno_with_message!(Errno::EPERM, "priority target ownership is not authorized");
    }
    let mut admin = target.thread.sched_attr().administer();
    let limit = target
        .process
        .resource_limits()
        .get_rlimit(RLIMIT_NICE)
        .get_cur();
    if nice < admin.nice()
        && nice_rlimit(nice) > limit
        && require_sys_nice(&target.process, ctx).is_err()
    {
        return_errno_with_message!(
            Errno::EACCES,
            "priority increase exceeds the target nice limit"
        );
    }
    // Static nice changes on RT/declared Idle retain their original class;
    // ordinary Fair updates publish its actual scheduling weight as well.
    admin.set_nice(nice);
    Ok(())
}
