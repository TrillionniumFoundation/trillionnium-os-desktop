//! Native UI adapter over the original Root/Agentd text worker and ChatWorkspace.
//! Only transient request/ticket correlation lives here. Root owns signatures,
//! AuthBus owns admission, and the original App Server owns turns and history.
use codex_hepta_agentd::text_session::{
    AgentdTextWorker, TextCommand, TextOwnerReceipt, TextPrepared, TextSignerEndpoint,
    TextWorkerEvent,
};
use codex_hepta_agentd::{AuthBusTextState, AuthBusTextStatus};
use hepta_control_core::chat::{ChatWorkspace, StreamBinding};
use hepta_control_core::chat_owner::{
    ChatCapability, ChatOwnerError, DispatchTicket, OwnerDeliveryObservation, OwnerDeliveryState,
    OwnerScope, OwnerSession, SignedEnvelopeMetadata, SignedTextRef, SubmissionAdmission,
};
use std::collections::BTreeMap;
use std::sync::Arc;
#[path = "text_approvals.rs"]
mod approvals;
pub use approvals::TextChatApproval;
pub use codex_hepta_agentd::text_session::TextApprovalDecision;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct TextChatAvailability {
    pub can_submit: bool,
    pub can_interrupt: bool,
    pub can_load_earlier: bool,
    pub can_load_latest: bool,
}

struct Intent {
    room: u64,
    text: String,
    message_id: Option<String>,
    clear_draft: bool,
}

pub struct TextChatAdapter {
    worker: AgentdTextWorker,
    owner: Option<OwnerSession>,
    connection_id: u64,
    stream: Option<(u64, StreamBinding)>,
    intents: BTreeMap<String, Intent>,
    tickets: BTreeMap<String, DispatchTicket>,
    active: BTreeMap<u64, String>,
    signing: Option<String>,
    serial: u64,
    intent_namespace: String,
    releases: std::collections::BTreeSet<String>,
    unavailable: bool,
    recovering: bool,
    history_ready: bool,
    history_pending: bool,
    viewing_earlier: bool,
    can_load_earlier: bool,
    approvals: BTreeMap<String, (codex_hepta_agentd::text_session::TextApproval, bool)>,
}

impl TextChatAdapter {
    /// Root must already be running with its registered UI lane and pre-held UI
    /// pidfd. `root_pid` is a trusted launch input, never a chat message field.
    pub fn start(
        socket_path: std::path::PathBuf,
        root_pid: u32,
        waker: Arc<dyn Fn() + Send + Sync>,
    ) -> Result<Self, String> {
        let worker = AgentdTextWorker::start_authenticated(
            TextSignerEndpoint {
                socket_path,
                owner_uid: 0,
                owner_pid: root_pid,
            },
            waker,
        )
        .map_err(error)?;
        Ok(Self {
            worker,
            owner: None,
            connection_id: 0,
            stream: None,
            intents: BTreeMap::new(),
            tickets: BTreeMap::new(),
            active: BTreeMap::new(),
            signing: None,
            serial: 0,
            intent_namespace: String::new(),
            releases: Default::default(),
            unavailable: false,
            recovering: true,
            history_ready: false,
            history_pending: true,
            viewing_earlier: false,
            can_load_earlier: false,
            approvals: BTreeMap::new(),
        })
    }

    /// Consume a bounded batch outside Draw. Only an authenticated receipt can
    /// install the original owner; ordinary health/transport events cannot.
    pub fn poll(&mut self, workspace: &mut ChatWorkspace, now_ms: u64) -> TextChatAvailability {
        self.releases.retain(|message_id| {
            self.worker
                .try_send(TextCommand::Release {
                    message_id: message_id.clone(),
                })
                .is_err()
        });
        for _ in 0..32 {
            match self.worker.try_recv() {
                Ok(Some(event)) => {
                    if let Err(message) = self.observe(workspace, event, now_ms) {
                        workspace.presentation_note = Some(message);
                    }
                }
                Ok(None) => break,
                Err(issue) => {
                    self.disconnect(workspace, error(issue));
                    break;
                }
            }
        }
        if self
            .owner
            .as_ref()
            .is_some_and(|owner| now_ms >= owner.expires_at_ms)
        {
            self.disconnect(workspace, "Original Root chat session expired".into());
        }
        let room = workspace.active_id();
        let bound = self
            .stream
            .as_ref()
            .is_some_and(|(expected, _)| *expected == room);
        TextChatAvailability {
            can_submit: !self.unavailable
                && !self.recovering
                && self.history_ready
                && !self.viewing_earlier
                && !self.history_pending
                && bound
                && self.signing.is_none()
                && self.intents.len() < 32
                && workspace
                    .authenticated_chat_scope(ChatCapability::SubmitSignedText, now_ms)
                    .is_ok(),
            can_interrupt: !self.unavailable
                && !self.recovering
                && self.history_ready
                && !self.viewing_earlier
                && bound
                && self.active.contains_key(&room)
                && workspace
                    .authenticated_chat_scope(ChatCapability::InterruptTurn, now_ms)
                    .is_ok(),
            can_load_earlier: !self.unavailable
                && !self.recovering
                && !self.history_pending
                && bound
                && self.can_load_earlier
                && workspace
                    .authenticated_chat_scope(ChatCapability::ReadHistory, now_ms)
                    .is_ok(),
            can_load_latest: !self.unavailable
                && !self.history_pending
                && bound
                && (self.viewing_earlier || !self.history_ready)
                && workspace
                    .authenticated_chat_scope(ChatCapability::ReadHistory, now_ms)
                    .is_ok(),
        }
    }

    pub fn request_send(
        &mut self,
        workspace: &mut ChatWorkspace,
        room: u64,
        now_ms: u64,
    ) -> Result<(), String> {
        let epoch = workspace.presentation_epoch();
        if room != workspace.active_id()
            || workspace.composing
            || !self.poll(workspace, now_ms).can_submit
            || workspace.presentation_epoch() != epoch
            || workspace.active_id() != room
        {
            return Err("Original chat owner is not available for this room".into());
        }
        workspace
            .authenticated_chat_scope(ChatCapability::SubmitSignedText, now_ms)
            .map_err(error)?;
        let text = workspace.draft().text.clone();
        if text.trim().is_empty() || text.len() > 8192 {
            return Err("Text must contain 1–8192 UTF-8 bytes".into());
        }
        self.serial = self
            .serial
            .checked_add(1)
            .ok_or("Text intent identity exhausted")?;
        let request_id = format!("{}:{}", self.intent_namespace, self.serial);
        self.worker
            .try_send(TextCommand::Submit {
                request_id: request_id.clone(),
                text: text.clone(),
            })
            .map_err(error)?;
        self.intents.insert(
            request_id.clone(),
            Intent {
                room,
                text,
                message_id: None,
                clear_draft: true,
            },
        );
        self.signing = Some(request_id);
        Ok(())
    }

    pub fn request_interrupt(
        &mut self,
        workspace: &mut ChatWorkspace,
        room: u64,
        now_ms: u64,
    ) -> Result<(), String> {
        let epoch = workspace.presentation_epoch();
        if room != workspace.active_id()
            || !self.poll(workspace, now_ms).can_interrupt
            || workspace.presentation_epoch() != epoch
            || workspace.active_id() != room
        {
            return Err("Original owner has no interruptible turn in this room".into());
        }
        let message_id = self
            .active
            .get(&room)
            .ok_or("Original turn is unavailable")?
            .clone();
        self.worker
            .try_send(TextCommand::Interrupt { message_id })
            .map_err(error)?;
        workspace.presentation_note =
            Some("Cancellation requested; waiting for the original owner outcome".into());
        Ok(())
    }

    pub fn reconnect(&mut self) -> Result<(), String> {
        self.worker.try_send(TextCommand::Reconnect).map_err(error)
    }

    pub fn request_earlier_history(
        &mut self,
        workspace: &mut ChatWorkspace,
        room: u64,
        now_ms: u64,
    ) -> Result<(), String> {
        self.request_history(workspace, room, now_ms, TextCommand::EarlierHistory)
    }

    pub fn request_latest_history(
        &mut self,
        workspace: &mut ChatWorkspace,
        room: u64,
        now_ms: u64,
    ) -> Result<(), String> {
        self.request_history(workspace, room, now_ms, TextCommand::LatestHistory)
    }

    fn request_history(
        &mut self,
        workspace: &mut ChatWorkspace,
        room: u64,
        now_ms: u64,
        command: TextCommand,
    ) -> Result<(), String> {
        let epoch = workspace.presentation_epoch();
        let availability = self.poll(workspace, now_ms);
        let allowed = match &command {
            TextCommand::EarlierHistory => availability.can_load_earlier,
            TextCommand::LatestHistory => availability.can_load_latest,
            _ => false,
        };
        if !allowed
            || workspace.composing
            || workspace.active_id() != room
            || workspace.presentation_epoch() != epoch
        {
            return Err("Original history action no longer belongs to this room".into());
        }
        self.worker.try_send(command).map_err(error)?;
        self.history_pending = true;
        Ok(())
    }

    fn observe(
        &mut self,
        workspace: &mut ChatWorkspace,
        event: TextWorkerEvent,
        now_ms: u64,
    ) -> Result<(), String> {
        match event {
            TextWorkerEvent::Approval(observation) => {
                self.observe_approval(workspace, observation)?
            }
            TextWorkerEvent::ApprovalWritten { connection_id, id } => {
                self.check_connection(connection_id)?;
                if self.approvals.contains_key(&id) {
                    workspace.presentation_note =
                        Some("Decision sent; waiting for the original approval resolution".into());
                }
            }
            TextWorkerEvent::Connected { connection_id } => {
                self.connection_id = connection_id;
            }
            TextWorkerEvent::Authenticated {
                connection_id,
                owner,
            } => {
                if connection_id != self.connection_id {
                    return Err("Stale chat authentication receipt".into());
                }
                self.serial = self
                    .serial
                    .max(owner.next_intent_sequence.saturating_sub(1));
                self.intent_namespace = owner.intent_namespace.clone();
                let session = owner_session(owner, connection_id);
                workspace
                    .install_owner(session.clone(), now_ms)
                    .map_err(error)?;
                let room = workspace.active_id();
                self.stream = Some((
                    room,
                    workspace
                        .begin_stream(room, connection_id, now_ms)
                        .map_err(error)?,
                ));
                self.owner = Some(session);
                self.tickets.clear();
                self.unavailable = false;
                self.recovering = true;
                self.history_ready = false;
                self.history_pending = true;
                self.viewing_earlier = false;
                self.can_load_earlier = false;
                self.approvals.clear();
                self.signing = None;
                workspace.presentation_note = Some("Recovering original signed references".into());
            }
            TextWorkerEvent::Recovered {
                connection_id,
                reference,
            } => {
                self.check_connection(connection_id)?;
                if !reference.lookup_only {
                    return Err("Recovered input cannot authorize submission".into());
                }
                let room = self
                    .stream
                    .as_ref()
                    .ok_or("Original stream binding is unavailable")?
                    .0;
                let envelope = self.signed_reference(&reference)?;
                workspace
                    .restore_chat_delivery_reference(
                        room,
                        envelope,
                        digest(&reference.delivery_id)?,
                        now_ms,
                    )
                    .map_err(error)?;
                if let Some(old) = self.intents.get(&reference.host_reference)
                    && old.text != reference.text
                {
                    return Err("Original recovered text identity changed".into());
                }
                if self.signing.as_ref() == Some(&reference.host_reference) {
                    self.signing = None;
                }
                self.intents.insert(
                    reference.host_reference,
                    Intent {
                        room,
                        text: reference.text,
                        message_id: Some(reference.message_id),
                        clear_draft: false,
                    },
                );
            }
            TextWorkerEvent::RecoveryComplete { connection_id } => {
                self.check_connection(connection_id)?;
                self.recovering = false;
            }
            TextWorkerEvent::History {
                connection_id,
                page,
                viewing_earlier,
            } => {
                self.check_connection(connection_id)?;
                self.history_pending = false;
                let (_, stream) = self
                    .stream
                    .as_ref()
                    .ok_or("Original stream binding is unavailable")?;
                let turns = page
                    .turns
                    .into_iter()
                    .map(serde_json::to_value)
                    .collect::<Result<Vec<_>, _>>()
                    .map_err(error)?;
                workspace
                    .receive_app_server_history(stream, connection_id, &turns, now_ms)
                    .map_err(error)?;
                self.history_ready = true;
                self.viewing_earlier = viewing_earlier;
                self.can_load_earlier = page.earlier_cursor.is_some();
                workspace.presentation_note = page.notice.or_else(|| {
                    viewing_earlier
                        .then(|| "Viewing earlier messages; return to latest to continue".into())
                });
            }
            TextWorkerEvent::HistoryActivity {
                connection_id,
                page,
            } => {
                self.check_connection(connection_id)?;
                if !self.viewing_earlier {
                    let (_, stream) = self
                        .stream
                        .as_ref()
                        .ok_or("Original stream binding is unavailable")?;
                    for turn in page.turns {
                        workspace
                            .receive_app_server_turn(
                                stream,
                                connection_id,
                                &serde_json::to_value(turn).map_err(error)?,
                                now_ms,
                            )
                            .map_err(error)?;
                    }
                    if page.notice.is_some() {
                        workspace.presentation_note = page.notice;
                    }
                } else {
                    workspace.presentation_note = Some(
                        "New activity in the original thread; select Latest messages to view it"
                            .into(),
                    );
                }
            }
            TextWorkerEvent::Prepared {
                connection_id,
                reference,
            } => {
                self.check_connection(connection_id)?;
                let request_id = reference.host_reference.clone();
                if let Err(issue) = self.prepared(workspace, reference, now_ms) {
                    if self.signing.as_ref() == Some(&request_id) {
                        self.signing = None;
                    }
                    return Err(issue);
                }
            }
            TextWorkerEvent::PreparationClosed {
                connection_id,
                request_id,
                text_sha256,
                original_watermark,
                message,
            } => {
                // A non-transmission/Root closure proof may arrive after a
                // disconnect. It can only release this exact unsigned local
                // correlation, and never changes owner state or local text.
                if connection_id != self.connection_id {
                    return Err("Stale original preparation closure".into());
                }
                if let Some(intent) = self.intents.get(&request_id) {
                    if intent.message_id.is_some()
                        || text_sha256
                            != *codex_hepta_types::Digest32::of_bytes(intent.text.as_bytes())
                                .as_array()
                    {
                        return Err(
                            "Preparation closure does not match an unsigned original intent".into(),
                        );
                    }
                    self.intents.remove(&request_id);
                    if let Some(watermark) = original_watermark {
                        self.serial = self.serial.max(watermark);
                    }
                    if self.signing.as_ref() == Some(&request_id) {
                        self.signing = None;
                    }
                    workspace.presentation_note = Some(message);
                }
            }
            TextWorkerEvent::Admission {
                connection_id,
                request_id,
                message_id,
                status,
            } => {
                self.check_connection(connection_id)?;
                let admitted = matches!(
                    status.state,
                    AuthBusTextState::Queued
                        | AuthBusTextState::Leased
                        | AuthBusTextState::QueueAccepted
                );
                self.delivery(workspace, &message_id, status, now_ms)?;
                self.admitted_draft(workspace, &message_id, admitted);
                if self.signing.as_ref() == Some(&request_id) {
                    self.signing = None;
                }
            }
            TextWorkerEvent::Notification(event) => {
                self.check_connection(event.connection_id)?;
                let (_, stream) = self
                    .stream
                    .as_ref()
                    .ok_or("Original stream binding is unavailable")?;
                let value = serde_json::to_value(event.notification).map_err(error)?;
                if !self.viewing_earlier {
                    workspace
                        .receive_app_server_notification(
                            stream,
                            event.connection_id,
                            &value,
                            now_ms,
                        )
                        .map_err(error)?;
                } else {
                    workspace.presentation_note = Some(
                        "New activity in the original thread; select Latest messages to view it"
                            .into(),
                    );
                }
                if !event.message_id.is_empty()
                    && value.get("method").and_then(serde_json::Value::as_str)
                        == Some("turn/completed")
                {
                    self.active
                        .retain(|_, message| message != &event.message_id);
                    // Original Core completion is not an AuthBus queue receipt.
                    self.worker
                        .try_send(TextCommand::Reconcile {
                            message_id: event.message_id,
                        })
                        .map_err(error)?;
                }
            }
            TextWorkerEvent::Reconciled {
                connection_id,
                view,
            } => {
                self.check_connection(connection_id)?;
                if let Some(status) = view.delivery {
                    let admitted = matches!(
                        status.state,
                        AuthBusTextState::Queued
                            | AuthBusTextState::Leased
                            | AuthBusTextState::QueueAccepted
                    );
                    self.delivery(workspace, &view.message_id, status, now_ms)?;
                    self.admitted_draft(workspace, &view.message_id, admitted);
                    if admitted
                        && let Some(intent) = self
                            .intents
                            .values()
                            .find(|intent| intent.message_id.as_ref() == Some(&view.message_id))
                    {
                        self.active.insert(intent.room, view.message_id.clone());
                    }
                } else if let Some(ticket) = self.tickets.remove(&view.message_id) {
                    workspace.delivery_unknown(&ticket).map_err(error)?;
                }
                if let Some(turn) = view.turn {
                    let (_, stream) = self
                        .stream
                        .as_ref()
                        .ok_or("Original stream binding is unavailable")?;
                    let value = serde_json::to_value(turn).map_err(error)?;
                    if !self.viewing_earlier {
                        workspace
                            .receive_app_server_turn(stream, connection_id, &value, now_ms)
                            .map_err(error)?;
                    }
                    if value.get("status").and_then(serde_json::Value::as_str) != Some("inProgress")
                    {
                        self.active.retain(|_, message| message != &view.message_id);
                        self.worker
                            .try_send(TextCommand::Retire {
                                message_id: view.message_id.clone(),
                            })
                            .map_err(error)?;
                    }
                } else if serde_json::to_value(&view.queue)
                    .map_err(error)?
                    .get("type")
                    .and_then(serde_json::Value::as_str)
                    == Some("cancelled")
                {
                    self.active.retain(|_, message| message != &view.message_id);
                    self.worker
                        .try_send(TextCommand::Retire {
                            message_id: view.message_id.clone(),
                        })
                        .map_err(error)?;
                }
            }
            TextWorkerEvent::Retired {
                connection_id,
                request_id,
                message_id,
            } => {
                self.check_connection(connection_id)?;
                if let Some(ticket) = self.tickets.remove(&message_id) {
                    workspace.delivery_unknown(&ticket).map_err(error)?;
                }
                if self.intents.contains_key(&request_id) {
                    match workspace.retire_chat_reference_from_owner(&message_id, now_ms) {
                        Ok(_) | Err(ChatOwnerError::UnknownDelivery) => {}
                        Err(issue) => return Err(error(issue)),
                    }
                }
                self.intents.remove(&request_id);
                self.tickets.remove(&message_id);
                self.active.retain(|_, message| message != &message_id);
                if self.signing.as_ref() == Some(&request_id) {
                    self.signing = None;
                }
                self.releases.insert(message_id);
            }
            TextWorkerEvent::Unavailable {
                request_id,
                message,
            } => {
                if let Some(request_id) = request_id {
                    if request_id == "history" {
                        self.history_pending = false;
                    }
                    let message_id = self
                        .intents
                        .get(&request_id)
                        .and_then(|intent| intent.message_id.as_ref())
                        .unwrap_or(&request_id);
                    if let Some(ticket) = self.tickets.remove(message_id) {
                        let _ = workspace.delivery_unknown(&ticket);
                    }
                    // Preserve the exact intent on uncertainty. A caller retries
                    // it by lookup/reconnect, never by replacing its identity.
                    workspace.presentation_note = Some(message);
                } else {
                    self.disconnect(workspace, message);
                }
            }
        }
        Ok(())
    }

    fn prepared(
        &mut self,
        workspace: &mut ChatWorkspace,
        reference: TextPrepared,
        now_ms: u64,
    ) -> Result<(), String> {
        let envelope = self.signed_reference(&reference)?;
        let intent = self
            .intents
            .get_mut(&reference.host_reference)
            .ok_or("Original text intent is not retained")?;
        intent.message_id = Some(reference.message_id.clone());
        let admission = if reference.lookup_only {
            workspace
                .begin_chat_delivery_status(&reference.message_id, now_ms)
                .map_err(error)?
        } else {
            workspace
                .stage_authorized_text(intent.room, envelope)
                .map_err(error)?;
            workspace
                .begin_authorized_submit(intent.room, now_ms)
                .map_err(error)?
        };
        if let SubmissionAdmission::Dispatch(ticket) = admission {
            workspace
                .retain_chat_delivery_identity(&ticket, digest(&reference.delivery_id)?, now_ms)
                .map_err(error)?;
            self.tickets.insert(reference.message_id.clone(), *ticket);
            self.worker
                .try_send(TextCommand::Dispatch {
                    request_id: reference.host_reference.clone(),
                })
                .map_err(error)?;
        }
        self.active.insert(intent.room, reference.message_id);
        Ok(())
    }

    fn signed_reference(&self, reference: &TextPrepared) -> Result<SignedTextRef, String> {
        let mut scope = self
            .owner
            .as_ref()
            .ok_or("Original owner is unavailable")?
            .scope
            .clone();
        scope.agent_generation = reference.spawn_generation;
        SignedTextRef::new(
            scope,
            SignedEnvelopeMetadata {
                host_reference: reference.host_reference.clone(),
                issuer_id: reference.issuer_id.clone(),
                key_epoch: reference.key_epoch,
                message_id: reference.message_id.clone(),
                sequence: reference.sequence,
                expires_at_ms: reference.expires_at_ms,
                payload_sha256: reference.payload_sha256,
                envelope_sha256: reference.envelope_sha256,
            },
            reference.text.clone(),
        )
        .map_err(error)
    }

    fn delivery(
        &mut self,
        workspace: &mut ChatWorkspace,
        message_id: &str,
        status: AuthBusTextStatus,
        now_ms: u64,
    ) -> Result<(), String> {
        let ticket = match self.tickets.remove(message_id) {
            Some(ticket) => ticket,
            None => match workspace
                .begin_chat_delivery_status(message_id, now_ms)
                .map_err(error)?
            {
                SubmissionAdmission::Dispatch(ticket) => *ticket,
                SubmissionAdmission::Existing(_) => return Ok(()),
            },
        };
        let metadata = ticket.envelope().metadata();
        let observation = OwnerDeliveryObservation {
            observer: ticket.observer().clone(),
            message_id: message_id.into(),
            payload_sha256: metadata.payload_sha256,
            envelope_sha256: metadata.envelope_sha256,
            delivery_id: digest(&status.delivery_id)?,
            state: match status.state {
                AuthBusTextState::Queued => OwnerDeliveryState::Queued,
                AuthBusTextState::Leased => OwnerDeliveryState::Leased,
                AuthBusTextState::QueueAccepted => OwnerDeliveryState::QueueAccepted,
                AuthBusTextState::Expired => OwnerDeliveryState::Expired,
                AuthBusTextState::Quarantined => OwnerDeliveryState::Quarantined,
            },
            delivery_attempts: status.delivery_attempts,
            queue_receipt_digest: status
                .queue_receipt_digest
                .as_deref()
                .map(digest)
                .transpose()?,
        };
        workspace
            .observe_delivery(&ticket, observation, now_ms)
            .map_err(error)?;
        Ok(())
    }

    fn check_connection(&self, connection_id: u64) -> Result<(), String> {
        if self.unavailable || self.owner.is_none() || connection_id != self.connection_id {
            Err("Stale original chat connection".into())
        } else {
            Ok(())
        }
    }

    fn admitted_draft(&mut self, workspace: &mut ChatWorkspace, message_id: &str, admitted: bool) {
        if let Some((request_id, intent)) = self
            .intents
            .iter()
            .find(|(_, intent)| intent.message_id.as_deref() == Some(message_id))
        {
            if admitted
                && intent.clear_draft
                && intent.room == workspace.active_id()
                && workspace.draft().text == intent.text
                && !workspace.composing
            {
                workspace.edit(String::new());
            }
            if self.signing.as_ref() == Some(request_id) {
                self.signing = None;
            }
        }
    }

    fn disconnect(&mut self, workspace: &mut ChatWorkspace, message: String) {
        if !self.unavailable {
            workspace.disconnect_owner();
        }
        self.unavailable = true;
        self.recovering = true;
        self.history_ready = false;
        self.history_pending = false;
        self.owner = None;
        self.stream = None;
        self.approvals.clear();
        workspace.presentation_note = Some(message);
    }
}

fn owner_session(owner: TextOwnerReceipt, connection_id: u64) -> OwnerSession {
    let mut capabilities = vec![
        ChatCapability::SubmitSignedText,
        ChatCapability::ReadDeliveryStatus,
        ChatCapability::ReadHistory,
        ChatCapability::Subscribe,
    ];
    if owner.can_interrupt {
        capabilities.push(ChatCapability::InterruptTurn);
    }
    if owner.can_resolve_approvals {
        capabilities.push(ChatCapability::ResolveApproval);
    }
    OwnerSession {
        protocol: owner.protocol,
        scope: OwnerScope {
            principal_id: owner.principal_id,
            session_id: owner.session_id,
            connection_generation: connection_id,
            permission_revision: owner.permission_revision,
            agent_id: owner.route.agent_id.to_string(),
            agent_generation: owner.route.spawn_generation,
            thread_id: owner.route.thread_id,
        },
        expires_at_ms: owner.expires_at_ms,
        capabilities,
    }
}

fn digest(value: &str) -> Result<[u8; 32], String> {
    value
        .parse::<codex_hepta_types::Digest32>()
        .map(|value| *value.as_array())
        .map_err(error)
}

fn error(value: impl std::fmt::Debug) -> String {
    format!("{value:?}")
}

#[cfg(test)]
#[path = "text_tests.rs"]
mod tests;
