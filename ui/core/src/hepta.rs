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

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HeptaProjection {
    pub connection: HeptaConnectionState,
    pub last_attempt_unix_ms: Option<u64>,
    /// Stable, bounded diagnostic code only; no endpoint or raw backend error.
    pub error_code: Option<String>,
    pub last_observation: Option<HeptaRuntimeObservation>,
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
        let malicious = "错误\u{2028}READY\u{202E}DENIED\u{202C}\u{2066}SUCCESS\u{2069}\u{061C}\u{200F}";
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
}
