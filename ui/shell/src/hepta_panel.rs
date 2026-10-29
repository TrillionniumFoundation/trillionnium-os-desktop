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

/// A complete monotonic age bound and the original wall-clock sample must
/// both be current. Shared by visible state and the layout diagnostic.
fn freshness_failure(
    projection: &HeptaProjection,
    clock: &RuntimeReceiptClock,
    now: Instant,
    now_unix_ms: u64,
) -> Option<&'static str> {
    observation::freshness_failure(
        projection
            .last_observation
            .as_ref()
            .map(|observation| observation.sampled_unix_ms),
        clock.age_for(projection, now),
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
    clock: &RuntimeReceiptClock,
    now: Instant,
    now_unix_ms: u64,
) {
    if projection.connection == HeptaConnectionState::Observed {
        if let Some(code) = freshness_failure(projection, clock, now, now_unix_ms) {
            projection.mark_runtime_unavailable(code);
        }
    }
}

#[derive(PartialEq, Eq)]
struct RuntimeSource {
    session_instance: String,
    agent_id: String,
    spawn_generation: u64,
    process_id: u32,
}

/// A runtime clock is separate from the known run and scoped to the actual
/// Session and original process identity. Lifecycle generation changes do
/// not replace that process or reset a repeated successful sample's budget.
#[derive(Default)]
pub struct RuntimeReceiptClock {
    source: Option<RuntimeSource>,
    sequence: Option<u64>,
    anchor: Option<ReceiptAgeAnchor>,
}

impl RuntimeReceiptClock {
    pub fn observe(
        &mut self,
        session_instance: &str,
        projection: &mut HeptaProjection,
        request_started_at: Instant,
        received_at: Instant,
    ) {
        let Some(sample) = &projection.last_observation else {
            // A missing-history frame from the same Session is unknown; it
            // cannot erase a successful sample's already accumulated age.
            if self
                .source
                .as_ref()
                .is_some_and(|source| source.session_instance != session_instance)
            {
                *self = Self::default();
            }
            return;
        };
        let source = RuntimeSource {
            session_instance: session_instance.into(),
            agent_id: sample.agent_id.clone(),
            spawn_generation: sample.spawn_generation,
            process_id: sample.health.process_id,
        };
        if self.source.as_ref() != Some(&source) {
            self.source = Some(source);
            self.sequence = None;
            self.anchor = None;
        }
        // Historical states keep their original diagnostic. They cannot
        // refresh a successful receipt merely because another poll arrived.
        if projection.connection != HeptaConnectionState::Observed {
            return;
        }
        if session_instance.is_empty() || sample.agent_id.is_empty() {
            projection.mark_runtime_unavailable("hepta_observation_identity_invalid");
            return;
        }
        let Some(sample_clock) = projection.runtime_sample_clock.as_deref().copied() else {
            projection.mark_runtime_unavailable("hepta_observation_age_missing");
            return;
        };
        if sample_clock.observation_sequence == 0 {
            projection.mark_runtime_unavailable("hepta_observation_sequence_invalid");
            return;
        }
        if self
            .sequence
            .is_some_and(|sequence| sample_clock.observation_sequence < sequence)
        {
            projection.mark_runtime_unavailable("hepta_observation_sequence_regressed");
            return;
        }
        let previous = (self.sequence == Some(sample_clock.observation_sequence))
            .then_some(self.anchor)
            .flatten();
        let Some(anchor) = ReceiptAgeAnchor::from_snapshot(
            previous,
            sample_clock.sample_age_at_snapshot_ms,
            request_started_at,
            received_at,
        ) else {
            projection.mark_runtime_unavailable("session_snapshot_time_invalid");
            return;
        };
        self.sequence = Some(sample_clock.observation_sequence);
        self.anchor = Some(anchor);
    }

    pub fn age_at(&self, now: Instant) -> Option<Duration> {
        self.anchor.and_then(|anchor| anchor.age_at(now))
    }

    fn age_for(&self, projection: &HeptaProjection, now: Instant) -> Option<Duration> {
        let source = self.source.as_ref()?;
        let sample = projection.last_observation.as_ref()?;
        let sample_clock = projection.runtime_sample_clock.as_deref()?;
        if self.sequence != Some(sample_clock.observation_sequence)
            || source.agent_id != sample.agent_id
            || source.spawn_generation != sample.spawn_generation
            || source.process_id != sample.health.process_id
        {
            return None;
        }
        self.age_at(now)
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
    anchor: Option<ReceiptAgeAnchor>,
}

#[derive(Clone, Copy)]
struct ReceiptAgeAnchor {
    received_at: Instant,
    age_at_receipt: Duration,
}

impl ReceiptAgeAnchor {
    fn from_snapshot(
        previous: Option<Self>,
        source_age_ms: u64,
        request_started_at: Instant,
        received_at: Instant,
    ) -> Option<Self> {
        // The source snapshot occurs inside this request. The full RTT
        // conservatively bounds its unmeasured transfer time, including a
        // first response that is queued while wall time rolls back.
        let rtt = received_at.checked_duration_since(request_started_at)?;
        let mut age_at_receipt = Duration::from_millis(source_age_ms).checked_add(rtt)?;
        if let Some(previous) = previous {
            // Advance an old bound once; overlapping RTTs must not be added
            // repeatedly, nor can a younger repeated frame undo elapsed time.
            age_at_receipt = age_at_receipt.max(previous.age_at(received_at)?);
        }
        Some(Self {
            received_at,
            age_at_receipt,
        })
    }

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
        let previous = (self.sequence == Some(sample.observation_sequence))
            .then_some(self.anchor)
            .flatten();
        let Some(anchor) = ReceiptAgeAnchor::from_snapshot(
            previous,
            source_age_ms,
            request_started_at,
            received_at,
        ) else {
            run.mark_unavailable("run_receipt_time_invalid");
            return;
        };
        self.sequence = Some(sample.observation_sequence);
        self.anchor = Some(anchor);
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
        clock: &RuntimeReceiptClock,
        now: Instant,
        now_unix_ms: u64,
        output: &mut W,
    ) -> io::Result<()> {
        if !self.enabled || self.emitted || projection.connection != HeptaConnectionState::Observed
        {
            return Ok(());
        }
        if freshness_failure(projection, clock, now, now_unix_ms).is_some() {
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
    ui.colored_label(
        color,
        format!("Hepta runtime observer: {}", projection.connection.label()),
    );
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
        "Read-only runtime view · 已签请求请见 Signed requests；草稿仍未提交",
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
    use trill_ui_core::hepta::{
        HeptaHealthObservation, HeptaRuntimeObservation, HeptaRuntimeSampleClock,
    };

    fn observed() -> HeptaProjection {
        HeptaProjection {
            connection: HeptaConnectionState::Observed,
            last_attempt_unix_ms: Some(10_000),
            error_code: None,
            run: None,
            runtime_sample_clock: Some(Box::new(HeptaRuntimeSampleClock {
                observation_sequence: 1,
                sample_age_at_snapshot_ms: 0,
            })),
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

    fn receipt_clock(received: Option<Instant>) -> RuntimeReceiptClock {
        let mut clock = RuntimeReceiptClock::default();
        if let Some(received) = received {
            clock.observe("layout-test-session", &mut observed(), received, received);
        }
        clock
    }

    #[test]
    fn runtime_repeated_samples_share_one_advancing_budget_with_the_layout_gate() {
        let now = Instant::now();
        let mut view = observed();
        let history = view.last_observation.clone();
        view.runtime_sample_clock
            .as_mut()
            .unwrap()
            .sample_age_at_snapshot_ms = 4_000;
        let mut clock = RuntimeReceiptClock::default();
        clock.observe(
            "session-a",
            &mut view,
            now - Duration::from_millis(200),
            now,
        );
        assert_eq!(clock.age_at(now), Some(Duration::from_millis(4_200)));
        view.runtime_sample_clock
            .as_mut()
            .unwrap()
            .sample_age_at_snapshot_ms = 5_000;
        clock.observe(
            "session-a",
            &mut view,
            now + Duration::from_millis(800),
            now + Duration::from_millis(1_000),
        );
        assert_eq!(
            clock.age_at(now + Duration::from_millis(1_000)),
            Some(Duration::from_millis(5_200))
        );
        view.runtime_sample_clock
            .as_mut()
            .unwrap()
            .sample_age_at_snapshot_ms = 0;
        clock.observe(
            "session-a",
            &mut view,
            now + Duration::from_millis(1_900),
            now + Duration::from_millis(2_000),
        );
        for (elapsed_ms, expected) in [
            (2_800, HeptaConnectionState::Observed),
            (2_801, HeptaConnectionState::Stale),
        ] {
            let at = now + Duration::from_millis(elapsed_ms);
            let mut rendered = view.clone();
            expire_unfresh_observation(&mut rendered, &clock, at, 10_000);
            assert_eq!(rendered.connection, expected);
            assert_eq!(rendered.last_observation, history);
            let mut marker = Vec::new();
            // Use the original current-looking projection as input: checking
            // the marker after a caller already staled it would be too weak.
            LayoutProbe::new(true)
                .emit_after_runtime_layout(&view, &clock, at, 10_000, &mut marker)
                .unwrap();
            assert_eq!(marker.is_empty(), expected == HeptaConnectionState::Stale);
        }
    }

    #[test]
    fn runtime_clock_is_bound_to_session_agent_spawn_and_process_but_not_lifecycle_revision() {
        let now = Instant::now();
        for source_part in 0..4 {
            let mut view = observed();
            view.runtime_sample_clock = Some(Box::new(HeptaRuntimeSampleClock {
                observation_sequence: 9,
                sample_age_at_snapshot_ms: 6_000,
            }));
            let mut clock = RuntimeReceiptClock::default();
            clock.observe("session-a", &mut view, now, now);
            // A normal lifecycle generation change cannot rejuvenate the
            // same successful sample, even if its new claimed age is zero.
            view.last_observation.as_mut().unwrap().current_generation += 1;
            view.runtime_sample_clock
                .as_mut()
                .unwrap()
                .sample_age_at_snapshot_ms = 0;
            let later = now + Duration::from_millis(1_001);
            clock.observe("session-a", &mut view, later, later);
            expire_unfresh_observation(&mut view, &clock, later, 10_000);
            assert_eq!(view.connection, HeptaConnectionState::Stale);

            let mut replacement = observed();
            let session = if source_part == 0 {
                "session-b"
            } else {
                "session-a"
            };
            let identity = replacement.last_observation.as_mut().unwrap();
            match source_part {
                1 => identity.agent_id = "22222222-2222-4222-8222-222222222222".into(),
                2 => identity.spawn_generation += 1,
                3 => identity.health.process_id += 1,
                _ => {}
            }
            replacement.runtime_sample_clock = None;
            clock.observe(session, &mut replacement, later, later);
            assert_eq!(replacement.connection, HeptaConnectionState::Stale);
            assert_eq!(
                replacement.error_code.as_deref(),
                Some("hepta_observation_age_missing")
            );
            assert_eq!(
                clock.age_at(later),
                None,
                "new source inherited an old clock"
            );

            replacement.connection = HeptaConnectionState::Observed;
            replacement.error_code = None;
            replacement.runtime_sample_clock = Some(Box::new(HeptaRuntimeSampleClock {
                observation_sequence: 1,
                sample_age_at_snapshot_ms: 1_000,
            }));
            clock.observe(session, &mut replacement, later, later);
            expire_unfresh_observation(&mut replacement, &clock, later, 10_000);
            assert_eq!(replacement.connection, HeptaConnectionState::Observed);
            assert_eq!(clock.age_at(later), Some(Duration::from_millis(1_000)));
        }
    }

    #[test]
    fn runtime_sequence_regression_is_unknown_and_only_a_new_success_can_reset_its_age() {
        let now = Instant::now();
        let mut view = observed();
        view.runtime_sample_clock = Some(Box::new(HeptaRuntimeSampleClock {
            observation_sequence: 2,
            sample_age_at_snapshot_ms: 6_000,
        }));
        let mut clock = RuntimeReceiptClock::default();
        clock.observe("session-a", &mut view, now, now);
        view.runtime_sample_clock = Some(Box::new(HeptaRuntimeSampleClock {
            observation_sequence: 1,
            sample_age_at_snapshot_ms: 0,
        }));
        let history = view.last_observation.clone();
        clock.observe("session-a", &mut view, now, now);
        assert_eq!(view.connection, HeptaConnectionState::Stale);
        assert_eq!(
            view.error_code.as_deref(),
            Some("hepta_observation_sequence_regressed")
        );
        assert_eq!(view.last_observation, history);
        assert_eq!(clock.age_at(now), Some(Duration::from_millis(6_000)));
        view.connection = HeptaConnectionState::Observed;
        view.error_code = None;
        view.runtime_sample_clock = Some(Box::new(HeptaRuntimeSampleClock {
            observation_sequence: 3,
            sample_age_at_snapshot_ms: 0,
        }));
        let later = now + Duration::from_secs(8);
        clock.observe("session-a", &mut view, later, later);
        expire_unfresh_observation(&mut view, &clock, later, 10_000);
        assert_eq!(view.connection, HeptaConnectionState::Observed);
        assert_eq!(clock.age_at(later), Some(Duration::ZERO));
    }

    #[test]
    fn a_generic_frame_or_stale_projection_cannot_satisfy_runtime_layout_probe() {
        let now = Instant::now();
        let mut output = Vec::new();
        LayoutProbe::new(false)
            .emit_after_runtime_layout(
                &observed(),
                &receipt_clock(Some(now)),
                now,
                10_000,
                &mut output,
            )
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
                .emit_after_runtime_layout(
                    &projection,
                    &receipt_clock(Some(now)),
                    now,
                    10_000,
                    &mut output,
                )
                .unwrap();
        }
        for (received, sample_now) in [
            (None, 10_000),
            (Some(now - Duration::from_secs(8)), 10_000),
            (Some(now), 17_001),
            (Some(now), 9_999),
        ] {
            LayoutProbe::new(true)
                .emit_after_runtime_layout(
                    &observed(),
                    &receipt_clock(received),
                    now,
                    sample_now,
                    &mut output,
                )
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
                .emit_after_runtime_layout(
                    &observed(),
                    &receipt_clock(Some(now)),
                    now,
                    10_005,
                    &mut output,
                )
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
