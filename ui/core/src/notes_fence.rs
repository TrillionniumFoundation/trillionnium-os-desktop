//! A separately authorized effect, never accepted on the recovery lane.

use super::*;

pub const NOTES_FENCE_TOPIC: &str = "trill.notes.fence.v1";

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotesFenceAction {
    FenceNoteOperation,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesFence {
    pub schema_version: u16,
    pub action: NotesFenceAction,
    pub operation_id: String,
    pub destination_id: String,
    pub target: NotesTargetIdentity,
    pub original_operation_id: String,
    pub original_payload_sha256: String,
    pub expected_revision: u64,
}

impl NotesFence {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, NotesProtocolError> {
        check_frame(raw)?;
        let value: Self = serde_json::from_slice(raw).map_err(|_| NotesProtocolError::Schema)?;
        check_version(value.schema_version)?;
        value.target.validate()?;
        if !valid_operation_id(&value.operation_id)
            || !valid_operation_id(&value.original_operation_id)
            || value.operation_id == value.original_operation_id
        {
            return Err(NotesProtocolError::Operation);
        }
        if value.destination_id != value.target.destination_id() {
            return Err(NotesProtocolError::Destination);
        }
        if !lower_hex(&value.original_payload_sha256, 64) {
            return Err(NotesProtocolError::Digest);
        }
        Ok(value)
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case", deny_unknown_fields)]
pub enum NotesFenceResult {
    Fenced {
        original_operation_id: String,
        original_payload_sha256: String,
        previous_revision: u64,
        revision: u64,
        text_sha256: String,
    },
    NotFenced {
        reason: NotesNotAppliedReason,
        current_revision: u64,
    },
    Unknown {
        current_revision: u64,
    },
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesFenceResponse {
    pub schema_version: u16,
    pub target: NotesTargetIdentity,
    pub operation_id: String,
    pub payload_sha256: String,
    pub result: NotesFenceResult,
}

impl NotesFenceResponse {
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
        if let NotesFenceResult::Fenced {
            original_operation_id,
            original_payload_sha256,
            previous_revision,
            revision,
            text_sha256,
        } = &value.result
        {
            if !valid_operation_id(original_operation_id)
                || original_operation_id == &value.operation_id
                || !lower_hex(original_payload_sha256, 64)
                || previous_revision.checked_add(1) != Some(*revision)
                || !lower_hex(text_sha256, 64)
            {
                return Err(NotesProtocolError::Receipt);
            }
        }
        Ok(value)
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ObserveFence {
    schema_version: u16,
    action: ObserveFenceAction,
    target: NotesTargetIdentity,
    operation_id: String,
    payload_sha256: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum ObserveFenceAction { ObserveFence }

impl NotesDocument {
    /// The private effect owner must authorize these exact bytes first. The
    /// worker serializes this CAS with all edits and persists before replying.
    pub fn fence_exact(&mut self, raw: &[u8]) -> Result<NotesFenceResponse, NotesProtocolError> {
        let request = NotesFence::parse_exact(raw)?;
        let digest = sha256_hex(raw);
        let response = |result| NotesFenceResponse {
            schema_version: NOTES_SCHEMA_VERSION,
            target: self.target.clone(),
            operation_id: request.operation_id.clone(),
            payload_sha256: digest.clone(),
            result,
        };
        let refusal = |reason| response(NotesFenceResult::NotFenced {
            reason, current_revision: self.revision,
        });
        if request.target != self.target {
            return Ok(refusal(NotesNotAppliedReason::TargetMismatch));
        }
        if let Some(previous) = &self.last_fence {
            if previous.operation_id == request.operation_id {
                return Ok(if previous.payload_sha256 == digest {
                    previous.clone()
                } else { refusal(NotesNotAppliedReason::OperationConflict) });
            }
        }
        if request.expected_revision != self.revision {
            return Ok(refusal(NotesNotAppliedReason::RevisionConflict));
        }
        if self.last_applied.is_some() || self.last_fence.is_some() {
            return Ok(refusal(NotesNotAppliedReason::ReceiptPending));
        }
        let Some(revision) = self.revision.checked_add(1) else {
            return Ok(refusal(NotesNotAppliedReason::RevisionExhausted));
        };
        let receipt = response(NotesFenceResult::Fenced {
            original_operation_id: request.original_operation_id,
            original_payload_sha256: request.original_payload_sha256,
            previous_revision: self.revision,
            revision,
            text_sha256: sha256_hex(self.text.as_bytes()),
        });
        self.revision = revision;
        self.last_fence = Some(receipt.clone());
        self.fence_checkpoint = true;
        Ok(receipt)
    }

    pub(super) fn observe_fence_exact(&self, raw: &[u8]) -> Option<Result<Vec<u8>, NotesProtocolError>> {
        let query: ObserveFence = serde_json::from_slice(raw).ok()?;
        Some((|| {
            let _ = query.action;
            check_frame(raw)?;
            check_version(query.schema_version)?;
            query.target.validate()?;
            if query.target != self.target { return Err(NotesProtocolError::Target); }
            if !valid_operation_id(&query.operation_id) || !lower_hex(&query.payload_sha256, 64) {
                return Err(NotesProtocolError::Digest);
            }
            let response = self.last_fence.as_ref().filter(|r| {
                r.operation_id == query.operation_id && r.payload_sha256 == query.payload_sha256
            }).cloned().unwrap_or(NotesFenceResponse {
                schema_version: 1, target: self.target.clone(),
                operation_id: query.operation_id, payload_sha256: query.payload_sha256,
                result: NotesFenceResult::Unknown { current_revision: self.revision },
            });
            serde_json::to_vec(&response).map_err(|_| NotesProtocolError::Receipt)
        })())
    }
}

#[cfg(test)]
#[path = "notes_fence_tests.rs"]
mod tests;
