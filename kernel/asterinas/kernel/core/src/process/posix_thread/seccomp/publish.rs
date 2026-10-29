// SPDX-License-Identifier: MPL-2.0

use super::Program;
use crate::{
    prelude::*,
    process::{credentials::capabilities::CapSet, posix_thread::AsPosixThread},
    thread::AsThread,
};

pub(crate) fn publish_strict(ctx: &Context) -> Result<()> {
    let _update = ctx.process.seccomp_update().lock();
    if ctx.process.tasks().lock().in_execve() {
        return_errno_with_message!(Errno::EINTR, "seccomp publication interrupted by exec");
    }
    ctx.posix_thread.seccomp().lock().install_strict()
}

/// A positive result is the incompatible thread's TID, as in the Linux UAPI.
/// All eligibility checks precede every policy/no_new_privs mutation.
pub(crate) fn publish_filter(ctx: &Context, program: Program, sync: bool) -> Result<usize> {
    let _update = ctx.process.seccomp_update().lock();
    let tasks = ctx.process.tasks().lock();
    if tasks.in_execve() || tasks.has_exited_group() {
        return_errno_with_message!(Errno::EINTR, "seccomp publication interrupted by exec/exit");
    }
    let credentials = ctx.posix_thread.credentials();
    let no_new_privs = credentials.no_new_privs();
    if !no_new_privs && !credentials.effective_capset().contains(CapSet::SYS_ADMIN) {
        return_errno_with_message!(Errno::EACCES, "seccomp requires no_new_privs or SYS_ADMIN");
    }
    let previous = ctx.posix_thread.seccomp().lock().clone();
    let mut next = previous.clone();
    next.install_filter(program)?;
    if !sync {
        *ctx.posix_thread.seccomp().lock() = next;
        return Ok(0);
    }
    for task in tasks.as_slice() {
        if task.as_thread().unwrap().is_exited() {
            continue;
        }
        let thread = task.as_posix_thread().unwrap();
        if !thread.seccomp().lock().can_sync_from(&previous) {
            return Ok(thread.tid() as usize);
        }
    }
    for task in tasks.as_slice() {
        if task.as_thread().unwrap().is_exited() {
            continue;
        }
        let thread = task.as_posix_thread().unwrap();
        if no_new_privs {
            // This is solely the monotonic no_new_privs bit; it changes no ID,
            // capability or dumpability. Exec credential preparation is excluded
            // by _update. No writable credential capability escapes this owner.
            thread.credentials.set_no_new_privs();
        }
        *thread.seccomp().lock() = next.clone();
    }
    Ok(0)
}
