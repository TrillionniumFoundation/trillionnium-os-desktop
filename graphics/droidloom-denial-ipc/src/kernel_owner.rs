//! Bind the native task-control ingress to the original Denial owner.
//!
//! Its short-lived namespace connector is the connection creator. Every actual
//! request is separately authenticated using SCM_PIDFD and SCM_CREDENTIALS from
//! the current sender. An ancestor PID may be invisible (zero); its real pidfs
//! inode and lifetime remain authoritative, without PID lookup or UID fallback.
use crate::kernel_caller::{alive, context, identity, peer_pidfd};
use crate::{SeqPacket, SeqPacketListener};
use std::io;
use std::mem;
use std::os::fd::{AsFd, AsRawFd, FromRawFd, OwnedFd};
use std::sync::Arc;
use std::time::{Duration, Instant};

const BROKER: &[u8] = b"u:r:droidloom_broker:s0";
const SO_PASSPIDFD: i32 = 76;
const SCM_PIDFD: i32 = 4;
const OVERFLOW_ID: u32 = 65534;
const MAX_BYTES: usize = 65536;

fn need(value: bool, message: &str) -> io::Result<()> {
    if value {
        Ok(())
    } else {
        Err(io::Error::new(io::ErrorKind::PermissionDenied, message))
    }
}
fn cv(value: i32) -> io::Result<i32> {
    if value < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(value)
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Credentials {
    pid: i32,
    uid: u32,
    gid: u32,
}
fn credentials(fd: &OwnedFd) -> io::Result<Credentials> {
    let mut value: libc::ucred = unsafe { mem::zeroed() };
    let mut length = mem::size_of_val(&value) as libc::socklen_t;
    cv(unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut value as *mut libc::ucred).cast(),
            &mut length,
        )
    })?;
    need(
        length as usize == mem::size_of_val(&value) && value.pid >= 0,
        "owner kernel credential shape",
    )?;
    Ok(Credentials {
        pid: value.pid,
        uid: value.uid,
        gid: value.gid,
    })
}
fn enable(fd: impl AsFd) -> io::Result<()> {
    let one = 1_i32;
    for option in [libc::SO_PASSCRED, SO_PASSPIDFD] {
        cv(unsafe {
            libc::setsockopt(
                fd.as_fd().as_raw_fd(),
                libc::SOL_SOCKET,
                option,
                (&one as *const i32).cast(),
                mem::size_of_val(&one) as u32,
            )
        })?;
    }
    Ok(())
}
fn connected(fd: &OwnedFd) -> io::Result<()> {
    let mut state = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLRDHUP,
        revents: 0,
    };
    need(
        cv(unsafe { libc::poll(&mut state, 1, 0) })? == 0,
        "original Denial owner connection was revoked",
    )
}

/// Original native owner observed on the already connected Denial endpoint.
pub struct KernelOwner {
    socket: OwnedFd,
    pidfd: OwnedFd,
    node: (u64, u64),
    credentials: Credentials,
    context: Vec<u8>,
}
impl KernelOwner {
    /// Enable actual per-message sender identity before the listener is exposed.
    /// Accepted sockets inherit these kernel flags.
    pub fn prepare_listener(listener: &SeqPacketListener) -> io::Result<()> {
        enable(listener)
    }
    /// Pin the original ancestor owner. The selected subordinate maps do not
    /// contain host root, and its host PID is outside Android's PID namespace.
    pub fn acquire(denial: &SeqPacket) -> io::Result<Self> {
        Self::acquire_exact(
            denial,
            Credentials {
                pid: 0,
                uid: OVERFLOW_ID,
                gid: OVERFLOW_ID,
            },
            BROKER,
        )
    }
    fn acquire_exact(denial: &SeqPacket, expected: Credentials, label: &[u8]) -> io::Result<Self> {
        let socket = denial.as_fd().try_clone_to_owned()?;
        need(
            credentials(&socket)? == expected && context(&socket)? == label,
            "Denial endpoint is not the original native owner role",
        )?;
        let pidfd = peer_pidfd(&socket)?;
        let value = Self {
            node: identity(&pidfd)?,
            socket,
            pidfd,
            credentials: expected,
            context: label.to_vec(),
        };
        value.revalidate()?;
        Ok(value)
    }
    /// Revalidate the same live owner and original connection. No protocol data
    /// are read from Denial, and no external PID or receipt can replace the pin.
    pub fn revalidate(&self) -> io::Result<()> {
        alive(&self.pidfd)?;
        let current = peer_pidfd(&self.socket)?;
        need(
            identity(&current)? == self.node
                && identity(&self.pidfd)? == self.node
                && credentials(&self.socket)? == self.credentials
                && context(&self.socket)? == self.context,
            "original native owner identity changed",
        )?;
        connected(&self.socket)?;
        alive(&self.pidfd)
    }
    /// Admit only the fixed connector role. Its actual PIDFD may already be
    /// exited; the live request sender must still be this original owner.
    pub fn accept(self: &Arc<Self>, socket: &SeqPacket) -> io::Result<OwnerSession> {
        self.accept_exact(
            socket,
            Credentials {
                pid: 0,
                uid: 1000,
                gid: 1000,
            },
            BROKER,
        )
    }
    fn accept_exact(
        self: &Arc<Self>,
        socket: &SeqPacket,
        creator: Credentials,
        label: &[u8],
    ) -> io::Result<OwnerSession> {
        self.revalidate()?;
        let fd = socket.as_fd().try_clone_to_owned()?;
        need(
            credentials(&fd)? == creator && context(&fd)? == label,
            "task connection was not created by the fixed native connector",
        )?;
        enable(&fd)?;
        socket.set_nonblocking(true).map_err(io::Error::other)?;
        Ok(OwnerSession {
            socket: fd,
            owner: Arc::clone(self),
            creator,
            context: label.to_vec(),
        })
    }
}

/// One task channel; every record is authorized before codec parsing.
pub struct OwnerSession {
    socket: OwnedFd,
    owner: Arc<KernelOwner>,
    creator: Credentials,
    context: Vec<u8>,
}
impl OwnerSession {
    /// Check the immutable connector identity and current original owner.
    pub fn revalidate(&self) -> io::Result<()> {
        self.owner.revalidate()?;
        need(
            credentials(&self.socket)? == self.creator && context(&self.socket)? == self.context,
            "native connector connection identity changed",
        )
    }
    /// Receive a finite record from the exact original owner. The kernel PIDFD
    /// and credentials belong to this packet, not the retired connector.
    pub fn receive(&self, limit: usize) -> io::Result<Vec<u8>> {
        need(limit > 0 && limit <= MAX_BYTES, "native owner record bound")?;
        let deadline = Instant::now() + Duration::from_secs(120);
        loop {
            self.revalidate()?;
            let left = deadline
                .checked_duration_since(Instant::now())
                .ok_or_else(|| {
                    io::Error::new(io::ErrorKind::TimedOut, "native task channel idle deadline")
                })?;
            let mut events = [
                libc::pollfd {
                    fd: self.socket.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.owner.pidfd.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.owner.socket.as_raw_fd(),
                    events: libc::POLLRDHUP,
                    revents: 0,
                },
            ];
            let rc = unsafe {
                libc::poll(
                    events.as_mut_ptr(),
                    events.len() as libc::nfds_t,
                    left.as_millis().min(100) as i32,
                )
            };
            if rc < 0 {
                if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(io::Error::last_os_error());
            }
            self.revalidate()?;
            if events[0].revents == 0 {
                continue;
            }
            match receive_packet(&self.socket, limit) {
                Err(error)
                    if matches!(
                        error.kind(),
                        io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                    ) =>
                {
                    continue;
                }
                Err(error) => return Err(error),
                Ok((bytes, sender, cred)) => {
                    need(
                        identity(&sender)? == self.owner.node
                            && Credentials {
                                pid: cred.pid,
                                uid: cred.uid,
                                gid: cred.gid,
                            } == self.owner.credentials,
                        "task record was sent by a different process or credential epoch",
                    )?;
                    alive(&sender)?;
                    self.revalidate()?;
                    return Ok(bytes);
                }
            }
        }
    }
}
#[repr(C, align(8))]
struct Control([u8; 256]);
fn receive_packet(socket: &OwnedFd, limit: usize) -> io::Result<(Vec<u8>, OwnedFd, libc::ucred)> {
    let mut data = vec![0; limit];
    let mut control = Control([0; 256]);
    let mut iov = libc::iovec {
        iov_base: data.as_mut_ptr().cast(),
        iov_len: data.len(),
    };
    let mut message: libc::msghdr = unsafe { mem::zeroed() };
    message.msg_iov = &mut iov;
    message.msg_iovlen = 1;
    message.msg_control = control.0.as_mut_ptr().cast();
    message.msg_controllen = control.0.len();
    let count = unsafe {
        libc::recvmsg(
            socket.as_raw_fd(),
            &mut message,
            libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error());
    }
    let mut sender = None;
    let mut credentials = None;
    let mut forbidden = Vec::new();
    let mut invalid = false;
    let mut header = unsafe { libc::CMSG_FIRSTHDR(&message) };
    while !header.is_null() {
        let base = unsafe { libc::CMSG_LEN(0) } as usize;
        let length = unsafe { (*header).cmsg_len };
        let offset = header as usize - message.msg_control as usize;
        if length < base
            || offset
                .checked_add(length)
                .is_none_or(|n| n > message.msg_controllen)
        {
            invalid = true;
            break;
        }
        let bytes = length - base;
        let body = unsafe { libc::CMSG_DATA(header) };
        match unsafe { ((*header).cmsg_level, (*header).cmsg_type) } {
            (libc::SOL_SOCKET, SCM_PIDFD) if bytes == mem::size_of::<i32>() => {
                let raw = unsafe { std::ptr::read_unaligned(body.cast::<i32>()) };
                if raw < 0 {
                    invalid = true;
                } else {
                    let fd = unsafe { OwnedFd::from_raw_fd(raw) };
                    if sender.is_some() {
                        forbidden.push(fd);
                        invalid = true;
                    } else {
                        sender = Some(fd);
                    }
                }
            }
            (libc::SOL_SOCKET, libc::SCM_RIGHTS) => {
                invalid = true;
                for i in 0..bytes / mem::size_of::<i32>() {
                    let raw = unsafe { std::ptr::read_unaligned(body.cast::<i32>().add(i)) };
                    if raw >= 0 {
                        forbidden.push(unsafe { OwnedFd::from_raw_fd(raw) });
                    }
                }
            }
            (libc::SOL_SOCKET, libc::SCM_CREDENTIALS)
                if bytes == mem::size_of::<libc::ucred>() && credentials.is_none() =>
            {
                credentials = Some(unsafe { std::ptr::read_unaligned(body.cast::<libc::ucred>()) });
            }
            _ => invalid = true,
        }
        header = unsafe { libc::CMSG_NXTHDR(&message, header) };
    }
    need(
        !invalid
            && count > 0
            && count as usize <= limit
            && message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) == 0,
        "task record carried truncated, duplicate or forbidden ancillary data",
    )?;
    let sender = sender.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::PermissionDenied,
            "task record lacks kernel sender PIDFD",
        )
    })?;
    need(
        cv(unsafe { libc::fcntl(sender.as_raw_fd(), libc::F_GETFD) })? & libc::FD_CLOEXEC != 0,
        "sender PIDFD is not close-on-exec",
    )?;
    let credentials = credentials.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::PermissionDenied,
            "task record lacks kernel sender credentials",
        )
    })?;
    data.truncate(count as usize);
    Ok((data, sender, credentials))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn own() -> Credentials {
        unsafe {
            Credentials {
                pid: libc::getpid(),
                uid: libc::getuid(),
                gid: libc::getgid(),
            }
        }
    }
    fn owner() -> (Arc<KernelOwner>, SeqPacket) {
        let (left, right) = SeqPacket::pair().unwrap();
        let label = context(&left.as_fd().try_clone_to_owned().unwrap()).unwrap();
        (
            Arc::new(KernelOwner::acquire_exact(&left, own(), &label).unwrap()),
            right,
        )
    }
    fn session(owner: &Arc<KernelOwner>) -> (OwnerSession, SeqPacket) {
        let (left, right) = SeqPacket::pair().unwrap();
        let label = context(&left.as_fd().try_clone_to_owned().unwrap()).unwrap();
        (owner.accept_exact(&left, own(), &label).unwrap(), right)
    }
    #[test]
    fn kernel_owner_authenticates_each_real_packet_and_revokes_original_connection() {
        let (owner, lifetime) = owner();
        let (channel, sender) = session(&owner);
        sender.send_record(b"actual owner", &[]).unwrap();
        assert_eq!(channel.receive(64).unwrap(), b"actual owner");
        unsafe {
            libc::shutdown(lifetime.as_fd().as_raw_fd(), libc::SHUT_RDWR);
        }
        assert!(channel.revalidate().is_err());
    }
    #[test]
    fn kernel_owner_rejects_extra_fds_truncation_and_uid_only_admission() {
        let (owner, _life) = owner();
        let (channel, sender) = session(&owner);
        let file = std::fs::File::open("/dev/null").unwrap();
        sender
            .send_record(b"bad", &[file.as_fd(), file.as_fd()])
            .unwrap();
        assert!(channel.receive(64).is_err());
        let (channel, sender) = session(&owner);
        sender.send_record(&[1; 65], &[]).unwrap();
        assert!(channel.receive(64).is_err());
        let (left, _right) = SeqPacket::pair().unwrap();
        assert!(owner.accept(&left).is_err());
        assert!(KernelOwner::acquire(&left).is_err());
    }

    #[test]
    #[ignore = "entered only by the isolated cross-PID-namespace test"]
    fn kernel_owner_invisible_parent_fixture() {
        if std::env::var_os("DROIDLOOM_OWNER_PIDNS_FIXTURE").is_none() {
            return;
        }
        assert_eq!(unsafe { libc::getpid() }, 1);
        let denial = SeqPacket::from_owned_fd(unsafe { OwnedFd::from_raw_fd(198) }).unwrap();
        let data = SeqPacket::from_owned_fd(unsafe { OwnedFd::from_raw_fd(199) }).unwrap();
        let label = context(&denial.as_fd().try_clone_to_owned().unwrap()).unwrap();
        let invisible = Credentials {
            pid: 0,
            uid: OVERFLOW_ID,
            gid: OVERFLOW_ID,
        };
        let owner = Arc::new(KernelOwner::acquire_exact(&denial, invisible, &label).unwrap());
        let channel = owner.accept_exact(&data, invisible, &label).unwrap();
        // This is deliberately not an identity fallback: the expected kernel
        // API refuses PID details for the ancestor, while its original FD is
        // still checked by inode/poll and every message's kernel sender PIDFD.
        let mut info = [0u64; 8];
        info[0] = 3;
        let rc = unsafe {
            libc::ioctl(
                owner.pidfd.as_raw_fd(),
                0xc040ff0b as libc::c_ulong,
                info.as_mut_ptr(),
            )
        };
        assert_eq!(rc, -1);
        assert_eq!(
            io::Error::last_os_error().raw_os_error(),
            Some(libc::EREMOTE)
        );
        denial.send_record(b"ready", &[]).unwrap();
        assert_eq!(channel.receive(64).unwrap(), b"original ancestor");
        denial
            .send_record(b"bound-original-invisible-pidfd", &[])
            .unwrap();
    }
    #[test]
    #[ignore = "requires an isolated privileged namespace fixture; run by exact filter"]
    fn kernel_owner_cross_pid_namespace_preserves_invisible_sender_pidfd() {
        use std::os::unix::process::CommandExt;
        use std::process::{Child, Command, Stdio};
        assert_eq!(
            unsafe { libc::getuid() },
            0,
            "this explicit fixture requires root solely to create isolated namespaces"
        );
        struct Reap(Child);
        impl Drop for Reap {
            fn drop(&mut self) {
                unsafe {
                    libc::kill(-(self.0.id() as i32), libc::SIGKILL);
                }
                let _ = self.0.kill();
                let _ = self.0.wait();
            }
        }
        let (denial_parent, denial_child) = SeqPacket::pair().unwrap();
        let (data_parent, data_child) = SeqPacket::pair().unwrap();
        let executable = std::fs::File::open(std::env::current_exe().unwrap()).unwrap();
        let program = executable.as_raw_fd();
        let denial = denial_child.as_fd().as_raw_fd();
        let data = data_child.as_fd().as_raw_fd();
        let mut command = Command::new("/usr/bin/unshare");
        command
            .args([
                "--user",
                "--map-users=0:1000000000:65536",
                "--map-groups=0:1000000000:65536",
                "--setuid=0",
                "--setgid=0",
                "--pid",
                "--fork",
                "/proc/self/fd/197",
                "--ignored",
                "--exact",
                "kernel_owner::tests::kernel_owner_invisible_parent_fixture",
                "--nocapture",
            ])
            .env("DROIDLOOM_OWNER_PIDNS_FIXTURE", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit());
        unsafe {
            command.pre_exec(move || {
                if libc::setpgid(0, 0) != 0
                    || libc::dup2(program, 197) != 197
                    || libc::dup2(denial, 198) != 198
                    || libc::dup2(data, 199) != 199
                    || libc::fcntl(197, libc::F_SETFD, 0) != 0
                    || libc::fcntl(198, libc::F_SETFD, 0) != 0
                    || libc::fcntl(199, libc::F_SETFD, 0) != 0
                {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        let mut child = Reap(command.spawn().unwrap());
        drop(denial_child);
        drop(data_child);
        for expected in [b"ready".as_slice(), b"bound-original-invisible-pidfd"] {
            let mut poll = libc::pollfd {
                fd: denial_parent.as_fd().as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            assert_eq!(unsafe { libc::poll(&mut poll, 1, 10_000) }, 1);
            let record = denial_parent.receive_record().unwrap();
            assert!(record.descriptors.is_empty());
            assert_eq!(record.bytes, expected);
            if expected == b"ready" {
                data_parent.send_record(b"original ancestor", &[]).unwrap();
            }
        }
        assert!(child.0.wait().unwrap().success());
        println!(
            "actual invisible ancestor PID=0, UID/GID=65534, PIDFD_GET_INFO=EREMOTE; SO_PEERPIDFD inode equals per-message SCM_PIDFD and live original owner accepted"
        );
    }

    fn fixture(mode: &str, control: &SeqPacket) -> std::process::Child {
        use std::os::unix::process::CommandExt;
        let raw = control.as_fd().as_raw_fd();
        let mut command = std::process::Command::new(std::env::current_exe().unwrap());
        command
            .args([
                "--ignored",
                "--exact",
                "kernel_owner::tests::kernel_owner_process_fixture",
                "--nocapture",
            ])
            .env("DROIDLOOM_OWNER_PROCESS_FIXTURE", mode)
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::inherit());
        unsafe {
            command.pre_exec(move || {
                if libc::dup2(raw, 199) != 199 || libc::fcntl(199, libc::F_SETFD, 0) != 0 {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        command.spawn().unwrap()
    }
    struct Reaped(std::process::Child);
    impl Drop for Reaped {
        fn drop(&mut self) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
    fn bounded(socket: &SeqPacket) -> crate::RawRecord {
        let mut p = libc::pollfd {
            fd: socket.as_fd().as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        assert_eq!(unsafe { libc::poll(&mut p, 1, 10_000) }, 1);
        socket.receive_record().unwrap()
    }
    #[test]
    #[ignore = "private child process used by actual sender and lifetime tests"]
    fn kernel_owner_process_fixture() {
        let Some(mode) = std::env::var_os("DROIDLOOM_OWNER_PROCESS_FIXTURE") else {
            return;
        };
        let control = SeqPacket::from_owned_fd(unsafe { OwnedFd::from_raw_fd(199) }).unwrap();
        if mode == "forward" {
            let mut message = bounded(&control);
            let data = SeqPacket::from_owned_fd(message.descriptors.pop().unwrap()).unwrap();
            data.send_record(b"forwarded", &[]).unwrap();
            return;
        }
        let (left, right) = SeqPacket::pair().unwrap();
        if mode == "connector" {
            control
                .send_record(b"connector", &[left.as_fd(), right.as_fd()])
                .unwrap();
            return;
        }
        assert_eq!(mode, "owner");
        let (data, sender) = SeqPacket::pair().unwrap();
        control
            .send_record(
                b"owner",
                &[left.as_fd(), right.as_fd(), data.as_fd(), sender.as_fd()],
            )
            .unwrap();
        assert_eq!(bounded(&control).bytes, b"send");
        sender.send_record(b"original live owner", &[]).unwrap();
        let _ = control.receive_record();
    }
    #[test]
    fn kernel_owner_rejects_forwarded_connection_from_another_real_process() {
        let (owner, _life) = owner();
        let (channel, sender) = session(&owner);
        let (control, child_control) = SeqPacket::pair().unwrap();
        let mut child = Reaped(fixture("forward", &child_control));
        drop(child_control);
        control.send_record(b"send", &[sender.as_fd()]).unwrap();
        assert!(channel.receive(64).is_err());
        assert!(child.0.wait().unwrap().success());
    }
    #[test]
    fn kernel_owner_accepts_actual_owner_after_connector_is_reaped() {
        let (owner, _life) = owner();
        let (control, child_control) = SeqPacket::pair().unwrap();
        let mut connector = Reaped(fixture("connector", &child_control));
        drop(child_control);
        let mut record = bounded(&control);
        assert_eq!(record.bytes, b"connector");
        assert_eq!(record.descriptors.len(), 2);
        let sender = SeqPacket::from_owned_fd(record.descriptors.pop().unwrap()).unwrap();
        let receiver = SeqPacket::from_owned_fd(record.descriptors.pop().unwrap()).unwrap();
        assert!(connector.0.wait().unwrap().success());
        let raw = receiver.as_fd().try_clone_to_owned().unwrap();
        let creator = credentials(&raw).unwrap();
        assert_eq!(creator.pid, connector.0.id() as i32);
        let label = context(&raw).unwrap();
        let channel = owner.accept_exact(&receiver, creator, &label).unwrap();
        sender
            .send_record(b"owner after real connector retirement", &[])
            .unwrap();
        assert_eq!(
            channel.receive(64).unwrap(),
            b"owner after real connector retirement"
        );
    }
    #[test]
    fn kernel_owner_rejects_dead_owner_even_when_both_denial_endpoints_survive() {
        let (control, child_control) = SeqPacket::pair().unwrap();
        let mut child = Reaped(fixture("owner", &child_control));
        drop(child_control);
        let mut record = bounded(&control);
        assert_eq!(record.bytes, b"owner");
        assert_eq!(record.descriptors.len(), 4);
        let _forwarded_sender = record.descriptors.pop().unwrap();
        let data = SeqPacket::from_owned_fd(record.descriptors.pop().unwrap()).unwrap();
        let _lifetime = record.descriptors.pop().unwrap();
        let denial = SeqPacket::from_owned_fd(record.descriptors.pop().unwrap()).unwrap();
        let raw = denial.as_fd().try_clone_to_owned().unwrap();
        let actual = credentials(&raw).unwrap();
        assert_eq!(actual.pid, child.0.id() as i32);
        let label = context(&raw).unwrap();
        let owner = Arc::new(KernelOwner::acquire_exact(&denial, actual, &label).unwrap());
        let channel = owner.accept_exact(&data, actual, &label).unwrap();
        control.send_record(b"send", &[]).unwrap();
        assert_eq!(channel.receive(64).unwrap(), b"original live owner");
        child.0.kill().unwrap();
        assert!(!child.0.wait().unwrap().success());
        connected(&owner.socket).unwrap();
        assert!(owner.revalidate().is_err());
        assert!(channel.revalidate().is_err());
    }
}
