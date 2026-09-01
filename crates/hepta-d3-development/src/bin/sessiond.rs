//! Persistent, systemd-socket-activated D3 development AgentPort service.
//!
//! systemd owns the listener. The process retains one BrowserActor, PageOwner,
//! and durable receipt observer across sequential one-request connections.

#![deny(unsafe_op_in_unsafe_fn)]

#[path = "../sessiond/activation.rs"]
mod activation;
#[path = "../sessiond/service.rs"]
mod service;
#[path = "../sessiond/storage.rs"]
mod storage;

use hepta_browser_actor::{D3_BROWSERD_VERSION, D3_PLAN_REVISION, D3_SERVO_COMMIT};
use std::error::Error;
use std::io;
use std::time::Duration;

pub(crate) type AnyError = Box<dyn Error + Send + Sync>;
pub(crate) const MARKER_PATH: &str = "/etc/hepta/enable-agent-port-development";
pub(crate) const SOCKET_PATH: &str = "/run/hepta/browserd/agent-development.sock";
pub(crate) const SOCKET_FD_NAME: &str = "agent-development";
pub(crate) const JOURNAL_PATH: &str = "/var/lib/hepta-browserd/development/receipts.journal";
pub(crate) const JOURNAL_ROOT: &str = "/var/lib/hepta-browserd/development";
pub(crate) const PEER_USER: &str = "hepta-agent";
pub(crate) const PEER_GROUP: &str = "hepta-agent";
pub(crate) const PEER_UNIT: &str = "hepta-agent.service";
pub(crate) const PEER_EXECUTABLE: &str = "/usr/libexec/hepta-agent";
pub(crate) const PROFILE: &str = "development";
pub(crate) const REQUEST_BUDGET: Duration = Duration::from_secs(20);

fn main() {
    let arguments = std::env::args().skip(1).collect::<Vec<_>>();
    let result = if arguments.iter().any(|argument| argument == "--self-check") {
        self_check(&arguments).map(|json| println!("{json}"))
    } else {
        service::run_service(&arguments)
    };
    if let Err(error) = result {
        eprintln!("hepta-agent-port-development-sessiond: {error}");
        std::process::exit(1);
    }
}

fn self_check(arguments: &[String]) -> Result<String, AnyError> {
    activation::require_profile(arguments)?;
    hepta_browser_actor::self_check().map_err(invalid)?;
    Ok(format!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.d3-sessiond-self-check.v1\",",
            "\"ok\":true,\"systemd_listener_required\":true,",
            "\"listener_created\":false,\"accept_mode\":\"accept_no\",",
            "\"persistent_actor\":true,\"one_request_per_connection\":true,",
            "\"same_peer_pid_required\":true,\"receipt_recovery_wired\":true,",
            "\"static_attestation_wired\":true,",
            "\"cross_uid_procfs_required\":false,",
            "\"product_agent_port_enabled\":false,",
            "\"external_effect_authority\":false,\"socket\":\"{}\",",
            "\"plan_revision\":\"{}\",\"servo_commit\":\"{}\",",
            "\"browserd_version\":\"{}\"}}"
        ),
        SOCKET_PATH, D3_PLAN_REVISION, D3_SERVO_COMMIT, D3_BROWSERD_VERSION
    ))
}

pub(crate) fn invalid(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    #[test]
    fn profile_argument_is_exact() {
        assert!(activation::require_profile(&["--profile".into(), "development".into()]).is_ok());
        assert!(activation::require_profile(&[]).is_err());
        assert!(activation::require_profile(&["--profile=development".into()]).is_err());
    }

    #[test]
    fn journal_path_is_confined() {
        assert!(storage::validate_journal_path(Path::new(JOURNAL_PATH)).is_ok());
        assert!(storage::validate_journal_path(Path::new("relative.journal")).is_err());
        assert!(
            storage::validate_journal_path(Path::new("/var/lib/hepta-browserd/outside.journal"))
                .is_err()
        );
    }
}
