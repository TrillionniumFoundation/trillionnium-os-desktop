//! Initial-userns selected host socket custody.
//! A helper creates only sockets in the original newly selected netns. The
//! original parent connects/binds them, retaining its real SO_PEERCRED/PIDFD.
//! Source candidate: this module has no compilation or runtime qualification yet.
use super::host_peer::{HostPeerAuthority, HostPeerIssuer, HostPeerPair, HostPeerRole};
use super::host_peer_control::{PrivateHostPeerControl, SelectorState, SetOutcome};
use super::host_peer_namespace::{HostPeerNetworkBinding, HostPeerNetworkOwner};
use super::netns_provider::{NamespaceIdentity, namespace};
use super::package::{PackageMacOwner, PackageMacRole};
use super::*;
use std::os::fd::{IntoRawFd, OwnedFd};
use std::os::unix::net::{UnixListener, UnixStream};

#[path = "production_mac_kernel_first_socket.rs"]
mod kernel_first_socket;
pub(crate) use kernel_first_socket::{
    KernelFirstAcceptedStream, KernelFirstBrokerListener, KernelFirstPackageStream,
};

const READY: u32 = 0x5048_5330;
const REPLY: u32 = 0x5048_5331;
const CREATE_BOUND: Duration = Duration::from_secs(10);
const RETIRE_BOUND: Duration = Duration::from_secs(2);
const SO_PEERPIDFD: i32 = 77;
#[repr(C)]
#[derive(Clone, Copy, Debug)]
struct Packet {
    magic: u32,
    stage: u32,
    errno: i32,
    reserved: u32,
    nonce: [u8; 16],
}
const _: () = assert!(std::mem::size_of::<Packet>() == 32);
#[repr(C)]
#[derive(Clone, Copy)]
struct ExpectedNamespace {
    dev: u64,
    ino: u64,
    id: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    spare: u32,
}
impl From<NamespaceIdentity> for ExpectedNamespace {
    fn from(n: NamespaceIdentity) -> Self {
        Self {
            dev: n.node.dev,
            ino: n.node.ino,
            id: n.id,
            mode: n.node.mode,
            uid: n.node.uid,
            gid: n.node.gid,
            spare: 0,
        }
    }
}
#[repr(C)]
struct KernelStatfs {
    kind: i64,
    block_size: i64,
    blocks: u64,
    free_blocks: u64,
    available_blocks: u64,
    files: u64,
    free_files: u64,
    fsid: [i32; 2],
    name_length: i64,
    fragment_size: i64,
    flags: i64,
    spare: [i64; 4],
}
const _: () = assert!(std::mem::size_of::<KernelStatfs>() == 120);
#[repr(C)]
struct TypedContext {
    id: u64,
    flags: u64,
    len: u64,
    ctx_len: u64,
    ctx: [u8; 128],
}

fn zero(rc: i32) -> Result<()> {
    if rc == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error().into())
    }
}
fn now_ns() -> Result<u64> {
    let mut t: libc::timespec = unsafe { std::mem::zeroed() };
    zero(unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut t) })?;
    require(
        t.tv_sec >= 0 && (0..1_000_000_000).contains(&t.tv_nsec),
        "selected socket monotonic clock",
    )?;
    (t.tv_sec as u64)
        .checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(t.tv_nsec as u64))
        .ok_or(MacError::Rejected("selected socket clock overflow"))
}
fn nonce() -> Result<[u8; 16]> {
    let mut v = [0_u8; 16];
    let rc = unsafe { libc::syscall(libc::SYS_getrandom, v.as_mut_ptr(), v.len(), 1_u32) };
    if rc < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(rc == v.len() as i64, "complete original helper nonce")?;
    Ok(v)
}
unsafe fn alive_raw(fd: RawFd) -> bool {
    let mut p = libc::pollfd {
        fd,
        events: libc::POLLIN,
        revents: 0,
    };
    unsafe { libc::syscall(libc::SYS_poll, &mut p, 1, 0) == 0 && p.revents == 0 }
}
fn creator() -> Result<(OwnedFd, i64, i32)> {
    let tid = unsafe { libc::syscall(libc::SYS_gettid) };
    let pid = unsafe { libc::getpid() };
    require(
        tid > 1 && pid > 1,
        "selected socket helper cannot be host PID1",
    )?;
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, tid, 0x80_u32) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let held = unsafe { OwnedFd::from_raw_fd(raw as i32) };
    let mut info = crate::production_activation_protocol::PidfdInfo::request_exit();
    info.mask = 3;
    zero(unsafe {
        libc::ioctl(
            held.as_raw_fd(),
            crate::production_activation_protocol::PIDFD_GET_INFO as libc::c_ulong,
            &mut info,
        )
    })?;
    require(
        info.mask & 3 == 3
            && info.pid == tid as u32
            && info.tgid == pid as u32
            && unsafe { alive_raw(held.as_raw_fd()) },
        "original selected socket creator thread PIDFD",
    )?;
    Ok((held, tid, pid))
}
#[derive(Debug)]
struct Helper {
    pidfd: Option<OwnedFd>,
    channel: OwnedFd,
    creator_pidfd: OwnedFd,
    creator: i64,
    pid: i32,
    deadline: Instant,
    nonce: [u8; 16],
    preparation_error: Option<i32>,
    ready: bool,
    started: bool,
    rights: Vec<OwnedFd>,
    rights_packet: Option<Packet>,
    acked: bool,
    reply: Option<Packet>,
    exit: Option<(i32, i32)>,
    waited_pid: Option<i32>,
    terminal_verified: bool,
    retirement_end: Option<Instant>,
    parent: i32,
    process: Option<File>,
    process_identity: Option<SocketProcessIdentity>,
}
impl Helper {
    fn spawn(
        network: &File,
        expected: ExpectedNamespace,
        expected_user: ExpectedNamespace,
        role: HostPeerRole,
        end: Instant,
    ) -> Result<Self> {
        let duration = end
            .checked_duration_since(Instant::now())
            .filter(|v| !v.is_zero() && *v <= CREATE_BOUND)
            .ok_or(MacError::Rejected("fixed selected socket helper deadline"))?;
        let absolute = now_ns()?
            .checked_add(
                u64::try_from(duration.as_nanos())
                    .map_err(|_| MacError::Rejected("socket deadline overflow"))?,
            )
            .ok_or(MacError::Rejected("socket absolute deadline overflow"))?;
        let mut action: libc::sigaction = unsafe { std::mem::zeroed() };
        zero(unsafe { libc::sigaction(libc::SIGCHLD, std::ptr::null(), &mut action) })?;
        require(
            action.sa_sigaction == libc::SIG_DFL && action.sa_flags & libc::SA_NOCLDWAIT == 0,
            "selected socket helper requires original-parent PIDFD reaping",
        )?;
        let mut pair = [-1_i32; 2];
        zero(unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                0,
                pair.as_mut_ptr(),
            )
        })?;
        let parent = unsafe { OwnedFd::from_raw_fd(pair[0]) };
        let child = unsafe { OwnedFd::from_raw_fd(pair[1]) };
        let one = 1_i32;
        zero(unsafe {
            libc::setsockopt(
                parent.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PASSCRED,
                (&one as *const i32).cast(),
                std::mem::size_of_val(&one) as _,
            )
        })?;
        let (creator_pidfd, creator, parent_pid) = creator()?;
        let nonce = nonce()?;
        let mut full: libc::sigset_t = unsafe { std::mem::zeroed() };
        let mut old: libc::sigset_t = unsafe { std::mem::zeroed() };
        zero(unsafe { libc::sigfillset(&mut full) })?;
        let blocked = unsafe { libc::pthread_sigmask(libc::SIG_SETMASK, &full, &mut old) };
        if blocked != 0 {
            return Err(io::Error::from_raw_os_error(blocked).into());
        }
        let mut pidfd = -1_i32;
        let mut args = [0_u64; 11];
        args[0] = libc::CLONE_PIDFD as u64;
        args[1] = (&mut pidfd as *mut i32) as u64;
        args[4] = libc::SIGCHLD as u64;
        let pid = unsafe {
            libc::syscall(
                libc::SYS_clone3,
                args.as_ptr(),
                std::mem::size_of_val(&args),
            )
        };
        if pid == 0 {
            unsafe {
                child_run(
                    network.as_raw_fd(),
                    expected,
                    expected_user,
                    role,
                    child.as_raw_fd(),
                    creator_pidfd.as_raw_fd(),
                    parent_pid,
                    nonce,
                    absolute,
                )
            }
        }
        if pid < 0 {
            let error = io::Error::last_os_error();
            unsafe { libc::pthread_sigmask(libc::SIG_SETMASK, &old, std::ptr::null_mut()) };
            drop(child);
            return Err(error.into());
        }
        if pidfd < 0 || pid > i32::MAX as i64 {
            // A successful CLONE_PIDFD without its atomic PIDFD violates the
            // kernel contract. Returning Err here would abandon a real child.
            // Fail the original process closed; never adopt a numeric PID.
            unsafe { libc::abort() }
        }
        // Establish original typed ownership immediately after successful
        // clone, before restoring signals or performing another syscall.
        let mut value = Self {
            pidfd: Some(unsafe { OwnedFd::from_raw_fd(pidfd) }),
            channel: parent,
            creator_pidfd,
            creator,
            pid: pid as i32,
            deadline: end,
            nonce,
            preparation_error: None,
            ready: false,
            started: false,
            rights: Vec::new(),
            rights_packet: None,
            acked: false,
            reply: None,
            exit: None,
            waited_pid: None,
            terminal_verified: false,
            retirement_end: None,
            parent: parent_pid,
            process: None,
            process_identity: None,
        };
        let restored =
            unsafe { libc::pthread_sigmask(libc::SIG_SETMASK, &old, std::ptr::null_mut()) };
        value.preparation_error = (restored != 0).then_some(restored);
        drop(child);
        // A restoration error remains in this original owner. The caller
        // stores it before start() can report the error or release READY.
        Ok(value)
    }
    fn same_creator(&self) -> Result<()> {
        require(
            unsafe { libc::syscall(libc::SYS_gettid) } == self.creator
                && unsafe { alive_raw(self.creator_pidfd.as_raw_fd()) },
            "selected socket owner left its original creating thread",
        )
    }
    fn before(&self) -> Result<()> {
        self.same_creator()?;
        require(
            Instant::now() < self.deadline,
            "original selected socket creation deadline",
        )
    }
    fn peer_live(&self) -> Result<()> {
        self.before()?;
        require(
            self.exit.is_none()
                && self
                    .pidfd
                    .as_ref()
                    .is_some_and(|f| unsafe { alive_raw(f.as_raw_fd()) }),
            "original socket helper must remain live before ACK",
        )
    }
    fn poll(&self) -> Result<()> {
        self.before()?;
        let mut p = [
            libc::pollfd {
                fd: self.channel.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: self
                    .pidfd
                    .as_ref()
                    .ok_or(MacError::Rejected("socket helper PIDFD absent"))?
                    .as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
        ];
        let rc = unsafe {
            libc::poll(
                p.as_mut_ptr(),
                p.len() as _,
                self.deadline
                    .saturating_duration_since(Instant::now())
                    .as_millis()
                    .clamp(1, 50) as i32,
            )
        };
        if rc < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
            return Err(io::Error::last_os_error().into());
        }
        require(
            !p.iter().any(|v| v.revents & libc::POLLNVAL != 0),
            "original socket helper descriptor changed",
        )?;
        self.before()
    }
    /// Own every delivered FD before rejecting framing, nonce or credentials.
    fn receive(&mut self) -> Result<Option<(Packet, usize)>> {
        let mut packet: Packet = unsafe { std::mem::zeroed() };
        let mut iov = libc::iovec {
            iov_base: (&mut packet as *mut Packet).cast(),
            iov_len: std::mem::size_of::<Packet>(),
        };
        let mut control = [0_usize; 24];
        let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
        msg.msg_iov = &mut iov;
        msg.msg_iovlen = 1;
        msg.msg_control = control.as_mut_ptr().cast();
        msg.msg_controllen = std::mem::size_of_val(&control);
        let count = unsafe {
            libc::recvmsg(
                self.channel.as_raw_fd(),
                &mut msg,
                libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
            )
        };
        if count < 0 {
            let e = io::Error::last_os_error();
            if [Some(libc::EAGAIN), Some(libc::EINTR)].contains(&e.raw_os_error()) {
                return Ok(None);
            }
            return Err(e.into());
        }
        if count == 0 {
            return Err(MacError::Rejected(
                "selected socket helper closed before its record",
            ));
        }
        let mut credentials = None;
        let mut invalid = false;
        let before = self.rights.len();
        let mut header = unsafe { libc::CMSG_FIRSTHDR(&msg) };
        while !header.is_null() {
            let h = unsafe { &*header };
            let base = unsafe { libc::CMSG_LEN(0) } as usize;
            if h.cmsg_len < base {
                invalid = true;
                break;
            }
            let n = h.cmsg_len - base;
            let body = unsafe { libc::CMSG_DATA(header) };
            if h.cmsg_level == libc::SOL_SOCKET && h.cmsg_type == libc::SCM_RIGHTS {
                invalid |= n == 0 || n % std::mem::size_of::<i32>() != 0;
                for i in 0..n / std::mem::size_of::<i32>() {
                    let raw = unsafe { std::ptr::read_unaligned(body.add(i * 4).cast::<i32>()) };
                    if raw < 0 {
                        invalid = true;
                    } else {
                        self.rights.push(unsafe { OwnedFd::from_raw_fd(raw) });
                    }
                }
            } else if h.cmsg_level == libc::SOL_SOCKET
                && h.cmsg_type == libc::SCM_CREDENTIALS
                && n == std::mem::size_of::<libc::ucred>()
            {
                invalid |= credentials.is_some();
                credentials = Some(unsafe { std::ptr::read_unaligned(body.cast::<libc::ucred>()) });
            } else {
                invalid = true;
            }
            header = unsafe { libc::CMSG_NXTHDR(&msg, header) };
        }
        let c = credentials.ok_or(MacError::Rejected(
            "actual socket helper sender credentials absent",
        ))?;
        require(
            !invalid
                && msg.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) == 0
                && count as usize == std::mem::size_of::<Packet>()
                && c.pid == self.pid
                && c.uid == unsafe { libc::getuid() }
                && c.gid == unsafe { libc::getgid() }
                && packet.nonce == self.nonce
                && packet.reserved == 0
                && (packet.magic == READY || packet.magic == REPLY)
                && (1..=8).contains(&packet.stage)
                && (0..=4095).contains(&packet.errno),
            "original helper record framing/nonce/actual credentials differ",
        )?;
        require(
            self.rights.len() <= 3,
            "unexpected additional helper rights remain retained for retirement",
        )?;
        for fd in &self.rights {
            let flags = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFD) };
            if flags < 0 {
                return Err(io::Error::last_os_error().into());
            }
            require(
                flags & libc::FD_CLOEXEC != 0,
                "actual received socket must be CLOEXEC",
            )?;
        }
        Ok(Some((packet, self.rights.len() - before)))
    }
    fn send_byte(&self, value: u8) -> Result<()> {
        self.peer_live()?;
        let n = unsafe {
            libc::send(
                self.channel.as_raw_fd(),
                (&value as *const u8).cast(),
                1,
                libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
            )
        };
        if n < 0 {
            return Err(io::Error::last_os_error().into());
        }
        require(n == 1, "fixed original helper barrier byte")
    }
    fn start(&mut self) -> Result<()> {
        self.before()?;
        if let Some(error) = self.preparation_error {
            return Err(io::Error::from_raw_os_error(error).into());
        }
        require(
            !self.started && !self.ready && self.exit.is_none(),
            "helper release cannot be replayed",
        )?;
        loop {
            self.before()?;
            if let Some((p, n)) = self.receive()? {
                if p.magic == REPLY {
                    self.reply = Some(p);
                }
                require(
                    p.magic == READY && p.stage == 3 && p.errno == 0 && n == 0,
                    "actual post-PDEATHSIG helper READY required",
                )?;
                self.ready = true;
                break;
            }
            self.poll()?;
        }
        // Only the same original still-executing parent can release READY. A
        // cached getppid or a leader PIDFD poll alone cannot close this race.
        self.send_byte(1)?;
        self.started = true;
        Ok(())
    }
    fn receive_rights(&mut self) -> Result<()> {
        require(
            self.started && self.rights_packet.is_none() && !self.acked,
            "one actual original helper rights transfer",
        )?;
        loop {
            self.before()?;
            if let Some((p, n)) = self.receive()? {
                if p.errno != 0 {
                    self.reply = Some(p);
                    return Err(io::Error::from_raw_os_error(p.errno).into());
                }
                // The three FDs already belong to this struct before any later check.
                self.rights_packet = Some(p);
                require(
                    p.magic == REPLY && p.stage == 7 && n == 3 && self.rights.len() == 3,
                    "exact original three-socket transfer",
                )?;
                self.peer_live()?;
                return Ok(());
            }
            self.poll()?;
        }
    }
    fn ack(&mut self) -> Result<()> {
        require(
            self.rights_packet.is_some() && self.rights.len() == 3 && !self.acked,
            "retained original socket rights before ACK",
        )?;
        self.send_byte(2)?;
        self.acked = true;
        Ok(())
    }
    fn reap(&mut self) -> Result<bool> {
        self.same_creator()?;
        if self.exit.is_some() {
            require(
                self.terminal_verified,
                "original socket helper terminal identity was not verified",
            )?;
            return Ok(true);
        }
        let fd = self
            .pidfd
            .as_ref()
            .ok_or(MacError::Rejected("original helper PIDFD custody absent"))?;
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        zero(unsafe {
            libc::waitid(
                libc::P_PIDFD,
                fd.as_raw_fd() as u32,
                &mut info,
                libc::WEXITED | libc::WNOHANG,
            )
        })?;
        let pid = unsafe { info.si_pid() };
        if pid == 0 {
            return Ok(false);
        }
        // waitid has already consumed the real child. Journal it before any
        // later validation so a failed check cannot be hidden by ECHILD.
        self.waited_pid = Some(pid);
        self.exit = Some((info.si_code, unsafe { info.si_status() }));
        require(
            pid == self.pid
                && [libc::CLD_EXITED, libc::CLD_KILLED, libc::CLD_DUMPED].contains(&info.si_code),
            "actual helper waitid original PIDFD identity",
        )?;
        self.terminal_verified = true;
        Ok(true)
    }
    fn complete(&mut self) -> Result<()> {
        require(
            self.acked,
            "selected socket helper must be acknowledged after actual provider proof",
        )?;
        loop {
            self.before()?;
            if self.reply.is_none() {
                if let Some((p, n)) = self.receive()? {
                    require(n == 0, "final helper record cannot add rights")?;
                    self.reply = Some(p);
                }
            }
            if self.reap()? {
                if self.reply.is_none() {
                    if let Some((p, n)) = self.receive()? {
                        require(n == 0, "final helper record cannot add rights")?;
                        self.reply = Some(p);
                    }
                }
                let p = self.reply.ok_or(MacError::Rejected(
                    "actual reaped helper lacks terminal record",
                ))?;
                require(
                    p.magic == REPLY
                        && p.stage == 8
                        && p.errno == 0
                        && self.exit == Some((libc::CLD_EXITED, 0)),
                    "selected socket helper final record and actual exit disagree",
                )?;
                self.before()?;
                return Ok(());
            }
            self.poll()?;
        }
    }
    fn retire(&mut self) -> Result<()> {
        self.same_creator()?;
        if self.reap()? {
            return Ok(());
        }
        let pidfd = self
            .pidfd
            .as_ref()
            .ok_or(MacError::Rejected(
                "original helper PIDFD unavailable for retirement",
            ))?
            .as_raw_fd();
        let rc = unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                pidfd,
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        };
        if rc != 0 && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH) {
            return Err(io::Error::last_os_error().into());
        }
        let end = *self
            .retirement_end
            .get_or_insert_with(|| Instant::now() + RETIRE_BOUND);
        while !self.reap()? {
            let left = end.saturating_duration_since(Instant::now());
            require(
                !left.is_zero(),
                "selected socket helper retirement unproven; original custody retained",
            )?;
            let mut p = libc::pollfd {
                fd: pidfd,
                events: libc::POLLIN,
                revents: 0,
            };
            let rc = unsafe { libc::poll(&mut p, 1, left.as_millis().clamp(1, 50) as i32) };
            if rc < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
                return Err(io::Error::last_os_error().into());
            }
        }
        Ok(())
    }
}
impl Drop for Helper {
    fn drop(&mut self) {
        if !self.terminal_verified {
            if let Some(fd) = self.pidfd.take() {
                std::mem::forget(fd);
            }
        }
    }
}
fn socket_option(fd: BorrowedFd<'_>, key: i32, expected: i32) -> Result<()> {
    let mut value = 0_i32;
    let mut size = std::mem::size_of_val(&value) as libc::socklen_t;
    zero(unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            key,
            (&mut value as *mut i32).cast(),
            &mut size,
        )
    })?;
    require(
        size as usize == std::mem::size_of_val(&value) && value == expected,
        "selected helper socket option differs",
    )
}
fn socket_cookie(fd: BorrowedFd<'_>) -> Result<u64> {
    let mut value = 0_u64;
    let mut size = std::mem::size_of_val(&value) as libc::socklen_t;
    zero(unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_COOKIE,
            (&mut value as *mut u64).cast(),
            &mut size,
        )
    })?;
    require(
        size as usize == std::mem::size_of_val(&value) && value > 0,
        "selected socket actual kernel cookie",
    )?;
    Ok(value)
}
fn helper_peer(socket: BorrowedFd<'_>, helper: &Helper, role: HostPeerRole) -> Result<()> {
    helper.peer_live()?;
    let mut c: libc::ucred = unsafe { std::mem::zeroed() };
    let mut length = std::mem::size_of_val(&c) as libc::socklen_t;
    zero(unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut c as *mut libc::ucred).cast(),
            &mut length,
        )
    })?;
    require(
        length as usize == std::mem::size_of_val(&c)
            && c.pid == helper.pid
            && c.uid == 0
            && c.gid == 0,
        "actual selected probe peer credentials must be original broker helper",
    )?;
    let mut raw = -1_i32;
    length = std::mem::size_of_val(&raw) as _;
    zero(unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            SO_PEERPIDFD,
            (&mut raw as *mut i32).cast(),
            &mut length,
        )
    })?;
    require(raw >= 0, "selected probe peer PIDFD absent")?;
    let actual = unsafe { OwnedFd::from_raw_fd(raw) };
    require(
        length as usize == std::mem::size_of_val(&raw)
            && descriptor_identity(actual.as_fd())?
                == descriptor_identity(helper.pidfd.as_ref().unwrap().as_fd())?,
        "selected probe peer is not the original atomic helper PIDFD",
    )?;
    let mut info = crate::production_activation_protocol::PidfdInfo::request_exit();
    info.mask = 3;
    zero(unsafe {
        libc::ioctl(
            actual.as_raw_fd(),
            crate::production_activation_protocol::PIDFD_GET_INFO as libc::c_ulong,
            &mut info,
        )
    })?;
    require(
        info.mask & 3 == 3 && info.pid == helper.pid as u32 && info.tgid == helper.pid as u32,
        "selected probe peer PIDFD live process binding",
    )?;
    require(
        context_matches(&actual_socket_security(socket)?, role.context()),
        "actual selected socket SO_PEERSEC is not broker SELinux",
    )?;
    helper.peer_live()
}

const NS_NAMES: [(&CStr, i32); 10] = [
    (c"user", libc::CLONE_NEWUSER),
    (c"net", libc::CLONE_NEWNET),
    (c"mnt", libc::CLONE_NEWNS),
    (c"pid", libc::CLONE_NEWPID),
    (c"pid_for_children", libc::CLONE_NEWPID),
    (c"ipc", libc::CLONE_NEWIPC),
    (c"uts", libc::CLONE_NEWUTS),
    (c"cgroup", libc::CLONE_NEWCGROUP),
    (c"time", 0x80),
    (c"time_for_children", 0x80),
];

fn deadline(end: Instant) -> Result<()> {
    require(
        Instant::now() < end,
        "original host selected socket creation deadline",
    )
}
fn process_record(proc: &File, name: &CStr) -> Result<Vec<u8>> {
    require(
        kind(proc)? == PROC_MAGIC,
        "socket helper requires its original procfs directory",
    )?;
    let file = open_at(proc.as_raw_fd(), name, libc::O_RDONLY)?;
    require(
        kind(&file)? == PROC_MAGIC,
        "socket helper record must remain procfs",
    )?;
    bounded(&file, 65536)
}
fn status_values(raw: &[u8], key: &[u8]) -> Result<Vec<Vec<u8>>> {
    require(
        !raw.is_empty() && raw.len() <= 65536 && raw.ends_with(b"\n"),
        "complete socket helper status",
    )?;
    let mut rows = raw
        .split(|v| *v == b'\n')
        .filter_map(|v| v.strip_prefix(key));
    let row = rows
        .next()
        .ok_or(MacError::Rejected("missing socket helper status field"))?;
    require(
        rows.next().is_none(),
        "duplicate socket helper status field",
    )?;
    Ok(row
        .split(|b| b.is_ascii_whitespace())
        .filter(|p| !p.is_empty())
        .map(|p| p.to_vec())
        .collect())
}
fn integer(raw: &[u8]) -> Result<u64> {
    require(
        !raw.is_empty()
            && raw.len() <= 20
            && raw.iter().all(u8::is_ascii_digit)
            && (raw.len() == 1 || raw[0] != b'0'),
        "canonical original socket helper integer",
    )?;
    std::str::from_utf8(raw)
        .map_err(|_| MacError::Rejected("helper proc integer encoding"))?
        .parse()
        .map_err(|_| MacError::Rejected("helper proc integer overflow"))
}
fn status_integer(raw: &[u8], key: &[u8]) -> Result<u64> {
    let v = status_values(raw, key)?;
    require(v.len() == 1, "one socket helper status integer")?;
    integer(&v[0])
}
fn security_state(proc: &File) -> Result<Vec<Vec<Vec<u8>>>> {
    let raw = process_record(proc, c"status")?;
    [
        b"Uid:".as_slice(),
        b"Gid:",
        b"CapInh:",
        b"CapPrm:",
        b"CapEff:",
        b"CapBnd:",
        b"CapAmb:",
        b"NoNewPrivs:",
        b"Seccomp:",
    ]
    .into_iter()
    .map(|key| status_values(&raw, key))
    .collect()
}
fn task_namespaces(proc: &File) -> Result<Vec<(File, NamespaceIdentity)>> {
    let dir = open_at(proc.as_raw_fd(), c"ns", libc::O_PATH | libc::O_DIRECTORY)?;
    require(
        kind(&dir)? == PROC_MAGIC,
        "original socket helper namespace directory",
    )?;
    let mut result = Vec::new();
    for (name, expected) in NS_NAMES {
        // Only these fixed links beneath the held original task are followed.
        let raw = unsafe {
            libc::openat(
                dir.as_raw_fd(),
                name.as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC,
            )
        };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let file = unsafe { File::from_raw_fd(raw) };
        let id = namespace(&file, expected)?;
        result.push((file, id));
    }
    Ok(result)
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct SocketProcessIdentity {
    pid: u32,
    parent: u32,
    start: u64,
    proc_node: Node,
}
fn process_identity(proc: &File, helper: &Helper) -> Result<SocketProcessIdentity> {
    helper.peer_live()?;
    let pidfd = helper
        .pidfd
        .as_ref()
        .ok_or(MacError::Rejected("original helper PIDFD absent"))?;
    let mut info = crate::production_activation_protocol::PidfdInfo::request_exit();
    info.mask = 3;
    zero(unsafe {
        libc::ioctl(
            pidfd.as_raw_fd(),
            crate::production_activation_protocol::PIDFD_GET_INFO as libc::c_ulong,
            &mut info,
        )
    })?;
    require(
        info.mask & 3 == 3
            && info.mask & !7 == 0
            && info.pid == helper.pid as u32
            && info.tgid == info.pid
            && info.ppid == helper.parent as u32
            && [
                info.ruid, info.euid, info.suid, info.fsuid, info.rgid, info.egid, info.sgid,
                info.fsgid,
            ] == [0; 8]
            && info.exit_code == 0
            && info.coredump_mask == 0
            && info.coredump_signal == 0,
        "actual original socket helper PIDFD/physical root credentials",
    )?;
    let node = Node::of(proc)?;
    require(
        node.mode & libc::S_IFMT == libc::S_IFDIR && kind(proc)? == PROC_MAGIC,
        "original socket helper held task directory",
    )?;
    let raw = process_record(proc, c"stat")?;
    require(raw.ends_with(b"\n"), "complete socket helper stat")?;
    let begin = raw
        .windows(2)
        .position(|v| v == b" (")
        .ok_or(MacError::Rejected("socket helper stat command start"))?;
    let end = raw
        .iter()
        .rposition(|v| *v == b')')
        .ok_or(MacError::Rejected("socket helper stat command end"))?;
    require(
        end > begin + 1 && raw.get(end + 1) == Some(&b' '),
        "socket helper stat delimiters",
    )?;
    let fields: Vec<_> = raw[end + 2..raw.len() - 1]
        .split(|v| v.is_ascii_whitespace())
        .filter(|p| !p.is_empty())
        .collect();
    require(
        (50..=64).contains(&fields.len())
            && fields[0].len() == 1
            && b"RSDTtWIP".contains(&fields[0][0]),
        "complete live socket helper stat fields",
    )?;
    let pid = integer(&raw[..begin])?;
    let parent = integer(fields[1])?;
    let start = integer(fields[19])?;
    let status = process_record(proc, c"status")?;
    require(
        pid == helper.pid as u64
            && parent == helper.parent as u64
            && start > 0
            && status_integer(&status, b"Pid:")? == pid
            && status_integer(&status, b"Tgid:")? == pid
            && status_integer(&status, b"PPid:")? == parent
            && status_integer(&status, b"Threads:")? == 1,
        "original single socket helper process identity",
    )?;
    let task = open_at(proc.as_raw_fd(), c"task", libc::O_PATH | libc::O_DIRECTORY)?;
    let name = CString::new(pid.to_string()).map_err(|_| MacError::Rejected("helper task name"))?;
    let thread = open_at(task.as_raw_fd(), &name, libc::O_RDONLY | libc::O_DIRECTORY)?;
    require(
        process_record(&thread, c"children")?.is_empty(),
        "socket helper created a descendant",
    )?;
    require(Node::of(proc)? == node, "socket helper proc inode changed")?;
    helper.peer_live()?;
    Ok(SocketProcessIdentity {
        pid: pid as u32,
        parent: parent as u32,
        start,
        proc_node: node,
    })
}
impl Helper {
    fn capture_process(&mut self) -> Result<()> {
        require(
            self.process.is_none()
                && self.process_identity.is_none()
                && self.rights_packet.is_some()
                && !self.acked,
            "capture the original live helper only once after its actual socket transfer",
        )?;
        self.peer_live()?;
        let name = format!("/proc/{}", self.pid);
        self.process = Some(open_absolute(&name, libc::O_RDONLY | libc::O_DIRECTORY)?);
        let observed = process_identity(self.process.as_ref().unwrap(), self)?;
        self.process_identity = Some(observed);
        self.peer_live()
    }
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) struct HostPeerSocketBinding {
    provider: ProviderBinding,
    pair: HostPeerPair,
    network: HostPeerNetworkBinding,
    original_pidfd: DescriptorIdentity,
    process: SocketProcessIdentity,
    selected_net: NamespaceIdentity,
    original_user: NamespaceIdentity,
}
pub(super) struct HostPeerSocketObservation<'a> {
    pending: &'a Pending,
}
impl HostPeerSocketObservation<'_> {
    pub(super) fn revalidate(&self, authority: &HostPeerAuthority<'_>) -> Result<()> {
        let p = self.pending;
        authority.revalidate()?;
        require(
            authority.pair() == p.pair && authority.provider() == p.provider,
            "socket helper belongs to another original issuer",
        )?;
        let h = p
            .helper
            .as_ref()
            .ok_or(MacError::Rejected("original socket helper absent"))?;
        let proc = h
            .process
            .as_ref()
            .ok_or(MacError::Rejected("original socket helper proc absent"))?;
        require(
            Some(process_identity(proc, h)?) == h.process_identity,
            "original socket helper process changed",
        )?;
        let observed = task_namespaces(proc)?;
        require(
            observed.len() == p.creator_namespaces.len(),
            "complete helper namespaces",
        )?;
        for (i, ((_, actual), (_, original))) in
            observed.iter().zip(&p.creator_namespaces).enumerate()
        {
            let expected = if i == 1 {
                p.network_id
                    .ok_or(MacError::Rejected("selected net identity absent"))?
            } else {
                *original
            };
            require(
                *actual == expected,
                "socket helper changed an original namespace",
            )?;
        }
        require(
            observed[0].1.id == 3 && security_state(proc)? == p.creator_security,
            "socket helper left initial user namespace or original physical credentials/capabilities",
        )?;
        require(
            Some(process_identity(proc, h)?) == h.process_identity,
            "helper process changed across actual namespace observations",
        )?;
        authority.revalidate()
    }
    pub(super) fn proc_directory(&self) -> Result<&File> {
        self.pending
            .helper
            .as_ref()
            .and_then(|h| h.process.as_ref())
            .ok_or(MacError::Rejected("original socket helper proc absent"))
    }
    pub(super) fn pidfd(&self) -> Result<BorrowedFd<'_>> {
        Ok(self
            .pending
            .helper
            .as_ref()
            .and_then(|h| h.pidfd.as_ref())
            .ok_or(MacError::Rejected("original socket helper PIDFD absent"))?
            .as_fd())
    }
    pub(super) fn network_binding(&self) -> Result<HostPeerNetworkBinding> {
        self.pending
            .network_binding
            .ok_or(MacError::Rejected("original socket network binding absent"))
    }
    pub(super) fn binding(&self) -> Result<HostPeerSocketBinding> {
        let p = self.pending;
        let h = p
            .helper
            .as_ref()
            .ok_or(MacError::Rejected("original socket helper absent"))?;
        Ok(HostPeerSocketBinding {
            provider: p.provider,
            pair: p.pair,
            network: self.network_binding()?,
            original_pidfd: descriptor_identity(self.pidfd()?)?,
            process: h
                .process_identity
                .ok_or(MacError::Rejected("helper process binding absent"))?,
            selected_net: p
                .network_id
                .ok_or(MacError::Rejected("selected net absent"))?,
            original_user: p.creator_namespaces[0].1,
        })
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Purpose {
    Manager,
    Package,
    Listener,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Stage {
    Prepared,
    Creating,
    Unbound,
    Connecting,
    Connected,
    Binding,
    Listening,
    Retiring,
    Retired,
}

struct Pending {
    // This is a retained original Rc issuer, never a reconstructed policy tuple.
    issuer: HostPeerIssuer,
    provider: ProviderBinding,
    pair: HostPeerPair,
    purpose: Purpose,
    end: Instant,
    creator_namespaces: Vec<(File, NamespaceIdentity)>,
    creator_security: Vec<Vec<Vec<u8>>>,
    network: HostPeerNetworkOwner,
    network_binding: Option<HostPeerNetworkBinding>,
    network_id: Option<NamespaceIdentity>,
    control: Option<PrivateHostPeerControl>,
    helper: Option<Helper>,
    nodes: Option<[DescriptorIdentity; 3]>,
    cookies: Option<[u64; 3]>,
    stream: Option<UnixStream>,
    listener: Option<UnixListener>,
    duplicate: Option<File>,
    stage: Stage,
}
impl Pending {
    fn original(&self) -> Result<HostPeerAuthority<'_>> {
        let authority = self.issuer.authority()?;
        require(
            authority.pair() == self.pair && authority.provider() == self.provider,
            "selected host socket lost its exact original issuer pair",
        )?;
        let current = task_namespaces(&authority.loaded().own_proc)?;
        require(
            current.len() == self.creator_namespaces.len()
                && current
                    .iter()
                    .zip(&self.creator_namespaces)
                    .all(|(a, b)| a.1 == b.1)
                && current[0].1.id == 3
                && security_state(&authority.loaded().own_proc)? == self.creator_security,
            "selected host socket creator changed its original namespaces or security state",
        )?;
        authority.revalidate()?;
        Ok(authority)
    }
    fn used(&self, authority: &HostPeerAuthority<'_>) -> Result<()> {
        require(
            Some(self.network.binding(authority)?) == self.network_binding
                && Some(self.network.network(authority)?.1) == self.network_id,
            "selected socket moved to a different original network owner",
        )?;
        let control = self.control.as_ref().ok_or(MacError::Rejected(
            "original selected control custody absent",
        ))?;
        require(
            control.set_outcome() == SetOutcome::Applied
                && control.get(authority, &self.network)?
                    == (SelectorState {
                        lsm_id: 101,
                        flags: 3,
                    }),
            "original selected netns must retain SELinux FIXED and actual USED state",
        )
    }
    fn main(&self) -> Result<BorrowedFd<'_>> {
        if let Some(stream) = &self.stream {
            return Ok(stream.as_fd());
        }
        if let Some(listener) = &self.listener {
            return Ok(listener.as_fd());
        }
        Err(MacError::Rejected("original selected main socket absent"))
    }
    fn revalidate(&self) -> Result<()> {
        require(
            matches!(
                self.stage,
                Stage::Unbound | Stage::Connected | Stage::Listening
            ),
            "selected socket is not in an issued stage",
        )?;
        let authority = self.original()?;
        self.used(&authority)?;
        let helper = self
            .helper
            .as_ref()
            .ok_or(MacError::Rejected("original socket creator absent"))?;
        helper.same_creator()?;
        require(
            helper.terminal_verified
                && helper.waited_pid == Some(helper.pid)
                && helper.exit == Some((libc::CLD_EXITED, 0))
                && helper.acked
                && helper.rights.len() == 2,
            "selected socket creator has not actually delivered and exited",
        )?;
        let nodes = self
            .nodes
            .ok_or(MacError::Rejected("original socket node bindings absent"))?;
        let cookies = self
            .cookies
            .ok_or(MacError::Rejected("original socket cookies absent"))?;
        for i in 0..2 {
            socket_identity(helper.rights[i].as_fd(), nodes[i], cookies[i], true, false)?;
            require(
                context_matches(
                    &actual_socket_security(helper.rights[i].as_fd())?,
                    authority.context(),
                ),
                "selected socket's actual provider probe peer changed",
            )?;
        }
        let nonblocking = self.purpose != Purpose::Package || self.stage != Stage::Connected;
        socket_identity(
            self.main()?,
            nodes[2],
            cookies[2],
            nonblocking,
            self.stage == Stage::Listening,
        )?;
        let duplicate = self
            .duplicate
            .as_ref()
            .ok_or(MacError::Rejected("original socket duplicate absent"))?;
        socket_identity(
            duplicate.as_fd(),
            nodes[2],
            cookies[2],
            nonblocking,
            self.stage == Stage::Listening,
        )?;
        self.used(&authority)?;
        authority.revalidate()
    }
    fn retire(&mut self) -> Result<()> {
        if self.stage == Stage::Retired {
            return Ok(());
        }
        self.stage = Stage::Retiring;
        // No loaded-policy re-acquisition or new privileged operation on failure.
        // Finish the original helper before closing either data or control FDs.
        if let Some(helper) = &mut self.helper {
            helper.retire()?;
        }
        self.duplicate.take();
        self.stream.take();
        self.listener.take();
        if let Some(helper) = &mut self.helper {
            helper.rights.clear();
        }
        if let Some(control) = &mut self.control {
            control.retire()?;
        }
        self.control.take();
        self.network.retire_owned()?;
        self.helper.take();
        self.creator_namespaces.clear();
        self.stage = Stage::Retired;
        Ok(())
    }
}
struct StreamCore {
    pending: Option<Pending>,
}
impl std::fmt::Debug for StreamCore {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("OriginalSelectedHostSocket")
            .field("stage", &self.pending.as_ref().map(|p| p.stage))
            .finish_non_exhaustive()
    }
}
impl StreamCore {
    fn prepare(issuer: HostPeerIssuer, purpose: Purpose, end: Instant) -> Result<Self> {
        deadline(end)?;
        let end = end.min(Instant::now() + CREATE_BOUND);
        let authority = issuer.authority()?;
        if purpose == Purpose::Listener {
            authority.require_runtime_broker()?;
        }
        if purpose == Purpose::Package {
            require(
                authority.role() == HostPeerRole::Helper,
                "package client requires its original helper preparation issuer",
            )?;
        }
        let provider = authority.provider();
        let pair = authority.pair();
        let creator_namespaces = task_namespaces(&authority.loaded().own_proc)?;
        require(
            creator_namespaces.len() == NS_NAMES.len() && creator_namespaces[0].1.id == 3,
            "initial-userns original socket creator",
        )?;
        let creator_security = security_state(&authority.loaded().own_proc)?;
        let network = HostPeerNetworkOwner::prepare(&authority, end)?;
        authority.revalidate()?;
        deadline(end)?;
        // Preparation is read-only. The caller must store this value before
        // create_unbound performs its first mutation or clone.
        Ok(Self {
            pending: Some(Pending {
                issuer,
                provider,
                pair,
                purpose,
                end,
                creator_namespaces,
                creator_security,
                network,
                network_binding: None,
                network_id: None,
                control: None,
                helper: None,
                nodes: None,
                cookies: None,
                stream: None,
                listener: None,
                duplicate: None,
                stage: Stage::Prepared,
            }),
        })
    }
    fn pending(&self) -> Result<&Pending> {
        self.pending
            .as_ref()
            .ok_or(MacError::Rejected("selected socket already retired"))
    }
    fn pending_mut(&mut self) -> Result<&mut Pending> {
        self.pending
            .as_mut()
            .ok_or(MacError::Rejected("selected socket already retired"))
    }
    fn create_unbound(&mut self) -> Result<()> {
        let p = self.pending_mut()?;
        require(
            p.stage == Stage::Prepared,
            "selected host socket creation cannot be replayed",
        )?;
        p.original()?;
        deadline(p.end)?;
        p.stage = Stage::Creating;
        let a = p.issuer.authority()?;
        p.network.create(&a)?;
        deadline(p.end)?;
        p.network_binding = Some(p.network.binding(&a)?);
        p.network_id = Some(p.network.network(&a)?.1);
        p.control = Some(PrivateHostPeerControl::prepare(&a, &p.network)?);
        deadline(p.end)?;
        p.control.as_mut().unwrap().create(&a, &p.network)?;
        deadline(p.end)?;
        require(
            p.control.as_ref().unwrap().get(&a, &p.network)?
                == (SelectorState {
                    lsm_id: 0,
                    flags: 0,
                }),
            "fresh host netns selector was already chosen or used",
        )?;
        deadline(p.end)?;
        p.control.as_mut().unwrap().set(&a, &p.network)?;
        deadline(p.end)?;
        require(
            p.control.as_ref().unwrap().get(&a, &p.network)?
                == (SelectorState {
                    lsm_id: 101,
                    flags: 1,
                }),
            "fixed original SELinux choice must precede all new-netns sockets",
        )?;
        deadline(p.end)?;
        let (network, network_id) = p.network.network(&a)?;
        p.helper = Some(Helper::spawn(
            network,
            network_id.into(),
            p.creator_namespaces[0].1.into(),
            a.role(),
            p.end,
        )?);
        // Parent owns the original PIDFD before the helper can leave READY.
        p.helper.as_mut().unwrap().start()?;
        p.helper.as_mut().unwrap().receive_rights()?;
        p.helper.as_mut().unwrap().capture_process()?;
        let helper = p.helper.as_ref().unwrap();
        let mut nodes = [descriptor_identity(helper.rights[0].as_fd())?; 3];
        let mut cookies = [0; 3];
        for i in 0..3 {
            nodes[i] = descriptor_identity(helper.rights[i].as_fd())?;
            cookies[i] = socket_cookie(helper.rights[i].as_fd())?;
            socket_identity(helper.rights[i].as_fd(), nodes[i], cookies[i], true, false)?;
        }
        require(
            nodes[0] != nodes[1]
                && nodes[0] != nodes[2]
                && nodes[1] != nodes[2]
                && cookies[0] != cookies[1]
                && cookies[0] != cookies[2]
                && cookies[1] != cookies[2],
            "three separate actual selected host sockets",
        )?;
        helper_peer(helper.rights[0].as_fd(), helper, a.role())?;
        helper_peer(helper.rights[1].as_fd(), helper, a.role())?;
        p.nodes = Some(nodes);
        p.cookies = Some(cookies);
        let observation = HostPeerSocketObservation { pending: p };
        // Foreign actual process MAC is checked while this original helper is
        // still alive. Own xattrs or matching role strings cannot replace it.
        p.network.verify_socket(&a, &observation)?;
        p.used(&a)?;
        deadline(p.end)?;
        p.helper.as_mut().unwrap().ack()?;
        p.helper.as_mut().unwrap().complete()?;
        p.used(&a)?;
        p.helper.as_ref().unwrap().before()?;
        let main = p
            .helper
            .as_mut()
            .unwrap()
            .rights
            .pop()
            .ok_or(MacError::Rejected("original third selected socket absent"))?;
        p.stream = Some(UnixStream::from(main));
        // A real dup of the same open file description, never a cast or a new
        // connection. All copies close before selector or namespace custody.
        p.duplicate = Some(File::from(
            p.stream.as_ref().unwrap().as_fd().try_clone_to_owned()?,
        ));
        deadline(p.end)?;
        p.stage = Stage::Unbound;
        p.revalidate()?;
        deadline(p.end)
    }
    fn revalidate(&self) -> Result<()> {
        self.pending()?.revalidate()
    }
    fn retire(&mut self) -> Result<()> {
        if let Some(p) = &mut self.pending {
            p.retire()?;
        }
        self.pending.take();
        Ok(())
    }
}
impl Drop for StreamCore {
    fn drop(&mut self) {
        if self.retire().is_err() {
            // A failed original kill/reap/retirement retains all remaining
            // ownership. It is not silently converted into successful cleanup.
            if let Some(p) = self.pending.take() {
                std::mem::forget(p);
            }
        }
    }
}
fn socket_identity(
    fd: BorrowedFd<'_>,
    node: DescriptorIdentity,
    cookie: u64,
    nonblocking: bool,
    listening: bool,
) -> Result<()> {
    require(
        node.kind == libc::S_IFSOCK
            && descriptor_identity(fd)? == node
            && socket_cookie(fd)? == cookie,
        "actual selected socket descriptor or cookie changed",
    )?;
    for (key, value) in [
        (libc::SO_DOMAIN, libc::AF_UNIX),
        (libc::SO_TYPE, libc::SOCK_STREAM),
        (libc::SO_PROTOCOL, 0),
        (libc::SO_ACCEPTCONN, i32::from(listening)),
    ] {
        socket_option(fd, key, value)?;
    }
    let flags = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFL) };
    let close = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFD) };
    if flags < 0 || close < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        close == libc::FD_CLOEXEC
            && flags & libc::O_ACCMODE == libc::O_RDWR
            && (flags & libc::O_NONBLOCK != 0) == nonblocking
            && flags & !(libc::O_RDWR | libc::O_NONBLOCK | libc::O_LARGEFILE) == 0,
        "actual socket flags disagree with its fixed transport purpose",
    )
}
fn address(alias: &str) -> Result<(libc::sockaddr_un, libc::socklen_t)> {
    let mut a: libc::sockaddr_un = unsafe { std::mem::zeroed() };
    require(
        !alias.is_empty()
            && alias.len() < a.sun_path.len()
            && alias.as_bytes().iter().all(|b| *b != 0),
        "bounded internal socket alias",
    )?;
    a.sun_family = libc::AF_UNIX as _;
    for (out, b) in a.sun_path.iter_mut().zip(alias.bytes()) {
        *out = b as libc::c_char;
    }
    Ok((
        a,
        (std::mem::size_of::<libc::sa_family_t>() + alias.len() + 1) as _,
    ))
}
fn connect_original(fd: BorrowedFd<'_>, server: &File, end: Instant) -> Result<()> {
    let (a, n) = address(&format!("/proc/self/fd/{}", server.as_raw_fd()))?;
    deadline(end)?;
    if unsafe { libc::connect(fd.as_raw_fd(), (&a as *const libc::sockaddr_un).cast(), n) } != 0 {
        let error = io::Error::last_os_error();
        if error.raw_os_error() != Some(libc::EINPROGRESS) {
            return Err(error.into());
        }
        loop {
            deadline(end)?;
            let mut event = libc::pollfd {
                fd: fd.as_raw_fd(),
                events: libc::POLLOUT,
                revents: 0,
            };
            let wait = end
                .saturating_duration_since(Instant::now())
                .as_millis()
                .clamp(1, 50) as i32;
            let rc = unsafe { libc::poll(&mut event, 1, wait) };
            if rc < 0 {
                let e = io::Error::last_os_error();
                if e.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(e.into());
            }
            deadline(end)?;
            if rc == 0 {
                continue;
            }
            socket_option(fd, libc::SO_ERROR, 0)?;
            require(
                event.revents & libc::POLLOUT != 0
                    && event.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) == 0,
                "original-parent socket connect did not complete",
            )?;
            break;
        }
    }
    deadline(end)
}
fn held_label(file: &File) -> Result<Vec<u8>> {
    let before = Node::of(file)?;
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    if flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        flags & libc::O_PATH != 0,
        "actual held named socket must be O_PATH",
    )?;
    let alias = CString::new(format!("/proc/self/fd/{}", file.as_raw_fd()))
        .map_err(|_| MacError::Rejected("invalid internal held-inode alias"))?;
    let mut bytes = [0_u8; 1024];
    let n = unsafe {
        libc::getxattr(
            alias.as_ptr(),
            c"security.selinux".as_ptr(),
            bytes.as_mut_ptr().cast(),
            bytes.len(),
        )
    };
    if n < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        n > 0 && n as usize <= bytes.len() && Node::of(file)? == before,
        "actual bounded held-inode SELinux label",
    )?;
    Ok(bytes[..n as usize].to_vec())
}
fn object_context(raw: &[u8]) -> Result<&str> {
    let raw = raw.strip_suffix(&[0]).unwrap_or(raw);
    let raw = raw.strip_suffix(b"\n").unwrap_or(raw);
    let value =
        std::str::from_utf8(raw).map_err(|_| MacError::Rejected("SELinux context encoding"))?;
    require(
        !value.is_empty()
            && value.len() <= 512
            && value.starts_with("u:object_r:")
            && value
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"_:,.-".contains(&b)),
        "actual fixed host inode SELinux context",
    )?;
    Ok(value)
}
fn named_socket(file: &File, expected: Node) -> Result<Vec<u8>> {
    require(
        Node::of(file)? == expected
            && expected.mode & libc::S_IFMT == libc::S_IFSOCK
            && expected.uid == 0
            && expected.gid == 0
            && expected.links == 1,
        "held original root socket inode changed",
    )?;
    let label = held_label(file)?;
    object_context(&label)?;
    require(
        Node::of(file)? == expected,
        "named host socket changed across label read",
    )?;
    Ok(label)
}
fn connection_decisions(a: &HostPeerAuthority<'_>, server_label: &[u8], peer: &str) -> Result<()> {
    a.revalidate()?;
    let mut sequence = Some(a.loaded().av_sequence);
    access(
        &a.loaded().root,
        a.context(),
        a.context(),
        "unix_stream_socket",
        &[
            "create", "connect", "getattr", "read", "write", "getopt", "setopt",
        ],
        true,
        &mut sequence,
    )?;
    access(
        &a.loaded().root,
        a.context(),
        peer,
        "unix_stream_socket",
        &["connectto"],
        true,
        &mut sequence,
    )?;
    access(
        &a.loaded().root,
        a.context(),
        object_context(server_label)?,
        "sock_file",
        &["write"],
        true,
        &mut sequence,
    )?;
    a.revalidate()
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Credentials {
    pid: i32,
    uid: u32,
    gid: u32,
}
struct ConnectedPeer {
    credentials: Credentials,
    pidfd: File,
    identity: DescriptorIdentity,
    context: Vec<u8>,
}
fn peer_pidfd(fd: BorrowedFd<'_>) -> Result<File> {
    let mut raw = -1_i32;
    let mut size = std::mem::size_of_val(&raw) as libc::socklen_t;
    zero(unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            SO_PEERPIDFD,
            (&mut raw as *mut i32).cast(),
            &mut size,
        )
    })?;
    require(raw >= 0, "actual connected peer PIDFD absent")?;
    let result = unsafe { File::from_raw_fd(raw) };
    let flags = unsafe { libc::fcntl(raw, libc::F_GETFD) };
    require(
        size as usize == std::mem::size_of_val(&raw) && flags == libc::FD_CLOEXEC,
        "actual connected peer PIDFD size/flags",
    )?;
    Ok(result)
}
fn peer_credentials(fd: BorrowedFd<'_>) -> Result<Credentials> {
    let mut c: libc::ucred = unsafe { std::mem::zeroed() };
    let mut n = std::mem::size_of_val(&c) as libc::socklen_t;
    zero(unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut c as *mut libc::ucred).cast(),
            &mut n,
        )
    })?;
    require(
        n as usize == std::mem::size_of_val(&c) && c.pid > 0,
        "actual connected socket peer credentials",
    )?;
    Ok(Credentials {
        pid: c.pid,
        uid: c.uid,
        gid: c.gid,
    })
}
impl ConnectedPeer {
    fn capture(fd: BorrowedFd<'_>) -> Result<Self> {
        let credentials = peer_credentials(fd)?;
        let pidfd = peer_pidfd(fd)?;
        let identity = descriptor_identity(pidfd.as_fd())?;
        let context = actual_socket_security(fd)?;
        // Require an actual SELinux peer result. This value is not inferred
        // from the helper's own typed CURRENT or any local inode xattr.
        let text = context.strip_suffix(&[0]).unwrap_or(&context);
        let text = std::str::from_utf8(text)
            .map_err(|_| MacError::Rejected("actual peer security encoding"))?;
        require(
            text.starts_with("u:r:")
                && text.len() <= 512
                && text
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"_:,.-".contains(&b)),
            "selected socket returned no actual SELinux peer context",
        )?;
        let value = Self {
            credentials,
            pidfd,
            identity,
            context,
        };
        value.revalidate(fd)?;
        Ok(value)
    }
    fn revalidate(&self, fd: BorrowedFd<'_>) -> Result<()> {
        let original = descriptor_identity(self.pidfd.as_fd())?;
        require(
            original == self.identity && kind(&self.pidfd)? == 0x5049_4446,
            "original connected peer PIDFD identity changed",
        )?;
        require(
            unsafe { alive_raw(self.pidfd.as_raw_fd()) },
            "original connected peer is no longer live",
        )?;
        let now = peer_pidfd(fd)?;
        require(
            descriptor_identity(now.as_fd())? == self.identity
                && peer_credentials(fd)? == self.credentials
                && actual_socket_security(fd)? == self.context,
            "connected socket no longer names its original actual peer",
        )?;
        let mut info = crate::production_activation_protocol::PidfdInfo::request_exit();
        info.mask = 3;
        zero(unsafe {
            libc::ioctl(
                self.pidfd.as_raw_fd(),
                crate::production_activation_protocol::PIDFD_GET_INFO as libc::c_ulong,
                &mut info,
            )
        })?;
        require(
            info.mask & 3 == 3
                && info.pid == self.credentials.pid as u32
                && info.tgid == info.pid
                && info.euid == self.credentials.uid
                && info.egid == self.credentials.gid
                && info.exit_code == 0
                && info.coredump_mask == 0
                && info.coredump_signal == 0
                && unsafe { alive_raw(self.pidfd.as_raw_fd()) },
            "original connected peer live identity",
        )?;
        Ok(())
    }
}

fn same_inode(a: Node, b: Node) -> bool {
    a.dev == b.dev && a.ino == b.ino && a.mode == b.mode && a.uid == b.uid && a.gid == b.gid
}
fn trusted_directory(file: &File) -> Result<Node> {
    let node = Node::of(file)?;
    require(
        node.mode & libc::S_IFMT == libc::S_IFDIR
            && node.uid == 0
            && node.gid == 0
            && node.mode & 0o6022 == 0
            && node.links >= 2,
        "fixed root-controlled host directory",
    )?;
    Ok(node)
}
fn fixed_parent(purpose: Purpose) -> Result<File> {
    let mut dir = open_absolute("/", libc::O_PATH | libc::O_DIRECTORY)?;
    trusted_directory(&dir)?;
    for name in [
        c"run",
        if purpose == Purpose::Manager {
            c"systemd"
        } else {
            c"droidloom"
        },
    ] {
        dir = open_at(dir.as_raw_fd(), name, libc::O_PATH | libc::O_DIRECTORY)?;
        trusted_directory(&dir)?;
    }
    Ok(dir)
}
fn fixed_server(purpose: Purpose, held: &File, expected: Node) -> Result<()> {
    let parent = fixed_parent(purpose)?;
    let name = if purpose == Purpose::Manager {
        c"private"
    } else {
        c"control.sock"
    };
    let named = open_at(parent.as_raw_fd(), name, libc::O_PATH)?;
    require(
        Node::of(&named)? == expected && Node::of(held)? == expected,
        "selected host connection is not the fixed original server inode",
    )?;
    Ok(())
}
struct Connection {
    core: StreamCore,
    server: File,
    server_node: Node,
    initial_label: Vec<u8>,
    peer: Option<ConnectedPeer>,
}
impl Connection {
    fn prepare(
        issuer: HostPeerIssuer,
        server: &File,
        end: Instant,
        purpose: Purpose,
    ) -> Result<Self> {
        require(
            purpose != Purpose::Listener,
            "connection cannot select a listener purpose",
        )?;
        deadline(end)?;
        let node = Node::of(server)?;
        let label = named_socket(server, node)?;
        if purpose == Purpose::Manager {
            require(
                node.mode & 0o022 == 0,
                "manager server inode must remain root-controlled",
            )?;
        } else {
            require(
                node.mode & 0o7777 == 0o666,
                "package control server has its fixed public transport mode",
            )?;
        }
        fixed_server(purpose, server, node)?;
        let a = issuer.authority()?;
        connection_decisions(
            &a,
            &label,
            if purpose == Purpose::Manager {
                HOST
            } else {
                BROKER
            },
        )?;
        let server = server.try_clone()?;
        let core = StreamCore::prepare(issuer, purpose, end)?;
        deadline(end)?;
        Ok(Self {
            core,
            server,
            server_node: node,
            initial_label: label,
            peer: None,
        })
    }
    fn connect(&mut self) -> Result<()> {
        require(
            self.peer.is_none(),
            "original host connection cannot be replayed",
        )?;
        let purpose = self.core.pending()?.purpose;
        let end = self.core.pending()?.end;
        fixed_server(purpose, &self.server, self.server_node)?;
        require(
            named_socket(&self.server, self.server_node)? == self.initial_label,
            "original server label changed before selected socket creation",
        )?;
        self.core.create_unbound()?;
        let p = self.core.pending_mut()?;
        p.revalidate()?;
        let authority = p.issuer.authority()?;
        connection_decisions(
            &authority,
            &self.initial_label,
            if purpose == Purpose::Manager {
                HOST
            } else {
                BROKER
            },
        )?;
        deadline(end)?;
        p.stage = Stage::Connecting; // Journal before the original-parent connect.
        connect_original(p.main()?, &self.server, end)?;
        fixed_server(purpose, &self.server, self.server_node)?;
        require(
            named_socket(&self.server, self.server_node)? == self.initial_label,
            "fixed server inode or label changed during original-parent connect",
        )?;
        self.peer = Some(ConnectedPeer::capture(p.main()?)?);
        let peer = self.peer.as_ref().unwrap();
        let expected = if purpose == Purpose::Manager {
            HOST
        } else {
            BROKER
        };
        require(
            context_matches(&peer.context, expected)
                && peer.credentials.uid == 0
                && peer.credentials.gid == 0
                && (purpose != Purpose::Manager || peer.credentials.pid == 1),
            "selected connection has the wrong actual original host peer",
        )?;
        if purpose == Purpose::Package {
            // The existing package frame protocol is blocking with fixed
            // per-frame SO_RCVTIMEO/SO_SNDTIMEO. No caller chooses these flags.
            p.stream.as_ref().unwrap().set_nonblocking(false)?;
        }
        deadline(end)?;
        p.stage = Stage::Connected;
        self.revalidate()?;
        deadline(end)
    }
    fn revalidate(&self) -> Result<()> {
        let p = self.core.pending()?;
        require(
            p.stage == Stage::Connected,
            "original selected stream is not connected",
        )?;
        p.revalidate()?;
        self.peer
            .as_ref()
            .ok_or(MacError::Rejected("actual connected peer absent"))?
            .revalidate(p.main()?)?;
        if p.purpose == Purpose::Package {
            fixed_server(p.purpose, &self.server, self.server_node)?;
            require(
                named_socket(&self.server, self.server_node)? == self.initial_label,
                "package fixed server inode or label changed",
            )?;
        }
        // The manager endpoint has its own complete held/name/seal witness.
        // Its distinct consumed loader operation may legitimately relabel that
        // server inode; it never changes this connection or its actual peer.
        p.revalidate()
    }
    fn retire(&mut self) -> Result<()> {
        self.core.retire()?;
        self.peer.take();
        Ok(())
    }
}
pub(crate) struct ManagerSelectedStream {
    original: Connection,
}
impl std::fmt::Debug for ManagerSelectedStream {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ManagerSelectedStream")
            .field("core", &self.original.core)
            .finish_non_exhaustive()
    }
}
impl ManagerSelectedStream {
    pub(crate) fn prepare(
        issuer: HostPeerIssuer,
        server: &File,
        deadline: Instant,
    ) -> Result<Self> {
        Ok(Self {
            original: Connection::prepare(issuer, server, deadline, Purpose::Manager)?,
        })
    }
    pub(crate) fn connect(&mut self) -> Result<()> {
        self.original.connect()
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.original.revalidate()
    }
    pub(crate) fn connection(&self) -> Result<&File> {
        self.revalidate()?;
        self.original
            .core
            .pending()?
            .duplicate
            .as_ref()
            .ok_or(MacError::Rejected(
                "original manager socket duplicate absent",
            ))
    }
    pub(crate) fn check_duplicate(&self, file: &File) -> Result<()> {
        self.revalidate()?;
        let p = self.original.core.pending()?;
        socket_identity(
            file.as_fd(),
            p.nodes.unwrap()[2],
            p.cookies.unwrap()[2],
            true,
            false,
        )?;
        self.revalidate()
    }
    pub(crate) fn retire(&mut self) -> Result<()> {
        self.original.retire()
    }
}
pub(crate) struct PackageSelectedStream {
    original: Connection,
}
impl std::fmt::Debug for PackageSelectedStream {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PackageSelectedStream")
            .field("core", &self.original.core)
            .finish_non_exhaustive()
    }
}
impl PackageSelectedStream {
    pub(crate) fn prepare(
        owner: &PackageMacOwner,
        server_node: &File,
        deadline: Instant,
    ) -> Result<Self> {
        owner.revalidate()?;
        require(
            owner.role() == PackageMacRole::Helper && deadline <= owner.deadline(),
            "package stream requires its original helper and original deadline",
        )?;
        let issuer = HostPeerIssuer::package(owner.retain_original()?)?;
        let original = Connection::prepare(issuer, server_node, deadline, Purpose::Package)?;
        owner.revalidate()?;
        Ok(Self { original })
    }
    pub(crate) fn connect(&mut self) -> Result<()> {
        self.original.connect()
    }
    pub(crate) fn stream(&self) -> Result<&UnixStream> {
        self.original.revalidate()?;
        self.original
            .core
            .pending()?
            .stream
            .as_ref()
            .ok_or(MacError::Rejected("original package stream absent"))
    }
    pub(crate) fn stream_mut(&mut self) -> Result<&mut UnixStream> {
        self.original.revalidate()?;
        self.original
            .core
            .pending_mut()?
            .stream
            .as_mut()
            .ok_or(MacError::Rejected("original package stream absent"))
    }
    pub(crate) fn retire(&mut self) -> Result<()> {
        self.original.retire()
    }
}
struct ListenerInode {
    file: File,
    node: Node,
    label: Vec<u8>,
}
fn listener_creation(a: &HostPeerAuthority<'_>, parent: &File) -> Result<Vec<u8>> {
    a.require_runtime_broker()?;
    self_attr::require_no_fscreate()?;
    let label = held_label(parent)?;
    let parent_context = object_context(&label)?;
    a.loaded().stable_epoch()?;
    let number = class_number(&a.loaded().root, "sock_file")?;
    let command = format!("{} {} {} control.sock", BROKER, parent_context, number);
    let actual = transaction(&a.loaded().root, "create", command.as_bytes())?;
    let target = object_context(&actual)?;
    let mut sequence = Some(a.loaded().av_sequence);
    access(
        &a.loaded().root,
        BROKER,
        parent_context,
        "dir",
        &["getattr", "search", "write", "add_name"],
        true,
        &mut sequence,
    )?;
    access(
        &a.loaded().root,
        BROKER,
        target,
        "sock_file",
        &["create", "getattr", "setattr", "write"],
        true,
        &mut sequence,
    )?;
    access(
        &a.loaded().root,
        BROKER,
        BROKER,
        "unix_stream_socket",
        &[
            "create", "bind", "listen", "accept", "getattr", "read", "write", "getopt", "setopt",
        ],
        true,
        &mut sequence,
    )?;
    a.loaded().stable_epoch()?;
    require(
        held_label(parent)? == label,
        "fixed listener parent label changed during named create query",
    )?;
    a.revalidate()?;
    Ok(actual)
}
fn chmod_original(file: &File) -> Result<()> {
    let before = Node::of(file)?;
    let alias = CString::new(format!("/proc/self/fd/{}", file.as_raw_fd()))
        .map_err(|_| MacError::Rejected("fixed listener held inode alias"))?;
    // Resolve only the kernel link for this already-held exact O_PATH inode.
    // Never chmod a caller path or the current directory entry after a race.
    zero(unsafe { libc::chmod(alias.as_ptr(), 0o666) })?;
    let after = Node::of(file)?;
    require(
        before.dev == after.dev
            && before.ino == after.ino
            && before.uid == after.uid
            && before.gid == after.gid
            && after.mode & libc::S_IFMT == libc::S_IFSOCK
            && after.mode & 0o7777 == 0o666,
        "fixed listener mode change targeted a different original inode",
    )
}
pub(crate) struct BrokerSelectedListener {
    core: StreamCore,
    parent: File,
    parent_node: Node,
    expected_label: Vec<u8>,
    bound: bool,
    server: Option<ListenerInode>,
}
impl std::fmt::Debug for BrokerSelectedListener {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("BrokerSelectedListener")
            .field("core", &self.core)
            .field("bound", &self.bound)
            .finish_non_exhaustive()
    }
}
impl BrokerSelectedListener {
    pub(crate) fn prepare(
        issuer: HostPeerIssuer,
        parent: &File,
        deadline: Instant,
    ) -> Result<Self> {
        deadline_check(deadline)?;
        issuer.authority()?.require_runtime_broker()?;
        let original = trusted_directory(parent)?;
        let fixed = fixed_parent(Purpose::Listener)?;
        let parent_node = trusted_directory(&fixed)?;
        require(
            same_inode(original, parent_node),
            "listener parent is not original /run/droidloom",
        )?;
        let expected_label = listener_creation(&issuer.authority()?, &fixed)?;
        let core = StreamCore::prepare(issuer, Purpose::Listener, deadline)?;
        deadline_check(deadline)?;
        Ok(Self {
            core,
            parent: fixed,
            parent_node,
            expected_label,
            bound: false,
            server: None,
        })
    }
    fn parent(&self) -> Result<()> {
        let actual = trusted_directory(&self.parent)?;
        require(
            same_inode(actual, self.parent_node)
                && same_inode(
                    trusted_directory(&fixed_parent(Purpose::Listener)?)?,
                    self.parent_node,
                ),
            "fixed listener original parent changed",
        )
    }
    pub(crate) fn bind_and_listen(&mut self) -> Result<()> {
        require(
            !self.bound && self.server.is_none(),
            "original listener bind cannot be replayed",
        )?;
        self.parent()?;
        let end = self.core.pending()?.end;
        deadline(end)?;
        let mut stat: libc::stat = unsafe { std::mem::zeroed() };
        let absent = unsafe {
            libc::fstatat(
                self.parent.as_raw_fd(),
                c"control.sock".as_ptr(),
                &mut stat,
                libc::AT_SYMLINK_NOFOLLOW,
            )
        };
        require(
            absent < 0 && io::Error::last_os_error().raw_os_error() == Some(libc::ENOENT),
            "fixed control.sock must be absent; no implicit replacement or unlink",
        )?;
        self.core.create_unbound()?;
        self.parent()?;
        let p = self.core.pending_mut()?;
        p.revalidate()?;
        require(
            listener_creation(&p.issuer.authority()?, &self.parent)? == self.expected_label,
            "same-epoch fixed listener create decision changed",
        )?;
        deadline(end)?;
        p.stage = Stage::Binding;
        let (address, n) = address(&format!(
            "/proc/self/fd/{}/control.sock",
            self.parent.as_raw_fd()
        ))?;
        zero(unsafe {
            libc::bind(
                p.main()?.as_raw_fd(),
                (&address as *const libc::sockaddr_un).cast(),
                n,
            )
        })?;
        self.bound = true; // Journal the real filesystem side effect immediately.
        let file = open_at(self.parent.as_raw_fd(), c"control.sock", libc::O_PATH)?;
        let node = Node::of(&file)?;
        // Retain the exact original inode before any label/mode/postcondition.
        self.server = Some(ListenerInode {
            file,
            node,
            label: Vec::new(),
        });
        let server = self.server.as_mut().unwrap();
        let before_label = named_socket(&server.file, server.node)?;
        require(
            context_matches(&before_label, object_context(&self.expected_label)?),
            "actual control socket did not receive the fixed automatic transition",
        )?;
        deadline(end)?;
        chmod_original(&server.file)?;
        server.node = Node::of(&server.file)?;
        server.label = named_socket(&server.file, server.node)?;
        require(
            context_matches(&server.label, object_context(&self.expected_label)?),
            "original control socket label changed across exact chmod",
        )?;
        deadline(end)?;
        zero(unsafe { libc::listen(p.main()?.as_raw_fd(), 128) })?;
        // Conversion preserves the exact same already-bound open description.
        let stream = p
            .stream
            .take()
            .ok_or(MacError::Rejected("original listener socket absent"))?;
        p.listener = Some(unsafe { UnixListener::from_raw_fd(stream.into_raw_fd()) });
        deadline(end)?;
        p.stage = Stage::Listening;
        self.revalidate()?;
        deadline(end)
    }
    fn revalidate(&self) -> Result<()> {
        let p = self.core.pending()?;
        require(
            p.stage == Stage::Listening && self.bound,
            "selected broker listener is not actually listening",
        )?;
        p.revalidate()?;
        p.issuer.authority()?.require_runtime_broker()?;
        self.parent()?;
        let server = self
            .server
            .as_ref()
            .ok_or(MacError::Rejected("held listener inode absent"))?;
        require(
            server.node.mode & 0o7777 == 0o666
                && named_socket(&server.file, server.node)? == server.label
                && context_matches(&server.label, object_context(&self.expected_label)?),
            "actual original listener inode mode or label changed",
        )?;
        let named = open_at(self.parent.as_raw_fd(), c"control.sock", libc::O_PATH)?;
        require(
            Node::of(&named)? == server.node,
            "fixed named control socket changed",
        )?;
        p.revalidate()
    }
    pub(crate) fn server_inode(&self) -> Result<&File> {
        // Also available to the original outer unlink guard after a failed
        // post-bind check. This alone never declares Listening or readiness.
        self.parent()?;
        let server = self.server.as_ref().ok_or(MacError::Rejected(
            "original bound server inode not captured",
        ))?;
        let now = Node::of(&server.file)?;
        require(
            now.dev == server.node.dev
                && now.ino == server.node.ino
                && now.mode & libc::S_IFMT == libc::S_IFSOCK,
            "original bound server inode changed",
        )?;
        Ok(&server.file)
    }
    pub(crate) fn listener(&self) -> Result<&UnixListener> {
        self.revalidate()?;
        self.core
            .pending()?
            .listener
            .as_ref()
            .ok_or(MacError::Rejected("original listener absent"))
    }
    pub(crate) fn accept(&self) -> Result<BrokerAcceptedStream<'_>> {
        self.revalidate()?;
        let raw = unsafe {
            libc::accept4(
                self.listener()?.as_raw_fd(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            )
        };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let stream = unsafe { UnixStream::from_raw_fd(raw) };
        // accept4's temporary nonblocking state is not the existing blocking
        // frame protocol. Fix it before issuing this typed accepted stream.
        stream.set_nonblocking(false)?;
        let node = descriptor_identity(stream.as_fd())?;
        let cookie = socket_cookie(stream.as_fd())?;
        socket_identity(stream.as_fd(), node, cookie, false, false)?;
        let peer = ConnectedPeer::capture(stream.as_fd())?;
        let value = BrokerAcceptedStream {
            listener: self,
            stream,
            node,
            cookie,
            peer,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(crate) fn retire(&mut self) -> Result<()> {
        // Borrowing accepted wrappers makes this exclusive operation impossible
        // while one of our accepted transactions still owns its stream.
        self.core.retire()
        // The outer OwnedListener alone owns exact held-inode unlink.
    }
}
fn deadline_check(end: Instant) -> Result<()> {
    deadline(end)
}

pub(crate) struct BrokerAcceptedStream<'a> {
    listener: &'a BrokerSelectedListener,
    stream: UnixStream,
    node: DescriptorIdentity,
    cookie: u64,
    peer: ConnectedPeer,
}
impl std::fmt::Debug for BrokerAcceptedStream<'_> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("BrokerAcceptedStream")
            .finish_non_exhaustive()
    }
}
impl BrokerAcceptedStream<'_> {
    fn revalidate(&self) -> Result<()> {
        self.listener.revalidate()?;
        socket_identity(self.stream.as_fd(), self.node, self.cookie, false, false)?;
        self.peer.revalidate(self.stream.as_fd())?;
        self.listener.revalidate()
    }
    pub(crate) fn stream(&self) -> Result<&UnixStream> {
        self.revalidate()?;
        Ok(&self.stream)
    }
    pub(crate) fn stream_mut(&mut self) -> Result<&mut UnixStream> {
        self.revalidate()?;
        Ok(&mut self.stream)
    }
}

unsafe fn child_user(expected: ExpectedNamespace) -> bool {
    let raw = unsafe {
        libc::syscall(
            libc::SYS_openat,
            libc::AT_FDCWD,
            c"/proc/thread-self/ns/user".as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
            0,
        )
    };
    if raw < 0 || raw > i32::MAX as i64 {
        return false;
    }
    let matches =
        expected.id == 3 && unsafe { child_namespace(raw as RawFd, expected, libc::CLONE_NEWUSER) };
    let closed = unsafe { libc::syscall(libc::SYS_close, raw) == 0 };
    matches && closed
}
unsafe fn child_apparmor(role: HostPeerRole) -> bool {
    let raw = unsafe {
        libc::syscall(
            libc::SYS_openat,
            libc::AT_FDCWD,
            c"/proc/thread-self/attr/apparmor/current".as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            0,
        )
    };
    if raw < 0 || raw > i32::MAX as i64 {
        return false;
    }
    let mut value = [0_u8; 256];
    let count = unsafe { libc::syscall(libc::SYS_read, raw, value.as_mut_ptr(), value.len()) };
    let closed = unsafe { libc::syscall(libc::SYS_close, raw) == 0 };
    count >= 0
        && count as usize == role.apparmor().len()
        && value[..count as usize] == role.apparmor()[..]
        && closed
}
unsafe fn finish(channel: RawFd, nonce: [u8; 16], stage: u32, errno: i32) -> ! {
    let packet = Packet {
        magic: REPLY,
        stage,
        errno,
        reserved: 0,
        nonce,
    };
    unsafe {
        libc::syscall(
            libc::SYS_sendto,
            channel,
            &packet,
            std::mem::size_of::<Packet>(),
            libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
            std::ptr::null::<libc::sockaddr>(),
            0,
        );
        libc::syscall(libc::SYS_exit_group, if errno == 0 { 0 } else { 125 });
        std::hint::unreachable_unchecked()
    }
}
unsafe fn fail(channel: RawFd, nonce: [u8; 16], stage: u32) -> ! {
    let e = unsafe { *libc::__errno_location() };
    unsafe {
        finish(
            channel,
            nonce,
            stage,
            if (1..=4095).contains(&e) {
                e
            } else {
                libc::EIO
            },
        )
    }
}
unsafe fn child_before(channel: RawFd, creator: RawFd, nonce: [u8; 16], stage: u32, end: u64) {
    if !unsafe { alive_raw(creator) } {
        unsafe { finish(channel, nonce, stage, libc::ESRCH) }
    }
    let mut t: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_clock_gettime, libc::CLOCK_MONOTONIC, &mut t) } != 0 {
        unsafe { fail(channel, nonce, stage) }
    }
    let value = u64::try_from(t.tv_sec)
        .ok()
        .and_then(|s| s.checked_mul(1_000_000_000))
        .and_then(|s| s.checked_add(u64::try_from(t.tv_nsec).ok()?));
    if !(0..1_000_000_000).contains(&t.tv_nsec) || value.is_none_or(|n| n >= end) {
        unsafe { finish(channel, nonce, stage, libc::ETIMEDOUT) }
    }
}
unsafe fn child_barrier(
    channel: RawFd,
    creator: RawFd,
    nonce: [u8; 16],
    stage: u32,
    end: u64,
    expected: u8,
) {
    loop {
        unsafe {
            child_before(channel, creator, nonce, stage, end);
            let mut value = [0_u8; 2];
            let n = libc::syscall(
                libc::SYS_recvfrom,
                channel,
                value.as_mut_ptr(),
                value.len(),
                libc::MSG_DONTWAIT | libc::MSG_TRUNC,
                std::ptr::null::<libc::sockaddr>(),
                std::ptr::null::<libc::socklen_t>(),
            );
            if n == 1 && value[0] == expected {
                return;
            }
            if n >= 0 {
                finish(channel, nonce, stage, libc::EPROTO);
            }
            if *libc::__errno_location() != libc::EAGAIN && *libc::__errno_location() != libc::EINTR
            {
                fail(channel, nonce, stage);
            }
            let mut p = libc::pollfd {
                fd: channel,
                events: libc::POLLIN,
                revents: 0,
            };
            libc::syscall(libc::SYS_poll, &mut p, 1, 20);
        }
    }
}
unsafe fn child_namespace(fd: RawFd, expected: ExpectedNamespace, kind: i32) -> bool {
    let mut m: libc::stat = unsafe { std::mem::zeroed() };
    let mut fs: KernelStatfs = unsafe { std::mem::zeroed() };
    let mut id = 0_u64;
    unsafe {
        libc::syscall(libc::SYS_fstat, fd, &mut m) == 0
            && libc::syscall(libc::SYS_fstatfs, fd, &mut fs) == 0
            && fs.kind == 0x6e73_6673
            && (m.st_dev, m.st_ino, m.st_mode, m.st_uid, m.st_gid)
                == (
                    expected.dev,
                    expected.ino,
                    expected.mode,
                    expected.uid,
                    expected.gid,
                )
            && libc::syscall(libc::SYS_ioctl, fd, 0xb703_u64, 0_u64) == kind as i64
            && libc::syscall(libc::SYS_ioctl, fd, 0x8008_b70d_u64, &mut id) == 0
            && id == expected.id
            && id != 0
    }
}
unsafe fn child_role(role: HostPeerRole) -> bool {
    let mut value = TypedContext {
        id: 101,
        flags: 0,
        len: 0,
        ctx_len: 0,
        ctx: [0; 128],
    };
    let mut size = std::mem::size_of::<TypedContext>() as u32;
    let expected = role.context().as_bytes();
    let context_len = expected.len() + 1;
    let n = unsafe { libc::syscall(459, 100_u32, &mut value, &mut size, 1_u32) };
    let aligned = (32 + context_len + 7) & !7;
    n == 1
        && value.id == 101
        && value.flags == 0
        && value.ctx_len == context_len as u64
        && value.len == aligned as u64
        && size as usize == aligned
        && value.ctx[..expected.len()] == expected[..]
        && value.ctx[expected.len()..aligned - 32]
            .iter()
            .all(|v| *v == 0)
}
unsafe fn child_run(
    network: RawFd,
    expected: ExpectedNamespace,
    expected_user: ExpectedNamespace,
    role: HostPeerRole,
    socket: RawFd,
    creator: RawFd,
    parent: i32,
    nonce: [u8; 16],
    end: u64,
) -> ! {
    unsafe {
        if libc::syscall(
            libc::SYS_prctl,
            libc::PR_SET_PDEATHSIG,
            libc::SIGKILL,
            0,
            0,
            0,
        ) != 0
            || libc::syscall(libc::SYS_getppid) != parent as i64
        {
            fail(socket, nonce, 1);
        }
        if !alive_raw(creator) {
            finish(socket, nonce, 1, libc::ESRCH);
        }
        let mut keep = [-1_i32; 3];
        for (i, fd) in [network, creator, socket].into_iter().enumerate() {
            let n = libc::syscall(libc::SYS_fcntl, fd, libc::F_DUPFD_CLOEXEC, 128);
            if n < 128 || n > i32::MAX as i64 {
                fail(socket, nonce, 2);
            }
            keep[i] = n as i32;
        }
        let network = keep[0];
        let creator = keep[1];
        let channel = keep[2];
        let mut next = 0_u32;
        for fd in keep {
            if next < fd as u32 && libc::syscall(libc::SYS_close_range, next, fd as u32 - 1, 0) != 0
            {
                fail(channel, nonce, 2);
            }
            next = fd as u32 + 1;
        }
        if libc::syscall(libc::SYS_close_range, next, u32::MAX, 0) != 0 {
            fail(channel, nonce, 2);
        }
        child_before(channel, creator, nonce, 3, end);
        let ready = Packet {
            magic: READY,
            stage: 3,
            errno: 0,
            reserved: 0,
            nonce,
        };
        if libc::syscall(
            libc::SYS_sendto,
            channel,
            &ready,
            std::mem::size_of::<Packet>(),
            libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
            std::ptr::null::<libc::sockaddr>(),
            0,
        ) != std::mem::size_of::<Packet>() as i64
        {
            fail(channel, nonce, 3);
        }
        child_barrier(channel, creator, nonce, 3, end, 1);
        if !child_namespace(network, expected, libc::CLONE_NEWNET) {
            finish(channel, nonce, 4, libc::ESTALE);
        }
        if !child_role(role) || !child_user(expected_user) || !child_apparmor(role) {
            finish(channel, nonce, 4, libc::EPERM);
        }
        child_before(channel, creator, nonce, 5, end);
        if libc::syscall(libc::SYS_setns, network, libc::CLONE_NEWNET) != 0 {
            fail(channel, nonce, 5);
        }
        // The pathname is a fixed kernel link for this exact calling thread.
        let now = libc::syscall(
            libc::SYS_openat,
            libc::AT_FDCWD,
            c"/proc/thread-self/ns/net".as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
            0,
        );
        if now < 0 {
            fail(channel, nonce, 5);
        }
        if !child_namespace(now as i32, expected, libc::CLONE_NEWNET) {
            finish(channel, nonce, 5, libc::ESTALE);
        }
        if libc::syscall(libc::SYS_close, now) != 0 {
            fail(channel, nonce, 5);
        }
        if !child_role(role) || !child_user(expected_user) || !child_apparmor(role) {
            finish(channel, nonce, 5, libc::EPERM);
        }
        child_before(channel, creator, nonce, 6, end);
        let mut sockets = [-1_i32; 3];
        if libc::syscall(
            libc::SYS_socketpair,
            libc::AF_UNIX,
            libc::SOCK_STREAM | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0,
            sockets.as_mut_ptr(),
        ) != 0
        {
            fail(channel, nonce, 6);
        }
        let listener = libc::syscall(
            libc::SYS_socket,
            libc::AF_UNIX,
            libc::SOCK_STREAM | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0,
        );
        if listener < 0 || listener > i32::MAX as i64 {
            fail(channel, nonce, 6);
        }
        sockets[2] = listener as i32;
        if !child_role(role) || !child_user(expected_user) || !child_apparmor(role) {
            finish(channel, nonce, 6, libc::EPERM);
        }
        child_before(channel, creator, nonce, 7, end);
        let packet = Packet {
            magic: REPLY,
            stage: 7,
            errno: 0,
            reserved: 0,
            nonce,
        };
        let mut iov = libc::iovec {
            iov_base: (&packet as *const Packet).cast_mut().cast(),
            iov_len: std::mem::size_of::<Packet>(),
        };
        let mut control = [0_usize; 4];
        let mut message: libc::msghdr = std::mem::zeroed();
        message.msg_iov = &mut iov;
        message.msg_iovlen = 1;
        message.msg_control = control.as_mut_ptr().cast();
        message.msg_controllen = libc::CMSG_SPACE(12) as usize;
        let h = libc::CMSG_FIRSTHDR(&message);
        (*h).cmsg_level = libc::SOL_SOCKET;
        (*h).cmsg_type = libc::SCM_RIGHTS;
        (*h).cmsg_len = libc::CMSG_LEN(12) as usize;
        std::ptr::copy_nonoverlapping(sockets.as_ptr().cast::<u8>(), libc::CMSG_DATA(h), 12);
        if libc::syscall(
            libc::SYS_sendmsg,
            channel,
            &message,
            libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
        ) != std::mem::size_of::<Packet>() as i64
        {
            fail(channel, nonce, 7);
        }
        child_barrier(channel, creator, nonce, 8, end, 2);
        child_before(channel, creator, nonce, 8, end);
        finish(channel, nonce, 8, 0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn ordinary() -> (File, ExpectedNamespace) {
        let file = tempfile::tempfile().unwrap();
        let m = file.metadata().unwrap();
        let n = ExpectedNamespace {
            dev: m.dev(),
            ino: m.ino(),
            id: 1,
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            spare: 0,
        };
        (file, n)
    }
    fn original_helper() -> Helper {
        let (file, n) = ordinary();
        Helper::spawn(
            &file,
            n,
            n,
            HostPeerRole::Broker,
            Instant::now() + Duration::from_secs(3),
        )
        .unwrap()
    }
    #[test]
    fn host_selected_socket_unreleased_original_child_is_actually_reaped() {
        let mut h = original_helper();
        assert!(!h.started && h.rights.is_empty() && !h.reap().unwrap());
        h.retire().unwrap();
        assert_eq!(h.exit, Some((libc::CLD_KILLED, libc::SIGKILL)));
        assert_eq!(h.waited_pid, Some(h.pid));
        assert!(h.terminal_verified && h.process.is_none() && h.rights.is_empty());
        h.retire().unwrap();
        assert!(h.start().is_err());
    }
    #[test]
    fn host_selected_socket_real_non_namespace_fails_before_any_socket_transfer() {
        let mut h = original_helper();
        h.start().unwrap();
        assert!(h.ready && h.started);
        assert!(
            matches!(h.receive_rights(),Err(MacError::Io(e)) if e.raw_os_error()==Some(libc::ESTALE))
        );
        assert!(h.rights.is_empty() && !h.acked && h.rights_packet.is_none());
        assert_eq!(h.reply.unwrap().stage, 4);
        let end = Instant::now() + Duration::from_secs(2);
        while !h.reap().unwrap() {
            assert!(Instant::now() < end);
            std::thread::yield_now();
        }
        assert_eq!(h.exit, Some((libc::CLD_EXITED, 125)));
        assert!(h.terminal_verified);
        h.retire().unwrap();
    }
    #[test]
    fn host_selected_socket_wrong_original_nonce_keeps_unreleased_child_for_retirement() {
        let mut h = original_helper();
        h.nonce[0] ^= 1;
        assert!(matches!(
            h.start(),
            Err(MacError::Rejected(
                "original helper record framing/nonce/actual credentials differ"
            ))
        ));
        assert!(!h.started && !h.ready && h.rights.is_empty() && h.pidfd.is_some());
        h.retire().unwrap();
        assert_eq!(h.exit, Some((libc::CLD_KILLED, libc::SIGKILL)));
        assert!(h.terminal_verified);
    }
    #[test]
    fn host_selected_socket_expired_creation_does_not_release_original_child() {
        let mut h = original_helper();
        h.deadline = Instant::now();
        assert!(h.start().is_err());
        assert!(!h.started && h.rights.is_empty());
        h.retire().unwrap();
        assert!(h.terminal_verified);
        assert_eq!(h.exit, Some((libc::CLD_KILLED, libc::SIGKILL)));
    }
    #[test]
    fn host_selected_socket_fixed_blocking_purpose_is_checked_on_real_open_description() {
        let (stream, _peer) = UnixStream::pair().unwrap();
        let node = descriptor_identity(stream.as_fd()).unwrap();
        let cookie = socket_cookie(stream.as_fd()).unwrap();
        socket_identity(stream.as_fd(), node, cookie, false, false).unwrap();
        assert!(socket_identity(stream.as_fd(), node, cookie, true, false).is_err());
        let duplicate = File::from(stream.as_fd().try_clone_to_owned().unwrap());
        stream.set_nonblocking(true).unwrap();
        socket_identity(duplicate.as_fd(), node, cookie, true, false).unwrap();
        assert!(socket_identity(duplicate.as_fd(), node, cookie, false, false).is_err());
        stream.set_nonblocking(false).unwrap();
        socket_identity(duplicate.as_fd(), node, cookie, false, false).unwrap();
    }
    #[test]
    fn host_selected_socket_same_kind_different_actual_socket_is_not_a_duplicate() {
        let (original, _p) = UnixStream::pair().unwrap();
        let (replacement, _q) = UnixStream::pair().unwrap();
        let node = descriptor_identity(original.as_fd()).unwrap();
        let cookie = socket_cookie(original.as_fd()).unwrap();
        assert_ne!(socket_cookie(replacement.as_fd()).unwrap(), cookie);
        assert!(socket_identity(replacement.as_fd(), node, cookie, false, false).is_err());
        assert!(socket_identity(original.as_fd(), node, cookie, false, true).is_err());
        let regular = tempfile::tempfile().unwrap();
        assert!(socket_identity(regular.as_fd(), node, cookie, false, false).is_err());
    }
}
