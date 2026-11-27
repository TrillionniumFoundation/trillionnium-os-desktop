//! Private parent/helper comparison channel. Every received byte is checked
//! against kernel SCM_CREDENTIALS; the full Main is compared, never hashed away.
use crate::main_custody::RuntimeMainCustody;
use serde::{Deserialize, Serialize};
use std::{
    io, mem,
    os::{fd::AsRawFd, unix::net::UnixStream},
    time::{Duration, Instant},
};
pub(crate) const LIMIT: usize = 132 * 1024;
pub(crate) const SCHEMA: &str = "droidloom.retained-original-live-channel.v1";
fn reject(why: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, why)
}
#[derive(Serialize, Deserialize)]
#[serde(tag = "phase", deny_unknown_fields)]
pub(crate) enum Frame {
    Begin {
        schema: String,
        candidate_id: String,
        preparation_end_ns: u64,
        helper_end_ns: u64,
        main: RuntimeMainCustody,
    },
    Ready {
        schema: String,
        main: RuntimeMainCustody,
    },
    Finish {},
    Finished {
        schema: String,
        main: RuntimeMainCustody,
    },
    Retire {},
}
pub(crate) fn prepare(socket: &UnixStream) -> io::Result<()> {
    let one = 1i32;
    if unsafe {
        libc::setsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PASSCRED,
            (&one as *const i32).cast(),
            mem::size_of::<i32>() as libc::socklen_t,
        )
    } != 0
    {
        return Err(io::Error::last_os_error());
    }
    socket.set_nonblocking(true)
}
fn wait(
    fd: i32,
    events: i16,
    end: Instant,
    guard: &mut dyn FnMut() -> io::Result<()>,
) -> io::Result<()> {
    guard()?;
    let remaining = end
        .checked_duration_since(Instant::now())
        .ok_or_else(|| reject("retained private channel expired"))?;
    let mut p = libc::pollfd {
        fd,
        events,
        revents: 0,
    };
    let ms = i32::try_from(remaining.as_millis().min(1000).max(1)).map_err(io::Error::other)?;
    let n = unsafe { libc::poll(&mut p, 1, ms) };
    if n < 0 {
        let e = io::Error::last_os_error();
        if e.kind() != io::ErrorKind::Interrupted {
            return Err(e);
        }
    }
    if p.revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
        return Err(reject("retained private channel failed"));
    }
    if Instant::now() >= end {
        return Err(reject("retained private channel exceeded original end"));
    }
    guard()
}
fn read_exact(
    socket: &UnixStream,
    out: &mut [u8],
    pid: u32,
    end: Instant,
    guard: &mut dyn FnMut() -> io::Result<()>,
) -> io::Result<()> {
    let mut offset = 0;
    while offset < out.len() {
        wait(socket.as_raw_fd(), libc::POLLIN, end, guard)?;
        let mut iov = libc::iovec {
            iov_base: out[offset..].as_mut_ptr().cast(),
            iov_len: out.len() - offset,
        };
        let mut control = [0u64; 8];
        let mut msg: libc::msghdr = unsafe { mem::zeroed() };
        msg.msg_iov = &mut iov;
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
            if matches!(
                e.kind(),
                io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
            ) {
                continue;
            }
            return Err(e);
        }
        if n == 0 || msg.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0 {
            return Err(reject("retained private frame truncated or peer closed"));
        }
        let first = unsafe { libc::CMSG_FIRSTHDR(&msg) };
        if first.is_null() {
            return Err(reject(
                "retained private bytes lack actual sender credentials",
            ));
        }
        let h = unsafe { &*first };
        if h.cmsg_level != libc::SOL_SOCKET
            || h.cmsg_type != libc::SCM_CREDENTIALS
            || h.cmsg_len
                != unsafe { libc::CMSG_LEN(mem::size_of::<libc::ucred>() as u32) } as usize
            || !unsafe { libc::CMSG_NXTHDR(&msg, first) }.is_null()
        {
            return Err(reject("retained private ancillary schema differs"));
        }
        let cred =
            unsafe { std::ptr::read_unaligned(libc::CMSG_DATA(first).cast::<libc::ucred>()) };
        if cred.pid as u32 != pid || cred.uid != 0 || cred.gid != 0 {
            return Err(reject(
                "retained private bytes came from another actual process",
            ));
        }
        offset += n as usize;
        guard()?;
    }
    Ok(())
}
pub(crate) fn receive(
    socket: &UnixStream,
    pid: u32,
    end: Instant,
    guard: &mut dyn FnMut() -> io::Result<()>,
) -> io::Result<Frame> {
    let mut len = [0u8; 4];
    read_exact(socket, &mut len, pid, end, guard)?;
    let len = u32::from_be_bytes(len) as usize;
    if len == 0 || len > LIMIT {
        return Err(reject("retained complete frame exceeds bound"));
    }
    let mut raw = vec![0u8; len];
    read_exact(socket, &mut raw, pid, end, guard)?;
    let frame: Frame = serde_json::from_slice(&raw).map_err(io::Error::other)?;
    for main in match &frame {
        Frame::Begin { main, .. } | Frame::Ready { main, .. } | Frame::Finished { main, .. } => {
            Some(main)
        }
        _ => None,
    } {
        if serde_json::to_vec(main).map_err(io::Error::other)?.len() > 128 * 1024 {
            return Err(reject("retained full Main exceeds separate bound"));
        }
        main.validate(&main.epoch)
            .map_err(|_| reject("retained Main comparison schema differs"))?;
    }
    Ok(frame)
}
pub(crate) fn send(
    socket: &UnixStream,
    frame: &Frame,
    end: Instant,
    guard: &mut dyn FnMut() -> io::Result<()>,
) -> io::Result<()> {
    send_inner(socket, frame, end, guard, true)
}
pub(crate) fn send_retire(
    socket: &UnixStream,
    end: Instant,
    guard: &mut dyn FnMut() -> io::Result<()>,
) -> io::Result<()> {
    send_inner(socket, &Frame::Retire {}, end, guard, false)
}
fn send_inner(
    socket: &UnixStream,
    frame: &Frame,
    end: Instant,
    guard: &mut dyn FnMut() -> io::Result<()>,
    post_guard: bool,
) -> io::Result<()> {
    let raw = serde_json::to_vec(frame).map_err(io::Error::other)?;
    if raw.is_empty() || raw.len() > LIMIT {
        return Err(reject("retained complete frame exceeds bound"));
    }
    let mut bytes = (raw.len() as u32).to_be_bytes().to_vec();
    bytes.extend_from_slice(&raw);
    let mut offset = 0;
    while offset < bytes.len() {
        wait(socket.as_raw_fd(), libc::POLLOUT, end, guard)?;
        let n = unsafe {
            libc::send(
                socket.as_raw_fd(),
                bytes[offset..].as_ptr().cast(),
                bytes.len() - offset,
                libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
            )
        };
        if n < 0 {
            let e = io::Error::last_os_error();
            if matches!(
                e.kind(),
                io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
            ) {
                continue;
            }
            return Err(e);
        }
        if n == 0 {
            return Err(reject("retained private send made no progress"));
        }
        offset += n as usize;
    }
    if post_guard {
        guard()?;
    }
    Ok(())
}
pub(crate) fn clock() -> io::Result<u64> {
    let mut value = mem::MaybeUninit::<libc::timespec>::uninit();
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, value.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let v = unsafe { value.assume_init() };
    u64::try_from(i128::from(v.tv_sec) * 1_000_000_000 + i128::from(v.tv_nsec))
        .map_err(io::Error::other)
}
pub(crate) fn until(ns: u64) -> io::Result<Instant> {
    let now = Instant::now();
    let remain = ns
        .checked_sub(clock()?)
        .filter(|v| *v > 0)
        .ok_or_else(|| reject("retained absolute deadline elapsed"))?;
    now.checked_add(Duration::from_nanos(remain))
        .ok_or_else(|| reject("retained deadline overflow"))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn private_channel_requires_real_sender_credentials_and_finite_schema() {
        let (a, b) = UnixStream::pair().unwrap();
        prepare(&a).unwrap();
        prepare(&b).unwrap();
        let end = Instant::now() + Duration::from_secs(2);
        send(&a, &Frame::Finish {}, end, &mut || Ok(())).unwrap();
        let received = receive(&b, std::process::id(), end, &mut || Ok(()));
        if unsafe { libc::getuid() } == 0 {
            assert!(matches!(received.unwrap(), Frame::Finish {}));
        } else {
            assert!(
                received.is_err(),
                "non-root actual SCM sender cannot mint a root helper frame"
            );
        }
        send(&a, &Frame::Finish {}, end, &mut || Ok(())).unwrap();
        assert!(receive(&b, std::process::id() + 1, end, &mut || Ok(())).is_err());
        for raw in [
            r#"{"phase":"Finish","retained":true}"#,
            r#"{"phase":"Ready","schema":"old"}"#,
            r#"{"phase":"Uninstall","package":"other"}"#,
        ] {
            assert!(serde_json::from_str::<Frame>(raw).is_err());
        }
    }
}
