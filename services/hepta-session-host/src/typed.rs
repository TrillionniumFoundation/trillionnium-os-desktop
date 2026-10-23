//! Bounded typed intent handling over the original writer; no second ledger.
use crate::{HeptaSessionSubmission, control};
use codex_hepta_agent_protocol::{
    AgentCancellationDisposition, AgentRunPhase, AgentdPayload, AgentdRequest,
};
use codex_hepta_memory::{
    ObjectiveSenderCheckpoint, ObjectiveSenderOrigin, ObjectiveSenderRequest,
    ObjectiveSenderRetainedPosition, ProductionObjectiveSender,
};
use hepta_os_observer::objective::history::{HistoryStatus, PublicationOutcome};
use hepta_os_observer::objective::{AdmissionDisposition, SubmissionStatus};
use std::time::Duration;
use tokio::runtime::Handle;
use trill_ui_core::objective::*;

/// Implemented only by the trusted deployment. Identity is deterministic within
/// its persistent trust namespace. Issuing never grants device/effect authority.
/// Callbacks must be bounded; this synchronous host runs on one blocking worker.
pub trait ObjectiveHostAuthority: Send {
    type Checkpoint: ObjectiveSenderCheckpoint;
    fn sender(&self) -> Result<ProductionObjectiveSender<Self::Checkpoint>, ObjectiveHostIssue>;
    fn current_origin(&mut self) -> Result<ObjectiveSenderOrigin, ObjectiveHostIssue>;
    fn run_id(&self, client_intent_id: &str) -> Result<String, ObjectiveHostIssue>;
    /// Pure projection of the original source request ID, restricted to this
    /// deployment's UI profile. Return None for a different original producer.
    /// This must never sign, prepare, submit or create a parallel ID ledger.
    fn retained_client_intent_id(
        &self,
        request: &ObjectiveSenderRequest,
    ) -> Result<Option<String>, ObjectiveHostIssue>;
    fn issue(
        &mut self,
        intent: &ObjectiveIntent,
        origin: &ObjectiveSenderOrigin,
    ) -> Result<String, ObjectiveHostIssue>;
}

pub struct TypedObjectiveHost<A: ObjectiveHostAuthority> {
    authority: A,
    runtime: Handle,
    deadline: Duration,
}

impl<A: ObjectiveHostAuthority> TypedObjectiveHost<A> {
    pub fn new(
        authority: A,
        runtime: Handle,
        deadline: Duration,
    ) -> Result<Self, ObjectiveHostIssue> {
        crate::require_worker(&runtime, deadline).map_err(|_| ObjectiveHostIssue::Unavailable)?;
        Ok(Self {
            authority,
            runtime,
            deadline,
        })
    }

    pub fn handle(&mut self, command: ObjectiveCommand) -> ObjectiveObservation {
        let mut view = ObjectiveObservation::new(
            command.client_intent_id().map(str::to_owned),
            ObjectiveStage::Unavailable,
        );
        if let Err(issue) = command
            .validate()
            .and_then(|()| self.execute(command, &mut view))
        {
            view.issue = Some(issue);
        }
        view
    }

    fn execute(
        &mut self,
        command: ObjectiveCommand,
        view: &mut ObjectiveObservation,
    ) -> Result<(), ObjectiveHostIssue> {
        crate::require_worker(&self.runtime, self.deadline)
            .map_err(|_| ObjectiveHostIssue::Unavailable)?;
        let sender = self.authority.sender()?;
        let origin = self.authority.current_origin()?;
        crate::endpoint(&origin).map_err(|_| ObjectiveHostIssue::IdentityMismatch)?;
        if matches!(command, ObjectiveCommand::Availability {}) {
            let payload = control::call(
                &self.runtime,
                &origin,
                AgentdRequest::capabilities(origin.request_id, origin.spawn_generation),
            )?;
            let AgentdPayload::Capabilities(capabilities) = payload else {
                return Err(ObjectiveHostIssue::Unavailable);
            };
            capabilities
                .validate()
                .map_err(|_| ObjectiveHostIssue::IdentityMismatch)?;
            if !capabilities
                .capabilities
                .iter()
                .any(|capability| capability.id == "objective.start" && capability.major == 1)
            {
                return Err(ObjectiveHostIssue::Unavailable);
            }
            let retained = crate::retained::collect(
                &self.authority,
                &sender,
                &origin,
                &self.runtime,
                self.deadline,
            )?;
            let complete = retained.complete;
            view.retained_intents = Some(retained);
            if !complete {
                return Err(ObjectiveHostIssue::Capacity);
            }
            view.stage = ObjectiveStage::Ready;
            return Ok(());
        }
        let id = command
            .client_intent_id()
            .ok_or(ObjectiveHostIssue::InvalidIntent)?;
        let run_id = self.authority.run_id(id)?;
        let retained = self.find_retained(&sender, &run_id)?;
        let mut submission = if let Some(retained) = retained {
            if retained.origin().agent_id != origin.agent_id
                || retained.origin().spawn_generation > origin.spawn_generation
            {
                return Err(ObjectiveHostIssue::IdentityMismatch);
            }
            HeptaSessionSubmission::recover_unknown(
                sender,
                self.runtime.clone(),
                retained,
                self.deadline,
            )
            .map_err(|_| ObjectiveHostIssue::PersistenceUnknown)?
        } else if let ObjectiveCommand::Submit { intent } = &command {
            let original = self.authority.issue(intent, &origin)?;
            let parsed = ObjectiveSenderRequest::from_original(original.clone(), origin.clone())
                .map_err(|_| ObjectiveHostIssue::InvalidIntent)?;
            if parsed.identity().run_id != run_id {
                return Err(ObjectiveHostIssue::IdentityMismatch);
            }
            let mut submission = HeptaSessionSubmission::prepare(
                sender,
                self.runtime.clone(),
                origin.clone(),
                original,
                self.deadline,
            )
            .map_err(|_| ObjectiveHostIssue::PersistenceUnknown)?;
            view.request_retained = true;
            view.stage = ObjectiveStage::Retained;
            // The local permission is consumed exactly once, even if retention
            // of its response later fails. Future commands only recover it.
            let result = submission.submit_once();
            project(&submission.view(), view);
            if result.is_err() {
                view.issue = Some(ObjectiveHostIssue::PersistenceUnknown);
            }
            submission
        } else {
            return Err(ObjectiveHostIssue::NoRetainedIntent);
        };
        let _ = submission.reconcile_once(origin.clone());
        project(&submission.view(), view);
        if view.stage != ObjectiveStage::Admitted || !view.publication_retained {
            return Ok(());
        }
        let payload = control::call(
            &self.runtime,
            &origin,
            AgentdRequest::run_status(origin.request_id, origin.spawn_generation, run_id.clone()),
        )?;
        let AgentdPayload::RunStatus { run } = payload else {
            return Err(ObjectiveHostIssue::OwnerRefused);
        };
        let Some(run) = run else {
            return Ok(());
        }; // No run is not proof of non-admission.
        if run.run_id != run_id || run.generation < origin.spawn_generation {
            return Err(ObjectiveHostIssue::IdentityMismatch);
        }
        view.run = Some(run_view(&run));
        if matches!(command, ObjectiveCommand::Cancel { .. }) {
            let current = self.authority.current_origin()?;
            if current.agent_id != origin.agent_id
                || current.spawn_generation != origin.spawn_generation
                || current.expected_peer_pid != origin.expected_peer_pid
                || current.expected_peer_uid != origin.expected_peer_uid
                || current.endpoint_identity != origin.endpoint_identity
            {
                return Err(ObjectiveHostIssue::IdentityMismatch);
            }
            view.cancellation = ObjectiveCancellation::Unknown;
            let payload = control::call(
                &self.runtime,
                &current,
                AgentdRequest::run_cancel(
                    current.request_id,
                    current.spawn_generation,
                    run_id.clone(),
                    run.revision,
                    "user_requested".into(),
                ),
            )?;
            let AgentdPayload::RunCancellation(cancel) = payload else {
                return Err(ObjectiveHostIssue::OwnerRefused);
            };
            if cancel.receipt.run_id != run_id
                || cancel.receipt.generation < origin.spawn_generation
                || cancel.receipt.revision < run.revision
            {
                return Err(ObjectiveHostIssue::IdentityMismatch);
            }
            view.run = Some(run_view(&cancel.receipt));
            view.cancellation = match cancel.disposition {
                AgentCancellationDisposition::CancelledBeforeDispatch => {
                    ObjectiveCancellation::CancelledBeforeDispatch
                }
                AgentCancellationDisposition::CancellingAfterDispatch => {
                    ObjectiveCancellation::CancellingAfterDispatch
                }
                AgentCancellationDisposition::AlreadyTerminal => {
                    ObjectiveCancellation::AlreadyTerminal
                }
            };
        }
        Ok(())
    }

    fn find_retained(
        &self,
        sender: &ProductionObjectiveSender<A::Checkpoint>,
        run_id: &str,
    ) -> Result<Option<ObjectiveSenderRequest>, ObjectiveHostIssue> {
        self.runtime.block_on(async {
            tokio::time::timeout(self.deadline, async {
                let mut position = ObjectiveSenderRetainedPosition::Beginning;
                loop {
                    let page = sender
                        .retained_page(position)
                        .await
                        .map_err(|_| ObjectiveHostIssue::PersistenceUnknown)?;
                    if let Some(found) = page
                        .requests
                        .into_iter()
                        .find(|r| r.identity().run_id == run_id)
                    {
                        return Ok(Some(found));
                    }
                    match page.next {
                        Some(cursor) => position = ObjectiveSenderRetainedPosition::After(cursor),
                        None => return Ok(None),
                    }
                }
            })
            .await
            .map_err(|_| ObjectiveHostIssue::PersistenceUnknown)?
        })
    }
}

fn project(
    source: &trill_session::objective_submission::ObjectiveSubmissionView,
    view: &mut ObjectiveObservation,
) {
    view.request_retained = true;
    view.stage = match &source.observed_submission {
        Some(SubmissionStatus::Admitted(receipt)) => match receipt.disposition {
            AdmissionDisposition::ExplicitAbstain | AdmissionDisposition::CanonicalAbstained => {
                ObjectiveStage::Abstained
            }
            _ => ObjectiveStage::Admitted,
        },
        Some(SubmissionStatus::Conflict(_)) => ObjectiveStage::Conflict,
        Some(SubmissionStatus::NotSent(_)) => ObjectiveStage::NotSent,
        Some(SubmissionStatus::RefusedBeforePublication { .. }) => ObjectiveStage::Refused,
        Some(SubmissionStatus::SubmitUnknown(_)) | None => ObjectiveStage::SubmitUnknown,
    };
    view.publication_retained = source.submission_recorded
        && matches!(
            source.observed_submission,
            Some(SubmissionStatus::Admitted(_)) | Some(SubmissionStatus::Conflict(_))
        );
    if let Some(HistoryStatus::HistoricalPublication { publication, .. }) =
        &source.first_observed_publication
    {
        view.stage = match publication.outcome {
            PublicationOutcome::Conflict { .. } => ObjectiveStage::Conflict,
            PublicationOutcome::ExplicitAbstain { .. } => ObjectiveStage::Abstained,
            PublicationOutcome::Compiled { .. } => ObjectiveStage::Admitted,
        };
        view.publication_retained = source.history_recorded;
    }
}

fn run_view(run: &codex_hepta_agent_protocol::AgentRunReceipt) -> ObjectiveRunObservation {
    let phase = match run.phase {
        AgentRunPhase::Admitted => ObjectiveRunPhase::Admitted,
        AgentRunPhase::ContextAttached => ObjectiveRunPhase::ContextAttached,
        AgentRunPhase::Dispatched => ObjectiveRunPhase::Dispatched,
        AgentRunPhase::Cancelling => ObjectiveRunPhase::Cancelling,
        AgentRunPhase::Cancelled => ObjectiveRunPhase::Cancelled,
        AgentRunPhase::Succeeded => ObjectiveRunPhase::Succeeded,
        AgentRunPhase::Failed => ObjectiveRunPhase::Failed,
        AgentRunPhase::Indeterminate => ObjectiveRunPhase::Indeterminate,
    };
    ObjectiveRunObservation {
        revision: run.revision,
        phase,
        terminal_observed: run.terminal_observed,
    }
}
