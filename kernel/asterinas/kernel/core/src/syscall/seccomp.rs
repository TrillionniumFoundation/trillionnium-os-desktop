// SPDX-License-Identifier: MPL-2.0

use ostd::{arch::cpu::context::UserContext, mm::VmIo, user::UserContextApi};

use super::SyscallReturn;
use crate::{
    cpu::LinuxAbi,
    prelude::*,
    process::{
        TermStatus,
        credentials::capabilities::CapSet,
        posix_thread::{
            do_exit, do_exit_group,
            seccomp::{self, Action, Data, Instruction, Program},
        },
        signal::constants::SIGSYS,
    },
};

#[padding_struct]
#[repr(C)]
#[derive(Clone, Copy, Pod)]
struct SockFprog {
    len: u16,
    filter: Vaddr,
}

pub(super) fn sys_seccomp(
    operation: u32,
    flags: u32,
    args: Vaddr,
    ctx: &Context,
) -> Result<SyscallReturn> {
    if !cfg!(target_arch = "x86_64") {
        return_errno_with_message!(Errno::ENOSYS, "seccomp architecture not yet qualified");
    }
    if flags != 0 {
        // In particular, never pretend that TSYNC or NEW_LISTENER succeeded.
        return_errno_with_message!(Errno::EINVAL, "unsupported seccomp flags");
    }
    match operation {
        0 => {
            if args != 0 {
                return_errno_with_message!(Errno::EINVAL, "strict seccomp args must be null");
            }
            install(1, 0, ctx)?;
        }
        1 => install(2, args, ctx)?,
        2 => {
            let action: u32 = ctx.user_space().read_val(args)?;
            if !matches!(
                action,
                seccomp::KILL_THREAD | seccomp::KILL_PROCESS | seccomp::ERRNO | seccomp::ALLOW
            ) {
                return_errno_with_message!(Errno::EOPNOTSUPP, "seccomp action unavailable");
            }
        }
        _ => return_errno_with_message!(Errno::EINVAL, "unsupported seccomp operation"),
    }
    Ok(SyscallReturn::Return(0))
}

pub(super) fn install(mode: u32, address: Vaddr, ctx: &Context) -> Result<()> {
    if !cfg!(target_arch = "x86_64") {
        return_errno_with_message!(Errno::ENOSYS, "seccomp architecture not yet qualified");
    }
    match mode {
        1 => ctx.posix_thread.seccomp().lock().install_strict(),
        2 => {
            {
                let credentials = ctx.posix_thread.credentials();
                if !credentials.no_new_privs()
                    && !credentials.effective_capset().contains(CapSet::SYS_ADMIN)
                {
                    return_errno_with_message!(
                        Errno::EACCES,
                        "seccomp requires no_new_privs or SYS_ADMIN"
                    );
                }
            }
            let user_space = ctx.user_space();
            let descriptor: SockFprog = user_space.read_val(address)?;
            let count = descriptor.len as usize;
            if count == 0 || count > seccomp::MAX_PROGRAM_INSNS {
                return_errno_with_message!(Errno::EINVAL, "invalid seccomp program length");
            }
            // Copy all bytes before verification/publication. The pointer and
            // program may change afterwards without mutating an installed filter.
            let mut reader =
                user_space.reader(descriptor.filter, count * size_of::<Instruction>())?;
            let mut instructions = Vec::with_capacity(count);
            for _ in 0..count {
                instructions.push(reader.read_val()?);
            }
            let program = Program::verify(instructions)?;
            ctx.posix_thread.seccomp().lock().install_filter(program)
        }
        _ => return_errno_with_message!(Errno::EINVAL, "invalid seccomp mode"),
    }
}

/// Filter before dispatch, including unknown syscall numbers. A rejected call
/// never enters its handler; no signal or blocking work runs under the lock.
pub(super) fn check_entry(
    number: u64,
    args: [u64; 6],
    ctx: &Context,
    user_ctx: &mut UserContext,
) -> bool {
    let policy = ctx.posix_thread.seccomp().lock().clone();
    // Installation is currently x86-64 only. Other architectures retain the
    // disabled policy and explicitly refuse installation above.
    let data = Data::new(
        number,
        0xc000_003e,
        user_ctx.instruction_pointer() as u64,
        args,
    );
    let strict_allowed = matches!(number, 0 | 1 | 15 | 60);
    match policy.evaluate(&data, strict_allowed) {
        Action::Allow => true,
        Action::Errno(errno) => {
            user_ctx.set_syscall_ret((-(errno as isize)) as usize);
            false
        }
        Action::KillThread => {
            do_exit(TermStatus::Killed(SIGSYS), ctx, user_ctx);
            false
        }
        Action::KillProcess => {
            do_exit_group(TermStatus::Killed(SIGSYS), ctx, user_ctx);
            false
        }
    }
}
