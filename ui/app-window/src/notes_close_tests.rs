use super::*;
use eframe::egui::{RawInput, ViewportCommand, ViewportEvent, ViewportId};
use std::sync::{Arc, Mutex};

fn channel() -> (
    NotesAppChannel,
    mpsc::Receiver<worker::Command>,
    Arc<Mutex<worker::Projection>>,
) {
    let (sender, receiver) = mpsc::sync_channel(4);
    let projection = Arc::new(Mutex::new(worker::Projection::default()));
    let channel = NotesAppChannel::from_worker(worker::Connection {
        sender,
        projection: projection.clone(),
        durable: true,
        lifetime: None,
    });
    (channel, receiver, projection)
}

fn close_input() -> RawInput {
    let mut input = RawInput::default();
    input
        .viewports
        .get_mut(&ViewportId::ROOT)
        .unwrap()
        .events
        .push(ViewportEvent::Close);
    input
}

fn commands(output: egui::FullOutput) -> Vec<ViewportCommand> {
    output
        .viewport_output
        .get(&ViewportId::ROOT)
        .unwrap()
        .commands
        .clone()
}

#[test]
fn native_close_in_final_typing_frame_waits_for_the_save_acknowledgement() {
    let (mut channel, receiver, projection) = channel();
    let ctx = egui::Context::default();
    let output = ctx.run(close_input(), |ctx| {
        assert!(channel.local_edit_at(0, "last typed characters / 最后编辑".into()));
        channel.handle_close(ctx);
    });
    assert_eq!(channel.close_state(), NotesCloseState::Saving);
    assert!(commands(output).contains(&ViewportCommand::CancelClose));
    let worker::Command::LocalEdit { id, revision, text } = receiver.try_recv().unwrap() else {
        panic!("close must preserve the queued edit");
    };
    assert_eq!(revision, 0);
    *projection.lock().unwrap() = worker::Projection {
        version: 1,
        revision: 1,
        text,
        local_result: Some((id, true, 1)),
        ..Default::default()
    };
    let output = ctx.run(RawInput::default(), |ctx| {
        channel.poll();
        channel.handle_close(ctx);
    });
    assert_eq!(channel.close_state(), NotesCloseState::Ready);
    assert!(commands(output).contains(&ViewportCommand::Close));
}

#[test]
fn failed_storage_retains_the_draft_and_requires_explicit_discard_to_close() {
    let (mut channel, receiver, projection) = channel();
    assert!(channel.local_edit_at(0, "preserve the unsaved draft".into()));
    let worker::Command::LocalEdit { id, .. } = receiver.try_recv().unwrap() else {
        panic!("expected local edit");
    };
    *projection.lock().unwrap() = worker::Projection {
        version: 1,
        storage_failed: true,
        local_result: Some((id, false, 0)),
        ..Default::default()
    };
    channel.poll();
    let ctx = egui::Context::default();
    let output = ctx.run(close_input(), |ctx| channel.handle_close(ctx));
    assert_eq!(channel.text(), "preserve the unsaved draft");
    assert_eq!(channel.close_state(), NotesCloseState::Unsaved);
    assert!(commands(output).contains(&ViewportCommand::CancelClose));
    channel.keep_open();
    assert!(!channel.close_requested());
    channel.discard_and_close();
    channel.keep_open();
    assert_eq!(channel.close_state(), NotesCloseState::Unsaved);
    channel.discard_and_close();
    let output = ctx.run(RawInput::default(), |ctx| channel.handle_close(ctx));
    assert!(commands(output).contains(&ViewportCommand::Close));
}

#[test]
fn revision_conflict_does_not_close_or_replace_the_unsaved_draft() {
    let (mut channel, receiver, projection) = channel();
    channel.local_edit_at(0, "user draft".into());
    let worker::Command::LocalEdit { id, .. } = receiver.try_recv().unwrap() else {
        panic!("expected local edit");
    };
    *projection.lock().unwrap() = worker::Projection {
        version: 1,
        revision: 1,
        text: "independently applied effect".into(),
        local_result: Some((id, false, 1)),
        ..Default::default()
    };
    channel.poll();
    let ctx = egui::Context::default();
    let output = ctx.run(close_input(), |ctx| channel.handle_close(ctx));
    assert_eq!(channel.text(), "user draft");
    assert_eq!(channel.revision(), 1);
    assert_eq!(channel.close_state(), NotesCloseState::Unsaved);
    assert!(commands(output).contains(&ViewportCommand::CancelClose));
    assert!(
        receiver.try_recv().is_err(),
        "close must never retry an edit"
    );
}

#[test]
fn committed_input_waiting_in_the_native_queue_defers_close_until_drained() {
    let (mut channel, _, _) = channel();
    channel.input_queue_changed(true);
    let ctx = egui::Context::default();
    let output = ctx.run(close_input(), |ctx| channel.handle_close(ctx));
    assert_eq!(channel.close_state(), NotesCloseState::Saving);
    assert!(commands(output).contains(&ViewportCommand::CancelClose));
    channel.input_queue_changed(false);
    let output = ctx.run(RawInput::default(), |ctx| channel.handle_close(ctx));
    assert!(commands(output).contains(&ViewportCommand::Close));
}

#[test]
fn composition_keeps_its_original_revision_and_only_explicit_keep_rebases() {
    let (mut channel, receiver, projection) = channel();
    *projection.lock().unwrap() = worker::Projection {
        version: 1,
        revision: 1,
        text: "external result".into(),
        ..Default::default()
    };
    channel.poll();
    assert!(channel.local_edit_at(0, "confirmed composition from revision zero".into()));
    assert!(channel.has_conflict());
    assert_eq!(channel.close_state(), NotesCloseState::Unsaved);
    assert!(
        receiver.try_recv().is_err(),
        "stale commit must never be dispatched"
    );
    channel.keep_local_after_conflict();
    let worker::Command::LocalEdit { revision, text, .. } = receiver.try_recv().unwrap() else {
        panic!("expected explicit local rebase");
    };
    assert_eq!(revision, 1);
    assert_eq!(text, "confirmed composition from revision zero");
}

#[test]
fn discarding_conflict_loads_the_saved_projection_without_another_write() {
    let (mut channel, receiver, projection) = channel();
    *projection.lock().unwrap() = worker::Projection {
        version: 1,
        revision: 1,
        text: "external result".into(),
        ..Default::default()
    };
    channel.poll();
    channel.local_edit_at(0, "stale composition".into());
    channel.discard_local_after_conflict();
    assert_eq!(channel.text(), "external result");
    assert_eq!(channel.close_state(), NotesCloseState::Ready);
    assert!(!channel.has_conflict());
    assert!(receiver.try_recv().is_err());
}

#[test]
fn a_stalled_save_can_be_explicitly_closed_without_cancelling_or_repeating_the_edit() {
    let (mut channel, receiver, _) = channel();
    channel.local_edit_at(0, "in-flight local edit".into());
    assert!(matches!(
        receiver.try_recv().unwrap(),
        worker::Command::LocalEdit { .. }
    ));
    let ctx = egui::Context::default();
    let output = ctx.run(close_input(), |ctx| channel.handle_close(ctx));
    assert_eq!(channel.close_state(), NotesCloseState::Saving);
    assert!(commands(output).contains(&ViewportCommand::CancelClose));
    // No worker acknowledgement is available. The user can choose to stop
    // waiting, without making any claim that the original save did not happen.
    channel.discard_and_close();
    let output = ctx.run(RawInput::default(), |ctx| channel.handle_close(ctx));
    assert!(commands(output).contains(&ViewportCommand::Close));
    assert_eq!(channel.text(), "in-flight local edit");
    assert!(
        receiver.try_recv().is_err(),
        "closing never cancels or repeats the save"
    );
}
