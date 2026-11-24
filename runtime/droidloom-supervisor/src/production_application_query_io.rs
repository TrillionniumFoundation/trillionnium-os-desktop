//! Fixed query I/O creation outside the broker and Android domains.
//!
//! Only the original broker can lend its held guest root and self pidfd through
//! a fresh authenticated seqpacket. The separately exec'd, capability-free
//! creator opens only that root's /dev/null and creates two anonymous pipes.
//! Nothing is returned to a query until the actual creator pidfd was reaped with
//! exit status zero. No namespace, pidfd or arbitrary executable is created by
//! the creator; the broker creates and retains its one direct child.
use super::{ApplicationError, Result, external, reject, require};
use std::ffi::CStr;
use std::fs::File;
use std::io::{self, Read};
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::MetadataExt;
use std::time::{Duration, Instant};

const ARGUMENT: &CStr = c"__production-query-io";
const BROKER: &[u8] = b"u:r:droidloom_broker:s0";
const CREATOR: &[u8] = b"u:r:droidloom_query_io:s0";
const AA_BROKER: &[u8] = b"droidloom-production-broker (enforce)\n";
const LIMIT: Duration = Duration::from_secs(5);
const RETIRE_LIMIT: Duration = Duration::from_secs(3);
const MAGIC: &[u8; 8] = b"DLQIOv1\0";
const WIRE_BYTES: usize = 40;
const PIDFD_GET_INFO: u64 = 0xc050_ff0b;
const REQUEST: u8 = 1;
const CREATED: u8 = 2;

/// The fixed five descriptors. Reads are nonblocking; query writes remain
/// blocking. Every descriptor is CLOEXEC until the real query deliberately
/// installs its three standard streams.
/// Actual one-time creator retirement. Only create(), after its original
/// PIDFD waitid, constructs this source-owned record.
#[derive(Clone, Debug, serde::Serialize)]
pub(crate) struct CreatorReceipt {
    pid: u32,
    waitid_code: i32,
    waitid_status: i32,
}
impl CreatorReceipt {
    pub(crate) fn pid(&self) -> u32 {
        self.pid
    }
    pub(crate) fn successful_retirement(&self) -> bool {
        self.pid > 1 && self.waitid_code == libc::CLD_EXITED && self.waitid_status == 0
    }
}
pub(crate) struct QueryIo {
    creator: Option<CreatorReceipt>,
    pub(crate) stdin: File,
    pub(crate) stdout_read: File,
    pub(crate) stdout_write: File,
    pub(crate) stderr_read: File,
    pub(crate) stderr_write: File,
}

impl QueryIo {
    pub(crate) fn creator_receipt(&self) -> Result<CreatorReceipt> {
        let receipt = self
            .creator
            .as_ref()
            .ok_or_else(|| reject("query I/O has no actual creator retirement"))?;
        require(
            receipt.successful_retirement(),
            "query I/O creator retirement is not normal",
        )?;
        Ok(receipt.clone())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Wire {
    phase: u8,
    nonce: [u8; 16],
    deadline_ns: u64,
}
impl Wire {
    fn bytes(self) -> [u8; WIRE_BYTES] {
        let mut bytes = [0; WIRE_BYTES];
        bytes[..8].copy_from_slice(MAGIC);
        bytes[8] = self.phase;
        bytes[16..32].copy_from_slice(&self.nonce);
        bytes[32..].copy_from_slice(&self.deadline_ns.to_le_bytes());
        bytes
    }
    fn parse(bytes: &[u8]) -> Result<Self> {
        require(
            bytes.len() == WIRE_BYTES
                && &bytes[..8] == MAGIC
                && matches!(bytes[8], REQUEST | CREATED)
                && bytes[9..16] == [0; 7],
            "query I/O wire format differs",
        )?;
        Ok(Self {
            phase: bytes[8],
            nonce: bytes[16..32].try_into().map_err(external)?,
            deadline_ns: u64::from_le_bytes(bytes[32..].try_into().map_err(external)?),
        })
    }
}
struct Received {
    wire: Wire,
    files: Vec<File>,
    peer: libc::ucred,
}

fn wait(fd: RawFd, events: i16, deadline: Instant) -> Result<()> {
    loop {
        let left = deadline.saturating_duration_since(Instant::now());
        require(!left.is_zero(), "query I/O absolute deadline")?;
        let mut p = libc::pollfd {
            fd,
            events,
            revents: 0,
        };
        let count = unsafe { libc::poll(&mut p, 1, left.as_millis().clamp(1, 20) as i32) };
        if count < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error.into());
        }
        if count > 0 {
            require(
                p.revents & (libc::POLLERR | libc::POLLNVAL) == 0,
                "query I/O invalid channel",
            )?;
            if p.revents & (events | libc::POLLHUP) != 0 {
                return Ok(());
            }
        }
    }
}
fn send(socket: RawFd, wire: Wire, files: &[RawFd], deadline: Instant) -> Result<()> {
    require(files.len() <= 5, "query I/O descriptor send bound")?;
    let bytes = wire.bytes();
    loop {
        require(Instant::now() < deadline, "query I/O send deadline")?;
        let mut vector = libc::iovec {
            iov_base: bytes.as_ptr().cast_mut().cast(),
            iov_len: bytes.len(),
        };
        let mut control = [0_usize; 16];
        let mut header: libc::msghdr = unsafe { mem::zeroed() };
        header.msg_iov = &mut vector;
        header.msg_iovlen = 1;
        if !files.is_empty() {
            header.msg_control = control.as_mut_ptr().cast();
            header.msg_controllen =
                unsafe { libc::CMSG_SPACE(mem::size_of_val(files) as u32) } as usize;
            let cmsg = unsafe { libc::CMSG_FIRSTHDR(&header) };
            require(!cmsg.is_null(), "query I/O rights header absent")?;
            unsafe {
                (*cmsg).cmsg_level = libc::SOL_SOCKET;
                (*cmsg).cmsg_type = libc::SCM_RIGHTS;
                (*cmsg).cmsg_len = libc::CMSG_LEN(mem::size_of_val(files) as u32) as usize;
                std::ptr::copy_nonoverlapping(
                    files.as_ptr().cast::<u8>(),
                    libc::CMSG_DATA(cmsg),
                    mem::size_of_val(files),
                );
            }
        }
        let count =
            unsafe { libc::sendmsg(socket, &header, libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL) };
        if count >= 0 {
            return require(count as usize == bytes.len(), "partial query I/O seqpacket");
        }
        let error = io::Error::last_os_error();
        if error.kind() == io::ErrorKind::Interrupted {
            continue;
        }
        if error.kind() != io::ErrorKind::WouldBlock {
            return Err(error.into());
        }
        wait(socket, libc::POLLOUT, deadline)?;
    }
}
fn receive(socket: RawFd, expected_files: usize, deadline: Instant) -> Result<Received> {
    require(expected_files <= 5, "query I/O receive descriptor bound")?;
    loop {
        require(Instant::now() < deadline, "query I/O receive deadline")?;
        let mut bytes = [0_u8; WIRE_BYTES];
        let mut vector = libc::iovec {
            iov_base: bytes.as_mut_ptr().cast(),
            iov_len: bytes.len(),
        };
        // Larger than the permitted input: every received right is adopted even
        // when the sender supplies extra descriptors, truncates data, or spoofs
        // the fixed protocol. The kernel closes any truncated excess rights.
        let mut control = [0_usize; 128];
        let mut header: libc::msghdr = unsafe { mem::zeroed() };
        header.msg_iov = &mut vector;
        header.msg_iovlen = 1;
        header.msg_control = control.as_mut_ptr().cast();
        header.msg_controllen = mem::size_of_val(&control);
        let count = unsafe {
            libc::recvmsg(
                socket,
                &mut header,
                libc::MSG_CMSG_CLOEXEC | libc::MSG_DONTWAIT,
            )
        };
        if count < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            if error.kind() != io::ErrorKind::WouldBlock {
                return Err(error.into());
            }
            wait(socket, libc::POLLIN, deadline)?;
            continue;
        }
        let mut files = Vec::new();
        let mut peer = None;
        let mut malformed = false;
        let mut rights_messages = 0;
        let mut cmsg = unsafe { libc::CMSG_FIRSTHDR(&header) };
        while !cmsg.is_null() {
            let fixed = unsafe { libc::CMSG_LEN(0) } as usize;
            let size = unsafe { (*cmsg).cmsg_len };
            if size < fixed {
                malformed = true;
                break;
            }
            let payload = size - fixed;
            if unsafe { (*cmsg).cmsg_level } == libc::SOL_SOCKET
                && unsafe { (*cmsg).cmsg_type } == libc::SCM_RIGHTS
            {
                rights_messages += 1;
                if payload % mem::size_of::<i32>() != 0 {
                    malformed = true;
                }
                for offset in
                    (0..payload / mem::size_of::<i32>()).map(|i| i * mem::size_of::<i32>())
                {
                    let raw = unsafe {
                        std::ptr::read_unaligned(libc::CMSG_DATA(cmsg).add(offset).cast::<i32>())
                    };
                    if raw < 0 {
                        malformed = true;
                    } else {
                        files.push(unsafe { File::from_raw_fd(raw) });
                    }
                }
            } else if unsafe { (*cmsg).cmsg_level } == libc::SOL_SOCKET
                && unsafe { (*cmsg).cmsg_type } == libc::SCM_CREDENTIALS
                && payload == mem::size_of::<libc::ucred>()
            {
                let value = unsafe {
                    std::ptr::read_unaligned(libc::CMSG_DATA(cmsg).cast::<libc::ucred>())
                };
                if peer.replace(value).is_some() {
                    malformed = true;
                }
            } else {
                malformed = true;
            }
            cmsg = unsafe { libc::CMSG_NXTHDR(&header, cmsg) };
        }
        require(
            count as usize == WIRE_BYTES
                && header.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) == 0
                && !malformed
                && rights_messages == 1
                && files.len() == expected_files,
            "query I/O message or descriptor custody differs",
        )?;
        return Ok(Received {
            wire: Wire::parse(&bytes)?,
            files,
            peer: peer.ok_or_else(|| reject("query I/O sender credentials absent"))?,
        });
    }
}

pub(super) fn own_root_credentials() -> Result<()> {
    require(
        unsafe {
            libc::getuid() == 0
                && libc::geteuid() == 0
                && libc::getgid() == 0
                && libc::getegid() == 0
        },
        "query I/O requires its initial-root owner",
    )
}
fn proc_value(path: &CStr) -> Result<Vec<u8>> {
    let raw = unsafe {
        libc::open(
            path.as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(raw) };
    let mut fs: libc::statfs = unsafe { mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        fs.f_type == 0x9fa0 && file.metadata()?.is_file(),
        "query I/O attribute is not procfs",
    )?;
    let mut value = Vec::new();
    file.take(257).read_to_end(&mut value)?;
    require(value.len() <= 256, "query I/O attribute is oversized")?;
    Ok(value)
}
pub(super) fn mac_context(selinux: &[u8]) -> Result<()> {
    let actual = proc_value(c"/proc/thread-self/attr/current")?;
    require(
        actual == selinux || actual.strip_suffix(b"\0") == Some(selinux),
        "query I/O SELinux domain differs",
    )?;
    require(
        proc_value(c"/proc/thread-self/attr/apparmor/current")? == AA_BROKER,
        "query I/O AppArmor broker profile differs",
    )
}
pub(super) fn channel_kind(socket: RawFd) -> Result<()> {
    let mut kind = 0_i32;
    let mut length = mem::size_of_val(&kind) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket,
            libc::SOL_SOCKET,
            libc::SO_TYPE,
            (&mut kind as *mut i32).cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        length as usize == mem::size_of_val(&kind) && kind == libc::SOCK_SEQPACKET,
        "query I/O channel is not seqpacket",
    )?;
    let mut domain = 0_i32;
    length = mem::size_of_val(&domain) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket,
            libc::SOL_SOCKET,
            libc::SO_DOMAIN,
            (&mut domain as *mut i32).cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(domain == libc::AF_UNIX, "query I/O channel is not local")?;
    let mut label = [0_u8; 256];
    length = label.len() as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket,
            libc::SOL_SOCKET,
            libc::SO_PEERSEC,
            label.as_mut_ptr().cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        length as usize <= label.len(),
        "query I/O peer context is oversized",
    )?;
    let actual = &label[..length as usize];
    require(
        actual == BROKER || actual.strip_suffix(b"\0") == Some(BROKER),
        "query I/O peer socket was not created by the broker",
    )
}

#[repr(C)]
#[derive(Default)]
pub(super) struct PidfdInfo {
    pub(super) mask: u64,
    pub(super) cgroup_id: u64,
    pub(super) pid: u32,
    pub(super) tgid: u32,
    pub(super) ppid: u32,
    pub(super) ruid: u32,
    pub(super) rgid: u32,
    pub(super) euid: u32,
    pub(super) egid: u32,
    pub(super) suid: u32,
    pub(super) sgid: u32,
    pub(super) fsuid: u32,
    pub(super) fsgid: u32,
    pub(super) exit_code: i32,
    pub(super) coredump_mask: u32,
    pub(super) coredump_signal: u32,
    pub(super) supported_mask: u64,
}
const _: () = assert!(mem::size_of::<PidfdInfo>() == 80);
pub(super) fn pidfd_info(file: &File) -> Result<PidfdInfo> {
    let mut value = PidfdInfo {
        mask: 3,
        ..PidfdInfo::default()
    };
    if unsafe { libc::ioctl(file.as_raw_fd(), PIDFD_GET_INFO as _, &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        value.mask & 3 == 3 && value.pid > 1 && value.pid == value.tgid,
        "query I/O incomplete pidfd identity",
    )?;
    Ok(value)
}
pub(super) fn alive(file: &File) -> Result<()> {
    let mut poll = libc::pollfd {
        fd: file.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    let count = unsafe { libc::poll(&mut poll, 1, 0) };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        count == 0 && poll.revents == 0,
        "query I/O original parent has exited",
    )
}
pub(super) fn parent_identity(pidfd: &File, peer: libc::ucred, parent: libc::pid_t) -> Result<()> {
    alive(pidfd)?;
    let value = pidfd_info(pidfd)?;
    require(
        peer.pid == parent
            && peer.uid == 0
            && peer.gid == 0
            && value.pid == parent as u32
            && [
                value.ruid,
                value.euid,
                value.suid,
                value.fsuid,
                value.rgid,
                value.egid,
                value.sgid,
                value.fsgid,
            ] == [0; 8],
        "query I/O sender is not its live original root broker parent",
    )?;
    require(
        unsafe { libc::getppid() } == parent,
        "query I/O parent changed",
    )?;
    alive(pidfd)
}

#[repr(C)]
struct CapHeader {
    version: u32,
    pid: i32,
}
#[repr(C)]
#[derive(Clone, Copy, Default)]
struct CapData {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}
pub(super) fn empty_capabilities() -> Result<()> {
    let mut header = CapHeader {
        version: 0x2008_0522,
        pid: 0,
    };
    let mut caps = [CapData::default(); 2];
    if unsafe { libc::syscall(libc::SYS_capget, &mut header, caps.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        caps.iter()
            .all(|c| c.effective == 0 && c.permitted == 0 && c.inheritable == 0),
        "query I/O creator retained capabilities",
    )?;
    for capability in 0..64 {
        let state = unsafe { libc::prctl(libc::PR_CAP_AMBIENT, 1, capability, 0, 0) };
        if state < 0 {
            require(
                io::Error::last_os_error().raw_os_error() == Some(libc::EINVAL),
                "query I/O unreadable ambient set",
            )?;
            break;
        }
        require(
            state == 0,
            "query I/O creator retained an ambient capability",
        )?;
    }
    require(
        unsafe {
            libc::getgroups(0, std::ptr::null_mut()) == 0
                && libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) == 1
                && libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) == 0
        },
        "query I/O creator privilege state differs",
    )
}
fn new_pipe() -> Result<(File, File)> {
    let mut fds = [-1; 2];
    if unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_CLOEXEC) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let read = unsafe { File::from_raw_fd(fds[0]) };
    let write = unsafe { File::from_raw_fd(fds[1]) };
    if unsafe { libc::fcntl(read.as_raw_fd(), libc::F_SETFL, libc::O_NONBLOCK) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok((read, write))
}
fn flags(file: &File) -> Result<i32> {
    let value = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    if value < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let descriptor_flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFD) };
    if descriptor_flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        descriptor_flags & libc::FD_CLOEXEC != 0,
        "query I/O descriptor lost CLOEXEC",
    )?;
    Ok(value)
}
fn validate_null(file: &File, root: &File) -> Result<()> {
    let m = file.metadata()?;
    let owner = root.metadata()?;
    require(
        owner.is_dir()
            && m.mode() == libc::S_IFCHR | 0o666
            && m.rdev() == 259
            && m.nlink() == 1
            && m.uid() == owner.uid()
            && m.gid() == owner.gid(),
        "query I/O stdin is not the fixed idmapped guest null",
    )?;
    require(
        flags(file)? & (libc::O_ACCMODE | libc::O_PATH) == libc::O_RDONLY,
        "query I/O stdin access differs",
    )?;
    let mut label = [0_u8; 64];
    let n = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            label.as_mut_ptr().cast(),
            label.len(),
        )
    };
    if n < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        n as usize == b"u:object_r:null_device:s0\0".len()
            && &label[..n as usize] == b"u:object_r:null_device:s0\0",
        "query I/O guest null label differs",
    )
}
fn validate_pipes(read: &File, write: &File) -> Result<(u64, u64)> {
    let r = read.metadata()?;
    let w = write.metadata()?;
    let mut fs: libc::statfs = unsafe { mem::zeroed() };
    if unsafe { libc::fstatfs(read.as_raw_fd(), &mut fs) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        r.mode() & libc::S_IFMT == libc::S_IFIFO
            && w.mode() & libc::S_IFMT == libc::S_IFIFO
            && fs.f_type == 0x5049_5045
            && r.dev() == w.dev()
            && r.ino() == w.ino()
            && r.nlink() == 1
            && w.nlink() == 1
            && flags(read)? & (libc::O_ACCMODE | libc::O_NONBLOCK | libc::O_PATH)
                == libc::O_NONBLOCK
            && flags(write)? & (libc::O_ACCMODE | libc::O_NONBLOCK | libc::O_PATH)
                == libc::O_WRONLY,
        "query I/O anonymous pipe pair or access mode differs",
    )?;
    Ok((r.dev(), r.ino()))
}
fn assemble(files: Vec<File>, root: &File) -> Result<QueryIo> {
    let [stdin, stdout_read, stdout_write, stderr_read, stderr_write]: [File; 5] = files
        .try_into()
        .map_err(|_| reject("query I/O reply must contain exactly five descriptors"))?;
    validate_null(&stdin, root)?;
    require(
        validate_pipes(&stdout_read, &stdout_write)?
            != validate_pipes(&stderr_read, &stderr_write)?,
        "query I/O output pipes alias",
    )?;
    Ok(QueryIo {
        creator: None,
        stdin,
        stdout_read,
        stdout_write,
        stderr_read,
        stderr_write,
    })
}
fn guest_null(root: &File) -> Result<File> {
    require(
        root.metadata()?.is_dir(),
        "query I/O guest root is not a directory",
    )?;
    let dev = unsafe {
        libc::openat(
            root.as_raw_fd(),
            c"dev".as_ptr(),
            libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if dev < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let dev = unsafe { File::from_raw_fd(dev) };
    require(
        dev.metadata()?.is_dir(),
        "query I/O guest dev is not a directory",
    )?;
    let raw = unsafe {
        libc::openat(
            dev.as_raw_fd(),
            c"null".as_ptr(),
            libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let null = unsafe { File::from_raw_fd(raw) };
    validate_null(&null, root)?;
    Ok(null)
}

// These syscall filters support only the reviewed native x86_64 host ABI.
// Arguments can narrow the one preexec execveat and the sole permitted pidfd
// ioctl. The creator has no process/namespace/pidfd/socket creation operation.
pub(super) fn filter(executable: Option<RawFd>, metadata: bool) -> Vec<libc::sock_filter> {
    let ins = |code, jt, jf, k| libc::sock_filter { code, jt, jf, k };
    let deny = 0x0005_0000 | libc::EPERM as u32;
    let allow = 0x7fff_0000;
    let mut f = vec![
        ins(0x20, 0, 0, 4),
        ins(0x15, 1, 0, 0xc000_003e),
        ins(0x06, 0, 0, 0x8000_0000),
        ins(0x20, 0, 0, 0),
        ins(0x35, 0, 1, 0x4000_0000),
        ins(0x06, 0, 0, deny),
    ];
    if metadata {
        // Before fixed entry consumes its held namespace, allow only the two
        // read-only identity ioctls it needs. The final filter binds PIDFD_INFO
        // to the exact original target descriptor.
        f.extend([
            ins(0x15, 0, 8, libc::SYS_ioctl as u32),
            ins(0x20, 0, 0, 28),
            ins(0x15, 1, 0, 0),
            ins(0x06, 0, 0, deny),
            ins(0x20, 0, 0, 24),
            ins(0x15, 2, 0, PIDFD_GET_INFO as u32),
            ins(0x15, 1, 0, 0xb703),
            ins(0x06, 0, 0, deny),
            ins(0x06, 0, 0, allow),
            ins(0x20, 0, 0, 0),
        ]);
    }
    let mut narrow = |syscall: libc::c_long, arguments: &[(u32, u64)]| {
        let mut body = Vec::new();
        for &(index, value) in arguments {
            for (offset, value) in [
                (16 + index * 8, value as u32),
                (20 + index * 8, (value >> 32) as u32),
            ] {
                body.extend([
                    ins(0x20, 0, 0, offset),
                    ins(0x15, 1, 0, value),
                    ins(0x06, 0, 0, deny),
                ]);
            }
        }
        body.push(ins(0x06, 0, 0, allow));
        f.push(ins(0x15, 0, body.len() as u8, syscall as u32));
        f.extend(body);
        f.push(ins(0x20, 0, 0, 0));
    };
    if !metadata {
        narrow(libc::SYS_ioctl, &[(1, PIDFD_GET_INFO)]);
    }
    narrow(libc::SYS_recvmsg, &[(0, 3)]);
    narrow(libc::SYS_sendmsg, &[(0, 3)]);
    narrow(libc::SYS_pipe2, &[(1, libc::O_CLOEXEC as u64)]);
    if metadata {
        narrow(libc::SYS_setns, &[(0, 4), (1, libc::CLONE_NEWUSER as u64)]);
    }
    if let Some(fd) = executable {
        narrow(
            libc::SYS_execveat,
            &[(0, fd as u64), (4, libc::AT_EMPTY_PATH as u64)],
        );
    }
    for syscall in [
        libc::SYS_read,
        libc::SYS_write,
        libc::SYS_close,
        libc::SYS_fstat,
        libc::SYS_newfstatat,
        libc::SYS_statx,
        libc::SYS_fstatfs,
        libc::SYS_openat,
        libc::SYS_readlink,
        libc::SYS_readlinkat,
        libc::SYS_mmap,
        libc::SYS_mprotect,
        libc::SYS_munmap,
        libc::SYS_brk,
        libc::SYS_madvise,
        libc::SYS_rt_sigaction,
        libc::SYS_rt_sigprocmask,
        libc::SYS_rt_sigreturn,
        libc::SYS_arch_prctl,
        libc::SYS_prlimit64,
        libc::SYS_getrlimit,
        libc::SYS_getrandom,
        libc::SYS_set_tid_address,
        libc::SYS_set_robust_list,
        libc::SYS_rseq,
        libc::SYS_access,
        libc::SYS_faccessat,
        libc::SYS_faccessat2,
        libc::SYS_futex,
        libc::SYS_clock_gettime,
        libc::SYS_clock_nanosleep,
        libc::SYS_nanosleep,
        libc::SYS_poll,
        libc::SYS_ppoll,
        libc::SYS_fcntl,
        libc::SYS_getpid,
        libc::SYS_getppid,
        libc::SYS_getuid,
        libc::SYS_geteuid,
        libc::SYS_getgid,
        libc::SYS_getegid,
        libc::SYS_getgroups,
        libc::SYS_capget,
        libc::SYS_prctl,
        libc::SYS_getsockopt,
        libc::SYS_fgetxattr,
        libc::SYS_lseek,
        libc::SYS_pread64,
        libc::SYS_sched_getaffinity,
        libc::SYS_exit_group,
        libc::SYS_exit,
    ] {
        f.extend([ins(0x15, 0, 1, syscall as u32), ins(0x06, 0, 0, allow)]);
    }
    if metadata {
        for syscall in [libc::SYS_capset, libc::SYS_dup3] {
            f.extend([ins(0x15, 0, 1, syscall as u32), ins(0x06, 0, 0, allow)]);
        }
    }
    f.push(ins(0x06, 0, 0, deny));
    f
}
pub(super) fn install_filter(program: &[libc::sock_filter]) -> Result<()> {
    let f = libc::sock_fprog {
        len: program.len() as u16,
        filter: program.as_ptr().cast_mut(),
    };
    if unsafe { libc::prctl(libc::PR_SET_SECCOMP, 2, &f as *const libc::sock_fprog) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}

/// Runs only after the protected daemon's private fresh-image dispatch.
pub(super) fn entry() -> Result<()> {
    #[cfg(not(target_arch = "x86_64"))]
    return Err(reject(
        "query I/O creator requires the reviewed native x86_64 ABI",
    ));
    own_root_credentials()?;
    verify_fixed_stdio()?;
    mac_context(CREATOR)?;
    // Stacking this filter removes even the single preexec execveat exception.
    install_filter(&filter(None, false))?;
    // exec may reset dumpability. This only restricts the current creator and
    // is rechecked with the remaining fixed privilege state.
    if unsafe { libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    empty_capabilities()?;
    drop(crate::production_host_admission::application_worker_executable().map_err(external)?);
    channel_kind(3)?;
    let parent = unsafe { libc::getppid() };
    require(parent > 1, "query I/O creator has no broker parent")?;
    let received = receive(3, 2, Instant::now() + LIMIT)?;
    require(
        received.wire.phase == REQUEST,
        "query I/O first phase differs",
    )?;
    let [root, owner]: [File; 2] = received
        .files
        .try_into()
        .map_err(|_| reject("query I/O owner descriptor count"))?;
    parent_identity(&owner, received.peer, parent)?;
    // A MAC transition can clear PDEATHSIG. Re-arm it against the same live
    // held parent, checking both sides; no PID is accepted from the request.
    if unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    parent_identity(&owner, received.peer, parent)?;
    let remaining = received
        .wire
        .deadline_ns
        .checked_sub(super::protocol::monotonic_ns()?)
        .ok_or_else(|| reject("query I/O creator request expired"))?;
    require(
        remaining > 0 && remaining <= LIMIT.as_nanos() as u64,
        "query I/O creator deadline exceeds fixed budget",
    )?;
    let deadline = Instant::now() + Duration::from_nanos(remaining);
    let stdin = guest_null(&root)?;
    let (stdout_read, stdout_write) = new_pipe()?;
    let (stderr_read, stderr_write) = new_pipe()?;
    let io = assemble(
        vec![stdin, stdout_read, stdout_write, stderr_read, stderr_write],
        &root,
    )?;
    mac_context(CREATOR)?;
    empty_capabilities()?;
    parent_identity(&owner, received.peer, parent)?;
    let reply = Wire {
        phase: CREATED,
        ..received.wire
    };
    send(
        3,
        reply,
        &[
            io.stdin.as_raw_fd(),
            io.stdout_read.as_raw_fd(),
            io.stdout_write.as_raw_fd(),
            io.stderr_read.as_raw_fd(),
            io.stderr_write.as_raw_fd(),
        ],
        deadline,
    )?;
    parent_identity(&owner, received.peer, parent)?;
    Ok(())
}

pub(super) fn above_reserved(file: &File) -> Result<File> {
    let raw = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 64) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}


/// A broker-created anonymous read end whose only writer is already closed.
/// Keeping 0..2 valid prevents Rust's fresh-image startup from opening host
/// /dev/null before either private helper can execute its entry checks.
pub(super) fn fixed_stdio() -> Result<File> {
    let (read, write) = new_pipe()?;
    let stdio = above_reserved(&read)?;
    drop(read);
    drop(write);
    fixed_stdio_node(stdio.as_raw_fd(), false)?;
    Ok(stdio)
}

fn fixed_stdio_node(fd: RawFd, inherited: bool) -> Result<(u64, u64)> {
    let mut stat: libc::stat = unsafe { mem::zeroed() };
    if unsafe { libc::fstat(fd, &mut stat) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
    let descriptor = unsafe { libc::fcntl(fd, libc::F_GETFD) };
    require(
        stat.st_mode & libc::S_IFMT == libc::S_IFIFO
            && flags >= 0
            && flags & (libc::O_ACCMODE | libc::O_PATH) == libc::O_RDONLY
            && flags & libc::O_NONBLOCK != 0
            && descriptor >= 0
            && (descriptor & libc::FD_CLOEXEC == 0) == inherited,
        "helper stdio is not the fixed read-only inherited pipe",
    )?;
    let mut state = libc::pollfd { fd, events: libc::POLLIN, revents: 0 };
    let ready = unsafe { libc::poll(&mut state, 1, 0) };
    require(
        ready == 1 && state.revents == libc::POLLHUP,
        "helper stdio still has data or a live writer",
    )?;
    let mut byte = 0_u8;
    require(
        unsafe { libc::read(fd, (&mut byte as *mut u8).cast(), 1) } == 0,
        "helper stdio has no actual EOF",
    )?;
    Ok((stat.st_dev, stat.st_ino))
}

/// Check the actual three inherited descriptions before private helper work.
/// No host character device or control socket can stand in for this pipe.
pub(super) fn verify_fixed_stdio() -> Result<()> {
    let node = fixed_stdio_node(0, true)?;
    for fd in 1..3 {
        require(
            fixed_stdio_node(fd, true)? == node,
            "helper standard descriptors do not share the one fixed pipe",
        )?;
    }
    Ok(())
}

/// After raw clone3, use only preallocated memory and async-signal-safe syscalls.
unsafe fn raw_attribute(path: &CStr, expected: &[u8], write: bool) -> bool {
    unsafe {
        let raw = libc::syscall(
            libc::SYS_openat,
            libc::AT_FDCWD,
            path.as_ptr(),
            (if write {
                libc::O_WRONLY
            } else {
                libc::O_RDONLY
            }) | libc::O_NOFOLLOW
                | libc::O_CLOEXEC
                | libc::O_NONBLOCK,
            0,
        );
        if raw < 0 {
            return false;
        }
        let mut fs: libc::statfs = mem::zeroed();
        let mut node: libc::stat = mem::zeroed();
        let valid = libc::syscall(libc::SYS_fstatfs, raw, &mut fs) == 0
            && libc::syscall(libc::SYS_fstat, raw, &mut node) == 0
            && fs.f_type == 0x9fa0
            && node.st_mode & libc::S_IFMT == libc::S_IFREG;
        let mut bytes = [0_u8; 256];
        let count = if !valid {
            -1
        } else if write {
            libc::syscall(libc::SYS_write, raw, expected.as_ptr(), expected.len())
        } else {
            libc::syscall(libc::SYS_read, raw, bytes.as_mut_ptr(), bytes.len())
        };
        let good = if write {
            count == expected.len() as libc::c_long
        } else {
            count >= 0
                && (count as usize == expected.len() || count as usize == expected.len() + 1)
                && bytes.get(..expected.len()) == Some(expected)
                && (count as usize == expected.len() || bytes[expected.len()] == 0)
        };
        let tail = if !write && good {
            libc::syscall(libc::SYS_read, raw, bytes.as_mut_ptr(), 1)
        } else {
            0
        };
        let closed = libc::syscall(libc::SYS_close, raw);
        valid && good && tail == 0 && closed == 0
    }
}
/// Both private helpers use the same reviewed no-argument fresh image gate.
#[derive(Clone, Copy)]
pub(super) enum HelperRole {
    QueryIo,
    MetadataObserver,
}
impl HelperRole {
    fn terminated(self) -> &'static [u8] {
        match self {
            Self::QueryIo => b"u:r:droidloom_query_io:s0\0",
            Self::MetadataObserver => b"u:r:droidloom_metadata_observer:s0\0",
        }
    }
    fn context(self) -> &'static [u8] {
        match self {
            Self::QueryIo => CREATOR,
            Self::MetadataObserver => b"u:r:droidloom_metadata_observer:s0",
        }
    }
}
pub(super) unsafe fn bootstrap(
    role: HelperRole,
    parent: libc::pid_t,
    executable: RawFd,
    socket: RawFd,
    stdio: RawFd,
    argv: *const *const libc::c_char,
    environment: *const *const libc::c_char,
    program: &libc::sock_fprog,
) -> ! {
    unsafe {
        if libc::getppid() != parent
            || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0
            || libc::getppid() != parent
        {
            libc::_exit(125);
        }
        if !raw_attribute(c"/proc/thread-self/attr/current", BROKER, false)
            || !raw_attribute(c"/proc/thread-self/attr/apparmor/current", AA_BROKER, false)
            || !raw_attribute(c"/proc/thread-self/attr/exec", b"", false)
            || !raw_attribute(c"/proc/thread-self/attr/exec", role.terminated(), true)
            || !raw_attribute(c"/proc/thread-self/attr/exec", role.context(), false)
            || !raw_attribute(c"/proc/thread-self/attr/current", BROKER, false)
            || !raw_attribute(c"/proc/thread-self/attr/apparmor/current", AA_BROKER, false)
        {
            libc::_exit(125);
        }
        if libc::dup2(socket, 3) != 3
            || libc::syscall(libc::SYS_close_range, 3_u32, u32::MAX, 4_u32) != 0
            || libc::fcntl(3, libc::F_SETFD, 0) != 0
        {
            libc::_exit(125);
        }
        if stdio < 64 || stdio == socket || stdio == executable {
            libc::_exit(125);
        }
        for fd in 0..3 {
            if libc::dup2(stdio, fd) != fd || libc::fcntl(fd, libc::F_SETFD, 0) != 0 {
                libc::_exit(125);
            }
        }
        let zero = libc::rlimit {
            rlim_cur: 0,
            rlim_max: 0,
        };
        let memory = libc::rlimit {
            rlim_cur: 256 * 1024 * 1024,
            rlim_max: 256 * 1024 * 1024,
        };
        let cpu = libc::rlimit {
            rlim_cur: 5,
            rlim_max: 5,
        };
        if libc::setrlimit(libc::RLIMIT_CORE, &zero) != 0
            || libc::setrlimit(libc::RLIMIT_FSIZE, &zero) != 0
            || libc::setrlimit(libc::RLIMIT_AS, &memory) != 0
            || libc::setrlimit(libc::RLIMIT_CPU, &cpu) != 0
            || libc::syscall(libc::SYS_setgroups, 0_usize, std::ptr::null::<u32>()) != 0
            || libc::prctl(libc::PR_CAP_AMBIENT, 4, 0, 0, 0) != 0
        {
            libc::_exit(125);
        }
        // Dropping P/E/I needs no new CAP_SETPCAP policy grant. NNP makes the
        // fixed no-file-capability exec incapable of raising those empty sets;
        // fresh entry verifies them and removes the last execveat exception.
        // The bounding set is not current authority and is left untouched.
        let mut header = CapHeader {
            version: 0x2008_0522,
            pid: 0,
        };
        let caps = [CapData {
            effective: 0,
            permitted: 0,
            inheritable: 0,
        }; 2];
        if libc::syscall(libc::SYS_capset, &mut header, caps.as_ptr()) != 0
            || libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
            || libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) != 0
            || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0
            || libc::getppid() != parent
            || libc::prctl(libc::PR_SET_SECCOMP, 2, program as *const libc::sock_fprog) != 0
        {
            libc::_exit(125);
        }
        libc::syscall(
            libc::SYS_execveat,
            executable,
            c"".as_ptr(),
            argv,
            environment,
            libc::AT_EMPTY_PATH,
        );
        libc::_exit(125);
    }
}

pub(super) struct Child {
    pub(super) pid: u32,
    pub(super) pidfd: Option<File>,
    pub(super) terminal: Option<(i32, i32)>,
}
impl Child {
    fn observe(&mut self) -> Result<bool> {
        if self.terminal.is_some() {
            return Ok(true);
        }
        let fd = self
            .pidfd
            .as_ref()
            .ok_or_else(|| reject("query I/O original child pidfd absent"))?;
        let mut status: libc::siginfo_t = unsafe { mem::zeroed() };
        let result = unsafe {
            libc::waitid(
                libc::P_PIDFD,
                fd.as_raw_fd() as u32,
                &mut status,
                libc::WEXITED | libc::WNOHANG,
            )
        };
        if result != 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                return Ok(false);
            }
            return Err(e.into());
        }
        let observed = unsafe { status.si_pid() };
        if observed == 0 {
            return Ok(false);
        }
        require(
            observed as u32 == self.pid
                && matches!(
                    status.si_code,
                    libc::CLD_EXITED | libc::CLD_KILLED | libc::CLD_DUMPED
                ),
            "query I/O child wait identity differs",
        )?;
        self.terminal = Some((status.si_code, unsafe { status.si_status() }));
        Ok(true)
    }
    pub(super) fn finish(&mut self, deadline: Instant) -> Result<()> {
        while !self.observe()? {
            wait(
                self.pidfd.as_ref().unwrap().as_raw_fd(),
                libc::POLLIN,
                deadline,
            )?;
        }
        require(
            self.terminal == Some((libc::CLD_EXITED, 0)),
            "query I/O creator did not exit successfully",
        )
    }
    pub(super) fn retire(&mut self) -> Result<()> {
        if self.terminal.is_some() {
            return Ok(());
        }
        if self.observe()? {
            return Ok(());
        }
        let fd = self
            .pidfd
            .as_ref()
            .ok_or(ApplicationError::RetirementUnproven)?;
        if unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                fd.as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0_u32,
            )
        } != 0
            && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
        {
            return Err(ApplicationError::RetirementUnproven);
        }
        let deadline = Instant::now() + RETIRE_LIMIT;
        while !self
            .observe()
            .map_err(|_| ApplicationError::RetirementUnproven)?
        {
            wait(
                self.pidfd.as_ref().unwrap().as_raw_fd(),
                libc::POLLIN,
                deadline,
            )
            .map_err(|_| ApplicationError::RetirementUnproven)?;
        }
        Ok(())
    }
}
impl Drop for Child {
    fn drop(&mut self) {
        if self.terminal.is_none() && self.pidfd.is_some() && self.retire().is_err() {
            // Preserve the actual ownership handle on an unproven terminal;
            // callers receive RetirementUnproven and retain their outer lease.
            if let Some(fd) = self.pidfd.take() {
                mem::forget(fd);
            }
        }
    }
}

/// Create the fixed query streams through one owned, separately exec'd creator.
pub(crate) fn create(root: &File, deadline: Instant) -> Result<QueryIo> {
    #[cfg(not(target_arch = "x86_64"))]
    return Err(reject("query I/O requires the reviewed native x86_64 ABI"));
    let deadline = deadline.min(Instant::now() + LIMIT);
    require(
        Instant::now() < deadline,
        "query I/O deadline already expired",
    )?;
    own_root_credentials()?;
    mac_context(BROKER)?;
    require(
        root.metadata()?.is_dir(),
        "query I/O root is not held directory custody",
    )?;
    super::worker::require_wait_semantics()?;
    let executable =
        crate::production_host_admission::application_worker_executable().map_err(external)?;
    let executable = above_reserved(&executable)?;
    let (channel, child_channel) = super::protocol::socketpair()?;
    let child_channel = above_reserved(&File::from(child_channel))?;
    let stdio = fixed_stdio()?;
    let owner = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0_u32) };
    if owner < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let owner = unsafe { File::from_raw_fd(owner as RawFd) };
    alive(&owner)?;
    require(
        pidfd_info(&owner)?.pid == unsafe { libc::getpid() } as u32,
        "query I/O owner pidfd differs",
    )?;
    let mut nonce = [0_u8; 16];
    let mut offset = 0;
    while offset < nonce.len() {
        let count = unsafe {
            libc::getrandom(nonce[offset..].as_mut_ptr().cast(), nonce.len() - offset, 0)
        };
        if count < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error.into());
        }
        require(count > 0, "query I/O random nonce unavailable")?;
        offset += count as usize;
    }
    let left = deadline.saturating_duration_since(Instant::now());
    require(!left.is_zero(), "query I/O preparation exceeded deadline")?;
    let wire = Wire {
        phase: REQUEST,
        nonce,
        deadline_ns: super::protocol::monotonic_ns()?
            .checked_add(left.as_nanos() as u64)
            .ok_or_else(|| reject("query I/O deadline overflow"))?,
    };
    let program = filter(Some(executable.as_raw_fd()), false);
    let fprog = libc::sock_fprog {
        len: program.len() as u16,
        filter: program.as_ptr().cast_mut(),
    };
    let argv = [
        c"droidloom-owned-query-io".as_ptr(),
        ARGUMENT.as_ptr(),
        std::ptr::null(),
    ];
    let environment = [c"LC_ALL=C".as_ptr(), std::ptr::null()];
    let parent = unsafe { libc::getpid() };
    let mut raw_pidfd = -1_i32;
    let args = super::worker::CloneArgs {
        flags: libc::CLONE_PIDFD as u64,
        pidfd: (&mut raw_pidfd as *mut i32) as u64,
        exit_signal: libc::SIGCHLD as u64,
        ..super::worker::CloneArgs::default()
    };
    let mut mask = super::worker::SignalMask::block()?;
    let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args)) };
    if pid < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if pid == 0 {
        unsafe {
            bootstrap(
                HelperRole::QueryIo,
                parent,
                executable.as_raw_fd(),
                child_channel.as_raw_fd(),
                stdio.as_raw_fd(),
                argv.as_ptr(),
                environment.as_ptr(),
                &fprog,
            )
        }
    }
    if raw_pidfd < 0 {
        return Err(ApplicationError::RetirementUnproven);
    }
    let mut child = Child {
        pid: pid as u32,
        pidfd: Some(unsafe { File::from_raw_fd(raw_pidfd) }),
        terminal: None,
    };
    drop(child_channel);
    let operation = (|| -> Result<QueryIo> {
        mask.restore()?;
        let info = pidfd_info(child.pidfd.as_ref().unwrap())?;
        require(
            info.pid == child.pid && info.ppid == parent as u32,
            "query I/O created pidfd is not the owned direct child",
        )?;
        send(
            channel.as_raw_fd(),
            wire,
            &[root.as_raw_fd(), owner.as_raw_fd()],
            deadline,
        )?;
        let reply = receive(channel.as_raw_fd(), 5, deadline)?;
        require(
            reply.peer.pid == pid as i32
                && reply.peer.uid == 0
                && reply.peer.gid == 0
                && reply.wire
                    == Wire {
                        phase: CREATED,
                        ..wire
                    },
            "query I/O creator reply identity differs",
        )?;
        child.finish(deadline)?;
        // Descriptor validation happens only after actual successful reap.
        let (waitid_code, waitid_status) =
            child.terminal.ok_or(ApplicationError::RetirementUnproven)?;
        let mut result = assemble(reply.files, root)?;
        result.creator = Some(CreatorReceipt {
            pid: child.pid,
            waitid_code,
            waitid_status,
        });
        Ok(result)
    })();
    if operation.is_err() && child.retire().is_err() {
        if let Some(fd) = child.pidfd.take() {
            mem::forget(fd);
        }
        return Err(ApplicationError::RetirementUnproven);
    }
    operation
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn query_io_wire_has_no_optional_path_label_or_pid_authority() {
        let w = Wire {
            phase: REQUEST,
            nonce: [7; 16],
            deadline_ns: 123,
        };
        assert_eq!(Wire::parse(&w.bytes()).unwrap(), w);
        let mut bytes = w.bytes();
        bytes[9] = 1;
        assert!(Wire::parse(&bytes).is_err());
        bytes = w.bytes();
        bytes[8] = 3;
        assert!(Wire::parse(&bytes).is_err());
        assert!(Wire::parse(&w.bytes()[..39]).is_err());
        let mut extra = w.bytes().to_vec();
        extra.push(0);
        assert!(Wire::parse(&extra).is_err());
    }
    #[test]
    fn query_io_extra_rights_are_rejected_and_closed() {
        let (a, b) = super::super::protocol::socketpair().unwrap();
        let null = File::open("/dev/null").unwrap();
        let deadline = Instant::now() + Duration::from_secs(1);
        let before = std::fs::read_dir("/proc/self/fd").unwrap().count();
        send(
            a.as_raw_fd(),
            Wire {
                phase: REQUEST,
                nonce: [3; 16],
                deadline_ns: 7,
            },
            &[null.as_raw_fd(), null.as_raw_fd(), null.as_raw_fd()],
            deadline,
        )
        .unwrap();
        assert!(receive(b.as_raw_fd(), 2, deadline).is_err());
        assert_eq!(std::fs::read_dir("/proc/self/fd").unwrap().count(), before);
    }
    #[test]
    fn query_io_pipe_pairs_reject_swaps_and_aliases() {
        let (read, write) = new_pipe().unwrap();
        let (other_read, other_write) = new_pipe().unwrap();
        assert!(validate_pipes(&read, &write).is_ok());
        assert!(validate_pipes(&write, &read).is_err());
        assert!(validate_pipes(&read, &other_write).is_err());
        assert_ne!(
            validate_pipes(&read, &write).unwrap(),
            validate_pipes(&other_read, &other_write).unwrap()
        );
    }
    #[test]
    fn query_io_ordinary_host_cannot_invoke_creator_or_create() {
        let root = File::open("/").unwrap();
        assert!(create(&root, Instant::now() + LIMIT).is_err());
        assert!(entry().is_err());
    }
    #[test]
    fn query_io_real_filter_denies_process_namespace_pidfd_and_exec() {
        let program = filter(None, false);
        let fprog = libc::sock_fprog {
            len: program.len() as u16,
            filter: program.as_ptr().cast_mut(),
        };
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            unsafe {
                if libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
                    || libc::prctl(libc::PR_SET_SECCOMP, 2, &fprog as *const libc::sock_fprog) != 0
                {
                    libc::_exit(31);
                }
                for syscall in [
                    libc::SYS_clone3,
                    libc::SYS_fork,
                    libc::SYS_vfork,
                    libc::SYS_setns,
                    libc::SYS_unshare,
                    libc::SYS_pidfd_open,
                    libc::SYS_pidfd_getfd,
                    libc::SYS_socket,
                    libc::SYS_execve,
                    libc::SYS_execveat,
                    libc::SYS_mount,
                    libc::SYS_ptrace,
                ] {
                    if libc::syscall(syscall, 0, 0, 0, 0, 0, 0) != -1
                        || *libc::__errno_location() != libc::EPERM
                    {
                        libc::_exit(32);
                    }
                }
                if libc::ioctl(-1, 0xb703_u64) != -1 || *libc::__errno_location() != libc::EPERM {
                    libc::_exit(33);
                }
                let mut p = [-1; 2];
                if libc::pipe2(p.as_mut_ptr(), libc::O_CLOEXEC) != 0 {
                    libc::_exit(34);
                }
                libc::close(p[0]);
                libc::close(p[1]);
                libc::_exit(0);
            }
        }
        let mut status = 0;
        assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
        assert!(libc::WIFEXITED(status));
        assert_eq!(libc::WEXITSTATUS(status), 0);
    }
    #[test]
    fn query_io_helper_stdio_is_read_only_eof_and_rejects_a_live_writer() {
        let fixed = fixed_stdio().unwrap();
        assert!(fixed.as_raw_fd() >= 64);
        let node = fixed_stdio_node(fixed.as_raw_fd(), false).unwrap();
        let same = above_reserved(&fixed).unwrap();
        assert_eq!(fixed_stdio_node(same.as_raw_fd(), false).unwrap(), node);
        assert_eq!(unsafe { libc::write(fixed.as_raw_fd(), b"x".as_ptr().cast(), 1) }, -1);
        assert_eq!(io::Error::last_os_error().raw_os_error(), Some(libc::EBADF));
        let (read, write) = new_pipe().unwrap();
        assert!(fixed_stdio_node(read.as_raw_fd(), false).is_err());
        assert!(fixed_stdio_node(write.as_raw_fd(), false).is_err());
        drop(write);
        assert!(fixed_stdio_node(read.as_raw_fd(), false).is_ok());
    }

    #[test]
    fn query_io_fresh_exec_initializes_both_fixed_filters() {
        // This proves host Rust/loader startup under the actual preexec BPF.
        // It does not claim a production MAC role or Android runtime readiness.
        let directory = tempfile::tempdir().unwrap();
        let source = directory.path().join("fresh.rs");
        let binary = directory.path().join("fresh");
        std::fs::write(&source, r#"
unsafe extern "C" {
    fn write(fd: i32, bytes: *const u8, length: usize) -> isize;
    fn _exit(status: i32) -> !;
}
fn main() {
    let marker = b"FRESH\n";
    unsafe {
        if write(3, marker.as_ptr(), marker.len()) != marker.len() as isize { _exit(71); }
        _exit(0);
    }
}
"#).unwrap();
        let compiler = std::env::var_os("RUSTC").unwrap_or_else(|| "rustc".into());
        let built = std::process::Command::new(compiler)
            .arg("--edition=2024").arg("-Cpanic=abort")
            .arg(&source).arg("-o").arg(&binary).output().unwrap();
        assert!(built.status.success(), "{}", String::from_utf8_lossy(&built.stderr));
        let executable = above_reserved(&File::open(&binary).unwrap()).unwrap();
        let stdio = fixed_stdio().unwrap();
        let mut outcomes = Vec::new();
        for metadata in [false, true] {
            super::super::worker::require_wait_semantics().unwrap();
            let (channel, child_channel) = super::super::protocol::socketpair().unwrap();
            let channel = File::from(channel);
            let child_channel = above_reserved(&File::from(child_channel)).unwrap();
            let instructions = filter(Some(executable.as_raw_fd()), metadata);
            let program = libc::sock_fprog {
                len: instructions.len() as u16,
                filter: instructions.as_ptr().cast_mut(),
            };
            let argv = [c"fixed-fresh-helper-probe".as_ptr(), std::ptr::null()];
            let environment = [c"LC_ALL=C".as_ptr(), std::ptr::null()];
            let mut raw = -1;
            let args = super::super::worker::CloneArgs {
                flags: libc::CLONE_PIDFD as u64,
                pidfd: (&mut raw as *mut i32) as u64,
                exit_signal: libc::SIGCHLD as u64,
                ..Default::default()
            };
            let mut mask = super::super::worker::SignalMask::block().unwrap();
            let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args)) };
            assert!(pid >= 0, "{}", io::Error::last_os_error());
            if pid == 0 {
                unsafe {
                    if libc::dup2(child_channel.as_raw_fd(), 3) != 3
                        || libc::fcntl(3, libc::F_SETFD, 0) != 0
                    { libc::_exit(125); }
                    for fd in 0..3 {
                        if libc::dup2(stdio.as_raw_fd(), fd) != fd
                            || libc::fcntl(fd, libc::F_SETFD, 0) != 0
                        { libc::_exit(125); }
                    }
                    let mut empty: libc::sigset_t = mem::zeroed();
                    if libc::sigemptyset(&mut empty) != 0
                        || libc::sigprocmask(libc::SIG_SETMASK, &empty, std::ptr::null_mut()) != 0
                        || libc::syscall(libc::SYS_close_range, 4_u32, u32::MAX, 4_u32) != 0
                        || libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
                        || libc::prctl(libc::PR_SET_SECCOMP, 2, &program as *const libc::sock_fprog) != 0
                    { libc::_exit(125); }
                    libc::syscall(libc::SYS_execveat, executable.as_raw_fd(), c"".as_ptr(),
                        argv.as_ptr(), environment.as_ptr(), libc::AT_EMPTY_PATH);
                    libc::_exit(125);
                }
            }
            assert!(raw >= 0);
            let mut child = Child {
                pid: pid as u32,
                pidfd: Some(unsafe { File::from_raw_fd(raw) }),
                terminal: None,
            };
            mask.restore().unwrap();
            drop(child_channel);
            let finished = child.finish(Instant::now() + Duration::from_secs(5));
            if finished.is_err() { child.retire().unwrap(); }
            let mut bytes = [0_u8; 32];
            let count = unsafe { libc::read(channel.as_raw_fd(), bytes.as_mut_ptr().cast(), bytes.len()) };
            assert!(count >= 0, "{}", io::Error::last_os_error());
            outcomes.push((metadata, child.terminal, bytes[..count as usize].to_vec()));
        }
        assert!(outcomes.iter().all(|(_, terminal, marker)| {
            *terminal == Some((libc::CLD_EXITED, 0)) && marker == b"FRESH\n"
        }), "actual fresh helper startup outcomes: {outcomes:?}");
    }

}
