//! Disposable Linux UDS fixtures, not original-owner admission qualification.
#![cfg(all(feature = "objective-history", target_os = "linux"))]

use hepta_os_observer::objective::history::{
    HistoryAnchor, HistoryAttempt, HistoryIssue, HistoryStatus, ObjectiveHistoryClient,
    OwnerUnknownReason,
};
use hepta_os_observer::objective::{ProvidedObjective, SubmissionIssue};
use hepta_os_observer::{EndpointConfig, MAX_FRAME_BYTES};
use serde_json::{json, Value};
use std::fs::{self, DirBuilder};
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::ffi::OsStringExt;
use std::os::unix::fs::{DirBuilderExt, MetadataExt, PermissionsExt};
use std::os::unix::net::UnixListener;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

const AGENT: &str = "11111111-1111-4111-8111-111111111111";
const SPAWN: u64 = 7;
const REQUEST: u64 = 91;
static NEXT: AtomicU64 = AtomicU64::new(1);

fn raw() -> String {
    include_str!("fixtures/objective_ingress_original_wire_only.json")
        .trim_end_matches('\n')
        .replace("\"body\":{", "\"body\": {  ")
}

fn publication() -> Value {
    let input: Value = serde_json::from_str(&raw()).unwrap();
    json!({"run_id":input["body"]["run_id"],"original_spawn_generation":input["body"]["spawn_generation"],
        "issuer_id":input["issuer_id"],"key_epoch":input["key_epoch"],"message_id":input["message_id"],
        "message_sequence":input["sequence"],"expires_at_ms":input["expires_at_ms"],
        "signed_body_digest":"1".repeat(64),"profile_digest":"2".repeat(64),
        "publication_sequence":2,"publication_digest":"3".repeat(64),"chain_digest":"4".repeat(64),
        "outcome":{"type":"compiled","objective_digest":"5".repeat(64),"hard_constraint_digest":"6".repeat(64)}})
}

fn response(outcome: Value) -> Value {
    json!({"schema_version":2,"request_id":REQUEST,"agent_id":AGENT,"spawn_generation":SPAWN,
        "current_generation":SPAWN+1,"payload":{"type":"objective_admission","outcome":outcome}})
}

fn published() -> Value {
    response(json!({"type":"published","publication":publication()}))
}
fn frame(value: &Value) -> Vec<u8> {
    let mut bytes = serde_json::to_vec(value).unwrap();
    bytes.push(b'\n');
    bytes
}

enum Reply {
    Bytes(Vec<u8>),
    Lost,
    ExpectZero,
    Stall,
}

struct Fixture {
    root: PathBuf,
    socket: PathBuf,
    listener: Option<UnixListener>,
    uid: u32,
}

impl Fixture {
    fn new() -> Self {
        let root = PathBuf::from(format!(
            "/tmp/hp-history-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        DirBuilder::new().mode(0o700).create(&root).unwrap();
        let socket = root.join("control.sock");
        let listener = UnixListener::bind(&socket).unwrap();
        listener.set_nonblocking(true).unwrap();
        fs::set_permissions(&socket, fs::Permissions::from_mode(0o600)).unwrap();
        let uid = fs::metadata(&root).unwrap().uid();
        Self {
            root,
            socket,
            listener: Some(listener),
            uid,
        }
    }

    fn client(&self, pid: u32) -> ObjectiveHistoryClient {
        let config =
            EndpointConfig::new(self.socket.clone(), AGENT.into(), SPAWN, self.uid).unwrap();
        ObjectiveHistoryClient::new(config, pid, REQUEST).unwrap()
    }

    fn cli(&self) -> Command {
        let mut command = Command::new(env!("CARGO_BIN_EXE_hepta-history"));
        command.args([
            self.socket.to_str().unwrap(),
            AGENT,
            &SPAWN.to_string(),
            &self.uid.to_string(),
            &std::process::id().to_string(),
            &REQUEST.to_string(),
        ]);
        command
    }

    fn serve(&mut self, reply: Reply) -> (mpsc::Sender<()>, thread::JoinHandle<Vec<u8>>) {
        let listener = self.listener.take().unwrap();
        let (done, finished) = mpsc::channel();
        let handle = thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(9);
            let (mut stream, _) = loop {
                match listener.accept() {
                    Ok(pair) => break pair,
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        assert!(Instant::now() < deadline, "missing query connection");
                        thread::sleep(Duration::from_millis(2));
                    }
                    Err(error) => panic!("{error}"),
                }
            };
            stream
                .set_read_timeout(Some(Duration::from_secs(9)))
                .unwrap();
            stream
                .set_write_timeout(Some(Duration::from_secs(2)))
                .unwrap();
            let mut reader = BufReader::new(stream.try_clone().unwrap());
            let mut received = Vec::new();
            if matches!(reply, Reply::ExpectZero) {
                assert_eq!(reader.read_to_end(&mut received).unwrap(), 0);
            } else {
                (&mut reader)
                    .take(MAX_FRAME_BYTES + 1)
                    .read_until(b'\n', &mut received)
                    .unwrap();
                assert!(received.ends_with(b"\n") && received.len() as u64 <= MAX_FRAME_BYTES);
                assert!(reader.buffer().is_empty());
            }
            let stalled = matches!(reply, Reply::Stall);
            if let Reply::Bytes(bytes) = reply {
                let _ = stream.write_all(&bytes);
            }
            if stalled {
                finished.recv_timeout(Duration::from_secs(9)).unwrap();
            }
            drop(reader);
            drop(stream);
            if !stalled {
                finished.recv_timeout(Duration::from_secs(9)).unwrap();
            }
            assert!(
                matches!(listener.accept(), Err(error) if error.kind() == std::io::ErrorKind::WouldBlock),
                "no automatic repeat"
            );
            received
        });
        (done, handle)
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

fn perform(reply: Reply, anchor: Option<HistoryAnchor>) -> (HistoryAttempt, Vec<u8>) {
    let mut fixture = Fixture::new();
    let client = fixture.client(std::process::id());
    let (done, server) = fixture.serve(reply);
    let result = client.query_once(ProvidedObjective::parse_json(raw()).unwrap(), anchor);
    done.send(()).unwrap();
    let received = server.join().unwrap();
    assert!(result.matches_original_json(raw().as_bytes()));
    assert!(!result.matches_original_json(b"new request"));
    assert_eq!(result.bytes_written(), received.len());
    assert_eq!(result.request_frame_bytes(), Some(received.len()));
    (result, received)
}

#[test]
fn raw_history_query_keeps_old_body_spawn_and_current_peer_boundary() {
    let (attempt, bytes) = perform(Reply::Bytes(frame(&published())), None);
    let prefix = format!("{{\"schema_version\":2,\"request_id\":{REQUEST},\"spawn_generation\":{SPAWN},\"method\":{{\"type\":\"objective_admission\",\"query\":{{\"request\":");
    let expected = format!("{prefix}{},\"anchor\":null}}}}}}\n", raw());
    assert_eq!(bytes, expected.as_bytes());
    let input: Value = serde_json::from_str(&raw()).unwrap();
    assert_ne!(input["body"]["spawn_generation"], SPAWN);
    assert_eq!(attempt.identity().spawn_generation, SPAWN);
    let HistoryStatus::HistoricalPublication {
        publication: p,
        response_generation,
    } = attempt.status()
    else {
        panic!("scripted history expected")
    };
    assert_eq!(serde_json::to_value(p).unwrap(), publication());
    assert_eq!(*response_generation, SPAWN + 1);
}

#[test]
fn retained_anchor_is_sent_and_cannot_cover_a_later_or_different_record() {
    for (sequence, digest, expected) in [
        (2, '4', true),
        (3, '7', true),
        (1, '4', false),
        (2, '7', false),
    ] {
        let anchor = HistoryAnchor::new(sequence, digest.to_string().repeat(64)).unwrap();
        let (attempt, bytes) = perform(Reply::Bytes(frame(&published())), Some(anchor.clone()));
        let request: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(
            request["method"]["query"]["anchor"],
            serde_json::to_value(&anchor).unwrap()
        );
        assert_eq!(attempt.anchor(), Some(&anchor));
        assert_eq!(
            matches!(
                attempt.status(),
                HistoryStatus::HistoricalPublication { .. }
            ),
            expected
        );
        if !expected {
            assert_eq!(
                attempt.status(),
                &HistoryStatus::Unknown(HistoryIssue::Transport(SubmissionIssue::ProtocolMismatch))
            );
        }
    }
}

#[test]
fn every_owner_unknown_preserves_uncertainty_and_conflict_is_only_history() {
    for (name, reason) in [
        ("invalid_query", OwnerUnknownReason::InvalidQuery),
        ("owner_unavailable", OwnerUnknownReason::OwnerUnavailable),
        (
            "journal_unavailable",
            OwnerUnknownReason::JournalUnavailable,
        ),
        (
            "no_matching_publication",
            OwnerUnknownReason::NoMatchingPublication,
        ),
        ("anchor_missing", OwnerUnknownReason::AnchorMissing),
        ("anchor_mismatch", OwnerUnknownReason::AnchorMismatch),
        (
            "publication_outside_anchor",
            OwnerUnknownReason::PublicationOutsideAnchor,
        ),
    ] {
        let (attempt, _) = perform(
            Reply::Bytes(frame(&response(json!({"type":"unknown","reason":name})))),
            None,
        );
        assert_eq!(
            attempt.status(),
            &HistoryStatus::Unknown(HistoryIssue::Owner(reason))
        );
    }
    for outcome in [
        json!({"type":"explicit_abstain","objective_digest":"5".repeat(64),"hard_constraint_digest":"6".repeat(64)}),
        json!({"type":"conflict","conflict_digest":"8".repeat(64)}),
    ] {
        let mut value = published();
        value["payload"]["outcome"]["publication"]["outcome"] = outcome;
        let (attempt, _) = perform(Reply::Bytes(frame(&value)), None);
        assert!(matches!(
            attempt.status(),
            HistoryStatus::HistoricalPublication { .. }
        ));
    }
}

#[test]
fn wrong_owner_request_authentication_metadata_and_anchor_shapes_fail_closed() {
    for (path, replacement) in [
        ("/schema_version", json!(1)),
        ("/request_id", json!(REQUEST + 1)),
        ("/agent_id", json!("22222222-2222-4222-8222-222222222222")),
        ("/spawn_generation", json!(SPAWN - 1)),
        ("/current_generation", json!(SPAWN + 3)),
        ("/payload/outcome/publication/run_id", json!("run.other")),
        (
            "/payload/outcome/publication/original_spawn_generation",
            json!(SPAWN),
        ),
        (
            "/payload/outcome/publication/issuer_id",
            json!("issuer.other"),
        ),
        ("/payload/outcome/publication/key_epoch", json!(99)),
        (
            "/payload/outcome/publication/message_id",
            json!("message.other"),
        ),
        ("/payload/outcome/publication/message_sequence", json!(99)),
        ("/payload/outcome/publication/expires_at_ms", json!(1)),
        (
            "/payload/outcome/publication/publication_sequence",
            json!(0),
        ),
        (
            "/payload/outcome/publication/publication_sequence",
            json!(4097),
        ),
        (
            "/payload/outcome/publication/signed_body_digest",
            json!("0".repeat(64)),
        ),
        (
            "/payload/outcome/publication/profile_digest",
            json!("A".repeat(64)),
        ),
        (
            "/payload/outcome/publication/publication_digest",
            json!("1".repeat(63)),
        ),
        (
            "/payload/outcome/publication/chain_digest",
            json!("z".repeat(64)),
        ),
    ] {
        let mut value = published();
        *value.pointer_mut(path).unwrap() = replacement;
        let (attempt, _) = perform(Reply::Bytes(frame(&value)), None);
        assert_eq!(
            attempt.status(),
            &HistoryStatus::Unknown(HistoryIssue::Transport(SubmissionIssue::ProtocolMismatch)),
            "{path}"
        );
    }
}

#[test]
fn malformed_duplicate_extra_and_unscoped_responses_are_not_publication_proof() {
    let valid = frame(&published());
    let mut doubled = valid.clone();
    doubled.extend_from_slice(&valid);
    let duplicate = String::from_utf8(valid.clone())
        .unwrap()
        .replace(
            "\"publication_sequence\":2",
            "\"publication_sequence\":2,\"publication_sequence\":2",
        )
        .into_bytes();
    let mut extra = published();
    extra["payload"]["outcome"]["publication"]["terminal_observed"] = json!(true);
    for bytes in [
        b"{}\n".to_vec(),
        vec![0xff, b'\n'],
        valid[..valid.len() - 1].to_vec(),
        vec![b'x'; MAX_FRAME_BYTES as usize + 1],
        doubled,
        duplicate,
        frame(&extra),
        frame(&response(json!({"type":"unknown","reason":"not_admitted"}))),
        frame(&response(
            json!({"type":"unknown","reason":"no_matching_publication","run":null}),
        )),
    ] {
        let (attempt, _) = perform(Reply::Bytes(bytes), None);
        assert_eq!(
            attempt.status(),
            &HistoryStatus::Unknown(HistoryIssue::Transport(SubmissionIssue::ProtocolMismatch))
        );
    }
    let (attempt, _) = perform(
        Reply::Bytes(b"{\"type\":\"overloaded\",\"retry_after_ms\":50}\n".to_vec()),
        None,
    );
    assert_eq!(
        attempt.status(),
        &HistoryStatus::Unknown(HistoryIssue::Transport(SubmissionIssue::Overloaded))
    );
}

#[test]
fn query_loss_or_deadline_never_reconnects_or_submits() {
    for reply in [Reply::Lost, Reply::Stall] {
        let (attempt, _) = perform(reply, None);
        assert!(matches!(
            attempt.status(),
            HistoryStatus::Unknown(HistoryIssue::Transport(_))
        ));
        assert!(attempt.bytes_written() > 0);
    }
}

#[test]
fn wrong_peer_is_zero_query_bytes_and_private_path_is_checked_before_connect() {
    let mut fixture = Fixture::new();
    let client = fixture.client(std::process::id() + 1);
    let (done, server) = fixture.serve(Reply::ExpectZero);
    let attempt = client.query_once(ProvidedObjective::parse_json(raw()).unwrap(), None);
    done.send(()).unwrap();
    assert!(server.join().unwrap().is_empty());
    assert_eq!(
        attempt.status(),
        &HistoryStatus::QueryNotSent(SubmissionIssue::PeerDenied)
    );
    assert_eq!(attempt.bytes_written(), 0);
    let fixture = Fixture::new();
    fs::set_permissions(&fixture.root, fs::Permissions::from_mode(0o750)).unwrap();
    let attempt = fixture
        .client(std::process::id())
        .query_once(ProvidedObjective::parse_json(raw()).unwrap(), None);
    assert_eq!(
        attempt.status(),
        &HistoryStatus::QueryNotSent(SubmissionIssue::PeerDenied)
    );
    assert!(
        matches!(fixture.listener.as_ref().unwrap().accept(), Err(e) if e.kind()==std::io::ErrorKind::WouldBlock)
    );
}

#[test]
fn cli_preserves_anchor_and_emits_finite_history_without_source_or_signature() {
    let mut fixture = Fixture::new();
    let (done, server) = fixture.serve(Reply::Bytes(frame(&published())));
    let mut child = fixture
        .cli()
        .args(["2", &"4".repeat(64)])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(raw().as_bytes())
        .unwrap();
    let output = child.wait_with_output().unwrap();
    done.send(()).unwrap();
    let request: Value = serde_json::from_slice(&server.join().unwrap()).unwrap();
    assert_eq!(request["method"]["type"], "objective_admission");
    assert_eq!(output.status.code(), Some(0));
    assert!(output.stderr.is_empty());
    assert_eq!(output.stdout.iter().filter(|&&b| b == b'\n').count(), 1);
    let result: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(result["status"], "historical_publication");
    assert_eq!(result["publication"], publication());
    assert_eq!(result["anchor_coverage"], "retained_anchor");
    assert_eq!(result["anchor"], request["method"]["query"]["anchor"]);
    let text = String::from_utf8(output.stdout).unwrap();
    assert!(
        !text.contains("source_envelope_json")
            && !text.contains("signature_hex")
            && !text.contains(fixture.socket.to_str().unwrap())
    );
}

#[test]
fn cli_invalid_input_and_unknown_owner_errors_never_clear_original_uncertainty() {
    let fixture = Fixture::new();
    let output = fixture.cli().args(["0", &"4".repeat(64)]).output().unwrap();
    assert_eq!(output.status.code(), Some(10));
    assert_eq!(
        serde_json::from_slice::<Value>(&output.stdout).unwrap()["status"],
        "query_not_sent"
    );
    let output = Command::new(env!("CARGO_BIN_EXE_hepta-history"))
        .arg(std::ffi::OsString::from_vec(vec![0xff]))
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(10));
    assert!(output.stderr.is_empty());
    let mut fixture = Fixture::new();
    let mut value = published();
    value["payload"] =
        json!({"type":"error","code":"request_rejected","message":"private-fixture-source"});
    let (done, server) = fixture.serve(Reply::Bytes(frame(&value)));
    let mut child = fixture
        .cli()
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(raw().as_bytes())
        .unwrap();
    let output = child.wait_with_output().unwrap();
    done.send(()).unwrap();
    server.join().unwrap();
    assert_eq!(output.status.code(), Some(12));
    let text = String::from_utf8(output.stdout).unwrap();
    assert!(!text.contains("private-fixture"));
    assert_eq!(
        serde_json::from_str::<Value>(&text).unwrap()["status"],
        "unknown"
    );
}

#[test]
fn deserialized_out_of_range_anchor_and_oversize_query_do_not_connect() {
    let fixture = Fixture::new();
    assert!(HistoryAnchor::new(4097, "4".repeat(64)).is_err());
    let anchor: HistoryAnchor = serde_json::from_value(json!({
        "sequence":4097,"chain_digest":"4".repeat(64)
    }))
    .unwrap();
    let attempt = fixture
        .client(std::process::id())
        .query_once(ProvidedObjective::parse_json(raw()).unwrap(), Some(anchor));
    assert_eq!(
        attempt.status(),
        &HistoryStatus::QueryNotSent(SubmissionIssue::ProtocolMismatch)
    );
    assert_eq!(attempt.bytes_written(), 0);
    let mut input = raw();
    input.insert_str(1, &" ".repeat(MAX_FRAME_BYTES as usize - input.len()));
    let attempt = fixture
        .client(std::process::id())
        .query_once(ProvidedObjective::parse_json(input).unwrap(), None);
    assert_eq!(
        attempt.status(),
        &HistoryStatus::QueryNotSent(SubmissionIssue::FrameBound)
    );
    assert_eq!(attempt.bytes_written(), 0);
    assert!(
        matches!(fixture.listener.as_ref().unwrap().accept(), Err(error)
        if error.kind()==std::io::ErrorKind::WouldBlock)
    );
}
