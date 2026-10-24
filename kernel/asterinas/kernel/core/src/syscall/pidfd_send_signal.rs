// SPDX-License-Identifier: MPL-2.0

use ostd::mm::VmIo;

use crate::{
    fs::file::file_table::{RawFileDesc, get_file_fast},
    prelude::*,
    process::{
        Pgid, Pid, PidFile, Process, kill_group_with, kill_owned_with,
        posix_thread::AsPosixThread,
        signal::{
            c_types::siginfo_t,
            constants::SI_TKILL,
            sig_num::SigNum,
            signals::{
                OwnedSignal, Signal,
                raw::RawSignal,
                user::{UserSignal, UserSignalKind},
            },
        },
        tgkill_owned_with,
    },
    syscall::SyscallReturn,
    thread::Tid,
};

pub(super) fn sys_pidfd_send_signal(
    pidfd: RawFileDesc,
    sig_num: i32,
    info_ptr: Vaddr,
    flags: u32,
    ctx: &Context,
) -> Result<SyscallReturn> {
    let flags = PidfdSendSignalFlags::try_from(flags)?;
    // Resolve the fd and hold its original Process identity before user-memory
    // access. A reaped target stays absent; its numeric PID is never authority.
    let target = get_target_from_pidfd(pidfd, flags, ctx)?;
    let raw_info = if info_ptr != 0 {
        let info = ctx.user_space().read_val::<siginfo_t>(info_ptr)?;
        if info.si_signo != sig_num {
            return_errno!(Errno::EINVAL);
        }
        let is_self = match &target {
            SignalTarget::Thread { tid, .. } => *tid == ctx.posix_thread.tid(),
            SignalTarget::Process { process } => process.pid() == ctx.posix_thread.tid(),
            SignalTarget::ProcessGroup { .. } | SignalTarget::Exited => false,
        };
        if !is_self && (info.si_code >= 0 || info.si_code == SI_TKILL) {
            return_errno!(Errno::EPERM);
        }
        Some(info)
    } else {
        None
    };
    // Linux copies and checks supplied siginfo even for signal zero, then
    // resolves the live target before checking the full signed signal number.
    let sender_pid = ctx.process.pid();
    let sender_uid = ctx.posix_thread.credentials().ruid();
    let prepare = || {
        if sig_num == 0 {
            return Ok(None);
        }
        let num = SigNum::try_from(sig_num)?;
        let info = raw_info.unwrap_or_else(|| {
            UserSignal::new(num, UserSignalKind::Kill, sender_pid, sender_uid).to_info()
        });
        Ok(Some(OwnedSignal::new(RawSignal::new(info))))
    };
    match target {
        SignalTarget::Thread { tid, tgid, process } => {
            tgkill_owned_with(tid, Some(tgid), Some(&process), prepare, ctx)?;
        }
        SignalTarget::Process { process } => {
            kill_owned_with(process.pid(), Some(&process), prepare, ctx)?;
        }
        SignalTarget::ProcessGroup { pgid, process } => {
            kill_group_with(pgid, Some(&process), prepare, ctx)?;
        }
        SignalTarget::Exited => return_errno!(Errno::ESRCH),
    }
    Ok(SyscallReturn::Return(0))
}

fn get_target_from_pidfd(
    pidfd: RawFileDesc,
    flags: PidfdSendSignalFlags,
    ctx: &Context,
) -> Result<SignalTarget> {
    // Helper closures to create signal targets.
    let thread_target = |tid: Tid, process: Arc<Process>| SignalTarget::Thread {
        tid,
        tgid: process.pid(),
        process,
    };
    let process_target = |process: Arc<Process>| SignalTarget::Process { process };
    let group_target =
        |pgid: Pgid, process: Arc<Process>| SignalTarget::ProcessGroup { pgid, process };

    let target = match pidfd {
        PIDFD_SELF_THREAD => match flags {
            PidfdSendSignalFlags::Default | PidfdSendSignalFlags::Thread => {
                thread_target(ctx.posix_thread.tid(), ctx.process.clone())
            }
            PidfdSendSignalFlags::ThreadGroup => process_target(ctx.process.clone()),
            PidfdSendSignalFlags::ProcessGroup => {
                group_target(ctx.posix_thread.tid(), ctx.process.clone())
            }
        },
        PIDFD_SELF_THREAD_GROUP => match flags {
            PidfdSendSignalFlags::Default | PidfdSendSignalFlags::ThreadGroup => {
                process_target(ctx.process.clone())
            }
            PidfdSendSignalFlags::Thread => thread_target(
                ctx.process.main_thread().as_posix_thread().unwrap().tid(),
                ctx.process.clone(),
            ),
            PidfdSendSignalFlags::ProcessGroup => {
                group_target(ctx.process.pid(), ctx.process.clone())
            }
        },
        _ => {
            let mut file_table = ctx.thread_local.borrow_file_table_mut();
            let file = get_file_fast!(&mut file_table, pidfd.try_into()?);

            // FIXME: On Linux, a pidfd can be also obtained by opening a `/proc/pid` directory.
            // Reference: <https://man7.org/linux/man-pages/man2/pidfd_send_signal.2.html>
            let Some(pid_file) = file.downcast_ref::<PidFile>() else {
                return_errno_with_message!(Errno::EBADF, "the file is not a PID file");
            };

            let Some(process) = pid_file.process_opt() else {
                return Ok(SignalTarget::Exited);
            };

            match flags {
                PidfdSendSignalFlags::Default => {
                    // FIXME: On Linux, a pidfd can refer to either a process or a thread.
                    // We currently only support pidfds that refer to processes.
                    process_target(process)
                }
                PidfdSendSignalFlags::Thread => {
                    // FIXME: On Linux, the signal can be sent to any thread.
                    // We currently only support the main thread.
                    thread_target(
                        process.main_thread().as_posix_thread().unwrap().tid(),
                        process,
                    )
                }
                PidfdSendSignalFlags::ThreadGroup => process_target(process),
                PidfdSendSignalFlags::ProcessGroup => group_target(process.pid(), process),
            }
        }
    };

    Ok(target)
}

enum SignalTarget {
    Thread {
        tid: Tid,
        tgid: Pid,
        process: Arc<Process>,
    },
    Process {
        process: Arc<Process>,
    },
    ProcessGroup {
        pgid: Pgid,
        process: Arc<Process>,
    },
    Exited,
}

// Reference: <https://elixir.bootlin.com/linux/v6.18/source/include/uapi/linux/pidfd.h#L19>.
#[repr(u32)]
#[derive(Clone, Copy, Debug, Eq, PartialEq, TryFromInt)]
enum PidfdSendSignalFlags {
    Default = 0x0,
    Thread = 0x1,
    ThreadGroup = 0x2,
    ProcessGroup = 0x4,
}

// Reference: <https://elixir.bootlin.com/linux/v6.18/source/include/uapi/linux/fcntl.h#L110>.
const PIDFD_SELF_THREAD: i32 = -10000;
const PIDFD_SELF_THREAD_GROUP: i32 = -10001;
