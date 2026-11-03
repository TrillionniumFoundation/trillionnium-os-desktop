//! Disposable Objective UI observations. The host owns identity, admission,
//! publication and run state; this module retains no authority or recovery log.
use super::{Desktop, Workspace};
use eframe::egui;
use std::fmt::Write as _;
use std::io::Read;
use std::time::{Duration, Instant};
use trill_ui_core::notes::MAX_NOTES_TEXT_BYTES;
use trill_ui_core::objective::{ObjectiveObservation, ObjectiveStage, MAX_OBJECTIVE_VIEWS};
use trill_ui_core::{unix_ms, Request};

const READY_MAX_AGE: Duration = Duration::from_secs(2);

struct Receipt {
    session: String,
    observation: ObjectiveObservation,
    received_at: Instant,
}

struct IntentView {
    workspace: Option<Workspace>,
    session: String,
    id: String,
    observation: ObjectiveObservation,
    received_at: Instant,
    cancel_queued: bool,
}

#[derive(Default)]
pub(super) struct ObjectivePanel {
    availability: Option<Receipt>,
    intents: Vec<IntentView>,
    last_query: Option<Instant>,
    query_status: bool,
    selected: Option<String>,
    status_cursor: usize,
    rotating_status_next: bool,
}

fn fresh(
    observation: &ObjectiveObservation,
    received_at: Instant,
    now: Instant,
    wall_ms: u64,
) -> bool {
    now.checked_duration_since(received_at)
        .is_some_and(|age| age <= READY_MAX_AGE)
        && wall_ms
            .checked_sub(observation.observed_unix_ms)
            .is_some_and(|age| age <= READY_MAX_AGE.as_millis() as u64)
}

fn finished(observation: &ObjectiveObservation) -> bool {
    matches!(
        observation.stage,
        ObjectiveStage::NotSent
            | ObjectiveStage::Refused
            | ObjectiveStage::Abstained
            | ObjectiveStage::Conflict
    ) || observation
        .run
        .as_ref()
        .is_some_and(|run| run.terminal_observed)
}

impl ObjectivePanel {
    pub(super) fn invalidate(&mut self) {
        self.availability = None;
    }

    /// Session is a display transport, not the Objective owner. Keep the
    /// caller's original IDs after its restart and query them through the new
    /// trusted host. This never recreates a Submit or a sender permission.
    pub(super) fn follow_session(&mut self, session: &str) {
        self.invalidate();
        self.last_query = None;
        self.query_status = false;
        self.status_cursor = 0;
        self.rotating_status_next = false;
        for intent in &mut self.intents {
            if intent.session != session {
                intent.session = session.into();
                intent.observation.observed_unix_ms = 0;
                // The operation ID survives; a live document snapshot does not
                // gain the new Session's provenance from its recent timestamp.
                intent.observation.notes_document = None;
                intent.observation.issue =
                    Some(trill_ui_core::objective::ObjectiveHostIssue::Unavailable);
                intent.cancel_queued = false;
            }
        }
    }

    fn ready(&self, session: &str, now: Instant, wall_ms: u64) -> bool {
        self.availability.as_ref().is_some_and(|receipt| {
            receipt.session == session
                && receipt.observation.stage == ObjectiveStage::Ready
                && receipt.observation.issue.is_none()
                && receipt
                    .observation
                    .retained_intents
                    .as_ref()
                    .is_some_and(|retained| retained.complete && retained.validate().is_ok())
                && fresh(&receipt.observation, receipt.received_at, now, wall_ms)
        })
    }

    pub(super) fn observe(
        &mut self,
        session: &str,
        observation: ObjectiveObservation,
        received_at: Instant,
    ) {
        if let Some(id) = &observation.client_intent_id {
            let Some(intent) = self
                .intents
                .iter_mut()
                .find(|intent| intent.session == session && &intent.id == id)
            else {
                return;
            };
            if let Some(old) = &intent.observation.run {
                let Some(new) = &observation.run else {
                    return;
                };
                if new.revision < old.revision
                    || (new.revision == old.revision && new != old)
                    || (old.terminal_observed && new != old)
                {
                    return;
                }
            }
            if observation.observed_unix_ms < intent.observation.observed_unix_ms {
                return;
            }
            if observation.cancellation
                != trill_ui_core::objective::ObjectiveCancellation::NotRequested
            {
                intent.cancel_queued = false;
            }
            intent.observation = observation;
            intent.received_at = received_at;
        } else {
            if let Some(retained) = &observation.retained_intents {
                if retained.validate().is_err() {
                    self.invalidate();
                    return;
                }
                for id in &retained.client_intent_ids {
                    if self.intents.iter().any(|intent| &intent.id == id) {
                        continue;
                    }
                    if self.intents.len() == MAX_OBJECTIVE_VIEWS {
                        break;
                    }
                    let mut recovered =
                        ObjectiveObservation::new(Some(id.clone()), ObjectiveStage::SubmitUnknown);
                    recovered.request_retained = true;
                    self.intents.push(IntentView {
                        workspace: recovered_workspace(id),
                        session: session.into(),
                        id: id.clone(),
                        observation: recovered,
                        received_at,
                        cancel_queued: false,
                    });
                }
            }
            self.availability = Some(Receipt {
                session: session.into(),
                observation,
                received_at,
            });
        }
    }

    fn current(&self, workspace: Workspace, session: &str) -> Option<&IntentView> {
        let matches = |intent: &&IntentView| {
            intent.session == session
                && intent
                    .workspace
                    .is_none_or(|previous| previous == workspace)
        };
        if let Some(selected) = &self.selected {
            if let Some(intent) = self
                .intents
                .iter()
                .filter(matches)
                .find(|intent| &intent.id == selected)
            {
                return Some(intent);
            }
        }
        self.intents.iter().rev().find(matches)
    }

    fn document_readback(
        &self,
        workspace: Workspace,
        session: &str,
    ) -> Option<(&trill_ui_core::objective::NotesDocumentObservation, Instant)> {
        self.current(workspace, session)
            .and_then(|intent| {
                intent
                    .observation
                    .notes_document
                    .as_ref()
                    .map(|document| (document, intent.received_at))
            })
            .into_iter()
            .chain(
                self.availability
                    .as_ref()
                    .filter(|receipt| receipt.session == session)
                    .and_then(|receipt| {
                        receipt
                            .observation
                            .notes_document
                            .as_ref()
                            .map(|document| (document, receipt.received_at))
                    }),
            )
            .max_by_key(|(document, _)| document.observed_unix_ms)
    }

    fn poll(&mut self, workspace: Workspace, session: &str, now: Instant) -> Option<Request> {
        if self
            .last_query
            .is_some_and(|last| now.duration_since(last) < Duration::from_millis(700))
        {
            return None;
        }
        self.last_query = Some(now);
        self.query_status = !self.query_status;
        if self.query_status {
            let current = self
                .current(workspace, session)
                .map(|intent| (intent.id.clone(), finished(&intent.observation)));
            // Current request stays responsive while every original unresolved
            // ID gets a turn, including recovered requests from another local
            // workspace. The bounded vector never removes or renumbers IDs.
            if !self.rotating_status_next {
                if let Some((id, false)) = &current {
                    self.rotating_status_next = true;
                    return Some(Request::ObjectiveStatus {
                        client_intent_id: id.clone(),
                        expected_instance: session.into(),
                    });
                }
            }
            self.rotating_status_next = false;
            for offset in 0..self.intents.len() {
                let index = (self.status_cursor + offset) % self.intents.len();
                let intent = &self.intents[index];
                if intent.session == session && !finished(&intent.observation) {
                    self.status_cursor = (index + 1) % self.intents.len();
                    return Some(Request::ObjectiveStatus {
                        client_intent_id: intent.id.clone(),
                        expected_instance: session.into(),
                    });
                }
            }
            if let Some((id, _)) = current {
                return Some(Request::ObjectiveStatus {
                    client_intent_id: id,
                    expected_instance: session.into(),
                });
            }
        }
        Some(Request::ObjectiveAvailability {
            expected_instance: session.into(),
        })
    }
}

fn recovered_workspace(id: &str) -> Option<Workspace> {
    Workspace::ALL.into_iter().find(|workspace| {
        id.strip_prefix(&format!("desktop-{}-", workspace.code()))
            .is_some_and(|nonce| nonce.len() == 32 && nonce.bytes().all(|c| c.is_ascii_hexdigit()))
    })
}

fn intent_id(workspace: Workspace) -> std::io::Result<String> {
    let mut nonce = [0u8; 16];
    std::fs::File::open("/dev/urandom")?.read_exact(&mut nonce)?;
    Ok(format!(
        "desktop-{}-{}",
        workspace.code(),
        nonce
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>()
    ))
}

fn readback_fresh(
    document: &trill_ui_core::objective::NotesDocumentObservation,
    received_at: Instant,
    now: Instant,
    wall_ms: u64,
) -> bool {
    now.checked_duration_since(received_at)
        .is_some_and(|age| age <= READY_MAX_AGE)
        && wall_ms
            .checked_sub(document.observed_unix_ms)
            .is_some_and(|age| age <= READY_MAX_AGE.as_millis() as u64)
}

/// Shared projection for both Rust renderers. This carries observations and
/// button availability, never an admission, grant or operation receipt.
pub(super) struct NotesControlsView {
    pub status: String,
    pub can_write: bool,
    pub can_refresh: bool,
    pub can_cancel: bool,
}

impl Desktop {
    pub(super) fn poll_notes_controls(&mut self) {
        if let Some(session) = self.session_instance.as_deref().filter(|_| self.connected) {
            let cursor = (
                self.objectives.query_status,
                self.objectives.status_cursor,
                self.objectives.rotating_status_next,
            );
            if let Some(request) = self
                .objectives
                .poll(self.workspace, session, Instant::now())
            {
                if !self.bridge.poll_objective(request) {
                    // Keep the selected read on a full/disconnected queue. The
                    // 700 ms throttle remains; no effect request is retried.
                    (
                        self.objectives.query_status,
                        self.objectives.status_cursor,
                        self.objectives.rotating_status_next,
                    ) = cursor;
                }
            }
        }
    }

    pub(super) fn notes_controls_view(&self) -> NotesControlsView {
        let now = Instant::now();
        let wall_ms = unix_ms();
        let session = self.session_instance.as_deref().filter(|_| self.connected);
        let composer = self.drafts.composer(self.workspace);
        let ready = session.is_some_and(|session| self.objectives.ready(session, now, wall_ms));
        let document =
            session.and_then(|session| self.objectives.document_readback(self.workspace, session));
        let receipt_pending = document.is_some_and(|(document, received_at)| {
            document.receipt_pending && readback_fresh(document, received_at, now, wall_ms)
        });
        let may_start = self
            .objectives
            .intents
            .iter()
            .all(|intent| finished(&intent.observation));
        let can_write = ready
            && !receipt_pending
            && may_start
            && composer.contexts.is_empty()
            && !composer.text().trim().is_empty()
            && composer.text().len() <= MAX_NOTES_TEXT_BYTES
            && composer.can_save_local().is_ok()
            && !self.activation.composing()
            && self.objectives.intents.len() < MAX_OBJECTIVE_VIEWS;
        let current = session.and_then(|session| self.objectives.current(self.workspace, session));
        let can_cancel = current.is_some_and(|intent| {
            !intent.cancel_queued
                && intent.observation.cancellation
                    == trill_ui_core::objective::ObjectiveCancellation::NotRequested
                && !finished(&intent.observation)
                && fresh(&intent.observation, intent.received_at, now, wall_ms)
        });
        let availability_issue = self
            .objectives
            .availability
            .as_ref()
            .filter(|receipt| Some(receipt.session.as_str()) == session)
            .and_then(|receipt| receipt.observation.issue);
        let mut status = if session.is_none() {
            "Waiting for the current host session. Sending is unavailable.".to_owned()
        } else if availability_issue.is_some() {
            "Hepta 暂时无法核对笔记状态，请刷新后重试。".to_owned()
        } else if !ready {
            "Checking Hepta availability; writing requires a fresh host observation.".to_owned()
        } else if receipt_pending {
            "上一笔笔记写入仍待核对，请先恢复原请求再写入新内容。".to_owned()
        } else if !may_start {
            "A previous request is unresolved. Refresh its original status before writing again."
                .to_owned()
        } else if !composer.contexts.is_empty() {
            "Notes accepts text only. Remove quoted references before writing; the draft and references are preserved.".to_owned()
        } else if composer.text().len() > MAX_NOTES_TEXT_BYTES {
            "Notes content exceeds 4096 UTF-8 bytes. Shorten it before writing; the draft is preserved.".to_owned()
        } else if composer.can_save_local().is_err() || self.activation.composing() {
            "Finish the current editor transaction before writing Notes.".to_owned()
        } else if self.objectives.intents.len() >= MAX_OBJECTIVE_VIEWS {
            "The request history limit has been reached. Existing status remains available."
                .to_owned()
        } else {
            "Hepta is available to write the draft into the configured Notes document.".to_owned()
        };
        if let Some(intent) = current {
            let observation = &intent.observation;
            let observed = fresh(observation, intent.received_at, now, wall_ms);
            let _ = write!(
                status,
                "\nRequest {} · admission: {:?}{}",
                intent.id,
                observation.stage,
                if observed {
                    ""
                } else {
                    " (last observed; refresh pending)"
                }
            );
            let _ = write!(
                status,
                "\nRequest retained: {} · publication retained: {}",
                observation.request_retained, observation.publication_retained
            );
            if let Some(run) = &observation.run {
                let _ = write!(
                    status,
                    "\nRun: {:?} · revision {} · terminal observed: {}",
                    run.phase, run.revision, run.terminal_observed
                );
            } else {
                status.push_str("\nRun state has not been observed.");
            }
            let _ = write!(status, "\nCancellation: {:?}", observation.cancellation);
            if intent.cancel_queued {
                status.push_str(" (request queued; outcome unconfirmed)");
            }
            if let Some(issue) = observation.issue {
                let _ = write!(status, "\nHost observation: {issue:?}");
            }
            if intent.workspace.is_none() {
                status.push_str("\nRecovered request: status is queried without sending it again.");
            }
        }
        if let Some((document, received_at)) = document {
            let observed = readback_fresh(document, received_at, now, wall_ms);
            let digest: String = document.text_sha256.chars().take(12).collect();
            let _ = write!(status, "\nNotes readback{}: {} · document revision {} · text digest {} · receipt pending: {}",
                if observed { "" } else { " (last observed; refresh pending)" }, document.target.destination_id(),
                document.revision, digest, document.receipt_pending);
        } else {
            status.push_str("\nNotes readback unavailable.");
        }
        status.push_str("\nRun status and the current document snapshot are separate from an exact operation receipt. Your draft is retained.");
        NotesControlsView {
            status,
            can_write,
            can_refresh: session.is_some(),
            can_cancel,
        }
    }

    pub(super) fn write_note_from_draft(&mut self) -> Result<(), String> {
        if !self.notes_controls_view().can_write {
            return Err("Notes writing is unavailable for the current draft or host observation; draft retained".into());
        }
        let session = self
            .session_instance
            .clone()
            .ok_or("No current host session")?;
        let text = self.drafts.composer(self.workspace).text().to_owned();
        let id = intent_id(self.workspace)
            .map_err(|error| format!("Cannot create an intent ID; nothing queued: {error}"))?;
        if !self.submit(Request::ObjectiveSubmit {
            client_intent_id: id.clone(),
            text,
            expected_instance: session.clone(),
        }) {
            return Err("Notes request was not queued; draft retained".into());
        }
        self.objectives.intents.push(IntentView {
            workspace: Some(self.workspace),
            session,
            id: id.clone(),
            observation: ObjectiveObservation::new(Some(id.clone()), ObjectiveStage::Queued),
            received_at: Instant::now(),
            cancel_queued: false,
        });
        self.objectives.selected = Some(id);
        self.notice("Objective queued for the host. Admission and execution are not yet confirmed; your draft remains available.");
        Ok(())
    }

    pub(super) fn refresh_notes_controls(&mut self) -> Result<(), String> {
        let session = self
            .session_instance
            .as_deref()
            .filter(|_| self.connected)
            .ok_or("No current host session")?;
        let request = self
            .objectives
            .current(self.workspace, session)
            .map_or_else(
                || Request::ObjectiveAvailability {
                    expected_instance: session.into(),
                },
                |intent| Request::ObjectiveStatus {
                    client_intent_id: intent.id.clone(),
                    expected_instance: session.into(),
                },
            );
        self.objectives.last_query = None;
        if self.bridge.poll_objective(request) {
            Ok(())
        } else {
            Err("A Notes observation is already pending or the connection is unavailable; refresh was not queued".into())
        }
    }

    pub(super) fn cancel_note_request(&mut self) -> Result<(), String> {
        if !self.notes_controls_view().can_cancel {
            return Err(
                "No fresh cancellable Notes request is available; refresh the original status"
                    .into(),
            );
        }
        let session = self
            .session_instance
            .clone()
            .ok_or("No current host session")?;
        let id = self
            .objectives
            .current(self.workspace, &session)
            .ok_or("No retained Notes request")?
            .id
            .clone();
        if !self.submit(Request::ObjectiveCancel {
            client_intent_id: id.clone(),
            expected_instance: session,
        }) {
            return Err("Cancellation was not queued; its outcome remains unknown".into());
        }
        if let Some(intent) = self
            .objectives
            .intents
            .iter_mut()
            .find(|intent| intent.id == id)
        {
            intent.cancel_queued = true;
        }
        Ok(())
    }

    pub(super) fn objective_controls(&mut self, ui: &mut egui::Ui) {
        ui.separator();
        ui.strong("Hepta Notes / 笔记");
        self.poll_notes_controls();
        let session = self.session_instance.as_deref().filter(|_| self.connected);
        let previous: Vec<_> = self
            .objectives
            .intents
            .iter()
            .filter(|intent| {
                Some(intent.session.as_str()) == session
                    && intent
                        .workspace
                        .is_none_or(|workspace| workspace == self.workspace)
            })
            .map(|intent| intent.id.clone())
            .collect();
        // Preserve a stable parent scope before the history appears.
        ui.scope(|ui| {
            if !previous.is_empty() {
                ui.collapsing("Previous Hepta requests / 之前的请求", |ui| {
                    egui::ScrollArea::vertical()
                        .max_height(120.0)
                        .show(ui, |ui| {
                            for id in previous {
                                if self.activation.activated(&ui.selectable_label(
                                    self.objectives.selected.as_ref() == Some(&id),
                                    &id,
                                )) {
                                    self.objectives.selected = Some(id);
                                    self.objectives.last_query = None;
                                    self.objectives.query_status = false;
                                    self.objectives.rotating_status_next = false;
                                }
                            }
                        });
                });
            }
        });
        let view = self.notes_controls_view();
        ui.label(view.status);
        ui.small("Notes 窗口显示本机保存状态，并可打开已经保存的笔记。此操作会保留当前对话草稿。");
        if self.activation.activated(&ui.add_enabled(
            view.can_write,
            egui::Button::new("Write note via Hepta / 通过 Hepta 写入笔记"),
        )) {
            if let Err(error) = self.write_note_from_draft() {
                self.notice(error);
            }
        }
        let view = self.notes_controls_view();
        let id = self.objectives.selected.clone();
        ui.push_id(("objective-actions", id), |ui| {
            ui.horizontal(|ui| {
                if self.activation.activated(&ui.add_enabled(
                    view.can_refresh,
                    egui::Button::new("Refresh objective status"),
                )) {
                    if let Err(error) = self.refresh_notes_controls() {
                        self.notice(error);
                    }
                }
                if self.activation.activated(
                    &ui.add_enabled(view.can_cancel, egui::Button::new("Request cancellation")),
                ) {
                    if let Err(error) = self.cancel_note_request() {
                        self.notice(error);
                    }
                }
            })
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use trill_ui_core::objective::{ObjectiveRunObservation, ObjectiveRunPhase};

    fn ready_observation() -> ObjectiveObservation {
        let mut view = ObjectiveObservation::new(None, ObjectiveStage::Ready);
        view.retained_intents = Some(trill_ui_core::objective::ObjectiveRetainedIntents {
            client_intent_ids: Vec::new(),
            complete: true,
        });
        view
    }

    #[test]
    fn semantic_submit_preserves_draft_and_reuses_one_intent_for_cancellation() {
        let (mut desktop, _) = super::super::observation_freshness_tests::queued_desktop();
        let (actions, requests) = std::sync::mpsc::sync_channel(8);
        desktop.bridge.actions = actions;
        desktop.connected = true;
        desktop.session_instance = Some("current-session".into());
        desktop
            .drafts
            .composer_mut(Workspace::Personal)
            .edit("保留原始笔记".into());
        desktop
            .objectives
            .observe("current-session", ready_observation(), Instant::now());
        let ctx = egui::Context::default();
        ctx.enable_accesskit();
        let frame = |desktop: &mut Desktop, events| {
            ctx.run(
                egui::RawInput {
                    focused: true,
                    screen_rect: Some(egui::Rect::from_min_size(
                        egui::Pos2::ZERO,
                        egui::vec2(900.0, 900.0),
                    )),
                    events,
                    ..Default::default()
                },
                |ctx| {
                    desktop.activation.begin_frame(ctx);
                    egui::CentralPanel::default().show(ctx, |ui| desktop.objective_controls(ui));
                },
            )
        };
        let output = frame(&mut desktop, vec![]);
        let target = output
            .platform_output
            .accesskit_update
            .unwrap()
            .nodes
            .into_iter()
            .find(|(_, node)| node.label() == Some("Write note via Hepta / 通过 Hepta 写入笔记"))
            .unwrap()
            .0;
        let click = |target| {
            egui::Event::AccessKitActionRequest(egui::accesskit::ActionRequest {
                action: egui::accesskit::Action::Click,
                target,
                data: None,
            })
        };
        let oversize = "界".repeat(MAX_NOTES_TEXT_BYTES / 3 + 1);
        desktop
            .drafts
            .composer_mut(Workspace::Personal)
            .edit(oversize.clone());
        frame(&mut desktop, vec![click(target)]);
        assert!(
            requests.try_recv().is_err(),
            "oversized Notes content cannot submit via accessibility"
        );
        assert_eq!(
            desktop.drafts.composer(Workspace::Personal).text(),
            oversize
        );
        desktop
            .drafts
            .composer_mut(Workspace::Personal)
            .edit("保留原始笔记".into());
        let output = frame(&mut desktop, vec![click(target)]);
        let Request::ObjectiveSubmit {
            client_intent_id,
            text,
            expected_instance,
        } = requests.try_recv().unwrap()
        else {
            panic!("typed submission");
        };
        assert_eq!(text, "保留原始笔记");
        assert_eq!(expected_instance, "current-session");
        assert_eq!(desktop.drafts.composer(Workspace::Personal).text(), text);
        assert_eq!(desktop.objectives.intents.len(), 1);
        let cancel = output
            .platform_output
            .accesskit_update
            .unwrap()
            .nodes
            .into_iter()
            .find(|(_, node)| node.label() == Some("Request cancellation"))
            .unwrap()
            .0;
        frame(&mut desktop, vec![click(target)]);
        assert!(
            requests.try_recv().is_err(),
            "queued or uncertain submission cannot mint a replacement ID"
        );
        frame(&mut desktop, vec![click(cancel)]);
        let Request::ObjectiveCancel {
            client_intent_id: cancelled,
            ..
        } = requests.try_recv().unwrap()
        else {
            panic!("typed cancellation");
        };
        assert_eq!(cancelled, client_intent_id);
        assert!(desktop.objectives.intents[0].cancel_queued);
    }

    #[test]
    fn ready_expires_on_both_transport_and_original_observation_clocks() {
        let now = Instant::now();
        let mut panel = ObjectivePanel::default();
        let mut observation = ready_observation();
        observation.observed_unix_ms = 10_000;
        panel.observe("session-a", observation, now);
        assert!(panel.ready("session-a", now, 10_000));
        assert!(!panel.ready("session-b", now, 10_000));
        assert!(!panel.ready("session-a", now + Duration::from_secs(3), 10_000));
        assert!(!panel.ready("session-a", now, 12_001));
        assert!(!panel.ready("session-a", now, 9_999));
        panel.invalidate();
        assert!(!panel.ready("session-a", now, 10_000));
    }

    #[test]
    fn stale_or_unrelated_observations_cannot_rewrite_a_run() {
        let now = Instant::now();
        let mut panel = ObjectivePanel::default();
        let mut original =
            ObjectiveObservation::new(Some("intent-a".into()), ObjectiveStage::Admitted);
        original.run = Some(ObjectiveRunObservation {
            revision: 8,
            phase: ObjectiveRunPhase::Succeeded,
            terminal_observed: true,
        });
        panel.intents.push(IntentView {
            workspace: Some(Workspace::Personal),
            session: "a".into(),
            id: "intent-a".into(),
            observation: original.clone(),
            received_at: now,
            cancel_queued: false,
        });
        let mut stale = original.clone();
        stale.run.as_mut().unwrap().revision = 7;
        panel.observe("a", stale, now);
        let mut conflicting = original.clone();
        conflicting.run.as_mut().unwrap().phase = ObjectiveRunPhase::Dispatched;
        panel.observe("a", conflicting, now);
        panel.observe(
            "b",
            ObjectiveObservation::new(Some("intent-a".into()), ObjectiveStage::Queued),
            now,
        );
        panel.observe(
            "a",
            ObjectiveObservation::new(Some("unrelated".into()), ObjectiveStage::Queued),
            now,
        );
        assert_eq!(panel.intents[0].observation, original);
    }

    #[test]
    fn status_and_cancel_identity_survive_uncertain_submission() {
        let now = Instant::now();
        let mut panel = ObjectivePanel::default();
        let observation =
            ObjectiveObservation::new(Some("stable-intent".into()), ObjectiveStage::SubmitUnknown);
        panel.intents.push(IntentView {
            workspace: Some(Workspace::Build),
            session: "a".into(),
            id: "stable-intent".into(),
            observation,
            received_at: now,
            cancel_queued: false,
        });
        assert!(!finished(&panel.intents[0].observation));
        assert!(
            matches!(panel.poll(Workspace::Build, "a", now), Some(Request::ObjectiveStatus { client_intent_id, .. }) if client_intent_id == "stable-intent")
        );
        assert!(panel.poll(Workspace::Build, "a", now).is_none());
    }

    #[test]
    fn session_restart_queries_original_uncertain_intent_without_minting_or_resubmitting() {
        let now = Instant::now();
        let mut panel = ObjectivePanel::default();
        panel.intents.push(IntentView {
            workspace: Some(Workspace::Personal),
            session: "old-session".into(),
            id: "original-intent".into(),
            observation: ObjectiveObservation::new(
                Some("original-intent".into()),
                ObjectiveStage::SubmitUnknown,
            ),
            received_at: now,
            cancel_queued: true,
        });
        panel.observe("old-session", ready_observation(), now);
        panel.follow_session("new-session");
        assert!(!panel.ready("new-session", now, unix_ms()));
        let intent = panel.current(Workspace::Personal, "new-session").unwrap();
        assert!(!finished(&intent.observation));
        assert!(!intent.cancel_queued);
        assert!(!fresh(
            &intent.observation,
            intent.received_at,
            now,
            unix_ms()
        ));
        assert!(
            matches!(panel.poll(Workspace::Personal, "new-session", now),
            Some(Request::ObjectiveStatus { client_intent_id, expected_instance })
            if client_intent_id == "original-intent" && expected_instance == "new-session")
        );
        panel.observe(
            "old-session",
            ObjectiveObservation::new(Some("original-intent".into()), ObjectiveStage::Admitted),
            now,
        );
        assert_eq!(
            panel.intents[0].observation.stage,
            ObjectiveStage::SubmitUnknown
        );
        let mut recovered =
            ObjectiveObservation::new(Some("original-intent".into()), ObjectiveStage::Admitted);
        recovered.request_retained = true;
        panel.observe("new-session", recovered, now);
        assert_eq!(panel.intents.len(), 1);
        assert_eq!(panel.intents[0].id, "original-intent");
        assert_eq!(panel.intents[0].observation.stage, ObjectiveStage::Admitted);
    }

    #[test]
    fn fresh_shell_recovers_original_navigation_as_unknown_and_only_queries_status() {
        let now = Instant::now();
        let id = format!("desktop-research-{}", "ab".repeat(16));
        let mut view = ready_observation();
        view.retained_intents.as_mut().unwrap().client_intent_ids =
            vec![id.clone(), "legacy-id".into()];
        let mut panel = ObjectivePanel::default();
        panel.observe("session", view.clone(), now);
        panel.observe("session", view, now);
        assert_eq!(
            panel.intents.len(),
            2,
            "repeated recovery does not duplicate cards"
        );
        assert_eq!(panel.intents[0].workspace, Some(Workspace::Research));
        assert_eq!(panel.intents[1].workspace, None);
        for intent in &panel.intents {
            assert_eq!(intent.observation.stage, ObjectiveStage::SubmitUnknown);
            assert!(intent.observation.request_retained);
            assert!(!intent.observation.publication_retained);
            assert!(intent.observation.run.is_none());
            assert!(!finished(&intent.observation));
        }
        panel.selected = Some(id.clone());
        assert!(matches!(panel.poll(Workspace::Research, "session", now),
            Some(Request::ObjectiveStatus { client_intent_id, .. }) if client_intent_id == id));
        let mut incomplete = ready_observation();
        incomplete.retained_intents.as_mut().unwrap().complete = false;
        panel.observe("session", incomplete, now);
        assert!(!panel.ready("session", now, unix_ms()));
        panel.observe(
            "session",
            ObjectiveObservation::new(None, ObjectiveStage::Ready),
            now,
        );
        assert!(
            !panel.ready("session", now, unix_ms()),
            "missing recovery is unknown"
        );
    }
}

#[cfg(test)]
#[path = "objective_notes_tests.rs"]
mod notes_tests;
