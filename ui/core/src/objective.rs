//! Narrow user intent and original-owner observations. No authority or endpoint crosses UI IPC.
use serde::{Deserialize, Serialize};

pub const MAX_INTENT_BYTES: usize = 16 * 1024;
pub const MAX_OBJECTIVE_VIEWS: usize = 128;

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ObjectiveIntent {
    pub client_intent_id: String,
    pub text: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum ObjectiveCommand {
    Availability {},
    Submit { intent: ObjectiveIntent },
    Status { client_intent_id: String },
    Cancel { client_intent_id: String },
}

impl ObjectiveCommand {
    pub fn client_intent_id(&self) -> Option<&str> {
        match self {
            Self::Availability {} => None,
            Self::Submit { intent } => Some(&intent.client_intent_id),
            Self::Status { client_intent_id } | Self::Cancel { client_intent_id } => {
                Some(client_intent_id)
            }
        }
    }

    pub fn validate(&self) -> Result<(), ObjectiveHostIssue> {
        if let Some(id) = self.client_intent_id() {
            if id.is_empty()
                || id.len() > 96
                || !id
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || b"-_".contains(&c))
            {
                return Err(ObjectiveHostIssue::InvalidIntent);
            }
        }
        if let Self::Submit { intent } = self {
            if intent.text.trim().is_empty() || intent.text.len() > MAX_INTENT_BYTES {
                return Err(ObjectiveHostIssue::InvalidIntent);
            }
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ObjectiveHostIssue {
    Unavailable,
    InvalidIntent,
    Capacity,
    OwnerRefused,
    PersistenceUnknown,
    TransportUnknown,
    IdentityMismatch,
    NoRetainedIntent,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ObjectiveStage {
    Unavailable,
    Ready,
    Queued,
    Retained,
    NotSent,
    SubmitUnknown,
    Refused,
    Admitted,
    Abstained,
    Conflict,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ObjectiveRunPhase {
    Admitted,
    ContextAttached,
    Dispatched,
    Cancelling,
    Cancelled,
    Succeeded,
    Failed,
    Indeterminate,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ObjectiveRunObservation {
    pub revision: u64,
    pub phase: ObjectiveRunPhase,
    pub terminal_observed: bool,
}

/// Navigation IDs read from the original owner's retained requests. No signed
/// request, admission, sending permission or effect result is projected here.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ObjectiveRetainedIntents {
    pub client_intent_ids: Vec<String>,
    pub complete: bool,
}

impl ObjectiveRetainedIntents {
    pub fn validate(&self) -> Result<(), ObjectiveHostIssue> {
        if self.client_intent_ids.len() > MAX_OBJECTIVE_VIEWS {
            return Err(ObjectiveHostIssue::Capacity);
        }
        let mut seen = std::collections::BTreeSet::new();
        for id in &self.client_intent_ids {
            ObjectiveCommand::Status {
                client_intent_id: id.clone(),
            }
            .validate()?;
            if !seen.insert(id) {
                return Err(ObjectiveHostIssue::IdentityMismatch);
            }
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ObjectiveCancellation {
    #[default]
    NotRequested,
    Unknown,
    CancelledBeforeDispatch,
    CancellingAfterDispatch,
    AlreadyTerminal,
}

/// Admission, run state and cancellation remain separate. No field establishes
/// device/effect completion. This disposable view is never a recovery ledger.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ObjectiveObservation {
    /// Local view freshness only; never an authority clock.
    pub observed_unix_ms: u64,
    pub client_intent_id: Option<String>,
    pub stage: ObjectiveStage,
    pub request_retained: bool,
    pub publication_retained: bool,
    pub run: Option<ObjectiveRunObservation>,
    pub cancellation: ObjectiveCancellation,
    pub issue: Option<ObjectiveHostIssue>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub retained_intents: Option<ObjectiveRetainedIntents>,
}

impl ObjectiveObservation {
    pub fn new(client_intent_id: Option<String>, stage: ObjectiveStage) -> Self {
        Self {
            observed_unix_ms: crate::unix_ms(),
            client_intent_id,
            stage,
            request_retained: false,
            publication_retained: false,
            run: None,
            cancellation: ObjectiveCancellation::NotRequested,
            issue: None,
            retained_intents: None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{parse_host_request, Request};

    #[test]
    fn typed_intents_reject_authority_injection_and_duplicate_fields() {
        let valid = br#"{"type":"objective_submit","client_intent_id":"intent-1","text":"hello","expected_instance":"session"}"#;
        assert!(matches!(
            parse_host_request(valid).unwrap(),
            Request::ObjectiveSubmit { .. }
        ));
        for invalid in [
            br#"{"type":"objective_submit","client_intent_id":"intent-1","text":"hello","expected_instance":"session","signature":"trusted"}"#.as_slice(),
            br#"{"type":"objective_cancel","client_intent_id":"intent-1","expected_instance":"session","expected_revision":9}"#.as_slice(),
            br#"{"type":"objective_submit","client_intent_id":"one","client_intent_id":"two","text":"hello","expected_instance":"session"}"#.as_slice(),
        ] { assert!(parse_host_request(invalid).is_err()); }
        let invalid = ObjectiveCommand::Submit {
            intent: ObjectiveIntent {
                client_intent_id: "../owner".into(),
                text: "hello".into(),
            },
        };
        assert_eq!(invalid.validate(), Err(ObjectiveHostIssue::InvalidIntent));
    }

    #[test]
    fn navigation_recovery_rejects_duplicate_foreign_and_excessive_ids() {
        let valid = ObjectiveRetainedIntents {
            client_intent_ids: vec!["old-intent".into()],
            complete: true,
        };
        assert_eq!(valid.validate(), Ok(()));
        for ids in [
            vec!["one".into(), "one".into()],
            vec!["../owner".into()],
            (0..=MAX_OBJECTIVE_VIEWS)
                .map(|n| format!("id-{n}"))
                .collect(),
        ] {
            assert!(ObjectiveRetainedIntents {
                client_intent_ids: ids,
                complete: false
            }
            .validate()
            .is_err());
        }
        let old = ObjectiveObservation::new(None, ObjectiveStage::Unavailable);
        let json = serde_json::to_string(&old).unwrap();
        assert!(!json.contains("retained_intents"));
        assert_eq!(
            serde_json::from_str::<ObjectiveObservation>(&json).unwrap(),
            old
        );
    }
}
