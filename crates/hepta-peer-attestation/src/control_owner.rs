//! Live control-custodian continuity around the existing descriptor protocol.
//! No listener, configurable procfs source, static attestation, principal,
//! daemon startup or native action authority is supplied here.

use crate::{AttestedPeer, PeerRuntimePolicy, ProcfsPeerAttestor};
use hepta_agent_transport::{
    AcceptedStreamCustody, HandoffError, HandoffReceiver, HandoffSender, MAX_HANDOFF_BUDGET,
    PeerIdentity, PeerPolicy, ReceivedAcceptedStream,
};
use std::fmt;
use std::os::fd::OwnedFd;
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::time::{Duration, Instant};

mod control_request;
mod retained_request;
mod root_path;
pub use control_request::{
    ControlReceivedAcceptedStream, ControlRequestCustody, ControlRequestVerifier,
};
pub use retained_request::{
    AttestedPendingHandoff, AttestedRetainedReceiver, ControlRetainedAcceptedStream,
    PeerReportedRetirement,
};
pub use root_path::{RootPathAttestedHandoffReceiver, RootPathAttestedHandoffSender};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ControlOwnerError {
    InvalidConfiguration,
    PeerRefused,
    DeadlineExceeded,
    ChannelRetired,
    Cancelled,
    ProcessChanged,
    HandoffRefused,
}
impl fmt::Display for ControlOwnerError {
    fn fmt(&self, output: &mut fmt::Formatter<'_>) -> fmt::Result {
        output.write_str(match self {
            Self::InvalidConfiguration => "invalid control-owner policy or budget",
            Self::PeerRefused => "live control-owner identity refused",
            Self::DeadlineExceeded => "original control-owner deadline expired",
            Self::ChannelRetired => "control-owner channel is retired",
            Self::Cancelled => "control-owner channel was cancelled",
            Self::ProcessChanged => "control-owner creating process changed",
            Self::HandoffRefused => "accepted-stream control handoff refused",
        })
    }
}
impl std::error::Error for ControlOwnerError {}

/// Explicit trusted-owner configuration, never approval received from a peer.
/// The digest is compared to bytes actually observed through fixed `/proc`.
/// This object supplies no authentication for the provisioning process itself.
#[derive(Clone)]
pub struct ControlOwnerPolicy {
    kernel: PeerPolicy,
    runtime: PeerRuntimePolicy,
    executable_sha256: String,
}
impl fmt::Debug for ControlOwnerPolicy {
    fn fmt(&self, output: &mut fmt::Formatter<'_>) -> fmt::Result {
        output.write_str("ControlOwnerPolicy(<redacted>)")
    }
}
impl ControlOwnerPolicy {
    pub fn new(
        kernel: PeerPolicy,
        runtime: PeerRuntimePolicy,
        approved_executable_sha256: String,
    ) -> Result<Self, ControlOwnerError> {
        if kernel.expected_uid != runtime.expected_uid
            || kernel.expected_gid != Some(runtime.expected_gid)
            || kernel.expected_pid == Some(0)
            || approved_executable_sha256.len() != 64
            || !approved_executable_sha256
                .bytes()
                .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value))
        {
            return Err(ControlOwnerError::InvalidConfiguration);
        }
        Ok(Self {
            kernel,
            runtime,
            executable_sha256: approved_executable_sha256,
        })
    }
}

fn creator(owner_pid: u32) -> Result<(), ControlOwnerError> {
    if owner_pid != std::process::id() {
        return Err(ControlOwnerError::ProcessChanged);
    }
    Ok(())
}
fn remaining(owner_pid: u32, deadline: Instant) -> Result<Duration, ControlOwnerError> {
    creator(owner_pid)?;
    deadline
        .checked_duration_since(Instant::now())
        .filter(|value| !value.is_zero())
        .ok_or(ControlOwnerError::DeadlineExceeded)
}
fn fixed_deadline(budget: Duration) -> Result<Instant, ControlOwnerError> {
    let started = Instant::now();
    if budget.is_zero() || budget > MAX_HANDOFF_BUDGET {
        return Err(ControlOwnerError::InvalidConfiguration);
    }
    started
        .checked_add(budget)
        .ok_or(ControlOwnerError::InvalidConfiguration)
}
fn handoff(error: HandoffError) -> ControlOwnerError {
    match error {
        HandoffError::DeadlineExceeded => ControlOwnerError::DeadlineExceeded,
        HandoffError::ProcessChanged => ControlOwnerError::ProcessChanged,
        _ => ControlOwnerError::HandoffRefused,
    }
}

struct ControlPeerOwner {
    owner_pid: u32,
    deadline: Instant,
    attestor: ProcfsPeerAttestor,
    attested: AttestedPeer,
    root_path: Option<std::sync::Arc<root_path::RetainedRootPath>>,
    approved: Vec<crate::approved_policy::ApprovedGuard>,
}
impl ControlPeerOwner {
    fn admit(
        control: OwnedFd,
        policy: ControlOwnerPolicy,
        owner_pid: u32,
        deadline: Instant,
    ) -> Result<(Self, OwnedFd, PeerPolicy), ControlOwnerError> {
        remaining(owner_pid, deadline)?;
        let stream = UnixStream::from(control);
        let peer =
            PeerIdentity::from_stream(&stream).map_err(|_| ControlOwnerError::PeerRefused)?;
        remaining(owner_pid, deadline)?;
        policy
            .kernel
            .authorize(peer)
            .map_err(|_| ControlOwnerError::PeerRefused)?;
        // This API deliberately cannot choose a test proc root or static source.
        let attestor = ProcfsPeerAttestor::default();
        let attested = attestor
            .attest(peer, &policy.runtime)
            .map_err(|_| ControlOwnerError::PeerRefused)?;
        remaining(owner_pid, deadline)?;
        if attested.snapshot().executable_sha256 != policy.executable_sha256 {
            return Err(ControlOwnerError::PeerRefused);
        }
        let owner = Self {
            owner_pid,
            deadline,
            attestor,
            attested,
            root_path: None,
            approved: Vec::new(),
        };
        owner.current()?;
        Ok((owner, OwnedFd::from(stream), PeerPolicy::exact(peer)))
    }
    fn current(&self) -> Result<Duration, ControlOwnerError> {
        remaining(self.owner_pid, self.deadline)?;
        if let Some(path) = &self.root_path {
            path.current()?;
        }
        for policy in &self.approved {
            policy.current()?;
        }
        self.attested
            .refresh_snapshot(&self.attestor)
            .map_err(|_| ControlOwnerError::PeerRefused)?;
        if let Some(path) = &self.root_path {
            path.current()?;
        }
        for policy in &self.approved {
            policy.current()?;
        }
        remaining(self.owner_pid, self.deadline)
    }
    // Denial-only reporting scope. The original action may already be revoked;
    // actual packet consumption and reporting still use complete current().
    fn idle_reporting_scope(&self) -> Result<Duration, ControlOwnerError> {
        remaining(self.owner_pid, self.deadline)?;
        let path = self
            .root_path
            .as_ref()
            .ok_or(ControlOwnerError::PeerRefused)?;
        path.current()?;
        if self.approved.is_empty() {
            return Err(ControlOwnerError::PeerRefused);
        }
        for policy in &self.approved {
            policy.verify_control_reporting_source(&self.attested)?;
        }
        self.attested
            .ensure_alive()
            .map_err(|_| ControlOwnerError::PeerRefused)?;
        path.current()?;
        for policy in &self.approved {
            policy.verify_control_reporting_source(&self.attested)?;
        }
        remaining(self.owner_pid, self.deadline)
    }
    fn request_deadline(&self, accepted: Instant) -> Result<Instant, ControlOwnerError> {
        creator(self.owner_pid)?;
        // Legacy channels keep their accepted ceiling. A rooted channel also
        // retains its already captured, possibly earlier pathname ceiling.
        Ok(if self.root_path.is_some() || !self.approved.is_empty() {
            self.current()?;
            accepted.min(self.deadline)
        } else {
            accepted
        })
    }
    fn retain_approved(
        &mut self,
        policy: &crate::approved_policy::ApprovedGuard,
    ) -> Result<(), ControlOwnerError> {
        creator(self.owner_pid)?;
        policy.current()?;
        if self.approved.len() >= 2 || self.approved.iter().any(|old| old.same_role(policy)) {
            return Err(ControlOwnerError::PeerRefused);
        }
        self.deadline = self.deadline.min(policy.deadline()?);
        self.approved.push(policy.clone());
        self.current()?;
        Ok(())
    }
}

/// One original accepted socket and one live control owner, with a fixed
/// absolute ingress ceiling captured before any control-peer attestation.
/// Not cloneable; send success is packet enqueue only, never an action receipt.
///
/// ```compile_fail
/// use hepta_peer_attestation::AttestedHandoffSender;
/// fn needs_clone<T: Clone>() {}
/// needs_clone::<AttestedHandoffSender>();
/// ```
pub struct AttestedHandoffSender {
    owner_pid: u32,
    deadline: Instant,
    owner: Option<ControlPeerOwner>,
    channel: Option<HandoffSender>,
    custody: Option<AcceptedStreamCustody>,
    cancelled: bool,
}
impl AttestedHandoffSender {
    pub fn from_accepted(
        control: OwnedFd,
        accepted: UnixStream,
        expected_local_path: &Path,
        policy: ControlOwnerPolicy,
        budget: Duration,
    ) -> Result<Self, ControlOwnerError> {
        let owner_pid = std::process::id();
        let deadline = fixed_deadline(budget)?;
        let custody =
            AcceptedStreamCustody::capture_before(accepted, expected_local_path, deadline)
                .map_err(handoff)?;
        let (owner, control, kernel) =
            ControlPeerOwner::admit(control, policy, owner_pid, deadline)?;
        let channel =
            HandoffSender::from_control(control, kernel, owner.current()?).map_err(handoff)?;
        // The low-level Duration handshake may resample its clock. This fixed
        // outer Instant is checked after it, never renewed by a late result.
        owner.current()?;
        Ok(Self {
            owner_pid,
            deadline,
            owner: Some(owner),
            channel: Some(channel),
            custody: Some(custody),
            cancelled: false,
        })
    }
    pub fn ensure_current(&mut self) -> Result<Instant, ControlOwnerError> {
        creator(self.owner_pid)?;
        let result = if self.cancelled {
            Err(ControlOwnerError::Cancelled)
        } else {
            self.owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)
                .and_then(|owner| owner.current())
                .map(|_| self.deadline)
        };
        if result.is_err() {
            self.retire()?;
        }
        result
    }
    pub fn send(&mut self) -> Result<(), ControlOwnerError> {
        creator(self.owner_pid)?;
        let result = (|| {
            self.ensure_current()?;
            // Retire local replay custody before any possible native enqueue.
            let custody = self
                .custody
                .take()
                .ok_or(ControlOwnerError::ChannelRetired)?;
            let sent = self
                .channel
                .as_mut()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .send(custody)
                .map_err(handoff);
            let checked = self
                .owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .current();
            sent?;
            checked?;
            Ok(())
        })();
        self.retire()?;
        result
    }
    /// Exclusive-owner cancellation; cannot concurrently interrupt a call
    /// already borrowing this owner mutably. No shutdown is performed.
    pub fn cancel(&mut self) -> Result<(), ControlOwnerError> {
        creator(self.owner_pid)?;
        self.cancelled = true;
        self.retire()
    }
    fn retire(&mut self) -> Result<(), ControlOwnerError> {
        creator(self.owner_pid)?;
        self.custody.take();
        self.channel.take();
        self.owner.take();
        Ok(())
    }
}

/// One live original control-custodian incarnation and independent fixed
/// control-wait ceiling. Returned custody retains its own original deadline.
/// This is not a retained native-effect authority or installed daemon owner.
pub struct AttestedHandoffReceiver {
    owner_pid: u32,
    deadline: Instant,
    owner: Option<ControlPeerOwner>,
    channel: Option<HandoffReceiver>,
    cancelled: bool,
}
impl AttestedHandoffReceiver {
    pub fn from_control(
        control: OwnedFd,
        policy: ControlOwnerPolicy,
        expected_local_path: &Path,
        budget: Duration,
    ) -> Result<Self, ControlOwnerError> {
        let owner_pid = std::process::id();
        let deadline = fixed_deadline(budget)?;
        let (owner, control, kernel) =
            ControlPeerOwner::admit(control, policy, owner_pid, deadline)?;
        let channel =
            HandoffReceiver::from_control(control, kernel, expected_local_path).map_err(handoff)?;
        owner.current()?;
        Ok(Self {
            owner_pid,
            deadline,
            owner: Some(owner),
            channel: Some(channel),
            cancelled: false,
        })
    }
    pub fn ensure_current(&mut self) -> Result<Instant, ControlOwnerError> {
        creator(self.owner_pid)?;
        let result = if self.cancelled {
            Err(ControlOwnerError::Cancelled)
        } else {
            self.owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)
                .and_then(|owner| owner.current())
                .map(|_| self.deadline)
        };
        if result.is_err() {
            self.retire()?;
        }
        result
    }
    pub fn receive(&mut self) -> Result<ReceivedAcceptedStream, ControlOwnerError> {
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
            self.owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .current()?;
            // This also validates the original socket and native clock scope.
            // No new Instant replaces that accepted transaction's deadline.
            received.deadline().map_err(handoff)?;
            remaining(self.owner_pid, self.deadline)?;
            Ok(received)
        })();
        // On late identity/deadline failure `received` above is dropped too.
        self.retire()?;
        result
    }
    pub fn cancel(&mut self) -> Result<(), ControlOwnerError> {
        creator(self.owner_pid)?;
        self.cancelled = true;
        self.retire()
    }
    fn retire(&mut self) -> Result<(), ControlOwnerError> {
        creator(self.owner_pid)?;
        self.channel.take();
        self.owner.take();
        Ok(())
    }
}
