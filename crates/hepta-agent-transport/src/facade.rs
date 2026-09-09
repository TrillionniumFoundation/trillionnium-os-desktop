//! Fail-stop authenticated, bounded AF_UNIX carrier for the desktop Agent port.
//!
//! The private `wire` module owns framing, nonce material, raw frame values,
//! and kernel peer authentication. This facade exposes only the product
//! connected-stream operations and redacted identity values. Test nonce
//! injection and raw frame constructors never cross the crate boundary.

#![cfg_attr(not(any(target_os = "linux", target_os = "android")), allow(dead_code))]
#![deny(unsafe_op_in_unsafe_fn)]

mod wire;

use std::fmt;
use std::io;
use std::os::unix::net::UnixStream;
use std::time::Duration;

pub const MAX_PAYLOAD_BYTES: usize = 262_144;

const POISONED_CONNECTION_MESSAGE: &str =
    "Agent transport connection is poisoned after a wire or protocol failure";
const REDACTED_IDENTITY: &str = "<redacted-local-peer>";

#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub struct PeerIdentity {
    pub pid: Option<u32>,
    pub uid: u32,
    pub gid: u32,
}

impl PeerIdentity {
    pub fn from_stream(stream: &UnixStream) -> Result<Self, TransportError> {
        wire::PeerIdentity::from_stream(stream)
            .map(Self::from_wire)
            .map_err(TransportError::from)
    }

    const fn from_wire(value: wire::PeerIdentity) -> Self {
        Self {
            pid: value.pid,
            uid: value.uid,
            gid: value.gid,
        }
    }
}

impl fmt::Debug for PeerIdentity {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("PeerIdentity(<redacted>)")
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
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
            Ok(())
        } else {
            Err(TransportError::UnauthorizedPeer)
        }
    }

    const fn into_wire(self) -> wire::PeerPolicy {
        wire::PeerPolicy {
            expected_pid: self.expected_pid,
            expected_uid: self.expected_uid,
            expected_gid: self.expected_gid,
        }
    }
}

impl fmt::Debug for PeerPolicy {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("PeerPolicy(<redacted>)")
    }
}

#[derive(Debug)]
pub struct ReceivedRequest {
    pub sequence: u64,
    pub payload: Vec<u8>,
}

pub enum TransportError {
    Io(io::Error),
    UnsupportedPlatform,
    InvalidPeerCredentials,
    UnauthorizedPeer,
    InvalidMagic,
    UnsupportedVersion(u16),
    UnknownFrameKind(u8),
    ReservedFlags(u8),
    InvalidSessionNonce,
    FrameTooLarge { length: usize, maximum: usize },
    PayloadDigestMismatch,
    DeadlineExceeded,
    UnexpectedEof,
    InvalidChallenge,
    UnexpectedFrameKind,
    SessionNonceMismatch,
    SequenceMismatch { expected: u64, actual: u64 },
    SequenceExhausted,
    SelfCheckThreadPanicked,
}

impl From<wire::TransportError> for TransportError {
    fn from(value: wire::TransportError) -> Self {
        match value {
            wire::TransportError::Io(error) => Self::Io(error),
            wire::TransportError::UnsupportedPlatform => Self::UnsupportedPlatform,
            wire::TransportError::InvalidPeerCredentials => Self::InvalidPeerCredentials,
            wire::TransportError::UnauthorizedPeer { .. } => Self::UnauthorizedPeer,
            wire::TransportError::InvalidMagic => Self::InvalidMagic,
            wire::TransportError::UnsupportedVersion(version) => Self::UnsupportedVersion(version),
            wire::TransportError::UnknownFrameKind(kind) => Self::UnknownFrameKind(kind),
            wire::TransportError::ReservedFlags(flags) => Self::ReservedFlags(flags),
            wire::TransportError::InvalidSessionNonce => Self::InvalidSessionNonce,
            wire::TransportError::FrameTooLarge { length, maximum } => {
                Self::FrameTooLarge { length, maximum }
            }
            wire::TransportError::PayloadDigestMismatch => Self::PayloadDigestMismatch,
            wire::TransportError::DeadlineExceeded => Self::DeadlineExceeded,
            wire::TransportError::UnexpectedEof => Self::UnexpectedEof,
            wire::TransportError::InvalidChallenge => Self::InvalidChallenge,
            wire::TransportError::UnexpectedFrameKind { .. } => Self::UnexpectedFrameKind,
            wire::TransportError::SessionNonceMismatch => Self::SessionNonceMismatch,
            wire::TransportError::SequenceMismatch { expected, actual } => {
                Self::SequenceMismatch { expected, actual }
            }
            wire::TransportError::SequenceExhausted => Self::SequenceExhausted,
            wire::TransportError::SelfCheckThreadPanicked => Self::SelfCheckThreadPanicked,
        }
    }
}

impl From<io::Error> for TransportError {
    fn from(error: io::Error) -> Self {
        if matches!(
            error.kind(),
            io::ErrorKind::TimedOut | io::ErrorKind::WouldBlock
        ) {
            Self::DeadlineExceeded
        } else {
            Self::Io(error)
        }
    }
}

impl fmt::Display for TransportError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "Agent transport I/O failed ({:?})", error.kind()),
            Self::UnsupportedPlatform => formatter
                .write_str("Agent transport peer credentials are unsupported on this platform"),
            Self::InvalidPeerCredentials => {
                formatter.write_str("Agent transport returned malformed peer credentials")
            }
            Self::UnauthorizedPeer => {
                formatter.write_str("Agent transport rejected an unauthorized local peer")
            }
            Self::InvalidMagic => formatter.write_str("Agent transport frame magic is invalid"),
            Self::UnsupportedVersion(version) => {
                write!(
                    formatter,
                    "Agent transport version {version} is unsupported"
                )
            }
            Self::UnknownFrameKind(kind) => {
                write!(formatter, "Agent transport frame kind {kind} is unknown")
            }
            Self::ReservedFlags(flags) => write!(
                formatter,
                "Agent transport reserved flags are non-zero: {flags}"
            ),
            Self::InvalidSessionNonce => {
                formatter.write_str("Agent transport session nonce is invalid")
            }
            Self::FrameTooLarge { length, maximum } => write!(
                formatter,
                "Agent transport payload length {length} exceeds maximum {maximum}"
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
            Self::InvalidChallenge => formatter.write_str("Agent transport challenge is invalid"),
            Self::UnexpectedFrameKind => {
                formatter.write_str("Agent transport received an unexpected frame kind")
            }
            Self::SessionNonceMismatch => {
                formatter.write_str("Agent transport session binding does not match")
            }
            Self::SequenceMismatch { expected, actual } => write!(
                formatter,
                "Agent transport expected sequence {expected}, received {actual}"
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

impl fmt::Debug for TransportError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        fmt::Display::fmt(self, formatter)
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

pub struct ServerConnection {
    inner: Option<wire::ServerConnection>,
    peer: PeerIdentity,
}

impl ServerConnection {
    pub fn accept(
        stream: UnixStream,
        policy: PeerPolicy,
        timeout: Duration,
    ) -> Result<Self, TransportError> {
        reject_local_timeout(timeout)?;
        let inner = wire::ServerConnection::accept(stream, policy.into_wire(), timeout)
            .map_err(TransportError::from)?;
        let peer = PeerIdentity::from_wire(inner.peer_identity());
        Ok(Self {
            inner: Some(inner),
            peer,
        })
    }

    pub const fn peer_identity(&self) -> PeerIdentity {
        self.peer
    }

    pub const fn is_poisoned(&self) -> bool {
        self.inner.is_none()
    }

    pub fn receive_request(
        &mut self,
        timeout: Duration,
    ) -> Result<ReceivedRequest, TransportError> {
        self.ensure_live()?;
        reject_local_timeout(timeout)?;
        let result = self.inner_mut()?.receive_request(timeout);
        match result {
            Ok(request) => Ok(ReceivedRequest {
                sequence: request.sequence,
                payload: request.payload,
            }),
            Err(error) => self.fail_stop(TransportError::from(error)),
        }
    }

    pub fn send_response(
        &mut self,
        request_sequence: u64,
        payload: Vec<u8>,
        timeout: Duration,
    ) -> Result<(), TransportError> {
        self.ensure_live()?;
        preflight_payload(&payload)?;
        reject_local_timeout(timeout)?;
        let result = self
            .inner_mut()?
            .send_response(request_sequence, payload, timeout);
        match result {
            Ok(()) => Ok(()),
            Err(error) => self.fail_stop(TransportError::from(error)),
        }
    }

    fn ensure_live(&self) -> Result<(), TransportError> {
        if self.inner.is_some() {
            Ok(())
        } else {
            Err(connection_poisoned_error())
        }
    }

    fn inner_mut(&mut self) -> Result<&mut wire::ServerConnection, TransportError> {
        self.inner.as_mut().ok_or_else(connection_poisoned_error)
    }

    fn fail_stop<T>(&mut self, error: TransportError) -> Result<T, TransportError> {
        self.inner.take();
        Err(error)
    }
}

impl fmt::Display for ServerConnection {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "ServerConnection(peer={}, poisoned={})",
            REDACTED_IDENTITY,
            self.is_poisoned()
        )
    }
}

impl fmt::Debug for ServerConnection {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        fmt::Display::fmt(self, formatter)
    }
}

pub struct ClientConnection {
    inner: Option<wire::ClientConnection>,
    peer: PeerIdentity,
}

impl ClientConnection {
    pub fn connect(
        stream: UnixStream,
        server_policy: PeerPolicy,
        timeout: Duration,
    ) -> Result<Self, TransportError> {
        reject_local_timeout(timeout)?;
        let inner = wire::ClientConnection::connect(stream, server_policy.into_wire(), timeout)
            .map_err(TransportError::from)?;
        let peer = PeerIdentity::from_wire(inner.peer_identity());
        Ok(Self {
            inner: Some(inner),
            peer,
        })
    }

    pub const fn peer_identity(&self) -> PeerIdentity {
        self.peer
    }

    pub const fn is_poisoned(&self) -> bool {
        self.inner.is_none()
    }

    pub fn send_request(
        &mut self,
        payload: Vec<u8>,
        timeout: Duration,
    ) -> Result<u64, TransportError> {
        self.ensure_live()?;
        preflight_payload(&payload)?;
        reject_local_timeout(timeout)?;
        let result = self.inner_mut()?.send_request(payload, timeout);
        match result {
            Ok(sequence) => Ok(sequence),
            Err(error @ wire::TransportError::SequenceExhausted) => {
                Err(TransportError::from(error))
            }
            Err(error) => self.fail_stop(TransportError::from(error)),
        }
    }

    pub fn receive_response(
        &mut self,
        request_sequence: u64,
        timeout: Duration,
    ) -> Result<Vec<u8>, TransportError> {
        self.ensure_live()?;
        reject_local_timeout(timeout)?;
        let result = self
            .inner_mut()?
            .receive_response(request_sequence, timeout);
        match result {
            Ok(payload) => Ok(payload),
            Err(error) => self.fail_stop(TransportError::from(error)),
        }
    }

    fn ensure_live(&self) -> Result<(), TransportError> {
        if self.inner.is_some() {
            Ok(())
        } else {
            Err(connection_poisoned_error())
        }
    }

    fn inner_mut(&mut self) -> Result<&mut wire::ClientConnection, TransportError> {
        self.inner.as_mut().ok_or_else(connection_poisoned_error)
    }

    fn fail_stop<T>(&mut self, error: TransportError) -> Result<T, TransportError> {
        self.inner.take();
        Err(error)
    }
}

impl fmt::Display for ClientConnection {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "ClientConnection(peer={}, poisoned={})",
            REDACTED_IDENTITY,
            self.is_poisoned()
        )
    }
}

impl fmt::Debug for ClientConnection {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        fmt::Display::fmt(self, formatter)
    }
}

fn preflight_payload(payload: &[u8]) -> Result<(), TransportError> {
    if payload.len() > MAX_PAYLOAD_BYTES {
        Err(TransportError::FrameTooLarge {
            length: payload.len(),
            maximum: MAX_PAYLOAD_BYTES,
        })
    } else {
        Ok(())
    }
}

fn reject_local_timeout(timeout: Duration) -> Result<(), TransportError> {
    if timeout.is_zero() {
        Err(TransportError::DeadlineExceeded)
    } else {
        Ok(())
    }
}

fn connection_poisoned_error() -> TransportError {
    TransportError::Io(io::Error::new(
        io::ErrorKind::BrokenPipe,
        POISONED_CONNECTION_MESSAGE,
    ))
}

#[cfg(test)]
fn is_connection_poisoned(error: &TransportError) -> bool {
    matches!(
        error,
        TransportError::Io(source)
            if source.kind() == io::ErrorKind::BrokenPipe
                && source.to_string() == POISONED_CONNECTION_MESSAGE
    )
}

pub fn self_check() -> Result<(), TransportError> {
    let timeout = Duration::from_secs(2);
    let (client_stream, server_stream) = UnixStream::pair().map_err(TransportError::from)?;
    let client_policy = PeerPolicy::exact(PeerIdentity::from_stream(&client_stream)?);
    let server_policy = PeerPolicy::exact(PeerIdentity::from_stream(&server_stream)?);
    let server = std::thread::spawn(move || -> Result<(), TransportError> {
        let mut connection = ServerConnection::accept(server_stream, server_policy, timeout)?;
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
mod facade_tests {
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
    fn response_sequence_mismatch_permanently_poisoned_client() {
        let timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().unwrap();
        let (client_policy, server_policy) = policies(&client_stream, &server_stream).unwrap();
        let server = thread::spawn(move || {
            let mut connection =
                ServerConnection::accept(server_stream, server_policy, timeout).unwrap();
            let request = connection.receive_request(timeout).unwrap();
            connection
                .send_response(request.sequence + 1, b"wrong-sequence".to_vec(), timeout)
                .unwrap();
        });

        let mut client = ClientConnection::connect(client_stream, client_policy, timeout).unwrap();
        let sequence = client.send_request(b"request".to_vec(), timeout).unwrap();
        assert!(matches!(
            client.receive_response(sequence, timeout),
            Err(TransportError::SequenceMismatch { .. })
        ));
        assert!(client.is_poisoned());
        let error = client
            .send_request(b"must-not-be-written".to_vec(), timeout)
            .unwrap_err();
        assert!(is_connection_poisoned(&error));
        server.join().unwrap();
    }

    #[test]
    fn local_payload_preflight_does_not_poison_or_write() {
        let timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().unwrap();
        let (client_policy, server_policy) = policies(&client_stream, &server_stream).unwrap();
        let server = thread::spawn(move || {
            let mut connection =
                ServerConnection::accept(server_stream, server_policy, timeout).unwrap();
            let request = connection.receive_request(timeout).unwrap();
            assert_eq!(request.payload, b"valid-after-preflight");
            connection
                .send_response(request.sequence, b"ok".to_vec(), timeout)
                .unwrap();
        });

        let mut client = ClientConnection::connect(client_stream, client_policy, timeout).unwrap();
        assert!(matches!(
            client.send_request(vec![0; MAX_PAYLOAD_BYTES + 1], timeout),
            Err(TransportError::FrameTooLarge { .. })
        ));
        assert!(!client.is_poisoned());
        let sequence = client
            .send_request(b"valid-after-preflight".to_vec(), timeout)
            .unwrap();
        assert_eq!(client.receive_response(sequence, timeout).unwrap(), b"ok");
        server.join().unwrap();
    }

    #[test]
    fn response_deadline_failure_permanently_poisoned_client() {
        let timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().unwrap();
        let (client_policy, server_policy) = policies(&client_stream, &server_stream).unwrap();
        let server = thread::spawn(move || {
            let mut connection =
                ServerConnection::accept(server_stream, server_policy, timeout).unwrap();
            let _request = connection.receive_request(timeout).unwrap();
            thread::sleep(Duration::from_millis(75));
        });

        let mut client = ClientConnection::connect(client_stream, client_policy, timeout).unwrap();
        let sequence = client.send_request(b"request".to_vec(), timeout).unwrap();
        assert!(matches!(
            client.receive_response(sequence, Duration::from_millis(20)),
            Err(TransportError::DeadlineExceeded)
        ));
        assert!(client.is_poisoned());
        let error = client
            .receive_response(sequence, Duration::from_secs(1))
            .unwrap_err();
        assert!(is_connection_poisoned(&error));
        server.join().unwrap();
    }

    #[test]
    fn zero_timeout_is_local_preflight_and_does_not_poison() {
        let timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().unwrap();
        let (client_policy, server_policy) = policies(&client_stream, &server_stream).unwrap();
        let server = thread::spawn(move || {
            let mut connection =
                ServerConnection::accept(server_stream, server_policy, timeout).unwrap();
            let request = connection.receive_request(timeout).unwrap();
            connection
                .send_response(request.sequence, b"ok".to_vec(), timeout)
                .unwrap();
        });

        let mut client = ClientConnection::connect(client_stream, client_policy, timeout).unwrap();
        assert!(matches!(
            client.send_request(b"not-written".to_vec(), Duration::ZERO),
            Err(TransportError::DeadlineExceeded)
        ));
        assert!(!client.is_poisoned());
        let sequence = client.send_request(b"written".to_vec(), timeout).unwrap();
        assert_eq!(client.receive_response(sequence, timeout).unwrap(), b"ok");
        server.join().unwrap();
    }

    #[test]
    fn public_identity_policy_connection_and_error_formatting_are_redacted() {
        let identity = PeerIdentity {
            pid: Some(123_456_789),
            uid: 223_456_789,
            gid: 323_456_789,
        };
        let policy = PeerPolicy::exact(identity);
        let unauthorized = TransportError::UnauthorizedPeer;
        for rendered in [
            format!("{identity:?}"),
            format!("{policy:?}"),
            format!("{unauthorized}"),
            format!("{unauthorized:?}"),
        ] {
            assert!(!rendered.contains("123456789"));
            assert!(!rendered.contains("223456789"));
            assert!(!rendered.contains("323456789"));
            assert!(!rendered.contains("expected_uid"));
            assert!(!rendered.contains("expected_pid"));
            assert!(!rendered.contains("expected_gid"));
        }
    }

    #[test]
    fn unauthorized_peer_error_does_not_reveal_runtime_identity() {
        let (left, right) = UnixStream::pair().unwrap();
        let actual = PeerIdentity::from_stream(&right).unwrap();
        let wrong_uid = if actual.uid == u32::MAX {
            actual.uid - 1
        } else {
            actual.uid + 1
        };
        let error = ServerConnection::accept(
            right,
            PeerPolicy::new(wrong_uid),
            Duration::from_millis(100),
        )
        .unwrap_err();
        drop(left);
        let display = error.to_string();
        let debug = format!("{error:?}");
        for value in [
            actual.pid.unwrap_or_default(),
            actual.uid,
            actual.gid,
            wrong_uid,
        ] {
            let token = value.to_string();
            assert!(!display.contains(&token));
            assert!(!debug.contains(&token));
        }
    }

    #[test]
    fn full_facade_self_check_passes() {
        self_check().unwrap();
    }
}
