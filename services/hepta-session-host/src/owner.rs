//! Exact adapter to the original owner's capability; no independent persistence.

use crate::receipt;
use codex_hepta_memory::{
    ObjectiveSenderCheckpoint, ObjectiveSenderError, ObjectiveSenderObservation,
    ObjectiveSenderOrigin, ObjectiveSenderRequest, ObjectiveSenderTicket,
    ProductionObjectiveSender,
};
use hepta_os_observer::objective::history::{HistoryAnchor, HistoryAttempt};
use hepta_os_observer::objective::{SubmissionAttempt, SubmissionIdentity};
use std::future::Future;
use std::time::Duration;
use tokio::runtime::Handle;
use trill_session::objective_submission::{OriginalObjectiveRequestOwner, RequestOwnerIssue};

pub(crate) struct OriginalOwner<C: ObjectiveSenderCheckpoint> {
    sender: ProductionObjectiveSender<C>,
    runtime: Handle,
    origin: ObjectiveSenderOrigin,
    deadline: Duration,
}

impl<C: ObjectiveSenderCheckpoint> OriginalOwner<C> {
    pub(crate) fn new(
        sender: ProductionObjectiveSender<C>,
        runtime: Handle,
        origin: ObjectiveSenderOrigin,
        deadline: Duration,
    ) -> Self {
        Self {
            sender,
            runtime,
            origin,
            deadline,
        }
    }

    pub(crate) fn recovery_view(
        &self,
        request: ObjectiveSenderRequest,
    ) -> Result<crate::recovery::RecoveredObservations, RequestOwnerIssue> {
        let snapshot = self.execute(async {
            let ticket = self.sender.recover_pending(request.clone()).await?;
            // A committed row alone does not establish the independent ACK.
            // Recovered *_recorded metadata is projected only after the original
            // owner has acknowledged its current cut under its write transaction.
            self.sender.snapshot_acknowledged(&ticket).await
        })?;
        crate::recovery::project(&request, &snapshot)
    }

    fn execute<T>(
        &self,
        operation: impl Future<Output = Result<T, ObjectiveSenderError>>,
    ) -> Result<T, RequestOwnerIssue> {
        if Handle::try_current().is_ok() {
            return Err(RequestOwnerIssue::Unavailable);
        }
        // A timeout drops the pending future. A SQLite commit may already have
        // happened; never label that absence or rearm a sender. The original
        // owner's durable uniqueness fence and recovery own that uncertainty.
        self.runtime.block_on(async {
            tokio::time::timeout(self.deadline, operation)
                .await
                .map_err(|_| RequestOwnerIssue::PersistenceUnknown)?
                .map_err(owner_error)
        })
    }

    fn original(
        &self,
        identity: &SubmissionIdentity,
        original: &[u8],
    ) -> Result<ObjectiveSenderRequest, RequestOwnerIssue> {
        let request = ObjectiveSenderRequest::from_original(
            String::from_utf8(original.to_vec())
                .map_err(|_| RequestOwnerIssue::IdentityMismatch)?,
            self.origin.clone(),
        )
        .map_err(|_| RequestOwnerIssue::IdentityMismatch)?;
        receipt::require_submission_identity(&request, identity)?;
        Ok(request)
    }

    fn retain(
        &self,
        ticket: &ObjectiveSenderTicket,
        observation: ObjectiveSenderObservation,
    ) -> Result<(), RequestOwnerIssue> {
        self.execute(self.sender.retain_observation(ticket, &observation))
    }
}

impl<C: ObjectiveSenderCheckpoint> OriginalObjectiveRequestOwner for OriginalOwner<C> {
    type Pending = ObjectiveSenderTicket;

    fn retain_before_send(
        &mut self,
        identity: &SubmissionIdentity,
        exact_original: &[u8],
    ) -> Result<Self::Pending, RequestOwnerIssue> {
        let request = self.original(identity, exact_original)?;
        self.execute(self.sender.retain_before_send(request))
    }

    fn recover_pending(
        &mut self,
        identity: &SubmissionIdentity,
        exact_original: &[u8],
    ) -> Result<Self::Pending, RequestOwnerIssue> {
        let request = self.original(identity, exact_original)?;
        self.execute(self.sender.recover_pending(request))
    }

    fn mark_send_started(&mut self, pending: &Self::Pending) -> Result<(), RequestOwnerIssue> {
        self.execute(self.sender.mark_send_started(pending))
    }

    fn retain_submission_attempt(
        &mut self,
        pending: &Self::Pending,
        attempt: &SubmissionAttempt,
    ) -> Result<(), RequestOwnerIssue> {
        self.retain(pending, receipt::submission(pending.request(), attempt)?)
    }

    fn retained_history_anchor(
        &mut self,
        pending: &Self::Pending,
    ) -> Result<Option<HistoryAnchor>, RequestOwnerIssue> {
        let snapshot = self.execute(self.sender.snapshot(pending))?;
        receipt::retained_anchor(pending.request(), &snapshot)
    }

    fn retain_history_attempt(
        &mut self,
        pending: &Self::Pending,
        attempt: &HistoryAttempt,
    ) -> Result<(), RequestOwnerIssue> {
        let observation = receipt::history(pending.request(), attempt)?;
        self.execute(self.sender.retain_observation_checked(
            pending,
            &observation,
            |snapshot| {
                // The current projection and append share the original owner's
                // write transaction, including across concurrently recovered
                // handles. This callback performs only bounded data checks.
                let retained = crate::recovery::project(pending.request(), snapshot)
                    .map_err(|_| ObjectiveSenderError::IdentityMismatch)?;
                if let (
                    Some(
                        hepta_os_observer::objective::history::HistoryStatus::HistoricalPublication {
                            publication: previous,
                            ..
                        },
                    ),
                    hepta_os_observer::objective::history::HistoryStatus::HistoricalPublication {
                        publication,
                        ..
                    },
                ) = (retained.first_publication.as_ref(), attempt.status())
                    && **previous != **publication
                {
                    // Later response generations may differ; the original
                    // publication itself must remain exactly the same.
                    return Err(ObjectiveSenderError::IdentityMismatch);
                }
                Ok(())
            },
        ))
    }

    fn retain_local_cancellation(
        &mut self,
        pending: &Self::Pending,
        identity: &SubmissionIdentity,
    ) -> Result<(), RequestOwnerIssue> {
        receipt::require_submission_identity(pending.request(), identity)?;
        self.execute(self.sender.retain_local_cancellation(pending))
    }
}

fn owner_error(error: ObjectiveSenderError) -> RequestOwnerIssue {
    match error {
        ObjectiveSenderError::AlreadyRetained => RequestOwnerIssue::AlreadyRetained,
        ObjectiveSenderError::IdentityMismatch | ObjectiveSenderError::Missing => {
            RequestOwnerIssue::IdentityMismatch
        }
        ObjectiveSenderError::AcknowledgementUnknown | ObjectiveSenderError::Store(_) => {
            RequestOwnerIssue::PersistenceUnknown
        }
        ObjectiveSenderError::Capacity => RequestOwnerIssue::Unavailable,
        ObjectiveSenderError::Input(_)
        | ObjectiveSenderError::Writer(_)
        | ObjectiveSenderError::ObservationConflict
        | ObjectiveSenderError::LocalCancellationUnavailable
        | ObjectiveSenderError::SendPermissionUnavailable => RequestOwnerIssue::Refused,
    }
}
