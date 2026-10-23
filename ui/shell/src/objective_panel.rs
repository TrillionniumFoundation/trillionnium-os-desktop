//! Disposable Objective UI observations. The host owns identity, admission,
//! publication and run state; this module retains no authority or recovery log.
use super::{Desktop, Workspace};
use eframe::egui;
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
        for intent in &mut self.intents {
            if intent.session != session {
                intent.session = session.into();
                intent.observation.observed_unix_ms = 0;
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
            if let Some(intent) = self.current(workspace, session) {
                return Some(Request::ObjectiveStatus {
                    client_intent_id: intent.id.clone(),
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

impl Desktop {
    pub(super) fn objective_controls(&mut self, ui: &mut egui::Ui) {
        ui.separator();
        ui.strong("Hepta Notes / 笔记");
        let Some(session) = self.session_instance.clone().filter(|_| self.connected) else {
            ui.label("Waiting for the current host session. Sending is unavailable.");
            return;
        };
        let now = Instant::now();
        if let Some(request) = self.objectives.poll(self.workspace, &session, now) {
            self.bridge.poll_objective(request);
        }
        let ready = self.objectives.ready(&session, now, unix_ms());
        let previous: Vec<_> = self
            .objectives
            .intents
            .iter()
            .filter(|intent| {
                intent.session == session
                    && intent
                        .workspace
                        .is_none_or(|workspace| workspace == self.workspace)
            })
            .map(|intent| intent.id.clone())
            .collect();
        // Keep one parent scope even before the first request. Inserting the
        // history must not renumber an already exposed cancellation control.
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
                                }
                            }
                        });
                });
            }
        });
        ui.label(if ready {
            "Hepta is available to write this text into the configured Notes document."
        } else {
            "Checking Hepta availability; sending remains disabled until a fresh host observation."
        });
        ui.small("The text is Notes document content. General AI tasks and other device actions are not supported here. Notes remain in app memory unless separately exported.");
        let composer = self.drafts.composer(self.workspace);
        let has_context = !composer.contexts.is_empty();
        let text = composer.text().to_owned();
        let may_start = self
            .objectives
            .intents
            .iter()
            .all(|intent| finished(&intent.observation));
        let enabled = ready
            && may_start
            && !has_context
            && !text.trim().is_empty()
            && text.len() <= MAX_NOTES_TEXT_BYTES
            && composer.can_save_local().is_ok()
            && self.objectives.intents.len() < MAX_OBJECTIVE_VIEWS;
        if self.activation.activated(&ui.add_enabled(
            enabled,
            egui::Button::new("Write note via Hepta / 通过 Hepta 写入笔记"),
        )) {
            match intent_id(self.workspace) {
                Ok(id) => {
                    if self.submit(Request::ObjectiveSubmit {
                        client_intent_id: id.clone(),
                        text: text.clone(),
                        expected_instance: session.clone(),
                    }) {
                        self.objectives.intents.push(IntentView {
                            workspace: Some(self.workspace),
                            session: session.clone(),
                            id: id.clone(),
                            observation: ObjectiveObservation::new(
                                Some(id),
                                ObjectiveStage::Queued,
                            ),
                            received_at: now,
                            cancel_queued: false,
                        });
                        self.objectives.selected = self
                            .objectives
                            .intents
                            .last()
                            .map(|intent| intent.id.clone());
                        self.notice("Objective queued for the host. Admission and execution are not yet confirmed; your draft remains available.");
                    }
                }
                Err(error) => self.notice(format!(
                    "Cannot create an intent ID; nothing queued: {error}"
                )),
            }
        }
        if text.len() > MAX_NOTES_TEXT_BYTES {
            ui.small("Notes content exceeds 4096 UTF-8 bytes. Shorten it before writing; all text remains in your draft.");
        }
        if has_context {
            ui.small("This objective transport accepts text only. Remove the quoted references before sending; your current draft and references are preserved.");
        }
        if self.objectives.intents.len() >= MAX_OBJECTIVE_VIEWS {
            ui.small("This window has reached its objective history limit. Existing status and cancellation remain available.");
        }
        let Some(intent) = self.objectives.current(self.workspace, &session) else {
            return;
        };
        let id = intent.id.clone();
        if intent.workspace.is_none() {
            ui.small("This request was recovered from Hepta. Its earlier workspace is unknown; status is queried without sending it again.");
        }
        let observation = &intent.observation;
        let current = fresh(observation, intent.received_at, now, unix_ms());
        ui.label(format!(
            "Objective {} · admission: {:?}{}",
            id,
            observation.stage,
            if current {
                ""
            } else {
                " (last observed; refresh pending)"
            }
        ));
        if observation.stage == ObjectiveStage::Abstained {
            ui.label("Hepta abstained. This objective was not admitted for execution.");
        }
        ui.small(format!(
            "Request retained: {} · publication retained: {}",
            observation.request_retained, observation.publication_retained
        ));
        if let Some(run) = &observation.run {
            ui.label(format!(
                "Run: {:?} · revision {} · terminal observed: {}",
                run.phase, run.revision, run.terminal_observed
            ));
        } else {
            ui.label("Run state has not been observed.");
        }
        ui.label(format!("Cancellation: {:?}", observation.cancellation));
        if intent.cancel_queued {
            ui.small("Cancellation request queued for the host; outcome remains unconfirmed.");
        }
        if let Some(issue) = observation.issue {
            ui.label(format!("Host observation: {issue:?}"));
        }
        ui.small("Run admission or a terminal run state does not prove a device effect. Your original draft is retained.");
        let can_cancel = !finished(observation);
        ui.push_id(("objective-actions", &id), |ui| {
            ui.horizontal(|ui| {
                if self
                    .activation
                    .activated(&ui.button("Refresh objective status"))
                {
                    self.bridge.poll_objective(Request::ObjectiveStatus {
                        client_intent_id: id.clone(),
                        expected_instance: session.clone(),
                    });
                }
                if self.activation.activated(
                    &ui.add_enabled(can_cancel, egui::Button::new("Request cancellation")),
                ) && self.submit(Request::ObjectiveCancel {
                    client_intent_id: id.clone(),
                    expected_instance: session,
                }) {
                    if let Some(intent) = self
                        .objectives
                        .intents
                        .iter_mut()
                        .find(|intent| intent.id == id)
                    {
                        intent.cancel_queued = true;
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
