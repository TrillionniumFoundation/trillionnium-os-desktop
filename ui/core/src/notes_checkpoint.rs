//! Bounded application data, not an authorization or operation journal.

use super::*;
use crate::notes_recovery::NotesAcknowledge;

const MAX_CHECKPOINT_BYTES: usize = 16 * 1024;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Checkpoint {
    schema_version: u16,
    target: NotesTargetIdentity,
    text: String,
    revision: u64,
    pending_receipt: Option<NotesResponse>,
    retired_receipt: Option<NotesAcknowledge>,
}

impl NotesDocument {
    /// Serialize the text, CAS revision and one retained receipt together.
    /// This does not attest persistence; the storage owner must sync the file
    /// and its containing directory before returning an effect/retirement ACK.
    pub fn checkpoint(&self) -> Result<Vec<u8>, NotesProtocolError> {
        let value = Checkpoint {
            schema_version: 1,
            target: self.target.clone(),
            text: self.text.clone(),
            revision: self.revision,
            pending_receipt: self.last_applied.clone(),
            retired_receipt: self.last_retired.clone(),
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
    pub fn restore_checkpoint(
        raw: &[u8],
        target: &NotesTargetIdentity,
    ) -> Result<Self, NotesProtocolError> {
        if raw.is_empty() || raw.len() > MAX_CHECKPOINT_BYTES {
            return Err(NotesProtocolError::FrameBound);
        }
        let value: Checkpoint =
            serde_json::from_slice(raw).map_err(|_| NotesProtocolError::Schema)?;
        if value.schema_version != 1 {
            return Err(NotesProtocolError::Version);
        }
        value.target.validate()?;
        if &value.target != target {
            return Err(NotesProtocolError::Target);
        }
        if value.text.len() > MAX_NOTES_TEXT_BYTES {
            return Err(NotesProtocolError::TextBound);
        }
        if value.revision == 0
            && (!value.text.is_empty()
                || value.pending_receipt.is_some()
                || value.retired_receipt.is_some())
        {
            return Err(NotesProtocolError::Receipt);
        }
        if let Some(receipt) = &value.pending_receipt {
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
        if let Some(retired) = &value.retired_receipt {
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
            last_applied: value.pending_receipt,
            last_retired: value.retired_receipt,
        })
    }
}
