//! Read-only custody of one installed native qualification unit.
//!
//! This observes the actual manager and cgroup; it is not a production
//! HostPeerIssuer, a cell admission, or permission to run an arbitrary command.
use super::{BoundProcess, current_cgroup_parent, gallery_resources, invalid};
use crate::control::NativeApplicationSourceLocks;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::ffi::{CStr, CString};
use std::fs::{self, File, OpenOptions};
use std::io;
use std::marker::PhantomData;
use std::os::fd::{AsFd, AsRawFd, BorrowedFd, FromRawFd};
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::time::{Duration, Instant};

#[path = "application_leaf_unit_bus.rs"]
mod bus;
type Result<T, E = io::Error> = std::result::Result<T, E>;
// The fixed Linux socket option used by the unchanged production endpoint.
const SO_PEERPIDFD: libc::c_int = 77;
fn require(ok: bool, why: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(invalid(why)) }
}

const PROPERTIES: &str = "Id,LoadState,ActiveState,SubState,InvocationID,MainPID,ControlGroup,FragmentPath,DropInPaths,ExecMainStartTimestampMonotonic,KillMode,KillSignal,FinalKillSignal,SendSIGKILL,TimeoutStopFailureMode,TimeoutStopUSec,RuntimeMaxUSec,Restart,CPUQuotaPerSecUSec,CPUQuotaPeriodUSec,MemoryMax,MemorySwapMax,TasksMax,CPUAffinity,LimitCORE,Type,User,Group";

/// Only the two current resource-sensitive application routes are supported.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum OwnedLeafProfile {
    CalendarReminder,
    Gallery,
}

impl OwnedLeafProfile {
    /// Parse a finite installed-entry profile, never arbitrary resource values.
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "calendar-reminder" => Ok(Self::CalendarReminder),
            "gallery" => Ok(Self::Gallery),
            _ => {
                Err("only current Calendar reminder or Gallery unit profiles are supported".into())
            }
        }
    }
    /// Stable profile name used by the root-owned request directory.
    pub fn name(self) -> &'static str {
        match self {
            Self::CalendarReminder => "calendar-reminder",
            Self::Gallery => "gallery",
        }
    }
    /// Fixed installed unit template; no caller supplies a unit name.
    pub fn template(self) -> &'static str {
        match self {
            Self::CalendarReminder => "droidloom-native-calendar@.service",
            Self::Gallery => "droidloom-native-gallery@.service",
        }
    }
    /// The complete controller budget includes the unchanged native PM bookends.
    pub fn controller_seconds(self) -> u64 {
        match self {
            Self::CalendarReminder => 1200,
            Self::Gallery => 2400,
        }
    }
    fn resources(self) -> gallery_resources::Profile {
        match self {
            Self::CalendarReminder => gallery_resources::Profile::CalendarReminder,
            Self::Gallery => gallery_resources::Profile::Gallery,
        }
    }
    fn memory(self) -> u64 {
        match self {
            Self::CalendarReminder => 536_870_912,
            Self::Gallery => 2_147_483_648,
        }
    }
    fn quota(self) -> u64 {
        match self {
            Self::CalendarReminder => 500_000,
            Self::Gallery => 2_000_000,
        }
    }
    fn cpus(self) -> &'static [usize] {
        match self {
            Self::CalendarReminder => &[20],
            Self::Gallery => &[20, 21],
        }
    }
    fn instance(self, sha: &str) -> Result<String, String> {
        if sha.len() != 64
            || !sha
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err("exact lower-case content-addressed plan hash required".into());
        }
        Ok(self.template().replace("@.", &format!("@{sha}.")))
    }
}

fn identity(file: &File) -> io::Result<[u64; 9]> {
    let m = file.metadata()?;
    let ns = |s: i64, n: i64| {
        u64::try_from(i128::from(s) * 1_000_000_000 + i128::from(n))
            .map_err(|_| invalid("negative installed tool timestamp"))
    };
    Ok([
        m.dev(),
        m.ino(),
        u64::from(m.mode()),
        u64::from(m.uid()),
        u64::from(m.gid()),
        m.nlink(),
        m.len(),
        ns(m.mtime(), m.mtime_nsec())?,
        ns(m.ctime(), m.ctime_nsec())?,
    ])
}

fn digest(file: &File, size: u64) -> io::Result<String> {
    if size == 0 || size > 16 * 1024 * 1024 {
        return Err(invalid("bounded installed manager executable required"));
    }
    let mut data = vec![0; size as usize];
    file.read_exact_at(&mut data, 0)?;
    if file.read_at(&mut [0_u8; 1], size)? != 0 {
        return Err(invalid("installed manager executable grew"));
    }
    Ok(hex::encode(Sha256::digest(data)))
}

struct Tool {
    path: &'static str,
    file: File,
    identity: [u64; 9],
    sha: String,
    parents: Vec<(PathBuf, File, [u64; 6])>,
}
impl Tool {
    fn open(path: &'static str) -> io::Result<Self> {
        if Path::new(path).canonicalize()? != Path::new(path) {
            return Err(invalid("canonical installed executable required"));
        }
        let mut parents = Vec::new();
        for parent in Path::new(path)
            .parent()
            .ok_or_else(|| invalid("installed executable parent absent"))?
            .ancestors()
        {
            let m = fs::symlink_metadata(parent)?;
            if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {
                return Err(invalid("root-owned installed executable parents required"));
            }
            let file = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(parent)?;
            let pin: [u64; 6] = identity(&file)?[..6]
                .try_into()
                .map_err(|_| invalid("parent identity"))?;
            parents.push((parent.to_path_buf(), file, pin));
        }
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(path)?;
        let identity = identity(&file)?;
        if identity[2] & 0o170000 != 0o100000
            || identity[2] & 0o111 == 0
            || identity[2] & 0o6022 != 0
            || identity[3..6] != [0, 0, 1]
        {
            return Err(invalid(
                "ordinary root-owned installed manager executable required",
            ));
        }
        let result = Self {
            path,
            sha: digest(&file, identity[6])?,
            file,
            identity,
            parents,
        };
        result.guard()?;
        Ok(result)
    }
    fn guard(&self) -> io::Result<()> {
        for (path, file, pin) in &self.parents {
            let named = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(path)?;
            if identity(file)?[..6] != *pin
                || identity(&named)?[..6] != *pin
                || fs::symlink_metadata(path)?.file_type().is_symlink()
            {
                return Err(invalid("held installed executable parent changed"));
            }
        }
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(self.path)?;
        if identity(&named)? != self.identity
            || identity(&self.file)? != self.identity
            || digest(&self.file, self.identity[6])? != self.sha
        {
            return Err(invalid("held installed manager executable changed"));
        }
        Ok(())
    }
}

fn affinity(bytes: &[u8]) -> Vec<usize> {
    bytes
        .iter()
        .enumerate()
        .flat_map(|(n, b)| {
            (0..8).filter_map(move |bit| {
                if b & (1 << bit) != 0 {
                    Some(n * 8 + bit)
                } else {
                    None
                }
            })
        })
        .collect()
}

fn actual_affinity(profile: OwnedLeafProfile) -> Result<(), String> {
    let mut mask = std::mem::MaybeUninit::<libc::cpu_set_t>::zeroed();
    // SAFETY: mask is valid writable cpu_set_t storage for this actual process.
    if unsafe {
        libc::sched_getaffinity(0, std::mem::size_of::<libc::cpu_set_t>(), mask.as_mut_ptr())
    } != 0
    {
        return Err(io::Error::last_os_error().to_string());
    }
    // SAFETY: successful sched_getaffinity initialized the cpu_set_t.
    let mask = unsafe { mask.assume_init() };
    let actual: Vec<_> = (0..libc::CPU_SETSIZE as usize)
        .filter(|cpu|
        // SAFETY: cpu remains within the cpu_set_t range.
        unsafe {libc::CPU_ISSET(*cpu,&mask)})
        .collect();
    if actual != profile.cpus() {
        return Err(
            "actual native controller scheduler affinity differs from its fixed unit profile"
                .into(),
        );
    }
    Ok(())
}

fn validate(
    values: &BTreeMap<String, String>,
    profile: OwnedLeafProfile,
    unit: &str,
    pid: u32,
) -> Result<(), String> {
    let text = |name: &str| {
        values
            .get(name)
            .map(String::as_str)
            .ok_or_else(|| format!("missing manager property {name}"))
    };
    for (key, want) in [
        ("Id", unit),
        ("LoadState", "loaded"),
        ("ActiveState", "active"),
        ("SubState", "running"),
        ("Type", "exec"),
        ("User", "root"),
        ("Group", "root"),
        ("Restart", "no"),
        ("KillMode", "control-group"),
        ("KillSignal", "15"),
        ("FinalKillSignal", "9"),
        ("SendSIGKILL", "yes"),
        ("TimeoutStopFailureMode", "terminate"),
        ("MemorySwapMax", "0"),
        ("TasksMax", "64"),
        ("LimitCORE", "0"),
    ] {
        if text(key)? != want {
            return Err(format!("effective owned unit {key} differs"));
        }
    }
    if text("MainPID")? != pid.to_string()
        || text("ControlGroup")? != format!("/system.slice/{unit}")
        || text("FragmentPath")? != format!("/usr/lib/systemd/system/{}", profile.template())
        || text("MemoryMax")? != profile.memory().to_string()
        || text("RuntimeMaxUSec")? != (profile.controller_seconds() * 1_000_000).to_string()
        || text("TimeoutStopUSec")? != "180000000"
        || text("CPUQuotaPerSecUSec")? != profile.quota().to_string()
        || text("CPUQuotaPeriodUSec")? != "100000"
    {
        return Err(
            "actual single controller identity or fixed effective unit budget differs".into(),
        );
    }
    let invocation = text("InvocationID")?;
    if invocation.len() != 32
        || !invocation
            .bytes()
            .all(|x| x.is_ascii_digit() || (b'a'..=b'f').contains(&x))
        || invocation.bytes().all(|x| x == b'0')
        || text("ExecMainStartTimestampMonotonic")?
            .parse::<u64>()
            .ok()
            .filter(|x| *x > 0)
            .is_none()
    {
        return Err("real nonempty systemd invocation and start instant required".into());
    }
    let affinity = profile
        .cpus()
        .iter()
        .map(usize::to_string)
        .collect::<Vec<_>>()
        .join(" ");
    if text("CPUAffinity")? != affinity {
        return Err("effective manager CPU affinity differs from its fixed profile".into());
    }
    Ok(())
}

fn actual_properties(
    unit: &bus::Properties,
    service: &bus::Properties,
    invocation: &bus::Invocation,
    profile: OwnedLeafProfile,
    pid: u32,
) -> Result<BTreeMap<String, String>, String> {
    use bus::Value as V;
    for key in ["Transient", "NeedDaemonReload"] {
        if unit.get(key) != Some(&V::Boolean(false)) {
            return Err(format!("actual installed unit {key} must be false"));
        }
    }
    if unit.get("InvocationID") != Some(&V::Bytes(invocation.id.to_vec())) {
        return Err("actual manager invocation property differs from PIDFD lookup".into());
    }
    let prefix = profile
        .template()
        .split_once('@')
        .ok_or("fixed unit template missing instance")?
        .0;
    let sha = invocation
        .unit
        .strip_prefix(&format!("{prefix}@"))
        .and_then(|s| s.strip_suffix(".service"))
        .ok_or("actual instance differs from fixed unit template")?;
    if profile.instance(sha)? != invocation.unit {
        return Err("actual owned instance hash differs".into());
    }
    let commands = match service.get("ExecStartEx") {
        Some(V::Commands(v)) => v,
        _ => return Err("actual manager omitted typed ExecStartEx".into()),
    };
    for key in [
        "ExecConditionEx",
        "ExecStartPreEx",
        "ExecStartPostEx",
        "ExecReloadEx",
        "ExecStopEx",
        "ExecStopPostEx",
    ] {
        if service.get(key) != Some(&V::Commands(Vec::new())) {
            return Err(format!(
                "actual owned unit {key} must contain no additional command"
            ));
        }
    }
    let [command] = commands.as_slice() else {
        return Err("one actual native ExecStart required".into());
    };
    let argv = vec![
        "/usr/bin/droidloom-applications".to_owned(),
        "--owned-leaf-profile".into(),
        profile.name().into(),
        "--owned-leaf-plan-sha256".into(),
        sha.into(),
    ];
    if command.path != "/usr/bin/droidloom-applications"
        || command.arguments != argv
        || !command.flags.is_empty()
        || command.pid != pid
        || command.started[1] == 0
        || command.exited != [0, 0]
        || command.code != 0
        || command.status != 0
    {
        return Err("actual manager execution differs from the single fixed native plan".into());
    }
    let mut values = BTreeMap::new();
    for key in PROPERTIES.split(',') {
        let source = if [
            "Id",
            "LoadState",
            "ActiveState",
            "SubState",
            "InvocationID",
            "FragmentPath",
            "DropInPaths",
        ]
        .contains(&key)
        {
            unit
        } else {
            service
        };
        let value = source
            .get(key)
            .ok_or_else(|| format!("actual manager omitted required {key}"))?;
        let text = match (key, value) {
            ("InvocationID", V::Bytes(bytes)) if bytes.len() == 16 => hex::encode(bytes),
            ("CPUAffinity", V::Bytes(bytes)) => {
                let cpus = affinity(bytes);
                if cpus != profile.cpus() {
                    return Err(
                        "manager affinity bitmap differs from exact installed profile".into(),
                    );
                }
                cpus.iter()
                    .map(usize::to_string)
                    .collect::<Vec<_>>()
                    .join(" ")
            }
            ("DropInPaths", V::Strings(paths)) => {
                serde_json::to_string(paths).map_err(|e| e.to_string())?
            }
            (
                "TimeoutStopUSec" | "RuntimeMaxUSec" | "CPUQuotaPerSecUSec" | "CPUQuotaPeriodUSec",
                V::U64(n),
            ) => n.to_string(),
            (
                "ExecMainStartTimestampMonotonic"
                | "MemoryMax"
                | "MemorySwapMax"
                | "TasksMax"
                | "LimitCORE",
                V::U64(n),
            ) => n.to_string(),
            ("MainPID", V::U32(n)) => n.to_string(),
            ("KillSignal" | "FinalKillSignal", V::I32(n)) => n.to_string(),
            ("SendSIGKILL", V::Boolean(v)) => if *v { "yes" } else { "no" }.into(),
            (
                "Id"
                | "LoadState"
                | "ActiveState"
                | "SubState"
                | "ControlGroup"
                | "FragmentPath"
                | "KillMode"
                | "Restart"
                | "Type"
                | "User"
                | "Group"
                | "TimeoutStopFailureMode",
                V::Text(text),
            ) => text.clone(),
            _ => return Err(format!("actual manager {key} has a different wire type")),
        };
        values.insert(key.to_owned(), text);
    }
    Ok(values)
}

struct Connection {
    bus: bus::PrivateBus,
    file: File,
    peer: File,
    listener: File,
    listener_identity: [u64; 9],
    parents: Vec<(PathBuf, File, [u64; 6])>,
}

impl Connection {
    fn open(deadline: Instant) -> Result<Self, String> {
        const PATH: &str = "/run/systemd/private";
        if Path::new(PATH).canonicalize().map_err(|e| e.to_string())? != Path::new(PATH) {
            return Err("canonical private manager endpoint required".into());
        }
        let mut parents = Vec::new();
        for path in ["/", "/run", "/run/systemd"] {
            let file = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(path)
                .map_err(|e| e.to_string())?;
            let pin: [u64; 6] = identity(&file).map_err(|e| e.to_string())?[..6]
                .try_into()
                .map_err(|_| "manager parent identity")?;
            if pin[3..5] != [0, 0] || pin[2] & 0o022 != 0 {
                return Err("private manager parent is not root-owned".into());
            }
            parents.push((PathBuf::from(path), file, pin));
        }
        let listener = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(PATH)
            .map_err(|e| e.to_string())?;
        let listener_identity = identity(&listener).map_err(|e| e.to_string())?;
        if listener_identity[2] & 0o170000 != 0o140000
            || listener_identity[3..6] != [0, 0, 1]
            || listener_identity[2] & 0o022 != 0
        {
            return Err("actual root private manager socket required".into());
        }
        // SAFETY: socket has no borrowed pointers and returns a fresh owned FD.
        let fd = unsafe {
            libc::socket(
                libc::AF_UNIX,
                libc::SOCK_STREAM | libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC,
                0,
            )
        };
        if fd < 0 {
            return Err(io::Error::last_os_error().to_string());
        }
        // SAFETY: fd was just allocated above and is owned exactly once.
        let file = unsafe { File::from_raw_fd(fd) };
        // SAFETY: a zeroed sockaddr_un is valid before setting family/path.
        let mut address: libc::sockaddr_un = unsafe { std::mem::zeroed() };
        address.sun_family = libc::AF_UNIX as libc::sa_family_t;
        let path = b"/run/systemd/private\0";
        for (to, from) in address.sun_path.iter_mut().zip(path) {
            *to = *from as libc::c_char;
        }
        let length = std::mem::offset_of!(libc::sockaddr_un, sun_path) + path.len();
        // SAFETY: address is initialized and length covers only its fixed path.
        // Nonblocking local connect fails closed if the manager queue is busy.
        if unsafe {
            libc::connect(
                file.as_raw_fd(),
                (&address as *const libc::sockaddr_un).cast(),
                length as libc::socklen_t,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().to_string());
        }
        check_peer(&file)?;
        let mut peer_fd: libc::c_int = -1;
        let mut size = std::mem::size_of::<libc::c_int>() as libc::socklen_t;
        // SAFETY: the fixed socket option writes one owned peer PIDFD.
        if unsafe {
            libc::getsockopt(
                file.as_raw_fd(),
                libc::SOL_SOCKET,
                SO_PEERPIDFD,
                (&mut peer_fd as *mut libc::c_int).cast(),
                &mut size,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().to_string());
        }
        if peer_fd < 0 {
            return Err("manager did not return its actual peer PIDFD".into());
        }
        // SAFETY: successful SO_PEERPIDFD returned a newly owned descriptor.
        let peer = unsafe { File::from_raw_fd(peer_fd) };
        if size as usize != std::mem::size_of::<libc::c_int>() {
            return Err("manager peer PIDFD size differs".into());
        }
        // SAFETY: F_GETFD reads flags of this owned peer descriptor.
        let flags = unsafe { libc::fcntl(peer.as_raw_fd(), libc::F_GETFD) };
        if flags < 0 || flags & libc::FD_CLOEXEC == 0 {
            return Err("actual peer PIDFD must be close-on-exec".into());
        }
        let bus = bus::PrivateBus::from_authenticated_socket(&file, deadline)
            .map_err(|e| e.to_string())?;
        let result = Self {
            bus,
            file,
            peer,
            listener,
            listener_identity,
            parents,
        };
        result.guard()?;
        Ok(result)
    }
    fn guard(&self) -> Result<(), String> {
        for (path, file, pin) in &self.parents {
            let named = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(path)
                .map_err(|e| e.to_string())?;
            if identity(file).map_err(|e| e.to_string())?[..6] != *pin
                || identity(&named).map_err(|e| e.to_string())?[..6] != *pin
                || fs::symlink_metadata(path)
                    .map_err(|e| e.to_string())?
                    .file_type()
                    .is_symlink()
            {
                return Err("held private manager endpoint parent changed".into());
            }
        }
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open("/run/systemd/private")
            .map_err(|e| e.to_string())?;
        if identity(&named).map_err(|e| e.to_string())? != self.listener_identity
            || identity(&self.listener).map_err(|e| e.to_string())? != self.listener_identity
        {
            return Err("held manager socket inode changed".into());
        }
        check_peer(&self.file)?;
        let mut poll = libc::pollfd {
            fd: self.peer.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        // SAFETY: poll points to one valid descriptor record; zero never blocks.
        if unsafe { libc::poll(&mut poll, 1, 0) } != 0 || poll.revents != 0 {
            return Err("actual private manager peer retired".into());
        }
        let info = super::bounded_text(
            File::open(format!("/proc/self/fdinfo/{}", self.peer.as_raw_fd()))
                .map_err(|e| e.to_string())?,
            4096,
        )
        .map_err(|e| e.to_string())?;
        let pids: Vec<_> = info
            .lines()
            .filter_map(|s| s.strip_prefix("Pid:"))
            .map(str::trim)
            .collect();
        if pids != ["1"] {
            return Err("actual private manager peer PIDFD is not the held host PID1".into());
        }
        Ok(())
    }
}

fn check_peer(file: &File) -> Result<(), String> {
    let mut peer = std::mem::MaybeUninit::<libc::ucred>::uninit();
    let mut size = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    // SAFETY: peer points to correctly sized writable ucred storage.
    if unsafe {
        libc::getsockopt(
            file.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            peer.as_mut_ptr().cast(),
            &mut size,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().to_string());
    }
    if size as usize != std::mem::size_of::<libc::ucred>() {
        return Err("private manager peer credential size differs".into());
    }
    // SAFETY: the successful exact-sized getsockopt initialized peer.
    let peer = unsafe { peer.assume_init() };
    if (peer.pid, peer.uid, peer.gid) != (1, 0, 0) {
        return Err("actual private query peer must be host PID1 root".into());
    }
    Ok(())
}

/// An observation of one actual root controller, without Android authority.
pub struct NativeOwnedLeafUnit<'a> {
    locks: &'a NativeApplicationSourceLocks,
    profile: OwnedLeafProfile,
    unit: String,
    current: BoundProcess,
    manager: BoundProcess,
    manager_exe: Tool,
    manager_actual_exe: File,
    namespaces: Vec<(&'static str, File, File)>,
    group: File,
    group_path: PathBuf,
    budget: gallery_resources::Scope,
    connection: Connection,
    invocation: bus::Invocation,
    values: BTreeMap<String, String>,
}

impl<'a> NativeOwnedLeafUnit<'a> {
    /// Read the actual current unit and fixed resource profile before any leaf.
    pub fn capture(
        profile: OwnedLeafProfile,
        plan_sha: &str,
        locks: &'a NativeApplicationSourceLocks,
    ) -> Result<Self, String> {
        locks.validate().map_err(|e| e.to_string())?;
        let unit = profile.instance(plan_sha)?;
        let group_path = current_cgroup_parent().map_err(|e| e.to_string())?;
        if group_path != PathBuf::from(format!("/sys/fs/cgroup/system.slice/{unit}")) {
            return Err("native controller is not in its exact owned systemd unit".into());
        }
        let current = BoundProcess::capture(std::process::id()).map_err(|e| e.to_string())?;
        let manager = BoundProcess::capture(1).map_err(|e| e.to_string())?;
        let mut namespaces = Vec::new();
        for name in [
            "ns/mnt",
            "ns/user",
            "ns/pid",
            "ns/cgroup",
            "ns/net",
            "ns/ipc",
            "ns/uts",
        ] {
            let current_ns = current.open(name, false).map_err(|e| e.to_string())?;
            let manager_ns = manager.open(name, false).map_err(|e| e.to_string())?;
            if !super::same_file(&current_ns, &manager_ns).map_err(|e| e.to_string())? {
                return Err("owned native unit must remain in the host manager namespaces".into());
            }
            namespaces.push((name, current_ns, manager_ns));
        }
        let group = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&group_path)
            .map_err(|e| e.to_string())?;
        let mut fs_type = std::mem::MaybeUninit::<libc::statfs>::uninit();
        // SAFETY: group is held and the output points to correctly sized storage.
        if unsafe { libc::fstatfs(group.as_raw_fd(), fs_type.as_mut_ptr()) } != 0 {
            return Err(io::Error::last_os_error().to_string());
        }
        // SAFETY: successful fstatfs initialized the output.
        if unsafe { fs_type.assume_init() }.f_type != libc::CGROUP2_SUPER_MAGIC {
            return Err("actual owned cgroup v2 required".into());
        }
        let budget = gallery_resources::Scope::capture(&group_path, &group, profile.resources())
            .map_err(|e| e.to_string())?;
        gallery_resources::require_original_cpu_available().map_err(|e| e.to_string())?;
        let manager_exe = Tool::open("/usr/lib/systemd/systemd").map_err(|e| e.to_string())?;
        let manager_actual_exe = manager.open("exe", false).map_err(|e| e.to_string())?;
        if manager.identity.comm != "systemd"
            || identity(&manager_actual_exe).map_err(|e| e.to_string())? != manager_exe.identity
        {
            return Err("actual live PID1 executable differs from installed systemd".into());
        }
        actual_affinity(profile)?;
        let deadline = Instant::now() + Duration::from_secs(15);
        let connection = Connection::open(deadline)?;
        let invocation = connection
            .bus
            .invocation(current.pidfd.as_fd(), deadline)
            .map_err(|e| e.to_string())?;
        if invocation.unit != unit {
            return Err("actual manager PIDFD lookup returned a different unit".into());
        }
        let mut result = Self {
            locks,
            profile,
            unit,
            current,
            manager,
            manager_exe,
            manager_actual_exe,
            namespaces,
            group,
            group_path,
            budget,
            connection,
            invocation,
            values: BTreeMap::new(),
        };
        result.values = result.query()?;
        result.guard()?;
        Ok(result)
    }

    fn namespace_guard(&self) -> Result<(), String> {
        for (name, current, manager) in &self.namespaces {
            let current_named = self.current.open(name, false).map_err(|e| e.to_string())?;
            let manager_named = self.manager.open(name, false).map_err(|e| e.to_string())?;
            if !super::same_file(current, manager).map_err(|e| e.to_string())?
                || !super::same_file(current, &current_named).map_err(|e| e.to_string())?
                || !super::same_file(manager, &manager_named).map_err(|e| e.to_string())?
            {
                return Err("actual native or manager host namespace changed".into());
            }
        }
        Ok(())
    }

    fn query(&self) -> Result<BTreeMap<String, String>, String> {
        let deadline = Instant::now() + Duration::from_secs(15);
        // SAFETY: these identity reads take no pointers and have no side effects.
        if unsafe {
            (
                libc::getuid(),
                libc::geteuid(),
                libc::getgid(),
                libc::getegid(),
            )
        } != (0, 0, 0, 0)
        {
            return Err("owned native controller must retain its actual root identity".into());
        }
        self.locks.validate().map_err(|e| e.to_string())?;
        self.current.validate().map_err(|e| e.to_string())?;
        self.manager.validate().map_err(|e| e.to_string())?;
        self.namespace_guard()?;
        self.manager_exe.guard().map_err(|e| e.to_string())?;
        if identity(&self.manager_actual_exe).map_err(|e| e.to_string())?
            != self.manager_exe.identity
            || identity(&self.manager.open("exe", false).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?
                != self.manager_exe.identity
        {
            return Err("actual held manager executable changed".into());
        }
        self.budget.validate().map_err(|e| e.to_string())?;
        actual_affinity(self.profile)?;
        self.connection.guard()?;
        let invocation = self
            .connection
            .bus
            .invocation(self.current.pidfd.as_fd(), deadline)
            .map_err(|e| e.to_string())?;
        if invocation != self.invocation {
            return Err("actual manager invocation generation changed".into());
        }
        let unit = self
            .connection
            .bus
            .properties(&invocation, bus::Interface::Unit, deadline)
            .map_err(|e| e.to_string())?;
        let service = self
            .connection
            .bus
            .properties(&invocation, bus::Interface::Service, deadline)
            .map_err(|e| e.to_string())?;
        let values = actual_properties(
            &unit,
            &service,
            &invocation,
            self.profile,
            self.current.identity.pid,
        )?;
        if self
            .connection
            .bus
            .invocation(self.current.pidfd.as_fd(), deadline)
            .map_err(|e| e.to_string())?
            != invocation
        {
            return Err("manager invocation changed during its complete property read".into());
        }
        self.connection.guard()?;
        actual_affinity(self.profile)?;
        self.current.validate().map_err(|e| e.to_string())?;
        self.manager.validate().map_err(|e| e.to_string())?;
        self.namespace_guard()?;
        self.manager_exe.guard().map_err(|e| e.to_string())?;
        self.budget.validate().map_err(|e| e.to_string())?;
        validate(&values, self.profile, &self.unit, self.current.identity.pid)?;
        if Instant::now() >= deadline {
            return Err("actual owned unit observation exceeded its deadline".into());
        }
        Ok(values)
    }

    /// Re-query effective manager properties after the original leaf retires.
    pub fn guard(&self) -> Result<(), String> {
        if std::process::id() != self.current.identity.pid
            || current_cgroup_parent().map_err(|e| e.to_string())? != self.group_path
        {
            return Err("owned unit controller changed process or cgroup".into());
        }
        if self.query()? != self.values {
            return Err("effective unit invocation or properties changed".into());
        }
        let procs = super::bounded_text(
            super::open_at(self.group.as_raw_fd(), c"cgroup.procs", libc::O_RDONLY)
                .map_err(|e| e.to_string())?,
            4096,
        )
        .map_err(|e| e.to_string())?;
        if procs.lines().collect::<Vec<_>>() != [self.current.identity.pid.to_string()] {
            return Err("owned unit contains another direct controller".into());
        }
        if fs::read_dir(&self.group_path)
            .map_err(|e| e.to_string())?
            .any(|entry| entry.map_or(true, |e| e.file_type().map_or(true, |t| t.is_dir())))
        {
            return Err("owned unit still contains an unretired nested group".into());
        }
        Ok(())
    }

    /// Return previously checked actual metadata; this carries no acceptance.
    pub fn observation(&self) -> Value {
        json!({"schema":"droidloom-owned-native-leaf-unit-observation-v1","profile":self.profile.name(),
            "unit":self.unit,"properties":self.values,"cgroup":self.group_path,
            "controller_pid":self.current.identity.pid,"controller_start_ticks":self.current.identity.start_ticks,
            "manager_pid":self.manager.identity.pid,"manager_start_ticks":self.manager.identity.start_ticks,
            "manager_executable":{"path":self.manager_exe.path,"bytes":self.manager_exe.identity[6],"sha256":self.manager_exe.sha,"f9":self.manager_exe.identity},
            "private_manager_endpoint":{"path":"/run/systemd/private","f9":self.connection.listener_identity,
                "peer_pid":1,"peer_uid":0,"peer_gid":0,"actual_peer_pidfd_held":true},
            "runtime_qualified":false,"production_ready":false,"whole_app_business_accepted":false})
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manager_fixture(
        profile: OwnedLeafProfile,
    ) -> (bus::Properties, bus::Properties, bus::Invocation) {
        use bus::Value as V;
        let sha = "a".repeat(64);
        let invocation = bus::Invocation {
            path: "/org/freedesktop/systemd1/unit/fixture".into(),
            unit: profile.instance(&sha).unwrap(),
            id: [1; 16],
        };
        let mut unit = bus::Properties::new();
        for (key, value) in [
            ("Id", invocation.unit.clone()),
            ("LoadState", "loaded".into()),
            ("ActiveState", "active".into()),
            ("SubState", "running".into()),
            (
                "FragmentPath",
                format!("/usr/lib/systemd/system/{}", profile.template()),
            ),
        ] {
            unit.insert(key.into(), V::Text(value));
        }
        unit.insert("Transient".into(), V::Boolean(false));
        unit.insert("NeedDaemonReload".into(), V::Boolean(false));
        unit.insert("InvocationID".into(), V::Bytes(invocation.id.to_vec()));
        unit.insert("DropInPaths".into(), V::Strings(Vec::new()));
        let mut service = bus::Properties::new();
        for (key, value) in [
            ("Type", "exec"),
            ("User", "root"),
            ("Group", "root"),
            ("Restart", "no"),
            ("KillMode", "control-group"),
            ("TimeoutStopFailureMode", "terminate"),
        ] {
            service.insert(key.into(), V::Text(value.into()));
        }
        service.insert(
            "ControlGroup".into(),
            V::Text(format!("/system.slice/{}", invocation.unit)),
        );
        for (key, value) in [
            ("ExecMainStartTimestampMonotonic", 1),
            ("MemoryMax", profile.memory()),
            ("MemorySwapMax", 0),
            ("TasksMax", 64),
            ("LimitCORE", 0),
            ("TimeoutStopUSec", 180_000_000),
            ("RuntimeMaxUSec", profile.controller_seconds() * 1_000_000),
            ("CPUQuotaPerSecUSec", profile.quota()),
            ("CPUQuotaPeriodUSec", 100_000),
        ] {
            service.insert(key.into(), V::U64(value));
        }
        service.insert("MainPID".into(), V::U32(42));
        service.insert("KillSignal".into(), V::I32(15));
        service.insert("FinalKillSignal".into(), V::I32(9));
        service.insert("SendSIGKILL".into(), V::Boolean(true));
        service.insert(
            "CPUAffinity".into(),
            V::Bytes(match profile {
                OwnedLeafProfile::CalendarReminder => vec![0, 0, 0x10],
                OwnedLeafProfile::Gallery => vec![0, 0, 0x30],
            }),
        );
        for key in [
            "ExecConditionEx",
            "ExecStartPreEx",
            "ExecStartPostEx",
            "ExecReloadEx",
            "ExecStopEx",
            "ExecStopPostEx",
        ] {
            service.insert(key.into(), V::Commands(Vec::new()));
        }
        service.insert(
            "ExecStartEx".into(),
            V::Commands(vec![bus::ExecCommand {
                path: "/usr/bin/droidloom-applications".into(),
                arguments: vec![
                    "/usr/bin/droidloom-applications".into(),
                    "--owned-leaf-profile".into(),
                    profile.name().into(),
                    "--owned-leaf-plan-sha256".into(),
                    sha,
                ],
                flags: Vec::new(),
                started: [1, 1],
                exited: [0, 0],
                pid: 42,
                code: 0,
                status: 0,
            }]),
        );
        (unit, service, invocation)
    }

    fn accepted(
        unit: &bus::Properties,
        service: &bus::Properties,
        invocation: &bus::Invocation,
        profile: OwnedLeafProfile,
    ) -> Result<(), String> {
        validate(
            &actual_properties(unit, service, invocation, profile, 42)?,
            profile,
            &invocation.unit,
            42,
        )
    }

    #[test]
    fn fixed_owned_unit_profile_cannot_inject_a_name_or_expand_resources() {
        let hash = "a".repeat(64);
        assert_eq!(
            OwnedLeafProfile::Gallery.instance(&hash).unwrap(),
            format!("droidloom-native-gallery@{hash}.service")
        );
        for bad in ["", "system.slice", "../gallery", "calendar", "Gallery"] {
            assert!(OwnedLeafProfile::parse(bad).is_err());
        }
        for bad in [
            "a".repeat(63),
            "A".repeat(64),
            format!("{};", "a".repeat(63)),
        ] {
            assert!(OwnedLeafProfile::Gallery.instance(&bad).is_err());
        }
    }

    #[test]
    fn manager_affinity_bitmap_cannot_omit_or_add_a_cpu() {
        assert_eq!(affinity(&[0, 0, 0x10]), vec![20]);
        assert_eq!(affinity(&[0, 0, 0x30, 0]), vec![20, 21]);
        assert_ne!(
            affinity(&[1, 0, 0x10]),
            OwnedLeafProfile::CalendarReminder.cpus()
        );
        assert_ne!(affinity(&[0, 0, 0x70]), OwnedLeafProfile::Gallery.cpus());
    }

    #[test]
    fn effective_manager_overrides_cannot_expand_resources_or_weaken_retirement() {
        use bus::Value as V;
        for profile in [
            OwnedLeafProfile::CalendarReminder,
            OwnedLeafProfile::Gallery,
        ] {
            let (unit, service, invocation) = manager_fixture(profile);
            assert!(accepted(&unit, &service, &invocation, profile).is_ok());
            for (key, value) in [
                ("FinalKillSignal", V::I32(15)),
                ("KillMode", V::Text("process".into())),
                ("SendSIGKILL", V::Boolean(false)),
                ("TimeoutStopFailureMode", V::Text("abort".into())),
                ("MemoryMax", V::U64(profile.memory() + 1)),
                ("MemorySwapMax", V::U64(1)),
                ("TasksMax", V::U64(65)),
                ("CPUQuotaPerSecUSec", V::U64(profile.quota() + 1)),
                ("RuntimeMaxUSec", V::U64(u64::MAX)),
                ("TimeoutStopUSec", V::U64(181_000_000)),
                ("MainPID", V::U32(43)),
                ("CPUAffinity", V::Bytes(vec![0, 0, 0x70])),
                ("LimitCORE", V::U64(1)),
            ] {
                let mut changed = service.clone();
                changed.insert(key.into(), value);
                assert!(
                    accepted(&unit, &changed, &invocation, profile).is_err(),
                    "{key}"
                );
            }
        }
    }

    #[test]
    fn typed_manager_identity_rejects_extra_commands_wrong_types_and_another_invocation() {
        use bus::Value as V;
        let profile = OwnedLeafProfile::Gallery;
        let (unit, service, invocation) = manager_fixture(profile);
        for key in [
            "ExecConditionEx",
            "ExecStartPreEx",
            "ExecStartPostEx",
            "ExecReloadEx",
            "ExecStopEx",
            "ExecStopPostEx",
        ] {
            let mut changed = service.clone();
            changed.insert(key.into(), service["ExecStartEx"].clone());
            assert!(accepted(&unit, &changed, &invocation, profile).is_err());
        }
        for (key, value) in [
            ("MemoryMax", V::Boolean(false)),
            ("MainPID", V::U64(42)),
            ("SendSIGKILL", V::U32(1)),
            ("FinalKillSignal", V::U32(9)),
        ] {
            let mut changed = service.clone();
            changed.insert(key.into(), value);
            assert!(accepted(&unit, &changed, &invocation, profile).is_err());
        }
        for (key, value) in [
            ("Transient", V::Boolean(true)),
            ("NeedDaemonReload", V::Boolean(true)),
            ("InvocationID", V::Bytes(vec![2; 16])),
        ] {
            let mut changed = unit.clone();
            changed.insert(key.into(), value);
            assert!(accepted(&changed, &service, &invocation, profile).is_err());
        }
        let mut missing = service.clone();
        missing.remove("ExecStopPostEx");
        assert!(accepted(&unit, &missing, &invocation, profile).is_err());
    }
}
