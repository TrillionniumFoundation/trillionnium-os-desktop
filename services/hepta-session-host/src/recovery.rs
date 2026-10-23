//! Strict projections of observations already retained by the original owner.
//! Retained metadata does not recreate a Session send permission.

use crate::receipt::{self, HistoryRecord, HistoryRecordStatus, Identity};
use codex_hepta_memory::{
    ObjectiveSenderObservationKind, ObjectiveSenderRequest, ObjectiveSenderSnapshot,
};
use hepta_os_observer::objective::history::{HistoryIssue, HistoryStatus, OwnerUnknownReason};
use hepta_os_observer::objective::{
    AdmissionDisposition, AdmissionReceipt, ConflictReceipt, PrePublicationRefusal,
    SubmissionIssue, SubmissionStatus,
};
use serde::Deserialize;
use trill_session::objective_submission::{ObjectiveSubmissionView, RequestOwnerIssue};

#[derive(Default)]
pub(crate) struct RecoveredObservations {
    pub(crate) submission: Option<SubmissionStatus>,
    pub(crate) latest_history: Option<HistoryStatus>,
    pub(crate) first_publication: Option<HistoryStatus>,
    locally_cancelled: bool,
}

impl RecoveredObservations {
    pub(crate) fn apply(&self, view: &mut ObjectiveSubmissionView) {
        if view.observed_submission.is_none() && self.submission.is_some() {
            view.observed_submission = self.submission.clone();
            view.submission_recorded = true;
        }
        if view.last_history.is_none() && self.latest_history.is_some() {
            view.last_history = self.latest_history.clone();
            view.history_recorded = true;
        }
        if self.first_publication.is_some() {
            // Preserve the original first observation, including its original
            // response generation, across later queries after recovery.
            view.first_observed_publication = self.first_publication.clone();
        }
        view.local_cancellation_recorded |= self.locally_cancelled;
        // The local recovered phase intentionally remains unknown/no-send.
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SubmissionRecord {
    schema: u32,
    original_sha256: String,
    submission: Identity,
    bytes_written: usize,
    request_frame_bytes: Option<usize>,
    status: SubmissionRecordStatus,
}

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
enum SubmissionRecordStatus {
    NotSent {
        issue: String,
    },
    SubmitUnknown {
        issue: String,
    },
    RefusedBeforePublication {
        reason: Refusal,
        response_generation: u64,
    },
    Admitted {
        run_id: String,
        objective_digest: String,
        hard_constraint_digest: String,
        publication_digest: String,
        chain_digest: String,
        disposition: Disposition,
        idempotent: bool,
        response_generation: u64,
    },
    Conflict {
        run_id: String,
        conflict_digest: String,
        response_generation: u64,
    },
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum Refusal {
    ObjectiveUnavailable,
    UnsupportedSchema,
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum Disposition {
    Compiled,
    ExplicitAbstain,
    CanonicalReady,
    CanonicalAbstained,
    CanonicalSlowPath,
}

pub(crate) fn project(
    request: &ObjectiveSenderRequest,
    snapshot: &ObjectiveSenderSnapshot,
) -> Result<RecoveredObservations, RequestOwnerIssue> {
    let mut out = RecoveredObservations {
        locally_cancelled: snapshot.locally_cancelled,
        ..Default::default()
    };
    for observation in &snapshot.observations {
        match observation.kind() {
            ObjectiveSenderObservationKind::Submission => {
                if out.submission.is_some() {
                    return Err(RequestOwnerIssue::Refused);
                }
                let r: SubmissionRecord = serde_json::from_slice(observation.exact_original())
                    .map_err(|_| RequestOwnerIssue::Refused)?;
                receipt::require_submission_identity(request, &r.submission.transport())?;
                if r.schema != 1 || r.original_sha256 != request.identity().original_sha256.as_str()
                {
                    return Err(RequestOwnerIssue::IdentityMismatch);
                }
                io_shape(r.bytes_written, r.request_frame_bytes)?;
                out.submission = Some(submission_status(request, r)?);
            }
            ObjectiveSenderObservationKind::History => {
                let r: HistoryRecord = serde_json::from_slice(observation.exact_original())
                    .map_err(|_| RequestOwnerIssue::Refused)?;
                let query = r.query.transport();
                if r.schema != 1
                    || r.original_sha256 != request.identity().original_sha256.as_str()
                    || query.agent_id != request.origin().agent_id.as_str()
                    || !receipt::objective_matches(request, &query.objective)
                    || query.spawn_generation == 0
                    || query.request_id == 0
                    || query.expected_peer_pid == 0
                    || query.expected_peer_pid > i32::MAX as u32
                {
                    return Err(RequestOwnerIssue::IdentityMismatch);
                }
                io_shape(r.bytes_written, r.request_frame_bytes)?;
                let status = match r.status {
                    HistoryRecordStatus::HistoricalPublication {
                        publication,
                        response_generation,
                    } => {
                        receipt::require_publication(request.identity(), &publication)?;
                        response_shape(
                            query.spawn_generation,
                            response_generation,
                            r.bytes_written,
                            r.request_frame_bytes,
                        )?;
                        if let Some(anchor) = r.requested_anchor {
                            // Deserialization bypasses the constructor: recheck it.
                            let checked =
                                hepta_os_observer::objective::history::HistoryAnchor::new(
                                    anchor.sequence(),
                                    anchor.chain_digest().to_owned(),
                                )
                                .map_err(|_| RequestOwnerIssue::Refused)?;
                            if publication.publication_sequence > checked.sequence()
                                || (publication.publication_sequence == checked.sequence()
                                    && publication.chain_digest != checked.chain_digest())
                            {
                                return Err(RequestOwnerIssue::Refused);
                            }
                        }
                        if let Some(HistoryStatus::HistoricalPublication {
                            publication: previous,
                            ..
                        }) = &out.first_publication
                            && **previous != *publication
                        {
                            return Err(RequestOwnerIssue::Refused);
                        }
                        let status = HistoryStatus::HistoricalPublication {
                            publication,
                            response_generation,
                        };
                        if out.first_publication.is_none() {
                            out.first_publication = Some(status.clone());
                        }
                        status
                    }
                    HistoryRecordStatus::Unknown { issue } => {
                        if r.bytes_written == 0 {
                            return Err(RequestOwnerIssue::Refused);
                        }
                        HistoryStatus::Unknown(history_issue(&issue)?)
                    }
                    HistoryRecordStatus::QueryNotSent { issue } => {
                        if r.bytes_written != 0 {
                            return Err(RequestOwnerIssue::Refused);
                        }
                        HistoryStatus::QueryNotSent(submission_issue(&issue)?)
                    }
                };
                out.latest_history = Some(status);
            }
        }
    }
    if out.locally_cancelled && (out.submission.is_some() || out.latest_history.is_some()) {
        return Err(RequestOwnerIssue::Refused);
    }
    Ok(out)
}

fn submission_status(
    request: &ObjectiveSenderRequest,
    r: SubmissionRecord,
) -> Result<SubmissionStatus, RequestOwnerIssue> {
    let spawn = request.origin().spawn_generation;
    Ok(match r.status {
        SubmissionRecordStatus::NotSent { issue } => {
            if r.bytes_written != 0 {
                return Err(RequestOwnerIssue::Refused);
            }
            SubmissionStatus::NotSent(submission_issue(&issue)?)
        }
        SubmissionRecordStatus::SubmitUnknown { issue } => {
            if r.bytes_written == 0 {
                return Err(RequestOwnerIssue::Refused);
            }
            SubmissionStatus::SubmitUnknown(submission_issue(&issue)?)
        }
        SubmissionRecordStatus::RefusedBeforePublication {
            reason,
            response_generation,
        } => {
            response_shape(
                spawn,
                response_generation,
                r.bytes_written,
                r.request_frame_bytes,
            )?;
            SubmissionStatus::RefusedBeforePublication {
                reason: match reason {
                    Refusal::ObjectiveUnavailable => PrePublicationRefusal::ObjectiveUnavailable,
                    Refusal::UnsupportedSchema => PrePublicationRefusal::UnsupportedSchema,
                },
                response_generation,
            }
        }
        SubmissionRecordStatus::Admitted {
            run_id,
            objective_digest,
            hard_constraint_digest,
            publication_digest,
            chain_digest,
            disposition,
            idempotent,
            response_generation,
        } => {
            response_shape(
                spawn,
                response_generation,
                r.bytes_written,
                r.request_frame_bytes,
            )?;
            if run_id != request.identity().run_id
                || [
                    &objective_digest,
                    &hard_constraint_digest,
                    &publication_digest,
                    &chain_digest,
                ]
                .iter()
                .any(|d| !receipt::digest_shape(d))
            {
                return Err(RequestOwnerIssue::IdentityMismatch);
            }
            SubmissionStatus::Admitted(AdmissionReceipt {
                run_id,
                objective_digest,
                hard_constraint_digest,
                publication_digest,
                chain_digest,
                disposition: match disposition {
                    Disposition::Compiled => AdmissionDisposition::Compiled,
                    Disposition::ExplicitAbstain => AdmissionDisposition::ExplicitAbstain,
                    Disposition::CanonicalReady => AdmissionDisposition::CanonicalReady,
                    Disposition::CanonicalAbstained => AdmissionDisposition::CanonicalAbstained,
                    Disposition::CanonicalSlowPath => AdmissionDisposition::CanonicalSlowPath,
                },
                idempotent,
                response_generation,
            })
        }
        SubmissionRecordStatus::Conflict {
            run_id,
            conflict_digest,
            response_generation,
        } => {
            response_shape(
                spawn,
                response_generation,
                r.bytes_written,
                r.request_frame_bytes,
            )?;
            if run_id != request.identity().run_id || !receipt::digest_shape(&conflict_digest) {
                return Err(RequestOwnerIssue::IdentityMismatch);
            }
            SubmissionStatus::Conflict(ConflictReceipt {
                run_id,
                conflict_digest,
                response_generation,
            })
        }
    })
}

fn io_shape(bytes: usize, frame: Option<usize>) -> Result<(), RequestOwnerIssue> {
    if bytes > frame.unwrap_or(0) || frame.is_some_and(|length| length == 0 || length > 65_536) {
        return Err(RequestOwnerIssue::Refused);
    }
    Ok(())
}

fn response_shape(
    spawn: u64,
    response: u64,
    bytes: usize,
    frame: Option<usize>,
) -> Result<(), RequestOwnerIssue> {
    if !(spawn..=spawn.saturating_add(2)).contains(&response) || bytes == 0 || Some(bytes) != frame
    {
        return Err(RequestOwnerIssue::Refused);
    }
    Ok(())
}

fn submission_issue(code: &str) -> Result<SubmissionIssue, RequestOwnerIssue> {
    Ok(match code {
        "objective_invalid_execution_context" => SubmissionIssue::InvalidExecutionContext,
        "objective_generation_fenced" => SubmissionIssue::GenerationFenced,
        "objective_frame_bound" => SubmissionIssue::FrameBound,
        "objective_unavailable_transport" => SubmissionIssue::Unavailable,
        "objective_peer_denied" => SubmissionIssue::PeerDenied,
        "objective_deadline_elapsed" => SubmissionIssue::DeadlineElapsed,
        "objective_write_failed" => SubmissionIssue::WriteFailed,
        "objective_read_failed" => SubmissionIssue::ReadFailed,
        "objective_protocol_mismatch" => SubmissionIssue::ProtocolMismatch,
        "objective_owner_request_rejected" => SubmissionIssue::OwnerRequestRejected,
        "objective_owner_error" => SubmissionIssue::OwnerError,
        "objective_overloaded" => SubmissionIssue::Overloaded,
        _ => return Err(RequestOwnerIssue::Refused),
    })
}

fn history_issue(code: &str) -> Result<HistoryIssue, RequestOwnerIssue> {
    Ok(match code {
        "invalid_query" => HistoryIssue::Owner(OwnerUnknownReason::InvalidQuery),
        "owner_unavailable" => HistoryIssue::Owner(OwnerUnknownReason::OwnerUnavailable),
        "journal_unavailable" => HistoryIssue::Owner(OwnerUnknownReason::JournalUnavailable),
        "no_matching_publication" => HistoryIssue::Owner(OwnerUnknownReason::NoMatchingPublication),
        "anchor_missing" => HistoryIssue::Owner(OwnerUnknownReason::AnchorMissing),
        "anchor_mismatch" => HistoryIssue::Owner(OwnerUnknownReason::AnchorMismatch),
        "publication_outside_anchor" => {
            HistoryIssue::Owner(OwnerUnknownReason::PublicationOutsideAnchor)
        }
        _ => HistoryIssue::Transport(submission_issue(code)?),
    })
}
