//! Required exact-PIN executable. Explicit root fixture, default procfs and
//! externally preselected transient unit are not installed production approval.
#[path = "trillionnium_approved_startup.rs"]
mod approved_startup;
mod common;
#[path = "trillionnium_native_owner.rs"]
mod native_owner;
#[path = "trillionnium_approved_test_support.rs"]
mod support;
use approved_startup::ApprovedImmutableNativeStartup;
use hepta_browser_codec::{
    BrowserOperation, BrowserRequest, JsonObject, JsonValue, ObservationField, ProfilePersistence,
    ProfileSpec, decode_response,
};
use hepta_browserd::{
    ApprovedRetainedAdmission, ProductControlMonitorOutcome, ProductDispatchError, RuntimeState,
};
use hepta_session_core::{JournalId, ManagedOpenPolicy, ReceiptJournal, ReceiptLifecycleState};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};
use support::phase_diagnostics::{self as phases, Data, Edge, Phase};
fn request(id: &str, binding: Option<(&str, u64)>, operation: BrowserOperation) -> BrowserRequest {
    BrowserRequest {
        request_id: id.into(),
        session_id: binding.map(|v| v.0.into()),
        session_generation: binding.map(|v| v.1),
        deadline_unix_ms: None,
        operation,
    }
}
fn admission(trio: &mut support::Trio) -> ApprovedRetainedAdmission {
    phases::mark(Phase::Admission, Edge::Begin);
    let received = trio.receive();
    let admission =
        ApprovedRetainedAdmission::from_received(received, trio.document.select_agent().unwrap())
            .unwrap();
    phases::mark(Phase::Admission, Edge::End);
    admission
}
fn servo() -> common::ServoTest {
    common::ServoTest::new_with_builder(|builder| {
        let mut preferences = servo::Preferences::default();
        preferences.accessibility_enabled = true;
        preferences.network_http_proxy_uri.clear();
        preferences.network_https_proxy_uri.clear();
        builder.preferences(preferences)
    })
}
fn request_marker_at_failure(reader: Option<&mut std::process::ChildStdout>) -> &'static str {
    use std::io::Read;
    use std::os::fd::AsRawFd;
    let Some(reader) = reader else {
        return "unknown";
    };
    // This Trio owns the only reader of this unbuffered child stdout pipe.
    // No other reader can consume the bytes between poll and this single read.
    let mut pending = libc::pollfd {
        fd: reader.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    if unsafe { libc::poll(&mut pending, 1, 0) } != 1 || pending.revents & libc::POLLIN == 0 {
        return "unknown";
    }
    // A successful response may contribute up to 17 JSON bytes to this fixed
    // read. Only fixed prefixes are classified; those bytes are discarded.
    let mut bytes = [0; 34];
    match reader.read(&mut bytes) {
        Ok(8) if bytes.starts_with(b"REQUEST\n") => "request-observed",
        Ok(n) if n >= 17 && bytes[..17] == *b"REQUEST\nRESPONSE " => "response-envelope-observed",
        Ok(17) if bytes[..17] == *b"REQUEST\nRESPONSE_" => "agent-receive-error",
        Ok(34) if bytes.starts_with(b"REQUEST\nRESPONSE_REFUSED ") => {
            support::agent_receive_error_label(&bytes[25..]).unwrap_or("unknown")
        },
        _ => "unknown",
    }
}
fn run(
    driver: &mut ApprovedImmutableNativeStartup,
    trio: &mut support::Trio,
    input: &BrowserRequest,
) -> (JsonObject, (String, String)) {
    let started = Instant::now();
    let deadline = driver.original_deadline().unwrap();
    phases::record(
        Phase::RequestSend,
        Edge::Sample,
        Data::Send {
            request: phases::request(&input.request_id),
            remaining_ms: deadline.saturating_duration_since(started).as_millis(),
        },
    );
    trio.request(input);
    let mut drives = 0_u64;
    let mut drive_elapsed = Duration::ZERO;
    let mut last_drive = None;
    let mut drive_results = [0_u64; 4];
    let mut first_pending_ms = None;
    let mut first_completion_ms = None;
    let observation = loop {
        match driver.try_observation().unwrap() {
            Some(value) => break value.unwrap(),
            None => (),
        }
        assert!(
            Instant::now() < driver.original_deadline().unwrap(),
            "original accepted budget, no renewal; request={} elapsed_ms={} drives={} drive_ms={} last_drive={last_drive:?}; returns_idle_pending_completion_retired={drive_results:?}; first_pending_ms={first_pending_ms:?}; first_completion_ms={first_completion_ms:?}; agent_request_at_failure={}",
            input.request_id,
            started.elapsed().as_millis(),
            drives,
            drive_elapsed.as_millis(),
            request_marker_at_failure(trio.agent.child.stdout.as_mut())
        );
        let drive_started = Instant::now();
        let driven = driver.drive();
        drive_elapsed += drive_started.elapsed();
        drives = drives.saturating_add(1);
        last_drive = Some(driven.unwrap_or_else(|error| {
            panic!(
                "native drive refused; request={} elapsed_ms={} drives={} drive_ms={} error={error:?}",
                input.request_id,
                started.elapsed().as_millis(),
                drives,
                drive_elapsed.as_millis()
            )
        }));
        if let Some(value) = last_drive {
            let result_index = match value {
                native_owner::NativeDrive::Idle => 0,
                native_owner::NativeDrive::Pending => 1,
                native_owner::NativeDrive::Completion(_) => 2,
                native_owner::NativeDrive::Retired => 3,
            };
            drive_results[result_index] = drive_results[result_index].saturating_add(1);
            match value {
                native_owner::NativeDrive::Pending if first_pending_ms.is_none() => {
                    first_pending_ms = Some(started.elapsed().as_millis());
                },
                native_owner::NativeDrive::Completion(_) if first_completion_ms.is_none() => {
                    first_completion_ms = Some(started.elapsed().as_millis());
                },
                _ => (),
            }
        }
        thread::sleep(Duration::from_millis(1));
    };
    let traced_drive = match last_drive {
        None => phases::Drive::None,
        Some(native_owner::NativeDrive::Idle) => phases::Drive::Idle,
        Some(native_owner::NativeDrive::Pending) => phases::Drive::Pending,
        Some(native_owner::NativeDrive::Retired) => phases::Drive::Retired,
        Some(native_owner::NativeDrive::Completion(value)) => match value {
            hepta_browser_actor::ServoCompletionDelivery::Queued => phases::Drive::Queued,
            hepta_browser_actor::ServoCompletionDelivery::Retired => {
                phases::Drive::RetiredCompletion
            },
            hepta_browser_actor::ServoCompletionDelivery::ReceiverGone => {
                phases::Drive::ReceiverGone
            },
            hepta_browser_actor::ServoCompletionDelivery::WakeFailed => phases::Drive::WakeFailed,
        },
    };
    phases::record(
        Phase::RequestObserved,
        Edge::Sample,
        Data::Observation {
            request: phases::request(&input.request_id),
            elapsed_ms: started.elapsed().as_millis(),
            drives,
            drive_ms: drive_elapsed.as_millis(),
            last_drive: traced_drive,
        },
    );
    assert_eq!(
        observation.original_deadline(),
        trio.deadline.min(observation.original_deadline())
    );
    assert!(observation.service().as_ref().unwrap().response_committed);
    assert!(
        matches!(
            observation.report(),
            Ok(ProductControlMonitorOutcome::ReportEnqueued)
        ),
        "completed original report outcome={:?}",
        observation.report()
    );
    assert_eq!(observation.runtime_state(), RuntimeState::Ready);
    phases::mark(Phase::Response, Edge::Begin);
    trio.agent.expect("REQUEST");
    let response = trio.agent.line();
    let response = decode_response(response.strip_prefix("RESPONSE ").unwrap().as_bytes())
        .unwrap()
        .value;
    phases::mark(Phase::Response, Edge::End);
    phases::mark(Phase::Report, Edge::Begin);
    let report = trio.custodian.line();
    let words: Vec<_> = report.split_whitespace().collect();
    assert_eq!(words.len(), 4);
    assert_eq!(&words[..2], &["REPORT", "Completed"]);
    assert_eq!(
        words[2],
        observation.service().as_ref().unwrap().request_sha256
    );
    assert_eq!(words[3].len(), 64);
    phases::mark(Phase::Report, Edge::End);
    phases::mark(Phase::ChildrenFinish, Edge::Begin);
    trio.finish();
    phases::mark(Phase::ChildrenFinish, Edge::End);
    (
        response.outcome.unwrap(),
        (words[2].to_owned(), words[3].to_owned()),
    )
}
fn string<'a>(value: &'a JsonObject, key: &str) -> &'a str {
    match value.get(key).unwrap() {
        JsonValue::String(v) => v,
        _ => panic!("string"),
    }
}
fn integer(value: &JsonObject, key: &str) -> u64 {
    match value.get(key).unwrap() {
        JsonValue::Integer(v) => u64::try_from(*v).unwrap(),
        _ => panic!("integer"),
    }
}
fn open_receipts(path: &std::path::Path) -> ReceiptJournal {
    let stop = Instant::now() + Duration::from_secs(1);
    loop {
        match ReceiptJournal::open_managed(path, JournalId([0x72; 16]), ManagedOpenPolicy::STRICT) {
            Ok(value) => return value,
            Err(_) => {
                assert!(Instant::now() < stop, "owned worker clean retirement");
                thread::sleep(Duration::from_millis(1));
            },
        }
    }
}
fn actual_approved_startup_semantic_lifecycle() {
    let started = Instant::now();
    let servo = servo();
    phases::record(
        Phase::ServoReady,
        Edge::Sample,
        Data::Stage {
            elapsed_ms: started.elapsed().as_millis(),
        },
    );
    let mut first = support::Trio::new(support::WAIT);
    phases::record(
        Phase::PeersReady,
        Edge::Sample,
        Data::Stage {
            elapsed_ms: started.elapsed().as_millis(),
        },
    );
    let packet = admission(&mut first);
    phases::record(
        Phase::AdmissionReady,
        Edge::Sample,
        Data::Stage {
            elapsed_ms: started.elapsed().as_millis(),
        },
    );
    let original = packet.deadline().unwrap();
    let path = first.fixture.root.join("native-receipts");
    let journal = ReceiptJournal::create_managed(&path, JournalId([0x72; 16]), 1).unwrap();
    let (mut driver, ingress) = ApprovedImmutableNativeStartup::start(
        packet,
        servo.servo.clone(),
        servo.rendering_context.clone(),
        Arc::new(|| {}),
        journal,
        "approved-native-source".into(),
    )
    .unwrap();
    drop(servo);
    phases::record(
        Phase::StartupReady,
        Edge::Sample,
        Data::Startup {
            elapsed_ms: started.elapsed().as_millis(),
            remaining_ms: original
                .saturating_duration_since(Instant::now())
                .as_millis(),
        },
    );
    assert_eq!(driver.original_deadline().unwrap(), original);
    let (health, health_fact) = run(
        &mut driver,
        &mut first,
        &request("health", None, BrowserOperation::Health),
    );
    assert_eq!(string(&health, "runtime"), "actual-servo-immutable-owner");
    let mut creating = support::Trio::new_before(original);
    phases::mark(Phase::Enqueue, Edge::Begin);
    ingress.try_submit(admission(&mut creating)).unwrap();
    phases::mark(Phase::Enqueue, Edge::End);
    let (created, created_digest) = run(
        &mut driver,
        &mut creating,
        &request(
            "create",
            None,
            BrowserOperation::SessionCreate {
                profile: ProfileSpec {
                    profile_id: native_owner::IMMUTABLE_PROFILE.into(),
                    persistence: ProfilePersistence::Ephemeral,
                },
                ui_mode: "headed".into(),
            },
        ),
    );
    let session = string(&created, "session_id").to_owned();
    let generation = integer(&created, "session_generation");
    let mut facts = vec![("health", health_fact), ("create", created_digest)];
    assert!(matches!(created.get("nodes"),Some(JsonValue::Array(v)) if !v.is_empty()));
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
        phases::mark(Phase::Enqueue, Edge::Begin);
        ingress.try_submit(admission(&mut next)).unwrap();
        phases::mark(Phase::Enqueue, Edge::End);
        let (value, digest) = run(
            &mut driver,
            &mut next,
            &request(id, Some((&session, generation)), operation),
        );
        facts.push((id, digest));
        for key in ["native_webview_id", "document_tree_id"] {
            assert_eq!(created.get(key), value.get(key));
        }
        assert_eq!(driver.original_deadline().unwrap(), original);
    }
    driver.retire().unwrap();
    drop(ingress);
    drop(driver);
    // The first fixture is retained until own-journal readback completes.
    let mut journal = open_receipts(&path);
    assert!(!journal.has_unresolved_receipts().unwrap());
    for (id, (hex, reported_record)) in facts {
        let mut digest = [0; 32];
        for (out, part) in digest.iter_mut().zip(hex.as_bytes().chunks_exact(2)) {
            *out = u8::from_str_radix(std::str::from_utf8(part).unwrap(), 16).unwrap();
        }
        let fact = journal.receipt_fact(id, digest).unwrap();
        assert_eq!(fact.lifecycle().unwrap(), ReceiptLifecycleState::Completed);
        assert_eq!(
            hepta_session_core::hex_digest(fact.record_sha256().unwrap()),
            reported_record
        );
    }
    println!(
        "ACTUAL_APPROVED_NATIVE_STARTUP lifecycle; same actual WebView/document; three real peers; original deadline; no installed claim"
    );
}
fn actual_approved_startup_policy_refusal_before_constructor() {
    let servo = servo();
    let mut trio = support::Trio::new(support::WAIT);
    let packet = admission(&mut trio);
    let path = trio.fixture.root.join("refused-receipts");
    let journal = ReceiptJournal::create_managed(&path, JournalId([0x72; 16]), 1).unwrap();
    trio.drift();
    let result = ApprovedImmutableNativeStartup::start(
        packet,
        servo.servo.clone(),
        servo.rendering_context.clone(),
        Arc::new(|| {}),
        journal,
        "approved-native-refusal".into(),
    );
    assert_eq!(result.err(), Some(ProductDispatchError::PeerRefused));
    trio.restore();
    trio.agent.command(b'e');
    trio.agent.expect("ORIGINAL_EOF_WITHOUT_HANDSHAKE");
    let mut journal = open_receipts(&path);
    assert!(!journal.contains_receipt("create").unwrap());
    assert!(!journal.has_unresolved_receipts().unwrap());
    drop(journal);
    trio.finish();
    drop(servo);
    println!(
        "ACTUAL_APPROVED_NATIVE_STARTUP policy-refused; no constructor/worker/handshake/durable facts; no installed claim"
    );
}
fn main() {
    if support::child_entry() {
        return;
    }
    let args: Vec<_> = std::env::args().collect();
    assert_eq!(args.len(), 3);
    support::configure(&args[2]);
    phases::run_case(|| match args[1].as_str() {
        "actual_approved_startup_semantic_lifecycle" => {
            actual_approved_startup_semantic_lifecycle()
        },
        "actual_approved_startup_policy_refusal_before_constructor" => {
            actual_approved_startup_policy_refusal_before_constructor()
        },
        _ => panic!("closed exact native case"),
    });
}
