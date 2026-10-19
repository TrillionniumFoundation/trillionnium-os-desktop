// SPDX-License-Identifier: MPL-2.0

use crate::{
    fs::file::{
        StatusFlags,
        file_table::{FdFlags, FileTable},
    },
    prelude::*,
    process::{Pid, PidFile, pid_table},
    syscall::SyscallReturn,
};

pub(super) fn sys_pidfd_open(pid: Pid, flags: u32, ctx: &Context) -> Result<SyscallReturn> {
    let is_nonblocking = {
        let flags = PidfdFlags::from_bits(flags)
            .ok_or_else(|| Error::with_message(Errno::EINVAL, "invalid flags"))?;
        debug!("pid = {}, flags = {:?}", pid, flags);
        flags.contains(PidfdFlags::PIDFD_NONBLOCK)
    };

    if pid.cast_signed() <= 0 {
        return_errno_with_message!(Errno::EINVAL, "non-positive PIDs are not valid");
    }

    let process = pid_table::pid_table_mut()
        .get_process(pid)
        .ok_or_else(|| Error::with_message(Errno::ESRCH, "the process does not exist"))?;

    let pid_fd = {
        let pid_file = Arc::new(PidFile::new(process, is_nonblocking));
        // "the close-on-exec flag is set on the file descriptor."
        // Reference: <https://man7.org/linux/man-pages/man2/pidfd_open.2.html>.
        FileTable::reserve_fd(ctx, FdFlags::CLOEXEC)?.install(pid_file)
    };

    Ok(SyscallReturn::Return(pid_fd.into()))
}

bitflags! {
    struct PidfdFlags: u32 {
        const PIDFD_NONBLOCK = StatusFlags::O_NONBLOCK.bits();
    }
}
