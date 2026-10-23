// SPDX-License-Identifier: MPL-2.0

use super::{
    Pgid, Pid, Process, pid_table,
    posix_thread::AsPosixThread,
    signal::{
        constants::SIGCONT,
        sig_num::SigNum,
        signals::{OwnedSignal, Signal},
    },
};
use crate::{
    prelude::*,
    process::{credentials::capabilities::CapSet, posix_thread::PosixThread},
    security::lsm::hooks as lsm_hooks,
    thread::Tid,
};

/// Sends a signal to a process, using the current process as the sender.
///
/// The credentials of the current process will be checked to determine
/// if it is authorized to send the signal to this particular target process.
///
/// If `signal` is `None`, this method will only check permission without sending
/// any signal.
pub(crate) fn kill(pid: Pid, signal: Option<Box<dyn Signal>>, ctx: &Context) -> Result<()> {
    kill_owned(pid, signal.map(OwnedSignal::from_box), ctx)
}

/// Same permission checks as `kill`, retaining the prepared signal owner.
pub(crate) fn kill_owned(pid: Pid, signal: Option<OwnedSignal>, ctx: &Context) -> Result<()> {
    kill_owned_with(pid, None, || Ok(signal), ctx)
}

/// Resolves the original target before validating a user-supplied signal.
/// This preserves ESRCH before EINVAL without a second target lookup.
pub(crate) fn kill_owned_with(
    pid: Pid,
    expected_process: Option<&Arc<Process>>,
    prepare: impl FnOnce() -> Result<Option<OwnedSignal>>,
    ctx: &Context,
) -> Result<()> {
    // Fast path: If the signal is sent to self, we can skip most checks.
    if pid == ctx.process.pid() {
        if expected_process.is_some_and(|process| !Arc::ptr_eq(process, &ctx.process)) {
            return_errno!(Errno::ESRCH);
        }
        let Some(signal) = prepare()? else {
            return Ok(());
        };

        if !ctx.posix_thread.has_signal_blocked(signal.num()) {
            // Killing the current thread does not raise any permission issues.
            ctx.posix_thread.enqueue_owned_signal(signal);
            return Ok(());
        }

        return kill_process(ctx.process.as_ref(), Some(signal), ctx);
    }

    // Linux resolves PIDTYPE_PID, including a nonleader TID, then sends to
    // that task's shared process queue. Pin both owners at the lookup cut.
    let (thread, process) = {
        let table = pid_table::pid_table_mut();
        let thread = table
            .get_thread(pid)
            .ok_or_else(|| Error::with_message(Errno::ESRCH, "the target thread does not exist"))?;
        let process = thread.as_posix_thread().unwrap().process();
        (thread, process)
    };
    if expected_process.is_some_and(|expected| !Arc::ptr_eq(expected, &process)) {
        return_errno!(Errno::ESRCH);
    }
    kill_process_via_thread(thread.as_posix_thread().unwrap(), prepare()?, ctx)
}

/// Sends a signal to all processes in a group, using the current process
/// as the sender.
///
/// The credentials of the current process will be checked to determine
/// if it is authorized to send the signal to the target group.
///
/// If `signal` is `None`, this method will only check permission without sending
/// any signal.
pub(crate) fn kill_group<S: Signal + Clone>(
    pgid: Pgid,
    signal: Option<S>,
    ctx: &Context,
) -> Result<()> {
    kill_group_with(pgid, None, || Ok(signal.clone().map(OwnedSignal::new)), ctx)
}

/// Prepares a signal only after resolving an original group member.
pub(crate) fn kill_group_with(
    pgid: Pgid,
    expected_process: Option<&Arc<Process>>,
    mut prepare: impl FnMut() -> Result<Option<OwnedSignal>>,
    ctx: &Context,
) -> Result<()> {
    let process_group = {
        let table = pid_table::pid_table_mut();
        if let Some(expected) = expected_process {
            let actual = table.get_process(expected.pid());
            if !actual.is_some_and(|actual| Arc::ptr_eq(&actual, expected)) {
                return_errno!(Errno::ESRCH);
            }
        }
        table
            .get_process_group(&pgid)
            .ok_or_else(|| Error::with_message(Errno::ESRCH, "the target group does not exist"))?
    };

    let mut result = Ok(());

    let inner = process_group.lock();
    let mut any_target = false;
    for process in inner.iter() {
        any_target = true;
        let res = prepare().and_then(|signal| kill_process(&process, signal, ctx));
        if res.is_err_and(|err| err.error() != Errno::EPERM) {
            result = res;
        }
    }

    if !any_target {
        return_errno!(Errno::ESRCH);
    }
    result
}

/// Sends a signal to a target thread, using the current process
/// as the sender.
///
/// Checks the target thread belongs to the target process if `tgid` is provided.
///
/// If `signal` is `None`, this method will only check permission without sending
/// any signal.
pub(crate) fn tgkill(
    tid: Tid,
    tgid: Option<Pid>,
    signal: Option<Box<dyn Signal>>,
    ctx: &Context,
) -> Result<()> {
    tgkill_owned(tid, tgid, signal.map(OwnedSignal::from_box), ctx)
}

/// Same target and permission checks as `tgkill`, without changing the owner.
pub(crate) fn tgkill_owned(
    tid: Tid,
    tgid: Option<Pid>,
    signal: Option<OwnedSignal>,
    ctx: &Context,
) -> Result<()> {
    tgkill_owned_with(tid, tgid, None, || Ok(signal), ctx)
}

/// Resolves one held Thread/Process pair before signal validation.
pub(crate) fn tgkill_owned_with(
    tid: Tid,
    tgid: Option<Pid>,
    expected_process: Option<&Arc<Process>>,
    prepare: impl FnOnce() -> Result<Option<OwnedSignal>>,
    ctx: &Context,
) -> Result<()> {
    let (thread, process) = {
        let table = pid_table::pid_table_mut();
        let thread = table
            .get_thread(tid)
            .ok_or_else(|| Error::with_message(Errno::ESRCH, "the target thread does not exist"))?;
        let process = thread.as_posix_thread().unwrap().process();
        (thread, process)
    };
    if expected_process.is_some_and(|expected| !Arc::ptr_eq(expected, &process)) {
        return_errno!(Errno::ESRCH);
    }
    if tgid.is_some_and(|tgid| tgid != process.pid()) {
        return_errno_with_message!(Errno::ESRCH, "the TGID and TID do not match");
    }
    let signal = prepare()?;
    let target_posix_thread = thread.as_posix_thread().unwrap();

    // Check permission
    let signum = signal.as_ref().map(|signal| signal.num());
    check_signal_perm(target_posix_thread, ctx, signum)?;

    if thread.is_exited() {
        return Ok(());
    }

    if let Some(signal) = signal {
        // We've checked the permission issues above.
        // FIXME: We should take some lock while checking the permission to avoid race conditions.
        target_posix_thread.enqueue_owned_signal(signal);
    }

    Ok(())
}

/// Sends a signal to all processes except current process and init process, using
/// the current process as the sender.
///
/// The credentials of the current process will be checked to determine
/// if it is authorized to send the signal to the target group.
pub(crate) fn kill_all<S: Signal + Clone>(signal: Option<S>, ctx: &Context) -> Result<()> {
    kill_all_with(|| Ok(signal.clone().map(OwnedSignal::new)), ctx)
}

/// Prepares only for a live eligible process under the original membership lock.
pub(crate) fn kill_all_with(
    mut prepare: impl FnMut() -> Result<Option<OwnedSignal>>,
    ctx: &Context,
) -> Result<()> {
    let mut result = Ok(());
    let mut any_target = false;

    for process in pid_table::pid_table_mut().iter_processes() {
        if Arc::ptr_eq(&ctx.process, &process) || process.is_init_process() {
            continue;
        }

        any_target = true;
        let res = prepare().and_then(|signal| kill_process(&process, signal, ctx));
        if res.is_err_and(|err| err.error() != Errno::EPERM) {
            result = res;
        }
    }

    if !any_target {
        return_errno!(Errno::ESRCH);
    }
    result
}

fn kill_process(process: &Process, signal: Option<OwnedSignal>, ctx: &Context) -> Result<()> {
    let target_main_thread = process.main_thread();
    kill_process_via_thread(target_main_thread.as_posix_thread().unwrap(), signal, ctx)
}

/// Checks the selected thread's actual credentials and sends to its process.
/// The caller must retain its Process while resolving and using the thread.
pub(crate) fn kill_process_via_thread(
    target: &PosixThread,
    signal: Option<OwnedSignal>,
    ctx: &Context,
) -> Result<()> {
    let process = target.process();
    let signum = signal.as_ref().map(|signal| signal.num());
    check_signal_perm(target, ctx, signum)?;

    if let Some(signal) = signal {
        process.enqueue_owned_signal(signal);
    }

    Ok(())
}

// Reference: <https://elixir.bootlin.com/linux/v6.17/source/kernel/signal.c#L799>.
fn check_signal_perm(target: &PosixThread, ctx: &Context, signum: Option<SigNum>) -> Result<()> {
    let target_process = target.process();

    if Arc::ptr_eq(&target_process, &ctx.process) {
        return Ok(());
    }

    let current_cred = ctx.posix_thread.credentials();
    let target_cred = target.credentials();
    if current_cred.euid() == target_cred.suid()
        || current_cred.euid() == target_cred.ruid()
        || current_cred.ruid() == target_cred.suid()
        || current_cred.ruid() == target_cred.ruid()
    {
        return Ok(());
    }

    if lsm_hooks::on_capable(lsm_hooks::CapableContext::new(
        target_process.user_ns().lock().as_ref(),
        ctx.posix_thread,
        CapSet::KILL,
    ))
    .is_ok()
    {
        return Ok(());
    }

    if let Some(signum) = signum
        && signum == SIGCONT
    {
        let target_sid = target_process.sid();
        let current_sid = ctx.process.sid();
        if target_sid == current_sid {
            return Ok(());
        }
    }

    return_errno_with_message!(
        Errno::EPERM,
        "sending signal to the target process or thread is not allowed"
    )
}
