// SPDX-License-Identifier: MPL-2.0

use ostd::mm::VmIo;

use super::SyscallReturn;
use crate::{
    prelude::*,
    process::{
        kill_process_via_thread, pid_table,
        posix_thread::AsPosixThread,
        signal::{
            c_types::siginfo_t,
            constants::SI_TKILL,
            sig_num::SigNum,
            signals::{OwnedSignal, raw::RawSignal},
        },
    },
};

/// Sends user-provided signal data to one process, using actual caller credentials.
pub(super) fn sys_rt_sigqueueinfo(
    pid: i32,
    sig: i32,
    info_ptr: Vaddr,
    ctx: &Context,
) -> Result<SyscallReturn> {
    // Linux copies first (including sig=0), then checks code, target and signal.
    // The payload's PID/UID are data and never participate in authorization.
    // Reference: linux v6.17 kernel/signal.c, do_rt_sigqueueinfo/kill_proc_info.
    let mut info = ctx.user_space().read_val::<siginfo_t>(info_ptr)?;
    info.si_signo = sig;
    if (info.si_code >= 0 || info.si_code == SI_TKILL)
        && pid != ctx.posix_thread.tid().cast_signed()
    {
        return_errno_with_message!(Errno::EPERM, "this signal code requires the current thread");
    }

    // This interface does not interpret zero/negative PIDs as process groups.
    if pid <= 0 {
        return_errno_with_message!(Errno::ESRCH, "the target process does not exist");
    }
    // Linux resolves a PIDTYPE_PID task, including a nonleader TID, then sends
    // to its shared process queue. Retain both owners while still under the
    // original membership lock, so exit/reap cannot expire the Process.
    let (thread, _process) = {
        let table = pid_table::pid_table_mut();
        let thread = table
            .get_thread(pid.cast_unsigned())
            .ok_or_else(|| Error::with_message(Errno::ESRCH, "the target thread does not exist"))?;
        let process = thread.as_posix_thread().unwrap().process();
        (thread, process)
    };

    // Validate the full signed argument after finding the target. In particular,
    // truncation must not turn 256 into the permission-only signal zero.
    let signal = if sig == 0 {
        None
    } else {
        let byte = u8::try_from(sig).map_err(|_| Error::new(Errno::EINVAL))?;
        SigNum::try_from(byte)?;
        Some(OwnedSignal::new(RawSignal::new(info)))
    };
    // The original check uses this actual target thread's credentials; the
    // signal still belongs to its process, not the thread-private queue.
    kill_process_via_thread(thread.as_posix_thread().unwrap(), signal, ctx)?;
    Ok(SyscallReturn::Return(0))
}
