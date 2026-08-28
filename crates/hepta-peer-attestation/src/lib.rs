//! Runtime identity attestation for a peer accepted on the local Agent socket.
//!
//! `SO_PEERCRED` binds a connected AF_UNIX stream to a kernel PID/UID/GID.
//! This crate keeps a pidfd alive while it verifies bounded procfs identity,
//! process start time, the unified cgroup-v2 path, and the expected systemd
//! service unit. It creates no socket, listener, browser authority, or permit.

#![deny(unsafe_op_in_unsafe_fn)]

use hepta_agent_transport::PeerIdentity;
use std::ffi::{CStr, CString};
use std::fmt;
use std::fs;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::path::{Path, PathBuf};

const MAX_STATUS_BYTES: usize = 128 * 1024;
const MAX_STAT_BYTES: usize = 64 * 1024;
const MAX_CGROUP_BYTES: usize = 64 * 1024;
const MAX_ACCOUNT_BUFFER_BYTES: usize = 1024 * 1024;

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
        if pid == 0 {
            return Err(AttestationError::MissingPeerPid);
        }
        let process_root = self.proc_root.join(pid.to_string());
        let status = read_bounded(&process_root.join("status"), MAX_STATUS_BYTES)?;
        let (uid, gid) = parse_status_ids(&status)?;
        let stat = read_bounded(&process_root.join("stat"), MAX_STAT_BYTES)?;
        let start_time_ticks = parse_start_time_ticks(&stat)?;
        let cgroup = read_bounded(&process_root.join("cgroup"), MAX_CGROUP_BYTES)?;
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
        assert_eq!(attested.snapshot(), &snapshot);
    }

    #[test]
    fn root_account_resolution_is_consistent() {
        assert_eq!(resolve_user_id("root").expect("root user"), 0);
        assert_eq!(resolve_group_id("root").expect("root group"), 0);
    }
}
