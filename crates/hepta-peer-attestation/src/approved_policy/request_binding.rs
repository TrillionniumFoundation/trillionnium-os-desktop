//! An approved session retains the root source, never an expired previous
//! request's peer. Each replacement carries its own original live pair.
use super::*;
use crate::{ControlRequestVerifier, PeerRequestCustody, PeerRequestVerifier, PeerRuntimeSnapshot};

/// Non-cloneable proof from consuming one root-approved original stream.
/// A raw principal, snapshot, PID or digest cannot construct this type.
///
/// ```compile_fail
/// use hepta_peer_attestation::ApprovedAgentRequestBinding;
/// fn requires_clone<T: Clone>() {}
/// requires_clone::<ApprovedAgentRequestBinding>();
/// ```
pub struct ApprovedAgentRequestBinding {
    owner_pid: u32,
    guard: ApprovedGuard,
    deadline: Instant,
    peer: PeerIdentity,
    snapshot: PeerRuntimeSnapshot,
    original: PeerRequestCustody,
    control: ControlRequestVerifier,
}

/// Root-selected semantic scope with the first original absolute ceiling.
/// This retains neither the first Agent nor its retired Control request.
///
/// ```compile_fail
/// use hepta_peer_attestation::ApprovedAgentSession;
/// fn requires_clone<T: Clone>() {}
/// requires_clone::<ApprovedAgentSession>();
/// ```
pub struct ApprovedAgentSession {
    owner_pid: u32,
    guard: ApprovedGuard,
    deadline: Instant,
}

/// Read-only verifier of one original request. Dropping its non-cloneable
/// binding/custody retires it; retaining this value cannot extend authority.
///
/// ```compile_fail
/// use hepta_peer_attestation::ApprovedAgentRequestVerifier;
/// fn requires_clone<T: Clone>() {}
/// requires_clone::<ApprovedAgentRequestVerifier>();
/// ```
pub struct ApprovedAgentRequestVerifier {
    owner_pid: u32,
    guard: ApprovedGuard,
    deadline: Instant,
    original: PeerRequestVerifier,
    control: ControlRequestVerifier,
}
impl ApprovedAgentRequestVerifier {
    /// Borrow only the privately retained original identities for a controlled
    /// dispatcher. Callback data are not a full attestation or an action permit.
    /// The dispatcher must perform full current readback through these sources.
    pub fn with_original_pair<T>(
        &self,
        session: &ApprovedAgentSession,
        consumer: impl FnOnce(&ProcfsPeerAttestor, &AttestedPeer, &ControlRequestVerifier, Instant) -> T,
    ) -> Result<T, ApprovedPolicyError> {
        self.ensure_pair_alive_for_session(session)?;
        let original = self
            .original
            .original_attested_peer()
            .map_err(|_| ApprovedPolicyError::PeerRefused)?;
        let result = consumer(
            &ProcfsPeerAttestor::default(),
            original,
            &self.control,
            self.deadline.min(session.deadline),
        );
        self.ensure_pair_alive_for_session(session)?;
        Ok(result)
    }
    /// Cheap gate for a controlled dispatcher which separately performs full
    /// current Agent/Control attestation before admission and runtime effect.
    pub fn ensure_pair_alive_for_session(
        &self,
        session: &ApprovedAgentSession,
    ) -> Result<(), ApprovedPolicyError> {
        remaining(self.owner_pid, self.deadline)?;
        remaining(session.owner_pid, session.deadline)?;
        session.guard.state.inspect()?;
        self.guard.state.inspect()?;
        if self.owner_pid != session.owner_pid
            || self.deadline > session.deadline
            || self.guard.role != 1
            || session.guard.role != 1
            || self.guard.state.entries != session.guard.state.entries
        {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        self.control
            .ensure_pair_alive(&self.original)
            .map_err(approval_error)?;
        session.guard.state.inspect()?;
        remaining(session.owner_pid, session.deadline)
    }
    pub fn verify_for_session(
        &self,
        session: &ApprovedAgentSession,
    ) -> Result<(), ApprovedPolicyError> {
        remaining(self.owner_pid, self.deadline)?;
        remaining(session.owner_pid, session.deadline)?;
        session.guard.state.inspect()?;
        self.guard.state.inspect()?;
        if self.owner_pid != session.owner_pid
            || self.deadline > session.deadline
            || self.guard.role != 1
            || session.guard.role != 1
            || self.guard.state.entries != session.guard.state.entries
        {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        self.control
            .verify_pair_current(&self.original)
            .map_err(approval_error)?;
        session.guard.state.inspect()?;
        remaining(session.owner_pid, session.deadline)
    }
}

impl ApprovedAgentReceivedStream {
    /// Consume the same admitted stream once and carry a privately minted
    /// binding alongside the original custody. The legacy callback is unchanged.
    pub fn consume_with_request_binding<T>(
        self,
        consumer: impl FnOnce(
            UnixStream,
            Instant,
            ControlRequestCustody,
            AttestedRetainedReceiver,
            AttestedPeer,
            &str,
            ApprovedAgentRequestBinding,
        ) -> T,
    ) -> Result<T, ApprovedPolicyError> {
        self.guard.state.inspect()?;
        remaining(self.guard.state.pid, self.deadline)?;
        let original = self
            .attested
            .request_custody()
            .map_err(|_| ApprovedPolicyError::PeerRefused)?;
        let control = self.custody.verifier().map_err(approval_error)?;
        let peer = PeerIdentity::from_stream(&self.stream)
            .map_err(|_| ApprovedPolicyError::PeerRefused)?;
        let snapshot = self.attested.snapshot().clone();
        if peer.pid != Some(snapshot.pid) || peer.uid != snapshot.uid || peer.gid != snapshot.gid {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        let binding = ApprovedAgentRequestBinding {
            owner_pid: self.guard.state.pid,
            guard: self.guard.clone(),
            deadline: self.deadline,
            peer,
            snapshot,
            original,
            control,
        };
        self.consume_before(|stream, deadline, custody, retained, attested, principal| {
            consumer(
                stream, deadline, custody, retained, attested, principal, binding,
            )
        })
    }
}
impl ApprovedAgentRequestBinding {
    fn verify_current(&self) -> Result<(), ApprovedPolicyError> {
        remaining(self.owner_pid, self.deadline)?;
        self.guard.state.inspect()?;
        self.control
            .verify_pair_current(&self.original.verifier())
            .map_err(approval_error)?;
        self.guard.state.inspect()?;
        remaining(self.owner_pid, self.deadline)
    }
    pub fn start_session(&self) -> Result<ApprovedAgentSession, ApprovedPolicyError> {
        remaining(self.owner_pid, self.deadline)?;
        self.guard.state.inspect()?;
        self.control
            .ensure_pair_alive(&self.original.verifier())
            .map_err(approval_error)?;
        Ok(ApprovedAgentSession {
            owner_pid: self.owner_pid,
            guard: self.guard.clone(),
            deadline: self.deadline,
        })
    }
    pub fn verifier_for_session(
        &self,
        session: &ApprovedAgentSession,
    ) -> Result<ApprovedAgentRequestVerifier, ApprovedPolicyError> {
        remaining(self.owner_pid, self.deadline)?;
        let verifier = ApprovedAgentRequestVerifier {
            owner_pid: self.owner_pid,
            guard: self.guard.clone(),
            deadline: self.deadline,
            original: self.original.verifier(),
            control: self.control.clone(),
        };
        verifier.ensure_pair_alive_for_session(session)?;
        Ok(verifier)
    }
    /// Compare both complete selected role entries (all thirteen schema fields),
    /// then verify this request's own original live Control/Agent pair. Returned
    /// data alone cannot mint a session or rebind the production actor.
    pub fn verify_for_session(
        &self,
        session: &ApprovedAgentSession,
    ) -> Result<(PeerIdentity, PeerRuntimeSnapshot, String), ApprovedPolicyError> {
        remaining(self.owner_pid, self.deadline)?;
        remaining(session.owner_pid, session.deadline)?;
        session.guard.state.inspect()?;
        self.guard.state.inspect()?;
        if self.owner_pid != session.owner_pid
            || self.deadline > session.deadline
            || self.guard.role != 1
            || session.guard.role != 1
            || self.guard.state.entries != session.guard.state.entries
        {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        self.verify_current()?;
        session.guard.state.inspect()?;
        remaining(session.owner_pid, session.deadline)?;
        Ok((
            self.peer,
            self.snapshot.clone(),
            self.guard.state.entries[1].principal.clone(),
        ))
    }
}
