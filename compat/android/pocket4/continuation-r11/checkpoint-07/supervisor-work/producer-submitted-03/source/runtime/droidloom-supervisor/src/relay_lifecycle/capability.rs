//! Lifecycle-owned process and artifact handles; no numeric peer fallback.
use super::domain::{self, Identity};
use super::policy::{self, RelayArtifact};
use sha2::{Digest, Sha256};
use std::ffi::CString;
use std::fs::File;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::{FileExt, MetadataExt};
use std::path::Path;
use std::process::Child;
use std::time::{Duration, Instant};

pub(crate) const NS_NAMES: [&str; 10] = ["pid", "pid_for_children", "mnt", "cgroup", "user", "net", "ipc", "uts", "time", "time_for_children"];
const NS_TYPES: [i32; 10] = [libc::CLONE_NEWPID, libc::CLONE_NEWPID, libc::CLONE_NEWNS, libc::CLONE_NEWCGROUP,
    libc::CLONE_NEWUSER, libc::CLONE_NEWNET, libc::CLONE_NEWIPC, libc::CLONE_NEWUTS, 0x80, 0x80];
const PROC_MAGIC: libc::c_long = 0x9fa0;
const NSFS_MAGIC: libc::c_long = 0x6e73_6673;
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
fn error(message: &'static str) -> io::Error { domain::error(message) }
pub(crate) fn kernel_link(parent: &File, name: &str, flags: i32) -> io::Result<File> {
    let name = CString::new(name).map_err(|_| error("invalid fixed proc link"))?;
    // Only kernel-owned exe/root/ns/map_files links, below an already pinned
    // proc directory, may use this helper. No request supplies this pathname.
    let raw = unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), flags | libc::O_CLOEXEC) };
    if raw < 0 { Err(io::Error::last_os_error()) } else {
        // SAFETY: openat returned one fresh descriptor.
        Ok(unsafe { File::from_raw_fd(raw) })
    }
}
fn birth(text: &str, pid: i32) -> io::Result<u64> {
    let (front, tail) = text.rsplit_once(')').ok_or_else(|| error("proc stat is truncated"))?;
    let wanted = pid.to_string();
    if front.split_whitespace().next() != Some(wanted.as_str()) {
        return Err(error("proc stat PID view differs"));
    }
    tail.split_whitespace().nth(19).ok_or_else(|| error("proc birth field missing"))?
        .parse().map_err(|_| error("invalid proc birth"))
}
fn status_numbers(text: &str, key: &str) -> io::Result<Vec<u64>> {
    let mut lines = text.lines().filter_map(|line| line.strip_prefix(key));
    let values = lines.next().ok_or_else(|| error("proc status key missing"))?;
    if lines.next().is_some() { return Err(error("proc status key repeated")); }
    values.split_whitespace().map(|value| value.parse().map_err(|_| error("invalid proc status number"))).collect()
}
fn scalar(text: &str, key: &str) -> io::Result<u64> {
    let values = status_numbers(text, key)?;
    if values.len() != 1 { return Err(error("proc scalar has multiple values")); }
    Ok(values[0])
}
fn host_proc() -> io::Result<File> {
    let root = domain::directory(Path::new("/proc"))?;
    domain::filesystem(&root, PROC_MAGIC)?;
    let stat = domain::read(kernel_link(&root, "self/stat", libc::O_RDONLY)?, 65536)?;
    birth(&stat, unsafe { libc::getpid() })?;
    Ok(root)
}
fn pidfd_number(root: &File, descriptor: RawFd) -> io::Result<i32> {
    let info = domain::read(kernel_link(root, &format!("thread-self/fdinfo/{descriptor}"), libc::O_RDONLY)?, 65536)?;
    let number = scalar(&info, "Pid:")?;
    let pid = i32::try_from(number).map_err(|_| error("pidfd PID exceeds host range"))?;
    if pid <= 0 { return Err(error("pidfd no longer identifies a live host process")); }
    Ok(pid)
}

pub(crate) struct Process {
    pid: i32,
    pidfd: File,
    proc: File,
    start: u64,
}
impl Process {
    /// Child ownership is retained by the caller throughout pinning.
    pub(crate) fn from_child(child: &mut Child) -> io::Result<Self> {
        if child.try_wait()?.is_some() { return Err(error("owned child already exited")); }
        let pid = i32::try_from(child.id()).map_err(|_| error("owned child PID overflow"))?;
        // SAFETY: exact unreaped std::process::Child cannot be PID-reused.
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
        if raw < 0 { return Err(io::Error::last_os_error()); }
        // SAFETY: successful pidfd_open returns a fresh owned descriptor.
        let result = Self::from_received_pidfd(unsafe { File::from_raw_fd(raw as i32) })?;
        if result.pid != pid || child.try_wait()?.is_some() { return Err(error("owned child changed while pinning")); }
        Ok(result)
    }
    /// A received pidfd never authenticates a role by itself. The HELLO caller
    /// must additionally check exact owned parent, credentials, namespaces,
    /// root projection and independently pinned executables before use.
    pub(crate) fn from_received_pidfd(pidfd: File) -> io::Result<Self> {
        let flags = unsafe { libc::fcntl(pidfd.as_raw_fd(), libc::F_GETFD) };
        if flags < 0 || flags & libc::FD_CLOEXEC == 0 { return Err(error("received pidfd is not CLOEXEC")); }
        let root = host_proc()?;
        let pid = pidfd_number(&root, pidfd.as_raw_fd())?;
        let proc = domain::named(&root, &pid.to_string(), libc::O_RDONLY | libc::O_DIRECTORY)?;
        let start = birth(&domain::read_name(&proc, "stat")?, pid)?;
        let status = domain::read_name(&proc, "status")?;
        if scalar(&status, "Pid:")? != pid as u64 || scalar(&status, "Tgid:")? != pid as u64
            || pidfd_number(&root, pidfd.as_raw_fd())? != pid {
            return Err(error("received pidfd is not a stable host process leader"));
        }
        let result = Self { pid, pidfd, proc, start };
        result.live()?; Ok(result)
    }
    pub(crate) fn pid(&self) -> i32 { self.pid }
    pub(crate) fn start(&self) -> u64 { self.start }
    pub(crate) fn fd(&self) -> &File { &self.pidfd }
    pub(crate) fn proc(&self) -> &File { &self.proc }
    pub(crate) fn try_clone(&self) -> io::Result<Self> {
        self.live()?;
        Ok(Self { pid: self.pid, pidfd: self.pidfd.try_clone()?, proc: self.proc.try_clone()?, start: self.start })
    }
    pub(crate) fn dead(&self) -> io::Result<bool> {
        let mut item = libc::pollfd { fd: self.pidfd.as_raw_fd(), events: libc::POLLIN, revents: 0 };
        let result = unsafe { libc::poll(&mut item, 1, 0) };
        if result < 0 { return Err(io::Error::last_os_error()); }
        if item.revents & (libc::POLLERR | libc::POLLNVAL) != 0 { return Err(error("pidfd poll fault")); }
        Ok(result > 0 && item.revents & (libc::POLLIN | libc::POLLHUP) != 0)
    }
    pub(crate) fn live(&self) -> io::Result<()> {
        if self.dead()? || birth(&domain::read_name(&self.proc, "stat")?, self.pid)? != self.start {
            return Err(error("owned process generation is dead or changed"));
        }
        Ok(())
    }
    pub(crate) fn signal(&self, signal: i32) -> io::Result<()> {
        if self.dead()? { return Ok(()); }
        let result = unsafe { libc::syscall(libc::SYS_pidfd_send_signal, self.pidfd.as_raw_fd(), signal,
            std::ptr::null::<libc::siginfo_t>(), 0) };
        if result < 0 {
            let error = io::Error::last_os_error();
            if error.raw_os_error() != Some(libc::ESRCH) || !self.dead()? { return Err(error); }
        }
        Ok(())
    }
    pub(crate) fn require_dead(&self, timeout: Duration) -> io::Result<()> {
        let deadline = Instant::now() + timeout;
        loop {
            if self.dead()? { return Ok(()); }
            if Instant::now() >= deadline { return Err(error("exact process retirement timed out")); }
            std::thread::sleep(Duration::from_millis(1));
        }
    }
    pub(crate) fn validate_init_child(&self, owner: &Process) -> io::Result<()> {
        owner.live()?; self.live()?;
        let status = domain::read_name(&self.proc, "status")?;
        if status_numbers(&status, "Uid:")? != [0; 4] || status_numbers(&status, "Gid:")? != [0; 4]
            || scalar(&status, "PPid:")? != owner.pid as u64 {
            return Err(error("HELLO peer is not the owned root init child"));
        }
        let pids = status_numbers(&status, "NSpid:")?;
        if pids.len() < 2 || pids.first() != Some(&(self.pid as u64)) || pids.last() != Some(&1) {
            return Err(error("HELLO peer is not private Android PID1"));
        }
        let cmdline = domain::read(domain::named(&self.proc, "cmdline", libc::O_RDONLY)?, 1024)?;
        if cmdline.as_bytes() != b"/init\0second_stage\0" {
            return Err(error("HELLO peer is not exact second-stage init"));
        }
        self.live()?; owner.live()
    }
    pub(crate) fn validate_namespaces(&self, supplied: &[File]) -> io::Result<()> {
        self.live()?;
        if supplied.len() != NS_NAMES.len() { return Err(error("init namespace handle count differs")); }
        for (index, name) in NS_NAMES.iter().enumerate() {
            domain::filesystem(&supplied[index], NSFS_MAGIC)?;
            if unsafe { libc::ioctl(supplied[index].as_raw_fd(), NS_GET_NSTYPE) } != NS_TYPES[index] {
                return Err(error("init namespace handle type/order differs"));
            }
            let current = kernel_link(&self.proc, &format!("ns/{name}"), libc::O_RDONLY)?;
            if Identity::of(&current)? != Identity::of(&supplied[index])? {
                return Err(error("init namespace handle is outside the exact process"));
            }
        }
        self.live()
    }
    pub(crate) fn root(&self) -> io::Result<File> {
        self.live()?; kernel_link(&self.proc, "root", libc::O_RDONLY | libc::O_DIRECTORY)
    }
    pub(crate) fn executable(&self) -> io::Result<File> {
        self.live()?; kernel_link(&self.proc, "exe", libc::O_RDONLY)
    }
    pub(crate) fn require_preload(&self, expected: &str) -> io::Result<()> {
        let text = domain::read(domain::named(&self.proc, "environ", libc::O_RDONLY)?, 128 * 1024)?;
        let mut values = text.split('\0').filter_map(|entry| entry.strip_prefix("LD_PRELOAD="));
        if values.next() != Some(expected) || values.next().is_some() {
            return Err(error("actual init preload differs from the exact paired contract"));
        }
        self.live()
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Stamp {
    id: Identity, bytes: u64, mode: u32, uid: u32, gid: u32, modified: (i64, i64), changed: (i64, i64),
}
fn stamp(file: &File, execute: bool, owner: u32) -> io::Result<Stamp> {
    let metadata = file.metadata()?;
    if !metadata.is_file() || metadata.size() == 0 || metadata.size() > 128 * 1024 * 1024
        || metadata.uid() != owner || metadata.mode() & 0o022 != 0
        || (execute && (metadata.mode() & 0o111 == 0 || metadata.mode() & 0o6000 != 0)) {
        return Err(error("package artifact type/size/ownership/mode differs"));
    }
    if execute {
        // Executing a privileged image can clear PR_SET_PDEATHSIG and make
        // AT_SECURE suppress LD_PRELOAD. Neither transition is admissible.
        let count = unsafe { libc::fgetxattr(file.as_raw_fd(), c"security.capability".as_ptr(),
            std::ptr::null_mut(), 0) };
        if count >= 0 { return Err(error("executable carries file capabilities")); }
        let code = io::Error::last_os_error().raw_os_error();
        if code != Some(libc::ENODATA) && code != Some(libc::EOPNOTSUPP) {
            return Err(error("cannot establish executable has no file capabilities"));
        }
    }
    Ok(Stamp { id: Identity::of(file)?, bytes: metadata.size(), mode: metadata.mode(), uid: metadata.uid(),
        gid: metadata.gid(), modified: (metadata.mtime(), metadata.mtime_nsec()), changed: (metadata.ctime(), metadata.ctime_nsec()) })
}
pub(crate) fn hash(file: &File) -> io::Result<[u8; 32]> {
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    let mut offset = 0u64;
    loop {
        let count = file.read_at(&mut buffer, offset)?;
        if count == 0 { break; }
        offset += count as u64;
        if offset > 128 * 1024 * 1024 { return Err(error("artifact hash size exceeded")); }
        hash.update(&buffer[..count]);
    }
    Ok(hash.finalize().into())
}
pub(crate) struct Artifact {
    file: File,
    expected: [u8; 32],
    original: Stamp,
    execute: bool,
    owner: u32,
}
impl Artifact {
    pub(crate) fn open(spec: &RelayArtifact, execute: bool) -> io::Result<Self> {
        let parent = spec.path.parent().ok_or_else(|| error("artifact parent missing"))?;
        let name = spec.path.file_name().and_then(|name| name.to_str()).ok_or_else(|| error("artifact name invalid"))?;
        let directory = domain::directory(parent)?;
        let file = domain::named(&directory, name, libc::O_RDONLY)?;
        let expected = policy::digest(&spec.sha256).map_err(error)?;
        Self::from_file(file, expected, execute)
    }
    pub(crate) fn from_file(file: File, expected: [u8; 32], execute: bool) -> io::Result<Self> {
        Self::from_file_owned(file, expected, execute, 0)
    }
    fn from_file_owned(file: File, expected: [u8; 32], execute: bool, owner: u32) -> io::Result<Self> {
        if expected == [0; 32] { return Err(error("artifact expected digest is zero")); }
        let original = stamp(&file, execute, owner)?;
        if hash(&file)? != expected || stamp(&file, execute, owner)? != original {
            return Err(error("artifact digest/generation differs"));
        }
        Ok(Self { file, expected, original, execute, owner })
    }
    pub(crate) fn file(&self) -> &File { &self.file }
    pub(crate) fn digest(&self) -> [u8; 32] { self.expected }
    pub(crate) fn identity(&self) -> Identity { self.original.id }
    pub(crate) fn validate(&self, rehash: bool) -> io::Result<()> {
        if stamp(&self.file, self.execute, self.owner)? != self.original
            || (rehash && hash(&self.file)? != self.expected) {
            return Err(error("held artifact changed"));
        }
        Ok(())
    }
    /// Maps are selected by the independently held artifact inode, not a
    /// rendered pathname. Every executable mapping is reopened through the
    /// exact pinned proc directory and compared before/after.
    pub(crate) fn validate_mapped(&self, process: &Process) -> io::Result<()> {
        self.validate(true)?; process.live()?;
        let selected = |text: &str| -> io::Result<Vec<String>> {
            let mut ranges = Vec::new();
            let major = ((self.original.id.device >> 8) & 0xfff) | ((self.original.id.device >> 32) & 0xfffff000);
            let minor = (self.original.id.device & 0xff) | ((self.original.id.device >> 12) & 0xffffff00);
            for line in text.lines() {
                let fields: Vec<_> = line.split_whitespace().take(5).collect();
                if fields.len() != 5 { return Err(error("short process maps row")); }
                let (a,b) = fields[3].split_once(':').ok_or_else(|| error("maps device missing"))?;
                let device = (u64::from_str_radix(a,16).map_err(|_| error("maps major invalid"))?,
                    u64::from_str_radix(b,16).map_err(|_| error("maps minor invalid"))?);
                let inode: u64 = fields[4].parse().map_err(|_| error("maps inode invalid"))?;
                if device != (major,minor) || inode != self.original.id.inode || !fields[1].contains('x') { continue; }
                let (start,end) = fields[0].split_once('-').ok_or_else(|| error("maps range invalid"))?;
                if start.is_empty() || end.is_empty() || !start.bytes().chain(end.bytes()).all(|v| v.is_ascii_hexdigit()) {
                    return Err(error("maps range has unsafe characters"));
                }
                ranges.push(fields[0].to_owned());
                if ranges.len() > 64 { return Err(error("artifact executable map count exceeded")); }
            }
            if ranges.is_empty() { return Err(error("required artifact has no executable mapping")); }
            Ok(ranges)
        };
        let before = selected(&domain::read(domain::named(&process.proc,"maps",libc::O_RDONLY)?,4*1024*1024)?)?;
        let mut handles = Vec::new();
        for range in &before {
            let file = kernel_link(&process.proc, &format!("map_files/{range}"), libc::O_RDONLY)?;
            if Identity::of(&file)? != self.original.id || stamp(&file, self.execute, self.owner)? != self.original {
                return Err(error("actual mapped artifact identity differs"));
            }
            handles.push(file);
        }
        if hash(&handles[0])? != self.expected { return Err(error("actual mapped artifact bytes differ")); }
        let after = selected(&domain::read(domain::named(&process.proc,"maps",libc::O_RDONLY)?,4*1024*1024)?)?;
        if after != before { return Err(error("required artifact maps changed during bootstrap")); }
        self.validate(false)?; process.live()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::os::unix::fs::PermissionsExt;
    struct OwnedChild(Child);
    impl Drop for OwnedChild { fn drop(&mut self) { let _ = self.0.kill(); let _ = self.0.wait(); } }
    #[test]
    fn actual_owned_child_pidfd_retains_death_after_reap() {
        let mut child = OwnedChild(std::process::Command::new("/usr/bin/sleep").arg("30").spawn().unwrap());
        let process = Process::from_child(&mut child.0).unwrap();
        process.live().unwrap(); assert!(!process.dead().unwrap());
        process.signal(libc::SIGTERM).unwrap(); child.0.wait().unwrap();
        assert!(process.dead().unwrap()); assert!(process.live().is_err());
        process.require_dead(Duration::from_millis(10)).unwrap();
    }
    #[test]
    fn received_ordinary_descriptor_cannot_be_promoted_to_process_authority() {
        let file = File::open("/dev/null").unwrap();
        assert!(Process::from_received_pidfd(file).is_err());
    }
    #[test]
    fn privileged_exec_mode_cannot_clear_the_parent_death_contract() {
        let temp = tempfile::tempdir().unwrap(); let path = temp.path().join("executable");
        std::fs::write(&path, b"owned executable control").unwrap();
        let owner = unsafe { libc::geteuid() };
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
        let file = File::open(&path).unwrap(); let expected = hash(&file).unwrap();
        Artifact::from_file_owned(file, expected, true, owner).unwrap();
        for mode in [0o4700, 0o2700] {
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(mode)).unwrap();
            assert!(Artifact::from_file_owned(File::open(&path).unwrap(), expected, true, owner).is_err());
        }
    }
    #[test]
    fn actual_held_artifact_detects_content_and_inode_change() {
        let temp = tempfile::tempdir().unwrap(); let path = temp.path().join("artifact");
        std::fs::write(&path,b"generation one").unwrap();
        std::fs::set_permissions(&path,std::fs::Permissions::from_mode(0o700)).unwrap();
        let owner = unsafe { libc::geteuid() };
        let file = File::open(&path).unwrap(); let expected = hash(&file).unwrap();
        let pin = Artifact::from_file_owned(file,expected,true,owner).unwrap();
        pin.validate(true).unwrap();
        let mut writer = std::fs::OpenOptions::new().write(true).truncate(true).open(&path).unwrap();
        writer.write_all(b"generation two").unwrap();
        assert!(pin.validate(false).is_err()); assert!(pin.validate(true).is_err());
        let replacement = temp.path().join("replacement");
        std::fs::write(&replacement,b"generation one").unwrap();
        std::fs::set_permissions(&replacement,std::fs::Permissions::from_mode(0o700)).unwrap();
        std::fs::rename(&replacement,&path).unwrap();
        assert_ne!(pin.identity(),Identity::of(&File::open(&path).unwrap()).unwrap());
    }
}
