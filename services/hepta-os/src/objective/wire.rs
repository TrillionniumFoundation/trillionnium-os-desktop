//! Exact private subset of the fixed original protocol; no signing or generic
//! method construction. Source declarations are listed in OBJECTIVE_TRANSPORT.md.

use super::{
    AdmissionDisposition, AdmissionReceipt, ConflictReceipt, EnvelopeError, ObjectiveIdentity,
    PrePublicationRefusal, ProvidedObjective, SubmissionIssue, SubmissionStatus,
};
use crate::wire::{valid_identity, OVERLOAD_FRAME};
use crate::{EndpointConfig, CONTROL_SCHEMA_VERSION, MAX_FRAME_BYTES};
use serde::{Deserialize, Serialize};
use serde_json::value::RawValue;

const MAX_SOURCE_BYTES: usize = 32 * 1024;
const MAX_BODY_BYTES: usize = 48 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Ingress {
    issuer_id: String,
    key_epoch: u64,
    message_id: String,
    sequence: u64,
    expires_at_ms: u64,
    signature_hex: String,
    body: Body,
}

// Field order matches original AuthBusObjectiveBody: serializing this only
// checks the original canonical body bound. The outgoing body uses raw bytes.
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Body {
    spawn_generation: u64,
    run_id: String,
    objective_revision: u64,
    source_envelope_json: String,
    runtime_body_digest: String,
    preference_state_digest: String,
    model_tuple_digest: String,
    prompt_registry_digest: String,
    artifact_set_digest: String,
    authority_epoch: u64,
}

pub(super) fn validate_envelope(raw: &str) -> Result<ObjectiveIdentity, EnvelopeError> {
    if raw.len() as u64 > MAX_FRAME_BYTES {
        return Err(EnvelopeError::FrameBound);
    }
    if !raw.starts_with('{') || !raw.ends_with('}') || raw.contains(['\r', '\n']) {
        return Err(EnvelopeError::FramingProfile);
    }
    let ingress: Ingress =
        serde_json::from_str(raw).map_err(|_| EnvelopeError::MalformedEnvelope)?;
    let body = &ingress.body;
    if [&ingress.issuer_id, &ingress.message_id, &body.run_id]
        .iter()
        .any(|value| !valid_identity(value))
    {
        return Err(EnvelopeError::InvalidIdentity);
    }
    if [
        ingress.key_epoch,
        ingress.sequence,
        ingress.expires_at_ms,
        body.spawn_generation,
        body.objective_revision,
        body.authority_epoch,
    ]
    .contains(&0)
    {
        return Err(EnvelopeError::InvalidNumber);
    }
    // Structural width/alphabet only: 128 ASCII hex characters = 64 bytes.
    // The original issuer/trust owner must authenticate the actual signature.
    if ingress.signature_hex.len() != 128
        || !ingress
            .signature_hex
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
    {
        return Err(EnvelopeError::InvalidSignatureShape);
    }
    if body.source_envelope_json.is_empty() || body.source_envelope_json.len() > MAX_SOURCE_BYTES {
        return Err(EnvelopeError::SourceBound);
    }
    if [
        &body.runtime_body_digest,
        &body.preference_state_digest,
        &body.model_tuple_digest,
        &body.prompt_registry_digest,
        &body.artifact_set_digest,
    ]
    .iter()
    .any(|value| !valid_digest(value))
    {
        return Err(EnvelopeError::InvalidDigest);
    }
    if serde_json::to_vec(body)
        .map_err(|_| EnvelopeError::MalformedEnvelope)?
        .len()
        > MAX_BODY_BYTES
    {
        return Err(EnvelopeError::BodyBound);
    }
    let body = ingress.body;
    Ok(ObjectiveIdentity {
        issuer_id: ingress.issuer_id,
        key_epoch: ingress.key_epoch,
        message_id: ingress.message_id,
        sequence: ingress.sequence,
        expires_at_ms: ingress.expires_at_ms,
        spawn_generation: body.spawn_generation,
        run_id: body.run_id,
        objective_revision: body.objective_revision,
        authority_epoch: body.authority_epoch,
        runtime_body_digest: body.runtime_body_digest,
        preference_state_digest: body.preference_state_digest,
        model_tuple_digest: body.model_tuple_digest,
        prompt_registry_digest: body.prompt_registry_digest,
        artifact_set_digest: body.artifact_set_digest,
    })
}

fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
        && value.bytes().any(|byte| byte != b'0')
}

#[derive(Serialize)]
struct Request<'a> {
    schema_version: u32,
    request_id: u64,
    spawn_generation: u64,
    method: Method<'a>,
}

#[derive(Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum Method<'a> {
    ObjectiveStart { request: &'a RawValue },
}

pub(super) fn request_frame(
    objective: &ProvidedObjective,
    request_id: u64,
    config: &EndpointConfig,
) -> Result<Vec<u8>, SubmissionIssue> {
    let mut frame = serde_json::to_vec(&Request {
        schema_version: CONTROL_SCHEMA_VERSION,
        request_id,
        spawn_generation: config.spawn_generation,
        method: Method::ObjectiveStart {
            request: &objective.raw,
        },
    })
    .map_err(|_| SubmissionIssue::FrameBound)?;
    frame.push(b'\n');
    if frame.len() as u64 > MAX_FRAME_BYTES {
        return Err(SubmissionIssue::FrameBound);
    }
    Ok(frame)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Response {
    schema_version: u32,
    request_id: u64,
    agent_id: String,
    spawn_generation: u64,
    current_generation: u64,
    payload: Payload,
}

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
enum Payload {
    ObjectiveRun(Admission),
    ObjectiveConflict {
        run_id: String,
        conflict_digest: String,
    },
    Error {
        code: String,
        message: String,
    },
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Admission {
    run_id: String,
    objective_digest: String,
    hard_constraint_digest: String,
    publication_digest: String,
    chain_digest: String,
    disposition: String,
    idempotent: bool,
}

pub(super) fn classify_response(
    frame: &[u8],
    config: &EndpointConfig,
    request_id: u64,
    run_id: &str,
) -> Result<SubmissionStatus, SubmissionIssue> {
    if frame == OVERLOAD_FRAME {
        // This frame has no source/request identity. It cannot establish a
        // negative publication result; its retry_after_ms never schedules work.
        return Err(SubmissionIssue::Overloaded);
    }
    let response: Response =
        serde_json::from_slice(frame).map_err(|_| SubmissionIssue::ProtocolMismatch)?;
    if response.schema_version != CONTROL_SCHEMA_VERSION
        || response.request_id != request_id
        || response.agent_id != config.expected_agent_id
        || response.spawn_generation != config.spawn_generation
        || !matches!(
            response
                .current_generation
                .checked_sub(config.spawn_generation),
            Some(0..=2)
        )
    {
        return Err(SubmissionIssue::ProtocolMismatch);
    }
    let response_generation = response.current_generation;
    match response.payload {
        Payload::ObjectiveRun(receipt) => {
            if receipt.run_id != run_id
                || [
                    &receipt.objective_digest,
                    &receipt.hard_constraint_digest,
                    &receipt.publication_digest,
                    &receipt.chain_digest,
                ]
                .iter()
                .any(|value| !valid_digest(value))
            {
                return Err(SubmissionIssue::ProtocolMismatch);
            }
            let disposition = match receipt.disposition.as_str() {
                "compiled" => AdmissionDisposition::Compiled,
                "explicit_abstain" => AdmissionDisposition::ExplicitAbstain,
                "canonical_ready" => AdmissionDisposition::CanonicalReady,
                "canonical_abstained" => AdmissionDisposition::CanonicalAbstained,
                "canonical_slow_path" => AdmissionDisposition::CanonicalSlowPath,
                _ => return Err(SubmissionIssue::ProtocolMismatch),
            };
            Ok(SubmissionStatus::Admitted(AdmissionReceipt {
                run_id: receipt.run_id,
                objective_digest: receipt.objective_digest,
                hard_constraint_digest: receipt.hard_constraint_digest,
                publication_digest: receipt.publication_digest,
                chain_digest: receipt.chain_digest,
                disposition,
                idempotent: receipt.idempotent,
                response_generation,
            }))
        }
        Payload::ObjectiveConflict {
            run_id: response_run,
            conflict_digest,
        } => {
            if response_run != run_id || !valid_digest(&conflict_digest) {
                return Err(SubmissionIssue::ProtocolMismatch);
            }
            Ok(SubmissionStatus::Conflict(ConflictReceipt {
                run_id: response_run,
                conflict_digest,
                response_generation,
            }))
        }
        Payload::Error { code, message } => {
            if !valid_identity(&code) || message.chars().count() > 512 {
                return Err(SubmissionIssue::ProtocolMismatch);
            }
            // Source-specific pre-dispatch paths only. Generic request_rejected
            // also wraps failures AFTER the original durable journal publish.
            // Never search the human message for apparent non-admission clues.
            let reason = match (code.as_str(), message.as_str()) {
                ("objective_unavailable", "no owner objective profile is configured") => {
                    PrePublicationRefusal::ObjectiveUnavailable
                }
                ("unsupported_schema", "unsupported agentd control schema")
                    if response_generation == config.spawn_generation =>
                {
                    PrePublicationRefusal::UnsupportedSchema
                }
                ("request_rejected", _) => return Err(SubmissionIssue::OwnerRequestRejected),
                _ => return Err(SubmissionIssue::OwnerError),
            };
            Ok(SubmissionStatus::RefusedBeforePublication {
                reason,
                response_generation,
            })
        }
    }
}
