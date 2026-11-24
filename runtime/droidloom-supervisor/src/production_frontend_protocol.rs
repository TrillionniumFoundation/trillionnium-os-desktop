//! Fixed production presentation handoff. Numeric PIDs are observations only:
//! every granted connection retains the kernel PIDFD and the original owner link.
//! This source is shared by the owner and presenter; it has no environment policy.
use std::fs::File;
use std::io;
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::MetadataExt;
use std::path::Path;
use std::time::Instant;

pub(crate) const CONTROL_PARENT: &str = "/run/droidloom-frontend";
pub(crate) const BROKER_CONTEXT: &[u8] = b"u:r:droidloom_broker:s0";
pub(crate) const PRESENTER_CONTEXT: &[u8] = b"u:system_r:droidloom_presenter:s0";
pub(crate) const COMPOSER_CONTEXT: &[u8] = b"u:r:hal_graphics_composer_default:s0";

pub(crate) const INPUT_CONTEXT: &[u8] = b"u:r:droidloom_input_bridge:s0";
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Role {
    Composer,
    Clipboard,
    TextInput,
    Notifications,
}
impl Role {
    pub(crate) const ALL: [Self; 4] = [
        Self::Composer,
        Self::Clipboard,
        Self::TextInput,
        Self::Notifications,
    ];
    pub(crate) fn control(self) -> &'static std::ffi::CStr {
        match self {
            Self::Composer => c"control.sock",
            Self::Clipboard => c"clipboard.sock",
            Self::TextInput => c"text-input.sock",
            Self::Notifications => c"notifications.sock",
        }
    }
    pub(crate) fn endpoint(self) -> &'static std::ffi::CStr {
        match self {
            Self::Composer => c"denial",
            Self::Clipboard => c"clipboard",
            Self::TextInput => c"text-input",
            Self::Notifications => c"notifications",
        }
    }
    pub(crate) fn socket_type(self) -> i32 {
        if self == Self::Composer {
            libc::SOCK_SEQPACKET
        } else {
            libc::SOCK_STREAM
        }
    }
    pub(crate) fn context(self) -> &'static [u8] {
        if self == Self::Composer {
            COMPOSER_CONTEXT
        } else {
            INPUT_CONTEXT
        }
    }
    pub(crate) fn android_id(self) -> u32 {
        if self == Self::Composer { 1000 } else { 0 }
    }
}

pub(crate) const HELLO: u32 = 1;
pub(crate) const GRANT: u32 = 2;
pub(crate) const ACK: u32 = 3;
const RECORD_BYTES: usize = 64;
const SO_PEERPIDFD: i32 = 77;
const PIDFD_GET_INFO: libc::c_ulong = 0xc040ff0b;

pub(crate) fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, message)
}
pub(crate) fn check(value: bool, message: &str) -> io::Result<()> {
    if value { Ok(()) } else { Err(invalid(message)) }
}
pub(crate) fn cv(value: i32) -> io::Result<i32> {
    if value < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(value)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Node(pub(crate) u64, pub(crate) u64);
impl Node {
    pub(crate) fn of(fd: &impl AsRawFd) -> io::Result<Self> {
        let mut value: libc::stat = unsafe { mem::zeroed() };
        cv(unsafe { libc::fstat(fd.as_raw_fd(), &mut value) })?;
        Ok(Self(value.st_dev, value.st_ino))
    }
}

#[repr(C)]
#[derive(Default, Clone, Copy, Debug)]
pub(crate) struct PidInfo {
    pub(crate) mask: u64,
    pub(crate) cgroup: u64,
    pub(crate) pid: u32,
    pub(crate) tgid: u32,
    pub(crate) ppid: u32,
    pub(crate) ruid: u32,
    pub(crate) rgid: u32,
    pub(crate) euid: u32,
    pub(crate) egid: u32,
    pub(crate) suid: u32,
    pub(crate) sgid: u32,
    pub(crate) fsuid: u32,
    pub(crate) fsgid: u32,
    pub(crate) exit_code: i32,
}
pub(crate) fn live(fd: &impl AsRawFd) -> io::Result<()> {
    let mut poll = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    check(
        cv(unsafe { libc::poll(&mut poll, 1, 0) })? == 0,
        "the original registered process exited or its PIDFD is invalid",
    )
}
pub(crate) fn pid_info(fd: &impl AsRawFd) -> io::Result<PidInfo> {
    live(fd)?;
    let mut info = PidInfo {
        mask: 3,
        ..Default::default()
    };
    cv(unsafe { libc::ioctl(fd.as_raw_fd(), PIDFD_GET_INFO, &mut info) })?;
    check(
        info.mask & 3 == 3 && info.pid > 1 && info.pid == info.tgid,
        "missing or invalid kernel process identity",
    )?;
    live(fd)?;
    Ok(info)
}
pub(crate) fn exact_ids(info: &PidInfo, uid: u32, gid: u32) -> io::Result<()> {
    check(
        [info.ruid, info.euid, info.suid, info.fsuid] == [uid; 4]
            && [info.rgid, info.egid, info.sgid, info.fsgid] == [gid; 4],
        "registered process credentials changed",
    )
}
fn option(fd: &impl AsRawFd, name: i32) -> io::Result<i32> {
    let mut value = 0_i32;
    let mut bytes = mem::size_of_val(&value) as libc::socklen_t;
    cv(unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            name,
            (&mut value as *mut i32).cast(),
            &mut bytes,
        )
    })?;
    check(
        bytes as usize == mem::size_of_val(&value),
        "socket option size differs",
    )?;
    Ok(value)
}
pub(crate) fn socket_shape(fd: &impl AsRawFd, listening: bool) -> io::Result<()> {
    socket_shape_as(fd, libc::SOCK_SEQPACKET, listening)
}
pub(crate) fn socket_shape_as(fd: &impl AsRawFd, kind: i32, listening: bool) -> io::Result<()> {
    check(
        option(fd, libc::SO_TYPE)? == kind
            && option(fd, libc::SO_DOMAIN)? == libc::AF_UNIX
            && option(fd, libc::SO_ACCEPTCONN)? == i32::from(listening),
        "frontend descriptor is not the required Unix sequenced socket",
    )?;
    check(
        cv(unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFD) })? & libc::FD_CLOEXEC != 0,
        "frontend descriptor is not close-on-exec",
    )?;
    if !listening {
        let mut address: libc::sockaddr_un = unsafe { mem::zeroed() };
        let mut size = mem::size_of_val(&address) as libc::socklen_t;
        cv(unsafe {
            libc::getpeername(
                fd.as_raw_fd(),
                (&mut address as *mut libc::sockaddr_un).cast(),
                &mut size,
            )
        })?;
        check(
            address.sun_family == libc::AF_UNIX as libc::sa_family_t,
            "frontend socket is unconnected",
        )?;
    }
    Ok(())
}
pub(crate) fn nonblocking(fd: &impl AsRawFd) -> io::Result<()> {
    let flags = cv(unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFL) })?;
    cv(unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_SETFL, flags | libc::O_NONBLOCK) })?;
    Ok(())
}
pub(crate) fn peer_pidfd(socket: &impl AsRawFd) -> io::Result<OwnedFd> {
    let mut raw = -1_i32;
    let mut bytes = mem::size_of_val(&raw) as libc::socklen_t;
    cv(unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            SO_PEERPIDFD,
            (&mut raw as *mut i32).cast(),
            &mut bytes,
        )
    })?;
    check(raw >= 0, "kernel did not return a peer PIDFD")?;
    let fd = unsafe { OwnedFd::from_raw_fd(raw) };
    check(
        bytes as usize == mem::size_of_val(&raw)
            && cv(unsafe { libc::fcntl(raw, libc::F_GETFD) })? & libc::FD_CLOEXEC != 0,
        "kernel peer PIDFD shape differs",
    )?;
    pid_info(&fd)?;
    Ok(fd)
}
pub(crate) fn credentials(socket: &impl AsRawFd) -> io::Result<libc::ucred> {
    let mut value: libc::ucred = unsafe { mem::zeroed() };
    let mut bytes = mem::size_of_val(&value) as libc::socklen_t;
    cv(unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut value as *mut libc::ucred).cast(),
            &mut bytes,
        )
    })?;
    check(
        bytes as usize == mem::size_of_val(&value) && value.pid > 1,
        "missing actual frontend peer credentials",
    )?;
    Ok(value)
}
pub(crate) fn peer_security(socket: &impl AsRawFd) -> io::Result<Vec<u8>> {
    let mut value = [0_u8; 256];
    let mut bytes = value.len() as libc::socklen_t;
    cv(unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERSEC,
            value.as_mut_ptr().cast(),
            &mut bytes,
        )
    })?;
    check(
        bytes > 0 && (bytes as usize) <= value.len(),
        "peer security bound",
    )?;
    let raw = &value[..bytes as usize];
    Ok(raw.strip_suffix(&[0]).unwrap_or(raw).to_vec())
}

pub(crate) struct Peer {
    pub(crate) pidfd: OwnedFd,
    pub(crate) pid: u32,
    pub(crate) uid: u32,
    pub(crate) gid: u32,
    node: Node,
    security: Vec<u8>,
    socket_type: i32,
}
impl Peer {
    pub(crate) fn acquire(socket: &impl AsRawFd, context: &[u8]) -> io::Result<Self> {
        Self::acquire_as(socket, context, libc::SOCK_SEQPACKET)
    }
    pub(crate) fn acquire_as(
        socket: &impl AsRawFd,
        context: &[u8],
        socket_type: i32,
    ) -> io::Result<Self> {
        socket_shape_as(socket, socket_type, false)?;
        let credentials = credentials(socket)?;
        let pidfd = peer_pidfd(socket)?;
        let value = Self {
            node: Node::of(&pidfd)?,
            pidfd,
            pid: credentials.pid as u32,
            uid: credentials.uid,
            gid: credentials.gid,
            security: peer_security(socket)?,
            socket_type,
        };
        check(
            value.security == context,
            "frontend peer is in a different SELinux domain",
        )?;
        value.revalidate(socket)?;
        Ok(value)
    }
    pub(crate) fn revalidate(&self, socket: &impl AsRawFd) -> io::Result<()> {
        socket_shape_as(socket, self.socket_type, false)?;
        endpoint_live(socket)?;
        let original = pid_info(&self.pidfd)?;
        let again = peer_pidfd(socket)?;
        let credentials = credentials(socket)?;
        check(
            Node::of(&self.pidfd)? == self.node
                && Node::of(&again)? == self.node
                && original.pid == self.pid
                && credentials.pid as u32 == self.pid
                && credentials.uid == self.uid
                && credentials.gid == self.gid
                && peer_security(socket)? == self.security,
            "original frontend peer changed",
        )?;
        exact_ids(&original, self.uid, self.gid)
    }
}

pub(crate) fn fresh_nonce() -> io::Result<[u8; 16]> {
    let mut value = [0u8; 16];
    let mut used = 0;
    while used < value.len() {
        let n =
            unsafe { libc::getrandom(value[used..].as_mut_ptr().cast(), value.len() - used, 0) };
        if n < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(e);
        }
        check(n > 0, "empty kernel random result")?;
        used += n as usize;
    }
    Ok(value)
}

pub(crate) struct Record {
    pub(crate) kind: u32,
    pub(crate) nonce: [u8; 16],
    pub(crate) pid: u32,
    pub(crate) uid: u32,
    pub(crate) gid: u32,
    pub(crate) fds: Vec<OwnedFd>,
}
impl Record {
    pub(crate) fn control(kind: u32, nonce: [u8; 16]) -> Self {
        Self {
            kind,
            nonce,
            pid: 0,
            uid: 0,
            gid: 0,
            fds: Vec::new(),
        }
    }
    fn bytes(&self) -> io::Result<[u8; RECORD_BYTES]> {
        self.shape()?;
        let mut bytes = [0u8; RECORD_BYTES];
        bytes[..8].copy_from_slice(b"DLFRONT1");
        bytes[8..12].copy_from_slice(&self.kind.to_le_bytes());
        bytes[16..32].copy_from_slice(&self.nonce);
        bytes[32..36].copy_from_slice(&self.pid.to_le_bytes());
        bytes[36..40].copy_from_slice(&self.uid.to_le_bytes());
        bytes[40..44].copy_from_slice(&self.gid.to_le_bytes());
        Ok(bytes)
    }
    fn shape(&self) -> io::Result<()> {
        check(
            match self.kind {
                HELLO | ACK => {
                    self.fds.is_empty() && self.pid == 0 && self.uid == 0 && self.gid == 0
                }
                GRANT => self.fds.len() == 2 && self.pid > 1,
                _ => false,
            },
            "unexpected frontend message or descriptor count",
        )
    }
}
pub(crate) fn send(socket: &impl AsRawFd, record: &Record) -> io::Result<()> {
    let mut bytes = record.bytes()?;
    let mut vector = libc::iovec {
        iov_base: bytes.as_mut_ptr().cast(),
        iov_len: bytes.len(),
    };
    let mut control = [0usize; 16];
    let mut msg: libc::msghdr = unsafe { mem::zeroed() };
    msg.msg_iov = &mut vector;
    msg.msg_iovlen = 1;
    if !record.fds.is_empty() {
        msg.msg_control = control.as_mut_ptr().cast();
        msg.msg_controllen =
            unsafe { libc::CMSG_SPACE((record.fds.len() * mem::size_of::<i32>()) as _) } as usize;
        let c = unsafe { libc::CMSG_FIRSTHDR(&msg) };
        unsafe {
            (*c).cmsg_level = libc::SOL_SOCKET;
            (*c).cmsg_type = libc::SCM_RIGHTS;
            (*c).cmsg_len =
                libc::CMSG_LEN((record.fds.len() * mem::size_of::<i32>()) as _) as usize;
            let data = libc::CMSG_DATA(c).cast::<i32>();
            for (index, fd) in record.fds.iter().enumerate() {
                data.add(index).write_unaligned(fd.as_raw_fd());
            }
        }
    }
    let n = unsafe {
        libc::sendmsg(
            socket.as_raw_fd(),
            &msg,
            libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
        )
    };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    check(n as usize == RECORD_BYTES, "partial frontend grant send")
}
pub(crate) fn receive(socket: &impl AsRawFd) -> io::Result<Option<Record>> {
    let mut bytes = [0u8; RECORD_BYTES + 1];
    let mut vector = libc::iovec {
        iov_base: bytes.as_mut_ptr().cast(),
        iov_len: bytes.len(),
    };
    let mut control = [0usize; 32];
    let mut msg: libc::msghdr = unsafe { mem::zeroed() };
    msg.msg_iov = &mut vector;
    msg.msg_iovlen = 1;
    msg.msg_control = control.as_mut_ptr().cast();
    msg.msg_controllen = mem::size_of_val(&control);
    let n = unsafe {
        libc::recvmsg(
            socket.as_raw_fd(),
            &mut msg,
            libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
        )
    };
    if n < 0 {
        let e = io::Error::last_os_error();
        return if matches!(
            e.kind(),
            io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
        ) {
            Ok(None)
        } else {
            Err(e)
        };
    }
    let mut fds = Vec::new();
    let mut allowed = true;
    let mut c = unsafe { libc::CMSG_FIRSTHDR(&msg) };
    while !c.is_null() {
        let length = unsafe { (*c).cmsg_len };
        let head = unsafe { libc::CMSG_LEN(0) } as usize;
        if length < head {
            allowed = false;
            break;
        }
        let raw_bytes = length - head;
        let level = unsafe { (*c).cmsg_level };
        let kind = unsafe { (*c).cmsg_type };
        if level == libc::SOL_SOCKET && (kind == libc::SCM_RIGHTS || kind == 4) {
            allowed &= kind == libc::SCM_RIGHTS && raw_bytes % mem::size_of::<i32>() == 0;
            let data = unsafe { libc::CMSG_DATA(c) }.cast::<i32>();
            for index in 0..raw_bytes / mem::size_of::<i32>() {
                let raw = unsafe { data.add(index).read_unaligned() };
                if raw >= 0 {
                    fds.push(unsafe { OwnedFd::from_raw_fd(raw) });
                } else {
                    allowed = false;
                }
            }
        } else {
            allowed = false;
        }
        c = unsafe { libc::CMSG_NXTHDR(&msg, c) };
    }
    check(
        allowed
            && msg.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) == 0
            && n as usize == RECORD_BYTES
            && &bytes[..8] == b"DLFRONT1"
            && bytes[12..16] == [0; 4]
            && bytes[44..64] == [0; 20],
        "invalid, closed or truncated frontend record",
    )?;
    let field = |start| u32::from_le_bytes(bytes[start..start + 4].try_into().unwrap());
    let value = Record {
        kind: field(8),
        nonce: bytes[16..32].try_into().unwrap(),
        pid: field(32),
        uid: field(36),
        gid: field(40),
        fds,
    };
    value.shape()?;
    Ok(Some(value))
}
pub(crate) fn wait(socket: &impl AsRawFd, events: i16, until: Instant) -> io::Result<()> {
    check(
        Instant::now() < until,
        "frontend registration deadline expired",
    )?;
    let mut p = libc::pollfd {
        fd: socket.as_raw_fd(),
        events,
        revents: 0,
    };
    let n = unsafe {
        libc::poll(
            &mut p,
            1,
            until
                .saturating_duration_since(Instant::now())
                .as_millis()
                .clamp(1, 100) as i32,
        )
    };
    if n < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
        return Err(io::Error::last_os_error());
    }
    check(
        p.revents & (libc::POLLERR | libc::POLLNVAL | libc::POLLHUP) == 0,
        "frontend owner connection closed",
    )
}
pub(crate) fn control_live(socket: &impl AsRawFd) -> io::Result<()> {
    let mut p = libc::pollfd {
        fd: socket.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    cv(unsafe { libc::poll(&mut p, 1, 0) })?;
    // No post-registration messages are permitted. EOF/revoke and data both
    // terminate this original authorization; there is no reconnect fallback.
    check(
        p.revents == 0,
        "frontend authorization was closed or changed",
    )
}
pub(crate) fn endpoint_live(fd: &impl AsRawFd) -> io::Result<()> {
    let mut p = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLRDHUP,
        revents: 0,
    };
    cv(unsafe { libc::poll(&mut p, 1, 0) })?;
    check(
        p.revents & (libc::POLLHUP | libc::POLLRDHUP | libc::POLLERR | libc::POLLNVAL) == 0,
        "original endpoint closed or half-closed",
    )
}
pub(crate) fn reply(record: &Record, kind: u32, nonce: [u8; 16]) -> io::Result<()> {
    record.shape()?;
    check(
        record.kind == kind && record.nonce == nonce,
        "stale or mismatched frontend exchange",
    )
}
pub(crate) fn shutdown(fd: &impl AsRawFd) {
    unsafe {
        libc::shutdown(fd.as_raw_fd(), libc::SHUT_RDWR);
    }
}

pub(crate) fn address(path: &str) -> io::Result<(libc::sockaddr_un, libc::socklen_t)> {
    let mut value: libc::sockaddr_un = unsafe { mem::zeroed() };
    check(
        path.starts_with('/') && !path.as_bytes().contains(&0) && path.len() < value.sun_path.len(),
        "invalid fixed frontend path",
    )?;
    value.sun_family = libc::AF_UNIX as _;
    for (out, byte) in value.sun_path.iter_mut().zip(path.bytes()) {
        *out = byte as _;
    }
    Ok((
        value,
        (mem::offset_of!(libc::sockaddr_un, sun_path) + path.len() + 1) as _,
    ))
}
pub(crate) fn socket() -> io::Result<OwnedFd> {
    socket_as(libc::SOCK_SEQPACKET)
}
pub(crate) fn socket_as(kind: i32) -> io::Result<OwnedFd> {
    let raw = cv(unsafe {
        libc::socket(
            libc::AF_UNIX,
            kind | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0,
        )
    })?;
    Ok(unsafe { OwnedFd::from_raw_fd(raw) })
}
pub(crate) fn openat(parent: &impl AsRawFd, name: &std::ffi::CStr, flags: i32) -> io::Result<File> {
    let raw = cv(unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
            0,
        )
    })?;
    Ok(unsafe { File::from_raw_fd(raw) })
}
pub(crate) fn trusted_directory(path: &str) -> io::Result<File> {
    use std::ffi::CString;
    let raw = cv(unsafe {
        libc::open(
            c"/".as_ptr(),
            libc::O_PATH | libc::O_DIRECTORY | libc::O_CLOEXEC,
        )
    })?;
    let mut held = unsafe { File::from_raw_fd(raw) };
    for part in Path::new(path).components() {
        use std::path::Component;
        match part {
            Component::RootDir => (),
            Component::Normal(name) => {
                use std::os::unix::ffi::OsStrExt;
                let name =
                    CString::new(name.as_bytes()).map_err(|_| invalid("bad trusted path"))?;
                held = openat(&held, &name, libc::O_PATH | libc::O_DIRECTORY)?;
                let m = held.metadata()?;
                check(
                    m.is_dir() && m.uid() == 0 && m.gid() == 0 && m.mode() & 0o022 == 0,
                    "frontend parent is not a root-owned protected directory",
                )?;
            }
            _ => return Err(invalid("noncanonical trusted path")),
        }
    }
    Ok(held)
}
pub(crate) fn socket_node(
    parent: &File,
    name: &std::ffi::CStr,
    uid: u32,
    gid: u32,
    mode: u32,
) -> io::Result<File> {
    let node = openat(parent, name, libc::O_PATH)?;
    let m = node.metadata()?;
    check(
        m.mode() == libc::S_IFSOCK | mode && m.uid() == uid && m.gid() == gid && m.nlink() == 1,
        "frontend filesystem socket identity differs",
    )?;
    Ok(node)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn pair() -> (OwnedFd, OwnedFd) {
        let mut fds = [-1; 2];
        cv(unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                0,
                fds.as_mut_ptr(),
            )
        })
        .unwrap();
        unsafe { (OwnedFd::from_raw_fd(fds[0]), OwnedFd::from_raw_fd(fds[1])) }
    }
    #[test]
    fn frontend_records_bind_nonce_and_exact_descriptor_roles() {
        let (a, b) = pair();
        let nonce = fresh_nonce().unwrap();
        send(&a, &Record::control(HELLO, nonce)).unwrap();
        let r = receive(&b).unwrap().unwrap();
        assert_eq!(r.kind, HELLO);
        assert_eq!(r.nonce, nonce);
        assert!(r.fds.is_empty());
        let (channel, _) = pair();
        let pidfd = peer_pidfd(&channel).unwrap();
        let expected = Node::of(&pidfd).unwrap();
        let grant = Record {
            kind: GRANT,
            nonce,
            pid: std::process::id(),
            uid: unsafe { libc::getuid() },
            gid: unsafe { libc::getgid() },
            fds: vec![channel, pidfd],
        };
        send(&a, &grant).unwrap();
        let received = receive(&b).unwrap().unwrap();
        assert_eq!(received.fds.len(), 2);
        socket_shape(&received.fds[0], false).unwrap();
        assert_eq!(Node::of(&received.fds[1]).unwrap(), expected);
        assert_eq!(pid_info(&received.fds[1]).unwrap().pid, std::process::id());
    }
    #[test]
    fn frontend_rejects_non_pidfd_and_wrong_socket_resources() {
        let file = File::open("/dev/null").unwrap();
        assert!(pid_info(&file).is_err());
        assert!(socket_shape(&file, false).is_err());
        let (a, _) = pair();
        let info = pid_info(&peer_pidfd(&a).unwrap()).unwrap();
        assert!(exact_ids(&info, info.euid.wrapping_add(1), info.egid).is_err());
    }
    #[test]
    fn frontend_owner_disconnect_revokes_authorization() {
        let (a, b) = pair();
        control_live(&a).unwrap();
        shutdown(&b);
        assert!(control_live(&a).is_err());
    }
    #[test]
    fn frontend_truncated_record_closes_received_descriptors() {
        let (a, b) = pair();
        let (probe, observer) = pair();
        let mut bytes = [0u8; RECORD_BYTES + 1];
        bytes[..8].copy_from_slice(b"DLFRONT1");
        let mut iov = libc::iovec {
            iov_base: bytes.as_mut_ptr().cast(),
            iov_len: bytes.len(),
        };
        let mut control = [0usize; 8];
        let mut msg: libc::msghdr = unsafe { mem::zeroed() };
        msg.msg_iov = &mut iov;
        msg.msg_iovlen = 1;
        msg.msg_control = control.as_mut_ptr().cast();
        msg.msg_controllen = unsafe { libc::CMSG_SPACE(4) } as usize;
        let c = unsafe { libc::CMSG_FIRSTHDR(&msg) };
        unsafe {
            (*c).cmsg_level = libc::SOL_SOCKET;
            (*c).cmsg_type = libc::SCM_RIGHTS;
            (*c).cmsg_len = libc::CMSG_LEN(4) as usize;
            libc::CMSG_DATA(c)
                .cast::<i32>()
                .write_unaligned(probe.as_raw_fd());
        }
        assert_eq!(
            unsafe { libc::sendmsg(a.as_raw_fd(), &msg, libc::MSG_NOSIGNAL) },
            bytes.len() as isize
        );
        drop(probe);
        assert!(receive(&b).is_err());
        let mut p = libc::pollfd {
            fd: observer.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        assert_eq!(unsafe { libc::poll(&mut p, 1, 0) }, 1);
        assert_ne!(p.revents & libc::POLLHUP, 0);
    }

    #[test]
    fn frontend_rejects_wrong_nonce_kind_and_postgrant_data() {
        let nonce = fresh_nonce().unwrap();
        assert!(reply(&Record::control(ACK, [0; 16]), ACK, nonce).is_err());
        assert!(reply(&Record::control(HELLO, nonce), ACK, nonce).is_err());
        let (a, b) = pair();
        send(&b, &Record::control(HELLO, nonce)).unwrap();
        assert!(control_live(&a).is_err());
    }
    #[test]
    fn frontend_stream_and_composer_descriptors_cannot_be_interchanged() {
        let (a, b) = std::os::unix::net::UnixStream::pair().unwrap();
        socket_shape_as(&a, libc::SOCK_STREAM, false).unwrap();
        assert!(socket_shape(&a, false).is_err());
        let (c, _) = pair();
        assert!(socket_shape_as(&c, libc::SOCK_STREAM, false).is_err());
        endpoint_live(&a).unwrap();
        b.shutdown(std::net::Shutdown::Write).unwrap();
        assert!(endpoint_live(&a).is_err());
    }
}
