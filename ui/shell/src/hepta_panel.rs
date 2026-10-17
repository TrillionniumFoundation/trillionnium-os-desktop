//! Presentation only. Agentd transport and endpoint configuration live in
//! the host Session; this module cannot submit objectives or grant rights.

use eframe::egui::{self, RichText};
use trill_ui_core::hepta::{HeptaConnectionState, HeptaProjection};

pub fn status(ui: &mut egui::Ui, projection: &HeptaProjection) {
    let color = if projection.connection == HeptaConnectionState::Observed {
        super::success_color()
    } else {
        super::warning()
    };
    ui.colored_label(color, format!("Hepta: {}", projection.connection.label()));
    if let Some(code) = &projection.error_code {
        ui.small(format!("Observation diagnostic: {code}"));
    }
}

pub fn runtime(ui: &mut egui::Ui, projection: &HeptaProjection) {
    ui.heading("Hepta / Runtime");
    status(ui, projection);
    ui.label("Read-only runtime observations from the independent host Session.");
    ui.colored_label(
        super::warning(),
        "Objective submission unavailable · 认证目标适配器未装配；草稿未提交",
    );
    ui.small("Readiness and advertised capabilities do not grant permissions or confirm an AI task result.");
    ui.separator();
    let Some(observation) = &projection.last_observation else {
        ui.label("No successful Hepta runtime observation has been received.");
        if projection.connection == HeptaConnectionState::NotConfigured {
            ui.label("The host Session has no configured Hepta observer endpoint.");
        }
        ui.label("Local drafts and independent host applications remain available.");
        return;
    };
    egui::ScrollArea::vertical().show(ui, |ui| {
        ui.label(RichText::new("Last successful observation").strong());
        ui.label(format!("Agent: {}", observation.agent_id));
        ui.label(format!(
            "Spawn generation: {} · observed current generation: {}",
            observation.spawn_generation, observation.current_generation
        ));
        ui.label(format!(
            "Observed unix ms: {} · process ID: {}",
            observation.sampled_unix_ms, observation.health.process_id
        ));
        if projection.connection != HeptaConnectionState::Observed {
            ui.colored_label(super::warning(), "These values are stale. The current runtime state is unknown.");
        }
        ui.separator();
        ui.label(RichText::new("Runtime health").strong());
        ui.label(format!("Lifecycle: {}", observation.health.lifecycle));
        ui.label(format!(
            "Ready: {} · promotion ready: {} · fenced: {}",
            observation.health.ready,
            observation.health.promotion_ready,
            observation.health.fenced
        ));
        ui.separator();
        ui.label(RichText::new("Advertised protocol capabilities").strong());
        for capability in &observation.capabilities {
            ui.label(format!("{}  {}.{}", capability.id, capability.major, capability.minor));
        }
        if observation.capabilities.is_empty() {
            ui.label("None in this observation.");
        }
        if observation.capabilities_truncated {
            ui.colored_label(super::warning(), "The capability display was truncated to its bounded window.");
        }
        ui.small("The renderer can only read this projection; advertised capabilities are not callable from this page.");
        ui.separator();
        ui.label(RichText::new("Recent runtime event metadata").strong());
        ui.label(format!(
            "Read cursor: {} · latest reported cursor: {}",
            observation.next_cursor, observation.latest_cursor
        ));
        if observation.history_gap {
            ui.colored_label(super::warning(), "HISTORY GAP OBSERVED · This session does not have complete event history.");
        }
        if observation.source_changed {
            ui.colored_label(super::warning(), "Runtime process or generation changed; the previous event window was invalidated.");
        }
        if observation.events_omitted_from_view != 0 {
            ui.small(format!(
                "{} previously observed event entries omitted from this bounded view.",
                observation.events_omitted_from_view
            ));
        }
        egui::Grid::new("hepta-event-metadata").striped(true).show(ui, |ui| {
            ui.strong("Cursor");
            ui.strong("Kind");
            ui.strong("Generation");
            ui.strong("Lifecycle");
            ui.end_row();
            for event in observation.events.iter().rev() {
                ui.label(event.cursor.to_string());
                ui.label(&event.kind);
                ui.label(event.generation.map_or_else(|| "—".into(), |value| value.to_string()));
                ui.label(event.lifecycle.as_deref().unwrap_or("—"));
                ui.end_row();
            }
        });
        if observation.events.is_empty() {
            ui.label("No event entries in the current display window.");
        }
        ui.small("This is a volatile metadata view. It contains no event payloads, objective text, run ledger, or effect receipts.");
    });
}
