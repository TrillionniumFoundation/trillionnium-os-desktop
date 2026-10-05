//! Root-configured retained ingress. No listener creation, supplied principal,
//! substitute attestor, native construction or installed activation occurs here.

use super::{ApprovedRetainedAdmission, ProductDispatchError};
use hepta_agent_transport::{RootControlPathError, RootPathControlConnection};
use hepta_peer_attestation::{
    ApprovedPolicyDocument, ApprovedPolicyError, ControlOwnerError, RootPathAttestedHandoffReceiver,
};
use std::path::Path;
use std::time::Instant;

/// One root-configured original control connection. Both role selections come
/// from the same retained document, not another read of an equivalent pathname.
/// A successful admission moves its original stream and private monitor intact.
///
/// ```compile_fail
/// use hepta_browserd::ConfiguredRetainedBootstrap;
/// fn requires_clone<T: Clone>() {}
/// requires_clone::<ConfiguredRetainedBootstrap>();
/// ```
pub struct ConfiguredRetainedBootstrap {
    creator_pid: u32,
    original_deadline: Instant,
    document: ApprovedPolicyDocument,
    receiver: RootPathAttestedHandoffReceiver,
}

impl ConfiguredRetainedBootstrap {
    /// Read only the fixed root-owned product policy at the original connection
    /// deadline. Missing policy refuses; no observed identity creates approval.
    pub fn from_control(
        connection: RootPathControlConnection,
        expected_agent_path: &Path,
    ) -> Result<Self, ProductDispatchError> {
        let deadline = connection.deadline().map_err(path_error)?;
        let document =
            ApprovedPolicyDocument::open_default_before(deadline).map_err(policy_error)?;
        Self::from_root_document(connection, expected_agent_path, document)
    }

    /// Explicit root document for a configured installation or qualification.
    /// The opaque type itself enforces root pathname/file custody; this API
    /// accepts neither policy text nor an observed peer/principal tuple.
    pub fn from_root_document(
        connection: RootPathControlConnection,
        expected_agent_path: &Path,
        document: ApprovedPolicyDocument,
    ) -> Result<Self, ProductDispatchError> {
        let creator_pid = std::process::id();
        let original_deadline = connection.deadline().map_err(path_error)?;
        document.ensure_current().map_err(policy_error)?;
        let receiver = document
            .select_control()
            .map_err(policy_error)?
            .bind_receiver(connection, expected_agent_path)
            .map_err(policy_error)?;
        let mut value = Self {
            creator_pid,
            original_deadline,
            document,
            receiver,
        };
        value.ensure_current()?;
        Ok(value)
    }

    /// The connection's initial Instant never changes. A shorter document
    /// ceiling can refuse earlier; this return does not renew either scope.
    pub fn original_deadline(&mut self) -> Result<Instant, ProductDispatchError> {
        self.ensure_current()?;
        Ok(self.original_deadline)
    }

    fn ensure_current(&mut self) -> Result<(), ProductDispatchError> {
        if self.creator_pid != std::process::id() {
            return Err(ProductDispatchError::PeerRefused);
        }
        self.document.ensure_current().map_err(policy_error)?;
        let current = self.receiver.ensure_current().map_err(control_error)?;
        if current > self.original_deadline {
            return Err(ProductDispatchError::PeerRefused);
        }
        Ok(())
    }

    /// Consume exactly one original SCM_RIGHTS handoff. The existing admission
    /// rechecks both approved roles and retains the same terminal report owner.
    /// No AgentPort handshake, journal or native effect is produced here; the
    /// existing Control protocol has already performed its original challenge.
    pub fn into_admission(mut self) -> Result<ApprovedRetainedAdmission, ProductDispatchError> {
        self.ensure_current()?;
        let agent = self.document.select_agent().map_err(policy_error)?;
        let received = self
            .receiver
            .receive_retained_custodied()
            .map_err(control_error)?;
        // The legacy receiver has transferred its unique channel/owner into
        // `received` and is permanently retired. Rechecking that empty receiver
        // would refuse every valid transfer. Check the moved scope instead.
        self.document.ensure_current().map_err(policy_error)?;
        if received.deadline().map_err(control_error)? > self.original_deadline {
            return Err(ProductDispatchError::PeerRefused);
        }
        let admission = ApprovedRetainedAdmission::from_received(received, agent)?;
        if admission.deadline()? > self.original_deadline {
            return Err(ProductDispatchError::PeerRefused);
        }
        self.document.ensure_current().map_err(policy_error)?;
        Ok(admission)
    }
}

fn path_error(error: RootControlPathError) -> ProductDispatchError {
    match error {
        RootControlPathError::DeadlineExceeded => ProductDispatchError::DeadlineExceeded,
        _ => ProductDispatchError::PeerRefused,
    }
}
fn policy_error(error: ApprovedPolicyError) -> ProductDispatchError {
    match error {
        ApprovedPolicyError::DeadlineExceeded => ProductDispatchError::DeadlineExceeded,
        ApprovedPolicyError::InvalidConfiguration => ProductDispatchError::InvalidConfiguration,
        _ => ProductDispatchError::PeerRefused,
    }
}
fn control_error(error: ControlOwnerError) -> ProductDispatchError {
    match error {
        ControlOwnerError::DeadlineExceeded => ProductDispatchError::DeadlineExceeded,
        _ => ProductDispatchError::PeerRefused,
    }
}
