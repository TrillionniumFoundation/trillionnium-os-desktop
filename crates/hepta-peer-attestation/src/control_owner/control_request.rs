//! Opaque pairing of one received original stream and the same live control
//! custodian. It supplies identity continuity, never an approval or principal.

use super::{AttestedHandoffReceiver, ControlOwnerError, creator, handoff, remaining};
use crate::{AttestedPeer, ExecutableSource, PeerRequestVerifier, ProcfsPeerAttestor};
use hepta_agent_transport::ReceivedAcceptedStream;
use std::fmt;
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Instant;

struct ControlLeaseState {
    owner_pid: u32,
    deadline: Instant,
    peer: AttestedPeer,
    revoked: AtomicBool,
    root_path: Option<Arc<super::root_path::RetainedRootPath>>,
}

/// One non-cloneable request owner. Dropping it revokes all retained verifiers.
/// Only the actual default-live control admission path can construct this type.
///
/// ```compile_fail
/// use hepta_peer_attestation::ControlRequestCustody;
/// fn clone_required<T: Clone>() {}
/// clone_required::<ControlRequestCustody>();
/// ```
pub struct ControlRequestCustody {
    state: Arc<ControlLeaseState>,
}
impl fmt::Debug for ControlRequestCustody {
    fn fmt(&self, out: &mut fmt::Formatter<'_>) -> fmt::Result {
        out.write_str("ControlRequestCustody(<redacted>)")
    }
}

/// Read-only verification of the exact original control-peer incarnation.
/// Cloning it cannot extend the original accepted-stream deadline or revive a
/// revoked owner. Methods refuse foreign creating PIDs before touching state.
#[derive(Clone)]
pub struct ControlRequestVerifier {
    state: Arc<ControlLeaseState>,
}
impl fmt::Debug for ControlRequestVerifier {
    fn fmt(&self, out: &mut fmt::Formatter<'_>) -> fmt::Result {
        out.write_str("ControlRequestVerifier(<redacted>)")
    }
}

impl ControlRequestCustody {
    pub(super) fn from_control_peer(
        peer: &AttestedPeer,
        deadline: Instant,
    ) -> Result<Self, ControlOwnerError> {
        let owner_pid = std::process::id();
        remaining(owner_pid, deadline)?;
        if peer.attestor.proc_root != Path::new("/proc")
            || !matches!(peer.executable_source, ExecutableSource::Live)
        {
            return Err(ControlOwnerError::PeerRefused);
        }
        peer.ensure_alive()
            .map_err(|_| ControlOwnerError::PeerRefused)?;
        // Duplicate the already retained pidfd, never look up a replacement PID.
        let original = AttestedPeer {
            snapshot: peer.snapshot.clone(),
            pidfd: peer
                .pidfd
                .try_clone()
                .map_err(|_| ControlOwnerError::PeerRefused)?,
            executable_source: peer.executable_source.clone(),
            attestor: ProcfsPeerAttestor::default(),
        };
        remaining(owner_pid, deadline)?;
        let custody = Self {
            state: Arc::new(ControlLeaseState {
                owner_pid,
                deadline,
                peer: original,
                revoked: AtomicBool::new(false),
                root_path: None,
            }),
        };
        custody.verifier()?.verify_current()?;
        Ok(custody)
    }

    pub(super) fn retain_root_path(
        &mut self,
        path: Option<&Arc<super::root_path::RetainedRootPath>>,
    ) -> Result<(), ControlOwnerError> {
        creator(self.state.owner_pid)?;
        if let Some(path) = path {
            path.current()?;
            Arc::get_mut(&mut self.state)
                .ok_or(ControlOwnerError::PeerRefused)?
                .root_path = Some(Arc::clone(path));
            self.verifier()?.verify_current()?;
        }
        Ok(())
    }

    pub fn verifier(&self) -> Result<ControlRequestVerifier, ControlOwnerError> {
        creator(self.state.owner_pid)?;
        let verifier = ControlRequestVerifier {
            state: self.state.clone(),
        };
        verifier.ensure_alive()?;
        Ok(verifier)
    }

    pub fn revoke(&self) -> Result<(), ControlOwnerError> {
        creator(self.state.owner_pid)?;
        self.state.revoked.store(true, Ordering::SeqCst);
        Ok(())
    }
}
impl Drop for ControlRequestCustody {
    fn drop(&mut self) {
        if self.state.owner_pid == std::process::id() {
            self.state.revoked.store(true, Ordering::SeqCst);
        }
        // Arc/OwnedFd destruction closes child descriptor copies only; no
        // shutdown, copied mutex, parent unlock or replacement process exists.
    }
}
impl ControlRequestVerifier {
    pub(super) fn revoke_scope(&self) -> Result<(), ControlOwnerError> {
        creator(self.state.owner_pid)?;
        self.state.revoked.store(true, Ordering::SeqCst);
        Ok(())
    }

    fn original_peer_result(
        &self,
        checked: Result<(), crate::AttestationError>,
    ) -> Result<(), ControlOwnerError> {
        creator(self.state.owner_pid)?;
        if checked.is_err() {
            self.state.revoked.store(true, Ordering::SeqCst);
            return Err(ControlOwnerError::PeerRefused);
        }
        self.ensure_alive()
    }

    /// Verify both opaque leases. Observed original-Agent loss also permanently
    /// retires this paired control scope; no caller boolean supplies a result.
    pub fn ensure_pair_alive(
        &self,
        original: &PeerRequestVerifier,
    ) -> Result<(), ControlOwnerError> {
        self.ensure_alive()?;
        self.original_peer_result(original.ensure_alive())
    }

    pub fn verify_pair_current(
        &self,
        original: &PeerRequestVerifier,
    ) -> Result<(), ControlOwnerError> {
        self.ensure_pair_alive(original)?;
        self.original_peer_result(original.verify_current())?;
        self.verify_current()?;
        self.ensure_pair_alive(original)
    }

    pub fn ensure_alive(&self) -> Result<(), ControlOwnerError> {
        creator(self.state.owner_pid)?;
        if self.state.revoked.load(Ordering::SeqCst) {
            return Err(ControlOwnerError::PeerRefused);
        }
        let checked = remaining(self.state.owner_pid, self.state.deadline).and_then(|_| {
            if let Some(path) = &self.state.root_path {
                path.current()?;
            }
            self.state
                .peer
                .ensure_alive()
                .map_err(|_| ControlOwnerError::PeerRefused)?;
            if let Some(path) = &self.state.root_path {
                path.current()?;
            }
            Ok(())
        });
        creator(self.state.owner_pid)?;
        if let Err(error) = checked {
            self.state.revoked.store(true, Ordering::SeqCst);
            return Err(error);
        }
        if self.state.revoked.load(Ordering::SeqCst) {
            return Err(ControlOwnerError::PeerRefused);
        }
        remaining(self.state.owner_pid, self.state.deadline)?;
        Ok(())
    }

    pub fn verify_current(&self) -> Result<(), ControlOwnerError> {
        self.ensure_alive()?;
        let checked = self.state.peer.refresh_snapshot(&self.state.peer.attestor);
        creator(self.state.owner_pid)?;
        if checked.is_err() {
            self.state.revoked.store(true, Ordering::SeqCst);
            return Err(ControlOwnerError::PeerRefused);
        }
        self.ensure_alive()
    }

    pub fn deadline(&self) -> Result<Instant, ControlOwnerError> {
        self.ensure_alive()?;
        Ok(self.state.deadline)
    }
}

/// Non-cloneable pairing produced only by `receive_custodied`. The callback
/// consumes the same original stream, absolute Instant and control custody.
pub struct ControlReceivedAcceptedStream {
    owner_pid: u32,
    received: Option<ReceivedAcceptedStream>,
    custody: Option<ControlRequestCustody>,
}
impl ControlReceivedAcceptedStream {
    fn new(
        received: ReceivedAcceptedStream,
        peer: &AttestedPeer,
    ) -> Result<Self, ControlOwnerError> {
        let owner_pid = std::process::id();
        let deadline = received.deadline().map_err(handoff)?;
        let custody = ControlRequestCustody::from_control_peer(peer, deadline)?;
        let result = Self {
            owner_pid,
            received: Some(received),
            custody: Some(custody),
        };
        result.deadline()?;
        Ok(result)
    }

    pub fn deadline(&self) -> Result<Instant, ControlOwnerError> {
        creator(self.owner_pid)?;
        let received = self
            .received
            .as_ref()
            .ok_or(ControlOwnerError::ChannelRetired)?;
        let verifier = self.control_verifier()?;
        let deadline = received.deadline().map_err(handoff)?;
        if deadline != verifier.deadline()? {
            return Err(ControlOwnerError::PeerRefused);
        }
        Ok(deadline)
    }

    pub fn control_verifier(&self) -> Result<ControlRequestVerifier, ControlOwnerError> {
        creator(self.owner_pid)?;
        self.custody
            .as_ref()
            .ok_or(ControlOwnerError::ChannelRetired)?
            .verifier()
    }

    pub fn consume_before<T>(
        mut self,
        consumer: impl FnOnce(UnixStream, Instant, ControlRequestCustody) -> T,
    ) -> Result<T, ControlOwnerError> {
        creator(self.owner_pid)?;
        self.deadline()?;
        self.control_verifier()?.verify_current()?;
        let received = self
            .received
            .take()
            .ok_or(ControlOwnerError::ChannelRetired)?;
        let custody = self
            .custody
            .take()
            .ok_or(ControlOwnerError::ChannelRetired)?;
        received
            .consume_before(|stream, deadline| consumer(stream, deadline, custody))
            .map_err(handoff)
    }
}

impl AttestedHandoffReceiver {
    /// Additive one-shot receive retaining the *original* default-live control
    /// pidfd and snapshot for the accepted transaction. No new attestation is
    /// substituted after retirement; the old `receive` API remains unchanged.
    pub fn receive_custodied(
        &mut self,
    ) -> Result<ControlReceivedAcceptedStream, ControlOwnerError> {
        creator(self.owner_pid)?;
        let result = (|| {
            self.ensure_current()?;
            let wait = remaining(self.owner_pid, self.deadline)?;
            let received = self
                .channel
                .as_mut()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .receive(wait)
                .map_err(handoff)?;
            let owner = self
                .owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)?;
            owner.current()?;
            let result = ControlReceivedAcceptedStream::new(received, &owner.attested)?;
            remaining(self.owner_pid, self.deadline)?;
            result.deadline()?;
            Ok(result)
        })();
        self.retire()?;
        result
    }
}
