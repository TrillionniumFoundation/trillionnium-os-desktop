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
    pub fn transport_request(&self) -> ObjectiveTransportRequest {
        match self {
            Self::Availability {} => ObjectiveTransportRequest::Availability {},
            Self::Submit { intent } => ObjectiveTransportRequest::Submit {
                client_intent_id: intent.client_intent_id.clone(),
            },
            Self::Status { client_intent_id } => ObjectiveTransportRequest::Status {
                client_intent_id: client_intent_id.clone(),
            },
            Self::Cancel { client_intent_id } => ObjectiveTransportRequest::Cancel {
                client_intent_id: client_intent_id.clone(),
            },
        }
    }

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

/// A Session transport receipt identifies one request without carrying text,
/// authority or an original-owner outcome. A consumer must match its own RPC.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum ObjectiveTransportRequest {
    Availability {},
    Submit { client_intent_id: String },
    Status { client_intent_id: String },
    Cancel { client_intent_id: String },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ObjectiveTransportRejectionReason {
    Capacity,
    Unavailable,
    InvalidIntent,
}

/// Only a rejection before Session enqueues the original RPC. A timeout,
/// dropped reply or owner Capacity observation cannot produce this receipt.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ObjectiveTransportRejection {
    pub request: ObjectiveTransportRequest,
    pub reason: ObjectiveTransportRejectionReason,
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

/// A read-only snapshot from the exact attached Notes application. This is
/// independent of run admission/terminality and is never an effect receipt.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesDocumentObservation {
    pub target: crate::notes::NotesTargetIdentity,
    pub observed_unix_ms: u64,
    pub revision: u64,
    pub text_sha256: String,
    pub receipt_pending: bool,
}

impl NotesDocumentObservation {
    pub fn validate(&self) -> Result<(), ObjectiveHostIssue> {
        self.target
            .validate()
            .map_err(|_| ObjectiveHostIssue::IdentityMismatch)?;
        if self.observed_unix_ms == 0
            || self.text_sha256.len() != 64
            || !self
                .text_sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            return Err(ObjectiveHostIssue::IdentityMismatch);
        }
        Ok(())
    }
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub notes_document: Option<NotesDocumentObservation>,
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
            notes_document: None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn local_transport_rejection_is_distinct_from_owner_observation() {
        let golden = include_str!("../../../tests/ui/objective-transport-rejection-v1.json");
        let response: crate::Response = serde_json::from_str(golden).unwrap();
        let crate::Response::ObjectiveTransportRejected {
            rejection,
            session_instance,
        } = &response
        else {
            panic!("expected the explicit local transport receipt");
        };
        assert_eq!(session_instance, "original-session");
        assert_eq!(
            rejection.reason,
            ObjectiveTransportRejectionReason::Capacity
        );
        assert_eq!(
            rejection.request,
            ObjectiveTransportRequest::Submit {
                client_intent_id: "original-intent".into()
            }
        );
        let value: serde_json::Value = serde_json::from_str(golden).unwrap();
        assert_eq!(serde_json::to_value(&response).unwrap(), value);
        for extra in ["run", "cancellation", "authority", "request_retained"] {
            let mut invalid = value.clone();
            invalid["rejection"][extra] = serde_json::json!(true);
            assert!(serde_json::from_value::<crate::Response>(invalid).is_err());
        }
        let mut uncertain = value;
        uncertain["rejection"]["reason"] = serde_json::json!("transport_unknown");
        assert!(serde_json::from_value::<crate::Response>(uncertain).is_err());
    }
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

    #[test]
    fn actual_document_readback_is_independent_of_unknown_objective_delivery() {
        let raw = include_str!("../../../tests/ui/notes-document-observation-v1.json");
        let view: ObjectiveObservation = serde_json::from_str(raw).unwrap();
        assert_eq!(view.stage, ObjectiveStage::SubmitUnknown);
        assert!(!view.publication_retained);
        assert!(view.run.is_none());
        let observed = view.notes_document.as_ref().unwrap();
        assert_eq!(observed.validate(), Ok(()));
        assert_eq!(observed.revision, 5);
        assert_eq!(
            observed.text_sha256,
            crate::notes::sha256_hex("已保存的笔记".as_bytes())
        );
        assert_eq!(
            serde_json::to_value(&view).unwrap(),
            serde_json::from_str::<serde_json::Value>(raw).unwrap()
        );
        for changed in ["foreign-target", "invalid-digest", "missing-time"] {
            let mut rejected = observed.clone();
            match changed {
                "foreign-target" => rejected.target.incarnation = "../../other".into(),
                "invalid-digest" => rejected.text_sha256 = "a".repeat(63),
                _ => rejected.observed_unix_ms = 0,
            }
            assert_eq!(
                rejected.validate(),
                Err(ObjectiveHostIssue::IdentityMismatch)
            );
        }
    }
}
