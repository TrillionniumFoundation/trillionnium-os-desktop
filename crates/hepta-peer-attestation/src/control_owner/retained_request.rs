//! Same-channel terminal reporting and remote cancellation. A peer report is
//! authenticated transport data, not proof about a local durable journal.

use super::{
    AttestedHandoffReceiver, AttestedHandoffSender, ControlOwnerError, ControlPeerOwner,
    ControlRequestCustody, ControlRequestVerifier, creator, handoff, remaining,
};
use hepta_agent_transport::{
    PendingHandoffReceiver, PendingHandoffSender, ReceivedAcceptedStream, RemoteRetirementReport,
    RemoteTerminalState,
};
use std::os::unix::net::UnixStream;
use std::time::Instant;

/// A report received from the original live approved control peer. This is a
/// remote assertion only: it is not a local journal fact, success, response
/// delivery, a replay permit or a semantic principal.
pub struct PeerReportedRetirement(RemoteRetirementReport);
impl PeerReportedRetirement {
    pub fn state(&self) -> RemoteTerminalState {
        self.0.state()
    }
    pub fn request_sha256(&self) -> [u8; 32] {
        self.0.request_sha256()
    }
    pub fn record_sha256(&self) -> [u8; 32] {
        self.0.record_sha256()
    }
}

/// Sender custody has already been consumed at the first native handoff.
/// This owner can request cancellation and read one report on the same
/// channel. It cannot send another accepted stream or renew the deadline.
pub struct AttestedPendingHandoff {
    owner_pid: u32,
    deadline: Instant,
    owner: Option<ControlPeerOwner>,
    channel: Option<PendingHandoffSender>,
}
impl AttestedPendingHandoff {
    pub fn ensure_current(&mut self) -> Result<Instant, ControlOwnerError> {
        creator(self.owner_pid)?;
        let checked = (|| {
            remaining(self.owner_pid, self.deadline)?;
            self.owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .current()?;
            let deadline = self
                .channel
                .as_mut()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .ensure_current()
                .map_err(handoff)?;
            remaining(self.owner_pid, self.deadline)?;
            Ok(self.deadline.min(deadline))
        })();
        if checked.is_err() {
            self.retire()?;
        }
        checked
    }
    pub fn request_cancel(&mut self) -> Result<(), ControlOwnerError> {
        creator(self.owner_pid)?;
        let checked = (|| {
            self.ensure_current()?;
            self.channel
                .as_mut()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .request_cancel()
                .map_err(handoff)?;
            self.ensure_current()?;
            Ok(())
        })();
        if checked.is_err() {
            self.retire()?;
        }
        checked
    }
    pub fn wait_retirement(&mut self) -> Result<PeerReportedRetirement, ControlOwnerError> {
        creator(self.owner_pid)?;
        let checked = (|| {
            self.ensure_current()?;
            let report = self
                .channel
                .as_mut()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .wait_report()
                .map_err(handoff)?;
            // The wire owner retires after the one report. Retain the original
            // live peer snapshot and outer ceiling through this last check.
            self.owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .current()?;
            remaining(self.owner_pid, self.deadline)?;
            Ok(PeerReportedRetirement(report))
        })();
        self.retire()?;
        checked
    }
    /// Nonblocking observation permits one owning thread to poll its own
    /// cancellation input between checks, without a duplicate control FD.
    pub fn poll_retirement(&mut self) -> Result<Option<PeerReportedRetirement>, ControlOwnerError> {
        creator(self.owner_pid)?;
        let checked = (|| {
            self.ensure_current()?;
            let report = self
                .channel
                .as_mut()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .poll_report()
                .map_err(handoff)?;
            self.owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .current()?;
            remaining(self.owner_pid, self.deadline)?;
            Ok(report.map(PeerReportedRetirement))
        })();
        if !matches!(&checked, Ok(None)) {
            self.retire()?;
        }
        checked
    }
    fn retire(&mut self) -> Result<(), ControlOwnerError> {
        creator(self.owner_pid)?;
        self.channel.take();
        self.owner.take();
        Ok(())
    }
}

/// Reporting identity is retained independently of the revocable execution
/// verifier. Revoking an action can never regrant it to send a terminal report.
/// `send_remote_report` accepts only remote-asserted transport data; trusted
/// journal association belongs to the coordinator, not this public API.
pub struct AttestedRetainedReceiver {
    owner_pid: u32,
    deadline: Instant,
    owner: Option<ControlPeerOwner>,
    channel: Option<PendingHandoffReceiver>,
    action: ControlRequestVerifier,
}
impl AttestedRetainedReceiver {
    pub fn ensure_current(&mut self) -> Result<Instant, ControlOwnerError> {
        creator(self.owner_pid)?;
        let checked = (|| {
            remaining(self.owner_pid, self.deadline)?;
            self.owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .current()?;
            let deadline = self
                .channel
                .as_mut()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .ensure_current()
                .map_err(handoff)?;
            remaining(self.owner_pid, self.deadline)?;
            Ok(self.deadline.min(deadline))
        })();
        if checked.is_err() {
            self.retire()?;
        }
        checked
    }
    pub fn poll_cancel(&mut self) -> Result<bool, ControlOwnerError> {
        creator(self.owner_pid)?;
        let checked = (|| {
            self.ensure_current()?;
            let cancelled = self
                .channel
                .as_mut()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .poll_cancel()
                .map_err(handoff)?;
            self.ensure_current()?;
            if cancelled {
                self.action.revoke_scope()?;
            }
            Ok(cancelled)
        })();
        if checked.is_err() {
            self.retire()?;
        }
        checked
    }
    pub fn send_remote_report(
        &mut self,
        report: RemoteRetirementReport,
    ) -> Result<(), ControlOwnerError> {
        creator(self.owner_pid)?;
        let checked = (|| {
            self.ensure_current()?;
            self.action.revoke_scope()?;
            self.channel
                .as_mut()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .send_report(report)
                .map_err(handoff)?;
            self.owner
                .as_ref()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .current()?;
            remaining(self.owner_pid, self.deadline)?;
            Ok(())
        })();
        self.retire()?;
        checked
    }
    fn retire(&mut self) -> Result<(), ControlOwnerError> {
        creator(self.owner_pid)?;
        self.action.revoke_scope()?;
        self.channel.take();
        self.owner.take();
        Ok(())
    }
}
impl Drop for AttestedRetainedReceiver {
    fn drop(&mut self) {
        // No inherited mutex, shutdown, peer PID lookup or parent mutation.
        if self.owner_pid == std::process::id() {
            let _ = self.action.revoke_scope();
        }
    }
}

/// Opaque original accepted socket and independent original report channel.
/// There is no report/durability constructor or replacement attestor here.
pub struct ControlRetainedAcceptedStream {
    owner_pid: u32,
    received: Option<ReceivedAcceptedStream>,
    custody: Option<ControlRequestCustody>,
    retained: Option<AttestedRetainedReceiver>,
}
impl ControlRetainedAcceptedStream {
    pub fn deadline(&self) -> Result<Instant, ControlOwnerError> {
        creator(self.owner_pid)?;
        let deadline = self
            .received
            .as_ref()
            .ok_or(ControlOwnerError::ChannelRetired)?
            .deadline()
            .map_err(handoff)?;
        let verifier = self
            .custody
            .as_ref()
            .ok_or(ControlOwnerError::ChannelRetired)?
            .verifier()?;
        let effective = verifier.deadline()?;
        if effective > deadline {
            return Err(ControlOwnerError::PeerRefused);
        }
        Ok(effective)
    }
    pub fn consume_before<T>(
        mut self,
        consumer: impl FnOnce(UnixStream, Instant, ControlRequestCustody, AttestedRetainedReceiver) -> T,
    ) -> Result<T, ControlOwnerError> {
        creator(self.owner_pid)?;
        let effective = self.deadline()?;
        self.retained
            .as_mut()
            .ok_or(ControlOwnerError::ChannelRetired)?
            .ensure_current()?;
        let received = self
            .received
            .take()
            .ok_or(ControlOwnerError::ChannelRetired)?;
        let custody = self
            .custody
            .take()
            .ok_or(ControlOwnerError::ChannelRetired)?;
        let retained = self
            .retained
            .take()
            .ok_or(ControlOwnerError::ChannelRetired)?;
        received
            .consume_before(|stream, _original| consumer(stream, effective, custody, retained))
            .map_err(handoff)
    }
}

impl AttestedHandoffSender {
    pub fn send_retained(&mut self) -> Result<AttestedPendingHandoff, ControlOwnerError> {
        creator(self.owner_pid)?;
        let result = (|| {
            self.ensure_current()?;
            // Both replay custody and the original channel transfer before the
            // first native send. Neither returns to the old sender on error.
            let custody = self
                .custody
                .take()
                .ok_or(ControlOwnerError::ChannelRetired)?;
            let channel = self
                .channel
                .take()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .send_retained(custody)
                .map_err(handoff)?;
            let owner = self.owner.take().ok_or(ControlOwnerError::ChannelRetired)?;
            owner.current()?;
            let mut pending = AttestedPendingHandoff {
                owner_pid: self.owner_pid,
                deadline: self.deadline,
                owner: Some(owner),
                channel: Some(channel),
            };
            pending.ensure_current()?;
            Ok(pending)
        })();
        self.retire()?;
        result
    }
}
impl AttestedHandoffReceiver {
    pub fn receive_retained_custodied(
        &mut self,
    ) -> Result<ControlRetainedAcceptedStream, ControlOwnerError> {
        creator(self.owner_pid)?;
        let result = (|| {
            self.ensure_current()?;
            let wait = remaining(self.owner_pid, self.deadline)?;
            let transferred = self
                .channel
                .take()
                .ok_or(ControlOwnerError::ChannelRetired)?
                .receive_retained(wait)
                .map_err(handoff)?;
            let (received, channel) = transferred.into_parts().map_err(handoff)?;
            let owner = self.owner.take().ok_or(ControlOwnerError::ChannelRetired)?;
            owner.current()?;
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
            let result = ControlRetainedAcceptedStream {
                owner_pid: self.owner_pid,
                received: Some(received),
                custody: Some(custody),
                retained: Some(retained),
            };
            result.deadline()?;
            Ok(result)
        })();
        self.retire()?;
        result
    }
}
