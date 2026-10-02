//! D1-only AgentPort qualification binary.
//!
//! This binary is compiled only with the explicit non-default
//! `fixture` feature and is installed only into the D1 qualification
//! image. Its `server` mode owns no listener: systemd supplies one already-
//! accepted AF_UNIX stream on standard input. Client modes exercise the same
//! bounded transport and canonical Browser API while the product
//! `hepta-agent-portd` binary remains fixture-free and fails closed.

#![deny(unsafe_op_in_unsafe_fn)]

use hepta_agent_port::{D0FixtureHandler, ServiceEvidence, serve_one};
use hepta_agent_transport::{ClientConnection, PeerIdentity, PeerPolicy};
use hepta_browser_codec::{BrowserOperation, BrowserRequest, decode_response, encode_request};
use hepta_peer_attestation::{
    AttestationError, PeerRuntimePolicy, ProcfsPeerAttestor, hash_trusted_executable,
    resolve_group_id, resolve_user_id,
};
use std::env;
use std::fmt;
use std::fs;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::OpenOptionsExt;
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::time::Duration;

const AGENT_SOCKET_PATH: &str = "/run/hepta/browserd/agent.sock";
const EXPECTED_PEER_USER: &str = "hepta-agent";
const EXPECTED_PEER_GROUP: &str = "hepta-agent";
const EXPECTED_PEER_UNIT: &str = "hepta-agent.service";
const QUALIFICATION_PEER_EXECUTABLE: &str = "/usr/libexec/hepta-agent-d1-fixture";
const CLIENT_TIMEOUT: Duration = Duration::from_secs(10);
const SERVER_CEILING: Duration = Duration::from_secs(20);

fn main() {
    match run() {
        Ok(result) => {
            if let Some(path) = result.output
                && write_result(&path, &result.json).is_err()
            {
                eprintln!("hepta-agent-d1-fixture: result_write_failed");
                std::process::exit(1);
            }
            let _ = write_public_result(io::stdout().lock(), result.mode);
        }
        Err(error) => {
            let category = error.category();
            let _ = write_failure(io::stderr().lock(), category);
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
    let mode = match mode.as_str() {
        "server" => FixtureMode::Server,
        "health" => FixtureMode::Health,
        "expect-denied" => FixtureMode::ExpectDenied,
        "hold" => FixtureMode::Hold,
        "self-check" => FixtureMode::SelfCheck,
        _ => return Err(FixtureError::Usage("unsupported mode")),
    };
    let json = match mode {
        FixtureMode::Server => run_server()?,
        FixtureMode::Health => run_health()?,
        FixtureMode::ExpectDenied => run_expect_denied()?,
        FixtureMode::Hold => run_hold()?,
        FixtureMode::SelfCheck => run_self_check()?,
    };
    Ok(FixtureResult { json, output, mode })
}

fn run_server() -> Result<String, FixtureError> {
    let stream = inherited_stream_from_stdin()?;
    verify_local_socket_path(&stream, Path::new(AGENT_SOCKET_PATH))?;

    let expected_uid = resolve_user_id(EXPECTED_PEER_USER)?;
    let expected_gid = resolve_group_id(EXPECTED_PEER_GROUP)?;
    let peer = PeerIdentity::from_stream(&stream)?;
    let runtime_policy =
        PeerRuntimePolicy::for_system_service(expected_uid, expected_gid, EXPECTED_PEER_UNIT)?;
    // This fixed image-only profile runs the peer under a different service
    // UID. Linux denies cross-UID /proc/<pid>/exe reads without ptrace
    // authority, which the browser service must not receive. Retain the live
    // pidfd/credentials/start-time/cgroup checks and rehash the root-owned
    // qualification executable instead. This does not observe the process's
    // live executable and is unavailable in the default product graph.
    let executable = hash_trusted_executable(QUALIFICATION_PEER_EXECUTABLE)?;
    let attested = ProcfsPeerAttestor::default().attest_with_static_executable_digest(
        peer,
        &runtime_policy,
        &executable,
    )?;

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
    Ok(server_evidence_json(&evidence, peer))
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
    let mut connection =
        ClientConnection::connect(stream, PeerPolicy::exact(server), CLIENT_TIMEOUT)?;

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

// Raw mechanism identity is explicit qualification evidence only. It is not
// added back to the redacted product AgentPort ServiceEvidence type.
fn server_evidence_json(evidence: &ServiceEvidence, peer: PeerIdentity) -> String {
    format!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.d1-agent-server-result.v1\",",
            "\"status\":\"PASS\",\"qualification_only\":true,",
            "\"product_handler_connected\":false,\"listener_created\":false,",
            "\"live_process_executable_observed\":false,",
            "\"peer_executable_binding\":\"root_owned_qualification_path\",",
            "\"peer_pid\":{},\"peer_uid\":{},\"peer_gid\":{},",
            "\"transport_sequence\":{},\"request_id\":\"{}\",",
            "\"request_sha256\":\"{}\",\"response_sha256\":\"{}\",",
            "\"response_ok\":{},\"response_committed\":{}}}"
        ),
        peer.pid.unwrap_or_default(),
        peer.uid,
        peer.gid,
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
    // Explicit qualification output is private evidence, never the operational
    // log sink. Refuse an existing file/link rather than truncate another fact.
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)?;
    use io::Write;
    writeln!(file, "{json}")?;
    file.sync_all()
}

struct FixtureResult {
    json: String,
    output: Option<PathBuf>,
    mode: FixtureMode,
}

#[derive(Clone, Copy)]
enum FixtureMode {
    Server,
    Health,
    ExpectDenied,
    Hold,
    SelfCheck,
}

impl FixtureMode {
    fn public_result(self) -> &'static str {
        match self {
            Self::Server => concat!(
                "{\"schema\":\"trillionnium.desktop.d1-agent-server-result.v1\",",
                "\"status\":\"PASS\",\"qualification_only\":true,",
                "\"product_handler_connected\":false,\"listener_created\":false,",
                "\"live_process_executable_observed\":false,",
                "\"peer_executable_binding\":\"root_owned_qualification_path\",",
                "\"peer_identity_redacted\":true}"
            ),
            Self::SelfCheck => concat!(
                "{\"schema\":\"trillionnium.desktop.d1-agent-fixture-self-check.v1\",",
                "\"status\":\"PASS\",\"qualification_only\":true,",
                "\"listener_created\":false,\"product_handler_connected\":false,",
                "\"peer_identity_redacted\":true}"
            ),
            Self::Health => concat!(
                "{\"schema\":\"trillionnium.desktop.d1-agent-fixture.v2\",",
                "\"status\":\"PASS\",\"mode\":\"health\",",
                "\"qualification_only\":true,\"product_handler_connected\":false}"
            ),
            Self::ExpectDenied => concat!(
                "{\"schema\":\"trillionnium.desktop.d1-agent-fixture.v2\",",
                "\"status\":\"PASS\",\"mode\":\"expect-denied\",",
                "\"qualification_only\":true,\"connection_admitted\":false}"
            ),
            Self::Hold => concat!(
                "{\"schema\":\"trillionnium.desktop.d1-agent-fixture.v2\",",
                "\"status\":\"PASS\",\"mode\":\"hold\",\"qualification_only\":true}"
            ),
        }
    }
}

fn write_public_result(mut writer: impl io::Write, mode: FixtureMode) -> io::Result<()> {
    writeln!(writer, "{}", mode.public_result())
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
    SocketPathMismatch { expected: PathBuf, actual: PathBuf },
    Invariant(&'static str),
    Usage(&'static str),
}

impl FixtureError {
    // Journald is an operational log, separate from the explicit qualification
    // evidence. Never forward peer IDs, process paths, digests, or I/O messages
    // from an underlying error into this sink.
    fn category(&self) -> FailureCategory {
        match self {
            Self::Io(_) => FailureCategory::Io,
            Self::Transport(_) => FailureCategory::Transport,
            Self::Codec(_) => FailureCategory::Codec,
            Self::AgentPort(_) => FailureCategory::AgentPort,
            Self::Attestation(_) => FailureCategory::Attestation,
            Self::WrongInheritedDescriptor => FailureCategory::WrongInheritedDescriptor,
            Self::UnnamedInheritedSocket => FailureCategory::UnnamedInheritedSocket,
            Self::SocketPathMismatch { .. } => FailureCategory::SocketPathMismatch,
            Self::Invariant(_) => FailureCategory::Invariant,
            Self::Usage(_) => FailureCategory::Usage,
        }
    }
}

// The operational logger cannot receive an underlying error or any payload.
// Classification finishes before entering the logging boundary.
enum FailureCategory {
    Io,
    Transport,
    Codec,
    AgentPort,
    Attestation,
    WrongInheritedDescriptor,
    UnnamedInheritedSocket,
    SocketPathMismatch,
    Invariant,
    Usage,
}

impl FailureCategory {
    fn public_code(self) -> &'static str {
        match self {
            Self::Io => "io_failed",
            Self::Transport => "transport_refused",
            Self::Codec => "codec_refused",
            Self::AgentPort => "agent_port_refused",
            Self::Attestation => "peer_attestation_refused",
            Self::WrongInheritedDescriptor => "inherited_descriptor_refused",
            Self::UnnamedInheritedSocket => "unnamed_inherited_socket_refused",
            Self::SocketPathMismatch => "inherited_socket_path_refused",
            Self::Invariant => "invariant_failed",
            Self::Usage => "invalid_usage",
        }
    }
}

fn write_failure(mut writer: impl io::Write, category: FailureCategory) -> io::Result<()> {
    writeln!(writer, "hepta-agent-d1-fixture: {}", category.public_code())
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
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn actual_public_sink_has_no_raw_identity_or_request_details() {
        let mut captured = Vec::new();
        for mode in [
            FixtureMode::Server,
            FixtureMode::Health,
            FixtureMode::ExpectDenied,
            FixtureMode::Hold,
            FixtureMode::SelfCheck,
        ] {
            write_public_result(&mut captured, mode).expect("public diagnostic");
        }
        let captured = String::from_utf8(captured).expect("UTF-8 public result");
        for private in [
            "peer_uid",
            "peer_gid",
            "peer_pid",
            "request_id",
            "response_sha256",
        ] {
            assert!(
                !captured.contains(private),
                "public sink contains {private}"
            );
        }
        assert!(captured.contains("\"connection_admitted\":false"));
        assert_eq!(captured.lines().count(), 5);
    }

    #[test]
    fn explicit_identity_evidence_is_private_exclusive_and_does_not_follow_links() {
        let directory = env::temp_dir().join(format!(
            "d1-private-output-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&directory).expect("private test directory");
        let path = directory.join("evidence.json");
        let json = "{\"peer_uid\":123456789,\"peer_pid\":987654321}";
        write_result(&path, json).expect("write explicit identity evidence");
        assert_eq!(fs::read_to_string(&path).unwrap(), format!("{json}\n"));
        assert_eq!(
            fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert!(write_result(&path, "{}").is_err());
        let link = directory.join("alias.json");
        std::os::unix::fs::symlink(&path, &link).expect("symlink probe");
        assert!(write_result(&link, "{}").is_err());
        assert_eq!(fs::read_to_string(&path).unwrap(), format!("{json}\n"));
        fs::remove_dir_all(directory).expect("cleanup private test evidence");
    }

    #[test]
    fn operational_error_sink_redacts_identity_and_untrusted_details() {
        let errors = [
            FixtureError::Attestation(AttestationError::UidMismatch {
                expected: 123456789,
                actual: 987654321,
            }),
            FixtureError::Attestation(AttestationError::GidMismatch {
                expected: 123456789,
                actual: 987654321,
            }),
            FixtureError::Attestation(AttestationError::ReadProc {
                path: PathBuf::from("/proc/123456789/private-process-path"),
                source: io::Error::other("private-io-detail"),
            }),
            FixtureError::Transport(hepta_agent_transport::TransportError::Io(io::Error::other(
                "private-transport-detail",
            ))),
            FixtureError::SocketPathMismatch {
                expected: PathBuf::from("/private-expected-socket"),
                actual: PathBuf::from("/private-actual-socket"),
            },
        ];
        let mut captured = Vec::new();
        for error in errors {
            write_failure(&mut captured, error.category()).expect("write operational diagnostic");
        }
        assert_eq!(
            String::from_utf8(captured).expect("UTF-8 diagnostics"),
            concat!(
                "hepta-agent-d1-fixture: peer_attestation_refused\n",
                "hepta-agent-d1-fixture: peer_attestation_refused\n",
                "hepta-agent-d1-fixture: peer_attestation_refused\n",
                "hepta-agent-d1-fixture: transport_refused\n",
                "hepta-agent-d1-fixture: inherited_socket_path_refused\n",
            )
        );
    }

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
        let encoded = server_evidence_json(
            &evidence,
            PeerIdentity {
                pid: Some(42),
                uid: 1000,
                gid: 1001,
            },
        );
        assert!(encoded.contains("\"qualification_only\":true"));
        assert!(encoded.contains("\"product_handler_connected\":false"));
        assert!(encoded.contains("\"live_process_executable_observed\":false"));
        assert!(encoded.contains("\"peer_executable_binding\":\"root_owned_qualification_path\""));
        assert!(encoded.contains("\"request_id\":\"request:one\""));
        assert!(encoded.contains("\"peer_pid\":42"));
        assert!(encoded.contains("\"peer_uid\":1000"));
        assert!(encoded.contains("\"peer_gid\":1001"));
    }
}
