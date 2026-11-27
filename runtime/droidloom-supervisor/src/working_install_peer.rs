//! Actual normal working parent of a current-epoch atomic APK update.
//! This object is never deserialized. It holds the original socket/PIDFD and
//! fixed installed executable while the broker performs every PM command.
use super::{ControlError, io_error};
use crate::production_frontend_protocol as peer;
use std::ffi::CStr;
use std::fs::{File, Metadata, OpenOptions};
use std::io::Read;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::os::unix::net::UnixStream;
use std::time::Instant;
const EXE: &str = "/usr/bin/droidloom-applications";
const SELINUX: &[u8] = b"u:system_r:p4_linux_working_qualification_t:s0";
const APPARMOR: &[u8] = b"droidloom-working-qualification (enforce)";
const ARGV: &[u8] = b"/usr/bin/droidloom-applications\0--owned-working-qualification\0";
const CGROUP: &[u8] = b"0::/system.slice/droidloom-working-qualification.service\n";
type Result<T> = std::result::Result<T, ControlError>;
fn reject(value: impl Into<String>) -> ControlError {
    ControlError::Invalid(value.into())
}
fn cv<T>(value: std::io::Result<T>) -> Result<T> {
    value.map_err(|e| io_error("observe actual working installation caller", e))
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
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
fn open_at(parent: &File, name: &CStr, flags: i32) -> Result<File> {
    let raw = unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), flags | libc::O_CLOEXEC) };
    if raw < 0 {
        return Err(io_error(
            "open held working caller component",
            std::io::Error::last_os_error(),
        ));
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}
fn bounded(process: &File, name: &CStr) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    cv(open_at(process, name, libc::O_RDONLY | libc::O_NOFOLLOW)?
        .take(8193)
        .read_to_end(&mut bytes))?;
    if bytes.len() > 8192 {
        return Err(reject("working caller metadata exceeds its fixed bound"));
    }
    Ok(bytes)
}
fn label(bytes: &[u8]) -> &[u8] {
    let value = bytes.strip_suffix(b"\n").unwrap_or(bytes);
    value.strip_suffix(&[0]).unwrap_or(value)
}
fn fixed_observations(
    argv: &[u8],
    cgroup: &[u8],
    selinux: &[u8],
    apparmor: &[u8],
    ppid: u32,
) -> Result<()> {
    if argv != ARGV
        || cgroup != CGROUP
        || label(selinux) != SELINUX
        || label(apparmor) != APPARMOR
        || ppid != 1
    {
        return Err(reject(
            "current installation requires the exact live normal PID1 working parent",
        ));
    }
    Ok(())
}
pub(crate) struct WorkingInstallPeer {
    socket: UnixStream,
    peer: peer::Peer,
    process: File,
    process_path: String,
    process_node: peer::Node,
    parents: Vec<(File, Node)>,
    executable: File,
    executable_node: Node,
}
impl WorkingInstallPeer {
    pub(crate) fn capture(socket: &UnixStream, deadline: Instant) -> Result<Self> {
        if Instant::now() >= deadline {
            return Err(reject("working installation caller admission expired"));
        }
        let socket = cv(socket.try_clone())?;
        // On the selected joint-LSM stream SO_PEERSEC is AppArmor. The separate
        // actual SELinux current attribute is checked below, never inferred.
        let actual = cv(peer::Peer::acquire_as(&socket, APPARMOR, libc::SOCK_STREAM))?;
        if actual.uid != 0 || actual.gid != 0 {
            return Err(reject(
                "working installation caller is not the normal root owner",
            ));
        }
        let process_path = format!("/proc/{}", actual.pid);
        let process = cv(OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW)
            .open(&process_path))?;
        let process_node = cv(peer::Node::of(&process))?;
        let mut parents = Vec::new();
        let root = cv(OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW)
            .open("/"))?;
        parents.push((
            root,
            Node {
                values: [0; 7],
                times: [0; 4],
            },
        ));
        for name in [c"usr", c"bin"] {
            let directory = open_at(
                &parents.last().expect("root").0,
                name,
                libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
            )?;
            parents.push((
                directory,
                Node {
                    values: [0; 7],
                    times: [0; 4],
                },
            ));
        }
        for (file, initial) in &mut parents {
            let m = cv(file.metadata())?;
            if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {
                return Err(reject(
                    "fixed installed working caller has an untrusted parent",
                ));
            }
            *initial = node(&m);
        }
        let executable = open_at(
            &parents.last().expect("bin").0,
            c"droidloom-applications",
            libc::O_RDONLY | libc::O_NOFOLLOW,
        )?;
        let m = cv(executable.metadata())?;
        if !m.is_file()
            || m.uid() != 0
            || m.gid() != 0
            || m.nlink() != 1
            || m.mode() & 0o022 != 0
            || m.mode() & 0o111 == 0
            || !(1024..=64 * 1024 * 1024).contains(&m.len())
        {
            return Err(reject(
                "working installation caller differs from the normal fixed executable",
            ));
        }
        let executable_node = node(&m);
        let result = Self {
            socket,
            peer: actual,
            process,
            process_path,
            process_node,
            parents,
            executable,
            executable_node,
        };
        result.guard()?;
        if Instant::now() >= deadline {
            return Err(reject("working installation caller admission expired"));
        }
        Ok(result)
    }
    pub(crate) fn pid(&self) -> u32 { self.peer.pid }
    pub(crate) fn guard(&self) -> Result<()> {
        cv(self.peer.revalidate(&self.socket))?;
        let info = cv(peer::pid_info(&self.peer.pidfd))?;
        cv(peer::exact_ids(&info, 0, 0))?;
        let current = cv(OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW)
            .open(&self.process_path))?;
        if cv(peer::Node::of(&current))? != self.process_node
            || cv(peer::Node::of(&self.process))? != self.process_node
        {
            return Err(reject(
                "held working installation process directory changed",
            ));
        }
        fixed_observations(
            &bounded(&self.process, c"cmdline")?,
            &bounded(&self.process, c"cgroup")?,
            &bounded(&self.process, c"attr/selinux/current")?,
            &bounded(&self.process, c"attr/apparmor/current")?,
            info.ppid,
        )?;
        for (index, (held, initial)) in self.parents.iter().enumerate() {
            let m = cv(held.metadata())?;
            if node(&m).values[..6] != initial.values[..6] {
                return Err(reject(
                    "working installed executable parent identity changed",
                ));
            }
            let named = if index == 0 {
                cv(OpenOptions::new()
                    .read(true)
                    .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW)
                    .open("/"))?
            } else {
                open_at(
                    &self.parents[index - 1].0,
                    if index == 1 { c"usr" } else { c"bin" },
                    libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
                )?
            };
            if node(&cv(named.metadata())?).values[..6] != initial.values[..6] {
                return Err(reject("working installed executable parent was replaced"));
            }
        }
        let named = open_at(
            &self.parents.last().expect("bin").0,
            c"droidloom-applications",
            libc::O_RDONLY | libc::O_NOFOLLOW,
        )?;
        // proc exe is the one intentional kernel-owned symlink follow. Both the
        // link text and the resulting open inode must be the held normal file.
        let actual = open_at(&self.process, c"exe", libc::O_RDONLY)?;
        if cv(std::fs::read_link(format!("{}/exe", self.process_path)))?
            != std::path::Path::new(EXE)
            || [
                node(&cv(self.executable.metadata())?),
                node(&cv(named.metadata())?),
                node(&cv(actual.metadata())?),
            ]
            .iter()
            .any(|n| *n != self.executable_node)
        {
            return Err(reject(
                "actual working installation caller executable changed",
            ));
        }
        cv(self.peer.revalidate(&self.socket))
    }
}
pub(super) fn validate_current_payload(file: &File, lengths: &[u64]) -> Result<()> {
    // This is deliberately the original 1..32 sealed transport validator.
    // The legacy split-only entry rejects one APK and is not this request.
    super::apk_payload::validate(file, lengths)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn current_source_requires_exact_parent_argv_cgroup_and_both_live_profiles() {
        fixed_observations(ARGV, CGROUP, SELINUX, APPARMOR, 1).unwrap();
        for (argv, cgroup, se, aa, ppid) in [
            (
                &b"/usr/bin/droidloom-applications\0--physical-suite\0"[..],
                CGROUP,
                SELINUX,
                APPARMOR,
                1,
            ),
            (
                ARGV,
                &b"0::/system.slice/other.service\n"[..],
                SELINUX,
                APPARMOR,
                1,
            ),
            (
                ARGV,
                CGROUP,
                &b"u:system_r:p4_linux_working_application_t:s0"[..],
                APPARMOR,
                1,
            ),
            (
                ARGV,
                CGROUP,
                SELINUX,
                &b"droidloom-working-qualification (complain)"[..],
                1,
            ),
            (ARGV, CGROUP, SELINUX, APPARMOR, 2),
        ] {
            assert!(fixed_observations(argv, cgroup, se, aa, ppid).is_err());
        }
    }
    #[test]
    fn current_payload_accepts_real_sealed_single_and_split_originals() {
        let single = super::super::apk_payload::test_payload(b"PK\x03\x04base");
        validate_current_payload(&single, &[8]).unwrap();
        assert!(validate_current_payload(&single, &[9]).is_err());
        let split = super::super::apk_payload::test_payload(b"PK\x03\x04basePK\x03\x04config");
        validate_current_payload(&split, &[8, 10]).unwrap();
        assert!(validate_current_payload(&split, &[9, 9]).is_err());
        assert!(validate_current_payload(&single, &[]).is_err());
    }
    #[test]
    fn unrelated_actual_stream_cannot_construct_a_working_installation_owner() {
        let (a, _b) = UnixStream::pair().unwrap();
        assert!(
            WorkingInstallPeer::capture(&a, Instant::now() + std::time::Duration::from_secs(1))
                .is_err()
        );
    }
}
