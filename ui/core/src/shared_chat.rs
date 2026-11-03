//! Default-off Desktop adapter to the exact Hepta #3067 shared presenter.
//!
//! `SharedComposer` contains the sole active draft. The native feature borrows
//! that same workspace for the original App; this grants no owner or I/O API.
//! Desktop's existing Session task/context observations remain separate. Saving
//! an immutable local archive does not turn it into an observed chat message.

pub use hepta_control_core::chat::ChatWorkspace;
pub use hepta_control_core::chat::ComposeStatus;
pub use hepta_control_core::chat::LocalDraftArchive;
#[cfg(feature = "hepta-native-makepad")]
pub use hepta_control_core::chat::WorkspaceTab as NativeWorkspaceTab;
use hepta_robrix_ui::presentation::{
    apply_action, project, PresentationAction, PresentationCommand, TimelineWindow,
};
pub use hepta_robrix_ui::presentation::{ActionResult, ChatPresentation, RoomKey};
#[cfg(feature = "hepta-native-makepad")]
pub use hepta_robrix_ui::{makepad_widgets, native_presentation};

#[derive(Default)]
pub struct SharedComposer {
    workspace: ChatWorkspace,
}

impl SharedComposer {
    /// Includes the original owner's parked local text partitions. The archive
    /// contains no authority, and restoration never activates a named account.
    pub fn export_local_archive(&self) -> Result<LocalDraftArchive, &'static str> {
        self.workspace.archive_local_drafts()
    }

    pub fn restore_local_archive(
        &mut self,
        archive: LocalDraftArchive,
    ) -> Result<(), &'static str> {
        self.workspace = ChatWorkspace::from_local_draft_archive(archive)?;
        Ok(())
    }

    /// The original renderer borrows this sole owner; it must never copy the
    /// draft or use a task observation to install chat authority.
    #[cfg(feature = "hepta-native-makepad")]
    pub fn native_workspace(&self) -> &ChatWorkspace {
        &self.workspace
    }

    #[cfg(feature = "hepta-native-makepad")]
    pub fn native_workspace_mut(&mut self) -> &mut ChatWorkspace {
        &mut self.workspace
    }

    /// Snapshot every local room, not the selected editor alone. Room keys,
    /// owners, delivery attempts and observed history are never persisted here.
    pub fn export_local_rooms(&self) -> Result<(Vec<String>, usize), &'static str> {
        if self.workspace.composing {
            return Err("IME composition is active; checkpoint deferred");
        }
        let mut active = None;
        let mut rooms = Vec::new();
        for (id, draft) in self.workspace.drafts() {
            if id == self.workspace.active_id() {
                active = Some(rooms.len());
            }
            rooms.push(draft.text.clone());
        }
        Ok((rooms, active.ok_or("Missing active local room")?))
    }

    /// Restore into a fresh original workspace using its own validated edits.
    /// Only local text survives restart; no owner or timeline is reconstituted.
    pub fn restore_local_rooms(
        &mut self,
        rooms: &[String],
        active: usize,
    ) -> Result<(), &'static str> {
        if rooms.is_empty()
            || rooms.len() > hepta_control_core::chat::MAX_LOCAL_DRAFTS
            || active >= rooms.len()
        {
            return Err("Invalid local room checkpoint");
        }
        let mut restored = ChatWorkspace::default();
        let mut selected = None;
        for (index, text) in rooms.iter().enumerate() {
            if index != 0 && !restored.new_draft() {
                return Err("Original composer refused a restored room");
            }
            if !restored.edit(text.clone()) {
                return Err("Original composer refused restored text");
            }
            if index == active {
                selected = Some(restored.active_id());
            }
        }
        if !restored.select(selected.ok_or("Missing restored active room")?) {
            return Err("Original composer refused restored selection");
        }
        self.workspace = restored;
        Ok(())
    }

    pub fn text(&self) -> &str {
        &self.workspace.draft().text
    }

    /// Borrow the original presenter. Task snapshots are never injected into
    /// the original timeline or used to install an authenticated chat owner.
    pub fn presentation(&self, now_ms: u64) -> ChatPresentation<'_> {
        project(&self.workspace, now_ms, TimelineWindow::default())
    }

    pub fn source(&self) -> RoomKey {
        RoomKey {
            epoch: self.workspace.presentation_epoch(),
            local_id: self.workspace.active_id(),
        }
    }

    /// One complete editor transaction; rejecting it preserves the old text,
    /// including a selection that the widget deleted before inserting a paste.
    pub fn edit(&mut self, source: RoomKey, text: String) -> ActionResult {
        self.apply(source, PresentationCommand::Edit(text))
    }

    /// The renderer supplies its actual IME lifecycle, never a guessed timeout.
    pub fn set_composing(&mut self, composing: bool) -> ActionResult {
        self.apply(self.source(), PresentationCommand::SetComposing(composing))
    }

    pub fn can_save_local(&self) -> Result<(), &'static str> {
        if self.workspace.composing {
            return Err("IME composition is active; local draft was not saved or cleared.");
        }
        if self.workspace.draft().status == ComposeStatus::InputLimit {
            return Err("The last edit was rejected (16 KiB or NUL); previous text is kept. Edit it before saving.");
        }
        Ok(())
    }

    /// Called only after Desktop validates local archive capacity and context.
    /// It deliberately does not create an observed history entry or a delivery.
    pub fn clear(&mut self, source: RoomKey) -> ActionResult {
        self.apply(source, PresentationCommand::Clear)
    }

    /// Retains the original refusal. This is not connected to Objective submit,
    /// AuthBus signing, an owner port, or Desktop's local task transport.
    pub fn request_send(&mut self, source: RoomKey) -> ActionResult {
        self.apply(source, PresentationCommand::RequestSend)
    }

    fn apply(&mut self, source: RoomKey, command: PresentationCommand) -> ActionResult {
        apply_action(&mut self.workspace, PresentationAction { source, command })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::conversation::MAX_DRAFT_BYTES;
    use hepta_robrix_ui::presentation::{EmptyState, TimelineStatus};

    #[test]
    fn edit_and_projection_borrow_the_one_original_draft() {
        let mut draft = SharedComposer::default();
        assert_eq!(
            draft.edit(draft.source(), "中文 📝".into()),
            ActionResult::Applied
        );
        let view = draft.presentation(42);
        assert_eq!(view.composer.text, "中文 📝");
        assert_eq!(view.composer.text.as_ptr(), draft.text().as_ptr());
        assert_eq!(view.timeline.status, TimelineStatus::LocalOnly);
        assert_eq!(view.timeline.empty_state, Some(EmptyState::LocalDraft));
        assert!(view.timeline.messages.is_empty());
        assert!(view.composer.delivery.is_none());
    }

    #[test]
    fn whole_utf8_edit_rejects_without_losing_selection_or_earlier_draft() {
        let mut draft = SharedComposer::default();
        let original = "保留这段 selected text";
        draft.edit(draft.source(), original.into());
        assert_eq!(
            draft.edit(draft.source(), "界".repeat(MAX_DRAFT_BYTES / 3 + 1)),
            ActionResult::Rejected
        );
        assert_eq!(draft.text(), original);
        assert_eq!(
            *draft.presentation(0).composer.status,
            ComposeStatus::InputLimit
        );
        assert!(draft.can_save_local().is_err());
        assert_eq!(
            draft.edit(draft.source(), "新输入".into()),
            ActionResult::Applied
        );
        assert!(draft.can_save_local().is_ok());
    }

    #[test]
    fn byte_limit_is_exact_and_never_truncates_a_unicode_scalar() {
        let mut draft = SharedComposer::default();
        let edge = format!("{}a", "界".repeat(MAX_DRAFT_BYTES / 3));
        assert_eq!(edge.len(), MAX_DRAFT_BYTES);
        assert_eq!(
            draft.edit(draft.source(), edge.clone()),
            ActionResult::Applied
        );
        assert_eq!(
            draft.edit(draft.source(), format!("{edge}é")),
            ActionResult::Rejected
        );
        assert_eq!(draft.text(), edge);
        assert_eq!(
            draft.edit(draft.source(), "bad\0input".into()),
            ActionResult::Rejected
        );
        assert_eq!(draft.text(), edge);
    }

    #[test]
    fn actual_composition_lifecycle_blocks_save_clear_and_send() {
        let mut draft = SharedComposer::default();
        draft.edit(draft.source(), "输入候选".into());
        assert_eq!(draft.set_composing(true), ActionResult::Applied);
        assert!(draft.presentation(0).composer.composing);
        assert!(draft.can_save_local().is_err());
        assert_eq!(draft.clear(draft.source()), ActionResult::Ignored);
        assert_eq!(draft.request_send(draft.source()), ActionResult::Ignored);
        assert_eq!(draft.text(), "输入候选");
        draft.set_composing(false);
        assert!(draft.can_save_local().is_ok());
        assert_eq!(
            draft.request_send(draft.source()),
            ActionResult::SendUnavailable
        );
        assert_eq!(draft.text(), "输入候选");
        assert!(draft.presentation(0).timeline.messages.is_empty());
    }

    #[test]
    fn stale_presenter_events_cannot_edit_or_clear_current_draft() {
        let mut draft = SharedComposer::default();
        draft.edit(draft.source(), "keep".into());
        let wrong = RoomKey {
            epoch: draft.source().epoch + 1,
            ..draft.source()
        };
        assert_eq!(draft.edit(wrong, "late".into()), ActionResult::Stale);
        assert_eq!(draft.clear(wrong), ActionResult::Stale);
        assert_eq!(draft.request_send(wrong), ActionResult::Stale);
        assert_eq!(draft.text(), "keep");
    }

    #[test]
    fn repeated_send_refusal_never_creates_transcript_delivery_or_clears_text() {
        let mut draft = SharedComposer::default();
        draft.edit(draft.source(), "unsubmitted".into());
        for _ in 0..3 {
            assert_eq!(
                draft.request_send(draft.source()),
                ActionResult::SendUnavailable
            );
        }
        let view = draft.presentation(100);
        assert_eq!(view.composer.text, "unsubmitted");
        assert_eq!(*view.composer.status, ComposeStatus::TransportUnavailable);
        assert_eq!(view.rooms.len(), 1);
        assert!(view.composer.delivery.is_none());
        assert!(view.timeline.messages.is_empty());
        assert_eq!(view.timeline.thread_id, None);
    }

    #[test]
    fn history_bound_draft_recovers_as_local_text_without_history_or_authority() {
        use hepta_control_core::chat_timeline::{History, ViewFence};
        let mut draft = SharedComposer::default();
        draft.edit(draft.source(), "尚未提交的中文".into());
        let ticket = draft
            .workspace
            .begin_history(
                0,
                "observed-thread",
                ViewFence {
                    owner_session: "observed-session".into(),
                    generation: 1,
                },
            )
            .unwrap();
        draft
            .workspace
            .receive_history(
                &ticket,
                History {
                    thread_id: "observed-thread".into(),
                    title: "Observed title".into(),
                    revision: 1,
                    event_sequence: 0,
                    messages: vec![],
                },
            )
            .unwrap();
        assert!(draft.workspace.has_history(0));
        let (rooms, active) = draft.export_local_rooms().unwrap();
        let mut restored = SharedComposer::default();
        restored.restore_local_rooms(&rooms, active).unwrap();
        assert_eq!(restored.text(), "尚未提交的中文");
        assert!(restored.workspace.timeline().is_none());
        assert_eq!(
            restored.request_send(restored.source()),
            ActionResult::SendUnavailable
        );
    }
}
