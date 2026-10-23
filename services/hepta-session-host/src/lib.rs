//! Trusted Session composition over the original Hepta durable Objective owner.
//!
//! Linux host library only. It neither owns a database nor supplies authority,
//! signing, checkpoint persistence, a background runtime, or a renderer command.

#![forbid(unsafe_code)]

mod owner;
mod receipt;
mod recovery;

use codex_hepta_memory::{
    ObjectiveSenderCheckpoint, ObjectiveSenderIdentity, ObjectiveSenderOrigin,
    ObjectiveSenderRequest, ProductionObjectiveSender,
};
use hepta_os_observer::EndpointConfig;
use hepta_os_observer::objective::history::{HistoryIssue, HistoryStatus, ObjectiveHistoryClient};
use hepta_os_observer::objective::{
    ObjectiveTransport, ProvidedObjective, SubmissionIdentity, SubmissionIssue,
};
use owner::OriginalOwner;
use std::path::PathBuf;
use std::time::Duration;
use tokio::runtime::{Handle, RuntimeFlavor};
use trill_session::objective_submission::{
    ObjectiveSubmission, ObjectiveSubmissionView, RequestOwnerIssue, SubmissionAdapterError,
};

pub use codex_hepta_memory::{ObjectiveSenderCheckpointError, ObjectiveSenderWriterFence};

/// A finite failure; original requests, authority material and endpoints are private.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum HostError {
    InvalidWorker,
    InvalidEndpoint,
    InvalidDeadline,
    Submission(SubmissionAdapterError),
}

impl std::fmt::Display for HostError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::InvalidWorker => {
                "hepta_session_host_requires_original_runtime_and_blocking_worker"
            }
            Self::InvalidEndpoint => "hepta_session_host_invalid_original_endpoint",
            Self::InvalidDeadline => "hepta_session_host_invalid_retention_deadline",
            Self::Submission(_) => "hepta_session_host_original_submission_failed",
        })
    }
}

impl std::error::Error for HostError {}

/// One original retained request, using the existing Session state machine.
///
/// Construct and operate this on the embedding's existing bounded non-Tokio
/// blocking worker. `runtime` is the independently running ORIGINAL Hepta
/// multi-thread runtime; this adapter never creates a second runtime. It must
/// outlive this handle. The original transport retains its existing bounded
/// one-shot socket runtime. No new dispatch queue or polling task is installed.
///
/// The trusted host must inject an already constructed original sender whose
/// checkpoint implementation has independent durable/current-cut provenance.
/// This type has no default checkpoint, issuer or in-memory production owner.
/// No Clone/Debug/serialization exposes the retained original envelope.
pub struct HeptaSessionSubmission<C: ObjectiveSenderCheckpoint> {
    submission: ObjectiveSubmission<OriginalOwner<C>>,
    recovered: recovery::RecoveredObservations,
    expected: ObjectiveSenderIdentity,
    history_projection_rejected: bool,
}

impl<C: ObjectiveSenderCheckpoint> HeptaSessionSubmission<C> {
    /// Retain exact original intent and obtain one local permission. The same
    /// immutable origin constructs BOTH the transport and original owner binding.
    pub fn prepare(
        sender: ProductionObjectiveSender<C>,
        runtime: Handle,
        origin: ObjectiveSenderOrigin,
        original: String,
        retention_deadline: Duration,
    ) -> Result<Self, HostError> {
        require_worker(&runtime, retention_deadline)?;
        let expected = ObjectiveSenderRequest::from_original(original.clone(), origin.clone())
            .map_err(|_| {
                HostError::Submission(SubmissionAdapterError::Owner(
                    RequestOwnerIssue::IdentityMismatch,
                ))
            })?
            .identity()
            .clone();
        let config = endpoint(&origin)?;
        let transport =
            ObjectiveTransport::new(config, origin.expected_peer_pid, origin.request_id)
                .map_err(|_| HostError::InvalidEndpoint)?;
        let owner = OriginalOwner::new(sender, runtime, origin, retention_deadline);
        let submission = ObjectiveSubmission::prepare(owner, transport, original)
            .map_err(HostError::Submission)?;
        Ok(Self {
            submission,
            recovered: Default::default(),
            expected,
            history_projection_rejected: false,
        })
    }

    /// Reopen a request returned by the original owner's retained enumeration.
    /// This creates no transport, never refreshes the old identity and never
    /// grants another send or pre-send cancellation permission.
    pub fn recover_unknown(
        sender: ProductionObjectiveSender<C>,
        runtime: Handle,
        retained: ObjectiveSenderRequest,
        retention_deadline: Duration,
    ) -> Result<Self, HostError> {
        require_worker(&runtime, retention_deadline)?;
        let expected = retained.identity().clone();
        let origin = retained.origin().clone();
        endpoint(&origin)?;
        let original = String::from_utf8(retained.exact_original().to_vec()).map_err(|_| {
            HostError::Submission(SubmissionAdapterError::Owner(
                RequestOwnerIssue::IdentityMismatch,
            ))
        })?;
        let parsed = ProvidedObjective::parse_json(original.clone())
            .map_err(|error| HostError::Submission(SubmissionAdapterError::Envelope(error)))?;
        let identity = SubmissionIdentity {
            request_id: origin.request_id,
            agent_id: origin.agent_id.as_str().to_owned(),
            spawn_generation: origin.spawn_generation,
            expected_peer_uid: origin.expected_peer_uid,
            expected_peer_pid: origin.expected_peer_pid,
            objective: parsed.identity().clone(),
        };
        let owner = OriginalOwner::new(sender, runtime, origin, retention_deadline);
        let recovered = owner
            .recovery_view(retained)
            .map_err(|issue| HostError::Submission(SubmissionAdapterError::Owner(issue)))?;
        let submission = ObjectiveSubmission::recover_unknown(owner, identity, original)
            .map_err(HostError::Submission)?;
        Ok(Self {
            submission,
            recovered,
            expected,
            history_projection_rejected: false,
        })
    }

    pub fn submit_once(&mut self) -> Result<(), HostError> {
        require_blocking_thread()?;
        self.submission.submit_once().map_err(HostError::Submission)
    }

    pub fn retain_observed_submission(&mut self) -> Result<(), HostError> {
        require_blocking_thread()?;
        self.submission
            .retain_observed_submission()
            .map_err(HostError::Submission)
    }

    /// Local unused permission only; this never calls Hepta RunCancel.
    pub fn cancel_before_send(&mut self) -> Result<(), HostError> {
        require_blocking_thread()?;
        self.submission
            .cancel_before_send()
            .map_err(HostError::Submission)
    }

    pub fn retain_local_cancellation(&mut self) -> Result<(), HostError> {
        require_blocking_thread()?;
        self.submission
            .retain_local_cancellation()
            .map_err(HostError::Submission)
    }

    /// Query the same original request against the independently trusted current
    /// endpoint. The historical request's generation is never rewritten.
    pub fn reconcile_once(&mut self, current: ObjectiveSenderOrigin) -> Result<(), HostError> {
        require_blocking_thread()?;
        let client = ObjectiveHistoryClient::new(
            endpoint(&current)?,
            current.expected_peer_pid,
            current.request_id,
        )
        .map_err(|_| HostError::InvalidEndpoint)?;
        self.remember_retained_first();
        let result = self.submission.reconcile_once(client);
        self.record_history_projection(&result);
        result.map_err(HostError::Submission)
    }

    pub fn retain_observed_history(&mut self) -> Result<(), HostError> {
        require_blocking_thread()?;
        let result = self.submission.retain_observed_history();
        self.record_history_projection(&result);
        result.map_err(HostError::Submission)
    }

    fn remember_retained_first(&mut self) {
        let view = self.submission.view();
        if self.recovered.first_publication.is_none() && view.history_recorded {
            self.recovered.first_publication = view.first_observed_publication;
        }
    }

    fn record_history_projection(&mut self, result: &Result<(), SubmissionAdapterError>) {
        if result.is_ok() {
            self.history_projection_rejected = false;
            self.remember_retained_first();
        } else if matches!(
            result,
            Err(SubmissionAdapterError::Owner(
                RequestOwnerIssue::IdentityMismatch
            ))
        ) && !self.submission.view().history_recorded
        {
            // A different recovery handle may have retained the first original
            // publication since this facade's initial snapshot. Session records
            // a reply before owner retention; a definitive identity rejection must
            // never promote that reply to a known publication in this view.
            // A timeout or live-authority refusal does not invalidate a reply
            // previously observed from the original trusted peer.
            self.history_projection_rejected = true;
        }
    }

    /// Metadata-only Session observations; no original JSON or socket path.
    pub fn view(&self) -> ObjectiveSubmissionView {
        let mut view = self.submission.view();
        // The original history transport checks its pinned wire identity. This
        // concrete owner additionally binds the canonical signed body. A rejected
        // body must not leak through Session's pre-retention observation view.
        if let Some(HistoryStatus::HistoricalPublication { publication, .. }) = &view.last_history
            && receipt::require_publication(&self.expected, publication).is_err()
        {
            view.last_history = Some(HistoryStatus::Unknown(HistoryIssue::Transport(
                SubmissionIssue::ProtocolMismatch,
            )));
            view.history_recorded = false;
        }
        if let Some(HistoryStatus::HistoricalPublication { publication, .. }) =
            &view.first_observed_publication
            && receipt::require_publication(&self.expected, publication).is_err()
        {
            view.first_observed_publication = None;
        }
        if self.history_projection_rejected {
            if matches!(
                view.last_history,
                Some(HistoryStatus::HistoricalPublication { .. })
            ) {
                view.last_history = Some(HistoryStatus::Unknown(HistoryIssue::Transport(
                    SubmissionIssue::ProtocolMismatch,
                )));
                view.history_recorded = false;
            }
            view.first_observed_publication = None;
        }
        self.recovered.apply(&mut view);
        if let (
            Some(HistoryStatus::HistoricalPublication {
                publication: first, ..
            }),
            Some(HistoryStatus::HistoricalPublication {
                publication: latest,
                ..
            }),
        ) = (&view.first_observed_publication, &view.last_history)
            && **first != **latest
        {
            view.last_history = Some(HistoryStatus::Unknown(HistoryIssue::Transport(
                SubmissionIssue::ProtocolMismatch,
            )));
            view.history_recorded = false;
        }
        view
    }
}

fn require_worker(runtime: &Handle, deadline: Duration) -> Result<(), HostError> {
    require_blocking_thread()?;
    if runtime.runtime_flavor() != RuntimeFlavor::MultiThread {
        return Err(HostError::InvalidWorker);
    }
    if deadline.is_zero() || deadline > Duration::from_secs(10) {
        return Err(HostError::InvalidDeadline);
    }
    Ok(())
}

fn require_blocking_thread() -> Result<(), HostError> {
    if Handle::try_current().is_ok() {
        return Err(HostError::InvalidWorker);
    }
    Ok(())
}

fn endpoint(origin: &ObjectiveSenderOrigin) -> Result<EndpointConfig, HostError> {
    EndpointConfig::new(
        PathBuf::from(&origin.endpoint_identity),
        origin.agent_id.as_str().to_owned(),
        origin.spawn_generation,
        origin.expected_peer_uid,
    )
    .map_err(|_| HostError::InvalidEndpoint)
}
