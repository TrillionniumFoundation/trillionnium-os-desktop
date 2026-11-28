//! A fixed native UVC loop. No control message carries a device path or frame.
use super::super::{protocol, query_io};
use super::{Result, device, mac, reject, require, wire};
use std::fs::File;
use std::io;
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::time::{Duration, Instant};
#[repr(C)]
#[derive(Default)]
struct Statistics {
    delivered: u64,
    dequeued: u64,
    dropped: u64,
    last_capture_ns: u64,
}
unsafe extern "C" {
    fn droidloom_camera_probe(fd: libc::c_int) -> libc::c_int;
    fn droidloom_camera_capture(
        device: libc::c_int,
        stream: libc::c_int,
        control: libc::c_int,
        original_init: libc::c_int,
        original_owner: libc::c_int,
        producer: libc::c_int,
        statistics: *mut Statistics,
    ) -> libc::c_int;
}
struct Custody {
    control: File,
    owner: File,
    init: File,
    listener: File,
    _proof: File,
    peer: libc::ucred,
    parent: libc::pid_t,
    uid: u32,
    gid: u32,
}
impl Custody {
    fn revalidate(&self) -> Result<()> {
        query_io::parent_identity(&self.owner, self.peer, self.parent)?;
        query_io::alive(&self.init)?;
        mac::exact_ids(&query_io::pidfd_info(&self.init)?, self.uid, self.gid)?;
        mac::own_capture()
    }
    fn stop(&self) -> Result<bool> {
        let mut bytes = [0u8; 9];
        let n = unsafe {
            libc::recv(
                self.control.as_raw_fd(),
                bytes.as_mut_ptr().cast(),
                bytes.len(),
                libc::MSG_DONTWAIT,
            )
        };
        if n < 0 {
            let error = io::Error::last_os_error();
            if matches!(
                error.kind(),
                io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
            ) {
                return Ok(false);
            }
            return Err(error.into());
        }
        require(
            n == 8 && &bytes[..8] == wire::STOP,
            "camera private owner channel ended or changed",
        )?;
        Ok(true)
    }
}
// Public I/O is separately parameterized by its held socket, never a PIDFD.
fn io_bytes(
    c: &Custody,
    socket: &File,
    producer: &File,
    bytes: &mut [u8],
    write: bool,
    deadline: Instant,
) -> Result<bool> {
    let mut offset = 0;
    while offset < bytes.len() {
        c.revalidate()?;
        query_io::alive(producer)?;
        if c.stop()? {
            return Ok(true);
        }
        require(Instant::now() < deadline, "camera public request deadline")?;
        let n = unsafe {
            if write {
                libc::send(
                    socket.as_raw_fd(),
                    bytes[offset..].as_ptr().cast(),
                    bytes.len() - offset,
                    libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
                )
            } else {
                libc::recv(
                    socket.as_raw_fd(),
                    bytes[offset..].as_mut_ptr().cast(),
                    bytes.len() - offset,
                    libc::MSG_DONTWAIT,
                )
            }
        };
        if n < 0 {
            let e = io::Error::last_os_error();
            if matches!(
                e.kind(),
                io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
            ) {
                let mut polls = [
                    libc::pollfd {
                        fd: c.control.as_raw_fd(),
                        events: libc::POLLIN,
                        revents: 0,
                    },
                    libc::pollfd {
                        fd: socket.as_raw_fd(),
                        events: if write { libc::POLLOUT } else { libc::POLLIN },
                        revents: 0,
                    },
                ];
                let r = unsafe { libc::poll(polls.as_mut_ptr(), 2, 20) };
                if r < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
                    return Err(io::Error::last_os_error().into());
                }
                continue;
            }
            return Err(e.into());
        }
        require(n > 0, "camera producer closed during the fixed exchange")?;
        offset += n as usize;
    }
    Ok(false)
}
fn listener(file: &File) -> Result<()> {
    let mut kind = 0i32;
    let mut length = mem::size_of_val(&kind) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            file.as_raw_fd(),
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
        kind == libc::SOCK_STREAM && length as usize == mem::size_of_val(&kind),
        "camera inherited endpoint is not a stream",
    )?;
    let mut listening = 0i32;
    if unsafe {
        libc::getsockopt(
            file.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_ACCEPTCONN,
            (&mut listening as *mut i32).cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        listening == 1,
        "camera endpoint is not an unconnected listening socket",
    )
}
pub(super) fn entry() -> Result<()> {
    query_io::own_root_credentials()?;
    query_io::verify_fixed_stdio()?;
    query_io::channel_kind(3)?;
    super::query_io::install_filter(&super::filter::program(None))?;
    if unsafe { libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    mac::own_capture()?;
    device::initial_scope()?;
    drop(
        crate::production_host_admission::application_worker_executable()
            .map_err(super::super::external)?,
    );
    let parent = unsafe { libc::getppid() };
    require(parent > 1, "camera has no original production owner")?;
    let request = wire::receive(3, 3, Instant::now() + Duration::from_secs(5))?;
    require(
        request.wire.phase == wire::INITIALIZE,
        "camera first ownership phase differs",
    )?;
    let [owner, init, listener_fd]: [File; 3] = request
        .files
        .try_into()
        .map_err(|_| reject("camera ownership descriptor count"))?;
    query_io::parent_identity(&owner, request.peer, parent)?;
    require(
        mac::peer(3, mac::SELINUX)? == mac::BROKER
            && mac::peer(3, mac::APPARMOR)? == b"droidloom-production-broker (enforce)",
        "camera private channel was not created by its original production broker",
    )?;
    if unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL, 0, 0, 0) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    query_io::parent_identity(&owner, request.peer, parent)?;
    let remaining = request
        .wire
        .deadline_ns
        .checked_sub(protocol::monotonic_ns()?)
        .ok_or_else(|| reject("camera initialization expired"))?;
    require(
        remaining > 0 && remaining <= 5_000_000_000,
        "camera initialization budget differs",
    )?;
    listener(&listener_fd)?;
    let (proof, retained) = protocol::socketpair()?;
    let c = Custody {
        control: unsafe { File::from_raw_fd(3) },
        owner,
        init,
        listener: listener_fd,
        _proof: File::from(retained),
        peer: request.peer,
        parent,
        uid: request.wire.uid,
        gid: request.wire.gid,
    };
    c.revalidate()?;
    wire::send(
        c.control.as_raw_fd(),
        wire::Wire {
            phase: wire::READY,
            ..request.wire
        },
        &[proof.as_raw_fd()],
        Instant::now() + Duration::from_nanos(remaining),
    )?;
    drop(proof);
    loop {
        c.revalidate()?;
        if c.stop()? {
            return Ok(());
        }
        let mut polls = [
            libc::pollfd {
                fd: c.control.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: c.listener.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: c.owner.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: c.init.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
        ];
        let n = unsafe { libc::poll(polls.as_mut_ptr(), polls.len() as _, 100) };
        if n < 0 {
            if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(io::Error::last_os_error().into());
        }
        c.revalidate()?;
        if c.stop()? {
            return Ok(());
        }
        if polls[1].revents & libc::POLLIN == 0 {
            continue;
        }
        let raw = unsafe {
            libc::accept4(
                c.listener.as_raw_fd(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            )
        };
        if raw < 0 {
            if matches!(
                io::Error::last_os_error().kind(),
                io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
            ) {
                continue;
            }
            return Err(io::Error::last_os_error().into());
        }
        let socket = unsafe { File::from_raw_fd(raw) };
        let producer = match mac::producer(socket.as_raw_fd(), &c.init, c.uid, c.gid) {
            Ok(p) => p,
            Err(_) => {
                continue;
            }
        };
        let mut request = [0u8; 12];
        let stopped = match io_bytes(
            &c,
            &socket,
            &producer,
            &mut request,
            false,
            Instant::now() + Duration::from_secs(2),
        ) {
            Ok(v) => v,
            Err(_) => {
                continue;
            }
        };
        if stopped {
            return Ok(());
        }
        let operation = match wire::Request::parse(&request) {
            Ok(op) => op,
            Err(_) => continue,
        };
        let camera = device::open()?;
        let available = if let Some(camera) = &camera {
            if unsafe { droidloom_camera_probe(camera.as_raw_fd()) } == 0 {
                true
            } else {
                let e = io::Error::last_os_error();
                match e.raw_os_error() {
                    Some(libc::ENODEV | libc::ENOENT | libc::ENOTSUP) => false,
                    _ => return Err(e.into()),
                }
            }
        } else {
            false
        };
        let mut response = wire::response(available);
        let stopped = match io_bytes(
            &c,
            &socket,
            &producer,
            &mut response,
            true,
            Instant::now() + Duration::from_secs(2),
        ) {
            Ok(v) => v,
            Err(_) => continue,
        };
        if stopped {
            return Ok(());
        }
        if !available || operation == wire::Request::Probe {
            continue;
        }
        c.revalidate()?;
        let mut statistics = Statistics::default();
        let result = unsafe {
            droidloom_camera_capture(
                camera.as_ref().unwrap().as_raw_fd(),
                socket.as_raw_fd(),
                c.control.as_raw_fd(),
                c.init.as_raw_fd(),
                c.owner.as_raw_fd(),
                producer.as_raw_fd(),
                &mut statistics,
            )
        };
        match result {
            0 | 2 => continue,  // consumer closed or the real device disappeared
            1 => return Ok(()), // private owner stop, after actual STREAMOFF/cleanup
            -1 => {
                let e = io::Error::last_os_error();
                if matches!(
                    e.raw_os_error(),
                    Some(libc::EPROTO | libc::EPIPE | libc::ECONNRESET | libc::ETIMEDOUT)
                ) {
                    continue;
                }
                return Err(e.into());
            }
            _ => return Err(reject("camera native loop returned an unknown result")),
        }
    }
}
