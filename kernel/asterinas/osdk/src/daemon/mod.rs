// SPDX-License-Identifier: MPL-2.0

//! Lifecycle management for host daemons running alongside QEMU.

mod signal;
mod supervisor;

use std::{
    os::unix::process::CommandExt,
    path::Path,
    process::{Child, Command},
    time::Duration,
};

use rustix::process::{self, Pid, Signal, WaitId, WaitIdOptions, WaitIdStatus};

use crate::{config::scheme::DaemonScheme, error::Errno, error_msg, warn_msg};

pub(crate) use signal::SignalGuard;
pub(crate) use supervisor::DaemonSupervisor;

/// Interval between polls while monitoring QEMU and shutting down daemons.
const POLL_INTERVAL: Duration = Duration::from_millis(50);
/// Maximum time allowed for a daemon to exit after `SIGTERM`.
const SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(5);

/// A host daemon that has been started and is supervised until QEMU exits.
///
/// The supervisor observes exit without reaping the leader. The waitable child
/// reserves its PID until the original group has been killed, so a final group
/// signal cannot target a recycled PGID. OSDK must be the sole reaper of these
/// children, with SIGCHLD left waitable (no auto-reap). Descendants that leave
/// the original process group are not covered.
struct RunningDaemon<'a> {
    daemon: &'a DaemonScheme,
    child: Child,
    owns_child: bool,
}

impl<'a> RunningDaemon<'a> {
    fn new(daemon: &'a DaemonScheme, work_dir: &Path) -> Result<Self, Errno> {
        let mut command = Command::new(&daemon.path);
        command.args(&daemon.args);

        command.current_dir(work_dir);
        // Each managed daemon is started as the leader of its own process group.
        // This allows descendants to be terminated in a clean boundary.
        command.process_group(0);

        let child = command.spawn().map_err(|err| {
            error_msg!("failed to spawn `{}`: {err}", daemon.path.display());
            Errno::ExecuteCommand
        })?;

        Ok(Self {
            daemon,
            child,
            owns_child: true,
        })
    }

    fn executable(&self) -> &Path {
        &self.daemon.path
    }

    fn poll_exit(&mut self) -> std::io::Result<Option<WaitIdStatus>> {
        if !self.owns_child {
            return Err(rustix::io::Errno::CHILD.into());
        }
        loop {
            match process::waitid(
                WaitId::Pid(Pid::from_child(&self.child)),
                WaitIdOptions::EXITED | WaitIdOptions::NOHANG | WaitIdOptions::NOWAIT,
            ) {
                Err(rustix::io::Errno::INTR) => continue,
                Err(error) => {
                    if error == rustix::io::Errno::CHILD {
                        // Another reaper or SIGCHLD auto-reap lost our identity
                        // anchor. Never signal this numeric group again.
                        self.owns_child = false;
                    }
                    return Err(error.into());
                }
                Ok(status) => return Ok(status),
            }
        }
    }

    fn kill_and_wait(&mut self) {
        if !self.owns_child {
            return;
        }
        self.kill();
        // Disarm before wait can release the PID. No later cleanup may signal
        // the group, even if wait itself reports an error.
        self.owns_child = false;
        if let Err(error) = self.child.wait() {
            warn_msg!(
                "failed to reap managed daemon `{}`: {error}",
                self.executable().display()
            );
        }
    }

    fn kill(&mut self) {
        if !self.owns_child {
            return;
        }
        let _ = process::kill_process_group(Pid::from_child(&self.child), Signal::KILL);
    }

    fn terminate(&self) {
        if !self.owns_child {
            return;
        }
        let _ = process::kill_process_group(Pid::from_child(&self.child), Signal::TERM);
    }
}

impl Drop for RunningDaemon<'_> {
    fn drop(&mut self) {
        self.kill_and_wait();
    }
}
