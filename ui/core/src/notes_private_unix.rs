//! One-shot transfer of ordered private effect stream and recovery datagram. Descriptor 0 carries
//! effects; descriptor 1 accepts only observation and exact receipt retirement.

use std::io;
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::net::{UnixDatagram, UnixStream};
use std::time::Duration;

const MAX_FRAME: usize = 1024;

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

fn datagram(channel: &UnixDatagram) -> io::Result<()> {
    require_socket(channel.as_raw_fd(), libc::SOCK_DGRAM)?;
    if !channel.local_addr()?.is_unnamed() || !channel.peer_addr()?.is_unnamed() {
        return Err(invalid("Notes handoff requires a private datagram pair"));
    }
    Ok(())
}

pub fn send_channels(
    channel: &UnixDatagram,
    raw: &[u8],
    effect: &UnixStream,
    recovery: &UnixDatagram,
    timeout: Duration,
) -> io::Result<()> {
    datagram(channel)?;
    if raw.is_empty() || raw.len() > MAX_FRAME {
        return Err(invalid("Notes handoff bound"));
    }
    require_socket(effect.as_raw_fd(), libc::SOCK_STREAM)?;
    if !effect.local_addr()?.is_unnamed() || !effect.peer_addr()?.is_unnamed() {
        return Err(invalid("Notes effect endpoint is not a private stream"));
    }
    datagram(recovery)?;
    channel.set_write_timeout(Some(timeout))?;
    let descriptors = [effect.as_raw_fd(), recovery.as_raw_fd()];
    let mut control = [0_usize; 8];
    // SAFETY: CMSG_SPACE computes storage for the two fixed descriptors.
    let space =
        unsafe { libc::CMSG_SPACE(mem::size_of_val(&descriptors) as libc::c_uint) } as usize;
    if space > mem::size_of_val(&control) {
        return Err(invalid("Notes ancillary bound"));
    }
    let mut vector = libc::iovec {
        iov_base: raw.as_ptr().cast_mut().cast(),
        iov_len: raw.len(),
    };
    // SAFETY: zeroed optional pointers, with bounded live buffers below.
    let mut message: libc::msghdr = unsafe { mem::zeroed() };
    message.msg_iov = &mut vector;
    message.msg_iovlen = 1;
    message.msg_control = control.as_mut_ptr().cast();
    message.msg_controllen = space;
    // SAFETY: aligned control storage fits exactly two borrowed descriptors;
    // sendmsg does not retain pointers, and both streams outlive the call.
    let count = unsafe {
        let header = libc::CMSG_FIRSTHDR(&message);
        (*header).cmsg_level = libc::SOL_SOCKET;
        (*header).cmsg_type = libc::SCM_RIGHTS;
        (*header).cmsg_len =
            libc::CMSG_LEN(mem::size_of_val(&descriptors) as libc::c_uint) as usize;
        for (index, descriptor) in descriptors.iter().enumerate() {
            libc::CMSG_DATA(header)
                .cast::<RawFd>()
                .add(index)
                .write_unaligned(*descriptor);
        }
        libc::sendmsg(channel.as_raw_fd(), &message, libc::MSG_NOSIGNAL)
    };
    if count < 0 {
        return Err(io::Error::last_os_error());
    }
    if count != raw.len() as isize {
        return Err(invalid("partial Notes handoff"));
    }
    Ok(())
}

pub fn receive_channels(
    channel: &UnixDatagram,
    timeout: Duration,
) -> io::Result<(Vec<u8>, UnixStream, UnixDatagram)> {
    datagram(channel)?;
    channel.set_read_timeout(Some(timeout))?;
    let mut bytes = [0_u8; MAX_FRAME + 1];
    let mut control = [0_usize; 32];
    let mut vector = libc::iovec {
        iov_base: bytes.as_mut_ptr().cast(),
        iov_len: bytes.len(),
    };
    // SAFETY: zeroed optional pointers, with bounded live writable buffers.
    let mut message: libc::msghdr = unsafe { mem::zeroed() };
    message.msg_iov = &mut vector;
    message.msg_iovlen = 1;
    message.msg_control = control.as_mut_ptr().cast();
    message.msg_controllen = mem::size_of_val(&control);
    // SAFETY: all buffers remain live; descriptors receive CLOEXEC atomically.
    let length =
        unsafe { libc::recvmsg(channel.as_raw_fd(), &mut message, libc::MSG_CMSG_CLOEXEC) };
    if length < 0 {
        return Err(io::Error::last_os_error());
    }
    let (descriptors, valid) = received_descriptors(&message);
    if !valid
        || descriptors.len() != 2
        || length == 0
        || length as usize > MAX_FRAME
        || message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
    {
        return Err(invalid("Notes handoff requires exactly two descriptors"));
    }
    let mut descriptors = descriptors.into_iter();
    let effect = descriptors
        .next()
        .ok_or_else(|| invalid("missing effect stream"))?;
    require_socket(effect.as_raw_fd(), libc::SOCK_STREAM)?;
    let effect = UnixStream::from(effect);
    if !effect.local_addr()?.is_unnamed() || !effect.peer_addr()?.is_unnamed() {
        return Err(invalid("Notes effect endpoint must be a private stream"));
    }
    let recovery = descriptors
        .next()
        .ok_or_else(|| invalid("missing recovery datagram"))?;
    require_socket(recovery.as_raw_fd(), libc::SOCK_DGRAM)?;
    let recovery = UnixDatagram::from(recovery);
    datagram(&recovery)?;
    effect.set_nonblocking(false)?;
    recovery.set_nonblocking(false)?;
    Ok((bytes[..length as usize].to_vec(), effect, recovery))
}

fn received_descriptors(message: &libc::msghdr) -> (Vec<OwnedFd>, bool) {
    let mut descriptors = Vec::new();
    let mut valid = true;
    // SAFETY: recvmsg initialized a kernel-bounded ancillary chain in the
    // aligned buffer retained by the caller throughout this traversal.
    let mut header = unsafe { libc::CMSG_FIRSTHDR(message) };
    while !header.is_null() {
        // SAFETY: CMSG iteration provides an in-bounds header, and CMSG_LEN(0)
        // gives its minimum length before payload arithmetic.
        let value = unsafe { &*header };
        let minimum = unsafe { libc::CMSG_LEN(0) } as usize;
        let offset = (header as usize).checked_sub(message.msg_control as usize);
        if value.cmsg_len < minimum
            || offset
                .and_then(|offset| offset.checked_add(value.cmsg_len))
                .is_none_or(|end| end > message.msg_controllen)
        {
            valid = false;
            break;
        }
        let count_bytes = value.cmsg_len - minimum;
        if value.cmsg_level == libc::SOL_SOCKET && value.cmsg_type == libc::SCM_RIGHTS {
            valid &= count_bytes % mem::size_of::<RawFd>() == 0;
            for index in 0..count_bytes / mem::size_of::<RawFd>() {
                // SAFETY: each complete descriptor lies within the ancillary
                // payload. Kernel-transferred descriptors have unique owned
                // numbers; adopting them immediately closes all on rejection.
                let descriptor = unsafe {
                    libc::CMSG_DATA(header)
                        .cast::<RawFd>()
                        .add(index)
                        .read_unaligned()
                };
                if descriptor < 0 {
                    valid = false;
                } else {
                    descriptors.push(unsafe { OwnedFd::from_raw_fd(descriptor) });
                }
            }
        } else {
            valid = false;
        }
        // SAFETY: same retained, bounded ancillary chain as above.
        header = unsafe { libc::CMSG_NXTHDR(message, header) };
    }
    (descriptors, valid)
}

fn require_socket(descriptor: RawFd, kind: libc::c_int) -> io::Result<()> {
    for (option, expected) in [(libc::SO_DOMAIN, libc::AF_UNIX), (libc::SO_TYPE, kind)] {
        let mut actual: libc::c_int = 0;
        let mut length = mem::size_of_val(&actual) as libc::socklen_t;
        // SAFETY: actual and its length are initialized writable values of the
        // exact size expected by these integer socket options.
        let result = unsafe {
            libc::getsockopt(
                descriptor,
                libc::SOL_SOCKET,
                option,
                (&mut actual as *mut libc::c_int).cast(),
                &mut length,
            )
        };
        if result != 0 {
            return Err(io::Error::last_os_error());
        }
        if length as usize != mem::size_of_val(&actual) || actual != expected {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "Notes descriptor socket type mismatch",
            ));
        }
    }
    Ok(())
}
