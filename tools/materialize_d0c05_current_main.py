#!/usr/bin/env python3
"""Adapt the reviewed D0C-05 custody surface to the current D0C-04 product API.

The calling workflow first restores only the reviewed D0C-05 source files from
the historical source branch. This script removes retired bridge dependencies,
uses the current `hepta-agent-port` API, avoids adding a test-only Cargo supply
chain, and extends the stable repository validator. It creates no socket and
ships no activation marker.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, value: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one marker, found {count}")
    return text.replace(old, new, 1)


def patch_workspace() -> None:
    path = "Cargo.toml"
    text = read(path)
    marker = '  "crates/hepta-agent-port",\n'
    insertion = (
        marker
        + '  "crates/hepta-peer-attestation",\n'
        + '  "apps/hepta-agent-portd",\n'
    )
    if '  "crates/hepta-peer-attestation",\n' not in text:
        if text.count(marker) != 2:
            raise ValueError("workspace AgentPort marker must occur in members and defaults")
        text = text.replace(marker, insertion)
    write(path, text)


def write_cargo_manifests() -> None:
    write(
        "crates/hepta-peer-attestation/Cargo.toml",
        '''[package]
name = "hepta-peer-attestation"
version.workspace = true
edition.workspace = true
rust-version.workspace = true
license.workspace = true
repository.workspace = true
publish = false

[dependencies]
hepta-agent-transport = { path = "../hepta-agent-transport" }
libc = "=0.2.186"
''',
    )
    write(
        "apps/hepta-agent-portd/Cargo.toml",
        '''[package]
name = "hepta-agent-portd"
version.workspace = true
edition.workspace = true
rust-version.workspace = true
license.workspace = true
repository.workspace = true
publish = false

[dependencies]
hepta-agent-port = { path = "../../crates/hepta-agent-port" }
hepta-agent-transport = { path = "../../crates/hepta-agent-transport" }
hepta-browser-codec = { path = "../../crates/hepta-browser-codec" }
hepta-peer-attestation = { path = "../../crates/hepta-peer-attestation" }

[[bin]]
name = "hepta-agent-portd"
path = "src/main.rs"
''',
    )


def patch_attestation_tests() -> None:
    path = "crates/hepta-peer-attestation/src/lib.rs"
    text = read(path)
    text = replace_once(
        text,
        "    use tempfile::TempDir;\n",
        "    use std::env;\n"
        "    use std::process;\n"
        "    use std::sync::atomic::{AtomicU64, Ordering};\n"
        "    use std::time::{SystemTime, UNIX_EPOCH};\n",
        "attestation std-only test imports",
    )
    helper_marker = "\n    fn fixture_snapshot(\n"
    helper = '''
    static NEXT_TEST_DIRECTORY: AtomicU64 = AtomicU64::new(1);

    struct TestDirectory {
        path: PathBuf,
    }

    impl TestDirectory {
        fn new() -> Self {
            let sequence = NEXT_TEST_DIRECTORY.fetch_add(1, Ordering::Relaxed);
            let nanos = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("test clock must follow Unix epoch")
                .as_nanos();
            let path = env::temp_dir().join(format!(
                "hepta-peer-attestation-{}-{nanos}-{sequence}",
                process::id()
            ));
            fs::create_dir(&path).expect("create isolated proc fixture directory");
            Self { path }
        }

        fn path(&self) -> &Path {
            &self.path
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }
'''
    if "struct TestDirectory" not in text:
        text = replace_once(text, helper_marker, helper + helper_marker, "attestation test directory")
    text = text.replace("let temp = TempDir::new().unwrap();", "let temp = TestDirectory::new();")
    if "tempfile" in text:
        raise ValueError("tempfile dependency remained in peer attestation source")
    write(path, text)


def write_agent_portd() -> None:
    write(
        "apps/hepta-agent-portd/src/main.rs",
        '''#![deny(unsafe_op_in_unsafe_fn)]

use hepta_agent_port::{
    AgentPortError, BrowserRequestHandler, DispatchContext, HandlerOutcome, serve_one,
};
use hepta_agent_transport::{PeerIdentity, PeerPolicy};
use hepta_browser_codec::{BrowserErrorCode, BrowserRequest, BrowserWireError};
use hepta_peer_attestation::{
    PeerRuntimePolicy, ProcfsPeerAttestor, resolve_group_id, resolve_user_id,
};
use std::env;
use std::os::fd::FromRawFd;
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::Duration;

const DEFAULT_SOCKET_PATH: &str = "/run/hepta/browserd/agent.sock";
const DEFAULT_AGENT_USER: &str = "hepta-agent";
const DEFAULT_AGENT_GROUP: &str = "hepta-agent";
const DEFAULT_AGENT_UNIT: &str = "hepta-agent.service";
const DEFAULT_TIMEOUT_MS: u64 = 20_000;
const RUNTIME_UNAVAILABLE_MESSAGE: &str =
    "browser.runtime_unavailable: the Servo BrowserActor is not active in the current product stage";

#[derive(Debug)]
struct Options {
    mode: Mode,
    socket_path: PathBuf,
    agent_user: String,
    agent_group: String,
    agent_unit: String,
    timeout: Duration,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Mode {
    ServeStdio,
    SelfCheck,
}

impl Options {
    fn parse() -> Result<Self, String> {
        Self::parse_from(env::args().skip(1))
    }

    fn parse_from(mut arguments: impl Iterator<Item = String>) -> Result<Self, String> {
        let mut mode = None;
        let mut socket_path = PathBuf::from(DEFAULT_SOCKET_PATH);
        let mut agent_user = DEFAULT_AGENT_USER.to_owned();
        let mut agent_group = DEFAULT_AGENT_GROUP.to_owned();
        let mut agent_unit = DEFAULT_AGENT_UNIT.to_owned();
        let mut timeout_ms = DEFAULT_TIMEOUT_MS;
        while let Some(argument) = arguments.next() {
            match argument.as_str() {
                "--serve-stdio" => set_mode(&mut mode, Mode::ServeStdio)?,
                "--self-check" => set_mode(&mut mode, Mode::SelfCheck)?,
                "--socket-path" => {
                    socket_path = PathBuf::from(next_value(&mut arguments, &argument)?);
                }
                "--agent-user" => agent_user = next_value(&mut arguments, &argument)?,
                "--agent-group" => agent_group = next_value(&mut arguments, &argument)?,
                "--agent-unit" => agent_unit = next_value(&mut arguments, &argument)?,
                "--timeout-ms" => {
                    timeout_ms = next_value(&mut arguments, &argument)?
                        .parse::<u64>()
                        .map_err(|_| "--timeout-ms must be an unsigned integer".to_owned())?;
                }
                "--help" | "-h" => return Err(usage()),
                other => return Err(format!("unknown argument {other}\\n{}", usage())),
            }
        }
        let mode = mode.ok_or_else(usage)?;
        if socket_path.as_os_str().is_empty() || !socket_path.is_absolute() {
            return Err("--socket-path must be an absolute path".to_owned());
        }
        if agent_user.is_empty() || agent_group.is_empty() || agent_unit.is_empty() {
            return Err("agent user, group and unit must be non-empty".to_owned());
        }
        if !agent_unit.ends_with(".service") || agent_unit.contains('/') {
            return Err("--agent-unit must be one .service unit name".to_owned());
        }
        if timeout_ms == 0 || timeout_ms > 120_000 {
            return Err("--timeout-ms must be between 1 and 120000".to_owned());
        }
        Ok(Self {
            mode,
            socket_path,
            agent_user,
            agent_group,
            agent_unit,
            timeout: Duration::from_millis(timeout_ms),
        })
    }
}

fn set_mode(target: &mut Option<Mode>, value: Mode) -> Result<(), String> {
    if target.replace(value).is_some() {
        return Err("select exactly one execution mode".to_owned());
    }
    Ok(())
}

fn next_value(
    arguments: &mut impl Iterator<Item = String>,
    option: &str,
) -> Result<String, String> {
    arguments
        .next()
        .ok_or_else(|| format!("{option} requires a value"))
}

fn usage() -> String {
    "usage: hepta-agent-portd (--serve-stdio | --self-check) \\\n     [--socket-path PATH] [--agent-user USER] [--agent-group GROUP] \\\n     [--agent-unit UNIT.service] [--timeout-ms N]"
        .to_owned()
}

struct RuntimeUnavailable;

impl BrowserRequestHandler for RuntimeUnavailable {
    fn handle(
        &mut self,
        _context: &DispatchContext,
        _request: &BrowserRequest,
    ) -> Result<HandlerOutcome, AgentPortError> {
        Ok(HandlerOutcome::Failure(BrowserWireError {
            code: BrowserErrorCode::Unsupported,
            message: RUNTIME_UNAVAILABLE_MESSAGE.to_owned(),
            details: None,
        }))
    }
}

fn serve_stdio(options: &Options) -> Result<(), String> {
    // SAFETY: systemd's `StandardInput=socket` transfers ownership of the one
    // accepted AF_UNIX stream to descriptor zero for this short-lived service.
    // This process constructs exactly one owner for fd 0 and does not use stdin
    // through another API after this transfer.
    let stream = unsafe { UnixStream::from_raw_fd(0) };
    verify_local_socket_path(&stream, &options.socket_path)?;

    let peer = PeerIdentity::from_stream(&stream).map_err(|error| error.to_string())?;
    let expected_uid = resolve_user_id(&options.agent_user).map_err(|error| error.to_string())?;
    let expected_gid = resolve_group_id(&options.agent_group).map_err(|error| error.to_string())?;
    let runtime_policy = PeerRuntimePolicy::for_system_service(
        expected_uid,
        expected_gid,
        options.agent_unit.clone(),
    )
    .map_err(|error| error.to_string())?;
    let attestor = ProcfsPeerAttestor::default();
    let attested = attestor
        .attest(peer, &runtime_policy)
        .map_err(|error| error.to_string())?;

    let evidence = serve_one(
        stream,
        PeerPolicy::exact(peer),
        options.timeout,
        &mut RuntimeUnavailable,
    )
    .map_err(|error| error.to_string())?;
    attested.ensure_alive().map_err(|error| error.to_string())?;

    eprintln!(
        "hepta-agent-portd request_id={} peer_pid={} peer_uid={} cgroup={} sequence={} effect={:?} ok={} committed={} request_sha256={} response_sha256={}",
        evidence.request_id,
        attested.snapshot().pid,
        attested.snapshot().uid,
        attested.snapshot().cgroup_v2_path,
        evidence.transport_sequence,
        evidence.effect_class,
        evidence.response_ok,
        evidence.response_committed,
        evidence.request_sha256,
        evidence.response_sha256,
    );
    Ok(())
}

fn verify_local_socket_path(stream: &UnixStream, expected: &Path) -> Result<(), String> {
    let address = stream
        .local_addr()
        .map_err(|error| format!("failed to inspect inherited socket address: {error}"))?;
    let actual = address
        .as_pathname()
        .ok_or_else(|| "inherited socket has no pathname local address".to_owned())?;
    if actual != expected {
        return Err(format!(
            "inherited socket path {} does not match {}",
            actual.display(),
            expected.display()
        ));
    }
    Ok(())
}

fn self_check() -> Result<(), String> {
    hepta_agent_port::self_check().map_err(|error| error.to_string())?;
    let (stream, _peer) = UnixStream::pair().map_err(|error| error.to_string())?;
    let identity = PeerIdentity::from_stream(&stream).map_err(|error| error.to_string())?;
    let pid = identity
        .pid
        .ok_or_else(|| "self-check peer has no PID".to_owned())?;
    let attestor = ProcfsPeerAttestor::default();
    let snapshot = attestor
        .read_snapshot(pid)
        .map_err(|error| error.to_string())?;
    let attested = attestor
        .attest(identity, &PeerRuntimePolicy::exact(&snapshot))
        .map_err(|error| error.to_string())?;
    attested.ensure_alive().map_err(|error| error.to_string())?;
    Ok(())
}

fn main() -> ExitCode {
    let options = match Options::parse() {
        Ok(options) => options,
        Err(error) => {
            eprintln!("{error}");
            return ExitCode::from(2);
        }
    };
    let result = match options.mode {
        Mode::ServeStdio => serve_stdio(&options),
        Mode::SelfCheck => self_check(),
    };
    if let Err(error) = result {
        eprintln!("hepta-agent-portd failed: {error}");
        return ExitCode::FAILURE;
    }
    ExitCode::SUCCESS
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(arguments: &[&str]) -> Result<Options, String> {
        Options::parse_from(arguments.iter().map(|value| (*value).to_owned()))
    }

    #[test]
    fn requires_exactly_one_mode() {
        assert!(parse(&[]).is_err());
        assert!(parse(&["--self-check", "--serve-stdio"]).is_err());
        assert!(parse(&["--self-check"]).is_ok());
    }

    #[test]
    fn default_socket_path_is_absolute_and_runtime_scoped() {
        let options = parse(&["--self-check"]).unwrap();
        assert!(options.socket_path.is_absolute());
        assert!(options.socket_path.starts_with("/run/hepta/browserd"));
    }

    #[test]
    fn rejects_relative_socket_and_non_service_unit() {
        assert!(parse(&["--self-check", "--socket-path", "relative.sock"]).is_err());
        assert!(parse(&["--self-check", "--agent-unit", "agent.scope"]).is_err());
    }

    #[cfg(any(target_os = "linux", target_os = "android"))]
    #[test]
    fn full_self_check_passes() {
        self_check().unwrap();
    }
}
''',
    )


def patch_custody_validator() -> None:
    path = "tools/verify_systemd_socket_custody.py"
    text = read(path)
    old = '''    for token in (
        "PeerIdentity::from_stream",
        "ProcfsPeerAttestor::default",
        "PeerRuntimePolicy::for_system_service",
        "verify_local_socket_path",
        "serve_single_request",
        "browser.runtime_unavailable",
    ):
'''
    new = '''    for token in (
        "PeerIdentity::from_stream",
        "ProcfsPeerAttestor::default",
        "PeerRuntimePolicy::for_system_service",
        "verify_local_socket_path",
        "serve_one",
        "BrowserErrorCode::Unsupported",
        "hepta_agent_port::self_check",
        "browser.runtime_unavailable",
    ):
'''
    text = replace_once(text, old, new, "custody source markers")
    retired = '''    if "hepta_browser_agent_port" in source_text or "serve_single_request" in source_text:
        raise CustodyError("retired AgentPort bridge remains in the service source")
'''
    insert_marker = '''    for token in (
        "PeerIdentity::from_stream",
'''
    if retired not in text:
        position = text.find(insert_marker)
        if position == -1:
            raise ValueError("custody marker loop is missing")
        loop_end = text.find("\n\n    print(", position)
        if loop_end == -1:
            raise ValueError("custody source marker loop end is missing")
        text = text[:loop_end] + "\n" + retired + text[loop_end:]
    write(path, text)


def patch_permanent_workflow() -> None:
    path = ".github/workflows/agent-port-custody.yml"
    text = read(path).replace(
        '      - "crates/hepta-browser-agent-port/**"\n',
        '      - "crates/hepta-agent-port/**"\n',
    )
    text = text.replace(
        "cargo clippy -p hepta-peer-attestation -p hepta-agent-portd --all-targets --locked -- -D warnings",
        "cargo clippy -p hepta-peer-attestation -p hepta-agent-portd --all-targets --locked -- -D warnings",
    )
    if "hepta-browser-agent-port" in text:
        raise ValueError("retired AgentPort path remained in permanent workflow")
    write(path, text)


def patch_stable_validator() -> None:
    path = "tools/validate_repository.py"
    text = read(path)
    member_marker = '    "crates/hepta-agent-port",\n'
    member_addition = (
        member_marker
        + '    "crates/hepta-peer-attestation",\n'
        + '    "apps/hepta-agent-portd",\n'
    )
    if '    "crates/hepta-peer-attestation",\n' not in text:
        text = replace_once(text, member_marker, member_addition, "stable D0C-05 members")
    path_marker = '    "crates/hepta-agent-port/src/lib.rs",\n'
    path_addition = path_marker + '''    "crates/hepta-peer-attestation/Cargo.toml",
    "crates/hepta-peer-attestation/src/lib.rs",
    "apps/hepta-agent-portd/Cargo.toml",
    "apps/hepta-agent-portd/src/main.rs",
    "contracts/agent-port-custody.v1.json",
    "packaging/debian/systemd/hepta-browserd-agent.socket",
    "packaging/debian/systemd/hepta-browserd-agent@.service",
    "packaging/debian/sysusers.d/trillionnium-desktop.conf",
    "packaging/debian/tmpfiles.d/trillionnium-desktop.conf",
    "packaging/debian/systemd-preset/90-trillionnium-desktop.preset",
    "packaging/debian/hepta-agent-portd.install",
    "tools/verify_systemd_socket_custody.py",
    "docs/architecture/AGENT_PORT_SYSTEMD_CUSTODY.md",
    "docs/evidence/2026-08-28-d0c05-systemd-agent-port-custody.md",
'''
    if '    "contracts/agent-port-custody.v1.json",\n' not in text:
        text = replace_once(text, path_marker, path_addition, "stable D0C-05 required paths")
    write(path, text)


def patch_contract_and_docs() -> None:
    path = "contracts/agent-port-custody.v1.json"
    import json

    contract = json.loads(read(path))
    contract["status"] = "D0C_05_SOURCE_CANDIDATE_DEFAULT_DISABLED"
    contract["request_model"]["browser_runtime_handler"] = (
        "typed_unsupported_until_BrowserActor_and_Servo_runtime_are_host_validated"
    )
    contract["source_integration"] = {
        "agent_port_crate": "hepta-agent-port",
        "peer_attestation_crate": "hepta-peer-attestation",
        "connection_service": "hepta-agent-portd",
        "listener_created_during_tests": False,
        "enable_marker_shipped": False,
        "host_validation": "PENDING",
    }
    write(path, json.dumps(contract, indent=2, sort_keys=True) + "\n")

    evidence_path = "docs/evidence/2026-08-28-d0c05-systemd-agent-port-custody.md"
    evidence = read(evidence_path)
    appendix = '''

## Current-main rebuild boundary

This candidate is rebuilt from the host-validated D0C-04 product graph and uses
`hepta-agent-port`; the historical `hepta-browser-agent-port` bridge is not a
product dependency. Test-only peer-attestation fixtures use the Rust standard
library and do not add a `tempfile` dependency. Source presence does not enable
the socket: the preset remains `disable` and `/etc/hepta/enable-agent-port` is
not shipped.
'''
    if "## Current-main rebuild boundary" not in evidence:
        evidence += appendix
    write(evidence_path, evidence)


def main() -> int:
    patch_workspace()
    write_cargo_manifests()
    patch_attestation_tests()
    write_agent_portd()
    patch_custody_validator()
    patch_permanent_workflow()
    patch_stable_validator()
    patch_contract_and_docs()
    print("materialized current-main D0C-05 source candidate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
