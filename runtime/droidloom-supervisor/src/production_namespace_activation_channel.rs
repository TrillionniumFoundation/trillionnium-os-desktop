//! Bounded authenticated records on the actual activation peer connection.
//!
//! This transport does not create execution authority. The broker must retain
//! and revalidate OwnedActivationPeer and the separate live MAC witness. Each
//! received datagram carries the actual kernel sender credentials; packet PID
//! fields are never a source of authority or a target for a syscall.

use super::activation_peer::{peer_credentials, require_activation_socket};
use super::*;
use crate::production_activation_protocol as wire;
use std::mem::{size_of, size_of_val};

pub(super) fn monotonic_ns() -> Result<u64> {
    let mut time: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut time) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if time.tv_sec < 0 || !(0..1_000_000_000).contains(&time.tv_nsec) {
        return Err(NamespaceError::Rejected("invalid actual monotonic clock"));
    }
    (time.tv_sec as u64)
        .checked_mul(1_000_000_000)
        .and_then(|value| value.checked_add(time.tv_nsec as u64))
        .ok_or(NamespaceError::Rejected("monotonic clock overflow"))
}

pub(super) fn before(deadline: u64) -> Result<()> {
    if monotonic_ns()? >= deadline {
        return Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "activation absolute deadline expired",
        )
        .into());
    }
    Ok(())
}

/// Poll never extends the caller's original absolute deadline. Observation
/// after a zero timeout or after a slow syscall cannot turn expiry into success.
pub(super) fn wait_event(fd: BorrowedFd<'_>, events: i16, deadline: u64) -> Result<i16> {
    loop {
        before(deadline)?;
        let remaining = deadline.checked_sub(monotonic_ns()?).ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "activation absolute deadline expired",
            )
        })?;
        let millis = remaining.div_ceil(1_000_000).min(i32::MAX as u64) as i32;
        let mut poll = libc::pollfd {
            fd: fd.as_raw_fd(),
            events,
            revents: 0,
        };
        let result = unsafe { libc::poll(&mut poll, 1, millis) };
        if result < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error.into());
        }
        before(deadline)?;
        if poll.revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
            return Err(NamespaceError::Rejected("activation descriptor error"));
        }
        if result != 0 {
            return Ok(poll.revents);
        }
    }
}

#[derive(Clone, Copy)]
pub(super) enum Rights {
    None,
    One,
    Optional,
}

pub(super) struct Received {
    pub(super) packet: wire::Packet,
    pub(super) descriptor: Option<OwnedFd>,
    pub(super) data: Vec<u8>,
}

/// An existing accepted connection; it cannot bind, connect or select a path.
/// The actual connected peer is read from the kernel and checked again before
/// every record. It still does not establish the peer's owned-init or MAC role.
pub(super) struct Channel<'a> {
    socket: &'a OwnedFd,
    credentials: libc::ucred,
}

impl<'a> Channel<'a> {
    pub(super) fn observe(socket: &'a OwnedFd) -> Result<Self> {
        require_activation_socket(socket)?;
        Ok(Self {
            socket,
            credentials: peer_credentials(socket)?,
        })
    }

    fn revalidate(&self) -> Result<()> {
        require_activation_socket(self.socket)?;
        let now = peer_credentials(self.socket)?;
        if now.pid != self.credentials.pid
            || now.uid != self.credentials.uid
            || now.gid != self.credentials.gid
        {
            return Err(NamespaceError::Rejected(
                "activation connected peer changed",
            ));
        }
        Ok(())
    }

    pub(super) fn send(
        &self,
        packet: &wire::Packet,
        descriptor: Option<BorrowedFd<'_>>,
        deadline: u64,
    ) -> Result<()> {
        if !packet.header_is_fixed() || packet.data_length != 0 || packet.detail != 0 {
            return Err(NamespaceError::Rejected("invalid fixed broker record"));
        }
        self.revalidate()?;
        let mut iov = libc::iovec {
            iov_base: (packet as *const wire::Packet).cast_mut().cast(),
            iov_len: wire::PACKET_BYTES,
        };
        // Properly aligned CMSG_SPACE(sizeof(int)); only AUTH transfers a
        // descriptor. CLOEXEC on reception is mandatory in the static peer.
        let mut control = [0_usize; 3];
        let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
        message.msg_iov = &mut iov;
        message.msg_iovlen = 1;
        if let Some(fd) = descriptor {
            message.msg_control = control.as_mut_ptr().cast();
            message.msg_controllen = unsafe { libc::CMSG_SPACE(size_of::<i32>() as u32) } as usize;
            let header = unsafe { libc::CMSG_FIRSTHDR(&message) };
            unsafe {
                (*header).cmsg_len = libc::CMSG_LEN(size_of::<i32>() as u32) as usize;
                (*header).cmsg_level = libc::SOL_SOCKET;
                (*header).cmsg_type = libc::SCM_RIGHTS;
                std::ptr::write_unaligned(libc::CMSG_DATA(header).cast::<i32>(), fd.as_raw_fd());
            }
        }
        loop {
            before(deadline)?;
            let result = unsafe {
                libc::sendmsg(
                    self.socket.as_raw_fd(),
                    &message,
                    libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
                )
            };
            if result < 0 {
                let error = io::Error::last_os_error();
                if error.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                if error.kind() == io::ErrorKind::WouldBlock {
                    let events = wait_event(self.socket.as_fd(), libc::POLLOUT, deadline)?;
                    if events & (libc::POLLOUT | libc::POLLHUP) != libc::POLLOUT {
                        return Err(NamespaceError::Rejected(
                            "activation peer closed before send",
                        ));
                    }
                    continue;
                }
                return Err(error.into());
            }
            before(deadline)?;
            if result as usize != wire::PACKET_BYTES {
                return Err(NamespaceError::Rejected("partial activation record send"));
            }
            self.revalidate()?;
            return Ok(());
        }
    }

    pub(super) fn receive(&self, rights: Rights, deadline: u64) -> Result<Received> {
        self.revalidate()?;
        loop {
            before(deadline)?;
            let events = wait_event(self.socket.as_fd(), libc::POLLIN, deadline)?;
            if events & (libc::POLLIN | libc::POLLHUP) != libc::POLLIN {
                return Err(NamespaceError::Rejected(
                    "activation peer closed before record",
                ));
            }
            let mut packet = wire::Packet::empty(0);
            let mut data = [0_u8; wire::DIAGNOSTIC_CHUNK];
            let mut iov = [
                libc::iovec {
                    iov_base: (&mut packet as *mut wire::Packet).cast(),
                    iov_len: wire::PACKET_BYTES,
                },
                libc::iovec {
                    iov_base: data.as_mut_ptr().cast(),
                    iov_len: data.len(),
                },
            ];
            // More than enough for the one allowed FD and credentials. Any
            // delivered extra rights are owned and closed before rejection;
            // the kernel closes rights discarded through MSG_CTRUNC.
            let mut control = [0_usize; 32];
            let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
            message.msg_iov = iov.as_mut_ptr();
            message.msg_iovlen = iov.len();
            message.msg_control = control.as_mut_ptr().cast();
            message.msg_controllen = size_of_val(&control);
            let result = unsafe {
                libc::recvmsg(
                    self.socket.as_raw_fd(),
                    &mut message,
                    libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
                )
            };
            if result < 0 {
                let error = io::Error::last_os_error();
                if matches!(
                    error.kind(),
                    io::ErrorKind::Interrupted | io::ErrorKind::WouldBlock
                ) {
                    continue;
                }
                return Err(error.into());
            }
            // Parse every delivered right before any header/deadline failure,
            // so malformed records cannot leak received descriptors.
            let (credentials, mut descriptors, invalid_control) = ancillary(&message)?;
            before(deadline)?;
            if message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
                || invalid_control
                || !packet.header_is_fixed()
                || packet.data_length as usize > data.len()
                || result as usize != wire::PACKET_BYTES + packet.data_length as usize
            {
                return Err(NamespaceError::Rejected(
                    "activation record framing or ancillary shape",
                ));
            }
            let c = credentials.ok_or(NamespaceError::Rejected(
                "activation record credentials absent",
            ))?;
            if c.pid != self.credentials.pid
                || c.uid != self.credentials.uid
                || c.gid != self.credentials.gid
            {
                return Err(NamespaceError::Rejected(
                    "activation record actual sender differs",
                ));
            }
            let correct = match rights {
                Rights::None => descriptors.is_empty(),
                Rights::One => descriptors.len() == 1,
                Rights::Optional => descriptors.len() <= 1,
            };
            if !correct {
                return Err(NamespaceError::Rejected(
                    "activation record descriptor count",
                ));
            }
            for fd in &descriptors {
                let flags = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFD) };
                if flags < 0 {
                    return Err(io::Error::last_os_error().into());
                }
                if flags & libc::FD_CLOEXEC == 0 {
                    return Err(NamespaceError::Rejected(
                        "activation received descriptor lacks CLOEXEC",
                    ));
                }
            }
            self.revalidate()?;
            before(deadline)?;
            return Ok(Received {
                packet,
                descriptor: descriptors.pop(),
                data: data[..packet.data_length as usize].to_vec(),
            });
        }
    }
}

fn ancillary(message: &libc::msghdr) -> Result<(Option<libc::ucred>, Vec<OwnedFd>, bool)> {
    let mut credentials = None;
    let mut descriptors = Vec::new();
    let mut invalid = false;
    let mut header = unsafe { libc::CMSG_FIRSTHDR(message) };
    while !header.is_null() {
        let h = unsafe { &*header };
        let base = unsafe { libc::CMSG_LEN(0) } as usize;
        if h.cmsg_len < base {
            return Err(NamespaceError::Rejected("invalid kernel ancillary length"));
        }
        let bytes = h.cmsg_len - base;
        let value = unsafe { libc::CMSG_DATA(header) };
        if h.cmsg_level == libc::SOL_SOCKET && h.cmsg_type == libc::SCM_RIGHTS {
            invalid |= bytes == 0 || bytes % size_of::<i32>() != 0;
            for offset in (0..bytes / size_of::<i32>()).map(|i| i * size_of::<i32>()) {
                let raw = unsafe { std::ptr::read_unaligned(value.add(offset).cast::<i32>()) };
                if raw < 0 {
                    invalid = true;
                } else {
                    descriptors.push(unsafe { OwnedFd::from_raw_fd(raw) });
                }
            }
        } else if h.cmsg_level == libc::SOL_SOCKET
            && h.cmsg_type == libc::SCM_CREDENTIALS
            && bytes == size_of::<libc::ucred>()
        {
            invalid |= credentials.is_some();
            credentials = Some(unsafe { std::ptr::read_unaligned(value.cast::<libc::ucred>()) });
        } else {
            invalid = true;
        }
        header = unsafe { libc::CMSG_NXTHDR(message, header) };
    }
    Ok((credentials, descriptors, invalid))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pair() -> [OwnedFd; 2] {
        let mut raw = [-1; 2];
        assert_eq!(
            unsafe {
                libc::socketpair(
                    libc::AF_UNIX,
                    libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                    0,
                    raw.as_mut_ptr(),
                )
            },
            0
        );
        let pair = unsafe { [OwnedFd::from_raw_fd(raw[0]), OwnedFd::from_raw_fd(raw[1])] };
        for socket in &pair {
            let one = 1_i32;
            assert_eq!(
                unsafe {
                    libc::setsockopt(
                        socket.as_raw_fd(),
                        libc::SOL_SOCKET,
                        libc::SO_PASSCRED,
                        (&one as *const i32).cast(),
                        size_of_val(&one) as _,
                    )
                },
                0
            );
        }
        pair
    }

    #[test]
    fn activation_channel_real_credentials_single_right_and_deadline() {
        let sockets = pair();
        let sender = Channel::observe(&sockets[0]).unwrap();
        let receiver = Channel::observe(&sockets[1]).unwrap();
        let file = tempfile::tempfile().unwrap();
        let packet = wire::Packet::empty(wire::CHILD);
        let deadline = monotonic_ns().unwrap() + 1_000_000_000;
        sender.send(&packet, Some(file.as_fd()), deadline).unwrap();
        let received = receiver.receive(Rights::One, deadline).unwrap();
        let passed = received.descriptor.unwrap();
        let held: File = passed.into();
        assert_eq!(Node::of(&held).unwrap(), Node::of(&file).unwrap());
        assert_eq!(received.packet.phase, wire::CHILD);
        assert!(received.data.is_empty());
        assert_ne!(
            unsafe { libc::fcntl(held.as_raw_fd(), libc::F_GETFD) } & libc::FD_CLOEXEC,
            0
        );
        // Even a queued real record must not turn an expired budget into a
        // successful read. The record remains for the next valid observation.
        sender.send(&packet, None, deadline).unwrap();
        match receiver.receive(Rights::None, monotonic_ns().unwrap()) {
            Err(NamespaceError::Io(error)) => assert_eq!(error.kind(), io::ErrorKind::TimedOut),
            _ => panic!("expired receive did not produce the exact deadline error"),
        }
        assert_eq!(
            receiver
                .receive(Rights::None, deadline)
                .unwrap()
                .packet
                .phase,
            wire::CHILD
        );
    }

    #[test]
    fn activation_channel_rejected_right_is_actually_closed() {
        let sockets = pair();
        let sender = Channel::observe(&sockets[0]).unwrap();
        let receiver = Channel::observe(&sockets[1]).unwrap();
        let mut raw = [-1; 2];
        assert_eq!(
            unsafe { libc::pipe2(raw.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) },
            0
        );
        let reader = unsafe { OwnedFd::from_raw_fd(raw[0]) };
        let writer = unsafe { OwnedFd::from_raw_fd(raw[1]) };
        let deadline = monotonic_ns().unwrap() + 1_000_000_000;
        sender
            .send(
                &wire::Packet::empty(wire::HELLO),
                Some(writer.as_fd()),
                deadline,
            )
            .unwrap();
        drop(writer);
        match receiver.receive(Rights::None, deadline) {
            Err(NamespaceError::Rejected("activation record descriptor count")) => {}
            _ => panic!("unexpected received right was not rejected exactly"),
        }
        let mut byte = [0_u8];
        assert_eq!(
            unsafe { libc::read(reader.as_raw_fd(), byte.as_mut_ptr().cast(), 1) },
            0,
            "the refused transferred writer must really be closed, not leaked"
        );
    }
}
