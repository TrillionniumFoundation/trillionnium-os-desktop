//! Presentation only. Agentd transport and endpoint configuration live in
//! the host Session; this module cannot submit objectives or grant rights.

use eframe::egui::{self, RichText};
use serde::Serialize;
use std::io::{self, Write};
use std::time::{Duration, Instant};
use trill_ui_core::hepta::{HeptaConnectionState, HeptaProjection};

const LAYOUT_PROBE_PREFIX: &[u8] = b"TRILL_HEPTA_LAYOUT_V1 ";
const MAX_OBSERVATION_AGE: Duration = Duration::from_secs(7);

/// Both the local receipt and the original sample must be current. A response
/// can wait in the Shell queue while the UI is paused; receiving it now must
/// not reset the age of its runtime observation. Clock rollback is unknown,
/// not a zero-age success. Shared by visible state and the layout diagnostic.
fn freshness_failure(
    projection: &HeptaProjection,
    received_at: Option<Instant>,
    now: Instant,
    now_unix_ms: u64,
) -> Option<&'static str> {
    let Some(observation) = &projection.last_observation else {
        return Some("hepta_observation_missing");
    };
    let Some(received_age) = received_at.and_then(|received| now.checked_duration_since(received))
    else {
        return Some("session_snapshot_time_invalid");
    };
    if received_age > MAX_OBSERVATION_AGE {
        return Some("session_snapshot_expired");
    }
    let Some(sample_age_ms) = now_unix_ms.checked_sub(observation.sampled_unix_ms) else {
        return Some("hepta_observation_time_invalid");
    };
    if sample_age_ms > MAX_OBSERVATION_AGE.as_millis() as u64 {
        return Some("hepta_observation_expired");
    }
    None
}

/// Downgrade only current-looking data, preserving the complete last success
/// and the Session's attempt timestamp. Only a later Session snapshot may
/// restore Observed; existing unknown-state diagnostics are kept unchanged.
pub fn expire_unfresh_observation(
    projection: &mut HeptaProjection,
    received_at: Option<Instant>,
    now: Instant,
    now_unix_ms: u64,
) {
    if projection.connection == HeptaConnectionState::Observed {
        if let Some(code) = freshness_failure(projection, received_at, now, now_unix_ms) {
            projection.mark_unavailable(code);
        }
    }
}

/// Explicit opt-in stdout evidence from a completed runtime-page widget update.
/// It is not compositor presentation, a Hepta operation, or an effect receipt.
pub struct LayoutProbe {
    enabled: bool,
    emitted: bool,
}

#[derive(Serialize)]
struct LayoutObservation<'a> {
    page: &'static str,
    connection: &'static str,
    agent_id: &'a str,
    spawn_generation: u64,
    current_generation: u64,
    process_id: u32,
    sampled_unix_ms: u64,
}

impl LayoutProbe {
    pub fn new(enabled: bool) -> Self {
        Self {
            enabled,
            emitted: false,
        }
    }

    pub fn emit_after_runtime_layout<W: Write>(
        &mut self,
        projection: &HeptaProjection,
        received_at: Option<Instant>,
        now: Instant,
        now_unix_ms: u64,
        output: &mut W,
    ) -> io::Result<()> {
        if !self.enabled || self.emitted || projection.connection != HeptaConnectionState::Observed
        {
            return Ok(());
        }
        if freshness_failure(projection, received_at, now, now_unix_ms).is_some() {
            return Ok(());
        }
        let Some(observation) = &projection.last_observation else {
            return Ok(());
        };
        // A closed logging pipe never stalls the UI or creates a retry loop.
        self.emitted = true;
        let mut line = LAYOUT_PROBE_PREFIX.to_vec();
        serde_json::to_writer(
            &mut line,
            &LayoutObservation {
                page: "hepta",
                connection: "observed",
                agent_id: &observation.agent_id,
                spawn_generation: observation.spawn_generation,
                current_generation: observation.current_generation,
                process_id: observation.health.process_id,
                sampled_unix_ms: observation.sampled_unix_ms,
            },
        )
        .map_err(io::Error::other)?;
        line.push(b'\n');
        output.write_all(&line)?;
        output.flush()
    }
}

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
            ui.colored_label(super::warning(), "Runtime process or spawn generation changed; the previous event window was invalidated.");
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

#[cfg(test)]
mod probe_tests {
    use super::*;
    use trill_ui_core::hepta::{HeptaHealthObservation, HeptaRuntimeObservation};

    fn observed() -> HeptaProjection {
        HeptaProjection {
            connection: HeptaConnectionState::Observed,
            last_attempt_unix_ms: Some(10_000),
            error_code: None,
            last_observation: Some(HeptaRuntimeObservation {
                sampled_unix_ms: 10_000,
                agent_id: "11111111-1111-4111-8111-111111111111".into(),
                spawn_generation: 7,
                current_generation: 8,
                health: HeptaHealthObservation {
                    ready: true,
                    promotion_ready: true,
                    fenced: false,
                    lifecycle: "running".into(),
                    process_id: 42,
                },
                capabilities: Vec::new(),
                capabilities_truncated: false,
                events: Vec::new(),
                events_omitted_from_view: 0,
                next_cursor: 0,
                latest_cursor: 0,
                history_gap: false,
                source_changed: false,
            }),
        }
    }

    #[test]
    fn a_generic_frame_or_stale_projection_cannot_satisfy_runtime_layout_probe() {
        let now = Instant::now();
        let mut output = Vec::new();
        LayoutProbe::new(false)
            .emit_after_runtime_layout(&observed(), Some(now), now, 10_000, &mut output)
            .unwrap();
        for connection in [
            HeptaConnectionState::NotObserved,
            HeptaConnectionState::NotConfigured,
            HeptaConnectionState::Connecting,
            HeptaConnectionState::Unavailable,
            HeptaConnectionState::Stale,
        ] {
            let mut projection = observed();
            projection.connection = connection;
            LayoutProbe::new(true)
                .emit_after_runtime_layout(&projection, Some(now), now, 10_000, &mut output)
                .unwrap();
        }
        for (received, sample_now) in [
            (None, 10_000),
            (Some(now - Duration::from_secs(8)), 10_000),
            (Some(now), 17_001),
            (Some(now), 9_999),
        ] {
            LayoutProbe::new(true)
                .emit_after_runtime_layout(&observed(), received, now, sample_now, &mut output)
                .unwrap();
        }
        assert!(
            output.is_empty(),
            "unobserved or expired data emitted a runtime marker"
        );
    }

    #[test]
    fn runtime_layout_marker_binds_fresh_metadata_and_is_emitted_once() {
        let now = Instant::now();
        let mut probe = LayoutProbe::new(true);
        let mut output = Vec::new();
        for _ in 0..2 {
            probe
                .emit_after_runtime_layout(&observed(), Some(now), now, 10_005, &mut output)
                .unwrap();
        }
        assert_eq!(output.iter().filter(|byte| **byte == b'\n').count(), 1);
        assert!(output.starts_with(LAYOUT_PROBE_PREFIX));
        let marker: serde_json::Value =
            serde_json::from_slice(&output[LAYOUT_PROBE_PREFIX.len()..]).unwrap();
        assert_eq!(marker["page"], "hepta");
        assert_eq!(marker["connection"], "observed");
        assert_eq!(marker["agent_id"], "11111111-1111-4111-8111-111111111111");
        assert_eq!(marker["spawn_generation"], 7);
        assert_eq!(marker["current_generation"], 8);
        assert_eq!(marker["process_id"], 42);
        assert_eq!(marker["sampled_unix_ms"], 10_000);
    }
}
