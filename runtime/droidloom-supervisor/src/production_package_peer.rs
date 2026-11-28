//! Kernel socket peer and fixed installed process roles for the package RPC.
//! No caller PID, executable path, MAC role or serialized identity is accepted.

use sha2::{Digest, Sha256};
use std::ffi::{CStr, CString};
use std::fs::{File, Metadata};
use std::io::{self, Read};
use std::os::fd::{AsFd, AsRawFd, BorrowedFd, FromRawFd};
use std::os::unix::fs::{FileExt, MetadataExt};
use std::os::unix::net::UnixStream;
use std::time::Instant;

// Same selected Linux UAPI as production_systemd_endpoint/cgroup, not a PID lookup.
#[path = "production_native_ui_peer.rs"]
mod native_ui;
pub(crate) use native_ui::NativeUiPeer;
#[path = "production_preparation_peer.rs"]
mod preparation;
pub(crate) use preparation::PreparationPeer;
#[path = "production_empty_meituan_peer.rs"]
mod empty_meituan;
pub(crate) use empty_meituan::EmptyMeituanPeer;

const SO_PEERPIDFD: i32 = 77;
const NS_GET_ID: libc::c_ulong = 0x8008_b70d;
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const PROC_MAGIC: libc::c_long = 0x9fa0;
const ELF_LIMIT: u64 = 64 * 1024 * 1024;

fn reject(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, message)
}
pub(super) fn before(deadline: Instant) -> io::Result<()> {
    if Instant::now() >= deadline {
        Err(io::Error::from_raw_os_error(libc::ETIMEDOUT))
    } else {
        Ok(())
    }
}
fn opened(parent: i32, name: &CStr, flags: i32, follow_proc_magic: bool) -> io::Result<File> {
    let fd = unsafe {
        libc::openat(
            parent,
            name.as_ptr(),
            flags
                | libc::O_CLOEXEC
                | if follow_proc_magic {
                    0
                } else {
                    libc::O_NOFOLLOW
                },
        )
    };
    if fd < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(unsafe { File::from_raw_fd(fd) })
    }
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct Seal {
    node: [u64; 7],
    times: [i64; 4],
}
impl Seal {
    fn of(file: &File) -> io::Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            node: [
                m.dev(),
                m.ino(),
                m.mode() as u64,
                m.uid() as u64,
                m.gid() as u64,
                m.nlink(),
                m.len(),
            ],
            times: [m.mtime(), m.mtime_nsec(), m.ctime(), m.ctime_nsec()],
        })
    }
}
fn node(m: &Metadata) -> [u64; 5] {
    [
        m.dev(),
        m.ino(),
        m.mode() as u64,
        m.uid() as u64,
        m.gid() as u64,
    ]
}
fn live(fd: BorrowedFd<'_>) -> io::Result<()> {
    let mut p = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLIN | libc::POLLHUP | libc::POLLERR,
        revents: 0,
    };
    let n = unsafe { libc::poll(&mut p, 1, 0) };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    if n != 0 || p.revents != 0 {
        return Err(reject("original package peer PIDFD is no longer live"));
    }
    Ok(())
}

// A terminal check is intentionally distinct from live process observation.
// Retain the original PIDFD across service stop; never reopen a numeric PID.
fn exited(fd: BorrowedFd<'_>) -> io::Result<()> {
    loop {
        let mut p = libc::pollfd {
            fd: fd.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        let n = unsafe { libc::poll(&mut p, 1, 0) };
        if n < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error);
        }
        if n == 1
            && p.revents & libc::POLLIN != 0
            && p.revents & (libc::POLLERR | libc::POLLNVAL) == 0
        {
            return Ok(());
        }
        return Err(reject("original package broker PIDFD has not exited"));
    }
}
fn proc_text(directory: &File, name: &CStr) -> io::Result<String> {
    let file = opened(
        directory.as_raw_fd(),
        name,
        libc::O_RDONLY | libc::O_NONBLOCK,
        false,
    )?;
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if fs.f_type != PROC_MAGIC {
        return Err(reject("package peer observation is not real procfs"));
    }
    let mut bytes = Vec::new();
    (&file).take(65537).read_to_end(&mut bytes)?;
    if bytes.len() > 65536 {
        return Err(reject("package peer observation bound"));
    }
    String::from_utf8(bytes).map_err(|_| reject("non-UTF8 package peer observation"))
}
fn pidfd_pid(file: &File) -> io::Result<u32> {
    let own_proc = opened(
        libc::AT_FDCWD,
        c"/proc/self",
        libc::O_PATH | libc::O_DIRECTORY,
        true,
    )?;
    let name = CString::new(format!("fdinfo/{}", file.as_raw_fd())).unwrap();
    let text = proc_text(&own_proc, &name)?;
    let pid: Vec<_> = text
        .lines()
        .filter_map(|s| s.strip_prefix("Pid:\t"))
        .collect();
    let ns: Vec<_> = text
        .lines()
        .filter_map(|s| s.strip_prefix("NSpid:\t"))
        .collect();
    if pid.len() != 1 || ns.len() != 1 || pid[0] != ns[0] {
        return Err(reject("PIDFD is not an initial-namespace peer"));
    }
    let value = pid[0]
        .parse::<u32>()
        .map_err(|_| reject("invalid kernel peer PIDFD value"))?;
    if value == 0 {
        return Err(reject("original peer has exited"));
    }
    Ok(value)
}
fn start(text: &str, pid: u32) -> io::Result<u64> {
    let split = text
        .rfind(')')
        .ok_or_else(|| reject("invalid package peer stat"))?;
    let observed = text
        .split_once(' ')
        .and_then(|(value, _)| value.parse::<u32>().ok());
    if observed != Some(pid) {
        return Err(reject("package peer stat PID differs"));
    }
    text[split + 1..]
        .split_whitespace()
        .nth(19)
        .ok_or_else(|| reject("short package peer stat"))?
        .parse()
        .map_err(|_| reject("invalid package peer start time"))
}

/// Ordinary observation core. It does not itself issue a fixed production role.
struct ObservedProcess {
    pidfd: File,
    pid: u32,
    proc: File,
    proc_node: [u64; 5],
    start: u64,
    executable: File,
    executable_seal: Seal,
}
impl ObservedProcess {
    fn capture(pidfd: File, expected_pid: u32) -> io::Result<Self> {
        live(pidfd.as_fd())?;
        if pidfd_pid(&pidfd)? != expected_pid {
            return Err(reject("socket credential and PIDFD differ"));
        }
        let name = CString::new(format!("/proc/{expected_pid}")).unwrap();
        let proc = opened(
            libc::AT_FDCWD,
            &name,
            libc::O_PATH | libc::O_DIRECTORY,
            false,
        )?;
        let executable = opened(proc.as_raw_fd(), c"exe", libc::O_PATH, true)?;
        let value = Self {
            pidfd,
            pid: expected_pid,
            proc_node: node(&proc.metadata()?),
            start: start(&proc_text(&proc, c"stat")?, expected_pid)?,
            executable_seal: Seal::of(&executable)?,
            proc,
            executable,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn peer(stream: &UnixStream) -> io::Result<Self> {
        let mut cred: libc::ucred = unsafe { std::mem::zeroed() };
        let mut len = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
        if unsafe {
            libc::getsockopt(
                stream.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PEERCRED,
                (&mut cred as *mut libc::ucred).cast(),
                &mut len,
            )
        } != 0
        {
            return Err(io::Error::last_os_error());
        }
        if len as usize != std::mem::size_of::<libc::ucred>() || cred.pid <= 0 {
            return Err(reject("incomplete kernel socket peer credentials"));
        }
        let mut fd = -1_i32;
        let mut size = std::mem::size_of::<i32>() as libc::socklen_t;
        if unsafe {
            libc::getsockopt(
                stream.as_raw_fd(),
                libc::SOL_SOCKET,
                SO_PEERPIDFD,
                (&mut fd as *mut i32).cast(),
                &mut size,
            )
        } != 0
        {
            return Err(io::Error::last_os_error());
        }
        if fd < 0 {
            return Err(reject("kernel did not return a socket peer PIDFD"));
        }
        let held = unsafe { File::from_raw_fd(fd) };
        if size as usize != std::mem::size_of::<i32>() {
            return Err(reject("wrong socket peer PIDFD size"));
        }
        if unsafe { libc::fcntl(held.as_raw_fd(), libc::F_SETFD, libc::FD_CLOEXEC) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let value = Self::capture(held, cred.pid as u32)?;
        let status = proc_text(&value.proc, c"status")?;
        for (key, expected) in [("Uid:", cred.uid), ("Gid:", cred.gid)] {
            let rows: Vec<_> = status.lines().filter_map(|s| s.strip_prefix(key)).collect();
            let ids: Vec<u32> = rows
                .first()
                .ok_or_else(|| reject("peer credential row missing"))?
                .split_whitespace()
                .map(str::parse)
                .collect::<Result<_, _>>()
                .map_err(|_| reject("bad peer credentials"))?;
            if rows.len() != 1 || ids.len() != 4 || ids[1] != expected {
                return Err(reject("socket and current peer credentials differ"));
            }
        }
        value.revalidate()?;
        Ok(value)
    }
    fn own() -> io::Result<Self> {
        let pid = unsafe { libc::getpid() };
        if unsafe { libc::syscall(libc::SYS_gettid) } != pid as libc::c_long {
            return Err(reject(
                "fixed package role must run on its original process leader",
            ));
        }
        let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) } as i32;
        if fd < 0 {
            return Err(io::Error::last_os_error());
        }
        Self::capture(unsafe { File::from_raw_fd(fd) }, pid as u32)
    }
    fn revalidate(&self) -> io::Result<()> {
        live(self.pidfd.as_fd())?;
        if pidfd_pid(&self.pidfd)? != self.pid
            || node(&self.proc.metadata()?) != self.proc_node
            || start(&proc_text(&self.proc, c"stat")?, self.pid)? != self.start
        {
            return Err(reject("original package process generation changed"));
        }
        let current = opened(self.proc.as_raw_fd(), c"exe", libc::O_PATH, true)?;
        if Seal::of(&current)? != self.executable_seal
            || Seal::of(&self.executable)? != self.executable_seal
        {
            return Err(reject("original package process executed another inode"));
        }
        live(self.pidfd.as_fd())
    }
}

#[derive(Clone, Copy, Eq, PartialEq)]
enum Role {
    Helper,
    Broker,
}
struct InstalledExecutable {
    directories: Vec<(File, [u64; 5])>,
    file: File,
    seal: Seal,
    digest: [u8; 32],
    role: Role,
}
impl InstalledExecutable {
    fn open(role: Role) -> io::Result<Self> {
        let root = opened(
            libc::AT_FDCWD,
            c"/",
            libc::O_PATH | libc::O_DIRECTORY,
            false,
        )?;
        let mut directories = vec![(root, [0; 5])];
        let parts: &[&CStr] = match role {
            Role::Helper => &[c"usr", c"lib", c"droidloom"],
            Role::Broker => &[c"usr", c"lib", c"droidloom", c"production", c"current"],
        };
        for name in parts {
            let d = opened(
                directories.last().unwrap().0.as_raw_fd(),
                name,
                libc::O_PATH | libc::O_DIRECTORY,
                false,
            )?;
            directories.push((d, [0; 5]));
        }
        for (directory, identity) in &mut directories {
            let m = directory.metadata()?;
            if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {
                return Err(reject("fixed installed role parent is not root controlled"));
            }
            *identity = node(&m);
        }
        let name = match role {
            Role::Helper => c"droidloom-package-helper",
            Role::Broker => c"droidloomd",
        };
        let file = opened(
            directories.last().unwrap().0.as_raw_fd(),
            name,
            libc::O_RDONLY | libc::O_NONBLOCK,
            false,
        )?;
        let m = file.metadata()?;
        if !m.is_file()
            || m.uid() != 0
            || m.gid() != 0
            || m.nlink() != 1
            || m.mode() & 0o7022 != 0
            || m.mode() & 0o111 == 0
            || !(4..=ELF_LIMIT).contains(&m.len())
        {
            return Err(reject("fixed installed executable custody or size differs"));
        }
        let seal = Seal::of(&file)?;
        let mut hash = Sha256::new();
        let mut offset = 0;
        let mut buffer = [0_u8; 65536];
        while offset < m.len() {
            let size = ((m.len() - offset) as usize).min(buffer.len());
            file.read_exact_at(&mut buffer[..size], offset)?;
            if offset == 0 && !buffer[..size].starts_with(b"\x7fELF") {
                return Err(reject("fixed installed role is not an ELF"));
            }
            hash.update(&buffer[..size]);
            offset += size as u64;
        }
        if Seal::of(&file)? != seal {
            return Err(reject("installed executable changed while hashing"));
        }
        Ok(Self {
            directories,
            file,
            seal,
            digest: hash.finalize().into(),
            role,
        })
    }
    fn revalidate(&self) -> io::Result<()> {
        let current = Self::open(self.role)?;
        if current.seal != self.seal
            || current.digest != self.digest
            || current.directories.len() != self.directories.len()
            || Seal::of(&self.file)? != self.seal
        {
            return Err(reject("fixed installed executable changed"));
        }
        for ((held, original), (_, observed)) in self.directories.iter().zip(&current.directories) {
            if node(&held.metadata()?) != *original || original != observed {
                return Err(reject("fixed installed role parent changed"));
            }
        }
        Ok(())
    }
}

/// A fixed live role, built only from self or a kernel-authenticated socket peer.
/// No Deserialize/Clone, numeric-PID constructor or public role selector exists.
pub(crate) struct PackageProcess {
    observed: ObservedProcess,
    installed: InstalledExecutable,
    namespaces: Vec<File>,
}
impl PackageProcess {
    fn bind(observed: ObservedProcess, role: Role) -> io::Result<Self> {
        let installed = InstalledExecutable::open(role)?;
        let mut namespaces = Vec::new();
        for name in [c"ns/user", c"ns/pid"] {
            namespaces.push(opened(
                observed.proc.as_raw_fd(),
                name,
                libc::O_RDONLY,
                true,
            )?);
        }
        let value = Self {
            observed,
            installed,
            namespaces,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(super) fn own_helper() -> io::Result<Self> {
        Self::bind(ObservedProcess::own()?, Role::Helper)
    }
    pub(super) fn own_broker() -> io::Result<Self> {
        Self::bind(ObservedProcess::own()?, Role::Broker)
    }
    pub(super) fn peer_helper(stream: &UnixStream) -> io::Result<Self> {
        Self::bind(ObservedProcess::peer(stream)?, Role::Helper)
    }
    pub(super) fn peer_broker(stream: &UnixStream) -> io::Result<Self> {
        Self::bind(ObservedProcess::peer(stream)?, Role::Broker)
    }
    pub(crate) fn revalidate(&self) -> io::Result<()> {
        self.observed.revalidate()?;
        self.installed.revalidate()?;
        if self.observed.executable_seal != self.installed.seal {
            return Err(reject(
                "peer does not execute the fixed original installed role",
            ));
        }
        let status = proc_text(&self.observed.proc, c"status")?;
        for key in ["Uid:", "Gid:"] {
            let rows: Vec<_> = status.lines().filter_map(|s| s.strip_prefix(key)).collect();
            if rows.len() != 1
                || rows[0].split_whitespace().collect::<Vec<_>>() != ["0", "0", "0", "0"]
            {
                return Err(reject(
                    "fixed package role requires all actual root credentials",
                ));
            }
        }
        for (file, (name, kind, expected)) in self.namespaces.iter().zip([
            (c"ns/user", libc::CLONE_NEWUSER, 3_u64),
            (c"ns/pid", libc::CLONE_NEWPID, 4_u64),
        ]) {
            let mut id = 0_u64;
            let named = opened(self.observed.proc.as_raw_fd(), name, libc::O_RDONLY, true)?;
            if node(&named.metadata()?) != node(&file.metadata()?)
                || unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE, 0 as libc::c_ulong) }
                    != kind
                || unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_ID, &mut id as *mut u64) } != 0
                || id != expected
            {
                return Err(reject("package role left the actual initial namespaces"));
            }
        }
        self.observed.revalidate()
    }
    pub(crate) fn binding(&self) -> [u8; 32] {
        let mut hash = Sha256::new();
        hash.update(b"droidloom-package-process-v1\0");
        hash.update(self.observed.pid.to_le_bytes());
        hash.update(self.observed.start.to_le_bytes());
        for n in self.observed.proc_node {
            hash.update(n.to_le_bytes());
        }
        for n in self.installed.seal.node {
            hash.update(n.to_le_bytes());
        }
        for n in self.installed.seal.times {
            hash.update(n.to_le_bytes());
        }
        hash.update(self.installed.digest);
        hash.update([u8::from(self.is_broker())]);
        hash.finalize().into()
    }
    pub(crate) fn is_broker(&self) -> bool {
        self.installed.role == Role::Broker
    }
    pub(crate) fn verify_exited_broker(&self) -> io::Result<()> {
        if !self.is_broker() {
            return Err(reject(
                "terminal package custody requires the original broker",
            ));
        }
        self.installed.revalidate()?;
        exited(self.observed.pidfd.as_fd())
    }
    pub(crate) fn pidfd(&self) -> BorrowedFd<'_> {
        self.observed.pidfd.as_fd()
    }
    pub(crate) fn proc(&self) -> &File {
        &self.observed.proc
    }
    pub(crate) fn pid(&self) -> u32 {
        self.observed.pid
    }
    pub(crate) fn executable(&self) -> &File {
        &self.installed.file
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn package_original_peer_exit_invalidates_its_held_pidfd_and_proc_observation() {
        use std::io::{Read, Write};
        use std::os::unix::net::UnixListener;
        use std::process::{Child, Command, Stdio};
        use std::time::Duration;
        const SOCKET_ENV: &str = "DROIDLOOM_PACKAGE_PEER_TEST_SOCKET";
        const CASE: &str = "control::package::peer::tests::package_original_peer_exit_invalidates_its_held_pidfd_and_proc_observation";
        if let Some(path) = std::env::var_os(SOCKET_ENV) {
            let mut socket = UnixStream::connect(path).unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            socket
                .set_write_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            socket.write_all(b"R").unwrap();
            let mut byte = [0];
            socket.read_exact(&mut byte).unwrap();
            assert_eq!(byte, *b"X");
            return;
        }
        struct OriginalChild {
            child: Child,
            pidfd: Option<File>,
            reaped: bool,
        }
        impl OriginalChild {
            fn finish(&mut self, kill: bool) -> io::Result<std::process::ExitStatus> {
                if kill {
                    if let Some(fd) = &self.pidfd {
                        let rc = unsafe {
                            libc::syscall(
                                libc::SYS_pidfd_send_signal,
                                fd.as_raw_fd(),
                                libc::SIGKILL,
                                std::ptr::null::<libc::siginfo_t>(),
                                0,
                            )
                        };
                        if rc < 0 && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
                        {
                            return Err(io::Error::last_os_error());
                        }
                    } else {
                        // Only the direct, never-reaped std::process::Child.
                        // This fallback is solely initialization-error cleanup.
                        self.child.kill()?;
                    }
                }
                let deadline = Instant::now() + Duration::from_secs(3);
                loop {
                    if let Some(status) = self.child.try_wait()? {
                        self.reaped = true;
                        return Ok(status);
                    }
                    before(deadline)?;
                    std::thread::sleep(Duration::from_millis(5));
                }
            }
        }
        impl Drop for OriginalChild {
            fn drop(&mut self) {
                if !self.reaped {
                    let _ = self.finish(true);
                }
            }
        }
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("peer.sock");
        let listener = UnixListener::bind(&path).unwrap();
        listener.set_nonblocking(true).unwrap();
        let child = Command::new(std::env::current_exe().unwrap())
            .args(["--exact", CASE, "--nocapture"])
            .env(SOCKET_ENV, &path)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::inherit())
            .spawn()
            .unwrap();
        let mut owned = OriginalChild {
            child,
            pidfd: None,
            reaped: false,
        };
        let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, owned.child.id(), 0) } as i32;
        assert!(
            fd >= 0,
            "direct-child PIDFD: {}",
            io::Error::last_os_error()
        );
        owned.pidfd = Some(unsafe { File::from_raw_fd(fd) });
        let deadline = Instant::now() + Duration::from_secs(3);
        let mut socket = loop {
            match listener.accept() {
                Ok((socket, _)) => break socket,
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                    before(deadline).unwrap();
                    std::thread::sleep(Duration::from_millis(5));
                }
                Err(error) => panic!("accept original test peer: {error}"),
            }
        };
        socket
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        socket
            .set_write_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        let mut ready = [0];
        socket.read_exact(&mut ready).unwrap();
        assert_eq!(ready, *b"R");
        let peer = ObservedProcess::peer(&socket).unwrap();
        assert_eq!(peer.pid, owned.child.id());
        peer.revalidate().unwrap();
        assert!(exited(peer.pidfd.as_fd()).is_err());
        socket.write_all(b"X").unwrap();
        assert!(owned.finish(false).unwrap().success());
        assert!(peer.revalidate().is_err());
        assert!(live(peer.pidfd.as_fd()).is_err());
        exited(peer.pidfd.as_fd()).unwrap();
        // A new live process cannot replace the original held terminal peer.
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0) };
        assert!(raw >= 0);
        let current = unsafe { File::from_raw_fd(raw as i32) };
        assert!(exited(current.as_fd()).is_err());
        exited(peer.pidfd.as_fd()).unwrap();
        assert_eq!(socket.read(&mut [0_u8; 1]).unwrap(), 0);
    }

    #[test]
    fn package_socket_peer_is_derived_from_the_kernel_and_revalidated() {
        let (left, right) = UnixStream::pair().unwrap();
        let peer = ObservedProcess::peer(&left).unwrap();
        assert_eq!(peer.pid, unsafe { libc::getpid() } as u32);
        peer.revalidate().unwrap();
        assert!(PackageProcess::peer_helper(&right).is_err());
        assert!(PackageProcess::peer_broker(&left).is_err());
        peer.revalidate().unwrap();
    }
}
