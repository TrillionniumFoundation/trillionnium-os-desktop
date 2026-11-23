//! Linux owns this socket and the systemd notification. The independent Android
//! service only answers fresh, read-only challenges under its own domain.
use super::*;
use droidloom_supervisor::control::EarlyAndroidGeneration;
use std::mem;
use std::os::fd::{AsFd, BorrowedFd};
use std::os::unix::ffi::OsStrExt;

const CHANNEL: &str = "/run/droidloom-early/readiness/droidloom_readiness";
const PARENT: &str = "/run/droidloom-early/readiness";
const REQUEST: &[u8; 8] = b"DLRDREQ1";
const RESPONSE: &[u8; 8] = b"DLRDRSP1";
fn cv(n: i32) -> io::Result<i32> {
    if n < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(n)
    }
}

struct Endpoint {
    socket: OwnedFd,
    identity: (u64, u64),
}
impl Endpoint {
    fn bind(gid: u32) -> io::Result<Self> {
        let parent = fs::symlink_metadata(PARENT)?;
        if !parent.is_dir()
            || parent.uid() != 0
            || parent.gid() != gid
            || parent.mode() & 0o7777 != 0o2710
        {
            return Err(error(
                "early readiness directory has incorrect mapped ownership or permissions",
            ));
        }
        let fd = cv(unsafe {
            libc::socket(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                0,
            )
        })?;
        let socket = unsafe { OwnedFd::from_raw_fd(fd) };
        let mut address: libc::sockaddr_un = unsafe { mem::zeroed() };
        address.sun_family = libc::AF_UNIX as _;
        let pathname = Path::new(CHANNEL).as_os_str().as_bytes();
        assert!(pathname.len() < address.sun_path.len());
        for (dst, src) in address.sun_path.iter_mut().zip(pathname) {
            *dst = *src as libc::c_char;
        }
        cv(unsafe {
            libc::bind(
                fd,
                (&address as *const libc::sockaddr_un).cast(),
                mem::size_of_val(&address) as _,
            )
        })?;
        let node = fs::symlink_metadata(CHANNEL)?;
        let handle = Self {
            socket,
            identity: (node.dev(), node.ino()),
        };
        if !node.file_type().is_socket() || node.uid() != 0 || node.gid() != gid {
            return Err(error(
                "early readiness socket lacks its selected mapped DAC group",
            ));
        }
        fs::set_permissions(CHANNEL, fs::Permissions::from_mode(0o620))?;
        cv(unsafe { libc::listen(fd, 8) })?;
        Ok(handle)
    }
    fn accept(&self) -> io::Result<Option<OwnedFd>> {
        let value = unsafe {
            libc::accept4(
                self.socket.as_raw_fd(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                libc::SOCK_CLOEXEC,
            )
        };
        if value < 0 {
            let err = io::Error::last_os_error();
            if matches!(
                err.kind(),
                io::ErrorKind::Interrupted | io::ErrorKind::WouldBlock
            ) {
                return Ok(None);
            }
            return Err(err);
        }
        Ok(Some(unsafe { OwnedFd::from_raw_fd(value) }))
    }
}
impl Drop for Endpoint {
    fn drop(&mut self) {
        if fs::symlink_metadata(CHANNEL)
            .is_ok_and(|n| n.file_type().is_socket() && (n.dev(), n.ino()) == self.identity)
        {
            let _ = fs::remove_file(CHANNEL);
        }
    }
}

fn challenge(channel: BorrowedFd<'_>) -> io::Result<u8> {
    let mut req = [0u8; 40];
    req[..8].copy_from_slice(REQUEST);
    let mut random = File::open("/dev/urandom")?;
    random.read_exact(&mut req[8..])?;
    // Bound both directions; a wedged Android Binder must withdraw the observation.
    let timeout = libc::timeval {
        tv_sec: 3,
        tv_usec: 0,
    };
    for opt in [libc::SO_RCVTIMEO, libc::SO_SNDTIMEO] {
        cv(unsafe {
            libc::setsockopt(
                channel.as_raw_fd(),
                libc::SOL_SOCKET,
                opt,
                (&timeout as *const libc::timeval).cast(),
                mem::size_of_val(&timeout) as _,
            )
        })?;
    }
    let n = unsafe {
        libc::send(
            channel.as_raw_fd(),
            req.as_ptr().cast(),
            req.len(),
            libc::MSG_NOSIGNAL,
        )
    };
    if n != req.len() as isize {
        return Err(if n < 0 {
            io::Error::last_os_error()
        } else {
            error("partial readiness request")
        });
    }
    let mut reply = [0u8; 41];
    let n = unsafe {
        libc::recv(
            channel.as_raw_fd(),
            reply.as_mut_ptr().cast(),
            reply.len(),
            libc::MSG_TRUNC,
        )
    };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    if n != reply.len() as isize
        || &reply[..8] != RESPONSE
        || reply[8..40] != req[8..]
        || !matches!(reply[40], 0 | 1 | 3 | 7)
    {
        return Err(error("invalid or stale Android readiness response"));
    }
    Ok(reply[40])
}

pub(crate) fn run(stop: &AtomicBool) -> io::Result<()> {
    let mac = ContainerManagerMac::acquire()?;
    let generation = EarlyAndroidGeneration::acquire()?;
    let channel = Endpoint::bind(generation.observer_group()?)?;
    let mut clients = protocol::Clients::bind()?;
    let end = Instant::now() + START_LIMIT;
    let mut peer: Option<(OwnedFd, OwnedFd)> = None;
    let mut stage = 0;
    let mut notified = false;
    let mut last = Instant::now().checked_sub(Duration::from_secs(2)).unwrap();
    let results = (|| {
        while !stop.load(Ordering::Relaxed) {
            mac.check_epoch()?;
            generation.check_liveness()?;
            if peer.is_none() {
                if let Some(socket) = channel.accept()? {
                    if let Ok(held) = generation.verify_observer(socket.as_fd()) {
                        peer = Some((socket, held));
                    }
                }
            }
            if let Some((socket, held)) = &peer {
                if !live(held)? {
                    return Err(error("original stock-init readiness observer exited"));
                }
                if last.elapsed() >= Duration::from_secs(1) {
                    stage = challenge(socket.as_fd())?;
                    generation.revalidate()?;
                    mac.revalidate()?;
                    if !live(held)? {
                        return Err(error("observer exited during readiness query"));
                    }
                    if notified && stage == 0 {
                        return Err(error("selected Android Binder became unavailable"));
                    }
                    if !notified && stage & 1 != 0 {
                        protocol::notify_main()?;
                        notified = true;
                    }
                    last = Instant::now();
                }
            }
            if !notified && Instant::now() >= end {
                return Err(error(
                    "selected early Android did not establish Binder before its deadline",
                ));
            }
            clients.poll(stage == 7, || {
                generation.revalidate()?;
                mac.revalidate()?;
                match &peer {
                    Some((socket, held)) if live(held)? && challenge(socket.as_fd())? == 7 => {
                        generation.revalidate()?;
                        mac.revalidate()?;
                        if !live(held)? {
                            return Err(error("observer exited before reply"));
                        }
                        Ok(())
                    }
                    _ => Err(error(
                        "Android framework readiness changed before desktop reply",
                    )),
                }
            })?;
            thread::sleep(Duration::from_millis(50));
        }
        Ok(())
    })();
    drop(clients);
    drop(channel);
    let stopped = if notified {
        protocol::notify_stopping()
    } else {
        Ok(())
    };
    results.and(stopped)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn kernel_seqpacket_challenge_rejects_replay_oversize_and_invalid_progress() {
        for action in 0..4 {
            let mut pair = [-1; 2];
            assert_eq!(
                unsafe {
                    libc::socketpair(
                        libc::AF_UNIX,
                        libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                        0,
                        pair.as_mut_ptr(),
                    )
                },
                0
            );
            let caller = unsafe { OwnedFd::from_raw_fd(pair[0]) };
            let guest = unsafe { OwnedFd::from_raw_fd(pair[1]) };
            let worker = thread::spawn(move || {
                let mut req = [0u8; 40];
                assert_eq!(
                    unsafe { libc::recv(guest.as_raw_fd(), req.as_mut_ptr().cast(), req.len(), 0) },
                    40
                );
                let mut rsp = [0u8; 42];
                rsp[..8].copy_from_slice(RESPONSE);
                rsp[8..40].copy_from_slice(&req[8..]);
                rsp[40] = 7;
                if action == 1 {
                    rsp[9] ^= 1;
                }
                if action == 2 {
                    rsp[40] = 4;
                }
                let len = if action == 3 { 42 } else { 41 };
                assert_eq!(
                    unsafe {
                        libc::send(
                            guest.as_raw_fd(),
                            rsp.as_ptr().cast(),
                            len,
                            libc::MSG_NOSIGNAL,
                        )
                    },
                    len as isize
                );
            });
            let result = challenge(caller.as_fd());
            assert_eq!(result.is_ok(), action == 0);
            worker.join().unwrap();
        }
    }
}
