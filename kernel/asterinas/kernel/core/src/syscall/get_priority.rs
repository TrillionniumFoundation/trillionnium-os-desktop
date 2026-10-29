// SPDX-License-Identifier: MPL-2.0

use super::SyscallReturn;
use crate::{
    prelude::*,
    process::{Pgid, Process, Uid, pid_table, posix_thread::AsPosixThread},
    sched::Nice,
    thread::{AsThread, Thread, Tid},
};

pub(super) fn sys_get_priority(which: i32, who: u32, ctx: &Context) -> Result<SyscallReturn> {
    let targets = get_priority_threads(PriorityTarget::new(which, who, ctx)?)?;
    let mut nice = Nice::MAX;
    for target in targets {
        nice = nice.min(target.thread.sched_attr().user_snapshot().nice());
    }
    // Linux's raw syscall ABI maps nice [-20,19] to [40,1].
    Ok(SyscallReturn::Return(
        (20 - i32::from(nice.value().get())) as isize,
    ))
}

/// Strong target identities survive credential checks and sleeping administration.
pub(super) struct PriorityThread {
    pub(super) thread: Arc<Thread>,
    pub(super) process: Arc<Process>,
}

pub(super) fn get_priority_threads(target: PriorityTarget) -> Result<Vec<PriorityThread>> {
    let (processes, uid_filter) = match target {
        PriorityTarget::Thread(tid) => {
            let thread = {
                let table = pid_table::pid_table_mut();
                table.get_thread(tid).ok_or(Errno::ESRCH)?
            };
            let process = thread
                .as_posix_thread()
                .ok_or(Errno::ESRCH)?
                .weak_process()
                .upgrade()
                .ok_or(Errno::ESRCH)?;
            return Ok(vec![PriorityThread { thread, process }]);
        }
        PriorityTarget::ProcessGroup(pgid) => {
            let group = {
                let table = pid_table::pid_table_mut();
                table.get_process_group(&pgid).ok_or(Errno::ESRCH)?
            };
            let processes: Vec<Arc<Process>> = group.lock().iter().collect();
            (processes, None)
        }
        PriorityTarget::User(uid) => {
            let processes: Vec<Arc<Process>> = {
                let table = pid_table::pid_table_mut();
                table.iter_processes().collect()
            };
            (processes, Some(uid))
        }
    };
    let mut targets = Vec::new();
    for process in processes {
        // Never carry the PID table, group or TaskSet across credentials or an
        // administrator/snapshot. A process may contain threads with different UIDs.
        let threads: Vec<Arc<Thread>> = process
            .tasks()
            .lock()
            .as_slice()
            .iter()
            .filter_map(|task| task.as_thread().cloned())
            .collect();
        for thread in threads {
            let Some(posix) = thread.as_posix_thread() else {
                continue;
            };
            if let Some(uid) = uid_filter
                && posix.credentials().ruid() != uid
            {
                continue;
            }
            targets.push(PriorityThread {
                thread,
                process: process.clone(),
            });
        }
    }
    if targets.is_empty() {
        return_errno!(Errno::ESRCH);
    }
    Ok(targets)
}

#[derive(Debug)]
pub(super) enum PriorityTarget {
    Thread(Tid),
    ProcessGroup(Pgid),
    User(Uid),
}

impl PriorityTarget {
    pub(super) fn new(which: i32, who: u32, ctx: &Context) -> Result<Self> {
        let which = Which::try_from(which)
            .map_err(|_| Error::with_message(Errno::EINVAL, "invalid which value"))?;
        Ok(match which {
            Which::PRIO_PROCESS => Self::Thread(if who == 0 {
                ctx.posix_thread.tid()
            } else {
                who
            }),
            Which::PRIO_PGRP => Self::ProcessGroup(if who == 0 { ctx.process.pgid() } else { who }),
            Which::PRIO_USER => Self::User(if who == 0 {
                ctx.posix_thread.credentials().ruid()
            } else {
                Uid::new(who)
            }),
        })
    }
}

#[expect(non_camel_case_types)]
#[repr(i32)]
#[derive(Clone, Debug, TryFromInt)]
pub(super) enum Which {
    PRIO_PROCESS = 0,
    PRIO_PGRP = 1,
    PRIO_USER = 2,
}
