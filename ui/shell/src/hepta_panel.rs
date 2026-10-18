//! Presentation only. Agentd transport and endpoint configuration live in
//! the host Session; this module cannot submit objectives or grant rights.

use eframe::egui::{self, RichText};
use serde::Serialize;
use std::io::{self, Write};
use std::time::{Duration, Instant};
use trill_ui_core::hepta::{
    HeptaConnectionState, HeptaProjection, HeptaRunConnectionState, HeptaRunProjection,
};
use trill_ui_core::observation::{self, FreshnessFailure};

const LAYOUT_PROBE_PREFIX: &[u8] = b"TRILL_HEPTA_LAYOUT_V1 ";

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
    observation::freshness_failure(
        projection
            .last_observation
            .as_ref()
            .map(|observation| observation.sampled_unix_ms),
        received_at.and_then(|received| now.checked_duration_since(received)),
        now_unix_ms,
    )
    .map(|failure| match failure {
        FreshnessFailure::SampleMissing => "hepta_observation_missing",
        FreshnessFailure::ReceiptTimeInvalid => "session_snapshot_time_invalid",
        FreshnessFailure::ReceiptExpired => "session_snapshot_expired",
        FreshnessFailure::SampleTimeInvalid => "hepta_observation_time_invalid",
        FreshnessFailure::SampleExpired => "hepta_observation_expired",
    })
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
            projection.mark_runtime_unavailable(code);
        }
    }
}

/// A conservative age bound combines the Session's monotonic sample age,
/// the whole IPC round trip, and time after actual transport receipt. It
/// includes a first response's queue delay even across wall-clock rollback.
/// Repeated snapshots retain the larger advancing bound for the same sample.
#[derive(Default)]
pub struct RunReceiptClock {
    source: Option<(String, String)>,
    sequence: Option<u64>,
    anchor: Option<RunAgeAnchor>,
}

#[derive(Clone, Copy)]
struct RunAgeAnchor {
    received_at: Instant,
    age_at_receipt: Duration,
}

impl RunAgeAnchor {
    fn age_at(self, now: Instant) -> Option<Duration> {
        self.age_at_receipt
            .checked_add(now.checked_duration_since(self.received_at)?)
    }
}

impl RunReceiptClock {
    pub fn observe(
        &mut self,
        session_instance: &str,
        run: Option<&mut HeptaRunProjection>,
        request_started_at: Instant,
        received_at: Instant,
    ) {
        let Some(run) = run else {
            *self = Self::default();
            return;
        };
        if self
            .source
            .as_ref()
            .is_none_or(|(session, run_id)| session != session_instance || run_id != &run.run_id)
        {
            self.source = Some((session_instance.into(), run.run_id.clone()));
            self.sequence = None;
            self.anchor = None;
        }
        let Some(sample) = &run.last_observation else {
            return;
        };
        if sample.run_id != run.run_id || sample.observation_sequence == 0 {
            run.mark_unavailable("run_observation_identity_invalid");
            return;
        }
        if self
            .sequence
            .is_some_and(|sequence| sample.observation_sequence < sequence)
        {
            run.mark_unavailable("run_observation_sequence_regressed");
            return;
        }
        let Some(source_age_ms) = run.sample_age_at_snapshot_ms else {
            run.mark_unavailable("run_observation_age_missing");
            return;
        };
        // The source snapshot occurs inside this request. The full RTT is
        // a conservative upper bound on its unmeasured transfer time; using
        // only receipt age could rejuvenate the first queued response.
        let Some(mut age_at_receipt) = received_at
            .checked_duration_since(request_started_at)
            .and_then(|rtt| Duration::from_millis(source_age_ms).checked_add(rtt))
        else {
            run.mark_unavailable("run_receipt_time_invalid");
            return;
        };
        if self.sequence == Some(sample.observation_sequence) {
            if let Some(anchor) = self.anchor {
                let Some(previous_age) = anchor.age_at(received_at) else {
                    run.mark_unavailable("run_receipt_time_invalid");
                    return;
                };
                // Advance the old bound once, rather than adding overlapping
                // RTTs or trusting a repeated frame with a younger source age.
                age_at_receipt = age_at_receipt.max(previous_age);
            }
        }
        self.sequence = Some(sample.observation_sequence);
        self.anchor = Some(RunAgeAnchor {
            received_at,
            age_at_receipt,
        });
    }

    pub fn age_at(&self, now: Instant) -> Option<Duration> {
        self.anchor.and_then(|anchor| anchor.age_at(now))
    }
}

pub fn expire_unfresh_run(
    run: Option<&mut HeptaRunProjection>,
    clock: &RunReceiptClock,
    now: Instant,
    now_unix_ms: u64,
) {
    let Some(run) = run else {
        return;
    };
    if run.connection != HeptaRunConnectionState::Observed {
        return;
    }
    if let Some(failure) = observation::freshness_failure(
        run.last_observation
            .as_ref()
            .map(|sample| sample.sampled_unix_ms),
        clock.age_at(now),
        now_unix_ms,
    ) {
        run.mark_unavailable(match failure {
            FreshnessFailure::SampleMissing => "run_observation_missing",
            FreshnessFailure::ReceiptTimeInvalid => "run_receipt_time_invalid",
            FreshnessFailure::ReceiptExpired => "run_receipt_expired",
            FreshnessFailure::SampleTimeInvalid => "run_observation_time_invalid",
            FreshnessFailure::SampleExpired => "run_observation_expired",
        });
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
    egui::ScrollArea::vertical().show(ui, |ui| {
        if let Some(run) = &projection.run {
            run_card(ui, run);
            ui.separator();
        }
        let Some(observation) = &projection.last_observation else {
            ui.label("No successful Hepta runtime observation has been received.");
            if projection.connection == HeptaConnectionState::NotConfigured {
                ui.label("The host Session has no configured Hepta observer endpoint.");
            }
            ui.label("Local drafts and independent host applications remain available.");
            return;
        };
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

fn run_card(ui: &mut egui::Ui, run: &HeptaRunProjection) {
    ui.group(|ui| {
        ui.label(RichText::new("Known Hepta run · read only").strong());
        ui.add(egui::Label::new(format!("Run ID: {}", run.run_id)).wrap());
        let color = if run.connection == HeptaRunConnectionState::Observed {
            super::success_color()
        } else {
            super::warning()
        };
        ui.colored_label(color, run.connection.label());
        if let Some(code) = &run.error_code {
            ui.small(format!("Run observation diagnostic: {code}"));
        }
        if run.connection == HeptaRunConnectionState::ProjectionMissing {
            ui.label("This ID is absent from the owner's current in-memory run projection. Objective admission and the durable outcome remain unknown.");
        }
        if let Some(sample) = &run.last_observation {
            if run.connection != HeptaRunConnectionState::Observed {
                ui.colored_label(super::warning(), "Retained owner metadata; the current run state is unknown.");
            }
            ui.label(format!("Owner phase: {} · revision: {}", sample.phase, sample.revision));
            ui.label(format!("Run generation: {} · authority epoch: {}", sample.generation, sample.authority_epoch));
            ui.label(format!("Terminal observed by original owner: {}", sample.terminal_observed));
            ui.small(format!("Owner receipt idempotent: {} · sampled unix ms: {} · read sequence: {}", sample.idempotent, sample.sampled_unix_ms, sample.observation_sequence));
        } else {
            ui.label("No successful observation of this run has been received.");
        }
        if run.observation_gap {
            ui.colored_label(super::warning(), "Run observation was interrupted; this volatile view has no complete run history.");
        }
        ui.small("The launcher supplied this exact ID. Owner phase and terminal observation do not prove a device effect completed. Host application tasks and local drafts remain separate.");
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
            run: None,
            runtime_sample_clock: None,
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

    #[test]
    fn run_card_keeps_exact_identity_owner_fields_and_unknown_history_visible() {
        use trill_ui_core::hepta::HeptaRunObservation;
        let exact_id = format!("known:{}", "r".repeat(122));
        let mut run = HeptaRunProjection::connecting(exact_id.clone());
        run.last_observation = Some(HeptaRunObservation {
            sampled_unix_ms: 10_000,
            observation_sequence: 1,
            run_id: exact_id.clone(),
            revision: 4,
            phase: "indeterminate".into(),
            authority_epoch: 9,
            generation: 6,
            terminal_observed: false,
            idempotent: false,
        });
        run.mark_projection_missing();
        // Exercise the actual runtime page with no successful health sample:
        // retained run metadata must still be shown above the empty runtime.
        let projection = HeptaProjection {
            run: Some(Box::new(run)),
            ..HeptaProjection::default()
        };
        let context = egui::Context::default();
        let output = context.run(
            egui::RawInput {
                screen_rect: Some(egui::Rect::from_min_size(
                    egui::Pos2::ZERO,
                    egui::vec2(1200.0, 1100.0),
                )),
                ..Default::default()
            },
            |ctx| {
                egui::CentralPanel::default().show(ctx, |ui| runtime(ui, &projection));
            },
        );
        let text = output
            .shapes
            .iter()
            .filter_map(|shape| match &shape.shape {
                egui::Shape::Text(text) => Some(text.galley.job.text.as_str()),
                _ => None,
            })
            .collect::<Vec<_>>()
            .join("\n");
        for expected in [
            exact_id.as_str(),
            "PROJECTION MISSING · CURRENT RUN STATE UNKNOWN",
            "Owner phase: indeterminate · revision: 4",
            "Run generation: 6 · authority epoch: 9",
            "Terminal observed by original owner: false",
            "Objective admission and the durable outcome remain unknown.",
            "do not prove a device effect completed",
        ] {
            assert!(
                text.contains(expected),
                "missing visible run metadata {expected:?}: {text:?}"
            );
        }
    }

    fn observed_run(sample_age_at_snapshot_ms: Option<u64>) -> HeptaRunProjection {
        use trill_ui_core::hepta::HeptaRunObservation;
        let mut run = HeptaRunProjection::connecting("known:run".into());
        run.connection = HeptaRunConnectionState::Observed;
        run.sample_age_at_snapshot_ms = sample_age_at_snapshot_ms;
        run.last_observation = Some(HeptaRunObservation {
            sampled_unix_ms: 10_000,
            observation_sequence: 2,
            run_id: run.run_id.clone(),
            revision: 4,
            phase: "indeterminate".into(),
            authority_epoch: 9,
            generation: 6,
            terminal_observed: false,
            idempotent: false,
        });
        run
    }

    #[test]
    fn missing_future_or_regressed_run_receipts_fail_closed_and_preserve_the_sample() {
        let now = Instant::now();
        let mut run = observed_run(Some(0));
        for receipt in [None, Some(now + Duration::from_millis(1))] {
            let mut missing_clock = run.clone();
            let mut clock = RunReceiptClock::default();
            if let Some(receipt) = receipt {
                clock.observe("session-a", Some(&mut missing_clock), receipt, receipt);
            }
            expire_unfresh_run(Some(&mut missing_clock), &clock, now, 10_000);
            assert_eq!(missing_clock.connection, HeptaRunConnectionState::Stale);
            assert_eq!(missing_clock.last_observation, run.last_observation);
        }
        let mut clock = RunReceiptClock::default();
        clock.observe("session-a", Some(&mut run), now, now);
        run.last_observation.as_mut().unwrap().observation_sequence = 1;
        clock.observe(
            "session-a",
            Some(&mut run),
            now,
            now + Duration::from_millis(1),
        );
        assert_eq!(run.connection, HeptaRunConnectionState::Stale);
        assert_eq!(
            run.error_code.as_deref(),
            Some("run_observation_sequence_regressed")
        );
        assert_eq!(clock.age_at(now), Some(Duration::ZERO));
    }

    #[test]
    fn repeated_run_age_advances_without_rejuvenation_or_double_counting_round_trips() {
        let now = Instant::now();
        let mut run = observed_run(Some(4_000));
        let history = run.last_observation.clone();
        let mut clock = RunReceiptClock::default();
        clock.observe(
            "session-a",
            Some(&mut run),
            now - Duration::from_millis(200),
            now,
        );
        assert_eq!(clock.age_at(now), Some(Duration::from_millis(4_200)));

        run.sample_age_at_snapshot_ms = Some(5_000);
        clock.observe(
            "session-a",
            Some(&mut run),
            now + Duration::from_millis(800),
            now + Duration::from_millis(1_000),
        );
        assert_eq!(
            clock.age_at(now + Duration::from_millis(1_000)),
            Some(Duration::from_millis(5_200)),
            "the repeated RTT must not be added to the overlapping old bound"
        );
        // A repeated, younger-looking source value cannot undo elapsed time.
        run.sample_age_at_snapshot_ms = Some(0);
        clock.observe(
            "session-a",
            Some(&mut run),
            now + Duration::from_millis(1_900),
            now + Duration::from_millis(2_000),
        );
        for (delta_ms, expected) in [
            (2_800, HeptaRunConnectionState::Observed),
            (2_801, HeptaRunConnectionState::Stale),
        ] {
            let mut view = run.clone();
            expire_unfresh_run(
                Some(&mut view),
                &clock,
                now + Duration::from_millis(delta_ms),
                10_000,
            );
            assert_eq!(view.connection, expected);
            assert_eq!(view.last_observation, history);
        }
    }

    #[test]
    fn missing_source_age_reversed_transport_time_and_huge_age_cannot_be_fresh() {
        let now = Instant::now();
        for (source_age, start, expected_code) in [
            (None, now, "run_observation_age_missing"),
            (
                Some(0),
                now + Duration::from_nanos(1),
                "run_receipt_time_invalid",
            ),
            (Some(u64::MAX), now, "run_receipt_expired"),
        ] {
            let mut run = observed_run(source_age);
            let history = run.last_observation.clone();
            let mut clock = RunReceiptClock::default();
            clock.observe("session-a", Some(&mut run), start, now);
            expire_unfresh_run(Some(&mut run), &clock, now, 10_000);
            assert_eq!(run.connection, HeptaRunConnectionState::Stale);
            assert_eq!(run.error_code.as_deref(), Some(expected_code));
            assert_eq!(run.last_observation, history);
        }
    }
}
