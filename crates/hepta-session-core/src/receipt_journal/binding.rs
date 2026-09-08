//! Immutable admission identity, shared by append, recovery and envelope export.
use super::*;

impl ReceiptProgress {
    /// This state is prepared before I/O; publish it only after durable append.
    /// Journal timestamps remain observational: generic callers may use
    /// different clocks. Envelope export separately checks terminal duration.
    pub(super) fn advance(
        previous: Option<&Self>,
        event: &ReceiptEvent,
    ) -> Result<Self, JournalError> {
        event.validate()?;
        validate_transition(
            &event.receipt_id,
            previous.map(|item| item.last_state),
            event.lifecycle,
        )?;
        let admission_sha256 = admission_digest(event)?;
        if let Some(previous) = previous {
            if previous.effect_class != event.effect_class {
                return Err(JournalError::InvalidInput(
                    "effect class cannot change within one receipt lifecycle".into(),
                ));
            }
            if previous.admission_sha256 != admission_sha256 {
                return Err(JournalError::InvalidInput(
                    "receipt admission identity, request digest or privacy changed".into(),
                ));
            }
        }
        Ok(Self {
            last_state: event.lifecycle,
            effect_class: event.effect_class,
            admission_sha256,
        })
    }
}

/// A compact, domain-separated commitment avoids duplicating admission strings
/// and never retains optional detail or outcome content in the progress map.
/// This is an internal equality key, not a new disk format or authentication
/// signature. The authoritative bytes remain in the original v1 records.
fn admission_digest(event: &ReceiptEvent) -> Result<Digest, JournalError> {
    let mut bytes = b"hepta.receipt.admission-binding.v1\0".to_vec();
    for value in [
        &event.receipt_id,
        &event.plan_revision,
        &event.image_id,
        &event.servo_commit,
        &event.browserd_version,
        &event.session_id,
        &event.operation,
    ] {
        put_string(&mut bytes, value)?;
    }
    for value in [
        event.session_generation,
        event.document_generation,
        event.semantic_snapshot_revision,
        event.mutation_epoch,
    ] {
        put_u64(&mut bytes, value);
    }
    bytes.extend_from_slice(&[
        event.source as u8,
        event.effect_class as u8,
        event.privacy_class as u8,
    ]);
    bytes.extend_from_slice(&event.request_sha256);
    Ok(sha256(&bytes))
}
