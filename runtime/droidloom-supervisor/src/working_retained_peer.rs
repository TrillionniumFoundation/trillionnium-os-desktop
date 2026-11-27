//! Actual fixed retained-original child of the live working parent.
//! Neither a PID number nor a receipt constructs this proof: admission requires
//! a held PIDFD, current kernel credentials, both MACs and the normal ELF.
use super::{ControlError, io_error};
use crate::native_working_contract::retained_data as c;
use crate::production_frontend_protocol as peer;
use std::{
    ffi::{CStr, CString},
    fs::{self, File, Metadata, OpenOptions},
    io::Read,
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::fs::{MetadataExt, OpenOptionsExt},
    },
    path::Path,
    time::Instant,
};
pub(crate) const ARG: &str = "--owned-working-retained-data";
pub(crate) const ROLE: &[u8] = b"u:system_r:p4_linux_working_retained_data_t:s0";
pub(crate) const PROFILE: &[u8] = b"droidloom-working-retained-data (enforce)";
const CGROUP: &[u8] = b"0::/system.slice/droidloom-working-qualification.service\n";
type Result<T> = std::result::Result<T, ControlError>;
fn cv<T>(v: std::io::Result<T>) -> Result<T> {
    v.map_err(|e| io_error("observe actual retained helper", e))
}
fn reject(why: &str) -> ControlError {
    ControlError::Invalid(why.into())
}
#[derive(Clone, Copy, Eq, PartialEq)]
struct Node {
    values: [u64; 7],
    times: [i64; 4],
}
fn node(m: &Metadata) -> Node {
    Node {
        values: [
            m.dev(),
            m.ino(),
            u64::from(m.mode()),
            u64::from(m.uid()),
            u64::from(m.gid()),
            m.nlink(),
            m.len(),
        ],
        times: [m.mtime(), m.mtime_nsec(), m.ctime(), m.ctime_nsec()],
    }
}
fn open(parent: &File, name: &CStr, flags: i32) -> Result<File> {
    let fd = unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), flags | libc::O_CLOEXEC) };
    if fd < 0 {
        return Err(io_error(
            "open actual retained helper component",
            std::io::Error::last_os_error(),
        ));
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn bounded(process: &File, name: &CStr) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    cv(open(process, name, libc::O_RDONLY | libc::O_NOFOLLOW)?
        .take(8193)
        .read_to_end(&mut bytes))?;
    if bytes.len() > 8192 {
        return Err(reject("retained helper metadata exceeds source bound"));
    }
    Ok(bytes)
}
fn strip(v: &[u8]) -> &[u8] {
    let v = v.strip_suffix(b"\n").unwrap_or(v);
    v.strip_suffix(&[0]).unwrap_or(v)
}
fn fixed(argv: &[u8], group: &[u8], se: &[u8], aa: &[u8], parent: u32, actual: u32) -> Result<()> {
    let expected = format!("{}\0{}\0", c::HELPER_PATH, ARG);
    if argv != expected.as_bytes()
        || group != CGROUP
        || strip(se) != ROLE
        || strip(aa) != PROFILE
        || actual != parent
        || parent <= 1
    {
        return Err(reject(
            "retained helper differs from the exact live parent/argv/cgroup/MAC",
        ));
    }
    Ok(())
}
pub(crate) struct RetainedHelperPeer {
    pidfd: File,
    pid: u32,
    parent: u32,
    process: File,
    process_node: Node,
    parents: Vec<(String, File, Node)>,
    executable: File,
    executable_node: Node,
}
impl RetainedHelperPeer {
    pub(crate) fn capture(pidfd: &File, parent: u32, end: Instant) -> Result<Self> {
        if Instant::now() >= end {
            return Err(reject("retained helper admission expired"));
        }
        let pidfd = cv(pidfd.try_clone())?;
        let info = cv(peer::pid_info(&pidfd))?;
        cv(peer::exact_ids(&info, 0, 0))?;
        if info.ppid != parent || parent <= 1 {
            return Err(reject("actual retained helper is not this parent child"));
        }
        let process = cv(OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW)
            .open(format!("/proc/{}", info.pid)))?;
        let process_node = node(&cv(process.metadata())?);
        let mut parents = Vec::new();
        for path in [
            "/",
            "/usr",
            "/usr/lib",
            "/usr/lib/droidloom",
            "/usr/lib/droidloom/qualification",
        ] {
            let file = cv(OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW)
                .open(path))?;
            let m = cv(file.metadata())?;
            if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {
                return Err(reject(
                    "normal retained helper parent is not protected root",
                ));
            }
            parents.push((path.into(), file, node(&m)));
        }
        let executable = open(
            &parents.last().expect("helper parent").1,
            c"working-retained-data",
            libc::O_RDONLY | libc::O_NOFOLLOW,
        )?;
        let m = cv(executable.metadata())?;
        if !m.is_file()
            || m.uid() != 0
            || m.gid() != 0
            || m.nlink() != 1
            || m.mode() & 0o7777 != 0o755
            || !(1024..=c::MAX_HELPER_BYTES).contains(&m.len())
        {
            return Err(reject("retained helper is not the fixed normal executable"));
        }
        let result = Self {
            pidfd,
            pid: info.pid,
            parent,
            process,
            process_node,
            parents,
            executable,
            executable_node: node(&m),
        };
        result.guard()?;
        if Instant::now() >= end {
            return Err(reject("retained helper admission expired"));
        }
        Ok(result)
    }
    pub(crate) fn guard(&self) -> Result<()> {
        let info = cv(peer::pid_info(&self.pidfd))?;
        cv(peer::exact_ids(&info, 0, 0))?;
        if info.pid != self.pid {
            return Err(reject("retained helper PIDFD generation changed"));
        }
        let named = cv(OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW)
            .open(format!("/proc/{}", self.pid)))?;
        if node(&cv(named.metadata())?) != self.process_node
            || node(&cv(self.process.metadata())?) != self.process_node
        {
            return Err(reject("retained helper actual proc inode changed"));
        }
        fixed(
            &bounded(&self.process, c"cmdline")?,
            &bounded(&self.process, c"cgroup")?,
            &bounded(&self.process, c"attr/selinux/current")?,
            &bounded(&self.process, c"attr/apparmor/current")?,
            self.parent,
            info.ppid,
        )?;
        for (i, (path, file, pin)) in self.parents.iter().enumerate() {
            let named = if i == 0 {
                cv(OpenOptions::new()
                    .read(true)
                    .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW)
                    .open("/"))?
            } else {
                open(
                    &self.parents[i - 1].1,
                    &CString::new(
                        Path::new(path)
                            .file_name()
                            .expect("fixed parent")
                            .as_encoded_bytes(),
                    )
                    .map_err(|e| reject(&e.to_string()))?,
                    libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
                )?
            };
            if node(&cv(file.metadata())?).values[..5] != pin.values[..5]
                || node(&cv(named.metadata())?).values[..5] != pin.values[..5]
            {
                return Err(reject("retained normal helper parent changed"));
            }
        }
        let named = open(
            &self.parents.last().expect("helper parent").1,
            c"working-retained-data",
            libc::O_RDONLY | libc::O_NOFOLLOW,
        )?;
        let executing = open(&self.process, c"exe", libc::O_RDONLY)?;
        if cv(fs::read_link(format!("/proc/{}/exe", self.pid)))? != Path::new(c::HELPER_PATH)
            || [
                node(&cv(named.metadata())?),
                node(&cv(executing.metadata())?),
                node(&cv(self.executable.metadata())?),
            ]
            .iter()
            .any(|v| *v != self.executable_node)
        {
            return Err(reject(
                "retained helper lost its exact normal installed executable",
            ));
        }
        cv(peer::live(&self.pidfd))
    }
    pub(crate) fn pid(&self) -> u32 {
        self.pid
    }
    pub(crate) fn parent_pid(&self) -> u32 {
        self.parent
    }
    pub(crate) fn pidfd(&self) -> &File {
        &self.pidfd
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn retained_helper_requires_exact_fixed_process_not_a_receipt() {
        let args = format!("{}\0{}\0", c::HELPER_PATH, ARG);
        fixed(args.as_bytes(), CGROUP, ROLE, PROFILE, 10, 10).unwrap();
        for (argv, group, se, aa, wanted, actual) in [
            (
                b"/usr/bin/droidloom-applications\0".as_slice(),
                CGROUP,
                ROLE,
                PROFILE,
                10,
                10,
            ),
            (
                args.as_bytes(),
                b"0::/system.slice/other.service\n",
                ROLE,
                PROFILE,
                10,
                10,
            ),
            (
                args.as_bytes(),
                CGROUP,
                b"u:system_r:p4_linux_working_qualification_t:s0",
                PROFILE,
                10,
                10,
            ),
            (
                args.as_bytes(),
                CGROUP,
                ROLE,
                b"droidloom-working-retained-data (complain)",
                10,
                10,
            ),
            (args.as_bytes(), CGROUP, ROLE, PROFILE, 10, 11),
            (args.as_bytes(), CGROUP, ROLE, PROFILE, 1, 1),
        ] {
            assert!(fixed(argv, group, se, aa, wanted, actual).is_err());
        }
    }
    #[test]
    fn a_regular_file_cannot_substitute_for_the_actual_helper_pidfd() {
        let file = tempfile::tempfile().unwrap();
        assert!(
            RetainedHelperPeer::capture(
                &file,
                10,
                Instant::now() + std::time::Duration::from_secs(1)
            )
            .is_err()
        );
    }
}
