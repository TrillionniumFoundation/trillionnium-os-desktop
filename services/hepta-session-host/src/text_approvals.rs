//! UI projection of original pending callbacks, with no independent authority.
use super::*;
use codex_hepta_agentd::text_session::TextApprovalObservation;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TextChatApproval {
    pub id: String,
    pub title: String,
    pub details: String,
    pub can_accept: bool,
    pub can_decline: bool,
    pub busy: bool,
}

impl TextChatAdapter {
    pub fn pending_approval(
        &self,
        workspace: &ChatWorkspace,
        now_ms: u64,
    ) -> Option<TextChatApproval> {
        if self.unavailable
            || self.recovering
            || self
                .stream
                .as_ref()
                .is_none_or(|(room, _)| *room != workspace.active_id())
        {
            return None;
        }
        workspace
            .authenticated_chat_scope(ChatCapability::Subscribe, now_ms)
            .ok()?;
        let (_, (approval, busy)) = self.approvals.first_key_value()?;
        let authorized = workspace
            .authenticated_chat_scope(ChatCapability::ResolveApproval, now_ms)
            .is_ok();
        Some(TextChatApproval {
            id: approval.id.clone(),
            title: approval.title.clone(),
            details: if authorized {
                approval.details.clone()
            } else {
                format!(
                    "{}\nThis original human session does not permit approval decisions.",
                    approval.details
                )
            },
            can_accept: authorized && !*busy && approval.can_accept,
            can_decline: authorized && !*busy && approval.can_decline,
            busy: *busy,
        })
    }

    pub fn request_approval(
        &mut self,
        workspace: &mut ChatWorkspace,
        room: u64,
        id: &str,
        decision: TextApprovalDecision,
        now_ms: u64,
    ) -> Result<(), String> {
        let epoch = workspace.presentation_epoch();
        self.poll(workspace, now_ms);
        let view = self
            .pending_approval(workspace, now_ms)
            .ok_or("Original approval is unavailable")?;
        let permitted = match decision {
            TextApprovalDecision::AcceptOnce => view.can_accept,
            TextApprovalDecision::Decline => view.can_decline,
        };
        if !permitted
            || view.id != id
            || workspace.composing
            || workspace.active_id() != room
            || workspace.presentation_epoch() != epoch
        {
            return Err(
                "Approval action no longer belongs to this original request and room".into(),
            );
        }
        self.worker
            .try_send(TextCommand::ResolveApproval {
                connection_id: self.connection_id,
                id: id.into(),
                decision,
            })
            .map_err(error)?;
        self.approvals
            .get_mut(id)
            .ok_or("Original approval disappeared")?
            .1 = true;
        Ok(())
    }

    pub(super) fn observe_approval(
        &mut self,
        workspace: &mut ChatWorkspace,
        observation: TextApprovalObservation,
    ) -> Result<(), String> {
        match observation {
            TextApprovalObservation::Pending(approval) => {
                self.check_connection(approval.connection_id)?;
                if self
                    .owner
                    .as_ref()
                    .is_none_or(|owner| owner.scope.thread_id != approval.thread_id)
                {
                    return Err("Approval belongs to another original thread".into());
                }
                if self.approvals.len() >= 16 && !self.approvals.contains_key(&approval.id) {
                    return Err("Original approval presentation capacity reached".into());
                }
                self.approvals
                    .insert(approval.id.clone(), (approval, false));
            }
            TextApprovalObservation::Resolved { connection_id, id } => {
                self.check_connection(connection_id)?;
                self.approvals.remove(&id);
                workspace.presentation_note = Some("Original approval request resolved; tool completion remains independently observed".into());
            }
            TextApprovalObservation::Unavailable {
                connection_id,
                message,
                ..
            } => {
                self.check_connection(connection_id)?;
                workspace.presentation_note = Some(message);
            }
        }
        Ok(())
    }
}
