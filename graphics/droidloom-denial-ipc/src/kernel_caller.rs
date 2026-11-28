//! Kernel-bound identity for a synchronous Binder caller's unnamed socketpair.
//!
//! No bytes are read from the proof socket. The descriptor only supplies kernel
//! credentials, the peer security context and a live, retained peer PIDFD.

use std::io;
use std::mem;
use std::os::fd::{AsFd, AsRawFd, FromRawFd, OwnedFd};
use std::time::{Duration, Instant};

const SO_PEERPIDFD: i32 = 77;
const PIDFD_GET_INFO: libc::c_ulong = 0xc040ff0b;

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
fn option(fd: &OwnedFd, name: i32) -> io::Result<i32> {
    let mut value = 0_i32;
    let mut size = mem::size_of_val(&value) as libc::socklen_t;
    // SAFETY: both output locations are live and have their advertised sizes.
    cv(unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            name,
            (&mut value as *mut i32).cast(),
            &mut size,
        )
    })?;
    need(
        size as usize == mem::size_of_val(&value),
        "kernel socket option size",
    )?;
    Ok(value)
}
pub(crate) fn identity(fd: &OwnedFd) -> io::Result<(u64, u64)> {
    let mut st: libc::stat = unsafe { mem::zeroed() };
    // SAFETY: the descriptor is held and st is a live stat buffer.
    cv(unsafe { libc::fstat(fd.as_raw_fd(), &mut st) })?;
    Ok((st.st_dev, st.st_ino))
}
pub(crate) fn context(fd: &OwnedFd) -> io::Result<Vec<u8>> {
    let mut bytes = [0_u8; 256];
    let mut size = bytes.len() as libc::socklen_t;
    // SAFETY: bytes is a writable buffer of the exact supplied size.
    cv(unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERSEC,
            bytes.as_mut_ptr().cast(),
            &mut size,
        )
    })?;
    need(
        size > 0 && size as usize <= bytes.len(),
        "kernel peer context bound",
    )?;
    Ok(bytes[..size as usize]
        .strip_suffix(&[0])
        .unwrap_or(&bytes[..size as usize])
        .to_vec())
}
fn credentials(fd: &OwnedFd) -> io::Result<libc::ucred> {
    let mut value: libc::ucred = unsafe { mem::zeroed() };
    let mut size = mem::size_of_val(&value) as libc::socklen_t;
    // SAFETY: the two output locations have the advertised sizes.
    cv(unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut value as *mut libc::ucred).cast(),
            &mut size,
        )
    })?;
    need(
        size as usize == mem::size_of_val(&value) && value.pid > 1,
        "kernel peer credentials",
    )?;
    Ok(value)
}
pub(crate) fn peer_pidfd(socket: &OwnedFd) -> io::Result<OwnedFd> {
    let mut raw = -1_i32;
    let mut size = mem::size_of_val(&raw) as libc::socklen_t;
    // SAFETY: both live outputs have the exact supplied lengths.
    cv(unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            SO_PEERPIDFD,
            (&mut raw as *mut i32).cast(),
            &mut size,
        )
    })?;
    need(raw >= 0, "kernel supplied no peer PIDFD")?;
    // Own the returned descriptor before checking any other output field.
    // SAFETY: successful SO_PEERPIDFD returned a fresh owned descriptor.
    let fd = unsafe { OwnedFd::from_raw_fd(raw) };
    need(
        size as usize == mem::size_of_val(&raw),
        "kernel peer PIDFD size",
    )?;
    // SAFETY: F_GETFD observes only this held descriptor.
    need(
        cv(unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFD) })? & libc::FD_CLOEXEC != 0,
        "peer PIDFD is not close-on-exec",
    )?;
    Ok(fd)
}
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
    exit_code: i32,
}
pub(crate) fn alive(fd: &OwnedFd) -> io::Result<()> {
    let mut event = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    // SAFETY: event is the one poll entry and timeout is nonblocking.
    need(
        cv(unsafe { libc::poll(&mut event, 1, 0) })? == 0,
        "original Binder caller exited or its PIDFD is invalid",
    )
}
fn info(fd: &OwnedFd) -> io::Result<PidInfo> {
    alive(fd)?;
    let mut value = PidInfo {
        mask: 3,
        ..Default::default()
    };
    // Bionic uses an int ioctl request while glibc uses unsigned long. The
    // fixed request occupies 32 bits; preserve that bit pattern for either ABI.
    // SAFETY: PIDFD_GET_INFO with the pinned 64-byte ABI writes this live buffer.
    cv(unsafe { libc::ioctl(fd.as_raw_fd(), PIDFD_GET_INFO as _, &mut value) })?;
    need(
        value.mask & 3 == 3 && value.pid > 1 && value.pid == value.tgid,
        "kernel PIDFD identity fields",
    )?;
    alive(fd)?;
    Ok(value)
}
fn shape(fd: &OwnedFd) -> io::Result<()> {
    need(
        option(fd, libc::SO_TYPE)? == libc::SOCK_SEQPACKET
            && option(fd, libc::SO_DOMAIN)? == libc::AF_UNIX
            && option(fd, libc::SO_ACCEPTCONN)? == 0,
        "proof must be a connected Unix seqpacket socketpair",
    )?;
    // Both endpoints of a real socketpair are unnamed. A pathname or abstract
    // listener/accepted connection cannot substitute a service-created socket.
    for peer in [false, true] {
        let mut address: libc::sockaddr_un = unsafe { mem::zeroed() };
        let mut size = mem::size_of_val(&address) as libc::socklen_t;
        // SAFETY: address and size are live outputs of the correct declared size.
        let rc = unsafe {
            if peer {
                libc::getpeername(
                    fd.as_raw_fd(),
                    (&mut address as *mut libc::sockaddr_un).cast(),
                    &mut size,
                )
            } else {
                libc::getsockname(
                    fd.as_raw_fd(),
                    (&mut address as *mut libc::sockaddr_un).cast(),
                    &mut size,
                )
            }
        };
        cv(rc)?;
        need(
            size as usize == mem::size_of::<libc::sa_family_t>()
                && address.sun_family == libc::AF_UNIX as libc::sa_family_t,
            "proof is not an unnamed socketpair",
        )?;
    }
    Ok(())
}

/// An original synchronous Binder caller, pinned by its actual kernel PIDFD.
/// The peer must keep its silent socketpair endpoint open for the channel's life.
pub struct KernelCaller {
    socket: OwnedFd,
    pidfd: OwnedFd,
    pid: u32,
    uid: u32,
    gid: u32,
    pidfd_node: (u64, u64),
    security: Vec<u8>,
}
impl KernelCaller {
    /// Bind an unnamed proof socket to the kernel-provided synchronous Binder
    /// PID/UID and the producer's fixed role and primary GID.
    ///
    /// There is no fallback when peer PIDFD, credentials or security metadata
    /// are unavailable. No application bytes are read from this descriptor.
    pub fn acquire(
        socket: OwnedFd,
        binder_pid: i32,
        binder_uid: u32,
        gid: u32,
        expected: &[u8],
    ) -> io::Result<Self> {
        shape(&socket)?;
        let cred = credentials(&socket)?;
        need(
            binder_pid > 1 && cred.pid == binder_pid && cred.uid == binder_uid && cred.gid == gid,
            "proof creator is not this synchronous Binder caller",
        )?;
        let pidfd = peer_pidfd(&socket)?;
        let value = Self {
            pidfd_node: identity(&pidfd)?,
            pidfd,
            socket,
            pid: binder_pid as u32,
            uid: binder_uid,
            gid,
            security: Vec::from(expected),
        };
        value.revalidate()?;
        Ok(value)
    }
    /// Recheck the original caller, proof socket and credentials without reading
    /// protocol bytes. Pending proof data, EOF, identity drift and exit revoke it.
    pub fn revalidate(&self) -> io::Result<()> {
        shape(&self.socket)?;
        let cred = credentials(&self.socket)?;
        let now = info(&self.pidfd)?;
        let current = peer_pidfd(&self.socket)?;
        need(
            identity(&current)? == self.pidfd_node
                && identity(&self.pidfd)? == self.pidfd_node
                && now.pid == self.pid
                && cred.pid as u32 == self.pid
                && cred.uid == self.uid
                && cred.gid == self.gid
                && [now.ruid, now.euid, now.suid, now.fsuid] == [self.uid; 4]
                && [now.rgid, now.egid, now.sgid, now.fsgid] == [self.gid; 4]
                && context(&self.socket)? == self.security,
            "original Binder proof identity or role changed",
        )?;
        let mut event = libc::pollfd {
            fd: self.socket.as_raw_fd(),
            events: libc::POLLIN | libc::POLLRDHUP,
            revents: 0,
        };
        // SAFETY: one initialized poll entry, nonblocking observation only.
        need(
            cv(unsafe { libc::poll(&mut event, 1, 0) })? == 0,
            "Binder proof channel closed or carried forbidden data",
        )?;
        alive(&self.pidfd)
    }
    /// Wait for one bounded application record while watching the same caller
    /// PIDFD and silent proof channel. Closing either revokes the data channel.
    pub fn wait_readable(&self, data: &impl AsFd, limit: Duration) -> io::Result<()> {
        let deadline = Instant::now() + limit;
        loop {
            self.revalidate()?;
            let left = deadline
                .checked_duration_since(Instant::now())
                .ok_or_else(|| {
                    io::Error::new(io::ErrorKind::TimedOut, "Binder channel idle deadline")
                })?;
            let mut events = [
                libc::pollfd {
                    fd: data.as_fd().as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.socket.as_raw_fd(),
                    events: libc::POLLIN | libc::POLLRDHUP,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.pidfd.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            // SAFETY: all three entries are live for this bounded poll.
            let result = unsafe {
                libc::poll(
                    events.as_mut_ptr(),
                    events.len() as libc::nfds_t,
                    left.as_millis().min(100) as i32,
                )
            };
            if result < 0 {
                let e = io::Error::last_os_error();
                if e.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(e);
            }
            self.revalidate()?;
            if events[0].revents != 0 {
                return Ok(());
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::SeqPacket;

    fn ids() -> (i32, u32, u32) {
        // SAFETY: these syscalls only observe the current test process IDs.
        unsafe { (libc::getpid(), libc::getuid(), libc::getgid()) }
    }
    #[test]
    fn kernel_caller_binds_real_creator_and_rejects_forwarder_ids_and_roles() {
        let (socket, _peer) = SeqPacket::pair().unwrap();
        let fd = socket.as_fd().try_clone_to_owned().unwrap();
        let security = context(&fd).unwrap();
        let (pid, uid, gid) = ids();
        let proof = KernelCaller::acquire(fd, pid, uid, gid, &security).unwrap();
        proof.revalidate().unwrap();
        assert!(
            KernelCaller::acquire(
                socket.as_fd().try_clone_to_owned().unwrap(),
                pid + 1,
                uid,
                gid,
                &security
            )
            .is_err()
        );
        assert!(
            KernelCaller::acquire(
                socket.as_fd().try_clone_to_owned().unwrap(),
                pid,
                uid + 1,
                gid,
                &security
            )
            .is_err()
        );
        assert!(
            KernelCaller::acquire(
                socket.as_fd().try_clone_to_owned().unwrap(),
                pid,
                uid,
                gid,
                b"u:r:wrong:s0"
            )
            .is_err()
        );
    }
    #[test]
    fn kernel_caller_rejects_closed_or_nonempty_proof_before_protocol_reads() {
        let (socket, peer) = SeqPacket::pair().unwrap();
        let fd = socket.as_fd().try_clone_to_owned().unwrap();
        let security = context(&fd).unwrap();
        let (pid, uid, gid) = ids();
        let proof = KernelCaller::acquire(fd, pid, uid, gid, &security).unwrap();
        peer.send_record(b"not authority", &[]).unwrap();
        assert!(proof.revalidate().is_err());
        drop(peer);
        assert!(proof.revalidate().is_err());
        let wrong = std::fs::File::open("/dev/null").unwrap();
        assert!(
            KernelCaller::acquire(
                wrong.as_fd().try_clone_to_owned().unwrap(),
                pid,
                uid,
                gid,
                &security
            )
            .is_err()
        );
    }

    // This test-only subprocess creates the proof itself. The parent deliberately
    // retains both socket endpoints, so creator exit must be detected by PIDFD.
    #[test]
    #[ignore = "entered only by kernel_caller_rejects_dead_creator_with_live_forwarded_fds"]
    fn kernel_caller_creator_process_fixture() {
        if std::env::var_os("DROIDLOOM_KERNEL_CALLER_TEST_CHILD").is_none() {
            return;
        }
        // SAFETY: the test's pre-exec hook transfers its owned channel as fd 199.
        let control = SeqPacket::from_owned_fd(unsafe { OwnedFd::from_raw_fd(199) }).unwrap();
        let (proof, lifetime) = SeqPacket::pair().unwrap();
        control
            .send_record(b"proof", &[proof.as_fd(), lifetime.as_fd()])
            .unwrap();
        let _ = control.receive_record();
    }

    #[test]
    fn kernel_caller_rejects_dead_creator_with_live_forwarded_fds() {
        use std::os::unix::process::CommandExt;
        use std::process::{Child, Command, Stdio};

        struct Reaped(Child);
        impl Drop for Reaped {
            fn drop(&mut self) {
                let _ = self.0.kill();
                let _ = self.0.wait();
            }
        }

        let (parent, child) = SeqPacket::pair().unwrap();
        let inherited = child.as_fd().as_raw_fd();
        let mut command = Command::new(std::env::current_exe().unwrap());
        command
            .args([
                "--ignored",
                "--exact",
                "kernel_caller::tests::kernel_caller_creator_process_fixture",
                "--nocapture",
            ])
            .env("DROIDLOOM_KERNEL_CALLER_TEST_CHILD", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::inherit());
        // SAFETY: the child-only hook uses only async-signal-safe FD syscalls.
        unsafe {
            command.pre_exec(move || {
                if libc::dup2(inherited, 199) != 199 || libc::fcntl(199, libc::F_SETFD, 0) != 0 {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        let mut creator = Reaped(command.spawn().unwrap());
        drop(child);
        let mut event = libc::pollfd {
            fd: parent.as_fd().as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        // SAFETY: the one poll entry is live and the wait is bounded.
        assert_eq!(unsafe { libc::poll(&mut event, 1, 10_000) }, 1);
        let mut record = parent.receive_record().unwrap();
        assert_eq!(record.bytes, b"proof");
        assert_eq!(record.descriptors.len(), 2);
        let lifetime = record.descriptors.pop().unwrap();
        let fd = record.descriptors.pop().unwrap();
        let security = context(&fd).unwrap();
        let (_, uid, gid) = ids();
        let replay = fd.try_clone().unwrap();
        assert!(
            KernelCaller::acquire(fd.try_clone().unwrap(), ids().0, uid, gid, &security).is_err()
        );
        let proof = KernelCaller::acquire(fd, creator.0.id() as i32, uid, gid, &security).unwrap();
        proof.revalidate().unwrap();
        creator.0.kill().unwrap();
        assert!(!creator.0.wait().unwrap().success());
        let mut still_open = libc::pollfd {
            fd: proof.socket.as_raw_fd(),
            events: libc::POLLIN | libc::POLLRDHUP,
            revents: 0,
        };
        // The forwarded peer FD keeps the connection live, but cannot keep the
        // original process alive or authorize a replay in another Binder call.
        assert_eq!(unsafe { libc::poll(&mut still_open, 1, 0) }, 0);
        assert!(proof.revalidate().is_err());
        assert!(KernelCaller::acquire(replay, creator.0.id() as i32, uid, gid, &security).is_err());
        drop(lifetime);
    }
}
