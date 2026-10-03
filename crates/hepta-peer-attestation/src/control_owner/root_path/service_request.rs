//! Private same-source service admission. Old rooted factories remain exact.
use super::*;
use crate::approved_policy::{ApprovedPolicyError, ServiceSessionState};

fn service_error(error: ApprovedPolicyError) -> ControlOwnerError {
    match error {
        ApprovedPolicyError::DeadlineExceeded => ControlOwnerError::DeadlineExceeded,
        ApprovedPolicyError::ProcessChanged => ControlOwnerError::ProcessChanged,
        _ => ControlOwnerError::PeerRefused,
    }
}

impl RootPathAttestedHandoffReceiver {
    pub(crate) fn from_service_control(
        connection: RootPathControlConnection,
        session: &ServiceSessionState,
        expected_agent_path: &Path,
    ) -> Result<Self, ControlOwnerError> {
        session.ensure_current().map_err(service_error)?;
        connection
            .consume_before(|control, deadline, custody| {
                let owner_pid = std::process::id();
                session.ensure_current().map_err(service_error)?;
                let path = Arc::new(RetainedRootPath::new(custody, deadline)?);
                path.current()?;
                let policy = session.control_policy().map_err(service_error)?;
                let (mut owner, control, kernel) =
                    ControlPeerOwner::admit(control, policy, owner_pid, deadline)?;
                owner.root_path = Some(path);
                owner.current()?;
                // Full same-source Owner and selected Control before challenge.
                session
                    .verify_control(&owner.attested)
                    .map_err(service_error)?;
                // Persistent service checks have no request clock; recheck the
                // original bounded Control scope immediately before challenge.
                remaining(owner_pid, deadline)?;
                let channel = HandoffReceiver::from_control(control, kernel, expected_agent_path)
                    .map_err(handoff)?;
                owner.current()?;
                session
                    .verify_control(&owner.attested)
                    .map_err(service_error)?;
                Ok(Self {
                    inner: AttestedHandoffReceiver {
                        owner_pid,
                        deadline,
                        owner: Some(owner),
                        channel: Some(channel),
                        cancelled: false,
                    },
                })
            })
            .map_err(path_error)?
    }

    pub(crate) fn receive_service_control(
        &mut self,
        session: &ServiceSessionState,
    ) -> Result<ControlRetainedAcceptedStream, ControlOwnerError> {
        session.ensure_current().map_err(service_error)?;
        let received = self.inner.receive_service_control(session)?;
        session.ensure_current().map_err(service_error)?;
        Ok(received)
    }
}
