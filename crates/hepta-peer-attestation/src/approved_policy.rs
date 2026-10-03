//! Bounded root-owned configuration. Namespace-local custody is not host trust.
//! No observed peer, environment, NSS lookup, action grant or policy export.
use crate::control_owner::{
    AttestedRetainedReceiver, ControlOwnerPolicy, ControlRequestCustody,
    ControlRetainedAcceptedStream, RootPathAttestedHandoffReceiver, RootPathAttestedHandoffSender,
};
use crate::{AttestedPeer, PeerRuntimePolicy, ProcfsPeerAttestor};
use hepta_agent_transport::{
    AcceptedStreamCustody, PeerIdentity, PeerPolicy, RootPathControlConnection,
};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    ffi::CString,
    fmt,
    fs::File,
    os::fd::{AsRawFd, FromRawFd, OwnedFd},
    os::unix::{
        ffi::OsStrExt,
        fs::{FileExt, MetadataExt},
        net::UnixStream,
    },
    path::{Component, Path},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};

pub const DEFAULT_APPROVED_POLICY_PATH: &str = "/etc/hepta/approved-mechanisms.v1.conf";
pub const MAX_APPROVED_POLICY_BYTES: usize = 8192;
const SCHEMA: &str = "trillionnium.approved-mechanisms.v1";
mod request_binding;
pub use request_binding::{
    ApprovedAgentRequestBinding, ApprovedAgentRequestVerifier, ApprovedAgentSession,
};
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ApprovedPolicyError {
    InvalidConfiguration,
    SourceRefused,
    Changed,
    DeadlineExceeded,
    ProcessChanged,
    PeerRefused,
}
impl fmt::Display for ApprovedPolicyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::InvalidConfiguration => "approved configuration invalid",
            Self::SourceRefused => "approved configuration source refused",
            Self::Changed => "approved configuration retired",
            Self::DeadlineExceeded => "original approved scope expired",
            Self::ProcessChanged => "approved scope creating process changed",
            Self::PeerRefused => "approved mechanism refused",
        })
    }
}
impl std::error::Error for ApprovedPolicyError {}
fn remaining(pid: u32, deadline: Instant) -> Result<(), ApprovedPolicyError> {
    if pid != std::process::id() {
        return Err(ApprovedPolicyError::ProcessChanged);
    }
    if deadline
        .checked_duration_since(Instant::now())
        .filter(|v| !v.is_zero())
        .is_none()
    {
        return Err(ApprovedPolicyError::DeadlineExceeded);
    }
    Ok(())
}
#[derive(Clone, PartialEq, Eq)]
struct Entry {
    uid: u32,
    gid: u32,
    unit: String,
    cgroup: String,
    pin: String,
    principal: String,
}
impl Entry {
    fn runtime(&self) -> PeerRuntimePolicy {
        PeerRuntimePolicy {
            expected_uid: self.uid,
            expected_gid: self.gid,
            expected_systemd_unit: Some(self.unit.clone()),
            expected_cgroup_v2_path: self.cgroup.clone(),
        }
    }
    fn control(&self) -> Result<ControlOwnerPolicy, ApprovedPolicyError> {
        ControlOwnerPolicy::new(
            PeerPolicy {
                expected_uid: self.uid,
                expected_gid: Some(self.gid),
                expected_pid: None,
            },
            self.runtime(),
            self.pin.clone(),
        )
        .map_err(|_| ApprovedPolicyError::InvalidConfiguration)
    }
}
fn parse(bytes: &[u8]) -> Result<[Entry; 2], ApprovedPolicyError> {
    let bad = || ApprovedPolicyError::InvalidConfiguration;
    if bytes.is_empty()
        || bytes.len() > MAX_APPROVED_POLICY_BYTES
        || !bytes.is_ascii()
        || !bytes.ends_with(b"\n")
    {
        return Err(bad());
    }
    let text = std::str::from_utf8(bytes).map_err(|_| bad())?;
    let mut fields = BTreeMap::new();
    for line in text.split_terminator('\n') {
        let (k, v) = line.split_once('=').ok_or_else(bad)?;
        if k.is_empty() || v.is_empty() || v.contains('=') || fields.insert(k, v).is_some() {
            return Err(bad());
        }
    }
    let mut expected = vec!["schema".to_owned()];
    for role in ["control", "agent"] {
        for key in ["uid", "gid", "unit", "cgroup", "elf_sha256", "principal_id"] {
            expected.push(format!("{role}.{key}"))
        }
    }
    if fields.len() != 13
        || expected.iter().any(|k| !fields.contains_key(k.as_str()))
        || fields["schema"] != SCHEMA
    {
        return Err(bad());
    }
    let mut values = Vec::new();
    for role in ["control", "agent"] {
        let field = |name: &str| fields[format!("{role}.{name}").as_str()];
        let number = |name: &str| -> Result<u32, ApprovedPolicyError> {
            let v = field(name);
            if v.is_empty()
                || !v.bytes().all(|b| b.is_ascii_digit())
                || (v.len() > 1 && v.starts_with('0'))
            {
                return Err(bad());
            }
            let n: u32 = v.parse().map_err(|_| bad())?;
            if n == u32::MAX {
                return Err(bad());
            }
            Ok(n)
        };
        let unit = field("unit");
        if unit.len() > 128
            || crate::validate_unit_name(unit).is_err()
            || !unit
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"@_.:-".contains(&b))
        {
            return Err(bad());
        }
        let cgroup = field("cgroup");
        if cgroup.len() > 512
            || !cgroup.starts_with('/')
            || cgroup.split('/').skip(1).any(|p| {
                p.is_empty()
                    || p == "."
                    || p == ".."
                    || p.len() > 128
                    || !p
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"@_.:-".contains(&b))
            })
            || cgroup.rsplit('/').next() != Some(unit)
        {
            return Err(bad());
        }
        let pin = field("elf_sha256");
        if pin.len() != 64
            || !pin
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err(bad());
        }
        let principal = field("principal_id");
        if principal.len() > 64
            || !principal
                .bytes()
                .next()
                .is_some_and(|b| b.is_ascii_alphanumeric())
            || !principal
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"_.-".contains(&b))
        {
            return Err(bad());
        }
        values.push(Entry {
            uid: number("uid")?,
            gid: number("gid")?,
            unit: unit.into(),
            cgroup: cgroup.into(),
            pin: pin.into(),
            principal: principal.into(),
        });
    }
    if values[0].principal == values[1].principal {
        return Err(bad());
    }
    values.try_into().map_err(|_| bad())
}
#[derive(Clone, PartialEq, Eq)]
struct Identity {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    size: u64,
    nlink: u64,
    mtime: i64,
    mtime_ns: i64,
    ctime: i64,
    ctime_ns: i64,
}
impl Identity {
    fn file(fd: i32) -> Result<Self, ApprovedPolicyError> {
        let mut s = std::mem::MaybeUninit::<libc::stat>::uninit();
        if unsafe { libc::fstat(fd, s.as_mut_ptr()) } != 0 {
            return Err(ApprovedPolicyError::SourceRefused);
        }
        Ok(Self::from_stat(unsafe { s.assume_init() }))
    }
    fn named(parent: i32, name: &CString) -> Result<Self, ApprovedPolicyError> {
        let mut s = std::mem::MaybeUninit::<libc::stat>::uninit();
        if unsafe {
            libc::fstatat(
                parent,
                name.as_ptr(),
                s.as_mut_ptr(),
                libc::AT_SYMLINK_NOFOLLOW,
            )
        } != 0
        {
            return Err(ApprovedPolicyError::SourceRefused);
        }
        Ok(Self::from_stat(unsafe { s.assume_init() }))
    }
    fn from_stat(s: libc::stat) -> Self {
        Self {
            dev: s.st_dev,
            ino: s.st_ino,
            mode: s.st_mode,
            uid: s.st_uid,
            gid: s.st_gid,
            size: s.st_size as u64,
            nlink: s.st_nlink,
            mtime: s.st_mtime,
            mtime_ns: s.st_mtime_nsec,
            ctime: s.st_ctime,
            ctime_ns: s.st_ctime_nsec,
        }
    }
    fn directory(&self) -> bool {
        self.mode & libc::S_IFMT == libc::S_IFDIR && self.uid == 0 && self.mode & 0o022 == 0
    }
    fn same_directory(&self, other: &Self) -> bool {
        self.dev == other.dev
            && self.ino == other.ino
            && self.mode == other.mode
            && self.uid == other.uid
            && self.gid == other.gid
            && other.directory()
    }
    fn regular(&self) -> bool {
        self.mode & libc::S_IFMT == libc::S_IFREG
            && self.uid == 0
            && self.mode & 0o022 == 0
            && self.nlink == 1
            && self.size > 0
            && self.size <= MAX_APPROVED_POLICY_BYTES as u64
    }
}
struct Directory {
    fd: OwnedFd,
    name: CString,
    identity: Identity,
}
fn open_at(parent: i32, name: &CString, flags: i32) -> Result<OwnedFd, ApprovedPolicyError> {
    let fd = unsafe {
        libc::openat(
            parent,
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(ApprovedPolicyError::SourceRefused);
    }
    Ok(unsafe { OwnedFd::from_raw_fd(fd) })
}
fn namespace() -> Result<[(u64, u64); 3], ApprovedPolicyError> {
    let mut value = [(0, 0); 3];
    for (i, name) in [
        "/proc/thread-self/ns/user",
        "/proc/thread-self/ns/mnt",
        "/proc/thread-self/ns/time",
    ]
    .into_iter()
    .enumerate()
    {
        let s = std::fs::metadata(name).map_err(|_| ApprovedPolicyError::SourceRefused)?;
        value[i] = (s.dev(), s.ino())
    }
    Ok(value)
}
fn read(file: &File) -> Result<Vec<u8>, ApprovedPolicyError> {
    let mut bytes = vec![0; MAX_APPROVED_POLICY_BYTES + 1];
    let mut offset = 0;
    while offset < bytes.len() {
        let count = file
            .read_at(&mut bytes[offset..], offset as u64)
            .map_err(|_| ApprovedPolicyError::SourceRefused)?;
        if count == 0 {
            break;
        }
        offset += count
    }
    bytes.truncate(offset);
    if bytes.is_empty() || bytes.len() > MAX_APPROVED_POLICY_BYTES {
        return Err(ApprovedPolicyError::SourceRefused);
    }
    Ok(bytes)
}
struct PolicyState {
    pid: u32,
    deadline: Instant,
    namespace: [(u64, u64); 3],
    directories: Vec<Directory>,
    leaf: CString,
    file: File,
    identity: Identity,
    digest: [u8; 32],
    entries: [Entry; 2],
    retired: AtomicBool,
}
impl PolicyState {
    fn inspect(&self) -> Result<(), ApprovedPolicyError> {
        remaining(self.pid, self.deadline)?;
        if self.retired.load(Ordering::SeqCst) {
            return Err(ApprovedPolicyError::Changed);
        }
        let checked = (|| {
            if namespace()? != self.namespace
                || !self.directories[0]
                    .identity
                    .same_directory(&Identity::named(libc::AT_FDCWD, &self.directories[0].name)?)
            {
                return Err(ApprovedPolicyError::Changed);
            }
            for (i, dir) in self.directories.iter().enumerate() {
                if !dir
                    .identity
                    .same_directory(&Identity::file(dir.fd.as_raw_fd())?)
                {
                    return Err(ApprovedPolicyError::Changed);
                }
                if i > 0
                    && !dir.identity.same_directory(&Identity::named(
                        self.directories[i - 1].fd.as_raw_fd(),
                        &dir.name,
                    )?)
                {
                    return Err(ApprovedPolicyError::Changed);
                }
            }
            let parent = self
                .directories
                .last()
                .ok_or(ApprovedPolicyError::SourceRefused)?;
            if Identity::file(self.file.as_raw_fd())? != self.identity
                || Identity::named(parent.fd.as_raw_fd(), &self.leaf)? != self.identity
            {
                return Err(ApprovedPolicyError::Changed);
            }
            let data = read(&self.file)?;
            if <[u8; 32]>::from(Sha256::digest(&data)) != self.digest
                || Identity::file(self.file.as_raw_fd())? != self.identity
                || Identity::named(parent.fd.as_raw_fd(), &self.leaf)? != self.identity
                || namespace()? != self.namespace
            {
                return Err(ApprovedPolicyError::Changed);
            }
            for (i, dir) in self.directories.iter().enumerate() {
                if !dir
                    .identity
                    .same_directory(&Identity::file(dir.fd.as_raw_fd())?)
                    || i > 0
                        && !dir.identity.same_directory(&Identity::named(
                            self.directories[i - 1].fd.as_raw_fd(),
                            &dir.name,
                        )?)
                {
                    return Err(ApprovedPolicyError::Changed);
                }
            }
            if !self.directories[0]
                .identity
                .same_directory(&Identity::named(libc::AT_FDCWD, &self.directories[0].name)?)
            {
                return Err(ApprovedPolicyError::Changed);
            }
            remaining(self.pid, self.deadline)
        })();
        if self.pid != std::process::id() {
            return Err(ApprovedPolicyError::ProcessChanged);
        }
        if checked.is_err() {
            self.retired.store(true, Ordering::SeqCst)
        }
        checked
    }
}
/// Opaque configuration in the loader's current user/mount namespaces. No host
/// root, installed provisioning or semantic-action authority is inferred.
///
/// ```compile_fail
/// use hepta_peer_attestation::ApprovedPolicyDocument;
/// let forged = ApprovedPolicyDocument { state: () };
/// ```
pub struct ApprovedPolicyDocument {
    state: Arc<PolicyState>,
}
impl ApprovedPolicyDocument {
    pub fn open_default_before(deadline: Instant) -> Result<Self, ApprovedPolicyError> {
        Self::open_root_owned_before(Path::new(DEFAULT_APPROVED_POLICY_PATH), deadline)
    }
    pub fn open_root_owned_before(
        path: &Path,
        deadline: Instant,
    ) -> Result<Self, ApprovedPolicyError> {
        let pid = std::process::id();
        remaining(pid, deadline)?;
        if deadline.saturating_duration_since(Instant::now()) > Duration::from_secs(20) {
            return Err(ApprovedPolicyError::InvalidConfiguration);
        }
        if !path.is_absolute()
            || path.as_os_str().as_bytes().len() > 1024
            || path.components().count() > 32
            || path.as_os_str().as_bytes().contains(&0)
        {
            return Err(ApprovedPolicyError::InvalidConfiguration);
        }
        let parts: Vec<_> = path.components().collect();
        if parts.len() < 2
            || parts
                .iter()
                .skip(1)
                .any(|c| !matches!(c, Component::Normal(_)))
        {
            return Err(ApprovedPolicyError::InvalidConfiguration);
        }
        // Component iteration normalizes '.', so reject raw aliases before walking.
        if path
            .as_os_str()
            .as_bytes()
            .split(|b| *b == b'/')
            .skip(1)
            .any(|p| p.is_empty() || p == b"." || p == b"..")
        {
            return Err(ApprovedPolicyError::InvalidConfiguration);
        }
        let ns = namespace()?;
        let name = CString::new("/").unwrap();
        let fd = open_at(libc::AT_FDCWD, &name, libc::O_PATH | libc::O_DIRECTORY)?;
        let identity = Identity::file(fd.as_raw_fd())?;
        if !identity.directory() {
            return Err(ApprovedPolicyError::SourceRefused);
        }
        let mut dirs = vec![Directory { fd, name, identity }];
        for part in &parts[1..parts.len() - 1] {
            let name = CString::new(part.as_os_str().as_bytes())
                .map_err(|_| ApprovedPolicyError::InvalidConfiguration)?;
            let fd = open_at(
                dirs.last().unwrap().fd.as_raw_fd(),
                &name,
                libc::O_PATH | libc::O_DIRECTORY,
            )?;
            let identity = Identity::file(fd.as_raw_fd())?;
            if !identity.directory() {
                return Err(ApprovedPolicyError::SourceRefused);
            }
            dirs.push(Directory { fd, name, identity });
            remaining(pid, deadline)?;
        }
        let leaf = CString::new(parts.last().unwrap().as_os_str().as_bytes())
            .map_err(|_| ApprovedPolicyError::InvalidConfiguration)?;
        let fd = open_at(
            dirs.last().unwrap().fd.as_raw_fd(),
            &leaf,
            libc::O_RDONLY | libc::O_NONBLOCK,
        )?;
        let identity = Identity::file(fd.as_raw_fd())?;
        if !identity.regular() {
            return Err(ApprovedPolicyError::SourceRefused);
        }
        let file = File::from(fd);
        let bytes = read(&file)?;
        let entries = parse(&bytes)?;
        let state = Arc::new(PolicyState {
            pid,
            deadline,
            namespace: ns,
            directories: dirs,
            leaf,
            file,
            identity,
            digest: Sha256::digest(&bytes).into(),
            entries,
            retired: AtomicBool::new(false),
        });
        state.inspect()?;
        Ok(Self { state })
    }
    pub fn ensure_current(&self) -> Result<(), ApprovedPolicyError> {
        self.state.inspect()
    }
    pub fn select_control(&self) -> Result<ApprovedControlSelection, ApprovedPolicyError> {
        self.ensure_current()?;
        Ok(ApprovedControlSelection {
            guard: ApprovedGuard {
                state: Arc::clone(&self.state),
                role: 0,
            },
        })
    }
    pub fn select_agent(&self) -> Result<ApprovedAgentSelection, ApprovedPolicyError> {
        self.ensure_current()?;
        Ok(ApprovedAgentSelection {
            guard: ApprovedGuard {
                state: Arc::clone(&self.state),
                role: 1,
            },
        })
    }
}
#[derive(Clone)]
pub(crate) struct ApprovedGuard {
    state: Arc<PolicyState>,
    role: usize,
}
impl ApprovedGuard {
    pub(crate) fn verify_control_reporting_source(
        &self,
        attested: &AttestedPeer,
    ) -> Result<(), crate::ControlOwnerError> {
        self.current()?;
        if self.role != 0 {
            return Err(crate::ControlOwnerError::PeerRefused);
        }
        let entry = &self.state.entries[0];
        let snapshot = attested.snapshot();
        if snapshot.uid != entry.uid
            || snapshot.gid != entry.gid
            || snapshot.systemd_unit.as_deref() != Some(entry.unit.as_str())
            || snapshot.cgroup_v2_path != entry.cgroup
            || snapshot.executable_sha256 != entry.pin
        {
            return Err(crate::ControlOwnerError::PeerRefused);
        }
        self.current()
    }
    pub(crate) fn current(&self) -> Result<(), crate::ControlOwnerError> {
        self.state.inspect().map_err(control_error)
    }
    pub(crate) fn deadline(&self) -> Result<Instant, crate::ControlOwnerError> {
        self.current()?;
        Ok(self.state.deadline)
    }
    pub(crate) fn same_role(&self, other: &Self) -> bool {
        self.role == other.role
    }
    pub(crate) fn is_agent_for_control(&self, other: &Self) -> bool {
        self.role == 1 && other.role == 0 && Arc::ptr_eq(&self.state, &other.state)
    }
}
fn control_error(error: ApprovedPolicyError) -> crate::ControlOwnerError {
    match error {
        ApprovedPolicyError::DeadlineExceeded => crate::ControlOwnerError::DeadlineExceeded,
        ApprovedPolicyError::ProcessChanged => crate::ControlOwnerError::ProcessChanged,
        _ => crate::ControlOwnerError::PeerRefused,
    }
}
fn approval_error(error: crate::ControlOwnerError) -> ApprovedPolicyError {
    match error {
        crate::ControlOwnerError::DeadlineExceeded => ApprovedPolicyError::DeadlineExceeded,
        crate::ControlOwnerError::ProcessChanged => ApprovedPolicyError::ProcessChanged,
        _ => ApprovedPolicyError::PeerRefused,
    }
}
/// Non-cloneable Control role; no permanent naked ControlOwnerPolicy export.
pub struct ApprovedControlSelection {
    guard: ApprovedGuard,
}
impl ApprovedControlSelection {
    pub fn bind_sender(
        self,
        connection: RootPathControlConnection,
        accepted: AcceptedStreamCustody,
    ) -> Result<RootPathAttestedHandoffSender, ApprovedPolicyError> {
        self.guard.state.inspect()?;
        let policy = self.guard.state.entries[0].control()?;
        RootPathAttestedHandoffSender::from_approved(connection, accepted, policy, self.guard)
            .map_err(approval_error)
    }
    pub fn bind_receiver(
        self,
        connection: RootPathControlConnection,
        expected_local_path: &Path,
    ) -> Result<RootPathAttestedHandoffReceiver, ApprovedPolicyError> {
        self.guard.state.inspect()?;
        let policy = self.guard.state.entries[0].control()?;
        RootPathAttestedHandoffReceiver::from_approved(
            connection,
            policy,
            expected_local_path,
            self.guard,
        )
        .map_err(approval_error)
    }
}
/// Non-cloneable Agent role. Every observed tuple is compared to configuration.
///
/// ```compile_fail
/// use hepta_peer_attestation::ApprovedAgentSelection;
/// fn requires_clone<T: Clone>() {}
/// requires_clone::<ApprovedAgentSelection>();
/// ```
pub struct ApprovedAgentSelection {
    guard: ApprovedGuard,
}
impl ApprovedAgentSelection {
    pub fn admit_retained(
        self,
        received: ControlRetainedAcceptedStream,
    ) -> Result<ApprovedAgentReceivedStream, ApprovedPolicyError> {
        self.guard.state.inspect()?;
        received.deadline().map_err(approval_error)?;
        received
            .consume_before(|stream, _deadline, custody, mut retained| {
                self.guard.state.inspect()?;
                custody
                    .verify_approved_agent_source(&self.guard)
                    .map_err(approval_error)?;
                let deadline = custody
                    .verifier()
                    .map_err(approval_error)?
                    .deadline()
                    .map_err(approval_error)?;
                remaining(self.guard.state.pid, deadline)?;
                let peer = PeerIdentity::from_stream(&stream)
                    .map_err(|_| ApprovedPolicyError::PeerRefused)?;
                let entry = &self.guard.state.entries[1];
                let attested = ProcfsPeerAttestor::default()
                    .attest(peer, &entry.runtime())
                    .map_err(|_| ApprovedPolicyError::PeerRefused)?;
                if attested.snapshot().executable_sha256 != entry.pin {
                    return Err(ApprovedPolicyError::PeerRefused);
                }
                self.guard.state.inspect()?;
                custody
                    .verifier()
                    .map_err(approval_error)?
                    .verify_current()
                    .map_err(approval_error)?;
                retained.ensure_current().map_err(approval_error)?;
                remaining(self.guard.state.pid, deadline)?;
                Ok(ApprovedAgentReceivedStream {
                    guard: self.guard,
                    stream,
                    deadline,
                    custody,
                    retained,
                    attested,
                })
            })
            .map_err(approval_error)?
    }
}
/// Original admitted Agent stream plus both policy/peer scopes. Callback data
/// is not an action permit. Retained custody carries approval through execution.
pub struct ApprovedAgentReceivedStream {
    guard: ApprovedGuard,
    stream: UnixStream,
    deadline: Instant,
    custody: ControlRequestCustody,
    retained: AttestedRetainedReceiver,
    attested: AttestedPeer,
}
impl ApprovedAgentReceivedStream {
    pub fn consume_before<T>(
        mut self,
        consumer: impl FnOnce(
            UnixStream,
            Instant,
            ControlRequestCustody,
            AttestedRetainedReceiver,
            AttestedPeer,
            &str,
        ) -> T,
    ) -> Result<T, ApprovedPolicyError> {
        self.guard.state.inspect()?;
        remaining(self.guard.state.pid, self.deadline)?;
        self.custody
            .verifier()
            .map_err(approval_error)?
            .verify_current()
            .map_err(approval_error)?;
        self.retained.ensure_current().map_err(approval_error)?;
        let guard = self.guard;
        let principal = guard.state.entries[1].principal.as_str();
        let result = consumer(
            self.stream,
            self.deadline,
            self.custody,
            self.retained,
            self.attested,
            principal,
        );
        guard.state.inspect()?;
        remaining(guard.state.pid, self.deadline)?;
        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn golden() -> Vec<u8> {
        include_bytes!("../../../contracts/fixtures/approved-mechanisms.v1.conf").to_vec()
    }
    #[test]
    fn exact_golden_has_two_distinct_configured_roles() {
        let value = parse(&golden()).unwrap();
        assert_eq!(value[0].principal, "fixture-control");
        assert_eq!(value[1].principal, "fixture-agent");
        assert_eq!(value[1].uid, 65534);
    }
    #[test]
    fn every_missing_duplicate_and_unknown_field_refuses() {
        let original = String::from_utf8(golden()).unwrap();
        for line in original.lines() {
            assert!(parse(original.replace(&format!("{line}\n"), "").as_bytes()).is_err());
            assert!(parse(format!("{original}{line}\n").as_bytes()).is_err());
        }
        assert!(parse(format!("{original}agent.allow_actions=true\n").as_bytes()).is_err());
    }
    #[test]
    fn numeric_aliases_out_of_range_and_noncanonical_numbers_refuse() {
        let original = String::from_utf8(golden()).unwrap();
        for key in ["control.uid", "control.gid", "agent.uid", "agent.gid"] {
            for bad in [
                "true",
                "false",
                "65534.0",
                "+65534",
                "065534",
                "-1",
                "4294967295",
                "4294967296",
                " 65534",
            ] {
                assert!(
                    parse(
                        original
                            .replace(&format!("{key}=65534"), &format!("{key}={bad}"))
                            .as_bytes()
                    )
                    .is_err(),
                    "{key}/{bad}"
                );
            }
        }
    }
    #[test]
    fn exact_strings_bounds_syntax_and_role_collision_refuse() {
        let original = String::from_utf8(golden()).unwrap();
        for (old, new) in [
            (
                "schema=trillionnium.approved-mechanisms.v1",
                "schema=trillionnium.approved-mechanisms.v2",
            ),
            (
                "agent.unit=hepta-policy-fixture.service",
                "agent.unit=other.service",
            ),
            (
                "agent.principal_id=fixture-agent",
                "agent.principal_id=fixture-control",
            ),
            (
                "agent.cgroup=/system.slice/",
                "agent.cgroup=/system.slice/../",
            ),
            (
                "agent.principal_id=fixture-agent",
                "agent.principal_id=escaped\\name",
            ),
        ] {
            assert!(parse(original.replace(old, new).as_bytes()).is_err());
        }
        assert!(
            parse(
                original
                    .replace(
                        "agent.principal_id=fixture-agent",
                        &format!("agent.principal_id={}", "x".repeat(65))
                    )
                    .as_bytes()
            )
            .is_err()
        );
        assert!(parse(original.replace('0', "A").as_bytes()).is_err());
    }
    #[test]
    fn empty_nonascii_crlf_missing_newline_and_overbound_refuse() {
        let bytes = golden();
        for bad in [
            vec![],
            b"\xff\n".to_vec(),
            bytes[..bytes.len() - 1].to_vec(),
            String::from_utf8(bytes)
                .unwrap()
                .replace('\n', "\r\n")
                .into_bytes(),
            vec![b'x'; MAX_APPROVED_POLICY_BYTES + 1],
        ] {
            assert!(parse(&bad).is_err());
        }
    }
}
