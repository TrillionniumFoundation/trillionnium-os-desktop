//! Linux protected control-path custody. This creates no listener pathname,
//! service, capability, approved executable identity or semantic principal.
//! The privileged listener profile rejects another process's creation identity.

use crate::{MAX_HANDOFF_BUDGET, PeerIdentity, PeerPolicy};
use std::ffi::CString;
use std::fmt;
use std::mem::{size_of, zeroed};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

const SIOCUNIXFILE: libc::c_ulong = 0x89e0;
const MAX_COMPONENTS: usize = 32;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RootControlPathError {
    InvalidConfiguration,
    ProcessChanged,
    PrivilegedProfileRequired,
    ListenerCreatorMismatch,
    WrongDescriptor,
    PathRefused,
    PeerRefused,
    DeadlineExceeded,
    Retired,
    Io,
}
impl fmt::Display for RootControlPathError {
    fn fmt(&self, out: &mut fmt::Formatter<'_>) -> fmt::Result {
        out.write_str(match self {
            Self::InvalidConfiguration => "invalid control-path policy or absolute ceiling",
            Self::ProcessChanged => "control-path creator changed",
            Self::PrivilegedProfileRequired => "explicit privileged control-path profile required",
            Self::ListenerCreatorMismatch => "listener creation incarnation differs from owner",
            Self::WrongDescriptor => "control descriptor shape refused",
            Self::PathRefused => "protected control pathname custody refused",
            Self::PeerRefused => "original kernel control peer refused",
            Self::DeadlineExceeded => "original control-path ceiling expired",
            Self::Retired => "control-path custody retired",
            Self::Io => "control-path native operation refused",
        })
    }
}
impl std::error::Error for RootControlPathError {}
type Result<T> = std::result::Result<T, RootControlPathError>;

/// Configuration supplied by a trusted provisioner. Its construction grants
/// no authority and never derives approval from the observed socket or peer.
#[derive(Clone)]
pub struct RootControlPathPolicy {
    path: PathBuf,
    names: Vec<CString>,
    directory_gid: u32,
    directory_mode: u32,
    socket_gid: u32,
    socket_mode: u32,
}
impl fmt::Debug for RootControlPathPolicy {
    fn fmt(&self, out: &mut fmt::Formatter<'_>) -> fmt::Result {
        out.write_str("RootControlPathPolicy(<redacted configuration>)")
    }
}
impl RootControlPathPolicy {
    pub fn new(
        path: &Path,
        directory_gid: u32,
        directory_mode: u32,
        socket_gid: u32,
        socket_mode: u32,
    ) -> Result<Self> {
        let raw = path.as_os_str().as_bytes();
        if raw.len() < 2
            || raw.len() > 107
            || raw[0] != b'/'
            || !raw
                .iter()
                .all(|b| b.is_ascii_alphanumeric() || b"/._-".contains(b))
            || !matches!(directory_mode, 0o700 | 0o750)
            || !matches!(socket_mode, 0o600 | 0o660)
        {
            return Err(RootControlPathError::InvalidConfiguration);
        }
        let pieces: Vec<_> = raw[1..].split(|b| *b == b'/').collect();
        if pieces.len() < 2
            || pieces.len() > MAX_COMPONENTS
            || pieces
                .iter()
                .any(|v| v.is_empty() || *v == b"." || *v == b"..")
        {
            return Err(RootControlPathError::InvalidConfiguration);
        }
        let names = pieces
            .into_iter()
            .map(|v| CString::new(v).unwrap())
            .collect();
        Ok(Self {
            path: path.to_owned(),
            names,
            directory_gid,
            directory_mode,
            socket_gid,
            socket_mode,
        })
    }
}

fn creator(pid: u32) -> Result<()> {
    if pid != std::process::id() {
        return Err(RootControlPathError::ProcessChanged);
    }
    Ok(())
}
fn remaining(pid: u32, deadline: Instant) -> Result<Duration> {
    creator(pid)?;
    deadline
        .checked_duration_since(Instant::now())
        .filter(|v| !v.is_zero())
        .ok_or(RootControlPathError::DeadlineExceeded)
}
fn initial_ceiling(pid: u32, deadline: Instant) -> Result<()> {
    if remaining(pid, deadline)? > MAX_HANDOFF_BUDGET {
        return Err(RootControlPathError::InvalidConfiguration);
    }
    Ok(())
}
fn stat(fd: RawFd) -> Result<libc::stat> {
    // SAFETY: initialized output storage is live for fstat and not retained.
    let mut value = unsafe { zeroed() };
    if unsafe { libc::fstat(fd, &mut value) } != 0 {
        return Err(RootControlPathError::Io);
    }
    Ok(value)
}
fn option<T: Copy>(fd: RawFd, name: libc::c_int) -> Result<T> {
    // SAFETY: all callers use integer socket options and initialized output.
    let mut value: T = unsafe { zeroed() };
    let mut len = size_of::<T>() as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            fd,
            libc::SOL_SOCKET,
            name,
            std::ptr::addr_of_mut!(value).cast(),
            &mut len,
        )
    } != 0
        || len as usize != size_of::<T>()
    {
        return Err(RootControlPathError::WrongDescriptor);
    }
    Ok(value)
}
fn open_at(parent: RawFd, name: &CString, flags: libc::c_int) -> Result<OwnedFd> {
    // SAFETY: the name is bounded NUL-terminated; openat returns a fresh owner.
    let fd = unsafe {
        libc::openat(
            parent,
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW,
        )
    };
    if fd < 0 {
        return Err(RootControlPathError::PathRefused);
    }
    Ok(unsafe { OwnedFd::from_raw_fd(fd) })
}
#[derive(Clone, Copy, PartialEq, Eq)]
struct Identity {
    dev: libc::dev_t,
    ino: libc::ino_t,
    uid: u32,
    gid: u32,
    mode: libc::mode_t,
}
impl Identity {
    fn from(value: &libc::stat) -> Self {
        Self {
            dev: value.st_dev,
            ino: value.st_ino,
            uid: value.st_uid,
            gid: value.st_gid,
            mode: value.st_mode,
        }
    }
}
struct PathSnapshot {
    owner_pid: u32,
    policy: RootControlPathPolicy,
    descriptors: Vec<OwnedFd>,
    identities: Vec<Identity>,
    current: AtomicBool,
}
impl PathSnapshot {
    fn acquire(owner_pid: u32, policy: &RootControlPathPolicy) -> Result<Self> {
        creator(owner_pid)?;
        let root = open_at(
            libc::AT_FDCWD,
            &CString::new("/").unwrap(),
            libc::O_PATH | libc::O_DIRECTORY,
        )?;
        let mut descriptors = vec![root];
        let mut identities = Vec::new();
        let root_stat = stat(descriptors[0].as_raw_fd())?;
        check_directory(&root_stat)?;
        identities.push(Identity::from(&root_stat));
        for (index, name) in policy.names.iter().enumerate() {
            creator(owner_pid)?;
            let leaf = index + 1 == policy.names.len();
            let fd = open_at(
                descriptors.last().unwrap().as_raw_fd(),
                name,
                libc::O_PATH | if leaf { 0 } else { libc::O_DIRECTORY },
            )?;
            let metadata = stat(fd.as_raw_fd())?;
            if leaf {
                check_leaf(&metadata, policy)?;
            } else {
                check_directory(&metadata)?;
                if index + 2 == policy.names.len()
                    && (metadata.st_gid != policy.directory_gid
                        || metadata.st_mode & 0o7777 != policy.directory_mode)
                {
                    return Err(RootControlPathError::PathRefused);
                }
            }
            identities.push(Identity::from(&metadata));
            descriptors.push(fd);
        }
        creator(owner_pid)?;
        Ok(Self {
            owner_pid,
            policy: policy.clone(),
            descriptors,
            identities,
            current: AtomicBool::new(true),
        })
    }
    fn check(&self) -> Result<()> {
        creator(self.owner_pid)?;
        if !self.current.load(Ordering::Acquire) {
            return Err(RootControlPathError::Retired);
        }
        let result = (|| {
            let fresh = Self::acquire(self.owner_pid, &self.policy)?;
            if self.identities != fresh.identities {
                return Err(RootControlPathError::PathRefused);
            }
            for (index, fd) in self.descriptors.iter().enumerate() {
                creator(self.owner_pid)?;
                let metadata = stat(fd.as_raw_fd())?;
                if Identity::from(&metadata) != self.identities[index] {
                    return Err(RootControlPathError::PathRefused);
                }
                if index + 1 == self.descriptors.len() {
                    check_leaf(&metadata, &self.policy)?;
                } else {
                    check_directory(&metadata)?;
                }
            }
            Ok(())
        })();
        if result.is_err() {
            self.current.store(false, Ordering::Release);
        }
        result
    }
}
fn check_directory(metadata: &libc::stat) -> Result<()> {
    if metadata.st_mode & libc::S_IFMT != libc::S_IFDIR
        || metadata.st_uid != 0
        || metadata.st_mode & 0o022 != 0
    {
        return Err(RootControlPathError::PathRefused);
    }
    Ok(())
}
fn check_leaf(metadata: &libc::stat, policy: &RootControlPathPolicy) -> Result<()> {
    if metadata.st_mode & libc::S_IFMT != libc::S_IFSOCK
        || metadata.st_uid != 0
        || metadata.st_gid != policy.socket_gid
        || metadata.st_mode & 0o7777 != policy.socket_mode
        || metadata.st_nlink != 1
    {
        return Err(RootControlPathError::PathRefused);
    }
    Ok(())
}
fn shape(socket: &UnixStream, listening: bool) -> Result<()> {
    if option::<libc::c_int>(socket.as_raw_fd(), libc::SO_DOMAIN)? != libc::AF_UNIX
        || option::<libc::c_int>(socket.as_raw_fd(), libc::SO_TYPE)? != libc::SOCK_SEQPACKET
        || option::<libc::c_int>(socket.as_raw_fd(), libc::SO_ACCEPTCONN)? != i32::from(listening)
    {
        return Err(RootControlPathError::WrongDescriptor);
    }
    Ok(())
}
fn peer(socket: &UnixStream, policy: PeerPolicy) -> Result<PeerIdentity> {
    let value = PeerIdentity::from_stream(socket).map_err(|_| RootControlPathError::PeerRefused)?;
    policy
        .authorize(value)
        .map_err(|_| RootControlPathError::PeerRefused)?;
    Ok(value)
}
fn wait(fd: RawFd, owner_pid: u32, deadline: Instant, events: libc::c_short) -> Result<()> {
    loop {
        let left = remaining(owner_pid, deadline)?;
        let timeout = libc::timespec {
            tv_sec: left.as_secs() as libc::time_t,
            tv_nsec: left.subsec_nanos() as libc::c_long,
        };
        let mut state = libc::pollfd {
            fd,
            events,
            revents: 0,
        };
        // SAFETY: one live pollfd and timespec; ppoll retains no pointer.
        let result = unsafe { libc::ppoll(&mut state, 1, &timeout, std::ptr::null()) };
        remaining(owner_pid, deadline)?;
        if result < 0 {
            if std::io::Error::last_os_error().raw_os_error() == Some(libc::EINTR) {
                continue;
            }
            return Err(RootControlPathError::Io);
        }
        if result == 0 {
            return Err(RootControlPathError::DeadlineExceeded);
        }
        if state.revents & events != 0 {
            return Ok(());
        }
        return Err(RootControlPathError::Io);
    }
}

/// Consumes an existing listener created/listened by this exact root process.
/// Other creators, including an inherited PID1 listener, are rejected without
/// relisten. It never binds, chmods, chowns, unlinks or starts a service.
pub struct RootOwnedControlListener {
    owner_pid: u32,
    socket: Option<UnixStream>,
    snapshot: Arc<PathSnapshot>,
    bound: OwnedFd,
    bound_identity: Identity,
    cookie: u64,
    creator_identity: PeerIdentity,
}
impl RootOwnedControlListener {
    pub fn from_inherited(listener: OwnedFd, policy: &RootControlPathPolicy) -> Result<Self> {
        let owner_pid = std::process::id();
        creator(owner_pid)?;
        // SAFETY: identity observation only; no privilege changes.
        if unsafe { libc::geteuid() } != 0 {
            return Err(RootControlPathError::PrivilegedProfileRequired);
        }
        let socket = UnixStream::from(listener);
        shape(&socket, true)?;
        let identity = PeerIdentity::from_stream(&socket)
            .map_err(|_| RootControlPathError::WrongDescriptor)?;
        if identity.pid != Some(owner_pid)
            || identity.uid != 0
            || identity.gid != unsafe { libc::getegid() }
        {
            return Err(RootControlPathError::ListenerCreatorMismatch);
        }
        if socket
            .local_addr()
            .map_err(|_| RootControlPathError::WrongDescriptor)?
            .as_pathname()
            != Some(policy.path.as_path())
        {
            return Err(RootControlPathError::PathRefused);
        }
        let snapshot = Arc::new(PathSnapshot::acquire(owner_pid, policy)?);
        creator(owner_pid)?;
        // SAFETY: SIOCUNIXFILE returns a fresh O_PATH/CLOEXEC descriptor for
        // the kernel's actual bound dentry. No metadata/address fallback.
        let fd = unsafe { libc::ioctl(socket.as_raw_fd(), SIOCUNIXFILE) };
        if fd < 0 {
            return Err(RootControlPathError::PrivilegedProfileRequired);
        }
        let bound = unsafe { OwnedFd::from_raw_fd(fd) };
        let metadata = stat(bound.as_raw_fd())?;
        check_leaf(&metadata, policy)?;
        let bound_identity = Identity::from(&metadata);
        if snapshot.identities.last() != Some(&bound_identity) {
            return Err(RootControlPathError::PathRefused);
        }
        let cookie = option::<u64>(socket.as_raw_fd(), libc::SO_COOKIE)?;
        if cookie == 0 {
            return Err(RootControlPathError::WrongDescriptor);
        }
        socket
            .set_nonblocking(true)
            .map_err(|_| RootControlPathError::Io)?;
        let value = Self {
            owner_pid,
            socket: Some(socket),
            snapshot,
            bound,
            bound_identity,
            cookie,
            creator_identity: identity,
        };
        value.check()?;
        Ok(value)
    }
    fn check(&self) -> Result<()> {
        creator(self.owner_pid)?;
        self.snapshot.check()?;
        let socket = self.socket.as_ref().ok_or(RootControlPathError::Retired)?;
        shape(socket, true)?;
        // accept4's SOCK_NONBLOCK flag applies to the accepted socket, not
        // this listener. A stable alias clearing this status must be refused.
        let flags = unsafe { libc::fcntl(socket.as_raw_fd(), libc::F_GETFL) };
        if flags < 0 || flags & libc::O_NONBLOCK == 0 {
            return Err(RootControlPathError::WrongDescriptor);
        }
        if PeerIdentity::from_stream(socket).map_err(|_| RootControlPathError::WrongDescriptor)?
            != self.creator_identity
        {
            return Err(RootControlPathError::ListenerCreatorMismatch);
        }
        if option::<u64>(socket.as_raw_fd(), libc::SO_COOKIE)? != self.cookie
            || Identity::from(&stat(self.bound.as_raw_fd())?) != self.bound_identity
        {
            return Err(RootControlPathError::PathRefused);
        }
        check_leaf(&stat(self.bound.as_raw_fd())?, &self.snapshot.policy)?;
        self.snapshot.check()
    }
    pub fn accept_before(
        &mut self,
        approved_kernel_peer: PeerPolicy,
        deadline: Instant,
    ) -> Result<RootPathControlConnection> {
        creator(self.owner_pid)?;
        initial_ceiling(self.owner_pid, deadline)?;
        let result = (|| {
            self.check()?;
            let socket = self.socket.as_ref().ok_or(RootControlPathError::Retired)?;
            loop {
                remaining(self.owner_pid, deadline)?;
                self.check()?;
                // SAFETY: no address outputs; a successful accept4 returns
                // one fresh nonblocking CLOEXEC connected descriptor.
                let fd = unsafe {
                    libc::accept4(
                        socket.as_raw_fd(),
                        std::ptr::null_mut(),
                        std::ptr::null_mut(),
                        libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                    )
                };
                if fd >= 0 {
                    let accepted = unsafe { UnixStream::from_raw_fd(fd) };
                    self.check()?;
                    return RootPathControlConnection::admit(
                        self.owner_pid,
                        accepted,
                        Arc::clone(&self.snapshot),
                        approved_kernel_peer,
                        deadline,
                    );
                }
                let error = std::io::Error::last_os_error().raw_os_error();
                if matches!(error, Some(libc::EINTR)) {
                    continue;
                }
                if !matches!(error, Some(libc::EAGAIN)) {
                    return Err(RootControlPathError::Io);
                }
                wait(socket.as_raw_fd(), self.owner_pid, deadline, libc::POLLIN)?;
            }
        })();
        if result.is_err() {
            self.socket.take();
            self.snapshot.current.store(false, Ordering::Release);
        }
        result
    }
}

/// A protected pathname and original kernel peer, never approved executable
/// identity. Only the server can obtain its listener's SIOCUNIXFILE binding.
pub struct RootPathControlConnection {
    owner_pid: u32,
    socket: Option<UnixStream>,
    custody: Option<RootControlPathCustody>,
    deadline: Instant,
}
impl RootPathControlConnection {
    pub fn connect_before(
        policy: &RootControlPathPolicy,
        approved_kernel_peer: PeerPolicy,
        deadline: Instant,
    ) -> Result<Self> {
        let owner_pid = std::process::id();
        initial_ceiling(owner_pid, deadline)?;
        let snapshot = Arc::new(PathSnapshot::acquire(owner_pid, policy)?);
        remaining(owner_pid, deadline)?;
        // SAFETY: socket returns one fresh CLOEXEC nonblocking native owner.
        let fd = unsafe {
            libc::socket(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                0,
            )
        };
        if fd < 0 {
            return Err(RootControlPathError::Io);
        }
        let socket = unsafe { UnixStream::from_raw_fd(fd) };
        // SAFETY: zeroed sockaddr_un is valid initialized output storage.
        let mut address: libc::sockaddr_un = unsafe { zeroed() };
        address.sun_family = libc::AF_UNIX as libc::sa_family_t;
        let bytes = policy.path.as_os_str().as_bytes();
        for (dest, value) in address.sun_path.iter_mut().zip(bytes) {
            *dest = *value as libc::c_char;
        }
        let length = (std::mem::offset_of!(libc::sockaddr_un, sun_path) + bytes.len() + 1)
            as libc::socklen_t;
        snapshot.check()?;
        remaining(owner_pid, deadline)?;
        // SAFETY: live bounded pathname sockaddr; connect retains no pointer.
        if unsafe {
            libc::connect(
                socket.as_raw_fd(),
                std::ptr::addr_of!(address).cast(),
                length,
            )
        } != 0
        {
            if std::io::Error::last_os_error().raw_os_error() != Some(libc::EINPROGRESS) {
                return Err(RootControlPathError::Io);
            }
            wait(socket.as_raw_fd(), owner_pid, deadline, libc::POLLOUT)?;
            if option::<libc::c_int>(socket.as_raw_fd(), libc::SO_ERROR)? != 0 {
                return Err(RootControlPathError::Io);
            }
        }
        snapshot.check()?;
        if socket
            .peer_addr()
            .map_err(|_| RootControlPathError::WrongDescriptor)?
            .as_pathname()
            != Some(policy.path.as_path())
        {
            return Err(RootControlPathError::PathRefused);
        }
        Self::admit(owner_pid, socket, snapshot, approved_kernel_peer, deadline)
    }
    fn admit(
        owner_pid: u32,
        socket: UnixStream,
        snapshot: Arc<PathSnapshot>,
        policy: PeerPolicy,
        deadline: Instant,
    ) -> Result<Self> {
        remaining(owner_pid, deadline)?;
        shape(&socket, false)?;
        let identity = peer(&socket, policy)?;
        // SO_PEERPIDFD refers directly to the socket's original peer; a
        // later numeric pidfd_open lookup would not establish that relation.
        let fd = option::<libc::c_int>(socket.as_raw_fd(), libc::SO_PEERPIDFD)?;
        if fd < 0 {
            return Err(RootControlPathError::PeerRefused);
        }
        let pidfd = unsafe { OwnedFd::from_raw_fd(fd) };
        let held = socket.try_clone().map_err(|_| RootControlPathError::Io)?;
        let cookie = option::<u64>(socket.as_raw_fd(), libc::SO_COOKIE)?;
        let socket_identity = Identity::from(&stat(socket.as_raw_fd())?);
        let scope = Arc::new(ConnectionScope {
            owner_pid,
            snapshot,
            socket: held,
            pidfd,
            identity,
            socket_identity,
            cookie,
            deadline,
            current: AtomicBool::new(true),
        });
        scope.check()?;
        Ok(Self {
            owner_pid,
            socket: Some(socket),
            custody: Some(RootControlPathCustody { scope }),
            deadline,
        })
    }
    pub fn deadline(&self) -> Result<Instant> {
        creator(self.owner_pid)?;
        self.custody
            .as_ref()
            .ok_or(RootControlPathError::Retired)?
            .scope
            .check()?;
        Ok(self.deadline)
    }
    /// Transfers the same descriptor, unchanged Instant and unique custody.
    /// The consumer must retain this custody and check its verifier at each
    /// later boundary; a bare escaped FD is not a retained-path claim.
    pub fn consume_before<T>(
        mut self,
        consumer: impl FnOnce(OwnedFd, Instant, RootControlPathCustody) -> T,
    ) -> Result<T> {
        self.deadline()?;
        let socket = self.socket.take().ok_or(RootControlPathError::Retired)?;
        let custody = self.custody.take().ok_or(RootControlPathError::Retired)?;
        custody.scope.check()?;
        Ok(consumer(OwnedFd::from(socket), self.deadline, custody))
    }
}
struct ConnectionScope {
    owner_pid: u32,
    snapshot: Arc<PathSnapshot>,
    socket: UnixStream,
    pidfd: OwnedFd,
    identity: PeerIdentity,
    socket_identity: Identity,
    cookie: u64,
    deadline: Instant,
    current: AtomicBool,
}
impl ConnectionScope {
    fn check(&self) -> Result<()> {
        creator(self.owner_pid)?;
        if !self.current.load(Ordering::Acquire) {
            return Err(RootControlPathError::Retired);
        }
        let result = (|| {
            remaining(self.owner_pid, self.deadline)?;
            self.snapshot.check()?;
            let mut poll = libc::pollfd {
                fd: self.pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            // SAFETY: one initialized descriptor, zero wait, no pointer retained.
            if unsafe { libc::poll(&mut poll, 1, 0) } != 0 {
                return Err(RootControlPathError::PeerRefused);
            }
            shape(&self.socket, false)?;
            if self.identity
                != PeerIdentity::from_stream(&self.socket)
                    .map_err(|_| RootControlPathError::PeerRefused)?
                || self.socket_identity != Identity::from(&stat(self.socket.as_raw_fd())?)
                || self.cookie == 0
                || self.cookie != option::<u64>(self.socket.as_raw_fd(), libc::SO_COOKIE)?
            {
                return Err(RootControlPathError::PeerRefused);
            }
            self.snapshot.check()?;
            // The same original peer can die during the bounded pathname
            // reads; recheck its actual retained kernel handle afterward.
            poll.revents = 0;
            if unsafe { libc::poll(&mut poll, 1, 0) } != 0 {
                return Err(RootControlPathError::PeerRefused);
            }
            remaining(self.owner_pid, self.deadline)?;
            Ok(())
        })();
        if result.is_err() {
            self.current.store(false, Ordering::Release);
        }
        result
    }
}
/// Unique lifetime custody; dropping it revokes only its same-process scope.
///
/// ```compile_fail,E0451
/// use hepta_agent_transport::RootControlPathCustody;
/// let forged = RootControlPathCustody { scope: panic!() };
/// ```
///
/// ```compile_fail
/// use hepta_agent_transport::RootControlPathCustody;
/// fn requires_clone<T: Clone>() {}
/// requires_clone::<RootControlPathCustody>();
/// ```
pub struct RootControlPathCustody {
    scope: Arc<ConnectionScope>,
}
impl RootControlPathCustody {
    pub fn verifier(&self) -> Result<RootControlPathVerifier> {
        self.scope.check()?;
        Ok(RootControlPathVerifier {
            scope: Arc::clone(&self.scope),
        })
    }
}
impl Drop for RootControlPathCustody {
    fn drop(&mut self) {
        if self.scope.owner_pid == std::process::id() {
            self.scope.current.store(false, Ordering::Release);
        }
    }
}
/// Read-only original-path/kernel-incarnation check, not executable or unit
/// approval. This grants no native action, terminal fact or principal.
pub struct RootControlPathVerifier {
    scope: Arc<ConnectionScope>,
}
impl RootControlPathVerifier {
    pub fn verify_current(&self) -> Result<()> {
        self.scope.check()
    }
}
