//! D1-only AgentPort qualification binary.
//!
//! This binary is compiled only with the explicit non-default
//! `d1-qualification` feature and is installed only into the D1 qualification
//! image. Its `server` mode owns no listener: systemd supplies one already-
//! accepted AF_UNIX stream on standard input. Client modes exercise the same
//! bounded transport and canonical Browser API while the product
//! `hepta-agent-portd` binary remains fixture-free and fails closed.

#![deny(unsafe_op_in_unsafe_fn)]

use hepta_agent_port::{D0FixtureHandler, ServiceEvidence, serve_one};
use hepta_agent_transport::{ClientConnection, PeerIdentity, PeerPolicy};
use hepta_browser_codec::{BrowserOperation, BrowserRequest, decode_response, encode_request};
use hepta_peer_attestation::{
    AttestationError, PeerRuntimePolicy, ProcfsPeerAttestor, resolve_group_id, resolve_user_id,
};
use std::env;
use std::fmt;
use std::fs;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::time::Duration;

const AGENT_SOCKET_PATH: &str = "/run/hepta/browserd/agent.sock";
const EXPECTED_PEER_USER: &str = "hepta-agent";
const EXPECTED_PEER_GROUP: &str = "hepta-agent";
const EXPECTED_PEER_UNIT: &str = "hepta-agent.service";
const CLIENT_TIMEOUT: Duration = Duration::from_secs(10);
const SERVER_CEILING: Duration = Duration::from_secs(20);

fn main() {
    match run() {
        Ok(result) => {
            if let Some(path) = result.output
                && let Err(error) = write_result(&path, &result.json)
            {
                eprintln!("hepta-agent-d1-fixture: failed to write result: {error}");
                std::process::exit(1);
            }
            println!("{}", result.json);
        }
        Err(error) => {
            eprintln!("hepta-agent-d1-fixture: {error}");
            std::process::exit(1);
        }
    }
}

fn run() -> Result<FixtureResult, FixtureError> {
    let mut mode = None;
    let mut output = None;
    let mut arguments = env::args().skip(1);
    while let Some(argument) = arguments.next() {
        match argument.as_str() {
            "--mode" => {
                mode = Some(
                    arguments
                        .next()
                        .ok_or(FixtureError::Usage("--mode requires a value"))?,
                );
            }
            "--output" => {
                output = Some(PathBuf::from(
                    arguments
                        .next()
                        .ok_or(FixtureError::Usage("--output requires a path"))?,
                ));
            }
            "--help" | "-h" => {
                println!(
                    "Usage: hepta-agent-d1-fixture --mode server|health|expect-denied|hold|self-check [--output PATH]"
                );
                std::process::exit(0);
            }
            _ => return Err(FixtureError::Usage("unknown argument")),
        }
    }

    let mode = mode.ok_or(FixtureError::Usage("--mode is required"))?;
    let json = match mode.as_str() {
        "server" => run_server()?,
        "health" => run_health()?,
        "expect-denied" => run_expect_denied()?,
        "hold" => run_hold()?,
        "self-check" => run_self_check()?,
        _ => return Err(FixtureError::Usage("unsupported mode")),
    };
    Ok(FixtureResult { json, output })
}

fn run_server() -> Result<String, FixtureError> {
    let stream = inherited_stream_from_stdin()?;
    verify_local_socket_path(&stream, Path::new(AGENT_SOCKET_PATH))?;

    let expected_uid = resolve_user_id(EXPECTED_PEER_USER)?;
    let expected_gid = resolve_group_id(EXPECTED_PEER_GROUP)?;
    let peer = PeerIdentity::from_stream(&stream)?;
    let runtime_policy =
        PeerRuntimePolicy::for_system_service(expected_uid, expected_gid, EXPECTED_PEER_UNIT)?;
    let attested = ProcfsPeerAttestor::default().attest(peer, &runtime_policy)?;

    let transport_policy = PeerPolicy {
        expected_pid: peer.pid,
        expected_uid,
        expected_gid: Some(expected_gid),
    };
    let mut handler = D0FixtureHandler::default();
    let evidence = serve_one(stream, transport_policy, SERVER_CEILING, &mut handler)?;
    attested.ensure_alive()?;
    if handler.invocation_count != 1 {
        return Err(FixtureError::Invariant(
            "qualification server did not dispatch exactly once",
        ));
    }
    Ok(server_evidence_json(&evidence))
}

fn inherited_stream_from_stdin() -> Result<UnixStream, FixtureError> {
    verify_stream_socket(0)?;
    // SAFETY: F_DUPFD_CLOEXEC creates a new descriptor referring to fd 0. The
    // returned descriptor is owned by this function and transferred exactly
    // once to UnixStream. Standard input remains owned by the process runtime.
    let duplicated = unsafe { libc::fcntl(0, libc::F_DUPFD_CLOEXEC, 3) };
    if duplicated < 0 {
        return Err(FixtureError::Io(io::Error::last_os_error()));
    }
    // SAFETY: `duplicated` is a fresh descriptor returned by fcntl and is now
    // transferred exactly once to UnixStream ownership.
    Ok(unsafe { UnixStream::from_raw_fd(duplicated) })
}

fn verify_stream_socket(fd: libc::c_int) -> Result<(), FixtureError> {
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
        return Err(FixtureError::Io(io::Error::last_os_error()));
    }
    if usize::try_from(length).ok() != Some(std::mem::size_of::<libc::c_int>())
        || socket_type != libc::SOCK_STREAM
    {
        return Err(FixtureError::WrongInheritedDescriptor);
    }
    Ok(())
}

fn verify_local_socket_path(stream: &UnixStream, expected: &Path) -> Result<(), FixtureError> {
    let address = stream.local_addr().map_err(FixtureError::Io)?;
    let actual = address
        .as_pathname()
        .ok_or(FixtureError::UnnamedInheritedSocket)?;
    if actual != expected {
        return Err(FixtureError::SocketPathMismatch {
            expected: expected.to_path_buf(),
            actual: actual.to_path_buf(),
        });
    }
    Ok(())
}

fn run_health() -> Result<String, FixtureError> {
    let stream = UnixStream::connect(AGENT_SOCKET_PATH).map_err(FixtureError::Io)?;
    let server = PeerIdentity::from_stream(&stream)?;
    let mut connection = ClientConnection::connect(stream, PeerPolicy::exact(server), CLIENT_TIMEOUT)?;

    let request = BrowserRequest {
        request_id: "d1-agent-port-health:1".to_owned(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    };
    let encoded = encode_request(&request)?;
    let sequence = connection.send_request(encoded, CLIENT_TIMEOUT)?;
    let response = connection.receive_response(sequence, CLIENT_TIMEOUT)?;
    let decoded = decode_response(&response)?;
    if decoded.value.request_id != request.request_id
        || decoded.value.session_id.is_some()
        || decoded.value.session_generation.is_some()
        || decoded.value.outcome.is_err()
    {
        return Err(FixtureError::Invariant(
            "health response was not successful and request-bound",
        ));
    }

    Ok(format!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.d1-agent-fixture.v2\",",
            "\"status\":\"PASS\",\"mode\":\"health\",",
            "\"qualification_only\":true,\"product_handler_connected\":false,",
            "\"request_id\":\"{}\",\"transport_sequence\":{},",
            "\"response_sha256\":\"{}\"}}"
        ),
        request.request_id, sequence, decoded.canonical_sha256
    ))
}

fn run_expect_denied() -> Result<String, FixtureError> {
    match UnixStream::connect(AGENT_SOCKET_PATH) {
        Err(error)
            if matches!(
                error.kind(),
                io::ErrorKind::PermissionDenied | io::ErrorKind::NotFound
            ) =>
        {
            Ok(concat!(
                "{\"schema\":\"trillionnium.desktop.d1-agent-fixture.v2\",",
                "\"status\":\"PASS\",\"mode\":\"expect-denied\",",
                "\"qualification_only\":true,\"connection_admitted\":false}"
            )
            .to_owned())
        }
        Err(error) => Err(FixtureError::Io(error)),
        Ok(_) => Err(FixtureError::Invariant(
            "unauthorized peer unexpectedly connected to AgentPort",
        )),
    }
}

fn run_hold() -> Result<String, FixtureError> {
    let _stream = UnixStream::connect(AGENT_SOCKET_PATH).map_err(FixtureError::Io)?;
    std::thread::sleep(Duration::from_secs(120));
    Ok(concat!(
        "{\"schema\":\"trillionnium.desktop.d1-agent-fixture.v2\",",
        "\"status\":\"PASS\",\"mode\":\"hold\",",
        "\"qualification_only\":true}"
    )
    .to_owned())
}

fn run_self_check() -> Result<String, FixtureError> {
    hepta_agent_port::self_check()?;
    let (left, _right) = UnixStream::pair().map_err(FixtureError::Io)?;
    verify_stream_socket(left.as_raw_fd())?;
    let peer = PeerIdentity::from_stream(&left)?;
    let attestor = ProcfsPeerAttestor::default();
    let snapshot = attestor.read_snapshot(peer.pid.ok_or(FixtureError::Invariant(
        "self-check peer credentials have no PID",
    ))?)?;
    let attested = attestor.attest(peer, &PeerRuntimePolicy::exact(&snapshot))?;
    attested.ensure_alive()?;
    if resolve_user_id("root")? != 0 || resolve_group_id("root")? != 0 {
        return Err(FixtureError::Invariant("root account resolution changed"));
    }
    Ok(format!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.d1-agent-fixture-self-check.v1\",",
            "\"status\":\"PASS\",\"qualification_only\":true,",
            "\"listener_created\":false,\"product_handler_connected\":false,",
            "\"peer_pid\":{},\"peer_uid\":{},\"peer_gid\":{}}}"
        ),
        snapshot.pid, snapshot.uid, snapshot.gid
    ))
}

fn server_evidence_json(evidence: &ServiceEvidence) -> String {
    format!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.d1-agent-server-result.v1\",",
            "\"status\":\"PASS\",\"qualification_only\":true,",
            "\"product_handler_connected\":false,\"listener_created\":false,",
            "\"peer_pid\":{},\"peer_uid\":{},\"peer_gid\":{},",
            "\"transport_sequence\":{},\"request_id\":\"{}\",",
            "\"request_sha256\":\"{}\",\"response_sha256\":\"{}\",",
            "\"response_ok\":{},\"response_committed\":{}}}"
        ),
        evidence.peer.pid.unwrap_or_default(),
        evidence.peer.uid,
        evidence.peer.gid,
        evidence.transport_sequence,
        escape_json(&evidence.request_id),
        evidence.request_sha256,
        evidence.response_sha256,
        evidence.response_ok,
        evidence.response_committed,
    )
}

fn escape_json(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    for character in value.chars() {
        match character {
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            character if character.is_control() => {
                use std::fmt::Write;
                let _ = write!(output, "\\u{:04x}", character as u32);
            }
            character => output.push(character),
        }
    }
    output
}

fn write_result(path: &Path, json: &str) -> Result<(), io::Error> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, format!("{json}\n"))
}

struct FixtureResult {
    json: String,
    output: Option<PathBuf>,
}

#[derive(Debug)]
enum FixtureError {
    Io(io::Error),
    Transport(hepta_agent_transport::TransportError),
    Codec(hepta_browser_codec::CodecError),
    AgentPort(hepta_agent_port::AgentPortError),
    Attestation(AttestationError),
    WrongInheritedDescriptor,
    UnnamedInheritedSocket,
    SocketPathMismatch {
        expected: PathBuf,
        actual: PathBuf,
    },
    Invariant(&'static str),
    Usage(&'static str),
}

impl fmt::Display for FixtureError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "I/O failed: {error}"),
            Self::Transport(error) => write!(formatter, "transport failed: {error}"),
            Self::Codec(error) => write!(formatter, "codec failed: {error}"),
            Self::AgentPort(error) => write!(formatter, "AgentPort failed: {error}"),
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
            Self::Invariant(message) => write!(formatter, "invariant failed: {message}"),
            Self::Usage(message) => write!(formatter, "usage error: {message}"),
        }
    }
}

impl std::error::Error for FixtureError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            Self::Transport(error) => Some(error),
            Self::Codec(error) => Some(error),
            Self::AgentPort(error) => Some(error),
            Self::Attestation(error) => Some(error),
            _ => None,
        }
    }
}

impl From<io::Error> for FixtureError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}

impl From<hepta_agent_transport::TransportError> for FixtureError {
    fn from(error: hepta_agent_transport::TransportError) -> Self {
        Self::Transport(error)
    }
}

impl From<hepta_browser_codec::CodecError> for FixtureError {
    fn from(error: hepta_browser_codec::CodecError) -> Self {
        Self::Codec(error)
    }
}

impl From<hepta_agent_port::AgentPortError> for FixtureError {
    fn from(error: hepta_agent_port::AgentPortError) -> Self {
        Self::AgentPort(error)
    }
}

impl From<AttestationError> for FixtureError {
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
            Err(FixtureError::UnnamedInheritedSocket)
        ));
    }

    #[test]
    fn server_evidence_marks_the_qualification_boundary() {
        let evidence = ServiceEvidence {
            peer: PeerIdentity {
                pid: Some(42),
                uid: 1000,
                gid: 1001,
            },
            transport_sequence: 1,
            request_id: "request:one".to_owned(),
            session_id: None,
            session_generation: None,
            request_sha256: "a".repeat(64),
            response_sha256: "b".repeat(64),
            effect_class: hepta_browser_codec::EffectClass::Observation,
            response_ok: true,
            response_committed: true,
        };
        let encoded = server_evidence_json(&evidence);
        assert!(encoded.contains("\"qualification_only\":true"));
        assert!(encoded.contains("\"product_handler_connected\":false"));
        assert!(encoded.contains("\"request_id\":\"request:one\""));
    }
}
