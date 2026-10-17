//! Real Linux UDS I/O against scripted fixtures, not a running Hepta daemon.
//! Run tests/integration/hepta/check_upstream_contract.py for source binding and
//! source-derived serialization conformance of these v2 fixtures.

#![cfg(target_os = "linux")]

use hepta_os_observer::{
    EndpointConfig, ObserverClient, ObserverError, MAX_FRAME_BYTES, POLL_TIMEOUT_MS,
    READ_ONLY_METHODS,
};
use serde_json::{json, Value};
use std::fs::{self, DirBuilder};
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::fs::{symlink, DirBuilderExt, MetadataExt, PermissionsExt};
use std::os::unix::net::UnixListener;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::{Duration, Instant};

const AGENT: &str = "11111111-1111-4111-8111-111111111111";
const GENERATION: u64 = 7;
static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(1);

fn fixture(name: &str) -> Value {
    let fixtures: Value = serde_json::from_str(include_str!("fixtures/agentd_v2_payloads.json"))
        .expect("checked fixture JSON");
    let mut value = fixtures[name].clone();
    if name == "health" {
        value["process_id"] = json!(std::process::id());
    }
    value
}

fn envelope(request_id: u64, payload: Value) -> Value {
    json!({
        "schema_version": 2, "request_id": request_id, "agent_id": AGENT,
        "spawn_generation": GENERATION, "current_generation": GENERATION + 1,
        "payload": payload
    })
}

enum Reply {
    Payload(Value),
    Envelope(Value),
    Raw(Vec<u8>),
    Stall,
}

struct Step {
    method: Value,
    reply: Reply,
}

impl Step {
    fn new(method: Value, payload: Value) -> Self {
        Self {
            method,
            reply: Reply::Payload(payload),
        }
    }
}

struct SocketFixture {
    directory: PathBuf,
    socket: PathBuf,
    listener: Option<UnixListener>,
    uid: u32,
}

impl SocketFixture {
    fn new() -> Self {
        let serial = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
        let directory = PathBuf::from(format!(
            "/tmp/hepta-observer-{}-{serial}",
            std::process::id()
        ));
        DirBuilder::new()
            .mode(0o700)
            .create(&directory)
            .expect("private fixture directory");
        let uid = fs::metadata(&directory).expect("metadata").uid();
        let socket = directory.join("control.sock");
        let listener = UnixListener::bind(&socket).expect("bind actual Linux UDS");
        fs::set_permissions(&socket, fs::Permissions::from_mode(0o600)).expect("private UDS");
        Self {
            directory,
            socket,
            listener: Some(listener),
            uid,
        }
    }

    fn config(&self) -> EndpointConfig {
        EndpointConfig::new(self.socket.clone(), AGENT.to_owned(), GENERATION, self.uid)
            .expect("trusted fixture config")
    }

    fn client(&self) -> ObserverClient {
        ObserverClient::new(self.config()).expect("client runtime")
    }

    fn serve(&mut self, steps: Vec<Step>) -> thread::JoinHandle<()> {
        let listener = self.listener.take().expect("single fixture server");
        listener.set_nonblocking(true).expect("bounded accept");
        thread::spawn(move || {
            for (index, step) in steps.into_iter().enumerate() {
                let deadline = Instant::now() + Duration::from_secs(8);
                let mut stream = loop {
                    match listener.accept() {
                        Ok((stream, _)) => break stream,
                        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                            assert!(
                                Instant::now() < deadline,
                                "expected fixture connection missing"
                            );
                            thread::sleep(Duration::from_millis(2));
                        }
                        Err(error) => panic!("fixture accept: {error}"),
                    }
                };
                stream
                    .set_read_timeout(Some(Duration::from_secs(2)))
                    .expect("read bound");
                let mut reader = BufReader::new(stream.try_clone().expect("clone fixture socket"))
                    .take(MAX_FRAME_BYTES + 1);
                let mut frame = Vec::new();
                reader
                    .read_until(b'\n', &mut frame)
                    .expect("actual request frame");
                assert!(frame.ends_with(b"\n") && frame.len() as u64 <= MAX_FRAME_BYTES);
                let request: Value = serde_json::from_slice(&frame).expect("request JSON");
                assert_eq!(
                    request,
                    json!({
                        "schema_version": 2, "request_id": index as u64 + 1,
                        "spawn_generation": GENERATION, "method": step.method
                    })
                );
                assert!(READ_ONLY_METHODS.contains(&request["method"]["type"].as_str().unwrap()));
                let mut bytes = match step.reply {
                    Reply::Payload(payload) => {
                        serde_json::to_vec(&envelope(index as u64 + 1, payload)).unwrap()
                    }
                    Reply::Envelope(response) => serde_json::to_vec(&response).unwrap(),
                    Reply::Raw(bytes) => {
                        // Oversize replies may be closed before the write finishes.
                        let _ = stream.write_all(&bytes);
                        continue;
                    }
                    Reply::Stall => {
                        thread::sleep(Duration::from_millis(POLL_TIMEOUT_MS + 300));
                        continue;
                    }
                };
                bytes.push(b'\n');
                stream.write_all(&bytes).expect("fixture reply");
            }
        })
    }
}

impl Drop for SocketFixture {
    fn drop(&mut self) {
        // Only this test's freshly-created private fixture directory.
        let _ = fs::remove_dir_all(&self.directory);
    }
}

fn health() -> Step {
    Step::new(json!({"type": "health"}), fixture("health"))
}
fn caps() -> Step {
    Step::new(json!({"type": "capabilities"}), fixture("capabilities"))
}
fn events(after: u64, limit: u16, payload: Value) -> Step {
    Step::new(
        json!({"type": "events", "after_cursor": after, "limit": limit}),
        payload,
    )
}

fn assert_first_error(reply: Reply, expected: ObserverError) {
    let mut socket = SocketFixture::new();
    let server = socket.serve(vec![Step {
        method: json!({"type": "health"}),
        reply,
    }]);
    assert_eq!(socket.client().poll(0, 16), Err(expected));
    server.join().expect("fixture server");
}

#[test]
fn actual_socket_projects_only_bounded_safe_observations_and_allows_no_effect_methods() {
    let mut socket = SocketFixture::new();
    let server = socket.serve(vec![
        health(),
        caps(),
        events(0, 16, fixture("events")),
        health(),
    ]);
    let observed = socket
        .client()
        .poll(0, 16)
        .expect("real socket fixture roundtrip");
    server.join().expect("fixture server");
    assert!(observed.health.ready);
    assert_eq!(observed.health.process_id, std::process::id());
    assert_eq!(observed.current_generation, GENERATION + 1);
    assert_eq!(observed.events.len(), 3);
    assert_eq!(observed.next_cursor, 3);
    assert_eq!(observed.events[1].generation, Some(GENERATION + 1));
    assert_eq!(observed.capabilities[0].id, "fixture:future");
    let encoded = serde_json::to_string(&observed).unwrap();
    for excluded in [
        "private-fixture",
        "socket_path",
        "workspace",
        "home_root",
        "run_root",
        "signature_hex",
    ] {
        assert!(
            !encoded.contains(excluded),
            "sensitive fields must not be projected"
        );
    }
}

#[test]
fn event_gap_and_pagination_never_skip_unreturned_events() {
    let page_one = json!({"type":"events", "events":[{"cursor":4,"kind":{"type":"bootstrapped"}}],
        "gap":true,"next_cursor":4,"latest_cursor":5});
    let page_two = json!({"type":"events", "events":[{"cursor":5,"kind":{"type":"app_server_ready"}}],
        "gap":false,"next_cursor":5,"latest_cursor":5});
    let empty = json!({"type":"events", "events":[],"gap":false,"next_cursor":5,"latest_cursor":5});
    let mut socket = SocketFixture::new();
    let server = socket.serve(vec![
        health(),
        caps(),
        events(0, 1, page_one),
        health(),
        health(),
        caps(),
        events(4, 16, page_two),
        health(),
        health(),
        caps(),
        events(5, 16, empty),
        health(),
    ]);
    let mut client = socket.client();
    let first = client.poll(0, 1).expect("retained suffix");
    assert!(first.history_gap);
    assert_eq!(first.next_cursor, 4);
    let next = client
        .poll(first.next_cursor, 16)
        .expect("next complete page");
    assert!(!next.history_gap);
    assert_eq!(next.events[0].cursor, 5);
    let last = client.poll(next.next_cursor, 16).expect("empty tail");
    assert!(last.events.is_empty());
    assert_eq!(last.next_cursor, 5);
    server.join().expect("fixture server");
}

#[test]
fn historical_run_state_is_read_only_and_does_not_disclose_owner_inputs() {
    let mut socket = SocketFixture::new();
    let server = socket.serve(vec![
        health(),
        Step::new(
            json!({"type":"run_status","run_id":"fixture:run-1"}),
            fixture("run_status"),
        ),
        health(),
        health(),
        Step::new(
            json!({"type":"run_status","run_id":"missing"}),
            json!({"type":"run_status","run":null}),
        ),
        health(),
    ]);
    let mut client = socket.client();
    let run = client
        .run_status("fixture:run-1")
        .expect("owner run snapshot")
        .expect("known run");
    assert_eq!(run.phase, "indeterminate");
    assert_eq!(run.generation, 6, "historical run identity is preserved");
    assert!(!run.terminal_observed);
    let encoded = serde_json::to_string(&run).unwrap();
    for private in [
        "cancel_reason",
        "fence_digest",
        "context_digest",
        "private fixture",
    ] {
        assert!(!encoded.contains(private));
    }
    assert_eq!(client.run_status("missing").unwrap(), None);
    server.join().expect("fixture server");
}

#[test]
fn response_correlation_version_identity_and_generation_are_mandatory() {
    for (field, value, error) in [
        ("schema_version", json!(3), ObserverError::ProtocolMismatch),
        ("request_id", json!(99), ObserverError::ProtocolMismatch),
        (
            "agent_id",
            json!("22222222-2222-4222-8222-222222222222"),
            ObserverError::ProtocolMismatch,
        ),
        (
            "spawn_generation",
            json!(8),
            ObserverError::ProtocolMismatch,
        ),
        (
            "current_generation",
            json!(10),
            ObserverError::GenerationFenced,
        ),
        (
            "extra",
            json!("/private-leak"),
            ObserverError::ProtocolMismatch,
        ),
    ] {
        let mut response = envelope(1, fixture("health"));
        response[field] = value;
        assert_first_error(Reply::Envelope(response), error);
    }
}

#[test]
fn peer_pid_health_invariants_and_unexpected_privileged_payload_fail_closed() {
    let mut wrong_pid = fixture("health");
    wrong_pid["process_id"] = json!(std::process::id() + 1);
    assert_first_error(Reply::Payload(wrong_pid), ObserverError::PeerDenied);
    let mut fenced = fixture("health");
    fenced["fenced"] = json!(true);
    assert_first_error(Reply::Payload(fenced), ObserverError::GenerationFenced);
    let mut stopped = fixture("health");
    stopped["lifecycle"] = json!("stopped");
    assert_first_error(Reply::Payload(stopped), ObserverError::GenerationFenced);
    for (field, value) in [("promotion_ready", json!(false)), ("extra", json!(true))] {
        let mut invalid = fixture("health");
        invalid[field] = value;
        assert_first_error(Reply::Payload(invalid), ObserverError::ProtocolMismatch);
    }
    assert_first_error(
        Reply::Payload(
            json!({"type":"session_ingress","socket_path":"/privileged.sock",
        "transport":"codex_app_server_websocket_over_uds"}),
        ),
        ObserverError::ProtocolMismatch,
    );
}

#[test]
fn owner_errors_and_overload_are_redacted_and_do_not_enable_retry_or_submission() {
    assert_first_error(
        Reply::Payload(json!({"type":"error","code":"request_rejected",
        "message":"/private-owner/config token=never-print-this"})),
        ObserverError::OwnerRejected,
    );
    assert_eq!(ObserverError::OwnerRejected.to_string(), "owner_rejected");
    assert_first_error(
        Reply::Raw(b"{\"type\":\"overloaded\",\"retry_after_ms\":50}\n".to_vec()),
        ObserverError::Overloaded,
    );
    assert_first_error(
        Reply::Raw(b"{\"type\":\"overloaded\",\"retry_after_ms\":1}\n".to_vec()),
        ObserverError::ProtocolMismatch,
    );
}

#[test]
fn bounded_frame_and_newline_requirements_are_enforced_on_the_socket() {
    for bytes in [
        Vec::new(),
        b"{}".to_vec(),
        b"{broken}\n".to_vec(),
        vec![b'x'; MAX_FRAME_BYTES as usize + 1],
    ] {
        assert_first_error(Reply::Raw(bytes), ObserverError::ProtocolMismatch);
    }
}

#[test]
fn malformed_capability_sets_and_unknown_fields_are_rejected() {
    let mut cases = Vec::new();
    let mut invalid = fixture("capabilities");
    invalid["schema_version"] = json!(2);
    cases.push(invalid);
    for change in [
        json!({"id":"bad/name","major":1,"minor":0}),
        json!({"id":"ok","major":0,"minor":0}),
        json!({"id":"ok","major":1,"minor":0,"authority":"root"}),
    ] {
        let mut invalid = fixture("capabilities");
        invalid["capabilities"] = json!([change]);
        cases.push(invalid);
    }
    let duplicate = json!({"id":"run.lifecycle","major":1,"minor":1});
    let mut invalid = fixture("capabilities");
    invalid["capabilities"] = json!([duplicate, duplicate]);
    cases.push(invalid);
    let mut oversized = fixture("capabilities");
    oversized["capabilities"] = json!((0..65)
        .map(|i| json!({"id":format!("cap.{i}"),"major":1,"minor":0}))
        .collect::<Vec<_>>());
    cases.push(oversized);
    for payload in cases {
        let mut socket = SocketFixture::new();
        let server = socket.serve(vec![
            health(),
            Step::new(json!({"type":"capabilities"}), payload),
        ]);
        assert_eq!(
            socket.client().poll(0, 16),
            Err(ObserverError::ProtocolMismatch)
        );
        server.join().expect("fixture server");
    }
}

#[test]
fn event_integrity_gap_limits_and_cursor_ahead_are_checked() {
    let mut cases = Vec::new();
    for (field, value) in [
        ("next_cursor", json!(2)),
        ("latest_cursor", json!(2)),
        ("gap", json!(true)),
        ("extra", json!(true)),
    ] {
        let mut invalid = fixture("events");
        invalid[field] = value;
        cases.push(invalid);
    }
    let mut duplicate = fixture("events");
    duplicate["events"][1]["cursor"] = json!(1);
    cases.push(duplicate);
    let mut unknown = fixture("events");
    unknown["events"][0]["kind"]["type"] = json!("objective_completed");
    cases.push(unknown);
    let mut extra = fixture("events");
    extra["events"][0]["kind"]["unexpected"] = json!(true);
    cases.push(extra);
    let mut empty_skip = fixture("events");
    empty_skip["events"] = json!([]);
    cases.push(empty_skip);
    for payload in cases {
        let mut socket = SocketFixture::new();
        let server = socket.serve(vec![health(), caps(), events(0, 16, payload)]);
        assert_eq!(
            socket.client().poll(0, 16),
            Err(ObserverError::ProtocolMismatch)
        );
        server.join().expect("fixture server");
    }
    let mut socket = SocketFixture::new();
    let server = socket.serve(vec![
        health(),
        caps(),
        events(
            9,
            16,
            json!({"type":"events","events":[],"gap":false,"next_cursor":9,"latest_cursor":3}),
        ),
    ]);
    assert_eq!(
        socket.client().poll(9, 16),
        Err(ObserverError::EventCursorAhead)
    );
    server.join().expect("fixture server");
}

#[test]
fn last_health_fence_discards_the_whole_partial_poll() {
    let mut changed = envelope(4, fixture("health"));
    changed["current_generation"] = json!(10);
    let mut socket = SocketFixture::new();
    let server = socket.serve(vec![
        health(),
        caps(),
        events(0, 16, fixture("events")),
        Step {
            method: json!({"type":"health"}),
            reply: Reply::Envelope(changed),
        },
    ]);
    assert_eq!(
        socket.client().poll(0, 16),
        Err(ObserverError::GenerationFenced)
    );
    server.join().expect("fixture server");
}

#[test]
fn endpoint_identity_private_directory_socket_modes_and_symlinks_are_enforced() {
    let socket = SocketFixture::new();
    let mut client = socket.client();
    assert_eq!(client.poll(0, 0), Err(ObserverError::InvalidRequest));
    assert_eq!(client.poll(0, 257), Err(ObserverError::InvalidRequest));
    assert_eq!(
        client.run_status("../untrusted"),
        Err(ObserverError::InvalidRequest)
    );
    for path in [
        "relative.sock",
        "/tmp/../a.sock",
        "/tmp//a.sock",
        "/tmp/./a.sock",
        "/tmp/",
    ] {
        assert!(matches!(
            EndpointConfig::new(
                PathBuf::from(path),
                AGENT.to_owned(),
                GENERATION,
                socket.uid
            ),
            Err(ObserverError::InvalidEndpoint)
        ));
    }
    for agent in [
        "not-an-agent",
        "11111111-1111-0111-8111-111111111111",
        "11111111-1111-4111-7111-111111111111",
    ] {
        assert!(matches!(
            EndpointConfig::new(
                socket.socket.clone(),
                agent.to_owned(),
                GENERATION,
                socket.uid
            ),
            Err(ObserverError::InvalidEndpoint)
        ));
    }
    let wrong_uid = EndpointConfig::new(
        socket.socket.clone(),
        AGENT.to_owned(),
        GENERATION,
        socket.uid.checked_add(1).unwrap(),
    )
    .unwrap();
    assert_eq!(
        ObserverClient::new(wrong_uid).unwrap().poll(0, 16),
        Err(ObserverError::PeerDenied)
    );
    fs::set_permissions(&socket.socket, fs::Permissions::from_mode(0o666)).unwrap();
    assert_eq!(client.poll(0, 16), Err(ObserverError::PeerDenied));
    fs::set_permissions(&socket.socket, fs::Permissions::from_mode(0o600)).unwrap();
    fs::set_permissions(&socket.directory, fs::Permissions::from_mode(0o755)).unwrap();
    assert_eq!(client.poll(0, 16), Err(ObserverError::PeerDenied));
    fs::set_permissions(&socket.directory, fs::Permissions::from_mode(0o700)).unwrap();
    let link = socket.directory.join("link.sock");
    symlink(&socket.socket, &link).unwrap();
    let linked = EndpointConfig::new(link, AGENT.to_owned(), GENERATION, socket.uid).unwrap();
    assert_eq!(
        ObserverClient::new(linked).unwrap().poll(0, 16),
        Err(ObserverError::PeerDenied)
    );
}

#[test]
fn missing_endpoint_fails_unavailable_without_creating_or_discovering_anything() {
    let socket = SocketFixture::new();
    let missing = socket.directory.join("absent.sock");
    let endpoint =
        EndpointConfig::new(missing.clone(), AGENT.to_owned(), GENERATION, socket.uid).unwrap();
    assert_eq!(
        ObserverClient::new(endpoint).unwrap().poll(0, 16),
        Err(ObserverError::Unavailable)
    );
    assert!(!missing.exists());
}

#[test]
fn stalled_socket_is_bounded_by_one_total_poll_deadline() {
    let mut socket = SocketFixture::new();
    let server = socket.serve(vec![Step {
        method: json!({"type":"health"}),
        reply: Reply::Stall,
    }]);
    let start = Instant::now();
    assert_eq!(socket.client().poll(0, 16), Err(ObserverError::Timeout));
    assert!(start.elapsed() < Duration::from_millis(POLL_TIMEOUT_MS + 1500));
    server.join().expect("fixture server");
}

#[test]
fn upstream_running_uses_spawn_plus_one_and_draining_uses_spawn_plus_two() {
    // Fixed upstream fleet/model.rs::successor increments every lifecycle
    // transition; agentd/state.rs accepts Starting/+0, Running/+1, Draining/+2.
    // The previous observer rejected the first real promoted Running response.
    let mut steps = Vec::new();
    for (index, lifecycle) in ["starting", "running", "draining"].into_iter().enumerate() {
        let current = GENERATION + index as u64;
        let cursor = index as u64 + 1;
        let mut stage_health = fixture("health");
        stage_health["lifecycle"] = json!(lifecycle);
        stage_health["ready"] = json!(lifecycle == "running");
        stage_health["promotion_ready"] = json!(lifecycle != "draining");
        let page = json!({"type":"events", "events":[{"cursor":cursor,
            "kind":{"type":"lifecycle","lifecycle":lifecycle,"generation":current}}],
            "gap":false,"next_cursor":cursor,"latest_cursor":cursor});
        for (method, payload) in [
            (json!({"type":"health"}), stage_health.clone()),
            (json!({"type":"capabilities"}), fixture("capabilities")),
            (
                json!({"type":"events","after_cursor":cursor-1,"limit":16}),
                page,
            ),
            (json!({"type":"health"}), stage_health),
        ] {
            let mut response = envelope(steps.len() as u64 + 1, payload);
            response["current_generation"] = json!(current);
            steps.push(Step {
                method,
                reply: Reply::Envelope(response),
            });
        }
    }
    let mut socket = SocketFixture::new();
    let server = socket.serve(steps);
    let mut client = socket.client();
    for (index, lifecycle) in ["starting", "running", "draining"].into_iter().enumerate() {
        let observation = client
            .poll(index as u64, 16)
            .expect("upstream-valid lifecycle cut");
        assert_eq!(observation.spawn_generation, GENERATION);
        assert_eq!(observation.current_generation, GENERATION + index as u64);
        assert_eq!(observation.health.lifecycle, lifecycle);
        assert_eq!(
            observation.events[0].generation,
            Some(GENERATION + index as u64)
        );
    }
    server.join().expect("fixture server");
}

fn generation_step(id: u64, method: Value, payload: Value, current: u64) -> Step {
    let mut response = envelope(id, payload);
    response["current_generation"] = json!(current);
    Step {
        method,
        reply: Reply::Envelope(response),
    }
}

fn lifecycle_health(lifecycle: &str) -> Value {
    let mut value = fixture("health");
    value["lifecycle"] = json!(lifecycle);
    value["ready"] = json!(lifecycle == "running");
    value["promotion_ready"] = json!(lifecycle != "draining");
    value
}

#[test]
fn promotion_inside_a_poll_preserves_prior_phase_events_and_final_current() {
    let mut page = fixture("events");
    page["events"][0]["kind"] =
        json!({"type":"lifecycle", "lifecycle":"starting", "generation":GENERATION});
    let mut socket = SocketFixture::new();
    let server = socket.serve(vec![
        generation_step(
            1,
            json!({"type":"health"}),
            lifecycle_health("starting"),
            GENERATION,
        ),
        caps(),
        events(0, 16, page),
        generation_step(
            4,
            json!({"type":"health"}),
            lifecycle_health("draining"),
            GENERATION + 2,
        ),
    ]);
    let observed = socket
        .client()
        .poll(0, 16)
        .expect("monotonic promotion inside a non-atomic cut");
    assert_eq!(observed.current_generation, GENERATION + 2);
    assert_eq!(observed.health.lifecycle, "draining");
    assert_eq!(observed.events[0].generation, Some(GENERATION));
    assert_eq!(observed.events[1].generation, Some(GENERATION + 1));
    server.join().expect("fixture server");
}

#[test]
fn valid_offsets_do_not_allow_wrong_phase_future_events_or_rollbacks() {
    for lifecycle in ["starting", "draining", "failed"] {
        assert_first_error(
            Reply::Payload(lifecycle_health(lifecycle)),
            ObserverError::GenerationFenced,
        );
    }
    for (lifecycle, generation) in [
        ("running", GENERATION),
        ("draining", GENERATION + 2),
        ("stopped", GENERATION),
    ] {
        let mut page = fixture("events");
        page["events"][1]["kind"] =
            json!({"type":"lifecycle", "lifecycle":lifecycle, "generation":generation});
        let mut socket = SocketFixture::new();
        let server = socket.serve(vec![health(), caps(), events(0, 16, page)]);
        assert_eq!(
            socket.client().poll(0, 16),
            Err(ObserverError::GenerationFenced)
        );
        server.join().expect("fixture server");
    }
    // Each response is individually a valid phase, but the same process
    // cannot move backwards during one cut or after a successful prior cut.
    let mut socket = SocketFixture::new();
    let server = socket.serve(vec![
        health(),
        generation_step(
            2,
            json!({"type":"capabilities"}),
            fixture("capabilities"),
            GENERATION,
        ),
    ]);
    assert_eq!(
        socket.client().poll(0, 16),
        Err(ObserverError::GenerationFenced)
    );
    server.join().expect("fixture server");

    let mut socket = SocketFixture::new();
    let server = socket.serve(vec![
        health(),
        caps(),
        events(0, 16, fixture("events")),
        health(),
        generation_step(
            5,
            json!({"type":"health"}),
            lifecycle_health("starting"),
            GENERATION,
        ),
    ]);
    let mut client = socket.client();
    client.poll(0, 16).expect("first running cut");
    assert_eq!(client.poll(3, 16), Err(ObserverError::GenerationFenced));
    server.join().expect("fixture server");
}
