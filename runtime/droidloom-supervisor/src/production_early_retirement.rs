use super::{EarlyBoardResources, identity, invalid};
use crate::production_cgroup::PreparedCgroup;
use std::fs::File;
use std::io;
use std::os::fd::AsRawFd;

unsafe extern "C" {
    fn droidloom_board_retire_root(pidfd: i32, nsfd: i32, rootfd: i32, delivery_attempted: i32) -> i32;
}
/// Constructed only after the exact process has exited, its budget is empty
/// and removed, and the kernel reports that the original root was detached.
pub(crate) struct EarlyBaseRetirement {
    userns: File,
    original_pidfd: File,
    host_uid: u32,
    cohort: String,
}
impl EarlyBaseRetirement {
    pub(super) fn finish(
        board: &EarlyBoardResources,
        group: &PreparedCgroup,
        delivered: &File,
        delivery_attempted: bool,
    ) -> io::Result<Self> {
        group.verify_early_exit(board).map_err(io::Error::other)?;
        let userns = board.user_namespace().try_clone()?;
        let pidfd = board.pidfd().try_clone()?;
        let selection = board.selection();
        let result = Self {
            userns,
            original_pidfd: pidfd,
            host_uid: selection.spec().host_uid,
            cohort: selection.base_cohort().to_owned(),
        };
        if unsafe {
            droidloom_board_retire_root(
                board.pidfd().as_raw_fd(),
                board.mount_namespace().as_raw_fd(),
                delivered.as_raw_fd(),
                i32::from(delivery_attempted),
            )
        } < 0
        {
            return Err(io::Error::last_os_error());
        }
        group.retire_early_empty(board).map_err(io::Error::other)?;
        Ok(result)
    }
    pub(crate) fn verify_mount_retirement(
        &self,
        userns: &File,
        host_uid: u32,
        cohort: &str,
    ) -> io::Result<()> {
        if identity(userns)? != identity(&self.userns)?
            || self.host_uid != host_uid
            || self.cohort != cohort
        {
            return Err(invalid(
                "resources do not belong to the retired original Android generation",
            ));
        }
        verify_exit(&self.original_pidfd)
    }
}
pub(crate) fn verify_exit(pidfd: &File) -> io::Result<()> {
    let mut status = libc::pollfd {
        fd: pidfd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    loop {
        let n = unsafe { libc::poll(&mut status, 1, 0) };
        if n < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(e);
        }
        if n == 1
            && status.revents & libc::POLLIN != 0
            && status.revents & (libc::POLLNVAL | libc::POLLERR) == 0
        {
            return Ok(());
        }
        return Err(invalid("original Android PID 1 has not exited"));
    }
}
