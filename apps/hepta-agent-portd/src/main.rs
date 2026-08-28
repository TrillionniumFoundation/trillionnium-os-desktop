use hepta_agent_transport::{
    OsNonceSource, PeerIdentity, PeerPolicy,
};
use hepta_browser_agent_port::{
    BrowserRequestHandler, BrowserResult, DispatchContext, serve_single_request,
};
use hepta_browser_codec::{BrowserRequest, BrowserWireError};
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
        let mut mode = None;
        let mut socket_path = PathBuf::from(DEFAULT_SOCKET_PATH);
        let mut agent_user = DEFAULT_AGENT_USER.to_owned();
        let mut agent_group = DEFAULT_AGENT_GROUP.to_owned();
        let mut agent_unit = DEFAULT_AGENT_UNIT.to_owned();
        let mut timeout_ms = DEFAULT_TIMEOUT_MS;
        let mut arguments = env::args().skip(1);
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
                other => return Err(format!("unknown argument {other}\n{}", usage())),
            }
        }
        let mode = mode.ok_or_else(usage)?;
        if socket_path.as_os_str().is_empty() || !socket_path.is_absolute() {
            return Err("--socket-path must be an absolute path".to_owned());
        }
        if agent_user.is_empty() || agent_group.is_empty() || agent_unit.is_empty() {
            return Err("agent user, group and unit must be non-empty".to_owned());
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
    "usage: hepta-agent-portd (--serve-stdio | --self-check) \
     [--socket-path PATH] [--agent-user USER] [--agent-group GROUP] \
     [--agent-unit UNIT.service] [--timeout-ms N]"
        .to_owned()
}

struct RuntimeUnavailable;

impl BrowserRequestHandler for RuntimeUnavailable {
    fn handle(
        &mut self,
        _request: &BrowserRequest,
        _context: &DispatchContext,
    ) -> Result<BrowserResult, BrowserWireError> {
        Err(BrowserWireError {
            code: "browser.runtime_unavailable".to_owned(),
            message: "the Servo BrowserActor is not active in the current product stage".to_owned(),
            retryable: true,
        })
    }
}

fn serve_stdio(options: &Options) -> Result<(), String> {
    // SAFETY: systemd's `StandardInput=socket` transfers ownership of the one
    // accepted AF_UNIX stream to descriptor zero for this short-lived service.
    // The process does not construct another owner for fd 0.
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

    let outcome = serve_single_request(
        stream,
        PeerPolicy::exact(peer),
        OsNonceSource,
        options.timeout,
        &mut RuntimeUnavailable,
    )
    .map_err(|error| error.to_string())?;
    attested.ensure_alive().map_err(|error| error.to_string())?;

    eprintln!(
        "hepta-agent-portd request_id={} peer_pid={} peer_uid={} cgroup={} sequence={} effect={:?} ok={} request_sha256={} response_sha256={}",
        outcome.request_id,
        attested.snapshot().pid,
        attested.snapshot().uid,
        attested.snapshot().cgroup_v2_path,
        outcome.transport_sequence,
        outcome.effect_class,
        outcome.response_ok,
        outcome.canonical_request_sha256,
        outcome.canonical_response_sha256,
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
    hepta_browser_agent_port::self_check().map_err(|error| error.to_string())?;
    let (stream, _peer) = UnixStream::pair().map_err(|error| error.to_string())?;
    let identity = PeerIdentity::from_stream(&stream).map_err(|error| error.to_string())?;
    let attestor = ProcfsPeerAttestor::default();
    let snapshot = attestor
        .read_snapshot(identity.pid.ok_or_else(|| "self-check peer has no PID".to_owned())?)
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

    #[test]
    fn requires_exactly_one_mode() {
        let mut mode = None;
        set_mode(&mut mode, Mode::SelfCheck).unwrap();
        assert!(set_mode(&mut mode, Mode::ServeStdio).is_err());
    }

    #[test]
    fn default_socket_path_is_absolute_and_runtime_scoped() {
        let path = Path::new(DEFAULT_SOCKET_PATH);
        assert!(path.is_absolute());
        assert!(path.starts_with("/run/hepta/browserd"));
    }

    #[cfg(any(target_os = "linux", target_os = "android"))]
    #[test]
    fn full_self_check_passes() {
        self_check().unwrap();
    }
}
