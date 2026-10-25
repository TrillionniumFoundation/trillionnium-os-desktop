//! Safe projection of a separately configured original ObjectiveStart client.
//! Drafts, claimed issuer fields and local delivery markers are not admission.
use serde::{Deserialize, Serialize};

pub const MAX_ENTRIES: usize = 8;
pub fn valid_entry_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 32
        && id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ObjectiveDelivery {
    #[default]
    Ready,
    Submitting,
    NotSent,
    Refused,
    Admitted,
    Conflict,
    Unknown,
}
impl ObjectiveDelivery {
    pub fn label(&self) -> &'static str {
        match self {
            Self::Ready => "Not submitted",
            Self::Submitting => "Submission in progress; outcome unknown",
            Self::NotSent => "This attempt wrote no bytes",
            Self::Refused => "Owner refused before publication",
            Self::Admitted => "Original owner published admission",
            Self::Conflict => "Original owner reported conflict",
            Self::Unknown => "Submission outcome unknown; do not resend",
        }
    }
}
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ObjectiveHistory {
    #[default]
    NotQueried,
    Querying,
    HistoricalPublication,
    Unknown,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ObjectiveSummary {
    pub id: String,
    pub envelope_sha256: String,
    pub claimed_issuer_id: String,
    pub run_id: String,
    pub original_spawn_generation: u64,
    pub delivery: ObjectiveDelivery,
    pub diagnostic: Option<String>,
    pub publication_digest: Option<String>,
    pub history: ObjectiveHistory,
    pub history_diagnostic: Option<String>,
    pub history_publication_digest: Option<String>,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ObjectiveDetail {
    pub summary: ObjectiveSummary,
    /// Explicitly selected, untrusted signed-claim source text. It is shown as
    /// plain text, never executed, interpreted as instructions or re-signed.
    pub claimed_source_envelope_json: String,
}
