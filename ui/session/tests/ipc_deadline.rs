//! Actual Session process regression, using only a private temporary runtime.
//! No compositor, application window or Hepta endpoint is started.
use std::fs::{self, DirBuilder};
use std::io::{self, Write};
use std::os::unix::fs::DirBuilderExt;
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};
use trill_ui_core::{read_frame, unix_ms, Response};

struct SessionProcess {
    child: Child,
    directory: PathBuf,
}

impl Drop for SessionProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = fs::remove_dir_all(&self.directory);
    }
}

struct DripPeer {
    stopped: Arc<AtomicBool>,
    worker: Option<JoinHandle<()>>,
}

impl Drop for DripPeer {
    fn drop(&mut self) {
        self.stopped.store(true, Ordering::Relaxed);
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

fn snapshot(socket: &std::path::Path) -> io::Result<Response> {
    let mut peer = UnixStream::connect(socket)?;
    peer.set_read_timeout(Some(Duration::from_millis(1500)))?;
    peer.set_write_timeout(Some(Duration::from_millis(100)))?;
    peer.write_all(b"{\"type\":\"snapshot\"}\n")?;
    serde_json::from_slice(&read_frame(peer)?).map_err(io::Error::other)
}

#[test]
fn dripping_peer_releases_the_owner_for_an_independent_snapshot() {
    let directory = std::env::temp_dir().join(format!(
        "trill-deadline-{}-{}",
        std::process::id(),
        unix_ms()
    ));
    DirBuilder::new().mode(0o700).create(&directory).unwrap();
    let mut command = Command::new(env!("CARGO_BIN_EXE_trill-session"));
    for name in [
        "TRILL_HEPTA_AGENTD_SOCKET",
        "TRILL_HEPTA_AGENT_ID",
        "TRILL_HEPTA_SPAWN_GENERATION",
        "TRILL_HEPTA_PEER_UID",
        "TRILL_HEPTA_RUN_ID",
        "TRILL_OBJECTIVE_HOST_SOCKET",
        "TRILL_OBJECTIVE_HOST_PID",
    ] {
        command.env_remove(name);
    }
    let child = command
        .env("XDG_RUNTIME_DIR", &directory)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let mut owner = SessionProcess { child, directory };
    let socket = owner.directory.join("trillionnium-ui/session.sock");
    let ready_deadline = Instant::now() + Duration::from_secs(3);
    let initial = loop {
        if let Ok(response) = snapshot(&socket) {
            break response;
        }
        assert!(
            owner.child.try_wait().unwrap().is_none(),
            "Session exited before readiness"
        );
        assert!(
            Instant::now() < ready_deadline,
            "Session did not bind its private socket"
        );
        thread::sleep(Duration::from_millis(20));
    };
    let Response::Snapshot {
        session_instance, ..
    } = initial
    else {
        panic!("initial snapshot");
    };

    let mut slow = UnixStream::connect(&socket).unwrap();
    slow.set_write_timeout(Some(Duration::from_millis(100)))
        .unwrap();
    slow.write_all(b"{").unwrap();
    let stopped = Arc::new(AtomicBool::new(false));
    let worker_stopped = stopped.clone();
    let worker = thread::spawn(move || {
        while !worker_stopped.load(Ordering::Relaxed) {
            if slow.write_all(b" ").is_err() {
                break;
            }
            thread::sleep(Duration::from_millis(40));
        }
    });
    let _slow_peer = DripPeer {
        stopped,
        worker: Some(worker),
    };
    // Connect order puts the slow peer first. Leave it active while observing
    // the independent client; closing it is not allowed to make the test pass.
    let started = Instant::now();
    let response = snapshot(&socket).expect("one slow peer must not monopolize Session");
    assert!(started.elapsed() < Duration::from_millis(1500));
    let Response::Snapshot {
        session_instance: current,
        tasks,
        ..
    } = response
    else {
        panic!("independent snapshot");
    };
    assert_eq!(
        current, session_instance,
        "the same owner must recover without restart"
    );
    assert!(tasks.is_empty(), "a partial request must not create a task");
}
