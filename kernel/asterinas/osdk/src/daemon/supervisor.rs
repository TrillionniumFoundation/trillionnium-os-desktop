// SPDX-License-Identifier: MPL-2.0

//! Supervises running host daemons for the duration of QEMU.

use std::{
    path::Path,
    process::{self, Child, ExitStatus},
    time::{Duration, Instant},
};

use crate::{error::Errno, error_msg, warn_msg};

use super::{DaemonScheme, POLL_INTERVAL, RunningDaemon, SHUTDOWN_TIMEOUT, SignalGuard};

/// Time given to a daemon to create resources needed by QEMU before setup
/// continues. QEMU socket backends fail if their socket does not exist yet.
const STARTUP_DELAY: Duration = Duration::from_secs(1);

/// Supervises host daemons for the duration of a QEMU run.
///
/// The supervisor starts all executables, reaps normal exits, reports failures, and
/// stops all running daemons when QEMU exits or the run is interrupted.
pub(crate) struct DaemonSupervisor<'a> {
    /// Host daemons currently managed by the supervisor.
    running_daemons: Vec<RunningDaemon<'a>>,
    /// Shared state used to observe termination signals.
    signal: &'a SignalGuard,
    /// Working directory assigned to each managed host daemon.
    work_dir: &'a Path,
}

impl<'a> DaemonSupervisor<'a> {
    /// Starts all daemon executables.
    pub(crate) fn start(
        daemons: &'a [DaemonScheme],
        work_dir: &'a Path,
        signal: &'a SignalGuard,
    ) -> Result<Self, Errno> {
        let mut supervisor = Self {
            running_daemons: Vec::new(),
            signal,
            work_dir,
        };

        for daemon in daemons {
            if signal.received_signal().is_some() {
                supervisor.stop_all();
                return Err(Errno::Interrupted);
            }

            if let Err(errno) = supervisor.start_daemon(daemon) {
                supervisor.stop_all();
                return Err(errno);
            }

            // FIXME: Replace this fixed delay with a readiness check for the
            // resources that QEMU needs.
            std::thread::sleep(STARTUP_DELAY);

            if signal.received_signal().is_some() {
                supervisor.stop_all();
                return Err(Errno::Interrupted);
            }

            if let Err(errno) = supervisor.reap_exited_daemons() {
                supervisor.stop_all();
                return Err(errno);
            }
        }

        Ok(supervisor)
    }

    /// Starts one daemon executable and records its running state.
    fn start_daemon(&mut self, daemon: &'a DaemonScheme) -> Result<(), Errno> {
        info!("Starting managed QEMU daemon `{}`", daemon.path.display());

        let running = RunningDaemon::new(daemon, self.work_dir)?;
        self.running_daemons.push(running);

        Ok(())
    }

    /// Waits for QEMU while observing managed daemons and termination signals.
    pub(crate) fn wait_for_qemu(&mut self, qemu: &mut Child) -> Result<ExitStatus, Errno> {
        loop {
            if self.signal.received_signal().is_some() {
                self.stop_qemu_and_daemons(qemu);
                return Err(Errno::Interrupted);
            }

            let status = match qemu.try_wait() {
                Ok(status) => status,
                Err(err) => {
                    warn_msg!("failed to poll QEMU: {err}");

                    self.stop_qemu_and_daemons(qemu);

                    return Err(Errno::ExecuteCommand);
                }
            };

            if let Some(status) = status {
                // Daemons are expected to terminate with their QEMU peer, so
                // their exit status is no longer meaningful here.
                self.stop_all();
                return Ok(status);
            }

            if let Err(errno) = self.reap_exited_daemons() {
                self.stop_qemu_and_daemons(qemu);
                return Err(errno);
            }

            std::thread::sleep(POLL_INTERVAL);
        }
    }

    /// Reaps normally exited daemons and reports abnormal exits.
    pub(crate) fn reap_exited_daemons(&mut self) -> Result<(), Errno> {
        let mut index = 0;

        while index < self.running_daemons.len() {
            let status = self.running_daemons[index].poll_exit().map_err(|err| {
                warn_msg!(
                    "failed to poll managed QEMU daemon `{}`: {err}",
                    self.running_daemons[index].executable().display()
                );
                Errno::ExecuteCommand
            })?;

            let Some(status) = status else {
                index += 1;
                continue;
            };

            let mut running = self.running_daemons.remove(index);
            let executable = running.executable().display().to_string();
            // A successful leader may still have live descendants. Kill the
            // original group before releasing the waitable leader's PID.
            running.kill_and_wait();
            if status.exit_status() == Some(0) {
                info!("managed QEMU daemon `{executable}` exited successfully");
                continue;
            }

            error_msg!(
                "managed QEMU daemon `{executable}` exited unexpectedly with status {status:?}"
            );

            return Err(Errno::ExecuteCommand);
        }

        Ok(())
    }

    /// Stops all managed daemons and releases their runtime state.
    pub(crate) fn stop_all(&mut self) {
        // Peek before TERM: ECHILD means the numeric group is no longer ours.
        for running in &mut self.running_daemons {
            match running.poll_exit() {
                Ok(None) => running.terminate(),
                Ok(Some(_)) => running.kill_and_wait(),
                Err(error) => {
                    warn_msg!(
                        "failed to poll managed daemon `{}`: {error}",
                        running.executable().display()
                    );
                    running.kill_and_wait();
                }
            }
        }
        self.running_daemons.retain(|running| running.owns_child);

        let deadline = Instant::now() + SHUTDOWN_TIMEOUT;
        while !self.running_daemons.is_empty() && Instant::now() < deadline {
            self.running_daemons.retain_mut(|running| {
                match running.poll_exit() {
                    Ok(None) => return true,
                    Ok(Some(_)) => {}
                    Err(error) => {
                        warn_msg!(
                            "failed to poll managed daemon `{}`: {error}",
                            running.executable().display()
                        );
                    }
                }
                // Even after TERM has stopped the leader, descendants may
                // ignore it. Escalate before reaping that identity anchor.
                running.kill_and_wait();
                false
            });
            if !self.running_daemons.is_empty() {
                std::thread::sleep(POLL_INTERVAL);
            }
        }

        for running in &mut self.running_daemons {
            warn_msg!(
                "managed QEMU daemon `{}` did not stop in time; killing it",
                running.executable().display()
            );
            running.kill_and_wait();
        }
        self.running_daemons.clear();
    }

    /// Stops QEMU and all managed daemons.
    pub(crate) fn stop_qemu_and_daemons(&mut self, qemu: &mut Child) {
        stop_qemu(qemu);
        self.stop_all();
    }

    /// Stops QEMU when present, stops all managed daemons, and exits.
    pub(crate) fn abort(&mut self, qemu: Option<&mut Child>, errno: Errno) -> ! {
        if let Some(qemu) = qemu {
            stop_qemu(qemu);
        }
        self.stop_all();
        process::exit(errno as _);
    }
}

impl Drop for DaemonSupervisor<'_> {
    // `process::exit` does not run destructors, so error paths that exit the
    // process must stop daemons explicitly. This covers ordinary returns and
    // panics.
    fn drop(&mut self) {
        self.stop_all();
    }
}

fn stop_qemu(qemu: &mut Child) {
    let _ = qemu.kill();
    let _ = qemu.wait();
}

#[cfg(test)]
mod tests;
