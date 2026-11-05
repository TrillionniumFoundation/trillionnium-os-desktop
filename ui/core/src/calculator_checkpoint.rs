//! Bounded Calculator application state; never an authority or operation journal.
use super::*;

const MAX_CHECKPOINT_BYTES: usize = 16 * 1024;

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
#[derive(Serialize, Deserialize)]
enum CheckpointFormat {
    #[serde(rename = "trill.calculator.checkpoint")]
    Calculator,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Checkpoint {
    format: CheckpointFormat,
    schema_version: u16,
    target: CalculatorTargetIdentity,
    state: CalculatorValueState,
    revision: u64,
    // Explicit null is required. An absent field is not evidence of absence.
    pending_receipt: Nullable<CalculatorResponse>,
    retired_receipt: Nullable<CalculatorAcknowledge>,
}

impl CalculatorDocument {
    /// The storage owner must sync these complete bytes before returning an
    /// Applied response or receipt-retirement acknowledgement.
    pub fn checkpoint(&self) -> Result<Vec<u8>, CalculatorProtocolError> {
        let bytes = serde_json::to_vec(&Checkpoint {
            format: CheckpointFormat::Calculator,
            schema_version: 1,
            target: self.target.clone(),
            state: self.state.clone(),
            revision: self.revision,
            pending_receipt: self.pending.clone().into(),
            retired_receipt: self.retired.clone().into(),
        })
        .map_err(|_| CalculatorProtocolError::Schema)?;
        if bytes.len() > MAX_CHECKPOINT_BYTES {
            return Err(CalculatorProtocolError::FrameBound);
        }
        Ok(bytes)
    }

    /// Restore the exact old target. These bytes never authorize another
    /// effect, create an operation, or rebind a receipt to a successor.
    pub fn restore_checkpoint(
        raw: &[u8],
        target: &CalculatorTargetIdentity,
    ) -> Result<Self, CalculatorProtocolError> {
        let saved: Checkpoint = parse(raw, MAX_CHECKPOINT_BYTES)?;
        version(saved.schema_version)?;
        saved.target.validate()?;
        if &saved.target != target {
            return Err(CalculatorProtocolError::Target);
        }
        saved.state.validate()?;
        let pending = saved.pending_receipt.into_option();
        let retired = saved.retired_receipt.into_option();
        if saved.revision == 0
            && (saved.state != CalculatorValueState::default()
                || pending.is_some()
                || retired.is_some())
        {
            return Err(CalculatorProtocolError::Receipt);
        }
        if let Some(receipt) = &pending {
            let raw = serde_json::to_vec(receipt).map_err(|_| CalculatorProtocolError::Receipt)?;
            CalculatorResponse::parse_exact(&raw)?;
            let CalculatorResult::Applied {
                revision, state, ..
            } = &receipt.result
            else {
                return Err(CalculatorProtocolError::Receipt);
            };
            if &receipt.target != target
                || *revision > saved.revision
                || (*revision == saved.revision && state != &saved.state)
                || retired
                    .as_ref()
                    .is_some_and(|old| old.operation_id == receipt.operation_id)
            {
                return Err(CalculatorProtocolError::Receipt);
            }
        }
        if let Some(receipt) = &retired {
            version(receipt.schema_version)?;
            receipt.target.validate()?;
            operation_digest(&receipt.operation_id, &receipt.payload_sha256)?;
            if &receipt.target != target || !lower_hex(&receipt.receipt_sha256, 64) {
                return Err(CalculatorProtocolError::Receipt);
            }
        }
        Ok(Self {
            target: saved.target,
            state: saved.state,
            revision: saved.revision,
            pending,
            retired,
        })
    }
}

#[cfg(test)]
#[path = "calculator_checkpoint_tests.rs"]
mod tests;
