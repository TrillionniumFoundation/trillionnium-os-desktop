//! Default-procfs opaque-pair kernel evidence. Source callbacks are synthetic;
//! this host target is never evidence of actual Servo execution or installation.
#[path = "../../../experiments/servo-product-owner/src/approved_test_support.rs"]
mod support;
use hepta_browser_actor::{ServoRuntimeError, servo_runtime_pair};
use hepta_browser_codec::{BrowserOperation, BrowserRequest, JsonObject};
use hepta_browserd::{
    ApprovedRetainedAdmission, ProductControlMonitorOutcome, ProductDispatchError,
    approved_retained_queue, approved_retained_queue_before,
};
use hepta_session_core::{JournalId, ManagedOpenPolicy, ReceiptJournal, ReceiptLifecycleState};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};
use support::{Trio, WAIT};
fn admit(trio: &mut Trio) -> ApprovedRetainedAdmission {
    let received = trio.receive();
    ApprovedRetainedAdmission::from_received(received, trio.document.select_agent().unwrap())
        .unwrap()
}
fn eof(trio: &mut Trio) {
    trio.agent.command(b'e');
    trio.agent.expect("ORIGINAL_EOF_WITHOUT_HANDSHAKE");
    trio.finish();
}
fn full_and_drop() {
    let mut first = Trio::new(WAIT);
    let mut second = Trio::new(WAIT);
    let (ingress, mut queue, _) = approved_retained_queue();
    ingress.try_submit(admit(&mut first)).unwrap();
    assert_eq!(
        ingress.try_submit(admit(&mut second)).err(),
        Some(ProductDispatchError::QueueFull)
    );
    eof(&mut second);
    let packet = queue.try_next().unwrap().unwrap();
    assert!(queue.try_next().unwrap().is_none());
    drop(packet);
    eof(&mut first);
}
fn retire_queued() {
    let mut trio = Trio::new(WAIT);
    let (ingress, mut queue, retirement) = approved_retained_queue();
    ingress.try_submit(admit(&mut trio)).unwrap();
    retirement.request().unwrap();
    assert_eq!(queue.try_next().err(), Some(ProductDispatchError::Closed));
    drop(queue);
    eof(&mut trio);
}
fn original_expiry() {
    let mut trio = Trio::new_mode(WAIT, "early", WAIT);
    let packet = admit(&mut trio);
    let deadline = packet.deadline().unwrap();
    let (ingress, mut queue, _) = approved_retained_queue_before(deadline).unwrap();
    ingress.try_submit(packet).unwrap();
    thread::sleep(deadline.saturating_duration_since(Instant::now()) + Duration::from_millis(5));
    assert_eq!(
        queue.try_next().err(),
        Some(ProductDispatchError::DeadlineExceeded)
    );
    drop(queue);
    eof(&mut trio);
}
fn fixed_ceiling() {
    let mut trio = Trio::new(WAIT);
    let packet = admit(&mut trio);
    let ceiling = Instant::now() + Duration::from_millis(100);
    assert!(packet.deadline().unwrap() > ceiling);
    let (ingress, queue, _) = approved_retained_queue_before(ceiling).unwrap();
    assert_eq!(
        ingress.try_submit(packet).err(),
        Some(ProductDispatchError::DeadlineExceeded)
    );
    drop(queue);
    eof(&mut trio);
}
fn policy_drift() {
    let mut trio = Trio::new(WAIT);
    let packet = admit(&mut trio);
    trio.drift();
    let (ingress, queue, _) = approved_retained_queue();
    assert_eq!(
        ingress.try_submit(packet).err(),
        Some(ProductDispatchError::PeerRefused)
    );
    trio.restore();
    drop(queue);
    eof(&mut trio);
}
fn fork_original() {
    let mut trio = Trio::new(WAIT);
    let packet = admit(&mut trio);
    let (ingress, mut queue, retirement) = approved_retained_queue();
    let pid = unsafe { libc::fork() };
    assert!(pid >= 0);
    if pid == 0 {
        assert_eq!(
            packet.ensure_creating_process(),
            Err(ProductDispatchError::PeerRefused)
        );
        assert_eq!(packet.deadline(), Err(ProductDispatchError::PeerRefused));
        assert_eq!(
            ingress.try_submit(packet).err(),
            Some(ProductDispatchError::PeerRefused)
        );
        assert_eq!(
            queue.try_next().err(),
            Some(ProductDispatchError::PeerRefused)
        );
        assert_eq!(retirement.request(), Err(ProductDispatchError::PeerRefused));
        drop(queue);
        drop(ingress);
        drop(retirement);
        unsafe { libc::_exit(0) }
    }
    let mut status = 0;
    assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
    assert_eq!(status, 0);
    assert!(!retirement.is_requested().unwrap());
    ingress.try_submit(packet).unwrap();
    queue.try_next().unwrap().unwrap().deadline().unwrap();
    eof(&mut trio);
}
fn serve_normal() {
    serve(false);
}
fn active_cancel() {
    serve(true);
}
fn serve(cancel: bool) {
    let mut trio = Trio::new(WAIT);
    let packet = admit(&mut trio);
    let deadline = packet.deadline().unwrap();
    let path = trio.fixture.root.join("receipts");
    let journal = ReceiptJournal::create_managed(&path, JournalId([0x71; 16]), 1).unwrap();
    let (endpoint, mut owner) = servo_runtime_pair(Arc::new(|| {}));
    let (ingress, mut queue, retirement) = approved_retained_queue_before(deadline).unwrap();
    ingress.try_submit(packet).unwrap();
    let packet = queue.try_next().unwrap().unwrap();
    let worker = thread::spawn(move || {
        let mut coordinator = packet
            .coordinator(endpoint, journal, "source-approved-startup".into())
            .unwrap();
        packet.serve(&mut coordinator).unwrap()
    });
    let input = BrowserRequest {
        request_id: "startup-health".into(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    };
    trio.request(&input);
    while !worker.is_finished() {
        owner.pump_one();
        if let Some(command) = owner.take_command() {
            let (_, _, completion) = command.into_parts();
            if cancel {
                retirement.request().unwrap();
                assert!(completion.ensure_active().is_err());
                completion.complete_error(ServoRuntimeError::Cancelled);
            } else {
                completion.ensure_current_peer().unwrap();
                completion.complete_success(JsonObject::new(), None);
            }
        }
        assert!(Instant::now() < deadline);
        thread::sleep(Duration::from_millis(1));
    }
    let observation = worker.join().unwrap();
    assert_eq!(observation.original_deadline(), deadline);
    eprintln!(
        "served cancel={cancel} service={:?} report={:?}",
        observation.service(),
        observation.report()
    );
    assert_eq!(observation.service().is_ok(), !cancel);
    assert!(matches!(
        observation.report(),
        Ok(ProductControlMonitorOutcome::ReportEnqueued)
    ));
    trio.agent.expect("REQUEST");
    assert!(trio.agent.line().starts_with(if cancel {
        "RESPONSE_REFUSED"
    } else {
        "RESPONSE "
    }));
    assert!(trio.custodian.line().starts_with(if cancel {
        "REPORT Indeterminate "
    } else {
        "REPORT Completed "
    }));
    let mut reopened =
        ReceiptJournal::open_managed(&path, JournalId([0x71; 16]), ManagedOpenPolicy::STRICT)
            .unwrap();
    assert!(!reopened.has_unresolved_receipts().unwrap());
    if cancel {
        assert_eq!(
            observation.runtime_state(),
            hepta_browserd::RuntimeState::ReplayReconciliationRequired
        );
    }
    let records = reopened.inspect().unwrap().records;
    assert_eq!(records.len(), 3);
    assert!(
        records
            .iter()
            .all(|v| v.event.receipt_id == "startup-health")
    );
    assert_eq!(
        records.last().unwrap().event.lifecycle,
        if cancel {
            ReceiptLifecycleState::Indeterminate
        } else {
            ReceiptLifecycleState::Completed
        }
    );
    drop(reopened);
    drop(queue);
    drop(ingress);
    trio.finish();
}
fn main() {
    support::launch_host(|| {
        for (name, test) in [
            ("full-pair-drop", full_and_drop as fn()),
            ("queued-retirement", retire_queued),
            ("original-expiry", original_expiry),
            ("fixed-outer-ceiling", fixed_ceiling),
            ("policy-drift-no-recovery", policy_drift),
            ("fork-parent-custody", fork_original),
            ("same-pair-durable-terminal", serve_normal),
            ("active-original-cancel-indeterminate", active_cancel),
        ] {
            let before = support::inventory();
            test();
            assert_eq!(support::inventory(), before);
            println!(
                "PASS {name}; actual three processes/default procfs, synthetic source callback only"
            );
        }
    });
}
