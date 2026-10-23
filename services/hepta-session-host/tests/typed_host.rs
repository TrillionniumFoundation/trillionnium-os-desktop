//! Real original sender/store regression; socket replies and trust are explicit
//! test fixtures. Deployment qualification separately exercises real Agentd.
#![cfg(target_os = "linux")]
#[allow(dead_code)]
mod support;

use codex_hepta_memory::{
    ObjectiveSenderOrigin, ProductionDurableWriter, ProductionObjectiveSender,
};
use hepta_session_host::{ObjectiveHostAuthority, TypedObjectiveHost};
use serde_json::{Value, json};
use std::io::{BufRead, BufReader, Write};
use std::sync::{
    Arc,
    atomic::{AtomicUsize, Ordering},
};
use std::time::{Duration, Instant};
use support::{Fixture, TestOnlyCheckpoint};
use trill_ui_core::objective::*;

struct Authority {
    writer: Arc<ProductionDurableWriter>,
    checkpoint: Arc<TestOnlyCheckpoint>,
    origin: ObjectiveSenderOrigin,
    original: String,
    issued: Arc<AtomicUsize>,
}
impl ObjectiveHostAuthority for Authority {
    type Checkpoint = TestOnlyCheckpoint;
    fn sender(&self) -> Result<ProductionObjectiveSender<Self::Checkpoint>, ObjectiveHostIssue> {
        self.writer
            .objective_sender(self.checkpoint.clone(), Duration::from_secs(1))
            .map_err(|_| ObjectiveHostIssue::OwnerRefused)
    }
    fn current_origin(&mut self) -> Result<ObjectiveSenderOrigin, ObjectiveHostIssue> {
        Ok(self.origin.clone())
    }
    fn run_id(&self, _: &str) -> Result<String, ObjectiveHostIssue> {
        Ok("test-only-original-run".into())
    }
    fn retained_client_intent_id(
        &self,
        _: &codex_hepta_memory::ObjectiveSenderRequest,
    ) -> Result<Option<String>, ObjectiveHostIssue> {
        // Explicit test fixture mapping; production reads its canonical source.
        Ok(Some("intent-1".into()))
    }
    fn issue(
        &mut self,
        _: &ObjectiveIntent,
        _: &ObjectiveSenderOrigin,
    ) -> Result<String, ObjectiveHostIssue> {
        self.issued.fetch_add(1, Ordering::SeqCst);
        Ok(self.original.clone())
    }
}
fn host(fixture: &Fixture, issued: &Arc<AtomicUsize>) -> TypedObjectiveHost<Authority> {
    TypedObjectiveHost::new(
        Authority {
            writer: fixture.writer.clone(),
            checkpoint: fixture.checkpoint.clone(),
            origin: fixture.origin.clone(),
            original: fixture.original.clone(),
            issued: issued.clone(),
        },
        fixture.runtime.handle().clone(),
        Duration::from_secs(2),
    )
    .unwrap()
}
fn serve(fixture: &Fixture, replies: Vec<Value>) -> std::thread::JoinHandle<Vec<Value>> {
    let listener = fixture.listener.try_clone().unwrap();
    std::thread::spawn(move || {
        replies
            .into_iter()
            .map(|reply| {
                let deadline = Instant::now() + Duration::from_secs(10);
                let (mut stream, _) = loop {
                    match listener.accept() {
                        Ok(pair) => break pair,
                        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                            assert!(Instant::now() < deadline);
                            std::thread::sleep(Duration::from_millis(1));
                        }
                        Err(error) => panic!("{error}"),
                    }
                };
                stream
                    .set_read_timeout(Some(Duration::from_secs(3)))
                    .unwrap();
                let mut frame = String::new();
                BufReader::new(stream.try_clone().unwrap())
                    .read_line(&mut frame)
                    .unwrap();
                let mut response = serde_json::to_vec(&reply).unwrap();
                response.push(b'\n');
                stream.write_all(&response).unwrap();
                serde_json::from_str(&frame).unwrap()
            })
            .collect()
    })
}
fn run_reply(fixture: &Fixture, cancel: bool) -> Value {
    let receipt = json!({"run_id":"test-only-original-run","revision":if cancel {8} else {7},"phase":if cancel {"cancelled"} else {"admitted"},"context_digest":null,"authority_epoch":71,"generation":2,"fence_digest":"1".repeat(64),"deadline_ms":4000000000000u64,"cancel_reason":null,"cancel_ack_deadline_ms":null,"terminal_observed":cancel,"idempotent":false});
    let payload = if cancel {
        json!({"type":"run_cancellation","disposition":"cancelled_before_dispatch","receipt":receipt})
    } else {
        json!({"type":"run_status","run":receipt})
    };
    json!({"schema_version":2,"request_id":19,"agent_id":fixture.origin.agent_id.as_str(),"spawn_generation":1,"current_generation":2,"payload":payload})
}

#[test]
fn restart_recovers_original_intent_without_issuing_or_submitting_again_and_cancel_uses_owner_revision()
 {
    let fixture = Fixture::new();
    let issued = Arc::new(AtomicUsize::new(0));
    let mut history = fixture.history_reply(Some(fixture.publication()), 2);
    history["request_id"] = json!(19);
    history["spawn_generation"] = json!(1);
    let submit = ObjectiveCommand::Submit {
        intent: ObjectiveIntent {
            client_intent_id: "intent-1".into(),
            text: "你好".into(),
        },
    };
    let server = serve(
        &fixture,
        vec![
            fixture.admitted(),
            history.clone(),
            run_reply(&fixture, false),
        ],
    );
    let mut first = host(&fixture, &issued);
    let view = first.handle(submit.clone());
    assert_eq!(view.stage, ObjectiveStage::Admitted);
    assert!(view.request_retained && view.publication_retained);
    assert_eq!(
        server.join().unwrap()[0]["method"]["type"],
        "objective_start"
    );
    drop(first);
    let mut recovered = host(&fixture, &issued);
    let server = serve(&fixture, vec![history.clone(), run_reply(&fixture, false)]);
    assert_eq!(recovered.handle(submit).stage, ObjectiveStage::Admitted);
    assert!(
        server
            .join()
            .unwrap()
            .iter()
            .all(|r| r["method"]["type"] != "objective_start")
    );
    assert_eq!(issued.load(Ordering::SeqCst), 1);
    let server = serve(
        &fixture,
        vec![
            history,
            run_reply(&fixture, false),
            run_reply(&fixture, true),
        ],
    );
    let view = recovered.handle(ObjectiveCommand::Cancel {
        client_intent_id: "intent-1".into(),
    });
    assert_eq!(
        view.cancellation,
        ObjectiveCancellation::CancelledBeforeDispatch
    );
    let requests = server.join().unwrap();
    assert_eq!(requests[2]["method"]["expected_revision"], 7);
    assert_eq!(fixture.retained().len(), 1);
}

#[test]
fn invalid_intent_and_missing_status_never_issue_or_retain() {
    let fixture = Fixture::new();
    let issued = Arc::new(AtomicUsize::new(0));
    let mut host = host(&fixture, &issued);
    let invalid = host.handle(ObjectiveCommand::Submit {
        intent: ObjectiveIntent {
            client_intent_id: "intent-1".into(),
            text: " ".into(),
        },
    });
    assert_eq!(invalid.issue, Some(ObjectiveHostIssue::InvalidIntent));
    assert_eq!(
        host.handle(ObjectiveCommand::Status {
            client_intent_id: "missing".into()
        })
        .issue,
        Some(ObjectiveHostIssue::NoRetainedIntent)
    );
    assert_eq!(issued.load(Ordering::SeqCst), 0);
    assert!(fixture.retained().is_empty());
    fixture.assert_no_connection();
}

#[test]
fn readiness_requires_the_original_objective_capability_without_issuing() {
    let fixture = Fixture::new();
    let issued = Arc::new(AtomicUsize::new(0));
    let mut host = host(&fixture, &issued);
    for (capabilities, expected) in [
        (json!([]), ObjectiveStage::Unavailable),
        (
            json!([{"id":"objective.start","major":1,"minor":0}]),
            ObjectiveStage::Ready,
        ),
    ] {
        let server = serve(
            &fixture,
            vec![json!({"schema_version":2,"request_id":19,
            "agent_id":fixture.origin.agent_id.as_str(),"spawn_generation":1,"current_generation":2,
            "payload":{"type":"capabilities","schema_version":1,"capabilities":capabilities}})],
        );
        assert_eq!(
            host.handle(ObjectiveCommand::Availability {}).stage,
            expected
        );
        assert_eq!(server.join().unwrap()[0]["method"]["type"], "capabilities");
    }
    assert_eq!(issued.load(Ordering::SeqCst), 0);
    assert!(fixture.retained().is_empty());
}

#[test]
fn fresh_host_recovers_navigation_from_original_owner_without_a_new_send() {
    let fixture = Fixture::new();
    let issued = Arc::new(AtomicUsize::new(0));
    drop(fixture.prepare().unwrap());
    let retained = fixture.retained();
    assert_eq!(retained.len(), 1);
    let events = fixture
        .snapshot(retained.into_iter().next().unwrap())
        .observations
        .len();
    let server = serve(
        &fixture,
        vec![json!({"schema_version":2,"request_id":19,
        "agent_id":fixture.origin.agent_id.as_str(),"spawn_generation":1,"current_generation":2,
        "payload":{"type":"capabilities","schema_version":1,
            "capabilities":[{"id":"objective.start","major":1,"minor":0}]}})],
    );
    let view = host(&fixture, &issued).handle(ObjectiveCommand::Availability {});
    assert_eq!(view.stage, ObjectiveStage::Ready);
    let recovery = view.retained_intents.unwrap();
    assert!(recovery.complete);
    assert_eq!(recovery.client_intent_ids, ["intent-1"]);
    let wire = server.join().unwrap();
    assert_eq!(wire.len(), 1);
    assert_eq!(wire[0]["method"]["type"], "capabilities");
    assert_eq!(issued.load(Ordering::SeqCst), 0);
    let retained = fixture.retained();
    assert_eq!(retained.len(), 1);
    assert_eq!(
        fixture
            .snapshot(retained.into_iter().next().unwrap())
            .observations
            .len(),
        events
    );
    fixture.assert_no_connection();
}
