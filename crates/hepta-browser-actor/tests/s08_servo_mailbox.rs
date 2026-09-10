//! S08 qualification-only host vertical slice.
//!
//! This test is inert unless `HEPTA_S08_MAILBOX` names an absolute private
//! directory created by the permanent exact-pin Servo workflow. The mailbox is
//! test transport only; product request bytes still cross the production
//! AgentPort framing and the product actor still requires pidfd-backed custody.

use hepta_agent_port::{
    AgentPortError, BrowserRequestHandler, DispatchContext, HandlerOutcome, serve_one_with_observer,
};
use hepta_agent_transport::{ClientConnection, PeerIdentity, PeerPolicy};
use hepta_browser_actor::{
    ServoBrowserActor, ServoCompletionDelivery, ServoPumpResult, ServoRuntimeCommand,
    ServoRuntimeCompletion, ServoRuntimeError, ServoRuntimeOperation, TaskFlowPrincipal,
    servo_runtime_pair,
};
use hepta_browser_codec::{
    BrowserErrorCode, BrowserOperation, BrowserRequest, BrowserResponse, ElementReference,
    JsonObject, JsonValue, NavigationTarget, ObservationField, PageAction, ProfilePersistence,
    ProfileSpec, WaitCondition, decode_response, encode_request,
};
use hepta_peer_attestation::{AttestedPeer, PeerRuntimePolicy, ProcfsPeerAttestor};
use hepta_session_core::{JournalId, ReceiptJournal, ReceiptLifecycleState};
use std::collections::BTreeMap;
use std::fs;
use std::io::{Read, Write};
use std::net::{Shutdown, TcpListener};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::thread;
use std::time::{Duration, Instant};

const BUDGET: Duration = Duration::from_secs(30);
const MAILBOX_BUDGET: Duration = Duration::from_secs(180);
const EXPECTED_REQUESTS: usize = 10;
const EXPECTED_SERVO_COMMANDS: usize = 9;
const NAME_SHA256: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const STRUCTURAL_SHA256: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
static UNIQUE: AtomicU64 = AtomicU64::new(0);

struct AttestedServoHandler {
    actor: ServoBrowserActor,
    attestor: ProcfsPeerAttestor,
    attested: AttestedPeer,
}

impl BrowserRequestHandler for AttestedServoHandler {
    fn handle(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<HandlerOutcome, AgentPortError> {
        self.actor
            .handle_attested(context, request, &self.attestor, &self.attested)
    }
}

struct TestDirectory(PathBuf);

impl TestDirectory {
    fn new(prefix: &str) -> Self {
        let path = std::env::temp_dir().join(format!(
            "{prefix}-{}-{}",
            std::process::id(),
            UNIQUE.fetch_add(1, Ordering::SeqCst)
        ));
        fs::create_dir(&path).expect("create private test directory");
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700))
            .expect("set private test directory mode");
        Self(path)
    }
}

impl Drop for TestDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[derive(Debug)]
struct ServerSummary {
    evidence_count: usize,
    receipt_records: usize,
    all_responses_committed: bool,
    unresolved_receipts: usize,
}

#[derive(Debug)]
struct ClientSummary {
    stale_document_rejected: bool,
    click_count_exactly_one: bool,
}

fn synthetic_attestation(
    root: &Path,
    peer: PeerIdentity,
) -> (ProcfsPeerAttestor, AttestedPeer, TaskFlowPrincipal) {
    let pid = peer.pid.expect("AF_UNIX peer must expose PID");
    let process = root.join(pid.to_string());
    fs::create_dir_all(&process).expect("create synthetic procfs process");
    fs::write(
        process.join("status"),
        format!(
            "Uid:\t{0}\t{0}\t{0}\t{0}\nGid:\t{1}\t{1}\t{1}\t{1}\n",
            peer.uid, peer.gid
        ),
    )
    .expect("write synthetic status");
    let mut fields = vec!["S"; 20];
    fields[19] = "987654";
    fs::write(
        process.join("stat"),
        format!("{pid} (s08-fixture) {}\n", fields.join(" ")),
    )
    .expect("write synthetic stat");
    fs::write(
        process.join("cgroup"),
        "0::/system.slice/hepta-s08-qualification.service\n",
    )
    .expect("write synthetic cgroup");
    fs::write(process.join("exe"), b"hepta-s08-qualification-fixture")
        .expect("write synthetic executable");

    let attestor = ProcfsPeerAttestor::new(root);
    let snapshot = attestor
        .read_snapshot(pid)
        .expect("read synthetic process snapshot");
    let attested = attestor
        .attest(peer, &PeerRuntimePolicy::exact(&snapshot))
        .expect("attest live PID against bounded synthetic service facts");
    let principal = TaskFlowPrincipal {
        principal_id: "s08-qualification-principal".to_owned(),
        expected_uid: peer.uid,
        expected_gid: peer.gid,
        expected_systemd_unit: snapshot
            .systemd_unit
            .clone()
            .expect("synthetic cgroup must identify one service"),
        expected_cgroup_v2_path: snapshot.cgroup_v2_path.clone(),
        expected_executable_sha256: snapshot.executable_sha256.clone(),
    };
    (attestor, attested, principal)
}

fn request(
    request_id: &str,
    session_id: Option<&str>,
    session_generation: Option<u64>,
    operation: BrowserOperation,
) -> BrowserRequest {
    BrowserRequest {
        request_id: request_id.to_owned(),
        session_id: session_id.map(str::to_owned),
        session_generation,
        deadline_unix_ms: None,
        operation,
    }
}

fn invoke(stream: UnixStream, request: BrowserRequest) -> BrowserResponse {
    let peer = PeerIdentity::from_stream(&stream).expect("read client-side peer");
    let mut client = ClientConnection::connect(stream, PeerPolicy::exact(peer), BUDGET)
        .expect("authenticate client transport");
    let sequence = client
        .send_request(
            encode_request(&request).expect("encode canonical request"),
            BUDGET,
        )
        .expect("send request");
    let response = decode_response(
        &client
            .receive_response(sequence, BUDGET)
            .expect("receive response"),
    )
    .expect("decode canonical response")
    .value;
    assert_eq!(response.request_id, request.request_id);
    assert_eq!(response.session_id, request.session_id);
    assert_eq!(response.session_generation, request.session_generation);
    response
}

fn success(response: BrowserResponse) -> JsonObject {
    response.outcome.expect("operation must succeed")
}

fn string(object: &JsonObject, key: &str) -> String {
    let Some(JsonValue::String(value)) = object.get(key) else {
        panic!("missing string result {key}")
    };
    value.clone()
}

fn number(object: &JsonObject, key: &str) -> u64 {
    let Some(JsonValue::Integer(value)) = object.get(key) else {
        panic!("missing integer result {key}")
    };
    (*value)
        .try_into()
        .expect("result integer must be non-negative")
}

fn boolean(object: &JsonObject, key: &str) -> bool {
    let Some(JsonValue::Bool(value)) = object.get(key) else {
        panic!("missing boolean result {key}")
    };
    *value
}

fn element_from_observation(object: &JsonObject) -> ElementReference {
    ElementReference {
        session_generation: number(object, "session_generation"),
        document_generation: number(object, "document_generation"),
        semantic_snapshot_revision: number(object, "semantic_snapshot_revision"),
        frame_id: string(object, "target_frame_id"),
        backend_node_key: Some(string(object, "target_backend_node_key")),
        role: Some(string(object, "target_role")),
        accessible_name_sha256: Some(string(object, "target_accessible_name_sha256")),
        structural_fingerprint: string(object, "target_structural_fingerprint"),
    }
}

fn socket_pairs(count: usize) -> (Vec<UnixStream>, Vec<UnixStream>) {
    (0..count)
        .map(|_| UnixStream::pair().expect("create AF_UNIX pair"))
        .unzip()
}

fn start_loopback_fixture() -> (String, String, Arc<AtomicBool>, thread::JoinHandle<()>) {
    let listener = TcpListener::bind(("127.0.0.1", 0)).expect("bind loopback fixture");
    listener
        .set_nonblocking(true)
        .expect("make fixture listener nonblocking");
    let address = listener.local_addr().expect("fixture address");
    let stop = Arc::new(AtomicBool::new(false));
    let worker_stop = stop.clone();
    let worker = thread::spawn(move || {
        let body = concat!(
            "<!doctype html><meta charset=utf-8>",
            "<title>Trillionnium S08 fixture</title>",
            "<h1 id=count>Click count 0</h1>",
            "<button aria-label=\"Action target\" onclick=\"",
            "let n=Number(document.body.dataset.n||0)+1;",
            "document.body.dataset.n=String(n);",
            "document.getElementById('count').textContent='Click count '+n;",
            "\">Action target</button>"
        );
        while !worker_stop.load(Ordering::SeqCst) {
            match listener.accept() {
                Ok((mut stream, _)) => {
                    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
                    let mut request = [0_u8; 4096];
                    let _ = stream.read(&mut request);
                    let response = format!(
                        concat!(
                            "HTTP/1.1 200 OK\r\n",
                            "Content-Type: text/html; charset=utf-8\r\n",
                            "Cache-Control: no-store\r\n",
                            "Content-Length: {}\r\n",
                            "Connection: close\r\n\r\n{}"
                        ),
                        body.len(),
                        body
                    );
                    stream
                        .write_all(response.as_bytes())
                        .expect("serve loopback fixture");
                    let _ = stream.flush();
                    let _ = stream.shutdown(Shutdown::Both);
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(2));
                }
                Err(error) => panic!("loopback fixture accept failed: {error}"),
            }
        }
    });
    (
        format!("http://127.0.0.1:{}/first", address.port()),
        format!("http://127.0.0.1:{}/second", address.port()),
        stop,
        worker,
    )
}

fn wait_for_file(path: &Path, budget: Duration) {
    let deadline = Instant::now() + budget;
    while !path.is_file() {
        assert!(
            Instant::now() < deadline,
            "timed out waiting for {}",
            path.display()
        );
        thread::sleep(Duration::from_millis(5));
    }
}

fn valid_field(key: &str, value: &str) {
    assert!(!key.is_empty() && key.len() <= 64);
    assert!(
        key.bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
    );
    assert!(value.len() <= 8 * 1024);
    assert!(!value.chars().any(char::is_control));
    assert!(!value.contains('='));
}

fn write_record(path: &Path, fields: &BTreeMap<String, String>) {
    let mut text = String::new();
    for (key, value) in fields {
        valid_field(key, value);
        text.push_str(key);
        text.push('=');
        text.push_str(value);
        text.push('\n');
    }
    assert!(text.len() <= 32 * 1024);
    let name = path.file_name().unwrap().to_string_lossy();
    let stage = path.with_file_name(format!(".{name}.{}.tmp", std::process::id()));
    fs::write(&stage, text).expect("write staged mailbox record");
    fs::rename(&stage, path).expect("publish mailbox record");
}

fn read_record(path: &Path) -> BTreeMap<String, String> {
    wait_for_file(path, MAILBOX_BUDGET);
    let text = fs::read_to_string(path).expect("read mailbox response");
    assert!(text.len() <= 32 * 1024);
    let mut fields = BTreeMap::new();
    for line in text.lines() {
        let (key, value) = line.split_once('=').expect("mailbox line separator");
        valid_field(key, value);
        assert!(fields.insert(key.to_owned(), value.to_owned()).is_none());
    }
    fs::remove_file(path).expect("remove consumed mailbox response");
    fields
}

fn observation_field_name(field: ObservationField) -> &'static str {
    match field {
        ObservationField::Role => "role",
        ObservationField::Name => "name",
        ObservationField::Text => "text",
        ObservationField::Href => "href",
        ObservationField::Bounds => "bounds",
    }
}

fn add_target(fields: &mut BTreeMap<String, String>, target: &ElementReference) {
    fields.insert("target_frame_id".to_owned(), target.frame_id.clone());
    if let Some(value) = &target.backend_node_key {
        fields.insert("target_backend_node_key".to_owned(), value.clone());
    }
    if let Some(value) = &target.role {
        fields.insert("target_role".to_owned(), value.clone());
    }
    if let Some(value) = &target.accessible_name_sha256 {
        fields.insert("target_accessible_name_sha256".to_owned(), value.clone());
    }
    fields.insert(
        "target_structural_fingerprint".to_owned(),
        target.structural_fingerprint.clone(),
    );
    fields.insert(
        "target_session_generation".to_owned(),
        target.session_generation.to_string(),
    );
    fields.insert(
        "target_document_generation".to_owned(),
        target.document_generation.to_string(),
    );
    fields.insert(
        "target_semantic_snapshot_revision".to_owned(),
        target.semantic_snapshot_revision.to_string(),
    );
}

fn complete_error(completion: ServoRuntimeCompletion, error: ServoRuntimeError) {
    assert!(matches!(
        completion.complete_error(error),
        ServoCompletionDelivery::Queued
    ));
}

fn process_servo_command(mailbox: &Path, sequence: usize, command: ServoRuntimeCommand) {
    let (_owner, operation, completion) = command.into_parts();
    if let Err(error) = completion.ensure_active() {
        complete_error(completion, error);
        return;
    }
    if matches!(&operation, ServoRuntimeOperation::Act { .. })
        && let Err(error) = completion.ensure_current_peer()
    {
        complete_error(completion, error);
        return;
    }

    let mut fields = BTreeMap::from([
        ("version".to_owned(), "1".to_owned()),
        ("sequence".to_owned(), sequence.to_string()),
        ("request_id".to_owned(), completion.request_id().to_owned()),
    ]);
    match &operation {
        ServoRuntimeOperation::Health => {
            fields.insert("kind".to_owned(), "health".to_owned());
        }
        ServoRuntimeOperation::CreateSession {
            session_id,
            profile,
        } => {
            fields.insert("kind".to_owned(), "create".to_owned());
            fields.insert("session_id".to_owned(), session_id.clone());
            fields.insert("profile_id".to_owned(), profile.profile_id.clone());
        }
        ServoRuntimeOperation::Snapshot => {
            fields.insert("kind".to_owned(), "snapshot".to_owned());
        }
        ServoRuntimeOperation::Close => {
            fields.insert("kind".to_owned(), "close".to_owned());
        }
        ServoRuntimeOperation::Navigate {
            url,
            expected_document_generation,
        } => {
            fields.insert("kind".to_owned(), "navigate".to_owned());
            fields.insert("url".to_owned(), url.clone());
            fields.insert(
                "expected_document_generation".to_owned(),
                expected_document_generation.to_string(),
            );
        }
        ServoRuntimeOperation::Observe { fields: requested } => {
            fields.insert("kind".to_owned(), "observe".to_owned());
            fields.insert(
                "observation_fields".to_owned(),
                requested
                    .iter()
                    .copied()
                    .map(observation_field_name)
                    .collect::<Vec<_>>()
                    .join(","),
            );
        }
        ServoRuntimeOperation::Wait { condition, timeout } => {
            fields.insert("kind".to_owned(), "wait".to_owned());
            fields.insert("timeout_ms".to_owned(), timeout.as_millis().to_string());
            match condition {
                WaitCondition::ElementPresent { target } => {
                    fields.insert("wait_type".to_owned(), "element_present".to_owned());
                    add_target(&mut fields, target);
                }
                _ => {
                    complete_error(
                        completion,
                        ServoRuntimeError::Unsupported("S08 qualifies element_present only"),
                    );
                    return;
                }
            }
        }
        ServoRuntimeOperation::Extract { .. } => {
            complete_error(
                completion,
                ServoRuntimeError::Unsupported("S08 does not qualify extraction"),
            );
            return;
        }
        ServoRuntimeOperation::Act { target, action } => {
            fields.insert("kind".to_owned(), "act".to_owned());
            add_target(&mut fields, target);
            match action {
                PageAction::Click => {
                    fields.insert("action".to_owned(), "click".to_owned());
                }
                _ => {
                    complete_error(
                        completion,
                        ServoRuntimeError::Unsupported("S08 qualifies click only"),
                    );
                    return;
                }
            }
        }
    }

    let command_path = mailbox.join(format!("command-{sequence:04}.kv"));
    write_record(&command_path, &fields);
    let response_path = mailbox.join(format!("response-{sequence:04}.kv"));
    let response = read_record(&response_path);
    assert_eq!(response.get("status").map(String::as_str), Some("ok"));
    let expected_sequence = sequence.to_string();
    assert_eq!(
        response.get("sequence").map(String::as_str),
        Some(expected_sequence.as_str())
    );
    assert_eq!(
        response.get("request_id").map(String::as_str),
        Some(completion.request_id())
    );

    let current_url = response.get("current_url").cloned();
    let mut result = JsonObject::new();
    match operation {
        ServoRuntimeOperation::Health => {
            result.insert("real_servo_adapter".to_owned(), JsonValue::Bool(true));
            result.insert(
                "external_effect_authority".to_owned(),
                JsonValue::Bool(false),
            );
        }
        ServoRuntimeOperation::CreateSession { profile, .. } => {
            result.insert(
                "profile_id".to_owned(),
                JsonValue::String(profile.profile_id),
            );
            result.insert(
                "runtime".to_owned(),
                JsonValue::String("exact_pin_servo".to_owned()),
            );
        }
        ServoRuntimeOperation::Snapshot => {
            result.insert("real_servo".to_owned(), JsonValue::Bool(true));
            result.insert(
                "click_count".to_owned(),
                JsonValue::Integer(
                    response
                        .get("click_count")
                        .expect("snapshot click count")
                        .parse()
                        .expect("snapshot click count integer"),
                ),
            );
        }
        ServoRuntimeOperation::Close => {
            result.insert("closed".to_owned(), JsonValue::Bool(true));
        }
        ServoRuntimeOperation::Navigate {
            url,
            expected_document_generation,
        } => {
            result.insert("navigated".to_owned(), JsonValue::Bool(true));
            result.insert("url".to_owned(), JsonValue::String(url));
            result.insert(
                "expected_document_generation".to_owned(),
                JsonValue::Integer(
                    expected_document_generation
                        .try_into()
                        .expect("document generation must fit canonical JSON"),
                ),
            );
            result.insert(
                "servo_navigation_count".to_owned(),
                JsonValue::Integer(
                    response
                        .get("servo_navigation_count")
                        .expect("navigation count")
                        .parse()
                        .expect("navigation count integer"),
                ),
            );
        }
        ServoRuntimeOperation::Observe { fields: requested } => {
            result.insert(
                "fields".to_owned(),
                JsonValue::Array(
                    requested
                        .into_iter()
                        .map(|field| JsonValue::String(observation_field_name(field).to_owned()))
                        .collect(),
                ),
            );
            for key in [
                "target_frame_id",
                "target_backend_node_key",
                "target_role",
                "target_accessible_name_sha256",
                "target_structural_fingerprint",
            ] {
                result.insert(
                    key.to_owned(),
                    JsonValue::String(response.get(key).expect("target metadata").clone()),
                );
            }
        }
        ServoRuntimeOperation::Wait { .. } => {
            result.insert("satisfied".to_owned(), JsonValue::Bool(true));
            result.insert("element_present".to_owned(), JsonValue::Bool(true));
        }
        ServoRuntimeOperation::Extract { .. } => unreachable!("extract returned before mailbox"),
        ServoRuntimeOperation::Act { .. } => {
            result.insert(
                "click_count".to_owned(),
                JsonValue::Integer(
                    response
                        .get("click_count")
                        .expect("click count")
                        .parse()
                        .expect("click count integer"),
                ),
            );
        }
    }
    assert_eq!(
        completion.complete_success(result, current_url),
        ServoCompletionDelivery::Queued
    );
}

fn product_result(mailbox: &Path, server: &ServerSummary, client: &ClientSummary) {
    let result = format!(
        concat!(
            "{{\n",
            "  \"schema\": \"trillionnium.desktop.s08-product-result.v1\",\n",
            "  \"status\": \"PASS_REAL_SERVO_AGENTPORT_BROWSERACTOR_RECEIPT_CHAIN\",\n",
            "  \"agent_port_requests\": {},\n",
            "  \"servo_runtime_commands\": {},\n",
            "  \"durable_receipt_records\": {},\n",
            "  \"all_responses_committed\": {},\n",
            "  \"unresolved_receipts\": {},\n",
            "  \"stale_document_rejected\": {},\n",
            "  \"retained_node_click_exactly_once\": {},\n",
            "  \"peer_identity_redacted\": true,\n",
            "  \"production_agent_port_enabled\": false,\n",
            "  \"installed_image_proven\": false,\n",
            "  \"physical_hardware_proven\": false,\n",
            "  \"release_proven\": false\n",
            "}}\n"
        ),
        server.evidence_count,
        EXPECTED_SERVO_COMMANDS,
        server.receipt_records,
        server.all_responses_committed,
        server.unresolved_receipts,
        client.stale_document_rejected,
        client.click_count_exactly_one,
    );
    let destination = mailbox.join("s08-product-result.json");
    let stage = mailbox.join(format!(".s08-product-result.{}.tmp", std::process::id()));
    fs::write(&stage, result).expect("write staged product result");
    fs::rename(stage, destination).expect("publish product result");
}

#[test]
fn real_servo_agent_port_browser_actor_receipt_chain() {
    let Some(mailbox) = std::env::var_os("HEPTA_S08_MAILBOX") else {
        return;
    };
    let mailbox = PathBuf::from(mailbox);
    assert!(
        mailbox.is_absolute(),
        "qualification mailbox must be absolute"
    );
    let metadata = fs::metadata(&mailbox).expect("qualification mailbox must exist");
    assert!(metadata.is_dir());
    assert_eq!(metadata.permissions().mode() & 0o777, 0o700);
    wait_for_file(&mailbox.join("servo-ready"), MAILBOX_BUDGET);

    let (first_url, second_url, fixture_stop, fixture_worker) = start_loopback_fixture();
    let state = TestDirectory::new("hepta-s08-product-state");
    let proc_root = state.0.join("proc");
    fs::create_dir(&proc_root).expect("create synthetic procfs root");
    fs::set_permissions(&proc_root, fs::Permissions::from_mode(0o700))
        .expect("protect synthetic procfs root");
    let receipt_root = mailbox.join("private-product-state").join("receipt-store");
    fs::create_dir(mailbox.join("private-product-state")).expect("create product state parent");
    fs::set_permissions(
        mailbox.join("private-product-state"),
        fs::Permissions::from_mode(0o700),
    )
    .expect("protect product state parent");

    let (server_streams, client_streams) = socket_pairs(EXPECTED_REQUESTS);
    let peer = PeerIdentity::from_stream(&server_streams[0]).expect("read server peer");
    let (endpoint, mut servo_owner) = servo_runtime_pair(Arc::new(|| {}));

    let server_proc_root = proc_root.clone();
    let server_receipt_root = receipt_root.clone();
    let server = thread::spawn(move || {
        let (attestor, attested, principal) = synthetic_attestation(&server_proc_root, peer);
        let actor =
            ServoBrowserActor::from_attested(principal, peer, &attestor, &attested, endpoint)
                .expect("construct sealed Servo actor");
        let journal =
            ReceiptJournal::create_managed(&server_receipt_root, JournalId([0x58; 16]), 1)
                .expect("create private managed receipt store");
        let mut observer = actor.receipt_observer(journal, "s08-exact-pin-host");
        let mut handler = AttestedServoHandler {
            actor,
            attestor,
            attested,
        };
        let mut evidence = Vec::with_capacity(EXPECTED_REQUESTS);
        for stream in server_streams {
            evidence.push(
                serve_one_with_observer(
                    stream,
                    PeerPolicy::exact(peer),
                    BUDGET,
                    &mut handler,
                    &mut observer,
                )
                .expect("serve one attested S08 request"),
            );
        }
        assert!(handler.actor.page_owner().is_none());
        let report = observer.inspect().expect("inspect complete receipt chain");
        assert_eq!(report.records.len(), EXPECTED_REQUESTS * 3);
        for rows in report.records.chunks_exact(3) {
            assert_eq!(rows[0].event.lifecycle, ReceiptLifecycleState::Requested);
            assert_eq!(rows[1].event.lifecycle, ReceiptLifecycleState::Dispatched);
            assert_eq!(rows[2].event.lifecycle, ReceiptLifecycleState::Completed);
        }
        ServerSummary {
            evidence_count: evidence.len(),
            receipt_records: report.records.len(),
            all_responses_committed: evidence.iter().all(|item| item.response_committed),
            unresolved_receipts: report.unresolved.len(),
        }
    });

    let client = thread::spawn(move || {
        let mut streams = client_streams.into_iter();
        let health = success(invoke(
            streams.next().unwrap(),
            request("health", None, None, BrowserOperation::Health),
        ));
        assert!(boolean(&health, "real_servo_adapter"));

        let created = success(invoke(
            streams.next().unwrap(),
            request(
                "create",
                None,
                None,
                BrowserOperation::SessionCreate {
                    profile: ProfileSpec {
                        profile_id: "s08-ephemeral".to_owned(),
                        persistence: ProfilePersistence::Ephemeral,
                    },
                    ui_mode: "headed".to_owned(),
                },
            ),
        ));
        let session_id = string(&created, "session_id");
        let session_generation = number(&created, "session_generation");
        let initial_document_generation = number(&created, "document_generation");

        let first_navigation = success(invoke(
            streams.next().unwrap(),
            request(
                "navigate-first",
                Some(&session_id),
                Some(session_generation),
                BrowserOperation::PageNavigate {
                    target: NavigationTarget::LocalHttpFixture { url: first_url },
                    expected_document_generation: initial_document_generation,
                },
            ),
        ));
        let first_document_generation = number(&first_navigation, "document_generation");
        assert!(first_document_generation > initial_document_generation);

        let observed = success(invoke(
            streams.next().unwrap(),
            request(
                "observe-target",
                Some(&session_id),
                Some(session_generation),
                BrowserOperation::PageObserve {
                    fields: vec![ObservationField::Role, ObservationField::Name],
                },
            ),
        ));
        let target = element_from_observation(&observed);
        assert_eq!(target.document_generation, first_document_generation);
        assert_eq!(target.accessible_name_sha256.as_deref(), Some(NAME_SHA256));
        assert_eq!(target.structural_fingerprint, STRUCTURAL_SHA256);

        let waited = success(invoke(
            streams.next().unwrap(),
            request(
                "wait-target",
                Some(&session_id),
                Some(session_generation),
                BrowserOperation::PageWait {
                    condition: WaitCondition::ElementPresent {
                        target: target.clone(),
                    },
                    timeout_ms: 10_000,
                },
            ),
        ));
        assert!(boolean(&waited, "element_present"));

        let clicked = success(invoke(
            streams.next().unwrap(),
            request(
                "click-target",
                Some(&session_id),
                Some(session_generation),
                BrowserOperation::PageAct {
                    target: target.clone(),
                    action: PageAction::Click,
                },
            ),
        ));
        let click_count_exactly_one = number(&clicked, "click_count") == 1;
        assert!(click_count_exactly_one);

        let snapshot = success(invoke(
            streams.next().unwrap(),
            request(
                "snapshot",
                Some(&session_id),
                Some(session_generation),
                BrowserOperation::SessionSnapshot,
            ),
        ));
        assert!(boolean(&snapshot, "real_servo"));
        assert_eq!(number(&snapshot, "click_count"), 1);

        let second_navigation = success(invoke(
            streams.next().unwrap(),
            request(
                "navigate-second",
                Some(&session_id),
                Some(session_generation),
                BrowserOperation::PageNavigate {
                    target: NavigationTarget::LocalHttpFixture { url: second_url },
                    expected_document_generation: first_document_generation,
                },
            ),
        ));
        assert!(number(&second_navigation, "document_generation") > first_document_generation);

        let stale = invoke(
            streams.next().unwrap(),
            request(
                "stale-click",
                Some(&session_id),
                Some(session_generation),
                BrowserOperation::PageAct {
                    target,
                    action: PageAction::Click,
                },
            ),
        );
        let stale_document_rejected = matches!(
            stale.outcome,
            Err(error) if error.code == BrowserErrorCode::StaleDocument
        );
        assert!(stale_document_rejected);

        let closed = success(invoke(
            streams.next().unwrap(),
            request(
                "close",
                Some(&session_id),
                Some(session_generation),
                BrowserOperation::SessionClose,
            ),
        ));
        assert!(boolean(&closed, "closed"));
        ClientSummary {
            stale_document_rejected,
            click_count_exactly_one,
        }
    });

    let mut runtime_commands = 0_usize;
    let deadline = Instant::now() + Duration::from_secs(300);
    while !server.is_finished() {
        assert!(Instant::now() < deadline, "S08 host vertical slice stalled");
        match servo_owner.pump_one() {
            ServoPumpResult::Idle => thread::sleep(Duration::from_millis(1)),
            ServoPumpResult::Pending => {
                if let Some(command) = servo_owner.take_command() {
                    runtime_commands += 1;
                    process_servo_command(&mailbox, runtime_commands, command);
                } else {
                    thread::yield_now();
                }
            }
            ServoPumpResult::Replied => {}
            ServoPumpResult::Retired => break,
        }
    }
    assert_eq!(runtime_commands, EXPECTED_SERVO_COMMANDS);
    let client = client.join().expect("client thread");
    let server = server.join().expect("server thread");
    assert_eq!(server.evidence_count, EXPECTED_REQUESTS);
    assert_eq!(server.receipt_records, EXPECTED_REQUESTS * 3);
    assert!(server.all_responses_committed);
    assert_eq!(server.unresolved_receipts, 0);
    product_result(&mailbox, &server, &client);

    wait_for_file(&mailbox.join("s08-servo-result.json"), MAILBOX_BUDGET);
    let servo_result =
        fs::read_to_string(mailbox.join("s08-servo-result.json")).expect("read Servo result");
    assert!(servo_result.contains("PASS_EXACT_PIN_REAL_SERVO"));
    assert!(servo_result.contains("retained_node_click_dispatched_exactly_once\": true"));
    assert!(servo_result.contains("installed_image_proven\": false"));

    fixture_stop.store(true, Ordering::SeqCst);
    fixture_worker.join().expect("loopback fixture thread");
}
