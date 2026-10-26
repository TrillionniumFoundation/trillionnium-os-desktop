//! Bounded application data, not an authorization or operation journal.

use super::*;
use crate::notes_recovery::NotesAcknowledge;

const MAX_CHECKPOINT_BYTES: usize = 16 * 1024;

// JSON null is meaningful; an absent receipt field is not proof of absence.
#[derive(Serialize, Deserialize)]
#[serde(untagged)]
enum Nullable<T> {
    Value(T),
    Null(()),
}

impl<T> From<Option<T>> for Nullable<T> {
    fn from(value: Option<T>) -> Self {
        match value {
            Some(value) => Self::Value(value),
            None => Self::Null(()),
        }
    }
}

impl<T> Nullable<T> {
    fn into_option(self) -> Option<T> {
        match self {
            Self::Value(value) => Some(value),
            Self::Null(()) => None,
        }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LegacyCheckpoint {
    schema_version: u16,
    target: NotesTargetIdentity,
    text: String,
    revision: u64,
    pending_receipt: Nullable<NotesResponse>,
    retired_receipt: Nullable<NotesAcknowledge>,
}

#[derive(Serialize, Deserialize)]
enum CheckpointFormat {
    #[serde(rename = "trill.notes.checkpoint")]
    Notes,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Checkpoint {
    format: CheckpointFormat,
    schema_version: u16,
    target: NotesTargetIdentity,
    text: String,
    revision: u64,
    pending_receipt: Nullable<NotesResponse>,
    retired_receipt: Nullable<NotesAcknowledge>,
}

#[derive(Deserialize)]
#[serde(untagged)]
enum InputCheckpoint {
    Current(Checkpoint),
    Legacy(LegacyCheckpoint),
}

impl InputCheckpoint {
    fn into_document_fields(self) -> Result<LegacyCheckpoint, NotesProtocolError> {
        match self {
            Self::Current(value) if value.schema_version == 2 => Ok(LegacyCheckpoint {
                schema_version: value.schema_version,
                target: value.target,
                text: value.text,
                revision: value.revision,
                pending_receipt: value.pending_receipt,
                retired_receipt: value.retired_receipt,
            }),
            Self::Legacy(value) if value.schema_version == 1 => Ok(value),
            _ => Err(NotesProtocolError::Version),
        }
    }
}

impl NotesDocument {
    /// Serialize the text, CAS revision and one retained receipt together.
    /// This does not attest persistence; the storage owner must sync the file
    /// and its containing directory before returning an effect/retirement ACK.
    pub fn checkpoint(&self) -> Result<Vec<u8>, NotesProtocolError> {
        let value = Checkpoint {
            format: CheckpointFormat::Notes,
            schema_version: 2,
            target: self.target.clone(),
            text: self.text.clone(),
            revision: self.revision,
            pending_receipt: self.last_applied.clone().into(),
            retired_receipt: self.last_retired.clone().into(),
        };
        let bytes = serde_json::to_vec(&value).map_err(|_| NotesProtocolError::Schema)?;
        if bytes.len() > MAX_CHECKPOINT_BYTES {
            return Err(NotesProtocolError::FrameBound);
        }
        Ok(bytes)
    }

    /// Recover only the exact document incarnation. A caller must not rebind
    /// the saved receipt to a fresh Session, task or application generation.
    /// Restoring these bytes conveys no permission to execute another effect.
    /// Legacy version-one bytes are read without rewriting their file. A later
    /// legitimate state change uses version two while retaining the exact old
    /// target and receipts; this is not an identity or authority migration.
    pub fn restore_checkpoint(
        raw: &[u8],
        target: &NotesTargetIdentity,
    ) -> Result<Self, NotesProtocolError> {
        if raw.is_empty() || raw.len() > MAX_CHECKPOINT_BYTES {
            return Err(NotesProtocolError::FrameBound);
        }
        let value: InputCheckpoint =
            serde_json::from_slice(raw).map_err(|_| NotesProtocolError::Schema)?;
        let value = value.into_document_fields()?;
        let pending_receipt = value.pending_receipt.into_option();
        let retired_receipt = value.retired_receipt.into_option();
        value.target.validate()?;
        if &value.target != target {
            return Err(NotesProtocolError::Target);
        }
        if value.text.len() > MAX_NOTES_TEXT_BYTES {
            return Err(NotesProtocolError::TextBound);
        }
        if value.revision == 0
            && (!value.text.is_empty() || pending_receipt.is_some() || retired_receipt.is_some())
        {
            return Err(NotesProtocolError::Receipt);
        }
        if let Some(receipt) = &pending_receipt {
            let raw = serde_json::to_vec(receipt).map_err(|_| NotesProtocolError::Receipt)?;
            NotesResponse::parse_exact(&raw)?;
            let NotesResult::Applied {
                revision,
                text_sha256,
                ..
            } = &receipt.result
            else {
                return Err(NotesProtocolError::Receipt);
            };
            if &receipt.target != target
                || *revision > value.revision
                || (*revision == value.revision
                    && *text_sha256 != sha256_hex(value.text.as_bytes()))
            {
                return Err(NotesProtocolError::Receipt);
            }
        }
        if let Some(retired) = &retired_receipt {
            let raw = serde_json::to_vec(retired).map_err(|_| NotesProtocolError::Receipt)?;
            NotesAcknowledge::parse_exact(&raw)?;
            if &retired.target != target {
                return Err(NotesProtocolError::Target);
            }
        }
        Ok(Self {
            target: value.target,
            text: value.text,
            revision: value.revision,
            last_applied: pending_receipt,
            last_retired: retired_receipt,
        })
    }
}

#[cfg(test)]
#[path = "notes_checkpoint_tests.rs"]
mod tests;
