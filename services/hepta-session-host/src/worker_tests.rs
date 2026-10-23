//! Real worker-thread scheduling tests. The handler is an explicit queue-only
//! fixture; original sender/store and Agentd contracts have separate tests.
use super::*;
use std::sync::mpsc;
use std::time::Duration;

fn blocked_worker() -> (
    ObjectiveWorker,
    mpsc::Receiver<ObjectiveCommand>,
    mpsc::Sender<()>,
) {
    let (observed, received) = mpsc::channel();
    let (resume, blocked) = mpsc::channel();
    let mut first = true;
    let worker = ObjectiveWorker::spawn_handler(move |command| {
        observed.send(command.clone()).unwrap();
        if first {
            first = false;
            blocked.recv_timeout(Duration::from_secs(5)).unwrap();
        }
        ObjectiveObservation::new(
            command.client_intent_id().map(str::to_owned),
            ObjectiveStage::Ready,
        )
    })
    .unwrap();
    worker.request(ObjectiveCommand::Availability {});
    assert_eq!(
        received.recv_timeout(Duration::from_secs(5)).unwrap(),
        ObjectiveCommand::Availability {}
    );
    (worker, received, resume)
}

#[test]
fn passive_flood_cannot_consume_cancel_slots_or_overtake_submit() {
    let (worker, received, resume) = blocked_worker();
    for _ in 0..2_000 {
        assert_eq!(
            worker.request(ObjectiveCommand::Availability {}).issue,
            None
        );
        assert_eq!(
            worker
                .request(ObjectiveCommand::Status {
                    client_intent_id: "intent-one".into(),
                })
                .issue,
            None
        );
    }
    let submit = ObjectiveCommand::Submit {
        intent: ObjectiveIntent {
            client_intent_id: "intent-one".into(),
            text: "note".into(),
        },
    };
    let cancel = ObjectiveCommand::Cancel {
        client_intent_id: "intent-one".into(),
    };
    assert_eq!(worker.request(submit.clone()).issue, None);
    assert_eq!(worker.request(cancel.clone()).issue, None);
    {
        let pending = worker.queue.pending.lock().unwrap();
        assert_eq!(pending.passive.len(), 2);
        assert_eq!(pending.actions.len(), 2);
    }
    resume.send(()).unwrap();
    assert_eq!(
        received.recv_timeout(Duration::from_secs(5)).unwrap(),
        submit
    );
    assert_eq!(
        received.recv_timeout(Duration::from_secs(5)).unwrap(),
        cancel
    );
    drop(worker);
}

#[test]
fn explicit_actions_remain_bounded_and_do_not_create_a_fallback_dispatch() {
    let (worker, received, resume) = blocked_worker();
    for index in 0..ACTION_CAPACITY {
        assert_eq!(
            worker
                .request(ObjectiveCommand::Submit {
                    intent: ObjectiveIntent {
                        client_intent_id: format!("intent-{index}"),
                        text: "note".into()
                    },
                })
                .issue,
            None
        );
    }
    assert_eq!(
        worker
            .request(ObjectiveCommand::Cancel {
                client_intent_id: "intent-0".into(),
            })
            .issue,
        Some(ObjectiveHostIssue::Capacity)
    );
    drop(worker);
    resume.send(()).unwrap();
    assert_eq!(
        received.recv_timeout(Duration::from_secs(5)),
        Err(mpsc::RecvTimeoutError::Disconnected)
    );
}

#[test]
fn dropping_the_host_prevents_pending_submit_from_starting_afterward() {
    let (worker, received, resume) = blocked_worker();
    worker.request(ObjectiveCommand::Submit {
        intent: ObjectiveIntent {
            client_intent_id: "pending".into(),
            text: "note".into(),
        },
    });
    drop(worker);
    resume.send(()).unwrap();
    assert_eq!(
        received.recv_timeout(Duration::from_secs(5)),
        Err(mpsc::RecvTimeoutError::Disconnected)
    );
}
