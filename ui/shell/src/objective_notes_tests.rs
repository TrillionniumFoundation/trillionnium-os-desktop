use super::*;
use std::sync::mpsc::{self, Receiver};
use trill_ui_core::conversation::{ContextRef, HeptaRuntimeContext};
use trill_ui_core::objective::{NotesDocumentObservation, ObjectiveRetainedIntents};

fn fixture() -> (Desktop, Receiver<Request>) {
    let (mut desktop, _) = super::super::observation_freshness_tests::queued_desktop();
    let (actions, requests) = mpsc::sync_channel(8);
    desktop.bridge.actions = actions;
    desktop.connected = true;
    desktop.session_instance = Some("session".into());
    desktop
        .drafts
        .composer_mut(desktop.workspace)
        .edit("保留原始草稿".into());
    let mut ready = ObjectiveObservation::new(None, ObjectiveStage::Ready);
    ready.retained_intents = Some(ObjectiveRetainedIntents {
        client_intent_ids: vec![],
        complete: true,
    });
    desktop.objectives.observe("session", ready, Instant::now());
    (desktop, requests)
}

#[test]
fn shared_notes_actions_preserve_quoted_context_and_refuse_to_drop_it_to_submit() {
    let (mut desktop, requests) = fixture();
    let context = ContextRef::HeptaRuntime(HeptaRuntimeContext {
        session_instance: "session".into(),
        agent_id: "agent".into(),
        spawn_generation: 1,
        process_id: 7,
        quoted_current_generation: 1,
        quoted_lifecycle: "observed".into(),
        sampled_unix_ms: unix_ms(),
    });
    desktop
        .drafts
        .composer_mut(desktop.workspace)
        .contexts
        .push(context.clone());
    assert!(!desktop.notes_controls_view().can_write);
    assert!(desktop.write_note_from_draft().is_err());
    assert_eq!(
        desktop.drafts.composer(desktop.workspace).contexts,
        vec![context]
    );
    assert_eq!(
        desktop.drafts.composer(desktop.workspace).text(),
        "保留原始草稿"
    );
    assert!(requests.try_recv().is_err());
}

#[test]
fn shared_notes_submission_rechecks_fresh_source_and_keeps_a_single_original_intent() {
    let (mut desktop, requests) = fixture();
    assert!(desktop.notes_controls_view().can_write);
    desktop.write_note_from_draft().unwrap();
    let Request::ObjectiveSubmit {
        client_intent_id, ..
    } = requests.try_recv().unwrap()
    else {
        panic!("typed Objective submit");
    };
    assert!(desktop.write_note_from_draft().is_err());
    desktop.cancel_note_request().unwrap();
    assert!(
        matches!(requests.try_recv().unwrap(), Request::ObjectiveCancel { client_intent_id: cancelled, .. } if cancelled == client_intent_id)
    );
    assert!(desktop.cancel_note_request().is_err());
    let mut unknown = desktop.objectives.intents[0].observation.clone();
    unknown.cancellation = trill_ui_core::objective::ObjectiveCancellation::Unknown;
    desktop
        .objectives
        .observe("session", unknown, Instant::now());
    assert!(
        desktop.cancel_note_request().is_err(),
        "uncertain cancellation is observed, never automatically repeated"
    );
    assert!(requests.try_recv().is_err());
    desktop.objectives.follow_session("replacement-session");
    desktop.session_instance = Some("replacement-session".into());
    assert!(!desktop.notes_controls_view().can_write);
    assert!(desktop.write_note_from_draft().is_err());
    assert_eq!(desktop.objectives.intents[0].id, client_intent_id);
}

#[test]
fn independent_document_readback_has_its_own_freshness_and_never_replaces_the_draft() {
    let (mut desktop, requests) = fixture();
    let original = desktop.drafts.composer(desktop.workspace).text().to_owned();
    let target = trill_ui_core::notes::NotesTargetIdentity {
        session_instance: "a".repeat(32),
        task_id: 8,
        incarnation: "b".repeat(32),
    };
    let mut observation = desktop
        .objectives
        .availability
        .as_ref()
        .unwrap()
        .observation
        .clone();
    observation.notes_document = Some(NotesDocumentObservation {
        target: target.clone(),
        observed_unix_ms: unix_ms().saturating_sub(3_001),
        revision: 9,
        text_sha256: "c".repeat(64),
        receipt_pending: true,
    });
    desktop
        .objectives
        .observe("session", observation.clone(), Instant::now());
    let stale = desktop.notes_controls_view();
    assert!(
        stale.can_write,
        "a stale snapshot cannot replace the original fresh availability observation"
    );
    assert!(stale
        .status
        .contains("Notes readback (last observed; refresh pending)"));
    assert!(stale.status.contains(&target.destination_id()));
    assert!(stale.status.contains("document revision 9"));
    assert!(stale.status.contains("cccccccccccc"));
    assert!(stale.status.contains("receipt pending: true"));
    observation
        .notes_document
        .as_mut()
        .unwrap()
        .observed_unix_ms = unix_ms();
    desktop
        .objectives
        .observe("session", observation, Instant::now());
    assert!(desktop
        .notes_controls_view()
        .status
        .contains("Notes readback:"));
    assert!(
        !desktop.notes_controls_view().can_write,
        "fresh pending receipt blocks a new intent"
    );
    assert!(desktop.write_note_from_draft().is_err());
    assert!(requests.try_recv().is_err());
    assert!(desktop.objectives.intents.is_empty());
    assert_eq!(desktop.drafts.composer(desktop.workspace).text(), original);
}

#[test]
fn ready_with_an_observation_issue_never_enables_a_new_notes_intent() {
    let (mut desktop, requests) = fixture();
    let mut observation = desktop
        .objectives
        .availability
        .as_ref()
        .unwrap()
        .observation
        .clone();
    observation.issue = Some(trill_ui_core::objective::ObjectiveHostIssue::TransportUnknown);
    desktop
        .objectives
        .observe("session", observation, Instant::now());
    assert!(!desktop.notes_controls_view().can_write);
    assert!(desktop.write_note_from_draft().is_err());
    assert!(requests.try_recv().is_err());
    assert!(desktop.objectives.intents.is_empty());
    assert_eq!(
        desktop.drafts.composer(desktop.workspace).text(),
        "保留原始草稿"
    );
}

#[test]
fn passive_status_rotation_reconciles_all_original_recovered_ids_before_unblocking_write() {
    let (mut desktop, requests) = fixture();
    let mut availability = desktop
        .objectives
        .availability
        .as_ref()
        .unwrap()
        .observation
        .clone();
    let ids = ["earlier-original", "middle-original", "latest-original"];
    availability
        .retained_intents
        .as_mut()
        .unwrap()
        .client_intent_ids = ids.iter().map(|id| (*id).into()).collect();
    desktop
        .objectives
        .observe("session", availability, Instant::now());
    assert!(!desktop.notes_controls_view().can_write);
    let now = Instant::now();
    let mut queried = std::collections::BTreeSet::new();
    for tick in 0..10 {
        match desktop
            .objectives
            .poll(
                desktop.workspace,
                "session",
                now + Duration::from_millis(tick * 701),
            )
            .unwrap()
        {
            Request::ObjectiveStatus {
                client_intent_id, ..
            } => {
                queried.insert(client_intent_id);
            }
            Request::ObjectiveAvailability { .. } => {}
            _ => panic!("passive reconciliation must never submit or cancel"),
        }
    }
    assert_eq!(queried, ids.into_iter().map(str::to_owned).collect());
    for (index, id) in ids.into_iter().enumerate() {
        let mut terminal = ObjectiveObservation::new(Some(id.into()), ObjectiveStage::Admitted);
        terminal.run = Some(trill_ui_core::objective::ObjectiveRunObservation {
            revision: 1,
            phase: trill_ui_core::objective::ObjectiveRunPhase::Succeeded,
            terminal_observed: true,
        });
        desktop
            .objectives
            .observe("session", terminal, Instant::now());
        assert_eq!(
            desktop.notes_controls_view().can_write,
            index == ids.len() - 1
        );
    }
    assert!(requests.try_recv().is_err());
    assert_eq!(desktop.objectives.intents.len(), ids.len());
    assert_eq!(
        desktop.drafts.composer(desktop.workspace).text(),
        "保留原始草稿"
    );
}

#[test]
fn a_full_passive_queue_keeps_the_selected_original_read_until_it_is_accepted() {
    let (mut desktop, requests) = fixture();
    let (polls, observed) = mpsc::sync_channel(1);
    desktop.bridge.objective_polls = polls;
    let mut availability = desktop
        .objectives
        .availability
        .as_ref()
        .unwrap()
        .observation
        .clone();
    availability
        .retained_intents
        .as_mut()
        .unwrap()
        .client_intent_ids = vec!["earlier-original".into(), "latest-original".into()];
    desktop
        .objectives
        .observe("session", availability, Instant::now());
    desktop.poll_notes_controls();
    assert!(
        matches!(observed.try_recv().unwrap(), Request::ObjectiveStatus { client_intent_id, .. } if client_intent_id == "latest-original")
    );
    desktop.objectives.last_query = None;
    desktop.poll_notes_controls();
    assert!(matches!(
        observed.try_recv().unwrap(),
        Request::ObjectiveAvailability { .. }
    ));
    assert!(desktop
        .bridge
        .poll_objective(Request::ObjectiveAvailability {
            expected_instance: "already-pending".into()
        }));
    desktop.objectives.last_query = None;
    desktop.poll_notes_controls(); // earlier-original cannot enter this full queue.
    assert!(
        matches!(observed.try_recv().unwrap(), Request::ObjectiveAvailability { expected_instance } if expected_instance == "already-pending")
    );
    desktop.objectives.last_query = None;
    desktop.poll_notes_controls();
    assert!(
        matches!(observed.try_recv().unwrap(), Request::ObjectiveStatus { client_intent_id, .. } if client_intent_id == "earlier-original")
    );
    assert!(requests.try_recv().is_err());
    assert_eq!(desktop.objectives.intents.len(), 2);
}

#[test]
fn session_replacement_never_rebinds_a_recent_old_document_snapshot() {
    let (mut desktop, requests) = fixture();
    desktop.write_note_from_draft().unwrap();
    let Request::ObjectiveSubmit {
        client_intent_id, ..
    } = requests.try_recv().unwrap()
    else {
        panic!("original request");
    };
    let target = trill_ui_core::notes::NotesTargetIdentity {
        session_instance: "a".repeat(32),
        task_id: 8,
        incarnation: "b".repeat(32),
    };
    desktop.objectives.intents[0].observation.notes_document = Some(NotesDocumentObservation {
        target: target.clone(),
        observed_unix_ms: unix_ms(),
        revision: 9,
        text_sha256: "c".repeat(64),
        receipt_pending: false,
    });
    assert!(desktop
        .notes_controls_view()
        .status
        .contains(&target.destination_id()));
    desktop.objectives.follow_session("replacement-session");
    desktop.session_instance = Some("replacement-session".into());
    let mut available = ObjectiveObservation::new(None, ObjectiveStage::Ready);
    available.retained_intents = Some(ObjectiveRetainedIntents {
        client_intent_ids: vec![client_intent_id.clone()],
        complete: true,
    });
    desktop
        .objectives
        .observe("replacement-session", available, Instant::now());
    let view = desktop.notes_controls_view();
    assert!(view.status.contains("Notes readback unavailable"));
    assert!(!view.status.contains(&target.destination_id()));
    assert!(desktop.objectives.intents[0]
        .observation
        .notes_document
        .is_none());
    assert_eq!(desktop.objectives.intents[0].id, client_intent_id);
    assert!(!view.can_write);
    assert!(requests.try_recv().is_err());
}
