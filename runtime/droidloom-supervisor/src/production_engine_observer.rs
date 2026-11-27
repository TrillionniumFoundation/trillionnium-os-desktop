//! Fixed, one-shot observation of a selected running application's engine.
//! The helper enters only the original held Android USERNS. It cannot open
//! private data, change namespaces again, ptrace, signal, execute, or create
//! descendants. Only a bounded comparison packet returns after real waitid 0.
use super::{ApplicationError, Result, external, reject, require};
use super::{protocol, query_io as helper};
use crate::control::application_custody::{CustodyFileIdentity, CustodyNamespace};
use crate::engine_custody::native_profile::NativeFileKind;
use crate::engine_custody::{
    EngineFile, EngineFileMount, EngineImageSource, EngineMapping, EngineProcess, MAX_ENGINE_BYTES,
    MAX_MAP_BYTES, NativeExecutableObservation, app_context, engine_mappings, native_mappings,
    selected_package, user_zero_app_uid,
};
use crate::main_custody::{MainNodeIdentity, RuntimeMainCustody};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::ffi::{CStr, CString};
use std::fs::File;
use std::io::{self, Read};
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::{FileExt, MetadataExt};
use std::time::{Duration, Instant};
const ARGUMENT: &CStr = c"__production-engine-observer";
const CONTEXT: &[u8] = b"u:r:droidloom_engine_observer:s0";
const LIMIT: Duration = Duration::from_secs(5);
const PROC: RawFd = 5;
const TARGET: RawFd = 6;
const OWNER: RawFd = 7;
const USER: RawFd = 4;
const ROOT_FD: RawFd = 8;
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
static SELINUX: &CStr = c"attr/current";
static APPARMOR: &CStr = c"attr/apparmor/current";
static CGROUP: &CStr = c"cgroup";
static CMDLINE: &CStr = c"cmdline";
static MAPS: &CStr = c"maps";
static ENGINE_NAME: &CStr = c"system/system_ext/lib64/libberberis_arm64.so";
static NATIVE_EXE_NAME: &CStr = c"system/bin/app_process64";
static NATIVE_ART_NAME: &CStr = c"apex/com.android.art/lib64/libart.so";
const EXE_FLAGS: i32 = libc::O_PATH | libc::O_CLOEXEC;
const ROOT_FLAGS: i32 = libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NONBLOCK;
const NS_FLAGS: i32 = libc::O_RDONLY | libc::O_CLOEXEC;
const TEXT_FLAGS: i32 = libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK;
#[repr(C)]
struct OpenHow {
    flags: u64,
    mode: u64,
    resolve: u64,
}
static ENGINE_HOW: OpenHow = OpenHow {
    flags: (libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NONBLOCK | libc::O_NOFOLLOW) as u64,
    mode: 0,
    resolve: 0x08 | 0x02 | 0x04,
};
/// Private parent-authenticated comparisons. Public requests cannot supply
/// these fields, an engine path, a target PID, or a MAC context.
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct EngineTarget {
    pub(crate) package: String,
    pub(crate) uid: u32,
    pub(crate) main: RuntimeMainCustody,
    pub(crate) source: EngineImageSource,
}
impl EngineTarget {
    fn validate(&self) -> Result<()> {
        self.main.validate(&self.main.epoch).map_err(reject)?;
        self.source.validate_origin(&self.main).map_err(reject)?;
        require(
            selected_package(&self.package) && user_zero_app_uid(self.uid),
            "engine private request shape differs",
        )
    }
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct EngineSample {
    pub(crate) process: EngineProcess,
    pub(crate) engine: EngineFile,
    pub(crate) mappings: Vec<EngineMapping>,
    pub(crate) native_executable: Option<NativeExecutableObservation>,
    pub(crate) maps_before_sha256: String,
    pub(crate) maps_after_sha256: String,
    pub(crate) observed_monotonic_ns: u64,
}
static RETIREMENT_UNPROVEN: std::sync::atomic::AtomicBool =
    std::sync::atomic::AtomicBool::new(false);
pub(crate) fn retirement_failed() -> bool {
    RETIREMENT_UNPROVEN.load(std::sync::atomic::Ordering::Acquire)
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
        "engine descriptor filesystem differs",
    )
}
fn namespace(file: &File, kind: i32) -> Result<()> {
    filesystem(file, NSFS)?;
    require(
        unsafe { libc::ioctl(file.as_raw_fd(), 0xb703 as libc::c_ulong) } == kind,
        "engine namespace kind differs",
    )
}
fn context_matches(actual: &[u8], expected: &[u8]) -> bool {
    actual == expected || actual.strip_suffix(b"\0") == Some(expected)
}
fn birth(text: &str, expected_pid: u32) -> Result<(u32, u32, u64)> {
    let (pid, tail) = text
        .split_once(" (")
        .ok_or_else(|| reject("engine stat PID absent"))?;
    let (_, tail) = tail
        .rsplit_once(") ")
        .ok_or_else(|| reject("engine stat fields absent"))?;
    let fields: Vec<_> = tail.split_ascii_whitespace().collect();
    require(
        pid.parse::<u32>().ok() == Some(expected_pid) && fields.len() >= 20,
        "engine stat identity differs",
    )?;
    require(
        !matches!(fields[0], "Z" | "X" | "x"),
        "engine target is terminal",
    )?;
    let parent = fields[1].parse::<u32>().map_err(external)?;
    let ticks = fields[19].parse::<u64>().map_err(external)?;
    require(ticks > 0, "engine stat birth absent")?;
    Ok((expected_pid, parent, ticks))
}

/// procfs is the original host PIDNS mount. Only the original host and the
/// verified Main PID namespace may occur; a number from AMS never opens proc.
fn guest_process_id(text: &str, host: u32) -> Result<u32> {
    let exact = |key: &str| -> Result<Vec<u32>> {
        let mut lines = text.lines().filter_map(|line| line.strip_prefix(key));
        let value = lines
            .next()
            .ok_or_else(|| reject("engine proc PID field absent"))?;
        require(lines.next().is_none(), "duplicate engine proc PID field")?;
        value
            .split_ascii_whitespace()
            .map(|n| {
                require(
                    !n.is_empty() && n.bytes().all(|c| c.is_ascii_digit()) && !n.starts_with('0'),
                    "noncanonical engine proc PID",
                )?;
                n.parse::<u32>().map_err(external)
            })
            .collect()
    };
    let pid = exact("Pid:")?;
    let tgid = exact("Tgid:")?;
    let ns = exact("NSpid:")?;
    let groups = exact("NStgid:")?;
    require(
        pid == [host]
            && tgid == [host]
            && ns.len() == 2
            && ns == groups
            && ns[0] == host
            && ns[1] > 1,
        "engine process PID namespace chain differs",
    )?;
    Ok(ns[1])
}

fn raw_open(parent: RawFd, name: &CStr, flags: i32) -> Result<File> {
    let raw = unsafe { libc::openat(parent, name.as_ptr(), flags) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}
fn text_at(name: &CStr, limit: u64) -> Result<String> {
    let file = raw_open(PROC, name, TEXT_FLAGS)?;
    filesystem(&file, libc::PROC_SUPER_MAGIC)?;
    let mut value = Vec::new();
    file.take(limit + 1).read_to_end(&mut value)?;
    require(
        value.len() <= limit as usize,
        "engine proc text exceeded its fixed bound",
    )?;
    String::from_utf8(value).map_err(external)
}
fn same_process(a: &helper::PidfdInfo, b: &helper::PidfdInfo) -> Result<()> {
    require(
        (
            a.pid, a.tgid, a.ppid, a.ruid, a.euid, a.suid, a.fsuid, a.rgid, a.egid, a.sgid, a.fsgid,
        ) == (
            b.pid, b.tgid, b.ppid, b.ruid, b.euid, b.suid, b.fsuid, b.rgid, b.egid, b.sgid, b.fsgid,
        ),
        "engine original pidfd process or credentials changed",
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
        "engine observer retained other namespace capabilities",
    )?;
    require(
        unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) } == 1,
        "engine observer lost no-new-privileges",
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
        (SELINUX, TEXT_FLAGS),
        (APPARMOR, TEXT_FLAGS),
        (CGROUP, TEXT_FLAGS),
        (CMDLINE, TEXT_FLAGS),
        (MAPS, TEXT_FLAGS),
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
            .collect(),
    );
    narrow(
        libc::SYS_ioctl,
        vec![
            vec![(0, TARGET as u64), (1, PIDFD_INFO)],
            vec![(1, 0xb703)],
            vec![(1, 0xb701)],
        ],
    );
    narrow(
        libc::SYS_openat2,
        [ENGINE_NAME, NATIVE_EXE_NAME, NATIVE_ART_NAME]
            .into_iter()
            .map(|name| {
                vec![
                    (0, ROOT_FD as u64),
                    (1, name.as_ptr() as u64),
                    (2, (&ENGINE_HOW as *const OpenHow) as u64),
                    (3, mem::size_of::<OpenHow>() as u64),
                ]
            })
            .collect(),
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
        libc::SYS_pread64,
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
fn relocate(files: Vec<std::os::fd::OwnedFd>) -> Result<[File; 3]> {
    let files = files
        .into_iter()
        .map(File::from)
        .map(|file| helper::above_reserved(&file))
        .collect::<Result<Vec<_>>>()?;
    let files: [File; 3] = files
        .try_into()
        .map_err(|_| reject("engine request descriptor count"))?;
    // Wire order is the original user namespace, original target PIDFD and owner.
    let mut out = Vec::new();
    for (source, target) in files.iter().zip([USER, TARGET, OWNER]) {
        if unsafe { libc::dup3(source.as_raw_fd(), target, libc::O_CLOEXEC) } != target {
            return Err(io::Error::last_os_error().into());
        }
        out.push(unsafe { File::from_raw_fd(target) });
    }
    out.try_into()
        .map_err(|_| reject("engine fixed descriptors absent"))
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
        "engine target is not a proc directory",
    )?;
    Ok(directory)
}

fn node(file: &File) -> Result<MainNodeIdentity> {
    Ok(MainNodeIdentity::of(&file.metadata()?))
}
fn file_node(file: &File) -> Result<CustodyFileIdentity> {
    let n = file.metadata()?;
    Ok(CustodyFileIdentity {
        device: n.dev(),
        inode: n.ino(),
        mode: n.mode(),
        uid: n.uid(),
        gid: n.gid(),
        links: n.nlink(),
        bytes: n.len(),
        modified: (n.mtime(), n.mtime_nsec()),
        changed: (n.ctime(), n.ctime_nsec()),
    })
}
fn bytes_at(name: &CStr, limit: usize) -> Result<Vec<u8>> {
    let file = raw_open(PROC, name, TEXT_FLAGS)?;
    filesystem(&file, libc::PROC_SUPER_MAGIC)?;
    let mut bytes = Vec::new();
    file.take(limit as u64 + 1).read_to_end(&mut bytes)?;
    require(
        bytes.len() <= limit,
        "engine proc read exceeded its fixed bound",
    )?;
    Ok(bytes)
}
fn command() -> Result<String> {
    let bytes = bytes_at(CMDLINE, 4096)?;
    let end = bytes
        .iter()
        .position(|b| *b == 0)
        .ok_or_else(|| reject("engine process command is not terminated"))?;
    let first = &bytes[..end];
    require(
        !first.is_empty() && first.len() <= 255,
        "engine process command extent differs",
    )?;
    String::from_utf8(first.to_vec()).map_err(external)
}
fn scoped_ids(info: &helper::PidfdInfo, uid: u32) -> Result<()> {
    require(
        [
            info.ruid, info.euid, info.suid, info.fsuid, info.rgid, info.egid, info.sgid,
            info.fsgid,
        ] == [uid; 8],
        "engine process is not the actual PM UID",
    )
}
fn fixed_engine(deadline: Instant) -> Result<EngineFile> {
    let raw = unsafe {
        libc::syscall(
            libc::SYS_openat2,
            ROOT_FD,
            ENGINE_NAME.as_ptr(),
            &ENGINE_HOW as *const OpenHow,
            mem::size_of::<OpenHow>(),
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(raw as RawFd) };
    let before = file_node(&file)?;
    require(
        before.mode == libc::S_IFREG | 0o644
            && before.uid == 0
            && before.gid == 0
            && before.links == 1
            && (64..=MAX_ENGINE_BYTES).contains(&before.bytes),
        "engine file metadata differs",
    )?;
    let mut hash = Sha256::new();
    let mut offset = 0;
    let mut bytes = [0u8; 65536];
    while offset < before.bytes {
        crate::production_host_admission::check_observation_before(deadline)?;
        let n = (before.bytes - offset).min(bytes.len() as u64) as usize;
        file.read_exact_at(&mut bytes[..n], offset)?;
        hash.update(&bytes[..n]);
        offset += n as u64;
    }
    require(
        file_node(&file)? == before,
        "held engine changed during full read",
    )?;
    Ok(EngineFile {
        identity: before,
        sha256: format!("{:x}", hash.finalize()),
    })
}

fn native_name(kind: NativeFileKind) -> &'static CStr {
    match kind {
        NativeFileKind::Executable => NATIVE_EXE_NAME,
        NativeFileKind::Art => NATIVE_ART_NAME,
    }
}
fn native_mount(file: &File) -> Result<EngineFileMount> {
    let mut fs: libc::statfs = unsafe { mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let mut sx: libc::statx = unsafe { mem::zeroed() };
    if unsafe {
        libc::statx(
            file.as_raw_fd(),
            c"".as_ptr(),
            libc::AT_EMPTY_PATH | libc::AT_SYMLINK_NOFOLLOW,
            libc::STATX_MNT_ID,
            &mut sx,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    // Normal glibc fstatvfs obtains flags through the same descriptor's
    // fstatfs syscall; it opens no pathname and only removes ST_VALID.
    let mut vf: libc::statvfs = unsafe { mem::zeroed() };
    if unsafe { libc::fstatvfs(file.as_raw_fd(), &mut vf) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let out = EngineFileMount {
        filesystem_type: fs.f_type as i64,
        mount_flags: vf.f_flag as u64,
        mount_id: sx.stx_mnt_id,
    };
    require(
        sx.stx_mask & libc::STATX_MNT_ID != 0 && out.readonly_ext4(),
        "native runtime file is not on the original readonly executable ext4 mount",
    )?;
    Ok(out)
}
fn open_native(kind: NativeFileKind) -> Result<File> {
    let raw = unsafe {
        libc::syscall(
            libc::SYS_openat2,
            ROOT_FD,
            native_name(kind).as_ptr(),
            &ENGINE_HOW as *const OpenHow,
            mem::size_of::<OpenHow>(),
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(raw as RawFd) })
}
fn read_native(file: &File, kind: NativeFileKind, deadline: Instant) -> Result<EngineFile> {
    let before = file_node(file)?;
    let (bytes, expected_sha, mode, uid, gid) = kind.expected();
    require(
        before.mode == mode
            && before.uid == uid
            && before.gid == gid
            && before.links == 1
            && before.bytes == bytes,
        "native runtime exact source metadata differs",
    )?;
    let mut header = [0_u8; 64];
    file.read_exact_at(&mut header, 0)?;
    require(
        &header[..7] == b"\x7fELF\x02\x01\x01"
            && u16::from_le_bytes([header[16], header[17]]) == 3
            && u16::from_le_bytes([header[18], header[19]]) == 62
            && u32::from_le_bytes(header[20..24].try_into().unwrap()) == 1,
        "native runtime is not the selected x86_64 ELF",
    )?;
    let mut hash = Sha256::new();
    let mut offset = 0;
    let mut buffer = [0_u8; 65536];
    while offset < before.bytes {
        crate::production_host_admission::check_observation_before(deadline)?;
        let count = (before.bytes - offset).min(buffer.len() as u64) as usize;
        file.read_exact_at(&mut buffer[..count], offset)?;
        hash.update(&buffer[..count]);
        offset += count as u64;
    }
    let out = EngineFile {
        identity: before,
        sha256: format!("{:x}", hash.finalize()),
    };
    require(
        file_node(file)? == before && out.sha256 == expected_sha && kind.validate(&out),
        "native runtime held bytes or identity differ from the selected source",
    )?;
    Ok(out)
}
struct NativeHeldFile {
    file: File,
    kind: NativeFileKind,
    observed: EngineFile,
    mount: EngineFileMount,
}
impl NativeHeldFile {
    fn open(kind: NativeFileKind, deadline: Instant) -> Result<Self> {
        let file = open_native(kind)?;
        let mount = native_mount(&file)?;
        let observed = read_native(&file, kind, deadline)?;
        require(
            native_mount(&file)? == mount,
            "native runtime mount changed during full read",
        )?;
        Ok(Self {
            file,
            kind,
            observed,
            mount,
        })
    }
    fn revalidate(&self, deadline: Instant) -> Result<()> {
        require(
            read_native(&self.file, self.kind, deadline)? == self.observed
                && native_mount(&self.file)? == self.mount,
            "native runtime held file changed across actual mappings",
        )?;
        let named = open_native(self.kind)?;
        require(
            file_node(&named)? == self.observed.identity && native_mount(&named)? == self.mount,
            "native runtime fixed pathname no longer names the original held file",
        )
    }
}

fn sample(
    request: &EngineTarget,
    userns: &File,
    target: &File,
    owner: &File,
    parent: i32,
    deadline: Instant,
) -> Result<Option<EngineSample>> {
    request.validate()?;
    helper::alive(target)?;
    let before = helper::pidfd_info(target)?;
    require(
        before.pid == before.tgid && before.ppid == request.main.zygote.host_pid,
        "engine target is not a direct original zygote child",
    )?;
    let proc = open_target_proc(before.pid)?;
    let initial_birth = birth(&text_at(STAT, 2048)?, before.pid)?;
    require(
        initial_birth.1 == before.ppid && initial_birth.2 > request.main.zygote.start_ticks,
        "engine original process lineage differs",
    )?;
    same_process(&before, &helper::pidfd_info(target)?)?;
    namespace(userns, libc::CLONE_NEWUSER)?;
    let own = File::open("/proc/thread-self/ns/user")?;
    namespace(&own, libc::CLONE_NEWUSER)?;
    require(
        identity(&own)? != identity(userns)?,
        "engine helper cannot retain initial USERNS",
    )?;
    drop(own);
    if unsafe { libc::setns(USER, libc::CLONE_NEWUSER) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    scoped_capabilities(true)?;
    if unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    helper::mac_context(CONTEXT)?;
    require(
        unsafe { libc::getppid() } == parent,
        "engine helper original parent changed",
    )?;
    helper::alive(owner)?;
    // Only this fixed proc-root descriptor survives in the final openat2 rule.
    let opened = raw_open(PROC, ROOT, ROOT_FLAGS)?;
    let high = helper::above_reserved(&opened)?;
    drop(opened);
    if unsafe { libc::dup3(high.as_raw_fd(), ROOT_FD, libc::O_CLOEXEC) } != ROOT_FD {
        return Err(io::Error::last_os_error().into());
    }
    let root = unsafe { File::from_raw_fd(ROOT_FD) };
    drop(high);
    helper::install_filter(&read_filter())?;
    let scoped = helper::pidfd_info(target)?;
    require(
        (scoped.pid, scoped.tgid, scoped.ppid) == (before.pid, before.tgid, before.ppid),
        "engine target changed across USERNS entry",
    )?;
    scoped_ids(&scoped, request.uid)?;
    let cmd = command()?;
    if cmd != request.package {
        // Another same-UID process is not a successful engine observation.
        helper::alive(target)?;
        same_process(&scoped, &helper::pidfd_info(target)?)?;
        helper::alive(owner)?;
        return Ok(None);
    }
    let stat = birth(&text_at(STAT, 2048)?, scoped.pid)?;
    require(
        stat == initial_birth,
        "engine original process birth changed",
    )?;
    let guest_pid = guest_process_id(&text_at(STATUS, 65536)?, scoped.pid)?;
    let selinux = text_at(SELINUX, 256)?;
    require(
        app_context(&selinux),
        "engine target is outside fixed actual app types",
    )?;
    let apparmor = text_at(APPARMOR, 256)?;
    require(
        apparmor == "droidloom-production-android (enforce)\n",
        "engine target AA confinement differs",
    )?;
    let cgroup = text_at(CGROUP, 4096)?;
    let executable = raw_open(PROC, EXE, EXE_FLAGS)?;
    require(
        node(&root)? == request.main.framework.root
            && node(&executable)? == request.main.zygote.executable,
        "engine target root or executable differs from held Main",
    )?;
    let mut ns = Vec::new();
    let mut held_ns = Vec::new();
    for ((name, kind), logical) in NS_NAMES
        .into_iter()
        .zip(["user", "pid", "mount", "ipc", "uts", "net", "cgroup"])
    {
        let file = raw_open(PROC, name, NS_FLAGS)?;
        namespace(&file, kind)?;
        let n = node(&file)?;
        if logical == "user" {
            require(n == node(userns)?, "engine target USERNS differs")?;
        } else {
            let raw = unsafe { libc::ioctl(file.as_raw_fd(), 0xb701 as libc::c_ulong) };
            if raw < 0 {
                return Err(io::Error::last_os_error().into());
            }
            let owner_ns = unsafe { File::from_raw_fd(raw) };
            require(
                node(&owner_ns)? == node(userns)?,
                "engine namespace has another actual USERNS owner",
            )?;
        }
        if logical != "mount" {
            require(
                request
                    .main
                    .framework_namespaces
                    .iter()
                    .filter(|row| {
                        row.name == logical && row.device == n.device && row.inode == n.inode
                    })
                    .count()
                    == 1,
                "engine target left original Main namespaces",
            )?;
        }
        ns.push(CustodyNamespace {
            name: logical.into(),
            device: n.device,
            inode: n.inode,
        });
        held_ns.push(file);
    }
    ns.sort_by(|a, b| a.name.cmp(&b.name));
    let (actual_engine, native_files) = match &request.source {
        EngineImageSource::BerberisArm64 { image } => {
            let file = fixed_engine(deadline)?;
            require(
                file == image.engine,
                "engine library differs from normal selected image",
            )?;
            (file, None)
        }
        EngineImageSource::NativeX86_64 { image } => {
            let exe = NativeHeldFile::open(NativeFileKind::Executable, deadline)?;
            let art = NativeHeldFile::open(NativeFileKind::Art, deadline)?;
            require(
                node(&exe.file)? == node(&executable)?
                    && exe.observed.identity.device == image.system_image.mount_root.device
                    && art.observed.identity.device != exe.observed.identity.device
                    && exe.mount.mount_id != art.mount.mount_id,
                "native runtime does not match the actual app executable and selected system",
            )?;
            (art.observed.clone(), Some((exe, art)))
        }
    };
    let before_maps = bytes_at(MAPS, MAX_MAP_BYTES)?;
    let (mappings, native_executable) = match &native_files {
        None => (
            engine_mappings(&before_maps, &actual_engine).map_err(reject)?,
            None,
        ),
        Some((exe, art)) => (
            native_mappings(&before_maps, &art.observed, NativeFileKind::Art).map_err(reject)?,
            Some(NativeExecutableObservation {
                file: exe.observed.clone(),
                mappings: native_mappings(&before_maps, &exe.observed, NativeFileKind::Executable)
                    .map_err(reject)?,
                mount: exe.mount.clone(),
                art_mount: art.mount.clone(),
            }),
        ),
    };
    let after_maps = bytes_at(MAPS, MAX_MAP_BYTES)?;
    match (&native_files, &native_executable) {
        (None, None) => {
            require(
                engine_mappings(&after_maps, &actual_engine).map_err(reject)? == mappings,
                "actual engine mappings changed during observation",
            )?;
            require(
                fixed_engine(deadline)? == actual_engine,
                "named engine changed across mapping observation",
            )?;
        }
        (Some((exe, art)), Some(observed)) => {
            require(
                native_mappings(&after_maps, &art.observed, NativeFileKind::Art).map_err(reject)?
                    == mappings
                    && native_mappings(&after_maps, &exe.observed, NativeFileKind::Executable)
                        .map_err(reject)?
                        == observed.mappings,
                "actual native executable or ART mappings changed during observation",
            )?;
            exe.revalidate(deadline)?;
            art.revalidate(deadline)?;
        }
        _ => return Err(reject("native runtime observation shape differs")),
    }
    require(
        birth(&text_at(STAT, 2048)?, scoped.pid)? == initial_birth
            && command()? == cmd
            && guest_process_id(&text_at(STATUS, 65536)?, scoped.pid)? == guest_pid
            && text_at(SELINUX, 256)? == selinux
            && text_at(APPARMOR, 256)? == apparmor
            && text_at(CGROUP, 4096)? == cgroup
            && node(&raw_open(PROC, EXE, EXE_FLAGS)?)? == node(&executable)?
            && node(&raw_open(PROC, ROOT, ROOT_FLAGS)?)? == node(&root)?,
        "engine original process bookends changed",
    )?;
    for ((name, _), held) in NS_NAMES.into_iter().zip(&held_ns) {
        require(
            node(&raw_open(PROC, name, NS_FLAGS)?)? == node(held)?,
            "engine original namespace inode changed",
        )?;
    }
    same_process(&scoped, &helper::pidfd_info(target)?)?;
    scoped_capabilities(false)?;
    helper::alive(target)?;
    helper::alive(owner)?;
    require(
        unsafe { libc::getppid() } == parent,
        "engine helper original parent changed",
    )?;
    crate::production_host_admission::check_observation_before(deadline)?;
    Ok(Some(EngineSample {
        process: EngineProcess {
            host_pid: scoped.pid,
            guest_pid,
            host_parent_pid: scoped.ppid,
            start_ticks: stat.2,
            pidfd: node(target)?,
            proc: node(&proc)?,
            root: node(&root)?,
            executable: node(&executable)?,
            scoped_uids: [scoped.ruid, scoped.euid, scoped.suid, scoped.fsuid],
            scoped_gids: [scoped.rgid, scoped.egid, scoped.sgid, scoped.fsgid],
            host_uids: [before.ruid, before.euid, before.suid, before.fsuid],
            host_gids: [before.rgid, before.egid, before.sgid, before.fsgid],
            command: cmd,
            cgroup,
            selinux,
            apparmor,
            namespaces: ns,
        },
        engine: actual_engine,
        mappings,
        native_executable,
        maps_before_sha256: format!("{:x}", Sha256::digest(&before_maps)),
        maps_after_sha256: format!("{:x}", Sha256::digest(&after_maps)),
        observed_monotonic_ns: protocol::monotonic_ns()?,
    }))
}
pub(super) fn entry() -> Result<()> {
    helper::own_root_credentials()?;
    helper::verify_fixed_stdio()?;
    helper::mac_context(CONTEXT)?;
    if unsafe { libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    helper::empty_capabilities()?;
    drop(crate::production_host_admission::application_worker_executable().map_err(external)?);
    helper::install_filter(&helper::engine_filter(None))?;
    helper::channel_kind(3)?;
    let parent = unsafe { libc::getppid() };
    require(parent > 1, "engine helper lacks its original broker")?;
    let received = protocol::receive(3, Instant::now() + LIMIT)?;
    let (nonce, request, deadline_ns) = match received.message {
        protocol::Message::EngineRequest {
            nonce,
            request,
            deadline_ns,
        } => (nonce, request, deadline_ns),
        _ => return Err(reject("engine helper request phase differs")),
    };
    let [userns, target, owner] = relocate(received.files)?;
    helper::parent_identity(&owner, received.peer, parent)?;
    let remaining = deadline_ns
        .checked_sub(protocol::monotonic_ns()?)
        .ok_or_else(|| reject("engine helper deadline expired"))?;
    require(
        remaining > 0 && remaining <= LIMIT.as_nanos() as u64,
        "engine helper budget differs",
    )?;
    let deadline = Instant::now() + Duration::from_nanos(remaining);
    let message = match sample(&request, &userns, &target, &owner, parent, deadline) {
        Ok(Some(sample)) => protocol::Message::EngineObserved { nonce, sample },
        Ok(None) => protocol::Message::EngineNotTarget { nonce },
        Err(error) => protocol::Message::EngineRejected {
            nonce,
            reason: error.to_string(),
        },
    };
    protocol::send(3, &message, &[], deadline)?;
    helper::alive(&owner)?;
    Ok(())
}

pub(crate) fn observe(
    request: EngineTarget,
    target: &File,
    userns: &File,
    deadline: Instant,
) -> Result<Option<EngineSample>> {
    request.validate()?;
    if retirement_failed() {
        return Err(ApplicationError::RetirementUnproven);
    }
    let deadline = deadline.min(Instant::now() + LIMIT);
    crate::production_host_admission::check_observation_before(deadline)?;
    helper::own_root_credentials()?;
    helper::mac_context(b"u:r:droidloom_broker:s0")?;
    super::worker::require_wait_semantics()?;
    namespace(userns, libc::CLONE_NEWUSER)?;
    helper::alive(target)?;
    let original = helper::pidfd_info(target)?;
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
        require(count > 0, "engine random nonce absent")?;
        offset += count as usize;
    }
    let remaining = deadline.saturating_duration_since(Instant::now());
    crate::production_host_admission::check_observation_before(deadline)?;
    let deadline_ns = protocol::monotonic_ns()?
        .checked_add(remaining.as_nanos() as u64)
        .ok_or_else(|| reject("engine deadline overflow"))?;
    let program = helper::engine_filter(Some(executable.as_raw_fd()));
    let fprog = libc::sock_fprog {
        len: program.len() as u16,
        filter: program.as_ptr().cast_mut(),
    };
    let argv = [
        c"droidloom-owned-engine-observer".as_ptr(),
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
                helper::HelperRole::EngineObserver,
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
    let operation = (|| -> Result<Option<EngineSample>> {
        mask.restore()?;
        let info = helper::pidfd_info(child.pidfd.as_ref().unwrap())?;
        require(
            info.pid == child.pid && info.ppid == parent as u32,
            "engine helper is not the actual original child",
        )?;
        protocol::send(
            channel.as_raw_fd(),
            &protocol::Message::EngineRequest {
                nonce,
                request,
                deadline_ns,
            },
            &[userns.as_raw_fd(), target.as_raw_fd(), owner.as_raw_fd()],
            deadline,
        )?;
        let reply = protocol::receive(channel.as_raw_fd(), deadline)?;
        require(
            reply.peer.pid == pid as i32 && reply.peer.uid == 0 && reply.peer.gid == 0,
            "engine helper reply credentials differ",
        )?;
        require(
            reply.files.is_empty(),
            "engine observer returned unexpected descriptors",
        )?;
        let sample = match reply.message {
            protocol::Message::EngineObserved {
                nonce: actual,
                sample,
            } if actual == nonce => Some(sample),
            protocol::Message::EngineNotTarget { nonce: actual } if actual == nonce => None,
            protocol::Message::EngineRejected {
                nonce: actual,
                reason,
            } if actual == nonce => {
                child.finish(deadline)?;
                return Err(reject(reason));
            }
            _ => return Err(reject("engine response phase or nonce differs")),
        };
        child.finish(deadline)?;
        // Acceptance follows actual waitid exit 0, never an unauthenticated body.
        helper::alive(target)?;
        same_process(&original, &helper::pidfd_info(target)?)?;
        if let Some(row) = &sample {
            require(
                row.process.host_pid == original.pid
                    && row.process.host_parent_pid == original.ppid
                    && row.process.pidfd == node(target)?
                    && row.process.host_uids
                        == [original.ruid, original.euid, original.suid, original.fsuid]
                    && row.process.host_gids
                        == [original.rgid, original.egid, original.sgid, original.fsgid],
                "engine reply differs from the parent's original PIDFD",
            )?;
        }
        Ok(sample)
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

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture(symlink: bool) -> (std::path::PathBuf, File, File) {
        let root = std::env::temp_dir().join(format!(
            "droidloom-engine-filter-{}-{}",
            std::process::id(),
            if symlink { "link" } else { "file" }
        ));
        std::fs::create_dir(&root).unwrap();
        std::fs::create_dir_all(root.join("system/system_ext/lib64")).unwrap();
        std::fs::create_dir_all(root.join("system/bin")).unwrap();
        std::fs::create_dir_all(root.join("apex/com.android.art/lib64")).unwrap();
        std::fs::write(
            root.join("system/bin/app_process64"),
            b"public executable fixture",
        )
        .unwrap();
        std::fs::write(
            root.join("apex/com.android.art/lib64/libart.so"),
            b"public ART fixture",
        )
        .unwrap();
        let engine = root.join("system/system_ext/lib64/libberberis_arm64.so");
        if symlink {
            std::fs::write(root.join("other"), b"public test fixture").unwrap();
            std::os::unix::fs::symlink("../../../other", engine).unwrap();
        } else {
            std::fs::write(engine, b"public test fixture").unwrap();
        }
        let file = helper::above_reserved(&File::open(&root).unwrap()).unwrap();
        let proc = helper::above_reserved(&File::open("/proc/self").unwrap()).unwrap();
        (root, file, proc)
    }
    fn wait(pid: i32) {
        let mut status = 0;
        assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
        assert_eq!(status, 0, "fixed engine seccomp child wait status");
    }
    #[test]
    fn engine_observer_filter_has_real_fixed_read_and_side_effect_complements() {
        let (path, root, proc) = fixture(false);
        let program = read_filter();
        let copied_name = CString::new(ENGINE_NAME.to_bytes()).unwrap();
        let copied_how = OpenHow {
            flags: ENGINE_HOW.flags,
            mode: 0,
            resolve: ENGINE_HOW.resolve,
        };
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            unsafe {
                if libc::dup2(proc.as_raw_fd(), PROC) != PROC
                    || libc::dup2(root.as_raw_fd(), ROOT_FD) != ROOT_FD
                    || libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
                {
                    libc::_exit(91)
                }
            }
            if helper::install_filter(&program).is_err() {
                unsafe { libc::_exit(92) }
            }
            let maps = unsafe { libc::openat(PROC, MAPS.as_ptr(), TEXT_FLAGS) };
            if maps < 0 {
                unsafe { libc::_exit(93) }
            }
            unsafe {
                libc::close(maps);
            }
            // The executable is only an inode witness, never a readable FD.
            let exe = unsafe { libc::openat(PROC, EXE.as_ptr(), EXE_FLAGS) };
            let mut st: libc::stat = unsafe { mem::zeroed() };
            let mut byte = 0_u8;
            if exe < 0
                || unsafe { libc::fstat(exe, &mut st) } != 0
                || st.st_mode & libc::S_IFMT != libc::S_IFREG
                || unsafe { libc::read(exe, (&mut byte as *mut u8).cast(), 1) } != -1
                || io::Error::last_os_error().raw_os_error() != Some(libc::EBADF)
            {
                unsafe { libc::_exit(99) }
            }
            unsafe {
                libc::close(exe);
            }
            let engine = unsafe {
                libc::syscall(
                    libc::SYS_openat2,
                    ROOT_FD,
                    ENGINE_NAME.as_ptr(),
                    &ENGINE_HOW as *const OpenHow,
                    mem::size_of::<OpenHow>(),
                )
            };
            if engine < 0 {
                unsafe { libc::_exit(94) }
            }
            unsafe {
                libc::close(engine as i32);
            }
            for name in [NATIVE_EXE_NAME, NATIVE_ART_NAME] {
                let fd = unsafe {
                    libc::syscall(
                        libc::SYS_openat2,
                        ROOT_FD,
                        name.as_ptr(),
                        &ENGINE_HOW as *const OpenHow,
                        mem::size_of::<OpenHow>(),
                    )
                };
                if fd < 0 {
                    unsafe { libc::_exit(100) }
                }
                let mut vf: libc::statvfs = unsafe { mem::zeroed() };
                if unsafe { libc::fstatvfs(fd as i32, &mut vf) } != 0 || vf.f_bsize == 0 {
                    unsafe { libc::_exit(101) }
                }
                unsafe {
                    libc::close(fd as i32);
                }
            }
            for (name, how) in [
                (copied_name.as_ptr(), &ENGINE_HOW as *const OpenHow),
                (ENGINE_NAME.as_ptr(), &copied_how as *const OpenHow),
            ] {
                let got = unsafe {
                    libc::syscall(
                        libc::SYS_openat2,
                        ROOT_FD,
                        name,
                        how,
                        mem::size_of::<OpenHow>(),
                    )
                };
                if got != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::EPERM) {
                    unsafe { libc::_exit(95) }
                }
            }
            let copied_maps = c"mem";
            let got = unsafe { libc::openat(PROC, copied_maps.as_ptr(), TEXT_FLAGS) };
            if got != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::EPERM) {
                unsafe { libc::_exit(96) }
            }
            for call in [
                libc::SYS_ptrace,
                libc::SYS_pidfd_open,
                libc::SYS_pidfd_send_signal,
                libc::SYS_kill,
                libc::SYS_clone3,
                libc::SYS_setns,
                libc::SYS_capset,
                libc::SYS_execveat,
                libc::SYS_write,
                libc::SYS_socket,
                libc::SYS_mount,
                libc::SYS_unlinkat,
                libc::SYS_getdents64,
            ] {
                let got = unsafe { libc::syscall(call, -1_i64, 0_i64, 0_i64, 0_i64, 0_i64, 0_i64) };
                if got != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::EPERM) {
                    unsafe { libc::_exit(97) }
                }
            }
            for call in [libc::SYS_mmap, libc::SYS_mprotect] {
                let got = unsafe {
                    libc::syscall(
                        call,
                        0_u64,
                        4096_u64,
                        libc::PROT_READ | libc::PROT_EXEC,
                        libc::MAP_PRIVATE | libc::MAP_ANONYMOUS,
                        -1_i64,
                        0_i64,
                    )
                };
                if got != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::EPERM) {
                    unsafe { libc::_exit(98) }
                }
            }
            unsafe { libc::_exit(0) }
        }
        wait(pid);
        std::fs::remove_dir_all(path).unwrap();
    }
    #[test]
    fn engine_observer_real_openat2_rejects_symlink_at_fixed_engine() {
        let (path, root, proc) = fixture(true);
        let program = read_filter();
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            unsafe {
                if libc::dup2(proc.as_raw_fd(), PROC) != PROC
                    || libc::dup2(root.as_raw_fd(), ROOT_FD) != ROOT_FD
                    || libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
                {
                    libc::_exit(91)
                }
            }
            if helper::install_filter(&program).is_err() {
                unsafe { libc::_exit(92) }
            }
            let got = unsafe {
                libc::syscall(
                    libc::SYS_openat2,
                    ROOT_FD,
                    ENGINE_NAME.as_ptr(),
                    &ENGINE_HOW as *const OpenHow,
                    mem::size_of::<OpenHow>(),
                )
            };
            if got != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::ELOOP) {
                unsafe { libc::_exit(93) }
            }
            unsafe { libc::_exit(0) }
        }
        wait(pid);
        std::fs::remove_dir_all(path).unwrap();
    }
    #[test]
    fn engine_observer_birth_keeps_original_lineage_and_rejects_terminal() {
        let text = format!("41 (odd ) name) S 31 {} 901 0\n", ["0"; 17].join(" "));
        assert_eq!(birth(&text, 41).unwrap(), (41, 31, 901));
        assert!(birth(&text, 42).is_err());
        assert!(birth(&text.replacen(" S ", " Z ", 1), 41).is_err());
        assert!(birth("41 (short) S 31", 41).is_err());
    }
    #[test]
    fn engine_observer_rejects_unconfined_direct_entry() {
        assert!(entry().is_err());
    }

    #[test]
    fn engine_namespace_pid_comes_only_from_the_same_host_proc_status() {
        let text = "Name:\tclock\nPid:\t5678\nTgid:\t5678\nNSpid:\t5678\t432\nNStgid:\t5678\t432\n";
        assert_eq!(guest_process_id(text, 5678).unwrap(), 432);
        for bad in [
            text.replace("NSpid:\t5678\t432", "NSpid:\t5678"),
            text.replace("NSpid:\t5678\t432", "NSpid:\t5678\t432\t21"),
            text.replace("NStgid:\t5678\t432", "NStgid:\t5678\t433"),
            text.replace("Pid:\t5678", "Pid:\t5679"),
            text.replace("\t432", "\t0432"),
            format!("{text}NSpid:\t5678\t432\n"),
        ] {
            assert!(guest_process_id(&bad, 5678).is_err(), "{bad}");
        }
        assert!(guest_process_id(text, 5679).is_err());
        // Equality of numeric host/guest PIDs by coincidence is not a foreign
        // namespace. The held namespace identities are checked separately.
        assert_eq!(
            guest_process_id(&text.replace("\t432", "\t5678"), 5678).unwrap(),
            5678
        );
    }
}
