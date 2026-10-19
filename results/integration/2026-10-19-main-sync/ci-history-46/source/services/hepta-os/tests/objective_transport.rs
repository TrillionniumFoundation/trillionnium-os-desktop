//! Real disposable Linux UDS I/O, with scripted protocol responses only.
//! No original daemon, issuer, signing key, model, objective execution or device
//! is used. The all-zero signature and expired envelope are copied from the
//! fixed original protocol's own wire-only fixture; they are not credentials.

#![cfg(all(feature = "objective-transport", target_os = "linux"))]

use hepta_os_observer::objective::{
    AdmissionDisposition, EnvelopeError, ObjectiveTransport, PrePublicationRefusal,
    ProvidedObjective, SubmissionAttempt, SubmissionIssue, SubmissionStatus,
};
use hepta_os_observer::{EndpointConfig, ObserverError, MAX_FRAME_BYTES, POLL_TIMEOUT_MS};
use serde_json::{json, Value};
use std::fs::{self, DirBuilder};
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::fs::{symlink, DirBuilderExt, MetadataExt, PermissionsExt};
use std::os::unix::net::UnixListener;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

const AGENT: &str = "11111111-1111-4111-8111-111111111111";
const SPAWN: u64 = 3;
const REQUEST_ID: u64 = 41;
const RUN_ID: &str = "run.objective.1";
static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(1);

fn original_fixture() -> String {
    include_str!("fixtures/objective_ingress_original_wire_only.json")
        .trim_end_matches('\n')
        .to_owned()
}

fn fixture_value() -> Value {
    serde_json::from_str(&original_fixture()).unwrap()
}

fn encoded(value: &Value) -> String {
    serde_json::to_string(value).unwrap()
}

fn request_frame(raw: &str) -> Vec<u8> {
    let mut frame = format!(
        "{{\"schema_version\":2,\"request_id\":{REQUEST_ID},\"spawn_generation\":{SPAWN},\"method\":{{\"type\":\"objective_start\",\"request\":"
    )
    .into_bytes();
    frame.extend_from_slice(raw.as_bytes());
    frame.extend_from_slice(b"}}\n");
    frame
}

fn admitted() -> Value {
    json!({
        "type":"objective_run", "run_id":RUN_ID,
        "objective_digest":"1".repeat(64), "hard_constraint_digest":"2".repeat(64),
        "publication_digest":"3".repeat(64), "chain_digest":"4".repeat(64),
        "disposition":"compiled", "idempotent":false
    })
}

fn response(payload: Value) -> Value {
    json!({
        "schema_version":2, "request_id":REQUEST_ID, "agent_id":AGENT,
        "spawn_generation":SPAWN, "current_generation":SPAWN+1, "payload":payload
    })
}

fn response_frame(value: Value) -> Vec<u8> {
    let mut bytes = serde_json::to_vec(&value).unwrap();
    bytes.push(b'\n');
    bytes
}

enum Behavior {
    Reply(Vec<u8>),
    CloseAfterFrame,
    CloseAfterPrefix,
    StallAfterFrame,
    ExpectNoRequestBytes,
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
        let directory = PathBuf::from(format!("/tmp/hp-objective-{}-{serial}", std::process::id()));
        DirBuilder::new().mode(0o700).create(&directory).unwrap();
        let socket = directory.join("control.sock");
        let listener = UnixListener::bind(&socket).unwrap();
        listener.set_nonblocking(true).unwrap();
        fs::set_permissions(&socket, fs::Permissions::from_mode(0o600)).unwrap();
        let uid = fs::metadata(&directory).unwrap().uid();
        Self {
            directory,
            socket,
            listener: Some(listener),
            uid,
        }
    }

    fn config(&self) -> EndpointConfig {
        EndpointConfig::new(self.socket.clone(), AGENT.to_owned(), SPAWN, self.uid).unwrap()
    }

    fn transport(&self) -> ObjectiveTransport {
        ObjectiveTransport::new(self.config(), std::process::id(), REQUEST_ID).unwrap()
    }

    fn assert_no_connections(&self) {
        assert!(matches!(
            self.listener.as_ref().unwrap().accept(),
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock
        ));
    }

    fn serve(
        &mut self,
        raw: &str,
        behavior: Behavior,
    ) -> (mpsc::Sender<()>, thread::JoinHandle<Vec<u8>>) {
        let listener = self.listener.take().unwrap();
        let expected = request_frame(raw);
        let (done, client_finished) = mpsc::channel();
        let worker = thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(8);
            let (mut stream, _) = loop {
                match listener.accept() {
                    Ok(connection) => break connection,
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
                .set_read_timeout(Some(Duration::from_secs(8)))
                .unwrap();
            stream
                .set_write_timeout(Some(Duration::from_secs(2)))
                .unwrap();
            let mut reader = BufReader::new(stream.try_clone().unwrap());
            let mut received = Vec::new();
            match behavior {
                Behavior::ExpectNoRequestBytes => {
                    let mut byte = [0];
                    assert_eq!(
                        reader.read(&mut byte).unwrap(),
                        0,
                        "peer check must precede writes"
                    );
                }
                Behavior::CloseAfterPrefix => {
                    received.resize(1, 0);
                    reader.read_exact(&mut received).unwrap();
                    assert_eq!(received[0], expected[0]);
                }
                _ => {
                    let count = (&mut reader)
                        .take(MAX_FRAME_BYTES + 1)
                        .read_until(b'\n', &mut received)
                        .unwrap();
                    assert!(count as u64 <= MAX_FRAME_BYTES && received.ends_with(b"\n"));
                    assert_eq!(
                        received, expected,
                        "outgoing raw issuer envelope must be unchanged"
                    );
                    assert!(
                        reader.buffer().is_empty(),
                        "only one request frame is permitted"
                    );
                }
            }
            let stalled = matches!(behavior, Behavior::StallAfterFrame);
            match behavior {
                Behavior::Reply(bytes) => {
                    // Malformed/oversized replies may cause the client to close early.
                    let _ = stream.write_all(&bytes);
                }
                Behavior::StallAfterFrame => {
                    // No sleeps as evidence: the peer has verified a complete
                    // real request and sends nothing until the client returns.
                    client_finished
                        .recv_timeout(Duration::from_secs(8))
                        .unwrap();
                    let mut byte = [0];
                    assert_eq!(reader.read(&mut byte).unwrap(), 0);
                }
                _ => {}
            }
            drop(reader);
            drop(stream);
            if !stalled {
                client_finished
                    .recv_timeout(Duration::from_secs(8))
                    .unwrap();
            }
            // The facade has returned. Any reconnect/retry would now be in the
            // listener backlog; keep the listener open until this exact cut.
            assert!(
                matches!(listener.accept(), Err(error)
                if error.kind() == std::io::ErrorKind::WouldBlock),
                "no second connection"
            );
            received
        });
        (done, worker)
    }
}

impl Drop for SocketFixture {
    fn drop(&mut self) {
        // Only this test's newly-created private directory, never original state.
        let _ = fs::remove_dir_all(&self.directory);
    }
}

fn perform(raw: String, behavior: Behavior) -> (SubmissionAttempt, Vec<u8>) {
    let mut socket = SocketFixture::new();
    let transport = socket.transport();
    let (done, server) = socket.serve(&raw, behavior);
    let input = ProvidedObjective::parse_json(raw.clone()).unwrap();
    let result = transport.submit_once(input);
    done.send(()).unwrap();
    let captured = server.join().expect("bounded disposable fixture server");
    assert_retained(&result, &raw);
    (result, captured)
}

fn assert_retained(attempt: &SubmissionAttempt, raw: &str) {
    let supplied = ProvidedObjective::parse_json(raw.to_owned()).unwrap();
    assert!(attempt.matches_original_json(raw.as_bytes()));
    assert!(!attempt.matches_original_json(b"replacement source"));
    let identity = attempt.identity();
    assert_eq!(identity.request_id, REQUEST_ID);
    assert_eq!(identity.agent_id, AGENT);
    assert_eq!(identity.spawn_generation, SPAWN);
    assert_eq!(identity.expected_peer_pid, std::process::id());
    assert_eq!(&identity.objective, supplied.identity());
}

fn assert_unknown_reply(frame: Vec<u8>, issue: SubmissionIssue) {
    let raw = original_fixture();
    let expected_bytes = request_frame(&raw).len();
    let (attempt, captured) = perform(raw, Behavior::Reply(frame));
    assert_eq!(captured.len(), expected_bytes);
    assert_eq!(attempt.bytes_written(), expected_bytes);
    assert_eq!(attempt.status(), &SubmissionStatus::SubmitUnknown(issue));
}

fn expect_input_error(raw: String, expected: EnvelopeError) {
    let error = match ProvidedObjective::parse_json(raw) {
        Ok(_) => panic!("invalid test envelope passed structural checks"),
        Err(error) => error,
    };
    assert_eq!(error, expected);
    assert_eq!(error.to_string(), expected.code());
}

#[test]
fn real_socket_transmits_exact_raw_envelope_once_and_keeps_original_identity() {
    let raw = original_fixture().replace("\"body\":{", "\"body\": {  ");
    let input = ProvidedObjective::parse_json(raw.clone()).unwrap();
    assert!(input.matches_original_json(raw.as_bytes()));
    // Expiry and the all-zero signature are deliberately NOT authenticated here.
    assert_eq!(input.identity().expires_at_ms, 9_999_999);
    let (attempt, captured) = perform(
        raw.clone(),
        Behavior::Reply(response_frame(response(admitted()))),
    );
    assert_eq!(captured, request_frame(&raw));
    assert_eq!(attempt.bytes_written(), captured.len());
    assert_eq!(attempt.request_frame_bytes(), Some(captured.len()));
    let SubmissionStatus::Admitted(receipt) = attempt.status() else {
        panic!("scripted receipt")
    };
    assert_eq!(receipt.run_id, RUN_ID);
    assert_eq!(receipt.disposition, AdmissionDisposition::Compiled);
    assert!(!receipt.idempotent);
    assert_eq!(receipt.response_generation, SPAWN + 1);
    assert_eq!(receipt.publication_digest, "3".repeat(64));
}

#[test]
fn original_dispositions_and_conflict_are_publication_responses_only() {
    for (name, expected) in [
        ("compiled", AdmissionDisposition::Compiled),
        ("explicit_abstain", AdmissionDisposition::ExplicitAbstain),
        ("canonical_ready", AdmissionDisposition::CanonicalReady),
        (
            "canonical_abstained",
            AdmissionDisposition::CanonicalAbstained,
        ),
        (
            "canonical_slow_path",
            AdmissionDisposition::CanonicalSlowPath,
        ),
    ] {
        let mut payload = admitted();
        payload["disposition"] = json!(name);
        payload["idempotent"] = json!(true);
        let (attempt, _) = perform(
            original_fixture(),
            Behavior::Reply(response_frame(response(payload))),
        );
        let SubmissionStatus::Admitted(receipt) = attempt.status() else {
            panic!("scripted disposition")
        };
        assert_eq!(receipt.disposition, expected);
        assert!(receipt.idempotent);
    }
    let (attempt, _) = perform(
        original_fixture(),
        Behavior::Reply(response_frame(response(json!({
            "type":"objective_conflict", "run_id":RUN_ID, "conflict_digest":"6".repeat(64)
        })))),
    );
    let SubmissionStatus::Conflict(receipt) = attempt.status() else {
        panic!("scripted conflict")
    };
    assert_eq!(receipt.run_id, RUN_ID);
    assert_eq!(receipt.conflict_digest, "6".repeat(64));
}

#[test]
fn only_exact_original_predispatch_errors_are_certain_for_this_sent_attempt() {
    for (code, message, generation, expected) in [
        (
            "objective_unavailable",
            "no owner objective profile is configured",
            SPAWN + 1,
            PrePublicationRefusal::ObjectiveUnavailable,
        ),
        (
            "unsupported_schema",
            "unsupported agentd control schema",
            SPAWN,
            PrePublicationRefusal::UnsupportedSchema,
        ),
    ] {
        let mut value = response(json!({"type":"error", "code":code, "message":message}));
        value["current_generation"] = json!(generation);
        let (attempt, _) = perform(original_fixture(), Behavior::Reply(response_frame(value)));
        assert!(attempt.bytes_written() > 0);
        assert_eq!(
            attempt.status(),
            &SubmissionStatus::RefusedBeforePublication {
                reason: expected,
                response_generation: generation
            }
        );
    }
}

#[test]
fn generic_rejection_unknown_errors_and_unscoped_overload_keep_unknown_and_redact_messages() {
    for (code, message, expected) in [
        (
            "request_rejected",
            "objective trust changed after durable publication; retry after reconciliation",
            SubmissionIssue::OwnerRequestRejected,
        ),
        (
            "request_rejected",
            "objective signature: fixture-secret-signature-source",
            SubmissionIssue::OwnerRequestRejected,
        ),
        (
            "request_rejected",
            "no owner objective profile is configured",
            SubmissionIssue::OwnerRequestRejected,
        ),
        (
            "owner_future_code",
            "fixture-secret-source-body",
            SubmissionIssue::OwnerError,
        ),
        (
            "objective_unavailable",
            "fixture-secret-source-body",
            SubmissionIssue::OwnerError,
        ),
        (
            "unsupported_schema",
            "unsupported agentd control schema",
            SubmissionIssue::OwnerError,
        ),
    ] {
        let frame = response_frame(response(
            json!({"type":"error", "code":code, "message":message}),
        ));
        let (attempt, _) = perform(original_fixture(), Behavior::Reply(frame));
        assert_eq!(attempt.status(), &SubmissionStatus::SubmitUnknown(expected));
        assert!(!format!("{:?}", attempt.status()).contains("fixture-secret"));
        assert!(!expected.to_string().contains(message));
    }
    assert_unknown_reply(
        b"{\"type\":\"overloaded\",\"retry_after_ms\":50}\n".to_vec(),
        SubmissionIssue::Overloaded,
    );
}

#[test]
fn eof_or_peer_loss_after_any_actual_bytes_keeps_the_original_unknown() {
    for behavior in [Behavior::CloseAfterFrame, Behavior::CloseAfterPrefix] {
        let (attempt, captured) = perform(original_fixture(), behavior);
        assert!(!captured.is_empty(), "peer actually received request bytes");
        assert!(attempt.bytes_written() >= captured.len());
        assert!(matches!(
            attempt.status(),
            SubmissionStatus::SubmitUnknown(_)
        ));
    }
}

#[test]
fn deadline_after_a_verified_complete_request_is_unknown_without_retry() {
    let started = Instant::now();
    let (attempt, captured) = perform(original_fixture(), Behavior::StallAfterFrame);
    assert!(!captured.is_empty());
    assert_eq!(attempt.bytes_written(), captured.len());
    assert_eq!(
        attempt.status(),
        &SubmissionStatus::SubmitUnknown(SubmissionIssue::DeadlineElapsed)
    );
    assert!(started.elapsed() < Duration::from_millis(POLL_TIMEOUT_MS + 2_000));
}

#[test]
fn malformed_non_utf8_duplicate_extra_or_oversize_frames_cannot_establish_a_result() {
    let valid = response_frame(response(admitted()));
    let mut extra = valid.clone();
    extra.extend_from_slice(&valid);
    let mut trailing_blank = valid.clone();
    trailing_blank.push(b'\n');
    let duplicate_envelope = String::from_utf8(valid.clone())
        .unwrap()
        .replacen(
            "\"request_id\":41",
            "\"request_id\":41,\"request_id\":41",
            1,
        )
        .into_bytes();
    let duplicate_payload = String::from_utf8(valid.clone())
        .unwrap()
        .replacen(
            "\"run_id\":\"run.objective.1\"",
            "\"run_id\":\"run.objective.1\",\"run_id\":\"run.objective.1\"",
            1,
        )
        .into_bytes();
    for frame in [
        b"not-json\n".to_vec(),
        vec![0xff, b'\n'],
        valid[..valid.len() - 1].to_vec(),
        vec![b'x'; MAX_FRAME_BYTES as usize + 1],
        extra,
        trailing_blank,
        duplicate_envelope,
        duplicate_payload,
        response_frame(response(json!({"type":"run_status", "run":null}))),
        response_frame(response(json!({"type":"admitted", "receipt":admitted()}))),
    ] {
        assert_unknown_reply(frame, SubmissionIssue::ProtocolMismatch);
    }
}

#[test]
fn mismatched_response_identity_or_receipt_never_clears_uncertainty() {
    let mut cases = Vec::new();
    for (key, value) in [
        ("schema_version", json!(1)),
        ("request_id", json!(REQUEST_ID + 1)),
        ("agent_id", json!("22222222-2222-4222-8222-222222222222")),
        ("spawn_generation", json!(SPAWN + 1)),
        ("current_generation", json!(SPAWN - 1)),
        ("current_generation", json!(SPAWN + 3)),
        ("unexpected", json!(true)),
    ] {
        // Even the exact original pre-dispatch code/message needs the matching
        // request and original source. A different peer is tested before writes.
        let mut value_response = response(json!({"type":"error", "code":"objective_unavailable",
            "message":"no owner objective profile is configured"}));
        value_response[key] = value;
        cases.push(value_response);
    }
    for (key, value) in [
        ("run_id", json!("run.replacement")),
        ("objective_digest", json!("0".repeat(64))),
        ("hard_constraint_digest", json!("A".repeat(64))),
        ("publication_digest", json!("3".repeat(63))),
        ("chain_digest", json!("g".repeat(64))),
        ("disposition", json!("future_disposition")),
        ("idempotent", json!("true")),
        ("unexpected", json!("extra")),
    ] {
        let mut payload = admitted();
        payload[key] = value;
        cases.push(response(payload));
    }
    cases.push(response(
        json!({"type":"objective_conflict", "run_id":"run.replacement",
        "conflict_digest":"6".repeat(64)}),
    ));
    cases.push(response(
        json!({"type":"objective_conflict", "run_id":RUN_ID,
        "conflict_digest":"0".repeat(64)}),
    ));
    cases.push(response(
        json!({"type":"error", "code":"bad code", "message":"safe fixture"}),
    ));
    cases.push(response(
        json!({"type":"error", "code":"request_rejected", "message":"x".repeat(513)}),
    ));
    for value in cases {
        assert_unknown_reply(response_frame(value), SubmissionIssue::ProtocolMismatch);
    }
}

#[test]
fn peer_pid_mismatch_is_not_sent_and_never_adopts_the_connected_peer() {
    let raw = original_fixture();
    let mut socket = SocketFixture::new();
    let wrong_pid = std::process::id().checked_add(1).unwrap();
    let transport = ObjectiveTransport::new(socket.config(), wrong_pid, REQUEST_ID).unwrap();
    let (done, server) = socket.serve(&raw, Behavior::ExpectNoRequestBytes);
    let attempt = transport.submit_once(ProvidedObjective::parse_json(raw.clone()).unwrap());
    done.send(()).unwrap();
    assert!(server.join().unwrap().is_empty());
    assert_eq!(attempt.bytes_written(), 0);
    assert_eq!(
        attempt.status(),
        &SubmissionStatus::NotSent(SubmissionIssue::PeerDenied)
    );
    assert_eq!(attempt.identity().expected_peer_pid, wrong_pid);
    assert!(attempt.matches_original_json(raw.as_bytes()));
}

#[test]
fn private_path_uid_mode_and_socket_checks_precede_any_connection() {
    for case in [
        "uid",
        "parent_mode",
        "socket_mode",
        "socket_link",
        "parent_link",
    ] {
        let socket = SocketFixture::new();
        let mut config = socket.config();
        match case {
            "uid" => {
                config = EndpointConfig::new(
                    socket.socket.clone(),
                    AGENT.to_owned(),
                    SPAWN,
                    socket.uid.checked_add(1).unwrap(),
                )
                .unwrap()
            }
            "parent_mode" => {
                fs::set_permissions(&socket.directory, fs::Permissions::from_mode(0o750)).unwrap()
            }
            "socket_mode" => {
                fs::set_permissions(&socket.socket, fs::Permissions::from_mode(0o660)).unwrap()
            }
            "socket_link" => {
                let link = socket.directory.join("alias.sock");
                symlink(&socket.socket, &link).unwrap();
                config = EndpointConfig::new(link, AGENT.to_owned(), SPAWN, socket.uid).unwrap();
            }
            "parent_link" => {
                let real = socket.directory.join("real");
                DirBuilder::new().mode(0o700).create(&real).unwrap();
                let link = socket.directory.join("alias");
                symlink(&real, &link).unwrap();
                let actual = real.join("control.sock");
                let _inner = UnixListener::bind(&actual).unwrap();
                fs::set_permissions(&actual, fs::Permissions::from_mode(0o600)).unwrap();
                config = EndpointConfig::new(
                    link.join("control.sock"),
                    AGENT.to_owned(),
                    SPAWN,
                    socket.uid,
                )
                .unwrap();
            }
            _ => unreachable!(),
        }
        let attempt = ObjectiveTransport::new(config, std::process::id(), REQUEST_ID)
            .unwrap()
            .submit_once(ProvidedObjective::parse_json(original_fixture()).unwrap());
        assert_eq!(
            attempt.status(),
            &SubmissionStatus::NotSent(SubmissionIssue::PeerDenied),
            "{case}"
        );
        assert_eq!(attempt.bytes_written(), 0);
        socket.assert_no_connections();
    }
}

#[test]
fn no_listener_or_wrong_spawn_is_zero_byte_not_sent_without_rebinding() {
    let mut socket = SocketFixture::new();
    drop(socket.listener.take()); // Its private filesystem socket remains, but no listener does.
    let attempt = socket
        .transport()
        .submit_once(ProvidedObjective::parse_json(original_fixture()).unwrap());
    assert_eq!(attempt.bytes_written(), 0);
    assert_eq!(
        attempt.status(),
        &SubmissionStatus::NotSent(SubmissionIssue::Unavailable)
    );

    let socket = SocketFixture::new();
    let mut value = fixture_value();
    value["body"]["spawn_generation"] = json!(SPAWN + 1);
    let raw = encoded(&value);
    let attempt = socket
        .transport()
        .submit_once(ProvidedObjective::parse_json(raw.clone()).unwrap());
    assert_eq!(
        attempt.status(),
        &SubmissionStatus::NotSent(SubmissionIssue::GenerationFenced)
    );
    assert_eq!(attempt.bytes_written(), 0);
    assert!(attempt.matches_original_json(raw.as_bytes()));
    socket.assert_no_connections();
}

#[test]
fn request_bound_includes_the_outer_envelope_and_exact_final_newline() {
    let mut raw = original_fixture();
    let extra = MAX_FRAME_BYTES as usize - request_frame(&raw).len();
    raw.insert_str(1, &" ".repeat(extra));
    let (attempt, captured) = perform(
        raw.clone(),
        Behavior::Reply(response_frame(response(admitted()))),
    );
    assert_eq!(captured.len() as u64, MAX_FRAME_BYTES);
    assert!(matches!(attempt.status(), SubmissionStatus::Admitted(_)));

    raw.insert(1, ' ');
    let socket = SocketFixture::new();
    let attempt = socket
        .transport()
        .submit_once(ProvidedObjective::parse_json(raw.clone()).unwrap());
    assert_eq!(
        attempt.status(),
        &SubmissionStatus::NotSent(SubmissionIssue::FrameBound)
    );
    assert_eq!(attempt.bytes_written(), 0);
    assert!(attempt.matches_original_json(raw.as_bytes()));
    socket.assert_no_connections();
}

#[test]
fn structural_checks_reject_changed_shape_duplicates_numbers_and_credentials_without_auth_claims() {
    let raw = original_fixture();
    for malformed in [
        format!(" {raw}"),
        format!("{raw} "),
        format!("\n{raw}"),
        raw.replacen('{', "{\r\n", 1),
    ] {
        expect_input_error(malformed, EnvelopeError::FramingProfile);
    }
    expect_input_error(
        format!("{{{}}}", " ".repeat(MAX_FRAME_BYTES as usize)),
        EnvelopeError::FrameBound,
    );
    expect_input_error(
        raw.replacen(
            "\"issuer_id\":",
            "\"issuer_id\":\"duplicate\",\"issuer_id\":",
            1,
        ),
        EnvelopeError::MalformedEnvelope,
    );
    expect_input_error(
        raw.replacen("\"run_id\":", "\"run_id\":\"duplicate\",\"run_id\":", 1),
        EnvelopeError::MalformedEnvelope,
    );
    for (pointer, replacement, expected) in [
        ("/unexpected", json!(true), EnvelopeError::MalformedEnvelope),
        ("/sequence", json!(true), EnvelopeError::MalformedEnvelope),
        (
            "/issuer_id",
            json!("bad issuer"),
            EnvelopeError::InvalidIdentity,
        ),
        ("/message_id", json!("é"), EnvelopeError::InvalidIdentity),
        (
            "/body/run_id",
            json!("x".repeat(129)),
            EnvelopeError::InvalidIdentity,
        ),
        (
            "/body/run_id",
            json!("run\u{0000}bad"),
            EnvelopeError::InvalidIdentity,
        ),
        (
            "/signature_hex",
            json!("0".repeat(127)),
            EnvelopeError::InvalidSignatureShape,
        ),
        (
            "/signature_hex",
            json!("0".repeat(129)),
            EnvelopeError::InvalidSignatureShape,
        ),
        (
            "/signature_hex",
            json!("z".repeat(128)),
            EnvelopeError::InvalidSignatureShape,
        ),
    ] {
        let mut value = fixture_value();
        if pointer == "/unexpected" {
            value["unexpected"] = replacement;
        } else {
            *value.pointer_mut(pointer).unwrap() = replacement;
        }
        expect_input_error(encoded(&value), expected);
    }
    for pointer in [
        "/key_epoch",
        "/sequence",
        "/expires_at_ms",
        "/body/spawn_generation",
        "/body/objective_revision",
        "/body/authority_epoch",
    ] {
        let mut value = fixture_value();
        *value.pointer_mut(pointer).unwrap() = json!(0);
        expect_input_error(encoded(&value), EnvelopeError::InvalidNumber);
    }
    for field in [
        "runtime_body_digest",
        "preference_state_digest",
        "model_tuple_digest",
        "prompt_registry_digest",
        "artifact_set_digest",
    ] {
        for invalid in [
            "0".repeat(64),
            "A".repeat(64),
            "f".repeat(63),
            "f".repeat(65),
        ] {
            let mut value = fixture_value();
            value["body"][field] = json!(invalid);
            expect_input_error(encoded(&value), EnvelopeError::InvalidDigest);
        }
    }
}

#[test]
fn source_and_canonical_body_limits_are_utf8_bytes_without_source_normalization() {
    let mut value = fixture_value();
    value["body"]["source_envelope_json"] = json!("");
    expect_input_error(encoded(&value), EnvelopeError::SourceBound);
    value["body"]["source_envelope_json"] = json!("é".repeat(16_384));
    let raw = encoded(&value);
    assert!(ProvidedObjective::parse_json(raw.clone())
        .unwrap()
        .matches_original_json(raw.as_bytes()));
    value["body"]["source_envelope_json"] = json!("é".repeat(16_385));
    expect_input_error(encoded(&value), EnvelopeError::SourceBound);
    value["body"]["source_envelope_json"] = json!("\u{0001}".repeat(8_200));
    expect_input_error(encoded(&value), EnvelopeError::BodyBound);
}

#[test]
fn execution_context_and_explicit_request_identity_are_checked_before_io() {
    let socket = SocketFixture::new();
    for (pid, id) in [
        (0, REQUEST_ID),
        (std::process::id(), 0),
        (u32::MAX, REQUEST_ID),
    ] {
        assert!(matches!(
            ObjectiveTransport::new(socket.config(), pid, id),
            Err(ObserverError::InvalidRequest)
        ));
    }
    let transport = socket.transport();
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    runtime.block_on(async {
        assert!(matches!(
            ObjectiveTransport::new(socket.config(), std::process::id(), REQUEST_ID),
            Err(ObserverError::InvalidExecutionContext)
        ));
        let attempt =
            transport.submit_once(ProvidedObjective::parse_json(original_fixture()).unwrap());
        assert_eq!(
            attempt.status(),
            &SubmissionStatus::NotSent(SubmissionIssue::InvalidExecutionContext)
        );
        assert_eq!(attempt.bytes_written(), 0);
    });
    socket.assert_no_connections();
}
