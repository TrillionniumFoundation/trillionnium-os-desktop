// SPDX-License-Identifier: MPL-2.0

use super::SyscallReturn;
use crate::{
    prelude::*,
    process::{
        ProcessFilter, kill_all_with, kill_group_with, kill_owned_with,
        signal::{
            sig_num::SigNum,
            signals::{
                OwnedSignal,
                user::{UserSignal, UserSignalKind},
            },
        },
    },
};

pub(super) fn sys_kill(process_filter: i32, sig_num: i32, ctx: &Context) -> Result<SyscallReturn> {
    let filter = ProcessFilter::from_id(process_filter)?;
    // Linux validates the full int signal after locating a target. Preparing
    // inside the original helper keeps invalid sends side-effect free.
    // Capture payload fields before the group helper takes membership locks.
    // Actual permission checks still read credentials through the original path.
    let sender_pid = ctx.process.pid();
    let sender_uid = ctx.posix_thread.credentials().ruid();
    let prepare = || {
        let signum = if sig_num == 0 {
            None
        } else {
            Some(SigNum::try_from(sig_num)?)
        };
        Ok(signum.map(|num| {
            OwnedSignal::new(UserSignal::new(
                num,
                UserSignalKind::Kill,
                sender_pid,
                sender_uid,
            ))
        }))
    };
    match filter {
        ProcessFilter::Any => kill_all_with(prepare, ctx)?,
        ProcessFilter::WithPid(pid) => kill_owned_with(pid, None, prepare, ctx)?,
        ProcessFilter::WithPgid(pgid) => kill_group_with(pgid, None, prepare, ctx)?,
        ProcessFilter::WithPidfd(_) => unreachable!(),
    }
    Ok(SyscallReturn::Return(0))
}
