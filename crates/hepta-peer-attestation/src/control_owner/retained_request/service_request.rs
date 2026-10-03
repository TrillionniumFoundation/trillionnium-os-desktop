//! Private original SCM packing for the explicit service bridge.
//! No v1 approval guard or replacement Control/Agent deadline is manufactured.
use super::*;
use crate::approved_policy::{ApprovedPolicyError, ServiceSessionState};

fn service_error(error: ApprovedPolicyError) -> ControlOwnerError {
    match error {
        ApprovedPolicyError::DeadlineExceeded => ControlOwnerError::DeadlineExceeded,
        ApprovedPolicyError::ProcessChanged => ControlOwnerError::ProcessChanged,
        _ => ControlOwnerError::PeerRefused,
    }
}

impl AttestedHandoffReceiver {
    pub(in crate::control_owner) fn receive_service_control(
        &mut self,
        session: &ServiceSessionState,
    ) -> Result<ControlRetainedAcceptedStream, ControlOwnerError> {
        creator(self.owner_pid)?;
        let result = (|| {
            session.ensure_current().map_err(service_error)?;
            self.ensure_service_current(session)?;
            let wait = remaining(self.owner_pid, self.deadline)?;
            let transferred = self
                .channel
                .take()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .receive_retained_service_control(wait)
                .map_err(handoff)?;
            // Actual returned Pending owns the same creation-time Control
            // identity and already enables it for all packet/report paths.
            let (received, channel) = transferred.into_parts().map_err(handoff)?;
            let owner = self.owner.take().ok_or(ControlOwnerError::ChannelRetired)?;
            owner.current_for_service(session)?;
            let deadline = received.deadline().map_err(handoff)?;
            let effective = owner.request_deadline(deadline)?;
            let mut custody = ControlRequestCustody::from_control_peer(&owner.attested, effective)?;
            custody.retain_root_path(owner.root_path.as_ref())?;
            let action = custody.verifier()?;
            let mut retained = AttestedRetainedReceiver {
                owner_pid: self.owner_pid,
                deadline: self.deadline.min(deadline),
                owner: Some(owner),
                channel: Some(channel),
                action,
            };
            retained.ensure_current()?;
            session.ensure_current().map_err(service_error)?;
            let received = ControlRetainedAcceptedStream {
                owner_pid: self.owner_pid,
                received: Some(received),
                custody: Some(custody),
                retained: Some(retained),
            };
            received.deadline()?;
            Ok(received)
        })();
        self.retire()?;
        result
    }

    // Same original cancellation/retirement and deadline behavior as the complete
    // legacy ensure_current, combined with the actual full selected service check.
    pub(in crate::control_owner) fn ensure_service_current(
        &mut self,
        session: &ServiceSessionState,
    ) -> Result<Instant, ControlOwnerError> {
        creator(self.owner_pid)?;
        let result = if self.cancelled {
            Err(ControlOwnerError::Cancelled)
        } else {
            self.owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)
                .and_then(|owner| owner.current_for_service(session))
                .map(|_| self.deadline)
        };
        if result.is_err() {
            self.retire()?;
        }
        result
    }
}
