//! The target tests the SAME reusable actual native adapter. The explicitly
//! approved same-UID transient-unit test policy is not production provisioning.
//! Run each test name in a fresh process: Servo initializes global state once.
mod common;
#[path = "trillionnium_native_owner.rs"]
mod native_owner;
use hepta_agent_transport::{ClientConnection, PeerIdentity, PeerPolicy};
use hepta_browser_actor::{TaskFlowPrincipal, scoped_frame_id};
use hepta_browser_codec::{
    BrowserErrorCode, BrowserOperation, BrowserRequest, BrowserResponse, ElementReference,
    JsonValue, NavigationTarget, ObservationField, PageAction, ProfilePersistence, ProfileSpec,
    WaitCondition, decode_response, encode_request,
};
use hepta_browserd::{
    AcceptedProductConnection, ProductRequestCoordinator, RestartPolicy, RuntimeState,
    product_connection_queue,
};
use hepta_peer_attestation::{PeerRuntimePolicy, ProcfsPeerAttestor};
use hepta_session_core::{JournalId, ManagedOpenPolicy, ReceiptJournal, ReceiptLifecycleState};
use native_owner::{ClosedImmutableNativeOwner, IMMUTABLE_PROFILE};
use std::fs;
use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::sync::{Arc, mpsc};
use std::thread;
use std::time::{Duration, Instant};
const BUDGET: Duration = Duration::from_secs(20);

fn approved_policy() -> (PeerRuntimePolicy, TaskFlowPrincipal) {
    // This tuple is supplied by the test launcher BEFORE the process starts.
    // Do not convert freshly observed process facts into approved authority.
    let env =
        |key: &str| std::env::var(key).expect("externally supplied explicit qualification policy");
    let uid = env("HEPTA_OWNER_EXPECTED_UID").parse::<u32>().unwrap();
    let gid = env("HEPTA_OWNER_EXPECTED_GID").parse::<u32>().unwrap();
    let unit = env("HEPTA_OWNER_EXPECTED_UNIT");
    let policy = PeerRuntimePolicy::for_system_service(uid, gid, &unit).unwrap();
    let principal = TaskFlowPrincipal {
        principal_id: "explicit-native-owner-qualification".into(),
        expected_uid: uid,
        expected_gid: gid,
        expected_systemd_unit: unit,
        expected_cgroup_v2_path: policy.expected_cgroup_v2_path.clone(),
        expected_executable_sha256: env("HEPTA_OWNER_EXPECTED_EXE_SHA256"),
    };
    (policy, principal)
}
fn private_case(name: &str) -> PathBuf {
    let root = PathBuf::from(std::env::var("HEPTA_OWNER_OUTPUT").expect("owned test output"));
    assert!(root.is_absolute());
    let metadata = fs::symlink_metadata(&root).unwrap();
    assert!(
        metadata.is_dir()
            && !metadata.file_type().is_symlink()
            && metadata.permissions().mode() & 0o777 == 0o700
    );
    let path = root.join(name);
    fs::DirBuilder::new().mode(0o700).create(&path).unwrap();
    path
}
fn request(id: &str, binding: Option<(&str, u64)>, operation: BrowserOperation) -> BrowserRequest {
    BrowserRequest {
        request_id: id.into(),
        session_id: binding.map(|v| v.0.into()),
        session_generation: binding.map(|v| v.1),
        deadline_unix_ms: None,
        operation,
    }
}
fn integer(result: &hepta_browser_codec::JsonObject, key: &str) -> u64 {
    match result.get(key).unwrap() {
        JsonValue::Integer(v) => u64::try_from(*v).unwrap(),
        _ => panic!("exact integer"),
    }
}
fn string<'a>(result: &'a hepta_browser_codec::JsonObject, key: &str) -> &'a str {
    match result.get(key).unwrap() {
        JsonValue::String(v) => v,
        _ => panic!("exact string"),
    }
}
fn digest(hex: &str) -> [u8; 32] {
    assert_eq!(hex.len(), 64);
    let mut result = [0; 32];
    for (i, pair) in hex.as_bytes().chunks_exact(2).enumerate() {
        result[i] = u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap();
    }
    result
}
struct Driver {
    native: ClosedImmutableNativeOwner,
    policy: PeerRuntimePolicy,
    ingress: Option<hepta_browserd::ProductConnectionIngress>,
    worker: Option<thread::JoinHandle<(Vec<hepta_agent_port::ServiceEvidence>, RuntimeState)>>,
    journal: PathBuf,
}
impl Driver {
    fn new(case: &Path) -> (Self, UnixStream) {
        let (policy, principal) = approved_policy();
        let servo = common::ServoTest::new_with_builder(|builder| {
            let mut preferences = servo::Preferences::default();
            preferences.accessibility_enabled = true;
            preferences.network_http_proxy_uri.clear();
            preferences.network_https_proxy_uri.clear();
            builder.preferences(preferences)
        });
        let (endpoint, native) = ClosedImmutableNativeOwner::new(
            servo.servo.clone(),
            servo.rendering_context.clone(),
            Arc::new(|| {}),
        );
        // The adapter owns the engine instance after this helper handle drops.
        drop(servo);
        let (server, client) = UnixStream::pair().unwrap();
        let bootstrap = AcceptedProductConnection::attest(
            server,
            ProcfsPeerAttestor::default(),
            &policy,
            BUDGET,
        )
        .unwrap();
        let (ingress, queue) = product_connection_queue(1).unwrap();
        let journal = case.join("journal");
        let worker_path = journal.clone();
        let worker = thread::spawn(move || {
            let journal =
                ReceiptJournal::create_managed(&worker_path, JournalId([0x61; 16]), 1).unwrap();
            let mut coordinator = ProductRequestCoordinator::from_connection(
                principal,
                &bootstrap,
                endpoint,
                journal,
                "source-only-immutable-owner".into(),
                RestartPolicy::new(1).unwrap(),
            )
            .unwrap();
            let mut evidence = vec![coordinator.serve_connection(bootstrap).unwrap()];
            loop {
                match queue.try_next() {
                    Ok(Some(connection)) => {
                        evidence.push(coordinator.serve_connection(connection).unwrap())
                    },
                    Ok(None) => thread::sleep(Duration::from_millis(1)),
                    Err(hepta_browserd::ProductDispatchError::Closed) => break,
                    Err(error) => panic!("owned queue: {error:?}"),
                }
            }
            (evidence, coordinator.state())
        });
        (
            Self {
                native,
                policy,
                ingress: Some(ingress),
                worker: Some(worker),
                journal,
            },
            client,
        )
    }
    fn invoke(&mut self, input: BrowserRequest, first: Option<UnixStream>) -> BrowserResponse {
        let stop = Instant::now().checked_add(BUDGET).unwrap();
        let client = if let Some(first) = first {
            first
        } else {
            let (server, client) = UnixStream::pair().unwrap();
            let connection = AcceptedProductConnection::attest(
                server,
                ProcfsPeerAttestor::default(),
                &self.policy,
                BUDGET,
            )
            .unwrap();
            self.ingress
                .as_ref()
                .unwrap()
                .try_submit(connection)
                .unwrap();
            client
        };
        let (sender, receiver) = mpsc::sync_channel(1);
        let client_worker = thread::spawn(move || {
            let remaining = || {
                stop.checked_duration_since(Instant::now())
                    .filter(|v| !v.is_zero())
                    .unwrap()
            };
            let peer = PeerIdentity::from_stream(&client).unwrap();
            let mut client =
                ClientConnection::connect(client, PeerPolicy::exact(peer), remaining()).unwrap();
            let sequence = client
                .send_request(encode_request(&input).unwrap(), remaining())
                .unwrap();
            let response = client.receive_response(sequence, remaining()).unwrap();
            sender
                .send(decode_response(&response).unwrap().value)
                .unwrap();
        });
        let response = loop {
            match receiver.try_recv() {
                Ok(response) => break response,
                Err(mpsc::TryRecvError::Disconnected) => panic!("client failed"),
                Err(mpsc::TryRecvError::Empty) => (),
            }
            assert!(Instant::now() < stop, "original request budget expired");
            let _ = self.native.drive().unwrap();
            let sleep = self
                .native
                .next_wake_deadline()
                .unwrap()
                .map(|deadline| deadline.saturating_duration_since(Instant::now()))
                .unwrap_or(Duration::from_millis(1))
                .min(Duration::from_millis(1));
            thread::sleep(sleep);
        };
        client_worker.join().unwrap();
        response
    }
    fn finish(
        mut self,
    ) -> (
        Vec<hepta_agent_port::ServiceEvidence>,
        RuntimeState,
        ReceiptJournal,
    ) {
        drop(self.ingress.take());
        let worker = self.worker.take().unwrap();
        let stop = Instant::now() + BUDGET;
        while !worker.is_finished() {
            assert!(Instant::now() < stop);
            let _ = self.native.drive().unwrap();
            thread::sleep(Duration::from_millis(1));
        }
        let (evidence, state) = worker.join().unwrap();
        let journal = ReceiptJournal::open_managed(
            &self.journal,
            JournalId([0x61; 16]),
            ManagedOpenPolicy::STRICT,
        )
        .unwrap();
        (evidence, state, journal)
    }
}
fn create(driver: &mut Driver) -> (String, u64, hepta_browser_codec::JsonObject) {
    let result = driver
        .invoke(
            request(
                "create",
                None,
                BrowserOperation::SessionCreate {
                    profile: ProfileSpec {
                        profile_id: IMMUTABLE_PROFILE.into(),
                        persistence: ProfilePersistence::Ephemeral,
                    },
                    ui_mode: "headed".into(),
                },
            ),
            None,
        )
        .outcome
        .unwrap();
    assert!(matches!(result.get("nodes"), Some(JsonValue::Array(v)) if !v.is_empty()));
    assert!(string(&result, "document_tree_id") != "00000000-0000-0000-0000-000000000000");
    (
        string(&result, "session_id").into(),
        integer(&result, "session_generation"),
        result,
    )
}
fn start(name: &str) -> Driver {
    let case = private_case(name);
    let (mut driver, first) = Driver::new(&case);
    let health = driver.invoke(
        request("health", None, BrowserOperation::Health),
        Some(first),
    );
    assert_eq!(
        string(&health.outcome.unwrap(), "runtime"),
        "actual-servo-immutable-owner"
    );
    driver
}
#[test]
fn actual_connected_immutable_semantic_snapshot() {
    let mut driver = start("positive");
    let (session, generation, created) = create(&mut driver);
    let observed = driver
        .invoke(
            request(
                "observe",
                Some((&session, generation)),
                BrowserOperation::PageObserve {
                    fields: vec![
                        ObservationField::Role,
                        ObservationField::Name,
                        ObservationField::Text,
                        ObservationField::Href,
                        ObservationField::Bounds,
                    ],
                },
            ),
            None,
        )
        .outcome
        .unwrap();
    let snapshot = driver
        .invoke(
            request(
                "snapshot",
                Some((&session, generation)),
                BrowserOperation::SessionSnapshot,
            ),
            None,
        )
        .outcome
        .unwrap();
    for key in ["native_webview_id", "document_tree_id"] {
        assert_eq!(created.get(key), observed.get(key));
        assert_eq!(observed.get(key), snapshot.get(key));
    }
    let JsonValue::Array(nodes) = observed.get("nodes").unwrap() else {
        panic!("actual nodes");
    };
    assert!(nodes.iter().any(|node| matches!(node, JsonValue::Object(item) if item.get("role")==Some(&JsonValue::String("Heading".into())) && item.get("name")==Some(&JsonValue::String("Owned semantic document".into())))));
    let (evidence, state, mut journal) = driver.finish();
    assert_eq!(evidence.len(), 4);
    assert_eq!(state, RuntimeState::Ready);
    assert!(!journal.has_unresolved_receipts().unwrap());
    for item in evidence {
        assert!(item.response_ok && item.response_committed);
        assert_eq!(
            journal
                .receipt_fact(&item.request_id, digest(&item.request_sha256))
                .unwrap()
                .lifecycle()
                .unwrap(),
            ReceiptLifecycleState::Completed
        );
    }
    println!(
        "ACTUAL_NATIVE_OWNER positive: original connected codec, live procfs/pidfd, same real WebView/document/tree and managed completion"
    );
}
#[test]
fn unsupported_operations_never_enter_durable_or_native_dispatch() {
    let mut driver = start("unsupported");
    let (session, generation, _) = create(&mut driver);
    let observed = driver
        .invoke(
            request(
                "observe",
                Some((&session, generation)),
                BrowserOperation::PageObserve {
                    fields: vec![ObservationField::Role],
                },
            ),
            None,
        )
        .outcome
        .unwrap();
    let target = ElementReference {
        session_generation: generation,
        document_generation: integer(&observed, "document_generation"),
        semantic_snapshot_revision: integer(&observed, "semantic_snapshot_revision"),
        frame_id: scoped_frame_id(&session, string(&observed, "webview_token"), "top").unwrap(),
        backend_node_key: Some("unsupported-actual-node-not-used".into()),
        role: Some("button".into()),
        accessible_name_sha256: Some("a".repeat(64)),
        structural_fingerprint: "b".repeat(64),
    };
    let denied = [
        (
            "navigate",
            BrowserOperation::PageNavigate {
                target: NavigationTarget::LocalHttpFixture {
                    url: "http://127.0.0.1:1234/".into(),
                },
                expected_document_generation: 1,
            },
        ),
        (
            "act",
            BrowserOperation::PageAct {
                target,
                action: PageAction::Click,
            },
        ),
        (
            "extract",
            BrowserOperation::PageExtract {
                schema_id: "arbitrary".into(),
            },
        ),
        (
            "wait",
            BrowserOperation::PageWait {
                condition: WaitCondition::DocumentReady,
                timeout_ms: 1,
            },
        ),
    ];
    for (id, operation) in denied {
        assert_eq!(
            driver
                .invoke(request(id, Some((&session, generation)), operation), None)
                .outcome
                .unwrap_err()
                .code,
            BrowserErrorCode::Unsupported
        );
    }
    let wrong = driver.invoke(
        request(
            "stale",
            Some((&session, generation + 1)),
            BrowserOperation::SessionSnapshot,
        ),
        None,
    );
    assert_eq!(
        wrong.outcome.unwrap_err().code,
        BrowserErrorCode::StaleSession
    );
    let (evidence, state, mut journal) = driver.finish();
    assert_eq!(state, RuntimeState::Ready);
    assert_eq!(evidence.len(), 8);
    for item in evidence.iter().filter(|item| !item.response_ok) {
        assert!(!journal.contains_receipt(&item.request_id).unwrap());
    }
    println!(
        "ACTUAL_NATIVE_OWNER unsupported: original four operations plus stale binding refused without durable admission"
    );
}
#[test]
fn native_handle_release_is_uncertain_and_blocks_reconstruction() {
    let mut driver = start("uncertain-close");
    let (session, generation, _) = create(&mut driver);
    let close = driver.invoke(
        request(
            "close",
            Some((&session, generation)),
            BrowserOperation::SessionClose,
        ),
        None,
    );
    assert!(matches!(
        close.outcome.unwrap_err().code,
        BrowserErrorCode::BrowserCrashed | BrowserErrorCode::Indeterminate
    ));
    assert_eq!(
        driver.native.drive().unwrap(),
        native_owner::NativeDrive::Retired
    );
    let (evidence, state, mut journal) = driver.finish();
    assert_eq!(state, RuntimeState::ReplayReconciliationRequired);
    let item = evidence.last().unwrap();
    assert_eq!(item.request_id, "close");
    assert!(!item.response_ok);
    assert_eq!(
        journal
            .receipt_fact("close", digest(&item.request_sha256))
            .unwrap()
            .lifecycle()
            .unwrap(),
        ReceiptLifecycleState::Indeterminate
    );
    println!(
        "ACTUAL_NATIVE_OWNER close: no pipeline retirement confirmation, durable uncertain history, no replay"
    );
}
#[test]
fn wrong_live_policy_and_cancelled_original_connection_refuse_admission() {
    let _case = private_case("custody-negative");
    let (policy, _) = approved_policy();
    let (server, _client) = UnixStream::pair().unwrap();
    let mut wrong = policy.clone();
    wrong.expected_uid = wrong.expected_uid.checked_add(1).unwrap();
    assert!(
        AcceptedProductConnection::attest(server, ProcfsPeerAttestor::default(), &wrong, BUDGET)
            .is_err()
    );
    let (server, _client) = UnixStream::pair().unwrap();
    let connection =
        AcceptedProductConnection::attest(server, ProcfsPeerAttestor::default(), &policy, BUDGET)
            .unwrap();
    let deadline = connection.deadline().unwrap();
    connection.cancellation().cancel();
    assert!(connection.deadline().is_err());
    assert!(deadline > Instant::now());
    let (server, _client) = UnixStream::pair().unwrap();
    assert!(
        AcceptedProductConnection::attest(
            server,
            ProcfsPeerAttestor::default(),
            &policy,
            Duration::from_nanos(1)
        )
        .is_err()
    );
    println!(
        "ACTUAL_NATIVE_OWNER custody: live policy, original cancellation and expiry refusal; no Servo effect"
    );
}
