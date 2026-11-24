//! Finite window commands carried only by the original frontend grant channel.
//! Serialized object numbers are observations; a live Session and presenter-owned
//! creation/binding history supply authority. This module grants no acceptance.
use serde::{Deserialize, Serialize};
use std::io;
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};

const MAX_PACKET: usize = 192 * 1024;
pub(crate) const MAX_PNG_BYTES: usize = 36 * 1024 * 1024;
pub(crate) const CAPTURE_CHUNK_BYTES: usize = 128 * 1024;

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    Observe,
    Capture,
    StopCapture,
    Tap { x: u32, y: u32 },
    Back,
    Key { keycode: u32 },
    Close,
}
impl Action {
    pub(crate) fn validate(&self) -> io::Result<()> {
        match self {
            Self::Tap { x, y } if *x >= 16_384 || *y >= 16_384 => {
                Err(invalid("tap is outside the fixed Android extent"))
            }
            // Linux evdev text/navigation keys only. No power, sleep, reboot,
            // media, modifier combinations, Home or global Overview operation.
            Self::Key { keycode }
                if !matches!(*keycode,
                2..=13 | 14 | 15 | 16..=27 | 28 | 30..=41 | 43..=53 |
                57 | 71..=83 | 96 | 98 | 102..=111) =>
            {
                Err(invalid(
                    "key is not an admitted application text/navigation key",
                ))
            }
            _ => Ok(()),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    Armed,
    Bound,
    CloseRequested,
    Destroyed,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Observation {
    pub lease: [u8; 16],
    pub package: String,
    pub phase: Phase,
    pub object: Option<u64>,
    pub android_task: Option<u64>,
    pub creation_serial: Option<u64>,
    pub mapped: bool,
    pub focused: bool,
    pub size: [u32; 2],
    pub submitted_frames: u64,
    pub capture_enabled: bool,
    pub last_input_serial: u64,
    pub close_requested: bool,
    pub destroy_observed: bool,
}
impl Observation {
    pub(crate) fn validate(&self) -> io::Result<()> {
        valid_token(self.lease)?;
        valid_package(&self.package)?;
        require(
            self.size.iter().all(|n| *n <= 16_384),
            "window extent exceeds bound",
        )?;
        let bound = self.object.is_some_and(|n| n > 0)
            && self.android_task.is_some_and(|n| n > 0)
            && self.creation_serial.is_some_and(|n| n > 0);
        require(
            match self.phase {
                Phase::Armed => {
                    self.object.is_none()
                        && self.android_task.is_none()
                        && self.creation_serial.is_none()
                        && !self.destroy_observed
                        && !self.close_requested
                        && !self.mapped
                        && !self.focused
                }
                Phase::Bound => bound && !self.close_requested && !self.destroy_observed,
                Phase::CloseRequested => bound && self.close_requested && !self.destroy_observed,
                Phase::Destroyed => bound && self.destroy_observed && !self.mapped && !self.focused,
            },
            "inconsistent original window observation",
        )
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CaptureMeta {
    pub capture: [u8; 16],
    pub object: u64,
    pub frame: u64,
    pub buffer: u64,
    pub width: u32,
    pub height: u32,
    pub captured_monotonic_ns: u64,
    /// Host input transmission sequence before capture, not Android UI acknowledgment.
    pub host_last_input_serial: u64,
    pub total_png_bytes: u64,
}
impl CaptureMeta {
    fn validate(&self) -> io::Result<()> {
        valid_token(self.capture)?;
        require(
            self.object > 0
                && self.frame > 0
                && self.buffer > 0
                && self.width > 0
                && self.width <= 4096
                && self.height > 0
                && self.height <= 4096
                && u64::from(self.width) * u64::from(self.height) <= 8 * 1024 * 1024
                && self.captured_monotonic_ns > 0
                && self.total_png_bytes >= 8
                && self.total_png_bytes <= MAX_PNG_BYTES as u64,
            "invalid original capture metadata",
        )
    }
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Image {
    pub original: CaptureMeta,
    pub sha256: String,
    pub png_base64: String,
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct CapturePart {
    pub(crate) original: CaptureMeta,
    pub(crate) offset: u64,
    pub(crate) bytes_base64: String,
}
impl CapturePart {
    pub(crate) fn decode(&self) -> io::Result<Vec<u8>> {
        use base64::Engine;
        self.original.validate()?;
        require(
            self.offset < self.original.total_png_bytes
                && self.offset % CAPTURE_CHUNK_BYTES as u64 == 0
                && self.bytes_base64.len() <= CAPTURE_CHUNK_BYTES.div_ceil(3) * 4,
            "capture part offset or size is invalid",
        )?;
        let bytes = base64::engine::general_purpose::STANDARD
            .decode(&self.bytes_base64)
            .map_err(io::Error::other)?;
        require(
            bytes.len() as u64
                == (self.original.total_png_bytes - self.offset).min(CAPTURE_CHUNK_BYTES as u64),
            "capture part is incomplete",
        )?;
        Ok(bytes)
    }
    fn validate(&self) -> io::Result<()> {
        self.decode().map(|_| ())
    }
    pub(crate) fn from_bytes(original: CaptureMeta, bytes: &[u8], offset: u64) -> io::Result<Self> {
        use base64::Engine;
        original.validate()?;
        require(
            original.total_png_bytes == bytes.len() as u64
                && offset < bytes.len() as u64
                && offset % CAPTURE_CHUNK_BYTES as u64 == 0,
            "capture does not match the original copied PNG",
        )?;
        let start = offset as usize;
        let end = bytes.len().min(start + CAPTURE_CHUNK_BYTES);
        Ok(Self {
            original,
            offset,
            bytes_base64: base64::engine::general_purpose::STANDARD.encode(&bytes[start..end]),
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "operation", rename_all = "snake_case", deny_unknown_fields)]
pub(crate) enum Command {
    Arm {
        lease: [u8; 16],
        package: String,
    },
    Bind {
        lease: [u8; 16],
        object: u64,
        task: u64,
    },
    Action {
        lease: [u8; 16],
        action: Action,
    },
    CaptureChunk {
        lease: [u8; 16],
        capture: [u8; 16],
        offset: u64,
    },
}
impl Command {
    pub(crate) fn lease(&self) -> [u8; 16] {
        match self {
            Self::Arm { lease, .. }
            | Self::Bind { lease, .. }
            | Self::Action { lease, .. }
            | Self::CaptureChunk { lease, .. } => *lease,
        }
    }
    fn validate(&self) -> io::Result<()> {
        valid_token(self.lease())?;
        match self {
            Self::Arm { package, .. } => valid_package(package),
            Self::Bind { object, task, .. } => {
                require(*object > 0 && *task > 0, "empty task binding")
            }
            Self::Action { action, .. } => action.validate(),
            Self::CaptureChunk {
                capture, offset, ..
            } => {
                valid_token(*capture)?;
                require(
                    *offset < MAX_PNG_BYTES as u64,
                    "capture offset exceeds bound",
                )
            }
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Request {
    pub(crate) nonce: [u8; 16],
    pub(crate) serial: u64,
    pub(crate) command: Command,
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Reply {
    pub(crate) nonce: [u8; 16],
    pub(crate) serial: u64,
    pub(crate) observation: Option<Observation>,
    pub(crate) error: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) capture: Option<CapturePart>,
}
impl Reply {
    pub(crate) fn result(&self) -> io::Result<&Observation> {
        require(
            self.error.is_none(),
            self.error.as_deref().unwrap_or("window request refused"),
        )?;
        self.observation
            .as_ref()
            .ok_or_else(|| invalid("window reply lacks an observation"))
    }
}

/// An original kernel process handle retained by the broker, never deserialized.
pub(crate) struct Session {
    pidfd: OwnedFd,
    node: (u64, u64),
    nonce: [u8; 16],
}
impl Session {
    pub(crate) fn acquire(pidfd: &OwnedFd, nonce: [u8; 16]) -> io::Result<Self> {
        valid_token(nonce)?;
        live(pidfd)?;
        Ok(Self {
            pidfd: pidfd.try_clone()?,
            node: node(pidfd)?,
            nonce,
        })
    }
    pub(crate) fn revalidate(&self, pidfd: &OwnedFd, nonce: [u8; 16]) -> io::Result<()> {
        live(&self.pidfd)?;
        live(pidfd)?;
        require(
            self.nonce == nonce && node(&self.pidfd)? == self.node && node(pidfd)? == self.node,
            "window lease belongs to a different original presenter",
        )
    }
}
fn node(fd: &OwnedFd) -> io::Result<(u64, u64)> {
    let mut s: libc::stat = unsafe { mem::zeroed() };
    if unsafe { libc::fstat(fd.as_raw_fd(), &mut s) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok((s.st_dev, s.st_ino))
}
fn live(fd: &OwnedFd) -> io::Result<()> {
    let mut p = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    if unsafe { libc::poll(&mut p, 1, 0) } < 0 {
        return Err(io::Error::last_os_error());
    }
    require(p.revents == 0, "original window presenter pidfd exited")
}

pub(crate) fn send_request(fd: &impl AsRawFd, request: &Request) -> io::Result<()> {
    request.command.validate()?;
    valid_token(request.nonce)?;
    require(request.serial > 0, "empty window request serial")?;
    send(fd, b"DLWREQ01", request)
}
pub(crate) fn receive_request(fd: &impl AsRawFd) -> io::Result<Option<Request>> {
    let Some(r): Option<Request> = receive(fd, b"DLWREQ01")? else {
        return Ok(None);
    };
    valid_token(r.nonce)?;
    require(r.serial > 0, "empty window request serial")?;
    r.command.validate()?;
    Ok(Some(r))
}
pub(crate) fn send_reply(fd: &impl AsRawFd, reply: &Reply) -> io::Result<()> {
    validate_reply(reply)?;
    send(fd, b"DLWREP01", reply)
}
pub(crate) fn receive_reply(fd: &impl AsRawFd) -> io::Result<Option<Reply>> {
    let value = receive(fd, b"DLWREP01")?;
    if let Some(r) = &value {
        validate_reply(r)?;
    }
    Ok(value)
}
fn validate_reply(r: &Reply) -> io::Result<()> {
    valid_token(r.nonce)?;
    require(
        r.serial > 0
            && r.error
                .as_ref()
                .is_none_or(|s| !s.is_empty() && s.len() <= 512),
        "invalid window reply",
    )?;
    require(
        r.error.is_some() || r.observation.is_some(),
        "empty window reply",
    )?;
    if let Some(o) = &r.observation {
        o.validate()?;
    }
    if let Some(c) = &r.capture {
        c.validate()?;
    }
    Ok(())
}
fn send(fd: &impl AsRawFd, magic: &[u8; 8], value: &impl Serialize) -> io::Result<()> {
    let mut bytes = magic.to_vec();
    bytes.extend(serde_json::to_vec(value).map_err(io::Error::other)?);
    require(bytes.len() <= MAX_PACKET, "window record exceeds bound")?;
    let n = unsafe {
        libc::send(
            fd.as_raw_fd(),
            bytes.as_ptr().cast(),
            bytes.len(),
            libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
        )
    };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    require(n as usize == bytes.len(), "partial window record send")
}
fn receive<T: serde::de::DeserializeOwned>(
    fd: &impl AsRawFd,
    magic: &[u8; 8],
) -> io::Result<Option<T>> {
    let mut bytes = [0u8; MAX_PACKET + 1];
    let mut vector = libc::iovec {
        iov_base: bytes.as_mut_ptr().cast(),
        iov_len: bytes.len(),
    };
    let mut control = [0usize; 32];
    let mut msg: libc::msghdr = unsafe { mem::zeroed() };
    msg.msg_iov = &mut vector;
    msg.msg_iovlen = 1;
    msg.msg_control = control.as_mut_ptr().cast();
    msg.msg_controllen = mem::size_of_val(&control);
    let n = unsafe {
        libc::recvmsg(
            fd.as_raw_fd(),
            &mut msg,
            libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
        )
    };
    if n < 0 {
        let e = io::Error::last_os_error();
        return if matches!(
            e.kind(),
            io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
        ) {
            Ok(None)
        } else {
            Err(e)
        };
    }
    // Close every received descriptor before rejecting ancillary data, including
    // a truncated malicious record. No descriptor can enter the window protocol.
    let mut fds = Vec::new();
    let mut ancillary = false;
    let mut c = unsafe { libc::CMSG_FIRSTHDR(&msg) };
    while !c.is_null() {
        ancillary = true;
        let length = unsafe { (*c).cmsg_len };
        let head = unsafe { libc::CMSG_LEN(0) } as usize;
        if length < head {
            break;
        }
        let kind = unsafe { (*c).cmsg_type };
        if unsafe { (*c).cmsg_level } == libc::SOL_SOCKET && (kind == libc::SCM_RIGHTS || kind == 4)
        {
            let data = unsafe { libc::CMSG_DATA(c) }.cast::<i32>();
            for index in 0..(length - head) / mem::size_of::<i32>() {
                let raw = unsafe { data.add(index).read_unaligned() };
                if raw >= 0 {
                    fds.push(unsafe { OwnedFd::from_raw_fd(raw) });
                }
            }
        }
        c = unsafe { libc::CMSG_NXTHDR(&msg, c) };
    }
    require(
        !ancillary
            && fds.is_empty()
            && msg.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) == 0
            && n as usize > 8
            && n as usize <= MAX_PACKET
            && &bytes[..8] == magic,
        "closed, oversized, ancillary or unexpected window record",
    )?;
    serde_json::from_slice(&bytes[8..n as usize])
        .map(Some)
        .map_err(io::Error::other)
}
pub(crate) fn fresh_token() -> io::Result<[u8; 16]> {
    let mut value = [0u8; 16];
    let mut done = 0;
    while done < value.len() {
        let n =
            unsafe { libc::getrandom(value[done..].as_mut_ptr().cast(), value.len() - done, 0) };
        if n < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(e);
        }
        require(n > 0, "kernel returned empty random token")?;
        done += n as usize;
    }
    valid_token(value)?;
    Ok(value)
}
pub(crate) fn valid_package(value: &str) -> io::Result<()> {
    require(
        !value.is_empty()
            && value.len() <= 255
            && value.contains('.')
            && value
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'_'),
        "invalid original window package",
    )
}
pub(crate) fn valid_token(value: [u8; 16]) -> io::Result<()> {
    require(value != [0; 16], "empty original window lease or nonce")
}
pub(crate) fn require(value: bool, message: &str) -> io::Result<()> {
    if value { Ok(()) } else { Err(invalid(message)) }
}
pub(crate) fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn pair() -> (OwnedFd, OwnedFd) {
        let mut fd = [-1; 2];
        assert_eq!(
            unsafe {
                libc::socketpair(
                    libc::AF_UNIX,
                    libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                    0,
                    fd.as_mut_ptr(),
                )
            },
            0
        );
        unsafe { (OwnedFd::from_raw_fd(fd[0]), OwnedFd::from_raw_fd(fd[1])) }
    }
    fn capture_meta(total: usize) -> CaptureMeta {
        CaptureMeta {
            capture: [3; 16],
            object: 4,
            frame: 5,
            buffer: 6,
            width: 64,
            height: 32,
            captured_monotonic_ns: 1,
            host_last_input_serial: 0,
            total_png_bytes: total as u64,
        }
    }
    #[test]
    fn window_wire_carries_maximum_capture_chunk_on_real_seqpacket() {
        let (a, b) = pair();
        let data = vec![17; CAPTURE_CHUNK_BYTES + 19];
        let meta = capture_meta(data.len());
        let part = CapturePart::from_bytes(meta.clone(), &data, 0).unwrap();
        let reply = Reply {
            nonce: [1; 16],
            serial: 1,
            observation: None,
            error: Some("transport test only".into()),
            capture: Some(part),
        };
        send_reply(&a, &reply).unwrap();
        let received = receive_reply(&b).unwrap().unwrap();
        assert_eq!(
            received.capture.unwrap().decode().unwrap(),
            &data[..CAPTURE_CHUNK_BYTES]
        );
        let tail = CapturePart::from_bytes(meta, &data, CAPTURE_CHUNK_BYTES as u64).unwrap();
        assert_eq!(tail.decode().unwrap(), &data[CAPTURE_CHUNK_BYTES..]);
    }
    #[test]
    fn window_capture_parts_reject_short_shifted_oversized_and_noncanonical_data() {
        let bytes = vec![0; CAPTURE_CHUNK_BYTES + 1];
        let mut p = CapturePart::from_bytes(capture_meta(bytes.len()), &bytes, 0).unwrap();
        p.offset = 1;
        assert!(p.decode().is_err());
        p.offset = 0;
        p.bytes_base64.pop();
        assert!(p.decode().is_err());
        assert!(CapturePart::from_bytes(capture_meta(MAX_PNG_BYTES + 1), &bytes, 0).is_err());
        assert!(
            CapturePart::from_bytes(capture_meta(bytes.len()), &bytes, bytes.len() as u64).is_err()
        );
    }
    #[test]
    fn window_session_rejects_nonce_change_and_observes_original_process_exit() {
        let mut child = std::process::Command::new("/usr/bin/sleep")
            .arg("30")
            .spawn()
            .unwrap();
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) } as i32;
        if raw < 0 {
            let _ = child.kill();
            let _ = child.wait();
            panic!("real pidfd_open failed");
        }
        let fd = unsafe { OwnedFd::from_raw_fd(raw) };
        let held = Session::acquire(&fd, [9; 16]).unwrap();
        let wrong = held.revalidate(&fd, [8; 16]).is_err();
        let valid = held.revalidate(&fd, [9; 16]).is_ok();
        child.kill().unwrap();
        child.wait().unwrap();
        assert!(wrong && valid && held.revalidate(&fd, [9; 16]).is_err());
    }
    fn request() -> Request {
        Request {
            nonce: [1; 16],
            serial: 1,
            command: Command::Arm {
                lease: [2; 16],
                package: "org.example.app".into(),
            },
        }
    }
    #[test]
    fn window_wire_uses_bounded_exact_typed_records() {
        let (a, b) = pair();
        send_request(&a, &request()).unwrap();
        assert_eq!(receive_request(&b).unwrap(), Some(request()));
        assert!(receive_request(&b).unwrap().is_none());
        send_request(&a, &request()).unwrap();
        assert!(receive_reply(&b).is_err());
    }
    #[test]
    fn window_wire_rejects_unknown_fields_and_eof() {
        let (a, b) = pair();
        let bytes = br#"DLWREQ01{"nonce":[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],"serial":1,"command":{"operation":"action","lease":[2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],"action":{"action":"close"},"path":"/foreign"}}"#;
        assert_eq!(
            unsafe { libc::send(a.as_raw_fd(), bytes.as_ptr().cast(), bytes.len(), 0) },
            bytes.len() as isize
        );
        assert!(receive_request(&b).is_err());
        drop(a);
        assert!(receive_request(&b).is_err());
    }
    #[test]
    fn window_wire_closes_injected_descriptors_even_on_truncation() {
        let (a, b) = pair();
        let (probe, observer) = pair();
        let mut bytes = [b'x'; MAX_PACKET + 1];
        bytes[..8].copy_from_slice(b"DLWREQ01");
        let mut v = libc::iovec {
            iov_base: bytes.as_mut_ptr().cast(),
            iov_len: bytes.len(),
        };
        let mut c = [0usize; 8];
        let mut m: libc::msghdr = unsafe { mem::zeroed() };
        m.msg_iov = &mut v;
        m.msg_iovlen = 1;
        m.msg_control = c.as_mut_ptr().cast();
        m.msg_controllen = unsafe { libc::CMSG_SPACE(mem::size_of::<i32>() as _) } as usize;
        let h = unsafe { libc::CMSG_FIRSTHDR(&m) };
        unsafe {
            (*h).cmsg_level = libc::SOL_SOCKET;
            (*h).cmsg_type = libc::SCM_RIGHTS;
            (*h).cmsg_len = libc::CMSG_LEN(mem::size_of::<i32>() as _) as usize;
            libc::CMSG_DATA(h)
                .cast::<i32>()
                .write_unaligned(probe.as_raw_fd());
        }
        assert!(unsafe { libc::sendmsg(a.as_raw_fd(), &m, 0) } > 0);
        drop(probe);
        assert!(receive_request(&b).is_err());
        let mut p = libc::pollfd {
            fd: observer.as_raw_fd(),
            events: libc::POLLHUP,
            revents: 0,
        };
        assert_eq!(unsafe { libc::poll(&mut p, 1, 0) }, 1);
        assert_ne!(p.revents & libc::POLLHUP, 0);
    }
    #[test]
    fn window_controls_exclude_global_power_and_out_of_bounds_inputs() {
        for code in [0, 1, 29, 42, 56, 116, 142, 143, 255] {
            assert!(Action::Key { keycode: code }.validate().is_err());
        }
        assert!(Action::Tap { x: 16384, y: 0 }.validate().is_err());
        assert!(Action::Key { keycode: 28 }.validate().is_ok());
        assert!(Action::Back.validate().is_ok());
    }
}
