//! A single selected-netns socket creation, with original helper custody.
//! The helper remains in the initial user namespace, inherits the broker MAC
//! role, and joins only the original selected network namespace. Parent holds
//! the atomic clone PIDFD before releasing the post-PDEATHSIG READY barrier.
//! Three actual sockets are received into custody before ACK: a connected
//! provider probe pair and one unbound seqpacket listener. No guest receives
//! the helper control channel, selector device, PIDFD or namespace descriptor.
use super::netns_provider::{NamespaceIdentity, SelectedAndroidNetwork};
use super::*;
use crate::production_namespace::OwnedNamespaceWitness;
use std::os::fd::OwnedFd;

const READY: u32 = 0x5053_4b30;
const REPLY: u32 = 0x5053_4b31;
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
}
impl Helper {
    fn spawn(network: &File, expected: ExpectedNamespace, end: Instant) -> Result<Self> {
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
                    child.as_raw_fd(),
                    creator_pidfd.as_raw_fd(),
                    parent_pid,
                    nonce,
                    absolute,
                )
            }
        }
        let error = if pid < 0 {
            Some(io::Error::last_os_error())
        } else {
            None
        };
        let restored =
            unsafe { libc::pthread_sigmask(libc::SIG_SETMASK, &old, std::ptr::null_mut()) };
        drop(child);
        if let Some(error) = error {
            return Err(error.into());
        }
        require(
            pidfd >= 0 && pid <= i32::MAX as i64,
            "selected socket clone3 atomic PIDFD absent",
        )?;
        Ok(Self {
            pidfd: Some(unsafe { OwnedFd::from_raw_fd(pidfd) }),
            channel: parent,
            creator_pidfd,
            creator,
            pid: pid as i32,
            deadline: end,
            nonce,
            preparation_error: (restored != 0).then_some(restored),
            ready: false,
            started: false,
            rights: Vec::new(),
            rights_packet: None,
            acked: false,
            reply: None,
            exit: None,
        })
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
        require(
            pid == self.pid
                && [libc::CLD_EXITED, libc::CLD_KILLED, libc::CLD_DUMPED].contains(&info.si_code),
            "actual helper waitid original PIDFD identity",
        )?;
        self.exit = Some((info.si_code, unsafe { info.si_status() }));
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
        let end = Instant::now() + RETIRE_BOUND;
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
        if self.exit.is_none() {
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
fn helper_peer(socket: BorrowedFd<'_>, helper: &Helper) -> Result<()> {
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
        context_matches(&actual_socket_security(socket)?, BROKER),
        "actual selected socket SO_PEERSEC is not broker SELinux",
    )?;
    helper.peer_live()
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Stage {
    Fresh,
    Creating,
    Complete,
    Failed,
    Retired,
    Taken,
}
struct Pending {
    network: SelectedAndroidNetwork,
    helper: Option<Helper>,
    socket_nodes: Option<[DescriptorIdentity; 3]>,
    cookies: Option<[u64; 3]>,
}
/// Store this builder in the outer DeviceResources before create(). A failed
/// stage cannot create another helper; retire() keeps the same original owner
/// until waitid proves termination. No caller-provided FD can replace it.
pub(crate) struct SelectedAndroidSocketBuilder {
    inner: Option<Pending>,
    stage: Stage,
}
impl std::fmt::Debug for SelectedAndroidSocketBuilder {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SelectedAndroidSocketBuilder")
            .field("stage", &self.stage)
            .finish_non_exhaustive()
    }
}
impl SelectedAndroidSocketBuilder {
    pub(crate) fn new(network: SelectedAndroidNetwork) -> Self {
        Self {
            inner: Some(Pending {
                network,
                helper: None,
                socket_nodes: None,
                cookies: None,
            }),
            stage: Stage::Fresh,
        }
    }
    pub(crate) fn create(
        &mut self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        owner: &OwnedNamespaceWitness<'_>,
    ) -> Result<()> {
        require(
            self.stage == Stage::Fresh,
            "selected socket builder cannot replay a creation attempt",
        )?;
        self.stage = Stage::Creating;
        let result = (|| {
            let p = self.inner.as_mut().ok_or(MacError::Rejected(
                "selected socket original builder custody absent",
            ))?;
            p.network.require_unused(mac, selection, owner)?;
            let end = Instant::now() + CREATE_BOUND;
            p.helper = Some(Helper::spawn(
                p.network.network()?,
                p.network.network_identity().into(),
                end,
            )?);
            let helper = p.helper.as_mut().unwrap(); // Stored before the child's release.
            helper.start()?;
            helper.receive_rights()?;
            let mut nodes = [descriptor_identity(helper.rights[0].as_fd())?; 3];
            let mut cookies = [0_u64; 3];
            for i in 0..3 {
                let fd = helper.rights[i].as_fd();
                nodes[i] = descriptor_identity(fd)?;
                cookies[i] = socket_cookie(fd)?;
                require(
                    nodes[i].kind == libc::S_IFSOCK,
                    "original helper must pass actual sockets",
                )?;
                for (key, value) in [
                    (libc::SO_DOMAIN, libc::AF_UNIX),
                    (libc::SO_TYPE, libc::SOCK_SEQPACKET),
                    (libc::SO_PROTOCOL, 0),
                    (libc::SO_ACCEPTCONN, 0),
                ] {
                    socket_option(fd, key, value)?;
                }
                let status = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFL) };
                if status < 0 {
                    return Err(io::Error::last_os_error().into());
                }
                require(
                    status & libc::O_NONBLOCK != 0,
                    "selected helper sockets must be nonblocking",
                )?;
            }
            require(
                nodes[0] != nodes[1]
                    && nodes[0] != nodes[2]
                    && nodes[1] != nodes[2]
                    && cookies[0] != cookies[1]
                    && cookies[0] != cookies[2]
                    && cookies[1] != cookies[2],
                "three distinct original selected sockets",
            )?;
            helper_peer(helper.rights[0].as_fd(), helper)?;
            helper_peer(helper.rights[1].as_fd(), helper)?;
            // These are literal observed original kernel identities, retained before
            // ACK. A typed role or a local inode xattr never replaces these peer reads.
            p.socket_nodes = Some(nodes);
            p.cookies = Some(cookies);
            p.network.require_used(mac, selection, owner)?;
            helper.ack()?;
            helper.complete()?;
            p.network.require_used(mac, selection, owner)?;
            helper.before()?;
            Ok(())
        })();
        self.stage = if result.is_ok() {
            Stage::Complete
        } else {
            Stage::Failed
        };
        result
    }
    pub(crate) fn take_complete(
        &mut self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        owner: &OwnedNamespaceWitness<'_>,
    ) -> Result<SelectedAndroidSocket> {
        require(
            self.stage == Stage::Complete,
            "only actual completed/reaped selected helper can issue a listener",
        )?;
        let p = self.inner.as_ref().ok_or(MacError::Rejected(
            "selected socket original custody absent",
        ))?;
        require(
            p.helper.as_ref().is_some_and(|h| {
                h.exit == Some((libc::CLD_EXITED, 0)) && h.acked && h.rights.len() == 3
            }) && p.socket_nodes.is_some()
                && p.cookies.is_some(),
            "selected helper original complete result absent",
        )?;
        validate_pending(p, mac, selection, owner)?;
        let value = SelectedAndroidSocket {
            pending: self.inner.take().unwrap(),
        };
        self.stage = Stage::Taken;
        Ok(value)
    }
    /// Retirement kills only the original atomically owned helper and closes
    /// this builder's own FDs. It cannot select a namespace or create a socket.
    pub(crate) fn retire(&mut self) -> Result<()> {
        if self.stage == Stage::Retired {
            return Ok(());
        }
        require(
            self.stage != Stage::Taken,
            "taken listener retains its own independent custody",
        )?;
        if let Some(p) = self.inner.as_mut() {
            if let Some(h) = p.helper.as_mut() {
                h.retire()?;
            }
            // Never close the original private control or namespace while
            // its atomically owned socket helper may still be alive.
            p.network.retire()?;
        }
        self.inner.take();
        self.stage = Stage::Retired;
        Ok(())
    }
}
impl Drop for SelectedAndroidSocketBuilder {
    fn drop(&mut self) {
        if self
            .inner
            .as_ref()
            .is_some_and(|p| p.helper.as_ref().is_some_and(|h| h.exit.is_none()))
        {
            // The outer owner must call retire; losing this value cannot manufacture
            // retirement or free its original network/control/PIDFD/socket custody.
            if let Some(p) = self.inner.take() {
                std::mem::forget(p);
            }
        }
    }
}
pub(crate) struct SelectedAndroidSocket {
    pending: Pending,
}
impl std::fmt::Debug for SelectedAndroidSocket {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SelectedAndroidSocket")
            .finish_non_exhaustive()
    }
}
impl SelectedAndroidSocket {
    /// The listener and probes remain owned until the outer DEV closes.
    /// This retires only their already-reaped creator and the original
    /// private selector resources; SET is never reversed or reissued.
    pub(crate) fn retire(&mut self) -> Result<()> {
        self.pending
            .helper
            .as_mut()
            .ok_or(MacError::Rejected(
                "selected listener original creator custody absent",
            ))?
            .retire()?;
        self.pending.network.retire()
    }
    pub(crate) fn server(&self) -> BorrowedFd<'_> {
        self.pending.helper.as_ref().unwrap().rights[2].as_fd()
    }
    pub(crate) fn revalidate(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        owner: &OwnedNamespaceWitness<'_>,
    ) -> Result<()> {
        validate_pending(&self.pending, mac, selection, owner)
    }
}
fn validate_pending(
    p: &Pending,
    mac: &MacPreflight,
    selection: &ProductionSelection,
    owner: &OwnedNamespaceWitness<'_>,
) -> Result<()> {
    p.network.require_used(mac, selection, owner)?;
    let h = p.helper.as_ref().ok_or(MacError::Rejected(
        "selected listener original creator custody absent",
    ))?;
    h.same_creator()?;
    require(
        h.exit == Some((libc::CLD_EXITED, 0)) && h.acked && h.rights.len() == 3,
        "selected listener creator was not actually reaped successfully",
    )?;
    let nodes = p.socket_nodes.ok_or(MacError::Rejected(
        "selected socket original identities absent",
    ))?;
    let cookies = p.cookies.ok_or(MacError::Rejected(
        "selected socket original cookies absent",
    ))?;
    for i in 0..3 {
        let fd = h.rights[i].as_fd();
        require(
            descriptor_identity(fd)? == nodes[i] && socket_cookie(fd)? == cookies[i],
            "original selected socket identity changed",
        )?;
        socket_option(fd, libc::SO_DOMAIN, libc::AF_UNIX)?;
        socket_option(fd, libc::SO_TYPE, libc::SOCK_SEQPACKET)?;
        socket_option(fd, libc::SO_PROTOCOL, 0)?;
    }
    // Connected peer SIDs survive the creator's verified exit. Their original
    // helper PIDFD was compared while live, before ACK, and remains retained.
    for fd in &h.rights[..2] {
        require(
            context_matches(&actual_socket_security(fd.as_fd())?, BROKER),
            "original selected provider probe peer context changed",
        )?;
    }
    p.network.revalidate(mac, selection, owner)
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
unsafe fn child_namespace(fd: RawFd, expected: ExpectedNamespace) -> bool {
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
            && libc::syscall(libc::SYS_ioctl, fd, 0xb703_u64, 0_u64) == libc::CLONE_NEWNET as i64
            && libc::syscall(libc::SYS_ioctl, fd, 0x8008_b70d_u64, &mut id) == 0
            && id == expected.id
            && id != 0
    }
}
unsafe fn child_broker() -> bool {
    let mut value = TypedContext {
        id: 101,
        flags: 0,
        len: 0,
        ctx_len: 0,
        ctx: [0; 128],
    };
    let mut size = std::mem::size_of::<TypedContext>() as u32;
    let expected = b"u:r:droidloom_broker:s0\0";
    let n = unsafe { libc::syscall(459, 100_u32, &mut value, &mut size, 1_u32) };
    let aligned = (32 + expected.len() + 7) & !7;
    n == 1
        && value.id == 101
        && value.flags == 0
        && value.ctx_len == expected.len() as u64
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
        if !child_namespace(network, expected) {
            finish(channel, nonce, 4, libc::ESTALE);
        }
        if !child_broker() {
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
        if !child_namespace(now as i32, expected) {
            finish(channel, nonce, 5, libc::ESTALE);
        }
        if libc::syscall(libc::SYS_close, now) != 0 {
            fail(channel, nonce, 5);
        }
        if !child_broker() {
            finish(channel, nonce, 5, libc::EPERM);
        }
        child_before(channel, creator, nonce, 6, end);
        let mut sockets = [-1_i32; 3];
        if libc::syscall(
            libc::SYS_socketpair,
            libc::AF_UNIX,
            libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0,
            sockets.as_mut_ptr(),
        ) != 0
        {
            fail(channel, nonce, 6);
        }
        let listener = libc::syscall(
            libc::SYS_socket,
            libc::AF_UNIX,
            libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0,
        );
        if listener < 0 || listener > i32::MAX as i64 {
            fail(channel, nonce, 6);
        }
        sockets[2] = listener as i32;
        if !child_broker() {
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
        let expected = ExpectedNamespace {
            dev: m.dev(),
            ino: m.ino(),
            id: 1,
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            spare: 0,
        };
        (file, expected)
    }
    #[test]
    fn selected_socket_helper_unreleased_child_is_actually_reaped() {
        let (file, expected) = ordinary();
        let mut helper =
            Helper::spawn(&file, expected, Instant::now() + Duration::from_secs(3)).unwrap();
        assert!(!helper.started && helper.rights.is_empty() && !helper.reap().unwrap());
        helper.retire().unwrap();
        assert_eq!(helper.exit, Some((libc::CLD_KILLED, libc::SIGKILL)));
        helper.retire().unwrap();
        assert!(helper.start().is_err());
    }
    #[test]
    fn selected_socket_helper_rejects_real_non_namespace_before_socket_creation() {
        let (file, expected) = ordinary();
        let mut helper =
            Helper::spawn(&file, expected, Instant::now() + Duration::from_secs(3)).unwrap();
        helper.start().unwrap();
        assert!(helper.ready && helper.started);
        assert!(
            matches!(helper.receive_rights(),Err(MacError::Io(e)) if e.raw_os_error()==Some(libc::ESTALE))
        );
        assert!(helper.rights.is_empty() && !helper.acked && helper.rights_packet.is_none());
        assert_eq!(helper.reply.unwrap().stage, 4);
        let end = Instant::now() + Duration::from_secs(2);
        while !helper.reap().unwrap() {
            assert!(Instant::now() < end);
            std::thread::yield_now();
        }
        assert_eq!(helper.exit, Some((libc::CLD_EXITED, 125)));
        helper.retire().unwrap();
    }
    #[test]
    fn ordinary_descriptor_cannot_supply_selected_socket_cookie_or_options() {
        let file = tempfile::tempfile().unwrap();
        assert!(socket_cookie(file.as_fd()).is_err());
        assert!(socket_option(file.as_fd(), libc::SO_DOMAIN, libc::AF_UNIX).is_err());
    }
}
