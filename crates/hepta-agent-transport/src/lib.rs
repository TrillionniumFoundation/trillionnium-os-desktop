//! Fail-stop authenticated, bounded AF_UNIX carrier for the desktop Agent port.
//!
//! The private `wire` module owns framing and kernel peer authentication. This
//! public facade makes connection reuse impossible after any wire, deadline,
//! digest, nonce, kind, or sequence failure. Local preflight rejection occurs
//! before any byte is emitted and therefore does not poison the connection.

#![cfg_attr(
    not(any(target_os = "linux", target_os = "android")),
    allow(dead_code)
)]
#![deny(unsafe_op_in_unsafe_fn)]

mod wire;

use std::fmt;
use std::io;
use std::os::unix::net::UnixStream;
use std::time::Duration;

pub use wire::{
    DIGEST_BYTES, FixedNonceSource, Frame, FrameKind, NONCE_BYTES, NonceSource, OsNonceSource,
    PeerIdentity, PeerPolicy, ReceivedRequest, SessionNonce, TransportError,
};

pub const PROTOCOL_MAGIC: [u8; 8] = *b"HEPTA001";
pub const PROTOCOL_VERSION: u16 = 1;
pub const HEADER_BYTES: usize = 88;
pub const MAX_PAYLOAD_BYTES: usize = 262_144;
pub const DEFAULT_OPERATION_TIMEOUT: Duration = Duration::from_secs(20);

// Kernel credential extraction remains isolated in `wire.rs` at the reviewed
// SAFETY: `libc::getsockopt(..., SO_PEERCRED, ...)` boundary. Keeping the raw
// carrier private prevents callers from bypassing the fail-stop facade.

const POISONED_CONNECTION_MESSAGE: &str =
    "Agent transport connection is poisoned after a wire or protocol failure";

/// Server-side authenticated connection with fail-stop reuse semantics.
#[derive(Debug)]
pub struct ServerConnection {
    inner: Option<wire::ServerConnection>,
    peer: PeerIdentity,
    binding: SessionNonce,
}

impl ServerConnection {
    pub fn accept(
        stream: UnixStream,
        policy: PeerPolicy,
        timeout: Duration,
    ) -> Result<Self, TransportError> {
        reject_local_timeout(timeout)?;
        let inner = wire::ServerConnection::accept(stream, policy, timeout)?;
        Ok(Self::from_inner(inner))
    }

    pub fn accept_with_nonce_source<S: NonceSource>(
        stream: UnixStream,
        policy: PeerPolicy,
        nonce_source: S,
        timeout: Duration,
    ) -> Result<Self, TransportError> {
        reject_local_timeout(timeout)?;
        let inner = wire::ServerConnection::accept_with_nonce_source(
            stream,
            policy,
            nonce_source,
            timeout,
        )?;
        Ok(Self::from_inner(inner))
    }

    fn from_inner(inner: wire::ServerConnection) -> Self {
        let peer = inner.peer_identity();
        let binding = inner.session_nonce();
        Self {
            inner: Some(inner),
            peer,
            binding,
        }
    }

    pub const fn peer_identity(&self) -> PeerIdentity {
        self.peer
    }

    pub const fn session_nonce(&self) -> SessionNonce {
        self.binding
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
            Ok(request) => Ok(request),
            Err(error) => self.fail_stop(error),
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
            Err(error) => self.fail_stop(error),
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

/// Client-side authenticated connection with fail-stop reuse semantics.
#[derive(Debug)]
pub struct ClientConnection {
    inner: Option<wire::ClientConnection>,
    peer: PeerIdentity,
    binding: SessionNonce,
}

impl ClientConnection {
    pub fn connect(
        stream: UnixStream,
        server_policy: PeerPolicy,
        timeout: Duration,
    ) -> Result<Self, TransportError> {
        reject_local_timeout(timeout)?;
        let inner = wire::ClientConnection::connect(stream, server_policy, timeout)?;
        let peer = inner.peer_identity();
        let binding = inner.session_nonce();
        Ok(Self {
            inner: Some(inner),
            peer,
            binding,
        })
    }

    pub const fn peer_identity(&self) -> PeerIdentity {
        self.peer
    }

    pub const fn session_nonce(&self) -> SessionNonce {
        self.binding
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
            // Sequence exhaustion is computed before a byte is written. The
            // connection remains synchronized, although no further sequence
            // can be allocated.
            Err(error @ TransportError::SequenceExhausted) => Err(error),
            Err(error) => self.fail_stop(error),
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
            Err(error) => self.fail_stop(error),
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

impl fmt::Display for ServerConnection {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "ServerConnection(peer={:?}, poisoned={})",
            self.peer,
            self.is_poisoned()
        )
    }
}

impl fmt::Display for ClientConnection {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "ClientConnection(peer={:?}, poisoned={})",
            self.peer,
            self.is_poisoned()
        )
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
            let mut connection = ServerConnection::accept_with_nonce_source(
                server_stream,
                server_policy,
                FixedNonceSource([0x61; NONCE_BYTES]),
                timeout,
            )
            .unwrap();
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
            let mut connection = ServerConnection::accept_with_nonce_source(
                server_stream,
                server_policy,
                FixedNonceSource([0x62; NONCE_BYTES]),
                timeout,
            )
            .unwrap();
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
            let mut connection = ServerConnection::accept_with_nonce_source(
                server_stream,
                server_policy,
                FixedNonceSource([0x63; NONCE_BYTES]),
                timeout,
            )
            .unwrap();
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
            let mut connection = ServerConnection::accept_with_nonce_source(
                server_stream,
                server_policy,
                FixedNonceSource([0x64; NONCE_BYTES]),
                timeout,
            )
            .unwrap();
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
    fn full_facade_self_check_passes() {
        self_check().unwrap();
    }
}
