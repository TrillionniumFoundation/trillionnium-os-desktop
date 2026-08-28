//! Authenticated, bounded AF_UNIX carrier for the desktop Agent port.
//!
//! This crate deliberately does not create a listener. It accepts an already
//! connected `UnixStream`, verifies peer credentials, establishes a fresh
//! per-connection nonce, and carries bounded, digest-bound frames under one
//! absolute deadline per operation. The systemd socket unit, path ownership,
//! service UID, cgroup binding, and production listener remain later gates.

#![cfg_attr(
    not(any(target_os = "linux", target_os = "android")),
    allow(dead_code)
)]
#![deny(unsafe_op_in_unsafe_fn)]

use sha2::{Digest, Sha256};
use std::fmt;
use std::fs::File;
use std::io::{self, Read, Write};
use std::os::unix::net::UnixStream;
use std::time::{Duration, Instant};

pub const PROTOCOL_MAGIC: [u8; 8] = *b"HEPTA001";
pub const PROTOCOL_VERSION: u16 = 1;
pub const HEADER_BYTES: usize = 88;
pub const NONCE_BYTES: usize = 32;
pub const DIGEST_BYTES: usize = 32;
pub const MAX_PAYLOAD_BYTES: usize = 262_144;
pub const DEFAULT_OPERATION_TIMEOUT: Duration = Duration::from_secs(20);
const CHALLENGE_PAYLOAD: &[u8] = b"trillionnium.desktop.agent-transport.v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum FrameKind {
    Challenge = 1,
    Request = 2,
    Response = 3,
    Event = 4,
    Close = 5,
}

impl TryFrom<u8> for FrameKind {
    type Error = TransportError;

    fn try_from(value: u8) -> Result<Self, Self::Error> {
        match value {
            1 => Ok(Self::Challenge),
            2 => Ok(Self::Request),
            3 => Ok(Self::Response),
            4 => Ok(Self::Event),
            5 => Ok(Self::Close),
            other => Err(TransportError::UnknownFrameKind(other)),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct SessionNonce([u8; NONCE_BYTES]);

impl SessionNonce {
    pub fn new(bytes: [u8; NONCE_BYTES]) -> Result<Self, TransportError> {
        if bytes.iter().all(|byte| *byte == 0) {
            return Err(TransportError::InvalidSessionNonce);
        }
        Ok(Self(bytes))
    }

    pub const fn as_bytes(&self) -> &[u8; NONCE_BYTES] {
        &self.0
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Frame {
    pub kind: FrameKind,
    pub sequence: u64,
    pub session_nonce: SessionNonce,
    pub payload: Vec<u8>,
}

impl Frame {
    pub fn new(
        kind: FrameKind,
        sequence: u64,
        session_nonce: SessionNonce,
        payload: Vec<u8>,
    ) -> Result<Self, TransportError> {
        if payload.len() > MAX_PAYLOAD_BYTES {
            return Err(TransportError::FrameTooLarge {
                length: payload.len(),
                maximum: MAX_PAYLOAD_BYTES,
            });
        }
        Ok(Self {
            kind,
            sequence,
            session_nonce,
            payload,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PeerIdentity {
    pub pid: Option<u32>,
    pub uid: u32,
    pub gid: u32,
}

impl PeerIdentity {
    pub fn from_stream(stream: &UnixStream) -> Result<Self, TransportError> {
        read_peer_identity(stream)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PeerPolicy {
    pub expected_pid: Option<u32>,
    pub expected_uid: u32,
    pub expected_gid: Option<u32>,
}

impl PeerPolicy {
    pub const fn new(expected_uid: u32) -> Self {
        Self {
            expected_pid: None,
            expected_uid,
            expected_gid: None,
        }
    }

    pub const fn exact(identity: PeerIdentity) -> Self {
        Self {
            expected_pid: identity.pid,
            expected_uid: identity.uid,
            expected_gid: Some(identity.gid),
        }
    }

    pub fn authorize(&self, actual: PeerIdentity) -> Result<(), TransportError> {
        let pid_matches = self
            .expected_pid
            .is_none_or(|expected| actual.pid == Some(expected));
        let gid_matches = self
            .expected_gid
            .is_none_or(|expected| actual.gid == expected);
        if actual.uid == self.expected_uid && pid_matches && gid_matches {
            return Ok(());
        }
        Err(TransportError::UnauthorizedPeer {
            expected: *self,
            actual,
        })
    }
}

pub trait NonceSource {
    fn next_nonce(&mut self) -> Result<[u8; NONCE_BYTES], TransportError>;
}

#[derive(Debug, Default)]
pub struct OsNonceSource;

impl NonceSource for OsNonceSource {
    fn next_nonce(&mut self) -> Result<[u8; NONCE_BYTES], TransportError> {
        let mut nonce = [0_u8; NONCE_BYTES];
        let mut random = File::open("/dev/urandom").map_err(TransportError::Io)?;
        random.read_exact(&mut nonce).map_err(TransportError::Io)?;
        Ok(nonce)
    }
}

#[derive(Debug, Clone, Copy)]
pub struct FixedNonceSource(pub [u8; NONCE_BYTES]);

impl NonceSource for FixedNonceSource {
    fn next_nonce(&mut self) -> Result<[u8; NONCE_BYTES], TransportError> {
        Ok(self.0)
    }
}

#[derive(Debug)]
pub struct ReceivedRequest {
    pub sequence: u64,
    pub payload: Vec<u8>,
}

#[derive(Debug)]
pub struct ServerConnection {
    framed: FramedUnixStream,
    binding: SessionNonce,
    peer: PeerIdentity,
    expected_request_sequence: u64,
}

impl ServerConnection {
    pub fn accept(
        stream: UnixStream,
        policy: PeerPolicy,
        timeout: Duration,
    ) -> Result<Self, TransportError> {
        Self::accept_with_nonce_source(stream, policy, OsNonceSource, timeout)
    }

    pub fn accept_with_nonce_source<S: NonceSource>(
        stream: UnixStream,
        policy: PeerPolicy,
        mut nonce_source: S,
        timeout: Duration,
    ) -> Result<Self, TransportError> {
        reject_zero_timeout(timeout)?;
        let peer = PeerIdentity::from_stream(&stream)?;
        policy.authorize(peer)?;
        let binding = SessionNonce::new(nonce_source.next_nonce()?)?;
        let mut framed = FramedUnixStream::new(stream);
        framed.write_frame(
            &Frame::new(
                FrameKind::Challenge,
                0,
                binding,
                CHALLENGE_PAYLOAD.to_vec(),
            )?,
            timeout,
        )?;
        Ok(Self {
            framed,
            binding,
            peer,
            expected_request_sequence: 1,
        })
    }

    pub const fn peer_identity(&self) -> PeerIdentity {
        self.peer
    }

    pub const fn session_nonce(&self) -> SessionNonce {
        self.binding
    }

    pub fn receive_request(&mut self, timeout: Duration) -> Result<ReceivedRequest, TransportError> {
        let frame = self.framed.read_frame(timeout)?;
        require_kind(frame.kind, FrameKind::Request)?;
        require_nonce(frame.session_nonce, self.binding)?;
        if frame.sequence != self.expected_request_sequence {
            return Err(TransportError::SequenceMismatch {
                expected: self.expected_request_sequence,
                actual: frame.sequence,
            });
        }
        self.expected_request_sequence = self
            .expected_request_sequence
            .checked_add(1)
            .ok_or(TransportError::SequenceExhausted)?;
        Ok(ReceivedRequest {
            sequence: frame.sequence,
            payload: frame.payload,
        })
    }

    pub fn send_response(
        &mut self,
        request_sequence: u64,
        payload: Vec<u8>,
        timeout: Duration,
    ) -> Result<(), TransportError> {
        self.framed.write_frame(
            &Frame::new(
                FrameKind::Response,
                request_sequence,
                self.binding,
                payload,
            )?,
            timeout,
        )
    }
}

#[derive(Debug)]
pub struct ClientConnection {
    framed: FramedUnixStream,
    binding: SessionNonce,
    peer: PeerIdentity,
    next_request_sequence: u64,
}

impl ClientConnection {
    pub fn connect(
        stream: UnixStream,
        server_policy: PeerPolicy,
        timeout: Duration,
    ) -> Result<Self, TransportError> {
        reject_zero_timeout(timeout)?;
        let peer = PeerIdentity::from_stream(&stream)?;
        server_policy.authorize(peer)?;
        let mut framed = FramedUnixStream::new(stream);
        let challenge = framed.read_frame(timeout)?;
        require_kind(challenge.kind, FrameKind::Challenge)?;
        if challenge.sequence != 0 || challenge.payload != CHALLENGE_PAYLOAD {
            return Err(TransportError::InvalidChallenge);
        }
        Ok(Self {
            framed,
            binding: challenge.session_nonce,
            peer,
            next_request_sequence: 1,
        })
    }

    pub const fn peer_identity(&self) -> PeerIdentity {
        self.peer
    }

    pub const fn session_nonce(&self) -> SessionNonce {
        self.binding
    }

    pub fn send_request(
        &mut self,
        payload: Vec<u8>,
        timeout: Duration,
    ) -> Result<u64, TransportError> {
        let sequence = self.next_request_sequence;
        self.framed.write_frame(
            &Frame::new(FrameKind::Request, sequence, self.binding, payload)?,
            timeout,
        )?;
        self.next_request_sequence = self
            .next_request_sequence
            .checked_add(1)
            .ok_or(TransportError::SequenceExhausted)?;
        Ok(sequence)
    }

    pub fn receive_response(
        &mut self,
        request_sequence: u64,
        timeout: Duration,
    ) -> Result<Vec<u8>, TransportError> {
        let frame = self.framed.read_frame(timeout)?;
        require_kind(frame.kind, FrameKind::Response)?;
        require_nonce(frame.session_nonce, self.binding)?;
        if frame.sequence != request_sequence {
            return Err(TransportError::SequenceMismatch {
                expected: request_sequence,
                actual: frame.sequence,
            });
        }
        Ok(frame.payload)
    }
}

#[derive(Debug)]
struct FramedUnixStream {
    stream: UnixStream,
}

impl FramedUnixStream {
    const fn new(stream: UnixStream) -> Self {
        Self { stream }
    }

    fn write_frame(&mut self, frame: &Frame, timeout: Duration) -> Result<(), TransportError> {
        reject_zero_timeout(timeout)?;
        if frame.payload.len() > MAX_PAYLOAD_BYTES {
            return Err(TransportError::FrameTooLarge {
                length: frame.payload.len(),
                maximum: MAX_PAYLOAD_BYTES,
            });
        }
        let payload_length = u32::try_from(frame.payload.len()).map_err(|_| {
            TransportError::FrameTooLarge {
                length: frame.payload.len(),
                maximum: MAX_PAYLOAD_BYTES,
            }
        })?;
        let mut header = [0_u8; HEADER_BYTES];
        header[0..8].copy_from_slice(&PROTOCOL_MAGIC);
        header[8..10].copy_from_slice(&PROTOCOL_VERSION.to_be_bytes());
        header[10] = frame.kind as u8;
        header[11] = 0;
        header[12..20].copy_from_slice(&frame.sequence.to_be_bytes());
        header[20..24].copy_from_slice(&payload_length.to_be_bytes());
        header[24..56].copy_from_slice(frame.session_nonce.as_bytes());
        header[56..88].copy_from_slice(&payload_digest(&frame.payload));

        let deadline = AbsoluteDeadline::new(timeout)?;
        write_all_until(&mut self.stream, &header, deadline)?;
        write_all_until(&mut self.stream, &frame.payload, deadline)?;
        self.stream
            .set_write_timeout(Some(deadline.remaining()?))
            .map_err(TransportError::Io)?;
        self.stream.flush().map_err(map_io_error)
    }

    fn read_frame(&mut self, timeout: Duration) -> Result<Frame, TransportError> {
        reject_zero_timeout(timeout)?;
        let deadline = AbsoluteDeadline::new(timeout)?;
        let mut header = [0_u8; HEADER_BYTES];
        read_exact_until(&mut self.stream, &mut header, deadline)?;
        if header[0..8] != PROTOCOL_MAGIC {
            return Err(TransportError::InvalidMagic);
        }
        let version = u16::from_be_bytes([header[8], header[9]]);
        if version != PROTOCOL_VERSION {
            return Err(TransportError::UnsupportedVersion(version));
        }
        let kind = FrameKind::try_from(header[10])?;
        if header[11] != 0 {
            return Err(TransportError::ReservedFlags(header[11]));
        }
        let sequence = u64::from_be_bytes(header[12..20].try_into().expect("fixed header slice"));
        let payload_length =
            u32::from_be_bytes(header[20..24].try_into().expect("fixed header slice")) as usize;
        if payload_length > MAX_PAYLOAD_BYTES {
            return Err(TransportError::FrameTooLarge {
                length: payload_length,
                maximum: MAX_PAYLOAD_BYTES,
            });
        }
        let session_nonce = SessionNonce::new(
            header[24..56]
                .try_into()
                .expect("fixed session nonce header slice"),
        )?;
        let expected_digest: [u8; DIGEST_BYTES] = header[56..88]
            .try_into()
            .expect("fixed digest header slice");
        let mut payload = vec![0_u8; payload_length];
        read_exact_until(&mut self.stream, &mut payload, deadline)?;
        if payload_digest(&payload) != expected_digest {
            return Err(TransportError::PayloadDigestMismatch);
        }
        Frame::new(kind, sequence, session_nonce, payload)
    }
}

#[derive(Debug, Clone, Copy)]
struct AbsoluteDeadline(Instant);

impl AbsoluteDeadline {
    fn new(timeout: Duration) -> Result<Self, TransportError> {
        let deadline = Instant::now()
            .checked_add(timeout)
            .ok_or(TransportError::DeadlineExceeded)?;
        Ok(Self(deadline))
    }

    fn remaining(self) -> Result<Duration, TransportError> {
        self.0
            .checked_duration_since(Instant::now())
            .filter(|remaining| !remaining.is_zero())
            .ok_or(TransportError::DeadlineExceeded)
    }
}

fn read_exact_until(
    stream: &mut UnixStream,
    buffer: &mut [u8],
    deadline: AbsoluteDeadline,
) -> Result<(), TransportError> {
    let mut offset = 0;
    while offset < buffer.len() {
        stream
            .set_read_timeout(Some(deadline.remaining()?))
            .map_err(TransportError::Io)?;
        match stream.read(&mut buffer[offset..]) {
            Ok(0) => return Err(TransportError::UnexpectedEof),
            Ok(read) => offset += read,
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(map_io_error(error)),
        }
    }
    Ok(())
}

fn write_all_until(
    stream: &mut UnixStream,
    buffer: &[u8],
    deadline: AbsoluteDeadline,
) -> Result<(), TransportError> {
    let mut offset = 0;
    while offset < buffer.len() {
        stream
            .set_write_timeout(Some(deadline.remaining()?))
            .map_err(TransportError::Io)?;
        match stream.write(&buffer[offset..]) {
            Ok(0) => return Err(TransportError::UnexpectedEof),
            Ok(written) => offset += written,
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(map_io_error(error)),
        }
    }
    Ok(())
}

fn map_io_error(error: io::Error) -> TransportError {
    if matches!(
        error.kind(),
        io::ErrorKind::TimedOut | io::ErrorKind::WouldBlock
    ) {
        TransportError::DeadlineExceeded
    } else {
        TransportError::Io(error)
    }
}

fn payload_digest(payload: &[u8]) -> [u8; DIGEST_BYTES] {
    Sha256::digest(payload).into()
}

fn require_kind(actual: FrameKind, expected: FrameKind) -> Result<(), TransportError> {
    if actual == expected {
        Ok(())
    } else {
        Err(TransportError::UnexpectedFrameKind { expected, actual })
    }
}

fn require_nonce(actual: SessionNonce, expected: SessionNonce) -> Result<(), TransportError> {
    if actual == expected {
        Ok(())
    } else {
        Err(TransportError::SessionNonceMismatch)
    }
}

fn reject_zero_timeout(timeout: Duration) -> Result<(), TransportError> {
    if timeout.is_zero() {
        Err(TransportError::DeadlineExceeded)
    } else {
        Ok(())
    }
}

#[cfg(any(target_os = "linux", target_os = "android"))]
fn read_peer_identity(stream: &UnixStream) -> Result<PeerIdentity, TransportError> {
    use std::mem::{size_of, zeroed};
    use std::os::fd::AsRawFd;

    // SAFETY: `credentials` is valid writable storage for a `libc::ucred`,
    // `length` names its exact size, and the file descriptor remains owned by
    // `stream` for the duration of this call. `getsockopt(SO_PEERCRED)` does not
    // retain either pointer after returning.
    let mut credentials: libc::ucred = unsafe { zeroed() };
    let mut length = size_of::<libc::ucred>() as libc::socklen_t;
    let status = unsafe {
        libc::getsockopt(
            stream.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            std::ptr::addr_of_mut!(credentials).cast(),
            std::ptr::addr_of_mut!(length),
        )
    };
    if status != 0 {
        return Err(TransportError::Io(std::io::Error::last_os_error()));
    }
    if usize::try_from(length).ok() != Some(size_of::<libc::ucred>()) {
        return Err(TransportError::InvalidPeerCredentials);
    }
    Ok(PeerIdentity {
        pid: u32::try_from(credentials.pid).ok(),
        uid: credentials.uid,
        gid: credentials.gid,
    })
}

#[cfg(not(any(target_os = "linux", target_os = "android")))]
fn read_peer_identity(_stream: &UnixStream) -> Result<PeerIdentity, TransportError> {
    Err(TransportError::UnsupportedPlatform)
}

#[derive(Debug)]
pub enum TransportError {
    Io(io::Error),
    UnsupportedPlatform,
    InvalidPeerCredentials,
    UnauthorizedPeer {
        expected: PeerPolicy,
        actual: PeerIdentity,
    },
    InvalidMagic,
    UnsupportedVersion(u16),
    UnknownFrameKind(u8),
    ReservedFlags(u8),
    InvalidSessionNonce,
    FrameTooLarge {
        length: usize,
        maximum: usize,
    },
    PayloadDigestMismatch,
    DeadlineExceeded,
    UnexpectedEof,
    InvalidChallenge,
    UnexpectedFrameKind {
        expected: FrameKind,
        actual: FrameKind,
    },
    SessionNonceMismatch,
    SequenceMismatch {
        expected: u64,
        actual: u64,
    },
    SequenceExhausted,
    SelfCheckThreadPanicked,
}

impl fmt::Display for TransportError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "Agent transport I/O failed: {error}"),
            Self::UnsupportedPlatform => formatter.write_str(
                "Agent transport peer credentials are unsupported on this platform",
            ),
            Self::InvalidPeerCredentials => {
                formatter.write_str("Agent transport returned malformed peer credentials")
            }
            Self::UnauthorizedPeer { expected, actual } => write!(
                formatter,
                "Agent transport rejected peer {actual:?}; expected {expected:?}",
            ),
            Self::InvalidMagic => formatter.write_str("Agent transport frame magic is invalid"),
            Self::UnsupportedVersion(version) => {
                write!(formatter, "Agent transport version {version} is unsupported")
            }
            Self::UnknownFrameKind(kind) => {
                write!(formatter, "Agent transport frame kind {kind} is unknown")
            }
            Self::ReservedFlags(flags) => {
                write!(formatter, "Agent transport reserved flags are non-zero: {flags}")
            }
            Self::InvalidSessionNonce => {
                formatter.write_str("Agent transport session nonce is all zero")
            }
            Self::FrameTooLarge { length, maximum } => write!(
                formatter,
                "Agent transport payload length {length} exceeds maximum {maximum}",
            ),
            Self::PayloadDigestMismatch => {
                formatter.write_str("Agent transport payload digest does not match")
            }
            Self::DeadlineExceeded => {
                formatter.write_str("Agent transport absolute operation deadline expired")
            }
            Self::UnexpectedEof => {
                formatter.write_str("Agent transport stream closed before the frame completed")
            }
            Self::InvalidChallenge => {
                formatter.write_str("Agent transport challenge is invalid")
            }
            Self::UnexpectedFrameKind { expected, actual } => write!(
                formatter,
                "Agent transport expected {expected:?} frame, received {actual:?}",
            ),
            Self::SessionNonceMismatch => {
                formatter.write_str("Agent transport session nonce does not match")
            }
            Self::SequenceMismatch { expected, actual } => write!(
                formatter,
                "Agent transport expected request sequence {expected}, received {actual}",
            ),
            Self::SequenceExhausted => {
                formatter.write_str("Agent transport sequence space is exhausted")
            }
            Self::SelfCheckThreadPanicked => {
                formatter.write_str("Agent transport self-check thread panicked")
            }
        }
    }
}

impl std::error::Error for TransportError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            _ => None,
        }
    }
}

impl From<io::Error> for TransportError {
    fn from(error: io::Error) -> Self {
        map_io_error(error)
    }
}

pub fn self_check() -> Result<(), TransportError> {
    let timeout = Duration::from_secs(2);
    let (client_stream, server_stream) = UnixStream::pair().map_err(TransportError::Io)?;
    let client_policy = PeerPolicy::exact(PeerIdentity::from_stream(&client_stream)?);
    let server_policy = PeerPolicy::exact(PeerIdentity::from_stream(&server_stream)?);
    let server = std::thread::spawn(move || -> Result<(), TransportError> {
        let mut connection = ServerConnection::accept_with_nonce_source(
            server_stream,
            server_policy,
            FixedNonceSource([0x5a; NONCE_BYTES]),
            timeout,
        )?;
        let request = connection.receive_request(timeout)?;
        if request.payload != b"desktop-transport-self-check" {
            return Err(TransportError::InvalidChallenge);
        }
        connection.send_response(request.sequence, b"ok".to_vec(), timeout)
    });

    let mut client = ClientConnection::connect(client_stream, client_policy, timeout)?;
    let sequence = client.send_request(b"desktop-transport-self-check".to_vec(), timeout)?;
    let response = client.receive_response(sequence, timeout)?;
    if response != b"ok" {
        return Err(TransportError::InvalidChallenge);
    }
    server
        .join()
        .map_err(|_| TransportError::SelfCheckThreadPanicked)??;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread;

    fn policies(
        client: &UnixStream,
        server: &UnixStream,
    ) -> Result<(PeerPolicy, PeerPolicy), TransportError> {
        Ok((
            PeerPolicy::exact(PeerIdentity::from_stream(client)?),
            PeerPolicy::exact(PeerIdentity::from_stream(server)?),
        ))
    }

    #[test]
    fn authenticated_round_trip_binds_peer_nonce_sequence_and_digest() {
        let timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().unwrap();
        let (client_policy, server_policy) = policies(&client_stream, &server_stream).unwrap();
        let server = thread::spawn(move || {
            let mut connection = ServerConnection::accept_with_nonce_source(
                server_stream,
                server_policy,
                FixedNonceSource([7; NONCE_BYTES]),
                timeout,
            )
            .unwrap();
            let request = connection.receive_request(timeout).unwrap();
            assert_eq!(request.sequence, 1);
            assert_eq!(request.payload, b"observe");
            connection
                .send_response(request.sequence, b"accepted".to_vec(), timeout)
                .unwrap();
        });
        let mut client = ClientConnection::connect(client_stream, client_policy, timeout).unwrap();
        assert_eq!(
            client.session_nonce(),
            SessionNonce::new([7; NONCE_BYTES]).unwrap()
        );
        let sequence = client.send_request(b"observe".to_vec(), timeout).unwrap();
        assert_eq!(
            client.receive_response(sequence, timeout).unwrap(),
            b"accepted"
        );
        server.join().unwrap();
    }

    #[test]
    fn unauthorized_peer_is_rejected_before_challenge() {
        let (client, server) = UnixStream::pair().unwrap();
        let identity = PeerIdentity::from_stream(&server).unwrap();
        let wrong_uid = identity.uid.checked_add(1).unwrap_or(identity.uid - 1);
        let error = ServerConnection::accept_with_nonce_source(
            server,
            PeerPolicy::new(wrong_uid),
            FixedNonceSource([1; NONCE_BYTES]),
            Duration::from_millis(100),
        )
        .unwrap_err();
        assert!(matches!(error, TransportError::UnauthorizedPeer { .. }));
        drop(client);
    }

    #[test]
    fn oversized_length_is_rejected_before_payload_allocation() {
        let (mut writer, reader) = UnixStream::pair().unwrap();
        let nonce = SessionNonce::new([2; NONCE_BYTES]).unwrap();
        let mut header = [0_u8; HEADER_BYTES];
        header[0..8].copy_from_slice(&PROTOCOL_MAGIC);
        header[8..10].copy_from_slice(&PROTOCOL_VERSION.to_be_bytes());
        header[10] = FrameKind::Request as u8;
        header[12..20].copy_from_slice(&1_u64.to_be_bytes());
        header[20..24].copy_from_slice(&((MAX_PAYLOAD_BYTES as u32) + 1).to_be_bytes());
        header[24..56].copy_from_slice(nonce.as_bytes());
        writer.write_all(&header).unwrap();
        let mut framed = FramedUnixStream::new(reader);
        let error = framed.read_frame(Duration::from_secs(1)).unwrap_err();
        assert!(matches!(error, TransportError::FrameTooLarge { .. }));
    }

    #[test]
    fn digest_tampering_fails_closed() {
        let (mut writer, reader) = UnixStream::pair().unwrap();
        let nonce = SessionNonce::new([3; NONCE_BYTES]).unwrap();
        let payload = b"original";
        let mut header = [0_u8; HEADER_BYTES];
        header[0..8].copy_from_slice(&PROTOCOL_MAGIC);
        header[8..10].copy_from_slice(&PROTOCOL_VERSION.to_be_bytes());
        header[10] = FrameKind::Request as u8;
        header[12..20].copy_from_slice(&1_u64.to_be_bytes());
        header[20..24].copy_from_slice(&(payload.len() as u32).to_be_bytes());
        header[24..56].copy_from_slice(nonce.as_bytes());
        header[56..88].copy_from_slice(&payload_digest(payload));
        writer.write_all(&header).unwrap();
        writer.write_all(b"tampered").unwrap();
        let mut framed = FramedUnixStream::new(reader);
        let error = framed.read_frame(Duration::from_secs(1)).unwrap_err();
        assert!(matches!(error, TransportError::PayloadDigestMismatch));
    }

    #[test]
    fn replayed_sequence_is_rejected() {
        let timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().unwrap();
        let (client_policy, server_policy) = policies(&client_stream, &server_stream).unwrap();
        let server = thread::spawn(move || {
            let mut connection = ServerConnection::accept_with_nonce_source(
                server_stream,
                server_policy,
                FixedNonceSource([4; NONCE_BYTES]),
                timeout,
            )
            .unwrap();
            assert_eq!(connection.receive_request(timeout).unwrap().sequence, 1);
            let error = connection.receive_request(timeout).unwrap_err();
            assert!(matches!(
                error,
                TransportError::SequenceMismatch {
                    expected: 2,
                    actual: 1
                }
            ));
        });
        let mut client = ClientConnection::connect(client_stream, client_policy, timeout).unwrap();
        let nonce = client.session_nonce();
        client
            .framed
            .write_frame(
                &Frame::new(FrameKind::Request, 1, nonce, b"first".to_vec()).unwrap(),
                timeout,
            )
            .unwrap();
        client
            .framed
            .write_frame(
                &Frame::new(FrameKind::Request, 1, nonce, b"replay".to_vec()).unwrap(),
                timeout,
            )
            .unwrap();
        server.join().unwrap();
    }

    #[test]
    fn absolute_deadline_applies_to_the_whole_frame() {
        let (_writer, reader) = UnixStream::pair().unwrap();
        let mut framed = FramedUnixStream::new(reader);
        let started = Instant::now();
        let error = framed.read_frame(Duration::from_millis(25)).unwrap_err();
        assert!(matches!(error, TransportError::DeadlineExceeded));
        assert!(started.elapsed() < Duration::from_secs(1));
    }

    #[test]
    fn all_zero_nonce_is_forbidden() {
        assert!(matches!(
            SessionNonce::new([0; NONCE_BYTES]),
            Err(TransportError::InvalidSessionNonce)
        ));
    }

    #[test]
    fn full_self_check_passes() {
        self_check().unwrap();
    }
}
