//! Resource admission for the original initramfs-created Android PID 1.
use super::{EarlyBoardResources, identity, invalid};
use crate::IdRange;
use crate::production_host_admission::HostAdmission;
use crate::production_identity::{IdentityAuthority, IdentityLease};
use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::OpenOptionsExt;
use std::path::PathBuf;

fn proc_path(directory: &File, component: &str) -> PathBuf {
    PathBuf::from(format!("/proc/self/fd/{}", directory.as_raw_fd())).join(component)
}
fn start_ticks(line: &str, expected_pid: u32) -> io::Result<u64> {
    let (pid, rest) = line
        .split_once(" (")
        .ok_or_else(|| invalid("incomplete process stat"))?;
    let (_, fields) = rest
        .rsplit_once(") ")
        .ok_or_else(|| invalid("missing process stat fields"))?;
    if pid.parse::<u32>().ok() != Some(expected_pid) {
        return Err(invalid("process number changed"));
    }
    fields
        .split_ascii_whitespace()
        .nth(19)
        .and_then(|v| v.parse::<u64>().ok())
        .filter(|&v| v > 0)
        .ok_or_else(|| invalid("missing kernel start time"))
}
fn exact_range(text: &str, range: IdRange) -> bool {
    let mut lines = text.lines();
    let Some(row) = lines.next() else {
        return false;
    };
    let mut fields = row.split_ascii_whitespace();
    let mut next = || fields.next().and_then(|s| s.parse::<u32>().ok());
    next() == Some(0)
        && next() == Some(range.start)
        && next() == Some(range.count)
        && fields.next().is_none()
        && lines.next().is_none()
}
fn procfs(dir: &File) -> io::Result<()> {
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(dir.as_raw_fd(), &mut fs) } < 0 {
        return Err(io::Error::last_os_error());
    }
    if fs.f_type != libc::PROC_SUPER_MAGIC {
        return Err(invalid("original process directory is not procfs"));
    }
    Ok(())
}
fn owner_ns(namespace: &File) -> io::Result<File> {
    let raw = unsafe { libc::ioctl(namespace.as_raw_fd(), 0xb701 as libc::c_ulong) };
    if raw < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}

/// A live view of the namespace pins and originating pidfd. Opening a numeric PID
/// directory alone cannot confer this capability.
pub(crate) struct EarlyBoundNamespaces<'a> {
    board: &'a EarlyBoardResources,
    proc: File,
    start: u64,
}
impl<'a> EarlyBoundNamespaces<'a> {
    pub(crate) fn acquire(board: &'a EarlyBoardResources) -> io::Result<Self> {
        board.revalidate()?;
        let proc = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(format!("/proc/{}", board.host_pid()))?;
        procfs(&proc)?;
        let start = start_ticks(
            &fs::read_to_string(proc_path(&proc, "stat"))?,
            board.host_pid() as u32,
        )?;
        let obj = Self { board, proc, start };
        obj.revalidate()?;
        Ok(obj)
    }
    pub(crate) fn user_namespace(&self) -> &File {
        self.board.user_namespace()
    }
    pub(crate) fn proc_directory(&self) -> &File {
        &self.proc
    }
    pub(crate) fn host_pid(&self) -> u32 {
        self.board.host_pid() as u32
    }
    pub(crate) fn start_ticks(&self) -> u64 {
        self.start
    }
    pub(crate) fn descendant_pid_namespace(&self) -> Option<&File> {
        Some(self.board.pid_namespace())
    }
    pub(crate) fn revalidate(&self) -> io::Result<()> {
        self.board.revalidate()?;
        procfs(&self.proc)?;
        if start_ticks(
            &fs::read_to_string(proc_path(&self.proc, "stat"))?,
            self.host_pid(),
        )? != self.start
        {
            return Err(invalid("original Android process changed"));
        }
        for (name, held) in [
            ("user", self.board.user_namespace()),
            ("mnt", self.board.mount_namespace()),
            ("pid", self.board.pid_namespace()),
        ] {
            let current = File::open(proc_path(&self.proc, &format!("ns/{name}")))?;
            let host = File::open(format!("/proc/self/ns/{name}"))?;
            if identity(held)? != identity(&current)? || identity(held)? == identity(&host)? {
                return Err(invalid(
                    "process namespace differs from original Android pin",
                ));
            }
            if name != "user"
                && identity(&owner_ns(held)?)? != identity(self.board.user_namespace())?
            {
                return Err(invalid(
                    "Android namespace is owned by a different user namespace",
                ));
            }
        }
        let spec = self.board.selection().spec();
        if !exact_range(
            &fs::read_to_string(proc_path(&self.proc, "uid_map"))?,
            spec.subordinate_uids,
        ) || !exact_range(
            &fs::read_to_string(proc_path(&self.proc, "gid_map"))?,
            spec.subordinate_gids,
        ) || fs::read_to_string(proc_path(&self.proc, "setgroups"))?.trim() != "allow"
        {
            return Err(invalid(
                "original Android namespace maps no longer match the private selection",
            ));
        }
        crate::production_host_admission::verify_early_root_status(
            &fs::read_to_string(proc_path(&self.proc, "status"))?,
            spec.subordinate_uids,
            spec.subordinate_gids,
        )
        .map_err(io::Error::other)?;
        self.board.revalidate()
    }
    pub(crate) fn admit_host(&self) -> io::Result<HostAdmission> {
        self.revalidate()?;
        let selection = self.board.selection();
        let spec = selection.spec();
        let lease = IdentityAuthority::inspect(spec)
            .and_then(|a| a.reserve(spec, selection.base_cohort()))
            .map_err(io::Error::other)?;
        HostAdmission::acquire_early(lease, self).map_err(io::Error::other)
    }
}

/// The canonical four-image provider borrows the reservation already owned by
/// the manager. It cannot construct an identity from a cohort or descriptor.
pub(crate) struct EarlyBaseAdmission<'a> {
    bound: &'a EarlyBoundNamespaces<'a>,
    host: &'a HostAdmission,
}
impl<'a> EarlyBaseAdmission<'a> {
    pub(crate) fn new(
        bound: &'a EarlyBoundNamespaces<'a>,
        host: &'a HostAdmission,
    ) -> io::Result<Self> {
        let value = Self { bound, host };
        value.revalidate()?;
        Ok(value)
    }
    pub(crate) fn revalidate(&self) -> io::Result<()> {
        self.bound.revalidate()?;
        let selection = self.bound.board.selection();
        let lease = self.identity_lease();
        let spec = selection.spec();
        if lease.host_uid() != spec.host_uid
            || lease.broker_cohort() != selection.base_cohort()
            || lease.broker_ranges() != (spec.subordinate_uids, spec.subordinate_gids)
        {
            return Err(invalid("host reservation and early release differ"));
        }
        self.host
            .revalidate_early(self.bound)
            .map_err(io::Error::other)?;
        self.bound.revalidate()
    }
    pub(crate) fn board(&self) -> &EarlyBoardResources {
        self.bound.board
    }
    pub(crate) fn identity_lease(&self) -> &IdentityLease {
        self.host.lease()
    }
    pub(crate) fn proc_directory(&self) -> &File {
        self.bound.proc_directory()
    }
    pub(crate) fn user_namespace(&self) -> &File {
        self.bound.user_namespace()
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn early_map_requires_exact_single_full_row() {
        let r = IdRange {
            start: 120000,
            count: 100000,
        };
        assert!(exact_range("         0     120000     100000\n", r));
        for v in [
            "0 120000 100000\n0 120000 100000\n",
            "1 120000 100000\n",
            "0 120001 100000",
            "0 120000 99999",
            "0 120000 100000 extra",
        ] {
            assert!(!exact_range(v, r));
        }
    }
    #[test]
    fn early_proc_identity_uses_kernel_start_after_final_comm() {
        let x = format!("921 (wait ) live) S {} 880 8\n", ["0"; 18].join(" "));
        assert_eq!(start_ticks(&x, 921).unwrap(), 880);
        assert!(start_ticks(&x, 922).is_err());
        assert!(start_ticks("921 (renamed task) S 1 2", 921).is_err());
    }
}
