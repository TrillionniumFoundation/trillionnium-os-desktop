//! Fresh host identity admission for the owned production namespace broker.
//!
//! This capability owns a real durable IdentityLease. Serialized observations,
//! numeric IDs and diagnostic reports cannot construct it. The observation
//! worker runs the same sealed executable without root privileges; its public
//! NSS result is consumed only after bounded pidfd-based exit and reap.
//!
//! No account, subordinate-ID grant, namespace, map, mount or Android data is
//! created here. Unsupported providers and unobservable namespace ownership
//! are rejected. This admission does not qualify the rest of the runtime.

use std::cell::Cell;
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::{CStr, CString};
use std::fs::{File, Metadata, OpenOptions};
use std::io::{self, Read, Write};
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::os::unix::net::UnixStream;
use std::path::{Component, Path, PathBuf};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::IdRange;
use crate::production_identity::IdentityLease;
use crate::production_namespace::OwnedNamespaceWitness;

const FILE_LIMIT: usize = 1024 * 1024;
const OUTPUT_LIMIT: usize = 8 * 1024 * 1024;
const RECORD_LIMIT: usize = 65536;
const PROC_LIMIT: usize = 65536;
const TASK_LIMIT: usize = 131072;
const WORKER_TIMEOUT: Duration = Duration::from_secs(30);
const RETIRE_TIMEOUT: Duration = Duration::from_secs(3);
const PROC_MAGIC: libc::c_long = 0x9fa0;
const NSFS_MAGIC: libc::c_long = 0x6e736673;
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const NS_GET_USERNS: libc::c_ulong = 0xb701;
const NS_GET_ID: libc::c_ulong = 0x8008_b70d;
const USER_NS_INIT_INO: u64 = 0xefff_fffd;
const USER_NS_INIT_ID: u64 = 3;
const WORKER_ARGUMENT: &str = "__production-nss-observe";
const USERDB: &str = "/run/systemd/userdb";

/// A rejected provider, changed observation, or unproven owned-worker exit.
#[derive(Debug, Error)]
pub enum HostAdmissionError {
    /// No complete fresh observation is available.
    #[error("production host admission rejected: {0}")]
    Rejected(String),
    /// A trusted input or a live identity changed during observation.
    #[error("production host observation changed; admission must be repeated")]
    Changed,
    /// The owned worker did not reach a proven reaped terminal state.
    #[error("NSS worker retirement is unproven; the identity lease is retained")]
    RetirementUnproven,
    /// A bounded read, socket or kernel operation failed.
    #[error(transparent)]
    Io(#[from] io::Error),
}
type Result<T> = std::result::Result<T, HostAdmissionError>;

fn reject(message: impl Into<String>) -> HostAdmissionError {
    HostAdmissionError::Rejected(message.into())
}

/// Non-serializable, non-cloneable authority owned by the namespace broker.
///
/// The lease is private and remains held throughout all map construction
/// stages. Dropping an admission never removes its durable reservation.
pub struct HostAdmission {
    lease: Option<IdentityLease>,
    baseline: Option<HostInputs>,
    quarantined: Cell<bool>,
}

impl HostAdmission {
    /// Observe the actual host and retain the supplied configured reservation.
    ///
    /// # Errors
    ///
    /// An unsupported provider, conflicting identity or namespace, changed
    /// input, non-root caller, or incomplete worker lifecycle rejects admission.
    pub fn acquire(lease: IdentityLease) -> Result<Self> {
        let mut value = Self {
            lease: Some(lease),
            baseline: None,
            quarantined: Cell::new(false),
        };
        let inputs = value.observe(None, true)?;
        value.baseline = Some(inputs);
        Ok(value)
    }

    pub(crate) fn lease(&self) -> &IdentityLease {
        self.lease
            .as_ref()
            .expect("admission owns its lease until drop")
    }

    // Reservation/provider revalidation only. Once the broker owns a user
    // namespace, map writes must use revalidate_live with its actual witness.
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.observe(None, false).map(|_| ())
    }

    pub(crate) fn revalidate_live(&self, witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
        witness
            .revalidate()
            .map_err(|error| reject(error.to_string()))?;
        self.observe(Some(witness), true)?;
        witness
            .revalidate()
            .map_err(|error| reject(error.to_string()))?;
        Ok(())
    }

    fn observe(
        &self,
        witness: Option<&OwnedNamespaceWitness<'_>>,
        include_live: bool,
    ) -> Result<HostInputs> {
        if self.quarantined.get() {
            return Err(HostAdmissionError::RetirementUnproven);
        }
        require_initial_root()?;
        self.lease()
            .revalidate_for_broker()
            .map_err(|error| reject(error.to_string()))?;
        let before = HostInputs::capture()?;
        if let Some(baseline) = &self.baseline {
            baseline.sssd.revalidate_held()?;
            if baseline != &before {
                return Err(HostAdmissionError::Changed);
            }
        }
        let observation = match run_owned_worker(&self.quarantined) {
            Err(HostAdmissionError::RetirementUnproven) => {
                self.quarantined.set(true);
                return Err(HostAdmissionError::RetirementUnproven);
            }
            value => value?,
        };
        let (name, uid, gid) = self.lease().broker_principal();
        let (uids, gids) = self.lease().broker_ranges();
        validate_public_identities(&before, &observation, name, uid, gid, uids, gids)?;
        if include_live {
            audit_live_tasks(uids, gids, uid, gid, witness)?;
        }
        let final_observation = match run_owned_worker(&self.quarantined) {
            Err(HostAdmissionError::RetirementUnproven) => {
                self.quarantined.set(true);
                return Err(HostAdmissionError::RetirementUnproven);
            }
            value => value?,
        };
        validate_public_identities(&before, &final_observation, name, uid, gid, uids, gids)?;
        if observation != final_observation {
            return Err(HostAdmissionError::Changed);
        }
        before.sssd.revalidate_held()?;
        let after = HostInputs::capture()?;
        before.sssd.revalidate_held()?;
        if before != after {
            return Err(HostAdmissionError::Changed);
        }
        self.lease()
            .revalidate_for_broker()
            .map_err(|error| reject(error.to_string()))?;
        Ok(after)
    }
}

impl Drop for HostAdmission {
    fn drop(&mut self) {
        if self.quarantined.get() {
            if let Some(lease) = self.lease.take() {
                // Unknown child exit must not release the live reservation lock.
                mem::forget(lease);
            }
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct PublicUser {
    name: String,
    uid: u32,
    gid: u32,
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct PublicGroup {
    name: String,
    gid: u32,
    members: Vec<String>,
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize, Ord, PartialOrd)]
#[serde(deny_unknown_fields)]
struct Membership {
    user: String,
    group: String,
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProviderRecords {
    service: String,
    users: Vec<PublicUser>,
    groups: Vec<PublicGroup>,
    memberships: Vec<Membership>,
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct PublicObservation {
    schema: u32,
    nss_users: Vec<PublicUser>,
    nss_groups: Vec<PublicGroup>,
    providers: Vec<ProviderRecords>,
    sssd: SssdSystemObservation,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Node {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    size: u64,
    mtime: (i64, i64),
    ctime: (i64, i64),
}
impl Node {
    fn of(metadata: &Metadata) -> Self {
        Self {
            dev: metadata.dev(),
            ino: metadata.ino(),
            mode: metadata.mode(),
            uid: metadata.uid(),
            gid: metadata.gid(),
            links: metadata.nlink(),
            size: metadata.len(),
            mtime: (metadata.mtime(), metadata.mtime_nsec()),
            ctime: (metadata.ctime(), metadata.ctime_nsec()),
        }
    }
    fn key(&self) -> (u64, u64) {
        (self.dev, self.ino)
    }
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct Seal {
    path: String,
    node: Option<Node>,
    sha256: Option<String>,
    entries: Vec<(String, Node)>,
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct HostInputs {
    seals: Vec<Seal>,
    users: Vec<PublicUser>,
    groups: Vec<PublicGroup>,
    services: Vec<String>,
    sssd: InactiveSssd,
}

const SSSD_STATE_PATHS: &[&str] = &[
    "/var/lib/sss",
    "/var/lib/sss/db",
    "/var/lib/sss/mc",
    "/var/lib/sss/pipes",
    "/var/lib/sss/pipes/private",
    "/run/sssd",
];
const SSSD_UNITS: &[(&str, usize, &str)] = &[
    (
        "sssd.service",
        1426,
        "5d782f35931160e062a42000ae6636a1f46ad94618a564e718a7094767815da1",
    ),
    (
        "sssd-nss.service",
        994,
        "709f22fe2c2110e0cdc805bb3b1c41a0e1926defed5a241e21e091b0a1db7e90",
    ),
    (
        "sssd-nss.socket",
        453,
        "c69f7b33ca98f17c586e7837e6dc9d5df92bf096da4ff6d31437eef904ab0bf8",
    ),
];
const SYSTEMD_LIBRARY: &str = "/usr/lib/x86_64-linux-gnu/libsystemd.so.0.42.0";
const SYSTEMD_LIBRARY_SHA: &str =
    "7c8bd89f59b9f96fdb933eb1414f449c2db45fbb078c8d793cc46f9173be7934";

#[derive(Clone, Debug, Eq, PartialEq)]
struct SssdIdentity {
    uid: u32,
    gid: u32,
}

#[derive(Clone, Debug)]
struct HeldSssdDirectory {
    file: std::sync::Arc<File>,
    seal: Seal,
}
impl PartialEq for HeldSssdDirectory {
    fn eq(&self, other: &Self) -> bool {
        self.seal == other.seal
    }
}
impl Eq for HeldSssdDirectory {}

#[derive(Clone, Debug, Eq, PartialEq)]
struct InactiveSssd {
    identity: SssdIdentity,
    directories: Vec<HeldSssdDirectory>,
}

fn sssd_files_identity(
    passwd: &str,
    users: &[PublicUser],
    groups: &[PublicGroup],
) -> Result<SssdIdentity> {
    let selected: Vec<_> = users.iter().filter(|u| u.name == "sssd").collect();
    if selected.len() != 1 || selected[0].uid == 0 || selected[0].gid == 0 {
        return Err(reject("one non-root SSSD files service identity required"));
    }
    let identity = SssdIdentity {
        uid: selected[0].uid,
        gid: selected[0].gid,
    };
    if identity.uid == u32::MAX
        || identity.gid == u32::MAX
        || users
            .iter()
            .filter(|u| u.uid == identity.uid || u.gid == identity.gid)
            .count()
            != 1
        || groups
            .iter()
            .filter(|g| g.name == "sssd" || g.gid == identity.gid)
            .count()
            != 1
        || !groups
            .iter()
            .any(|g| g.name == "sssd" && g.gid == identity.gid && g.members.is_empty())
        || groups.iter().any(|g| g.members.iter().any(|m| m == "sssd"))
    {
        return Err(reject("SSSD service UID/GID or memberships are shared"));
    }
    let selected: Vec<_> = passwd
        .lines()
        .filter(|line| line.split(':').next() == Some("sssd"))
        .collect();
    let fields: Vec<_> = selected
        .first()
        .ok_or_else(|| reject("SSSD files record missing"))?
        .split(':')
        .collect();
    if selected.len() != 1
        || fields.len() != 7
        || fields[5] != "/var/lib/sss"
        || fields[6] != "/usr/sbin/nologin"
    {
        return Err(reject(
            "SSSD must retain its noninteractive package service identity",
        ));
    }
    Ok(identity)
}

fn sssd_directory_policy(node: &Node, identity: &SssdIdentity) -> Result<()> {
    if node.mode & libc::S_IFMT != libc::S_IFDIR
        || node.uid != identity.uid
        || node.gid != identity.gid
        || node.mode & 0o6002 != 0
    {
        return Err(reject(
            "fixed SSSD state directory has an unknown owner or unsafe mode",
        ));
    }
    Ok(())
}

fn open_sssd_directory(path: &str, identity: &SssdIdentity) -> Result<File> {
    // This exception is deliberately absent from open_absolute/owned_trusted.
    // It applies only to the six fixed package state paths, never to config.
    if !SSSD_STATE_PATHS.contains(&path) {
        return Err(reject("SSSD directory exception outside fixed state paths"));
    }
    let (base, tail) = if let Some(tail) = path.strip_prefix("/var/lib/") {
        ("/var/lib", tail)
    } else if let Some(tail) = path.strip_prefix("/run/") {
        ("/run", tail)
    } else {
        return Err(reject("SSSD state path outside trusted parents"));
    };
    let mut directory = open_absolute(base, libc::O_RDONLY | libc::O_DIRECTORY)?;
    owned_trusted(&directory.metadata()?)?;
    for part in tail.split('/') {
        directory = open_at(&directory, part, libc::O_RDONLY | libc::O_DIRECTORY)?;
        sssd_directory_policy(&Node::of(&directory.metadata()?), identity)?;
    }
    Ok(directory)
}

fn sssd_directory_seal(path: &str, file: &File, identity: &SssdIdentity) -> Result<Seal> {
    let before = Node::of(&file.metadata()?);
    sssd_directory_policy(&before, identity)?;
    let allowed: &[&str] = match path {
        "/var/lib/sss" => &[
            "db",
            "deskprofile",
            "gpo_cache",
            "keytabs",
            "mc",
            "pipes",
            "pubconf",
            "secrets",
        ],
        "/var/lib/sss/pipes" => &["private"],
        _ => &[],
    };
    let names = directory_names(file, 32)?;
    if names.iter().any(|name| !allowed.contains(&name.as_str()))
        || (path == "/var/lib/sss"
            && ["db", "mc", "pipes"]
                .iter()
                .any(|required| !names.iter().any(|n| n == required)))
    {
        return Err(reject(
            "SSSD configuration cache or socket state is nonempty or unknown",
        ));
    }
    let mut entries = Vec::new();
    for name in names {
        let node = Node::of(&stat_at(file, &name)?);
        sssd_directory_policy(&node, identity)?;
        entries.push((name, node));
    }
    if before != Node::of(&file.metadata()?) {
        return Err(HostAdmissionError::Changed);
    }
    Ok(Seal {
        path: path.into(),
        node: Some(before),
        sha256: None,
        entries,
    })
}

impl InactiveSssd {
    fn capture(passwd: &str, users: &[PublicUser], groups: &[PublicGroup]) -> Result<Self> {
        let identity = sssd_files_identity(passwd, users, groups)?;
        let mut directories = Vec::new();
        for &path in SSSD_STATE_PATHS {
            let file = open_sssd_directory(path, &identity)?;
            let seal = sssd_directory_seal(path, &file, &identity)?;
            directories.push(HeldSssdDirectory {
                file: std::sync::Arc::new(file),
                seal,
            });
        }
        let value = Self {
            identity,
            directories,
        };
        value.revalidate_held()?;
        value.no_live_service_credentials()?;
        Ok(value)
    }
    fn revalidate_held(&self) -> Result<()> {
        for held in &self.directories {
            let current = open_sssd_directory(&held.seal.path, &self.identity)?;
            if sssd_directory_seal(&held.seal.path, &held.file, &self.identity)? != held.seal
                || sssd_directory_seal(&held.seal.path, &current, &self.identity)? != held.seal
            {
                return Err(HostAdmissionError::Changed);
            }
        }
        Ok(())
    }
    fn no_live_service_credentials(&self) -> Result<()> {
        let proc = open_absolute("/proc", libc::O_RDONLY | libc::O_DIRECTORY)?;
        if fs_type(&proc)? != PROC_MAGIC {
            return Err(reject("actual host procfs required for SSSD inactivity"));
        }
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut count = 0_usize;
        for name in directory_names(&proc, PROC_LIMIT)? {
            let Ok(pid) = name.parse::<u32>() else {
                continue;
            };
            if pid == 0 || name != pid.to_string() {
                return Err(reject("noncanonical proc PID"));
            }
            if Instant::now() >= deadline {
                return Err(reject("SSSD process observation deadline"));
            }
            let leader = match open_at(&proc, &name, libc::O_RDONLY | libc::O_DIRECTORY) {
                Ok(file) => file,
                Err(error) if error.kind() == io::ErrorKind::NotFound => {
                    return Err(HostAdmissionError::Changed);
                }
                Err(error) => return Err(error.into()),
            };
            let start = task_start(&proc_text(&leader, "stat")?, pid)?.0;
            let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) as i32 };
            if raw < 0 {
                return Err(io::Error::last_os_error().into());
            }
            let pidfd = unsafe { OwnedFd::from_raw_fd(raw) };
            if pidfd_terminal(pidfd.as_raw_fd())? {
                continue;
            }
            if start != task_start(&proc_text(&leader, "stat")?, pid)?.0 {
                return Err(HostAdmissionError::Changed);
            }
            let tasks = open_at(&leader, "task", libc::O_RDONLY | libc::O_DIRECTORY)?;
            for tid_name in directory_names(&tasks, TASK_LIMIT)? {
                let tid = number(&tid_name)?;
                if tid == 0 || tid.to_string() != tid_name {
                    return Err(reject("noncanonical proc TID"));
                }
                count += 1;
                if count > TASK_LIMIT || Instant::now() >= deadline {
                    return Err(reject("SSSD task observation bound"));
                }
                let task = open_at(&tasks, &tid_name, libc::O_RDONLY | libc::O_DIRECTORY)?;
                let before = task_start(&proc_text(&task, "stat")?, tid)?.0;
                let credentials = parse_status(&proc_text(&task, "status")?)?;
                if credentials.tgid != pid
                    || before != task_start(&proc_text(&task, "stat")?, tid)?.0
                {
                    return Err(HostAdmissionError::Changed);
                }
                if credentials.uids.contains(&self.identity.uid)
                    || credentials.gids.contains(&self.identity.gid)
                    || credentials.groups.contains(&self.identity.gid)
                {
                    return Err(reject("SSSD service identity has a live host task"));
                }
            }
        }
        Ok(())
    }
}

fn trusted_systemd_library() -> Result<(File, Seal)> {
    let file = open_absolute(SYSTEMD_LIBRARY, libc::O_RDONLY)?;
    let before = Node::of(&file.metadata()?);
    owned_trusted(&file.metadata()?)?;
    if before.mode & libc::S_IFMT != libc::S_IFREG
        || before.links != 1
        || before.size != 1_127_960
        || before.mode & 0o6000 != 0
    {
        return Err(reject("reviewed public systemd library custody differs"));
    }
    let raw = read_bounded(&file, 2 * FILE_LIMIT)?;
    let digest = format!("{:x}", Sha256::digest(&raw));
    if digest != SYSTEMD_LIBRARY_SHA || before != Node::of(&file.metadata()?) {
        return Err(reject("reviewed public systemd library bytes changed"));
    }
    Ok((
        file,
        Seal {
            path: SYSTEMD_LIBRARY.into(),
            node: Some(before),
            sha256: Some(digest),
            entries: Vec::new(),
        },
    ))
}

fn system_bus_seal() -> Result<Seal> {
    let dir = open_absolute("/run/dbus", libc::O_RDONLY | libc::O_DIRECTORY)?;
    owned_trusted(&dir.metadata()?)?;
    let before = Node::of(&dir.metadata()?);
    let socket = Node::of(&stat_at(&dir, "system_bus_socket")?);
    // A socket's write bits grant connect permission; they do not grant inode
    // replacement in its trusted parent directory.
    if socket.mode & libc::S_IFMT != libc::S_IFSOCK || socket.uid != 0 || socket.links != 1 {
        return Err(reject("trusted public system bus socket required"));
    }
    if before != Node::of(&dir.metadata()?) {
        return Err(HostAdmissionError::Changed);
    }
    Ok(Seal {
        path: "/run/dbus".into(),
        node: Some(before),
        sha256: None,
        entries: vec![("system_bus_socket".into(), socket)],
    })
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct SssdUnitObservation {
    unit: String,
    load_state: String,
    active_state: String,
    sub_state: String,
    fragment_path: String,
    unit_file_state: String,
    condition_result: bool,
    control_group: String,
    drop_in_paths: Vec<String>,
    main_pid: Option<u32>,
    user: Option<String>,
    group: Option<String>,
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct SssdSystemObservation {
    manager_pid: u32,
    manager_euid: u32,
    units: Vec<SssdUnitObservation>,
}

fn validate_sssd_system(observed: &SssdSystemObservation) -> Result<()> {
    if observed.manager_pid != 1 || observed.manager_euid != 0 || observed.units.len() != 3 {
        return Err(reject(
            "fresh system manager SSSD observation is incomplete",
        ));
    }
    let mut seen = BTreeSet::new();
    for unit in &observed.units {
        if !SSSD_UNITS.iter().any(|row| row.0 == unit.unit)
            || !seen.insert(&unit.unit)
            || unit.load_state != "loaded"
            || unit.active_state != "inactive"
            || unit.sub_state != "dead"
            || !unit.control_group.is_empty()
            || !unit.drop_in_paths.is_empty()
            || unit.fragment_path != format!("/usr/lib/systemd/system/{}", unit.unit)
        {
            return Err(reject(
                "SSSD unit is active, overridden, unavailable or has an owned cgroup",
            ));
        }
        let socket = unit.unit == "sssd-nss.socket";
        if unit.condition_result != socket
            || unit.unit_file_state
                != if unit.unit == "sssd-nss.service" {
                    "indirect"
                } else {
                    "enabled"
                }
            || if socket {
                unit.main_pid.is_some() || unit.user.is_some() || unit.group.is_some()
            } else {
                unit.main_pid != Some(0)
                    || unit.user.as_deref() != Some("sssd")
                    || unit.group.as_deref() != Some("sssd")
            }
        {
            return Err(reject(
                "SSSD package condition, service identity or enablement changed",
            ));
        }
    }
    Ok(())
}

fn sssd_public_coverage(inputs: &HostInputs, observed: &PublicObservation) -> Result<()> {
    let identity = &inputs.sssd.identity;
    let selected: Vec<_> = observed
        .nss_users
        .iter()
        .filter(|u| u.name == "sssd" || u.uid == identity.uid || u.gid == identity.gid)
        .collect();
    if selected.len() != 1
        || selected[0].name != "sssd"
        || selected[0].uid != identity.uid
        || selected[0].gid != identity.gid
    {
        return Err(reject(
            "complete NSS disagrees with the unique SSSD files identity",
        ));
    }
    let selected: Vec<_> = observed
        .nss_groups
        .iter()
        .filter(|g| g.name == "sssd" || g.gid == identity.gid)
        .collect();
    if selected.len() != 1
        || selected[0].name != "sssd"
        || selected[0].gid != identity.gid
        || !selected[0].members.is_empty()
        || observed
            .nss_groups
            .iter()
            .any(|g| g.members.iter().any(|m| m == "sssd"))
    {
        return Err(reject(
            "complete NSS shares the SSSD primary or supplemental group",
        ));
    }
    for provider in &observed.providers {
        if provider
            .users
            .iter()
            .any(|u| u.name == "sssd" || u.uid == identity.uid || u.gid == identity.gid)
            || provider.groups.iter().any(|g| {
                g.name == "sssd" || g.gid == identity.gid || g.members.iter().any(|m| m == "sssd")
            })
            || provider
                .memberships
                .iter()
                .any(|m| m.user == "sssd" || m.group == "sssd")
        {
            return Err(reject(
                "dynamic NSS provider shadows the fixed SSSD service identity",
            ));
        }
    }
    validate_sssd_system(&observed.sssd)
}

// The NSS worker is already a bounded single-threaded, unprivileged process.
// Load only the observed, root-owned public library through its held FD. No
// command execution, private systemd connection, or unit mutation is exposed.
type Bus = *mut libc::c_void;
type BusNew = unsafe extern "C" fn(*mut Bus) -> libc::c_int;
type BusSetAddress = unsafe extern "C" fn(Bus, *const libc::c_char) -> libc::c_int;
type BusSetInt = unsafe extern "C" fn(Bus, libc::c_int) -> libc::c_int;
type BusSetTimeout = unsafe extern "C" fn(Bus, u64) -> libc::c_int;
type BusStart = unsafe extern "C" fn(Bus) -> libc::c_int;
type BusClose = unsafe extern "C" fn(Bus) -> Bus;
type BusString = unsafe extern "C" fn(
    Bus,
    *const libc::c_char,
    *const libc::c_char,
    *const libc::c_char,
    *const libc::c_char,
    *mut libc::c_void,
    *mut *mut libc::c_char,
) -> libc::c_int;
type BusTrivial = unsafe extern "C" fn(
    Bus,
    *const libc::c_char,
    *const libc::c_char,
    *const libc::c_char,
    *const libc::c_char,
    *mut libc::c_void,
    libc::c_char,
    *mut libc::c_void,
) -> libc::c_int;
type BusStrv = unsafe extern "C" fn(
    Bus,
    *const libc::c_char,
    *const libc::c_char,
    *const libc::c_char,
    *const libc::c_char,
    *mut libc::c_void,
    *mut *mut *mut libc::c_char,
) -> libc::c_int;
type BusCreds = unsafe extern "C" fn(Bus, *const libc::c_char, u64, *mut Bus) -> libc::c_int;
type CredsPid = unsafe extern "C" fn(Bus, *mut libc::pid_t) -> libc::c_int;
type CredsEuid = unsafe extern "C" fn(Bus, *mut libc::uid_t) -> libc::c_int;

struct PublicSystemdLibrary {
    handle: Bus,
    file: File,
    seal: Seal,
}
impl Drop for PublicSystemdLibrary {
    fn drop(&mut self) {
        if !self.handle.is_null() {
            unsafe {
                libc::dlclose(self.handle);
            }
        }
    }
}
impl PublicSystemdLibrary {
    fn open() -> Result<Self> {
        let (file, seal) = trusted_systemd_library()?;
        let path = CString::new(format!("/proc/self/fd/{}", file.as_raw_fd())).unwrap();
        let handle = unsafe { libc::dlopen(path.as_ptr(), libc::RTLD_NOW | libc::RTLD_LOCAL) };
        if handle.is_null() {
            return Err(reject(
                "reviewed public systemd library could not be loaded",
            ));
        }
        let value = Self { handle, file, seal };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        let named = open_absolute(SYSTEMD_LIBRARY, libc::O_RDONLY)?;
        if Some(Node::of(&self.file.metadata()?)) != self.seal.node
            || Some(Node::of(&named.metadata()?)) != self.seal.node
        {
            return Err(HostAdmissionError::Changed);
        }
        Ok(())
    }
}

struct PublicSystemdBus {
    library: PublicSystemdLibrary,
    bus: Bus,
    close: BusClose,
    get_string: BusString,
    get_trivial: BusTrivial,
    get_strv: BusStrv,
    get_creds: BusCreds,
    creds_pid: CredsPid,
    creds_euid: CredsEuid,
    creds_unref: BusClose,
}
impl Drop for PublicSystemdBus {
    fn drop(&mut self) {
        if !self.bus.is_null() {
            unsafe {
                (self.close)(self.bus);
            }
            self.bus = std::ptr::null_mut();
        }
    }
}
fn bus_rc(code: libc::c_int) -> Result<()> {
    if code < 0 {
        return Err(io::Error::from_raw_os_error(-code).into());
    }
    Ok(())
}
impl PublicSystemdBus {
    fn open() -> Result<Self> {
        let library = PublicSystemdLibrary::open()?;
        macro_rules! symbol {
            ($name:literal, $ty:ty) => {{
                let address =
                    unsafe { libc::dlsym(library.handle, concat!($name, "\0").as_ptr().cast()) };
                if address.is_null() {
                    return Err(reject(concat!("missing public systemd ABI: ", $name)));
                }
                // The exact reviewed systemd header defines this symbol's ABI.
                unsafe { mem::transmute::<*mut libc::c_void, $ty>(address) }
            }};
        }
        let new = symbol!("sd_bus_new", BusNew);
        let set_address = symbol!("sd_bus_set_address", BusSetAddress);
        let set_client = symbol!("sd_bus_set_bus_client", BusSetInt);
        let set_timeout = symbol!("sd_bus_set_method_call_timeout", BusSetTimeout);
        let start = symbol!("sd_bus_start", BusStart);
        let close = symbol!("sd_bus_close_unref", BusClose);
        let get_string = symbol!("sd_bus_get_property_string", BusString);
        let get_trivial = symbol!("sd_bus_get_property_trivial", BusTrivial);
        let get_strv = symbol!("sd_bus_get_property_strv", BusStrv);
        let get_creds = symbol!("sd_bus_get_name_creds", BusCreds);
        let creds_pid = symbol!("sd_bus_creds_get_pid", CredsPid);
        let creds_euid = symbol!("sd_bus_creds_get_euid", CredsEuid);
        let creds_unref = symbol!("sd_bus_creds_unref", BusClose);
        let mut value = Self {
            library,
            bus: std::ptr::null_mut(),
            close,
            get_string,
            get_trivial,
            get_strv,
            get_creds,
            creds_pid,
            creds_euid,
            creds_unref,
        };
        bus_rc(unsafe { new(&mut value.bus) })?;
        if value.bus.is_null() {
            return Err(reject("public system bus allocation failed"));
        }
        // An explicit fixed address avoids every environment/default fallback.
        bus_rc(unsafe {
            set_address(value.bus, c"unix:path=/run/dbus/system_bus_socket".as_ptr())
        })?;
        bus_rc(unsafe { set_client(value.bus, 1) })?;
        bus_rc(unsafe { set_timeout(value.bus, 500_000) })?;
        bus_rc(unsafe { start(value.bus) })?;
        value.manager_identity()?;
        Ok(value)
    }
    fn manager_identity(&self) -> Result<(u32, u32)> {
        let mut creds: Bus = std::ptr::null_mut();
        // PID and EUID come from the authenticated bus. Do not request AUGMENT,
        // which would synthesize credentials using a separate /proc lookup.
        bus_rc(unsafe {
            (self.get_creds)(
                self.bus,
                c"org.freedesktop.systemd1".as_ptr(),
                (1_u64 << 0) | (1_u64 << 4),
                &mut creds,
            )
        })?;
        if creds.is_null() {
            return Err(reject("system manager has no public credentials"));
        }
        let result = (|| {
            let mut pid = 0;
            let mut euid = u32::MAX;
            bus_rc(unsafe { (self.creds_pid)(creds, &mut pid) })?;
            bus_rc(unsafe { (self.creds_euid)(creds, &mut euid) })?;
            if pid != 1 || euid != 0 {
                return Err(reject("system manager is not initial PID1/root"));
            }
            Ok((pid as u32, euid))
        })();
        unsafe {
            (self.creds_unref)(creds);
        }
        result
    }
    fn string(&self, path: &CStr, interface: &CStr, property: &CStr) -> Result<String> {
        let mut raw = std::ptr::null_mut();
        let code = unsafe {
            (self.get_string)(
                self.bus,
                c"org.freedesktop.systemd1".as_ptr(),
                path.as_ptr(),
                interface.as_ptr(),
                property.as_ptr(),
                std::ptr::null_mut(),
                &mut raw,
            )
        };
        if code < 0 {
            if !raw.is_null() {
                unsafe {
                    libc::free(raw.cast());
                }
            }
            return Err(io::Error::from_raw_os_error(-code).into());
        }
        if raw.is_null() {
            return Err(reject("systemd string property is absent"));
        }
        let result = (|| {
            let bytes = unsafe { CStr::from_ptr(raw) }.to_bytes();
            if bytes.len() > 4096 {
                return Err(reject("public systemd property exceeds bound"));
            }
            String::from_utf8(bytes.to_vec())
                .map_err(|_| reject("non-UTF8 public systemd property"))
        })();
        unsafe {
            libc::free(raw.cast());
        }
        result
    }
    fn uint(&self, path: &CStr, interface: &CStr, property: &CStr) -> Result<u32> {
        let mut value = u32::MAX;
        bus_rc(unsafe {
            (self.get_trivial)(
                self.bus,
                c"org.freedesktop.systemd1".as_ptr(),
                path.as_ptr(),
                interface.as_ptr(),
                property.as_ptr(),
                std::ptr::null_mut(),
                b'u' as libc::c_char,
                (&mut value as *mut u32).cast(),
            )
        })?;
        Ok(value)
    }
    fn boolean(&self, path: &CStr, property: &CStr) -> Result<bool> {
        let mut value: libc::c_int = -1;
        bus_rc(unsafe {
            (self.get_trivial)(
                self.bus,
                c"org.freedesktop.systemd1".as_ptr(),
                path.as_ptr(),
                c"org.freedesktop.systemd1.Unit".as_ptr(),
                property.as_ptr(),
                std::ptr::null_mut(),
                b'b' as libc::c_char,
                (&mut value as *mut libc::c_int).cast(),
            )
        })?;
        match value {
            0 => Ok(false),
            1 => Ok(true),
            _ => Err(reject("non-boolean systemd property")),
        }
    }
    fn empty_dropins(&self, path: &CStr) -> Result<Vec<String>> {
        let mut raw: *mut *mut libc::c_char = std::ptr::null_mut();
        bus_rc(unsafe {
            (self.get_strv)(
                self.bus,
                c"org.freedesktop.systemd1".as_ptr(),
                path.as_ptr(),
                c"org.freedesktop.systemd1.Unit".as_ptr(),
                c"DropInPaths".as_ptr(),
                std::ptr::null_mut(),
                &mut raw,
            )
        })?;
        if raw.is_null() {
            return Ok(Vec::new());
        }
        let mut count = 0_usize;
        // The trusted library returns a null-terminated vector of owned C
        // strings. Reject nonempty overrides; release each returned allocation.
        while count < RECORD_LIMIT {
            let item = unsafe { *raw.add(count) };
            if item.is_null() {
                break;
            }
            unsafe {
                libc::free(item.cast());
            }
            count += 1;
        }
        unsafe {
            libc::free(raw.cast());
        }
        if count != 0 {
            return Err(reject("SSSD has systemd drop-in overrides"));
        }
        Ok(Vec::new())
    }
    fn observe(&self) -> Result<SssdSystemObservation> {
        let manager = self.manager_identity()?;
        let mut units = Vec::new();
        for &(unit, _, _) in SSSD_UNITS {
            let path = CString::new(format!(
                "/org/freedesktop/systemd1/unit/{}",
                unit.replace('-', "_2d").replace('.', "_2e")
            ))
            .unwrap();
            let u = c"org.freedesktop.systemd1.Unit";
            let socket = unit.ends_with(".socket");
            let kind = if socket {
                c"org.freedesktop.systemd1.Socket"
            } else {
                c"org.freedesktop.systemd1.Service"
            };
            units.push(SssdUnitObservation {
                unit: unit.into(),
                load_state: self.string(&path, u, c"LoadState")?,
                active_state: self.string(&path, u, c"ActiveState")?,
                sub_state: self.string(&path, u, c"SubState")?,
                fragment_path: self.string(&path, u, c"FragmentPath")?,
                unit_file_state: self.string(&path, u, c"UnitFileState")?,
                condition_result: self.boolean(&path, c"ConditionResult")?,
                control_group: self.string(&path, kind, c"ControlGroup")?,
                drop_in_paths: self.empty_dropins(&path)?,
                main_pid: if socket {
                    None
                } else {
                    Some(self.uint(&path, kind, c"MainPID")?)
                },
                user: if socket {
                    None
                } else {
                    Some(self.string(&path, kind, c"User")?)
                },
                group: if socket {
                    None
                } else {
                    Some(self.string(&path, kind, c"Group")?)
                },
            });
        }
        if manager != self.manager_identity()? {
            return Err(HostAdmissionError::Changed);
        }
        self.library.revalidate()?;
        let value = SssdSystemObservation {
            manager_pid: manager.0,
            manager_euid: manager.1,
            units,
        };
        validate_sssd_system(&value)?;
        Ok(value)
    }
}

fn owned_trusted(metadata: &Metadata) -> Result<()> {
    if metadata.uid() != 0 || metadata.mode() & 0o022 != 0 {
        return Err(reject("root-owned non-writable host input required"));
    }
    Ok(())
}
fn component(name: &str) -> Result<CString> {
    if name.is_empty() || name.contains('/') || matches!(name, "." | "..") {
        return Err(reject("invalid single path component"));
    }
    CString::new(name).map_err(|_| reject("NUL in path component"))
}
fn open_at(directory: &File, name: &str, flags: i32) -> io::Result<File> {
    let name = component(name).map_err(io::Error::other)?;
    // SAFETY: valid directory FD and one terminated component, no symlinks.
    let fd = unsafe {
        libc::openat(
            directory.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: a successful openat returned this new owned descriptor.
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn open_absolute(path: &str, flags: i32) -> Result<File> {
    let mut directory = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open("/")?;
    let parts: Vec<_> = Path::new(path).components().collect();
    if !matches!(parts.first(), Some(Component::RootDir)) || parts.len() < 2 {
        return Err(reject("fixed absolute host path required"));
    }
    for (index, part) in parts.iter().enumerate().skip(1) {
        let Component::Normal(name) = part else {
            return Err(reject("non-normal host path"));
        };
        let name = name.to_str().ok_or_else(|| reject("non-UTF8 host path"))?;
        owned_trusted(&directory.metadata()?)?;
        let last = index + 1 == parts.len();
        directory = open_at(
            &directory,
            name,
            if last {
                flags
            } else {
                libc::O_RDONLY | libc::O_DIRECTORY
            },
        )?;
    }
    Ok(directory)
}
fn read_bounded(file: &File, limit: usize) -> Result<Vec<u8>> {
    let mut value = Vec::new();
    file.take((limit + 1) as u64).read_to_end(&mut value)?;
    if value.len() > limit {
        return Err(reject("bounded input exceeded"));
    }
    Ok(value)
}
fn directory_names(file: &File, maximum: usize) -> Result<Vec<String>> {
    with_directory_names(file, maximum, |names, _iterator| Ok(names.to_vec()))
}
fn with_directory_names<T>(
    file: &File,
    maximum: usize,
    consume: impl FnOnce(&[String], RawFd) -> Result<T>,
) -> Result<T> {
    // Open a new file description rather than dup: fdopendir consumes its
    // directory offset and must not affect the caller's held description.
    // SAFETY: "." under this held descriptor cannot escape its directory.
    let fd = unsafe {
        libc::openat(
            file.as_raw_fd(),
            c".".as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    // SAFETY: fdopendir takes ownership of this fresh directory descriptor.
    let directory = unsafe { libc::fdopendir(fd) };
    if directory.is_null() {
        unsafe {
            libc::close(fd);
        }
        return Err(io::Error::last_os_error().into());
    }
    let result = (|| {
        let mut names = Vec::new();
        loop {
            unsafe {
                *libc::__errno_location() = 0;
            }
            let entry = unsafe { libc::readdir(directory) };
            if entry.is_null() {
                if unsafe { *libc::__errno_location() } != 0 {
                    return Err(io::Error::last_os_error().into());
                }
                break;
            }
            let name = unsafe { CStr::from_ptr((*entry).d_name.as_ptr()) }
                .to_str()
                .map_err(|_| reject("non-text directory name"))?;
            if matches!(name, "." | "..") {
                continue;
            }
            if names.len() == maximum {
                return Err(reject("directory entry bound exceeded"));
            }
            names.push(name.to_owned());
        }
        names.sort();
        if names.windows(2).any(|v| v[0] == v[1]) {
            return Err(HostAdmissionError::Changed);
        }
        // Keep the iterator descriptor alive while the caller examines the
        // names. During a self FD-table audit its own numeric entry remains
        // real, so no guessed descriptor exclusion is necessary.
        consume(&names, fd)
    })();
    let closed = unsafe { libc::closedir(directory) };
    if closed != 0 {
        return Err(io::Error::last_os_error().into());
    }
    result
}
fn stat_at(directory: &File, name: &str) -> Result<Metadata> {
    let file = open_at(directory, name, libc::O_PATH)?;
    Ok(file.metadata()?)
}
fn static_file(path: &str) -> Result<(String, Seal)> {
    let file = open_absolute(path, libc::O_RDONLY)?;
    let before = file.metadata()?;
    owned_trusted(&before)?;
    if !before.is_file() || before.nlink() != 1 || before.len() > FILE_LIMIT as u64 {
        return Err(reject("invalid public authority file"));
    }
    let bytes = read_bounded(&file, FILE_LIMIT)?;
    let again = open_absolute(path, libc::O_RDONLY)?;
    if Node::of(&before) != Node::of(&file.metadata()?)
        || Node::of(&before) != Node::of(&again.metadata()?)
        || bytes.len() as u64 != before.len()
    {
        return Err(HostAdmissionError::Changed);
    }
    let text = String::from_utf8(bytes.clone()).map_err(|_| reject("non-text public authority"))?;
    Ok((
        text,
        Seal {
            path: path.to_owned(),
            node: Some(Node::of(&before)),
            sha256: Some(format!("{:x}", Sha256::digest(&bytes))),
            entries: Vec::new(),
        },
    ))
}
fn empty_or_absent_directory(path: &str, allowed: &[&str]) -> Result<Seal> {
    let file = match open_absolute(path, libc::O_RDONLY | libc::O_DIRECTORY) {
        Ok(file) => file,
        Err(HostAdmissionError::Io(error)) if error.kind() == io::ErrorKind::NotFound => {
            return Ok(Seal {
                path: path.into(),
                node: None,
                sha256: None,
                entries: Vec::new(),
            });
        }
        Err(error) => return Err(error),
    };
    let before = Node::of(&file.metadata()?);
    owned_trusted(&file.metadata()?)?;
    let names = directory_names(&file, 256)?;
    if names.iter().any(|name| !allowed.contains(&name.as_str())) {
        return Err(reject(format!(
            "unsupported nonempty provider directory: {path}"
        )));
    }
    let mut entries = Vec::new();
    for name in names {
        let meta = stat_at(&file, &name)?;
        owned_trusted(&meta)?;
        if !meta.is_dir() {
            return Err(reject("provider metadata child is not a directory"));
        }
        entries.push((name, Node::of(&meta)));
    }
    if before != Node::of(&file.metadata()?) {
        return Err(HostAdmissionError::Changed);
    }
    Ok(Seal {
        path: path.into(),
        node: Some(before),
        sha256: None,
        entries,
    })
}
fn absent_file(path: &str) -> Result<Seal> {
    match open_absolute(path, libc::O_PATH) {
        Err(HostAdmissionError::Io(error)) if error.kind() == io::ErrorKind::NotFound => Ok(Seal {
            path: path.into(),
            node: None,
            sha256: None,
            entries: Vec::new(),
        }),
        Ok(_) => Err(reject(format!(
            "configured SSSD is not supported by this admission: {path}"
        ))),
        Err(error) => Err(error),
    }
}
fn provider_directory() -> Result<(File, Seal)> {
    let directory = open_absolute(USERDB, libc::O_RDONLY | libc::O_DIRECTORY)?;
    owned_trusted(&directory.metadata()?)?;
    let before = Node::of(&directory.metadata()?);
    let names = directory_names(&directory, 32)?;
    let mut entries = Vec::new();
    for name in names {
        if !matches!(
            name.as_str(),
            "io.systemd.DynamicUser" | "org.gnome.DisplayManager"
        ) {
            return Err(reject("unknown userdb provider socket"));
        }
        let metadata = stat_at(&directory, &name)?;
        if metadata.mode() & libc::S_IFMT != libc::S_IFSOCK
            || metadata.uid() != 0
            || metadata.nlink() != 1
        {
            return Err(reject("userdb provider socket custody changed"));
        }
        entries.push((name, Node::of(&metadata)));
    }
    if entries.is_empty() {
        return Err(reject("no supported systemd userdb providers"));
    }
    if before != Node::of(&directory.metadata()?) {
        return Err(HostAdmissionError::Changed);
    }
    Ok((
        directory,
        Seal {
            path: USERDB.into(),
            node: Some(before),
            sha256: None,
            entries,
        },
    ))
}
fn nss_grammar(text: &str) -> Result<()> {
    let mut found = BTreeMap::new();
    for line in text.lines() {
        let line = line.split('#').next().unwrap_or_default().trim();
        if line.is_empty() {
            continue;
        }
        let (name, rest) = line
            .split_once(':')
            .ok_or_else(|| reject("unknown nsswitch grammar"))?;
        if matches!(name.trim(), "passwd" | "group") {
            let names: Vec<_> = rest.split_whitespace().collect();
            if names != ["files", "systemd", "sss"] || found.insert(name.trim(), ()).is_some() {
                return Err(reject(
                    "unsupported passwd/group NSS provider order or action",
                ));
            }
        }
    }
    if found.len() != 2 {
        return Err(reject("missing passwd/group NSS database"));
    }
    Ok(())
}
fn name(value: &str) -> Result<String> {
    if value.is_empty()
        || value.len() > 256
        || value.bytes().any(|b| {
            b.is_ascii_control() || b == b':' || b == b'/' || b == b'\\' || b.is_ascii_whitespace()
        })
    {
        return Err(reject("invalid public identity name"));
    }
    Ok(value.to_owned())
}
fn number(value: &str) -> Result<u32> {
    if value.is_empty() || !value.bytes().all(|b| b.is_ascii_digit()) {
        return Err(reject("invalid public identity number"));
    }
    let result = value
        .parse::<u32>()
        .map_err(|_| reject("identity number overflow"))?;
    if result == u32::MAX {
        return Err(reject("reserved uid_t/gid_t sentinel"));
    }
    Ok(result)
}
fn public_files(passwd: &str, group: &str) -> Result<(Vec<PublicUser>, Vec<PublicGroup>)> {
    let mut users = Vec::new();
    for line in passwd.lines().filter(|line| !line.is_empty()) {
        let fields: Vec<_> = line.split(':').collect();
        if fields.len() != 7 || users.len() == RECORD_LIMIT {
            return Err(reject("unsupported passwd record"));
        }
        users.push(PublicUser {
            name: name(fields[0])?,
            uid: number(fields[2])?,
            gid: number(fields[3])?,
        });
    }
    let mut groups = Vec::new();
    for line in group.lines().filter(|line| !line.is_empty()) {
        let fields: Vec<_> = line.split(':').collect();
        if fields.len() != 4 || groups.len() == RECORD_LIMIT {
            return Err(reject("unsupported group record"));
        }
        let mut members: Vec<_> = if fields[3].is_empty() {
            Vec::new()
        } else {
            fields[3].split(',').map(name).collect::<Result<_>>()?
        };
        members.sort();
        if members.windows(2).any(|m| m[0] == m[1]) {
            return Err(reject("duplicate group membership"));
        }
        groups.push(PublicGroup {
            name: name(fields[0])?,
            gid: number(fields[2])?,
            members,
        });
    }
    Ok((users, groups))
}
impl HostInputs {
    fn capture() -> Result<Self> {
        let (nss, nss_seal) = static_file("/etc/nsswitch.conf")?;
        nss_grammar(&nss)?;
        let (passwd, passwd_seal) = static_file("/etc/passwd")?;
        let (group, group_seal) = static_file("/etc/group")?;
        let (users, groups) = public_files(&passwd, &group)?;
        let mut seals = vec![nss_seal, passwd_seal, group_seal];
        // Keep config root-owned and absent/empty. Only fixed runtime state
        // directories use the unique noninteractive package service identity.
        seals.push(absent_file("/etc/sssd/sssd.conf")?);
        seals.push(empty_or_absent_directory("/etc/sssd/conf.d", &[])?);
        let sssd = InactiveSssd::capture(&passwd, &users, &groups)?;
        for &(unit, bytes, digest) in SSSD_UNITS {
            let path = format!("/usr/lib/systemd/system/{unit}");
            let (text, seal) = static_file(&path)?;
            if text.len() != bytes || seal.sha256.as_deref() != Some(digest) {
                return Err(reject("SSSD package condition/unit source changed"));
            }
            seals.push(seal);
        }
        let (_, library) = trusted_systemd_library()?;
        seals.push(library);
        seals.push(system_bus_seal()?);
        for path in [
            "/etc/userdb",
            "/run/userdb",
            "/run/host/userdb",
            "/usr/lib/userdb",
        ] {
            seals.push(empty_or_absent_directory(path, &[])?);
        }
        let (_, providers) = provider_directory()?;
        let services = providers.entries.iter().map(|(n, _)| n.clone()).collect();
        seals.push(providers);
        Ok(Self {
            seals,
            users,
            groups,
            services,
            sssd,
        })
    }
}

fn buffer_text(pointer: *const libc::c_char, buffer: &[u8]) -> Result<String> {
    let start = buffer.as_ptr() as usize;
    let address = pointer as usize;
    let end = start
        .checked_add(buffer.len())
        .ok_or_else(|| reject("NSS buffer overflow"))?;
    if address < start || address >= end {
        return Err(reject("NSS string is outside its returned buffer"));
    }
    let tail = &buffer[address - start..];
    let length = tail
        .iter()
        .position(|b| *b == 0)
        .ok_or_else(|| reject("unterminated NSS string"))?;
    let text = std::str::from_utf8(&tail[..length]).map_err(|_| reject("non-UTF8 NSS name"))?;
    name(text)
}
fn enumerate_nss_users() -> Result<Vec<PublicUser>> {
    unsafe {
        libc::setpwent();
    }
    let result = (|| {
        let mut users = Vec::new();
        let mut buffer = vec![0_u8; 16384];
        loop {
            let mut row: libc::passwd = unsafe { mem::zeroed() };
            let mut actual = std::ptr::null_mut();
            let code = unsafe {
                libc::getpwent_r(
                    &mut row,
                    buffer.as_mut_ptr().cast(),
                    buffer.len(),
                    &mut actual,
                )
            };
            if code == libc::ERANGE && buffer.len() < FILE_LIMIT {
                buffer.resize((buffer.len() * 2).min(FILE_LIMIT), 0);
                continue;
            }
            if actual.is_null() && matches!(code, 0 | libc::ENOENT) {
                break;
            }
            if code != 0 || actual.is_null() || users.len() == RECORD_LIMIT {
                return Err(reject("NSS passwd enumeration did not complete"));
            }
            if row.pw_uid == u32::MAX || row.pw_gid == u32::MAX {
                return Err(reject("NSS returned sentinel ID"));
            }
            users.push(PublicUser {
                name: buffer_text(row.pw_name, &buffer)?,
                uid: row.pw_uid,
                gid: row.pw_gid,
            });
            // No password, GECOS, home or shell field is copied to the output.
            buffer.fill(0);
        }
        Ok(users)
    })();
    unsafe {
        libc::endpwent();
    }
    result
}
fn enumerate_nss_groups() -> Result<Vec<PublicGroup>> {
    unsafe {
        libc::setgrent();
    }
    let result = (|| {
        let mut groups = Vec::new();
        let mut buffer = vec![0_u8; 16384];
        loop {
            let mut row: libc::group = unsafe { mem::zeroed() };
            let mut actual = std::ptr::null_mut();
            let code = unsafe {
                libc::getgrent_r(
                    &mut row,
                    buffer.as_mut_ptr().cast(),
                    buffer.len(),
                    &mut actual,
                )
            };
            if code == libc::ERANGE && buffer.len() < FILE_LIMIT {
                buffer.resize((buffer.len() * 2).min(FILE_LIMIT), 0);
                continue;
            }
            if actual.is_null() && matches!(code, 0 | libc::ENOENT) {
                break;
            }
            if code != 0 || actual.is_null() || groups.len() == RECORD_LIMIT {
                return Err(reject("NSS group enumeration did not complete"));
            }
            if row.gr_gid == u32::MAX {
                return Err(reject("NSS group sentinel ID"));
            }
            let mut members = Vec::new();
            if !row.gr_mem.is_null() {
                let start = buffer.as_ptr() as usize;
                let end = start + buffer.len();
                let mut address = row.gr_mem as usize;
                loop {
                    if address < start
                        || address
                            .checked_add(mem::size_of::<*const libc::c_char>())
                            .is_none_or(|v| v > end)
                    {
                        return Err(reject("NSS member array is outside its returned buffer"));
                    }
                    let pointer =
                        unsafe { std::ptr::read_unaligned(address as *const *const libc::c_char) };
                    if pointer.is_null() {
                        break;
                    }
                    if members.len() == RECORD_LIMIT {
                        return Err(reject("NSS member count exceeded"));
                    }
                    members.push(buffer_text(pointer, &buffer)?);
                    address += mem::size_of::<*const libc::c_char>();
                }
            }
            members.sort();
            if members.windows(2).any(|v| v[0] == v[1]) {
                return Err(reject("duplicate NSS group member"));
            }
            groups.push(PublicGroup {
                name: buffer_text(row.gr_name, &buffer)?,
                gid: row.gr_gid,
                members,
            });
            buffer.fill(0);
        }
        Ok(groups)
    })();
    unsafe {
        libc::endgrent();
    }
    result
}

struct UniqueValue(serde_json::Value);
impl<'de> Deserialize<'de> for UniqueValue {
    fn deserialize<D: serde::Deserializer<'de>>(
        deserializer: D,
    ) -> std::result::Result<Self, D::Error> {
        struct UniqueVisitor;
        impl<'de> serde::de::Visitor<'de> for UniqueVisitor {
            type Value = UniqueValue;
            fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                f.write_str("unambiguous JSON")
            }
            fn visit_bool<E: serde::de::Error>(
                self,
                v: bool,
            ) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(v.into()))
            }
            fn visit_i64<E: serde::de::Error>(self, v: i64) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(v.into()))
            }
            fn visit_u64<E: serde::de::Error>(self, v: u64) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(v.into()))
            }
            fn visit_f64<E: serde::de::Error>(self, v: f64) -> std::result::Result<Self::Value, E> {
                serde_json::Number::from_f64(v)
                    .map(|n| UniqueValue(n.into()))
                    .ok_or_else(|| E::custom("nonfinite JSON"))
            }
            fn visit_str<E: serde::de::Error>(
                self,
                v: &str,
            ) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(v.into()))
            }
            fn visit_string<E: serde::de::Error>(
                self,
                v: String,
            ) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(v.into()))
            }
            fn visit_unit<E: serde::de::Error>(self) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(serde_json::Value::Null))
            }
            fn visit_none<E: serde::de::Error>(self) -> std::result::Result<Self::Value, E> {
                self.visit_unit()
            }
            fn visit_seq<A: serde::de::SeqAccess<'de>>(
                self,
                mut seq: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut values = Vec::new();
                while let Some(value) = seq.next_element::<UniqueValue>()? {
                    if values.len() == RECORD_LIMIT {
                        return Err(serde::de::Error::custom("JSON array count"));
                    }
                    values.push(value.0);
                }
                Ok(UniqueValue(values.into()))
            }
            fn visit_map<A: serde::de::MapAccess<'de>>(
                self,
                mut map: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut values = serde_json::Map::new();
                while let Some(key) = map.next_key::<String>()? {
                    if values.contains_key(&key) {
                        return Err(serde::de::Error::custom("duplicate JSON key"));
                    }
                    let value = map.next_value::<UniqueValue>()?;
                    values.insert(key, value.0);
                    if values.len() > 4096 {
                        return Err(serde::de::Error::custom("JSON object count"));
                    }
                }
                Ok(UniqueValue(values.into()))
            }
        }
        deserializer.deserialize_any(UniqueVisitor)
    }
}
fn json_name(value: &serde_json::Value, key: &str) -> Result<String> {
    name(
        value
            .get(key)
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| reject("missing public record name"))?,
    )
}
fn json_id(value: &serde_json::Value, key: &str) -> Result<u32> {
    value
        .get(key)
        .and_then(serde_json::Value::as_u64)
        .filter(|v| *v < u64::from(u32::MAX))
        .map(|v| v as u32)
        .ok_or_else(|| reject("missing or invalid public record ID"))
}
fn reply_frame(bytes: &[u8], rows_seen: usize) -> Result<(Option<serde_json::Value>, bool)> {
    let value = serde_json::from_slice::<UniqueValue>(bytes)
        .map_err(|_| reject("malformed or duplicate-key userdb JSON"))?
        .0;
    let object = value
        .as_object()
        .ok_or_else(|| reject("userdb response is not an object"))?;
    if object
        .keys()
        .any(|k| !matches!(k.as_str(), "parameters" | "continues" | "error"))
    {
        return Err(reject("unknown userdb envelope field"));
    }
    let more = match value.get("continues") {
        None => false,
        Some(serde_json::Value::Bool(v)) => *v,
        _ => return Err(reject("invalid userdb continuation flag")),
    };
    if let Some(error) = value.get("error") {
        if error.as_str() == Some("io.systemd.UserDatabase.NoRecordFound")
            && !more
            && rows_seen == 0
            && !object.contains_key("parameters")
        {
            return Ok((None, false));
        }
        return Err(reject("userdb enumeration returned an error"));
    }
    let parameters = value
        .get("parameters")
        .and_then(serde_json::Value::as_object)
        .ok_or_else(|| reject("missing userdb parameters"))?;
    Ok((Some(serde_json::Value::Object(parameters.clone())), more))
}
fn query_provider(service: &str, method: &str, expected: &Node) -> Result<Vec<serde_json::Value>> {
    let (directory, _) = provider_directory()?;
    if Node::of(&stat_at(&directory, service)?) != *expected {
        return Err(HostAdmissionError::Changed);
    }
    let mut stream = UnixStream::connect(Path::new(USERDB).join(service))?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
    let mut peer: libc::ucred = unsafe { mem::zeroed() };
    let mut length = mem::size_of_val(&peer) as libc::socklen_t;
    let status = unsafe {
        libc::getsockopt(
            stream.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut peer as *mut libc::ucred).cast(),
            &mut length,
        )
    };
    if status != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if length as usize != mem::size_of_val(&peer) || peer.uid != 0 || peer.pid <= 0 {
        return Err(reject("userdb socket peer is not its root service"));
    }
    let request = serde_json::json!({"method":format!("io.systemd.UserDatabase.{method}"),
        "parameters":{"service":service},"more":true});
    let mut request =
        serde_json::to_vec(&request).map_err(|_| reject("userdb request encoding"))?;
    request.push(0);
    stream.write_all(&request)?;
    let mut pending = Vec::new();
    let mut rows = Vec::new();
    let mut total = 0;
    let end = Instant::now() + Duration::from_secs(8);
    loop {
        if Instant::now() >= end {
            return Err(reject("userdb enumeration deadline"));
        }
        let mut block = [0_u8; 4096];
        let count = stream.read(&mut block)?;
        if count == 0 {
            return Err(reject("userdb EOF before terminal response"));
        }
        total += count;
        if total > OUTPUT_LIMIT {
            return Err(reject("userdb response bound"));
        }
        pending.extend_from_slice(&block[..count]);
        loop {
            let Some(at) = pending.iter().position(|v| *v == 0) else {
                break;
            };
            if at == 0 || at > FILE_LIMIT {
                return Err(reject("invalid userdb frame size"));
            }
            let (parameters, more) = reply_frame(&pending[..at], rows.len())?;
            pending.drain(..=at);
            if let Some(parameters) = parameters {
                if rows.len() == RECORD_LIMIT {
                    return Err(reject("userdb record count"));
                }
                rows.push(parameters);
            }
            if !more {
                if !pending.is_empty() {
                    return Err(reject("userdb trailing response after terminal"));
                }
                if Node::of(&stat_at(&directory, service)?) != *expected {
                    return Err(HostAdmissionError::Changed);
                }
                return Ok(rows);
            }
        }
        if pending.len() > FILE_LIMIT {
            return Err(reject("unterminated userdb frame bound"));
        }
    }
}
fn public_record(parameters: &serde_json::Value) -> Result<&serde_json::Value> {
    if parameters.as_object().is_none_or(|m| {
        m.keys()
            .any(|k| !matches!(k.as_str(), "record" | "incomplete"))
    }) || !parameters
        .get("incomplete")
        .is_some_and(serde_json::Value::is_boolean)
    {
        return Err(reject("invalid userdb record envelope"));
    }
    let record = parameters
        .get("record")
        .filter(|v| v.is_object())
        .ok_or_else(|| reject("missing userdb record"))?;
    // Redacted privileged sections do not imply partial public enumeration.
    // No privileged/secret section is serialized or copied into observations.
    if record.get("realm").is_some_and(|v| v.as_str() != Some("")) {
        return Err(reject("realm-qualified userdb records are unsupported"));
    }
    Ok(record)
}
fn provider_records(service: &str, node: &Node) -> Result<ProviderRecords> {
    let mut users = Vec::new();
    for parameters in query_provider(service, "GetUserRecord", node)? {
        let record = public_record(&parameters)?;
        users.push(PublicUser {
            name: json_name(record, "userName")?,
            uid: json_id(record, "uid")?,
            gid: json_id(record, "gid")?,
        });
    }
    let mut groups = Vec::new();
    for parameters in query_provider(service, "GetGroupRecord", node)? {
        let record = public_record(&parameters)?;
        let mut members = Vec::new();
        if let Some(value) = record.get("members") {
            let values = value
                .as_array()
                .ok_or_else(|| reject("invalid public group members"))?;
            if values.len() > RECORD_LIMIT {
                return Err(reject("member count"));
            }
            for value in values {
                members.push(name(
                    value
                        .as_str()
                        .ok_or_else(|| reject("non-name group member"))?,
                )?);
            }
        }
        members.sort();
        if members.windows(2).any(|m| m[0] == m[1]) {
            return Err(reject("duplicate userdb group member"));
        }
        groups.push(PublicGroup {
            name: json_name(record, "groupName")?,
            gid: json_id(record, "gid")?,
            members,
        });
    }
    let mut memberships = Vec::new();
    for parameters in query_provider(service, "GetMemberships", node)? {
        if parameters.as_object().is_none_or(|m| {
            m.len() != 2 || !m.contains_key("userName") || !m.contains_key("groupName")
        }) {
            return Err(reject("invalid complete membership record"));
        }
        memberships.push(Membership {
            user: json_name(&parameters, "userName")?,
            group: json_name(&parameters, "groupName")?,
        });
    }
    memberships.sort();
    if memberships.windows(2).any(|m| m[0] == m[1]) {
        return Err(reject("duplicate userdb membership"));
    }
    Ok(ProviderRecords {
        service: service.into(),
        users,
        groups,
        memberships,
    })
}

/// Internal executable dispatch for public NSS observation only.
///
/// It accepts no path, identity, PID, range or authority input. Both production
/// binaries must dispatch this exact entry before their normal CLI parsing.
///
/// # Errors
///
/// Wrong credentials, inherited supplementary groups, missing no-new-privileges,
/// any incomplete enumeration or an unsupported provider rejects the worker.
#[doc(hidden)]
pub fn run_nss_observation_worker() -> Result<()> {
    let mut real = 0;
    let mut effective = 0;
    let mut saved = 0;
    if unsafe { libc::getresuid(&mut real, &mut effective, &mut saved) } != 0
        || [real, effective, saved] != [65534; 3]
    {
        return Err(reject("NSS worker requires all three unprivileged UIDs"));
    }
    if unsafe { libc::getresgid(&mut real, &mut effective, &mut saved) } != 0
        || [real, effective, saved] != [65534; 3]
        || unsafe { libc::getgroups(0, std::ptr::null_mut()) } != 0
        || unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) } != 1
    {
        return Err(reject(
            "NSS worker credential or no-new-privileges boundary",
        ));
    }
    let mut worker_filter = no_children_filter(true);
    let worker_program = libc::sock_fprog {
        len: worker_filter.len() as u16,
        filter: worker_filter.as_mut_ptr(),
    };
    if unsafe {
        libc::prctl(
            libc::PR_SET_SECCOMP,
            2,
            &worker_program as *const libc::sock_fprog,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    worker_signal_state()?;
    let (_, before) = provider_directory()?;
    let bus_before = system_bus_seal()?;
    let systemd = PublicSystemdBus::open()?;
    let sssd = systemd.observe()?;
    let nss_users = enumerate_nss_users()?;
    let nss_groups = enumerate_nss_groups()?;
    let mut providers = Vec::new();
    for (service, node) in &before.entries {
        providers.push(provider_records(service, node)?);
    }
    let (_, after) = provider_directory()?;
    if before != after || bus_before != system_bus_seal()? || sssd != systemd.observe()? {
        return Err(HostAdmissionError::Changed);
    }
    let observation = PublicObservation {
        schema: 2,
        nss_users,
        nss_groups,
        providers,
        sssd,
    };
    let bytes =
        serde_json::to_vec(&observation).map_err(|_| reject("public NSS observation encoding"))?;
    if bytes.len() > OUTPUT_LIMIT {
        return Err(reject("public NSS observation size"));
    }
    io::stdout().lock().write_all(&bytes)?;
    Ok(())
}

fn in_range(value: u32, range: IdRange) -> bool {
    u64::from(value) >= u64::from(range.start)
        && u64::from(value) < u64::from(range.start) + u64::from(range.count)
}
fn validate_range(range: IdRange) -> Result<()> {
    if range.count == 0 || u64::from(range.start) + u64::from(range.count) > u64::from(u32::MAX) {
        return Err(reject("invalid held subordinate range"));
    }
    Ok(())
}
fn public_observation_coverage(inputs: &HostInputs, observed: &PublicObservation) -> Result<()> {
    sssd_public_coverage(inputs, observed)?;
    if observed.schema != 2
        || observed.nss_users.len() > RECORD_LIMIT
        || observed.nss_groups.len() > RECORD_LIMIT
        || observed
            .providers
            .iter()
            .map(|p| p.service.clone())
            .collect::<Vec<_>>()
            != inputs.services
    {
        return Err(reject("NSS observation schema or provider set"));
    }
    for user in &inputs.users {
        if !observed.nss_users.contains(user) {
            return Err(reject("NSS omitted an authoritative files user"));
        }
    }
    for group in &inputs.groups {
        if !observed.nss_groups.contains(group) {
            return Err(reject("NSS omitted an authoritative files group"));
        }
    }
    Ok(())
}

fn validate_public_identities(
    inputs: &HostInputs,
    observed: &PublicObservation,
    principal: &str,
    uid: u32,
    gid: u32,
    uids: IdRange,
    gids: IdRange,
) -> Result<()> {
    validate_range(uids)?;
    validate_range(gids)?;
    public_observation_coverage(inputs, observed)?;
    let mut user_by_name = BTreeMap::new();
    let mut user_by_id = BTreeMap::new();
    for user in observed
        .nss_users
        .iter()
        .chain(observed.providers.iter().flat_map(|p| &p.users))
    {
        name(&user.name)?;
        if user.uid == u32::MAX
            || user.gid == u32::MAX
            || in_range(user.uid, uids)
            || in_range(user.gid, gids)
        {
            return Err(reject("subordinate identity is already supplied by NSS"));
        }
        if user_by_name
            .insert(user.name.clone(), (user.uid, user.gid))
            .is_some_and(|old| old != (user.uid, user.gid))
            || user_by_id
                .insert(user.uid, user.name.clone())
                .is_some_and(|old| old != user.name)
        {
            return Err(reject("ambiguous NSS user name or UID"));
        }
        if (user.uid == uid || user.name == principal || user.gid == gid)
            && (user.name != principal || user.uid != uid || user.gid != gid)
        {
            return Err(reject("dedicated principal or its primary GID is shared"));
        }
    }
    if user_by_name.get(principal) != Some(&(uid, gid)) {
        return Err(reject(
            "held principal is absent from complete NSS enumeration",
        ));
    }
    let mut group_by_name = BTreeMap::new();
    let mut group_by_id = BTreeMap::new();
    for group in observed
        .nss_groups
        .iter()
        .chain(observed.providers.iter().flat_map(|p| &p.groups))
    {
        name(&group.name)?;
        if group.gid == u32::MAX || in_range(group.gid, gids) {
            return Err(reject("subordinate GID is already supplied by NSS"));
        }
        if group_by_name
            .insert(group.name.clone(), group.gid)
            .is_some_and(|old| old != group.gid)
            || group_by_id
                .insert(group.gid, group.name.clone())
                .is_some_and(|old| old != group.name)
        {
            return Err(reject("ambiguous NSS group name or GID"));
        }
        if (group.gid == gid || group.name == principal)
            && (group.gid != gid || group.name != principal || !group.members.is_empty())
        {
            return Err(reject("dedicated primary group is shared"));
        }
        if group.members.iter().any(|member| member == principal) {
            return Err(reject(
                "dedicated principal has an explicit host group membership",
            ));
        }
    }
    if group_by_name.get(principal) != Some(&gid) {
        return Err(reject("dedicated NSS group absent"));
    }
    for provider in &observed.providers {
        if provider
            .users
            .iter()
            .any(|u| u.name == principal || u.uid == uid || u.gid == gid)
            || provider
                .groups
                .iter()
                .any(|g| g.name == principal || g.gid == gid)
        {
            return Err(reject(
                "dynamic provider shadows the files-only dedicated principal",
            ));
        }
        if provider.users.len() > RECORD_LIMIT
            || provider.groups.len() > RECORD_LIMIT
            || provider.memberships.len() > RECORD_LIMIT
        {
            return Err(reject("provider observation count"));
        }
        for membership in &provider.memberships {
            name(&membership.user)?;
            name(&membership.group)?;
            if membership.user == principal || membership.group == principal {
                return Err(reject(
                    "dynamic membership overlaps the dedicated principal",
                ));
            }
        }
    }
    Ok(())
}

fn canonical_observation(mut observation: PublicObservation) -> Result<PublicObservation> {
    fn users(rows: &mut [PublicUser]) -> Result<()> {
        rows.sort_by(|a, b| (&a.name, a.uid, a.gid).cmp(&(&b.name, b.uid, b.gid)));
        if rows.windows(2).any(|v| v[0] == v[1]) {
            return Err(reject("duplicate public user record"));
        }
        Ok(())
    }
    fn groups(rows: &mut [PublicGroup]) -> Result<()> {
        for row in &mut *rows {
            row.members.sort();
            if row.members.windows(2).any(|v| v[0] == v[1]) {
                return Err(reject("duplicate public member record"));
            }
        }
        rows.sort_by(|a, b| (&a.name, a.gid, &a.members).cmp(&(&b.name, b.gid, &b.members)));
        if rows.windows(2).any(|v| v[0] == v[1]) {
            return Err(reject("duplicate public group record"));
        }
        Ok(())
    }
    observation.sssd.units.sort_by(|a, b| a.unit.cmp(&b.unit));
    validate_sssd_system(&observation.sssd)?;
    users(&mut observation.nss_users)?;
    groups(&mut observation.nss_groups)?;
    for provider in &mut observation.providers {
        users(&mut provider.users)?;
        groups(&mut provider.groups)?;
        provider.memberships.sort();
        if provider.memberships.windows(2).any(|v| v[0] == v[1]) {
            return Err(reject("duplicate public membership record"));
        }
    }
    observation
        .providers
        .sort_by(|a, b| a.service.cmp(&b.service));
    if observation
        .providers
        .windows(2)
        .any(|v| v[0].service == v[1].service)
    {
        return Err(reject("duplicate public provider observation"));
    }
    Ok(observation)
}

#[repr(C)]
#[derive(Default)]
struct CloneArgs {
    flags: u64,
    pidfd: u64,
    child_tid: u64,
    parent_tid: u64,
    exit_signal: u64,
    stack: u64,
    stack_size: u64,
    tls: u64,
    set_tid: u64,
    set_tid_size: u64,
    cgroup: u64,
}
fn above_stdio(file: File) -> Result<File> {
    if file.as_raw_fd() >= 3 {
        return Ok(file);
    }
    let raw = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 3) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}
fn pipe() -> Result<(File, File)> {
    let mut fds = [-1; 2];
    if unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_CLOEXEC) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let read = unsafe { File::from_raw_fd(fds[0]) };
    let write = unsafe { File::from_raw_fd(fds[1]) };
    let read = above_stdio(read)?;
    let write = above_stdio(write)?;
    if unsafe { libc::fcntl(read.as_raw_fd(), libc::F_SETFL, libc::O_NONBLOCK) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok((read, write))
}
fn self_executable() -> Result<(File, Node, String)> {
    // The single proc magic link is opened deliberately, binding the binary
    // already executing this admission rather than trusting an argv path.
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NONBLOCK)
        .open("/proc/self/exe")?;
    let before = file.metadata()?;
    owned_trusted(&before)?;
    if !before.is_file()
        || before.nlink() != 1
        || before.mode() & 0o6000 != 0
        || before.mode() & 0o001 == 0
        || before.len() == 0
        || before.len() > 128 * 1024 * 1024
    {
        return Err(reject("worker requires the root-sealed running executable"));
    }
    let capabilities = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.capability".as_ptr(),
            std::ptr::null_mut(),
            0,
        )
    };
    if capabilities >= 0 || io::Error::last_os_error().raw_os_error() != Some(libc::ENODATA) {
        return Err(reject(
            "worker executable has file capabilities or unreadable metadata",
        ));
    }
    let mut hash = Sha256::new();
    let mut reader = &file;
    let mut total = 0_u64;
    loop {
        let mut buffer = [0_u8; 65536];
        let count = reader.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        total += count as u64;
        if total > before.len() {
            return Err(HostAdmissionError::Changed);
        }
        hash.update(&buffer[..count]);
    }
    let again = File::open("/proc/self/exe")?;
    if total != before.len()
        || Node::of(&before) != Node::of(&file.metadata()?)
        || Node::of(&before) != Node::of(&again.metadata()?)
    {
        return Err(HostAdmissionError::Changed);
    }
    Ok((file, Node::of(&before), format!("{:x}", hash.finalize())))
}
fn no_children_filter(deny_exec: bool) -> Vec<libc::sock_filter> {
    // Native x86_64 is the supported Pocket4 host ABI. Refuse x32 and foreign
    // syscall ABIs rather than allowing their fork/exec numbers through.
    let mut filter = vec![
        libc::sock_filter {
            code: 0x20,
            jt: 0,
            jf: 0,
            k: 4,
        },
        libc::sock_filter {
            code: 0x15,
            jt: 1,
            jf: 0,
            k: 0xc000_003e,
        },
        libc::sock_filter {
            code: 0x06,
            jt: 0,
            jf: 0,
            k: 0x8000_0000,
        },
        libc::sock_filter {
            code: 0x20,
            jt: 0,
            jf: 0,
            k: 0,
        },
        libc::sock_filter {
            code: 0x35,
            jt: 0,
            jf: 1,
            k: 0x4000_0000,
        },
        libc::sock_filter {
            code: 0x06,
            jt: 0,
            jf: 0,
            k: 0x0005_0000 | libc::EPERM as u32,
        },
    ];
    for syscall in [
        libc::SYS_clone,
        libc::SYS_clone3,
        libc::SYS_fork,
        libc::SYS_vfork,
    ]
    .into_iter()
    .chain(if deny_exec {
        vec![libc::SYS_execve, libc::SYS_execveat]
    } else {
        Vec::new()
    }) {
        filter.push(libc::sock_filter {
            code: 0x15,
            jt: 0,
            jf: 1,
            k: syscall as u32,
        });
        filter.push(libc::sock_filter {
            code: 0x06,
            jt: 0,
            jf: 0,
            k: 0x0005_0000 | libc::EPERM as u32,
        });
    }
    filter.push(libc::sock_filter {
        code: 0x06,
        jt: 0,
        jf: 0,
        k: 0x7fff_0000,
    });
    filter
}
unsafe fn child_exit() -> ! {
    unsafe {
        libc::_exit(125);
    }
}
unsafe fn worker_child(
    parent: libc::pid_t,
    executable: RawFd,
    input: RawFd,
    output: RawFd,
    error: RawFd,
    argv: *const *const libc::c_char,
    envp: *const *const libc::c_char,
    filter: &libc::sock_fprog,
) -> ! {
    // Only async-signal-safe syscalls after clone3; all strings and BPF storage
    // were allocated in the parent. There is no allocation, log or unwinding.
    unsafe {
        if libc::getppid() != parent
            || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0
            || libc::getppid() != parent
        {
            child_exit();
        }
        if libc::dup2(input, 0) != 0 || libc::dup2(output, 1) != 1 || libc::dup2(error, 2) != 2 {
            child_exit();
        }
        // Preserve descriptor usability for execveat while closing every
        // inherited registry, data and control descriptor at the exec boundary.
        if libc::syscall(libc::SYS_close_range, 3_u32, u32::MAX, 4_u32) != 0 {
            child_exit();
        } // CLOEXEC
        let limit = libc::rlimit {
            rlim_cur: 0,
            rlim_max: 0,
        };
        if libc::setrlimit(libc::RLIMIT_CORE, &limit) != 0
            || libc::setrlimit(libc::RLIMIT_FSIZE, &limit) != 0
        {
            child_exit();
        }
        let memory = libc::rlimit {
            rlim_cur: 256 * 1024 * 1024,
            rlim_max: 256 * 1024 * 1024,
        };
        let cpu = libc::rlimit {
            rlim_cur: 5,
            rlim_max: 5,
        };
        if libc::setrlimit(libc::RLIMIT_AS, &memory) != 0
            || libc::setrlimit(libc::RLIMIT_CPU, &cpu) != 0
        {
            child_exit();
        }
        let mut cap_header = CapHeader {
            version: 0x2008_0522,
            pid: 0,
        };
        let caps = [CapData {
            effective: 0,
            permitted: 0,
            inheritable: 0,
        }; 2];
        // Raw per-thread calls are required in this raw clone3 child.
        // Glibc NPTL setxid wrappers can synchronize inherited parent thread
        // state by signals; no parent-library synchronization runs here.
        if libc::syscall(
            libc::SYS_setgroups,
            0_usize,
            std::ptr::null::<libc::gid_t>(),
        ) != 0
            || libc::syscall(libc::SYS_setresgid, 65534_u32, 65534_u32, 65534_u32) != 0
            || libc::syscall(libc::SYS_setresuid, 65534_u32, 65534_u32, 65534_u32) != 0
            || libc::syscall(libc::SYS_capset, &mut cap_header, caps.as_ptr()) != 0
            || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0
            || libc::getppid() != parent
            || libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
        {
            child_exit();
        }
        // The parent blocked the kernel signal mask before clone3. Keep it
        // blocked through execveat so no inherited parent handler can run in
        // this async-signal-safe child window. The new image resets it.
        if libc::prctl(libc::PR_SET_SECCOMP, 2, filter as *const libc::sock_fprog) != 0 {
            child_exit();
        }
        libc::syscall(
            libc::SYS_execveat,
            executable,
            c"".as_ptr(),
            argv,
            envp,
            libc::AT_EMPTY_PATH,
        );
        child_exit()
    }
}
struct KernelSignalMask {
    original: u64,
    active: bool,
}
impl KernelSignalMask {
    fn block() -> Result<Self> {
        let all = u64::MAX;
        let mut original = 0_u64;
        if unsafe {
            libc::syscall(
                libc::SYS_rt_sigprocmask,
                libc::SIG_SETMASK,
                &all,
                &mut original,
                mem::size_of::<u64>(),
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        Ok(Self {
            original,
            active: true,
        })
    }
    fn restore(&mut self) -> Result<()> {
        if self.active {
            if unsafe {
                libc::syscall(
                    libc::SYS_rt_sigprocmask,
                    libc::SIG_SETMASK,
                    &self.original,
                    std::ptr::null_mut::<u64>(),
                    mem::size_of::<u64>(),
                )
            } != 0
            {
                return Err(io::Error::last_os_error().into());
            }
            self.active = false;
        }
        Ok(())
    }
}
impl Drop for KernelSignalMask {
    fn drop(&mut self) {
        let _ = self.restore();
    }
}
fn require_owned_wait_semantics() -> Result<()> {
    let mut action: libc::sigaction = unsafe { mem::zeroed() };
    if unsafe { libc::sigaction(libc::SIGCHLD, std::ptr::null(), &mut action) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if action.sa_sigaction != libc::SIG_DFL || action.sa_flags & libc::SA_NOCLDWAIT != 0 {
        return Err(reject(
            "NSS worker requires default, waitable SIGCHLD ownership",
        ));
    }
    Ok(())
}
fn worker_signal_state() -> Result<()> {
    // This runs only after the new image was entered, never in the fork child.
    // exec resets caught handlers; explicitly replace inherited ignored public
    // signals. glibc-reserved 32/33 cannot be changed with its sigaction API.
    for signal in 1..=64 {
        if matches!(signal, libc::SIGKILL | libc::SIGSTOP | 32 | 33) {
            continue;
        }
        let mut action: libc::sigaction = unsafe { mem::zeroed() };
        action.sa_sigaction = libc::SIG_DFL;
        if unsafe { libc::sigemptyset(&mut action.sa_mask) } != 0
            || unsafe { libc::sigaction(signal, &action, std::ptr::null_mut()) } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
    }
    let empty = 0_u64;
    if unsafe {
        libc::syscall(
            libc::SYS_rt_sigprocmask,
            libc::SIG_SETMASK,
            &empty,
            std::ptr::null_mut::<u64>(),
            mem::size_of::<u64>(),
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}
struct WorkerOwner<'a> {
    pid: libc::pid_t,
    pidfd: mem::ManuallyDrop<OwnedFd>,
    output: mem::ManuallyDrop<File>,
    error: mem::ManuallyDrop<File>,
    reaped: bool,
    terminal_status: Option<(i32, i32)>,
    quarantine: &'a Cell<bool>,
}
impl<'a> WorkerOwner<'a> {
    fn start(executable: &File, quarantine: &'a Cell<bool>) -> Result<Self> {
        #[cfg(not(target_arch = "x86_64"))]
        return Err(reject("unsupported NSS worker host ABI"));
        require_owned_wait_semantics()?;
        let executable_raw =
            unsafe { libc::fcntl(executable.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 3) };
        if executable_raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let executable = unsafe { File::from_raw_fd(executable_raw) };
        let input = above_stdio(
            OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
                .open("/dev/null")?,
        )?;
        let input_meta = input.metadata()?;
        if input_meta.mode() & libc::S_IFMT != libc::S_IFCHR || input_meta.rdev() != 259 {
            return Err(reject("stdin is not the host null device"));
        }
        let (output, output_write) = pipe()?;
        let (error, error_write) = pipe()?;
        let arg0 = c"droidloom-public-nss-observer";
        let command =
            CString::new(WORKER_ARGUMENT).map_err(|_| reject("invalid internal worker command"))?;
        let argv = [arg0.as_ptr(), command.as_ptr(), std::ptr::null()];
        let envp = [
            c"LC_ALL=C".as_ptr(),
            c"PATH=/usr/sbin:/usr/bin:/sbin:/bin".as_ptr(),
            std::ptr::null(),
        ];
        let mut filter = no_children_filter(false);
        let program = libc::sock_fprog {
            len: filter.len() as u16,
            filter: filter.as_mut_ptr(),
        };
        let parent = unsafe { libc::getpid() };
        let mut pidfd = -1_i32;
        let args = CloneArgs {
            flags: libc::CLONE_PIDFD as u64,
            pidfd: (&mut pidfd as *mut i32) as u64,
            exit_signal: libc::SIGCHLD as u64,
            ..CloneArgs::default()
        };
        let mut mask = KernelSignalMask::block()?;
        let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args)) };
        if pid < 0 {
            return Err(io::Error::last_os_error().into());
        }
        if pid == 0 {
            unsafe {
                worker_child(
                    parent,
                    executable.as_raw_fd(),
                    input.as_raw_fd(),
                    output_write.as_raw_fd(),
                    error_write.as_raw_fd(),
                    argv.as_ptr(),
                    envp.as_ptr(),
                    &program,
                );
            }
        }
        // CLONE_PIDFD provides this capability atomically; no numeric-PID
        // lookup or guessed generation is used to acquire worker ownership.
        if pidfd < 0 {
            // This is an impossible kernel ABI violation. No PID-based kill
            // fallback could safely establish custody; retain admission.
            return Err(HostAdmissionError::RetirementUnproven);
        }
        drop(output_write);
        drop(error_write);
        let owner = Self {
            pid: pid as libc::pid_t,
            pidfd: mem::ManuallyDrop::new(unsafe { OwnedFd::from_raw_fd(pidfd) }),
            output: mem::ManuallyDrop::new(output),
            error: mem::ManuallyDrop::new(error),
            reaped: false,
            terminal_status: None,
            quarantine,
        };
        mask.restore()?; // On failure owner Drop still retires exactly this child.
        Ok(owner)
    }
    fn terminal(&self, reap: bool) -> Result<Option<(i32, i32)>> {
        let mut info: libc::siginfo_t = unsafe { mem::zeroed() };
        let options = libc::WEXITED | libc::WNOHANG | if reap { 0 } else { libc::WNOWAIT };
        if unsafe {
            libc::waitid(
                libc::P_PIDFD,
                self.pidfd.as_raw_fd() as libc::id_t,
                &mut info,
                options,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        let pid = unsafe { info.si_pid() };
        if pid == 0 {
            return Ok(None);
        }
        if pid != self.pid
            || !matches!(
                info.si_code,
                libc::CLD_EXITED | libc::CLD_KILLED | libc::CLD_DUMPED
            )
        {
            return Err(reject("unexpected owned-worker wait result"));
        }
        Ok(Some((info.si_code, unsafe { info.si_status() })))
    }
    fn reap_terminal(&mut self, expected: (i32, i32)) -> Result<()> {
        if self.terminal(true)? != Some(expected) {
            return Err(HostAdmissionError::RetirementUnproven);
        }
        self.terminal_status = Some(expected);
        self.reaped = true;
        Ok(())
    }
    fn retire(&mut self) -> Result<()> {
        if self.reaped {
            return Ok(());
        }
        let first = self.terminal(false).ok().flatten();
        if let Some(value) = first {
            return self.reap_terminal(value);
        }
        let result = unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.pidfd.as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0_u32,
            )
        };
        if result != 0 && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH) {
            return Err(HostAdmissionError::RetirementUnproven);
        }
        let deadline = Instant::now() + RETIRE_TIMEOUT;
        while Instant::now() < deadline {
            if let Ok(Some(value)) = self.terminal(false) {
                return self.reap_terminal(value);
            }
            let mut poll = libc::pollfd {
                fd: self.pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            unsafe {
                libc::poll(&mut poll, 1, 20);
            }
        }
        Err(HostAdmissionError::RetirementUnproven)
    }
    fn collect(&mut self) -> Result<Vec<u8>> {
        let deadline = Instant::now() + WORKER_TIMEOUT;
        let mut output = Vec::new();
        let mut error = Vec::new();
        let mut output_eof = false;
        let mut error_eof = false;
        loop {
            drain_pipe(&mut self.output, &mut output, OUTPUT_LIMIT, &mut output_eof)?;
            drain_pipe(&mut self.error, &mut error, 65536, &mut error_eof)?;
            if let Some(value) = self.terminal(false)? {
                if output_eof && error_eof {
                    self.reap_terminal(value)?;
                    if value != (libc::CLD_EXITED, 0) || !error.is_empty() {
                        return Err(reject("owned NSS worker exited unsuccessfully"));
                    }
                    if output.is_empty() || output.len() > OUTPUT_LIMIT {
                        return Err(reject("worker output bound"));
                    }
                    return Ok(output);
                }
            }
            if Instant::now() >= deadline {
                return Err(reject("owned NSS worker deadline"));
            }
            let mut fds = [
                libc::pollfd {
                    fd: self.pidfd.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.output.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.error.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            let status = unsafe { libc::poll(fds.as_mut_ptr(), fds.len() as libc::nfds_t, 20) };
            if status < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
                return Err(io::Error::last_os_error().into());
            }
        }
    }
}
fn drain_pipe(file: &mut File, bytes: &mut Vec<u8>, maximum: usize, eof: &mut bool) -> Result<()> {
    if *eof {
        return Ok(());
    }
    loop {
        let mut buffer = [0_u8; 4096];
        match file.read(&mut buffer) {
            Ok(0) => {
                *eof = true;
                return Ok(());
            }
            Ok(count) => {
                if bytes.len().checked_add(count).is_none_or(|v| v > maximum) {
                    return Err(reject("worker log bound"));
                }
                bytes.extend_from_slice(&buffer[..count]);
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => return Ok(()),
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error.into()),
        }
    }
}
impl Drop for WorkerOwner<'_> {
    fn drop(&mut self) {
        if self.retire().is_err() {
            self.quarantine.set(true);
            return;
        }
        unsafe {
            mem::ManuallyDrop::drop(&mut self.pidfd);
            mem::ManuallyDrop::drop(&mut self.output);
            mem::ManuallyDrop::drop(&mut self.error);
        }
    }
}
#[derive(Serialize)]
struct WorkerReceipt {
    pid: i32,
    waitid_code: i32,
    waitid_status: i32,
    reaped: bool,
    executable_device: u64,
    executable_inode: u64,
    executable_bytes: u64,
    executable_sha256: String,
    output_bytes: usize,
    output_sha256: String,
    elapsed_millis: u64,
}
struct WorkerObservation {
    public: PublicObservation,
    receipt: WorkerReceipt,
}
fn run_owned_worker(quarantine: &Cell<bool>) -> Result<PublicObservation> {
    Ok(run_owned_worker_with_receipt(quarantine)?.public)
}
fn run_owned_worker_with_receipt(quarantine: &Cell<bool>) -> Result<WorkerObservation> {
    let started = Instant::now();
    let (executable, before, source_sha256) = self_executable()?;
    let mut worker = WorkerOwner::start(&executable, quarantine)?;
    let result = worker.collect();
    if worker.retire().is_err() {
        quarantine.set(true);
        mem::forget(worker);
        return Err(HostAdmissionError::RetirementUnproven);
    }
    let bytes = result?;
    if before != Node::of(&executable.metadata()?) {
        return Err(HostAdmissionError::Changed);
    }
    let terminal = worker
        .terminal_status
        .ok_or(HostAdmissionError::RetirementUnproven)?;
    if !worker.reaped || terminal != (libc::CLD_EXITED, 0) {
        return Err(HostAdmissionError::RetirementUnproven);
    }
    let observation = serde_json::from_slice(&bytes)
        .map_err(|_| reject("invalid complete public NSS worker result"))?;
    Ok(WorkerObservation {
        public: canonical_observation(observation)?,
        receipt: WorkerReceipt {
            pid: worker.pid,
            waitid_code: terminal.0,
            waitid_status: terminal.1,
            reaped: worker.reaped,
            executable_device: before.dev,
            executable_inode: before.ino,
            executable_bytes: before.size,
            executable_sha256: source_sha256,
            output_bytes: bytes.len(),
            output_sha256: format!("{:x}", Sha256::digest(&bytes)),
            elapsed_millis: started.elapsed().as_millis() as u64,
        },
    })
}

/// Observe the complete supported public NSS providers using owned workers.
///
/// This zero-argument diagnostic issues no capability and never acquires a
/// lease, creates a principal or grant, or starts a namespace. Its output is
/// observation data only and cannot be deserialized into admission authority.
///
/// # Errors
///
/// Requires the actual initial-host root boundary and a root-sealed executable.
/// Any provider change, incomplete enumeration or unproven child exit rejects
/// the diagnostic; no best-effort success is emitted.
#[doc(hidden)]
pub fn run_nss_observation_probe() -> Result<()> {
    require_initial_root()?;
    let before = HostInputs::capture()?;
    let quarantine = Cell::new(false);
    let first = run_owned_worker_with_receipt(&quarantine)?;
    public_observation_coverage(&before, &first.public)?;
    let second = run_owned_worker_with_receipt(&quarantine)?;
    public_observation_coverage(&before, &second.public)?;
    before.sssd.revalidate_held()?;
    let after = HostInputs::capture()?;
    before.sssd.revalidate_held()?;
    if before != after || first.public != second.public {
        return Err(HostAdmissionError::Changed);
    }
    let output = serde_json::json!({
        "schema": "droidloom-owned-public-nss-observation-v1",
        "state": "OBSERVATION_ONLY",
        "authority_issued": false,
        "lease_or_grant_created": false,
        "namespaces_or_maps_created": false,
        "runtime_qualified": false,
        "owned_workers": [first.receipt, second.receipt],
        "public_observation": second.public,
    });
    let bytes = serde_json::to_vec(&output).map_err(|_| reject("diagnostic encoding failed"))?;
    if bytes.len() > OUTPUT_LIMIT {
        return Err(reject("diagnostic output bound"));
    }
    io::stdout().lock().write_all(&bytes)?;
    Ok(())
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
struct NamespaceKey {
    device: u64,
    inode: u64,
    kernel_id: u64,
}
fn fs_type(file: &File) -> Result<libc::c_long> {
    let mut value: libc::statfs = unsafe { mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(value.f_type)
}
fn typed_namespace_key(file: &File, expected_kind: i32) -> Result<NamespaceKey> {
    if fs_type(file)? != NSFS_MAGIC
        || unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE, 0 as libc::c_ulong) }
            != expected_kind
    {
        return Err(reject(
            "descriptor is not the required kernel namespace kind",
        ));
    }
    let mut id = 0_u64;
    if unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_ID, &mut id) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let metadata = file.metadata()?;
    Ok(NamespaceKey {
        device: metadata.dev(),
        inode: metadata.ino(),
        kernel_id: id,
    })
}
fn namespace_key(file: &File) -> Result<NamespaceKey> {
    typed_namespace_key(file, libc::CLONE_NEWUSER)
}
fn initial_namespace(key: NamespaceKey) -> bool {
    key.inode == USER_NS_INIT_INO && key.kernel_id == USER_NS_INIT_ID
}
#[repr(C)]
struct CapHeader {
    version: u32,
    pid: i32,
}
#[repr(C)]
#[derive(Clone, Copy, Default)]
struct CapData {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}
fn require_initial_root() -> Result<()> {
    if unsafe { libc::getuid() } != 0 || unsafe { libc::geteuid() } != 0 {
        return Err(reject("initial-userns root admission required"));
    }
    let proc = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW)
        .open("/proc")?;
    if fs_type(&proc)? != PROC_MAGIC {
        return Err(reject("initial host procfs required"));
    }
    let pidns = File::open("/proc/self/ns/pid")?;
    let mut pid_id = 0_u64;
    if fs_type(&pidns)? != NSFS_MAGIC
        || pidns.metadata()?.ino() != 0xEFFF_FFFC
        || unsafe { libc::ioctl(pidns.as_raw_fd(), NS_GET_NSTYPE, 0 as libc::c_ulong) }
            != libc::CLONE_NEWPID
        || unsafe { libc::ioctl(pidns.as_raw_fd(), NS_GET_ID, &mut pid_id) } != 0
        || pid_id != 4
    {
        return Err(reject(
            "complete host audit requires the initial PID namespace",
        ));
    }
    let first = open_at(&proc, "1", libc::O_RDONLY | libc::O_DIRECTORY)?;
    let nsdir = open_at(&first, "ns", libc::O_RDONLY | libc::O_DIRECTORY)?;
    let first_pidns = open_namespace(&nsdir, "pid")?;
    let mut first_id = 0_u64;
    if first_pidns.metadata()?.ino() != 0xEFFF_FFFC
        || unsafe { libc::ioctl(first_pidns.as_raw_fd(), NS_GET_ID, &mut first_id) } != 0
        || first_id != 4
    {
        return Err(reject(
            "mounted procfs is not the initial PID-namespace view",
        ));
    }
    let actual_pid = unsafe { libc::getpid() } as u32;
    let own = open_at(
        &proc,
        &actual_pid.to_string(),
        libc::O_RDONLY | libc::O_DIRECTORY,
    )?;
    task_start(&proc_text(&own, "stat")?, actual_pid)?;
    let userns = File::open("/proc/self/ns/user")?;
    if !initial_namespace(namespace_key(&userns)?) {
        return Err(reject("admission is outside initial user namespace"));
    }
    let mut header = CapHeader {
        version: 0x2008_0522,
        pid: 0,
    };
    let mut data = [CapData::default(); 2];
    if unsafe { libc::syscall(libc::SYS_capget, &mut header, data.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let required = (1_u32 << 6) | (1_u32 << 7);
    if data[0].effective & required != required {
        return Err(reject("initial CAP_SETUID/CAP_SETGID required"));
    }
    Ok(())
}
fn proc_read(directory: &File, leaf: &str) -> Result<Vec<u8>> {
    let file = open_at(directory, leaf, libc::O_RDONLY)?;
    if fs_type(&file)? != PROC_MAGIC || !file.metadata()?.is_file() {
        return Err(reject("non-proc kernel identity input"));
    }
    read_bounded(&file, PROC_LIMIT)
}
fn proc_text(directory: &File, leaf: &str) -> Result<String> {
    String::from_utf8(proc_read(directory, leaf)?)
        .map_err(|_| reject("non-text proc identity input"))
}
fn open_namespace(directory: &File, leaf: &str) -> Result<File> {
    let name = component(leaf)?;
    // Kernel namespace magic links are followed only under a held proc ns FD.
    let fd = unsafe {
        libc::openat(
            directory.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    if fs_type(&file)? != NSFS_MAGIC {
        return Err(reject("namespace magic link changed type"));
    }
    Ok(file)
}
fn owning_userns(file: File) -> Result<File> {
    if unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE, 0 as libc::c_ulong) }
        == libc::CLONE_NEWUSER
    {
        return Ok(file);
    }
    let fd = unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_USERNS, 0 as libc::c_ulong) };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let owner = unsafe { File::from_raw_fd(fd) };
    namespace_key(&owner)?;
    Ok(owner)
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct MapLine {
    inner: u32,
    outer: u32,
    count: u32,
}
fn parse_map(text: &str) -> Result<Vec<MapLine>> {
    let mut lines = Vec::new();
    for line in text.lines() {
        let values: Vec<_> = line.split_whitespace().collect();
        if values.len() != 3 || lines.len() == 340 {
            return Err(reject("unsupported kernel ID map"));
        }
        let count = if values[2] == "4294967295" {
            u32::MAX
        } else {
            number(values[2])?
        };
        let row = MapLine {
            inner: number(values[0])?,
            outer: number(values[1])?,
            count,
        };
        if row.count == 0
            || u64::from(row.inner) + u64::from(row.count) > u64::from(u32::MAX)
            || u64::from(row.outer) + u64::from(row.count) > u64::from(u32::MAX)
        {
            return Err(reject("invalid kernel ID-map extent"));
        }
        for previous in &lines {
            let previous: &MapLine = previous;
            if intervals_overlap(row.inner, row.count, previous.inner, previous.count)
                || intervals_overlap(row.outer, row.count, previous.outer, previous.count)
            {
                return Err(reject("overlapping kernel ID-map extents"));
            }
        }
        lines.push(row);
    }
    Ok(lines)
}
fn intervals_overlap(start: u32, count: u32, other: u32, other_count: u32) -> bool {
    u64::from(start) < u64::from(other) + u64::from(other_count)
        && u64::from(other) < u64::from(start) + u64::from(count)
}
fn exact_map(rows: &[MapLine], range: IdRange) -> bool {
    rows == [MapLine {
        inner: 0,
        outer: range.start,
        count: range.count,
    }]
}
fn allowed_owned_maps(
    uid: &[MapLine],
    gid: &[MapLine],
    uids: IdRange,
    gids: IdRange,
    groups: &str,
) -> Result<()> {
    if groups != "allow\n"
        || !(uid.is_empty() && gid.is_empty()
            || exact_map(uid, uids) && gid.is_empty()
            || exact_map(uid, uids) && exact_map(gid, gids))
    {
        return Err(reject(
            "owned namespace is outside its exact monotonic map stages",
        ));
    }
    Ok(())
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct Credentials {
    uids: [u32; 4],
    gids: [u32; 4],
    groups: Vec<u32>,
    tgid: u32,
}
fn parse_status(text: &str) -> Result<Credentials> {
    let mut fields = BTreeMap::new();
    for line in text.lines() {
        let Some((key, value)) = line.split_once(':') else {
            continue;
        };
        if matches!(key, "Uid" | "Gid" | "Groups" | "Tgid") && fields.insert(key, value).is_some() {
            return Err(reject("duplicate proc credential field"));
        }
    }
    let values = |key: &str| -> Result<Vec<u32>> {
        fields
            .get(key)
            .ok_or_else(|| reject("incomplete proc credential record"))?
            .split_whitespace()
            .map(number)
            .collect()
    };
    let uids: [u32; 4] = values("Uid")?
        .try_into()
        .map_err(|_| reject("four real/effective/saved/fs UIDs required"))?;
    let gids: [u32; 4] = values("Gid")?
        .try_into()
        .map_err(|_| reject("four real/effective/saved/fs GIDs required"))?;
    let mut groups = values("Groups")?;
    if groups.len() > RECORD_LIMIT {
        return Err(reject("supplementary group count"));
    }
    groups.sort();
    let tgid = values("Tgid")?;
    if tgid.len() != 1 {
        return Err(reject("one thread-group identity required"));
    }
    Ok(Credentials {
        uids,
        gids,
        groups,
        tgid: tgid[0],
    })
}
fn task_start(text: &str, tid: u32) -> Result<(u64, char)> {
    if !text.starts_with(&format!("{tid} (")) {
        return Err(reject("proc task identity mismatch"));
    }
    let end = text
        .rfind(") ")
        .ok_or_else(|| reject("malformed proc task stat"))?;
    let fields: Vec<_> = text[end + 2..].split_whitespace().collect();
    if fields.len() < 20 || fields[0].len() != 1 {
        return Err(reject("short proc task stat"));
    }
    let start = fields[19]
        .parse::<u64>()
        .map_err(|_| reject("invalid task start ticks"))?;
    Ok((start, fields[0].chars().next().unwrap()))
}
fn pidfd_terminal(fd: RawFd) -> Result<bool> {
    let mut item = libc::pollfd {
        fd,
        events: libc::POLLIN,
        revents: 0,
    };
    if unsafe { libc::poll(&mut item, 1, 0) } < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if item.revents & libc::POLLNVAL != 0 {
        return Err(reject("invalid held pidfd"));
    }
    Ok(item.revents & (libc::POLLIN | libc::POLLHUP) != 0)
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct TaskView {
    credentials: Credentials,
    proc_identity: (u64, u64),
    namespace: Option<NamespaceKey>,
    pid_namespace: Option<NamespaceKey>,
    uid_map: Vec<MapLine>,
    gid_map: Vec<MapLine>,
    setgroups: String,
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct LiveView {
    tasks: BTreeMap<(u32, u32, u64), TaskView>,
    referenced_namespaces: BTreeSet<NamespaceKey>,
}
fn namespace_reference(file: File, references: &mut BTreeSet<NamespaceKey>) -> Result<()> {
    let userns = owning_userns(file)?;
    let mut current = userns;
    for _ in 0..32 {
        let key = namespace_key(&current)?;
        references.insert(key);
        if initial_namespace(key) {
            return Ok(());
        }
        let parent = unsafe {
            libc::ioctl(
                current.as_raw_fd(),
                0xb702 as libc::c_ulong,
                0 as libc::c_ulong,
            )
        };
        if parent < 0 {
            return Err(reject("noninitial namespace ancestry is not observable"));
        }
        current = unsafe { File::from_raw_fd(parent) };
    }
    Err(reject("user namespace ancestry bound"))
}
#[repr(C)]
struct OpenHow {
    flags: u64,
    mode: u64,
    resolve: u64,
}
fn mount_unescape(value: &str) -> Result<String> {
    let mut output = String::new();
    let mut rest = value;
    while let Some(at) = rest.find('\\') {
        output.push_str(&rest[..at]);
        let escaped = rest
            .get(at..at + 4)
            .ok_or_else(|| reject("truncated mountinfo escape"))?;
        output.push(match escaped {
            "\\040" => ' ',
            "\\011" => '\t',
            "\\012" => '\n',
            "\\134" => '\\',
            _ => return Err(reject("unknown mountinfo escape")),
        });
        rest = &rest[at + 4..];
    }
    output.push_str(rest);
    if !output.starts_with('/')
        || Path::new(&output)
            .components()
            .any(|c| !matches!(c, Component::RootDir | Component::Normal(_)))
    {
        return Err(reject("non-normal mountinfo path"));
    }
    Ok(output)
}
fn audit_nsfs_mounts(task: &File, references: &mut BTreeSet<NamespaceKey>) -> Result<bool> {
    let info = proc_text(task, "mountinfo")?;
    let mut nsfs = Vec::new();
    let mut full_root = false;
    for line in info.lines() {
        let Some((left, right)) = line.split_once(" - ") else {
            return Err(reject("malformed mountinfo"));
        };
        let left: Vec<_> = left.split_whitespace().collect();
        let right: Vec<_> = right.split_whitespace().collect();
        if left.len() < 6 || right.len() < 3 {
            return Err(reject("short mountinfo"));
        }
        let mountpoint = mount_unescape(left[4])?;
        if mountpoint == "/" && mount_unescape(left[3])? == "/" {
            full_root = true;
        }
        if right[0] == "nsfs" {
            nsfs.push(mountpoint);
        }
    }
    // A chrooted task may hide mounts in the same namespace. Another task
    // with that namespace's full root must provide the complete view.
    if !full_root {
        return Ok(false);
    }
    if nsfs.is_empty() {
        return Ok(true);
    }
    let root_fd = unsafe {
        libc::openat(
            task.as_raw_fd(),
            c"root".as_ptr(),
            libc::O_PATH | libc::O_CLOEXEC,
        )
    };
    if root_fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let root = unsafe { File::from_raw_fd(root_fd) };
    for mountpoint in nsfs {
        let path = CString::new(mountpoint).map_err(|_| reject("NUL mount path"))?;
        let how = OpenHow {
            flags: (libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NONBLOCK) as u64,
            mode: 0,
            resolve: 0x10 | 0x02 | 0x04,
        }; // IN_ROOT, NO_MAGICLINKS, NO_SYMLINKS
        let fd = unsafe {
            libc::syscall(
                libc::SYS_openat2,
                root.as_raw_fd(),
                path.as_ptr(),
                &how,
                mem::size_of_val(&how),
            )
        };
        if fd < 0 {
            return Err(reject(
                "persistent namespace mount is not observable under its held root",
            ));
        }
        let file = unsafe { File::from_raw_fd(fd as RawFd) };
        if fs_type(&file)? != NSFS_MAGIC {
            return Err(HostAdmissionError::Changed);
        }
        namespace_reference(file, references)?;
    }
    if info != proc_text(task, "mountinfo")? {
        return Err(HostAdmissionError::Changed);
    }
    Ok(true)
}
fn audit_fd_namespaces(
    task: &File,
    references: &mut BTreeSet<NamespaceKey>,
    inspected: &mut usize,
) -> Result<()> {
    let directory = open_at(task, "fd", libc::O_RDONLY | libc::O_DIRECTORY)?;
    // Linux tasks in one thread group can unshare their descriptor table.
    // Inspect every task's table; the leader's descriptors are not a proxy.
    with_directory_names(&directory, 65536, |names, _iterator| {
        for entry in names {
            number(entry)?;
            *inspected += 1;
            if *inspected > 262144 {
                return Err(reject("host descriptor audit bound"));
            }
            let name = component(entry)?;
            // O_PATH obtains only identity, never opens a device or user file
            // for data access. Reopen only a proven nsfs object.
            let fd = unsafe {
                libc::openat(
                    directory.as_raw_fd(),
                    name.as_ptr(),
                    libc::O_PATH | libc::O_CLOEXEC,
                )
            };
            if fd < 0 {
                return Err(HostAdmissionError::Changed);
            }
            let path = unsafe { File::from_raw_fd(fd) };
            if fs_type(&path)? == NSFS_MAGIC {
                let own_path = format!("/proc/self/fd/{}", path.as_raw_fd());
                let file = File::open(own_path)?;
                if Node::of(&path.metadata()?).key() != Node::of(&file.metadata()?).key() {
                    return Err(HostAdmissionError::Changed);
                }
                namespace_reference(file, references)?;
            }
        }
        Ok(())
    })
}
fn scan_live_tasks() -> Result<LiveView> {
    let proc = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW)
        .open("/proc")?;
    if fs_type(&proc)? != PROC_MAGIC {
        return Err(reject("host procfs is not observable"));
    }
    let pids: Vec<_> = directory_names(&proc, TASK_LIMIT)?
        .into_iter()
        .filter(|name| name.bytes().all(|b| b.is_ascii_digit()))
        .collect();
    let mut tasks = BTreeMap::new();
    let mut references = BTreeSet::new();
    let mut mount_namespaces = BTreeSet::new();
    let mut complete_mounts = BTreeSet::new();
    let mut inspected_fds = 0;
    let deadline = Instant::now() + Duration::from_secs(30);
    for entry in &pids {
        if Instant::now() >= deadline {
            return Err(reject("live identity audit deadline"));
        }
        let pid = number(entry)?;
        let process = open_at(&proc, entry, libc::O_RDONLY | libc::O_DIRECTORY)?;
        let process_before = task_start(&proc_text(&process, "stat")?, pid)?;
        let raw_pidfd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid as libc::pid_t, 0_u32) };
        if raw_pidfd < 0 {
            return Err(HostAdmissionError::Changed);
        }
        let pidfd = unsafe { OwnedFd::from_raw_fd(raw_pidfd as RawFd) };
        let task_dir = open_at(&process, "task", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let tids = directory_names(&task_dir, TASK_LIMIT)?;
        for entry in &tids {
            if tasks.len() == TASK_LIMIT {
                return Err(reject("host task audit bound"));
            }
            let tid = number(entry)?;
            let task = open_at(&task_dir, entry, libc::O_RDONLY | libc::O_DIRECTORY)?;
            let before = task_start(&proc_text(&task, "stat")?, tid)?;
            let credentials = parse_status(&proc_text(&task, "status")?)?;
            if credentials.tgid != pid {
                return Err(HostAdmissionError::Changed);
            }
            let ns_directory = open_at(&task, "ns", libc::O_RDONLY | libc::O_DIRECTORY)?;
            let userns = match open_namespace(&ns_directory, "user") {
                Ok(value) => Some(value),
                Err(HostAdmissionError::Io(error))
                    if matches!(
                        error.raw_os_error(),
                        Some(libc::ENOENT | libc::ESRCH | libc::EINVAL)
                    ) && matches!(before.1, 'Z' | 'X')
                        && pidfd_terminal(pidfd.as_raw_fd())? =>
                {
                    None
                }
                Err(error) => return Err(error),
            };
            let mut view = TaskView {
                credentials: credentials.clone(),
                proc_identity: Node::of(&process.metadata()?).key(),
                namespace: None,
                pid_namespace: None,
                uid_map: Vec::new(),
                gid_map: Vec::new(),
                setgroups: String::new(),
            };
            if let Some(userns) = userns {
                let key = namespace_key(&userns)?;
                view.namespace = Some(key);
                view.uid_map = parse_map(&proc_text(&task, "uid_map")?)?;
                view.gid_map = parse_map(&proc_text(&task, "gid_map")?)?;
                view.setgroups = proc_text(&task, "setgroups")?;
                namespace_reference(userns, &mut references)?;
                for ns in directory_names(&ns_directory, 32)? {
                    if ns == "user" {
                        continue;
                    }
                    let file = open_namespace(&ns_directory, &ns)?;
                    if ns == "pid" {
                        view.pid_namespace = Some(typed_namespace_key(&file, libc::CLONE_NEWPID)?);
                    }
                    if ns == "mnt" {
                        let key = Node::of(&file.metadata()?).key();
                        mount_namespaces.insert(key);
                        if !complete_mounts.contains(&key)
                            && audit_nsfs_mounts(&task, &mut references)?
                        {
                            complete_mounts.insert(key);
                        }
                    }
                    namespace_reference(file, &mut references)?;
                }
                audit_fd_namespaces(&task, &mut references, &mut inspected_fds)?;
            }
            if before.0 != task_start(&proc_text(&task, "stat")?, tid)?.0
                || credentials != parse_status(&proc_text(&task, "status")?)?
            {
                return Err(HostAdmissionError::Changed);
            }
            if tasks.insert((pid, tid, before.0), view).is_some() {
                return Err(HostAdmissionError::Changed);
            }
        }
        if tids != directory_names(&task_dir, TASK_LIMIT)?
            || process_before.0 != task_start(&proc_text(&process, "stat")?, pid)?.0
        {
            return Err(HostAdmissionError::Changed);
        }
    }
    if mount_namespaces != complete_mounts {
        return Err(reject(
            "a live mount namespace has no complete observable root",
        ));
    }
    let after: Vec<_> = directory_names(&proc, TASK_LIMIT)?
        .into_iter()
        .filter(|name| name.bytes().all(|b| b.is_ascii_digit()))
        .collect();
    if pids != after {
        return Err(HostAdmissionError::Changed);
    }
    Ok(LiveView {
        tasks,
        referenced_namespaces: references,
    })
}
#[derive(Clone, Copy)]
struct KeeperIdentity {
    pid: u32,
    start_ticks: u64,
    proc_identity: (u64, u64),
}
fn validate_owned_task(
    identity: (u32, u32, u64),
    task: &TaskView,
    keeper: &KeeperIdentity,
    descendant_pidns: Option<NamespaceKey>,
    uids: IdRange,
    gids: IdRange,
) -> Result<()> {
    allowed_owned_maps(&task.uid_map, &task.gid_map, uids, gids, &task.setgroups)?;
    if identity == (keeper.pid, keeper.pid, keeper.start_ticks)
        && task.proc_identity == keeper.proc_identity
    {
        return Ok(());
    }
    // Only a TreeOwner-backed witness can supply this held PID namespace.
    // Complete maps alone do not authorize every task sharing the userns.
    if descendant_pidns.is_some()
        && task.pid_namespace == descendant_pidns
        && exact_map(&task.uid_map, uids)
        && exact_map(&task.gid_map, gids)
    {
        return Ok(());
    }
    Err(reject("owned user namespace has an unowned live task"))
}

fn validate_live_view(
    view: &LiveView,
    uids: IdRange,
    gids: IdRange,
    principal_uid: u32,
    principal_gid: u32,
    witness: Option<&OwnedNamespaceWitness<'_>>,
) -> Result<()> {
    let owned = witness
        .map(|w| namespace_key(w.user_namespace()))
        .transpose()?;
    let keeper = witness
        .map(|w| {
            Ok::<_, HostAdmissionError>(KeeperIdentity {
                pid: w.host_pid(),
                start_ticks: w.start_ticks(),
                proc_identity: Node::of(&w.proc_directory().metadata()?).key(),
            })
        })
        .transpose()?;
    let descendant_pidns = witness
        .and_then(|w| w.descendant_pid_namespace())
        .map(|file| typed_namespace_key(file, libc::CLONE_NEWPID))
        .transpose()?;
    let mut known = BTreeMap::new();
    for (identity, task) in &view.tasks {
        let allowed = task.namespace.is_some() && task.namespace == owned;
        let c = &task.credentials;
        if c.uids.contains(&principal_uid)
            || c.gids.contains(&principal_gid)
            || c.groups.contains(&principal_gid)
        {
            return Err(reject(
                "dedicated host principal has a live credential user",
            ));
        }
        if !allowed
            && (c.uids.iter().any(|id| in_range(*id, uids))
                || c.gids.iter().chain(&c.groups).any(|id| in_range(*id, gids)))
        {
            return Err(reject("subordinate range has a live credential user"));
        }
        if let Some(key) = task.namespace {
            if let Some(previous) = known.insert(key, (task.uid_map.clone(), task.gid_map.clone()))
            {
                if previous != (task.uid_map.clone(), task.gid_map.clone()) {
                    return Err(HostAdmissionError::Changed);
                }
            }
            if initial_namespace(key) {
                let initial = IdRange {
                    start: 0,
                    count: u32::MAX,
                };
                if !exact_map(&task.uid_map, initial) || !exact_map(&task.gid_map, initial) {
                    return Err(reject("initial-namespace map view is incomplete"));
                }
                continue;
            }
            if allowed {
                validate_owned_task(
                    *identity,
                    task,
                    keeper
                        .as_ref()
                        .ok_or_else(|| reject("missing exact keeper"))?,
                    descendant_pidns,
                    uids,
                    gids,
                )?;
            } else {
                if task.uid_map.is_empty() || task.gid_map.is_empty() {
                    return Err(reject(
                        "unowned noninitial user namespace has unobservable future maps",
                    ));
                }
                if task
                    .uid_map
                    .iter()
                    .any(|row| intervals_overlap(row.outer, row.count, uids.start, uids.count))
                    || task
                        .gid_map
                        .iter()
                        .any(|row| intervals_overlap(row.outer, row.count, gids.start, gids.count))
                {
                    return Err(reject(
                        "subordinate range overlaps a live foreign namespace map",
                    ));
                }
            }
        }
    }
    for key in &view.referenced_namespaces {
        if !initial_namespace(*key) && !known.contains_key(key) {
            return Err(reject(format!(
                "retained namespace map is not observable (inode {}, kernel ID {})",
                key.inode, key.kernel_id
            )));
        }
    }
    Ok(())
}
fn audit_live_tasks(
    uids: IdRange,
    gids: IdRange,
    uid: u32,
    gid: u32,
    witness: Option<&OwnedNamespaceWitness<'_>>,
) -> Result<()> {
    if let Some(witness) = witness {
        witness.revalidate().map_err(|e| reject(e.to_string()))?;
    }
    let first = scan_live_tasks()?;
    validate_live_view(&first, uids, gids, uid, gid, witness)?;
    let second = scan_live_tasks()?;
    validate_live_view(&second, uids, gids, uid, gid, witness)?;
    if first != second {
        return Err(HostAdmissionError::Changed);
    }
    if let Some(witness) = witness {
        witness.revalidate().map_err(|e| reject(e.to_string()))?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ranges() -> (IdRange, IdRange) {
        (
            IdRange {
                start: 200000,
                count: 65536,
            },
            IdRange {
                start: 300000,
                count: 65536,
            },
        )
    }

    fn sssd_test_state() -> SssdSystemObservation {
        SssdSystemObservation {
            manager_pid: 1,
            manager_euid: 0,
            units: SSSD_UNITS
                .iter()
                .map(|&(unit, _, _)| {
                    let socket = unit.ends_with(".socket");
                    SssdUnitObservation {
                        unit: unit.into(),
                        load_state: "loaded".into(),
                        active_state: "inactive".into(),
                        sub_state: "dead".into(),
                        fragment_path: format!("/usr/lib/systemd/system/{unit}"),
                        unit_file_state: if unit == "sssd-nss.service" {
                            "indirect".into()
                        } else {
                            "enabled".into()
                        },
                        condition_result: socket,
                        control_group: String::new(),
                        drop_in_paths: Vec::new(),
                        main_pid: if socket { None } else { Some(0) },
                        user: if socket { None } else { Some("sssd".into()) },
                        group: if socket { None } else { Some("sssd".into()) },
                    }
                })
                .collect(),
        }
    }

    #[test]
    fn host_admission_sssd_package_service_directories_accept_real_uid_gid_and_modes() {
        let identity = SssdIdentity { uid: 110, gid: 113 };
        let node = Node {
            dev: 1,
            ino: 2,
            mode: libc::S_IFDIR | 0o775,
            uid: 110,
            gid: 113,
            links: 2,
            size: 4096,
            mtime: (1, 0),
            ctime: (1, 0),
        };
        sssd_directory_policy(&node, &identity).unwrap();
        let mut private = node.clone();
        private.mode = libc::S_IFDIR | 0o770;
        sssd_directory_policy(&private, &identity).unwrap();
        for changed in [
            Node {
                uid: 111,
                ..node.clone()
            },
            Node {
                gid: 114,
                ..node.clone()
            },
            Node {
                mode: libc::S_IFDIR | 0o777,
                ..node.clone()
            },
            Node {
                mode: libc::S_IFLNK | 0o777,
                ..node.clone()
            },
            Node {
                mode: libc::S_IFREG | 0o775,
                ..node.clone()
            },
        ] {
            assert!(sssd_directory_policy(&changed, &identity).is_err());
        }
    }

    #[test]
    fn host_admission_sssd_files_identity_requires_unique_noninteractive_service() {
        let passwd =
            "root:x:0:0::/root:/bin/bash\nsssd:x:110:113::/var/lib/sss:/usr/sbin/nologin\n";
        let group = "root:x:0:\nsssd:x:113:\n";
        let (users, groups) = public_files(passwd, group).unwrap();
        assert_eq!(
            sssd_files_identity(passwd, &users, &groups).unwrap(),
            SssdIdentity { uid: 110, gid: 113 }
        );
        for (p, g) in [
            (
                passwd.replace("/usr/sbin/nologin", "/bin/bash"),
                group.to_owned(),
            ),
            (
                format!("{passwd}alias:x:110:500::/:/usr/sbin/nologin\n"),
                group.to_owned(),
            ),
            (
                format!("{passwd}alias:x:500:113::/:/usr/sbin/nologin\n"),
                group.to_owned(),
            ),
            (
                passwd.to_owned(),
                group.replace("sssd:x:113:", "sssd:x:113:other"),
            ),
            (passwd.to_owned(), format!("{group}other:x:114:sssd\n")),
            (passwd.to_owned(), format!("{group}alias:x:113:\n")),
        ] {
            let (u, g) = public_files(&p, &g).unwrap();
            assert!(sssd_files_identity(&p, &u, &g).is_err());
        }
    }

    #[test]
    fn host_admission_sssd_empty_cache_check_uses_real_directory_without_reading_body() {
        let temp = tempfile::tempdir().unwrap();
        let dir = File::open(temp.path()).unwrap();
        let meta = dir.metadata().unwrap();
        let identity = SssdIdentity {
            uid: meta.uid(),
            gid: meta.gid(),
        };
        let before = sssd_directory_seal("/var/lib/sss/db", &dir, &identity).unwrap();
        std::thread::sleep(Duration::from_millis(10));
        let path = temp.path().join("config.ldb");
        std::fs::write(&path, b"never-read-private-fixture").unwrap();
        assert!(sssd_directory_seal("/var/lib/sss/db", &dir, &identity).is_err());
        assert_eq!(std::fs::read(&path).unwrap(), b"never-read-private-fixture");
        std::fs::remove_file(&path).unwrap();
        let after = sssd_directory_seal("/var/lib/sss/db", &dir, &identity).unwrap();
        assert_ne!(
            before, after,
            "same held directory records creation/removal identity changes"
        );
    }

    #[test]
    fn host_admission_sssd_fixed_tree_rejects_socket_and_link_entries() {
        let temp = tempfile::tempdir().unwrap();
        let dir = File::open(temp.path()).unwrap();
        let meta = dir.metadata().unwrap();
        let identity = SssdIdentity {
            uid: meta.uid(),
            gid: meta.gid(),
        };
        std::os::unix::fs::symlink("/outside", temp.path().join("private")).unwrap();
        assert!(sssd_directory_seal("/var/lib/sss/pipes", &dir, &identity).is_err());
        std::fs::remove_file(temp.path().join("private")).unwrap();
        let _socket = std::os::unix::net::UnixListener::bind(temp.path().join("nss")).unwrap();
        assert!(sssd_directory_seal("/var/lib/sss/pipes", &dir, &identity).is_err());
        assert!(open_sssd_directory("/etc/sssd", &identity).is_err());
    }

    #[test]
    fn host_admission_sssd_enabled_but_inactive_is_not_relabelled_disabled() {
        let value = sssd_test_state();
        validate_sssd_system(&value).unwrap();
        assert_eq!(value.units[0].unit_file_state, "enabled");
        let mut changed = value;
        changed.units[0].unit_file_state = "disabled".into();
        assert!(validate_sssd_system(&changed).is_err());
    }

    #[test]
    fn host_admission_sssd_live_unit_process_cgroup_and_overrides_are_rejected() {
        for mode in 0..6 {
            let mut value = sssd_test_state();
            match mode {
                0 => value.units[0].active_state = "active".into(),
                1 => value.units[0].main_pid = Some(123),
                2 => value.units[1].control_group = "/system.slice/sssd-nss.service".into(),
                3 => value.units[0]
                    .drop_in_paths
                    .push("/run/systemd/system/sssd.service.d/test.conf".into()),
                4 => value.units[0].condition_result = true,
                _ => value.units[0].fragment_path = "/etc/systemd/system/sssd.service".into(),
            }
            assert!(validate_sssd_system(&value).is_err());
        }
    }

    #[test]
    fn host_admission_sssd_system_manager_and_complete_unit_set_are_required() {
        for mode in 0..4 {
            let mut value = sssd_test_state();
            match mode {
                0 => value.manager_pid = 2,
                1 => value.manager_euid = 65534,
                2 => {
                    value.units.pop();
                }
                _ => value.units[1] = value.units[0].clone(),
            }
            assert!(validate_sssd_system(&value).is_err());
        }
    }

    #[test]
    fn host_admission_sssd_complete_nss_rejects_additional_alias_and_group_member() {
        let (inputs, value) = public_fixture();
        public_observation_coverage(&inputs, &value).unwrap();
        let mut alias = value.clone();
        alias.nss_users.push(PublicUser {
            name: "alias".into(),
            uid: 110,
            gid: 500,
        });
        assert!(public_observation_coverage(&inputs, &alias).is_err());
        let mut primary = value.clone();
        primary.nss_users.push(PublicUser {
            name: "other".into(),
            uid: 500,
            gid: 113,
        });
        assert!(public_observation_coverage(&inputs, &primary).is_err());
        let mut member = value.clone();
        member
            .nss_groups
            .iter_mut()
            .find(|g| g.name == "sssd")
            .unwrap()
            .members
            .push("other".into());
        assert!(public_observation_coverage(&inputs, &member).is_err());
        let mut supplemental = value;
        supplemental.nss_groups[0].members.push("sssd".into());
        assert!(public_observation_coverage(&inputs, &supplemental).is_err());
    }

    #[test]
    fn host_admission_sssd_dynamic_memberships_and_provider_shadowing_are_rejected() {
        let (inputs, value) = public_fixture();
        let mut membership = value.clone();
        membership.providers[0].memberships.push(Membership {
            user: "other".into(),
            group: "sssd".into(),
        });
        assert!(public_observation_coverage(&inputs, &membership).is_err());
        let mut shadow = value;
        shadow.providers[0].users.push(PublicUser {
            name: "sssd".into(),
            uid: 110,
            gid: 113,
        });
        assert!(public_observation_coverage(&inputs, &shadow).is_err());
    }

    fn public_fixture() -> (HostInputs, PublicObservation) {
        let users = vec![
            PublicUser {
                name: "root".into(),
                uid: 0,
                gid: 0,
            },
            PublicUser {
                name: "droidloom-test".into(),
                uid: 60001,
                gid: 60001,
            },
            PublicUser {
                name: "sssd".into(),
                uid: 110,
                gid: 113,
            },
        ];
        let groups = vec![
            PublicGroup {
                name: "root".into(),
                gid: 0,
                members: Vec::new(),
            },
            PublicGroup {
                name: "droidloom-test".into(),
                gid: 60001,
                members: Vec::new(),
            },
            PublicGroup {
                name: "sssd".into(),
                gid: 113,
                members: Vec::new(),
            },
        ];
        let services = vec![
            "io.systemd.DynamicUser".into(),
            "org.gnome.DisplayManager".into(),
        ];
        let providers = services
            .iter()
            .map(|service: &String| ProviderRecords {
                service: service.clone(),
                users: Vec::new(),
                groups: Vec::new(),
                memberships: Vec::new(),
            })
            .collect();
        (
            HostInputs {
                seals: Vec::new(),
                users: users.clone(),
                groups: groups.clone(),
                services,
                sssd: InactiveSssd {
                    identity: SssdIdentity { uid: 110, gid: 113 },
                    directories: Vec::new(),
                },
            },
            PublicObservation {
                schema: 2,
                nss_users: users,
                nss_groups: groups,
                providers,
                sssd: sssd_test_state(),
            },
        )
    }
    fn validate_fixture(inputs: &HostInputs, result: &PublicObservation) -> Result<()> {
        let (uids, gids) = ranges();
        validate_public_identities(inputs, result, "droidloom-test", 60001, 60001, uids, gids)
    }

    #[test]
    fn host_admission_dynamic_identity_changes_cannot_hide_behind_same_socket_inode() {
        let (_, first) = public_fixture();
        let mut reordered = first.clone();
        reordered.nss_users.reverse();
        reordered.nss_groups.reverse();
        reordered.providers.reverse();
        assert_eq!(
            canonical_observation(first.clone()).unwrap(),
            canonical_observation(reordered).unwrap()
        );
        let mut changed = first.clone();
        changed.providers[0].users.push(PublicUser {
            name: "fresh-dynamic".into(),
            uid: 61111,
            gid: 61111,
        });
        assert_ne!(
            canonical_observation(first.clone()).unwrap(),
            canonical_observation(changed).unwrap()
        );
        let mut repeated = first;
        repeated.nss_users.push(repeated.nss_users[0].clone());
        assert!(canonical_observation(repeated).is_err());
    }

    #[test]
    fn host_admission_self_fd_iterator_remains_real_during_full_table_inspection() {
        let proc_fd = File::open("/proc/self/fd").unwrap();
        with_directory_names(&proc_fd, 65536, |names, iterator| {
            assert!(names.contains(&iterator.to_string()));
            let target = component(&iterator.to_string())?;
            let fd = unsafe {
                libc::openat(
                    proc_fd.as_raw_fd(),
                    target.as_ptr(),
                    libc::O_PATH | libc::O_CLOEXEC,
                )
            };
            assert!(
                fd >= 0,
                "the enumerated iterator remains open until the consumer finishes"
            );
            let held = unsafe { File::from_raw_fd(fd) };
            assert_eq!(
                Node::of(&held.metadata()?).key(),
                Node::of(&proc_fd.metadata()?).key()
            );
            Ok(())
        })
        .unwrap();
    }

    #[test]
    fn host_admission_kernel_signal_mask_is_restored_on_owned_guard_drop() {
        let read_mask = || {
            let mut value = 0_u64;
            assert_eq!(
                unsafe {
                    libc::syscall(
                        libc::SYS_rt_sigprocmask,
                        libc::SIG_SETMASK,
                        std::ptr::null::<u64>(),
                        &mut value,
                        mem::size_of::<u64>(),
                    )
                },
                0
            );
            value
        };
        let original = read_mask();
        {
            let _guard = KernelSignalMask::block().unwrap();
            assert_ne!(read_mask() & (1_u64 << (libc::SIGUSR1 - 1)), 0);
        }
        assert_eq!(read_mask(), original);
    }

    #[test]
    fn host_admission_pipe_control_descriptors_are_above_stdio() {
        use std::os::unix::process::CommandExt;
        // Close stdio only in this owned child. The production helper must move
        // both pipe endpoints above it; otherwise dup2 would overwrite custody.
        let mut command = std::process::Command::new("/bin/true");
        unsafe {
            command.pre_exec(|| {
                for descriptor in 0..=2 {
                    libc::close(descriptor);
                }
                let (read, write) = match pipe() {
                    Ok(value) => value,
                    Err(_) => child_exit(),
                };
                if read.as_raw_fd() < 3
                    || write.as_raw_fd() < 3
                    || read.as_raw_fd() == write.as_raw_fd()
                {
                    child_exit();
                }
                let sent = [0x5a_u8];
                let mut received = [0_u8];
                if libc::write(write.as_raw_fd(), sent.as_ptr().cast(), 1) != 1
                    || libc::read(read.as_raw_fd(), received.as_mut_ptr().cast(), 1) != 1
                    || received != sent
                {
                    child_exit();
                }
                Ok(())
            });
        }
        assert!(command.status().unwrap().success());
    }

    #[test]
    fn host_admission_provider_grammar_is_explicit() {
        assert!(
            nss_grammar("passwd: files systemd sss\ngroup: files systemd sss\nhosts: files dns\n")
                .is_ok()
        );
        for value in [
            "passwd: files systemd\ngroup: files systemd sss\n",
            "passwd: files systemd sss ldap\ngroup: files systemd sss\n",
            "passwd: files [SUCCESS=return] systemd sss\ngroup: files systemd sss\n",
            "passwd: files systemd sss\npasswd: files systemd sss\ngroup: files systemd sss\n",
        ] {
            assert!(nss_grammar(value).is_err());
        }
    }

    #[test]
    fn host_admission_copies_only_public_files_fields() {
        let (users, groups) = public_files(
            "service:discarded-marker:60001:60001:private-name:/private-home:/private-shell\n",
            "service:discarded-group-marker:60001:\n",
        )
        .unwrap();
        let output = serde_json::to_string(&(users, groups)).unwrap();
        assert!(!output.contains("discarded"));
        assert!(!output.contains("private"));
        assert!(output.contains("60001"));
        assert!(public_files("s:x:4294967295:1::: \n", "s:x:1:\n").is_err());
    }

    #[test]
    fn host_admission_actual_nss_fields_are_not_assumed_contiguous() {
        let mut data = b"padding\0good-name\0discarded\0".to_vec();
        let pointer = unsafe { data.as_ptr().add(8) }.cast();
        assert_eq!(buffer_text(pointer, &data).unwrap(), "good-name");
        assert!(buffer_text(std::ptr::null(), &data).is_err());
        data.fill(b'x');
        assert!(buffer_text(data.as_ptr().cast(), &data).is_err());
    }

    #[test]
    fn host_admission_varlink_terminal_and_continuation_are_distinct() {
        let empty = br#"{"error":"io.systemd.UserDatabase.NoRecordFound"}"#;
        assert!(matches!(reply_frame(empty, 0).unwrap(), (None, false)));
        assert!(reply_frame(empty, 1).is_err());
        let first = br#"{"parameters":{"userName":"a","groupName":"b"},"continues":true}"#;
        assert!(reply_frame(first, 0).unwrap().1);
        let last = br#"{"parameters":{"userName":"a","groupName":"b"}}"#;
        assert!(!reply_frame(last, 1).unwrap().1);
        for error in [
            "EnumerationNotSupported",
            "ServiceNotAvailable",
            "BadService",
            "ConflictingRecordFound",
        ] {
            let value = format!(r#"{{"error":"io.systemd.UserDatabase.{error}"}}"#);
            assert!(reply_frame(value.as_bytes(), 0).is_err());
        }
    }

    #[test]
    fn host_admission_varlink_duplicate_keys_and_nonbool_flags_rejected() {
        for bytes in [
            br#"{"parameters":{},"continues":0}"#.as_slice(),
            br#"{"parameters":{"uid":1,"uid":2}}"#,
            br#"{"parameters":{},"parameters":{}}"#,
            br#"{"error":"io.systemd.UserDatabase.NoRecordFound","continues":true}"#,
            br#"{"error":"io.systemd.UserDatabase.NoRecordFound","parameters":{}}"#,
        ] {
            assert!(reply_frame(bytes, 0).is_err());
        }
        assert!(json_id(&serde_json::json!({"uid":true}), "uid").is_err());
        assert!(json_id(&serde_json::json!({"uid":4294967295_u64}), "uid").is_err());
        assert!(json_id(&serde_json::json!({"uid":3.0}), "uid").is_err());
    }

    #[test]
    fn host_admission_redaction_is_not_a_missing_public_enumeration() {
        let value =
            serde_json::json!({"record":{"userName":"example","uid":7,"gid":8},"incomplete":true});
        let record = public_record(&value).unwrap();
        assert_eq!(json_id(record, "uid").unwrap(), 7);
        assert!(public_record(&serde_json::json!({"record":{},"incomplete":1})).is_err());
        assert!(
            public_record(&serde_json::json!({"record":{"realm":"remote"},"incomplete":true}))
                .is_err()
        );
    }

    #[test]
    fn host_admission_complete_public_identity_join() {
        let (input, observation) = public_fixture();
        assert!(validate_fixture(&input, &observation).is_ok());
    }

    #[test]
    fn host_admission_range_occupancy_in_each_provider_domain_rejected() {
        let (input, base) = public_fixture();
        let mut uid = base.clone();
        uid.providers[0].users.push(PublicUser {
            name: "foreign".into(),
            uid: 200003,
            gid: 44,
        });
        assert!(validate_fixture(&input, &uid).is_err());
        let mut primary_gid = base.clone();
        primary_gid.nss_users.push(PublicUser {
            name: "foreign".into(),
            uid: 77,
            gid: 300003,
        });
        assert!(validate_fixture(&input, &primary_gid).is_err());
        let mut group = base;
        group.providers[1].groups.push(PublicGroup {
            name: "foreign".into(),
            gid: 300004,
            members: Vec::new(),
        });
        assert!(validate_fixture(&input, &group).is_err());
    }

    #[test]
    fn host_admission_memberships_cannot_be_replaced_by_empty_group_members() {
        let (input, mut observation) = public_fixture();
        observation.providers[1].memberships.push(Membership {
            user: "droidloom-test".into(),
            group: "wheel".into(),
        });
        assert!(validate_fixture(&input, &observation).is_err());
        observation.providers[1].memberships = vec![Membership {
            user: "another".into(),
            group: "droidloom-test".into(),
        }];
        assert!(validate_fixture(&input, &observation).is_err());
    }

    #[test]
    fn host_admission_dedicated_principal_must_remain_files_only_and_unshared() {
        let (input, base) = public_fixture();
        let mut value = base.clone();
        value.providers[0].users.push(value.nss_users[1].clone());
        assert!(validate_fixture(&input, &value).is_err());
        let mut value = base.clone();
        value.nss_users.push(PublicUser {
            name: "another".into(),
            uid: 88,
            gid: 60001,
        });
        assert!(validate_fixture(&input, &value).is_err());
        let mut value = base;
        value.nss_groups.push(PublicGroup {
            name: "alias".into(),
            gid: 60001,
            members: Vec::new(),
        });
        assert!(validate_fixture(&input, &value).is_err());
    }

    #[test]
    fn host_admission_provider_set_and_files_coverage_are_required() {
        let (input, mut observation) = public_fixture();
        observation.providers.pop();
        assert!(validate_fixture(&input, &observation).is_err());
        let (input, mut observation) = public_fixture();
        observation.nss_users.remove(0);
        assert!(validate_fixture(&input, &observation).is_err());
    }

    #[test]
    fn host_admission_map_parser_rejects_overflow_and_overlap() {
        assert_eq!(
            parse_map("         0          0 4294967295\n").unwrap(),
            vec![MapLine {
                inner: 0,
                outer: 0,
                count: u32::MAX
            }]
        );
        for value in [
            "0 200000 0\n",
            "0 4294967290 20\n",
            "0 3 7\n2 30 8\n",
            "0 3 7\n20 4 8\n",
            "0 200000 -1\n",
            "0 200000 true\n",
        ] {
            assert!(parse_map(value).is_err());
        }
    }

    #[test]
    fn host_admission_owned_maps_require_exact_monotonic_allow_stages() {
        let (uids, gids) = ranges();
        let uid = parse_map("0 200000 65536\n").unwrap();
        let gid = parse_map("0 300000 65536\n").unwrap();
        assert!(allowed_owned_maps(&[], &[], uids, gids, "allow\n").is_ok());
        assert!(allowed_owned_maps(&uid, &[], uids, gids, "allow\n").is_ok());
        assert!(allowed_owned_maps(&uid, &gid, uids, gids, "allow\n").is_ok());
        assert!(allowed_owned_maps(&[], &gid, uids, gids, "allow\n").is_err());
        assert!(allowed_owned_maps(&uid, &gid, uids, gids, "deny\n").is_err());
        assert!(
            allowed_owned_maps(
                &parse_map("0 200000 65535\n").unwrap(),
                &gid,
                uids,
                gids,
                "allow\n"
            )
            .is_err()
        );
    }

    #[test]
    fn host_admission_all_credential_slots_and_supplementary_groups_are_parsed() {
        let status = "Tgid:\t31\nUid:\t10 11 12 13\nGid:\t20 21 22 23\nGroups:\t42 41\n";
        let value = parse_status(status).unwrap();
        assert_eq!(value.uids, [10, 11, 12, 13]);
        assert_eq!(value.gids, [20, 21, 22, 23]);
        assert_eq!(value.groups, [41, 42]);
        assert!(parse_status(&(status.to_owned() + "Uid:\t1 1 1 1\n")).is_err());
        assert!(parse_status("Uid: 1 1 1 1\nGid: 1 1 1 1\n").is_err());
    }

    fn live_fixture() -> LiveView {
        let namespace = NamespaceKey {
            device: 4,
            inode: 9999,
            kernel_id: 900,
        };
        let task = TaskView {
            credentials: Credentials {
                uids: [1000; 4],
                gids: [1000; 4],
                groups: vec![],
                tgid: 31,
            },
            proc_identity: (9, 31),
            namespace: Some(namespace),
            pid_namespace: None,
            uid_map: parse_map("0 100000 65536\n").unwrap(),
            gid_map: parse_map("0 100000 65536\n").unwrap(),
            setgroups: "deny\n".into(),
        };
        LiveView {
            tasks: [((31, 31, 10), task)].into(),
            referenced_namespaces: [namespace].into(),
        }
    }

    #[test]
    fn host_admission_tree_scope_requires_full_maps_and_exact_held_pid_namespace() {
        let (uids, gids) = ranges();
        let mut task = live_fixture().tasks.values().next().unwrap().clone();
        let keeper = KeeperIdentity {
            pid: 31,
            start_ticks: 10,
            proc_identity: (9, 31),
        };
        let tree_pidns = NamespaceKey {
            device: 4,
            inode: 8111,
            kernel_id: 11,
        };
        task.uid_map.clear();
        task.gid_map.clear();
        task.setgroups = "allow\n".into();
        assert!(validate_owned_task((31, 31, 10), &task, &keeper, None, uids, gids).is_ok());
        assert!(
            validate_owned_task((32, 32, 11), &task, &keeper, Some(tree_pidns), uids, gids)
                .is_err()
        );
        task.uid_map = vec![MapLine {
            inner: 0,
            outer: uids.start,
            count: uids.count,
        }];
        task.pid_namespace = Some(tree_pidns);
        assert!(
            validate_owned_task((32, 32, 11), &task, &keeper, Some(tree_pidns), uids, gids)
                .is_err()
        );
        task.gid_map = vec![MapLine {
            inner: 0,
            outer: gids.start,
            count: gids.count,
        }];
        assert!(validate_owned_task((32, 32, 11), &task, &keeper, None, uids, gids).is_err());
        assert!(
            validate_owned_task((32, 32, 11), &task, &keeper, Some(tree_pidns), uids, gids).is_ok()
        );
        task.pid_namespace = Some(NamespaceKey {
            device: 4,
            inode: 8112,
            kernel_id: 12,
        });
        assert!(
            validate_owned_task((32, 32, 11), &task, &keeper, Some(tree_pidns), uids, gids)
                .is_err()
        );
        task.setgroups = "deny\n".into();
        assert!(
            validate_owned_task((31, 31, 10), &task, &keeper, Some(tree_pidns), uids, gids)
                .is_err()
        );
    }

    #[test]
    fn host_admission_keeper_numeric_pid_never_replaces_proc_and_start_identity() {
        let (uids, gids) = ranges();
        let mut task = live_fixture().tasks.values().next().unwrap().clone();
        let keeper = KeeperIdentity {
            pid: 31,
            start_ticks: 10,
            proc_identity: (9, 31),
        };
        task.uid_map.clear();
        task.gid_map.clear();
        task.setgroups = "allow\n".into();
        assert!(validate_owned_task((31, 31, 11), &task, &keeper, None, uids, gids).is_err());
        task.proc_identity = (9, 32);
        assert!(validate_owned_task((31, 31, 10), &task, &keeper, None, uids, gids).is_err());
        assert!(validate_owned_task((31, 32, 10), &task, &keeper, None, uids, gids).is_err());
    }

    #[test]
    fn host_admission_foreign_disjoint_maps_are_observations_not_authority() {
        let (uids, gids) = ranges();
        assert!(validate_live_view(&live_fixture(), uids, gids, 60001, 60001, None).is_ok());
    }

    #[test]
    fn host_admission_retained_namespace_without_observable_map_is_rejected() {
        let mut view = live_fixture();
        view.referenced_namespaces.insert(NamespaceKey {
            device: 4,
            inode: 10000,
            kernel_id: 901,
        });
        let (uids, gids) = ranges();
        assert!(validate_live_view(&view, uids, gids, 60001, 60001, None).is_err());
    }

    #[test]
    fn host_admission_foreign_empty_overlap_and_live_groups_fail() {
        let (uids, gids) = ranges();
        let mut view = live_fixture();
        view.tasks.values_mut().next().unwrap().uid_map.clear();
        assert!(validate_live_view(&view, uids, gids, 60001, 60001, None).is_err());
        let mut view = live_fixture();
        view.tasks.values_mut().next().unwrap().uid_map = parse_map("0 199999 2\n").unwrap();
        assert!(validate_live_view(&view, uids, gids, 60001, 60001, None).is_err());
        let mut view = live_fixture();
        view.tasks
            .values_mut()
            .next()
            .unwrap()
            .credentials
            .groups
            .push(300001);
        assert!(validate_live_view(&view, uids, gids, 60001, 60001, None).is_err());
    }

    #[test]
    fn host_admission_mountinfo_paths_cannot_escape_held_root() {
        assert_eq!(mount_unescape("/run/a\\040b").unwrap(), "/run/a b");
        assert!(mount_unescape("/run/../outside").is_err());
        assert!(mount_unescape("relative").is_err());
        assert!(mount_unescape("/bad\\999").is_err());
    }

    #[test]
    fn host_admission_actual_pipe_partial_and_oversize_are_not_complete() {
        let (mut read, mut write) = pipe().unwrap();
        let mut output = Vec::new();
        let mut eof = false;
        write.write_all(b"abc").unwrap();
        drain_pipe(&mut read, &mut output, 3, &mut eof).unwrap();
        assert_eq!(output, b"abc");
        assert!(!eof);
        write.write_all(b"d").unwrap();
        assert!(drain_pipe(&mut read, &mut output, 3, &mut eof).is_err());
    }

    #[test]
    fn host_admission_actual_directory_fd_does_not_follow_symlink_metadata() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("target"), b"original").unwrap();
        std::os::unix::fs::symlink("target", temp.path().join("link")).unwrap();
        let dir = File::open(temp.path()).unwrap();
        let names = directory_names(&dir, 4).unwrap();
        assert_eq!(names, ["link", "target"]);
        assert_eq!(
            stat_at(&dir, "link").unwrap().mode() & libc::S_IFMT,
            libc::S_IFLNK
        );
        assert!(open_at(&dir, "link", libc::O_RDONLY).is_err());
        assert!(open_at(&dir, "../outside", libc::O_RDONLY).is_err());
    }

    #[test]
    fn host_admission_hidden_worker_rejects_normal_caller_without_changing_it() {
        assert_ne!(
            unsafe { libc::getuid() },
            65534,
            "this normal control requires the normal build UID"
        );
        let before = unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) };
        assert!(run_nss_observation_worker().is_err());
        assert_eq!(before, unsafe {
            libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0)
        });
    }

    #[test]
    fn host_admission_real_child_cannot_fork_under_worker_filter() {
        use std::os::unix::process::CommandExt;
        let mut filter = no_children_filter(false);
        let mut command = std::process::Command::new("/bin/sh");
        command.args(["-c", "true & wait"]);
        unsafe {
            command.pre_exec(move || {
                if libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 {
                    return Err(io::Error::last_os_error());
                }
                let program = libc::sock_fprog {
                    len: filter.len() as u16,
                    filter: filter.as_mut_ptr(),
                };
                if libc::prctl(libc::PR_SET_SECCOMP, 2, &program as *const libc::sock_fprog) != 0 {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        let output = command.output().unwrap();
        assert!(!output.status.success());
        assert!(output.stdout.len() < 1024 && output.stderr.len() < 1024);
    }
}
