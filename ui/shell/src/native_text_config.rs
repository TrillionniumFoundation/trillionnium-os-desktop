//! Routing inputs for the existing Root UI lane, never authentication claims.
use std::ffi::OsString;
use std::path::PathBuf;

pub(super) struct TextLaunchEndpoint {
    pub socket_path: PathBuf,
    pub root_pid: u32,
}

pub(super) fn from_environment() -> Result<Option<TextLaunchEndpoint>, String> {
    parse(
        std::env::var_os("TRILL_UI_CHAT_SOCKET"),
        std::env::var_os("TRILL_UI_CHAT_ROOT_PID"),
    )
}

fn parse(
    socket: Option<OsString>,
    root_pid: Option<OsString>,
) -> Result<Option<TextLaunchEndpoint>, String> {
    match (socket, root_pid) {
        (None, None) => Ok(None),
        (Some(socket), Some(root_pid)) => {
            let socket_path = PathBuf::from(socket);
            if !socket_path.is_absolute() {
                return Err("TRILL_UI_CHAT_SOCKET must be an absolute Unix socket path".into());
            }
            let root_pid = root_pid
                .to_str()
                .and_then(|pid| pid.parse::<u32>().ok())
                .filter(|pid| *pid != 0)
                .ok_or("TRILL_UI_CHAT_ROOT_PID must name the running original Root process")?;
            Ok(Some(TextLaunchEndpoint {
                socket_path,
                root_pid,
            }))
        }
        _ => {
            Err("TRILL_UI_CHAT_SOCKET and TRILL_UI_CHAT_ROOT_PID must be supplied together".into())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn absent_lane_is_local_only_and_partial_or_relative_configuration_is_rejected() {
        assert!(parse(None, None).unwrap().is_none());
        assert!(parse(Some("/run/root-ui.sock".into()), None).is_err());
        assert!(parse(None, Some("123".into())).is_err());
        assert!(parse(Some("relative.sock".into()), Some("123".into())).is_err());
        assert!(parse(Some("/run/root-ui.sock".into()), Some("0".into())).is_err());
        assert!(parse(Some("/run/root-ui.sock".into()), Some("not-a-pid".into())).is_err());
        let endpoint = parse(Some("/run/root-ui.sock".into()), Some("123".into()))
            .unwrap()
            .unwrap();
        assert_eq!(endpoint.socket_path, PathBuf::from("/run/root-ui.sock"));
        assert_eq!(endpoint.root_pid, 123);
        // Parsing supplies no OwnerSession, agent/thread override or capability.
    }
}
