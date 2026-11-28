//! Fixed one-shot observation of the original Android process metadata.
//!
//! The broker never gains SYS_PTRACE. A fresh protected ELF enters one held,
//! non-initial Android user namespace, keeps only that namespace's SYS_PTRACE,
//! and reads fixed procfs leaves. It cannot ptrace, signal, execute, create a
//! process or open arbitrary paths. Only fixed public ELF/root/namespace files
//! are returned read-only, after this original helper is actually reaped.
use super::{ApplicationError, Result, external, reject, require};
use super::{protocol, query_io as helper};
use serde::{Deserialize, Serialize};
use std::ffi::{CStr, CString};
use std::fs::File;
use std::io::{self, Read};
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::MetadataExt;
use std::time::{Duration, Instant};

const ARGUMENT: &CStr = c"__production-metadata-observer";
const CONTEXT: &[u8] = b"u:r:droidloom_metadata_observer:s0";
const LIMIT: Duration = Duration::from_secs(5);
const PROC: RawFd = 5;
const TARGET: RawFd = 6;
const OWNER: RawFd = 7;
const USER: RawFd = 4;
const SELECTED_PROC: RawFd = 8;
const CAP_SYS_PTRACE: u32 = 19;
const NSFS: libc::c_long = 0x6e736673;
const PIDFD_INFO: u64 = 0xc050ff0b;
static NS_NAMES: [(&CStr, i32); 7] = [
    (c"ns/user", libc::CLONE_NEWUSER),
    (c"ns/pid", libc::CLONE_NEWPID),
    (c"ns/mnt", libc::CLONE_NEWNS),
    (c"ns/ipc", libc::CLONE_NEWIPC),
    (c"ns/uts", libc::CLONE_NEWUTS),
    (c"ns/net", libc::CLONE_NEWNET),
    (c"ns/cgroup", libc::CLONE_NEWCGROUP),
];
static EXE: &CStr = c"exe";
static ROOT: &CStr = c"root";
static STAT: &CStr = c"stat";
static STATUS: &CStr = c"status";
// Only opened relative to the authenticated selected-provider directory.
static SELINUX: &CStr = c"attr/current";
static APPARMOR: &CStr = c"attr/apparmor/current";
const EXE_FLAGS: i32 = libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NONBLOCK;
const ROOT_FLAGS: i32 = libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NONBLOCK;
const NS_FLAGS: i32 = libc::O_RDONLY | libc::O_CLOEXEC;
const TEXT_FLAGS: i32 = libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum MetadataRole {
    Init,
    InitLifecycle,
    Zygote,
    Framework,
    Composer,
    Query,
    Browser,
    ContactsRead,
    LaunchRead,
    LaunchStart,
    Install,
    CatalogRead,
    AppOpsRead,
    AccountRead,
    DisplayControl,
    PreparationRead,
    IhgInstrument,
    NativeUi,
    NativeUiRead,
    CalendarCounts,
    FixtureState,
}
impl MetadataRole {
    fn uid(self) -> u32 {
        match self {
            Self::Init | Self::InitLifecycle | Self::Zygote | Self::PreparationRead | Self::NativeUiRead => 0,
            Self::Framework | Self::Composer | Self::AccountRead => 1000,
            Self::CalendarCounts => crate::native_calendar_counts::OBSERVER_UID,
            _ => 2000,
        }
    }
    fn context(self) -> &'static [u8] {
        match self {
            Self::Init | Self::InitLifecycle => b"u:r:init:s0",
            Self::Zygote => b"u:r:zygote:s0",
            Self::Framework => b"u:r:system_server:s0",
            Self::Composer => b"u:r:hal_graphics_composer_default:s0",
            Self::Query => b"u:r:droidloom_query:s0",
            Self::Browser => b"u:r:droidloom_browser:s0",
            Self::ContactsRead => b"u:r:droidloom_contacts_read:s0",
            Self::LaunchRead => b"u:r:droidloom_launch_read:s0",
            Self::LaunchStart => b"u:r:droidloom_launch_start:s0",
            Self::Install => b"u:r:droidloom_install:s0",
            Self::CatalogRead => b"u:r:droidloom_catalog_read:s0",
            Self::AppOpsRead => b"u:r:droidloom_appops_read:s0",
            Self::AccountRead => b"u:r:droidloom_account_read:s0",
            Self::DisplayControl => b"u:r:droidloom_display_control:s0",
            Self::PreparationRead => b"u:r:droidloom_preparation_read:s0",
            Self::IhgInstrument => b"u:r:droidloom_ihg_instrument:s0",
            Self::NativeUi => b"u:r:droidloom_native_ui:s0",
            Self::NativeUiRead => b"u:r:droidloom_native_ui_read:s0",
            Self::CalendarCounts => b"u:r:droidloom_calendar_counts:s0:c512,c768",
            Self::FixtureState => b"u:r:droidloom_fixture_state:s0",
        }
    }
    fn matches_context(self, actual: &[u8]) -> bool {
        context_matches(actual, self.context())
            || (self == Self::InitLifecycle && context_matches(actual, b"u:r:kernel:s0"))
    }
    pub(crate) fn for_operation(domain: super::OperationDomain) -> Self {
        match domain {
            super::OperationDomain::Query => Self::Query,
            super::OperationDomain::Browser => Self::Browser,
            super::OperationDomain::ContactsRead => Self::ContactsRead,
            super::OperationDomain::LaunchRead => Self::LaunchRead,
            super::OperationDomain::LaunchStart => Self::LaunchStart,
            super::OperationDomain::Install => Self::Install,
            super::OperationDomain::CatalogRead => Self::CatalogRead,
            super::OperationDomain::AppOpsRead => Self::AppOpsRead,
            super::OperationDomain::AccountRead => Self::AccountRead,
            super::OperationDomain::DisplayControl => Self::DisplayControl,
            super::OperationDomain::PreparationRead => Self::PreparationRead,
            super::OperationDomain::IhgInstrument => Self::IhgInstrument,
            super::OperationDomain::NativeUi => Self::NativeUi,
            super::OperationDomain::NativeUiRead => Self::NativeUiRead,
            super::OperationDomain::CalendarCounts => Self::CalendarCounts,
            super::OperationDomain::FixtureState => Self::FixtureState,
        }
    }
}

/// All fields are captured by the authenticated fixed helper while it is
/// still in the host USERNS. No caller can supply a process path or these values.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct HostProcessMetadata {
    pub(crate) proc_device: u64,
    pub(crate) proc_inode: u64,
    pub(crate) status: String,
    pub(crate) uid_map: String,
    pub(crate) gid_map: String,
    pub(crate) setgroups: String,
    pub(crate) command: String,
    pub(crate) cgroup: String,
}
impl HostProcessMetadata {
    pub(crate) fn proc_identity(&self) -> (u64, u64) {
        (self.proc_device, self.proc_inode)
    }
}
static RETIREMENT_UNPROVEN: std::sync::atomic::AtomicBool =
    std::sync::atomic::AtomicBool::new(false);
pub(crate) fn retirement_failed() -> bool {
    RETIREMENT_UNPROVEN.load(std::sync::atomic::Ordering::Acquire)
}

pub(crate) struct MetadataObservation {
    pub(crate) executable: File,      // fixed public ELF, read-only
    pub(crate) namespaces: [File; 7], // user, pid, mnt, ipc, uts, net, cgroup
    pub(crate) root: File,            // held original root, read-only
    pub(crate) selinux: Vec<u8>,
    pub(crate) apparmor: Vec<u8>,
    pub(crate) stat: String,
    pub(crate) status: String, // UID/GID are in the held Android user namespace
    pub(crate) host: HostProcessMetadata,
}
fn identity(file: &File) -> Result<(u64, u64)> {
    let value = file.metadata()?;
    Ok((value.dev(), value.ino()))
}
fn filesystem(file: &File, expected: libc::c_long) -> Result<()> {
    let mut value: libc::statfs = unsafe { mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        value.f_type == expected,
        "metadata descriptor filesystem differs",
    )
}
fn namespace(file: &File, kind: i32) -> Result<()> {
    filesystem(file, NSFS)?;
    require(
        unsafe { libc::ioctl(file.as_raw_fd(), 0xb703 as libc::c_ulong) } == kind,
        "metadata namespace kind differs",
    )
}
fn context_matches(actual: &[u8], expected: &[u8]) -> bool {
    actual == expected || actual.strip_suffix(b"\0") == Some(expected)
}
fn birth(text: &str, expected_pid: u32) -> Result<(u32, u32, u64)> {
    let (pid, tail) = text
        .split_once(" (")
        .ok_or_else(|| reject("metadata stat PID absent"))?;
    let (_, tail) = tail
        .rsplit_once(") ")
        .ok_or_else(|| reject("metadata stat fields absent"))?;
    let fields: Vec<_> = tail.split_ascii_whitespace().collect();
    require(
        pid.parse::<u32>().ok() == Some(expected_pid) && fields.len() >= 20,
        "metadata stat identity differs",
    )?;
    require(
        !matches!(fields[0], "Z" | "X" | "x"),
        "metadata target is terminal",
    )?;
    let parent = fields[1].parse::<u32>().map_err(external)?;
    let ticks = fields[19].parse::<u64>().map_err(external)?;
    require(ticks > 0, "metadata stat birth absent")?;
    Ok((expected_pid, parent, ticks))
}
fn raw_open(parent: RawFd, name: &CStr, flags: i32) -> Result<File> {
    let raw = unsafe { libc::openat(parent, name.as_ptr(), flags) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}
fn text_at(name: &CStr, limit: u64) -> Result<String> {
    text_from(PROC, name, limit)
}
fn selected_text(name: &CStr, limit: u64) -> Result<String> {
    text_from(SELECTED_PROC, name, limit)
}
fn text_from(directory: RawFd, name: &CStr, limit: u64) -> Result<String> {
    let file = raw_open(directory, name, TEXT_FLAGS)?;
    filesystem(&file, libc::PROC_SUPER_MAGIC)?;
    let mut value = Vec::new();
    file.take(limit + 1).read_to_end(&mut value)?;
    require(
        value.len() <= limit as usize,
        "metadata proc text exceeded its fixed bound",
    )?;
    String::from_utf8(value).map_err(external)
}
fn exact_scope_ids(info: &helper::PidfdInfo, role: MetadataRole) -> Result<()> {
    require(
        [
            info.ruid, info.euid, info.suid, info.fsuid, info.rgid, info.egid, info.sgid,
            info.fsgid,
        ] == [role.uid(); 8],
        "metadata target has different Android role credentials",
    )
}
fn selected_directory(file: &File) -> Result<(u64, u64)> {
    filesystem(file, libc::PROC_SUPER_MAGIC)?;
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    require(
        file.metadata()?.is_dir()
            && flags >= 0
            && flags & (libc::O_PATH | libc::O_DIRECTORY) == (libc::O_PATH | libc::O_DIRECTORY),
        "observer selected process directory is not the authenticated O_PATH descriptor",
    )?;
    identity(file)
}
fn status_credentials(text: &str, info: &helper::PidfdInfo) -> Result<()> {
    for (field, expected) in [
        ("Uid:", [info.ruid, info.euid, info.suid, info.fsuid]),
        ("Gid:", [info.rgid, info.egid, info.sgid, info.fsgid]),
    ] {
        let mut rows = text.lines().filter_map(|line| line.strip_prefix(field));
        let row = rows
            .next()
            .ok_or_else(|| reject("observer status credentials absent"))?;
        require(
            rows.next().is_none(),
            "duplicate observer status credentials",
        )?;
        let values = row
            .split_ascii_whitespace()
            .map(str::parse::<u32>)
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(external)?;
        require(
            values == expected,
            "observer status and original PIDFD credentials differ",
        )?;
    }
    Ok(())
}
fn same_process(a: &helper::PidfdInfo, b: &helper::PidfdInfo) -> Result<()> {
    require(
        (
            a.pid, a.tgid, a.ppid, a.ruid, a.euid, a.suid, a.fsuid, a.rgid, a.egid, a.sgid, a.fsgid,
        ) == (
            b.pid, b.tgid, b.ppid, b.ruid, b.euid, b.suid, b.fsuid, b.rgid, b.egid, b.sgid, b.fsgid,
        ),
        "metadata original pidfd process or credentials changed",
    )
}

#[repr(C)]
struct CapHeader {
    version: u32,
    pid: i32,
}
#[repr(C)]
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
struct CapData {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}
fn scoped_capabilities(set: bool) -> Result<()> {
    let mut header = CapHeader {
        version: 0x20080522,
        pid: 0,
    };
    let wanted = [
        CapData {
            effective: 1 << CAP_SYS_PTRACE,
            permitted: 1 << CAP_SYS_PTRACE,
            inheritable: 0,
        },
        CapData::default(),
    ];
    if set && unsafe { libc::syscall(libc::SYS_capset, &mut header, wanted.as_ptr()) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let mut actual = [CapData::default(); 2];
    if unsafe { libc::syscall(libc::SYS_capget, &mut header, actual.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        actual == wanted,
        "metadata observer retained other namespace capabilities",
    )?;
    require(
        unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) } == 1,
        "metadata observer lost no-new-privileges",
    )?;
    Ok(())
}

/// Only fixed read paths below the actual held proc directory survive. Pointer
/// comparisons refer exclusively to immutable source-owned C string constants.
fn read_filter() -> Vec<libc::sock_filter> {
    let ins = |code, jt, jf, k| libc::sock_filter { code, jt, jf, k };
    let deny = 0x00050000 | libc::EPERM as u32;
    let allow = 0x7fff0000;
    let mut f = vec![
        ins(0x20, 0, 0, 4),
        ins(0x15, 1, 0, 0xc000003e),
        ins(0x06, 0, 0, 0x80000000),
        ins(0x20, 0, 0, 0),
        ins(0x35, 0, 1, 0x40000000),
        ins(0x06, 0, 0, deny),
    ];
    fn one(
        ins: &dyn Fn(u16, u8, u8, u32) -> libc::sock_filter,
        args: &[(u32, u64)],
        allow: u32,
    ) -> Vec<libc::sock_filter> {
        let mut body = Vec::new();
        let count = args.len() * 4;
        for &(index, value) in args {
            for (offset, want) in [
                (16 + index * 8, value as u32),
                (20 + index * 8, (value >> 32) as u32),
            ] {
                body.push(ins(0x20, 0, 0, offset));
                let remaining = count - body.len();
                body.push(ins(0x15, 0, remaining as u8, want));
            }
        }
        body.push(ins(0x06, 0, 0, allow));
        body
    }
    let mut narrow = |sys: libc::c_long, variants: Vec<Vec<(u32, u64)>>| {
        // A syscall dispatch block can contain many fixed path alternatives.
        let mut body = Vec::new();
        for args in variants {
            body.extend(one(&ins, &args, allow));
        }
        body.push(ins(0x06, 0, 0, deny));
        assert!(body.len() < 256);
        f.push(ins(0x15, 0, body.len() as u8, sys as u32));
        f.extend(body);
        f.push(ins(0x20, 0, 0, 0));
    };
    let mut paths = vec![
        (EXE, EXE_FLAGS),
        (ROOT, ROOT_FLAGS),
        (STAT, TEXT_FLAGS),
        (STATUS, TEXT_FLAGS),
        (APPARMOR, TEXT_FLAGS),
    ];
    paths.extend(NS_NAMES.iter().map(|(name, _)| (*name, NS_FLAGS)));
    narrow(
        libc::SYS_openat,
        paths
            .into_iter()
            .map(|(name, flags)| {
                vec![
                    (0, PROC as u64),
                    (1, name.as_ptr() as u64),
                    (2, flags as u64),
                ]
            })
            .chain([STAT, STATUS, SELINUX, APPARMOR].into_iter().map(|name| {
                vec![
                    (0, SELECTED_PROC as u64),
                    (1, name.as_ptr() as u64),
                    (2, TEXT_FLAGS as u64),
                ]
            }))
            .collect(),
    );
    narrow(
        libc::SYS_ioctl,
        vec![vec![(0, TARGET as u64), (1, PIDFD_INFO)], vec![(1, 0xb703)]],
    );
    narrow(libc::SYS_sendmsg, vec![vec![(0, 3)]]);
    narrow(
        libc::SYS_prctl,
        vec![vec![(0, libc::PR_GET_NO_NEW_PRIVS as u64)]],
    );
    // The executable image is already loaded. Metadata sampling never needs
    // executable mappings or permission upgrades on existing mappings.
    for syscall in [libc::SYS_mmap, libc::SYS_mprotect] {
        narrow(
            syscall,
            [
                0_u64,
                libc::PROT_READ as u64,
                (libc::PROT_READ | libc::PROT_WRITE) as u64,
            ]
            .into_iter()
            .map(|prot| vec![(2, prot)])
            .collect(),
        );
    }
    // No write syscall is admitted. Sending the one bounded packet on the
    // original inherited channel is the helper's only outward operation.
    for syscall in [
        libc::SYS_read,
        libc::SYS_close,
        libc::SYS_fstat,
        libc::SYS_newfstatat,
        libc::SYS_statx,
        libc::SYS_fstatfs,
        libc::SYS_munmap,
        libc::SYS_brk,
        libc::SYS_madvise,
        libc::SYS_futex,
        libc::SYS_rt_sigprocmask,
        libc::SYS_rt_sigreturn,
        libc::SYS_clock_gettime,
        libc::SYS_poll,
        libc::SYS_ppoll,
        libc::SYS_fcntl,
        libc::SYS_getpid,
        libc::SYS_getppid,
        libc::SYS_capget,
        libc::SYS_exit_group,
        libc::SYS_exit,
    ] {
        f.extend([ins(0x15, 0, 1, syscall as u32), ins(0x06, 0, 0, allow)]);
    }
    f.push(ins(0x06, 0, 0, deny));
    f
}
fn relocate(files: Vec<std::os::fd::OwnedFd>) -> Result<[File; 4]> {
    let files = files
        .into_iter()
        .map(File::from)
        .map(|file| helper::above_reserved(&file))
        .collect::<Result<Vec<_>>>()?;
    let files: [File; 4] = files
        .try_into()
        .map_err(|_| reject("metadata request descriptor count"))?;
    // The fourth descriptor is only this original target's selected proc directory.
    // No mount root or caller-selected path crosses the channel.
    let mut out = Vec::new();
    for (source, target) in files.iter().zip([USER, TARGET, OWNER, SELECTED_PROC]) {
        if unsafe { libc::dup3(source.as_raw_fd(), target, libc::O_CLOEXEC) } != target {
            return Err(io::Error::last_os_error().into());
        }
        out.push(unsafe { File::from_raw_fd(target) });
    }
    out.try_into()
        .map_err(|_| reject("metadata fixed descriptors absent"))
}
fn assemble(
    files: Vec<std::os::fd::OwnedFd>,
    role: MetadataRole,
    selinux: String,
    apparmor: String,
    stat: String,
    status: String,
    original: &helper::PidfdInfo,
    userns: &File,
    host: HostProcessMetadata,
) -> Result<MetadataObservation> {
    require(files.len() == 9, "metadata response descriptor count")?;
    require(
        role.matches_context(selinux.as_bytes()),
        "metadata observed SELinux role differs",
    )?;
    let mut files = files.into_iter().map(File::from);
    let executable = files.next().unwrap();
    let root = files.next().unwrap();
    require(
        executable.metadata()?.is_file() && root.metadata()?.is_dir(),
        "metadata executable or root kind differs",
    )?;
    for file in [&executable, &root] {
        let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
        require(
            flags >= 0 && flags & libc::O_PATH == 0 && flags & libc::O_ACCMODE == libc::O_RDONLY,
            "metadata returned a non-read-only public observation",
        )?;
    }
    let namespaces: [File; 7] = files
        .collect::<Vec<_>>()
        .try_into()
        .map_err(|_| reject("metadata namespace count"))?;
    for (file, (_, kind)) in namespaces.iter().zip(NS_NAMES) {
        namespace(file, kind)?;
    }
    require(
        identity(&namespaces[0])? == identity(userns)?,
        "metadata target user namespace differs",
    )?;
    let observed = birth(&stat, original.pid)?;
    require(
        observed.1 == original.ppid,
        "metadata target original parent changed",
    )?;
    Ok(MetadataObservation {
        executable,
        root,
        namespaces,
        selinux: selinux.into_bytes(),
        apparmor: apparmor.into_bytes(),
        stat,
        status,
        host,
    })
}

fn open_target_proc(pid: u32) -> Result<File> {
    // The PID comes exclusively from the original held PIDFD. The opened
    // directory is subsequently tied back to that same live task and birth.
    let root = raw_open(
        libc::AT_FDCWD,
        c"/proc",
        libc::O_PATH | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
    )?;
    filesystem(&root, libc::PROC_SUPER_MAGIC)?;
    let name = CString::new(pid.to_string()).map_err(external)?;
    let opened = raw_open(
        root.as_raw_fd(),
        &name,
        libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
    )?;
    let high = helper::above_reserved(&opened)?;
    drop(opened);
    drop(root);
    if unsafe { libc::dup3(high.as_raw_fd(), PROC, libc::O_CLOEXEC) } != PROC {
        return Err(io::Error::last_os_error().into());
    }
    let directory = unsafe { File::from_raw_fd(PROC) };
    filesystem(&directory, libc::PROC_SUPER_MAGIC)?;
    require(
        directory.metadata()?.is_dir(),
        "metadata target is not a proc directory",
    )?;
    Ok(directory)
}
fn host_metadata(directory: &File, before: &helper::PidfdInfo) -> Result<HostProcessMetadata> {
    let (proc_device, proc_inode) = identity(directory)?;
    let host = HostProcessMetadata {
        proc_device,
        proc_inode,
        status: text_at(STATUS, 4096)?,
        uid_map: text_at(c"uid_map", 1024)?,
        gid_map: text_at(c"gid_map", 1024)?,
        setgroups: text_at(c"setgroups", 32)?,
        command: text_at(c"comm", 256)?,
        cgroup: text_at(c"cgroup", 2048)?,
    };
    for (field, expected) in [
        (
            "Uid:",
            [before.ruid, before.euid, before.suid, before.fsuid],
        ),
        (
            "Gid:",
            [before.rgid, before.egid, before.sgid, before.fsgid],
        ),
    ] {
        let rows = host
            .status
            .lines()
            .filter_map(|line| line.strip_prefix(field))
            .collect::<Vec<_>>();
        require(rows.len() == 1, "metadata host credential field differs")?;
        let ids = rows[0]
            .split_ascii_whitespace()
            .map(str::parse::<u32>)
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(external)?;
        require(
            ids == expected,
            "metadata host status and original PIDFD disagree",
        )?;
    }
    Ok(host)
}
fn sample(
    role: MetadataRole,
    userns: &File,
    target: &File,
    owner: &File,
    selected: &File,
    parent: i32,
    deadline: Instant,
    calendar_factory: bool,
) -> Result<MetadataObservation> {
    require(
        calendar_factory == (role == MetadataRole::CalendarCounts),
        "Calendar metadata requires its independent high factory origin",
    )?;
    helper::alive(target)?;
    let before = helper::pidfd_info(target)?;
    let selected_node = selected_directory(selected)?;
    let proc = open_target_proc(before.pid)?;
    let initial_birth = birth(&text_at(STAT, 2048)?, before.pid)?;
    require(
        initial_birth.1 == before.ppid,
        "metadata original proc parent differs",
    )?;
    let host = host_metadata(&proc, &before)?;
    same_process(&before, &helper::pidfd_info(target)?)?;
    namespace(userns, libc::CLONE_NEWUSER)?;
    let own_user = File::open("/proc/thread-self/ns/user")?;
    namespace(&own_user, libc::CLONE_NEWUSER)?;
    require(
        identity(&own_user)? != identity(userns)?,
        "metadata helper must not enter or retain the initial user namespace",
    )?;
    drop(own_user);
    if unsafe { libc::setns(USER, libc::CLONE_NEWUSER) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    scoped_capabilities(true)?;
    if unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if calendar_factory {
        super::calendar_factory::context(true)?;
    } else {
        helper::mac_context(CONTEXT)?;
    }
    require(
        unsafe { libc::getppid() } == parent,
        "metadata helper original parent changed",
    )?;
    helper::alive(owner)?;
    helper::install_filter(&read_filter())?;
    let scoped = helper::pidfd_info(target)?;
    require(
        (scoped.pid, scoped.tgid, scoped.ppid) == (before.pid, before.tgid, before.ppid),
        "metadata target PIDFD changed across scope entry",
    )?;
    exact_scope_ids(&scoped, role)?;
    let stat = text_at(STAT, 2048)?;
    require(
        birth(&stat, scoped.pid)? == initial_birth,
        "metadata target birth changed across scope entry",
    )?;
    require(
        birth(&selected_text(STAT, 2048)?, scoped.pid)? == initial_birth,
        "selected and original metadata process births differ",
    )?;
    status_credentials(&selected_text(STATUS, 4096)?, &scoped)?;
    let selinux = selected_text(SELINUX, 256)?;
    require(
        role.matches_context(selinux.as_bytes()),
        "metadata actual target role differs",
    )?;
    let apparmor = text_at(APPARMOR, 256)?;
    require(
        selected_text(APPARMOR, 256)? == apparmor,
        "selected metadata AppArmor target differs",
    )?;
    let executable = raw_open(PROC, EXE, EXE_FLAGS)?;
    let root = raw_open(PROC, ROOT, ROOT_FLAGS)?;
    let mut namespaces = Vec::new();
    for (name, kind) in NS_NAMES {
        let file = raw_open(PROC, name, NS_FLAGS)?;
        namespace(&file, kind)?;
        namespaces.push(file);
    }
    require(
        identity(&namespaces[0])? == identity(userns)?,
        "metadata target is outside the original held Android scope",
    )?;
    let status = text_at(STATUS, 4096)?;
    status_credentials(&status, &scoped)?;
    require(
        birth(&text_at(STAT, 2048)?, scoped.pid)? == initial_birth,
        "metadata target birth changed during observation",
    )?;
    require(
        identity(&raw_open(PROC, EXE, EXE_FLAGS)?)? == identity(&executable)?
            && identity(&raw_open(PROC, ROOT, ROOT_FLAGS)?)? == identity(&root)?,
        "metadata target executable or root changed during observation",
    )?;
    for ((name, _), held) in NS_NAMES.into_iter().zip(&namespaces) {
        require(
            identity(&raw_open(PROC, name, NS_FLAGS)?)? == identity(held)?,
            "metadata target namespace changed during observation",
        )?;
    }
    require(
        selected_text(SELINUX, 256)?.as_bytes() == selinux.as_bytes()
            && text_at(APPARMOR, 256)? == apparmor
            && selected_text(APPARMOR, 256)? == apparmor
            && birth(&selected_text(STAT, 2048)?, scoped.pid)? == initial_birth
            && identity(selected)? == selected_node,
        "metadata target MAC role changed",
    )?;
    require(
        identity(&proc)? == host.proc_identity(),
        "metadata held proc inode changed",
    )?;
    status_credentials(&selected_text(STATUS, 4096)?, &scoped)?;
    status_credentials(&text_at(STATUS, 4096)?, &scoped)?;
    same_process(&scoped, &helper::pidfd_info(target)?)?;
    scoped_capabilities(false)?;
    helper::alive(target)?;
    helper::alive(owner)?;
    require(
        unsafe { libc::getppid() } == parent && Instant::now() < deadline,
        "metadata original parent or deadline changed",
    )?;
    Ok(MetadataObservation {
        executable,
        root,
        namespaces: namespaces
            .try_into()
            .map_err(|_| reject("metadata namespace count"))?,
        selinux: selinux.into_bytes(),
        apparmor: apparmor.into_bytes(),
        stat,
        status,
        host,
    })
}
pub(super) fn entry() -> Result<()> {
    entry_at(None)
}
pub(super) fn calendar_factory_entry(original_end: Instant) -> Result<()> {
    entry_at(Some(original_end))
}
fn entry_at(factory_end: Option<Instant>) -> Result<()> {
    let calendar_factory = factory_end.is_some();
    helper::own_root_credentials()?;
    helper::verify_fixed_stdio()?;
    if calendar_factory {
        super::calendar_factory::context(true)?;
    } else {
        helper::mac_context(CONTEXT)?;
    }
    if unsafe { libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    helper::empty_capabilities()?;
    if calendar_factory {
        super::calendar_factory::channel()?;
    } else {
        drop(crate::production_host_admission::application_worker_executable().map_err(external)?);
        helper::channel_kind(3)?;
    }
    let parent = unsafe { libc::getppid() };
    require(parent > 1, "metadata helper has no original broker")?;
    let admission_end = factory_end.unwrap_or_else(|| Instant::now() + LIMIT);
    let received = protocol::receive(3, admission_end)?;
    let (nonce, role, deadline_ns) = match received.message {
        protocol::Message::MetadataRequest {
            nonce,
            role,
            deadline_ns,
        } => (nonce, role, deadline_ns),
        _ => return Err(reject("metadata helper request phase differs")),
    };
    require(
        calendar_factory == (role == MetadataRole::CalendarCounts),
        "Calendar metadata role cannot enter the ordinary observer",
    )?;
    let [userns, target, owner, selected] = relocate(received.files)?;
    helper::parent_identity(&owner, received.peer, parent)?;
    let converted = Instant::now();
    let remaining = deadline_ns
        .checked_sub(protocol::monotonic_ns()?)
        .ok_or_else(|| reject("metadata helper deadline expired"))?;
    require(
        remaining > 0 && remaining <= LIMIT.as_nanos() as u64,
        "metadata helper budget differs",
    )?;
    let deadline = (converted + Duration::from_nanos(remaining)).min(admission_end);
    match sample(
        role,
        &userns,
        &target,
        &owner,
        &selected,
        parent,
        deadline,
        calendar_factory,
    ) {
        Ok(observed) => {
            let mut files = vec![observed.executable.as_raw_fd(), observed.root.as_raw_fd()];
            files.extend(observed.namespaces.iter().map(AsRawFd::as_raw_fd));
            protocol::send(
                3,
                &protocol::Message::MetadataObserved {
                    nonce,
                    role,
                    selinux: String::from_utf8(observed.selinux).map_err(external)?,
                    apparmor: String::from_utf8(observed.apparmor).map_err(external)?,
                    stat: observed.stat,
                    status: observed.status,
                    host: observed.host,
                },
                &files,
                deadline,
            )?;
        }
        Err(error) => {
            // A rejected sample still terminates normally and is actually
            // reaped. No output descriptors or success evidence are emitted.
            protocol::send(
                3,
                &protocol::Message::MetadataRejected {
                    nonce,
                    reason: error.to_string(),
                },
                &[],
                deadline,
            )?;
        }
    }
    helper::alive(&owner)?;
    Ok(())
}

/// The role is a closed source enum; no request can choose a PID, path, MAC
/// label, namespace name, executable, signal, or command. All targets are held.
fn ordinary_role(role: MetadataRole) -> Result<()> {
    require(
        role != MetadataRole::CalendarCounts,
        "Calendar metadata is exclusive to the high factory observer",
    )
}
pub(crate) fn observe(
    source: &crate::production_mac::ObserverProcSource<'_>,
    role: MetadataRole,
    target: &File,
    userns: &File,
    deadline: Instant,
) -> Result<MetadataObservation> {
    if retirement_failed() {
        return Err(ApplicationError::RetirementUnproven);
    }
    ordinary_role(role)?;
    let deadline = deadline.min(Instant::now() + LIMIT);
    crate::production_host_admission::check_observation_before(deadline)?;
    helper::own_root_credentials()?;
    helper::mac_context(b"u:r:droidloom_broker:s0")?;
    super::worker::require_wait_semantics()?;
    namespace(userns, libc::CLONE_NEWUSER)?;
    helper::alive(target)?;
    let original = helper::pidfd_info(target)?;
    let selected = source.metadata(role, target, deadline).map_err(external)?;
    let executable =
        crate::production_host_admission::application_worker_executable().map_err(external)?;
    let executable = helper::above_reserved(&executable)?;
    let (channel, child_channel) = protocol::socketpair()?;
    let child_channel = helper::above_reserved(&File::from(child_channel))?;
    let stdio = helper::fixed_stdio()?;
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0_u32) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let owner = unsafe { File::from_raw_fd(raw as RawFd) };
    let mut nonce = [0_u8; 16];
    let mut offset = 0;
    while offset < nonce.len() {
        let count = unsafe {
            libc::getrandom(nonce[offset..].as_mut_ptr().cast(), nonce.len() - offset, 0)
        };
        if count < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error.into());
        }
        require(count > 0, "metadata random nonce absent")?;
        offset += count as usize;
    }
    let remaining = deadline.saturating_duration_since(Instant::now());
    crate::production_host_admission::check_observation_before(deadline)?;
    let deadline_ns = protocol::monotonic_ns()?
        .checked_add(remaining.as_nanos() as u64)
        .ok_or_else(|| reject("metadata deadline overflow"))?;
    let program = helper::filter(Some(executable.as_raw_fd()), true);
    let fprog = libc::sock_fprog {
        len: program.len() as u16,
        filter: program.as_ptr().cast_mut(),
    };
    let argv = [
        c"droidloom-owned-metadata-observer".as_ptr(),
        ARGUMENT.as_ptr(),
        std::ptr::null(),
    ];
    let environment = [c"LC_ALL=C".as_ptr(), std::ptr::null()];
    let parent = unsafe { libc::getpid() };
    let mut raw_pidfd = -1_i32;
    let args = super::worker::CloneArgs {
        flags: libc::CLONE_PIDFD as u64,
        pidfd: (&mut raw_pidfd as *mut i32) as u64,
        exit_signal: libc::SIGCHLD as u64,
        ..super::worker::CloneArgs::default()
    };
    let mut mask = super::worker::SignalMask::block()?;
    let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args)) };
    if pid < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if pid == 0 {
        unsafe {
            helper::bootstrap(
                helper::HelperRole::MetadataObserver,
                parent,
                executable.as_raw_fd(),
                child_channel.as_raw_fd(),
                stdio.as_raw_fd(),
                argv.as_ptr(),
                environment.as_ptr(),
                &fprog,
            )
        }
    }
    if raw_pidfd < 0 {
        RETIREMENT_UNPROVEN.store(true, std::sync::atomic::Ordering::Release);
        return Err(ApplicationError::RetirementUnproven);
    }
    let mut child = helper::Child {
        pid: pid as u32,
        pidfd: Some(unsafe { File::from_raw_fd(raw_pidfd) }),
        terminal: None,
    };
    drop(child_channel);
    let operation = (|| -> Result<MetadataObservation> {
        mask.restore()?;
        let info = helper::pidfd_info(child.pidfd.as_ref().unwrap())?;
        require(
            info.pid == child.pid && info.ppid == parent as u32,
            "metadata helper is not the actual original child",
        )?;
        protocol::send(
            channel.as_raw_fd(),
            &protocol::Message::MetadataRequest {
                nonce,
                role,
                deadline_ns,
            },
            &[
                userns.as_raw_fd(),
                target.as_raw_fd(),
                owner.as_raw_fd(),
                selected.directory().as_raw_fd(),
            ],
            deadline,
        )?;
        let reply = protocol::receive(channel.as_raw_fd(), deadline)?;
        require(
            reply.peer.pid == pid as i32 && reply.peer.uid == 0 && reply.peer.gid == 0,
            "metadata helper reply credentials differ",
        )?;
        let (selinux, apparmor, stat, status, host) = match reply.message {
            protocol::Message::MetadataObserved {
                nonce: actual,
                role: actual_role,
                selinux,
                apparmor,
                stat,
                status,
                host,
            } if actual == nonce && actual_role == role => (selinux, apparmor, stat, status, host),
            protocol::Message::MetadataRejected {
                nonce: actual,
                reason,
            } if actual == nonce && reply.files.is_empty() => {
                child.finish(deadline)?;
                return Err(reject(reason));
            }
            _ => return Err(reject("metadata response phase or nonce differs")),
        };
        child.finish(deadline)?;
        // No output is trusted before the original waitid reports normal exit 0.
        selected.revalidate().map_err(external)?;
        helper::alive(target)?;
        same_process(&original, &helper::pidfd_info(target)?)?;
        assemble(
            reply.files,
            role,
            selinux,
            apparmor,
            stat,
            status,
            &original,
            userns,
            host,
        )
    })();
    if operation.is_err() && child.retire().is_err() {
        if let Some(fd) = child.pidfd.take() {
            mem::forget(fd);
        }
        RETIREMENT_UNPROVEN.store(true, std::sync::atomic::Ordering::Release);
        return Err(ApplicationError::RetirementUnproven);
    }
    operation
}

/// Only transport fields. These acquire authority solely from the original
/// factory channel, actual helper retirement and its nine received descriptors.
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct CalendarMetadataFields {
    pub(super) selinux: String,
    pub(super) apparmor: String,
    pub(super) stat: String,
    pub(super) status: String,
    pub(super) host: HostProcessMetadata,
}
impl CalendarMetadataFields {
    pub(super) fn from_observation(observed: MetadataObservation) -> Result<(Self, Vec<File>)> {
        let mut files = vec![observed.executable, observed.root];
        files.extend(observed.namespaces);
        Ok((
            Self {
                selinux: String::from_utf8(observed.selinux).map_err(external)?,
                apparmor: String::from_utf8(observed.apparmor).map_err(external)?,
                stat: observed.stat,
                status: observed.status,
                host: observed.host,
            },
            files,
        ))
    }
    pub(super) fn assemble(
        self,
        files: Vec<std::os::fd::OwnedFd>,
        original: &helper::PidfdInfo,
        userns: &File,
    ) -> Result<MetadataObservation> {
        assemble(
            files,
            MetadataRole::CalendarCounts,
            self.selinux,
            self.apparmor,
            self.stat,
            self.status,
            original,
            userns,
            self.host,
        )
    }
}
pub(super) fn observe_calendar_in_factory(
    target: &File,
    userns: &File,
    selected: &File,
    original_end: Instant,
) -> Result<(MetadataObservation, protocol::FactoryHelperRetirement)> {
    namespace(userns, libc::CLONE_NEWUSER)?;
    helper::alive(target)?;
    let original = helper::pidfd_info(target)?;
    require(
        original.ppid == unsafe { libc::getpid() } as u32,
        "Calendar metadata target is not the factory's direct query",
    )?;
    let mut child = super::calendar_factory::spawn_metadata(original_end)?;
    let operation = (|| -> Result<(MetadataObservation, protocol::FactoryHelperRetirement)> {
        let end = child.deadline();
        let mut nonce = [0_u8; 16];
        crate::production_host_admission::check_observation_before(end)?;
        require(
            unsafe { libc::getrandom(nonce.as_mut_ptr().cast(), nonce.len(), libc::GRND_NONBLOCK) }
                == nonce.len() as isize,
            "Calendar metadata nonce unavailable",
        )?;
        let deadline_ns = protocol::monotonic_ns()?
            .checked_add(end.saturating_duration_since(Instant::now()).as_nanos() as u64)
            .ok_or_else(|| reject("Calendar metadata deadline overflow"))?;
        protocol::send(
            child.socket().as_raw_fd(),
            &protocol::Message::MetadataRequest {
                nonce,
                role: MetadataRole::CalendarCounts,
                deadline_ns,
            },
            &[
                userns.as_raw_fd(),
                target.as_raw_fd(),
                child.owner().as_raw_fd(),
                selected.as_raw_fd(),
            ],
            end,
        )?;
        let response = protocol::receive(child.socket().as_raw_fd(), end)?;
        require(
            response.peer.pid == child.pid() as i32
                && response.peer.uid == 0
                && response.peer.gid == 0,
            "Calendar metadata response is not its actual owned helper",
        )?;
        let fields = match response.message {
            protocol::Message::MetadataObserved {
                nonce: actual,
                role: MetadataRole::CalendarCounts,
                selinux,
                apparmor,
                stat,
                status,
                host,
            } if actual == nonce => CalendarMetadataFields {
                selinux,
                apparmor,
                stat,
                status,
                host,
            },
            protocol::Message::MetadataRejected {
                nonce: actual,
                reason,
            } if actual == nonce && response.files.is_empty() => {
                child.finish()?;
                return Err(reject(reason));
            }
            _ => return Err(reject("Calendar metadata response phase differs")),
        };
        let (pid, waitid_code, waitid_status) = child.finish()?;
        helper::alive(target)?;
        same_process(&original, &helper::pidfd_info(target)?)?;
        crate::production_host_admission::check_observation_before(end)?;
        Ok((
            fields.assemble(response.files, &original, userns)?,
            protocol::FactoryHelperRetirement {
                pid,
                waitid_code,
                waitid_status,
            },
        ))
    })();
    if operation.is_err() {
        child.failed()?;
    }
    operation
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn metadata_observer_closed_roles_reject_caller_authority() {
        for text in [
            r#"{"phase":"MetadataRequest","nonce":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],"role":"framework","deadline_ns":1,"pid":7}"#,
            r#"{"phase":"MetadataRequest","nonce":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],"role":"kernel","deadline_ns":1}"#,
        ] {
            assert!(serde_json::from_str::<protocol::Message>(text).is_err());
        }
        assert_eq!(MetadataRole::Framework.uid(), 1000);
        assert_eq!(MetadataRole::Composer.uid(), 1000);
        assert!(!MetadataRole::Framework.matches_context(MetadataRole::Composer.context()));
        assert!(!MetadataRole::Composer.matches_context(MetadataRole::Framework.context()));
        assert!(MetadataRole::Composer.matches_context(b"u:r:hal_graphics_composer_default:s0"));
        assert_eq!(MetadataRole::Query.uid(), 2000);
        let preparation = MetadataRole::for_operation(super::super::OperationDomain::PreparationRead);
        assert_eq!(preparation.uid(), 0);
        assert!(preparation.matches_context(b"u:r:droidloom_preparation_read:s0"));
        assert!(!preparation.matches_context(MetadataRole::Query.context()));
        assert!(!MetadataRole::CalendarCounts.matches_context(b"u:r:droidloom_calendar_counts:s0"));
        assert!(
            !MetadataRole::CalendarCounts
                .matches_context(b"u:r:droidloom_calendar_counts:s0:c512,c769")
        );
        for (operation, uid) in [
            (super::super::OperationDomain::AccountRead, 1000),
            (super::super::OperationDomain::NativeUi, 2000),
            (super::super::OperationDomain::NativeUiRead, 0),
            (super::super::OperationDomain::CalendarCounts, 10017),
            (super::super::OperationDomain::FixtureState, 2000),
        ] {
            let role = MetadataRole::for_operation(operation);
            assert_eq!(role.uid(), uid);
            assert_eq!(role.context(), operation.context().as_bytes());
            assert!(!role.matches_context(b"u:r:shell:s0"));
        }
    }
    #[test]
    fn metadata_observer_birth_keeps_identity_and_rejects_terminal_target() {
        let text = format!("41 (odd ) name) S 31 {} 901 0\n", ["0"; 17].join(" "));
        assert_eq!(birth(&text, 41).unwrap(), (41, 31, 901));
        assert!(birth(&text, 42).is_err());
        assert!(birth(&text.replacen(" S ", " Z ", 1), 41).is_err());
        assert!(birth("41 (short) S 31", 41).is_err());
    }
    #[test]
    fn metadata_observer_filter_has_real_read_path_and_syscall_limits() {
        let proc = File::open("/proc/self").unwrap();
        let name = STAT;
        let forbidden = c"cmdline";
        let program = read_filter();
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            unsafe {
                if libc::dup2(proc.as_raw_fd(), PROC) != PROC
                    || libc::dup2(proc.as_raw_fd(), SELECTED_PROC) != SELECTED_PROC
                    || libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
                {
                    libc::_exit(91);
                }
            }
            if helper::install_filter(&program).is_err() {
                unsafe {
                    libc::_exit(92);
                }
            }
            // This is an actual descriptor-routing test of the installed BPF,
            // not an assertion that this host has the selected SELinux mount.
            for leaf in [STAT, STATUS, SELINUX, APPARMOR] {
                let fd = unsafe { libc::openat(SELECTED_PROC, leaf.as_ptr(), TEXT_FLAGS) };
                if fd < 0 {
                    unsafe { libc::_exit(101) }
                }
                unsafe { libc::close(fd) };
            }
            for (dir, leaf) in [
                (PROC, SELINUX),
                (SELECTED_PROC, EXE),
                (SELECTED_PROC, c"../stat"),
                (SELECTED_PROC, c"ns/user"),
            ] {
                let fd = unsafe { libc::openat(dir, leaf.as_ptr(), TEXT_FLAGS) };
                if fd != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::EPERM) {
                    unsafe { libc::_exit(102) }
                }
            }
            let raw = unsafe { libc::openat(PROC, name.as_ptr(), TEXT_FLAGS) };
            if raw < 0 {
                unsafe {
                    libc::_exit(93);
                }
            }
            unsafe {
                libc::close(raw);
            }
            let bad = unsafe { libc::openat(PROC, forbidden.as_ptr(), TEXT_FLAGS) };
            if bad >= 0 || io::Error::last_os_error().raw_os_error() != Some(libc::EPERM) {
                unsafe {
                    libc::_exit(94);
                }
            }
            for syscall in [
                libc::SYS_ptrace,
                libc::SYS_pidfd_open,
                libc::SYS_pidfd_send_signal,
                libc::SYS_kill,
                libc::SYS_clone3,
                libc::SYS_setns,
                libc::SYS_capset,
                libc::SYS_execveat,
                libc::SYS_write,
            ] {
                let result =
                    unsafe { libc::syscall(syscall, -1_i64, 0_i64, 0_i64, 0_i64, 0_i64, 0_i64) };
                if result != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::EPERM) {
                    unsafe {
                        libc::_exit(95);
                    }
                }
            }
            for syscall in [libc::SYS_mmap, libc::SYS_mprotect] {
                let result = unsafe {
                    libc::syscall(
                        syscall,
                        0_u64,
                        4096_u64,
                        libc::PROT_READ | libc::PROT_EXEC,
                        libc::MAP_PRIVATE | libc::MAP_ANONYMOUS,
                        -1_i64,
                        0_i64,
                    )
                };
                if result != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::EPERM) {
                    unsafe {
                        libc::_exit(96);
                    }
                }
            }
            unsafe {
                libc::_exit(0);
            }
        }
        let mut status = 0;
        assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
        assert_eq!(status, 0);
    }
    #[test]
    fn metadata_observer_rejects_ordinary_unconfined_entry() {
        assert!(entry().is_err());
    }

    #[test]
    fn calendar_metadata_cannot_use_the_ordinary_broker_observer() {
        assert!(ordinary_role(MetadataRole::CalendarCounts).is_err());
        assert!(ordinary_role(MetadataRole::Query).is_ok());
        assert!(calendar_factory_entry(Instant::now() + Duration::from_secs(1)).is_err());
    }
    #[test]
    fn selected_status_requires_each_actual_pidfd_uid_and_gid_once() {
        let mut info: helper::PidfdInfo = unsafe { mem::zeroed() };
        info.ruid = 2000;
        info.euid = 2000;
        info.suid = 2000;
        info.fsuid = 2000;
        info.rgid = 2000;
        info.egid = 2000;
        info.sgid = 2000;
        info.fsgid = 2000;
        let good = "Name:\tquery\nUid:\t2000\t2000\t2000\t2000\nGid:\t2000\t2000\t2000\t2000\n";
        assert!(status_credentials(good, &info).is_ok());
        for bad in [
            good.replace("Uid:\t2000", "Uid:\t1000"),
            good.replace("Gid:\t2000", "Gid:\t0"),
            format!("{good}Uid:\t2000\t2000\t2000\t2000\n"),
            good.replace("Gid:", "Missing:"),
            good.replace("2000\t2000\t2000\t2000", "2000\t2000\t2000"),
            good.replace("Uid:\t2000", "Uid:\t4294967296"),
        ] {
            assert!(status_credentials(&bad, &info).is_err(), "{bad}");
        }
    }
}
