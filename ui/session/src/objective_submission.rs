//! Trusted-host composition of the original Objective transport and request owner.
//!
//! This is deliberately absent from the standalone Session command protocol.
//! The embedding host supplies the original issuer envelope, trusted endpoint,
//! request identity and a real implementation of the existing durable owner.
//! Structural parsing is not authentication. No signer, new ledger, automatic
//! retry, run cancellation or model/device completion claim lives here.

#[path = "objective_pending.rs"]
mod pending;

pub use pending::LocalSubmissionPhase;

use hepta_os_observer::objective::history::{
    HistoryAnchor, HistoryAttempt, HistoryStatus, ObjectiveHistoryClient,
};
use hepta_os_observer::objective::{
    EnvelopeError, ObjectiveTransport, ProvidedObjective, SubmissionAttempt, SubmissionIdentity,
    SubmissionStatus,
};
use pending::{PendingPermission, RetainAttemptError};
use std::fmt;

/// Finite owner diagnostics. Source text, signatures and store paths stay private.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RequestOwnerIssue {
    Unavailable,
    Refused,
    IdentityMismatch,
    AlreadyRetained,
    PersistenceUnknown,
}

/// Port implemented by the original durable request owner, never a renderer.
///
/// A successful `retain_before_send` must commit the exact original bytes and
/// identity before returning a unique opaque ticket. It must atomically fence
/// competing senders and reject a previously retained request, including one
/// whose outcome is unknown. A fresh facade is not permission to send again.
/// An ambiguous store failure must remain recoverable in that same owner.
///
/// `recover_pending` verifies the caller's complete original bytes and identity
/// against an existing owner record; it must not create or reset a record.
/// Receipt writes are append-only and idempotent for the exact same observation.
/// The retained anchor must be an actual acknowledgement from the original
/// journal, not a sequence guessed from an admission response or RunStatus.
///
/// Calls run on the embedding host's bounded blocking worker. Implementations
/// must bound their own I/O and never run an Objective or external effect as a
/// side effect of retention. This crate intentionally provides no production
/// in-memory, file or database implementation of this port.
pub trait OriginalObjectiveRequestOwner: Send {
    type Pending: Send;

    fn retain_before_send(
        &mut self,
        identity: &SubmissionIdentity,
        exact_original: &[u8],
    ) -> Result<Self::Pending, RequestOwnerIssue>;

    fn recover_pending(
        &mut self,
        identity: &SubmissionIdentity,
        exact_original: &[u8],
    ) -> Result<Self::Pending, RequestOwnerIssue>;

    fn retain_submission_attempt(
        &mut self,
        pending: &Self::Pending,
        attempt: &SubmissionAttempt,
    ) -> Result<(), RequestOwnerIssue>;

    fn retained_history_anchor(
        &mut self,
        pending: &Self::Pending,
    ) -> Result<Option<HistoryAnchor>, RequestOwnerIssue>;

    fn retain_history_attempt(
        &mut self,
        pending: &Self::Pending,
        attempt: &HistoryAttempt,
    ) -> Result<(), RequestOwnerIssue>;

    /// Records only that this local send permission was cancelled before use.
    /// It is neither a run-cancel request nor evidence about another sender.
    fn retain_local_cancellation(
        &mut self,
        pending: &Self::Pending,
        identity: &SubmissionIdentity,
    ) -> Result<(), RequestOwnerIssue>;
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SubmissionAdapterError {
    Envelope(EnvelopeError),
    Owner(RequestOwnerIssue),
    GenerationFenced,
    RetainedIdentityMismatch,
    SendPermissionConsumed,
    OriginalOwnerCancellationRequired,
    NoObservedSubmission,
    HistoryBeforeSubmission,
    HistoryOwnerMismatch,
    UnretainedHistoryResult,
    NoObservedHistory,
    LocalCancellationNotAvailable,
}

impl fmt::Display for SubmissionAdapterError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let code = match self {
            Self::Envelope(issue) => return fmt::Display::fmt(issue, f),
            Self::Owner(_) => "objective_original_owner_retention_failed",
            Self::GenerationFenced => "objective_generation_fenced",
            Self::RetainedIdentityMismatch => "objective_retained_identity_mismatch",
            Self::SendPermissionConsumed => "objective_local_send_permission_consumed",
            Self::OriginalOwnerCancellationRequired => "objective_original_owner_cancel_required",
            Self::NoObservedSubmission => "objective_no_observed_submission",
            Self::HistoryBeforeSubmission => "objective_history_before_submission",
            Self::HistoryOwnerMismatch => "objective_history_owner_mismatch",
            Self::UnretainedHistoryResult => "objective_unretained_history_result",
            Self::NoObservedHistory => "objective_no_observed_history",
            Self::LocalCancellationNotAvailable => "objective_local_cancel_not_available",
        };
        f.write_str(code)
    }
}

impl std::error::Error for SubmissionAdapterError {}

/// Metadata-only observations. These fields are not a single completion verdict.
///
/// Admission and historical publication do not establish a run's completion or
/// an external effect. `last_history` can be unknown while an earlier original
/// publication remains known. A false `*_recorded` flag leaves durable recovery
/// unresolved even when an in-memory original reply was observed.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ObjectiveSubmissionView {
    pub identity: SubmissionIdentity,
    pub phase: LocalSubmissionPhase,
    pub observed_submission: Option<SubmissionStatus>,
    pub submission_recorded: bool,
    pub last_history: Option<HistoryStatus>,
    pub history_recorded: bool,
    pub first_observed_publication: Option<HistoryStatus>,
    pub local_cancellation_recorded: bool,
}

struct OriginalSend {
    transport: ObjectiveTransport,
    objective: ProvidedObjective,
}

/// One original request and one local send permission, bound to one owner.
///
/// No Clone, Debug, serialization, original-payload getter or extraction of the
/// transport is exposed. Dropping this value cannot erase the owner's pending
/// record or authorize another submission. Recovery never recreates a sender.
pub struct ObjectiveSubmission<O: OriginalObjectiveRequestOwner> {
    owner: O,
    pending: PendingPermission<OriginalSend, O::Pending>,
    identity: SubmissionIdentity,
    original: String,
    submission: Option<SubmissionAttempt>,
    history: Option<HistoryAttempt>,
    history_recorded: bool,
    first_observed_publication: Option<HistoryStatus>,
    local_cancellation_recorded: bool,
}

impl<O: OriginalObjectiveRequestOwner> ObjectiveSubmission<O> {
    /// Retains original pending intent before making a send permission available.
    /// Parsing and the original transport constructor perform no admission.
    pub fn prepare(
        mut owner: O,
        transport: ObjectiveTransport,
        original: String,
    ) -> Result<Self, SubmissionAdapterError> {
        let objective = ProvidedObjective::parse_json(original.clone())
            .map_err(SubmissionAdapterError::Envelope)?;
        let identity = transport.submission_identity(&objective);
        if identity.spawn_generation != identity.objective.spawn_generation {
            return Err(SubmissionAdapterError::GenerationFenced);
        }
        let pending = PendingPermission::retain(
            OriginalSend {
                transport,
                objective,
            },
            |_| owner.retain_before_send(&identity, original.as_bytes()),
        )
        .map_err(SubmissionAdapterError::Owner)?;
        Ok(Self::from_retained(owner, pending, identity, original))
    }

    /// Reopens only an existing pending record; it cannot send or cancel a run.
    /// An uncertain crash point remains uncertain even if no run can be found.
    pub fn recover_unknown(
        mut owner: O,
        identity: SubmissionIdentity,
        original: String,
    ) -> Result<Self, SubmissionAdapterError> {
        let objective = ProvidedObjective::parse_json(original.clone())
            .map_err(SubmissionAdapterError::Envelope)?;
        if identity.objective != *objective.identity()
            || identity.spawn_generation != objective.identity().spawn_generation
            || identity.request_id == 0
            || identity.expected_peer_pid == 0
            || identity.expected_peer_pid > i32::MAX as u32
        {
            return Err(SubmissionAdapterError::RetainedIdentityMismatch);
        }
        let ticket = owner
            .recover_pending(&identity, original.as_bytes())
            .map_err(SubmissionAdapterError::Owner)?;
        Ok(Self::from_retained(
            owner,
            PendingPermission::recover_unknown(ticket),
            identity,
            original,
        ))
    }

    fn from_retained(
        owner: O,
        pending: PendingPermission<OriginalSend, O::Pending>,
        identity: SubmissionIdentity,
        original: String,
    ) -> Self {
        Self {
            owner,
            pending,
            identity,
            original,
            submission: None,
            history: None,
            history_recorded: false,
            first_observed_publication: None,
            local_cancellation_recorded: false,
        }
    }

    /// Performs exactly one original transport call on the caller's worker.
    /// The unknown fence is set before any transport I/O. A zero-byte failure,
    /// strict refusal, lost reply or failed receipt handoff never rearms it.
    pub fn submit_once(&mut self) -> Result<(), SubmissionAdapterError> {
        let send = self
            .pending
            .begin_send()
            .map_err(|_| SubmissionAdapterError::SendPermissionConsumed)?;
        self.submission = Some(send.transport.submit_once(send.objective));
        self.retain_observed_submission()
    }

    /// Explicitly repeats only an immutable receipt handoff after store failure.
    /// It never calls the submission transport or changes the original request.
    pub fn retain_observed_submission(&mut self) -> Result<(), SubmissionAdapterError> {
        let attempt = self
            .submission
            .as_ref()
            .ok_or(SubmissionAdapterError::NoObservedSubmission)?;
        if self.pending.phase() == LocalSubmissionPhase::OriginalAttemptRetained {
            return Ok(());
        }
        let owner = &mut self.owner;
        self.pending
            .retain_attempt(|ticket| owner.retain_submission_attempt(ticket, attempt))
            .map_err(|error| match error {
                RetainAttemptError::Owner(issue) => SubmissionAdapterError::Owner(issue),
                RetainAttemptError::State(_) => SubmissionAdapterError::NoObservedSubmission,
            })
    }

    /// Consumes only this not-yet-used local send permission, then records that
    /// fact with the same owner. After start, use the original run-cancel owner.
    pub fn cancel_before_send(&mut self) -> Result<(), SubmissionAdapterError> {
        let send = self
            .pending
            .cancel_before_send()
            .map_err(|_| SubmissionAdapterError::OriginalOwnerCancellationRequired)?;
        drop(send);
        self.retain_local_cancellation()
    }

    /// Explicit owner handoff retry, never a cancellation of a running Objective.
    pub fn retain_local_cancellation(&mut self) -> Result<(), SubmissionAdapterError> {
        if self.pending.phase() != LocalSubmissionPhase::LocalSendCancelled {
            return Err(SubmissionAdapterError::LocalCancellationNotAvailable);
        }
        if !self.local_cancellation_recorded {
            self.owner
                .retain_local_cancellation(self.pending.ticket(), &self.identity)
                .map_err(SubmissionAdapterError::Owner)?;
            self.local_cancellation_recorded = true;
        }
        Ok(())
    }

    /// Explicit original-owner history read against the unchanged original bytes.
    /// The replacement endpoint may have a new generation/PID, but must name the
    /// same agent. No anchor is fabricated and an unknown read clears no result.
    pub fn reconcile_once(
        &mut self,
        client: ObjectiveHistoryClient,
    ) -> Result<(), SubmissionAdapterError> {
        if matches!(
            self.pending.phase(),
            LocalSubmissionPhase::PendingRetained | LocalSubmissionPhase::LocalSendCancelled
        ) {
            return Err(SubmissionAdapterError::HistoryBeforeSubmission);
        }
        // Do not discard an observation that the original owner has not retained.
        if self.history.is_some() && !self.history_recorded {
            return Err(SubmissionAdapterError::UnretainedHistoryResult);
        }
        let objective = ProvidedObjective::parse_json(self.original.clone())
            .map_err(SubmissionAdapterError::Envelope)?;
        if client.query_identity(&objective).agent_id != self.identity.agent_id {
            return Err(SubmissionAdapterError::HistoryOwnerMismatch);
        }
        let anchor = self
            .owner
            .retained_history_anchor(self.pending.ticket())
            .map_err(SubmissionAdapterError::Owner)?;
        let attempt = client.query_once(objective, anchor);
        if self.first_observed_publication.is_none()
            && matches!(
                attempt.status(),
                HistoryStatus::HistoricalPublication { .. }
            )
        {
            self.first_observed_publication = Some(attempt.status().clone());
        }
        self.history = Some(attempt);
        self.history_recorded = false;
        self.retain_observed_history()
    }

    /// Retries only retention of the same original read result, without new I/O.
    pub fn retain_observed_history(&mut self) -> Result<(), SubmissionAdapterError> {
        let attempt = self
            .history
            .as_ref()
            .ok_or(SubmissionAdapterError::NoObservedHistory)?;
        if !self.history_recorded {
            self.owner
                .retain_history_attempt(self.pending.ticket(), attempt)
                .map_err(SubmissionAdapterError::Owner)?;
            self.history_recorded = true;
        }
        Ok(())
    }

    pub fn view(&self) -> ObjectiveSubmissionView {
        ObjectiveSubmissionView {
            identity: self.identity.clone(),
            phase: self.pending.phase(),
            observed_submission: self.submission.as_ref().map(|a| a.status().clone()),
            submission_recorded: self.pending.phase()
                == LocalSubmissionPhase::OriginalAttemptRetained,
            last_history: self.history.as_ref().map(|a| a.status().clone()),
            history_recorded: self.history_recorded,
            first_observed_publication: self.first_observed_publication.clone(),
            local_cancellation_recorded: self.local_cancellation_recorded,
        }
    }
}
