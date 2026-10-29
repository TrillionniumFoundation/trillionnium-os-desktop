//! Bounded Notes document protocol for an explicitly inherited private channel.
//!
//! These types do not authenticate Hepta, issue a grant, or own operation
//! history. The original production writer must authorize the exact payload
//! before its target writes it. A `NotesDocument` receipt records an in-memory
//! change; the Linux `persistence::DurableNotes` product path publishes Applied
//! only after the document and exact receipt are durably committed together.
//! Neither receipt is a durable Hepta owner receipt or pixel evidence.

#[cfg(target_os = "linux")]
pub mod persistence;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub const NOTES_SCHEMA_VERSION: u16 = 1;
pub const NOTES_TOPIC: &str = "trill.notes.replace.v1";
pub const MAX_NOTES_TEXT_BYTES: usize = 4096;
pub const MAX_NOTES_REQUEST_BYTES: usize = 8192;
pub const MAX_NOTES_RESPONSE_BYTES: usize = 2048;

/// Read-only host projection. A prepared pipe or an observed application
/// layout does not install the original owner's production target.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotesChannelObservation {
    PrivateChannelPrepared,
    AppLayoutObserved,
    ChildExited,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesDestinationObservation {
    /// Session instance and task id already belong to the enclosing snapshot
    /// and TaskRecord. Keep this bounded projection within host frame limits.
    pub incarnation: String,
    pub channel: NotesChannelObservation,
    /// False for standalone Session. In explicit inherited-bootstrap mode,
    /// true records the parent's historical attachment ACK, not present
    /// authority, a signed grant, or application readiness. No effect request
    /// exists in public host IPC.
    pub original_owner_registered: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesTargetIdentity {
    pub session_instance: String,
    pub task_id: u64,
    pub incarnation: String,
}

impl NotesTargetIdentity {
    pub fn validate(&self) -> Result<(), NotesProtocolError> {
        if self.task_id == 0
            || !lower_hex(&self.session_instance, 32)
            || !lower_hex(&self.incarnation, 32)
        {
            return Err(NotesProtocolError::Target);
        }
        Ok(())
    }

    pub fn destination_id(&self) -> String {
        format!(
            "trill.notes:{}:{}:{}",
            self.session_instance, self.task_id, self.incarnation
        )
    }

    /// Domain-separated original-owner scope binding for this document
    /// incarnation. Revision belongs to the predecessor comparison, so local
    /// edits do not change this scope and cannot redirect it to another child.
    pub fn scope_sha256(&self) -> String {
        sha256_hex(
            format!(
                "trill.notes.scope.v1\0{}\0{}\0{}",
                self.session_instance, self.task_id, self.incarnation
            )
            .as_bytes(),
        )
    }

    /// Domain-separated original-owner predecessor binding. The production
    /// adapter must require its durable semantic predecessor digest to equal
    /// this value before handing off the exact request. The app compares this
    /// same incarnation/revision tuple atomically with its document mutation.
    pub fn predecessor_sha256(&self, revision: u64) -> String {
        sha256_hex(
            format!(
                "trill.notes.predecessor.v1\0{}\0{}\0{}\0{}",
                self.session_instance, self.task_id, self.incarnation, revision
            )
            .as_bytes(),
        )
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotesReplaceAction {
    ReplaceNote,
}

/// Exact JSON bytes, including their original whitespace/key order, are what
/// the production payload digest and target transport bind. Never reserialize
/// this parsed value and send the reconstruction instead of the original.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesReplace {
    pub schema_version: u16,
    pub action: NotesReplaceAction,
    pub operation_id: String,
    pub destination_id: String,
    pub target: NotesTargetIdentity,
    pub expected_revision: u64,
    pub text: String,
}

impl NotesReplace {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, NotesProtocolError> {
        check_frame(raw)?;
        let value: Self = serde_json::from_slice(raw).map_err(|_| NotesProtocolError::Schema)?;
        value.validate()?;
        Ok(value)
    }

    pub fn validate(&self) -> Result<(), NotesProtocolError> {
        check_version(self.schema_version)?;
        self.target.validate()?;
        if !valid_operation_id(&self.operation_id) {
            return Err(NotesProtocolError::Operation);
        }
        if self.destination_id != self.target.destination_id() {
            return Err(NotesProtocolError::Destination);
        }
        if self.text.len() > MAX_NOTES_TEXT_BYTES {
            return Err(NotesProtocolError::TextBound);
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotesObserveAction {
    Observe,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesObserve {
    pub schema_version: u16,
    pub action: NotesObserveAction,
    pub target: NotesTargetIdentity,
    pub operation_id: String,
    pub payload_sha256: String,
}

impl NotesObserve {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, NotesProtocolError> {
        check_frame(raw)?;
        let value: Self = serde_json::from_slice(raw).map_err(|_| NotesProtocolError::Schema)?;
        value.validate()?;
        Ok(value)
    }

    pub fn validate(&self) -> Result<(), NotesProtocolError> {
        check_version(self.schema_version)?;
        self.target.validate()?;
        if !valid_operation_id(&self.operation_id) {
            return Err(NotesProtocolError::Operation);
        }
        if !lower_hex(&self.payload_sha256, 64) {
            return Err(NotesProtocolError::Digest);
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotesNotAppliedReason {
    RevisionConflict,
    OperationConflict,
    RevisionExhausted,
    TargetMismatch,
    UiDeadlineElapsed,
    ReceiptPending,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case", deny_unknown_fields)]
pub enum NotesResult {
    Applied {
        previous_revision: u64,
        revision: u64,
        text_sha256: String,
    },
    NotApplied {
        reason: NotesNotAppliedReason,
        current_revision: u64,
    },
    Unknown {
        current_revision: u64,
    },
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesResponse {
    pub schema_version: u16,
    pub target: NotesTargetIdentity,
    pub operation_id: String,
    pub payload_sha256: String,
    pub result: NotesResult,
}

impl NotesResponse {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, NotesProtocolError> {
        if raw.is_empty() || raw.len() > MAX_NOTES_RESPONSE_BYTES {
            return Err(NotesProtocolError::FrameBound);
        }
        let value: Self = serde_json::from_slice(raw).map_err(|_| NotesProtocolError::Schema)?;
        check_version(value.schema_version)?;
        value.target.validate()?;
        if !valid_operation_id(&value.operation_id) || !lower_hex(&value.payload_sha256, 64) {
            return Err(NotesProtocolError::Digest);
        }
        if let NotesResult::Applied {
            previous_revision,
            revision,
            text_sha256,
        } = &value.result
        {
            if previous_revision.checked_add(1) != Some(*revision) || !lower_hex(text_sha256, 64) {
                return Err(NotesProtocolError::Receipt);
            }
        }
        Ok(value)
    }

    pub fn matches(&self, target: &NotesTargetIdentity, operation: &str, digest: &str) -> bool {
        &self.target == target && self.operation_id == operation && self.payload_sha256 == digest
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NotesProtocolError {
    FrameBound,
    Schema,
    Version,
    Target,
    Operation,
    Destination,
    TextBound,
    Digest,
    Receipt,
}

/// App-owned state, used on the egui thread. The one retained applied receipt
/// describes the last external mutation, not durable operation history. A
/// missing older receipt or a restarted process is Unknown, never "not sent".
pub struct NotesDocument {
    target: NotesTargetIdentity,
    text: String,
    revision: u64,
    last_applied: Option<NotesResponse>,
}

impl NotesDocument {
    pub fn new(target: NotesTargetIdentity) -> Result<Self, NotesProtocolError> {
        target.validate()?;
        Ok(Self {
            target,
            text: String::new(),
            revision: 0,
            last_applied: None,
        })
    }

    pub fn text(&self) -> &str {
        &self.text
    }

    pub fn revision(&self) -> u64 {
        self.revision
    }

    /// User edits share the same revision/CAS domain as externally authorized
    /// edits, so an agent cannot silently overwrite an intervening local edit.
    pub fn local_edit(&mut self, text: String) -> Result<(), NotesProtocolError> {
        if text.len() > MAX_NOTES_TEXT_BYTES {
            return Err(NotesProtocolError::TextBound);
        }
        if self.text != text {
            self.revision = self
                .revision
                .checked_add(1)
                .ok_or(NotesProtocolError::Receipt)?;
            self.text = text;
        }
        Ok(())
    }

    pub fn apply_exact(&mut self, raw: &[u8]) -> Result<NotesResponse, NotesProtocolError> {
        let request = NotesReplace::parse_exact(raw)?;
        let digest = sha256_hex(raw);
        let response = |result| NotesResponse {
            schema_version: NOTES_SCHEMA_VERSION,
            target: self.target.clone(),
            operation_id: request.operation_id.clone(),
            payload_sha256: digest.clone(),
            result,
        };
        let refusal = |reason| {
            response(NotesResult::NotApplied {
                reason,
                current_revision: self.revision,
            })
        };
        if request.target != self.target {
            return Ok(refusal(NotesNotAppliedReason::TargetMismatch));
        }
        if let Some(previous) = &self.last_applied {
            if previous.operation_id == request.operation_id {
                if previous.payload_sha256 == digest {
                    return Ok(previous.clone());
                }
                return Ok(refusal(NotesNotAppliedReason::OperationConflict));
            }
        }
        if request.expected_revision != self.revision {
            return Ok(refusal(NotesNotAppliedReason::RevisionConflict));
        }
        let Some(revision) = self.revision.checked_add(1) else {
            return Ok(refusal(NotesNotAppliedReason::RevisionExhausted));
        };
        let applied = response(NotesResult::Applied {
            previous_revision: self.revision,
            revision,
            text_sha256: sha256_hex(request.text.as_bytes()),
        });
        self.text = request.text;
        self.revision = revision;
        self.last_applied = Some(applied.clone());
        Ok(applied)
    }

    pub fn observe(&self, request: &NotesObserve) -> Result<NotesResponse, NotesProtocolError> {
        request.validate()?;
        if request.target != self.target {
            return Err(NotesProtocolError::Target);
        }
        if let Some(receipt) = &self.last_applied {
            if receipt.matches(&self.target, &request.operation_id, &request.payload_sha256) {
                return Ok(receipt.clone());
            }
        }
        Ok(NotesResponse {
            schema_version: NOTES_SCHEMA_VERSION,
            target: self.target.clone(),
            operation_id: request.operation_id.clone(),
            payload_sha256: request.payload_sha256.clone(),
            result: NotesResult::Unknown {
                current_revision: self.revision,
            },
        })
    }
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn check_frame(raw: &[u8]) -> Result<(), NotesProtocolError> {
    if raw.is_empty() || raw.len() > MAX_NOTES_REQUEST_BYTES {
        return Err(NotesProtocolError::FrameBound);
    }
    Ok(())
}

fn check_version(version: u16) -> Result<(), NotesProtocolError> {
    if version != NOTES_SCHEMA_VERSION {
        return Err(NotesProtocolError::Version);
    }
    Ok(())
}

pub fn lower_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

pub fn valid_operation_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-' | b':'))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn identity() -> NotesTargetIdentity {
        NotesTargetIdentity {
            session_instance: "a".repeat(32),
            task_id: 1,
            incarnation: "b".repeat(32),
        }
    }

    fn request(operation: &str, revision: u64, text: &str) -> Vec<u8> {
        serde_json::to_vec(&NotesReplace {
            schema_version: 1,
            action: NotesReplaceAction::ReplaceNote,
            operation_id: operation.into(),
            destination_id: identity().destination_id(),
            target: identity(),
            expected_revision: revision,
            text: text.into(),
        })
        .unwrap()
    }

    #[test]
    fn document_cas_preserves_user_edits_and_replay_does_not_repeat_effect() {
        let mut document = NotesDocument::new(identity()).unwrap();
        let payload = request("original-op", 0, "中文 Notes");
        let receipt = document.apply_exact(&payload).unwrap();
        assert_eq!(document.text(), "中文 Notes");
        document.local_edit("user changed this".into()).unwrap();
        assert_eq!(document.apply_exact(&payload).unwrap(), receipt);
        assert_eq!(document.text(), "user changed this");
        assert_eq!(document.revision(), 2);
        assert!(matches!(
            document
                .apply_exact(&request("next-op", 1, "overwrite"))
                .unwrap()
                .result,
            NotesResult::NotApplied {
                reason: NotesNotAppliedReason::RevisionConflict,
                current_revision: 2
            }
        ));
        assert_eq!(document.text(), "user changed this");
    }

    #[test]
    fn exact_bytes_and_only_retained_receipt_bound_observation() {
        let mut document = NotesDocument::new(identity()).unwrap();
        let payload = request("op-one", 0, "same text");
        document.apply_exact(&payload).unwrap();
        let query = NotesObserve {
            schema_version: 1,
            action: NotesObserveAction::Observe,
            target: identity(),
            operation_id: "op-one".into(),
            payload_sha256: sha256_hex(&payload),
        };
        assert!(matches!(
            document.observe(&query).unwrap().result,
            NotesResult::Applied { .. }
        ));
        let padded = [b" ".as_slice(), payload.as_slice()].concat();
        assert!(matches!(
            document.apply_exact(&padded).unwrap().result,
            NotesResult::NotApplied {
                reason: NotesNotAppliedReason::OperationConflict,
                ..
            }
        ));
        document
            .apply_exact(&request("op-two", 1, "same text"))
            .unwrap();
        assert!(matches!(
            document.observe(&query).unwrap().result,
            NotesResult::Unknown { .. }
        ));
        let fresh = NotesDocument::new(identity()).unwrap();
        assert!(matches!(
            fresh.observe(&query).unwrap().result,
            NotesResult::Unknown { .. }
        ));
    }

    #[test]
    fn schema_rejects_duplicates_unknown_fields_oversize_and_wrong_destination() {
        let raw = request("op", 0, "test");
        let text = String::from_utf8(raw).unwrap();
        for poisoned in [
            text.replacen("{", "{\"schema_version\":1,", 1),
            text.replacen("{", "{\"untrusted_grant\":true,", 1),
            text.replacen("\"task_id\":1", "\"task_id\":1,\"task_id\":2", 1),
        ] {
            assert!(NotesReplace::parse_exact(poisoned.as_bytes()).is_err());
        }
        assert!(NotesReplace::parse_exact(&request("op", 0, &"中".repeat(1366))).is_err());
        let mut parsed = NotesReplace::parse_exact(text.as_bytes()).unwrap();
        parsed.destination_id.push('x');
        assert_eq!(parsed.validate(), Err(NotesProtocolError::Destination));
    }

    #[test]
    fn fixed_cross_language_wire_fixture_matches_exact_payload_scope_and_predecessor() {
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../../../tests/ui/notes-target-v1.json")).unwrap();
        let raw = fixture["request_utf8"].as_str().unwrap().as_bytes();
        let request = NotesReplace::parse_exact(raw).unwrap();
        assert_eq!(sha256_hex(raw), fixture["payload_sha256"].as_str().unwrap());
        assert_eq!(
            request.target.scope_sha256(),
            fixture["expected_scope_sha256"].as_str().unwrap()
        );
        assert_eq!(
            request.target.predecessor_sha256(request.expected_revision),
            fixture["expected_predecessor_sha256"].as_str().unwrap()
        );
        let mut document = NotesDocument::new(request.target).unwrap();
        let response = document.apply_exact(raw).unwrap();
        let expected = NotesResponse::parse_exact(
            fixture["application_response_utf8"]
                .as_str()
                .unwrap()
                .as_bytes(),
        )
        .unwrap();
        assert_eq!(response, expected);
    }
}
