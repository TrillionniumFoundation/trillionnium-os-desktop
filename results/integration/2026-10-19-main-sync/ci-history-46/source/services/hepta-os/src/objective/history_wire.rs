//! Exact subset of the separately pinned original owner's history extension.

use super::{
    valid_digest, HistoricalPublication, HistoryAnchor, HistoryIssue, HistoryStatus,
    OwnerUnknownReason, PublicationOutcome, MAX_HISTORY_RECORDS,
};
use crate::objective::{ProvidedObjective, SubmissionIdentity, SubmissionIssue};
use crate::wire::OVERLOAD_FRAME;
use crate::{CONTROL_SCHEMA_VERSION, MAX_FRAME_BYTES};
use serde::{Deserialize, Serialize};
use serde_json::value::RawValue;

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
    ObjectiveAdmission { query: Query<'a> },
}

#[derive(Serialize)]
struct Query<'a> {
    request: &'a RawValue,
    anchor: Option<&'a HistoryAnchor>,
}

pub(super) fn request_frame(
    objective: &ProvidedObjective,
    anchor: Option<&HistoryAnchor>,
    identity: &SubmissionIdentity,
) -> Result<Vec<u8>, SubmissionIssue> {
    let mut frame = serde_json::to_vec(&Request {
        schema_version: CONTROL_SCHEMA_VERSION,
        request_id: identity.request_id,
        spawn_generation: identity.spawn_generation,
        method: Method::ObjectiveAdmission {
            query: Query {
                request: &objective.raw,
                anchor,
            },
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
    ObjectiveAdmission { outcome: Outcome },
    Error { code: String, message: String },
}

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
enum Outcome {
    Published {
        publication: Box<HistoricalPublication>,
    },
    Unknown {
        reason: OwnerUnknownReason,
    },
}

pub(super) fn classify_response(
    frame: &[u8],
    identity: &SubmissionIdentity,
    anchor: Option<&HistoryAnchor>,
) -> Result<HistoryStatus, SubmissionIssue> {
    if frame == OVERLOAD_FRAME {
        return Err(SubmissionIssue::Overloaded);
    }
    let response: Response =
        serde_json::from_slice(frame).map_err(|_| SubmissionIssue::ProtocolMismatch)?;
    let spawn = identity.spawn_generation;
    if response.schema_version != CONTROL_SCHEMA_VERSION
        || response.request_id != identity.request_id
        || response.agent_id != identity.agent_id
        || response.spawn_generation != spawn
        || !(spawn..=spawn.saturating_add(2)).contains(&response.current_generation)
    {
        return Err(SubmissionIssue::ProtocolMismatch);
    }
    match response.payload {
        Payload::Error { code, message } => {
            if !crate::wire::valid_identity(&code) || message.len() > 512 {
                return Err(SubmissionIssue::ProtocolMismatch);
            }
            Err(if code == "request_rejected" {
                SubmissionIssue::OwnerRequestRejected
            } else {
                SubmissionIssue::OwnerError
            })
        }
        Payload::ObjectiveAdmission {
            outcome: Outcome::Unknown { reason },
        } => Ok(HistoryStatus::Unknown(HistoryIssue::Owner(reason))),
        Payload::ObjectiveAdmission {
            outcome: Outcome::Published { publication },
        } => {
            let expected = &identity.objective;
            if publication.run_id != expected.run_id
                || publication.original_spawn_generation != expected.spawn_generation
                || publication.issuer_id != expected.issuer_id
                || publication.key_epoch != expected.key_epoch
                || publication.message_id != expected.message_id
                || publication.message_sequence != expected.sequence
                || publication.expires_at_ms != expected.expires_at_ms
                || !(1..=MAX_HISTORY_RECORDS).contains(&publication.publication_sequence)
                || [
                    &publication.signed_body_digest,
                    &publication.profile_digest,
                    &publication.publication_digest,
                    &publication.chain_digest,
                ]
                .iter()
                .any(|v| !valid_digest(v))
            {
                return Err(SubmissionIssue::ProtocolMismatch);
            }
            let valid_outcome = match &publication.outcome {
                PublicationOutcome::Compiled {
                    objective_digest,
                    hard_constraint_digest,
                }
                | PublicationOutcome::ExplicitAbstain {
                    objective_digest,
                    hard_constraint_digest,
                } => valid_digest(objective_digest) && valid_digest(hard_constraint_digest),
                PublicationOutcome::Conflict { conflict_digest } => valid_digest(conflict_digest),
            };
            if !valid_outcome
                || anchor.is_some_and(|a| {
                    publication.publication_sequence > a.sequence()
                        || (publication.publication_sequence == a.sequence()
                            && publication.chain_digest != a.chain_digest())
                })
            {
                return Err(SubmissionIssue::ProtocolMismatch);
            }
            Ok(HistoryStatus::HistoricalPublication {
                publication,
                response_generation: response.current_generation,
            })
        }
    }
}
