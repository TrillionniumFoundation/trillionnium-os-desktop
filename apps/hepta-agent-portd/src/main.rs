//! Product one-connection systemd socket-activation service for AgentPort.
//!
//! The binary never binds or listens. It verifies an already-accepted AF_UNIX
//! stream and the dedicated peer mechanism identity. Until D3 connects a real
//! BrowserActor handler, product activation fails closed without decoding or
//! dispatching a request. The D0 fixture handler lives in a separate,
//! feature-gated binary and is not part of the production installation graph.

#![deny(unsafe_op_in_unsafe_fn)]

use hepta_agent_transport::PeerIdentity;
use hepta_peer_attestation::{
    AttestationError, PeerRuntimePolicy, ProcfsPeerAttestor, resolve_group_id, resolve_user_id,
};
use std::fmt;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::net::UnixStream;
use std::path::Path;

const AGENT_SOCKET_PATH: &str = "/run/hepta/browserd/agent.sock";
const EXPECTED_PEER_USER: &str = "hepta-agent";
const EXPECTED_PEER_GROUP: &str = "hepta-agent";
const EXPECTED_PEER_UNIT: &str = "hepta-agent.service";

fn main() {
    let outcome = if std::env::args().any(|argument| argument == "--self-check") {
        self_check()
    } else {
        refuse_unconnected_product_handler().map(|()| String::new())
    };
    match outcome {
        Ok(report) => {
            if !report.is_empty() {
                println!("{report}");
            }
        }
        Err(error) => {
            eprintln!("hepta-agent-portd: {error}");
            std::process::exit(1);
        }
    }
}

fn refuse_unconnected_product_handler() -> Result<(), ServiceError> {
    let stream = inherited_stream_from_stdin()?;
    verify_local_socket_path(&stream, Path::new(AGENT_SOCKET_PATH))?;

    let expected_uid = resolve_user_id(EXPECTED_PEER_USER)?;
    let expected_gid = resolve_group_id(EXPECTED_PEER_GROUP)?;
    let peer = PeerIdentity::from_stream(&stream)?;
    let runtime_policy =
        PeerRuntimePolicy::for_system_service(expected_uid, expected_gid, EXPECTED_PEER_UNIT)?;
    let attested = ProcfsPeerAttestor::default().attest(peer, &runtime_policy)?;

    // Keep the pidfd-backed identity alive until the connection is refused.
    // The product binary intentionally does not decode a request or instantiate
    // the D0 fixture. A real BrowserActor binding is a separate D3 promotion.
    let _held_identity = attested.snapshot();
    Err(ServiceError::ProductHandlerUnavailable)
}

fn inherited_stream_from_stdin() -> Result<UnixStream, ServiceError> {
    verify_stream_socket(0)?;
    // SAFETY: F_DUPFD_CLOEXEC creates a new descriptor referring to fd 0. The
    // returned descriptor is owned by this function and transferred exactly
    // once to UnixStream. Standard input remains owned by the process runtime.
    let duplicated = unsafe { libc::fcntl(0, libc::F_DUPFD_CLOEXEC, 3) };
    if duplicated < 0 {
        return Err(ServiceError::Io(io::Error::last_os_error()));
    }
    // SAFETY: `duplicated` is a fresh descriptor returned by fcntl and is now
    // transferred exactly once to UnixStream ownership.
    Ok(unsafe { UnixStream::from_raw_fd(duplicated) })
}

fn verify_stream_socket(fd: libc::c_int) -> Result<(), ServiceError> {
    let mut socket_type: libc::c_int = 0;
    let mut length = std::mem::size_of::<libc::c_int>() as libc::socklen_t;
    // SAFETY: the output pointers refer to initialized writable storage for
    // the call and getsockopt retains neither pointer.
    let status = unsafe {
        libc::getsockopt(
            fd,
            libc::SOL_SOCKET,
            libc::SO_TYPE,
            std::ptr::addr_of_mut!(socket_type).cast(),
            std::ptr::addr_of_mut!(length),
        )
    };
    if status != 0 {
        return Err(ServiceError::Io(io::Error::last_os_error()));
    }
    if usize::try_from(length).ok() != Some(std::mem::size_of::<libc::c_int>())
        || socket_type != libc::SOCK_STREAM
    {
        return Err(ServiceError::WrongInheritedDescriptor);
    }
    Ok(())
}

fn verify_local_socket_path(stream: &UnixStream, expected: &Path) -> Result<(), ServiceError> {
    let address = stream.local_addr().map_err(ServiceError::Io)?;
    let actual = address
        .as_pathname()
        .ok_or(ServiceError::UnnamedInheritedSocket)?;
    if actual != expected {
        return Err(ServiceError::SocketPathMismatch {
            expected: expected.to_path_buf(),
            actual: actual.to_path_buf(),
        });
    }
    Ok(())
}

fn self_check() -> Result<String, ServiceError> {
    let (left, _right) = UnixStream::pair().map_err(ServiceError::Io)?;
    verify_stream_socket(left.as_raw_fd())?;
    let peer = PeerIdentity::from_stream(&left)?;
    let attestor = ProcfsPeerAttestor::default();
    let snapshot = attestor.read_snapshot(peer.pid.ok_or(ServiceError::Invariant(
        "self-check peer credentials have no PID",
    ))?)?;
    let attested = attestor.attest(peer, &PeerRuntimePolicy::exact(&snapshot))?;
    attested.ensure_alive()?;
    if resolve_user_id("root")? != 0 || resolve_group_id("root")? != 0 {
        return Err(ServiceError::Invariant("root account resolution changed"));
    }
    Ok(format!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.agent-portd-self-check.v2\",",
            "\"ok\":true,\"listener_created\":false,",
            "\"expected_product_socket\":\"{}\",",
            "\"product_handler_connected\":false,",
            "\"fixture_handler_linked\":false,",
            "\"activation_fail_closed\":true,",
            "\"peer_pid\":{},\"peer_uid\":{},\"peer_gid\":{}}}"
        ),
        AGENT_SOCKET_PATH, snapshot.pid, snapshot.uid, snapshot.gid,
    ))
}

#[derive(Debug)]
enum ServiceError {
    Io(io::Error),
    Transport(hepta_agent_transport::TransportError),
    Attestation(AttestationError),
    WrongInheritedDescriptor,
    UnnamedInheritedSocket,
    SocketPathMismatch {
        expected: std::path::PathBuf,
        actual: std::path::PathBuf,
    },
    ProductHandlerUnavailable,
    Invariant(&'static str),
}

impl fmt::Display for ServiceError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "inherited socket I/O failed: {error}"),
            Self::Transport(error) => write!(formatter, "transport failed: {error}"),
            Self::Attestation(error) => write!(formatter, "peer attestation failed: {error}"),
            Self::WrongInheritedDescriptor => {
                formatter.write_str("standard input is not an AF_UNIX stream socket")
            }
            Self::UnnamedInheritedSocket => {
                formatter.write_str("inherited stream has no filesystem pathname")
            }
            Self::SocketPathMismatch { expected, actual } => write!(
                formatter,
                "inherited socket path {} does not equal {}",
                actual.display(),
                expected.display()
            ),
            Self::ProductHandlerUnavailable => formatter.write_str(
                "product BrowserActor handler is not connected; fixture substitution is forbidden",
            ),
            Self::Invariant(reason) => write!(formatter, "service invariant failed: {reason}"),
        }
    }
}

impl std::error::Error for ServiceError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            Self::Transport(error) => Some(error),
            Self::Attestation(error) => Some(error),
            _ => None,
        }
    }
}

impl From<io::Error> for ServiceError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}

impl From<hepta_agent_transport::TransportError> for ServiceError {
    fn from(error: hepta_agent_transport::TransportError) -> Self {
        Self::Transport(error)
    }
}

impl From<AttestationError> for ServiceError {
    fn from(error: AttestationError) -> Self {
        Self::Attestation(error)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn socketpair_is_a_stream_but_not_a_product_path() {
        let (left, _right) = UnixStream::pair().expect("socketpair");
        verify_stream_socket(left.as_raw_fd()).expect("stream type");
        assert!(matches!(
            verify_local_socket_path(&left, Path::new(AGENT_SOCKET_PATH)),
            Err(ServiceError::UnnamedInheritedSocket)
        ));
    }

    #[test]
    fn product_self_check_reports_fixture_separation_and_closed_activation() {
        let report = self_check().expect("self-check");
        assert!(report.contains("\"ok\":true"));
        assert!(report.contains("\"listener_created\":false"));
        assert!(report.contains("\"product_handler_connected\":false"));
        assert!(report.contains("\"fixture_handler_linked\":false"));
        assert!(report.contains("\"activation_fail_closed\":true"));
    }

    #[test]
    fn missing_browser_actor_has_a_stable_fail_closed_error() {
        assert_eq!(
            ServiceError::ProductHandlerUnavailable.to_string(),
            "product BrowserActor handler is not connected; fixture substitution is forbidden"
        );
    }
}
