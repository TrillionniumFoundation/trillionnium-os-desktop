//! Exact receipt retirement on the inherited recovery lane. An ACK is not a
//! grant: only the original durable writer receives this private endpoint.

use serde::{Deserialize, Serialize};

use crate::notes::{
    lower_hex, valid_operation_id, NotesProtocolError, NotesTargetIdentity,
    MAX_NOTES_REQUEST_BYTES, NOTES_SCHEMA_VERSION,
};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotesAcknowledgeAction {
    AcknowledgeTerminal,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesAcknowledge {
    pub schema_version: u16,
    pub action: NotesAcknowledgeAction,
    pub target: NotesTargetIdentity,
    pub operation_id: String,
    pub payload_sha256: String,
    pub receipt_sha256: String,
}

impl NotesAcknowledge {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, NotesProtocolError> {
        if raw.is_empty() || raw.len() > MAX_NOTES_REQUEST_BYTES {
            return Err(NotesProtocolError::FrameBound);
        }
        let value: Self = serde_json::from_slice(raw).map_err(|_| NotesProtocolError::Schema)?;
        value.target.validate()?;
        if value.schema_version != NOTES_SCHEMA_VERSION {
            return Err(NotesProtocolError::Version);
        }
        if !valid_operation_id(&value.operation_id)
            || !lower_hex(&value.payload_sha256, 64)
            || !lower_hex(&value.receipt_sha256, 64)
        {
            return Err(NotesProtocolError::Digest);
        }
        Ok(value)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotesRetirementStatus {
    Released,
    AlreadyReleased,
    Unknown,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesRetirementResponse {
    pub schema_version: u16,
    pub target: NotesTargetIdentity,
    pub operation_id: String,
    pub payload_sha256: String,
    pub receipt_sha256: String,
    pub status: NotesRetirementStatus,
}

/// Original Hepta compiler observations on the same private recovery lane.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotesReadAction {
    ReadDocumentState,
    ReadPreviousReceipt,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesRead {
    pub schema_version: u16,
    pub action: NotesReadAction,
    pub target: NotesTargetIdentity,
    pub request_id: String,
}

impl NotesRead {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, NotesProtocolError> {
        if raw.is_empty() || raw.len() > MAX_NOTES_REQUEST_BYTES {
            return Err(NotesProtocolError::FrameBound);
        }
        let value: Self = serde_json::from_slice(raw).map_err(|_| NotesProtocolError::Schema)?;
        value.target.validate()?;
        if value.schema_version != NOTES_SCHEMA_VERSION {
            return Err(NotesProtocolError::Version);
        }
        if !lower_hex(&value.request_id, 32) {
            return Err(NotesProtocolError::Operation);
        }
        Ok(value)
    }
}
