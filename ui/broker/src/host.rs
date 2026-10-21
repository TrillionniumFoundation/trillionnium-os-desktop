//! One-shot Linux host transport for the existing default-deny broker.
//!
//! A peer writes one bounded JSON line, then shuts down its write half. The
//! server reads through EOF before admitting a session, so a second frame or
//! trailing bytes cannot be mistaken for a separate authenticated request.
//! The kernel-reported same UID is the only host identity established here.
//! It supplies no application identity, owner receipt, or effect authority.

use crate::{
    peer_credentials_from_unix, Broker, ClientHello, Request, Response, SameUidAuthenticator,
    SessionInfo,
};
use serde::{Deserialize, Serialize};
use socket2::{Domain, SockAddr, Socket, Type};
use std::io::{self, Read, Write};
use std::net::Shutdown;
use std::os::fd::OwnedFd;
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};
use trill_ui_core::host_peer::{current_effective_uid, require_same_uid_peer};
use trill_ui_core::{socket_path, write_frame, MAX_FRAME};

/// Complete server read/parse/handle/write budget, never reset by progress.
pub const EXCHANGE_TIMEOUT: Duration = Duration::from_millis(500);
const CLIENT_TIMEOUT: Duration = Duration::from_secs(2);

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExchangeRequest {
    pub hello: ClientHello,
    pub request: Request,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExchangeReply {
    /// Diagnostic local counter only; never accepted back as a credential.
    pub session: SessionInfo,
    pub response: Response,
}

pub fn broker_socket_path() -> io::Result<PathBuf> {
    Ok(socket_path()?.with_file_name("organ.sock"))
}

/// Consume one real connected peer using the process's single Broker owner.
/// No caller-supplied PID, UID, role, or session ID participates in admission.
/// Every admitted handle is closed before any response write can fail.
pub fn serve_exchange(stream: UnixStream, broker: &mut Broker) -> io::Result<()> {
    let deadline = Instant::now() + EXCHANGE_TIMEOUT;
    let peer = peer_credentials_from_unix(&stream)
        .map_err(|error| io::Error::new(io::ErrorKind::PermissionDenied, error))?;
    let auth = SameUidAuthenticator {
        expected_uid: current_effective_uid(),
    };
    // Reject before reading a single claimed identity byte from a foreign UID.
    if peer.uid != auth.expected_uid {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "cross-UID broker IPC refused",
        ));
    }
    let mut connection = DeadlineStream::new(stream, deadline);
    let frame = read_complete_frame(&mut connection)?;
    let exchange: ExchangeRequest = serde_json::from_slice(&frame)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    connection.remaining()?;
    let (session, info) = broker
        .open_session(&auth, exchange.hello, peer)
        .map_err(|error| io::Error::new(io::ErrorKind::PermissionDenied, error))?;
    let response = broker.handle(&session, exchange.request);
    broker.close_session(&session);
    write_frame(
        &mut connection,
        &ExchangeReply {
            session: info,
            response,
        },
    )
}

/// Single exchange with an explicit endpoint. Failure is not a non-submission
/// receipt and is never retried here. A reply supplies only the broker's
/// existing default-deny/local-only/unknown semantics.
pub fn exchange_at(socket: &Path, request: &ExchangeRequest) -> io::Result<ExchangeReply> {
    let deadline = Instant::now() + CLIENT_TIMEOUT;
    let stream = connect_until(socket, deadline)?;
    require_same_uid_peer(&stream)?;
    let mut connection = DeadlineStream::new(stream, deadline);
    write_frame(&mut connection, request)?;
    connection.stream.shutdown(Shutdown::Write)?;
    let frame = read_complete_frame(&mut connection)?;
    serde_json::from_slice(&frame)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))
}

/// Bounded connection setup for both the Organ client and Session's existing
/// stale-socket probe. This is transport only: callers must authenticate an
/// actual protocol peer separately. Any error except ConnectionRefused must
/// never be interpreted as permission to unlink an existing socket.
pub fn connect_until(socket: &Path, deadline: Instant) -> io::Result<UnixStream> {
    // A full Unix-listener backlog can also block connect. Use the existing
    // pinned workspace dependency's nonblocking connect/poll implementation,
    // and keep connection setup inside the same client exchange budget.
    let connection_socket = Socket::new(Domain::UNIX, Type::STREAM, None)?;
    let address = SockAddr::unix(socket)?;
    connection_socket.connect_timeout(&address, remaining_until(deadline)?)?;
    let stream = UnixStream::from(OwnedFd::from(connection_socket));
    // AF_UNIX EAGAIN is not an EINPROGRESS connection. A readiness report
    // with SO_ERROR=0 must not turn an unconnected descriptor into success.
    stream.peer_addr()?;
    Ok(stream)
}

fn read_complete_frame(input: &mut DeadlineStream) -> io::Result<Vec<u8>> {
    // The extra byte detects overflow; allocation never follows a peer length.
    let mut bytes = vec![0; MAX_FRAME + 1];
    let mut count = 0;
    loop {
        if count == bytes.len() {
            return Err(invalid_frame());
        }
        match input.read(&mut bytes[count..]) {
            Ok(0) => break,
            Ok(read) => count += read,
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error),
        }
    }
    bytes.truncate(count);
    if bytes.is_empty()
        || bytes.len() > MAX_FRAME
        || bytes.last() != Some(&b'\n')
        || bytes[..bytes.len() - 1].contains(&b'\n')
    {
        return Err(invalid_frame());
    }
    Ok(bytes)
}

fn invalid_frame() -> io::Error {
    io::Error::new(
        io::ErrorKind::InvalidData,
        "broker IPC requires exactly one bounded JSON line followed by EOF",
    )
}

/// A fixed I/O deadline shared by Session's two local endpoints. Progress,
/// short reads/writes and interrupted syscalls never extend this deadline.
pub struct DeadlineStream {
    stream: UnixStream,
    deadline: Instant,
}

impl DeadlineStream {
    pub fn new(stream: UnixStream, deadline: Instant) -> Self {
        Self { stream, deadline }
    }

    fn remaining(&self) -> io::Result<Duration> {
        remaining_until(self.deadline)
    }
}

fn remaining_until(deadline: Instant) -> io::Result<Duration> {
    deadline
        .checked_duration_since(Instant::now())
        .filter(|remaining| !remaining.is_zero())
        .ok_or_else(|| io::Error::new(io::ErrorKind::TimedOut, "broker IPC deadline expired"))
}

impl Read for DeadlineStream {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        self.stream.set_read_timeout(Some(self.remaining()?))?;
        self.stream.read(buffer)
    }
}

impl Write for DeadlineStream {
    fn write(&mut self, buffer: &[u8]) -> io::Result<usize> {
        self.stream.set_write_timeout(Some(self.remaining()?))?;
        self.stream.write(buffer)
    }

    fn flush(&mut self) -> io::Result<()> {
        self.remaining()?;
        self.stream.flush()
    }
}
