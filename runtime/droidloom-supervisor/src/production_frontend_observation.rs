//! A short-lived, PIDFD-owned reader for the current peer's fixed proc metadata.
//! The original owner never changes credentials or namespaces. After clone3,
//! the child executes only bounded syscalls on descriptors prepared by that
//! owner. Returned descriptors are unusable until its real waitid exit is zero.
#[cfg(test)]
use super::wire::Node;
use super::wire::{self, check, cv};
use crate::production_application::{FrontendCloneArgs, FrontendSignalMask};
use std::fs::File;
use std::io;
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::time::{Duration, Instant};

const LIMIT: usize = 8192;
const DESCRIPTORS: usize = 9;
const FRONTEND_DESCRIPTORS: usize = 5;
const MAGIC: [u8; 8] = *b"DLPROCO1";
const REAP_LIMIT: Duration = Duration::from_secs(2);
const PIDFD_GET_INFO: libc::c_ulong = 0xc040ff0b;
const NSFS: libc::c_long = 0x6e736673;
const CAP_SYS_NICE: u32 = 23;

// commoncap READ_FSCREDS requires the target's permitted set to be a subset.
// The selected Composer RC requests only SYS_NICE. The selected InputBridge
// RC explicitly requests an empty set; the native presenter has no file caps.
// No branch retains SYS_PTRACE, DAC overrides, SETUID/SETGID or SYS_ADMIN.
fn reader_capabilities(android_scope: bool, uid: u32) -> [u32; 6] {
    let keep = if android_scope && uid == 1000 {
        1 << CAP_SYS_NICE
    } else {
        0
    };
    [keep, keep, 0, 0, 0, 0]
}

#[repr(C)]
struct Packet {
    magic: [u8; 8],
    nonce: [u8; 16],
    error: i32,
    lengths: [u32; 3],
    capabilities: [u32; 6],
    bytes: [[u8; LIMIT]; 3],
}
impl Packet {
    fn empty(nonce: [u8; 16]) -> Self {
        Self {
            magic: MAGIC,
            nonce,
            error: 0,
            lengths: [0; 3],
            capabilities: [0; 6],
            bytes: [[0; LIMIT]; 3],
        }
    }
}
#[repr(C, align(8))]
struct Ancillary([u8; 256]);

#[repr(C)]
#[derive(Default)]
struct PidInfo {
    mask: u64,
    cgroup: u64,
    pid: u32,
    tgid: u32,
    ppid: u32,
    ruid: u32,
    rgid: u32,
    euid: u32,
    egid: u32,
    suid: u32,
    sgid: u32,
    fsuid: u32,
    fsgid: u32,
    exit: i32,
}
const _: () = assert!(mem::size_of::<PidInfo>() == 64);

#[derive(PartialEq, Eq, Debug)]
struct OwnerCredentials {
    tid: libc::pid_t,
    uids: [u32; 4],
    gids: [u32; 4],
    capabilities: [u32; 6],
}
impl OwnerCredentials {
    fn read() -> io::Result<Self> {
        let mut uids = [0; 4];
        let mut gids = [0; 4];
        cv(unsafe { libc::getresuid(&mut uids[0], &mut uids[1], &mut uids[2]) })?;
        cv(unsafe { libc::getresgid(&mut gids[0], &mut gids[1], &mut gids[2]) })?;
        // An invalid kuid/kgid queries the current filesystem identity.
        uids[3] = unsafe { libc::setfsuid(u32::MAX) } as u32;
        gids[3] = unsafe { libc::setfsgid(u32::MAX) } as u32;
        let header = [0x20080522_u32, 0];
        let mut capabilities = [0; 6];
        if unsafe { libc::syscall(libc::SYS_capget, header.as_ptr(), capabilities.as_mut_ptr()) }
            != 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(Self {
            tid: unsafe { libc::syscall(libc::SYS_gettid) } as i32,
            uids,
            gids,
            capabilities,
        })
    }
}

struct Child {
    pid: libc::pid_t,
    pidfd: Option<OwnedFd>,
    terminal: Option<i32>,
}
impl Child {
    fn wait(&mut self, deadline: Instant, kill: bool) -> io::Result<i32> {
        if let Some(status) = self.terminal {
            return Ok(status);
        }
        let fd = self
            .pidfd
            .as_ref()
            .ok_or_else(|| io::Error::other("observer PIDFD absent"))?;
        if kill {
            let rc = unsafe {
                libc::syscall(
                    libc::SYS_pidfd_send_signal,
                    fd.as_raw_fd(),
                    libc::SIGKILL,
                    std::ptr::null::<libc::siginfo_t>(),
                    0_u32,
                )
            };
            if rc != 0 && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH) {
                return Err(io::Error::last_os_error());
            }
        }
        loop {
            let mut status: libc::siginfo_t = unsafe { mem::zeroed() };
            cv(unsafe {
                libc::waitid(
                    libc::P_PIDFD,
                    fd.as_raw_fd() as u32,
                    &mut status,
                    libc::WEXITED | libc::WNOHANG,
                )
            })?;
            let pid = unsafe { status.si_pid() };
            if pid != 0 {
                check(
                    pid == self.pid
                        && matches!(
                            status.si_code,
                            libc::CLD_EXITED | libc::CLD_KILLED | libc::CLD_DUMPED
                        ),
                    "observer waitid returned another process",
                )?;
                let result = if status.si_code == libc::CLD_EXITED {
                    unsafe { status.si_status() }
                } else {
                    128 + unsafe { status.si_status() }
                };
                self.terminal = Some(result);
                return Ok(result);
            }
            let left = deadline
                .checked_duration_since(Instant::now())
                .ok_or_else(|| {
                    io::Error::new(io::ErrorKind::TimedOut, "observer retirement unproven")
                })?;
            let mut event = libc::pollfd {
                fd: fd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            let rc = unsafe { libc::poll(&mut event, 1, left.as_millis().min(20) as i32) };
            if rc < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
                return Err(io::Error::last_os_error());
            }
        }
    }
}
impl Drop for Child {
    fn drop(&mut self) {
        if self.terminal.is_none() {
            // The Frontend keeps a failed retirement quarantined. An unwind must
            // not close the last handle and silently turn it into proved absence.
            if let Some(fd) = self.pidfd.take() {
                mem::forget(fd);
            }
        }
    }
}

pub(super) struct Observation {
    pub executable: File,
    pub namespaces: [File; 3], // user, pid, mnt
    pub root: File,
    extra_namespaces: Option<[File; 4]>, // fixed query: ipc, uts, net, cgroup
    pub context: Vec<u8>,
    pub command: Vec<u8>,
    pub environment: Vec<u8>,
}
/// A fixed observation made only while the original query is held at TRACEEXEC.
/// All descriptors came from its held proc directory and were admitted only
/// after the zero-capability reader actually exited and was reaped.
pub(crate) struct QueryObservation {
    pub(crate) executable: File,
    pub(crate) namespaces: [File; 7], // user, pid, mnt, ipc, uts, net, cgroup
    pub(crate) root: File,
    pub(crate) selinux: Vec<u8>,
    pub(crate) apparmor: Vec<u8>,
}
pub(crate) fn observe_query(
    directory: &File,
    peer: &OwnedFd,
    userns: &File,
) -> io::Result<QueryObservation> {
    let result = Observer::default().sample_mode(
        directory,
        peer,
        Some(userns),
        2000,
        2000,
        false,
        c"attr/current",
        true,
    )?;
    let [user, pid, mnt] = result.namespaces;
    let [ipc, uts, net, cgroup] = result
        .extra_namespaces
        .ok_or_else(|| io::Error::other("query namespace observation incomplete"))?;
    Ok(QueryObservation {
        executable: result.executable,
        namespaces: [user, pid, mnt, ipc, uts, net, cgroup],
        root: result.root,
        selinux: result.context,
        apparmor: result.command,
    })
}
#[derive(Default)]
pub(super) struct Observer {
    pending: Option<Child>,
    unknown_child: bool,
}
impl Observer {
    pub(super) fn clean(&self) -> io::Result<()> {
        check(
            self.pending.is_none() && !self.unknown_child,
            "an original frontend observer remains quarantined",
        )
    }
    pub(super) fn retire(&mut self) -> io::Result<()> {
        check(!self.unknown_child, "atomic observer ownership is unproven")?;
        if let Some(child) = &mut self.pending {
            child.wait(Instant::now() + REAP_LIMIT, true)?;
            self.pending.take();
        }
        Ok(())
    }
    pub(super) fn sample(
        &mut self,
        directory: &File,
        peer: &OwnedFd,
        userns: Option<&File>,
        uid: u32,
        gid: u32,
        input: bool,
    ) -> io::Result<Observation> {
        self.sample_paths(
            directory,
            peer,
            userns,
            uid,
            gid,
            input,
            c"attr/selinux/current",
        )
    }
    fn sample_paths(
        &mut self,
        directory: &File,
        peer: &OwnedFd,
        userns: Option<&File>,
        uid: u32,
        gid: u32,
        input: bool,
        context_path: &std::ffi::CStr,
    ) -> io::Result<Observation> {
        self.sample_mode(
            directory,
            peer,
            userns,
            uid,
            gid,
            input,
            context_path,
            false,
        )
    }
    #[allow(clippy::too_many_arguments)]
    fn sample_mode(
        &mut self,
        directory: &File,
        peer: &OwnedFd,
        userns: Option<&File>,
        uid: u32,
        gid: u32,
        input: bool,
        context_path: &std::ffi::CStr,
        query: bool,
    ) -> io::Result<Observation> {
        self.clean()?;
        check(
            !query || !input,
            "query reader cannot request frontend environment",
        )?;
        let descriptor_count = if query {
            DESCRIPTORS
        } else {
            FRONTEND_DESCRIPTORS
        };
        super::procfs(directory)?;
        let before = OwnerCredentials::read()?;
        let peer_before = wire::pid_info(peer)?;
        wire::exact_ids(
            &peer_before,
            if userns.is_some() {
                peer_before.euid
            } else {
                uid
            },
            if userns.is_some() {
                peer_before.egid
            } else {
                gid
            },
        )?;
        if let Some(ns) = userns {
            let mut fs: libc::statfs = unsafe { mem::zeroed() };
            cv(unsafe { libc::fstatfs(ns.as_raw_fd(), &mut fs) })?;
            check(
                fs.f_type == NSFS
                    && unsafe { libc::ioctl(ns.as_raw_fd(), 0xb703 as libc::c_ulong) }
                        == libc::CLONE_NEWUSER,
                "observer scope is not the held user namespace",
            )?;
        }
        let mut signal: libc::sigaction = unsafe { mem::zeroed() };
        cv(unsafe { libc::sigaction(libc::SIGCHLD, std::ptr::null(), &mut signal) })?;
        check(
            signal.sa_sigaction == libc::SIG_DFL && signal.sa_flags & libc::SA_NOCLDWAIT == 0,
            "observer requires original waitable SIGCHLD",
        )?;
        let parent_pid = unsafe { libc::getpid() };
        let raw_parent = unsafe { libc::syscall(libc::SYS_pidfd_open, parent_pid, 0_u32) };
        if raw_parent < 0 {
            return Err(io::Error::last_os_error());
        }
        let parent = unsafe { OwnedFd::from_raw_fd(raw_parent as i32) };
        let parent_info = wire::pid_info(&parent)?;
        check(
            parent_info.pid == parent_pid as u32,
            "observer parent PIDFD is not the actual owner",
        )?;
        let mut sockets = [-1; 2];
        cv(unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                0,
                sockets.as_mut_ptr(),
            )
        })?;
        let receive = unsafe { OwnedFd::from_raw_fd(sockets[0]) };
        let send = unsafe { OwnedFd::from_raw_fd(sockets[1]) };
        let one = 1_i32;
        cv(unsafe {
            libc::setsockopt(
                receive.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PASSCRED,
                (&one as *const i32).cast(),
                mem::size_of_val(&one) as u32,
            )
        })?;
        let mut nonce = [0_u8; 16];
        check(
            unsafe { libc::syscall(libc::SYS_getrandom, nonce.as_mut_ptr(), nonce.len(), 0_u32) }
                == 16,
            "observer nonce generation failed",
        )?;
        // All buffers, pointers and the entire child operation are fixed before
        // clone. The child has private VM/files/FS/credentials and no Rust work.
        let expected_capabilities = reader_capabilities(userns.is_some(), uid);
        let cap_header = [0x20080522_u32, 0];
        let mut packet = Packet::empty(nonce);
        let mut ancillary = Ancillary([0; 256]);
        let mut child_fds = [-1_i32; DESCRIPTORS];
        let mut child_info = PidInfo {
            mask: 3,
            ..PidInfo::default()
        };
        let filter = child_filter(directory.as_raw_fd(), peer.as_raw_fd(), send.as_raw_fd());
        let program = libc::sock_fprog {
            len: filter.len() as u16,
            filter: filter.as_ptr().cast_mut(),
        };
        let mut keep = vec![
            parent.as_raw_fd(),
            peer.as_raw_fd(),
            directory.as_raw_fd(),
            send.as_raw_fd(),
        ];
        if let Some(ns) = userns {
            keep.push(ns.as_raw_fd());
        }
        keep.sort_unstable();
        keep.dedup();
        let mut raw_pidfd = -1_i32;
        let args = FrontendCloneArgs {
            flags: libc::CLONE_PIDFD as u64,
            pidfd: (&mut raw_pidfd as *mut i32) as u64,
            exit_signal: libc::SIGCHLD as u64,
            ..FrontendCloneArgs::default()
        };
        let mut blocked = FrontendSignalMask::block().map_err(io::Error::other)?;
        let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args)) };
        if pid < 0 {
            return Err(io::Error::last_os_error());
        }
        if pid == 0 {
            unsafe {
                child_read(
                    parent_pid,
                    parent.as_raw_fd(),
                    peer.as_raw_fd(),
                    peer_before.pid,
                    directory.as_raw_fd(),
                    userns.map_or(-1, AsRawFd::as_raw_fd),
                    uid,
                    gid,
                    input,
                    query,
                    descriptor_count,
                    context_path.as_ptr(),
                    receive.as_raw_fd(),
                    send.as_raw_fd(),
                    &mut packet,
                    &mut ancillary,
                    &mut child_fds,
                    &mut child_info,
                    &program,
                    keep.as_ptr(),
                    keep.len(),
                    &cap_header,
                    &expected_capabilities,
                );
            }
        }
        // CLONE_PIDFD is an atomic kernel output. Retain it before every fallible
        // operation, including restoring the original thread's signal mask.
        if raw_pidfd < 0 {
            self.unknown_child = true;
            return Err(io::Error::other("atomic observer PIDFD absent"));
        }
        self.pending = Some(Child {
            pid: pid as i32,
            pidfd: Some(unsafe { OwnedFd::from_raw_fd(raw_pidfd) }),
            terminal: None,
        });
        drop(send);
        let result = (|| {
            blocked.restore().map_err(io::Error::other)?;
            let (packet, descriptors, sender) =
                receive_packet(&receive, Instant::now() + Duration::from_secs(1))?;
            // No returned descriptor, label, executable or namespace is consumed
            // as authority until the original child has truly exited and reaped.
            let terminal = self
                .pending
                .as_mut()
                .unwrap()
                .wait(Instant::now() + REAP_LIMIT, false)?;
            check(terminal == 0, "frontend observer did not exit successfully")?;
            check(
                OwnerCredentials::read()? == before,
                "original owner credentials/capabilities changed across observation",
            )?;
            check(
                sender.pid == pid as i32
                    && sender.uid == before.uids[0]
                    && sender.gid == before.gids[0],
                "frontend observation came from another kernel sender",
            )?;
            check(
                packet.magic == MAGIC && packet.nonce == nonce,
                "frontend observation phase or nonce differs",
            )?;
            if packet.error != 0 {
                return Err(io::Error::from_raw_os_error(packet.error));
            }
            check(
                packet.capabilities == expected_capabilities,
                "frontend observer retained capabilities outside its fixed reader role",
            )?;
            check(
                descriptors.len() == descriptor_count,
                "frontend observation descriptor roles differ",
            )?;
            for length in packet.lengths {
                check(length as usize <= LIMIT, "frontend observation byte bound")?;
            }
            let mut files = descriptors.into_iter().map(File::from);
            let observation = Observation {
                executable: files.next().unwrap(),
                namespaces: [
                    files.next().unwrap(),
                    files.next().unwrap(),
                    files.next().unwrap(),
                ],
                root: files.next().unwrap(),
                extra_namespaces: if query {
                    Some([
                        files.next().unwrap(),
                        files.next().unwrap(),
                        files.next().unwrap(),
                        files.next().unwrap(),
                    ])
                } else {
                    None
                },
                context: packet.bytes[0][..packet.lengths[0] as usize]
                    .strip_suffix(&[0])
                    .unwrap_or(&packet.bytes[0][..packet.lengths[0] as usize])
                    .to_vec(),
                command: packet.bytes[1][..packet.lengths[1] as usize].to_vec(),
                environment: packet.bytes[2][..packet.lengths[2] as usize].to_vec(),
            };
            check(
                observation.executable.metadata()?.is_file()
                    && observation.root.metadata()?.is_dir(),
                "frontend observation executable/root type",
            )?;
            for (fd, kind) in observation.namespaces.iter().zip([
                libc::CLONE_NEWUSER,
                libc::CLONE_NEWPID,
                libc::CLONE_NEWNS,
            ]) {
                let mut fs: libc::statfs = unsafe { mem::zeroed() };
                cv(unsafe { libc::fstatfs(fd.as_raw_fd(), &mut fs) })?;
                check(
                    fs.f_type == NSFS
                        && unsafe { libc::ioctl(fd.as_raw_fd(), 0xb703 as libc::c_ulong) } == kind,
                    "frontend observation namespace role",
                )?;
            }
            if let Some(extra) = &observation.extra_namespaces {
                for (fd, kind) in extra.iter().zip([
                    libc::CLONE_NEWIPC,
                    libc::CLONE_NEWUTS,
                    libc::CLONE_NEWNET,
                    libc::CLONE_NEWCGROUP,
                ]) {
                    let mut fs: libc::statfs = unsafe { mem::zeroed() };
                    cv(unsafe { libc::fstatfs(fd.as_raw_fd(), &mut fs) })?;
                    check(
                        fs.f_type == NSFS
                            && unsafe { libc::ioctl(fd.as_raw_fd(), 0xb703 as libc::c_ulong) }
                                == kind,
                        "query observation namespace role",
                    )?;
                }
            }
            let after = wire::pid_info(peer)?;
            check(
                after.pid == peer_before.pid && after.ppid == peer_before.ppid,
                "frontend peer generation changed during observation",
            )?;
            wire::exact_ids(&after, peer_before.euid, peer_before.egid)?;
            Ok(observation)
        })();
        // A failed read, timeout or malformed transfer follows exactly the same
        // kernel retirement path. A failed retirement remains owned and poisons
        // future progress until the original Frontend can prove its cleanup.
        self.retire()?;
        check(
            OwnerCredentials::read()? == before,
            "owner credential restoration differs",
        )?;
        result
    }
}
impl Drop for Observer {
    fn drop(&mut self) {
        if let Err(error) = self.retire() {
            eprintln!("frontend observer retirement remains unproven: {error}");
        }
    }
}

fn receive_packet(
    socket: &OwnedFd,
    deadline: Instant,
) -> io::Result<(Packet, Vec<OwnedFd>, libc::ucred)> {
    loop {
        let left = deadline
            .checked_duration_since(Instant::now())
            .ok_or_else(|| {
                io::Error::new(io::ErrorKind::TimedOut, "frontend observation deadline")
            })?;
        let mut event = libc::pollfd {
            fd: socket.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        let rc = unsafe { libc::poll(&mut event, 1, left.as_millis().min(20) as i32) };
        if rc < 0 {
            if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(io::Error::last_os_error());
        }
        if event.revents == 0 {
            continue;
        }
        let mut packet = Packet::empty([0; 16]);
        let mut ancillary = Ancillary([0; 256]);
        let mut iov = libc::iovec {
            iov_base: (&mut packet as *mut Packet).cast(),
            iov_len: mem::size_of::<Packet>(),
        };
        let mut message: libc::msghdr = unsafe { mem::zeroed() };
        message.msg_iov = &mut iov;
        message.msg_iovlen = 1;
        message.msg_control = ancillary.0.as_mut_ptr().cast();
        message.msg_controllen = ancillary.0.len();
        let count = unsafe {
            libc::recvmsg(
                socket.as_raw_fd(),
                &mut message,
                libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
            )
        };
        if count < 0 {
            if matches!(
                io::Error::last_os_error().kind(),
                io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
            ) {
                continue;
            }
            return Err(io::Error::last_os_error());
        }
        let mut files = Vec::new();
        let mut sender = None;
        let mut malformed = false;
        let mut header = unsafe { libc::CMSG_FIRSTHDR(&message) };
        while !header.is_null() {
            let length = unsafe { (*header).cmsg_len };
            let base = unsafe { libc::CMSG_LEN(0) } as usize;
            let offset = header as usize - message.msg_control as usize;
            if length < base
                || offset
                    .checked_add(length)
                    .is_none_or(|end| end > message.msg_controllen)
            {
                malformed = true;
                break;
            }
            let bytes = length - base;
            let body = unsafe { libc::CMSG_DATA(header) };
            match unsafe { ((*header).cmsg_level, (*header).cmsg_type) } {
                (libc::SOL_SOCKET, libc::SCM_RIGHTS) => {
                    if bytes % mem::size_of::<i32>() != 0 {
                        malformed = true;
                    }
                    for i in 0..bytes / mem::size_of::<i32>() {
                        let raw = unsafe { std::ptr::read_unaligned(body.cast::<i32>().add(i)) };
                        if raw >= 0 {
                            files.push(unsafe { OwnedFd::from_raw_fd(raw) });
                        } else {
                            malformed = true;
                        }
                    }
                }
                (libc::SOL_SOCKET, libc::SCM_CREDENTIALS)
                    if bytes == mem::size_of::<libc::ucred>() && sender.is_none() =>
                {
                    sender = Some(unsafe { std::ptr::read_unaligned(body.cast::<libc::ucred>()) });
                }
                _ => malformed = true,
            }
            header = unsafe { libc::CMSG_NXTHDR(&message, header) };
        }
        check(
            !malformed
                && count as usize == mem::size_of::<Packet>()
                && message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) == 0
                && files.len() <= DESCRIPTORS,
            "frontend observation framing or descriptor limit",
        )?;
        return Ok((
            packet,
            files,
            sender.ok_or_else(|| io::Error::other("frontend observation lacks kernel sender"))?,
        ));
    }
}

fn child_filter(proc: i32, peer: i32, out: i32) -> Vec<libc::sock_filter> {
    const ALLOW: u32 = 0x7fff0000;
    const DENY: u32 = 0x00050000 | libc::EPERM as u32;
    fn s(code: u16, k: u32) -> libc::sock_filter {
        libc::sock_filter {
            code,
            jt: 0,
            jf: 0,
            k,
        }
    }
    fn j(k: u32, jt: u8, jf: u8) -> libc::sock_filter {
        libc::sock_filter {
            code: 0x15,
            jt,
            jf,
            k,
        }
    }
    let mut f = vec![
        s(0x20, 4),
        j(0xc000003e, 1, 0),
        s(0x06, 0x80000000),
        s(0x20, 0),
    ];
    for nr in [
        libc::SYS_read,
        libc::SYS_close,
        libc::SYS_poll,
        libc::SYS_exit,
        libc::SYS_exit_group,
    ] {
        f.extend([j(nr as u32, 0, 1), s(0x06, ALLOW)]);
    }
    // openat is confined to the original held proc directory, without any
    // creation, append, truncation or write access bit.
    f.extend([
        j(libc::SYS_openat as u32, 0, 7),
        s(0x20, 16),
        j(proc as u32, 0, 4),
        s(0x20, 32),
        libc::sock_filter {
            code: 0x45,
            jt: 1,
            jf: 0,
            k: (libc::O_WRONLY
                | libc::O_RDWR
                | libc::O_CREAT
                | libc::O_TRUNC
                | libc::O_APPEND
                | (libc::O_TMPFILE & !libc::O_DIRECTORY)) as u32,
        },
        s(0x06, ALLOW),
        s(0x06, DENY),
        s(0x06, DENY),
    ]);
    f.push(s(0x20, 0));
    f.extend([
        j(libc::SYS_ioctl as u32, 0, 7),
        s(0x20, 16),
        j(peer as u32, 0, 4),
        s(0x20, 24),
        j(PIDFD_GET_INFO as u32, 0, 1),
        s(0x06, ALLOW),
        s(0x06, DENY),
        s(0x06, DENY),
    ]);
    f.push(s(0x20, 0));
    f.extend([
        j(libc::SYS_sendmsg as u32, 0, 4),
        s(0x20, 16),
        j(out as u32, 0, 1),
        s(0x06, ALLOW),
        s(0x06, DENY),
    ]);
    f.push(s(0x06, DENY));
    f
}

// The entire child branch below uses already allocated buffers and raw libc
// syscall wrappers. It never constructs a Rust error, allocates, formats, locks,
// drops inherited owners or returns into the parent's runtime.
unsafe fn child_alive(fd: i32) -> bool {
    let mut event = libc::pollfd {
        fd,
        events: libc::POLLIN,
        revents: 0,
    };
    unsafe { libc::poll(&mut event, 1, 0) == 0 }
}
unsafe fn child_ids(fd: i32, pid: u32, uid: u32, gid: u32, value: &mut PidInfo) -> bool {
    value.mask = 3;
    let valid = unsafe { libc::ioctl(fd, PIDFD_GET_INFO, value as *mut PidInfo) == 0 };
    valid
        && value.mask & 3 == 3
        && value.pid == pid
        && value.tgid == pid
        && [value.ruid, value.euid, value.suid, value.fsuid] == [uid; 4]
        && [value.rgid, value.egid, value.sgid, value.fsgid] == [gid; 4]
}
unsafe fn child_file(
    proc: i32,
    path: *const libc::c_char,
    buffer: &mut [u8; LIMIT],
    length: &mut u32,
) -> i32 {
    let fd = unsafe {
        libc::openat(
            proc,
            path,
            libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
        )
    };
    if fd < 0 {
        return unsafe { *libc::__errno_location() };
    }
    let mut count = 0;
    let mut error = 0;
    while count < LIMIT {
        let got = unsafe { libc::read(fd, buffer.as_mut_ptr().add(count).cast(), LIMIT - count) };
        if got < 0 {
            error = unsafe { *libc::__errno_location() };
            break;
        }
        if got == 0 {
            break;
        }
        count += got as usize;
    }
    if count == LIMIT && error == 0 {
        let mut extra = 0u8;
        if unsafe { libc::read(fd, (&mut extra as *mut u8).cast(), 1) } != 0 {
            error = libc::EOVERFLOW;
        }
    }
    unsafe {
        libc::close(fd);
    }
    *length = count as u32;
    error
}
#[allow(clippy::too_many_arguments)]
unsafe fn child_read(
    parent: i32,
    parent_fd: i32,
    peer: i32,
    pid: u32,
    proc: i32,
    userns: i32,
    uid: u32,
    gid: u32,
    input: bool,
    query: bool,
    descriptor_count: usize,
    context: *const libc::c_char,
    unused: i32,
    out: i32,
    packet: &mut Packet,
    ancillary: &mut Ancillary,
    files: &mut [i32; DESCRIPTORS],
    info: &mut PidInfo,
    filter: &libc::sock_fprog,
    keep: *const i32,
    keep_len: usize,
    cap_header: &[u32; 2],
    expected_capabilities: &[u32; 6],
) -> ! {
    unsafe {
        libc::close(unused);
        let mut first = 0_u32;
        for i in 0..keep_len {
            let held = *keep.add(i) as u32;
            if first < held && libc::syscall(libc::SYS_close_range, first, held - 1, 0_u32) != 0 {
                libc::_exit(125);
            }
            first = held + 1;
        }
        if libc::syscall(libc::SYS_close_range, first, u32::MAX, 0_u32) != 0 {
            libc::_exit(125);
        }
        let mut error = 0;
        if libc::getppid() != parent
            || !child_alive(parent_fd)
            || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0
        {
            libc::_exit(125);
        }
        if userns >= 0 && libc::setns(userns, libc::CLONE_NEWUSER) != 0 {
            error = *libc::__errno_location();
        }
        if error == 0 {
            libc::setfsgid(gid);
            libc::setfsuid(uid);
            if libc::setfsgid(u32::MAX) as u32 != gid || libc::setfsuid(u32::MAX) as u32 != uid {
                error = libc::EACCES;
            }
        }
        // setns(USER) grants a full namespace capability set, including
        // SYS_PTRACE. Filesystem ID matching alone must never bypass dumpable.
        // Narrow effective/permitted/inheritable sets before any proc read and
        // read back the exact result. Seccomp below then forbids capset/exec.
        if error == 0
            && (libc::syscall(
                libc::SYS_capset,
                cap_header.as_ptr(),
                expected_capabilities.as_ptr(),
            ) != 0
                || libc::syscall(
                    libc::SYS_capget,
                    cap_header.as_ptr(),
                    packet.capabilities.as_mut_ptr(),
                ) != 0)
        {
            error = *libc::__errno_location();
        }
        if error == 0 && packet.capabilities != *expected_capabilities {
            error = libc::EPERM;
        }
        // Credential changes clear pdeath_signal. Re-arm only while the same
        // original parent PIDFD is still live, closing the parent-death window.
        if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0
            || libc::getppid() != parent
            || !child_alive(parent_fd)
        {
            libc::_exit(125);
        }
        if libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
            || libc::syscall(libc::SYS_seccomp, 1, 0, filter as *const libc::sock_fprog) != 0
        {
            libc::_exit(125);
        }
        if error == 0 && (!child_alive(peer) || !child_ids(peer, pid, uid, gid, info)) {
            error = libc::EPERM;
        }
        let paths = [
            c"exe".as_ptr(),
            c"ns/user".as_ptr(),
            c"ns/pid".as_ptr(),
            c"ns/mnt".as_ptr(),
            c"root".as_ptr(),
            c"ns/ipc".as_ptr(),
            c"ns/uts".as_ptr(),
            c"ns/net".as_ptr(),
            c"ns/cgroup".as_ptr(),
        ];
        if error == 0 {
            for i in 0..descriptor_count {
                let flags = libc::O_CLOEXEC
                    | if i == 0 && !query {
                        libc::O_PATH
                    } else if i == 4 {
                        libc::O_PATH | libc::O_DIRECTORY
                    } else {
                        libc::O_RDONLY
                    };
                files[i] = libc::openat(proc, paths[i], flags);
                if files[i] < 0 {
                    error = *libc::__errno_location();
                    break;
                }
            }
        }
        if error == 0 {
            error = child_file(proc, context, &mut packet.bytes[0], &mut packet.lengths[0]);
        }
        if error == 0 && query {
            error = child_file(
                proc,
                c"attr/apparmor/current".as_ptr(),
                &mut packet.bytes[1],
                &mut packet.lengths[1],
            );
        }
        if error == 0 && input {
            error = child_file(
                proc,
                c"cmdline".as_ptr(),
                &mut packet.bytes[1],
                &mut packet.lengths[1],
            );
        }
        if error == 0 && input {
            error = child_file(
                proc,
                c"environ".as_ptr(),
                &mut packet.bytes[2],
                &mut packet.lengths[2],
            );
        }
        if error == 0
            && (!child_alive(parent_fd)
                || !child_alive(peer)
                || !child_ids(peer, pid, uid, gid, info))
        {
            error = libc::EPERM;
        }
        packet.error = error;
        let mut iov = libc::iovec {
            iov_base: (packet as *mut Packet).cast(),
            iov_len: mem::size_of::<Packet>(),
        };
        let mut message: libc::msghdr = mem::zeroed();
        message.msg_iov = &mut iov;
        message.msg_iovlen = 1;
        if error == 0 {
            message.msg_control = ancillary.0.as_mut_ptr().cast();
            message.msg_controllen =
                libc::CMSG_SPACE((descriptor_count * mem::size_of::<i32>()) as u32) as usize;
            let header = libc::CMSG_FIRSTHDR(&message);
            (*header).cmsg_level = libc::SOL_SOCKET;
            (*header).cmsg_type = libc::SCM_RIGHTS;
            (*header).cmsg_len =
                libc::CMSG_LEN((descriptor_count * mem::size_of::<i32>()) as u32) as usize;
            std::ptr::copy_nonoverlapping(
                files.as_ptr(),
                libc::CMSG_DATA(header).cast(),
                descriptor_count,
            );
        }
        let sent = libc::sendmsg(out, &message, libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL);
        libc::_exit(if sent == mem::size_of::<Packet>() as isize {
            0
        } else {
            125
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn peer() -> OwnedFd {
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0) };
        assert!(raw >= 0);
        unsafe { OwnedFd::from_raw_fd(raw as i32) }
    }
    #[test]
    fn frontend_observer_returns_real_files_then_reaps_without_owner_drift() {
        let proc = File::open("/proc/self").unwrap();
        let before = OwnerCredentials::read().unwrap();
        let exe = File::open("/proc/self/exe").unwrap();
        let mut reader = Observer::default();
        let started = Instant::now();
        for _ in 0..8 {
            let got = reader
                .sample_paths(
                    &proc,
                    &peer(),
                    None,
                    before.uids[0],
                    before.gids[0],
                    true,
                    c"attr/current",
                )
                .unwrap();
            assert_eq!(Node::of(&got.executable).unwrap(), Node::of(&exe).unwrap());
            assert!(!got.context.is_empty() && !got.command.is_empty());
            for (fd, name) in got.namespaces.iter().zip(["user", "pid", "mnt"]) {
                let original = File::open(format!("/proc/self/ns/{name}")).unwrap();
                assert_eq!(Node::of(fd).unwrap(), Node::of(&original).unwrap());
            }
            reader.clean().unwrap();
            assert_eq!(OwnerCredentials::read().unwrap(), before);
        }
        eprintln!(
            "frontend observer eight real clone/read/SCM/waitid operations: {:?}",
            started.elapsed()
        );
    }
    #[test]
    fn query_reader_returns_all_exact_namespaces_and_body_after_real_retirement() {
        let directory = File::open("/proc/self").unwrap();
        let before = OwnerCredentials::read().unwrap();
        let executable = File::open("/proc/self/exe").unwrap();
        let mut reader = Observer::default();
        let got = reader
            .sample_mode(
                &directory,
                &peer(),
                None,
                before.uids[0],
                before.gids[0],
                false,
                c"attr/current",
                true,
            )
            .unwrap();
        assert_eq!(
            Node::of(&got.executable).unwrap(),
            Node::of(&executable).unwrap()
        );
        assert_eq!(
            unsafe { libc::fcntl(got.executable.as_raw_fd(), libc::F_GETFL) } & libc::O_PATH,
            0
        );
        for (fd, name) in got
            .namespaces
            .iter()
            .chain(got.extra_namespaces.as_ref().unwrap())
            .zip(["user", "pid", "mnt", "ipc", "uts", "net", "cgroup"])
        {
            let actual = File::open(format!("/proc/self/ns/{name}")).unwrap();
            assert_eq!(Node::of(fd).unwrap(), Node::of(&actual).unwrap());
        }
        assert!(!got.context.is_empty() && !got.command.is_empty());
        assert!(got.environment.is_empty());
        reader.clean().unwrap();
        assert_eq!(OwnerCredentials::read().unwrap(), before);
    }
    #[test]
    fn frontend_observer_rejects_wrong_scope_ids_and_missing_metadata_and_reaps() {
        let proc = File::open("/proc/self").unwrap();
        let before = OwnerCredentials::read().unwrap();
        let wrong = File::open("/dev/null").unwrap();
        let mut reader = Observer::default();
        assert!(
            reader
                .sample_paths(
                    &proc,
                    &peer(),
                    Some(&wrong),
                    before.uids[0],
                    before.gids[0],
                    false,
                    c"attr/current"
                )
                .is_err()
        );
        assert!(
            reader
                .sample_paths(
                    &proc,
                    &peer(),
                    None,
                    before.uids[0] + 1,
                    before.gids[0],
                    false,
                    c"attr/current"
                )
                .is_err()
        );
        assert!(
            reader
                .sample_paths(
                    &proc,
                    &peer(),
                    None,
                    before.uids[0],
                    before.gids[0],
                    false,
                    c"not-a-proc-field"
                )
                .is_err()
        );
        reader.clean().unwrap();
        assert_eq!(OwnerCredentials::read().unwrap(), before);
    }
    struct TestChild(std::process::Child);
    impl Drop for TestChild {
        fn drop(&mut self) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }

    #[test]
    #[ignore = "private child used by the actual nondumpable peer test"]
    fn frontend_observer_nondumpable_child_fixture() {
        assert_eq!(
            std::env::var("DROIDLOOM_OBSERVER_PRIVATE_FIXTURE").as_deref(),
            Ok("nondumpable")
        );
        assert_eq!(unsafe { libc::prctl(libc::PR_SET_DUMPABLE, 0) }, 0);
        assert_eq!(unsafe { libc::prctl(libc::PR_GET_DUMPABLE) }, 0);
        let marker = [b'R'];
        assert_eq!(unsafe { libc::write(198, marker.as_ptr().cast(), 1) }, 1);
        let mut stop = [0_u8];
        assert_eq!(unsafe { libc::read(198, stop.as_mut_ptr().cast(), 1) }, 1);
        // The observer may never change the target's dumpable bit to admit it.
        assert_eq!(unsafe { libc::prctl(libc::PR_GET_DUMPABLE) }, 0);
        assert_eq!(stop, [b'X']);
    }

    #[test]
    fn frontend_observer_rejects_real_nondumpable_peer_without_changing_it() {
        use std::os::unix::process::CommandExt;
        use std::process::{Command, Stdio};
        let before = OwnerCredentials::read().unwrap();
        let mut sockets = [-1; 2];
        assert_eq!(
            unsafe {
                libc::socketpair(
                    libc::AF_UNIX,
                    libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                    0,
                    sockets.as_mut_ptr(),
                )
            },
            0
        );
        let parent = unsafe { OwnedFd::from_raw_fd(sockets[0]) };
        let child = unsafe { OwnedFd::from_raw_fd(sockets[1]) };
        let child_raw = child.as_raw_fd();
        let mut command = Command::new(std::env::current_exe().unwrap());
        command
            .args([
                "--ignored",
                "frontend_observer_nondumpable_child_fixture",
                "--nocapture",
            ])
            .env("DROIDLOOM_OBSERVER_PRIVATE_FIXTURE", "nondumpable")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        unsafe {
            command.pre_exec(move || {
                if libc::dup2(child_raw, 198) < 0 || libc::fcntl(198, libc::F_SETFD, 0) < 0 {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        let mut process = TestChild(command.spawn().unwrap());
        drop(child);
        let mut event = libc::pollfd {
            fd: parent.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        assert_eq!(unsafe { libc::poll(&mut event, 1, 3000) }, 1);
        let mut marker = [0_u8];
        assert_eq!(
            unsafe { libc::read(parent.as_raw_fd(), marker.as_mut_ptr().cast(), 1) },
            1
        );
        assert_eq!(marker, [b'R']);
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, process.0.id(), 0) };
        assert!(raw >= 0);
        let pidfd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
        let directory = File::open(format!("/proc/{}", process.0.id())).unwrap();
        let mut reader = Observer::default();
        let error = reader
            .sample_paths(
                &directory,
                &pidfd,
                None,
                before.uids[0],
                before.gids[0],
                true,
                c"attr/current",
            )
            .err()
            .expect("a nondumpable peer must remain unreadable");
        assert!(
            matches!(error.raw_os_error(), Some(libc::EACCES | libc::EPERM)),
            "{error}"
        );
        reader.clean().unwrap();
        assert_eq!(OwnerCredentials::read().unwrap(), before);
        let stop = [b'X'];
        assert_eq!(
            unsafe { libc::write(parent.as_raw_fd(), stop.as_ptr().cast(), 1) },
            1
        );
        assert!(process.0.wait().unwrap().success());
    }
    struct UsernsFixture {
        process: std::process::Child,
        control: OwnedFd,
        target: Option<OwnedFd>,
    }
    impl Drop for UsernsFixture {
        fn drop(&mut self) {
            unsafe {
                libc::shutdown(self.control.as_raw_fd(), libc::SHUT_RDWR);
            }
            // The raw peer observes EOF and exits; its direct parent must reap
            // it before this outer fixture process can exit successfully.
            let until = Instant::now() + Duration::from_secs(6);
            while Instant::now() < until {
                if self.process.try_wait().ok().flatten().is_some() {
                    return;
                }
                std::thread::sleep(Duration::from_millis(10));
            }
            if let Some(target) = &self.target {
                unsafe {
                    libc::syscall(
                        libc::SYS_pidfd_send_signal,
                        target.as_raw_fd(),
                        libc::SIGKILL,
                        std::ptr::null::<libc::siginfo_t>(),
                        0,
                    );
                }
            }
            let until = Instant::now() + Duration::from_secs(2);
            while Instant::now() < until {
                if self.process.try_wait().ok().flatten().is_some() {
                    return;
                }
                std::thread::sleep(Duration::from_millis(10));
            }
            let _ = self.process.kill();
            let _ = self.process.wait();
        }
    }

    #[test]
    #[ignore = "private user-namespace peer used only by the privileged observer test"]
    fn frontend_observer_userns_peer_fixture() {
        let mode = std::env::var("DROIDLOOM_OBSERVER_PRIVATE_FIXTURE").unwrap();
        let (uid, dumpable) = match mode.as_str() {
            "userns-composer-readable" => (1000_u32, 1_i32),
            "userns-composer-nondumpable" => (1000, 0),
            "userns-input-readable" => (0, 1),
            "userns-input-nondumpable" => (0, 0),
            _ => panic!("not a private user namespace fixture"),
        };
        assert_eq!(unsafe { libc::getuid() }, 0);
        let namespace = File::open("/proc/self/ns/user").unwrap();
        let channel = unsafe { OwnedFd::from_raw_fd(198) };
        let mut readiness = [-1; 2];
        assert_eq!(
            unsafe { libc::pipe2(readiness.as_mut_ptr(), libc::O_CLOEXEC) },
            0
        );
        let ready_read = unsafe { OwnedFd::from_raw_fd(readiness[0]) };
        let ready_write = unsafe { OwnedFd::from_raw_fd(readiness[1]) };
        let header = [0x20080522_u32, 0];
        let capabilities = reader_capabilities(true, uid);
        let mut actual = [0_u32; 6];
        let parent = unsafe { libc::getpid() };
        let target = unsafe { libc::syscall(libc::SYS_fork) };
        assert!(target >= 0);
        if target == 0 {
            // Only raw, preallocated operations after fork. This is a single
            // real task, so capset and PIDFD credentials describe the same task.
            unsafe {
                libc::close(ready_read.as_raw_fd());
                if libc::prctl(libc::PR_SET_KEEPCAPS, 1) != 0
                    || libc::syscall(libc::SYS_setresgid, uid, uid, uid) != 0
                    || libc::syscall(libc::SYS_setresuid, uid, uid, uid) != 0
                    || libc::syscall(libc::SYS_capset, header.as_ptr(), capabilities.as_ptr()) != 0
                    || libc::syscall(libc::SYS_capget, header.as_ptr(), actual.as_mut_ptr()) != 0
                    || actual != capabilities
                    || libc::prctl(libc::PR_SET_DUMPABLE, dumpable) != 0
                    || libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
                    || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0
                    || libc::getppid() != parent
                {
                    libc::_exit(120);
                }
                let marker = [b'R'];
                if libc::write(ready_write.as_raw_fd(), marker.as_ptr().cast(), 1) != 1 {
                    libc::_exit(121);
                }
                libc::close(ready_write.as_raw_fd());
                let mut poll = libc::pollfd {
                    fd: 198,
                    events: libc::POLLIN,
                    revents: 0,
                };
                let mut stop = [0_u8];
                let ready = libc::poll(&mut poll, 1, 5000);
                let received = if ready > 0 {
                    libc::read(198, stop.as_mut_ptr().cast(), 1)
                } else {
                    -1
                };
                if libc::prctl(libc::PR_GET_DUMPABLE) != dumpable
                    || libc::syscall(libc::SYS_capget, header.as_ptr(), actual.as_mut_ptr()) != 0
                    || actual != capabilities
                {
                    libc::_exit(122);
                }
                libc::_exit(if received == 1 && stop == [b'X'] {
                    0
                } else {
                    123
                });
            }
        }
        drop(ready_write);
        let mut marker = [0_u8];
        let ready = unsafe { libc::read(ready_read.as_raw_fd(), marker.as_mut_ptr().cast(), 1) };
        if ready != 1 || marker != [b'R'] {
            let mut status = 0;
            unsafe {
                libc::waitpid(target as i32, &mut status, 0);
            }
            panic!("private userns peer setup failed: status={status}");
        }
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, target, 0) };
        assert!(raw >= 0);
        let target_fd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
        wire::send(
            &channel,
            &wire::Record {
                kind: wire::GRANT,
                nonce: [0x39; 16],
                pid: target as u32,
                uid,
                gid: dumpable as u32,
                fds: vec![namespace.into(), target_fd],
            },
        )
        .unwrap();
        let mut status = 0;
        assert_eq!(
            unsafe { libc::waitpid(target as i32, &mut status, 0) },
            target as i32
        );
        assert_eq!(status, 0, "actual peer must exit cleanly and be reaped");
    }

    #[test]
    #[ignore = "requires a frozen test ELF and private privileged user namespace fixture"]
    fn frontend_observer_userns_scope_drops_ptrace_before_reading_nondumpable_peer() {
        use std::os::unix::process::CommandExt;
        use std::process::{Command, Stdio};
        assert_eq!(unsafe { libc::geteuid() }, 0);
        let before = OwnerCredentials::read().unwrap();
        for (mode, uid, readable) in [
            ("userns-composer-readable", 1000_u32, true),
            ("userns-composer-nondumpable", 1000, false),
            ("userns-input-readable", 0, true),
            ("userns-input-nondumpable", 0, false),
        ] {
            let mut sockets = [-1; 2];
            assert_eq!(
                unsafe {
                    libc::socketpair(
                        libc::AF_UNIX,
                        libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                        0,
                        sockets.as_mut_ptr(),
                    )
                },
                0
            );
            let parent = unsafe { OwnedFd::from_raw_fd(sockets[0]) };
            let child = unsafe { OwnedFd::from_raw_fd(sockets[1]) };
            let executable = File::open(std::env::current_exe().unwrap()).unwrap();
            let child_raw = child.as_raw_fd();
            let executable_raw = executable.as_raw_fd();
            let mut command = Command::new("/usr/bin/unshare");
            command.args([
                "--user", "--map-users=0:1000000000:65536", "--map-groups=0:1000000000:65536",
                "--setuid=0", "--setgid=0", "/proc/self/fd/197", "--ignored", "--exact",
                "production_selection::early_generation::lifecycle::frontend::observation::tests::frontend_observer_userns_peer_fixture",
                "--nocapture",
            ]).env("DROIDLOOM_OBSERVER_PRIVATE_FIXTURE", mode)
                .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::inherit());
            unsafe {
                command.pre_exec(move || {
                    if libc::setpgid(0, 0) != 0
                        || libc::dup2(executable_raw, 197) < 0
                        || libc::dup2(child_raw, 198) < 0
                        || libc::fcntl(197, libc::F_SETFD, 0) < 0
                        || libc::fcntl(198, libc::F_SETFD, 0) < 0
                    {
                        return Err(io::Error::last_os_error());
                    }
                    Ok(())
                });
            }
            let mut fixture = UsernsFixture {
                process: command.spawn().unwrap(),
                control: parent,
                target: None,
            };
            drop(child);
            let mut event = libc::pollfd {
                fd: fixture.control.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            assert_eq!(unsafe { libc::poll(&mut event, 1, 3000) }, 1);
            let mut transfer = wire::receive(&fixture.control)
                .unwrap()
                .expect("real userns target descriptors");
            wire::reply(&transfer, wire::GRANT, [0x39; 16]).unwrap();
            assert_eq!((transfer.uid, transfer.gid), (uid, u32::from(readable)));
            fixture.target = Some(transfer.fds.pop().unwrap());
            let namespace = File::from(transfer.fds.pop().unwrap());
            let target = fixture.target.as_ref().unwrap();
            let info = wire::pid_info(target).unwrap();
            assert_eq!(info.pid, transfer.pid);
            assert_eq!(info.ppid, fixture.process.id());
            wire::exact_ids(&info, 1000000000 + uid, 1000000000 + uid).unwrap();
            let directory = File::open(format!("/proc/{}", info.pid)).unwrap();
            let mut reader = Observer::default();
            let result = reader.sample_paths(
                &directory,
                target,
                Some(&namespace),
                uid,
                uid,
                true,
                c"attr/current",
            );
            if readable {
                assert!(result.is_ok(), "{mode}: {:?}", result.err());
            } else {
                let error = result
                    .err()
                    .expect("setns must not grant a dumpable bypass");
                assert!(
                    matches!(error.raw_os_error(), Some(libc::EACCES | libc::EPERM)),
                    "{mode}: {error}"
                );
            }
            reader.clean().unwrap();
            assert_eq!(OwnerCredentials::read().unwrap(), before);
            let stop = [b'X'];
            assert_eq!(
                unsafe { libc::write(fixture.control.as_raw_fd(), stop.as_ptr().cast(), 1) },
                1
            );
            assert!(fixture.process.wait().unwrap().success());
            eprintln!(
                "{mode}: actual original userns, exact target caps, observer capset/readback, unchanged target dumpable, real child wait/reap passed"
            );
        }
    }
}
