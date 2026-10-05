//! Linux descriptor custody, separate from the HEPTA application frame protocol.
//!
//! Callers supply already connected control sockets and an explicit kernel peer
//! policy. This module binds neither a path nor a semantic principal. The fixed
//! deadline begins when `capture` first takes ownership, not at kernel accept.
//! Unit/executable/liveness attestation and product activation remain separate.

use std::fmt;
use std::fs;
use std::io;
use std::mem::{size_of, size_of_val, zeroed};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use crate::{PeerIdentity, PeerPolicy};

mod connected_denial;
mod retained_control;
pub use connected_denial::OriginalConnectedDenial;
pub use retained_control::{
    PendingHandoffReceiver, PendingHandoffSender, RemoteRetirementReport, RemoteTerminalState,
    RetainedReceivedAcceptedStream,
};

pub const MAX_HANDOFF_BUDGET: Duration = Duration::from_secs(20);
pub const MAX_HANDOFFS_PER_CHANNEL: usize = 64;
const MAX_RIGHTS: usize = 16;
const PACKET_BYTES: usize = 128;
const CHALLENGE_BYTES: usize = 40;
const MAGIC: &[u8; 8] = b"HPTAFD01";
const CHALLENGE_MAGIC: &[u8; 8] = b"HPTAFDC1";
// Linux socket cmsg ABI: include/linux/socket.h at v6.17 defines the
// read-only pidfd(int) type as 0x04; libc 0.2.186 does not expose it.
// https://github.com/torvalds/linux/blob/v6.17/include/linux/socket.h
const SCM_PIDFD: libc::c_int = 0x04;
// Enough aligned storage for 16 rights plus one kernel ucred. MSG_CTRUNC
// is rejected, and Linux closes rights that did not fit the receive buffer.
const CONTROL_WORDS: usize = 32;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HandoffError {
    InvalidConfiguration,
    WrongDescriptor,
    PeerRefused,
    ClockUnavailable,
    EntropyUnavailable,
    DeadlineExceeded,
    ProtocolRefused,
    IdentityMismatch,
    ConnectionClosed,
    ChannelRetired,
    CapacityExceeded,
    ProcessChanged,
    Io,
}
impl fmt::Display for HandoffError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::InvalidConfiguration => "invalid accepted-stream handoff configuration",
            Self::WrongDescriptor => "accepted-stream handoff descriptor refused",
            Self::PeerRefused => "accepted-stream handoff kernel peer refused",
            Self::ClockUnavailable => "accepted-stream handoff clock unavailable",
            Self::EntropyUnavailable => "accepted-stream handoff entropy unavailable",
            Self::DeadlineExceeded => "accepted-stream handoff deadline exceeded",
            Self::ProtocolRefused => "accepted-stream handoff protocol refused",
            Self::IdentityMismatch => "accepted-stream handoff socket identity changed",
            Self::ConnectionClosed => "accepted-stream handoff control connection closed",
            Self::ChannelRetired => "accepted-stream handoff channel retired",
            Self::CapacityExceeded => "accepted-stream handoff channel capacity exhausted",
            Self::ProcessChanged => "accepted-stream handoff process owner changed",
            Self::Io => "accepted-stream handoff I/O failed",
        })
    }
}
impl std::error::Error for HandoffError {}

#[derive(Clone, Copy, PartialEq, Eq)]
struct SocketIdentity {
    cookie: u64,
    device: u64,
    inode: u64,
}

// This is the Control endpoint captured at construction, not the submitted
// Agent stream identity carried by a handoff/sideband packet.
#[derive(Clone, Copy, PartialEq, Eq)]
struct OriginalControlIdentity(SocketIdentity);
impl OriginalControlIdentity {
    fn capture(fd: RawFd) -> Result<Self, HandoffError> {
        socket_identity(fd).map(Self)
    }
    fn verify(&self, fd: RawFd) -> Result<(), HandoffError> {
        if socket_identity(fd)? != self.0 {
            return Err(HandoffError::WrongDescriptor);
        }
        Ok(())
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
struct TimeNamespace {
    device: u64,
    inode: u64,
}

/// Non-cloneable local custody of one original accepted socket. No renewal,
/// raw-stream extraction or retry is available on this sender-side object.
///
/// ```compile_fail
/// use hepta_agent_transport::AcceptedStreamCustody;
/// fn requires_clone<T: Clone>() {}
/// requires_clone::<AcceptedStreamCustody>();
/// ```
pub struct AcceptedStreamCustody {
    stream: UnixStream,
    owner_pid: u32,
    identity: SocketIdentity,
    boot: [u8; 16],
    time_namespace: TimeNamespace,
    _time_namespace_file: fs::File,
    started: u64,
    deadline: u64,
}
impl AcceptedStreamCustody {
    /// Capture under an already fixed local absolute ceiling. Sample native
    /// monotonic time before Instant's remaining duration: the wire deadline
    /// is conservative relative to `deadline`, never a fresh Duration budget.
    pub fn capture_before(
        stream: UnixStream,
        expected_local_path: &Path,
        deadline: Instant,
    ) -> Result<Self, HandoffError> {
        let owner_pid = std::process::id();
        let started = monotonic_nanos()?;
        let remaining = deadline
            .checked_duration_since(Instant::now())
            .filter(|value| !value.is_zero())
            .ok_or(HandoffError::DeadlineExceeded)?;
        valid_budget(remaining)?;
        let monotonic_deadline = started
            .checked_add(
                u64::try_from(remaining.as_nanos())
                    .map_err(|_| HandoffError::InvalidConfiguration)?,
            )
            .ok_or(HandoffError::InvalidConfiguration)?;
        let (time_namespace, namespace_file) = time_namespace()?;
        valid_path(expected_local_path)?;
        let identity = accepted_identity(&stream, expected_local_path)?;
        let boot = boot_id()?;
        check_time(&boot, time_namespace, started, monotonic_deadline)?;
        if owner_pid != std::process::id() {
            return Err(HandoffError::ProcessChanged);
        }
        if deadline <= Instant::now() {
            return Err(HandoffError::DeadlineExceeded);
        }
        Ok(Self {
            stream,
            owner_pid,
            identity,
            boot,
            time_namespace,
            _time_namespace_file: namespace_file,
            started,
            deadline: monotonic_deadline,
        })
    }

    /// The reviewed custodian must call this at its earliest ownership point.
    /// `expected_local_path` is trusted configuration, not a peer assertion.
    /// Arbitrary Rust code with duplicate raw FDs is outside this custody API.
    pub fn capture(
        stream: UnixStream,
        expected_local_path: &Path,
        budget: Duration,
    ) -> Result<Self, HandoffError> {
        let started = monotonic_nanos()?;
        let (time_namespace, namespace_file) = time_namespace()?;
        valid_budget(budget)?;
        let deadline = started
            .checked_add(
                u64::try_from(budget.as_nanos()).map_err(|_| HandoffError::InvalidConfiguration)?,
            )
            .ok_or(HandoffError::InvalidConfiguration)?;
        valid_path(expected_local_path)?;
        let identity = accepted_identity(&stream, expected_local_path)?;
        let boot = boot_id()?;
        check_time(&boot, time_namespace, started, deadline)?;
        Ok(Self {
            stream,
            owner_pid: std::process::id(),
            identity,
            boot,
            time_namespace,
            _time_namespace_file: namespace_file,
            started,
            deadline,
        })
    }
}

struct ControlChannel {
    stream: Option<UnixStream>,
    owner_pid: u32,
    peer: PeerIdentity,
    policy: PeerPolicy,
    original_identity: OriginalControlIdentity,
}
impl ControlChannel {
    fn new(descriptor: OwnedFd, policy: PeerPolicy) -> Result<Self, HandoffError> {
        let stream = UnixStream::from(descriptor);
        socket_shape(&stream, libc::SOCK_SEQPACKET)?;
        let peer = PeerIdentity::from_stream(&stream).map_err(|_| HandoffError::PeerRefused)?;
        if peer.pid.is_none_or(|value| value == 0) {
            return Err(HandoffError::PeerRefused);
        }
        policy
            .authorize(peer)
            .map_err(|_| HandoffError::PeerRefused)?;
        // Received SCM_RIGHTS are CLOEXEC separately; also close this owned
        // control descriptor across exec. No inherited fork object may use it.
        let fd = stream.as_raw_fd();
        // SAFETY: fcntl and setsockopt operate on the live owned descriptor;
        // option storage is initialized and no pointer is retained.
        unsafe {
            let flags = libc::fcntl(fd, libc::F_GETFD);
            if flags < 0 || libc::fcntl(fd, libc::F_SETFD, flags | libc::FD_CLOEXEC) != 0 {
                return Err(HandoffError::Io);
            }
            let enabled: libc::c_int = 1;
            if libc::setsockopt(
                fd,
                libc::SOL_SOCKET,
                libc::SO_PASSCRED,
                std::ptr::addr_of!(enabled).cast(),
                size_of::<libc::c_int>() as libc::socklen_t,
            ) != 0
            {
                return Err(HandoffError::Io);
            }
        }
        let original_identity = OriginalControlIdentity::capture(fd)?;
        Ok(Self {
            stream: Some(stream),
            owner_pid: std::process::id(),
            peer,
            policy,
            original_identity,
        })
    }
    fn owner(&self) -> Result<(), HandoffError> {
        if self.owner_pid != std::process::id() {
            return Err(HandoffError::ProcessChanged);
        }
        Ok(())
    }
    fn verify(&self) -> Result<RawFd, HandoffError> {
        self.owner()?;
        let stream = self.stream.as_ref().ok_or(HandoffError::ChannelRetired)?;
        socket_shape(stream, libc::SOCK_SEQPACKET)?;
        let actual = PeerIdentity::from_stream(stream).map_err(|_| HandoffError::PeerRefused)?;
        if actual != self.peer {
            return Err(HandoffError::PeerRefused);
        }
        self.policy
            .authorize(actual)
            .map_err(|_| HandoffError::PeerRefused)?;
        Ok(stream.as_raw_fd())
    }
    fn retire(&mut self) {
        self.stream.take();
    }
}

/// One authenticated, fail-stop descriptor sender. Success means one packet
/// was enqueued; it is not an acknowledgment of receiver admission or action.
pub struct HandoffSender {
    channel: ControlChannel,
    nonce: [u8; 32],
    sequence: u64,
    seen: Vec<u64>,
}
impl HandoffSender {
    /// Receive the peer's OS-entropy challenge over an existing seqpacket
    /// control channel. No listener or deterministic nonce source is exposed.
    pub fn from_control(
        control: OwnedFd,
        policy: PeerPolicy,
        handshake_budget: Duration,
    ) -> Result<Self, HandoffError> {
        valid_budget(handshake_budget)?;
        let channel = ControlChannel::new(control, policy)?;
        let fd = channel.verify()?;
        let stop = Instant::now()
            .checked_add(handshake_budget)
            .ok_or(HandoffError::InvalidConfiguration)?;
        wait_readable(fd, stop)?;
        let mut data = [0; CHALLENGE_BYTES];
        let message = receive_packet(fd, &mut data)?;
        // The challenge may have been queued before SO_PASSCRED was enabled at
        // this endpoint; its authority is the original checked SO_PEERCRED.
        // Descriptor-bearing submissions below additionally require actual
        // per-message kernel credentials equal to that original peer.
        if message.length != data.len()
            || message.flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
            || message.rights_count != 0
            || message.invalid
            || &data[..8] != CHALLENGE_MAGIC
        {
            return Err(HandoffError::ProtocolRefused);
        }
        channel.verify()?;
        let mut nonce = [0; 32];
        nonce.copy_from_slice(&data[8..]);
        if nonce == [0; 32] {
            return Err(HandoffError::ProtocolRefused);
        }
        Ok(Self {
            channel,
            nonce,
            sequence: 1,
            seen: Vec::with_capacity(MAX_HANDOFFS_PER_CHANNEL),
        })
    }
    /// Consume local custody even on failure. Never automatically resend or
    /// return the accepted socket after possible descriptor publication.
    pub fn send(&mut self, custody: AcceptedStreamCustody) -> Result<(), HandoffError> {
        self.channel.owner()?;
        let result = self.send_inner(&custody);
        if result.is_err() {
            self.channel.retire();
        }
        result
    }
    fn send_inner(&mut self, custody: &AcceptedStreamCustody) -> Result<(), HandoffError> {
        if custody.owner_pid != std::process::id() {
            return Err(HandoffError::ProcessChanged);
        }
        let fd = self.channel.verify()?;
        check_time(
            &custody.boot,
            custody.time_namespace,
            custody.started,
            custody.deadline,
        )?;
        if self.seen.len() == MAX_HANDOFFS_PER_CHANNEL {
            return Err(HandoffError::CapacityExceeded);
        }
        if self.seen.contains(&custody.identity.cookie) {
            return Err(HandoffError::ProtocolRefused);
        }
        let identity = socket_identity(custody.stream.as_raw_fd())?;
        if identity != custody.identity {
            return Err(HandoffError::IdentityMismatch);
        }
        let data = encode(custody, self.sequence, &self.nonce);
        send_packet(fd, &data, Some(custody.stream.as_raw_fd()))?;
        self.channel.verify()?;
        check_time(
            &custody.boot,
            custody.time_namespace,
            custody.started,
            custody.deadline,
        )?;
        self.seen.push(identity.cookie);
        self.sequence = self
            .sequence
            .checked_add(1)
            .ok_or(HandoffError::CapacityExceeded)?;
        Ok(())
    }
}

/// One authenticated receiver with bounded replay memory. A protocol, timeout,
/// descriptor or credential failure permanently closes this control instance.
pub struct HandoffReceiver {
    channel: ControlChannel,
    nonce: [u8; 32],
    sequence: u64,
    expected_local_path: PathBuf,
    seen: Vec<u64>,
}
impl HandoffReceiver {
    pub fn from_control(
        control: OwnedFd,
        policy: PeerPolicy,
        expected_local_path: &Path,
    ) -> Result<Self, HandoffError> {
        valid_path(expected_local_path)?;
        let channel = ControlChannel::new(control, policy)?;
        let nonce = entropy_nonce()?;
        let mut challenge = [0; CHALLENGE_BYTES];
        challenge[..8].copy_from_slice(CHALLENGE_MAGIC);
        challenge[8..].copy_from_slice(&nonce);
        send_packet(channel.verify()?, &challenge, None)?;
        Ok(Self {
            channel,
            nonce,
            sequence: 1,
            expected_local_path: expected_local_path.to_owned(),
            seen: Vec::with_capacity(MAX_HANDOFFS_PER_CHANNEL),
        })
    }
    /// `wait_budget` bounds waiting for a control packet. It never replaces the
    /// sender custody's original deadline, which is validated independently.
    pub fn receive(
        &mut self,
        wait_budget: Duration,
    ) -> Result<ReceivedAcceptedStream, HandoffError> {
        self.channel.owner()?;
        let result = self.receive_inner(wait_budget);
        if result.is_err() {
            self.channel.retire();
        }
        result
    }
    fn receive_inner(
        &mut self,
        wait_budget: Duration,
    ) -> Result<ReceivedAcceptedStream, HandoffError> {
        valid_budget(wait_budget)?;
        let fd = self.channel.verify()?;
        if self.seen.len() == MAX_HANDOFFS_PER_CHANNEL {
            return Err(HandoffError::CapacityExceeded);
        }
        let stop = Instant::now()
            .checked_add(wait_budget)
            .ok_or(HandoffError::InvalidConfiguration)?;
        wait_readable(fd, stop)?;
        let mut data = [0; PACKET_BYTES];
        let mut message = receive_packet(fd, &mut data)?;
        if message.length == 0 {
            return Err(HandoffError::ConnectionClosed);
        }
        self.channel.verify()?;
        if message.flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
            || message.invalid
            || message.length != PACKET_BYTES
            || message.rights_count != 1
            || message.credentials != Some(self.channel.peer)
        {
            return Err(HandoffError::ProtocolRefused);
        }
        let packet = decode(&data, self.sequence, &self.nonce)?;
        check_time(
            &packet.boot,
            packet.time_namespace,
            packet.started,
            packet.deadline,
        )?;
        let descriptor = message.rights[0]
            .take()
            .ok_or(HandoffError::ProtocolRefused)?;
        let stream = UnixStream::from(descriptor);
        let identity = accepted_identity(&stream, &self.expected_local_path)?;
        if identity != packet.identity {
            return Err(HandoffError::IdentityMismatch);
        }
        if self.seen.contains(&identity.cookie) {
            return Err(HandoffError::ProtocolRefused);
        }
        // Sample Instant first: adding time remaining at the later CLOCK_MONOTONIC
        // sample is conservative and cannot renew transfer or queue residence.
        let deadline = instant_deadline(
            &packet.boot,
            packet.time_namespace,
            packet.started,
            packet.deadline,
        )?;
        let (scope, namespace_file) = time_namespace()?;
        if scope != packet.time_namespace {
            return Err(HandoffError::ProtocolRefused);
        }
        self.seen.push(identity.cookie);
        self.sequence = self
            .sequence
            .checked_add(1)
            .ok_or(HandoffError::CapacityExceeded)?;
        Ok(ReceivedAcceptedStream {
            stream,
            owner_pid: std::process::id(),
            identity,
            expected_local_path: self.expected_local_path.clone(),
            boot: packet.boot,
            time_namespace: packet.time_namespace,
            _time_namespace_file: namespace_file,
            started: packet.started,
            monotonic_deadline: packet.deadline,
            deadline,
        })
    }
}

/// Receiver-owned original stream plus its fixed absolute dispatch deadline.
/// This object cannot be sent again or renewed through this API.
///
/// ```compile_fail
/// use hepta_agent_transport::ReceivedAcceptedStream;
/// fn extract_without_deadline(received: ReceivedAcceptedStream) {
///     let _stream = received.stream;
/// }
/// ```
pub struct ReceivedAcceptedStream {
    stream: UnixStream,
    owner_pid: u32,
    identity: SocketIdentity,
    expected_local_path: PathBuf,
    boot: [u8; 16],
    time_namespace: TimeNamespace,
    _time_namespace_file: fs::File,
    started: u64,
    monotonic_deadline: u64,
    deadline: Instant,
}
impl ReceivedAcceptedStream {
    pub fn deadline(&self) -> Result<Instant, HandoffError> {
        self.verify()?;
        Ok(self.deadline)
    }
    /// Consume for the future AgentPort absolute-deadline path. No application
    /// request is decoded by handoff, and queue delay cannot renew this instant.
    pub fn consume_before<T>(
        self,
        dispatch: impl FnOnce(UnixStream, Instant) -> T,
    ) -> Result<T, HandoffError> {
        self.verify()?;
        Ok(dispatch(self.stream, self.deadline))
    }
    fn verify(&self) -> Result<(), HandoffError> {
        if self.owner_pid != std::process::id() {
            return Err(HandoffError::ProcessChanged);
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
        if accepted_identity(&self.stream, &self.expected_local_path)? != self.identity {
            return Err(HandoffError::IdentityMismatch);
        }
        Ok(())
    }
}

struct Packet {
    boot: [u8; 16],
    time_namespace: TimeNamespace,
    started: u64,
    deadline: u64,
    identity: SocketIdentity,
}
fn encode(custody: &AcceptedStreamCustody, sequence: u64, nonce: &[u8; 32]) -> [u8; PACKET_BYTES] {
    let mut data = [0; PACKET_BYTES];
    data[..8].copy_from_slice(MAGIC);
    data[8..10].copy_from_slice(&1u16.to_be_bytes());
    data[16..24].copy_from_slice(&sequence.to_be_bytes());
    data[24..40].copy_from_slice(&custody.boot);
    for (offset, value) in [
        (40, custody.started),
        (48, custody.deadline),
        (56, custody.identity.cookie),
        (64, custody.identity.device),
        (72, custody.identity.inode),
        (80, custody.time_namespace.device),
        (88, custody.time_namespace.inode),
    ] {
        data[offset..offset + 8].copy_from_slice(&value.to_be_bytes());
    }
    data[96..128].copy_from_slice(nonce);
    data
}
fn decode(
    data: &[u8; PACKET_BYTES],
    sequence: u64,
    nonce: &[u8; 32],
) -> Result<Packet, HandoffError> {
    let u64_at = |offset| {
        u64::from_be_bytes(
            data[offset..offset + 8]
                .try_into()
                .expect("fixed handoff layout"),
        )
    };
    if &data[..8] != MAGIC
        || data[8..10] != 1u16.to_be_bytes()
        || data[10..16] != [0; 6]
        || u64_at(16) != sequence
        || &data[96..128] != nonce
    {
        return Err(HandoffError::ProtocolRefused);
    }
    let mut boot = [0; 16];
    boot.copy_from_slice(&data[24..40]);
    Ok(Packet {
        boot,
        time_namespace: TimeNamespace {
            device: u64_at(80),
            inode: u64_at(88),
        },
        started: u64_at(40),
        deadline: u64_at(48),
        identity: SocketIdentity {
            cookie: u64_at(56),
            device: u64_at(64),
            inode: u64_at(72),
        },
    })
}

fn valid_budget(budget: Duration) -> Result<(), HandoffError> {
    if budget.is_zero() || budget > MAX_HANDOFF_BUDGET {
        return Err(HandoffError::InvalidConfiguration);
    }
    Ok(())
}
fn valid_path(path: &Path) -> Result<(), HandoffError> {
    let bytes = path.as_os_str().as_encoded_bytes();
    if !path.is_absolute()
        || bytes.len() <= 1
        || bytes.len() > 107
        || bytes.contains(&0)
        || bytes.ends_with(b"/")
        || bytes.windows(2).any(|v| v == b"//")
        || bytes.windows(3).any(|v| v == b"/./")
        || bytes.windows(4).any(|v| v == b"/../")
        || bytes.ends_with(b"/.")
        || bytes.ends_with(b"/..")
    {
        return Err(HandoffError::InvalidConfiguration);
    }
    Ok(())
}
fn socket_shape(stream: &UnixStream, expected_type: libc::c_int) -> Result<(), HandoffError> {
    let fd = stream.as_raw_fd();
    if socket_option::<libc::c_int>(fd, libc::SO_DOMAIN)? != libc::AF_UNIX
        || socket_option::<libc::c_int>(fd, libc::SO_TYPE)? != expected_type
        || socket_option::<libc::c_int>(fd, libc::SO_ACCEPTCONN)? != 0
        || stream.peer_addr().is_err()
    {
        return Err(HandoffError::WrongDescriptor);
    }
    Ok(())
}
fn socket_option<T: Copy>(fd: RawFd, option: libc::c_int) -> Result<T, HandoffError> {
    // SAFETY: callers use integer getsockopt options only. Zeroed integer
    // storage is valid; both output pointers stay live and are not retained.
    let mut value: T = unsafe { zeroed() };
    let mut length = size_of::<T>() as libc::socklen_t;
    let result = unsafe {
        libc::getsockopt(
            fd,
            libc::SOL_SOCKET,
            option,
            std::ptr::addr_of_mut!(value).cast(),
            &mut length,
        )
    };
    if result != 0 || length as usize != size_of::<T>() {
        return Err(HandoffError::WrongDescriptor);
    }
    Ok(value)
}
fn socket_identity(fd: RawFd) -> Result<SocketIdentity, HandoffError> {
    // SAFETY: fstat writes initialized stat storage and retains no pointer.
    let mut metadata: libc::stat = unsafe { zeroed() };
    if unsafe { libc::fstat(fd, &mut metadata) } != 0
        || metadata.st_mode & libc::S_IFMT != libc::S_IFSOCK
    {
        return Err(HandoffError::WrongDescriptor);
    }
    let cookie = socket_option::<u64>(fd, libc::SO_COOKIE)?;
    if cookie == 0 {
        return Err(HandoffError::WrongDescriptor);
    }
    Ok(SocketIdentity {
        cookie,
        device: metadata.st_dev,
        inode: metadata.st_ino,
    })
}
fn accepted_identity(stream: &UnixStream, path: &Path) -> Result<SocketIdentity, HandoffError> {
    socket_shape(stream, libc::SOCK_STREAM)?;
    if stream
        .local_addr()
        .map_err(|_| HandoffError::WrongDescriptor)?
        .as_pathname()
        != Some(path)
    {
        return Err(HandoffError::WrongDescriptor);
    }
    let peer = PeerIdentity::from_stream(stream).map_err(|_| HandoffError::PeerRefused)?;
    if peer.pid.is_none_or(|value| value == 0) {
        return Err(HandoffError::PeerRefused);
    }
    socket_identity(stream.as_raw_fd())
}
fn monotonic_nanos() -> Result<u64, HandoffError> {
    // SAFETY: timespec is writable initialized storage for this syscall.
    let mut value: libc::timespec = unsafe { zeroed() };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut value) } != 0
        || value.tv_sec < 0
        || !(0..1_000_000_000).contains(&value.tv_nsec)
    {
        return Err(HandoffError::ClockUnavailable);
    }
    (value.tv_sec as u64)
        .checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(value.tv_nsec as u64))
        .ok_or(HandoffError::ClockUnavailable)
}
fn boot_id() -> Result<[u8; 16], HandoffError> {
    use std::io::Read;
    let file = fs::File::open("/proc/sys/kernel/random/boot_id")
        .map_err(|_| HandoffError::ClockUnavailable)?;
    let mut value = Vec::with_capacity(37);
    file.take(38)
        .read_to_end(&mut value)
        .map_err(|_| HandoffError::ClockUnavailable)?;
    if value.len() != 37 || value[36] != b'\n' {
        return Err(HandoffError::ClockUnavailable);
    }
    let mut result = [0; 16];
    let mut index = 0;
    for (position, chunk) in value[..36].split(|b| *b == b'-').enumerate() {
        if chunk.len() != [8, 4, 4, 4, 12].get(position).copied().unwrap_or(0) {
            return Err(HandoffError::ClockUnavailable);
        }
        for pair in chunk.chunks_exact(2) {
            let nibble = |v| match v {
                b'0'..=b'9' => Some(v - b'0'),
                b'a'..=b'f' => Some(v - b'a' + 10),
                _ => None,
            };
            let (Some(a), Some(b)) = (nibble(pair[0]), nibble(pair[1])) else {
                return Err(HandoffError::ClockUnavailable);
            };
            if index >= 16 {
                return Err(HandoffError::ClockUnavailable);
            }
            result[index] = (a << 4) | b;
            index += 1;
        }
    }
    if index != 16 || result == [0; 16] {
        return Err(HandoffError::ClockUnavailable);
    }
    Ok(result)
}
fn time_namespace() -> Result<(TimeNamespace, fs::File), HandoffError> {
    use std::os::unix::fs::MetadataExt;
    // Follow only this fixed kernel namespace link, retaining the actual nsfs
    // descriptor through fstat. Unsupported namespace files fail closed.
    let file =
        fs::File::open("/proc/thread-self/ns/time").map_err(|_| HandoffError::ClockUnavailable)?;
    let metadata = file
        .metadata()
        .map_err(|_| HandoffError::ClockUnavailable)?;
    if metadata.ino() == 0 {
        return Err(HandoffError::ClockUnavailable);
    }
    Ok((
        TimeNamespace {
            device: metadata.dev(),
            inode: metadata.ino(),
        },
        file,
    ))
}
fn check_time(
    boot: &[u8; 16],
    scope: TimeNamespace,
    started: u64,
    deadline: u64,
) -> Result<u64, HandoffError> {
    let now = monotonic_nanos()?;
    if boot != &boot_id()?
        || scope != time_namespace()?.0
        || started > now
        || deadline <= started
        || deadline - started > MAX_HANDOFF_BUDGET.as_nanos() as u64
    {
        return Err(HandoffError::ProtocolRefused);
    }
    if deadline <= now {
        return Err(HandoffError::DeadlineExceeded);
    }
    Ok(now)
}
fn instant_deadline(
    boot: &[u8; 16],
    scope: TimeNamespace,
    started: u64,
    deadline: u64,
) -> Result<Instant, HandoffError> {
    let instant = Instant::now();
    let now = check_time(boot, scope, started, deadline)?;
    instant
        .checked_add(Duration::from_nanos(deadline - now))
        .ok_or(HandoffError::ClockUnavailable)
}
fn entropy_nonce() -> Result<[u8; 32], HandoffError> {
    let mut nonce = [0; 32];
    let mut filled = 0;
    while filled < nonce.len() {
        // SAFETY: the provided slice owns exactly the writable bytes requested.
        let result = unsafe {
            libc::getrandom(
                nonce[filled..].as_mut_ptr().cast(),
                nonce.len() - filled,
                libc::GRND_NONBLOCK,
            )
        };
        if result <= 0 {
            return Err(HandoffError::EntropyUnavailable);
        }
        filled += result as usize;
    }
    if nonce == [0; 32] {
        return Err(HandoffError::EntropyUnavailable);
    }
    Ok(nonce)
}
fn wait_readable(fd: RawFd, stop: Instant) -> Result<(), HandoffError> {
    loop {
        let remaining = stop
            .checked_duration_since(Instant::now())
            .filter(|v| !v.is_zero())
            .ok_or(HandoffError::DeadlineExceeded)?;
        let milliseconds = remaining
            .as_millis()
            .saturating_add(1)
            .min(i32::MAX as u128) as i32;
        let mut pollfd = libc::pollfd {
            fd,
            events: libc::POLLIN,
            revents: 0,
        };
        // SAFETY: poll receives one live stack record and retains no pointer.
        let result = unsafe { libc::poll(&mut pollfd, 1, milliseconds) };
        if result < 0 {
            if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(HandoffError::Io);
        }
        if Instant::now() >= stop {
            return Err(HandoffError::DeadlineExceeded);
        }
        if result > 0 {
            return Ok(());
        }
    }
}
fn send_packet(fd: RawFd, data: &[u8], right: Option<RawFd>) -> Result<(), HandoffError> {
    let mut vector = libc::iovec {
        iov_base: data.as_ptr().cast_mut().cast(),
        iov_len: data.len(),
    };
    let mut control = [0usize; CONTROL_WORDS];
    // SAFETY: msghdr contains only pointers to the above live bounded buffers.
    let mut message: libc::msghdr = unsafe { zeroed() };
    message.msg_iov = &mut vector;
    message.msg_iovlen = 1;
    if let Some(right) = right {
        message.msg_control = control.as_mut_ptr().cast();
        // SAFETY: CMSG storage is aligned, sized for one integer and live
        // throughout sendmsg. Sending rights duplicates, never consumes, fd.
        unsafe {
            message.msg_controllen = libc::CMSG_SPACE(size_of::<RawFd>() as u32) as usize;
            let header = libc::CMSG_FIRSTHDR(&message);
            (*header).cmsg_level = libc::SOL_SOCKET;
            (*header).cmsg_type = libc::SCM_RIGHTS;
            (*header).cmsg_len = libc::CMSG_LEN(size_of::<RawFd>() as u32) as usize;
            std::ptr::write_unaligned(libc::CMSG_DATA(header).cast::<RawFd>(), right);
        }
    }
    // A failed/short/EINTR send is never retried: it can be ambiguous.
    let result = unsafe { libc::sendmsg(fd, &message, libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL) };
    if result < 0 || result as usize != data.len() {
        return Err(HandoffError::Io);
    }
    Ok(())
}
struct ReceivedPacket {
    length: usize,
    flags: libc::c_int,
    rights: [Option<OwnedFd>; MAX_RIGHTS],
    rights_count: usize,
    credentials: Option<PeerIdentity>,
    invalid: bool,
}
fn receive_packet(fd: RawFd, data: &mut [u8]) -> Result<ReceivedPacket, HandoffError> {
    let mut control = [0usize; CONTROL_WORDS];
    let mut vector = libc::iovec {
        iov_base: data.as_mut_ptr().cast(),
        iov_len: data.len(),
    };
    // SAFETY: all header pointers refer to live, aligned, bounded writable
    // buffers. MSG_CMSG_CLOEXEC atomically protects every received rights fd.
    let mut message: libc::msghdr = unsafe { zeroed() };
    message.msg_iov = &mut vector;
    message.msg_iovlen = 1;
    message.msg_control = control.as_mut_ptr().cast();
    message.msg_controllen = size_of_val(&control);
    let length = unsafe {
        libc::recvmsg(
            fd,
            &mut message,
            libc::MSG_CMSG_CLOEXEC | libc::MSG_DONTWAIT,
        )
    };
    if length < 0 {
        return Err(HandoffError::Io);
    }
    let mut received = ReceivedPacket {
        length: length as usize,
        flags: message.msg_flags,
        rights: std::array::from_fn(|_| None),
        rights_count: 0,
        credentials: None,
        invalid: false,
    };
    // Parse all rights before returning any validation error. Each integer is
    // immediately adopted once; the stack owner closes every fd on rejection.
    // Linux supplies structurally valid ancillary headers, bounded by the
    // supplied buffer; explicit length checks additionally guard traversal.
    unsafe {
        let mut header = libc::CMSG_FIRSTHDR(&message);
        while !header.is_null() {
            let base = control.as_ptr() as usize;
            let offset = header as usize - base;
            let header_length = (*header).cmsg_len;
            let prefix = libc::CMSG_LEN(0) as usize;
            if header_length < prefix
                || offset
                    .checked_add(header_length)
                    .is_none_or(|end| end > message.msg_controllen)
            {
                received.invalid = true;
                break;
            }
            let payload_length = header_length - prefix;
            if (*header).cmsg_level == libc::SOL_SOCKET && (*header).cmsg_type == libc::SCM_RIGHTS {
                if !payload_length.is_multiple_of(size_of::<RawFd>()) {
                    received.invalid = true;
                }
                for index in 0..payload_length / size_of::<RawFd>() {
                    let raw = std::ptr::read_unaligned(
                        libc::CMSG_DATA(header).cast::<RawFd>().add(index),
                    );
                    let owned = OwnedFd::from_raw_fd(raw);
                    if received.rights_count < MAX_RIGHTS {
                        received.rights[received.rights_count] = Some(owned);
                    } else {
                        received.invalid = true;
                        drop(owned);
                    }
                    received.rights_count += 1;
                }
            } else if (*header).cmsg_level == libc::SOL_SOCKET && (*header).cmsg_type == SCM_PIDFD {
                // SO_PASSPIDFD may already be enabled on an owned control.
                // Refusal still owns every actual delivered pidfd. Never use
                // it as authorization, and continue parsing remaining rights.
                // Linux can report a negative errno instead of installing an
                // fd (net/core/scm.c:scm_pidfd_recv); that is not an OwnedFd.
                received.invalid = true;
                for index in 0..payload_length / size_of::<RawFd>() {
                    let raw = std::ptr::read_unaligned(
                        libc::CMSG_DATA(header).cast::<RawFd>().add(index),
                    );
                    if raw >= 0 {
                        drop(OwnedFd::from_raw_fd(raw));
                    }
                }
            } else if (*header).cmsg_level == libc::SOL_SOCKET
                && (*header).cmsg_type == libc::SCM_CREDENTIALS
            {
                if payload_length != size_of::<libc::ucred>() || received.credentials.is_some() {
                    received.invalid = true;
                } else {
                    let credentials =
                        std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<libc::ucred>());
                    if credentials.pid <= 0 {
                        received.invalid = true;
                    }
                    received.credentials = Some(PeerIdentity {
                        pid: u32::try_from(credentials.pid).ok(),
                        uid: credentials.uid,
                        gid: credentials.gid,
                    });
                }
            } else {
                received.invalid = true;
            }
            header = libc::CMSG_NXTHDR(&message, header);
        }
    }
    Ok(received)
}
