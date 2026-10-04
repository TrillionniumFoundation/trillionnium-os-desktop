//! Production actor accepts only an opaque root-approved original request.
use super::*;
use hepta_peer_attestation::ApprovedAgentRequestBinding;
impl ServoBrowserActor {
    pub fn from_approved_request(
        request: &ApprovedAgentRequestBinding,
        endpoint: ServoRuntimeEndpoint,
    ) -> Result<Self, AgentPortError> {
        let session = request
            .start_session()
            .map_err(|e| AgentPortError::Handler(format!("approved session refused: {e}")))?;
        let (peer, snapshot, principal_id) = request
            .verify_for_session(&session)
            .map_err(|e| AgentPortError::Handler(format!("approved session refused: {e}")))?;
        let principal = TaskFlowPrincipal {
            principal_id,
            expected_uid: snapshot.uid,
            expected_gid: snapshot.gid,
            expected_systemd_unit: snapshot
                .systemd_unit
                .clone()
                .ok_or_else(|| AgentPortError::Handler("approved unit absent".into()))?,
            expected_cgroup_v2_path: snapshot.cgroup_v2_path.clone(),
            expected_executable_sha256: snapshot.executable_sha256.clone(),
        };
        let binding = simulation::PrincipalBinding::bind_attested(principal, peer, &snapshot)
            .map_err(|e| AgentPortError::Handler(format!("approved binding refused: {e}")))?;
        let verifier = request
            .verifier_for_session(&session)
            .map_err(|e| AgentPortError::Handler(format!("approved request refused: {e}")))?;
        Ok(Self {
            approved_creator_pid: std::process::id(),
            profile: endpoint.profile,
            inner: simulation::BrowserActor::new(binding, endpoint.inner),
            approved_session: Some(session),
            approved_request: Some(verifier),
            approved_uncertain: false,
        })
    }
    pub fn rebind_approved_request(
        &mut self,
        request: &ApprovedAgentRequestBinding,
    ) -> Result<(), AgentPortError> {
        self.ensure_approved_creator()?;
        if self.approved_uncertain {
            return Err(AgentPortError::Handler(
                "approved actor requires effect reconciliation".into(),
            ));
        }
        // A legacy/raw actor cannot attach root approval retroactively.
        let session = self
            .approved_session
            .as_ref()
            .ok_or_else(|| AgentPortError::Handler("actor has no approved session".into()))?;
        let verifier = request
            .verifier_for_session(session)
            .map_err(|e| AgentPortError::Handler(format!("approved request refused: {e}")))?;
        self.inner.rebind_approved_request(request, session)?;
        self.approved_request = Some(verifier);
        Ok(())
    }
    pub(super) fn ensure_approved_request(&self) -> Result<(), AgentPortError> {
        self.ensure_approved_creator()?;
        if let Some(session) = &self.approved_session {
            self.approved_request
                .as_ref()
                .ok_or_else(|| AgentPortError::Handler("approved request absent".into()))?
                .ensure_pair_alive_for_session(session)
                .map_err(|e| AgentPortError::Handler(format!("approved request refused: {e}")))?;
            if self.approved_uncertain {
                return Err(AgentPortError::Handler(
                    "approved actor requires effect reconciliation".into(),
                ));
            }
        }
        Ok(())
    }
    pub(super) fn refuse_uncontrolled_approved_request(&self) -> Result<(), AgentPortError> {
        self.ensure_approved_creator()?;
        if self.approved_session.is_some() {
            self.ensure_approved_request()?;
            return Err(AgentPortError::Handler(
                "approved actor requires its original controlled dispatch".into(),
            ));
        }
        Ok(())
    }
    pub(super) fn with_approved_pair<T>(
        &mut self,
        context: &DispatchContext,
        operation: impl FnOnce(
            &mut simulation::BrowserActor<simulation::engine_dispatch::EngineThreadRuntime>,
            &ProcfsPeerAttestor,
            &AttestedPeer,
            &ControlRequestVerifier,
        ) -> Result<T, AgentPortError>,
    ) -> Result<T, AgentPortError> {
        self.ensure_approved_creator()?;
        let session = self
            .approved_session
            .as_ref()
            .ok_or_else(|| AgentPortError::Handler("approved session absent".into()))?;
        let verifier = self
            .approved_request
            .as_ref()
            .ok_or_else(|| AgentPortError::Handler("approved request absent".into()))?;
        let inner = &mut self.inner;
        verifier
            .with_original_pair(session, |attestor, attested, custodian, ceiling| {
                if context.effective_deadline > ceiling {
                    return Err(AgentPortError::Handler(
                        "caller deadline exceeds approved original scope".into(),
                    ));
                }
                operation(inner, attestor, attested, custodian)
            })
            .map_err(|e| AgentPortError::Handler(format!("approved original pair refused: {e}")))?
    }
    pub(super) fn handle_approved_controlled(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<HandlerOutcome, AgentPortError> {
        self.ensure_approved_creator()?;
        let session = self
            .approved_session
            .as_ref()
            .ok_or_else(|| AgentPortError::Handler("approved session absent".into()))?;
        let verifier = self
            .approved_request
            .as_ref()
            .ok_or_else(|| AgentPortError::Handler("approved request absent".into()))?;
        let inner = &mut self.inner;
        let uncertain = &mut self.approved_uncertain;
        let mut outcome = None;
        let scoped =
            verifier.with_original_pair(session, |attestor, attested, custodian, ceiling| {
                if context.effective_deadline > ceiling {
                    return;
                }
                // Unwinding after entry leaves the actor closed. Only a known
                // current return can clear the latch.
                *uncertain = true;
                outcome =
                    Some(inner.handle_attested_controlled(
                        context, request, attestor, attested, custodian,
                    ));
            });
        match (scoped, outcome) {
            (Ok(()), Some(outcome)) => {
                self.approved_uncertain = match &outcome {
                    Ok(HandlerOutcome::Success(_)) => false,
                    Ok(HandlerOutcome::Failure(error)) => matches!(
                        error.code,
                        BrowserErrorCode::Indeterminate | BrowserErrorCode::BrowserCrashed
                    ),
                    Err(_) => true,
                };
                outcome
            }
            (Err(_), Some(outcome)) => {
                // Scope retirement after possible dispatch cannot erase the
                // core's unknown result or publish a known success/failure.
                self.approved_uncertain = true;
                if let Ok(HandlerOutcome::Failure(error)) = outcome
                    && matches!(
                        error.code,
                        BrowserErrorCode::Indeterminate | BrowserErrorCode::BrowserCrashed
                    )
                {
                    return Ok(HandlerOutcome::Failure(error));
                }
                Ok(HandlerOutcome::Failure(BrowserWireError {
                    code: BrowserErrorCode::Indeterminate,
                    message: "approved original scope retired after possible dispatch".into(),
                    details: None,
                }))
            }
            (Err(error), None) => Err(AgentPortError::Handler(format!(
                "approved original pair refused: {error}"
            ))),
            (Ok(()), None) => Err(AgentPortError::Handler(
                "caller deadline exceeds approved original scope".into(),
            )),
        }
    }
    fn ensure_approved_creator(&self) -> Result<(), AgentPortError> {
        if self.approved_creator_pid != std::process::id() {
            return Err(AgentPortError::Handler(
                "approved actor creating process changed".into(),
            ));
        }
        Ok(())
    }
}
