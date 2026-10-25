use super::*;
use std::sync::mpsc::{self, Receiver};
use trill_ui_core::objective::{ObjectiveObservation, ObjectiveRetainedIntents, ObjectiveStage};
use trill_ui_core::Request;

fn fixture() -> (DesktopComposition, Receiver<Request>, Receiver<Request>) {
    let (mut desktop, _) = super::super::observation_freshness_tests::queued_desktop();
    let (actions, requests) = mpsc::sync_channel(8);
    let (polls, observations) = mpsc::sync_channel(8);
    desktop.bridge.actions = actions;
    desktop.bridge.objective_polls = polls;
    desktop.connected = true;
    desktop.session_instance = Some("current-session".into());
    desktop
        .drafts
        .composer_mut(desktop.workspace)
        .edit("原始草稿 · Native Notes".into());
    let mut ready = ObjectiveObservation::new(None, ObjectiveStage::Ready);
    ready.retained_intents = Some(ObjectiveRetainedIntents {
        client_intent_ids: vec![],
        complete: true,
    });
    desktop
        .objectives
        .observe("current-session", ready, Instant::now());
    let composition = DesktopComposition {
        desktop,
        refresh_pending: false,
        closed: false,
        displayed_recovery_warning: None,
        chat_config: Ok(None),
        chat: None,
        chat_started: false,
        last_native_tab: NativeWorkspaceTab::Conversations,
    };
    (composition, requests, observations)
}

fn source(composition: &DesktopComposition) -> RoomKey {
    RoomKey {
        epoch: composition.workspace().presentation_epoch(),
        local_id: composition.workspace().active_id(),
    }
}

#[test]
fn native_notes_use_the_original_bridge_and_one_intent_without_changing_the_draft() {
    let (mut composition, requests, observations) = fixture();
    let source = source(&composition);
    let original = composition.workspace().draft().clone();
    assert!(composition.notes_view().unwrap().can_write);
    composition.request_write_note(source).unwrap();
    let Request::ObjectiveSubmit {
        client_intent_id,
        text,
        expected_instance,
    } = requests.try_recv().unwrap()
    else {
        panic!("the original Objective bridge receives a typed request");
    };
    assert_eq!(expected_instance, "current-session");
    assert_eq!(text, original.text);
    assert_eq!(composition.workspace().draft(), &original);
    assert!(
        composition.request_write_note(source).is_err(),
        "unknown submit cannot create another intent"
    );
    composition.request_notes_refresh(source).unwrap();
    assert!(
        matches!(observations.try_recv().unwrap(), Request::ObjectiveStatus { client_intent_id: observed, expected_instance }
        if observed == client_intent_id && expected_instance == "current-session")
    );
    composition.request_notes_cancel(source).unwrap();
    assert!(
        matches!(requests.try_recv().unwrap(), Request::ObjectiveCancel { client_intent_id: cancelled, expected_instance }
        if cancelled == client_intent_id && expected_instance == "current-session")
    );
    assert!(composition.request_notes_cancel(source).is_err());
    assert!(requests.try_recv().is_err());
    assert_eq!(composition.workspace().draft(), &original);
}

#[test]
fn native_notes_callbacks_recheck_the_original_source_and_editor_fences() {
    for case in 0..6 {
        let (mut composition, requests, observations) = fixture();
        let mut source = source(&composition);
        match case {
            0 => source.epoch = source.epoch.saturating_add(1),
            1 => source.local_id = source.local_id.saturating_add(1),
            2 => composition.workspace_mut().composing = true,
            3 => composition.workspace_mut().navigation_open = true,
            4 => composition.workspace_mut().tab = NativeWorkspaceTab::Console,
            5 => composition.closed = true,
            _ => unreachable!(),
        }
        assert!(
            composition.request_write_note(source).is_err(),
            "fence case {case}"
        );
        assert!(
            composition.request_notes_refresh(source).is_err(),
            "fence case {case}"
        );
        assert!(
            composition.request_notes_cancel(source).is_err(),
            "fence case {case}"
        );
        assert!(requests.try_recv().is_err());
        assert!(observations.try_recv().is_err());
        assert_eq!(
            composition.workspace().draft().text,
            "原始草稿 · Native Notes"
        );
    }
}

#[test]
fn native_notes_host_freshness_is_rechecked_after_a_rendered_button() {
    let (mut composition, requests, _) = fixture();
    let source = source(&composition);
    assert!(composition.notes_view().unwrap().can_write);
    composition.desktop.objectives.invalidate();
    assert!(composition.request_write_note(source).is_err());
    assert!(!composition.notes_view().unwrap().can_write);
    assert!(requests.try_recv().is_err());
    assert_eq!(
        composition.workspace().draft().text,
        "原始草稿 · Native Notes"
    );
}
