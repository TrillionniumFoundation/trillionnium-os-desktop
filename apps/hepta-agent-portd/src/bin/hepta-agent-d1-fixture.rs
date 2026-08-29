//! Test-only D1 client for the systemd-owned local AgentPort.
//!
//! This binary is installed only into the D1 qualification image. It never
//! binds or listens and it does not grant semantic or external-effect authority.

#![forbid(unsafe_code)]

use hepta_agent_transport::{ClientConnection, PeerIdentity, PeerPolicy};
use hepta_browser_codec::{
    BrowserOperation, BrowserRequest, decode_response, encode_request,
};
use std::env;
use std::fmt;
use std::fs;
use std::io;
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::time::Duration;

const AGENT_SOCKET_PATH: &str = "/run/hepta/browserd/agent.sock";
const TIMEOUT: Duration = Duration::from_secs(10);

fn main() {
    match run() {
        Ok(result) => {
            if let Some(path) = result.output {
                if let Err(error) = write_result(&path, &result.json) {
                    eprintln!("hepta-agent-d1-fixture: failed to write result: {error}");
                    std::process::exit(1);
                }
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
                    "Usage: hepta-agent-d1-fixture --mode health|expect-denied|hold [--output PATH]"
                );
                std::process::exit(0);
            }
            _ => return Err(FixtureError::Usage("unknown argument")),
        }
    }

    let mode = mode.ok_or(FixtureError::Usage("--mode is required"))?;
    let json = match mode.as_str() {
        "health" => run_health()?,
        "expect-denied" => run_expect_denied()?,
        "hold" => run_hold()?,
        _ => return Err(FixtureError::Usage("unsupported mode")),
    };
    Ok(FixtureResult { json, output })
}

fn run_health() -> Result<String, FixtureError> {
    let stream = UnixStream::connect(AGENT_SOCKET_PATH).map_err(FixtureError::Io)?;
    let server = PeerIdentity::from_stream(&stream).map_err(FixtureError::Transport)?;
    let mut connection =
        ClientConnection::connect(stream, PeerPolicy::exact(server), TIMEOUT)
            .map_err(FixtureError::Transport)?;

    let request = BrowserRequest {
        request_id: "d1-agent-port-health:1".to_owned(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    };
    let encoded = encode_request(&request).map_err(FixtureError::Codec)?;
    let sequence = connection
        .send_request(encoded, TIMEOUT)
        .map_err(FixtureError::Transport)?;
    let response = connection
        .receive_response(sequence, TIMEOUT)
        .map_err(FixtureError::Transport)?;
    let decoded = decode_response(&response).map_err(FixtureError::Codec)?;
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
            "{\"schema\":\"trillionnium.desktop.d1-agent-fixture.v1\",",
            "\"status\":\"PASS\",\"mode\":\"health\",\"request_id\":\"{}\",",
            "\"transport_sequence\":{},\"response_sha256\":\"{}\"}"
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
                "{\"schema\":\"trillionnium.desktop.d1-agent-fixture.v1\",",
                "\"status\":\"PASS\",\"mode\":\"expect-denied\",",
                "\"connection_admitted\":false}"
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
        "{\"schema\":\"trillionnium.desktop.d1-agent-fixture.v1\",",
        "\"status\":\"PASS\",\"mode\":\"hold\"}"
    )
    .to_owned())
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
    Invariant(&'static str),
    Usage(&'static str),
}

impl fmt::Display for FixtureError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "I/O failed: {error}"),
            Self::Transport(error) => write!(formatter, "transport failed: {error}"),
            Self::Codec(error) => write!(formatter, "codec failed: {error}"),
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
            Self::Invariant(_) | Self::Usage(_) => None,
        }
    }
}
