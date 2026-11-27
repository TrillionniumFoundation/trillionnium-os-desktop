//! Private same-process-tree qualification packets, with per-message credentials.
//! SO_PEERCRED on a socketpair is the creator, not the later re-executed child.
use super::{error, monotonic_ns};
use std::fs::File;
use std::io;
use std::mem::{size_of, zeroed};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::time::Instant;

pub(super) const PAYLOAD_MAX: usize = 132 * 1024;
const HEADER: usize = 32;
const MAGIC: &[u8; 8] = b"P4QUAL01";
// Hello uses 0, each compiled case contributes Begin and End, and Complete
// uses the final sequence. ACK echoes that sequence without consuming another.
const MAX_SEQUENCE: u32 = 1 + 2 * super::CASE_COUNT as u32;

#[derive(Debug, PartialEq, Eq)]
pub(super) struct Packet {
    pub sequence: u32,
    pub kind: u8,
    pub case: u8,
    pub end_ns: u64,
    pub payload: Vec<u8>,
}

impl Packet {
    pub fn bytes(&self) -> io::Result<Vec<u8>> {
        if self.payload.len() > PAYLOAD_MAX
            || self.sequence > MAX_SEQUENCE
            || ![1, 2, 3, 4, 5].contains(&self.kind)
        {
            return Err(error("qualification packet bound or kind differs"));
        }
        let mut raw = Vec::with_capacity(HEADER + self.payload.len());
        raw.extend_from_slice(MAGIC);
        raw.extend_from_slice(&self.sequence.to_le_bytes());
        raw.extend_from_slice(&[self.kind, self.case, 0, 0]);
        raw.extend_from_slice(&self.end_ns.to_le_bytes());
        raw.extend_from_slice(&(self.payload.len() as u32).to_le_bytes());
        raw.extend_from_slice(&[0; 4]);
        raw.extend_from_slice(&self.payload);
        Ok(raw)
    }

    fn parse(raw: &[u8]) -> io::Result<Self> {
        if raw.len() < HEADER
            || &raw[..8] != MAGIC
            || raw[14..16] != [0; 2]
            || raw[28..32] != [0; 4]
        {
            return Err(error("qualification packet header differs"));
        }
        let sequence = u32::from_le_bytes(raw[8..12].try_into().unwrap());
        let end_ns = u64::from_le_bytes(raw[16..24].try_into().unwrap());
        let size = u32::from_le_bytes(raw[24..28].try_into().unwrap()) as usize;
        if size > PAYLOAD_MAX || raw.len() != HEADER + size {
            return Err(error("qualification packet is truncated or oversized"));
        }
        let result = Self {
            sequence,
            kind: raw[12],
            case: raw[13],
            end_ns,
            payload: raw[HEADER..].to_vec(),
        };
        if result.bytes()?.as_slice() != raw {
            return Err(error("qualification packet is not canonical"));
        }
        Ok(result)
    }
}

pub(super) fn nonblocking(fd: RawFd) -> io::Result<()> {
    // SAFETY: fcntl operates on this caller-owned descriptor.
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
    if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

pub(super) fn wait(fd: RawFd, events: i16, end: Instant) -> io::Result<()> {
    loop {
        let remaining = end
            .checked_duration_since(Instant::now())
            .ok_or_else(|| error("qualification original deadline exhausted"))?;
        let millis = remaining.as_millis().max(1).min(i32::MAX as u128) as i32;
        let mut item = libc::pollfd {
            fd,
            events,
            revents: 0,
        };
        // SAFETY: item is one initialized pollfd, borrowed for this call.
        let rc = unsafe { libc::poll(&mut item, 1, millis) };
        if rc < 0 {
            if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(io::Error::last_os_error());
        }
        if Instant::now() >= end {
            return Err(error("qualification original deadline exhausted"));
        }
        if rc == 0 {
            continue;
        }
        if item.revents & events != 0 {
            return Ok(());
        }
        return Err(error("qualification channel closed or poll failed"));
    }
}

pub(super) struct Socket {
    pub file: File,
}

impl Socket {
    pub fn pair() -> io::Result<(Self, Self)> {
        let mut fds = [-1; 2];
        // SAFETY: fds has room for both returned socket descriptors.
        if unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                0,
                fds.as_mut_ptr(),
            )
        } != 0
        {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: successful socketpair returned two uniquely owned descriptors.
        let a = Self {
            file: unsafe { File::from_raw_fd(fds[0]) },
        };
        let b = Self {
            file: unsafe { File::from_raw_fd(fds[1]) },
        };
        a.configure()?;
        b.configure()?;
        Ok((a, b))
    }

    pub fn inherited() -> io::Result<Self> {
        // Dup instead of adopting an arbitrary caller-owned descriptor. The source
        // fixed child entry alone calls this; the parent verifies its exact argv.
        // SAFETY: F_DUPFD_CLOEXEC either returns a new owned FD or fails.
        let fd = unsafe { libc::fcntl(3, libc::F_DUPFD_CLOEXEC, 64) };
        if fd < 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: fd is the newly returned unique descriptor.
        let value = Self {
            file: unsafe { File::from_raw_fd(fd) },
        };
        value.configure()?;
        // SAFETY: this fixed inherited channel is consumed, not left to children.
        if unsafe { libc::close(3) } != 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(value)
    }

    fn configure(&self) -> io::Result<()> {
        for (option, expected) in [
            (libc::SO_TYPE, libc::SOCK_SEQPACKET),
            (libc::SO_DOMAIN, libc::AF_UNIX),
        ] {
            let mut actual = 0i32;
            let mut size = size_of::<i32>() as libc::socklen_t;
            // SAFETY: actual and size are initialized writable storage.
            if unsafe {
                libc::getsockopt(
                    self.file.as_raw_fd(),
                    libc::SOL_SOCKET,
                    option,
                    (&mut actual as *mut i32).cast(),
                    &mut size,
                )
            } != 0
            {
                return Err(io::Error::last_os_error());
            }
            if size as usize != size_of::<i32>() || actual != expected {
                return Err(error(
                    "qualification requires an actual UNIX seqpacket socket",
                ));
            }
        }
        let yes = 1i32;
        let buffer = 512 * 1024i32;
        for (option, value) in [
            (libc::SO_PASSCRED, yes),
            (libc::SO_SNDBUF, buffer),
            (libc::SO_RCVBUF, buffer),
        ] {
            // SAFETY: value is a correctly sized socket option.
            if unsafe {
                libc::setsockopt(
                    self.file.as_raw_fd(),
                    libc::SOL_SOCKET,
                    option,
                    (&value as *const i32).cast(),
                    size_of::<i32>() as _,
                )
            } != 0
            {
                return Err(io::Error::last_os_error());
            }
        }
        nonblocking(self.file.as_raw_fd())
    }

    pub fn send(&self, packet: &Packet, end: Instant) -> io::Result<()> {
        let raw = packet.bytes()?;
        loop {
            if Instant::now() >= end {
                return Err(error("qualification send expired"));
            }
            // SAFETY: raw is borrowed unchanged for its entire exact length.
            let rc = unsafe {
                libc::send(
                    self.file.as_raw_fd(),
                    raw.as_ptr().cast(),
                    raw.len(),
                    libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
                )
            };
            if rc >= 0 {
                if rc as usize != raw.len() {
                    return Err(error("partial qualification packet send"));
                }
                return Ok(());
            }
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            if e.kind() != io::ErrorKind::WouldBlock {
                return Err(e);
            }
            wait(self.file.as_raw_fd(), libc::POLLOUT, end)?;
        }
    }

    pub fn receive(&self, expected_pid: u32, end: Instant) -> io::Result<Packet> {
        loop {
            if let Some(packet) = self.try_receive(expected_pid)? {
                return Ok(packet);
            }
            wait(self.file.as_raw_fd(), libc::POLLIN, end)?;
        }
    }

    pub fn try_receive(&self, expected_pid: u32) -> io::Result<Option<Packet>> {
        let mut raw = vec![0u8; HEADER + PAYLOAD_MAX + 1];
        // usize alignment satisfies cmsghdr's alignment on this supported target.
        let mut control = [0usize; 128];
        let mut iov = libc::iovec {
            iov_base: raw.as_mut_ptr().cast(),
            iov_len: raw.len(),
        };
        // SAFETY: zeroed msghdr has no borrowed pointers until assigned below.
        let mut message: libc::msghdr = unsafe { zeroed() };
        message.msg_iov = &mut iov;
        message.msg_iovlen = 1;
        message.msg_control = control.as_mut_ptr().cast();
        message.msg_controllen = size_of::<[usize; 128]>();
        // SAFETY: raw/control/iov remain valid and writable for recvmsg.
        let n = unsafe {
            libc::recvmsg(
                self.file.as_raw_fd(),
                &mut message,
                libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
            )
        };
        if n < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::WouldBlock || e.kind() == io::ErrorKind::Interrupted {
                return Ok(None);
            }
            return Err(e);
        }
        let mut credentials = None;
        let mut bad = n == 0 || message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0;
        // SAFETY: CMSG iteration is restricted to the kernel-written ancillary extent.
        let mut c = unsafe { libc::CMSG_FIRSTHDR(&message) };
        while !c.is_null() {
            // SAFETY: each c is an ancillary header returned within message's storage.
            let header = unsafe { &*c };
            let base = unsafe { libc::CMSG_LEN(0) } as usize;
            if header.cmsg_len < base {
                bad = true;
                break;
            }
            let bytes = header.cmsg_len - base;
            if header.cmsg_level == libc::SOL_SOCKET && header.cmsg_type == libc::SCM_RIGHTS {
                // Reject all passed FDs, closing any the kernel actually installed.
                if bytes % size_of::<i32>() != 0 {
                    bad = true;
                }
                for i in 0..bytes / size_of::<i32>() {
                    // SAFETY: this rights payload contains kernel-installed i32 descriptors.
                    let fd = unsafe {
                        std::ptr::read_unaligned(libc::CMSG_DATA(c).cast::<i32>().add(i))
                    };
                    if fd >= 0 {
                        unsafe {
                            libc::close(fd);
                        }
                    }
                }
                bad = true;
            } else if header.cmsg_level == libc::SOL_SOCKET
                && header.cmsg_type == libc::SCM_CREDENTIALS
                && bytes == size_of::<libc::ucred>()
            {
                let cred =
                    unsafe { std::ptr::read_unaligned(libc::CMSG_DATA(c).cast::<libc::ucred>()) };
                if credentials
                    .replace((cred.pid, cred.uid, cred.gid))
                    .is_some()
                {
                    bad = true;
                }
            } else {
                bad = true;
            }
            c = unsafe { libc::CMSG_NXTHDR(&message, c) };
        }
        if bad || credentials != Some((expected_pid as libc::pid_t, 0, 0)) {
            return Err(error(
                "qualification message credential, ancillary or completeness mismatch",
            ));
        }
        raw.truncate(n as usize);
        Ok(Some(Packet::parse(&raw)?))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn complete_compiled_case_transcript_and_acks_fit_the_wire_bound() {
        // Hello is 0. Each actual case has Begin and End, then Complete.
        // ACK echoes its request sequence rather than consuming another number.
        assert_eq!(super::super::CASE_COUNT, 46);
        let mut requests = vec![(1, 255)];
        for ordinal in 0..super::super::CASE_COUNT {
            requests.push((2, u8::try_from(ordinal).unwrap()));
            requests.push((3, u8::try_from(ordinal).unwrap()));
        }
        requests.push((4, 255));
        assert_eq!(requests.len(), 2 + 2 * super::super::CASE_COUNT);
        for (sequence, (kind, case)) in requests.into_iter().enumerate() {
            let packet = Packet {
                sequence: u32::try_from(sequence).unwrap(),
                kind,
                case,
                end_ns: 900,
                payload: if kind == 1 || kind == 4 {
                    b"{}".to_vec()
                } else {
                    Vec::new()
                },
            };
            let raw = packet.bytes().unwrap_or_else(|error| {
                panic!("valid sequence {sequence}, kind {kind}, case {case}: {error}")
            });
            assert_eq!(Packet::parse(&raw).unwrap(), packet);
            let ack = Packet {
                kind: 5,
                payload: Vec::new(),
                ..packet
            };
            assert_eq!(Packet::parse(&ack.bytes().unwrap()).unwrap(), ack);
        }
    }

    #[test]
    fn terminal_sequence_is_exact_and_larger_wire_values_are_rejected() {
        let terminal = Packet {
            sequence: MAX_SEQUENCE,
            kind: 4,
            case: 255,
            end_ns: 900,
            payload: Vec::new(),
        };
        let raw = terminal.bytes().unwrap();
        assert_eq!(Packet::parse(&raw).unwrap(), terminal);
        for sequence in [MAX_SEQUENCE + 1, u32::MAX] {
            let packet = Packet {
                sequence,
                kind: terminal.kind,
                case: terminal.case,
                end_ns: terminal.end_ns,
                payload: Vec::new(),
            };
            assert!(packet.bytes().is_err());
            let mut changed = raw.clone();
            changed[8..12].copy_from_slice(&sequence.to_le_bytes());
            assert!(Packet::parse(&changed).is_err());
        }
    }
    #[test]
    fn exact_framing_rejects_suffix_reserved_truncation_and_unknown_kind() {
        let p = Packet {
            sequence: 3,
            kind: 2,
            case: 1,
            end_ns: 900,
            payload: b"abc".to_vec(),
        };
        let raw = p.bytes().unwrap();
        assert_eq!(Packet::parse(&raw).unwrap(), p);
        for cut in 0..raw.len() {
            assert!(Packet::parse(&raw[..cut]).is_err());
        }
        for index in [0, 14, 15, 28, 29, 30, 31] {
            let mut changed = raw.clone();
            changed[index] = 1;
            assert!(Packet::parse(&changed).is_err());
        }
        let mut changed = raw.clone();
        changed.push(0);
        assert!(Packet::parse(&changed).is_err());
        let mut changed = raw;
        changed[12] = 6;
        assert!(Packet::parse(&changed).is_err());
        let _ = monotonic_ns().unwrap();
    }
}

#[cfg(test)]
mod credential_tests {
    use super::*;
    #[test]
    fn physical_qualification_checks_actual_per_message_credentials_not_pair_creator_claims() {
        let (a, b) = Socket::pair().unwrap();
        let end = Instant::now() + std::time::Duration::from_secs(2);
        let packet = Packet {
            sequence: 0,
            kind: 1,
            case: 255,
            end_ns: 123,
            payload: vec![],
        };
        a.send(&packet, end).unwrap();
        let result = b.receive(std::process::id(), end);
        // Normal non-root focused workers cannot manufacture root credentials.
        if unsafe { libc::getuid() } == 0 && unsafe { libc::getgid() } == 0 {
            assert_eq!(result.unwrap(), packet);
        } else {
            assert!(result.is_err());
        }
        a.send(&packet, end).unwrap();
        assert!(b.receive(std::process::id() + 1, end).is_err());
    }
}
