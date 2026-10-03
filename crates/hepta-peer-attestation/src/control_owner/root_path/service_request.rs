//! Private same-source service admission. Old rooted factories remain exact.
use super::*;
use crate::approved_policy::{ApprovedPolicyError, ServiceSessionState};
use std::time::Duration;

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
            .consume_service_control_before(|control, deadline, custody| {
                let owner_pid = std::process::id();
                session.original_owner_root_scope().map_err(service_error)?;
                let path = Arc::new(RetainedRootPath::new(custody, deadline)?);
                path.current()?;
                let policy = session.control_policy().map_err(service_error)?;
                let (mut owner, control, kernel) =
                    ControlPeerOwner::admit(control, policy, owner_pid, deadline)?;
                owner.root_path = Some(path);
                // Full same-source Owner and selected Control before challenge.
                owner.current_for_service(session)?;
                // Persistent service checks have no request clock; recheck the
                // original bounded Control scope immediately before challenge.
                remaining(owner_pid, deadline)?;
                let channel = HandoffReceiver::from_control(control, kernel, expected_agent_path)
                    .map_err(handoff)?;
                owner.current_for_service(session)?;
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

// Service-only composition of the original rooted Control and full selected
// Source/Owner check. It grants no action or replacement identity/deadline.
impl ControlPeerOwner {
    pub(in crate::control_owner) fn current_for_service(
        &self,
        session: &ServiceSessionState,
    ) -> Result<Duration, ControlOwnerError> {
        creator(self.owner_pid)?;
        remaining(self.owner_pid, self.deadline)?;
        // This route admits only the exact default-proc live service owner,
        // without a legacy approval guard or an unrooted substitute.
        if self.attestor.proc_root != Path::new("/proc")
            || !matches!(
                self.attested.executable_source,
                crate::ExecutableSource::Live
            )
            || !self.approved.is_empty()
        {
            return Err(ControlOwnerError::PeerRefused);
        }
        let path = self
            .root_path
            .as_ref()
            .ok_or(ControlOwnerError::PeerRefused)?;
        path.current()?;
        // The unchanged method performs full Source/Owner before and after
        // one fresh complete Control snapshot through the same original pidfd.
        session
            .verify_control(&self.attested)
            .map_err(service_error)?;
        path.current()?;
        remaining(self.owner_pid, self.deadline)
    }
}
