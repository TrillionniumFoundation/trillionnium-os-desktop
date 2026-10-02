//! Host composition tests use real AF_UNIX framing and pidfds with explicitly
//! synthetic procfs facts and controlled completion callbacks. They do not
//! qualify an upstream Servo renderer, a service installation, or hardware.
use super::*;
use hepta_agent_transport::ClientConnection;
use hepta_browser_actor::{ServoRuntimeOperation, servo_runtime_pair};
use hepta_browser_codec::{
    BrowserOperation, JsonObject, JsonValue, NavigationTarget, ProfilePersistence, ProfileSpec,
    decode_response, encode_request,
};
use hepta_session_core::{
    JournalId, ManagedOpenPolicy, PrivacyClass, ReceiptEffectClass, ReceiptEvent, ReceiptSource,
};
use std::fs;
use std::io::Read;
use std::os::unix::fs::DirBuilderExt;
use std::path::PathBuf;
use std::sync::atomic::AtomicU64;
use std::thread;

static NEXT: AtomicU64 = AtomicU64::new(0);
const BUDGET: Duration = Duration::from_secs(5);

struct Fixture {
    root: PathBuf,
    attestor: ProcfsPeerAttestor,
    policy: PeerRuntimePolicy,
    principal: TaskFlowPrincipal,
}
impl Fixture {
    fn new() -> Self {
        let root = std::env::temp_dir().join(format!(
            "hepta-product-dispatch-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::SeqCst)
        ));
        fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
        let proc_root = root.join("proc");
        fs::create_dir(&proc_root).unwrap();
        let (stream, _other) = UnixStream::pair().unwrap();
        let peer = PeerIdentity::from_stream(&stream).unwrap();
        let pid = peer.pid.unwrap();
        let process = proc_root.join(pid.to_string());
        fs::create_dir(&process).unwrap();
        fs::write(
            process.join("status"),
            format!(
                "Uid:\t{0}\t{0}\t{0}\t{0}\nGid:\t{1}\t{1}\t{1}\t{1}\n",
                peer.uid, peer.gid
            ),
        )
        .unwrap();
        let mut stat = vec!["S"; 20];
        stat[19] = "987654";
        fs::write(
            process.join("stat"),
            format!("{pid} (composition-test) {}\n", stat.join(" ")),
        )
        .unwrap();
        fs::write(
            process.join("cgroup"),
            "0::/system.slice/composition-test.service\n",
        )
        .unwrap();
        fs::write(
            process.join("exe"),
            b"explicitly-synthetic-composition-executable",
        )
        .unwrap();
        let attestor = ProcfsPeerAttestor::new(proc_root);
        let snapshot = attestor.read_snapshot(pid).unwrap();
        let principal = TaskFlowPrincipal {
            principal_id: "composition-test-principal".into(),
            expected_uid: peer.uid,
            expected_gid: peer.gid,
            expected_systemd_unit: snapshot.systemd_unit.clone().unwrap(),
            expected_cgroup_v2_path: snapshot.cgroup_v2_path.clone(),
            expected_executable_sha256: snapshot.executable_sha256.clone(),
        };
        Self {
            root,
            attestor,
            policy: PeerRuntimePolicy::exact(&snapshot),
            principal,
        }
    }
    fn connection(&self) -> (AcceptedProductConnection, UnixStream) {
        let (server, client) = UnixStream::pair().unwrap();
        let accepted =
            AcceptedProductConnection::attest(server, self.attestor.clone(), &self.policy, BUDGET)
                .unwrap();
        (accepted, client)
    }
    fn journal(&self) -> ReceiptJournal {
        ReceiptJournal::create_managed(self.root.join("receipts"), JournalId([0x61; 16]), 1)
            .unwrap()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

#[derive(Clone, Copy)]
enum Plan {
    Health(&'static str),
    Create(&'static str),
    Navigate(&'static str),
    Stale,
}
impl Plan {
    fn request(self, session: &Option<(String, u64)>) -> BrowserRequest {
        let (id, operation, bound) = match self {
            Self::Health(id) => (id, BrowserOperation::Health, false),
            Self::Create(id) => (
                id,
                BrowserOperation::SessionCreate {
                    profile: ProfileSpec {
                        persistence: ProfilePersistence::Ephemeral,
                        profile_id: "source-test".into(),
                    },
                    ui_mode: "headed".into(),
                },
                false,
            ),
            Self::Navigate(id) => (
                id,
                BrowserOperation::PageNavigate {
                    target: NavigationTarget::LocalHttpFixture {
                        url: "http://127.0.0.1:8080/source-test".into(),
                    },
                    expected_document_generation: 1,
                },
                true,
            ),
            Self::Stale => ("stale", BrowserOperation::SessionSnapshot, true),
        };
        let (session_id, generation) = if bound {
            session.clone().unwrap_or(("foreign-session".into(), 1))
        } else {
            (String::new(), 0)
        };
        BrowserRequest {
            request_id: id.into(),
            session_id: bound.then_some(session_id),
            session_generation: bound.then_some(generation),
            deadline_unix_ms: None,
            operation,
        }
    }
}
#[derive(Clone, Copy, PartialEq, Eq)]
enum Fault {
    None,
    TerminalStorage,
    UnknownNavigation,
    LostResponse,
    CancelAtNativeBoundary,
}
struct Summary {
    results: Vec<Result<ServiceEvidence, ProductDispatchError>>,
    responses: Vec<Option<BrowserResponse>>,
    records: usize,
    state: RuntimeState,
    commands: usize,
    reconciled: bool,
}

fn run(plans: &[Plan], fault: Fault) -> Summary {
    let fixture = Fixture::new();
    let (endpoint, mut owner) = servo_runtime_pair(Arc::new(|| {}));
    let journal = fixture.journal();
    let mut accepted = Vec::new();
    let mut clients = Vec::new();
    for _ in plans {
        let (connection, client) = fixture.connection();
        accepted.push(connection);
        clients.push(client);
    }
    let cancellations: Vec<_> = accepted
        .iter()
        .map(AcceptedProductConnection::cancellation)
        .collect();
    let principal = fixture.principal.clone();
    let worker = thread::spawn(move || {
        let mut coordinator = ProductRequestCoordinator::from_connection(
            principal,
            &accepted[0],
            endpoint,
            journal,
            "image-source-test".into(),
            RestartPolicy::new(3).unwrap(),
        )
        .unwrap();
        let results: Vec<_> = accepted
            .into_iter()
            .map(|connection| coordinator.serve_connection(connection))
            .collect();
        let mut reconciled = false;
        if fault == Fault::UnknownNavigation {
            let pending = coordinator
                .pending_reconciliation
                .clone()
                .expect("unknown outcome must latch admission");
            assert_eq!(
                coordinator
                    .reconcile_request("different-request", pending.digest)
                    .err(),
                Some(ProductDispatchError::RecoveryRequired)
            );
            assert_eq!(
                coordinator.reconcile_request(&pending.id, [0x99; 32]).err(),
                Some(ProductDispatchError::RecoveryRequired)
            );
            let fact = coordinator
                .reconcile_request(&pending.id, pending.digest)
                .unwrap();
            assert_eq!(fact.lifecycle(), ReceiptLifecycleState::Indeterminate);
            assert_eq!(fact.receipt_id(), pending.id);
            reconciled = true;
        }
        let records = coordinator
            .observer
            .borrow_mut()
            .as_mut()
            .unwrap()
            .inspect()
            .map(|report| report.records.len())
            .unwrap_or(0);
        (results, records, coordinator.state(), reconciled)
    });
    let plans = plans.to_vec();
    let client = thread::spawn(move || {
        let mut session = None;
        let mut responses = Vec::new();
        for (index, (stream, plan)) in clients.into_iter().zip(plans).enumerate() {
            let interrupt = stream.try_clone().unwrap();
            let peer = PeerIdentity::from_stream(&stream).unwrap();
            let mut client =
                match ClientConnection::connect(stream, PeerPolicy::exact(peer), BUDGET) {
                    Ok(client) => client,
                    Err(_) => {
                        responses.push(None);
                        continue;
                    }
                };
            let request = plan.request(&session);
            let sequence = client
                .send_request(encode_request(&request).unwrap(), BUDGET)
                .unwrap();
            if fault == Fault::LostResponse && index == 0 {
                interrupt.shutdown(Shutdown::Both).unwrap();
                responses.push(None);
                continue;
            }
            let response = client
                .receive_response(sequence, BUDGET)
                .ok()
                .map(|frame| decode_response(&frame).unwrap().value);
            if let Some(BrowserResponse {
                outcome: Ok(result),
                ..
            }) = response.as_ref()
                && let (Some(JsonValue::String(id)), Some(JsonValue::Integer(generation))) =
                    (result.get("session_id"), result.get("session_generation"))
            {
                session = Some((id.clone(), *generation as u64));
            }
            responses.push(response);
        }
        responses
    });
    let stop = Instant::now() + BUDGET;
    let mut commands = 0;
    while !worker.is_finished() {
        owner.pump_one();
        if let Some(command) = owner.take_command() {
            commands += 1;
            let (_, operation, completion) = command.into_parts();
            if fault == Fault::CancelAtNativeBoundary {
                cancellations[0].cancel();
                assert_eq!(
                    completion.ensure_current_peer(),
                    Err(hepta_browser_actor::ServoRuntimeError::Cancelled)
                );
                completion.complete_error(hepta_browser_actor::ServoRuntimeError::Cancelled);
                continue;
            }
            completion.ensure_current_peer().unwrap();
            if fault == Fault::TerminalStorage {
                let path = fixture
                    .root
                    .join("receipts/segment-0000000000000001.journal");
                fs::rename(&path, fixture.root.join("preserved.journal")).unwrap();
                fs::write(path, b"substituted-authority-path").unwrap();
            }
            if fault == Fault::UnknownNavigation
                && matches!(operation, ServoRuntimeOperation::Navigate { .. })
            {
                completion.complete_error(hepta_browser_actor::ServoRuntimeError::Internal(
                    "controlled engine completion loss",
                ));
            } else {
                completion.complete_success(JsonObject::new(), None);
            }
        }
        assert!(
            Instant::now() < stop,
            "composition source test exceeded its fixed budget"
        );
        thread::sleep(Duration::from_millis(1));
    }
    let (results, records, state, reconciled) = worker.join().unwrap();
    Summary {
        results,
        records,
        state,
        reconciled,
        commands,
        responses: client.join().unwrap(),
    }
}

#[test]
fn terminal_receipt_precedes_response_and_duplicate_never_reexecutes() {
    let result = run(
        &[Plan::Health("same-request"), Plan::Health("same-request")],
        Fault::None,
    );
    assert!(result.results.iter().all(Result::is_ok));
    assert_eq!(result.commands, 1);
    assert_eq!(result.records, 3);
    assert!(result.responses[0].as_ref().unwrap().outcome.is_ok());
    assert_eq!(
        result.responses[1]
            .as_ref()
            .unwrap()
            .outcome
            .as_ref()
            .unwrap_err()
            .code,
        BrowserErrorCode::PolicyDenied
    );
    assert_eq!(result.state, RuntimeState::Ready);
}

#[test]
fn stale_session_is_refused_before_any_admitted_fact_or_engine_command() {
    let result = run(&[Plan::Stale], Fault::None);
    assert_eq!(result.commands, 0);
    assert_eq!(result.records, 0);
    assert_eq!(
        result.responses[0]
            .as_ref()
            .unwrap()
            .outcome
            .as_ref()
            .unwrap_err()
            .code,
        BrowserErrorCode::StaleSession
    );
}

#[test]
fn engine_success_with_terminal_storage_loss_never_publishes_success() {
    let result = run(
        &[Plan::Health("storage-cut"), Plan::Health("blocked-next")],
        Fault::TerminalStorage,
    );
    assert_eq!(result.commands, 1);
    assert_eq!(
        result.results[0].as_ref().err(),
        Some(&ProductDispatchError::StorageUnavailable)
    );
    assert_eq!(
        result.results[1].as_ref().err(),
        Some(&ProductDispatchError::StorageUnavailable)
    );
    assert!(result.responses.iter().all(Option::is_none));
    assert_eq!(result.state, RuntimeState::ReplayReconciliationRequired);
}

#[test]
fn lost_response_preserves_terminal_history_and_refuses_original_request_replay() {
    let result = run(
        &[Plan::Health("lost-response"), Plan::Health("lost-response")],
        Fault::LostResponse,
    );
    assert_eq!(result.commands, 1);
    assert_eq!(result.records, 3);
    assert!(result.results[0].is_err());
    assert_eq!(
        result.responses[1]
            .as_ref()
            .unwrap()
            .outcome
            .as_ref()
            .unwrap_err()
            .code,
        BrowserErrorCode::PolicyDenied
    );
    assert_eq!(result.state, RuntimeState::Ready);
}

#[test]
fn unknown_execution_blocks_next_request_until_exact_durable_reconciliation() {
    let result = run(
        &[
            Plan::Create("create"),
            Plan::Navigate("uncertain-navigation"),
            Plan::Health("blocked"),
        ],
        Fault::UnknownNavigation,
    );
    assert_eq!(result.commands, 2);
    assert_eq!(result.records, 6);
    assert_eq!(
        result.results[2].as_ref().err(),
        Some(&ProductDispatchError::RecoveryRequired)
    );
    assert!(result.reconciled);
    assert_eq!(result.state, RuntimeState::Ready);
}

#[test]
fn queue_is_bounded_and_queued_cancellation_closes_without_handshake() {
    let fixture = Fixture::new();
    let (ingress, queue) = product_connection_queue(1).unwrap();
    let (accepted, mut client) = fixture.connection();
    let cancellation = ingress.try_submit(accepted).unwrap();
    let (overflow, _other_client) = fixture.connection();
    assert_eq!(
        ingress.try_submit(overflow).err(),
        Some(ProductDispatchError::QueueFull)
    );
    cancellation.cancel();
    let connection = queue.try_next().unwrap().unwrap();
    let (endpoint, _owner) = servo_runtime_pair(Arc::new(|| {}));
    let mut coordinator = ProductRequestCoordinator::from_connection(
        fixture.principal.clone(),
        &connection,
        endpoint,
        fixture.journal(),
        "test-image".into(),
        RestartPolicy::new(3).unwrap(),
    )
    .unwrap();
    let started = Instant::now();
    assert_eq!(
        coordinator.serve_connection(connection).err(),
        Some(ProductDispatchError::Cancelled)
    );
    assert!(started.elapsed() < Duration::from_millis(100));
    assert_eq!(client.read(&mut [0; 1]).unwrap(), 0);
    assert!(
        coordinator
            .observer
            .borrow_mut()
            .as_mut()
            .unwrap()
            .inspect()
            .unwrap()
            .records
            .is_empty()
    );
}

#[test]
fn cancellation_interrupts_a_silent_transport_before_its_original_deadline() {
    let fixture = Fixture::new();
    let (accepted, _silent_client) = fixture.connection();
    let cancellation = accepted.cancellation();
    let (endpoint, _owner) = servo_runtime_pair(Arc::new(|| {}));
    let journal = fixture.journal();
    let principal = fixture.principal.clone();
    let worker = thread::spawn(move || {
        let mut coordinator = ProductRequestCoordinator::from_connection(
            principal,
            &accepted,
            endpoint,
            journal,
            "test-image".into(),
            RestartPolicy::new(3).unwrap(),
        )
        .unwrap();
        let result = coordinator.serve_connection(accepted);
        assert!(
            coordinator
                .observer
                .borrow_mut()
                .as_mut()
                .unwrap()
                .inspect()
                .unwrap()
                .records
                .is_empty()
        );
        result.is_err()
    });
    thread::sleep(Duration::from_millis(10));
    let started = Instant::now();
    cancellation.cancel();
    assert!(worker.join().unwrap());
    assert!(started.elapsed() < Duration::from_millis(500));
}

#[test]
fn explicit_reconstruction_invalidates_generation_and_crash_loop_stays_locked() {
    let fixture = Fixture::new();
    let journal = fixture.journal();
    drop(journal);
    let reopened = ReceiptJournal::open_managed(
        fixture.root.join("receipts"),
        JournalId([0x61; 16]),
        ManagedOpenPolicy::STRICT,
    )
    .unwrap();
    let (connection, _client) = fixture.connection();
    let (endpoint, _owner) = servo_runtime_pair(Arc::new(|| {}));
    let mut coordinator = ProductRequestCoordinator::from_connection(
        fixture.principal.clone(),
        &connection,
        endpoint,
        reopened,
        "test-image".into(),
        RestartPolicy::new(2).unwrap(),
    )
    .unwrap();
    coordinator.content_process_crashed().unwrap();
    assert_eq!(coordinator.generation().get(), 2);
    assert_eq!(coordinator.state(), RuntimeState::NeedsReconstruction);
    assert!(coordinator.content_process_crashed().is_err());
    assert_eq!(coordinator.generation().get(), 2);
    let (fresh, _owner) = servo_runtime_pair(Arc::new(|| {}));
    coordinator.reconstruct(&connection, fresh).unwrap();
    coordinator.content_process_crashed().unwrap();
    assert_eq!(coordinator.state(), RuntimeState::CrashLoopOpen);
    assert_eq!(
        coordinator
            .reconstruct(&connection, servo_runtime_pair(Arc::new(|| {})).0)
            .err(),
        Some(ProductDispatchError::CrashLoopOpen)
    );
}

fn history_event(id: &str, lifecycle: ReceiptLifecycleState) -> ReceiptEvent {
    ReceiptEvent {
        receipt_id: id.into(),
        plan_revision: "2026-08-29-d6".into(),
        image_id: "source-test".into(),
        servo_commit: "670ae8a70801b162e186f81cbb5bdd2d59c39108".into(),
        browserd_version: "0.1.0".into(),
        session_id: "source-session".into(),
        session_generation: 1,
        document_generation: 1,
        semantic_snapshot_revision: 1,
        mutation_epoch: 0,
        source: ReceiptSource::Agent,
        operation: "page_navigate".into(),
        lifecycle,
        outcome: None,
        effect_class: ReceiptEffectClass::PotentialExternalEffect,
        privacy_class: PrivacyClass::Internal,
        request_sha256: [0x73; 32],
        response_sha256: None,
        error_code: lifecycle.is_terminal().then(|| "internal".into()),
        detail: None,
        monotonic_ms: 100,
        wall_clock_unix_ms: 200,
    }
}

#[test]
fn service_reopen_requires_exact_explicit_acknowledgment_of_terminal_uncertainty() {
    for terminal in [
        ReceiptLifecycleState::Indeterminate,
        ReceiptLifecycleState::Interrupted,
    ] {
        let fixture = Fixture::new();
        let mut journal = fixture.journal();
        for state in [
            ReceiptLifecycleState::Requested,
            ReceiptLifecycleState::Dispatched,
            terminal,
        ] {
            journal
                .append(history_event("uncertain-before-restart", state))
                .unwrap();
        }
        let (_, journal) = journal.rotate_managed(200).unwrap();
        drop(journal);
        let (connection, _client) = fixture.connection();
        let open = || {
            ReceiptJournal::open_managed(
                fixture.root.join("receipts"),
                JournalId([0x61; 16]),
                ManagedOpenPolicy::STRICT,
            )
            .unwrap()
        };
        for acknowledgments in [
            vec![],
            vec![("other-request", [0x73; 32])],
            vec![("uncertain-before-restart", [0x74; 32])],
            vec![("uncertain-before-restart", [0x73; 32]); 2],
        ] {
            let (endpoint, _owner) = servo_runtime_pair(Arc::new(|| {}));
            assert_eq!(
                ProductRequestCoordinator::from_connection_after_reconciliation(
                    fixture.principal.clone(),
                    &connection,
                    endpoint,
                    open(),
                    "test-image".into(),
                    RestartPolicy::new(2).unwrap(),
                    &acknowledgments
                )
                .err(),
                Some(ProductDispatchError::RecoveryRequired)
            );
        }
        let (endpoint, _owner) = servo_runtime_pair(Arc::new(|| {}));
        let coordinator = ProductRequestCoordinator::from_connection_after_reconciliation(
            fixture.principal.clone(),
            &connection,
            endpoint,
            open(),
            "test-image".into(),
            RestartPolicy::new(2).unwrap(),
            &[("uncertain-before-restart", [0x73; 32])],
        )
        .unwrap();
        assert_eq!(coordinator.state(), RuntimeState::Ready);
        assert!(
            coordinator
                .observer
                .borrow_mut()
                .as_mut()
                .unwrap()
                .contains_receipt("uncertain-before-restart")
                .unwrap()
        );
        assert!(
            coordinator
                .observer
                .borrow_mut()
                .as_mut()
                .unwrap()
                .inspect()
                .unwrap()
                .records
                .is_empty(),
            "no receipt rewrite or replay in the active segment"
        );
    }
}

#[test]
fn nonterminal_history_cannot_be_acknowledged_as_recovered_on_startup() {
    let fixture = Fixture::new();
    let mut journal = fixture.journal();
    journal
        .append(history_event(
            "incomplete-before-restart",
            ReceiptLifecycleState::Requested,
        ))
        .unwrap();
    let (connection, _client) = fixture.connection();
    let (endpoint, _owner) = servo_runtime_pair(Arc::new(|| {}));
    assert_eq!(
        ProductRequestCoordinator::from_connection_after_reconciliation(
            fixture.principal.clone(),
            &connection,
            endpoint,
            journal,
            "test-image".into(),
            RestartPolicy::new(2).unwrap(),
            &[("incomplete-before-restart", [0x73; 32])]
        )
        .err(),
        Some(ProductDispatchError::RecoveryRequired)
    );
}

#[test]
fn original_budget_is_not_restarted_after_queue_residence() {
    let fixture = Fixture::new();
    let (ingress, queue) = product_connection_queue(1).unwrap();
    let (server, _client) = UnixStream::pair().unwrap();
    let connection = AcceptedProductConnection::attest(
        server,
        fixture.attestor.clone(),
        &fixture.policy,
        Duration::from_millis(30),
    )
    .unwrap();
    ingress.try_submit(connection).unwrap();
    thread::sleep(Duration::from_millis(40));
    let connection = queue.try_next().unwrap().unwrap();
    let (endpoint, _owner) = servo_runtime_pair(Arc::new(|| {}));
    let mut coordinator = ProductRequestCoordinator::from_connection(
        fixture.principal.clone(),
        &connection,
        endpoint,
        fixture.journal(),
        "test-image".into(),
        RestartPolicy::new(2).unwrap(),
    )
    .unwrap();
    assert_eq!(
        coordinator.serve_connection(connection).err(),
        Some(ProductDispatchError::DeadlineExceeded)
    );
    assert!(
        coordinator
            .observer
            .borrow_mut()
            .as_mut()
            .unwrap()
            .inspect()
            .unwrap()
            .records
            .is_empty()
    );
}

#[test]
fn active_cancellation_is_visible_to_the_native_final_action_check() {
    let result = run(
        &[Plan::Create("cancel-before-native-action")],
        Fault::CancelAtNativeBoundary,
    );
    assert_eq!(result.commands, 1);
    assert!(
        result.responses[0].is_none(),
        "cancel shuts down the original response transport"
    );
    assert_eq!(
        result.records, 3,
        "durable dispatch intent and truthful terminal fact survive transport cancellation"
    );
}

#[test]
fn changed_sealed_history_after_startup_blocks_admission_and_engine_dispatch() {
    let fixture = Fixture::new();
    let mut journal = fixture.journal();
    journal
        .append(history_event(
            "prior-no-dispatch",
            ReceiptLifecycleState::Requested,
        ))
        .unwrap();
    journal
        .append(history_event(
            "prior-no-dispatch",
            ReceiptLifecycleState::Interrupted,
        ))
        .unwrap();
    let predecessor = journal.path().to_owned();
    let (_, journal) = journal.rotate_managed(200).unwrap();
    let (connection, stream) = fixture.connection();
    let (endpoint, mut owner) = servo_runtime_pair(Arc::new(|| {}));
    let mut coordinator = ProductRequestCoordinator::from_connection(
        fixture.principal.clone(),
        &connection,
        endpoint,
        journal,
        "test-image".into(),
        RestartPolicy::new(2).unwrap(),
    )
    .unwrap();
    let mut bytes = fs::read(&predecessor).unwrap();
    *bytes.last_mut().unwrap() ^= 1;
    fs::write(&predecessor, bytes).unwrap();
    let client = thread::spawn(move || {
        let peer = PeerIdentity::from_stream(&stream).unwrap();
        let mut client =
            ClientConnection::connect(stream, PeerPolicy::exact(peer), BUDGET).unwrap();
        let sequence = client
            .send_request(
                encode_request(&Plan::Health("fresh-after-drift").request(&None)).unwrap(),
                BUDGET,
            )
            .unwrap();
        assert!(client.receive_response(sequence, BUDGET).is_err());
    });
    assert_eq!(
        coordinator.serve_connection(connection).err(),
        Some(ProductDispatchError::StorageUnavailable)
    );
    client.join().unwrap();
    owner.pump_one();
    assert!(owner.take_command().is_none());
    assert_eq!(
        coordinator.state(),
        RuntimeState::ReplayReconciliationRequired
    );
}
