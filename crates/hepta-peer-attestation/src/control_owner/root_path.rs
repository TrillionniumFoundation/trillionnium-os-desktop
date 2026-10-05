//! A same-descriptor bridge, not an approved policy loader or installed broker.
//! No bare receive, replacement deadline, raw FD or static attestor is exposed.

mod approved;

use super::{
    AttestedHandoffReceiver, AttestedHandoffSender, AttestedPendingHandoff, ControlOwnerError,
    ControlOwnerPolicy, ControlPeerOwner, ControlRetainedAcceptedStream, creator, handoff,
    remaining,
};
use hepta_agent_transport::{
    AcceptedStreamCustody, HandoffReceiver, HandoffSender, RootControlPathCustody,
    RootControlPathError, RootControlPathVerifier, RootPathControlConnection,
};
use std::path::Path;
use std::sync::Arc;
use std::time::Instant;

fn path_error(error: RootControlPathError) -> ControlOwnerError {
    match error {
        RootControlPathError::DeadlineExceeded => ControlOwnerError::DeadlineExceeded,
        RootControlPathError::ProcessChanged => ControlOwnerError::ProcessChanged,
        _ => ControlOwnerError::PeerRefused,
    }
}

/// The unique pathname custody has one private shared lifetime owner. Execution
/// leases and reporting owners share this object, never clone its custody.
pub(super) struct RetainedRootPath {
    owner_pid: u32,
    deadline: Instant,
    _custody: RootControlPathCustody,
    verifier: RootControlPathVerifier,
}
impl RetainedRootPath {
    fn new(custody: RootControlPathCustody, deadline: Instant) -> Result<Self, ControlOwnerError> {
        let owner_pid = std::process::id();
        remaining(owner_pid, deadline)?;
        let verifier = custody.verifier().map_err(path_error)?;
        let result = Self {
            owner_pid,
            deadline,
            _custody: custody,
            verifier,
        };
        result.current()?;
        Ok(result)
    }
    pub(super) fn current(&self) -> Result<(), ControlOwnerError> {
        creator(self.owner_pid)?;
        remaining(self.owner_pid, self.deadline)?;
        self.verifier.verify_current().map_err(path_error)?;
        remaining(self.owner_pid, self.deadline)?;
        Ok(())
    }
}

/// Retained-only sender. Consumes the rooted connection's exact FD, fixed
/// Instant and unique path custody, and the existing accepted stream custody
/// with its original native ceiling. It never captures or rebudgets that stream.
/// Approved executable/unit policy remains an
/// explicit independently supplied input. No default product startup changes.
///
/// ```compile_fail
/// use hepta_peer_attestation::RootPathAttestedHandoffSender;
/// fn needs_clone<T: Clone>() {}
/// needs_clone::<RootPathAttestedHandoffSender>();
/// ```
pub struct RootPathAttestedHandoffSender {
    inner: AttestedHandoffSender,
}
impl RootPathAttestedHandoffSender {
    pub fn from_accepted(
        connection: RootPathControlConnection,
        accepted: AcceptedStreamCustody,
        policy: ControlOwnerPolicy,
    ) -> Result<Self, ControlOwnerError> {
        connection
            .consume_before(|control, deadline, custody| {
                let owner_pid = std::process::id();
                let path = Arc::new(RetainedRootPath::new(custody, deadline)?);
                path.current()?;
                let (mut owner, control, kernel) =
                    ControlPeerOwner::admit(control, policy, owner_pid, deadline)?;
                owner.root_path = Some(path);
                let channel = HandoffSender::from_control(control, kernel, owner.current()?)
                    .map_err(handoff)?;
                owner.current()?;
                Ok(Self {
                    inner: AttestedHandoffSender {
                        owner_pid,
                        deadline,
                        owner: Some(owner),
                        channel: Some(channel),
                        custody: Some(accepted),
                        cancelled: false,
                    },
                })
            })
            .map_err(path_error)?
    }
    /// Checks only the original root-control ceiling before publication. The
    /// opaque accepted scope is checked by the existing low-level send gate;
    /// the returned pending owner then checks the minimum of both ceilings.
    pub fn ensure_control_current(&mut self) -> Result<Instant, ControlOwnerError> {
        self.inner.ensure_current()
    }
    pub fn send_retained(&mut self) -> Result<AttestedPendingHandoff, ControlOwnerError> {
        self.inner.send_retained()
    }
    pub fn cancel(&mut self) -> Result<(), ControlOwnerError> {
        self.inner.cancel()
    }
}

/// Retained-only receiver. Its original control ceiling and path verifier flow
/// into request custody, Agent pairing, final-effect checks and terminal wait.
///
/// ```compile_fail
/// use hepta_peer_attestation::RootPathAttestedHandoffReceiver;
/// fn needs_clone<T: Clone>() {}
/// needs_clone::<RootPathAttestedHandoffReceiver>();
/// ```
pub struct RootPathAttestedHandoffReceiver {
    inner: AttestedHandoffReceiver,
}
impl RootPathAttestedHandoffReceiver {
    pub fn from_control(
        connection: RootPathControlConnection,
        policy: ControlOwnerPolicy,
        expected_local_path: &Path,
    ) -> Result<Self, ControlOwnerError> {
        connection
            .consume_before(|control, deadline, custody| {
                let owner_pid = std::process::id();
                let path = Arc::new(RetainedRootPath::new(custody, deadline)?);
                let (mut owner, control, kernel) =
                    ControlPeerOwner::admit(control, policy, owner_pid, deadline)?;
                owner.root_path = Some(path);
                let channel = HandoffReceiver::from_control(control, kernel, expected_local_path)
                    .map_err(handoff)?;
                owner.current()?;
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
    pub fn ensure_current(&mut self) -> Result<Instant, ControlOwnerError> {
        self.inner.ensure_current()
    }
    pub fn receive_retained_custodied(
        &mut self,
    ) -> Result<ControlRetainedAcceptedStream, ControlOwnerError> {
        self.inner.receive_retained_custodied()
    }
    pub fn cancel(&mut self) -> Result<(), ControlOwnerError> {
        self.inner.cancel()
    }
}

mod service_request;
