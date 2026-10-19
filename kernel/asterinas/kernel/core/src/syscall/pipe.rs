// SPDX-License-Identifier: MPL-2.0

use ostd::mm::VmIo;

use super::SyscallReturn;
use crate::{
    fs::{
        file::{
            CreationFlags, StatusFlags,
            file_table::{FdFlags, FileTable, RawFileDesc},
        },
        pipe,
    },
    prelude::*,
};

pub(super) fn sys_pipe2(fds: Vaddr, flags: u32, ctx: &Context) -> Result<SyscallReturn> {
    debug!("flags: {:?}", flags);

    const VALID_FLAGS: u32 = CreationFlags::O_CLOEXEC.bits()
        | StatusFlags::O_NONBLOCK.bits()
        | StatusFlags::O_DIRECT.bits();
    if flags & !VALID_FLAGS != 0 {
        return_errno_with_message!(Errno::EINVAL, "invalid pipe flags");
    }

    let status_flags = StatusFlags::from_bits_truncate(flags);
    let (pipe_reader, pipe_writer) = pipe::new_file_pair(status_flags)?;

    let creation_flags = CreationFlags::from_bits_truncate(flags);
    let fd_flags = if creation_flags.contains(CreationFlags::O_CLOEXEC) {
        FdFlags::CLOEXEC
    } else {
        FdFlags::empty()
    };

    let reader = FileTable::reserve_fd(ctx, fd_flags)?;
    let writer = FileTable::reserve_fd(ctx, fd_flags)?;
    let pipe_fds = PipeFds {
        reader_raw_fd: reader.fd().into(),
        writer_raw_fd: writer.fd().into(),
    };
    debug!("pipe_fds: {:?}", pipe_fds);

    // Reservations hold no table lock across user copyout and release both slots on error.
    ctx.user_space().write_val(fds, &pipe_fds)?;
    reader.install(pipe_reader);
    writer.install(pipe_writer);

    Ok(SyscallReturn::Return(0))
}

pub(super) fn sys_pipe(fds: Vaddr, ctx: &Context) -> Result<SyscallReturn> {
    sys_pipe2(fds, 0, ctx)
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod)]
struct PipeFds {
    reader_raw_fd: RawFileDesc,
    writer_raw_fd: RawFileDesc,
}
