//! Presentation for an explicitly configured signed-request inbox. This panel
//! cannot manufacture an envelope, sign a draft, choose an owner endpoint or
//! execute input. Only actual Session responses change admission/history text.
use eframe::egui::{self, RichText};
use std::time::{Duration, Instant};
use trill_ui_core::{objective::*, Request};

#[derive(Default)]
pub struct ObjectivePanel {
    configured: bool,
    owner: Option<String>,
    generation: Option<u64>,
    entries: Vec<ObjectiveSummary>,
    selected: Option<ObjectiveDetail>,
    reviewed: bool,
    last_poll: Option<Instant>,
    last_probe: Option<String>,
}
impl ObjectivePanel {
    pub fn list(
        &mut self,
        configured: bool,
        owner: Option<String>,
        generation: Option<u64>,
        entries: Vec<ObjectiveSummary>,
    ) {
        if entries.len() > MAX_ENTRIES {
            return;
        }
        if let Some(selected) = &mut self.selected {
            if let Some(current) = entries.iter().find(|e| {
                e.id == selected.summary.id && e.envelope_sha256 == selected.summary.envelope_sha256
            }) {
                selected.summary = current.clone();
            } else {
                self.selected = None;
                self.reviewed = false;
            }
        }
        self.configured = configured;
        self.owner = owner;
        self.generation = generation;
        self.entries = entries;
    }
    pub fn detail(&mut self, detail: ObjectiveDetail) {
        if detail.claimed_source_envelope_json.len() > 32 * 1024
            || !self.entries.iter().any(|e| {
                e.id == detail.summary.id && e.envelope_sha256 == detail.summary.envelope_sha256
            })
        {
            return;
        }
        self.selected = Some(detail);
        self.reviewed = false;
    }
    pub fn render(
        &mut self,
        ui: &mut egui::Ui,
        connected: bool,
        instance: Option<&str>,
        probe: bool,
    ) -> Option<Request> {
        ui.heading("Signed requests / 已签请求");
        ui.label("Choose an existing issuer envelope. Local conversation drafts stay local and are never added to its signed content.");
        let mut command = None;
        let mut positions = Vec::new();
        let now = Instant::now();
        let live = connected && instance.is_some();
        let instance = instance.unwrap_or_default();
        if live
            && self
                .last_poll
                .is_none_or(|last| now.duration_since(last) >= Duration::from_millis(800))
        {
            self.last_poll = Some(now);
            command = Some(Request::ObjectiveList {
                expected_instance: instance.into(),
            });
        }
        if !live {
            ui.colored_label(
                super::warning(),
                "Session unavailable. No request can be submitted; retained drafts are unchanged.",
            );
        }
        if !self.configured {
            ui.label("Submission unavailable: the trusted launcher has not supplied an original-owner connection and signed envelopes.");
        } else {
            ui.small(format!(
                "Original owner: {} · generation {}",
                self.owner.as_deref().unwrap_or("unknown"),
                self.generation.unwrap_or(0)
            ));
            ui.separator();
            for entry in &self.entries {
                let selected = self
                    .selected
                    .as_ref()
                    .is_some_and(|s| s.summary.id == entry.id);
                let response = ui.add_enabled(
                    live,
                    egui::Button::new(format!("{} · {}", entry.id, entry.delivery.label()))
                        .selected(selected),
                );
                positions.push((format!("select:{}", entry.id), response.rect));
                if response.clicked_by(egui::PointerButton::Primary) {
                    command = Some(Request::ObjectiveInspect {
                        id: entry.id.clone(),
                        expected_instance: instance.into(),
                    });
                }
            }
            if let Some(detail) = &self.selected {
                ui.separator();
                ui.label(RichText::new("Content claimed by the signed envelope — authentication is decided by the original owner").strong());
                ui.small(format!(
                    "Issuer claim: {} · run: {}",
                    detail.summary.claimed_issuer_id, detail.summary.run_id
                ));
                ui.small(format!(
                    "Envelope SHA-256: {}",
                    detail.summary.envelope_sha256
                ));
                egui::ScrollArea::vertical()
                    .id_salt("objective-claimed-content")
                    .max_height(170.0)
                    .show(ui, |ui| {
                        ui.add(egui::Label::new(&detail.claimed_source_envelope_json).wrap());
                    });
                ui.label(detail.summary.delivery.label());
                if let Some(issue) = &detail.summary.diagnostic {
                    ui.small(issue);
                }
                if let Some(digest) = &detail.summary.publication_digest {
                    ui.small(format!("Original admission publication: {digest}"));
                }
                ui.label(match detail.summary.history {
                    ObjectiveHistory::NotQueried => "Original history not queried",
                    ObjectiveHistory::Querying => "Querying original owner",
                    ObjectiveHistory::HistoricalPublication => {
                        "Original owner returned a historical publication"
                    }
                    ObjectiveHistory::Unknown => {
                        "History unknown; this does not prove non-admission"
                    }
                });
                if let Some(issue) = &detail.summary.history_diagnostic {
                    ui.small(issue);
                }
                if let Some(digest) = &detail.summary.history_publication_digest {
                    ui.small(format!("Last observed historical publication: {digest}"));
                }
                let review = ui.checkbox(
                    &mut self.reviewed,
                    "I reviewed the issuer's claimed content",
                );
                positions.push(("review".into(), review.rect));
                let ready = detail.summary.delivery == ObjectiveDelivery::Ready
                    && detail.summary.history != ObjectiveHistory::HistoricalPublication;
                ui.horizontal(|ui| {
                    let submit = ui.add_enabled(
                        live && ready && self.reviewed,
                        egui::Button::new("Submit signed request once"),
                    );
                    positions.push(("submit".into(), submit.rect));
                    if submit.clicked_by(egui::PointerButton::Primary) {
                        command = Some(Request::ObjectiveSubmit {
                            id: detail.summary.id.clone(),
                            expected_instance: instance.into(),
                        });
                        self.reviewed = false;
                    }
                    let idle = detail.summary.delivery != ObjectiveDelivery::Submitting
                        && detail.summary.history != ObjectiveHistory::Querying;
                    let query =
                        ui.add_enabled(live && idle, egui::Button::new("Query original owner"));
                    positions.push(("query".into(), query.rect));
                    if query.clicked_by(egui::PointerButton::Primary) {
                        command = Some(Request::ObjectiveQuery {
                            id: detail.summary.id.clone(),
                            expected_instance: instance.into(),
                        });
                    }
                });
                ui.small("Admission and history are not model execution or device-effect completion. Unknown delivery is never resent.");
            }
        }
        if probe {
            let value = serde_json::json!({"schema_version":1,"configured":self.configured,"connected":live,"selected":self.selected.as_ref().map(|d|&d.summary),"positions":positions.into_iter().map(|(name,rect)|serde_json::json!({"name":name,"x":rect.center().x,"y":rect.center().y})).collect::<Vec<_>>()});
            if let Ok(raw) = serde_json::to_string(&value) {
                if self.last_probe.as_ref() != Some(&raw) {
                    println!("TRILL_OBJECTIVE_LAYOUT_V1 {raw}");
                    self.last_probe = Some(raw);
                }
            }
        }
        command
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn detail() -> ObjectiveDetail {
        ObjectiveDetail {
            summary: ObjectiveSummary {
                id: "selected".into(),
                envelope_sha256: "1".repeat(64),
                claimed_issuer_id: "unverified-claim".into(),
                run_id: "run".into(),
                original_spawn_generation: 1,
                delivery: ObjectiveDelivery::Ready,
                diagnostic: None,
                publication_digest: None,
                history: ObjectiveHistory::NotQueried,
                history_diagnostic: None,
                history_publication_digest: None,
            },
            claimed_source_envelope_json: "untrusted plain source".into(),
        }
    }
    #[test]
    fn rendering_or_review_state_never_submits_without_primary_click() {
        let mut panel = ObjectivePanel::default();
        let value = detail();
        panel.list(
            true,
            Some("owner".into()),
            Some(1),
            vec![value.summary.clone()],
        );
        panel.detail(value);
        panel.reviewed = true;
        let ctx = egui::Context::default();
        let mut request = None;
        let _ = ctx.run(egui::RawInput::default(), |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                request = panel.render(ui, true, Some("instance"), false);
            });
        });
        assert!(matches!(
            request,
            Some(Request::ObjectiveList { .. }) | None
        ));
        assert_eq!(
            panel.selected.unwrap().summary.delivery,
            ObjectiveDelivery::Ready
        );
    }
    #[test]
    fn list_cannot_retarget_a_reviewed_selection_to_new_payload() {
        let mut panel = ObjectivePanel::default();
        let value = detail();
        panel.list(true, None, None, vec![value.summary.clone()]);
        panel.detail(value.clone());
        panel.reviewed = true;
        let mut changed = value.summary;
        changed.envelope_sha256 = "2".repeat(64);
        panel.list(true, None, None, vec![changed]);
        assert!(panel.selected.is_none());
        assert!(!panel.reviewed);
    }
}
