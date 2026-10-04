//! One descriptor submission's retained control sideband. Reports are remote
//! assertions, never local journal facts or execution/approval authority.

use super::{
    AcceptedStreamCustody, ControlChannel, HandoffError, HandoffReceiver, HandoffSender,
    ReceivedAcceptedStream, SocketIdentity, TimeNamespace, check_time, instant_deadline,
    receive_packet, send_packet, wait_readable,
};
use std::fs;
use std::os::fd::RawFd;
use std::time::Instant;

const SIDEBAND_MAGIC: &[u8; 8] = b"HPTAFDS1";
const SIDEBAND_BYTES: usize = 192;
const CANCEL: u8 = 1;
const REPORT: u8 = 2;

/// Remote-asserted lifecycle classification. Completed deliberately does not
/// distinguish application success, failure, refusal or cancellation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RemoteTerminalState {
    Completed,
    Interrupted,
    Indeterminate,
}

/// Bounded transport data declared by the remote peer, not a durable receipt.
/// Public construction does not attest a journal, response or delivered effect.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RemoteRetirementReport {
    state: RemoteTerminalState,
    request_sha256: [u8; 32],
    record_sha256: [u8; 32],
}
impl RemoteRetirementReport {
    pub fn new(
        state: RemoteTerminalState,
        request_sha256: [u8; 32],
        record_sha256: [u8; 32],
    ) -> Result<Self, HandoffError> {
        if request_sha256 == [0; 32] || record_sha256 == [0; 32] {
            return Err(HandoffError::ProtocolRefused);
        }
        Ok(Self {
            state,
            request_sha256,
            record_sha256,
        })
    }
    pub const fn state(&self) -> RemoteTerminalState {
        self.state
    }
    pub const fn request_sha256(&self) -> [u8; 32] {
        self.request_sha256
    }
    pub const fn record_sha256(&self) -> [u8; 32] {
        self.record_sha256
    }
}

struct Transaction {
    channel: ControlChannel,
    nonce: [u8; 32],
    sequence: u64,
    identity: SocketIdentity,
    boot: [u8; 16],
    time_namespace: TimeNamespace,
    _namespace_file: fs::File,
    started: u64,
    monotonic_deadline: u64,
    deadline: Instant,
    readiness_enabled: bool,
}
impl Transaction {
    fn verify(&self) -> Result<RawFd, HandoffError> {
        self.verify_channel(&self.channel)
    }
    fn verify_channel(&self, channel: &ControlChannel) -> Result<RawFd, HandoffError> {
        // Fork refusal precedes every clock, identity and descriptor access.
        channel.owner()?;
        let fd = channel.verify()?;
        if self.readiness_enabled {
            channel.original_identity.verify(fd)?;
        }
        check_time(
            &self.boot,
            self.time_namespace,
            self.started,
            self.monotonic_deadline,
        )?;
        if Instant::now() >= self.deadline {
            return Err(HandoffError::DeadlineExceeded);
        }
        if self.readiness_enabled {
            channel.original_identity.verify(fd)?;
        }
        Ok(fd)
    }
    fn take_channel(&mut self) -> Result<ControlChannel, HandoffError> {
        self.channel.owner()?;
        let stream = self
            .channel
            .stream
            .take()
            .ok_or(HandoffError::ChannelRetired)?;
        Ok(ControlChannel {
            stream: Some(stream),
            owner_pid: self.channel.owner_pid,
            peer: self.channel.peer,
            policy: self.channel.policy,
            original_identity: self.channel.original_identity,
        })
    }
    fn ensure_current(&mut self) -> Result<Instant, HandoffError> {
        self.channel.owner()?;
        match self.verify() {
            Ok(_) => Ok(self.deadline),
            Err(error) => {
                self.channel.retire();
                Err(error)
            }
        }
    }
    fn encode(&self, kind: u8, report: Option<RemoteRetirementReport>) -> [u8; SIDEBAND_BYTES] {
        let mut data = [0; SIDEBAND_BYTES];
        data[..8].copy_from_slice(SIDEBAND_MAGIC);
        data[8..10].copy_from_slice(&1u16.to_be_bytes());
        data[10] = kind;
        data[16..24].copy_from_slice(&self.sequence.to_be_bytes());
        data[24..40].copy_from_slice(&self.boot);
        for (offset, value) in [
            (40, self.started),
            (48, self.monotonic_deadline),
            (56, self.identity.cookie),
            (64, self.identity.device),
            (72, self.identity.inode),
            (80, self.time_namespace.device),
            (88, self.time_namespace.inode),
        ] {
            data[offset..offset + 8].copy_from_slice(&value.to_be_bytes());
        }
        data[96..128].copy_from_slice(&self.nonce);
        if let Some(report) = report {
            data[11] = match report.state {
                RemoteTerminalState::Completed => 1,
                RemoteTerminalState::Interrupted => 2,
                RemoteTerminalState::Indeterminate => 3,
            };
            data[128..160].copy_from_slice(&report.request_sha256);
            data[160..192].copy_from_slice(&report.record_sha256);
        }
        data
    }
    fn receive(
        &self,
        channel: &ControlChannel,
        kind: u8,
    ) -> Result<Option<RemoteRetirementReport>, HandoffError> {
        let fd = self.verify_channel(channel)?;
        let mut data = [0; SIDEBAND_BYTES];
        let message = receive_packet(fd, &mut data)?;
        if message.length == 0 {
            return Err(HandoffError::ConnectionClosed);
        }
        // The existing parser first owns every delivered rights/pidfd, so any
        // sideband refusal still cleans the entire actual ancillary delivery.
        if message.length != data.len()
            || message.flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
            || message.invalid
            || message.rights_count != 0
            || message.credentials != Some(channel.peer)
        {
            return Err(HandoffError::ProtocolRefused);
        }
        self.verify_channel(channel)?;
        let expected = self.encode(kind, None);
        if data[..11] != expected[..11] || data[12..128] != expected[12..128] {
            return Err(HandoffError::ProtocolRefused);
        }
        if kind == CANCEL {
            if data[11] != 0 || data[128..] != [0; 64] {
                return Err(HandoffError::ProtocolRefused);
            }
            self.verify_channel(channel)?;
            return Ok(None);
        }
        let state = match data[11] {
            1 => RemoteTerminalState::Completed,
            2 => RemoteTerminalState::Interrupted,
            3 => RemoteTerminalState::Indeterminate,
            _ => return Err(HandoffError::ProtocolRefused),
        };
        let mut request_sha256 = [0; 32];
        let mut record_sha256 = [0; 32];
        request_sha256.copy_from_slice(&data[128..160]);
        record_sha256.copy_from_slice(&data[160..192]);
        let report = RemoteRetirementReport::new(state, request_sha256, record_sha256)?;
        self.verify_channel(channel)?;
        Ok(Some(report))
    }
}

/// One submitted original socket's retained sender endpoint. No custody,
/// raw channel, challenge, sequence reset or resend is exposed.
pub struct PendingHandoffSender {
    transaction: Transaction,
    cancellation_attempted: bool,
}
impl PendingHandoffSender {
    pub fn ensure_current(&mut self) -> Result<Instant, HandoffError> {
        self.transaction.ensure_current()
    }
    pub fn deadline(&mut self) -> Result<Instant, HandoffError> {
        self.ensure_current()
    }
    /// Publish at most one cancellation request. This is no proof of an effect
    /// barrier, undo, application cancellation or remote acknowledgment.
    pub fn request_cancel(&mut self) -> Result<(), HandoffError> {
        self.transaction.channel.owner()?;
        let result = (|| {
            self.transaction.verify()?;
            if self.cancellation_attempted {
                return Err(HandoffError::ProtocolRefused);
            }
            // Consume before the first potentially ambiguous sendmsg.
            self.cancellation_attempted = true;
            let data = self.transaction.encode(CANCEL, None);
            send_packet(self.transaction.verify()?, &data, None)?;
            self.transaction.verify()?;
            Ok(())
        })();
        if result.is_err() {
            self.transaction.channel.retire();
        }
        result
    }
    /// Wait once within the original accepted socket's fixed deadline. Success
    /// is a remote assertion received here, never a local durable fact.
    pub fn wait_report(&mut self) -> Result<RemoteRetirementReport, HandoffError> {
        self.transaction.channel.owner()?;
        // The local owner closes on every return or unwind. The stored endpoint
        // is already retired before waiting/receiving, so it cannot wait twice.
        let channel = self.transaction.take_channel()?;
        let fd = self.transaction.verify_channel(&channel)?;
        wait_readable(fd, self.transaction.deadline)?;
        self.transaction
            .receive(&channel, REPORT)?
            .ok_or(HandoffError::ProtocolRefused)
    }
    /// Nonblocking alternative for an exclusive custodian command loop. An
    /// absent packet preserves the same deadline and permits one later cancel;
    /// a received report consumes this endpoint before delivery to the caller.
    pub fn poll_report(&mut self) -> Result<Option<RemoteRetirementReport>, HandoffError> {
        self.transaction.channel.owner()?;
        let result = (|| {
            if !readable_now(self.transaction.verify()?)? {
                self.transaction.verify()?;
                return Ok(None);
            }
            let channel = self.transaction.take_channel()?;
            let report = self
                .transaction
                .receive(&channel, REPORT)?
                .ok_or(HandoffError::ProtocolRefused)?;
            Ok(Some(report))
        })();
        if result.is_err() {
            self.transaction.channel.retire();
        }
        result
    }
}

/// One received socket's retained reply/cancellation endpoint. It cannot
/// reconstruct a socket or promote remote data into journal authority.
pub struct PendingHandoffReceiver {
    transaction: Transaction,
    cancellation_received: bool,
    report_attempted: bool,
}
impl PendingHandoffReceiver {
    pub fn ensure_current(&mut self) -> Result<Instant, HandoffError> {
        self.transaction.ensure_current()
    }
    pub fn deadline(&mut self) -> Result<Instant, HandoffError> {
        self.ensure_current()
    }
    /// Nonblocking poll of one original peer cancellation. Repeated, malformed
    /// or descriptor-bearing packets permanently retire this endpoint.
    pub fn poll_cancel(&mut self) -> Result<bool, HandoffError> {
        self.transaction.channel.owner()?;
        let result = (|| {
            let fd = self.transaction.verify()?;
            if !readable_now(fd)? {
                self.transaction.verify()?;
                return Ok(false);
            }
            self.transaction
                .receive(&self.transaction.channel, CANCEL)?;
            if self.cancellation_received {
                return Err(HandoffError::ProtocolRefused);
            }
            self.cancellation_received = true;
            self.transaction.verify()?;
            Ok(true)
        })();
        if result.is_err() {
            self.transaction.channel.retire();
        }
        result
    }
    /// Consume publication authority before any send. This low-level value is
    /// remote-asserted transport data; the product coordinator must independently
    /// read its own journal before constructing it. No automatic retry exists.
    pub fn send_report(&mut self, report: RemoteRetirementReport) -> Result<(), HandoffError> {
        self.transaction.channel.owner()?;
        let result = (|| {
            if self.report_attempted {
                return Err(HandoffError::ChannelRetired);
            }
            self.report_attempted = true;
            // Detach the actual channel before publication. Its local owner
            // closes even if unwinding interrupts a potentially delivered send.
            let channel = self.transaction.take_channel()?;
            let fd = self.transaction.verify_channel(&channel)?;
            let data = self.transaction.encode(REPORT, Some(report));
            send_packet(fd, &data, None)?;
            self.transaction.verify_channel(&channel)?;
            Ok(())
        })();
        self.transaction.channel.retire();
        result
    }
}

/// Original accepted-stream custody and sideband owner, consumed together.
pub struct RetainedReceivedAcceptedStream {
    received: ReceivedAcceptedStream,
    pending: PendingHandoffReceiver,
}
impl RetainedReceivedAcceptedStream {
    pub fn into_parts(
        mut self,
    ) -> Result<(ReceivedAcceptedStream, PendingHandoffReceiver), HandoffError> {
        self.pending.transaction.channel.owner()?;
        let deadline = self.received.deadline()?;
        if deadline != self.pending.ensure_current()? {
            return Err(HandoffError::ProtocolRefused);
        }
        Ok((self.received, self.pending))
    }
}

impl HandoffSender {
    /// Additive single-transaction submission retaining the original channel.
    /// Legacy send and its bounded multi-submission behavior remain unchanged.
    pub fn send_retained(
        mut self,
        custody: AcceptedStreamCustody,
    ) -> Result<PendingHandoffSender, HandoffError> {
        self.channel.owner()?;
        let sequence = self.sequence;
        self.send_inner(&custody)?;
        let deadline = instant_deadline(
            &custody.boot,
            custody.time_namespace,
            custody.started,
            custody.deadline,
        )?;
        let mut pending = PendingHandoffSender {
            transaction: Transaction {
                channel: self.channel,
                nonce: self.nonce,
                sequence,
                identity: custody.identity,
                boot: custody.boot,
                time_namespace: custody.time_namespace,
                _namespace_file: custody._time_namespace_file,
                started: custody.started,
                monotonic_deadline: custody.deadline,
                deadline,
                readiness_enabled: false,
            },
            cancellation_attempted: false,
        };
        pending.ensure_current()?;
        Ok(pending)
    }
}
impl HandoffReceiver {
    /// Additive single-transaction receive. Control wait does not renew the
    /// submitted socket's original clock namespace or monotonic deadline.
    pub fn receive_retained(
        mut self,
        wait_budget: std::time::Duration,
    ) -> Result<RetainedReceivedAcceptedStream, HandoffError> {
        self.channel.owner()?;
        let sequence = self.sequence;
        let received = self.receive_inner(wait_budget)?;
        let namespace_file = received
            ._time_namespace_file
            .try_clone()
            .map_err(|_| HandoffError::Io)?;
        let mut pending = PendingHandoffReceiver {
            transaction: Transaction {
                channel: self.channel,
                nonce: self.nonce,
                sequence,
                identity: received.identity,
                boot: received.boot,
                time_namespace: received.time_namespace,
                _namespace_file: namespace_file,
                started: received.started,
                monotonic_deadline: received.monotonic_deadline,
                deadline: received.deadline,
                readiness_enabled: false,
            },
            cancellation_received: false,
            report_attempted: false,
        };
        pending.ensure_current()?;
        received.verify()?;
        Ok(RetainedReceivedAcceptedStream { received, pending })
    }
}

fn readable_now(fd: RawFd) -> Result<bool, HandoffError> {
    let mut state = libc::pollfd {
        fd,
        events: libc::POLLIN,
        revents: 0,
    };
    // SAFETY: poll receives one live initialized record, waits zero milliseconds
    // and retains no pointer. EINTR is a typed fail-stop result, not a retry.
    let result = unsafe { libc::poll(&mut state, 1, 0) };
    if result < 0 {
        return Err(HandoffError::Io);
    }
    Ok(result != 0)
}

mod service_control;

#[cfg(test)]
mod readiness_tests;

mod readiness;
