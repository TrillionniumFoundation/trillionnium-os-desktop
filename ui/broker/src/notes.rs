//! Linux destination I/O for one explicitly inherited Notes socketpair.
//!
//! Only a trusted production-host composition may hand this target to the
//! original Hepta FinalUseProductionOutboxTarget. This module creates no grant,
//! signer, operation identity, effect ledger, network listener or reconnect.
//! `enter_exact` performs the physical write synchronously, so the production
//! consumer-entry boundary must call it before returning a future. Same-UID
//! broker sessions never receive this handle and cannot invoke it over IPC.

use std::io::{self, Read, Write};
use std::net::Shutdown;
use std::os::unix::net::{UnixDatagram, UnixStream};
use std::sync::{Mutex, TryLockError};
use std::time::{Duration, Instant};

use trill_ui_core::notes::{
    sha256_hex, MAX_NOTES_REQUEST_BYTES, MAX_NOTES_RESPONSE_BYTES, NOTES_SCHEMA_VERSION,
};
pub use trill_ui_core::notes::{
    NotesObserve, NotesObserveAction, NotesReplace, NotesReplaceAction, NotesResponse, NotesResult,
    NotesTargetIdentity, NOTES_TOPIC,
};

pub const NOTES_IO_DEADLINE: Duration = Duration::from_secs(2);

/// Values taken from the original production dispatch request. Shape checks
/// and equality here do not authenticate the caller or replace Final-use.
pub struct NotesDispatchBinding {
    pub operation_id: String,
    pub destination_id: String,
    pub target: NotesTargetIdentity,
    pub payload_sha256: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NotesTargetRejection {
    MalformedPayload,
    BindingMismatch,
    Busy,
    ChannelUnavailable,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NotesTargetUncertainty {
    WriteOrReadFailed,
    ReplyMismatch,
    ApplicationUnknown,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum NotesDispatchOutcome {
    /// App document mutation acknowledged. The production owner still owns
    /// durable terminal publication; no compositor presentation is implied.
    Applied(NotesResponse),
    NotApplied(NotesResponse),
    /// This invocation wrote no bytes to the destination.
    Rejected(NotesTargetRejection),
    /// Some request bytes may have reached the application. Never retry from
    /// this result or infer that a timeout/cancel prevented the mutation.
    Indeterminate(NotesTargetUncertainty),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum NotesObservation {
    Applied(NotesResponse),
    Unknown,
    Unavailable,
}

struct Channel {
    stream: UnixStream,
    poisoned: bool,
    contacted: bool,
}

struct RecoveryChannel {
    socket: UnixDatagram,
    contacted: bool,
}

pub struct NotesTarget {
    identity: NotesTargetIdentity,
    channel: Mutex<Channel>,
    recovery: Option<Mutex<RecoveryChannel>>,
}

impl NotesTarget {
    /// A trusted bootstrap supplies one end of a private socketpair; the other
    /// is inherited only by the identified Notes child. Kernel peer credentials
    /// on a pre-fork socketpair identify its creator, not the later child, so
    /// they are deliberately not called process/grant authentication here.
    pub fn from_private_channel(
        stream: UnixStream,
        identity: NotesTargetIdentity,
    ) -> io::Result<Self> {
        identity
            .validate()
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "notes target identity"))?;
        if !stream.local_addr()?.is_unnamed() || !stream.peer_addr()?.is_unnamed() {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "notes requires a private inherited socketpair",
            ));
        }
        stream.set_nonblocking(false)?;
        Ok(Self {
            identity,
            recovery: None,
            channel: Mutex::new(Channel {
                stream,
                poisoned: false,
                contacted: false,
            }),
        })
    }

    /// Both streams are created in the same trusted Session bootstrap. The
    /// recovery stream must reach the application's restricted recovery lane.
    pub fn from_private_channels(
        effect: UnixStream,
        recovery: UnixDatagram,
        identity: NotesTargetIdentity,
    ) -> io::Result<Self> {
        if !recovery.local_addr()?.is_unnamed() || !recovery.peer_addr()?.is_unnamed() {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "Notes recovery requires a private datagram pair",
            ));
        }
        recovery.set_nonblocking(false)?;
        let recovery = Mutex::new(RecoveryChannel {
            socket: recovery,
            contacted: false,
        });
        let mut target = Self::from_private_channel(effect, identity)?;
        target.recovery = Some(recovery);
        Ok(target)
    }

    pub fn into_initial_endpoints(
        mut self,
    ) -> io::Result<(NotesTargetIdentity, UnixStream, UnixDatagram)> {
        let recovery = self
            .recovery
            .take()
            .ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "Notes recovery endpoint is absent",
                )
            })?
            .into_inner()
            .map_err(|_| {
                io::Error::new(io::ErrorKind::BrokenPipe, "Notes recovery was poisoned")
            })?;
        if recovery.contacted {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "Notes bootstrap requires unused endpoints",
            ));
        }
        let (identity, effect) = self.into_initial_endpoint()?;
        Ok((identity, effect, recovery.socket))
    }

    pub fn identity(&self) -> &NotesTargetIdentity {
        &self.identity
    }

    pub fn destination_id(&self) -> String {
        self.identity.destination_id()
    }

    /// Consume an unused Session-owned handle for an explicit private
    /// bootstrap handoff. No public Session request exposes this method. A
    /// contacted or poisoned channel cannot be repackaged as a fresh target.
    pub fn into_initial_endpoint(self) -> io::Result<(NotesTargetIdentity, UnixStream)> {
        let channel = self
            .channel
            .into_inner()
            .map_err(|_| io::Error::new(io::ErrorKind::BrokenPipe, "Notes channel was poisoned"))?;
        if channel.poisoned || channel.contacted {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "Notes bootstrap requires a never-contacted target",
            ));
        }
        Ok((self.identity, channel.stream))
    }

    pub fn enter_exact(
        &self,
        payload: &[u8],
        binding: &NotesDispatchBinding,
    ) -> NotesDispatchOutcome {
        let request = match NotesReplace::parse_exact(payload) {
            Ok(request) => request,
            Err(_) => {
                return NotesDispatchOutcome::Rejected(NotesTargetRejection::MalformedPayload)
            }
        };
        let digest = sha256_hex(payload);
        if request.target != self.identity
            || binding.target != self.identity
            || binding.destination_id != request.destination_id
            || binding.operation_id != request.operation_id
            || binding.payload_sha256 != digest
        {
            return NotesDispatchOutcome::Rejected(NotesTargetRejection::BindingMismatch);
        }
        let mut channel = match self.channel.try_lock() {
            Ok(channel) => channel,
            Err(TryLockError::WouldBlock) => {
                return NotesDispatchOutcome::Rejected(NotesTargetRejection::Busy)
            }
            Err(TryLockError::Poisoned(_)) => {
                return NotesDispatchOutcome::Rejected(NotesTargetRejection::ChannelUnavailable)
            }
        };
        if channel.poisoned {
            return NotesDispatchOutcome::Rejected(NotesTargetRejection::ChannelUnavailable);
        }
        channel.contacted = true;
        let response = match exchange_exact(&mut channel.stream, payload) {
            Ok(response) => response,
            Err(_) => {
                poison(&mut channel);
                return NotesDispatchOutcome::Indeterminate(
                    NotesTargetUncertainty::WriteOrReadFailed,
                );
            }
        };
        if !response.matches(&self.identity, &request.operation_id, &digest) {
            poison(&mut channel);
            return NotesDispatchOutcome::Indeterminate(NotesTargetUncertainty::ReplyMismatch);
        }
        match &response.result {
            NotesResult::Applied {
                previous_revision,
                text_sha256,
                ..
            } if *previous_revision == request.expected_revision
                && *text_sha256 == sha256_hex(request.text.as_bytes()) =>
            {
                NotesDispatchOutcome::Applied(response)
            }
            NotesResult::NotApplied { .. } => NotesDispatchOutcome::NotApplied(response),
            NotesResult::Unknown { .. } => {
                NotesDispatchOutcome::Indeterminate(NotesTargetUncertainty::ApplicationUnknown)
            }
            _ => {
                poison(&mut channel);
                NotesDispatchOutcome::Indeterminate(NotesTargetUncertainty::ReplyMismatch)
            }
        }
    }

    /// Independent read-only query of the app's last retained receipt. It
    /// never calls `enter_exact`, resubmits text, or infers absence/success from
    /// a matching current document. A lost/poisoned channel is unavailable.
    pub fn observe(&self, operation_id: &str, payload_sha256: &str) -> NotesObservation {
        let query = NotesObserve {
            schema_version: NOTES_SCHEMA_VERSION,
            action: NotesObserveAction::Observe,
            target: self.identity.clone(),
            operation_id: operation_id.into(),
            payload_sha256: payload_sha256.into(),
        };
        if query.validate().is_err() {
            return NotesObservation::Unavailable;
        }
        let Some(recovery) = self.recovery.as_ref() else {
            return NotesObservation::Unavailable;
        };
        let Ok(mut channel) = recovery.try_lock() else {
            return NotesObservation::Unavailable;
        };
        let Ok(raw) = serde_json::to_vec(&query) else {
            return NotesObservation::Unavailable;
        };
        channel.contacted = true;
        let deadline = Instant::now() + NOTES_IO_DEADLINE;
        if channel
            .socket
            .set_write_timeout(Some(NOTES_IO_DEADLINE))
            .is_err()
            || channel.socket.send(&raw).ok() != Some(raw.len())
        {
            return NotesObservation::Unavailable;
        }
        // Late datagrams must be matched to the complete immutable request.
        // Neither timeout nor a stale reply invalidates the effect stream.
        let mut bytes = [0_u8; MAX_NOTES_RESPONSE_BYTES + 1];
        for _ in 0..16 {
            let Ok(left) = remaining(deadline) else {
                return NotesObservation::Unavailable;
            };
            if channel.socket.set_read_timeout(Some(left)).is_err() {
                return NotesObservation::Unavailable;
            }
            let Ok(length) = channel.socket.recv(&mut bytes) else {
                return NotesObservation::Unavailable;
            };
            let Ok(response) = NotesResponse::parse_exact(&bytes[..length]) else {
                continue;
            };
            if !response.matches(&self.identity, operation_id, payload_sha256) {
                continue;
            }
            return match response.result {
                NotesResult::Applied { .. } => NotesObservation::Applied(response),
                NotesResult::Unknown { .. } | NotesResult::NotApplied { .. } => {
                    NotesObservation::Unknown
                }
            };
        }
        NotesObservation::Unavailable
    }
}

fn poison(channel: &mut Channel) {
    channel.poisoned = true;
    let _ = channel.stream.shutdown(Shutdown::Both);
}

/// Prefix framing preserves every payload byte; no JSON reserialization is
/// permitted on the mutation path. One total deadline also bounds peers that
/// drip individual bytes just before a per-read timeout would expire.
fn exchange_exact(stream: &mut UnixStream, payload: &[u8]) -> io::Result<NotesResponse> {
    if payload.is_empty() || payload.len() > MAX_NOTES_REQUEST_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "notes frame bound",
        ));
    }
    let deadline = Instant::now() + NOTES_IO_DEADLINE;
    write_before(stream, &(payload.len() as u32).to_be_bytes(), deadline)?;
    write_before(stream, payload, deadline)?;
    let mut prefix = [0u8; 4];
    read_before(stream, &mut prefix, deadline)?;
    let length = u32::from_be_bytes(prefix) as usize;
    if length == 0 || length > MAX_NOTES_RESPONSE_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "notes reply bound",
        ));
    }
    let mut reply = vec![0; length];
    read_before(stream, &mut reply, deadline)?;
    NotesResponse::parse_exact(&reply)
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "notes reply schema"))
}

fn remaining(deadline: Instant) -> io::Result<Duration> {
    deadline
        .checked_duration_since(Instant::now())
        .filter(|left| !left.is_zero())
        .ok_or_else(|| io::Error::new(io::ErrorKind::TimedOut, "notes total deadline"))
}

fn write_before(stream: &mut UnixStream, mut bytes: &[u8], deadline: Instant) -> io::Result<()> {
    while !bytes.is_empty() {
        stream.set_write_timeout(Some(remaining(deadline)?))?;
        match stream.write(bytes) {
            Ok(0) => return Err(io::Error::new(io::ErrorKind::WriteZero, "notes write")),
            Ok(count) => bytes = &bytes[count..],
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error),
        }
    }
    Ok(())
}

fn read_before(stream: &mut UnixStream, mut bytes: &mut [u8], deadline: Instant) -> io::Result<()> {
    while !bytes.is_empty() {
        stream.set_read_timeout(Some(remaining(deadline)?))?;
        match stream.read(bytes) {
            Ok(0) => return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "notes read")),
            Ok(count) => bytes = &mut bytes[count..],
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error),
        }
    }
    Ok(())
}
