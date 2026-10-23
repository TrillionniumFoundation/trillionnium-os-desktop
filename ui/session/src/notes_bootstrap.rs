//! Explicit trusted-parent bootstrap, never public Session IPC. One inherited
//! unnamed datagram channel transfers only the initial Notes effect endpoint.

use std::io;
use std::mem;
use std::net::Shutdown;
use std::os::fd::{AsRawFd, BorrowedFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::net::{UnixDatagram, UnixStream};
use std::time::{Duration, Instant};

use trill_ui_core::notes::NotesTargetIdentity;
use trill_ui_core::notes_bootstrap::{
    NotesBootstrapAck, NotesBootstrapOffer, NotesBootstrapStatus, NOTES_BOOTSTRAP_MAX_BYTES,
};

const DEADLINE: Duration = Duration::from_secs(2);

pub struct NotesBootstrap {
    channel: UnixDatagram,
}

impl NotesBootstrap {
    pub fn from_inherited_stdin() -> io::Result<Self> {
        // The explicit command-line mode designates this process-owned fd.
        // Duplicating it adds CLOEXEC; ordinary Session startup never reads it.
        let descriptor = unsafe { BorrowedFd::borrow_raw(0) }.try_clone_to_owned()?;
        Self::from_private_channel(UnixDatagram::from(descriptor))
    }

    pub fn from_private_channel(channel: UnixDatagram) -> io::Result<Self> {
        require_socket_type(channel.as_raw_fd(), libc::SOCK_DGRAM)?;
        if !channel.local_addr()?.is_unnamed() || !channel.peer_addr()?.is_unnamed() {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "Notes bootstrap requires an inherited unnamed datagram pair",
            ));
        }
        channel.set_nonblocking(false)?;
        Ok(Self { channel })
    }

    /// Consume this one-shot bootstrap and the fresh endpoint. On success the
    /// original host alone retains the effect endpoint. On failure shut down
    /// all duplicate endpoint references; a lost attachment ACK is not proof
    /// that the parent never attached or that any concurrent effect rolled back.
    pub fn offer(
        self,
        identity: NotesTargetIdentity,
        endpoint: UnixStream,
        recovery: UnixDatagram,
    ) -> io::Result<()> {
        let outcome = self.offer_inner(identity, &endpoint, &recovery);
        if outcome.is_err() {
            let _ = endpoint.shutdown(Shutdown::Both);
            let _ = recovery.shutdown(Shutdown::Both);
        }
        outcome
    }

    fn offer_inner(
        &self,
        identity: NotesTargetIdentity,
        endpoint: &UnixStream,
        recovery: &UnixDatagram,
    ) -> io::Result<()> {
        let offer = NotesBootstrapOffer::new(identity).map_err(invalid)?;
        require_socket_type(endpoint.as_raw_fd(), libc::SOCK_STREAM)?;
        if !endpoint.local_addr()?.is_unnamed() || !endpoint.peer_addr()?.is_unnamed() {
            return Err(invalid("Notes effect endpoint is not a private pair"));
        }
        let raw = serde_json::to_vec(&offer).map_err(io::Error::other)?;
        if raw.is_empty() || raw.len() > NOTES_BOOTSTRAP_MAX_BYTES {
            return Err(invalid("Notes bootstrap offer bound"));
        }
        let deadline = Instant::now() + DEADLINE;
        trill_ui_core::notes_private_unix::send_channels(
            &self.channel,
            &raw,
            endpoint,
            recovery,
            remaining(deadline)?,
        )?;
        let raw = receive_ack(&self.channel, deadline)?;
        let ack = NotesBootstrapAck::parse_exact(&raw).map_err(invalid)?;
        if !ack.matches(&offer) {
            return Err(invalid("Notes bootstrap acknowledgement target mismatch"));
        }
        match ack.status {
            NotesBootstrapStatus::Attached => Ok(()),
            NotesBootstrapStatus::Rejected => Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "original production host rejected Notes attachment",
            )),
        }
    }
}

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

fn remaining(deadline: Instant) -> io::Result<Duration> {
    deadline
        .checked_duration_since(Instant::now())
        .filter(|left| !left.is_zero())
        .ok_or_else(|| io::Error::new(io::ErrorKind::TimedOut, "Notes bootstrap total deadline"))
}

fn require_socket_type(fd: RawFd, expected_type: libc::c_int) -> io::Result<()> {
    for (name, expected) in [
        (libc::SO_DOMAIN, libc::AF_UNIX),
        (libc::SO_TYPE, expected_type),
    ] {
        let mut value: libc::c_int = 0;
        let mut length = mem::size_of_val(&value) as libc::socklen_t;
        // Both output pointers refer to correctly sized writable values.
        let result = unsafe {
            libc::getsockopt(
                fd,
                libc::SOL_SOCKET,
                name,
                (&mut value as *mut libc::c_int).cast(),
                &mut length,
            )
        };
        if result != 0 {
            return Err(io::Error::last_os_error());
        }
        if length as usize != mem::size_of_val(&value) || value != expected {
            return Err(invalid("Notes bootstrap socket domain/type mismatch"));
        }
    }
    Ok(())
}

#[cfg(test)]
fn send_descriptor(
    channel: &UnixDatagram,
    raw: &[u8],
    fd: RawFd,
    deadline: Instant,
) -> io::Result<()> {
    // usize storage is aligned for Linux cmsghdr, including 32-bit targets.
    let mut control = [0usize; 8];
    let space = unsafe { libc::CMSG_SPACE(mem::size_of::<RawFd>() as libc::c_uint) } as usize;
    if space > mem::size_of_val(&control) {
        return Err(invalid("Notes bootstrap ancillary capacity"));
    }
    loop {
        channel.set_write_timeout(Some(remaining(deadline)?))?;
        let mut iov = libc::iovec {
            iov_base: raw.as_ptr().cast_mut().cast(),
            iov_len: raw.len(),
        };
        let mut message: libc::msghdr = unsafe { mem::zeroed() };
        message.msg_iov = &mut iov;
        message.msg_iovlen = 1;
        message.msg_control = control.as_mut_ptr().cast();
        message.msg_controllen = space;
        // The control buffer is aligned, zeroed and large enough for exactly
        // one rights message; the borrowed endpoint stays alive through send.
        let count = unsafe {
            let header = libc::CMSG_FIRSTHDR(&message);
            (*header).cmsg_level = libc::SOL_SOCKET;
            (*header).cmsg_type = libc::SCM_RIGHTS;
            (*header).cmsg_len = libc::CMSG_LEN(mem::size_of::<RawFd>() as libc::c_uint) as usize;
            libc::CMSG_DATA(header).cast::<RawFd>().write_unaligned(fd);
            libc::sendmsg(channel.as_raw_fd(), &message, libc::MSG_NOSIGNAL)
        };
        if count == raw.len() as isize {
            return Ok(());
        }
        if count < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error);
        }
        return Err(invalid("Notes bootstrap datagram was not sent atomically"));
    }
}

fn receive_ack(channel: &UnixDatagram, deadline: Instant) -> io::Result<Vec<u8>> {
    loop {
        channel.set_read_timeout(Some(remaining(deadline)?))?;
        let mut bytes = [0u8; NOTES_BOOTSTRAP_MAX_BYTES + 1];
        let mut control = [0usize; 32];
        let mut iov = libc::iovec {
            iov_base: bytes.as_mut_ptr().cast(),
            iov_len: bytes.len(),
        };
        let mut message: libc::msghdr = unsafe { mem::zeroed() };
        message.msg_iov = &mut iov;
        message.msg_iovlen = 1;
        message.msg_control = control.as_mut_ptr().cast();
        message.msg_controllen = mem::size_of_val(&control);
        let count =
            unsafe { libc::recvmsg(channel.as_raw_fd(), &mut message, libc::MSG_CMSG_CLOEXEC) };
        if count < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error);
        }
        // No descriptors belong in an ACK. Close every received rights fd
        // before rejecting ancillary data, including truncated deliveries.
        let mut ancillary = false;
        unsafe {
            let mut header = libc::CMSG_FIRSTHDR(&message);
            while !header.is_null() {
                ancillary = true;
                let minimum = libc::CMSG_LEN(0) as usize;
                if (*header).cmsg_level == libc::SOL_SOCKET
                    && (*header).cmsg_type == libc::SCM_RIGHTS
                    && (*header).cmsg_len >= minimum
                {
                    let size = (*header).cmsg_len - minimum;
                    for index in 0..size / mem::size_of::<RawFd>() {
                        let fd = libc::CMSG_DATA(header)
                            .cast::<RawFd>()
                            .add(index)
                            .read_unaligned();
                        if fd >= 0 {
                            drop(OwnedFd::from_raw_fd(fd));
                        }
                    }
                }
                header = libc::CMSG_NXTHDR(&message, header);
            }
        }
        if ancillary
            || message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
            || count == 0
            || count as usize > NOTES_BOOTSTRAP_MAX_BYTES
        {
            return Err(invalid("Notes bootstrap ACK framing or ancillary data"));
        }
        remaining(deadline)?;
        return Ok(bytes[..count as usize].to_vec());
    }
}

#[cfg(test)]
#[path = "notes_bootstrap_tests.rs"]
mod tests;
