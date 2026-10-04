//! Additive root-approved replacement; the ordinary binding remains fixed.
use super::*;
use hepta_peer_attestation::{ApprovedAgentRequestBinding, ApprovedAgentSession};

impl<R: PageRuntime> BrowserActor<R> {
    /// Change only the request mechanism after independently checking the
    /// opaque root-approved scope. Session, PageOwner and receipt state stay
    /// under the existing actor. Active or prepared requests refuse.
    pub fn rebind_approved_request(
        &mut self,
        request: &ApprovedAgentRequestBinding,
        session: &ApprovedAgentSession,
    ) -> Result<(), AgentPortError> {
        self.ensure_prepared_request_owner()?;
        if self.runtime_unavailable
            || !self.cancellation_tokens.is_empty()
            || !self.cancelled_requests.is_empty()
            || self.request_authority.borrow().is_some()
            || self.control_authority.borrow().is_some()
        {
            return Err(AgentPortError::Handler(
                "approved replacement conflicts with actor state".into(),
            ));
        }
        let (peer, snapshot, principal_id) = request
            .verify_for_session(session)
            .map_err(|e| AgentPortError::Handler(format!("approved replacement refused: {e}")))?;
        if self.binding.principal.principal_id != principal_id {
            return Err(AgentPortError::Handler(
                "approved semantic principal differs".into(),
            ));
        }
        let replacement =
            PrincipalBinding::bind_attested(self.binding.principal.clone(), peer, &snapshot)
                .map_err(|e| {
                    AgentPortError::Handler(format!("approved replacement binding refused: {e}"))
                })?;
        // Every fallible external observation precedes the only mutation.
        request
            .verify_for_session(session)
            .map_err(|e| AgentPortError::Handler(format!("approved replacement refused: {e}")))?;
        self.binding = replacement;
        Ok(())
    }
}
