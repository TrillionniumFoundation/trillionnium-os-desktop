//! Versioned metadata observations produced ONLY from original immutable attempts.
//! These are not raw wire replies, signature checks, run completion or effect ACKs.

use codex_hepta_memory::{
    ObjectiveSenderObservation, ObjectiveSenderObservationKind, ObjectiveSenderRequest,
    ObjectiveSenderSnapshot,
};
use hepta_os_observer::objective::history::{
    HistoricalPublication, HistoryAnchor, HistoryAttempt, HistoryStatus, MAX_HISTORY_RECORDS,
    PublicationOutcome,
};
use hepta_os_observer::objective::{
    AdmissionDisposition, ObjectiveIdentity, PrePublicationRefusal, SubmissionAttempt,
    SubmissionIdentity, SubmissionStatus,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use trill_session::objective_submission::RequestOwnerIssue;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Identity {
    pub(crate) request_id: u64,
    pub(crate) agent_id: String,
    pub(crate) spawn_generation: u64,
    pub(crate) expected_peer_uid: u32,
    pub(crate) expected_peer_pid: u32,
    pub(crate) objective: Objective,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Objective {
    pub(crate) issuer_id: String,
    pub(crate) key_epoch: u64,
    pub(crate) message_id: String,
    pub(crate) sequence: u64,
    pub(crate) expires_at_ms: u64,
    pub(crate) spawn_generation: u64,
    pub(crate) run_id: String,
    pub(crate) objective_revision: u64,
    pub(crate) authority_epoch: u64,
    pub(crate) runtime_body_digest: String,
    pub(crate) preference_state_digest: String,
    pub(crate) model_tuple_digest: String,
    pub(crate) prompt_registry_digest: String,
    pub(crate) artifact_set_digest: String,
}

impl From<&SubmissionIdentity> for Identity {
    fn from(i: &SubmissionIdentity) -> Self {
        let o = &i.objective;
        Self {
            request_id: i.request_id,
            agent_id: i.agent_id.clone(),
            spawn_generation: i.spawn_generation,
            expected_peer_uid: i.expected_peer_uid,
            expected_peer_pid: i.expected_peer_pid,
            objective: Objective {
                issuer_id: o.issuer_id.clone(),
                key_epoch: o.key_epoch,
                message_id: o.message_id.clone(),
                sequence: o.sequence,
                expires_at_ms: o.expires_at_ms,
                spawn_generation: o.spawn_generation,
                run_id: o.run_id.clone(),
                objective_revision: o.objective_revision,
                authority_epoch: o.authority_epoch,
                runtime_body_digest: o.runtime_body_digest.clone(),
                preference_state_digest: o.preference_state_digest.clone(),
                model_tuple_digest: o.model_tuple_digest.clone(),
                prompt_registry_digest: o.prompt_registry_digest.clone(),
                artifact_set_digest: o.artifact_set_digest.clone(),
            },
        }
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct HistoryRecord {
    pub(crate) schema: u32,
    pub(crate) original_sha256: String,
    pub(crate) query: Identity,
    pub(crate) requested_anchor: Option<HistoryAnchor>,
    pub(crate) bytes_written: usize,
    pub(crate) request_frame_bytes: Option<usize>,
    pub(crate) status: HistoryRecordStatus,
}

#[derive(Deserialize, Serialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub(crate) enum HistoryRecordStatus {
    HistoricalPublication {
        publication: Box<HistoricalPublication>,
        response_generation: u64,
    },
    Unknown {
        issue: String,
    },
    QueryNotSent {
        issue: String,
    },
}

pub(crate) fn require_submission_identity(
    request: &ObjectiveSenderRequest,
    identity: &SubmissionIdentity,
) -> Result<(), RequestOwnerIssue> {
    let origin = request.origin();
    if identity.agent_id != origin.agent_id.as_str()
        || identity.spawn_generation != origin.spawn_generation
        || identity.request_id != origin.request_id
        || identity.expected_peer_uid != origin.expected_peer_uid
        || identity.expected_peer_pid != origin.expected_peer_pid
        || !objective_matches(request, &identity.objective)
    {
        return Err(RequestOwnerIssue::IdentityMismatch);
    }
    Ok(())
}

pub(crate) fn objective_matches(request: &ObjectiveSenderRequest, o: &ObjectiveIdentity) -> bool {
    let expected = request.identity();
    o.issuer_id == expected.issuer_id
        && o.key_epoch == expected.key_epoch
        && o.message_id == expected.message_id
        && o.sequence == expected.sequence
        && o.expires_at_ms == expected.expires_at_ms
        && o.spawn_generation == expected.body_spawn_generation
        && o.run_id == expected.run_id
        && o.objective_revision == expected.objective_revision
        && o.authority_epoch == expected.authority_epoch
        && o.runtime_body_digest == expected.runtime_body_digest
        && o.preference_state_digest == expected.preference_state_digest
        && o.model_tuple_digest == expected.model_tuple_digest
        && o.prompt_registry_digest == expected.prompt_registry_digest
        && o.artifact_set_digest == expected.artifact_set_digest
}

pub(crate) fn submission(
    request: &ObjectiveSenderRequest,
    attempt: &SubmissionAttempt,
) -> Result<ObjectiveSenderObservation, RequestOwnerIssue> {
    require_submission_identity(request, attempt.identity())?;
    if !attempt.matches_original_json(request.exact_original()) {
        return Err(RequestOwnerIssue::IdentityMismatch);
    }
    let status: Value = match attempt.status() {
        SubmissionStatus::NotSent(issue) => json!({"type":"not_sent", "issue":issue.code()}),
        SubmissionStatus::SubmitUnknown(issue) => {
            json!({"type":"submit_unknown", "issue":issue.code()})
        }
        SubmissionStatus::RefusedBeforePublication {
            reason,
            response_generation,
        } => json!({
            "type":"refused_before_publication",
            "reason":match reason {
                PrePublicationRefusal::ObjectiveUnavailable => "objective_unavailable",
                PrePublicationRefusal::UnsupportedSchema => "unsupported_schema",
            },
            "response_generation":response_generation,
        }),
        SubmissionStatus::Admitted(receipt) => json!({
            "type":"admitted", "run_id":receipt.run_id,
            "objective_digest":receipt.objective_digest,
            "hard_constraint_digest":receipt.hard_constraint_digest,
            "publication_digest":receipt.publication_digest,
            "chain_digest":receipt.chain_digest,
            "disposition":match receipt.disposition {
                AdmissionDisposition::Compiled => "compiled",
                AdmissionDisposition::ExplicitAbstain => "explicit_abstain",
                AdmissionDisposition::CanonicalReady => "canonical_ready",
                AdmissionDisposition::CanonicalAbstained => "canonical_abstained",
                AdmissionDisposition::CanonicalSlowPath => "canonical_slow_path",
            },
            "idempotent":receipt.idempotent,
            "response_generation":receipt.response_generation,
        }),
        SubmissionStatus::Conflict(receipt) => json!({
            "type":"conflict", "run_id":receipt.run_id,
            "conflict_digest":receipt.conflict_digest,
            "response_generation":receipt.response_generation,
        }),
    };
    let json = serde_json::to_string(&json!({
        "schema":1,
        "original_sha256":request.identity().original_sha256.as_str(),
        "submission":Identity::from(attempt.identity()),
        "bytes_written":attempt.bytes_written(),
        "request_frame_bytes":attempt.request_frame_bytes(),
        "status":status,
    }))
    .map_err(|_| RequestOwnerIssue::Refused)?;
    ObjectiveSenderObservation::from_original(ObjectiveSenderObservationKind::Submission, json)
        .map_err(|_| RequestOwnerIssue::Refused)
}

pub(crate) fn history(
    request: &ObjectiveSenderRequest,
    attempt: &HistoryAttempt,
) -> Result<ObjectiveSenderObservation, RequestOwnerIssue> {
    if attempt.identity().agent_id != request.origin().agent_id.as_str()
        || !objective_matches(request, &attempt.identity().objective)
        || !attempt.matches_original_json(request.exact_original())
    {
        return Err(RequestOwnerIssue::IdentityMismatch);
    }
    let status = match attempt.status() {
        HistoryStatus::HistoricalPublication {
            publication,
            response_generation,
        } => {
            require_publication(request.identity(), publication)?;
            HistoryRecordStatus::HistoricalPublication {
                publication: publication.clone(),
                response_generation: *response_generation,
            }
        }
        HistoryStatus::Unknown(issue) => HistoryRecordStatus::Unknown {
            issue: issue.code().to_owned(),
        },
        HistoryStatus::QueryNotSent(issue) => HistoryRecordStatus::QueryNotSent {
            issue: issue.code().to_owned(),
        },
    };
    let record = HistoryRecord {
        schema: 1,
        original_sha256: request.identity().original_sha256.as_str().to_owned(),
        query: Identity::from(attempt.identity()),
        requested_anchor: attempt.anchor().cloned(),
        bytes_written: attempt.bytes_written(),
        request_frame_bytes: attempt.request_frame_bytes(),
        status,
    };
    let json = serde_json::to_string(&record).map_err(|_| RequestOwnerIssue::Refused)?;
    ObjectiveSenderObservation::from_original(ObjectiveSenderObservationKind::History, json)
        .map_err(|_| RequestOwnerIssue::Refused)
}

pub(crate) fn retained_anchor(
    request: &ObjectiveSenderRequest,
    snapshot: &ObjectiveSenderSnapshot,
) -> Result<Option<HistoryAnchor>, RequestOwnerIssue> {
    let recovered = crate::recovery::project(request, snapshot)?;
    if let Some(HistoryStatus::HistoricalPublication { publication, .. }) =
        recovered.first_publication
    {
        return HistoryAnchor::new(publication.publication_sequence, publication.chain_digest)
            .map(Some)
            .map_err(|_| RequestOwnerIssue::Refused);
    }
    // An admission response carries no sequence and never becomes an anchor.
    Ok(None)
}

pub(crate) fn require_publication(
    e: &codex_hepta_memory::ObjectiveSenderIdentity,
    p: &HistoricalPublication,
) -> Result<(), RequestOwnerIssue> {
    if p.run_id != e.run_id
        || p.original_spawn_generation != e.body_spawn_generation
        || p.issuer_id != e.issuer_id
        || p.key_epoch != e.key_epoch
        || p.message_id != e.message_id
        || p.message_sequence != e.sequence
        || p.expires_at_ms != e.expires_at_ms
        || p.signed_body_digest != e.signed_body_sha256.as_str()
        || !(1..=MAX_HISTORY_RECORDS).contains(&p.publication_sequence)
        || [&p.profile_digest, &p.publication_digest, &p.chain_digest]
            .iter()
            .any(|d| !digest_shape(d))
    {
        return Err(RequestOwnerIssue::IdentityMismatch);
    }
    let valid = match &p.outcome {
        PublicationOutcome::Compiled {
            objective_digest,
            hard_constraint_digest,
        }
        | PublicationOutcome::ExplicitAbstain {
            objective_digest,
            hard_constraint_digest,
        } => digest_shape(objective_digest) && digest_shape(hard_constraint_digest),
        PublicationOutcome::Conflict { conflict_digest } => digest_shape(conflict_digest),
    };
    if !valid {
        return Err(RequestOwnerIssue::IdentityMismatch);
    }
    Ok(())
}

pub(crate) fn digest_shape(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        && value.bytes().any(|byte| byte != b'0')
}

impl Identity {
    pub(crate) fn transport(&self) -> SubmissionIdentity {
        let o = &self.objective;
        SubmissionIdentity {
            request_id: self.request_id,
            agent_id: self.agent_id.clone(),
            spawn_generation: self.spawn_generation,
            expected_peer_uid: self.expected_peer_uid,
            expected_peer_pid: self.expected_peer_pid,
            objective: ObjectiveIdentity {
                issuer_id: o.issuer_id.clone(),
                key_epoch: o.key_epoch,
                message_id: o.message_id.clone(),
                sequence: o.sequence,
                expires_at_ms: o.expires_at_ms,
                spawn_generation: o.spawn_generation,
                run_id: o.run_id.clone(),
                objective_revision: o.objective_revision,
                authority_epoch: o.authority_epoch,
                runtime_body_digest: o.runtime_body_digest.clone(),
                preference_state_digest: o.preference_state_digest.clone(),
                model_tuple_digest: o.model_tuple_digest.clone(),
                prompt_registry_digest: o.prompt_registry_digest.clone(),
                artifact_set_digest: o.artifact_set_digest.clone(),
            },
        }
    }
}
