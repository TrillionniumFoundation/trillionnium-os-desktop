//! Ordinary host source regression: real AF_UNIX codec, pidfd and managed
//! journal, explicit synthetic procfs service/executable and callback fixture.
//! This proves profile admission behavior, never actual Servo or installed state.
use hepta_agent_transport::{ClientConnection, PeerIdentity, PeerPolicy};
use hepta_browser_actor::{
    ServoCompletionDelivery, ServoRuntimeOperation, TaskFlowPrincipal,
    closed_immutable_servo_runtime_pair,
};
use hepta_browser_codec::{
    BrowserErrorCode, BrowserOperation, BrowserRequest, ElementReference, JsonObject, JsonValue,
    NavigationTarget, ObservationField, PageAction, ProfilePersistence, ProfileSpec, WaitCondition,
    decode_response, encode_request,
};
use hepta_browserd::{
    AcceptedProductConnection, ProductRequestCoordinator, RestartPolicy, RuntimeState,
};
use hepta_peer_attestation::{PeerRuntimePolicy, ProcfsPeerAttestor};
use hepta_session_core::{JournalId, ManagedOpenPolicy, ReceiptJournal};
use std::fs;
use std::os::unix::fs::DirBuilderExt;
use std::os::unix::net::UnixStream;
use std::sync::{Arc, mpsc};
use std::thread;
use std::time::{Duration, Instant};
const BUDGET: Duration = Duration::from_secs(20);
#[test]
fn decoded_read_only_refusal_precedes_durable_admission_and_engine_command() {
    let root = std::env::temp_dir().join(format!("closed-profile-source-{}", std::process::id()));
    fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
    let process = root.join(std::process::id().to_string());
    fs::DirBuilder::new().mode(0o700).create(&process).unwrap();
    let (server, client) = UnixStream::pair().unwrap();
    let peer = PeerIdentity::from_stream(&server).unwrap();
    fs::write(
        process.join("status"),
        format!(
            "Uid:\t{0}\t{0}\t{0}\t{0}\nGid:\t{1}\t{1}\t{1}\t{1}\n",
            peer.uid, peer.gid
        ),
    )
    .unwrap();
    let mut fields = vec!["S"; 20];
    fields[19] = "987654";
    fs::write(
        process.join("stat"),
        format!(
            "{} (explicit-source-fixture) {}\n",
            std::process::id(),
            fields.join(" ")
        ),
    )
    .unwrap();
    fs::write(
        process.join("cgroup"),
        "0::/system.slice/explicit-source-fixture.service\n",
    )
    .unwrap();
    fs::write(process.join("exe"), b"explicit-source-fixture-not-servo").unwrap();
    let attestor = ProcfsPeerAttestor::new(&root);
    let snapshot = attestor.read_snapshot(peer.pid.unwrap()).unwrap();
    let policy = PeerRuntimePolicy::exact(&snapshot);
    let principal = TaskFlowPrincipal {
        principal_id: "closed-source-fixture".into(),
        expected_uid: peer.uid,
        expected_gid: peer.gid,
        expected_systemd_unit: snapshot.systemd_unit.clone().unwrap(),
        expected_cgroup_v2_path: snapshot.cgroup_v2_path,
        expected_executable_sha256: snapshot.executable_sha256,
    };
    let bootstrap =
        AcceptedProductConnection::attest(server, attestor.clone(), &policy, BUDGET).unwrap();
    let (endpoint, mut owner) = closed_immutable_servo_runtime_pair(Arc::new(|| {}));
    let (sender, receiver) = mpsc::sync_channel::<AcceptedProductConnection>(1);
    let journal_path = root.join("journal");
    let worker_path = journal_path.clone();
    let worker = thread::spawn(move || {
        let journal =
            ReceiptJournal::create_managed(worker_path, JournalId([0x55; 16]), 1).unwrap();
        let mut coordinator = ProductRequestCoordinator::from_connection(
            principal,
            &bootstrap,
            endpoint,
            journal,
            "source-fixture".into(),
            RestartPolicy::new(1).unwrap(),
        )
        .unwrap();
        let mut evidence = vec![coordinator.serve_connection(bootstrap).unwrap()];
        for connection in receiver {
            evidence.push(coordinator.serve_connection(connection).unwrap());
        }
        assert_eq!(coordinator.state(), RuntimeState::Ready);
        evidence
    });
    let mut commands = Vec::new();
    let mut invoke = |request: BrowserRequest, first: Option<UnixStream>| {
        let stream = first.unwrap_or_else(|| {
            let (server, client) = UnixStream::pair().unwrap();
            sender
                .send(
                    AcceptedProductConnection::attest(server, attestor.clone(), &policy, BUDGET)
                        .unwrap(),
                )
                .unwrap();
            client
        });
        let caller = thread::spawn(move || {
            let peer = PeerIdentity::from_stream(&stream).unwrap();
            let mut client =
                ClientConnection::connect(stream, PeerPolicy::exact(peer), BUDGET).unwrap();
            let sequence = client
                .send_request(encode_request(&request).unwrap(), BUDGET)
                .unwrap();
            decode_response(&client.receive_response(sequence, BUDGET).unwrap())
                .unwrap()
                .value
        });
        let stop = Instant::now() + BUDGET;
        while !caller.is_finished() {
            assert!(Instant::now() < stop);
            let _ = owner.pump_one();
            if let Some(command) = owner.take_command() {
                let (_, operation, completion) = command.into_parts();
                assert!(matches!(
                    operation,
                    ServoRuntimeOperation::Health
                        | ServoRuntimeOperation::CreateSession { .. }
                        | ServoRuntimeOperation::Observe { .. }
                ));
                commands.push(operation);
                let mut result = JsonObject::new();
                result.insert("source_callback_fixture".into(), JsonValue::Bool(true));
                assert_eq!(
                    completion.complete_success(result, Some("about:blank".into())),
                    ServoCompletionDelivery::Queued
                );
            }
            thread::sleep(Duration::from_millis(1));
        }
        caller.join().unwrap()
    };
    let request = |id: &str, session: Option<(&str, u64)>, operation| BrowserRequest {
        request_id: id.into(),
        session_id: session.map(|v| v.0.into()),
        session_generation: session.map(|v| v.1),
        deadline_unix_ms: None,
        operation,
    };
    assert!(
        invoke(
            request("health", None, BrowserOperation::Health),
            Some(client)
        )
        .outcome
        .is_ok()
    );
    let created = invoke(
        request(
            "create",
            None,
            BrowserOperation::SessionCreate {
                profile: ProfileSpec {
                    profile_id: "immutable-read-only-v1".into(),
                    persistence: ProfilePersistence::Ephemeral,
                },
                ui_mode: "headed".into(),
            },
        ),
        None,
    )
    .outcome
    .unwrap();
    let JsonValue::String(session) = created.get("session_id").unwrap() else {
        panic!("session");
    };
    let JsonValue::Integer(generation) = created.get("session_generation").unwrap() else {
        panic!("generation");
    };
    let observed = invoke(
        request(
            "observe",
            Some((session, *generation as u64)),
            BrowserOperation::PageObserve {
                fields: vec![ObservationField::Role],
            },
        ),
        None,
    )
    .outcome
    .unwrap();
    let JsonValue::Integer(revision) = observed.get("semantic_snapshot_revision").unwrap() else {
        panic!("revision");
    };
    let target = ElementReference {
        session_generation: *generation as u64,
        document_generation: 1,
        semantic_snapshot_revision: *revision as u64,
        frame_id: "valid-but-unsupported".into(),
        backend_node_key: None,
        role: None,
        accessible_name_sha256: None,
        structural_fingerprint: "a".repeat(64),
    };
    for (id, operation) in [
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
                schema_id: "not-admitted".into(),
            },
        ),
        (
            "wait",
            BrowserOperation::PageWait {
                condition: WaitCondition::DocumentReady,
                timeout_ms: 1,
            },
        ),
    ] {
        let response = invoke(
            request(id, Some((session, *generation as u64)), operation),
            None,
        );
        assert_eq!(
            response.outcome.unwrap_err().code,
            BrowserErrorCode::Unsupported
        );
    }
    drop(sender);
    let evidence = worker.join().unwrap();
    assert_eq!(commands.len(), 3);
    assert_eq!(evidence.len(), 7);
    let mut journal = ReceiptJournal::open_managed(
        &journal_path,
        JournalId([0x55; 16]),
        ManagedOpenPolicy::STRICT,
    )
    .unwrap();
    assert!(!journal.has_unresolved_receipts().unwrap());
    for evidence in &evidence[3..] {
        assert!(!evidence.response_ok && evidence.response_committed);
        assert!(!journal.contains_receipt(&evidence.request_id).unwrap());
    }
    drop(journal);
    fs::remove_dir_all(root).unwrap();
}
