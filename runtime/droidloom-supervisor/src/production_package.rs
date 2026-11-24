//! Fixed live package retirement protocol over the existing broker socket.
//!
//! Public callers supply only Upgrade/Remove and their already held fixed EX
//! guard. Peer PIDFDs, installed executable identities, manager Invocation and
//! MAC observations come from the kernel/live providers. A JSON reply alone
//! cannot construct LivePackageRetirement. Package hooks retain their existing
//! protected refusal until this complete path receives independent qualification.

use crate::production_cgroup::PackageBrokerUnit;
use crate::production_configuration::{
    MaintenanceFence, PackageConfigurationLock, ReceivedPackageConfigurationLock,
};
use crate::production_mac::{
    PackageMacOwner, PackageMacPreparation, PackageMacWitness,
    PackageSelectedStream, KernelFirstPackageStream,
};
use super::production::ProductionAcceptedStream;
use crate::production_namespace::TreeExit;
use crate::production_selection::ProductionSelection;
use serde::{Deserialize, Serialize};
use std::ffi::CStr;
use std::fs::{File, Metadata};
use std::io::{self, Read, Write};
use std::os::fd::{AsFd, AsRawFd, BorrowedFd, FromRawFd};
use std::os::unix::fs::MetadataExt;
use std::os::unix::net::UnixStream;
use std::time::{Duration, Instant};

#[path = "production_package_peer.rs"]
mod peer;
pub(crate) use peer::PackageProcess;
use peer::before;

const SCHEMA: &str = "droidloom-live-package-retirement-v1";
const PREFIX: u8 = 0;
const FRAME_LIMIT: usize = 4096;
const FRAME_TIME: Duration = Duration::from_secs(2);
// The owner phase covers 75 seconds of orderly Android shutdown, the existing
// 15/10-second fallback and bounded resource checks. Native-unit stop is a
// separate existing 120-second helper budget, within one absolute transaction.
const OWNER_RETIREMENT_TIME: Duration = Duration::from_secs(120);
const NATIVE_STOP_TIME: Duration = Duration::from_secs(120);
const TRANSACTION_TIME: Duration = OWNER_RETIREMENT_TIME.saturating_add(NATIVE_STOP_TIME);

// The native phase begins only after the resource-owner acknowledgement. Keep
// its separate budget within the deadline established by that original RPC.
fn bounded_native_stop_deadline(now: Instant, transaction_deadline: Instant) -> io::Result<Instant> {
    if now >= transaction_deadline {
        return Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "original package retirement transaction expired before native stop",
        ));
    }
    let phase_deadline = now.checked_add(NATIVE_STOP_TIME).ok_or_else(|| {
        io::Error::new(io::ErrorKind::TimedOut, "native stop deadline overflow")
    })?;
    Ok(phase_deadline.min(transaction_deadline))
}

fn denied(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, message)
}
fn other(error: impl std::fmt::Display) -> io::Error {
    io::Error::other(error.to_string())
}

/// The only requested package operations; no host command or path is accepted.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum PackageOperation {
    Upgrade,
    Remove,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Probe {
    schema: String,
    operation: PackageOperation,
    nonce: [u8; 32],
    selection: [u8; 32],
    offset: u64,
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Commit {
    schema: String,
    nonce: [u8; 32],
    fence: [u8; 32],
    offset: u64,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
enum Phase {
    Supported,
    Retired,
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Reply {
    schema: String,
    phase: Phase,
    operation: PackageOperation,
    nonce: [u8; 32],
    selection: [u8; 32],
    invocation: [u8; 16],
    offset: u64,
    fence: Option<[u8; 32]>,
}
#[derive(Serialize)]
struct DenyFence<'a> {
    schema: &'static str,
    operation: PackageOperation,
    nonce: &'a [u8; 32],
    selection: &'a [u8; 32],
    broker_invocation: &'a [u8; 16],
    resource_retirement_grant: bool,
}
fn fence_body(probe: &Probe, invocation: &[u8; 16]) -> io::Result<Vec<u8>> {
    let body = serde_json::to_vec(&DenyFence {
        schema: "droidloom-package-maintenance-deny-v1",
        operation: probe.operation,
        nonce: &probe.nonce,
        selection: &probe.selection,
        broker_invocation: invocation,
        resource_retirement_grant: false,
    })
    .map_err(other)?;
    if body.is_empty() || body.len() > FRAME_LIMIT {
        return Err(denied("maintenance body bound"));
    }
    Ok(body)
}
fn random<const N: usize>() -> io::Result<[u8; N]> {
    let deadline = Instant::now() + FRAME_TIME;
    let mut bytes = [0_u8; N];
    let mut offset = 0;
    while offset < N {
        before(deadline)?;
        let n = unsafe {
            libc::getrandom(
                bytes[offset..].as_mut_ptr().cast(),
                N - offset,
                libc::GRND_NONBLOCK,
            )
        };
        if n < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(e);
        }
        if n == 0 {
            return Err(denied("kernel did not provide fresh transaction entropy"));
        }
        offset += n as usize;
    }
    if bytes.iter().all(|n| *n == 0) {
        return Err(denied("zero transaction entropy"));
    }
    Ok(bytes)
}
fn offset_token() -> io::Result<u64> {
    Ok((u64::from_le_bytes(random()?) & ((1_u64 << 52) - 1)) + 1)
}
fn position(fd: BorrowedFd<'_>) -> io::Result<u64> {
    let n = unsafe { libc::lseek(fd.as_raw_fd(), 0, libc::SEEK_CUR) };
    if n < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(n as u64)
    }
}
fn seek(fd: BorrowedFd<'_>, value: u64) -> io::Result<()> {
    if value > i64::MAX as u64 {
        return Err(denied("setup lock description offset bound"));
    }
    if unsafe { libc::lseek(fd.as_raw_fd(), value as libc::off_t, libc::SEEK_SET) }
        != value as libc::off_t
    {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}
struct RestoreOffset<'a> {
    fd: BorrowedFd<'a>,
    original: u64,
    restored: bool,
}
impl<'a> RestoreOffset<'a> {
    fn new(fd: BorrowedFd<'a>) -> io::Result<Self> {
        Ok(Self {
            fd,
            original: position(fd)?,
            restored: false,
        })
    }
    fn restore(&mut self) -> io::Result<()> {
        seek(self.fd, self.original)?;
        self.restored = true;
        Ok(())
    }
}
impl Drop for RestoreOffset<'_> {
    fn drop(&mut self) {
        // No file bytes or flock operation change. Failed/unknown RPC delivery
        // leaves the deny inode present; restoration cannot issue a grant.
        if !self.restored {
            let _ = seek(self.fd, self.original);
        }
    }
}

fn read_bytes(stream: &mut UnixStream, mut bytes: &mut [u8], deadline: Instant) -> io::Result<()> {
    while !bytes.is_empty() {
        before(deadline)?;
        stream.set_read_timeout(Some(deadline.saturating_duration_since(Instant::now())))?;
        match stream.read(bytes) {
            Ok(0) => {
                return Err(io::Error::new(
                    io::ErrorKind::UnexpectedEof,
                    "original package peer disconnected",
                ));
            }
            Ok(n) => bytes = &mut bytes[n..],
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e),
        }
    }
    before(deadline)
}
fn write_bytes(stream: &mut UnixStream, mut bytes: &[u8], deadline: Instant) -> io::Result<()> {
    while !bytes.is_empty() {
        before(deadline)?;
        stream.set_write_timeout(Some(deadline.saturating_duration_since(Instant::now())))?;
        match stream.write(bytes) {
            Ok(0) => {
                return Err(io::Error::new(
                    io::ErrorKind::WriteZero,
                    "package peer did not accept bytes",
                ));
            }
            Ok(n) => bytes = &bytes[n..],
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e),
        }
    }
    before(deadline)
}
fn receive<T: serde::de::DeserializeOwned>(
    stream: &mut UnixStream,
    deadline: Instant,
) -> io::Result<T> {
    // Waiting for the original owner may span bounded retirement. Once its
    // frame begins, the complete finite body must arrive within FRAME_TIME.
    let mut size = [0; 4];
    read_bytes(stream, &mut size, deadline)?;
    let size = u32::from_le_bytes(size) as usize;
    if size == 0 || size > FRAME_LIMIT {
        return Err(denied("package protocol frame bound"));
    }
    let body_deadline = deadline.min(Instant::now() + FRAME_TIME);
    let mut bytes = vec![0; size];
    read_bytes(stream, &mut bytes, body_deadline)?;
    serde_json::from_slice(&bytes).map_err(other)
}
fn send<T: Serialize>(stream: &mut UnixStream, value: &T, deadline: Instant) -> io::Result<()> {
    let bytes = serde_json::to_vec(value).map_err(other)?;
    if bytes.is_empty() || bytes.len() > FRAME_LIMIT {
        return Err(denied("package protocol response bound"));
    }
    let deadline = deadline.min(Instant::now() + FRAME_TIME);
    write_bytes(stream, &(bytes.len() as u32).to_le_bytes(), deadline)?;
    write_bytes(stream, &bytes, deadline)
}

/// A leading non-JSON byte separates this fixed protocol from all legacy and
/// progress envelopes. Peeking does not consume or discard ancillary FDs.
pub(super) fn is_package(stream: &UnixStream) -> io::Result<bool> {
    stream.set_read_timeout(Some(FRAME_TIME))?;
    let mut first = 0_u8;
    let n = unsafe {
        libc::recv(
            stream.as_raw_fd(),
            (&mut first as *mut u8).cast(),
            1,
            libc::MSG_PEEK,
        )
    };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(n == 1 && first == PREFIX)
}

fn open(parent: i32, name: &CStr, flags: i32) -> io::Result<File> {
    let fd = unsafe {
        libc::openat(
            parent,
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(unsafe { File::from_raw_fd(fd) })
    }
}
fn directory_node(m: &Metadata) -> [u64; 5] {
    [
        m.dev(),
        m.ino(),
        m.mode() as u64,
        m.uid() as u64,
        m.gid() as u64,
    ]
}
fn socket_node(m: &Metadata) -> ([u64; 7], [i64; 4]) {
    (
        [
            m.dev(),
            m.ino(),
            m.mode() as u64,
            m.uid() as u64,
            m.gid() as u64,
            m.nlink(),
            m.len(),
        ],
        [m.mtime(), m.mtime_nsec(), m.ctime(), m.ctime_nsec()],
    )
}

fn retired_runtime_parent(run: &File, held: &File, identity: &[u64; 5]) -> io::Result<Option<File>> {
    if directory_node(&held.metadata()?) != *identity {
        return Err(denied("original retired runtime directory changed"));
    }
    match open(run.as_raw_fd(), c"droidloom", libc::O_PATH | libc::O_DIRECTORY) {
        Ok(named) if directory_node(&named.metadata()?) == *identity => Ok(Some(named)),
        Ok(_) => Err(denied("retired runtime directory was replaced")),
        Err(error) if error.kind() == io::ErrorKind::NotFound && held.metadata()?.nlink() == 0 => Ok(None),
        Err(error) => Err(error),
    }
}
enum PackageSocket {
    Selected(PackageSelectedStream),
    KernelFirst(KernelFirstPackageStream),
}
impl PackageSocket {
    fn connect(&mut self) -> io::Result<()> {
        match self {
            Self::Selected(value) => value.connect().map_err(other),
            Self::KernelFirst(value) => value.connect().map_err(other),
        }
    }
    fn stream(&self) -> io::Result<&UnixStream> {
        match self {
            Self::Selected(value) => value.stream().map_err(other),
            Self::KernelFirst(value) => value.stream().map_err(other),
        }
    }
    fn stream_mut(&mut self) -> io::Result<&mut UnixStream> {
        match self {
            Self::Selected(value) => value.stream_mut().map_err(other),
            Self::KernelFirst(value) => value.stream_mut().map_err(other),
        }
    }
}
struct SocketCustody {
    // The selected stream closes before its original server-path custody.
    selected: Option<PackageSocket>,
    directories: Vec<(File, [u64; 5])>,
    node: File,
    seal: ([u64; 7], [i64; 4]),
}
impl SocketCustody {
    fn capture() -> io::Result<Self> {
        let root = open(libc::AT_FDCWD, c"/", libc::O_PATH | libc::O_DIRECTORY)?;
        let mut directories = vec![(root, [0; 5])];
        for name in [c"run", c"droidloom"] {
            let value = open(
                directories.last().unwrap().0.as_raw_fd(),
                name,
                libc::O_PATH | libc::O_DIRECTORY,
            )?;
            directories.push((value, [0; 5]));
        }
        for (d, identity) in &mut directories {
            let m = d.metadata()?;
            if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {
                return Err(denied("fixed broker socket parent custody differs"));
            }
            *identity = directory_node(&m);
        }
        let node = open(
            directories.last().unwrap().0.as_raw_fd(),
            c"control.sock",
            libc::O_PATH | libc::O_NONBLOCK,
        )?;
        let m = node.metadata()?;
        if m.mode() & libc::S_IFMT != libc::S_IFSOCK
            || m.uid() != 0
            || m.gid() != 0
            || m.nlink() != 1
        {
            return Err(denied("fixed broker socket inode custody differs"));
        }
        Ok(Self {
            selected: None,
            directories,
            seal: socket_node(&m),
            node,
        })
    }
    fn revalidate(&self) -> io::Result<()> {
        let current = Self::capture()?;
        if current.seal != self.seal || socket_node(&self.node.metadata()?) != self.seal {
            return Err(denied("original broker socket inode changed"));
        }
        for ((held, original), (_, named)) in
            self.directories.iter().zip(current.directories.iter())
        {
            if directory_node(&held.metadata()?) != *original || original != named {
                return Err(denied("original broker socket parent changed"));
            }
        }
        Ok(())
    }
    fn revalidate_retired(&self) -> io::Result<()> {
        let mut current = open(libc::AT_FDCWD, c"/", libc::O_PATH | libc::O_DIRECTORY)?;
        for (index, (held, original)) in self.directories[..2].iter().enumerate() {
            if index > 0 {
                current = open(current.as_raw_fd(), [c"run", c"droidloom"][index - 1],
                    libc::O_PATH | libc::O_DIRECTORY)?;
            }
            if directory_node(&held.metadata()?) != *original || directory_node(&current.metadata()?) != *original {
                return Err(denied("original retired socket parent changed"));
            }
        }
        // systemd may remove its original RuntimeDirectory after stopping the
        // legacy native actor. Observe that terminal inode directly; neither a
        // renamed live directory nor a replacement at the fixed name qualifies.
        let runtime = retired_runtime_parent(&current, &self.directories[2].0, &self.directories[2].1)?;
        let m = self.node.metadata()?;
        let original = &self.seal.0;
        if [m.dev(), m.ino(), m.mode() as u64, m.uid() as u64, m.gid() as u64] != original[..5]
            || m.nlink() != 0
        {
            return Err(denied("original broker socket inode was not retired"));
        }
        let Some(runtime) = runtime else { return Ok(()); };
        match open(runtime.as_raw_fd(), c"control.sock", libc::O_PATH | libc::O_NONBLOCK) {
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(error),
            Ok(_) => Err(denied("broker socket was recreated after original retirement")),
        }
    }
    fn connect(&mut self, owner: &PackageMacOwner, deadline: Instant) -> io::Result<()> {
        self.revalidate()?;
        if self.selected.is_some() {
            return Err(denied(
                "package socket cannot reconnect to another generation",
            ));
        }
        // Preparation has no worker. Persist original custody before the
        // first namespace/socket helper can be created, including failure.
        self.selected = Some(if owner.selection().is_kernel_first() {
            PackageSocket::KernelFirst(KernelFirstPackageStream::prepare(owner, &self.node, deadline).map_err(other)?)
        } else {
            PackageSocket::Selected(PackageSelectedStream::prepare(owner, &self.node, deadline).map_err(other)?)
        });
        self.selected.as_mut().unwrap().connect()?;
        self.revalidate()
    }

    fn stream(&self) -> io::Result<&UnixStream> {
        self.selected
            .as_ref()
            .ok_or_else(|| denied("original package stream is absent"))?
            .stream()
    }

    fn stream_mut(&mut self) -> io::Result<&mut UnixStream> {
        self.selected
            .as_mut()
            .ok_or_else(|| denied("original package stream is absent"))?
            .stream_mut()
    }
}

/// Real live resource result only. It does not prove the three native units
/// stopped, authorize package replacement, or permit removal of the deny fence.
/// Those later gates cannot be replaced by serializing this in-memory value.
pub struct LivePackageRetirement<'a> {
    // Close the selected package stream before the remaining original owners.
    socket: SocketCustody,
    lock: &'a PackageConfigurationLock,
    fence: MaintenanceFence,
    broker: PackageProcess,
    unit: PackageBrokerUnit,
    mac: PackageMacWitness,
    deadline: Instant,
}
impl<'a> LivePackageRetirement<'a> {
    pub fn revalidate(&self) -> io::Result<()> {
        before(self.deadline)?;
        self.lock.revalidate_fence(&self.fence)?;
        self.mac.selection().revalidate().map_err(other)?;
        self.socket.revalidate()?;
        self.unit
            .revalidate(&self.broker, self.deadline)
            .map_err(other)?;
        self.mac
            .revalidate(&self.broker, &self.unit, self.socket.stream()?)
            .map_err(other)?;
        before(self.deadline)
    }

    /// Start the native-stop budget after the exact resource-retirement ACK.
    /// Revalidate the original owner and deny fence first; this cannot renew or
    /// extend the absolute deadline retained from that same transaction.
    pub fn native_stop_deadline(&self) -> io::Result<Instant> {
        self.revalidate()?;
        bounded_native_stop_deadline(Instant::now(), self.deadline)
    }

    /// Consume the original live result only after the native stop operation.
    /// The held PIDFD and original manager invocation must show a clean exit;
    /// no new connection, numeric PID, receipt or caller assertion is accepted.
    /// The caller must separately retire the other fixed native actors.
    pub fn complete_native_stop(self) -> io::Result<NativePackageRetirement<'a>> {
        let value = NativePackageRetirement { original: self };
        value.revalidate()?;
        Ok(value)
    }
}

/// The original resource result plus its original broker's terminal native
/// lifetime. This keeps the EX guard borrowed and the durable deny fence held.
/// It neither removes that fence nor grants an automatic new activation.
pub struct NativePackageRetirement<'a> {
    original: LivePackageRetirement<'a>,
}
impl NativePackageRetirement<'_> {
    pub fn revalidate(&self) -> io::Result<()> {
        let original = &self.original;
        before(original.deadline)?;
        original.lock.revalidate_fence(&original.fence)?;
        original.mac.selection().revalidate().map_err(other)?;
        original.mac.revalidate_after_broker_exit(&original.broker, &original.unit, original.deadline)
            .map_err(other)?;
        original.socket.revalidate_retired()?;
        before(original.deadline)
    }
}

/// One original helper-to-broker transaction. No retry, caller PID, socket,
/// supplied challenge, JSON grant, Start or service-manager Stop is accepted.
pub fn retire_for_package<'a>(
    lock: &'a PackageConfigurationLock,
    operation: PackageOperation,
) -> io::Result<LivePackageRetirement<'a>> {
    let deadline = Instant::now() + TRANSACTION_TIME;
    lock.require_unfenced()?;
    let selection = ProductionSelection::for_package(lock).map_err(other)?;
    let local = PackageProcess::own_helper()?;
    let preparation = PackageMacPreparation::helper(selection, local, deadline).map_err(other)?;
    let mut socket = SocketCustody::capture()?;
    socket.connect(preparation.owner(), deadline)?;
    // Public protocol announcement carries no lock FD or authority. It lets
    // the server classify the request while both sides validate live inputs.
    write_bytes(
        socket.stream_mut()?,
        &[PREFIX],
        deadline.min(Instant::now() + FRAME_TIME),
    )?;
    let broker = PackageProcess::peer_broker(socket.stream()?)?;
    let unit = PackageBrokerUnit::capture(
        &broker,
        preparation.owner().retain_original().map_err(other)?,
        deadline,
    )
    .map_err(other)?;
    let mac = preparation
        .finish(&broker, &unit, socket.stream()?)
        .map_err(other)?;
    let mut cursor = RestoreOffset::new(lock.as_fd())?;
    let probe = Probe {
        schema: SCHEMA.into(),
        operation,
        nonce: random()?,
        selection: mac.selection().package_binding(),
        offset: offset_token()?,
    };
    seek(lock.as_fd(), probe.offset)?;
    lock.require_unfenced()?;
    let descriptor = File::from(lock.as_fd().try_clone_to_owned()?);
    socket.stream()?.set_write_timeout(Some(FRAME_TIME))?;
    super::apk::send_file(socket.stream()?, PREFIX, &descriptor).map_err(other)?;
    drop(descriptor);
    send(socket.stream_mut()?, &probe, deadline)?;
    let supported: Reply = receive(socket.stream_mut()?, deadline)?;
    if supported.schema != SCHEMA
        || supported.phase != Phase::Supported
        || supported.operation != operation
        || supported.nonce != probe.nonce
        || supported.selection != probe.selection
        || supported.invocation != unit.invocation()
        || supported.fence.is_some()
        || supported.offset == 0
        || supported.offset > (1_u64 << 52)
        || supported.offset == probe.offset
        || position(lock.as_fd())? != supported.offset
    {
        return Err(denied(
            "package preflight or shared open-file-description proof failed",
        ));
    }
    // The receiver moved our original descriptor's cursor, without modifying
    // file bytes. We now move it again; its next read must observe this value.
    let confirmation = supported.offset ^ (1_u64 << 51);
    seek(lock.as_fd(), confirmation)?;
    socket.revalidate()?;
    unit.revalidate(&broker, deadline).map_err(other)?;
    mac.revalidate(&broker, &unit, socket.stream()?)
        .map_err(other)?;
    lock.require_unfenced()?;
    let fence = lock.create_maintenance_fence(&fence_body(&probe, &unit.invocation())?)?;
    let commit = Commit {
        schema: SCHEMA.into(),
        nonce: probe.nonce,
        fence: fence.binding(),
        offset: confirmation,
    };
    // From this send onward unknown delivery is a refusal with the durable
    // deny fence retained. The client never reconnects to another generation.
    send(socket.stream_mut()?, &commit, deadline)?;
    let response: Reply = receive(socket.stream_mut()?, deadline)?;
    if response.schema != SCHEMA
        || response.phase != Phase::Retired
        || response.operation != operation
        || response.nonce != probe.nonce
        || response.selection != probe.selection
        || response.invocation != unit.invocation()
        || response.fence != Some(fence.binding())
        || response.offset != confirmation
    {
        return Err(denied(
            "original broker did not return the exact live retirement result",
        ));
    }
    cursor.restore()?;
    let value = LivePackageRetirement {
        lock,
        fence,
        broker,
        unit,
        mac,
        socket,
        deadline,
    };
    value.revalidate()?;
    Ok(value)
}

/// Owns the received same-description EX guard and actual original peer. Only
/// the original ProductionDaemon may provide the actual terminal TreeExit.
pub(crate) struct ServerTransaction<'listener> {
    // This borrow keeps the actual startup listener authority alive.
    stream: ProductionAcceptedStream<'listener>,
    lock: ReceivedPackageConfigurationLock,
    helper: PackageProcess,
    unit: PackageBrokerUnit,
    mac: PackageMacWitness,
    probe: Probe,
    fence: Option<MaintenanceFence>,
    final_offset: Option<u64>,
    deadline: Instant,
}
impl<'listener> ServerTransaction<'listener> {
    pub(crate) fn receive(mut stream: ProductionAcceptedStream<'listener>) -> io::Result<Self> {
        let deadline = Instant::now() + TRANSACTION_TIME;
        let local = PackageProcess::own_broker()?;
        let helper = PackageProcess::peer_helper(stream.stream().map_err(other)?)?;
        stream
            .stream()
            .map_err(other)?
            .set_read_timeout(Some(FRAME_TIME))?;
        let (announcement, unexpected) =
            super::apk::receive_file(stream.stream().map_err(other)?).map_err(other)?;
        if announcement != PREFIX || unexpected.is_some() {
            return Err(denied(
                "package protocol announcement cannot carry a descriptor",
            ));
        }
        before(deadline)?;
        stream
            .stream()
            .map_err(other)?
            .set_read_timeout(Some(deadline.saturating_duration_since(Instant::now())))?;
        let (prefix, descriptor) =
            super::apk::receive_file(stream.stream().map_err(other)?).map_err(other)?;
        if prefix != PREFIX {
            return Err(denied("invalid fixed package protocol prefix"));
        }
        let lock = ReceivedPackageConfigurationLock::from_received(
            descriptor
                .ok_or_else(|| denied("package request requires the actual EX descriptor"))?,
        )?;
        lock.require_unfenced()?;
        let probe: Probe = receive(stream.stream_mut().map_err(other)?, deadline)?;
        if probe.schema != SCHEMA
            || probe.nonce.iter().all(|n| *n == 0)
            || probe.offset == 0
            || probe.offset > (1_u64 << 52)
            || position(lock.as_fd())? != probe.offset
        {
            return Err(denied(
                "invalid package request or original EX description cursor",
            ));
        }
        let selection = ProductionSelection::for_received_package(&lock).map_err(other)?;
        if probe.selection != selection.package_binding() {
            return Err(denied("package selected inputs differ"));
        }
        // This preparation precedes this transaction's manager connection.
        // It does not claim to have created the already accepted listener stream.
        let preparation =
            PackageMacPreparation::broker(selection, local, deadline).map_err(other)?;
        let unit = PackageBrokerUnit::capture(
            preparation.owner().local(),
            preparation.owner().retain_original().map_err(other)?,
            deadline,
        )
        .map_err(other)?;
        let mac = preparation
            .finish(&helper, &unit, stream.stream().map_err(other)?)
            .map_err(other)?;
        let value = Self {
            lock,
            helper,
            unit,
            mac,
            stream,
            probe,
            fence: None,
            final_offset: None,
            deadline,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(crate) fn selection(&self) -> &ProductionSelection {
        self.mac.selection()
    }
    pub(crate) fn revalidate(&self) -> io::Result<()> {
        before(self.deadline)?;
        self.lock.revalidate()?;
        self.mac.selection().revalidate().map_err(other)?;
        self.unit
            .revalidate(self.mac.local(), self.deadline)
            .map_err(other)?;
        self.mac
            .revalidate(
                &self.helper,
                &self.unit,
                self.stream.stream().map_err(other)?,
            )
            .map_err(other)?;
        if let Some(fence) = &self.fence {
            self.lock.revalidate_fence(fence)?;
        }
        before(self.deadline)
    }
    pub(crate) fn fence_before_retirement(&mut self) -> io::Result<()> {
        before(self.deadline - NATIVE_STOP_TIME)?;
        self.revalidate()?;
        self.lock.require_unfenced()?;
        let token = offset_token()?;
        if token == self.probe.offset {
            return Err(denied("fresh OFD challenge collided"));
        }
        seek(self.lock.as_fd(), token)?;
        let reply = Reply {
            schema: SCHEMA.into(),
            phase: Phase::Supported,
            operation: self.probe.operation,
            nonce: self.probe.nonce,
            selection: self.probe.selection,
            invocation: self.unit.invocation(),
            offset: token,
            fence: None,
        };
        send(
            self.stream.stream_mut().map_err(other)?,
            &reply,
            self.deadline,
        )?;
        let commit: Commit = receive(self.stream.stream_mut().map_err(other)?, self.deadline)?;
        let expected = token ^ (1_u64 << 51);
        if commit.schema != SCHEMA
            || commit.nonce != self.probe.nonce
            || commit.offset != expected
            || position(self.lock.as_fd())? != expected
        {
            return Err(denied("two-way original OFD confirmation failed"));
        }
        let body = fence_body(&self.probe, &self.unit.invocation())?;
        let fence = self.lock.observe_fence(&body)?;
        if fence.binding() != commit.fence {
            return Err(denied("original helper's deny inode changed"));
        }
        self.lock.confirm_fence_durable(&fence)?;
        self.fence = Some(fence);
        self.final_offset = Some(expected);
        self.revalidate()
    }
    pub(super) fn complete(&mut self, original: &TreeExit) -> io::Result<()> {
        self.revalidate()?;
        original.verify_package_retirement().map_err(other)?;
        self.send_complete()
    }
    pub(crate) fn complete_early(
        &mut self,
        original: &crate::production_selection::early_generation::EarlyPackageRetirement,
    ) -> io::Result<()> {
        self.revalidate()?;
        original.verify_package_retirement(self.selection())?;
        self.send_complete()
    }
    pub(crate) fn deadline(&self) -> Instant {
        self.deadline
    }
    fn send_complete(&mut self) -> io::Result<()> {
        before(self.deadline - NATIVE_STOP_TIME)?;
        let fence = self
            .fence
            .as_ref()
            .ok_or_else(|| denied("actual persistent deny fence is absent"))?;
        let offset = self
            .final_offset
            .ok_or_else(|| denied("same EX description was not confirmed"))?;
        if position(self.lock.as_fd())? != offset {
            return Err(denied("original client EX description changed"));
        }
        let reply = Reply {
            schema: SCHEMA.into(),
            phase: Phase::Retired,
            operation: self.probe.operation,
            nonce: self.probe.nonce,
            selection: self.probe.selection,
            invocation: self.unit.invocation(),
            offset,
            fence: Some(fence.binding()),
        };
        send(
            self.stream.stream_mut().map_err(other)?,
            &reply,
            self.deadline,
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::production_configuration::DirectorySetupLock;
    use std::os::unix::fs::OpenOptionsExt;

    #[test]
    fn package_native_stop_budget_starts_after_the_owner_phase() {
        let started = Instant::now();
        let transaction_deadline = started + TRANSACTION_TIME;
        for owner_seconds in [0, 75, 119, 120] {
            let acknowledged = started + Duration::from_secs(owner_seconds);
            let native_deadline =
                bounded_native_stop_deadline(acknowledged, transaction_deadline).unwrap();
            assert_eq!(native_deadline.duration_since(acknowledged), NATIVE_STOP_TIME);
            assert!(native_deadline <= transaction_deadline);
        }
        // The old helper budget incorrectly left only 45 seconds after a
        // normal 75-second resource shutdown.
        let acknowledged = started + Duration::from_secs(75);
        assert_eq!(
            bounded_native_stop_deadline(acknowledged, transaction_deadline).unwrap(),
            started + Duration::from_secs(195)
        );
    }

    #[test]
    fn package_native_stop_budget_never_renews_the_original_transaction() {
        let started = Instant::now();
        let transaction_deadline = started + TRANSACTION_TIME;
        for elapsed in [121, 239] {
            let now = started + Duration::from_secs(elapsed);
            assert_eq!(
                bounded_native_stop_deadline(now, transaction_deadline).unwrap(),
                transaction_deadline
            );
        }
        let last_instant = transaction_deadline - Duration::from_nanos(1);
        assert_eq!(
            bounded_native_stop_deadline(last_instant, transaction_deadline).unwrap(),
            transaction_deadline
        );
        for now in [transaction_deadline, transaction_deadline + Duration::from_nanos(1)] {
            assert_eq!(
                bounded_native_stop_deadline(now, transaction_deadline).unwrap_err().kind(),
                io::ErrorKind::TimedOut
            );
        }
    }

    #[test]
    fn package_terminal_runtime_directory_accepts_only_original_removal_or_original_name() {
        let fixture = tempfile::tempdir().unwrap();
        let run = File::options().read(true).custom_flags(libc::O_PATH | libc::O_DIRECTORY)
            .open(fixture.path()).unwrap();
        let directory = fixture.path().join("droidloom");
        std::fs::create_dir(&directory).unwrap();
        let held = File::options().read(true).custom_flags(libc::O_PATH | libc::O_DIRECTORY)
            .open(&directory).unwrap();
        let identity = directory_node(&held.metadata().unwrap());
        assert!(retired_runtime_parent(&run, &held, &identity).unwrap().is_some());
        let renamed = fixture.path().join("old-droidloom");
        std::fs::rename(&directory, &renamed).unwrap();
        assert!(retired_runtime_parent(&run, &held, &identity).is_err());
        std::fs::create_dir(&directory).unwrap();
        assert!(retired_runtime_parent(&run, &held, &identity).is_err());
        std::fs::remove_dir(&directory).unwrap();
        std::fs::remove_dir(&renamed).unwrap();
        assert_eq!(held.metadata().unwrap().nlink(), 0);
        assert!(retired_runtime_parent(&run, &held, &identity).unwrap().is_none());
        std::fs::create_dir(&directory).unwrap();
        assert!(retired_runtime_parent(&run, &held, &identity).is_err());
    }

    #[test]
    fn package_scm_lock_proves_the_same_open_file_description_in_both_directions() {
        let directory = tempfile::tempdir().unwrap();
        let parent = File::options()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY)
            .open(directory.path())
            .unwrap();
        let lock = DirectorySetupLock::exclusive_at(&parent, unsafe { libc::getuid() }, unsafe {
            libc::getgid()
        })
        .unwrap();
        let sent = File::from(lock.as_fd().try_clone_to_owned().unwrap());
        let (left, right) = UnixStream::pair().unwrap();
        seek(lock.as_fd(), 1234567).unwrap();
        super::super::apk::send_file(&left, PREFIX, &sent).unwrap();
        let (byte, received) = super::super::apk::receive_file(&right).unwrap();
        assert_eq!(byte, PREFIX);
        let received = received.unwrap();
        assert_eq!(unsafe { libc::fcntl(received.as_raw_fd(), libc::F_GETFL) } & libc::O_ACCMODE, libc::O_RDONLY);
        assert_eq!(std::os::unix::fs::FileExt::write_at(&received, b"not permitted", 0).unwrap_err().raw_os_error(), Some(libc::EBADF));
        assert_eq!(position(received.as_fd()).unwrap(), 1234567);
        seek(received.as_fd(), 9876543).unwrap();
        assert_eq!(position(lock.as_fd()).unwrap(), 9876543);
        seek(lock.as_fd(), 7654321).unwrap();
        assert_eq!(position(received.as_fd()).unwrap(), 7654321);
        let independent = File::options()
            .read(true)
            .open(directory.path().join("setup.lock"))
            .unwrap();
        assert_eq!(position(independent.as_fd()).unwrap(), 0);
        assert_eq!(
            unsafe { libc::flock(independent.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            -1
        );
        assert_eq!(
            io::Error::last_os_error().raw_os_error(),
            Some(libc::EWOULDBLOCK)
        );
        drop(sent);
        drop(lock);
        assert_eq!(
            unsafe { libc::flock(independent.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            -1
        );
        drop(received);
        assert_eq!(
            unsafe { libc::flock(independent.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        assert!(
            std::fs::read(directory.path().join("setup.lock"))
                .unwrap()
                .is_empty()
        );
    }

    #[test]
    fn package_partial_frames_and_peer_loss_cannot_issue_a_response() {
        let (mut sender, mut receiver) = UnixStream::pair().unwrap();
        sender.write_all(&10_u32.to_le_bytes()).unwrap();
        sender.write_all(b"{").unwrap();
        drop(sender);
        assert!(
            matches!(receive::<Reply>(&mut receiver, Instant::now() + FRAME_TIME),
            Err(error) if error.kind() == io::ErrorKind::UnexpectedEof)
        );
        let (sender, mut receiver) = UnixStream::pair().unwrap();
        drop(sender);
        assert!(
            matches!(receive::<Reply>(&mut receiver, Instant::now() + FRAME_TIME),
            Err(error) if error.kind() == io::ErrorKind::UnexpectedEof)
        );
        let (mut sender, mut receiver) = UnixStream::pair().unwrap();
        sender.write_all(&0_u32.to_le_bytes()).unwrap();
        assert!(receive::<Reply>(&mut receiver, Instant::now() + FRAME_TIME).is_err());
        // A caller record is never deserialized as a live object. These types
        // are private transport messages; no LivePackageRetirement is created.
        let probe = Probe {
            schema: SCHEMA.into(),
            operation: PackageOperation::Remove,
            nonce: [1; 32],
            selection: [2; 32],
            offset: 3,
        };
        let value: serde_json::Value =
            serde_json::from_slice(&fence_body(&probe, &[4; 16]).unwrap()).unwrap();
        assert_eq!(
            value["resource_retirement_grant"],
            serde_json::Value::Bool(false)
        );
    }

    #[test]
    fn package_frames_are_bounded_typed_and_legacy_json_is_not_the_package_protocol() {
        let (mut left, right) = UnixStream::pair().unwrap();
        left.write_all(b"{").unwrap();
        assert!(!is_package(&right).unwrap());
        let (mut left, mut right) = UnixStream::pair().unwrap();
        left.write_all(&((FRAME_LIMIT as u32) + 1).to_le_bytes())
            .unwrap();
        assert!(receive::<Probe>(&mut right, Instant::now() + FRAME_TIME).is_err());
        let valid = Probe {
            schema: SCHEMA.into(),
            operation: PackageOperation::Upgrade,
            nonce: [7; 32],
            selection: [8; 32],
            offset: 12,
        };
        let mut bytes = serde_json::to_value(&valid).unwrap();
        bytes
            .as_object_mut()
            .unwrap()
            .insert("pid".into(), serde_json::json!(1));
        assert!(serde_json::from_value::<Probe>(bytes).is_err());
    }
}
