//! Runtime identity attestation for a peer accepted on the local Agent socket.
//!
//! `SO_PEERCRED` proves the kernel PID/UID/GID attached to the connected stream.
//! This crate adds a short-lived pidfd guard and verifies that the same process
//! is still alive, has not changed its real/effective/saved/filesystem IDs, and
//! belongs to the exact cgroup-v2 path and systemd unit selected by policy.
//!
//! The attestor owns no socket and grants no browser or system capability.

#![deny(unsafe_op_in_unsafe_fn)]

use hepta_agent_transport::PeerIdentity;
use std::ffi::{CStr, CString};
use std::fmt;
use std::fs;
use std::io;
use std::os::fd::{FromRawFd, OwnedFd};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PeerRuntimeSnapshot {
    pub pid: u32,
    pub uid: u32,
    pub gid: u32,
    pub start_time_ticks: u64,
    pub cgroup_v2_path: String,
    pub systemd_unit: Option<String>,
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

    pub fn authorize(&self, snapshot: &PeerRuntimeSnapshot) -> Result<(), AttestationError> {
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
        if pid == 0 {
            return Err(AttestationError::MissingPeerPid);
        }
        let process_root = self.proc_root.join(pid.to_string());
        let status = read_bounded(&process_root.join("status"), 128 * 1024)?;
        let (uid, gid) = parse_status_ids(&status)?;
        let stat = read_bounded(&process_root.join("stat"), 64 * 1024)?;
        let start_time_ticks = parse_start_time_ticks(&stat)?;
        let cgroup = read_bounded(&process_root.join("cgroup"), 64 * 1024)?;
        let cgroup_v2_path = parse_unified_cgroup_path(&cgroup)?;
        let systemd_unit = systemd_unit_from_cgroup_path(&cgroup_v2_path);
        Ok(PeerRuntimeSnapshot {
            pid,
            uid,
            gid,
            start_time_ticks,
            cgroup_v2_path,
            systemd_unit,
        })
    }

    pub fn attest(
        &self,
        peer: PeerIdentity,
        policy: &PeerRuntimePolicy,
    ) -> Result<AttestedPeer, AttestationError> {
        let pid = peer.pid.ok_or(AttestationError::MissingPeerPid)?;
        let pidfd = open_pidfd(pid)?;
        ensure_pidfd_alive(&pidfd)?;

        let before = self.read_snapshot(pid)?;
        if before.uid != peer.uid || before.gid != peer.gid {
            return Err(AttestationError::PeerCredentialDrift {
                socket_uid: peer.uid,
                socket_gid: peer.gid,
                proc_uid: before.uid,
                proc_gid: before.gid,
            });
        }
        policy.authorize(&before)?;

        let after = self.read_snapshot(pid)?;
        if before != after {
            return Err(AttestationError::ProcessIdentityChanged);
        }
        ensure_pidfd_alive(&pidfd)?;
        Ok(AttestedPeer {
            snapshot: after,
            pidfd,
        })
    }
}

#[derive(Debug)]
pub struct AttestedPeer {
    snapshot: PeerRuntimeSnapshot,
    pidfd: OwnedFd,
}

impl AttestedPeer {
    pub fn snapshot(&self) -> &PeerRuntimeSnapshot {
        &self.snapshot
    }

    pub fn ensure_alive(&self) -> Result<(), AttestationError> {
        ensure_pidfd_alive(&self.pidfd)
    }
}

pub fn resolve_user_id(name: &str) -> Result<u32, AttestationError> {
    resolve_account_id(name, AccountKind::User)
}

pub fn resolve_group_id(name: &str) -> Result<u32, AttestationError> {
    resolve_account_id(name, AccountKind::Group)
}

#[derive(Debug, Clone, Copy)]
enum AccountKind {
    User,
    Group,
}

fn resolve_account_id(name: &str, kind: AccountKind) -> Result<u32, AttestationError> {
    let name = CString::new(name).map_err(|_| AttestationError::InvalidAccountName)?;
    match kind {
        AccountKind::User => resolve_user_id_c(&name),
        AccountKind::Group => resolve_group_id_c(&name),
    }
}

fn resolve_user_id_c(name: &CStr) -> Result<u32, AttestationError> {
    let mut buffer = vec![0_u8; account_buffer_size(libc::_SC_GETPW_R_SIZE_MAX)];
    // SAFETY: `record`, `result`, and `buffer` remain valid for the complete
    // `getpwnam_r` call. The name is NUL-terminated and contains no interior NUL.
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
        return Err(AttestationError::AccountLookup(io::Error::from_raw_os_error(
            status,
        )));
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
    // SAFETY: `record`, `result`, and `buffer` remain valid for the complete
    // `getgrnam_r` call. The name is NUL-terminated and contains no interior NUL.
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
        return Err(AttestationError::AccountLookup(io::Error::from_raw_os_error(
            status,
        )));
    }
    if result.is_null() {
        return Err(AttestationError::AccountNotFound(
            name.to_string_lossy().into_owned(),
        ));
    }
    Ok(record.gr_gid)
}

fn account_buffer_size(key: libc::c_int) -> usize {
    // SAFETY: `sysconf` has no pointer arguments and does not retain state.
    let configured = unsafe { libc::sysconf(key) };
    if configured <= 0 {
        16 * 1024
    } else {
        usize::try_from(configured).unwrap_or(16 * 1024).clamp(1024, 1024 * 1024)
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

fn parse_status_ids(value: &str) -> Result<(u32, u32), AttestationError> {
    let mut uid = None;
    let mut gid = None;
    for line in value.lines() {
        if let Some(rest) = line.strip_prefix("Uid:") {
            uid = Some(parse_uniform_id_field("Uid", rest)?);
        } else if let Some(rest) = line.strip_prefix("Gid:") {
            gid = Some(parse_uniform_id_field("Gid", rest)?);
        }
    }
    Ok((
        uid.ok_or(AttestationError::MalformedStatus("missing Uid"))?,
        gid.ok_or(AttestationError::MalformedStatus("missing Gid"))?,
    ))
}

fn parse_uniform_id_field(label: &'static str, value: &str) -> Result<u32, AttestationError> {
    let parsed = value
        .split_whitespace()
        .map(str::parse::<u32>)
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
    start_time
        .parse::<u64>()
        .map_err(|_| AttestationError::MalformedStat("invalid starttime field"))
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

#[cfg(any(target_os = "linux", target_os = "android"))]
fn open_pidfd(pid: u32) -> Result<OwnedFd, AttestationError> {
    // SAFETY: `pidfd_open` takes only integer values and returns a new owned FD
    // on success. No pointer is passed or retained.
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid as libc::pid_t, 0_u32) };
    if raw < 0 {
        return Err(AttestationError::Pidfd(io::Error::last_os_error()));
    }
    let raw = i32::try_from(raw).map_err(|_| AttestationError::InvalidPidfd)?;
    // SAFETY: the successful `pidfd_open` result is a fresh descriptor owned by
    // this function and is transferred exactly once to `OwnedFd`.
    Ok(unsafe { OwnedFd::from_raw_fd(raw) })
}

#[cfg(not(any(target_os = "linux", target_os = "android")))]
fn open_pidfd(_pid: u32) -> Result<OwnedFd, AttestationError> {
    Err(AttestationError::UnsupportedPlatform)
}

#[cfg(any(target_os = "linux", target_os = "android"))]
fn ensure_pidfd_alive(pidfd: &OwnedFd) -> Result<(), AttestationError> {
    use std::os::fd::AsRawFd;
    let mut descriptor = libc::pollfd {
        fd: pidfd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    // SAFETY: `descriptor` is valid writable storage for one pollfd and remains
    // alive for the call. `poll` does not retain the pointer.
    let result = unsafe { libc::poll(std::ptr::addr_of_mut!(descriptor), 1, 0) };
    if result < 0 {
        return Err(AttestationError::Pidfd(io::Error::last_os_error()));
    }
    if result > 0 && descriptor.revents != 0 {
        return Err(AttestationError::PeerExited);
    }
    Ok(())
}

#[cfg(not(any(target_os = "linux", target_os = "android")))]
fn ensure_pidfd_alive(_pidfd: &OwnedFd) -> Result<(), AttestationError> {
    Err(AttestationError::UnsupportedPlatform)
}

#[derive(Debug)]
pub enum AttestationError {
    UnsupportedPlatform,
    MissingPeerPid,
    InvalidPidfd,
    Pidfd(io::Error),
    PeerExited,
    ReadProc {
        path: PathBuf,
        source: io::Error,
    },
    ProcFileTooLarge {
        path: PathBuf,
        length: u64,
        maximum: usize,
    },
    MalformedStatus(&'static str),
    NonUniformProcessIds {
        field: &'static str,
        values: Vec<u32>,
    },
    MalformedStat(&'static str),
    MalformedCgroup(&'static str),
    InvalidSystemdUnit(String),
    PeerCredentialDrift {
        socket_uid: u32,
        socket_gid: u32,
        proc_uid: u32,
        proc_gid: u32,
    },
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
    ProcessIdentityChanged,
    InvalidAccountName,
    AccountLookup(io::Error),
    AccountNotFound(String),
}

impl fmt::Display for AttestationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnsupportedPlatform => formatter.write_str("pidfd peer attestation is unsupported"),
            Self::MissingPeerPid => formatter.write_str("peer credentials do not contain a PID"),
            Self::InvalidPidfd => formatter.write_str("pidfd result does not fit an owned descriptor"),
            Self::Pidfd(error) => write!(formatter, "pidfd operation failed: {error}"),
            Self::PeerExited => formatter.write_str("peer exited during runtime attestation"),
            Self::ReadProc { path, source } => {
                write!(formatter, "failed to read {}: {source}", path.display())
            }
            Self::ProcFileTooLarge {
                path,
                length,
                maximum,
            } => write!(
                formatter,
                "proc file {} has {length} bytes, maximum {maximum}",
                path.display()
            ),
            Self::MalformedStatus(reason) => write!(formatter, "malformed proc status: {reason}"),
            Self::NonUniformProcessIds { field, values } => {
                write!(formatter, "proc {field} identities are not uniform: {values:?}")
            }
            Self::MalformedStat(reason) => write!(formatter, "malformed proc stat: {reason}"),
            Self::MalformedCgroup(reason) => write!(formatter, "malformed proc cgroup: {reason}"),
            Self::InvalidSystemdUnit(unit) => write!(formatter, "invalid systemd unit name: {unit}"),
            Self::PeerCredentialDrift {
                socket_uid,
                socket_gid,
                proc_uid,
                proc_gid,
            } => write!(
                formatter,
                "socket peer {socket_uid}:{socket_gid} differs from proc identity {proc_uid}:{proc_gid}"
            ),
            Self::UidMismatch { expected, actual } => {
                write!(formatter, "peer UID {actual} does not match {expected}")
            }
            Self::GidMismatch { expected, actual } => {
                write!(formatter, "peer GID {actual} does not match {expected}")
            }
            Self::CgroupMismatch { expected, actual } => {
                write!(formatter, "peer cgroup {actual} does not match {expected}")
            }
            Self::SystemdUnitMismatch { expected, actual } => {
                write!(formatter, "peer unit {actual:?} does not match {expected:?}")
            }
            Self::ProcessIdentityChanged => {
                formatter.write_str("peer runtime identity changed during attestation")
            }
            Self::InvalidAccountName => formatter.write_str("account name contains NUL"),
            Self::AccountLookup(error) => write!(formatter, "account lookup failed: {error}"),
            Self::AccountNotFound(name) => write!(formatter, "account not found: {name}"),
        }
    }
}

impl std::error::Error for AttestationError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Pidfd(error) | Self::AccountLookup(error) => Some(error),
            Self::ReadProc { source, .. } => Some(source),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use hepta_agent_transport::PeerIdentity;
    use std::io::Write;
    use std::os::unix::net::UnixStream;
    use tempfile::TempDir;

    fn fixture_snapshot(
        root: &Path,
        pid: u32,
        uid: u32,
        gid: u32,
        cgroup: &str,
        start_time: u64,
    ) {
        let process = root.join(pid.to_string());
        fs::create_dir_all(&process).unwrap();
        fs::write(
            process.join("status"),
            format!("Name:\tfixture\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\nGid:\t{gid}\t{gid}\t{gid}\t{gid}\n"),
        )
        .unwrap();
        let mut stat = fs::File::create(process.join("stat")).unwrap();
        write!(
            stat,
            "{pid} (fixture process) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 {start_time} 21 22\n"
        )
        .unwrap();
        fs::write(process.join("cgroup"), format!("0::{cgroup}\n")).unwrap();
    }

    #[test]
    fn reads_exact_unified_identity_snapshot() {
        let temp = TempDir::new().unwrap();
        fixture_snapshot(
            temp.path(),
            42,
            1001,
            1002,
            "/system.slice/hepta-agent.service",
            777,
        );
        let snapshot = ProcfsPeerAttestor::new(temp.path())
            .read_snapshot(42)
            .unwrap();
        assert_eq!(snapshot.pid, 42);
        assert_eq!(snapshot.uid, 1001);
        assert_eq!(snapshot.gid, 1002);
        assert_eq!(snapshot.start_time_ticks, 777);
        assert_eq!(snapshot.cgroup_v2_path, "/system.slice/hepta-agent.service");
        assert_eq!(snapshot.systemd_unit.as_deref(), Some("hepta-agent.service"));
        PeerRuntimePolicy::for_system_service(1001, 1002, "hepta-agent.service")
            .unwrap()
            .authorize(&snapshot)
            .unwrap();
    }

    #[test]
    fn rejects_setuid_or_setgid_transition_shape() {
        let status = "Uid:\t1000\t0\t0\t0\nGid:\t1000\t1000\t1000\t1000\n";
        assert!(matches!(
            parse_status_ids(status),
            Err(AttestationError::NonUniformProcessIds { field: "Uid", .. })
        ));
    }

    #[test]
    fn stat_parser_handles_spaces_and_parentheses_in_comm() {
        let stat = "9 (name with ) spaces) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 123456 21";
        assert_eq!(parse_start_time_ticks(stat).unwrap(), 123456);
    }

    #[test]
    fn rejects_legacy_only_or_unsafe_cgroup_data() {
        assert!(parse_unified_cgroup_path("2:cpu:/legacy\n").is_err());
        assert!(parse_unified_cgroup_path("0::/system.slice/../escape\n").is_err());
        assert!(parse_unified_cgroup_path("0::/a\n0::/b\n").is_err());
    }

    #[test]
    fn exact_policy_rejects_wrong_unit_or_cgroup() {
        let snapshot = PeerRuntimeSnapshot {
            pid: 1,
            uid: 1000,
            gid: 1000,
            start_time_ticks: 1,
            cgroup_v2_path: "/system.slice/other.service".to_owned(),
            systemd_unit: Some("other.service".to_owned()),
        };
        let error = PeerRuntimePolicy::for_system_service(1000, 1000, "hepta-agent.service")
            .unwrap()
            .authorize(&snapshot)
            .unwrap_err();
        assert!(matches!(error, AttestationError::CgroupMismatch { .. }));
    }

    #[cfg(any(target_os = "linux", target_os = "android"))]
    #[test]
    fn live_peer_is_bound_to_pidfd_and_current_proc_identity() {
        let (client, _server) = UnixStream::pair().unwrap();
        let peer = PeerIdentity::from_stream(&client).unwrap();
        let attestor = ProcfsPeerAttestor::default();
        let snapshot = attestor.read_snapshot(peer.pid.unwrap()).unwrap();
        let attested = attestor
            .attest(peer, &PeerRuntimePolicy::exact(&snapshot))
            .unwrap();
        assert_eq!(attested.snapshot(), &snapshot);
        attested.ensure_alive().unwrap();
    }

    #[test]
    fn resolves_current_account_names_when_present() {
        // The test only checks the lookup mechanism, not a fixed distro UID.
        let uid = resolve_user_id("root").unwrap();
        let gid = resolve_group_id("root").unwrap();
        assert_eq!(uid, 0);
        assert_eq!(gid, 0);
    }
}
