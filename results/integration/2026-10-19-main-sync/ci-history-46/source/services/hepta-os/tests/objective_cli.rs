#![cfg(all(feature = "objective-transport", target_os = "linux"))]

use serde_json::{json, Value};
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::ffi::OsStringExt;
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::PathBuf;
use std::process::{Child, Command, Output, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::{Duration, Instant};

const AGENT: &str = "22222222-2222-4222-8222-222222222222";
const RAW: &str = include_str!("fixtures/objective_ingress_original_wire_only.json");
static NEXT: AtomicU64 = AtomicU64::new(1);

struct Endpoint {
    root: PathBuf,
    socket: PathBuf,
    listener: UnixListener,
}

impl Endpoint {
    fn new() -> Self {
        let root = std::env::temp_dir().join(format!(
            "hepta-cli-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        let socket = root.join("control.sock");
        let listener = UnixListener::bind(&socket).unwrap();
        fs::set_permissions(&socket, fs::Permissions::from_mode(0o600)).unwrap();
        Self {
            root,
            socket,
            listener,
        }
    }

    fn invoke(&self, raw: &[u8], pid: u32) -> Output {
        let uid = fs::metadata(&self.socket).unwrap().uid();
        let mut child = Command::new(env!("CARGO_BIN_EXE_hepta-submit"))
            .arg(&self.socket)
            .args([AGENT, "3", &uid.to_string(), &pid.to_string(), "41"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child.stdin.take().unwrap().write_all(raw).unwrap();
        bounded_output(child)
    }
}

fn accept(listener: &UnixListener) -> UnixStream {
    listener.set_nonblocking(true).unwrap();
    let deadline = Instant::now() + Duration::from_secs(8);
    loop {
        match listener.accept() {
            Ok((socket, _)) => return socket,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                assert!(Instant::now() < deadline, "CLI never connected");
                thread::sleep(Duration::from_millis(5));
            }
            Err(error) => panic!("test listener failed: {error}"),
        }
    }
}

fn bounded_output(mut child: Child) -> Output {
    let deadline = Instant::now() + Duration::from_secs(8);
    let mut timed_out = false;
    while child.try_wait().unwrap().is_none() {
        if Instant::now() >= deadline {
            timed_out = true;
            child.kill().unwrap();
            break;
        }
        thread::sleep(Duration::from_millis(5));
    }
    let output = child.wait_with_output().unwrap();
    assert!(!timed_out, "self-owned CLI exceeded its process deadline");
    output
}

impl Drop for Endpoint {
    fn drop(&mut self) {
        fs::remove_file(&self.socket).unwrap();
        fs::remove_dir(&self.root).unwrap();
    }
}

fn document(output: &Output) -> Value {
    assert!(output.stderr.is_empty());
    assert!(output.stdout.len() < 8_192);
    assert_eq!(output.stdout.iter().filter(|b| **b == b'\n').count(), 1);
    serde_json::from_slice(&output.stdout).unwrap()
}

#[test]
fn trusted_cli_keeps_original_wire_and_projects_only_admission_metadata() {
    let endpoint = Endpoint::new();
    let listener = endpoint.listener.try_clone().unwrap();
    let owner = thread::spawn(move || {
        let mut socket = accept(&listener);
        socket
            .set_read_timeout(Some(Duration::from_secs(8)))
            .unwrap();
        let mut frame = String::new();
        BufReader::new(&mut socket).read_line(&mut frame).unwrap();
        assert!(frame.contains(RAW.trim_end_matches('\n')));
        let request: Value = serde_json::from_str(&frame).unwrap();
        assert_eq!(request["method"]["type"], "objective_start");
        assert_eq!(request["request_id"], 41);
        let response = json!({
            "schema_version": 2, "request_id": 41, "agent_id": AGENT,
            "spawn_generation": 3, "current_generation": 4,
            "payload": {"type": "objective_run", "run_id": "run.objective.1",
                "objective_digest": "1".repeat(64), "hard_constraint_digest": "2".repeat(64),
                "publication_digest": "3".repeat(64), "chain_digest": "4".repeat(64),
                "disposition": "compiled", "idempotent": false}
        });
        writeln!(socket, "{response}").unwrap();
        frame.len()
    });
    let output = endpoint.invoke(RAW.trim_end_matches('\n').as_bytes(), std::process::id());
    let sent = owner.join().unwrap();
    assert_eq!(output.status.code(), Some(0));
    let result = document(&output);
    assert_eq!(result["status"], "admitted");
    assert_eq!(result["identity"]["message_id"], "objective.message.1");
    assert_eq!(result["identity"]["run_id"], "run.objective.1");
    assert_eq!(result["bytes_written"], sent);
    assert_eq!(result["request_frame_bytes"], sent);
    assert_eq!(result["receipt"]["disposition"], "compiled");
    assert_eq!(result["receipt"]["response_generation"], 4);
    let text = String::from_utf8(output.stdout).unwrap();
    assert!(!text.contains("signature_hex"));
    assert!(!text.contains("source_envelope_json"));
    assert!(!text.contains(endpoint.socket.to_str().unwrap()));
}

#[test]
fn lost_owner_reply_retains_unknown_and_does_not_reconnect() {
    let endpoint = Endpoint::new();
    let listener = endpoint.listener.try_clone().unwrap();
    let owner = thread::spawn(move || {
        let mut socket = accept(&listener);
        socket
            .set_read_timeout(Some(Duration::from_secs(8)))
            .unwrap();
        let mut frame = String::new();
        BufReader::new(&mut socket).read_line(&mut frame).unwrap();
        frame.len()
        // Drop the owner connection after receiving the complete request.
    });
    let output = endpoint.invoke(RAW.trim_end_matches('\n').as_bytes(), std::process::id());
    let sent = owner.join().unwrap();
    assert_eq!(output.status.code(), Some(12));
    let result = document(&output);
    assert_eq!(result["status"], "submit_unknown");
    assert_eq!(result["identity"]["run_id"], "run.objective.1");
    assert_eq!(result["bytes_written"], sent);
    assert!(sent > 0);
    endpoint.listener.set_nonblocking(true).unwrap();
    assert_eq!(
        endpoint.listener.accept().unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock
    );
}

#[test]
fn invalid_input_is_not_sent_and_never_echoes_the_source() {
    let endpoint = Endpoint::new();
    let output = endpoint.invoke(b"{private-invalid-source", std::process::id());
    assert_eq!(output.status.code(), Some(10));
    assert_eq!(
        document(&output),
        json!({"schema_version": 1, "status": "not_sent",
            "issue": "objective_framing_profile", "bytes_written": 0})
    );
    endpoint.listener.set_nonblocking(true).unwrap();
    assert_eq!(
        endpoint.listener.accept().unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock
    );
}

#[test]
fn non_utf8_argument_is_a_finite_rejection_without_echo_or_connection() {
    let endpoint = Endpoint::new();
    let child = Command::new(env!("CARGO_BIN_EXE_hepta-submit"))
        .arg(std::ffi::OsString::from_vec(
            b"private-endpoint-\xff".to_vec(),
        ))
        .args([AGENT, "3", "0", "1", "41"])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let output = bounded_output(child);
    assert_eq!(output.status.code(), Some(10));
    assert_eq!(
        document(&output),
        json!({"schema_version": 1, "status": "not_sent",
            "issue": "objective_invalid_arguments", "bytes_written": 0})
    );
    endpoint.listener.set_nonblocking(true).unwrap();
    assert_eq!(
        endpoint.listener.accept().unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock
    );
}

#[test]
fn wrong_trusted_peer_pid_sends_no_request_bytes() {
    let endpoint = Endpoint::new();
    let listener = endpoint.listener.try_clone().unwrap();
    let owner = thread::spawn(move || {
        let mut socket = accept(&listener);
        socket
            .set_read_timeout(Some(Duration::from_secs(8)))
            .unwrap();
        let mut bytes = Vec::new();
        socket.read_to_end(&mut bytes).unwrap();
        bytes
    });
    let output = endpoint.invoke(
        RAW.trim_end_matches('\n').as_bytes(),
        std::process::id() + 1,
    );
    assert!(owner.join().unwrap().is_empty());
    assert_eq!(output.status.code(), Some(10));
    let result = document(&output);
    assert_eq!(result["status"], "not_sent");
    assert_eq!(result["issue"], "objective_peer_denied");
    assert_eq!(result["bytes_written"], 0);
}

#[test]
fn closed_stdout_reports_lost_result_after_the_single_owner_attempt() {
    let endpoint = Endpoint::new();
    let listener = endpoint.listener.try_clone().unwrap();
    let owner = thread::spawn(move || {
        let mut socket = accept(&listener);
        socket
            .set_read_timeout(Some(Duration::from_secs(8)))
            .unwrap();
        let mut frame = String::new();
        BufReader::new(&mut socket).read_line(&mut frame).unwrap();
        let response = json!({
            "schema_version": 2, "request_id": 41, "agent_id": AGENT,
            "spawn_generation": 3, "current_generation": 4,
            "payload": {"type": "objective_run", "run_id": "run.objective.1",
                "objective_digest": "1".repeat(64), "hard_constraint_digest": "2".repeat(64),
                "publication_digest": "3".repeat(64), "chain_digest": "4".repeat(64),
                "disposition": "compiled", "idempotent": false}
        });
        writeln!(socket, "{response}").unwrap();
        frame
    });
    let uid = fs::metadata(&endpoint.socket).unwrap().uid();
    let mut child = Command::new(env!("CARGO_BIN_EXE_hepta-submit"))
        .arg(&endpoint.socket)
        .args([
            AGENT,
            "3",
            &uid.to_string(),
            &std::process::id().to_string(),
            "41",
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    drop(child.stdout.take());
    child
        .stdin
        .take()
        .unwrap()
        .write_all(RAW.trim_end_matches('\n').as_bytes())
        .unwrap();
    let output = bounded_output(child);
    let frame = owner.join().unwrap();
    assert!(frame.contains(RAW.trim_end_matches('\n')));
    assert_eq!(output.status.code(), Some(74));
    assert!(output.stderr.is_empty());
    assert!(output.stdout.is_empty());
    assert_eq!(
        endpoint.listener.accept().unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock
    );
}
