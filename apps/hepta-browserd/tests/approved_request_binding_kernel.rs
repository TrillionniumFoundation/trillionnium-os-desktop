//! Actual default /proc, root transient unit and three original processes.
//! Callback completions are synthetic; no native/installed qualification.
#[path = "../../../experiments/servo-product-owner/src/approved_test_support.rs"]
mod support;
use hepta_agent_port::DispatchContext;
use hepta_agent_transport::{PeerIdentity, PeerPolicy};
use hepta_browser_actor::{ServoBrowserActor, ServoRuntimeOwner, servo_runtime_pair};
use hepta_browser_codec::{
    BrowserOperation, BrowserRequest, JsonObject, JsonValue, ObservationField, ProfilePersistence,
    ProfileSpec, decode_response,
};
use hepta_browserd::{ApprovedRetainedAdmission, ApprovedRetainedObservation};
use hepta_peer_attestation::{
    ApprovedAgentRequestBinding, AttestedPeer, AttestedRetainedReceiver, ControlRequestCustody,
    ProcfsPeerAttestor,
};
use hepta_session_core::{
    Digest, JournalId, ManagedOpenPolicy, ReceiptJournal, ReceiptLifecycleState,
};
use std::os::unix::net::UnixStream;
use std::sync::{Arc, mpsc};
use std::thread;
use std::time::{Duration, Instant};

fn request(id: &str, operation: BrowserOperation) -> BrowserRequest {
    BrowserRequest {
        request_id: id.into(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation,
    }
}
fn admit(trio: &mut support::Trio) -> ApprovedRetainedAdmission {
    let original = trio.receive();
    ApprovedRetainedAdmission::from_received(original, trio.document.select_agent().unwrap())
        .unwrap()
}
fn collect(
    owner: &mut ServoRuntimeOwner,
    receiver: &mpsc::Receiver<ApprovedRetainedObservation>,
    ceiling: Instant,
    calls: &mut usize,
) -> ApprovedRetainedObservation {
    loop {
        if let Ok(value) = receiver.try_recv() {
            return value;
        }
        owner.pump_one();
        if let Some(command) = owner.take_command() {
            *calls += 1;
            let (_, _, done) = command.into_parts();
            done.ensure_current_peer().unwrap();
            done.complete_success(JsonObject::new(), None);
        }
        // Diagnostic collection grace neither dispatches nor renews authority.
        assert!(Instant::now() < ceiling + Duration::from_secs(1));
        thread::sleep(Duration::from_millis(1));
    }
}
fn digest(text: &str) -> Digest {
    assert_eq!(text.len(), 64);
    let mut bytes = [0; 32];
    for (out, part) in bytes.iter_mut().zip(text.as_bytes().chunks_exact(2)) {
        *out = u8::from_str_radix(std::str::from_utf8(part).unwrap(), 16).unwrap();
    }
    bytes
}
fn response(trio: &mut support::Trio) -> (JsonObject, (Digest, Digest)) {
    trio.agent.expect("REQUEST");
    let raw = trio.agent.line();
    let value = decode_response(raw.strip_prefix("RESPONSE ").unwrap().as_bytes())
        .unwrap()
        .value
        .outcome
        .unwrap();
    let control = trio.custodian.line();
    assert!(control.starts_with("REPORT Completed "), "{control}");
    let fields: Vec<_> = control.split_ascii_whitespace().collect();
    assert_eq!(fields.len(), 4);
    let fact = (digest(fields[2]), digest(fields[3]));
    trio.finish();
    (value, fact)
}
fn lifecycle() {
    let mut first = support::Trio::new(support::WAIT);
    let first_pid = first.agent.child.id();
    let packet = admit(&mut first);
    let original = packet.deadline().unwrap();
    let root_fields = std::fs::read(&first.fixture.config).unwrap();
    let path = first.fixture.root.join("binding-lifecycle-receipts");
    let journal = ReceiptJournal::create_managed(&path, JournalId([0x7a; 16]), 1).unwrap();
    let (endpoint, mut owner) = servo_runtime_pair(Arc::new(|| {}));
    let (send, requests) = mpsc::sync_channel::<ApprovedRetainedAdmission>(1);
    let (observations, receive) = mpsc::sync_channel(1);
    let worker = thread::spawn(move || {
        let mut coordinator = packet
            .coordinator(endpoint, journal, "binding-host-source".into())
            .unwrap();
        observations
            .send(packet.serve(&mut coordinator).unwrap())
            .unwrap();
        for _ in 0..3 {
            observations
                .send(requests.recv().unwrap().serve(&mut coordinator).unwrap())
                .unwrap();
        }
    });
    let mut calls = 0;
    first.request(&request("health", BrowserOperation::Health));
    assert_eq!(
        collect(&mut owner, &receive, original, &mut calls).original_deadline(),
        original
    );
    let (_, health_fact) = response(&mut first);
    assert!(!std::path::Path::new(&format!("/proc/{first_pid}")).exists());
    let mut next = support::Trio::new_before(original);
    assert_ne!(next.agent.child.id(), first_pid);
    assert_eq!(std::fs::read(&next.fixture.config).unwrap(), root_fields);
    send.send(admit(&mut next)).unwrap();
    next.request(&request(
        "create",
        BrowserOperation::SessionCreate {
            profile: ProfileSpec {
                profile_id: "binding-source-profile".into(),
                persistence: ProfilePersistence::Ephemeral,
            },
            ui_mode: "headed".into(),
        },
    ));
    assert_eq!(
        collect(&mut owner, &receive, original, &mut calls).original_deadline(),
        original
    );
    let (created, create_fact) = response(&mut next);
    let mut facts = vec![("health", health_fact), ("create", create_fact)];
    let session = match &created["session_id"] {
        JsonValue::String(s) => s.clone(),
        other => panic!("{other:?}"),
    };
    let generation = match created["session_generation"] {
        JsonValue::Integer(v) => v,
        ref other => panic!("{other:?}"),
    };
    let mut actual_pids = vec![first_pid, next.agent.child.id()];
    for (id, operation) in [
        (
            "observe",
            BrowserOperation::PageObserve {
                fields: vec![ObservationField::Role, ObservationField::Name],
            },
        ),
        ("snapshot", BrowserOperation::SessionSnapshot),
    ] {
        let mut next = support::Trio::new_before(original);
        assert_eq!(std::fs::read(&next.fixture.config).unwrap(), root_fields);
        assert!(!actual_pids.contains(&next.agent.child.id()));
        actual_pids.push(next.agent.child.id());
        send.send(admit(&mut next)).unwrap();
        let mut req = request(id, operation);
        req.session_id = Some(session.clone());
        req.session_generation = Some(generation as u64);
        next.request(&req);
        let observation = collect(&mut owner, &receive, original, &mut calls);
        assert_eq!(observation.original_deadline(), original);
        assert!(observation.service().as_ref().unwrap().response_ok);
        let (value, fact) = response(&mut next);
        facts.push((id, fact));
        assert_eq!(value["session_id"], created["session_id"]);
        assert_eq!(value["session_generation"], created["session_generation"]);
    }
    worker.join().unwrap();
    assert_eq!(calls, 4);
    let mut journal =
        ReceiptJournal::open_managed(&path, JournalId([0x7a; 16]), ManagedOpenPolicy::STRICT)
            .unwrap();
    assert!(!journal.has_unresolved_receipts().unwrap());
    for (id, (request_digest, reported_record)) in facts {
        let fact = journal.receipt_fact(id, request_digest).unwrap();
        assert_eq!(fact.lifecycle().unwrap(), ReceiptLifecycleState::Completed);
        assert_eq!(fact.record_sha256().unwrap(), reported_record);
    }
    assert!(journal.execution_reconciliation_facts().unwrap().is_empty());
    eprintln!(
        "PASS lifecycle actual Agent PIDs={actual_pids:?}; first exited; same Coordinator/PageOwner/root fields; four completed receipts; fixed first Instant; callbacks={calls}"
    );
}

// Separate additive test fixture: policy changes occur BEFORE either peer is
// launched. Original support/native fixtures and their budgets are untouched.
struct SelectedTrio {
    fixture: support::Fixture,
    custodian: support::ChildOwner,
    agent: support::ChildOwner,
    receiver: hepta_peer_attestation::RootPathAttestedHandoffReceiver,
    document: hepta_peer_attestation::ApprovedPolicyDocument,
}
impl SelectedTrio {
    fn new(ceiling: Instant, selected: Option<(&str, &str)>) -> Self {
        let fixture = support::Fixture::new();
        if let Some((key, value)) = selected {
            fixture.rewrite(key, value);
        }
        let mut listener = fixture.listener();
        let mut custodian =
            support::ChildOwner::spawn(&fixture, "custodian", fixture.agent_path(), false);
        custodian.expect("PATH_CURRENT");
        let mut agent = support::ChildOwner::spawn(&fixture, "agent", fixture.agent_path(), false);
        agent.expect("CONNECTED");
        let connection = listener
            .accept_before(
                PeerPolicy {
                    expected_uid: 0,
                    expected_gid: Some(0),
                    expected_pid: Some(custodian.child.id()),
                },
                ceiling,
            )
            .unwrap();
        let document = fixture.document(ceiling);
        let receiver = document
            .select_control()
            .unwrap()
            .bind_receiver(connection, fixture.agent_path())
            .unwrap();
        custodian.expect("ARMED");
        Self {
            fixture,
            custodian,
            agent,
            receiver,
            document,
        }
    }
    fn packet(&mut self) -> Packet {
        self.custodian.command(b's');
        let received = self.receiver.receive_retained_custodied().unwrap();
        self.custodian.expect("SENT");
        self.document
            .select_agent()
            .unwrap()
            .admit_retained(received)
            .unwrap()
            .consume_with_request_binding(
                |stream, deadline, control, retained, attested, _, binding| Packet {
                    stream,
                    deadline,
                    _control: control,
                    _retained: retained,
                    attested,
                    binding,
                },
            )
            .unwrap()
    }
}
struct Packet {
    stream: UnixStream,
    deadline: Instant,
    _control: ControlRequestCustody,
    _retained: AttestedRetainedReceiver,
    attested: AttestedPeer,
    binding: ApprovedAgentRequestBinding,
}
fn actor(packet: &Packet) -> (ServoBrowserActor, ServoRuntimeOwner) {
    let (endpoint, owner) = servo_runtime_pair(Arc::new(|| {}));
    (
        ServoBrowserActor::from_approved_request(&packet.binding, endpoint).unwrap(),
        owner,
    )
}
fn context(packet: &Packet, deadline: Instant) -> DispatchContext {
    DispatchContext {
        peer: PeerIdentity::from_stream(&packet.stream).unwrap(),
        transport_sequence: 1,
        canonical_request_sha256: "a".repeat(64),
        effect_class: hepta_browser_codec::EffectClass::Observation,
        accepted_at: Instant::now(),
        effective_deadline: deadline,
    }
}
fn fake_attestation(
    packet: &Packet,
    fixture: &support::Fixture,
) -> (ProcfsPeerAttestor, AttestedPeer) {
    let snapshot = packet.attested.snapshot();
    let root = fixture.root.join("attacker-proc");
    let process = root.join(snapshot.pid.to_string());
    std::fs::create_dir_all(&process).unwrap();
    std::fs::write(
        process.join("status"),
        format!(
            "Uid:\t{}\t{}\t{}\t{}\nGid:\t{}\t{}\t{}\t{}\n",
            snapshot.uid,
            snapshot.uid,
            snapshot.uid,
            snapshot.uid,
            snapshot.gid,
            snapshot.gid,
            snapshot.gid,
            snapshot.gid
        ),
    )
    .unwrap();
    std::fs::copy(format!("/proc/{}/stat", snapshot.pid), process.join("stat")).unwrap();
    std::fs::write(
        process.join("cgroup"),
        format!("0::{}\n", snapshot.cgroup_v2_path),
    )
    .unwrap();
    std::fs::copy(format!("/proc/{}/exe", snapshot.pid), process.join("exe")).unwrap();
    let attestor = ProcfsPeerAttestor::new(root);
    let peer = attestor
        .attest(
            PeerIdentity::from_stream(&packet.stream).unwrap(),
            &hepta_peer_attestation::PeerRuntimePolicy {
                expected_uid: snapshot.uid,
                expected_gid: snapshot.gid,
                expected_systemd_unit: snapshot.systemd_unit.clone(),
                expected_cgroup_v2_path: snapshot.cgroup_v2_path.clone(),
            },
        )
        .unwrap();
    (attestor, peer)
}
fn refused(
    value: Result<Option<hepta_browser_codec::BrowserWireError>, hepta_agent_port::AgentPortError>,
) -> bool {
    matches!(value, Err(_) | Ok(Some(_)))
}
fn negatives() {
    for (label, field) in [
        ("different-agent-principal", "agent.principal_id"),
        ("different-control-principal", "control.principal_id"),
    ] {
        let ceiling = Instant::now() + support::WAIT;
        let mut first = SelectedTrio::new(ceiling, None);
        let original = first.packet();
        let (mut actor, _owner) = actor(&original);
        let mut next = SelectedTrio::new(ceiling, Some((field, "different-source")));
        let next_packet = next.packet();
        assert!(actor.rebind_approved_request(&next_packet.binding).is_err());
        eprintln!("PASS {label}: independently preselected valid source refused");
    }
    for old in [true, false] {
        let ceiling = Instant::now() + support::WAIT;
        let mut first = SelectedTrio::new(ceiling, None);
        let original = first.packet();
        let (mut actor, _owner) = actor(&original);
        let mut next = SelectedTrio::new(ceiling, None);
        let next_packet = next.packet();
        let fixture = if old { &first.fixture } else { &next.fixture };
        fixture.rewrite("agent.principal_id", "drifted-source");
        assert!(actor.rebind_approved_request(&next_packet.binding).is_err());
        fixture.rewrite("agent.principal_id", "source-agent");
        assert!(actor.rebind_approved_request(&next_packet.binding).is_err());
        eprintln!("PASS observed policy drift old={old} permanently refused after restore");
    }
    for role in ["agent", "control"] {
        let ceiling = Instant::now() + support::WAIT;
        let mut first = SelectedTrio::new(ceiling, None);
        let original = first.packet();
        let (mut actor, _owner) = actor(&original);
        let mut next = SelectedTrio::new(ceiling, None);
        let next_packet = next.packet();
        if role == "agent" {
            next.agent.finish();
        } else {
            next.custodian.finish();
        }
        assert!(actor.rebind_approved_request(&next_packet.binding).is_err());
        eprintln!("PASS new original {role} dead refused");
    }
    {
        let ceiling = Instant::now() + support::WAIT;
        let mut first = SelectedTrio::new(ceiling, None);
        let original = first.packet();
        let (approved, _owner) = actor(&original);
        let (endpoint, _legacy_owner) = servo_runtime_pair(Arc::new(|| {}));
        let mut legacy = ServoBrowserActor::from_attested(
            approved.principal().clone(),
            PeerIdentity::from_stream(&original.stream).unwrap(),
            &ProcfsPeerAttestor::default(),
            &original.attested,
            endpoint,
        )
        .unwrap();
        let mut next = SelectedTrio::new(ceiling, None);
        let next_packet = next.packet();
        assert!(
            legacy
                .rebind_approved_request(&next_packet.binding)
                .is_err()
        );
        eprintln!("PASS legacy/raw actor cannot attach approval retroactively");
    }
    {
        let ceiling = Instant::now() + support::WAIT;
        let mut first = SelectedTrio::new(ceiling, None);
        let original = first.packet();
        let (mut actor, _owner) = actor(&original);
        let mut next = SelectedTrio::new(ceiling, None);
        let next_packet = next.packet();
        actor.rebind_approved_request(&next_packet.binding).unwrap();
        let (fake_proc, fake_peer) = fake_attestation(&next_packet, &next.fixture);
        let foreign_control = original._control.verifier().unwrap();
        assert_eq!(
            unsafe { libc::kill(next.agent.child.id() as i32, libc::SIGUSR1) },
            0
        );
        let wait = Instant::now() + Duration::from_secs(2);
        while std::fs::read_link(format!("/proc/{}/exe", next.agent.child.id())).unwrap()
            != std::path::Path::new("/usr/bin/sleep")
        {
            assert!(Instant::now() < wait);
            thread::sleep(Duration::from_millis(1));
        }
        // Attacker supplied facts still claim the admitted old ELF. They are
        // actual caller-controlled test objects, never production approval.
        assert_eq!(
            fake_peer
                .refresh_snapshot(&fake_proc)
                .unwrap()
                .executable_sha256,
            next_packet.attested.snapshot().executable_sha256
        );
        foreign_control.verify_current().unwrap();
        let controlled = actor.preflight_attested_controlled(
            &context(&next_packet, ceiling),
            &request("fake-source", BrowserOperation::Health),
            &fake_proc,
            &fake_peer,
            &foreign_control,
        );
        assert!(refused(controlled));
        assert!(actor.rebind_approved_request(&next_packet.binding).is_err());
        assert!(
            actor
                .handle_attested(
                    &context(&next_packet, ceiling),
                    &request("exec-handle", BrowserOperation::Health),
                    &ProcfsPeerAttestor::default(),
                    &next_packet.attested
                )
                .is_err()
        );
        eprintln!(
            "PASS actual new original exec changed ELF; caller fake procfs+foreign custodian, replacement and raw handle refused"
        );
    }
    {
        let ceiling = Instant::now() + support::WAIT;
        let mut first = SelectedTrio::new(ceiling, None);
        let original = first.packet();
        let (mut actor, _owner) = actor(&original);
        let mut next = SelectedTrio::new(ceiling, None);
        let next_packet = next.packet();
        actor.cancellation_token("prepared");
        assert!(actor.rebind_approved_request(&next_packet.binding).is_err());
        actor.retire_prepared_request("prepared").unwrap();
        actor.rebind_approved_request(&next_packet.binding).unwrap();
        // Old peer/raw context cannot acquire this new request's binding.
        assert!(
            actor
                .preflight_attested(
                    &context(&original, ceiling),
                    &request("old-handle", BrowserOperation::Health),
                    &ProcfsPeerAttestor::default(),
                    &original.attested
                )
                .is_err()
        );
        // Dropping custody irrevocably retires even a cloned read-only verifier.
        let session = next_packet.binding.start_session().unwrap();
        let verifier = next_packet.binding.verifier_for_session(&session).unwrap();
        drop(next_packet);
        assert!(verifier.verify_for_session(&session).is_err());
        assert!(
            actor
                .handle_attested(
                    &context(&original, ceiling),
                    &request("retired-handle", BrowserOperation::Health),
                    &ProcfsPeerAttestor::default(),
                    &original.attested
                )
                .is_err()
        );
        eprintln!(
            "PASS prepared conflict; new binding after explicit retirement; old raw handle refused; dropped opaque custody cannot execute"
        );
    }
    {
        let ceiling = Instant::now() + support::WAIT;
        let mut first = SelectedTrio::new(ceiling, None);
        let original = first.packet();
        let (mut actor, _owner) = actor(&original);
        let mut next = SelectedTrio::new(ceiling, None);
        let next_packet = next.packet();
        let child = unsafe { libc::fork() };
        assert!(child >= 0);
        if child == 0 {
            unsafe {
                libc::_exit(
                    if actor.rebind_approved_request(&next_packet.binding).is_err() {
                        0
                    } else {
                        3
                    },
                )
            };
        }
        let mut status = 0;
        assert_eq!(unsafe { libc::waitpid(child, &mut status, 0) }, child);
        assert_eq!(status, 0);
        actor.rebind_approved_request(&next_packet.binding).unwrap();
        eprintln!("PASS fork replacement refused before aliases; parent original custody usable");
    }
    {
        let ceiling = Instant::now() + Duration::from_secs(3);
        let mut first = SelectedTrio::new(ceiling, None);
        let original = first.packet();
        let (mut actor, _owner) = actor(&original);
        // New request has a larger legitimate own scope, but cannot extend this session.
        let mut next = SelectedTrio::new(Instant::now() + support::WAIT, None);
        let next_packet = next.packet();
        assert!(next_packet.deadline > original.deadline);
        assert!(actor.rebind_approved_request(&next_packet.binding).is_err());
        thread::sleep(ceiling.saturating_duration_since(Instant::now()) + Duration::from_millis(5));
        assert!(
            actor
                .handle_attested(
                    &context(&original, Instant::now() + support::WAIT),
                    &request("late-handle", BrowserOperation::Health),
                    &ProcfsPeerAttestor::default(),
                    &original.attested
                )
                .is_err()
        );
        eprintln!(
            "PASS later ceiling refused; caller renewed context cannot revive original session"
        );
    }
}
fn late_scope_unknown_cannot_rebind() {
    let ceiling = Instant::now() + support::WAIT;
    let mut first = SelectedTrio::new(ceiling, None);
    let original = first.packet();
    let mut next = SelectedTrio::new(ceiling, None);
    let replacement = next.packet();
    let Packet {
        stream,
        deadline,
        _control: control,
        _retained: retained,
        attested,
        binding,
    } = original;
    let peer = PeerIdentity::from_stream(&stream).unwrap();
    let verifier = control.verifier().unwrap();
    let (endpoint, mut owner) = servo_runtime_pair(Arc::new(|| {}));
    let worker = thread::spawn(move || {
        let mut actor = ServoBrowserActor::from_approved_request(&binding, endpoint).unwrap();
        let context = DispatchContext {
            peer,
            transport_sequence: 1,
            canonical_request_sha256: "b".repeat(64),
            effect_class: hepta_browser_codec::EffectClass::Observation,
            accepted_at: Instant::now(),
            effective_deadline: deadline,
        };
        let outcome = actor
            .handle_attested_controlled(
                &context,
                &request("late-scope", BrowserOperation::Health),
                &ProcfsPeerAttestor::default(),
                &attested,
                &verifier,
            )
            .unwrap();
        assert!(
            matches!(outcome, hepta_agent_port::HandlerOutcome::Failure(ref e) if e.code==hepta_browser_codec::BrowserErrorCode::Indeterminate)
        );
        assert!(actor.rebind_approved_request(&replacement.binding).is_err());
        drop(retained);
        drop(stream);
        drop(binding);
    });
    let mut called = false;
    while !worker.is_finished() {
        owner.pump_one();
        if let Some(command) = owner.take_command() {
            assert!(!called);
            called = true;
            let (_, _, completion) = command.into_parts();
            control.revoke().unwrap();
            assert!(completion.ensure_current_peer().is_err());
            completion.complete_error(hepta_browser_actor::ServoRuntimeError::Cancelled);
        }
        assert!(Instant::now() < ceiling);
        thread::sleep(Duration::from_millis(1));
    }
    worker.join().unwrap();
    assert!(called);
    eprintln!(
        "PASS actual original Control retirement after callback dispatch preserves Indeterminate and locks direct approved actor replacement"
    );
}
fn run() {
    lifecycle();
    negatives();
    late_scope_unknown_cannot_rebind();
    println!(
        "PASS approved request binding actual host corpus; zero skips; default procfs only; no native/installed promotion"
    );
}
extern "C" fn exec_original(_: libc::c_int) {
    let argv = [c"sleep".as_ptr(), c"120".as_ptr(), std::ptr::null()];
    let env = [std::ptr::null()];
    unsafe {
        libc::execve(c"/usr/bin/sleep".as_ptr(), argv.as_ptr(), env.as_ptr());
        libc::_exit(98);
    }
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    if args.get(1).is_some_and(|v| v == "--child") && args.get(2).is_some_and(|v| v == "agent") {
        assert_ne!(
            unsafe {
                libc::signal(
                    libc::SIGUSR1,
                    exec_original as *const () as libc::sighandler_t,
                )
            },
            libc::SIG_ERR
        );
    }
    support::launch_host(run);
}
