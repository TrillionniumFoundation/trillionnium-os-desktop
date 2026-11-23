//! The normal Ubuntu production service owns its actual budget, original APK
//! storage, read-only release and Android namespace until orderly retirement.
use super::{
    EarlyBaseAdmission, EarlyBaseRetirement, EarlyBoardResources, EarlyBoundNamespaces, identity,
    invalid,
};
use crate::production_cgroup::PreparedCgroup;
use crate::production_devices::PreparedDevices;
use crate::production_execution::PreparationAdmission;
use crate::production_mounts::{
    PreparedMounts,
    persistent_data::{EarlyStorageAdmission, PreparedPersistentData},
};
use std::{
    fs::File,
    io,
    os::fd::{AsRawFd, FromRawFd},
    path::Path,
    time::Duration,
};

unsafe extern "C" {
    fn droidloom_board_assemble(
        root: i32,
        dev: i32,
        data: i32,
        metadata: i32,
        payload: i32,
        generation: i32,
        uid: u32,
        gid: u32,
        observer_gid: u32,
    ) -> i32;
    fn droidloom_board_deliver_root(
        pidfd: i32,
        userns: i32,
        mountns: i32,
        childroot: i32,
        root: i32,
    ) -> i32;
}
struct ServiceSignals {
    events: File,
    previous: libc::sigset_t,
}
impl ServiceSignals {
    fn acquire() -> io::Result<Self> {
        let mut mask: libc::sigset_t = unsafe { std::mem::zeroed() };
        let mut old: libc::sigset_t = unsafe { std::mem::zeroed() };
        for result in [
            unsafe { libc::sigemptyset(&mut mask) },
            unsafe { libc::sigaddset(&mut mask, libc::SIGTERM) },
            unsafe { libc::sigaddset(&mut mask, libc::SIGINT) },
        ] {
            if result != 0 {
                return Err(io::Error::last_os_error());
            }
        }
        let rc = unsafe { libc::pthread_sigmask(libc::SIG_BLOCK, &mask, &mut old) };
        if rc != 0 {
            return Err(io::Error::from_raw_os_error(rc));
        }
        let fd = unsafe { libc::signalfd(-1, &mask, libc::SFD_CLOEXEC | libc::SFD_NONBLOCK) };
        if fd < 0 {
            let e = io::Error::last_os_error();
            unsafe {
                libc::pthread_sigmask(libc::SIG_SETMASK, &old, std::ptr::null_mut());
            }
            return Err(e);
        }
        Ok(Self {
            events: unsafe { File::from_raw_fd(fd) },
            previous: old,
        })
    }
    fn await_child(&self, pidfd: &File) -> io::Result<()> {
        let mut fds = [
            libc::pollfd {
                fd: pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: self.events.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
        ];
        loop {
            if unsafe { libc::poll(fds.as_mut_ptr(), 2, -1) } < 0 {
                let e = io::Error::last_os_error();
                if e.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(e);
            }
            if fds
                .iter()
                .any(|f| f.revents & (libc::POLLNVAL | libc::POLLERR) != 0)
            {
                return Err(invalid("lost Android lifetime monitor"));
            }
            if fds[1].revents & libc::POLLIN != 0 {
                let mut event: libc::signalfd_siginfo = unsafe { std::mem::zeroed() };
                if unsafe {
                    libc::read(
                        self.events.as_raw_fd(),
                        (&mut event as *mut libc::signalfd_siginfo).cast(),
                        std::mem::size_of_val(&event),
                    )
                } != std::mem::size_of_val(&event) as isize
                {
                    return Err(invalid("incomplete service stop signal"));
                }
                return Ok(());
            }
            if fds[0].revents & libc::POLLIN != 0 {
                return Err(invalid("original Android init exited before service stop"));
            }
        }
    }
}
impl Drop for ServiceSignals {
    fn drop(&mut self) {
        unsafe {
            libc::pthread_sigmask(libc::SIG_SETMASK, &self.previous, std::ptr::null_mut());
        }
    }
}
fn wait_ended(fd: &File, timeout: Duration) -> io::Result<bool> {
    let until = std::time::Instant::now() + timeout;
    loop {
        let mut p = libc::pollfd {
            fd: fd.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        let ms = until
            .saturating_duration_since(std::time::Instant::now())
            .as_millis()
            .min(i32::MAX as u128) as i32;
        let rc = unsafe { libc::poll(&mut p, 1, ms) };
        if rc < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(e);
        }
        if p.revents & (libc::POLLNVAL | libc::POLLERR) != 0 {
            return Err(invalid("original Android pidfd could not be observed"));
        }
        return Ok(rc > 0 && p.revents & libc::POLLIN != 0);
    }
}
#[derive(Debug, PartialEq, Eq)]
enum ChildExit {
    Observed,
    Forced,
}

impl ChildExit {
    fn after_retirement(self, retired: io::Result<()>) -> io::Result<()> {
        match (self, retired) {
            (Self::Observed, result) => result,
            (Self::Forced, Ok(())) => Err(invalid(
                "original Android PID 1 required SIGKILL; its resources were retired",
            )),
            (Self::Forced, Err(e)) => Err(io::Error::other(format!(
                "original Android PID 1 required SIGKILL; resource retirement failed: {e}"
            ))),
        }
    }
}

fn stop_child(fd: &File, term_timeout: Duration) -> io::Result<ChildExit> {
    for (signal, timeout) in [
        (libc::SIGTERM, term_timeout),
        (libc::SIGKILL, Duration::from_secs(10)),
    ] {
        if wait_ended(fd, Duration::ZERO)? {
            return Ok(ChildExit::Observed);
        }
        let signaled = unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                fd.as_raw_fd(),
                signal,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        } == 0;
        if !signaled {
            let e = io::Error::last_os_error();
            if e.raw_os_error() != Some(libc::ESRCH) {
                return Err(e);
            }
        }
        if wait_ended(fd, timeout)? {
            return Ok(if signaled && signal == libc::SIGKILL {
                ChildExit::Forced
            } else {
                ChildExit::Observed
            });
        }
    }
    Err(invalid("original Android PID 1 did not exit"))
}

/// Run in the actual droidloom-production.service MainPID after initramfs
/// created the original Android process. Success means the service stopped
/// and its released original resources were positively retired.
pub fn complete_early_resources() -> io::Result<()> {
    let signals = ServiceSignals::acquire()?;
    let board = EarlyBoardResources::acquire()?;
    let bound = EarlyBoundNamespaces::acquire(&board)?;
    let private = board
        .selection()
        .retain_for_retirement()
        .map_err(io::Error::other)?;
    let prep = PreparationAdmission::acquire(private).map_err(io::Error::other)?;
    let owner = prep.owner();
    let group =
        PreparedCgroup::prepare(bound.admit_host()?, owner.clone()).map_err(io::Error::other)?;
    let base = match EarlyBaseAdmission::new(&bound, group.admission()) {
        Ok(value) => value,
        Err(cause) => {
            group.retire_early_unstarted().map_err(io::Error::other)?;
            return Err(cause);
        }
    };
    if let Err(cause) = group.place_early_payload(&base, &owner) {
        if group.attempted_original(&board).map_err(io::Error::other)? {
            let stopped = stop_child(board.pidfd(), Duration::from_secs(15))?;
            let retired = group.retire_early_empty(&board).map_err(io::Error::other);
            if let Err(e) = stopped.after_retirement(retired) {
                return Err(io::Error::other(format!("{cause}; retirement: {e}")));
            }
        } else {
            group.retire_early_unstarted().map_err(io::Error::other)?;
        }
        return Err(io::Error::other(cause));
    }
    let mut images: Option<PreparedMounts> = None;
    let mut data: Option<PreparedPersistentData> = None;
    let mut devices: Option<PreparedDevices> = None;
    let mut original_root: Option<File> = None;
    let work = (|| -> io::Result<()> {
        let cg_ns = board.root_cgroup_namespace()?;
        group
            .finish_early_placement(&base, &cg_ns)
            .map_err(io::Error::other)?;
        let storage =
            EarlyStorageAdmission::acquire(&base, &group, &owner).map_err(io::Error::other)?;
        let payload = group
            .early_payload(&base, &owner)
            .map_err(io::Error::other)?;
        let outer_root = File::open(format!(
            "/proc/self/fd/{}/root",
            base.proc_directory().as_raw_fd()
        ))?;
        let generation =
            super::super::open_root_trusted_directory(Path::new("/run/droidloom-early"))
                .map_err(io::Error::other)?;
        let system = images.insert(PreparedMounts::prepare_early(&base).map_err(io::Error::other)?);
        let root = original_root.insert(File::from(
            system
                .early_root_for_transfer(&base)
                .map_err(io::Error::other)?
                .try_clone_to_owned()?,
        ));
        let private_dev =
            devices.insert(PreparedDevices::prepare_early(&base).map_err(io::Error::other)?);
        let dev = File::from(
            private_dev
                .early_descriptor_for_transfer(&base)
                .map_err(io::Error::other)?
                .try_clone_to_owned()?,
        );
        let mutable =
            data.insert(PreparedPersistentData::prepare_early(&storage).map_err(io::Error::other)?);
        let (owned, observed) = mutable
            .early_descriptors_for_transfer(&storage)
            .map_err(io::Error::other)?;
        let [userdata, metadata] = owned;
        let userdata = File::from(userdata.try_clone_to_owned()?);
        let metadata = File::from(metadata.try_clone_to_owned()?);
        observed[0].verify(&userdata).map_err(io::Error::other)?;
        observed[1].verify(&metadata).map_err(io::Error::other)?;
        let (u, g) = base.identity_lease().broker_ranges();
        let obs = g
            .start
            .checked_add(9999)
            .ok_or_else(|| invalid("observer gid overflow"))?;
        owner.objects().map_err(io::Error::other)?;
        if unsafe {
            droidloom_board_assemble(
                root.as_raw_fd(),
                dev.as_raw_fd(),
                userdata.as_raw_fd(),
                metadata.as_raw_fd(),
                payload.as_raw_fd(),
                generation.as_raw_fd(),
                u.start,
                g.start,
                obs,
            )
        } < 0
        {
            return Err(io::Error::last_os_error());
        }
        mutable
            .revalidate_early_lifetime(&storage)
            .map_err(io::Error::other)?;
        if identity(&outer_root)?
            != identity(&File::open(format!(
                "/proc/self/fd/{}/root",
                base.proc_directory().as_raw_fd()
            ))?)?
        {
            return Err(invalid(
                "original Android process changed root before delivery",
            ));
        }
        board.revalidate()?;
        if unsafe {
            droidloom_board_deliver_root(
                board.pidfd().as_raw_fd(),
                board.user_namespace().as_raw_fd(),
                board.mount_namespace().as_raw_fd(),
                outer_root.as_raw_fd(),
                root.as_raw_fd(),
            )
        } < 0
        {
            return Err(io::Error::last_os_error());
        }
        mutable
            .revalidate_early_lifetime(&storage)
            .map_err(io::Error::other)?;
        let stop = super::orderly::StopRequest::acquire(&board, obs, &userdata, &metadata)?;
        drop(userdata);
        drop(metadata);
        board.release_prepared_root()?;
        signals.await_child(board.pidfd())?;
        stop.deliver(&board)?;
        if !wait_ended(board.pidfd(), Duration::from_secs(75))? {
            return Err(invalid("Android did not finish its requested orderly shutdown"));
        }
        stop.check_mounts(&board, false)
    })();
    // The original pidfd retains exclusive custody even if an earlier stage
    // failed after moving a mount. Never release by a numeric process lookup.
    let cleanup = stop_child(board.pidfd(), Duration::from_secs(15)).and_then(|exit| {
        let retired = (|| -> io::Result<()> {
            if let Some(root) = original_root {
                let retired = EarlyBaseRetirement::finish(&board, &group, &root)?;
                drop(root);
                let dev_result = devices
                    .map(|v| v.retire_after_early_tree(&retired))
                    .transpose()
                    .map_err(io::Error::other);
                let data_result = data
                    .map(|v| v.retire_after_early_tree(&retired))
                    .transpose()
                    .map_err(io::Error::other);
                let image_result = images
                    .map(|v| v.retire_after_early_tree(&retired))
                    .transpose()
                    .map_err(io::Error::other);
                dev_result?;
                data_result?;
                image_result?;
            } else {
                group.retire_early_empty(&board).map_err(io::Error::other)?;
                if let Some(images) = images {
                    images.retire_untransferred().map_err(io::Error::other)?;
                }
            }
            Ok(())
        })();
        exit.after_retirement(retired)
    });
    match (work, cleanup) {
        (Err(operation), Err(cleanup)) => {
            Err(io::Error::other(format!("{operation}; cleanup: {cleanup}")))
        }
        (Err(e), _) | (_, Err(e)) => Err(e),
        (Ok(()), Ok(())) => Ok(()),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_process_receives_stop_and_pidfd_confirms_exit() {
        let mut child = std::process::Command::new("/bin/sleep")
            .arg("25")
            .spawn()
            .unwrap();
        let pid = child.id();
        let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
        assert!(fd >= 0);
        let fd = unsafe { File::from_raw_fd(fd as i32) };
        assert!(!wait_ended(&fd, Duration::ZERO).unwrap());
        assert_eq!(
            stop_child(&fd, Duration::from_secs(3)).unwrap(),
            ChildExit::Observed
        );
        assert!(wait_ended(&fd, Duration::ZERO).unwrap());
        child.wait().unwrap();
    }
    #[test]
    fn unresponsive_original_is_reaped_and_cannot_report_a_clean_stop() {
        use std::io::BufRead;
        use std::os::unix::process::ExitStatusExt;
        use std::process::{Command, Stdio};

        let mut child = Command::new("/bin/sh")
            .args(["-c", "trap '' TERM; echo ready; exec /bin/sleep 25"])
            .stdout(Stdio::piped())
            .spawn()
            .unwrap();
        let mut ready = String::new();
        std::io::BufReader::new(child.stdout.take().unwrap())
            .read_line(&mut ready)
            .unwrap();
        assert_eq!(ready.trim(), "ready");
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
        assert!(raw >= 0);
        let fd = unsafe { File::from_raw_fd(raw as i32) };
        let exit = stop_child(&fd, Duration::from_millis(20)).unwrap();
        assert_eq!(exit, ChildExit::Forced);
        assert_eq!(child.wait().unwrap().signal(), Some(libc::SIGKILL));
        assert!(
            exit.after_retirement(Ok(()))
                .unwrap_err()
                .to_string()
                .contains("SIGKILL")
        );
        let failure = ChildExit::Forced
            .after_retirement(Err(invalid("test detach failed")))
            .unwrap_err();
        assert!(
            failure.to_string().contains("SIGKILL")
                && failure.to_string().contains("test detach failed")
        );
    }
}
