//! Bounded, read-only Hepta observations for the host Session -> Shell IPC.
//!
//! These values are a volatile display projection, not an authority, objective
//! ingress, task ledger, or proof of an effect. The renderer never receives an
//! Agentd socket path, a raw event payload, or a general-purpose RPC method.

use serde::{Deserialize, Serialize};

pub const MAX_HEPTA_CAPABILITIES: usize = 16;
pub const MAX_HEPTA_EVENTS: usize = 16;
pub const MAX_HEPTA_TEXT_BYTES: usize = 96;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HeptaConnectionState {
    /// An older/missing Session projection must not imply a configured peer.
    #[default]
    NotObserved,
    NotConfigured,
    Connecting,
    Observed,
    Stale,
    Unavailable,
}

impl HeptaConnectionState {
    pub const fn label(self) -> &'static str {
        match self {
            Self::NotObserved => "NOT OBSERVED",
            Self::NotConfigured => "NOT CONFIGURED",
            Self::Connecting => "CONNECTING",
            Self::Observed => "OBSERVED · READ ONLY",
            Self::Stale => "STALE · CURRENT STATE UNKNOWN",
            Self::Unavailable => "UNAVAILABLE · CURRENT STATE UNKNOWN",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HeptaHealthObservation {
    pub ready: bool,
    pub promotion_ready: bool,
    pub fenced: bool,
    pub lifecycle: String,
    pub process_id: u32,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HeptaCapabilityObservation {
    pub id: String,
    pub major: u16,
    pub minor: u16,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HeptaEventObservation {
    pub cursor: u64,
    pub kind: String,
    pub generation: Option<u64>,
    pub lifecycle: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HeptaRuntimeObservation {
    pub sampled_unix_ms: u64,
    pub agent_id: String,
    pub spawn_generation: u64,
    pub current_generation: u64,
    pub health: HeptaHealthObservation,
    /// Advertised protocol versions are observations, never UI grants.
    pub capabilities: Vec<HeptaCapabilityObservation>,
    pub capabilities_truncated: bool,
    /// The last bounded window seen by this Session, not complete history.
    pub events: Vec<HeptaEventObservation>,
    pub events_omitted_from_view: u64,
    pub next_cursor: u64,
    pub latest_cursor: u64,
    /// Sticky for this Session: a later complete page cannot fill an old gap.
    pub history_gap: bool,
    /// A process/spawn change invalidates the old display event window.
    /// Ordinary current-generation advancement keeps the same source.
    pub source_changed: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HeptaRunConnectionState {
    Connecting,
    Observed,
    /// The owner's current in-memory projection did not contain this ID.
    /// This says nothing about objective publication or a durable outcome.
    ProjectionMissing,
    Stale,
    Unavailable,
}

impl HeptaRunConnectionState {
    pub const fn label(self) -> &'static str {
        match self {
            Self::Connecting => "CONNECTING · CURRENT RUN STATE UNKNOWN",
            Self::Observed => "OBSERVED · READ ONLY",
            Self::ProjectionMissing => "PROJECTION MISSING · CURRENT RUN STATE UNKNOWN",
            Self::Stale => "STALE · CURRENT RUN STATE UNKNOWN",
            Self::Unavailable => "UNAVAILABLE · CURRENT RUN STATE UNKNOWN",
        }
    }
}

/// One successful read of an already-known owner run. The seven owner fields
/// below retain the typed RunObservation meaning; no HostTask ID or inferred
/// effect state is added. Only sampling time and sequence belong to Session.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HeptaRunObservation {
    /// Conservative start of the completed read, including closing-health
    /// time in this sample's age instead of rejuvenating an earlier payload.
    pub sampled_unix_ms: u64,
    /// Volatile, nonwrapping successful-read sequence within this Session.
    /// It is neither the owner's revision nor a publication receipt.
    pub observation_sequence: u64,
    pub run_id: String,
    pub revision: u64,
    pub phase: String,
    pub authority_epoch: u64,
    pub generation: u64,
    pub terminal_observed: bool,
    pub idempotent: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HeptaRunProjection {
    /// Exact, launcher-selected identity; never shortened for display.
    pub run_id: String,
    pub connection: HeptaRunConnectionState,
    pub last_attempt_unix_ms: Option<u64>,
    pub error_code: Option<String>,
    pub last_observation: Option<HeptaRunObservation>,
    /// Monotonic age of the retained sample when Session formed this snapshot,
    /// rounded up to milliseconds. Absent before a successful sample or from
    /// an older producer; a consumer must not infer freshness from absence.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sample_age_at_snapshot_ms: Option<u64>,
    /// Sticky interruption after a successful read, not a durable journal gap
    /// or a claim that the surrounding observation history was complete.
    pub observation_gap: bool,
}

impl HeptaRunProjection {
    pub fn connecting(run_id: String) -> Self {
        Self {
            run_id,
            connection: HeptaRunConnectionState::Connecting,
            last_attempt_unix_ms: None,
            error_code: None,
            last_observation: None,
            sample_age_at_snapshot_ms: None,
            observation_gap: false,
        }
    }

    pub fn mark_unavailable(&mut self, code: &str) {
        self.observation_gap |= self.last_observation.is_some();
        self.connection = if self.last_observation.is_some() {
            HeptaRunConnectionState::Stale
        } else {
            HeptaRunConnectionState::Unavailable
        };
        self.error_code = Some(bounded_hepta_text(code));
    }

    pub fn mark_projection_missing(&mut self) {
        self.observation_gap |= self.last_observation.is_some();
        self.connection = HeptaRunConnectionState::ProjectionMissing;
        self.error_code = Some("run_projection_missing".into());
    }
}

/// Session's clock for one successful runtime read, independent of later
/// failed polls and separately sampled known-run observations.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HeptaRuntimeSampleClock {
    /// Nonzero, nonwrapping successful-read sequence owned by this Session.
    pub observation_sequence: u64,
    /// Rounded up from the beginning of the complete successful runtime poll
    /// to the Session snapshot; independent of wall-clock adjustments.
    pub sample_age_at_snapshot_ms: u64,
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HeptaProjection {
    pub connection: HeptaConnectionState,
    pub last_attempt_unix_ms: Option<u64>,
    /// Stable, bounded diagnostic code only; no endpoint or raw backend error.
    pub error_code: Option<String>,
    pub last_observation: Option<HeptaRuntimeObservation>,
    /// Missing in older producers. A consumer must treat an observed runtime
    /// with no successful-sample age as unknown, not as a zero-age success.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_sample_clock: Option<Box<HeptaRuntimeSampleClock>>,
    /// Omitted unless a trusted launcher configured an exact known run ID.
    /// A runtime sample clock is independent of this optional run projection.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub run: Option<Box<HeptaRunProjection>>,
}

impl HeptaProjection {
    pub fn not_configured() -> Self {
        Self {
            connection: HeptaConnectionState::NotConfigured,
            ..Self::default()
        }
    }

    pub fn connecting() -> Self {
        Self {
            connection: HeptaConnectionState::Connecting,
            ..Self::default()
        }
    }

    /// Losing a transport does not erase evidence or make old evidence live.
    pub fn mark_unavailable(&mut self, code: &str) {
        self.mark_runtime_unavailable(code);
        if let Some(run) = &mut self.run {
            run.mark_unavailable(code);
        }
    }

    /// A runtime sample's age does not expire a separately sampled run read.
    pub fn mark_runtime_unavailable(&mut self, code: &str) {
        self.connection = if self.last_observation.is_some() {
            HeptaConnectionState::Stale
        } else {
            HeptaConnectionState::Unavailable
        };
        self.error_code = Some(bounded_hepta_text(code));
    }
}

/// UI-only display data. Strip ASCII controls, Unicode line separators,
/// bidi overrides/isolates and direction markers BEFORE size truncation.
/// Untrusted event metadata must not forge a "ready", "fenced" or error label
/// through visual reordering. This does NOT authorize a Hepta operation.
pub fn bounded_hepta_text(text: &str) -> String {
    let mut output = String::new();
    for character in text.chars().filter(|character| {
        !character.is_control()
            && !matches!(
                *character as u32,
                0x061C | 0x200E..=0x200F | 0x2028..=0x202E | 0x2066..=0x2069
            )
    }) {
        if output.len() + character.len_utf8() > MAX_HEPTA_TEXT_BYTES {
            break;
        }
        output.push(character);
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn diagnostic_projection_has_no_control_characters_and_respects_utf8_bound() {
        let text = bounded_hepta_text(&format!("\n\0{}", "中文".repeat(100)));
        assert!(!text.chars().any(char::is_control));
        assert!(text.len() <= MAX_HEPTA_TEXT_BYTES);
        assert!(text.is_char_boundary(text.len()));
    }

    #[test]
    fn event_labels_never_render_bidi_overrides_or_line_spoofing() {
        let malicious =
            "错误\u{2028}READY\u{202E}DENIED\u{202C}\u{2066}SUCCESS\u{2069}\u{061C}\u{200F}";
        let projected = bounded_hepta_text(malicious);
        assert_eq!(projected, "错误READYDENIEDSUCCESS");
        assert!(projected.len() <= MAX_HEPTA_TEXT_BYTES);
        assert!(!projected.chars().any(|character| {
            character.is_control()
                || matches!(
                    character as u32,
                    0x061C | 0x200E..=0x200F | 0x2028..=0x202E | 0x2066..=0x2069
                )
        }));
        assert_eq!(
            bounded_hepta_text("中文输入、候选词 📝 / Arabic العربية"),
            "中文输入、候选词 📝 / Arabic العربية",
            "ordinary Unicode display text must survive"
        );
    }

    #[test]
    fn missing_observation_is_unknown_after_transport_failure() {
        let mut view = HeptaProjection::not_configured();
        view.mark_unavailable("host_session_unavailable");
        assert_eq!(view.connection, HeptaConnectionState::Unavailable);
        assert!(view.last_observation.is_none());
    }

    #[test]
    fn an_unconfigured_run_keeps_the_previous_exact_wire_shape() {
        let old = r#"{"connection":"not_configured","last_attempt_unix_ms":null,"error_code":null,"last_observation":null}"#;
        let projection: HeptaProjection = serde_json::from_str(old).unwrap();
        assert!(projection.run.is_none());
        assert!(projection.runtime_sample_clock.is_none());
        assert_eq!(serde_json::to_string(&projection).unwrap(), old);
        assert_eq!(projection, HeptaProjection::not_configured());
    }

    #[test]
    fn runtime_sample_clock_never_deserializes_invalid_or_missing_age_as_zero() {
        let mut wire = serde_json::to_value(HeptaProjection::default()).unwrap();
        for invalid in [
            serde_json::json!({"observation_sequence": 1}),
            serde_json::json!({"observation_sequence": 1, "sample_age_at_snapshot_ms": null}),
            serde_json::json!({"observation_sequence": 1, "sample_age_at_snapshot_ms": -1}),
            serde_json::json!({"observation_sequence": 1, "sample_age_at_snapshot_ms": "0"}),
            serde_json::json!({"observation_sequence": 1, "sample_age_at_snapshot_ms": 0, "extra": true}),
        ] {
            wire["runtime_sample_clock"] = invalid;
            assert!(serde_json::from_value::<HeptaProjection>(wire.clone()).is_err());
        }
        wire["runtime_sample_clock"] = serde_json::json!({
            "observation_sequence": 1, "sample_age_at_snapshot_ms": 6000
        });
        let current: HeptaProjection = serde_json::from_value(wire.clone()).unwrap();
        assert_eq!(
            current
                .runtime_sample_clock
                .as_deref()
                .unwrap()
                .sample_age_at_snapshot_ms,
            6000
        );
        wire.as_object_mut().unwrap().remove("runtime_sample_clock");
        let older: HeptaProjection = serde_json::from_value(wire).unwrap();
        assert!(older.runtime_sample_clock.is_none());
    }
}
