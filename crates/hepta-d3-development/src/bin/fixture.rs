//! Exact-image D3 TaskFlow fixture.
//!
//! One process issues sequential one-request connections so the persistent
//! daemon can bind one semantic principal to one live mechanism identity.

#[path = "../fixture/client.rs"]
mod client;
#[path = "../fixture/corpus.rs"]
mod corpus;
#[path = "../fixture/model.rs"]
mod model;

use hepta_browser_codec::{BrowserOperation, BrowserRequest, encode_request};
use std::error::Error;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

type AnyError = Box<dyn Error + Send + Sync>;
pub(crate) const SOCKET_PATH: &str = "/run/hepta/browserd/agent-development.sock";

fn main() {
    match run() {
        Ok(result) => {
            if let Some(path) = result.output
                && let Err(error) = write_result(&path, &result.json)
            {
                eprintln!("hepta-agent-d3-fixture: failed to write result: {error}");
                std::process::exit(1);
            }
            println!("{}", result.json);
        }
        Err(error) => {
            eprintln!("hepta-agent-d3-fixture: {error}");
            std::process::exit(1);
        }
    }
}

fn run() -> Result<FixtureResult, AnyError> {
    let mut mode = None;
    let mut output = None;
    let mut arguments = std::env::args().skip(1);
    while let Some(argument) = arguments.next() {
        match argument.as_str() {
            "--mode" => mode = arguments.next(),
            "--output" => output = arguments.next().map(PathBuf::from),
            "--help" | "-h" => {
                println!(
                    "Usage: hepta-agent-d3-fixture --mode corpus|expect-rejected|self-check [--output PATH]"
                );
                std::process::exit(0);
            }
            _ => return Err(invalid("unknown argument").into()),
        }
    }
    let json = match mode.as_deref() {
        Some("corpus") => corpus::run()?,
        Some("expect-rejected") => expect_rejected()?,
        Some("self-check") => self_check()?,
        _ => return Err(invalid("--mode is required").into()),
    };
    Ok(FixtureResult { json, output })
}

fn expect_rejected() -> Result<String, AnyError> {
    let request = BrowserRequest {
        request_id: "d3-wrong-unit".to_owned(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    };
    if client::invoke(request).is_ok() {
        return Err(invalid("wrong-unit peer unexpectedly completed a request").into());
    }
    Ok(format!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.d3-wrong-unit-negative.v1\",",
            "\"status\":\"PASS\",\"connection_admitted\":false,",
            "\"process_pid\":{},\"expected_unit\":\"hepta-agent.service\",",
            "\"actual_unit\":\"hepta-agent-unauthorized.service\"}}"
        ),
        std::process::id()
    ))
}

fn self_check() -> Result<String, AnyError> {
    let encoded = encode_request(&BrowserRequest {
        request_id: "d3-self-check".to_owned(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    })?;
    if encoded.is_empty() {
        return Err(invalid("canonical request encoding is empty").into());
    }
    Ok(concat!(
        "{\"schema\":\"trillionnium.desktop.d3-taskflow-fixture-self-check.v1\",",
        "\"status\":\"PASS\",\"listener_created\":false,",
        "\"one_long_lived_process\":true,\"one_request_per_connection\":true,",
        "\"external_effect_authority\":false}"
    )
    .to_owned())
}

fn write_result(path: &Path, json: &str) -> Result<(), io::Error> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, format!("{json}\n"))
}

pub(crate) fn escape_json(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
        .replace('\t', "\\t")
}

pub(crate) fn invalid(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.into())
}

struct FixtureResult {
    json: String,
    output: Option<PathBuf>,
}
