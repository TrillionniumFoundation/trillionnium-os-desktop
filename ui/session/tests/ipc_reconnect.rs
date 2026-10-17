//! Headless host Linux IPC smoke. Does not claim graphics or compositor success.
use std::fs::{self, Permissions};
use std::io::Write;
use std::os::unix::fs::PermissionsExt;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};
use trill_ui_core::{
    request_at, unix_ms, AppKind, Request, Response, TaskState, Workspace, MAX_FRAME,
};

struct Harness {
    child: Child,
    dir: PathBuf,
}
impl Drop for Harness {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = fs::remove_dir_all(&self.dir);
    }
}

#[test]
fn private_socket_survives_client_disconnect_and_reports_owned_task() {
    let dir = std::env::temp_dir().join(format!(
        "trill-ipc-test-{}-{}",
        std::process::id(),
        unix_ms()
    ));
    fs::create_dir(&dir).expect("create runtime directory");
    fs::set_permissions(&dir, Permissions::from_mode(0o700)).unwrap();
    let child = Command::new(env!("CARGO_BIN_EXE_trill-session"))
        .env("XDG_RUNTIME_DIR", &dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("start session service");
    let mut harness = Harness {
        child,
        dir: dir.clone(),
    };
    let socket = dir.join("trillionnium-ui/session.sock");

    let initial = {
        let mut ready = None;
        for _ in 0..100 {
            if let Ok(response) = request_at(&socket, &Request::Snapshot) {
                ready = Some(response);
                break;
            }
            if let Some(status) = harness.child.try_wait().unwrap() {
                panic!("session exited before binding socket: {status}");
            }
            thread::sleep(Duration::from_millis(20));
        }
        ready.expect("session must bind within 2s")
    };
    let Response::Snapshot {
        tasks,
        session_instance,
        ..
    } = initial
    else {
        panic!("expected session snapshot");
    };
    assert!(tasks.is_empty());
    assert!(!session_instance.is_empty());
    assert_eq!(
        fs::metadata(&socket).unwrap().permissions().mode() & 0o077,
        0
    );

    // A second real service executable must fail on the held flock without
    // unlinking or replacing the original live Unix listener. No GUI needed.
    let mut duplicate = Command::new(env!("CARGO_BIN_EXE_trill-session"))
        .env("XDG_RUNTIME_DIR", &dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .expect("start competing session");
    let mut duplicate_exited = false;
    for _ in 0..100 {
        if duplicate.try_wait().unwrap().is_some() {
            duplicate_exited = true;
            break;
        }
        thread::sleep(Duration::from_millis(10));
    }
    if !duplicate_exited {
        let _ = duplicate.kill();
        let _ = duplicate.wait();
        panic!("second session was not rejected promptly");
    }
    let duplicate_output = duplicate.wait_with_output().unwrap();
    assert!(
        !duplicate_output.status.success(),
        "second service must not acquire active socket"
    );
    let diagnostic = String::from_utf8_lossy(&duplicate_output.stderr);
    assert!(
        diagnostic.contains("os error 11")
            || diagnostic.contains("Resource temporarily unavailable"),
        "second instance must fail specifically on flock contention: {diagnostic}"
    );
    let Response::Snapshot {
        session_instance: survivor,
        tasks: survivor_tasks,
        ..
    } = request_at(&socket, &Request::Snapshot).unwrap()
    else {
        panic!("survivor snapshot");
    };
    assert_eq!(
        survivor, session_instance,
        "original session identity must survive competing startup"
    );
    assert!(survivor_tasks.is_empty());

    // An invalid enum must not silently map to an executable.
    let mut bad = std::os::unix::net::UnixStream::connect(&socket).unwrap();
    bad.write_all(b"{\"type\":\"launch\",\"workspace\":\"root\",\"app\":\"notes\"}\n")
        .unwrap();
    let rejected: Response =
        serde_json::from_slice(&trill_ui_core::read_frame(&mut bad).unwrap()).unwrap();
    assert!(matches!(rejected, Response::Error { .. }));
    drop(bad);
    let Response::Snapshot { tasks, .. } = request_at(&socket, &Request::Snapshot).unwrap() else {
        panic!("snapshot");
    };
    assert!(tasks.is_empty(), "invalid launch cannot create a process");

    // A hostile app name must not be interpreted as a binary path, options,
    // shell metacharacters, or a fallback to an arbitrary command.
    let mut injected = std::os::unix::net::UnixStream::connect(&socket).unwrap();
    let malformed = format!(
        r#"{{"type":"launch","workspace":"personal","app":"../../bin/sh","expected_instance":"{session_instance}"}}"#,
    );
    injected.write_all(malformed.as_bytes()).unwrap();
    injected.write_all(b"\n").unwrap();
    let response: Response =
        serde_json::from_slice(&trill_ui_core::read_frame(&mut injected).unwrap()).unwrap();
    assert!(matches!(response, Response::Error { .. }));
    drop(injected);
    let Response::Snapshot { tasks, .. } = request_at(&socket, &Request::Snapshot).unwrap() else {
        panic!("snapshot");
    };
    assert!(
        tasks.is_empty(),
        "invalid app enum must not launch arbitrary binaries"
    );

    // A stalled local socket peer cannot monopolize the single owner loop.
    // This test does not require a graphics display.
    let idle_peer = std::os::unix::net::UnixStream::connect(&socket).unwrap();
    let start = Instant::now();
    let Response::Snapshot { tasks, .. } = request_at(&socket, &Request::Snapshot).unwrap() else {
        panic!("snapshot after idle peer");
    };
    assert!(
        start.elapsed() < Duration::from_millis(1800),
        "idle peer must not starve real task/status requests"
    );
    assert!(tasks.is_empty());
    drop(idle_peer);

    // An oversize command must be rejected before any mutation and must
    // produce exactly one bounded Error response rather than a partial ACK.
    let mut too_large = std::os::unix::net::UnixStream::connect(&socket).unwrap();
    too_large
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    // Exactly one byte beyond the wire cap is sufficient. Send a single
    // write without waiting for a newline: the server must reject it before
    // parsing or spawning, even if it closes the connection immediately.
    too_large.write_all(&vec![b'x'; MAX_FRAME + 1]).unwrap();
    let oversized: Response =
        serde_json::from_slice(&trill_ui_core::read_frame(&mut too_large).unwrap()).unwrap();
    assert!(matches!(oversized, Response::Error { .. }));
    drop(too_large);
    let Response::Snapshot { tasks, .. } = request_at(&socket, &Request::Snapshot).unwrap() else {
        panic!("snapshot");
    };
    assert!(tasks.is_empty(), "oversized IPC cannot create a host child");

    // Client connection closes after launch; a new client can still see the
    // same process owner and no synthetic 'Hepta completed' status.
    let Response::Task {
        task,
        session_instance: launched_instance,
    } = request_at(
        &socket,
        &Request::Launch {
            workspace: Workspace::Research,
            app: AppKind::Notes,
            expected_instance: session_instance.clone(),
        },
    )
    .unwrap()
    else {
        panic!("expected launched task");
    };
    assert_eq!(launched_instance, session_instance);
    assert_eq!(task.id, 1);
    assert_eq!(task.hos2_revision, None);
    assert!(matches!(task.state, TaskState::Running | TaskState::Failed));

    let Response::Snapshot {
        tasks,
        session_instance: second,
        ..
    } = request_at(&socket, &Request::Snapshot).unwrap()
    else {
        panic!("expected snapshot");
    };
    assert_eq!(second, session_instance);
    assert_eq!(tasks.len(), 1);
    assert_eq!(tasks[0].id, task.id);
    assert_eq!(tasks[0].workspace, Workspace::Research);
    assert_eq!(tasks[0].execution_mode, "linux_host_process");

    // Avoid leaking a still-running GUI process when this headless test ends.
    // The app might already have exited in a no-display runner.
    let _ = request_at(
        &socket,
        &Request::Cancel {
            id: task.id,
            expected_instance: session_instance.clone(),
        },
    );
    let mut reaped = false;
    for _ in 0..100 {
        let Response::Snapshot { tasks, .. } = request_at(&socket, &Request::Snapshot).unwrap()
        else {
            panic!("expected snapshot");
        };
        if tasks[0].state.is_terminal() {
            reaped = true;
            break;
        }
        thread::sleep(Duration::from_millis(20));
    }
    assert!(
        reaped,
        "test child must be observed terminal before service teardown"
    );

    // Crash/restart of the session is NOT reattachment. A new instance has
    // no authority to reconstruct the old child's effects from reused IDs.
    harness.child.kill().unwrap();
    harness.child.wait().unwrap();
    harness.child = Command::new(env!("CARGO_BIN_EXE_trill-session"))
        .env("XDG_RUNTIME_DIR", &dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("restart host session with stale socket");
    let mut fresh = None;
    for _ in 0..100 {
        if let Ok(snapshot) = request_at(&socket, &Request::Snapshot) {
            fresh = Some(snapshot);
            break;
        }
        if let Some(status) = harness.child.try_wait().unwrap() {
            panic!("session cannot restart from stale socket: {status}");
        }
        thread::sleep(Duration::from_millis(20));
    }
    let Response::Snapshot {
        tasks,
        session_instance: new_instance,
        ..
    } = fresh.expect("new instance must bind same local socket")
    else {
        panic!("expected restart snapshot");
    };
    assert_ne!(
        session_instance, new_instance,
        "fresh owner must have a new generation"
    );
    assert!(
        tasks.is_empty(),
        "old task history must not be synthesized after session restart"
    );

    let Response::Error {
        message,
        session_instance: reply_generation,
    } = request_at(
        &socket,
        &Request::Launch {
            workspace: Workspace::Personal,
            app: AppKind::Notes,
            expected_instance: session_instance.clone(),
        },
    )
    .unwrap()
    else {
        panic!("stale launch must be rejected");
    };
    assert_eq!(reply_generation, new_instance);
    assert!(message.contains("NOT attempted"));
    let Response::Snapshot { tasks, .. } = request_at(&socket, &Request::Snapshot).unwrap() else {
        panic!("snapshot");
    };
    assert!(tasks.is_empty(), "stale launch cannot spawn a child");

    // PID/task IDs may be reused. An old-generation command must NEVER
    // cancel a new unrelated process with the same numeric task ID.
    let Response::Task { task: new_task, .. } = request_at(
        &socket,
        &Request::Launch {
            workspace: Workspace::Build,
            app: AppKind::Calculator,
            expected_instance: new_instance.clone(),
        },
    )
    .unwrap() else {
        panic!("expected new-generation task");
    };
    assert_eq!(new_task.id, task.id);
    let Response::Error {
        message,
        session_instance: reply_generation,
    } = request_at(
        &socket,
        &Request::Cancel {
            id: new_task.id,
            expected_instance: session_instance,
        },
    )
    .unwrap()
    else {
        panic!("stale cancellation must be rejected");
    };
    assert_eq!(reply_generation, new_instance);
    assert!(message.contains("NOT attempted"));
    let Response::Snapshot { tasks, .. } = request_at(&socket, &Request::Snapshot).unwrap() else {
        panic!("snapshot");
    };
    assert_eq!(tasks.len(), 1);
    assert_ne!(tasks[0].state, TaskState::CancelRequested);
    // Do not kill the session test harness while leaving its restarted
    // child unreaped. A failed/no-display GUI spawn may already be terminal.
    let _ = request_at(
        &socket,
        &Request::Cancel {
            id: new_task.id,
            expected_instance: new_instance,
        },
    );
    let mut settled = false;
    for _ in 0..100 {
        let Response::Snapshot { tasks, .. } = request_at(&socket, &Request::Snapshot).unwrap()
        else {
            panic!("snapshot");
        };
        if tasks
            .iter()
            .any(|record| record.id == new_task.id && record.state.is_terminal())
        {
            settled = true;
            break;
        }
        thread::sleep(Duration::from_millis(20));
    }
    assert!(
        settled,
        "new-generation child must be terminal before test teardown"
    );
}
