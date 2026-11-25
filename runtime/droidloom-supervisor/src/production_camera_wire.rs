//! Source-owned camera bootstrap and fixed, byte-only Android stream protocol.
use super::{Result, reject, require};
use std::fs::File;
use std::io;
use std::mem;
use std::os::fd::{FromRawFd, RawFd};
use std::time::Instant;

pub(super) const INITIALIZE: u8 = 1;
pub(super) const READY: u8 = 2;
pub(super) const FAILED: u8 = 3;
const MAGIC: &[u8; 8] = b"DLCOWN01";
const WIRE_BYTES: usize = 48;
pub(super) const PUBLIC_MAGIC: &[u8; 8] = b"DLCAM01\0";
pub(super) const STOP: &[u8; 8] = b"DLCSTOP1";
pub(super) const MAX_JPEG: u32 = 4 * 1024 * 1024;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) struct Wire {
    pub(super) phase: u8,
    pub(super) uid: u32,
    pub(super) gid: u32,
    pub(super) error: u32,
    pub(super) nonce: [u8; 16],
    pub(super) deadline_ns: u64,
}
impl Wire {
    fn bytes(self) -> [u8; WIRE_BYTES] {
        let mut bytes = [0; WIRE_BYTES];
        bytes[..8].copy_from_slice(MAGIC);
        bytes[8] = self.phase;
        bytes[12..16].copy_from_slice(&self.uid.to_le_bytes());
        bytes[16..20].copy_from_slice(&self.gid.to_le_bytes());
        bytes[20..24].copy_from_slice(&self.error.to_le_bytes());
        bytes[24..40].copy_from_slice(&self.nonce);
        bytes[40..48].copy_from_slice(&self.deadline_ns.to_le_bytes());
        bytes
    }
    fn parse(bytes: &[u8]) -> Result<Self> {
        require(
            bytes.len() == WIRE_BYTES
                && &bytes[..8] == MAGIC
                && bytes[9..12] == [0; 3]
                && matches!(bytes[8], INITIALIZE | READY | FAILED),
            "camera ownership record format differs",
        )?;
        let value = Self {
            phase: bytes[8],
            uid: u32::from_le_bytes(bytes[12..16].try_into().unwrap()),
            gid: u32::from_le_bytes(bytes[16..20].try_into().unwrap()),
            error: u32::from_le_bytes(bytes[20..24].try_into().unwrap()),
            nonce: bytes[24..40].try_into().unwrap(),
            deadline_ns: u64::from_le_bytes(bytes[40..48].try_into().unwrap()),
        };
        require(
            value.uid >= 65536
                && value.gid >= 65536
                && value.nonce != [0; 16]
                && value.deadline_ns > 0
                && if value.phase == FAILED {
                    (1..=4095).contains(&value.error)
                } else {
                    value.error == 0
                },
            "camera ownership record has invalid identities, nonce or status",
        )?;
        Ok(value)
    }
}
pub(super) struct Received {
    pub(super) wire: Wire,
    pub(super) files: Vec<File>,
    pub(super) peer: libc::ucred,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum Request {
    Probe,
    Stream,
}
impl Request {
    pub(super) fn parse(bytes: &[u8; 12]) -> Result<Self> {
        require(&bytes[..8] == PUBLIC_MAGIC, "camera request magic differs")?;
        match u32::from_be_bytes(bytes[8..12].try_into().unwrap()) {
            1 => Ok(Self::Probe),
            2 => Ok(Self::Stream),
            _ => Err(reject(
                "camera request is not a fixed probe or Surface stream",
            )),
        }
    }
}
pub(super) fn response(available: bool) -> [u8; 32] {
    let mut result = [0; 32];
    result[..8].copy_from_slice(PUBLIC_MAGIC);
    let fields = if available {
        [0, 640, 480, 30, MAX_JPEG, 0]
    } else {
        [1, 0, 0, 0, 0, 0]
    };
    for (offset, value) in fields.into_iter().enumerate() {
        result[8 + 4 * offset..12 + 4 * offset].copy_from_slice(&value.to_be_bytes());
    }
    result
}
pub(super) fn wait(fd: RawFd, events: i16, deadline: Instant) -> Result<()> {
    loop {
        let left = deadline.saturating_duration_since(Instant::now());
        require(!left.is_zero(), "camera ownership absolute deadline")?;
        let mut p = libc::pollfd {
            fd,
            events,
            revents: 0,
        };
        let count = unsafe { libc::poll(&mut p, 1, left.as_millis().clamp(1, 20) as i32) };
        if count < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error.into());
        }
        if count > 0 {
            require(
                p.revents & (libc::POLLERR | libc::POLLNVAL) == 0,
                "camera ownership invalid channel",
            )?;
            if p.revents & (events | libc::POLLHUP) != 0 {
                return Ok(());
            }
        }
    }
}
pub(super) fn send(socket: RawFd, wire: Wire, files: &[RawFd], deadline: Instant) -> Result<()> {
    require(files.len() <= 6, "camera ownership descriptor send bound")?;
    let bytes = wire.bytes();
    loop {
        require(Instant::now() < deadline, "camera ownership send deadline")?;
        let mut vector = libc::iovec {
            iov_base: bytes.as_ptr().cast_mut().cast(),
            iov_len: bytes.len(),
        };
        let mut control = [0_usize; 16];
        let mut header: libc::msghdr = unsafe { mem::zeroed() };
        header.msg_iov = &mut vector;
        header.msg_iovlen = 1;
        if !files.is_empty() {
            header.msg_control = control.as_mut_ptr().cast();
            header.msg_controllen =
                unsafe { libc::CMSG_SPACE(mem::size_of_val(files) as u32) } as usize;
            let cmsg = unsafe { libc::CMSG_FIRSTHDR(&header) };
            require(!cmsg.is_null(), "camera ownership rights header absent")?;
            unsafe {
                (*cmsg).cmsg_level = libc::SOL_SOCKET;
                (*cmsg).cmsg_type = libc::SCM_RIGHTS;
                (*cmsg).cmsg_len = libc::CMSG_LEN(mem::size_of_val(files) as u32) as usize;
                std::ptr::copy_nonoverlapping(
                    files.as_ptr().cast::<u8>(),
                    libc::CMSG_DATA(cmsg),
                    mem::size_of_val(files),
                );
            }
        }
        let count =
            unsafe { libc::sendmsg(socket, &header, libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL) };
        if count >= 0 {
            return require(
                count as usize == bytes.len(),
                "partial camera ownership seqpacket",
            );
        }
        let error = io::Error::last_os_error();
        if error.kind() == io::ErrorKind::Interrupted {
            continue;
        }
        if error.kind() != io::ErrorKind::WouldBlock {
            return Err(error.into());
        }
        wait(socket, libc::POLLOUT, deadline)?;
    }
}
pub(super) fn receive(socket: RawFd, expected_files: usize, deadline: Instant) -> Result<Received> {
    require(
        expected_files <= 6,
        "camera ownership receive descriptor bound",
    )?;
    loop {
        require(
            Instant::now() < deadline,
            "camera ownership receive deadline",
        )?;
        let mut bytes = [0_u8; WIRE_BYTES];
        let mut vector = libc::iovec {
            iov_base: bytes.as_mut_ptr().cast(),
            iov_len: bytes.len(),
        };
        // Larger than the permitted input: every received right is adopted even
        // when the sender supplies extra descriptors, truncates data, or spoofs
        // the fixed protocol. The kernel closes any truncated excess rights.
        let mut control = [0_usize; 128];
        let mut header: libc::msghdr = unsafe { mem::zeroed() };
        header.msg_iov = &mut vector;
        header.msg_iovlen = 1;
        header.msg_control = control.as_mut_ptr().cast();
        header.msg_controllen = mem::size_of_val(&control);
        let count = unsafe {
            libc::recvmsg(
                socket,
                &mut header,
                libc::MSG_CMSG_CLOEXEC | libc::MSG_DONTWAIT,
            )
        };
        if count < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            if error.kind() != io::ErrorKind::WouldBlock {
                return Err(error.into());
            }
            wait(socket, libc::POLLIN, deadline)?;
            continue;
        }
        let mut files = Vec::new();
        let mut peer = None;
        let mut malformed = false;
        let mut rights_messages = 0;
        let mut cmsg = unsafe { libc::CMSG_FIRSTHDR(&header) };
        while !cmsg.is_null() {
            let fixed = unsafe { libc::CMSG_LEN(0) } as usize;
            let size = unsafe { (*cmsg).cmsg_len };
            if size < fixed {
                malformed = true;
                break;
            }
            let payload = size - fixed;
            if unsafe { (*cmsg).cmsg_level } == libc::SOL_SOCKET
                && unsafe { (*cmsg).cmsg_type } == libc::SCM_RIGHTS
            {
                rights_messages += 1;
                if payload % mem::size_of::<i32>() != 0 {
                    malformed = true;
                }
                for offset in
                    (0..payload / mem::size_of::<i32>()).map(|i| i * mem::size_of::<i32>())
                {
                    let raw = unsafe {
                        std::ptr::read_unaligned(libc::CMSG_DATA(cmsg).add(offset).cast::<i32>())
                    };
                    if raw < 0 {
                        malformed = true;
                    } else {
                        files.push(unsafe { File::from_raw_fd(raw) });
                    }
                }
            } else if unsafe { (*cmsg).cmsg_level } == libc::SOL_SOCKET
                && unsafe { (*cmsg).cmsg_type } == libc::SCM_CREDENTIALS
                && payload == mem::size_of::<libc::ucred>()
            {
                let value = unsafe {
                    std::ptr::read_unaligned(libc::CMSG_DATA(cmsg).cast::<libc::ucred>())
                };
                if peer.replace(value).is_some() {
                    malformed = true;
                }
            } else {
                malformed = true;
            }
            cmsg = unsafe { libc::CMSG_NXTHDR(&header, cmsg) };
        }
        require(
            count as usize == WIRE_BYTES
                && header.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) == 0
                && !malformed
                && rights_messages == 1
                && files.len() == expected_files,
            "camera ownership message or descriptor custody differs",
        )?;
        return Ok(Received {
            wire: Wire::parse(&bytes)?,
            files,
            peer: peer.ok_or_else(|| reject("camera ownership sender credentials absent"))?,
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fixed_public_camera_contract_rejects_unselected_operations() {
        let mut request = [0; 12];
        request[..8].copy_from_slice(PUBLIC_MAGIC);
        for (op, expected) in [(1u32, Request::Probe), (2, Request::Stream)] {
            request[8..].copy_from_slice(&op.to_be_bytes());
            assert_eq!(Request::parse(&request).unwrap(), expected);
        }
        for op in [0u32, 3, 0x01000000, u32::MAX] {
            request[8..].copy_from_slice(&op.to_be_bytes());
            assert!(Request::parse(&request).is_err());
        }
        request[0] ^= 1;
        assert!(Request::parse(&request).is_err());
        assert_eq!(
            &response(false)[8..],
            &[
                0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
            ]
        );
        assert_eq!(
            u32::from_be_bytes(response(true)[24..28].try_into().unwrap()),
            MAX_JPEG
        );
    }
    #[test]
    fn ownership_records_bind_nonce_ids_deadline_and_real_error() {
        let record = Wire {
            phase: INITIALIZE,
            uid: 165536,
            gid: 165536,
            error: 0,
            nonce: [0x12; 16],
            deadline_ns: 100,
        };
        assert_eq!(Wire::parse(&record.bytes()).unwrap(), record);
        for index in [0usize, 8, 9] {
            let mut bad = record.bytes();
            bad[index] = 0xff;
            assert!(Wire::parse(&bad).is_err());
        }
        assert!(Wire::parse(&record.bytes()[..47]).is_err());
        for invalid in [
            Wire { uid: 0, ..record },
            Wire { gid: 0, ..record },
            Wire {
                nonce: [0; 16],
                ..record
            },
            Wire {
                deadline_ns: 0,
                ..record
            },
            Wire {
                error: 13,
                ..record
            },
            Wire {
                phase: FAILED,
                ..record
            },
        ] {
            assert!(Wire::parse(&invalid.bytes()).is_err());
        }
        let failed = Wire {
            phase: FAILED,
            error: 13,
            ..record
        };
        assert_eq!(Wire::parse(&failed.bytes()).unwrap(), failed);
    }
}
