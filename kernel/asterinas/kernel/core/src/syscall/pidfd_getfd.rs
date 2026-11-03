// SPDX-License-Identifier: MPL-2.0

use crate::{
    fs::file::file_table::{FdFlags, FileTable, RawFileDesc, get_file_fast},
    prelude::*,
    process::{
        PidFile,
        posix_thread::{AsPosixThread, alien_access::AlienAccessMode},
    },
    syscall::SyscallReturn,
};

pub(super) fn sys_pidfd_getfd(
    pidfd: RawFileDesc,
    targetfd: RawFileDesc,
    flags: u32,
    ctx: &Context,
) -> Result<SyscallReturn> {
    // The `flags` argument is reserved for future use. Currently, it must be specified as 0.
    if flags != 0 {
        return_errno_with_message!(Errno::EINVAL, "invalid flags");
    }
    debug!(
        "pidfd_getfd: pidfd={}, targetfd={}, flags={}",
        pidfd, targetfd, flags
    );

    let file = {
        let mut file_table = ctx.thread_local.borrow_file_table_mut();
        get_file_fast!(&mut file_table, pidfd.try_into()?).into_owned()
    };
    let Some(pid_file) = file.downcast_ref::<PidFile>() else {
        return_errno_with_message!(Errno::EBADF, "the file is not a PID file");
    };

    let process = pid_file
        .process_opt()
        .ok_or_else(|| Error::with_message(Errno::ESRCH, "the target process has been reaped"))?;

    let target_file = {
        let vmar = process.lock_vmar();
        let main_thread = process.main_thread();
        let target = main_thread.as_posix_thread().unwrap();
        let _access = target.check_alien_access_from(
            ctx.posix_thread,
            AlienAccessMode::ATTACH_WITH_REAL_CREDS,
            &vmar,
        )?;
        let table = target.file_table().lock();
        table
            .as_ref()
            .ok_or_else(|| Error::with_message(Errno::ESRCH, "the target process has exited"))?
            .read()
            .get_file(targetfd.try_into()?)?
            .clone()
    };

    // Duplicate the file descriptor into the caller's file descriptor table.
    let new_fd = FileTable::reserve_fd(ctx, FdFlags::CLOEXEC)?.install(target_file);

    Ok(SyscallReturn::Return(new_fd.into()))
}
