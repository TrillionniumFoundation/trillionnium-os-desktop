//! Fixed application commands borrowed from the actual early Android owner.
//! Numeric process names only bind already-held pidfds or observe framework
//! lineage; no request may supply a namespace, executable, root or command.
use super::{EarlyBaseAdmission, identity, info, live, pidfd};
use crate::control::application_probe::RuntimeEpoch;
use crate::production_application::{
    ApplicationWorkerAuthority, MetadataObservation, MetadataRole, QueryProjection,
};
use crate::production_cgroup::{ApplicationLeaf, PreparedCgroup};
use crate::production_execution::RuntimeMacOwner;
use crate::production_namespace::NamespaceError;
use crate::production_readiness::{BootProperty, read_boot_complete};
use crate::production_runtime_assets::EarlyQueryResources;
use std::ffi::{CStr, CString};
use std::fs::File;
use std::io::{self, Read};
use std::os::fd::{AsFd, AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::MetadataExt;
use std::time::{Duration, Instant};

#[path = "production_early_image_custody.rs"]
mod image_custody;
#[path = "production_early_task_control.rs"]
mod task_control;
pub(crate) use task_control::{EarlyTaskControlEndpoint, EarlyTaskControlPeer};

type Result<T> = std::result::Result<T, NamespaceError>;
fn external(e: impl std::error::Error + 'static) -> NamespaceError {
    if crate::production_application::metadata_retirement_failed() {
        NamespaceError::RetirementUnproven
    } else if let Some(deadline) = crate::production_host_admission::observation_expiry(&e) {
        NamespaceError::Io(crate::production_host_admission::observation_expired_error(deadline))
    } else {
        NamespaceError::RuntimeResource(e.to_string())
    }
}
fn require(value: bool, why: &'static str) -> Result<()> {
    if value {
        Ok(())
    } else {
        Err(NamespaceError::Rejected(why))
    }
}
fn open(parent: &File, name: &CStr, directory: bool) -> io::Result<File> {
    let raw = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            (if directory {
                libc::O_PATH | libc::O_DIRECTORY
            } else {
                libc::O_RDONLY
            }) | libc::O_NOFOLLOW
                | libc::O_CLOEXEC
                | libc::O_NONBLOCK,
        )
    };
    if raw < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(unsafe { File::from_raw_fd(raw) })
    }
}
fn proc_link(parent: &File, name: &CStr) -> io::Result<File> {
    let raw = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
        )
    };
    if raw < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(unsafe { File::from_raw_fd(raw) })
    }
}
fn fs_kind(file: &File, expected: libc::c_long) -> Result<()> {
    let mut st: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut st) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        st.f_type == expected,
        "early application descriptor filesystem differs",
    )
}
fn proc_bytes(parent: &File, name: &CStr) -> Result<Vec<u8>> {
    let file = open(parent, name, false)?;
    fs_kind(&file, libc::PROC_SUPER_MAGIC)?;
    let mut bytes = Vec::new();
    file.take(16385).read_to_end(&mut bytes)?;
    require(
        bytes.len() <= 16384,
        "early application proc evidence exceeded bound",
    )?;
    Ok(bytes)
}
fn proc_text(parent: &File, name: &CStr) -> Result<String> {
    String::from_utf8(proc_bytes(parent, name)?).map_err(external)
}
const NS_NAMES: [(&CStr, i32); 6] = [
    (c"ns/mnt", libc::CLONE_NEWNS),
    (c"ns/pid", libc::CLONE_NEWPID),
    (c"ns/ipc", libc::CLONE_NEWIPC),
    (c"ns/uts", libc::CLONE_NEWUTS),
    (c"ns/net", libc::CLONE_NEWNET),
    (c"ns/cgroup", libc::CLONE_NEWCGROUP),
];
fn ns_type(file: &File, kind: i32) -> Result<()> {
    fs_kind(file, 0x6e736673)?;
    let actual = unsafe { libc::ioctl(file.as_raw_fd(), 0xb703 as libc::c_ulong) };
    require(actual == kind, "early application namespace type differs")
}
fn ns_owner(file: &File, userns: &File) -> Result<()> {
    let raw = unsafe { libc::ioctl(file.as_raw_fd(), 0xb701 as libc::c_ulong) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let owner = unsafe { File::from_raw_fd(raw) };
    require(
        identity(&owner)? == identity(userns)?,
        "early application namespace has another owner",
    )
}
fn retirement_checked<T>(result: Result<T>) -> Result<T> {
    if crate::production_application::metadata_retirement_failed() {
        Err(NamespaceError::RetirementUnproven)
    } else {
        result
    }
}
fn request_checked<T>(base: &EarlyBaseAdmission<'_>, result: Result<T>) -> Result<T> {
    if base.retirement_unproven() {
        Err(NamespaceError::RetirementUnproven)
    } else {
        retirement_checked(result)
    }
}
fn metadata(
    target: &File,
    userns: &File,
    role: MetadataRole,
    absolute: Option<Instant>,
) -> Result<MetadataObservation> {
    retirement_checked(Ok(()))?;
    let deadline = super::resources::observer_deadline(absolute)?;
    retirement_checked(
        crate::production_application::observe_metadata(
            role,
            target,
            userns,
            deadline,
        )
        .map_err(|error| match error {
            crate::production_application::ApplicationError::RetirementUnproven => {
                NamespaceError::RetirementUnproven
            }
            crate::production_application::ApplicationError::Io(error) => NamespaceError::Io(error),
            error => external(error),
        }),
    )
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Process {
    pid: u32,
    parent: u32,
    start: u64,
}
fn parse_process(text: &str, pid: u32) -> Result<Process> {
    let (number, rest) = text
        .split_once(" (")
        .ok_or(NamespaceError::Rejected("process stat lacks PID"))?;
    let (_, tail) = rest
        .rsplit_once(") ")
        .ok_or(NamespaceError::Rejected("process stat lacks fields"))?;
    let fields: Vec<_> = tail.split_ascii_whitespace().collect();
    require(
        number.parse::<u32>().ok() == Some(pid) && fields.len() >= 20,
        "process stat identity or length differs",
    )?;
    require(
        !matches!(fields[0], "Z" | "X" | "x"),
        "process has exited and is awaiting reaping",
    )?;
    let parent = fields[1].parse::<u32>().map_err(external)?;
    let start = fields[19].parse::<u64>().map_err(external)?;
    require(pid > 0 && start > 0, "process stat lacks a live birth time")?;
    Ok(Process { pid, parent, start })
}
fn process(parent: &File, pid: u32) -> Result<Process> {
    parse_process(&proc_text(parent, c"stat")?, pid)
}
fn credentials_text(text: &str, uid: u32, gid: u32) -> Result<()> {
    for (prefix, expected) in [("Uid:", uid), ("Gid:", gid)] {
        let rows: Vec<_> = text
            .lines()
            .filter_map(|line| line.strip_prefix(prefix))
            .collect();
        require(
            rows.len() == 1,
            "process credential field missing or duplicated",
        )?;
        let values = rows[0]
            .split_ascii_whitespace()
            .map(str::parse::<u32>)
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(external)?;
        require(
            values == [expected; 4],
            "process credentials differ from the original mapped role",
        )?;
    }
    Ok(())
}
#[cfg(test)]
fn credentials(directory: &File, uid: u32, gid: u32) -> Result<()> {
    credentials_text(&proc_text(directory, c"status")?, uid, gid)
}
fn status_process(text: &str, process: Process) -> Result<()> {
    for (field, expected) in [
        ("Pid:", process.pid),
        ("Tgid:", process.pid),
        ("PPid:", process.parent),
    ] {
        let rows: Vec<_> = text
            .lines()
            .filter_map(|line| line.strip_prefix(field))
            .collect();
        require(
            rows.len() == 1,
            "process identity field missing or duplicated",
        )?;
        let values = rows[0].split_ascii_whitespace().collect::<Vec<_>>();
        require(
            values.len() == 1 && values[0].parse::<u32>().ok() == Some(expected),
            "process status and original PIDFD identity differ",
        )?;
    }
    Ok(())
}
fn exact_range(text: &str, start: u32, count: u32) -> bool {
    let mut lines = text.lines();
    let Some(row) = lines.next() else {
        return false;
    };
    let mut fields = row.split_ascii_whitespace();
    let mut number = || fields.next().and_then(|value| value.parse::<u32>().ok());
    number() == Some(0)
        && number() == Some(start)
        && number() == Some(count)
        && fields.next().is_none()
        && lines.next().is_none()
}
fn role_ids(base: &EarlyBaseAdmission<'_>, role: MetadataRole) -> Result<(u32, u32, u32)> {
    let guest = match role {
        MetadataRole::Init | MetadataRole::Zygote => 0,
        MetadataRole::Framework | MetadataRole::Composer => 1000,
        _ => {
            return Err(NamespaceError::Rejected(
                "not an early framework metadata role",
            ));
        }
    };
    let (uids, gids) = base.identity_lease().broker_ranges();
    require(
        guest < uids.count && guest < gids.count,
        "framework role is outside the original maps",
    )?;
    let uid = uids
        .start
        .checked_add(guest)
        .ok_or(NamespaceError::Rejected("framework UID overflow"))?;
    let gid = gids
        .start
        .checked_add(guest)
        .ok_or(NamespaceError::Rejected("framework GID overflow"))?;
    Ok((guest, uid, gid))
}
fn native_process(target: &File, expected: Process, uid: u32, gid: u32) -> Result<()> {
    live(target.as_fd())?;
    let actual = info(target.as_fd(), true)?;
    require(
        actual.pid == expected.pid
            && actual.tgid == expected.pid
            && actual.ppid == expected.parent
            && [actual.ruid, actual.euid, actual.suid, actual.fsuid] == [uid; 4]
            && [actual.rgid, actual.egid, actual.sgid, actual.fsgid] == [gid; 4],
        "held framework PIDFD identity or credentials changed",
    )?;
    live(target.as_fd())?;
    Ok(())
}
fn valid_chain(init: Process, zygote: Process, framework: Process) -> bool {
    init.pid != zygote.pid
        && zygote.pid != framework.pid
        && init.pid != framework.pid
        && zygote.parent == init.pid
        && framework.parent == zygote.pid
        && init.start < zygote.start
        && zygote.start < framework.start
}
fn payload_member(group: &str) -> Result<()> {
    let prefix = "0::/system.slice/droidloom-production.service/cell-u1000/payload/";
    require(
        group.starts_with(prefix)
            && group.lines().count() == 1
            && !group
                .trim_end_matches('\n')
                .split('/')
                .skip(1)
                .any(|part| part.is_empty() || part == "." || part == ".."),
        "framework process left the original Android payload",
    )
}
fn verify_sample(
    base: &EarlyBaseAdmission<'_>,
    root: &File,
    observed: &MetadataObservation,
    target: &File,
    role: MetadataRole,
    expected_pid: u32,
) -> Result<Process> {
    retirement_checked(Ok(()))?;
    let process = parse_process(&observed.stat, expected_pid)?;
    let (guest, uid, gid) = role_ids(base, role)?;
    native_process(target, process, uid, gid)?;
    credentials_text(&observed.host.status, uid, gid)?;
    credentials_text(&observed.status, guest, guest)?;
    status_process(&observed.host.status, process)?;
    status_process(&observed.status, process)?;
    let (uids, gids) = base.identity_lease().broker_ranges();
    require(
        exact_range(&observed.host.uid_map, uids.start, uids.count)
            && exact_range(&observed.host.gid_map, gids.start, gids.count)
            && observed.host.setgroups.trim() == "allow"
            && observed.host.proc_device != 0
            && observed.host.proc_inode != 0,
        "framework metadata maps or original proc identity differ",
    )?;
    let (context, command) = match role {
        MetadataRole::Init => (b"u:r:init:s0".as_slice(), observed.host.command == "init\n"),
        MetadataRole::Zygote => (
            b"u:r:zygote:s0".as_slice(),
            matches!(observed.host.command.as_str(), "zygote\n" | "zygote64\n"),
        ),
        MetadataRole::Framework => (
            b"u:r:system_server:s0".as_slice(),
            observed.host.command == "system_server\n",
        ),
        MetadataRole::Composer => (
            b"u:r:hal_graphics_composer_default:s0".as_slice(),
            observed.host.command == "android.hardwar\n",
        ),
        _ => {
            return Err(NamespaceError::Rejected(
                "not an early framework metadata role",
            ));
        }
    };
    require(
        (observed.selinux == context || observed.selinux.strip_suffix(b"\0") == Some(context))
            && command
            && !observed.apparmor.is_empty(),
        "framework actual command or MAC role differs",
    )?;
    payload_member(&observed.host.cgroup)?;
    ns_type(&observed.namespaces[0], libc::CLONE_NEWUSER)?;
    require(
        identity(&observed.namespaces[0])? == identity(base.user_namespace())?
            && identity(&observed.namespaces[1])? == identity(base.board().pid_namespace())?
            && identity(&observed.root)? == identity(root)?,
        "framework left the original Android USER/PID namespaces or root",
    )?;
    for ((_, kind), index) in NS_NAMES.into_iter().zip([2, 1, 3, 4, 5, 6]) {
        ns_type(&observed.namespaces[index], kind)?;
        ns_owner(&observed.namespaces[index], base.user_namespace())?;
    }
    native_process(target, process, uid, gid)?;
    retirement_checked(Ok(process))
}
fn same_sample(held: &MetadataObservation, current: &MetadataObservation) -> Result<()> {
    require(
        held.host.proc_identity() == current.host.proc_identity()
            && identity(&held.executable)? == identity(&current.executable)?
            && identity(&held.root)? == identity(&current.root)?
            && held.selinux == current.selinux
            && held.apparmor == current.apparmor
            && held.host.command == current.host.command,
        "original framework inode, executable, root or MAC identity changed",
    )?;
    for (held, current) in held.namespaces.iter().zip(&current.namespaces) {
        require(
            identity(held)? == identity(current)?,
            "original framework namespace changed",
        )?;
    }
    Ok(())
}

/// This owner can only borrow the existing reservation, budget, exact root and
/// private immutable query roles; it cannot manufacture a new Android lifetime.
pub(crate) struct EarlyApplicationAuthority<'a> {
    base: EarlyBaseAdmission<'a>,
    group: &'a PreparedCgroup,
    owner: &'a RuntimeMacOwner,
    root: &'a File,
    query: &'a EarlyQueryResources,
    images: &'a crate::production_mounts::PreparedMounts,
    proc_root: File,
    namespaces: Vec<File>,
    init: Process,
    init_node: (u64, u64),
    init_program: File,
    framework_program: File,
    device: File,
    progress: &'a dyn Fn() -> io::Result<()>,
}
pub(crate) struct EarlyFrameworkObservation {
    framework_metadata: MetadataObservation,
    framework: Process,
    framework_pidfd: File,
    zygote_metadata: MetadataObservation,
    zygote: Process,
    zygote_pidfd: File,
    init: Process,
    init_pidfd: (u64, u64),
    epoch: RuntimeEpoch,
}
impl<'a> EarlyApplicationAuthority<'a> {
    pub(crate) fn acquire(
        base: &'a EarlyBaseAdmission<'a>,
        group: &'a PreparedCgroup,
        owner: &'a RuntimeMacOwner,
        root: &'a File,
        query: &'a EarlyQueryResources,
        images: &'a crate::production_mounts::PreparedMounts,
        progress: &'a dyn Fn() -> io::Result<()>,
        absolute: Option<Instant>,
    ) -> Result<Self> {
        request_checked(base, Ok(()))?;
        let original = base;
        let base = base.for_request(absolute)?;
        let result = (|| {
        retirement_checked(Ok(()))?;
        retirement_checked(base.revalidate().map_err(NamespaceError::Io))?;
        group
            .revalidate_early_member(&base, owner)
            .map_err(external)?;
        let proc_root = File::open("/proc")?;
        fs_kind(&proc_root, libc::PROC_SUPER_MAGIC)?;
        let actual = metadata(
            base.board().pidfd(),
            base.user_namespace(),
            MetadataRole::Init,
            base.observation_deadline(),
        )?;
        let mut namespaces = Vec::new();
        for ((_, kind), index) in NS_NAMES.into_iter().zip([2, 1, 3, 4, 5, 6]) {
            let held = actual.namespaces[index].try_clone()?;
            ns_type(&held, kind)?;
            ns_owner(&held, base.user_namespace())?;
            namespaces.push(held);
        }
        require(
            identity(&namespaces[0])? == identity(base.board().mount_namespace())?
                && identity(&namespaces[1])? == identity(base.board().pid_namespace())?,
            "application namespaces differ from the original early pins",
        )?;
        let system = open(root, c"system", true)?;
        let bin = open(&system, c"bin", true)?;
        let init_program = open(&bin, c"init", false)?;
        let framework_program = open(&bin, c"app_process64", false)?;
        let device = open(root, c"dev", true)?;
        fs_kind(&device, libc::TMPFS_MAGIC)?;
        let init = verify_sample(
            &base,
            root,
            &actual,
            base.board().pidfd(),
            MetadataRole::Init,
            base.board().host_pid() as u32,
        )?;
        let init_node = actual.host.proc_identity();
        let this = Self {
            base,
            group,
            owner,
            root,
            query,
            images,
            proc_root,
            namespaces,
            init,
            init_node,
            init_program,
            framework_program,
            device,
            progress,
        };
        // This request-local authority is acquired only after the original
        // init has actually reached its stock role. An earlier request reports
        // Starting while the main boot/frontend owner continues progressing.
        this.revalidate()?;
        Ok(this)
        })();
        request_checked(original, result)
    }
    pub(crate) fn check_request_deadline(&self) -> Result<()> {
        request_checked(&self.base, Ok(()))?;
        super::resources::check_observation_deadline(self.base.observation_deadline())?;
        Ok(())
    }
    pub(crate) fn request_deadline(&self) -> Option<Instant> {
        self.base.observation_deadline()
    }
    /// Only a failed, expired read may use this finite kernel-only custody
    /// fence. It does not claim Ready/framework freshness and starts no worker.
    /// The existing main owner performs its next normal full validation.
    pub(crate) fn expired_request_bookend(&self, expected: Instant) -> Result<()> {
        request_checked(&self.base, Ok(()))?;
        require(
            self.request_deadline() == Some(expected) && Instant::now() >= expected,
            "expiry bookend does not match this private request",
        )?;
        let (_, uid, gid) = role_ids(&self.base, MetadataRole::Init)?;
        native_process(self.base.board().pidfd(), self.init, uid, gid)?;
        self.base.board().generation.check_liveness()?;
        for ((_, kind), held) in NS_NAMES.into_iter().zip(&self.namespaces) {
            ns_type(held, kind)?;
            ns_owner(held, self.base.user_namespace())?;
        }
        require(
            identity(&self.namespaces[0])? == identity(self.base.board().mount_namespace())?
                && identity(&self.namespaces[1])? == identity(self.base.board().pid_namespace())?
                && identity(&self.device)? == identity(&open(self.root, c"dev", true)?)?,
            "expired request retained namespace or device custody changed",
        )?;
        request_checked(&self.base, Ok(()))
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.check_request_deadline()?;
        let result = (|| {
            self.base.revalidate()?;
            self.group
                .revalidate_early_member(&self.base, self.owner)
                .map_err(external)?;
            self.query.revalidate(&self.base).map_err(external)?;
            let actual = metadata(
                self.base.board().pidfd(),
                self.base.user_namespace(),
                MetadataRole::Init,
                self.base.observation_deadline(),
            )?;
            require(
                verify_sample(
                    &self.base,
                    self.root,
                    &actual,
                    self.base.board().pidfd(),
                    MetadataRole::Init,
                    self.init.pid,
                )? == self.init
                    && actual.host.proc_identity() == self.init_node,
                "early application original init birth or proc inode changed",
            )?;
            for (((_, kind), held), index) in NS_NAMES
                .into_iter()
                .zip(&self.namespaces)
                .zip([2, 1, 3, 4, 5, 6])
            {
                ns_type(held, kind)?;
                require(
                    identity(&actual.namespaces[index])? == identity(held)?,
                    "original application namespace changed",
                )?;
            }
            require(
                identity(&actual.executable)? == identity(&self.init_program)?
                    && identity(&actual.root)? == identity(self.root)?,
                "early application requires the actual original init executable and root",
            )?;
            require(
                identity(&self.device)? == identity(&open(self.root, c"dev", true)?)?,
                "early application private device mount changed",
            )?;
            self.base.board().revalidate()?;
            Ok(())
        })();
        request_checked(&self.base, result)
    }
    pub(crate) fn host_pid(&self) -> u32 {
        self.init.pid
    }
    pub(crate) fn host_uid(&self) -> u32 {
        self.base.board().selection().spec().host_uid
    }
    pub(crate) fn verify_selection(
        &self,
        selected: &crate::production_selection::ProductionSelection,
    ) -> Result<()> {
        self.revalidate()?;
        selected.revalidate().map_err(external)?;
        require(
            self.base.board().selection().same_selection(selected),
            "application specification differs from the original early selection",
        )
    }

    fn executed(&self) -> Result<()> {
        self.revalidate()
    }
    pub(crate) fn ready(&self) -> Result<()> {
        self.executed()?;
        let property_dir = open(&self.device, c"__properties__", true)?;
        fs_kind(&property_dir, libc::TMPFS_MAGIC)?;
        let (uid, gid) = self.mapped_root()?;
        let m = property_dir.metadata()?;
        require(
            m.uid() == uid && m.gid() == gid && m.mode() & 0o6022 == 0,
            "early private property directory custody differs",
        )?;
        let file = open(&property_dir, c"u:object_r:boot_status_prop:s0", false)?;
        fs_kind(&file, libc::TMPFS_MAGIC)?;
        require(
            read_boot_complete(&file, uid, gid).map_err(external)? == BootProperty::Complete,
            "early application operation requires current Android boot completion",
        )?;
        self.executed()
    }
    fn process_dir(&self, pid: u32) -> Result<File> {
        let name = CString::new(pid.to_string()).map_err(external)?;
        let directory = open(&self.proc_root, &name, true)?;
        fs_kind(&directory, libc::PROC_SUPER_MAGIC)?;
        Ok(directory)
    }
    fn verify_framework_processes(&self, held: &EarlyFrameworkObservation) -> Result<()> {
        retirement_checked(Ok(()))?;
        live(held.framework_pidfd.as_fd())?;
        live(held.zygote_pidfd.as_fd())?;
        self.ready()?;
        let framework = metadata(
            &held.framework_pidfd,
            self.base.user_namespace(),
            MetadataRole::Framework,
            self.base.observation_deadline(),
        )?;
        let zygote = metadata(
            &held.zygote_pidfd,
            self.base.user_namespace(),
            MetadataRole::Zygote,
            self.base.observation_deadline(),
        )?;
        require(
            verify_sample(
                &self.base,
                self.root,
                &framework,
                &held.framework_pidfd,
                MetadataRole::Framework,
                held.framework.pid,
            )? == held.framework
                && verify_sample(
                    &self.base,
                    self.root,
                    &zygote,
                    &held.zygote_pidfd,
                    MetadataRole::Zygote,
                    held.zygote.pid,
                )? == held.zygote
                && held.init == self.init
                && held.init_pidfd == identity(self.base.board().pidfd())?
                && valid_chain(self.init, held.zygote, held.framework)
                && identity(&framework.executable)? == identity(&self.framework_program)?
                && identity(&zygote.executable)? == identity(&self.framework_program)?,
            "original early init/zygote/system_server lineage changed",
        )?;
        same_sample(&held.framework_metadata, &framework)?;
        same_sample(&held.zygote_metadata, &zygote)?;
        require(
            held.epoch.boot_id == self.base.board().generation.birth.boot_id
                && held.epoch.cell_host_pid == self.init.pid
                && held.epoch.framework_host_pid == held.framework.pid
                && held.epoch.framework_start_ticks == held.framework.start,
            "framework epoch differs from the original early generation",
        )?;
        self.ready()?;
        let (_, uid, gid) = role_ids(&self.base, MetadataRole::Framework)?;
        native_process(&held.framework_pidfd, held.framework, uid, gid)?;
        let (_, uid, gid) = role_ids(&self.base, MetadataRole::Zygote)?;
        native_process(&held.zygote_pidfd, held.zygote, uid, gid)?;
        retirement_checked(Ok(()))
    }
    pub(crate) fn observe_framework(&self) -> Result<EarlyFrameworkObservation> {
        self.ready()?;
        let mut found = None;
        let mut count = 0usize;
        let (_, wanted_uid, wanted_gid) = role_ids(&self.base, MetadataRole::Framework)?;
        for entry in std::fs::read_dir(format!("/proc/self/fd/{}", self.proc_root.as_raw_fd()))? {
            self.check_request_deadline()?;
            let entry = entry?;
            let Some(name) = entry.file_name().to_str().map(str::to_owned) else {
                continue;
            };
            if name.is_empty() || !name.bytes().all(|v| v.is_ascii_digit()) {
                continue;
            }
            count += 1;
            require(count <= 131072, "bounded host process inventory exceeded")?;
            let pid = name.parse::<u32>().map_err(external)?;
            let observed = (|| -> Result<Option<EarlyFrameworkObservation>> {
                // Enumeration supplies only a candidate number. Credentials and parent
                // come from the actual PIDFD before the fixed observer is invoked.
                let framework_pidfd = pidfd(i32::try_from(pid).map_err(external)?)?;
                live(framework_pidfd.as_fd())?;
                let ids = info(framework_pidfd.as_fd(), true)?;
                if ids.pid != pid
                    || ids.tgid != pid
                    || ids.ppid == 0
                    || [ids.ruid, ids.euid, ids.suid, ids.fsuid] != [wanted_uid; 4]
                    || [ids.rgid, ids.egid, ids.sgid, ids.fsgid] != [wanted_gid; 4]
                {
                    return Ok(None);
                }
                let framework_metadata = match metadata(
                    &framework_pidfd,
                    self.base.user_namespace(),
                    MetadataRole::Framework,
                    self.base.observation_deadline(),
                ) {
                    Ok(value) => value,
                    Err(NamespaceError::RetirementUnproven) => {
                        return Err(NamespaceError::RetirementUnproven);
                    }
                    Err(_) => {
                        self.check_request_deadline()?;
                        return Ok(None);
                    }
                };
                let framework = verify_sample(
                    &self.base,
                    self.root,
                    &framework_metadata,
                    &framework_pidfd,
                    MetadataRole::Framework,
                    pid,
                )?;
                require(
                    framework.parent == ids.ppid,
                    "framework parent changed before original parent binding",
                )?;
                // This PIDFD is bound only to the parent observed through the live
                // framework PIDFD and is rechecked against the helper's host evidence.
                let zygote_pidfd = pidfd(i32::try_from(ids.ppid).map_err(external)?)?;
                live(zygote_pidfd.as_fd())?;
                let zygote_metadata = metadata(
                    &zygote_pidfd,
                    self.base.user_namespace(),
                    MetadataRole::Zygote,
                    self.base.observation_deadline(),
                )?;
                let zygote = verify_sample(
                    &self.base,
                    self.root,
                    &zygote_metadata,
                    &zygote_pidfd,
                    MetadataRole::Zygote,
                    framework.parent,
                )?;
                require(
                    valid_chain(self.init, zygote, framework),
                    "framework observation is outside the original early lineage",
                )?;
                let held = EarlyFrameworkObservation {
                    framework_metadata,
                    framework,
                    framework_pidfd,
                    zygote_metadata,
                    zygote,
                    zygote_pidfd,
                    init: self.init,
                    init_pidfd: identity(self.base.board().pidfd())?,
                    epoch: RuntimeEpoch {
                        boot_id: self.base.board().generation.birth.boot_id.clone(),
                        cell_host_pid: self.init.pid,
                        framework_host_pid: pid,
                        framework_start_ticks: framework.start,
                    },
                };
                self.verify_framework_processes(&held)?;
                Ok(Some(held))
            })();
            self.check_request_deadline()?;
            match request_checked(&self.base, observed) {
                Ok(Some(held)) => {
                    require(
                        found.is_none(),
                        "multiple original early system_server processes",
                    )?;
                    found = Some(held);
                }
                Ok(None) => {}
                Err(NamespaceError::Io(error))
                    if matches!(error.raw_os_error(), Some(libc::ENOENT | libc::ESRCH)) => {}
                Err(error) => return Err(error),
            }
        }
        let held = found.ok_or(NamespaceError::Rejected(
            "original early Android system_server is absent",
        ))?;
        self.verify_framework_processes(&held)?;
        Ok(held)
    }
    pub(crate) fn catalog_jar_digest(&self) -> Result<String> {
        self.ready()?;
        let digest = self.query.catalog_jar_digest(&self.base).map_err(external)?;
        self.revalidate()?;
        Ok(digest)
    }
    pub(crate) fn epoch(&self, held: &EarlyFrameworkObservation) -> Result<RuntimeEpoch> {
        self.verify_framework_processes(held)?;
        Ok(held.epoch.clone())
    }
}
impl ApplicationWorkerAuthority for EarlyApplicationAuthority<'_> {
    fn query_projection(&self) -> QueryProjection {
        QueryProjection::EarlyDev
    }
    fn revalidate(&self) -> Result<()> {
        self.revalidate()
    }
    fn descriptors(&self, binary: &CStr) -> Result<Vec<File>> {
        let held = self.observe_framework()?;
        // Stock init retains the bootstrap mount namespace. Commands must borrow
        // the verified framework's default mount namespace containing active APEX.
        let actual = &held.framework_metadata;
        let [copy, original] = self
            .query
            .descriptors(&self.base, &actual.root, binary)
            .map_err(external)?;
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0u32) };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let parent = unsafe { File::from_raw_fd(raw as i32) };
        let mut files = vec![
            self.base.board().pidfd().try_clone()?,
            parent,
            actual.root.try_clone()?,
            actual.namespaces[0].try_clone()?,
        ];
        for index in [2, 1, 3, 4, 5, 6] {
            files.push(actual.namespaces[index].try_clone()?);
        }
        files.extend([copy, original]);
        self.verify_framework_processes(&held)?;
        Ok(files)
    }
    fn contacts_content_descriptors(&self) -> Result<[File; 2]> {
        let held = self.observe_framework()?;
        let out = self
            .query
            .content(&self.base, &held.framework_metadata.root)
            .map_err(external)?;
        self.verify_framework_processes(&held)?;
        Ok(out)
    }
    fn mapped_root(&self) -> Result<(u32, u32)> {
        let (uid, gid) = self.base.identity_lease().broker_ranges();
        Ok((uid.start, gid.start))
    }
    fn leaf(&self) -> Result<ApplicationLeaf<'_>> {
        self.ready()?;
        self.group
            .early_application_leaf(&self.base, self.owner)
            .map_err(external)
    }
    fn bind_created_process(&self, pidfd: &OwnedFd, query: bool) -> Result<(File, u32)> {
        self.revalidate()?;
        live(pidfd.as_fd())?;
        let observed = info(pidfd.as_fd(), true)?;
        require(
            observed.pid == observed.tgid
                && observed.ppid == std::process::id()
                && observed.pid != self.init.pid,
            "application pidfd is not this broker's direct child",
        )?;
        // Legacy broker-born child only; the kernel factory path never calls this.
        // The query is parked before USER setns and credential changes. Only
        // its PID namespace is already the selected Android namespace.
        let (uid, gid) = (0, 0);
        require(
            [observed.ruid, observed.euid, observed.suid, observed.fsuid] == [uid; 4]
                && [observed.rgid, observed.egid, observed.sgid, observed.fsgid] == [gid; 4],
            "created application process credentials differ",
        )?;
        let directory = self.process_dir(observed.pid)?;
        require(
            process(&directory, observed.pid)?.parent == std::process::id(),
            "created application child parent changed",
        )?;
        if query {
            let own = self.process_dir(std::process::id())?;
            require(
                identity(&proc_link(&directory, c"ns/user")?)?
                    == identity(&proc_link(&own, c"ns/user")?)?,
                "parked query changed its original host user namespace",
            )?;
            for ((name, _), held) in NS_NAMES.into_iter().zip(&self.namespaces) {
                let expected = if name == c"ns/pid" {
                    held.try_clone()?
                } else {
                    proc_link(&own, name)?
                };
                require(
                    identity(&proc_link(&directory, name)?)? == identity(&expected)?,
                    "parked query has changed namespace before its original trace owner",
                )?;
            }
        }
        live(pidfd.as_fd())?;
        self.revalidate()?;
        Ok((directory, observed.pid))
    }
    fn progress_inherited_native(&self, deadline: Instant) -> Result<()> {
        // Kernel-first Android has no inherited legacy seccomp-notify channel.
        // The callback services the same original frontend while commands run.
        require(
            Instant::now() < deadline,
            "early application progress deadline",
        )?;
        self.revalidate()?;
        (self.progress)()?;
        self.revalidate()?;
        require(
            Instant::now() < deadline,
            "early application progress exceeded deadline",
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn early_framework_stat_retains_kernel_birth_despite_parentheses_in_name() {
        let text = format!("31 (odd ) process) S 17 {} 12345 0\n", ["0"; 17].join(" "));
        assert_eq!(
            parse_process(&text, 31).unwrap(),
            Process {
                pid: 31,
                parent: 17,
                start: 12345
            }
        );
        assert!(parse_process(&text, 32).is_err());
        assert!(parse_process("31 (short) S 17", 31).is_err());
    }
    #[test]
    fn early_framework_chain_rejects_reparenting_and_birth_reuse() {
        let init = Process {
            pid: 31,
            parent: 1,
            start: 10,
        };
        let zygote = Process {
            pid: 32,
            parent: 31,
            start: 20,
        };
        let framework = Process {
            pid: 33,
            parent: 32,
            start: 30,
        };
        assert!(valid_chain(init, zygote, framework));
        assert!(!valid_chain(
            init,
            Process {
                parent: 1,
                ..zygote
            },
            framework
        ));
        assert!(!valid_chain(
            init,
            zygote,
            Process {
                parent: 31,
                ..framework
            }
        ));
        assert!(!valid_chain(
            init,
            Process {
                start: 30,
                ..zygote
            },
            framework
        ));
    }
    #[test]
    fn early_framework_zombie_cannot_pass_live_or_process_observation() {
        let mut child = std::process::Command::new("/bin/sleep")
            .arg("10")
            .spawn()
            .unwrap();
        let held = File::open(format!("/proc/{}", child.id())).unwrap();
        let original = pidfd(child.id() as i32).unwrap();
        live(original.as_fd()).unwrap();
        process(&held, child.id()).unwrap();
        child.kill().unwrap();
        let mut event = libc::pollfd {
            fd: original.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        assert_eq!(unsafe { libc::poll(&mut event, 1, 2000) }, 1);
        assert!(live(original.as_fd()).is_err());
        assert!(process(&held, child.id()).is_err());
        child.wait().unwrap();
    }
    #[test]
    fn early_application_proc_helpers_observe_real_child_and_reject_regular_files() {
        let mut child = std::process::Command::new("/bin/sleep")
            .arg("10")
            .spawn()
            .unwrap();
        let held = File::open(format!("/proc/{}", child.id())).unwrap();
        let observed = process(&held, child.id()).unwrap();
        assert_eq!(observed.parent, std::process::id());
        credentials(&held, unsafe { libc::getuid() }, unsafe { libc::getgid() }).unwrap();
        let ordinary = tempfile::tempfile().unwrap();
        assert!(fs_kind(&ordinary, libc::PROC_SUPER_MAGIC).is_err());
        assert!(ns_type(&ordinary, libc::CLONE_NEWPID).is_err());
        child.kill().unwrap();
        child.wait().unwrap();
    }
    #[test]
    fn early_framework_host_and_scoped_credentials_cannot_be_substituted() {
        let host = "Uid:\t121000\t121000\t121000\t121000\nGid:\t221000\t221000\t221000\t221000\n";
        let scoped = "Uid:\t1000\t1000\t1000\t1000\nGid:\t1000\t1000\t1000\t1000\n";
        assert!(credentials_text(host, 121000, 221000).is_ok());
        assert!(credentials_text(scoped, 1000, 1000).is_ok());
        assert!(credentials_text(host, 1000, 1000).is_err());
        assert!(credentials_text(scoped, 121000, 221000).is_err());
        assert!(
            credentials_text(
                &format!("{host}Uid:\t121000\t121000\t121000\t121000\n"),
                121000,
                221000
            )
            .is_err()
        );
        assert!(
            credentials_text(
                &host.replace(
                    "121000\t121000\t121000\t121000",
                    "121000\t121000\t0\t121000"
                ),
                121000,
                221000
            )
            .is_err()
        );
        assert!(credentials_text("Uid:\t1000\nGid:\t1000\n", 1000, 1000).is_err());
    }
    #[test]
    fn early_framework_host_status_binds_pid_parent_and_leader() {
        let expected = Process {
            pid: 190,
            parent: 180,
            start: 100,
        };
        let status = "Name:\tsystem_server\nTgid:\t190\nPid:\t190\nPPid:\t180\n";
        assert!(status_process(status, expected).is_ok());
        for altered in [
            status.replace("Pid:\t190", "Pid:\t191"),
            status.replace("Tgid:\t190", "Tgid:\t191"),
            status.replace("PPid:\t180", "PPid:\t1"),
            format!("{status}Pid:\t190\n"),
            status.replace("Pid:\t190", "Pid:\t190 191"),
        ] {
            assert!(status_process(&altered, expected).is_err());
        }
    }
    #[test]
    fn early_framework_maps_require_original_single_complete_mapping() {
        assert!(exact_range("         0 120000 100000\n", 120000, 100000));
        for map in [
            "0 120000 100000\n0 120000 100000\n",
            "0 120000 100000\n\n",
            "1 120000 100000\n",
            "0 120001 100000\n",
            "0 120000 99999\n",
            "0 120000 100000 extra\n",
            "0 120000\n",
        ] {
            assert!(!exact_range(map, 120000, 100000));
        }
    }
    #[test]
    fn early_framework_payload_scope_rejects_host_relative_and_sibling_groups() {
        let payload = "0::/system.slice/droidloom-production.service/cell-u1000/payload";
        assert!(payload_member(&format!("{payload}/init\n")).is_ok());
        assert!(payload_member(&format!("{payload}/uid_1000/pid_190\n")).is_ok());
        for bad in [
            "0::/\n".to_owned(),
            "0::/init\n".to_owned(),
            format!("{payload}\n"),
            format!("{payload}-other/init\n"),
            format!("{payload}/../broker\n"),
            format!("{payload}//init\n"),
            format!("{payload}/./init\n"),
            format!("{payload}/init\n0::/other\n"),
        ] {
            assert!(payload_member(&bad).is_err());
        }
    }
}
