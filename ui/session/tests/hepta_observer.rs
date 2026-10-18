//! Real Session executable / Unix IPC negatives. The deliberately stalled
//! peer below is a fault fixture, not evidence of a successful Hepta runtime.
use std::fs::{self, Permissions};
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::os::unix::net::UnixListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};
use trill_ui_core::hepta::HeptaConnectionState;
use trill_ui_core::{request_at, unix_ms, Request, Response};

struct Harness {
    child: Child,
    runtime: PathBuf,
}

impl Drop for Harness {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = fs::remove_dir_all(&self.runtime);
    }
}

fn runtime_dir(label: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "trill-hepta-{label}-{}-{}",
        std::process::id(),
        unix_ms()
    ));
    fs::create_dir(&path).unwrap();
    fs::set_permissions(&path, Permissions::from_mode(0o700)).unwrap();
    path
}

fn session_command(runtime: &PathBuf) -> Command {
    let mut command = Command::new(env!("CARGO_BIN_EXE_trill-session"));
    command
        .env("XDG_RUNTIME_DIR", runtime)
        .env_remove("TRILL_HEPTA_AGENTD_SOCKET")
        .env_remove("TRILL_HEPTA_AGENT_ID")
        .env_remove("TRILL_HEPTA_SPAWN_GENERATION")
        .env_remove("TRILL_HEPTA_PEER_UID")
        .env_remove("TRILL_HEPTA_RUN_ID")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    command
}

fn snapshot(harness: &mut Harness) -> Response {
    let socket = harness.runtime.join("trillionnium-ui/session.sock");
    let started = Instant::now();
    loop {
        if let Ok(response) = request_at(&socket, &Request::Snapshot) {
            return response;
        }
        assert!(
            harness.child.try_wait().unwrap().is_none(),
            "Session exited"
        );
        assert!(
            started.elapsed() < Duration::from_secs(2),
            "Session IPC unavailable"
        );
        thread::sleep(Duration::from_millis(20));
    }
}

#[test]
fn no_observer_configuration_is_explicit_and_cannot_submit_objectives() {
    let runtime = runtime_dir("unconfigured");
    let child = session_command(&runtime).spawn().unwrap();
    let mut harness = Harness { child, runtime };
    let Response::Snapshot { hepta, tasks, .. } = snapshot(&mut harness) else {
        panic!("expected snapshot");
    };
    assert_eq!(hepta.connection, HeptaConnectionState::NotConfigured);
    assert!(hepta.last_observation.is_none());
    assert!(tasks.is_empty());
    // Renderer IPC has no objective or generic Agentd forwarding variant.
    assert!(serde_json::from_str::<Request>(r#"{"type":"objective_start","text":"run"}"#).is_err());
    assert!(
        serde_json::from_str::<Request>(r#"{"type":"agentd_rpc","method":"run_start"}"#).is_err()
    );
}

#[test]
fn stalled_agentd_cannot_block_host_snapshot_or_action_dispatch() {
    let runtime = runtime_dir("stalled");
    let peer = runtime.join("stalled-agentd.sock");
    let _listener = UnixListener::bind(&peer).unwrap();
    fs::set_permissions(&peer, Permissions::from_mode(0o600)).unwrap();
    let uid = fs::metadata(&runtime).unwrap().uid();
    let child = session_command(&runtime)
        .env("TRILL_HEPTA_AGENTD_SOCKET", &peer)
        .env(
            "TRILL_HEPTA_AGENT_ID",
            "00000000-0000-4000-8000-000000000001",
        )
        .env("TRILL_HEPTA_SPAWN_GENERATION", "1")
        .env("TRILL_HEPTA_PEER_UID", uid.to_string())
        .spawn()
        .unwrap();
    let mut harness = Harness { child, runtime };
    let Response::Snapshot {
        session_instance, ..
    } = snapshot(&mut harness)
    else {
        panic!("expected snapshot");
    };
    let socket = harness.runtime.join("trillionnium-ui/session.sock");
    let started = Instant::now();
    let mut saw_timeout = false;
    while started.elapsed() < Duration::from_secs(7) {
        let before = Instant::now();
        let Response::Snapshot { hepta, tasks, .. } = snapshot(&mut harness) else {
            panic!("expected snapshot");
        };
        assert!(
            before.elapsed() < Duration::from_millis(750),
            "Agentd blocked host snapshots"
        );
        assert!(tasks.is_empty());
        assert!(hepta.last_observation.is_none());
        assert_ne!(hepta.connection, HeptaConnectionState::Observed);
        if hepta.connection == HeptaConnectionState::Unavailable {
            assert_eq!(hepta.error_code.as_deref(), Some("timeout"));
            saw_timeout = true;
            break;
        }
        let before = Instant::now();
        let response = request_at(
            &socket,
            &Request::Cancel {
                id: u64::MAX,
                expected_instance: session_instance.clone(),
            },
        )
        .unwrap();
        assert!(matches!(response, Response::Error { .. }));
        assert!(
            before.elapsed() < Duration::from_millis(750),
            "Agentd blocked host action dispatch"
        );
        thread::sleep(Duration::from_millis(50));
    }
    assert!(
        saw_timeout,
        "stalled peer must become unavailable within the total poll deadline"
    );
}
