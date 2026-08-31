//! Runtime identity attestation for a peer accepted on the local Agent socket.
//!
//! `SO_PEERCRED` binds a connected AF_UNIX stream to a kernel PID/UID/GID.
//! This crate keeps a pidfd alive while it verifies bounded procfs identity,
//! process start time, the unified cgroup-v2 path, and the expected systemd
//! service unit. It creates no socket, listener, browser authority, or permit.

#![deny(unsafe_op_in_unsafe_fn)]

use hepta_agent_transport::PeerIdentity;
use sha2::{Digest as _, Sha256};
use std::ffi::{CStr, CString};
use std::fmt;
use std::fs;
#[cfg(all(
    unix,
    any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    )
))]
use std::fs::OpenOptions;
use std::io::{self, Read};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
#[cfg(all(
    unix,
    any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    )
))]
use std::os::unix::fs::MetadataExt;
#[cfg(all(
    unix,
    any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    )
))]
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Path, PathBuf};

const MAX_STATUS_BYTES: usize = 128 * 1024;
const MAX_STAT_BYTES: usize = 64 * 1024;
const MAX_CGROUP_BYTES: usize = 64 * 1024;
const MAX_ACCOUNT_BUFFER_BYTES: usize = 1024 * 1024;
const MAX_EXECUTABLE_BYTES: u64 = 512 * 1024 * 1024;
const EXECUTABLE_READ_CHUNK_BYTES: usize = 64 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PeerRuntimeSnapshot {
    pub pid: u32,
    pub uid: u32,
    pub gid: u32,
    pub start_time_ticks: u64,
    pub cgroup_v2_path: String,
    pub systemd_unit: Option<String>,
    /// SHA-256 selected by the attestation source.  The default source hashes
    /// the exact image observed through `/proc/<pid>/exe`.  Explicit
    /// non-production static profiles instead re-open and hash one validated,
    /// root-owned executable path for every snapshot.  Callers must preserve
    /// the source kind through refreshes and must not describe a trusted-path
    /// binding as a live procfs image observation.
    pub executable_sha256: String,
}

/// Digest and pathname of an explicit non-production profile executable
/// that was opened and validated as a root-owned, non-writable regular file.
///
/// Keeping the pathname alongside the digest is intentional: a bare string
/// would let a caller hash one file and then accidentally use the digest as a
/// claim about another file.  The attestation helper re-opens this exact path
/// (with `O_NOFOLLOW`) for both identity snapshots and rejects any digest
/// change.  This type is available only to the explicit D1 qualification
/// graph or the explicit D3 development graph.  The default product graph
/// exposes only the live `/proc/<pid>/exe` path.
#[cfg(any(
    feature = "qualification-static-attestation",
    feature = "development-static-attestation"
))]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TrustedExecutableDigest {
    path: PathBuf,
    digest: String,
}

#[cfg(any(
    feature = "qualification-static-attestation",
    feature = "development-static-attestation"
))]
impl TrustedExecutableDigest {
    /// Return the lowercase SHA-256 digest represented by this binding.
    pub fn as_str(&self) -> &str {
        &self.digest
    }

    /// Return the validated executable pathname represented by this binding.
    pub fn path(&self) -> &Path {
        &self.path
    }
}

#[cfg(any(
    feature = "qualification-static-attestation",
    feature = "development-static-attestation"
))]
impl AsRef<str> for TrustedExecutableDigest {
    fn as_ref(&self) -> &str {
        self.as_str()
    }
}

#[derive(Debug, Clone)]
enum ExecutableSource {
    Live,
    #[cfg(any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    ))]
    Static(TrustedExecutableDigest),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PeerRuntimePolicy {
    pub expected_uid: u32,
    pub expected_gid: u32,
    pub expected_cgroup_v2_path: String,
    pub expected_systemd_unit: Option<String>,
}

impl PeerRuntimePolicy {
    pub fn exact(snapshot: &PeerRuntimeSnapshot) -> Self {
        Self {
            expected_uid: snapshot.uid,
            expected_gid: snapshot.gid,
            expected_cgroup_v2_path: snapshot.cgroup_v2_path.clone(),
            expected_systemd_unit: snapshot.systemd_unit.clone(),
        }
    }

    pub fn for_system_service(
        expected_uid: u32,
        expected_gid: u32,
        unit: impl Into<String>,
    ) -> Result<Self, AttestationError> {
        let unit = unit.into();
        validate_unit_name(&unit)?;
        Ok(Self {
            expected_uid,
            expected_gid,
            expected_cgroup_v2_path: format!("/system.slice/{unit}"),
            expected_systemd_unit: Some(unit),
        })
    }

    fn authorize(&self, snapshot: &PeerRuntimeSnapshot) -> Result<(), AttestationError> {
        if snapshot.uid != self.expected_uid {
            return Err(AttestationError::UidMismatch {
                expected: self.expected_uid,
                actual: snapshot.uid,
            });
        }
        if snapshot.gid != self.expected_gid {
            return Err(AttestationError::GidMismatch {
                expected: self.expected_gid,
                actual: snapshot.gid,
            });
        }
        if snapshot.cgroup_v2_path != self.expected_cgroup_v2_path {
            return Err(AttestationError::CgroupMismatch {
                expected: self.expected_cgroup_v2_path.clone(),
                actual: snapshot.cgroup_v2_path.clone(),
            });
        }
        if snapshot.systemd_unit != self.expected_systemd_unit {
            return Err(AttestationError::SystemdUnitMismatch {
                expected: self.expected_systemd_unit.clone(),
                actual: snapshot.systemd_unit.clone(),
            });
        }
        Ok(())
    }
}

#[derive(Debug, Clone)]
pub struct ProcfsPeerAttestor {
    proc_root: PathBuf,
}

impl Default for ProcfsPeerAttestor {
    fn default() -> Self {
        Self::new("/proc")
    }
}

impl ProcfsPeerAttestor {
    pub fn new(proc_root: impl Into<PathBuf>) -> Self {
        Self {
            proc_root: proc_root.into(),
        }
    }

    pub fn read_snapshot(&self, pid: u32) -> Result<PeerRuntimeSnapshot, AttestationError> {
        self.read_snapshot_with_source(pid, &ExecutableSource::Live)
    }

    fn read_snapshot_with_source(
        &self,
        pid: u32,
        executable_source: &ExecutableSource,
    ) -> Result<PeerRuntimeSnapshot, AttestationError> {
        if pid == 0 {
            return Err(AttestationError::MissingPeerPid);
        }
        // `SO_PEERCRED` reports a PID in the caller's PID namespace.  A
        // container may deliberately mount a procfs instance from a parent
        // namespace, in which case `/proc/<peer-pid>` does not name the peer
        // (or may name an unrelated process).  Resolve the procfs directory
        // through a pidfd first; the kernel gives us the PID used by this
        // procfs mount in fdinfo.  Synthetic procfs fixtures and older
        // platforms have no pidfd, so they retain the strict direct-path
        // fallback below.
        let (process_root, _pidfd) = self.resolve_process_root(pid)?;
        let status = read_bounded(&process_root.join("status"), MAX_STATUS_BYTES)?;
        let (uid, gid) = parse_status_ids(&status)?;
        let stat = read_bounded(&process_root.join("stat"), MAX_STAT_BYTES)?;
        let start_time_ticks = parse_start_time_ticks(&stat)?;
        let cgroup = read_bounded(&process_root.join("cgroup"), MAX_CGROUP_BYTES)?;
        let cgroup_v2_path = parse_unified_cgroup_path(&cgroup)?;
        let systemd_unit = systemd_unit_from_cgroup_path(&cgroup_v2_path);
        let executable_sha256 = match executable_source {
            ExecutableSource::Live => hash_executable(&process_root.join("exe"))?,
            #[cfg(any(
                feature = "qualification-static-attestation",
                feature = "development-static-attestation"
            ))]
            ExecutableSource::Static(binding) => {
                // Re-open and re-hash the same validated pathname for every
                // snapshot.  A bare startup digest would leave a replacement
                // (or an attacker-controlled path swap) invisible to the
                // before/after identity comparison.
                let current = hash_trusted_executable(binding.path())?;
                if current.as_str() != binding.as_str() {
                    return Err(AttestationError::ExecutableDigestMismatch {
                        expected: binding.as_str().to_owned(),
                        actual: current.as_str().to_owned(),
                    });
                }
                current.as_str().to_owned()
            }
        };
        Ok(PeerRuntimeSnapshot {
            pid,
            uid,
            gid,
            start_time_ticks,
            cgroup_v2_path,
            systemd_unit,
            executable_sha256,
        })
    }

    fn resolve_process_root(
        &self,
        pid: u32,
    ) -> Result<(PathBuf, Option<OwnedFd>), AttestationError> {
        #[cfg(target_os = "linux")]
        if let Ok(pidfd) = open_pidfd(pid) {
            if let Some(procfs_pid) = pidfd_procfs_pid(&pidfd)
                && procfs_pid != 0
            {
                let candidate = self.proc_root.join(procfs_pid.to_string());
                if procfs_entry_matches(&candidate, pid, true) {
                    return Ok((candidate, Some(pidfd)));
                }
            }
            // Keep the pidfd alive while the caller reads the direct procfs
            // path only when its optional NSpid record confirms the mapping
            // (or when a synthetic fixture has no NSpid record at all).  Do
            // not silently trust an unrelated process whose numeric host PID
            // happens to equal the namespace PID.
            let direct = self.proc_root.join(pid.to_string());
            if procfs_entry_matches(&direct, pid, self.proc_root.as_path() != Path::new("/proc")) {
                return Ok((direct, Some(pidfd)));
            }
        }

        let direct = self.proc_root.join(pid.to_string());
        if procfs_entry_matches(&direct, pid, self.proc_root.as_path() != Path::new("/proc")) {
            return Ok((direct, None));
        }

        // A custom procfs fixture can model a namespace mapping with NSpid.
        // Accept exactly one matching entry; ambiguity is a hard failure and
        // never silently selects an unrelated process.
        let mut matches = Vec::new();
        let entries =
            fs::read_dir(&self.proc_root).map_err(|source| AttestationError::ReadProc {
                path: self.proc_root.clone(),
                source,
            })?;
        for entry in entries {
            let entry = entry.map_err(|source| AttestationError::ReadProc {
                path: self.proc_root.clone(),
                source,
            })?;
            let name = entry.file_name();
            let Some(name) = name.to_str() else {
                continue;
            };
            if name.is_empty() || !name.bytes().all(|byte| byte.is_ascii_digit()) {
                continue;
            }
            let candidate = entry.path();
            let status_path = candidate.join("status");
            let Ok(status) = read_bounded(&status_path, MAX_STATUS_BYTES) else {
                continue;
            };
            // A malformed NSpid record must not be treated as a missing one:
            // doing so could make a custom procfs mount fall back to an
            // unrelated numeric path.  Only a successfully parsed record can
            // establish the namespace-PID mapping.
            if matches!(
                parse_nspid(&status),
                Ok(Some(ids)) if ids.last() == Some(&pid)
            ) {
                matches.push(candidate);
            }
        }
        match matches.as_slice() {
            [candidate] => Ok((candidate.clone(), None)),
            [] => Err(AttestationError::ReadProc {
                path: direct.join("status"),
                source: io::Error::from(io::ErrorKind::NotFound),
            }),
            _ => Err(AttestationError::MalformedStatus(
                "PID namespace mapping is ambiguous",
            )),
        }
    }

    pub fn attest(
        &self,
        peer: PeerIdentity,
        policy: &PeerRuntimePolicy,
    ) -> Result<AttestedPeer, AttestationError> {
        self.attest_inner(peer, policy, &ExecutableSource::Live)
    }

    /// Attest an explicit non-production profile peer when the supervisor
    /// cannot dereference `/proc/<pid>/exe` across service UIDs.  Linux gates
    /// that procfs file behind `PTRACE_MODE_READ_FSCREDS`; granting the browser
    /// service `CAP_SYS_PTRACE` would violate the custody boundary.  The caller
    /// instead supplies the binding for one fixed, root-owned executable path
    /// selected by the reviewed profile (normally obtained with
    /// [`hash_trusted_executable`]).
    ///
    /// This method retains PID/UID/GID/start-time/cgroup/unit and pidfd checks,
    /// compares the supplied path digest across both initial snapshots, and
    /// stores the same source in the returned [`AttestedPeer`] so every later
    /// dispatch refresh reopens that path rather than silently falling back to
    /// a cross-UID procfs read.  It is unavailable to the default product
    /// feature graph.  A trusted-path binding identifies the reviewed service
    /// mechanism; it is not a claim that `/proc/<pid>/exe` was observed.
    #[cfg(any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    ))]
    pub fn attest_with_static_executable_digest(
        &self,
        peer: PeerIdentity,
        policy: &PeerRuntimePolicy,
        executable: &TrustedExecutableDigest,
    ) -> Result<AttestedPeer, AttestationError> {
        validate_executable_digest(executable.as_str())?;
        let source = ExecutableSource::Static(executable.clone());
        self.attest_inner(peer, policy, &source)
    }

    fn attest_inner(
        &self,
        peer: PeerIdentity,
        policy: &PeerRuntimePolicy,
        executable_source: &ExecutableSource,
    ) -> Result<AttestedPeer, AttestationError> {
        let pid = peer.pid.ok_or(AttestationError::MissingPeerPid)?;
        let pidfd = open_pidfd(pid)?;
        ensure_pidfd_alive(&pidfd)?;

        let before = self.read_snapshot_with_source(pid, executable_source)?;
        if before.uid != peer.uid || before.gid != peer.gid {
            return Err(AttestationError::PeerCredentialDrift {
                socket_uid: peer.uid,
                socket_gid: peer.gid,
                proc_uid: before.uid,
                proc_gid: before.gid,
            });
        }
        policy.authorize(&before)?;

        let after = self.read_snapshot_with_source(pid, executable_source)?;
        if before != after {
            return Err(AttestationError::ProcessIdentityChanged);
        }
        ensure_pidfd_alive(&pidfd)?;
        Ok(AttestedPeer {
            snapshot: after,
            pidfd,
            executable_source: executable_source.clone(),
        })
    }
}

#[derive(Debug)]
pub struct AttestedPeer {
    snapshot: PeerRuntimeSnapshot,
    pidfd: OwnedFd,
    executable_source: ExecutableSource,
}

impl AttestedPeer {
    pub fn snapshot(&self) -> &PeerRuntimeSnapshot {
        &self.snapshot
    }

    pub fn ensure_alive(&self) -> Result<(), AttestationError> {
        ensure_pidfd_alive(&self.pidfd)
    }

    /// Re-read the complete identity using the exact executable source that
    /// created this attestation.  This prevents an explicit trusted-path
    /// profile from reverting to a forbidden cross-UID `/proc/<pid>/exe` read
    /// at the BrowserActor dispatch boundary.
    pub fn refresh_snapshot(
        &self,
        attestor: &ProcfsPeerAttestor,
    ) -> Result<PeerRuntimeSnapshot, AttestationError> {
        self.ensure_alive()?;
        let refreshed =
            attestor.read_snapshot_with_source(self.snapshot.pid, &self.executable_source)?;
        if refreshed != self.snapshot {
            return Err(AttestationError::ProcessIdentityChanged);
        }
        self.ensure_alive()?;
        Ok(refreshed)
    }
}

pub fn resolve_user_id(name: &str) -> Result<u32, AttestationError> {
    let name = CString::new(name).map_err(|_| AttestationError::InvalidAccountName)?;
    resolve_user_id_c(&name)
}

pub fn resolve_group_id(name: &str) -> Result<u32, AttestationError> {
    let name = CString::new(name).map_err(|_| AttestationError::InvalidAccountName)?;
    resolve_group_id_c(&name)
}

fn resolve_user_id_c(name: &CStr) -> Result<u32, AttestationError> {
    let mut buffer = vec![0_u8; account_buffer_size(libc::_SC_GETPW_R_SIZE_MAX)];
    // SAFETY: all pointers reference live writable storage for the complete
    // call; `name` is NUL-terminated and the libc function retains nothing.
    let mut record: libc::passwd = unsafe { std::mem::zeroed() };
    let mut result = std::ptr::null_mut();
    let status = unsafe {
        libc::getpwnam_r(
            name.as_ptr(),
            std::ptr::addr_of_mut!(record),
            buffer.as_mut_ptr().cast(),
            buffer.len(),
            std::ptr::addr_of_mut!(result),
        )
    };
    if status != 0 {
        return Err(AttestationError::AccountLookup(
            io::Error::from_raw_os_error(status),
        ));
    }
    if result.is_null() {
        return Err(AttestationError::AccountNotFound(
            name.to_string_lossy().into_owned(),
        ));
    }
    Ok(record.pw_uid)
}

fn resolve_group_id_c(name: &CStr) -> Result<u32, AttestationError> {
    let mut buffer = vec![0_u8; account_buffer_size(libc::_SC_GETGR_R_SIZE_MAX)];
    // SAFETY: all pointers reference live writable storage for the complete
    // call; `name` is NUL-terminated and the libc function retains nothing.
    let mut record: libc::group = unsafe { std::mem::zeroed() };
    let mut result = std::ptr::null_mut();
    let status = unsafe {
        libc::getgrnam_r(
            name.as_ptr(),
            std::ptr::addr_of_mut!(record),
            buffer.as_mut_ptr().cast(),
            buffer.len(),
            std::ptr::addr_of_mut!(result),
        )
    };
    if status != 0 {
        return Err(AttestationError::AccountLookup(
            io::Error::from_raw_os_error(status),
        ));
    }
    if result.is_null() {
        return Err(AttestationError::AccountNotFound(
            name.to_string_lossy().into_owned(),
        ));
    }
    Ok(record.gr_gid)
}

fn account_buffer_size(key: libc::c_int) -> usize {
    // SAFETY: `sysconf` takes one integer and retains no state.
    let configured = unsafe { libc::sysconf(key) };
    if configured <= 0 {
        16 * 1024
    } else {
        usize::try_from(configured)
            .unwrap_or(16 * 1024)
            .clamp(1_024, MAX_ACCOUNT_BUFFER_BYTES)
    }
}

fn read_bounded(path: &Path, maximum: usize) -> Result<String, AttestationError> {
    let metadata = fs::metadata(path).map_err(|source| AttestationError::ReadProc {
        path: path.to_path_buf(),
        source,
    })?;
    if metadata.len() > maximum as u64 {
        return Err(AttestationError::ProcFileTooLarge {
            path: path.to_path_buf(),
            length: metadata.len(),
            maximum,
        });
    }
    let value = fs::read_to_string(path).map_err(|source| AttestationError::ReadProc {
        path: path.to_path_buf(),
        source,
    })?;
    if value.len() > maximum {
        return Err(AttestationError::ProcFileTooLarge {
            path: path.to_path_buf(),
            length: value.len() as u64,
            maximum,
        });
    }
    Ok(value)
}

fn hash_executable(path: &Path) -> Result<String, AttestationError> {
    let mut file = fs::File::open(path).map_err(|source| AttestationError::ReadProc {
        path: path.to_path_buf(),
        source,
    })?;
    hash_open_file(path, &mut file)
}

fn hash_open_file(path: &Path, file: &mut fs::File) -> Result<String, AttestationError> {
    let mut digest = Sha256::new();
    let mut bytes_read = 0_u64;
    let mut buffer = [0_u8; EXECUTABLE_READ_CHUNK_BYTES];
    loop {
        let read = file
            .read(&mut buffer)
            .map_err(|source| AttestationError::ReadProc {
                path: path.to_path_buf(),
                source,
            })?;
        if read == 0 {
            break;
        }
        bytes_read = bytes_read.checked_add(read as u64).ok_or_else(|| {
            AttestationError::ExecutableTooLarge {
                path: path.to_path_buf(),
                maximum: MAX_EXECUTABLE_BYTES,
            }
        })?;
        if bytes_read > MAX_EXECUTABLE_BYTES {
            return Err(AttestationError::ExecutableTooLarge {
                path: path.to_path_buf(),
                maximum: MAX_EXECUTABLE_BYTES,
            });
        }
        digest.update(&buffer[..read]);
    }
    if bytes_read == 0 {
        return Err(AttestationError::EmptyExecutable {
            path: path.to_path_buf(),
        });
    }
    Ok(hex_digest(&digest.finalize()))
}

/// Hash a fixed executable trusted by an explicit non-production profile's
/// root-owned package/install map.  This helper rejects symlinks, unsafe path
/// components, and writable or non-root-owned files before reading bytes, so a
/// profile caller cannot turn the static binding into an arbitrary file claim.
///
/// The returned value intentionally carries the validated pathname with the
/// digest.  Callers pass that binding to
/// [`ProcfsPeerAttestor::attest_with_static_executable_digest`], which reopens
/// the path for each identity snapshot and therefore does not rely on a bare
/// digest surviving a path replacement.
#[cfg(any(
    feature = "qualification-static-attestation",
    feature = "development-static-attestation"
))]
pub fn hash_trusted_executable(
    path: impl AsRef<Path>,
) -> Result<TrustedExecutableDigest, AttestationError> {
    let path = path.as_ref();
    validate_trusted_path(path)?;
    #[cfg(unix)]
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
        .map_err(|source| AttestationError::ReadProc {
            path: path.to_path_buf(),
            source,
        })?;
    #[cfg(not(unix))]
    let mut file = fs::File::open(path).map_err(|source| AttestationError::ReadProc {
        path: path.to_path_buf(),
        source,
    })?;
    // Inspect the descriptor that will be hashed.  This closes the final
    // symlink/replacement race between metadata validation and byte reads.
    let metadata = file
        .metadata()
        .map_err(|source| AttestationError::ReadProc {
            path: path.to_path_buf(),
            source,
        })?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(AttestationError::UntrustedExecutable(path.to_path_buf()));
    }
    #[cfg(unix)]
    {
        if metadata.uid() != 0 || metadata.mode() & 0o022 != 0 || metadata.mode() & 0o111 == 0 {
            return Err(AttestationError::UntrustedExecutable(path.to_path_buf()));
        }
    }
    let digest = hash_open_file(path, &mut file)?;
    validate_executable_digest(&digest)?;
    Ok(TrustedExecutableDigest {
        path: path.to_path_buf(),
        digest,
    })
}

#[cfg(any(
    feature = "qualification-static-attestation",
    feature = "development-static-attestation"
))]
fn validate_trusted_path(path: &Path) -> Result<(), AttestationError> {
    use std::path::Component;

    // Qualification executable locations are image-owned absolute paths.  A
    // relative path would make the caller's working directory part of the
    // trust decision; `..` would make lexical component checks ambiguous.
    if !path.is_absolute()
        || path
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(AttestationError::UntrustedExecutable(path.to_path_buf()));
    }

    let mut current = PathBuf::from(std::path::MAIN_SEPARATOR.to_string());
    let mut components = path.components().peekable();
    while let Some(component) = components.next() {
        match component {
            Component::RootDir | Component::CurDir => continue,
            Component::Normal(value) => {
                current.push(value);
                let is_final = components.peek().is_none();
                match fs::symlink_metadata(&current) {
                    Ok(metadata) if metadata.file_type().is_symlink() => {
                        return Err(AttestationError::UntrustedExecutable(path.to_path_buf()));
                    }
                    Ok(metadata) if !is_final && !metadata.is_dir() => {
                        return Err(AttestationError::UntrustedExecutable(path.to_path_buf()));
                    }
                    Ok(metadata) =>
                    {
                        #[cfg(unix)]
                        if !is_final {
                            let root_owned_sticky =
                                metadata.uid() == 0 && metadata.mode() & 0o1000 != 0;
                            if metadata.uid() != 0
                                || (metadata.mode() & 0o022 != 0 && !root_owned_sticky)
                            {
                                return Err(AttestationError::UntrustedExecutable(
                                    path.to_path_buf(),
                                ));
                            }
                        }
                    }
                    Err(error) if error.kind() == io::ErrorKind::NotFound && is_final => {}
                    Err(error) if error.kind() == io::ErrorKind::NotFound => {
                        return Err(AttestationError::UntrustedExecutable(path.to_path_buf()));
                    }
                    Err(source) => {
                        return Err(AttestationError::ReadProc {
                            path: current,
                            source,
                        });
                    }
                }
            }
            _ => {}
        }
    }
    Ok(())
}

#[cfg(any(
    feature = "qualification-static-attestation",
    feature = "development-static-attestation"
))]
fn validate_executable_digest(value: &str) -> Result<(), AttestationError> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
        || value.bytes().all(|byte| byte == b'0')
    {
        return Err(AttestationError::InvalidExecutableDigest);
    }
    Ok(())
}

fn hex_digest(digest: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(digest.len() * 2);
    for byte in digest {
        output.push(HEX[usize::from(byte >> 4)] as char);
        output.push(HEX[usize::from(byte & 0x0f)] as char);
    }
    output
}

fn parse_status_ids(value: &str) -> Result<(u32, u32), AttestationError> {
    let mut uid = None;
    let mut gid = None;
    for line in value.lines() {
        if let Some(rest) = line.strip_prefix("Uid:") {
            if uid.is_some() {
                return Err(AttestationError::MalformedStatus("duplicate Uid field"));
            }
            uid = Some(parse_uniform_id_field("Uid", rest)?);
        } else if let Some(rest) = line.strip_prefix("Gid:") {
            if gid.is_some() {
                return Err(AttestationError::MalformedStatus("duplicate Gid field"));
            }
            gid = Some(parse_uniform_id_field("Gid", rest)?);
        }
    }
    Ok((
        uid.ok_or(AttestationError::MalformedStatus("missing Uid"))?,
        gid.ok_or(AttestationError::MalformedStatus("missing Gid"))?,
    ))
}

fn parse_nspid(value: &str) -> Result<Option<Vec<u32>>, AttestationError> {
    let mut parsed = None;
    for line in value.lines() {
        let Some(rest) = line.strip_prefix("NSpid:") else {
            continue;
        };
        if parsed.is_some() {
            return Err(AttestationError::MalformedStatus("duplicate NSpid field"));
        }
        let values = rest
            .split_whitespace()
            // `/proc/<pid>/status` emits plain decimal PID tokens.  Do not
            // accept `+42` or other alternate integer spellings in a
            // synthetic/custom procfs either: namespace mapping is an
            // identity boundary, so permissive parsing could make two
            // differently represented records compare as the same PID.
            .map(parse_canonical_u32)
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| AttestationError::MalformedStatus("invalid NSpid field"))?;
        if values.is_empty() {
            return Err(AttestationError::MalformedStatus("empty NSpid field"));
        }
        if values.contains(&0) {
            return Err(AttestationError::MalformedStatus(
                "NSpid field contains zero",
            ));
        }
        parsed = Some(values);
    }
    Ok(parsed)
}

fn procfs_entry_matches(path: &Path, namespace_pid: u32, allow_missing_nspid: bool) -> bool {
    let status_path = path.join("status");
    let Ok(status) = read_bounded(&status_path, MAX_STATUS_BYTES) else {
        return false;
    };
    // Synthetic fixtures predating NSpid are intentionally supported.  A real
    // procfs status file on Linux includes NSpid, and its innermost value must
    // match the PID reported by SO_PEERCRED.
    match parse_nspid(&status) {
        Ok(Some(ids)) => ids.last() == Some(&namespace_pid),
        Ok(None) => allow_missing_nspid,
        Err(_) => false,
    }
}

fn parse_uniform_id_field(label: &'static str, value: &str) -> Result<u32, AttestationError> {
    let parsed = value
        .split_whitespace()
        .map(parse_canonical_u32)
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| AttestationError::MalformedStatus(label))?;
    if parsed.len() != 4 || parsed.iter().any(|item| *item != parsed[0]) {
        return Err(AttestationError::NonUniformProcessIds {
            field: label,
            values: parsed,
        });
    }
    Ok(parsed[0])
}

/// Parse the decimal spelling emitted by Linux procfs identity fields.
///
/// Procfs writes unsigned IDs without a sign or redundant leading zeroes.  A
/// custom/synthetic procfs is still an identity input, so accepting alternate
/// spellings such as `+1000` or `01000` would make the parser less strict than
/// the kernel format and could hide malformed mappings.
fn parse_canonical_u32(token: &str) -> Result<u32, ()> {
    if token.is_empty()
        || !token.bytes().all(|byte| byte.is_ascii_digit())
        || (token.len() > 1 && token.starts_with('0'))
    {
        return Err(());
    }
    token.parse::<u32>().map_err(|_| ())
}

fn parse_start_time_ticks(value: &str) -> Result<u64, AttestationError> {
    let close = value
        .rfind(')')
        .ok_or(AttestationError::MalformedStat("missing comm terminator"))?;
    let remainder = value
        .get(close + 1..)
        .ok_or(AttestationError::MalformedStat("invalid comm terminator"))?;
    let fields: Vec<_> = remainder.split_whitespace().collect();
    let start_time = fields
        .get(19)
        .ok_or(AttestationError::MalformedStat("missing starttime field"))?;
    let start_time = start_time
        .parse::<u64>()
        .map_err(|_| AttestationError::MalformedStat("invalid starttime field"))?;
    if start_time == 0 {
        return Err(AttestationError::MalformedStat(
            "starttime field must be non-zero",
        ));
    }
    Ok(start_time)
}

fn parse_unified_cgroup_path(value: &str) -> Result<String, AttestationError> {
    let mut path = None;
    for line in value.lines().filter(|line| !line.trim().is_empty()) {
        let mut parts = line.splitn(3, ':');
        let hierarchy = parts.next().unwrap_or_default();
        let controllers = parts.next().unwrap_or_default();
        let candidate = parts
            .next()
            .ok_or(AttestationError::MalformedCgroup("missing path"))?;
        if hierarchy == "0" && controllers.is_empty() {
            if path.is_some() {
                return Err(AttestationError::MalformedCgroup(
                    "multiple unified hierarchy entries",
                ));
            }
            validate_cgroup_path(candidate)?;
            path = Some(candidate.to_owned());
        }
    }
    path.ok_or(AttestationError::MalformedCgroup(
        "missing unified cgroup-v2 entry",
    ))
}

fn validate_cgroup_path(value: &str) -> Result<(), AttestationError> {
    if !value.starts_with('/')
        || value.contains('\0')
        || value.split('/').any(|component| component == "..")
    {
        return Err(AttestationError::MalformedCgroup("unsafe cgroup path"));
    }
    Ok(())
}

fn systemd_unit_from_cgroup_path(value: &str) -> Option<String> {
    value
        .split('/')
        .rev()
        .find(|component| component.ends_with(".service") || component.ends_with(".scope"))
        .map(str::to_owned)
}

fn validate_unit_name(value: &str) -> Result<(), AttestationError> {
    if value.is_empty()
        || value.len() > 255
        || !value.ends_with(".service")
        || value.contains('/')
        || value.contains('\0')
        || value == ".service"
    {
        return Err(AttestationError::InvalidSystemdUnit(value.to_owned()));
    }
    Ok(())
}

#[cfg(target_os = "linux")]
fn open_pidfd(pid: u32) -> Result<OwnedFd, AttestationError> {
    // SAFETY: pidfd_open takes integer arguments and returns a new owned file
    // descriptor on success. No pointer is passed or retained.
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid as libc::pid_t, 0_u32) };
    if raw < 0 {
        return Err(AttestationError::Pidfd(io::Error::last_os_error()));
    }
    let raw = i32::try_from(raw).map_err(|_| AttestationError::InvalidPidfd)?;
    // SAFETY: `raw` is a fresh successful pidfd_open result and ownership is
    // transferred exactly once to OwnedFd.
    Ok(unsafe { OwnedFd::from_raw_fd(raw) })
}

#[cfg(target_os = "linux")]
fn pidfd_procfs_pid(pidfd: &OwnedFd) -> Option<u32> {
    let path = PathBuf::from(format!("/proc/self/fdinfo/{}", pidfd.as_raw_fd()));
    let contents = fs::read_to_string(path).ok()?;
    contents.lines().find_map(|line| {
        let value = line.strip_prefix("Pid:")?.trim();
        value.parse::<u32>().ok()
    })
}

#[cfg(not(target_os = "linux"))]
fn open_pidfd(_pid: u32) -> Result<OwnedFd, AttestationError> {
    Err(AttestationError::UnsupportedPlatform)
}

#[cfg(target_os = "linux")]
fn ensure_pidfd_alive(pidfd: &OwnedFd) -> Result<(), AttestationError> {
    let mut descriptor = libc::pollfd {
        fd: pidfd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    // SAFETY: `descriptor` points to one initialized pollfd for the duration
    // of the call and libc retains no pointer after returning.
    let status = unsafe { libc::poll(std::ptr::addr_of_mut!(descriptor), 1, 0) };
    if status < 0 {
        return Err(AttestationError::Pidfd(io::Error::last_os_error()));
    }
    if status == 0 {
        return Ok(());
    }
    Err(AttestationError::PeerProcessExited)
}

#[cfg(not(target_os = "linux"))]
fn ensure_pidfd_alive(_pidfd: &OwnedFd) -> Result<(), AttestationError> {
    Err(AttestationError::UnsupportedPlatform)
}

#[derive(Debug)]
pub enum AttestationError {
    UnsupportedPlatform,
    MissingPeerPid,
    ReadProc {
        path: PathBuf,
        source: io::Error,
    },
    ProcFileTooLarge {
        path: PathBuf,
        length: u64,
        maximum: usize,
    },
    ExecutableTooLarge {
        path: PathBuf,
        maximum: u64,
    },
    EmptyExecutable {
        path: PathBuf,
    },
    #[cfg(any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    ))]
    UntrustedExecutable(PathBuf),
    #[cfg(any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    ))]
    InvalidExecutableDigest,
    #[cfg(any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    ))]
    ExecutableDigestMismatch {
        expected: String,
        actual: String,
    },
    MalformedStatus(&'static str),
    NonUniformProcessIds {
        field: &'static str,
        values: Vec<u32>,
    },
    MalformedStat(&'static str),
    MalformedCgroup(&'static str),
    InvalidSystemdUnit(String),
    UidMismatch {
        expected: u32,
        actual: u32,
    },
    GidMismatch {
        expected: u32,
        actual: u32,
    },
    CgroupMismatch {
        expected: String,
        actual: String,
    },
    SystemdUnitMismatch {
        expected: Option<String>,
        actual: Option<String>,
    },
    PeerCredentialDrift {
        socket_uid: u32,
        socket_gid: u32,
        proc_uid: u32,
        proc_gid: u32,
    },
    ProcessIdentityChanged,
    PeerProcessExited,
    Pidfd(io::Error),
    InvalidPidfd,
    InvalidAccountName,
    AccountLookup(io::Error),
    AccountNotFound(String),
}

impl fmt::Display for AttestationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnsupportedPlatform => formatter.write_str("peer attestation is Linux-only"),
            Self::MissingPeerPid => formatter.write_str("peer credentials contain no usable PID"),
            Self::ReadProc { path, source } => {
                write!(formatter, "failed to read {}: {source}", path.display())
            }
            Self::ProcFileTooLarge {
                path,
                length,
                maximum,
            } => write!(
                formatter,
                "{} is {length} bytes, above the {maximum}-byte bound",
                path.display()
            ),
            Self::ExecutableTooLarge { path, maximum } => write!(
                formatter,
                "executable {} exceeds the {maximum}-byte hashing bound",
                path.display()
            ),
            Self::EmptyExecutable { path } => {
                write!(formatter, "executable {} is empty", path.display())
            }
            #[cfg(any(
                feature = "qualification-static-attestation",
                feature = "development-static-attestation"
            ))]
            Self::UntrustedExecutable(path) => write!(
                formatter,
                "trusted executable {} is not a root-owned, non-writable regular file",
                path.display()
            ),
            #[cfg(any(
                feature = "qualification-static-attestation",
                feature = "development-static-attestation"
            ))]
            Self::InvalidExecutableDigest => {
                formatter.write_str("executable digest must be lowercase non-zero SHA-256")
            }
            #[cfg(any(
                feature = "qualification-static-attestation",
                feature = "development-static-attestation"
            ))]
            Self::ExecutableDigestMismatch { expected, actual } => write!(
                formatter,
                "trusted executable digest changed (expected {expected}, observed {actual})"
            ),
            Self::MalformedStatus(reason) => write!(formatter, "malformed proc status: {reason}"),
            Self::NonUniformProcessIds { field, values } => {
                write!(formatter, "proc {field} values are not uniform: {values:?}")
            }
            Self::MalformedStat(reason) => write!(formatter, "malformed proc stat: {reason}"),
            Self::MalformedCgroup(reason) => write!(formatter, "malformed proc cgroup: {reason}"),
            Self::InvalidSystemdUnit(unit) => write!(formatter, "invalid systemd unit {unit:?}"),
            Self::UidMismatch { expected, actual } => {
                write!(
                    formatter,
                    "peer UID {actual} does not equal expected {expected}"
                )
            }
            Self::GidMismatch { expected, actual } => {
                write!(
                    formatter,
                    "peer GID {actual} does not equal expected {expected}"
                )
            }
            Self::CgroupMismatch { expected, actual } => write!(
                formatter,
                "peer cgroup {actual:?} does not equal expected {expected:?}"
            ),
            Self::SystemdUnitMismatch { expected, actual } => write!(
                formatter,
                "peer unit {actual:?} does not equal expected {expected:?}"
            ),
            Self::PeerCredentialDrift {
                socket_uid,
                socket_gid,
                proc_uid,
                proc_gid,
            } => write!(
                formatter,
                "SO_PEERCRED {socket_uid}:{socket_gid} disagrees with procfs {proc_uid}:{proc_gid}"
            ),
            Self::ProcessIdentityChanged => {
                formatter.write_str("peer process identity changed during attestation")
            }
            Self::PeerProcessExited => formatter.write_str("peer process exited"),
            Self::Pidfd(source) => write!(formatter, "pidfd operation failed: {source}"),
            Self::InvalidPidfd => formatter.write_str("pidfd value cannot be represented as an fd"),
            Self::InvalidAccountName => {
                formatter.write_str("account name contains an interior NUL")
            }
            Self::AccountLookup(source) => write!(formatter, "account lookup failed: {source}"),
            Self::AccountNotFound(name) => write!(formatter, "account {name:?} does not exist"),
        }
    }
}

impl std::error::Error for AttestationError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::ReadProc { source, .. } | Self::Pidfd(source) | Self::AccountLookup(source) => {
                Some(source)
            }
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::net::UnixStream;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn status_ids_must_be_uniform() {
        let good = "Uid:\t1000\t1000\t1000\t1000\nGid:\t1001\t1001\t1001\t1001\n";
        assert_eq!(parse_status_ids(good).expect("uniform IDs"), (1000, 1001));
        let bad = "Uid:\t1000\t0\t1000\t1000\nGid:\t1001\t1001\t1001\t1001\n";
        assert!(matches!(
            parse_status_ids(bad),
            Err(AttestationError::NonUniformProcessIds { field: "Uid", .. })
        ));
    }

    #[test]
    fn status_ids_reject_duplicate_identity_fields() {
        let duplicate_uid = "Uid:\t1000\t1000\t1000\t1000\nUid:\t1000\t1000\t1000\t1000\nGid:\t1001\t1001\t1001\t1001\n";
        assert!(matches!(
            parse_status_ids(duplicate_uid),
            Err(AttestationError::MalformedStatus("duplicate Uid field"))
        ));

        let duplicate_gid = "Uid:\t1000\t1000\t1000\t1000\nGid:\t1001\t1001\t1001\t1001\nGid:\t1001\t1001\t1001\t1001\n";
        assert!(matches!(
            parse_status_ids(duplicate_gid),
            Err(AttestationError::MalformedStatus("duplicate Gid field"))
        ));
    }

    #[test]
    fn status_ids_require_canonical_decimal_tokens() {
        let signed = "Uid:\t+1000\t+1000\t+1000\t+1000\nGid:\t1001\t1001\t1001\t1001\n";
        assert!(matches!(
            parse_status_ids(signed),
            Err(AttestationError::MalformedStatus("Uid"))
        ));

        let leading_zero = "Uid:\t01000\t01000\t01000\t01000\nGid:\t1001\t1001\t1001\t1001\n";
        assert!(matches!(
            parse_status_ids(leading_zero),
            Err(AttestationError::MalformedStatus("Uid"))
        ));

        // UID/GID zero is a valid kernel value; only alternate spellings are
        // rejected, not the canonical single-character `0`.
        let root = "Uid:\t0\t0\t0\t0\nGid:\t0\t0\t0\t0\n";
        assert_eq!(parse_status_ids(root).expect("canonical zero IDs"), (0, 0));
    }

    #[test]
    fn nspid_mapping_rejects_duplicate_or_zero_records() {
        let duplicate = "NSpid:\t10\t20\nNSpid:\t10\t20\n";
        assert!(matches!(
            parse_nspid(duplicate),
            Err(AttestationError::MalformedStatus("duplicate NSpid field"))
        ));

        let zero = "NSpid:\t10\t0\n";
        assert!(matches!(
            parse_nspid(zero),
            Err(AttestationError::MalformedStatus(
                "NSpid field contains zero"
            ))
        ));

        let malformed = "NSpid:\t10\tnope\n";
        assert!(matches!(
            parse_nspid(malformed),
            Err(AttestationError::MalformedStatus("invalid NSpid field"))
        ));
        let signed = "NSpid:\t+10\t20\n";
        assert!(matches!(
            parse_nspid(signed),
            Err(AttestationError::MalformedStatus("invalid NSpid field"))
        ));
        assert_eq!(parse_nspid("Name:\tfixture\n").unwrap(), None);
    }

    #[test]
    fn cgroup_parser_requires_one_safe_unified_entry() {
        assert_eq!(
            parse_unified_cgroup_path("0::/system.slice/hepta-agent.service\n")
                .expect("unified cgroup"),
            "/system.slice/hepta-agent.service"
        );
        assert!(parse_unified_cgroup_path("2:cpu:/legacy\n").is_err());
        assert!(parse_unified_cgroup_path("0::/safe/../escape\n").is_err());
        assert!(parse_unified_cgroup_path("0::/one\n0::/two\n").is_err());
    }

    #[test]
    fn system_service_policy_is_exact() {
        let policy = PeerRuntimePolicy::for_system_service(101, 102, "hepta-agent.service")
            .expect("valid unit");
        assert_eq!(
            policy.expected_cgroup_v2_path,
            "/system.slice/hepta-agent.service"
        );
        assert_eq!(
            policy.expected_systemd_unit.as_deref(),
            Some("hepta-agent.service")
        );
        assert!(PeerRuntimePolicy::for_system_service(1, 1, "../bad.service").is_err());
    }

    #[test]
    fn bounded_fixture_snapshot_is_parsed() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!("hepta-peer-attestation-{unique}"));
        let pid = 4242_u32;
        let process = root.join(pid.to_string());
        fs::create_dir_all(&process).expect("create fixture");
        fs::write(
            process.join("status"),
            "Uid:\t1000\t1000\t1000\t1000\nGid:\t1001\t1001\t1001\t1001\n",
        )
        .expect("status");
        let mut stat_fields = vec!["S".to_owned(); 20];
        stat_fields[19] = "987654".to_owned();
        fs::write(
            process.join("stat"),
            format!("{pid} (fixture name) {}\n", stat_fields.join(" ")),
        )
        .expect("stat");
        fs::write(
            process.join("cgroup"),
            "0::/system.slice/hepta-agent.service\n",
        )
        .expect("cgroup");
        fs::write(process.join("exe"), b"fixture-executable").expect("executable");
        let snapshot = ProcfsPeerAttestor::new(&root)
            .read_snapshot(pid)
            .expect("snapshot");
        assert_eq!(snapshot.uid, 1000);
        assert_eq!(snapshot.gid, 1001);
        assert_eq!(snapshot.start_time_ticks, 987654);
        assert_eq!(
            snapshot.systemd_unit.as_deref(),
            Some("hepta-agent.service")
        );
        assert_eq!(
            snapshot.executable_sha256,
            "38f6e245c905f6145e480121d5405540669eaca83272dc36eee827d3387df29c"
        );
        fs::remove_dir_all(root).expect("remove fixture");
    }

    #[cfg(any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    ))]
    #[test]
    fn static_executable_digest_validation_is_strict() {
        assert!(validate_executable_digest(&"a".repeat(64)).is_ok());
        assert!(matches!(
            validate_executable_digest(&"A".repeat(64)),
            Err(AttestationError::InvalidExecutableDigest)
        ));
        assert!(matches!(
            validate_executable_digest(&"0".repeat(64)),
            Err(AttestationError::InvalidExecutableDigest)
        ));
        assert!(matches!(
            validate_executable_digest("not-a-digest"),
            Err(AttestationError::InvalidExecutableDigest)
        ));
    }

    #[cfg(any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    ))]
    #[test]
    fn trusted_executable_hash_returns_path_bound_digest() {
        let path = Path::new("/usr/bin/true");
        assert!(path.is_absolute());
        let binding = hash_trusted_executable(path).expect("system executable is trusted");
        assert_eq!(binding.path(), path);
        assert_eq!(binding.as_str().len(), 64);
        assert!(
            binding
                .as_str()
                .bytes()
                .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
        );
    }

    #[cfg(any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    ))]
    #[test]
    fn trusted_executable_hash_rejects_relative_or_parent_paths() {
        assert!(matches!(
            hash_trusted_executable("usr/bin/true"),
            Err(AttestationError::UntrustedExecutable(path)) if path == Path::new("usr/bin/true")
        ));
        assert!(matches!(
            hash_trusted_executable("/usr/bin/../bin/true"),
            Err(AttestationError::UntrustedExecutable(path))
                if path == Path::new("/usr/bin/../bin/true")
        ));
    }

    #[cfg(any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    ))]
    #[test]
    fn trusted_executable_hash_rejects_symlink_aliases() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!("hepta-peer-attestation-trusted-{unique}"));
        fs::create_dir_all(&root).expect("create fixture directory");
        let target = root.join("target");
        let alias = root.join("alias");
        fs::write(&target, b"trusted-executable").expect("write target");
        std::os::unix::fs::symlink(&target, &alias).expect("create alias");
        assert!(matches!(
            hash_trusted_executable(&alias),
            Err(AttestationError::UntrustedExecutable(path)) if path == alias
        ));
        fs::remove_dir_all(root).expect("remove fixture");
    }

    #[cfg(any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    ))]
    #[test]
    fn static_digest_binding_detects_digest_mismatch_before_attestation() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!("hepta-peer-attestation-static-{unique}"));
        let pid = 4245_u32;
        let process = root.join(pid.to_string());
        fs::create_dir_all(&process).expect("create fixture");
        fs::write(
            process.join("status"),
            "Uid:\t1000\t1000\t1000\t1000\nGid:\t1001\t1001\t1001\t1001\n",
        )
        .expect("status");
        let mut stat_fields = vec!["S".to_owned(); 20];
        stat_fields[19] = "987657".to_owned();
        fs::write(
            process.join("stat"),
            format!("{pid} (fixture name) {}\n", stat_fields.join(" ")),
        )
        .expect("stat");
        fs::write(
            process.join("cgroup"),
            "0::/system.slice/hepta-agent.service\n",
        )
        .expect("cgroup");

        let trusted = hash_trusted_executable("/usr/bin/true").expect("trusted executable");
        let mismatched = TrustedExecutableDigest {
            path: trusted.path().to_path_buf(),
            digest: if trusted.as_str().starts_with('a') {
                format!("b{}", &trusted.as_str()[1..])
            } else {
                format!("a{}", &trusted.as_str()[1..])
            },
        };
        let error = ProcfsPeerAttestor::new(&root)
            .read_snapshot_with_source(pid, &ExecutableSource::Static(mismatched.clone()))
            .expect_err("changed digest must fail closed");
        assert!(matches!(
            error,
            AttestationError::ExecutableDigestMismatch { expected, actual }
                if expected == mismatched.as_str() && actual == trusted.as_str()
        ));
        fs::remove_dir_all(root).expect("remove fixture");
    }

    #[test]
    fn zero_start_time_fixture_is_rejected_during_snapshot_read() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!("hepta-peer-attestation-zero-start-{unique}"));
        let pid = 4244_u32;
        let process = root.join(pid.to_string());
        fs::create_dir_all(&process).expect("create fixture");
        fs::write(
            process.join("status"),
            "Uid:\t1000\t1000\t1000\t1000\nGid:\t1001\t1001\t1001\t1001\n",
        )
        .expect("status");
        let mut stat_fields = vec!["S".to_owned(); 20];
        stat_fields[19] = "0".to_owned();
        fs::write(
            process.join("stat"),
            format!("{pid} (fixture name) {}\n", stat_fields.join(" ")),
        )
        .expect("stat");

        let error = ProcfsPeerAttestor::new(&root)
            .read_snapshot(pid)
            .expect_err("zero start time must fail closed");
        assert!(matches!(
            error,
            AttestationError::MalformedStat("starttime field must be non-zero")
        ));
        fs::remove_dir_all(root).expect("remove fixture");
    }

    #[test]
    fn namespace_mapped_fixture_snapshot_uses_the_unique_nspid_entry() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!("hepta-peer-attestation-nspid-{unique}"));
        let host_pid = 999_991_u32;
        let namespace_pid = 424_242_u32;
        let process = root.join(host_pid.to_string());
        fs::create_dir_all(&process).expect("create fixture");
        fs::write(
            process.join("status"),
            format!(
                "Uid:\t1000\t1000\t1000\t1000\nGid:\t1001\t1001\t1001\t1001\nNSpid:\t{host_pid}\t{namespace_pid}\n"
            ),
        )
        .expect("status");
        let mut stat_fields = vec!["S".to_owned(); 20];
        stat_fields[19] = "987655".to_owned();
        fs::write(
            process.join("stat"),
            format!("{host_pid} (fixture name) {}\n", stat_fields.join(" ")),
        )
        .expect("stat");
        fs::write(
            process.join("cgroup"),
            "0::/system.slice/hepta-agent.service\n",
        )
        .expect("cgroup");
        fs::write(process.join("exe"), b"fixture-executable").expect("executable");

        let snapshot = ProcfsPeerAttestor::new(&root)
            .read_snapshot(namespace_pid)
            .expect("namespace-mapped snapshot");
        assert_eq!(snapshot.pid, namespace_pid);
        assert_eq!(snapshot.start_time_ticks, 987655);
        assert_eq!(snapshot.cgroup_v2_path, "/system.slice/hepta-agent.service");
        fs::remove_dir_all(root).expect("remove fixture");
    }

    #[test]
    fn ambiguous_namespace_mapping_fails_closed() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!("hepta-peer-attestation-ambiguous-{unique}"));
        let namespace_pid = 424_243_u32;
        for host_pid in [999_992_u32, 999_993_u32] {
            let process = root.join(host_pid.to_string());
            fs::create_dir_all(&process).expect("create fixture");
            fs::write(
                process.join("status"),
                format!(
                    "Uid:\t1000\t1000\t1000\t1000\nGid:\t1001\t1001\t1001\t1001\nNSpid:\t{host_pid}\t{namespace_pid}\n"
                ),
            )
            .expect("status");
        }
        let error = ProcfsPeerAttestor::new(&root)
            .read_snapshot(namespace_pid)
            .expect_err("ambiguous mapping must fail");
        assert!(matches!(
            error,
            AttestationError::MalformedStatus("PID namespace mapping is ambiguous")
        ));
        fs::remove_dir_all(root).expect("remove fixture");
    }

    #[test]
    fn live_socket_peer_can_be_attested_with_exact_snapshot_policy() {
        let (left, _right) = UnixStream::pair().expect("socketpair");
        let peer = PeerIdentity::from_stream(&left).expect("peer credentials");
        let attestor = ProcfsPeerAttestor::default();
        let pid = peer.pid.expect("peer PID");
        let snapshot = attestor.read_snapshot(pid).expect("live snapshot");
        let attested = attestor
            .attest(peer, &PeerRuntimePolicy::exact(&snapshot))
            .expect("attested peer");
        attested.ensure_alive().expect("peer remains alive");
        assert_eq!(
            attested
                .refresh_snapshot(&attestor)
                .expect("live source refresh"),
            snapshot
        );
        assert_eq!(attested.snapshot(), &snapshot);
        assert_eq!(snapshot.executable_sha256.len(), 64);
        assert!(
            snapshot
                .executable_sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
        );
    }

    #[cfg(any(
        feature = "qualification-static-attestation",
        feature = "development-static-attestation"
    ))]
    #[test]
    fn static_attested_peer_refresh_reuses_the_original_trusted_path_source() {
        let (left, _right) = UnixStream::pair().expect("socketpair");
        let peer = PeerIdentity::from_stream(&left).expect("peer credentials");
        let attestor = ProcfsPeerAttestor::default();
        let pid = peer.pid.expect("peer PID");
        let executable =
            hash_trusted_executable("/usr/bin/true").expect("trusted executable binding");
        let expected = attestor
            .read_snapshot_with_source(pid, &ExecutableSource::Static(executable.clone()))
            .expect("static-source snapshot");
        let attested = attestor
            .attest_with_static_executable_digest(
                peer,
                &PeerRuntimePolicy::exact(&expected),
                &executable,
            )
            .expect("static attestation");
        assert_eq!(
            attested
                .refresh_snapshot(&attestor)
                .expect("static source refresh"),
            expected
        );
    }

    #[test]
    fn root_account_resolution_is_consistent() {
        assert_eq!(resolve_user_id("root").expect("root user"), 0);
        assert_eq!(resolve_group_id("root").expect("root group"), 0);
    }
}
