//! A single read of the original owner's durable ObjectiveStart publication.
//!
//! Enabled only by `objective-history`; the owner extension is pinned separately
//! in OBJECTIVE_HISTORY_CONTRACT.json. The caller provides a retained original
//! envelope and the replacement owner's current endpoint identity. No signing,
//! submission, online journal access, persistence, retry or effect API is exposed.

#[path = "history_wire.rs"]
mod wire;

use super::wire::valid_digest;
use super::{
    exchange_raw, require_blocking_context, ObjectiveTransport, ProvidedObjective,
    SubmissionIdentity, SubmissionIssue,
};
use crate::{EndpointConfig, ObserverError, POLL_TIMEOUT_MS};
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tokio::time::timeout;

/// Fixed original ObjectiveRuntimeHost journal capacity at the history pin.
pub const MAX_HISTORY_RECORDS: u64 = 4_096;

/// An exact journal acknowledgement retained from a trusted owner response.
/// Shape checking does not establish provenance; do not guess its sequence.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HistoryAnchor {
    sequence: u64,
    chain_digest: String,
}

impl HistoryAnchor {
    pub fn new(sequence: u64, chain_digest: String) -> Result<Self, ObserverError> {
        if !(1..=MAX_HISTORY_RECORDS).contains(&sequence) || !valid_digest(&chain_digest) {
            return Err(ObserverError::InvalidRequest);
        }
        Ok(Self {
            sequence,
            chain_digest,
        })
    }

    pub fn sequence(&self) -> u64 {
        self.sequence
    }

    pub fn chain_digest(&self) -> &str {
        &self.chain_digest
    }
}

/// Historical publication only. A conflict was not an admission of this request.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum PublicationOutcome {
    Compiled {
        objective_digest: String,
        hard_constraint_digest: String,
    },
    ExplicitAbstain {
        objective_digest: String,
        hard_constraint_digest: String,
    },
    Conflict {
        conflict_digest: String,
    },
}

/// Bounded metadata read by the original journal owner. The desktop checks the
/// known request identity and field shapes; it does not authenticate signatures
/// or independently recompute the owner's signed body/publication digests.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HistoricalPublication {
    pub run_id: String,
    pub original_spawn_generation: u64,
    pub issuer_id: String,
    pub key_epoch: u64,
    pub message_id: String,
    pub message_sequence: u64,
    pub expires_at_ms: u64,
    pub signed_body_digest: String,
    pub profile_digest: String,
    pub publication_sequence: u64,
    pub publication_digest: String,
    pub chain_digest: String,
    pub outcome: PublicationOutcome,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum OwnerUnknownReason {
    InvalidQuery,
    OwnerUnavailable,
    JournalUnavailable,
    NoMatchingPublication,
    AnchorMissing,
    AnchorMismatch,
    PublicationOutsideAnchor,
}

impl OwnerUnknownReason {
    pub fn code(self) -> &'static str {
        match self {
            Self::InvalidQuery => "invalid_query",
            Self::OwnerUnavailable => "owner_unavailable",
            Self::JournalUnavailable => "journal_unavailable",
            Self::NoMatchingPublication => "no_matching_publication",
            Self::AnchorMissing => "anchor_missing",
            Self::AnchorMismatch => "anchor_mismatch",
            Self::PublicationOutsideAnchor => "publication_outside_anchor",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum HistoryIssue {
    Transport(SubmissionIssue),
    Owner(OwnerUnknownReason),
}

impl HistoryIssue {
    pub fn code(self) -> &'static str {
        match self {
            Self::Transport(issue) => issue.code(),
            Self::Owner(reason) => reason.code(),
        }
    }
}

/// None of these states establishes non-admission or an external-effect outcome.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum HistoryStatus {
    HistoricalPublication {
        publication: Box<HistoricalPublication>,
        response_generation: u64,
    },
    Unknown(HistoryIssue),
    /// Zero bytes of this read query were sent. Original submission is unknown.
    QueryNotSent(SubmissionIssue),
}

/// Retains the exact original input privately even after a query failure.
pub struct HistoryAttempt {
    identity: SubmissionIdentity,
    objective: ProvidedObjective,
    anchor: Option<HistoryAnchor>,
    status: HistoryStatus,
    bytes_written: usize,
    frame_bytes: Option<usize>,
}

impl HistoryAttempt {
    pub fn identity(&self) -> &SubmissionIdentity {
        &self.identity
    }
    pub fn anchor(&self) -> Option<&HistoryAnchor> {
        self.anchor.as_ref()
    }
    pub fn status(&self) -> &HistoryStatus {
        &self.status
    }
    pub fn bytes_written(&self) -> usize {
        self.bytes_written
    }
    pub fn request_frame_bytes(&self) -> Option<usize> {
        self.frame_bytes
    }
    pub fn matches_original_json(&self, original: &[u8]) -> bool {
        self.objective.matches_original_json(original)
    }
}

/// A dedicated, one-shot trusted host read. It shares only the bounded socket
/// transport with ObjectiveStart, and has no submit method or generic RPC path.
pub struct ObjectiveHistoryClient {
    transport: ObjectiveTransport,
}

impl ObjectiveHistoryClient {
    pub fn new(
        config: EndpointConfig,
        expected_peer_pid: u32,
        request_id: u64,
    ) -> Result<Self, ObserverError> {
        Ok(Self {
            transport: ObjectiveTransport::new(config, expected_peer_pid, request_id)?,
        })
    }

    /// Current trusted endpoint and unchanged historical request metadata.
    /// No connection, lookup, authentication or publication occurs here.
    pub fn query_identity(&self, objective: &ProvidedObjective) -> SubmissionIdentity {
        self.transport.submission_identity(objective)
    }

    pub fn query_once(
        self,
        objective: ProvidedObjective,
        anchor: Option<HistoryAnchor>,
    ) -> HistoryAttempt {
        let transport = &self.transport;
        let identity = self.query_identity(&objective);
        let mut bytes_written = 0;
        let mut frame_bytes = None;
        let result = (|| {
            require_blocking_context().map_err(|_| SubmissionIssue::InvalidExecutionContext)?;
            // Deserialization can construct an anchor without invoking new().
            if anchor.as_ref().is_some_and(|a| {
                !(1..=MAX_HISTORY_RECORDS).contains(&a.sequence) || !valid_digest(&a.chain_digest)
            }) {
                return Err(SubmissionIssue::ProtocolMismatch);
            }
            // The envelope's historical spawn is intentionally preserved. Only
            // the outer endpoint is fenced to the currently configured owner.
            let frame = wire::request_frame(&objective, anchor.as_ref(), &identity)?;
            frame_bytes = Some(frame.len());
            transport
                .runtime
                .as_ref()
                .expect("live runtime")
                .block_on(async {
                    timeout(Duration::from_millis(POLL_TIMEOUT_MS), async {
                        let response = exchange_raw(
                            &transport.config,
                            transport.expected_peer_pid,
                            &transport.metadata_gate,
                            &frame,
                            &mut bytes_written,
                        )
                        .await?;
                        wire::classify_response(&response, &identity, anchor.as_ref())
                    })
                    .await
                    .map_err(|_| SubmissionIssue::DeadlineElapsed)?
                })
        })();
        let status = result.unwrap_or_else(|issue| {
            if bytes_written == 0 {
                HistoryStatus::QueryNotSent(issue)
            } else {
                HistoryStatus::Unknown(HistoryIssue::Transport(issue))
            }
        });
        HistoryAttempt {
            identity,
            objective,
            anchor,
            status,
            bytes_written,
            frame_bytes,
        }
    }
}
