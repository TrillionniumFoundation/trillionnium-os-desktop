//! Private, descriptor-owned /dev for one admitted mapped Android tree.
//!
//! Only the seven fixed character nodes below are created, on a fresh detached
//! tmpfs. No host device pathname is opened, bind-mounted, chowned or chmodded.
//! Namespace/lease authority is borrowed from the existing owned tree. A failed
//! or uncertain transfer retains the mount, namespace FDs and reservation until
//! the same tree supplies its actual retirement witness.
use std::ffi::CStr;
use std::fs::File;
use std::io::{self, Read};
use std::os::fd::{AsFd, AsRawFd, BorrowedFd, FromRawFd, IntoRawFd};
use std::os::unix::fs::MetadataExt;
use thiserror::Error;

use crate::IdRange;
use crate::production_identity::IdentityError;
use crate::production_namespace::{NamespaceError, OwnedNamespaceWitness, RetiredTreeWitness};

const TMPFS_MAGIC: libc::c_long = 0x0102_1994;
const NSFS_MAGIC: libc::c_long = 0x6e73_6673;
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const NS_GET_ID: libc::c_ulong = 0x8008_b70d;
const INITIAL_USERNS_INODE: u64 = 0xefff_fffd;
const INITIAL_USERNS_ID: u64 = 3;
const AT_EMPTY_PATH: u32 = 0x1000;
const STATX_MNT_ID: u32 = 0x1000;
const MOUNT_ATTR_RDONLY: u64 = 1;
const MOUNT_ATTR_NOSUID: u64 = 2;
const MOUNT_ATTR_NODEV: u64 = 4;
const MOUNT_ATTR_NOEXEC: u64 = 8;
const MOUNT_ATTR_IDMAP: u64 = 0x0010_0000;
const PRIVATE_DEV_FLAGS: u64 = MOUNT_ATTR_NOSUID | MOUNT_ATTR_NOEXEC;
const TMPFS_MAX_BYTES: u64 = 64 * 1024 * 1024;
const TMPFS_MAX_INODES: u64 = 16_384;
const O_SAFE: i32 = libc::O_CLOEXEC | libc::O_NOFOLLOW;
const PROC_LIMIT: u64 = 65_536;
const MOUNTINFO_LIMIT: u64 = 16 * 1024 * 1024;

#[derive(Debug, Error)]
pub(crate) enum DeviceError {
    #[error("private device mount rejected: {0}")]
    Rejected(&'static str),
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Namespace(#[from] NamespaceError),
    #[error(transparent)]
    Identity(#[from] IdentityError),
}
type Result<T> = std::result::Result<T, DeviceError>;

fn need(ok: bool, why: &'static str) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(DeviceError::Rejected(why))
    }
}
fn fd_result(value: libc::c_long) -> Result<File> {
    if value < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let fd = i32::try_from(value).map_err(|_| DeviceError::Rejected("descriptor overflow"))?;
    // SAFETY: this successful syscall returned a new owned descriptor.
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn zero(value: libc::c_long) -> Result<()> {
    if value == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error().into())
    }
}
fn bounded(mut file: File, limit: u64) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    (&mut file).take(limit + 1).read_to_end(&mut bytes)?;
    need(
        bytes.len() as u64 <= limit,
        "complete bounded kernel observation",
    )?;
    Ok(bytes)
}
fn open_at(parent: &File, name: &CStr, flags: i32) -> Result<File> {
    // SAFETY: the parent is held and the name is a fixed single component.
    fd_result(unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), flags | O_SAFE) } as _)
}
fn node(file: &File) -> Result<(u64, u64)> {
    let m = file.metadata()?;
    Ok((m.dev(), m.ino()))
}
fn fs_type(file: &File) -> Result<libc::c_long> {
    let mut value: libc::statfs = unsafe { std::mem::zeroed() };
    zero(unsafe { libc::fstatfs(file.as_raw_fd(), &mut value) } as _)?;
    Ok(value.f_type)
}
fn namespace(file: &File, kind: i32) -> Result<(u64, u64)> {
    need(fs_type(file)? == NSFS_MAGIC, "actual namespace filesystem")?;
    need(
        unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE, 0) } == kind,
        "exact namespace type",
    )?;
    node(file)
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

fn require_initial_broker() -> Result<()> {
    need(
        unsafe { libc::getuid() } == 0 && unsafe { libc::geteuid() } == 0,
        "actual initial root device broker",
    )?;
    // This fixed calling-thread magic link is the observed namespace itself,
    // never a caller-selected path or an authority supplied by a saved receipt.
    let ns = File::open("/proc/thread-self/ns/user")?;
    let (_, inode) = namespace(&ns, libc::CLONE_NEWUSER)?;
    let mut id = 0_u64;
    zero(unsafe { libc::ioctl(ns.as_raw_fd(), NS_GET_ID, &mut id) } as _)?;
    need(
        inode == INITIAL_USERNS_INODE && id == INITIAL_USERNS_ID,
        "kernel-confirmed initial user namespace",
    )?;
    let status = bounded(File::open("/proc/thread-self/status")?, PROC_LIMIT)?;
    let status = std::str::from_utf8(&status)
        .map_err(|_| DeviceError::Rejected("kernel credential encoding"))?;
    for field in ["Uid:", "Gid:"] {
        let values: Vec<_> = status
            .lines()
            .filter_map(|line| line.strip_prefix(field))
            .collect();
        need(values.len() == 1, "one kernel credential row")?;
        let values: Vec<_> = values[0].split_ascii_whitespace().collect();
        need(
            values == ["0", "0", "0", "0"],
            "real/effective/saved/filesystem root credentials",
        )?;
    }
    let mut header = CapHeader {
        version: 0x2008_0522,
        pid: 0,
    };
    let mut caps = [CapData::default(); 2];
    zero(unsafe { libc::syscall(libc::SYS_capget, &mut header, caps.as_mut_ptr()) })?;
    let required = (1_u32 << 21) | (1_u32 << 27); // CAP_SYS_ADMIN + CAP_MKNOD.
    need(
        caps[0].effective & required == required && caps[0].permitted & required == required,
        "initial namespace mount and mknod capabilities",
    )?;
    Ok(())
}
fn map_is_exact(raw: &[u8], range: IdRange) -> Result<()> {
    let text = std::str::from_utf8(raw).map_err(|_| DeviceError::Rejected("ID map encoding"))?;
    need(
        text.ends_with('\n') && text.lines().count() == 1,
        "one complete ID-map row",
    )?;
    let words: Vec<_> = text.split_ascii_whitespace().collect();
    need(
        words.len() == 3
            && words
                .iter()
                .all(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())),
        "three decimal ID-map values",
    )?;
    let values = words
        .iter()
        .map(|s| {
            s.parse::<u64>()
                .map_err(|_| DeviceError::Rejected("ID-map overflow"))
        })
        .collect::<Result<Vec<_>>>()?;
    need(
        values == [0, u64::from(range.start), u64::from(range.count)],
        "same reserved complete ID map",
    )
}
fn require_tree(witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
    witness.revalidate()?;
    let (uids, gids) = witness.identity_lease()?.broker_ranges();
    for (name, range) in [(c"uid_map", uids), (c"gid_map", gids)] {
        map_is_exact(
            &bounded(
                open_at(witness.proc_directory(), name, libc::O_RDONLY)?,
                PROC_LIMIT,
            )?,
            range,
        )?;
    }
    need(
        bounded(
            open_at(witness.proc_directory(), c"setgroups", libc::O_RDONLY)?,
            PROC_LIMIT,
        )? == b"allow\n",
        "complete supplementary group semantics",
    )?;
    namespace(witness.user_namespace(), libc::CLONE_NEWUSER)?;
    let pidns = witness
        .descendant_pid_namespace()
        .ok_or(DeviceError::Rejected(
            "actual owned PID 1 namespace required",
        ))?;
    namespace(pidns, libc::CLONE_NEWPID)?;
    witness.revalidate()?;
    Ok(())
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct DeviceSpec {
    name: &'static CStr,
    major: u32,
    minor: u32,
}
const DEVICES: [DeviceSpec; 7] = [
    DeviceSpec {
        name: c"null",
        major: 1,
        minor: 3,
    },
    DeviceSpec {
        name: c"zero",
        major: 1,
        minor: 5,
    },
    DeviceSpec {
        name: c"full",
        major: 1,
        minor: 7,
    },
    DeviceSpec {
        name: c"random",
        major: 1,
        minor: 8,
    },
    DeviceSpec {
        name: c"urandom",
        major: 1,
        minor: 9,
    },
    DeviceSpec {
        name: c"tty",
        major: 5,
        minor: 0,
    },
    DeviceSpec {
        name: c"fuse",
        major: 10,
        minor: 229,
    },
];
fn spec_for(name: &[u8]) -> Result<DeviceSpec> {
    DEVICES
        .iter()
        .copied()
        .find(|s| s.name.to_bytes() == name)
        .ok_or(DeviceError::Rejected("unapproved private device role"))
}

#[repr(C)]
#[derive(Default)]
struct MountAttr {
    attr_set: u64,
    attr_clr: u64,
    propagation: u64,
    userns_fd: u64,
}
fn configure(context: &File, key: &CStr, value: Option<&CStr>) -> Result<()> {
    zero(unsafe {
        libc::syscall(
            libc::SYS_fsconfig,
            context.as_raw_fd(),
            if value.is_some() { 1_u32 } else { 0_u32 },
            key.as_ptr(),
            value.map_or(std::ptr::null(), CStr::as_ptr),
            0,
        )
    })
}
fn mount_id(file: &File) -> Result<u64> {
    let mut s: libc::statx = unsafe { std::mem::zeroed() };
    zero(unsafe {
        libc::syscall(
            libc::SYS_statx,
            file.as_raw_fd(),
            c"".as_ptr(),
            AT_EMPTY_PATH,
            STATX_MNT_ID,
            &mut s,
        )
    })?;
    need(
        s.stx_mask & STATX_MNT_ID != 0 && s.stx_mnt_id != 0,
        "actual kernel mount identity",
    )?;
    Ok(s.stx_mnt_id)
}
fn require_detached(file: &File) -> Result<u64> {
    let id = mount_id(file)?;
    let raw = bounded(File::open("/proc/thread-self/mountinfo")?, MOUNTINFO_LIMIT)?;
    let text =
        std::str::from_utf8(&raw).map_err(|_| DeviceError::Rejected("mount inventory encoding"))?;
    need(text.ends_with('\n'), "complete kernel mount inventory")?;
    for line in text.lines() {
        let current = line
            .split_ascii_whitespace()
            .next()
            .ok_or(DeviceError::Rejected("mount inventory row"))?
            .parse::<u64>()
            .map_err(|_| DeviceError::Rejected("mount inventory ID"))?;
        need(
            current != id,
            "private device mount attached to broker namespace",
        )?;
    }
    need(mount_id(file)? == id, "stable held mount identity")?;
    Ok(id)
}
fn fresh_tmpfs() -> Result<File> {
    require_initial_broker()?;
    let context = fd_result(unsafe { libc::syscall(libc::SYS_fsopen, c"tmpfs".as_ptr(), 1_u32) })?;
    for (key, value) in [
        (c"mode", c"0755"),
        (c"uid", c"0"),
        (c"gid", c"0"),
        (c"size", c"64m"),
        (c"nr_inodes", c"16384"),
        (c"huge", c"never"),
    ] {
        configure(&context, key, Some(value))?;
    }
    configure(&context, c"noswap", None)?;
    zero(unsafe {
        libc::syscall(
            libc::SYS_fsconfig,
            context.as_raw_fd(),
            6_u32,
            std::ptr::null::<libc::c_char>(),
            std::ptr::null::<libc::c_char>(),
            0,
        )
    })?;
    let mount = fd_result(unsafe {
        libc::syscall(
            libc::SYS_fsmount,
            context.as_raw_fd(),
            1_u32,
            PRIVATE_DEV_FLAGS as u32,
        )
    })?;
    require_detached(&mount)?;
    verify_root(&mount, 0, 0)?;
    need(
        directory_names(&mount)?.is_empty(),
        "new empty private tmpfs",
    )?;
    Ok(mount)
}
fn verify_root(mount: &File, uid: u32, gid: u32) -> Result<()> {
    let m = mount.metadata()?;
    need(
        m.is_dir() && m.mode() & 0o7777 == 0o755 && m.uid() == uid && m.gid() == gid,
        "exact mapped private dev root",
    )?;
    need(fs_type(mount)? == TMPFS_MAGIC, "private tmpfs filesystem")?;
    let mut v: libc::statvfs = unsafe { std::mem::zeroed() };
    zero(unsafe { libc::fstatvfs(mount.as_raw_fd(), &mut v) } as _)?;
    let flags = v.f_flag as u64;
    need(
        flags & PRIVATE_DEV_FLAGS == PRIVATE_DEV_FLAGS
            && flags & (MOUNT_ATTR_RDONLY | MOUNT_ATTR_NODEV) == 0,
        "writable device-enabled nosuid noexec mount",
    )?;
    let total = (v.f_blocks as u64)
        .checked_mul(v.f_frsize as u64)
        .ok_or(DeviceError::Rejected("tmpfs capacity overflow"))?;
    need(
        total == TMPFS_MAX_BYTES && v.f_files as u64 == TMPFS_MAX_INODES,
        "exact bounded private tmpfs capacity",
    )?;
    Ok(())
}
struct Directory(*mut libc::DIR);
impl Drop for Directory {
    fn drop(&mut self) {
        unsafe {
            libc::closedir(self.0);
        }
    }
}
fn directory_names(root: &File) -> Result<Vec<Vec<u8>>> {
    let file = open_at(root, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
    let raw = file.into_raw_fd();
    let dir = unsafe { libc::fdopendir(raw) };
    if dir.is_null() {
        let error = io::Error::last_os_error();
        unsafe {
            libc::close(raw);
        }
        return Err(error.into());
    }
    let directory = Directory(dir);
    let mut names = Vec::new();
    loop {
        // readdir uses this thread's errno; distinguish EOF from an actual failure.
        unsafe {
            *libc::__errno_location() = 0;
        }
        let entry = unsafe { libc::readdir(directory.0) };
        if entry.is_null() {
            let error = io::Error::last_os_error();
            need(
                error.raw_os_error() == Some(0),
                "complete private directory enumeration",
            )?;
            break;
        }
        let name = unsafe { CStr::from_ptr((*entry).d_name.as_ptr()) }.to_bytes();
        if name == b"." || name == b".." {
            continue;
        }
        need(names.len() < DEVICES.len(), "unexpected private dev entry")?;
        names.push(name.to_vec());
    }
    names.sort();
    need(
        names.windows(2).all(|pair| pair[0] != pair[1]),
        "duplicate private dev entry",
    )?;
    Ok(names)
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct DeviceIdentity {
    device: u64,
    inode: u64,
    mode: u32,
    rdev: u64,
    nlink: u64,
    modified: (i64, i64),
    changed: (i64, i64),
}
fn identity(m: &std::fs::Metadata) -> DeviceIdentity {
    DeviceIdentity {
        device: m.dev(),
        inode: m.ino(),
        mode: m.mode(),
        rdev: m.rdev(),
        nlink: m.nlink(),
        modified: (m.mtime(), m.mtime_nsec()),
        changed: (m.ctime(), m.ctime_nsec()),
    }
}
fn verify_device(
    file: &File,
    spec: DeviceSpec,
    uid: u32,
    gid: u32,
    filesystem: u64,
) -> Result<DeviceIdentity> {
    let m = file.metadata()?;
    need(
        m.dev() == filesystem
            && m.mode() == (libc::S_IFCHR | 0o666)
            && m.nlink() == 1
            && m.uid() == uid
            && m.gid() == gid
            && m.rdev() == libc::makedev(spec.major, spec.minor),
        "exact new private character node identity",
    )?;
    Ok(identity(&m))
}
fn create_devices(root: &File) -> Result<Vec<DeviceIdentity>> {
    let fs = root.metadata()?.dev();
    let mut identities = Vec::with_capacity(DEVICES.len());
    for spec in DEVICES {
        zero(unsafe {
            libc::mknodat(
                root.as_raw_fd(),
                spec.name.as_ptr(),
                libc::S_IFCHR | 0o600,
                libc::makedev(spec.major, spec.minor),
            )
        } as _)?;
        // O_PATH never opens the character driver. chmod applies to this held
        // new inode, not a host alias, and does not modify process-global umask.
        let file = open_at(root, spec.name, libc::O_PATH)?;
        let before = file.metadata()?;
        need(
            before.dev() == fs
                && before.mode() & libc::S_IFMT == libc::S_IFCHR
                && before.nlink() == 1
                && before.uid() == 0
                && before.gid() == 0
                && before.rdev() == libc::makedev(spec.major, spec.minor),
            "new mknodat result",
        )?;
        zero(unsafe {
            libc::syscall(
                libc::SYS_fchmodat2,
                file.as_raw_fd(),
                c"".as_ptr(),
                0o666_u32,
                AT_EMPTY_PATH,
            )
        })?;
        need(
            node(&file)? == (before.dev(), before.ino()),
            "same newly created inode",
        )?;
        identities.push(verify_device(&file, spec, 0, 0, fs)?);
    }
    verify_devices(root, 0, 0, &identities)?;
    Ok(identities)
}
fn verify_devices(root: &File, uid: u32, gid: u32, identities: &[DeviceIdentity]) -> Result<()> {
    need(
        identities.len() == DEVICES.len(),
        "complete fixed seven-node input",
    )?;
    let mut expected: Vec<_> = DEVICES.iter().map(|s| s.name.to_bytes().to_vec()).collect();
    expected.sort();
    need(
        directory_names(root)? == expected,
        "only the exact seven private device nodes",
    )?;
    let fs = root.metadata()?.dev();
    for (spec, expected) in DEVICES.iter().zip(identities) {
        let file = open_at(root, spec.name, libc::O_PATH)?;
        need(
            verify_device(&file, *spec, uid, gid, fs)? == *expected,
            "device inode or metadata changed before transfer",
        )?;
    }
    Ok(())
}
fn idmap_mount(root: &File, userns: &File) -> Result<()> {
    let attr = MountAttr {
        attr_set: PRIVATE_DEV_FLAGS | MOUNT_ATTR_IDMAP,
        userns_fd: u64::try_from(userns.as_raw_fd())
            .map_err(|_| DeviceError::Rejected("userns FD"))?,
        ..MountAttr::default()
    };
    zero(unsafe {
        libc::syscall(
            libc::SYS_mount_setattr,
            root.as_raw_fd(),
            c"".as_ptr(),
            AT_EMPTY_PATH,
            &attr,
            std::mem::size_of::<MountAttr>(),
        )
    })
}

#[derive(Debug)]
struct DeviceResources {
    mount: Option<File>,
    mount_id: u64,
    root_node: (u64, u64),
    nodes: Vec<DeviceIdentity>,
    userns: File,
    userns_node: (u64, u64),
    pidns: File,
    pidns_node: (u64, u64),
    host_uid: u32,
    cohort: String,
    uids: IdRange,
    gids: IdRange,
    reservation_retention: File,
}
impl DeviceResources {
    fn matches(&self, witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
        require_tree(witness)?;
        let lease = witness.identity_lease()?;
        let pidns = witness
            .descendant_pid_namespace()
            .ok_or(DeviceError::Rejected("owned PID namespace missing"))?;
        need(
            node(witness.user_namespace())? == self.userns_node
                && node(&self.userns)? == self.userns_node
                && node(pidns)? == self.pidns_node
                && node(&self.pidns)? == self.pidns_node
                && lease.host_uid() == self.host_uid
                && lease.broker_cohort() == self.cohort
                && lease.broker_ranges() == (self.uids, self.gids),
            "same owned tree, user namespace, cohort and reservation",
        )?;
        Ok(())
    }
    fn verify_for_transfer(&self) -> Result<()> {
        let mount = self
            .mount
            .as_ref()
            .ok_or(DeviceError::Rejected("private dev mount absent"))?;
        need(
            require_detached(mount)? == self.mount_id && node(mount)? == self.root_node,
            "same detached private mount and root",
        )?;
        verify_root(mount, self.uids.start, self.gids.start)?;
        verify_devices(mount, self.uids.start, self.gids.start, &self.nodes)
    }
    fn close_owned_mount(&mut self) -> Result<()> {
        if let Some(mount) = self.mount.as_ref() {
            need(
                fs_type(mount)? == TMPFS_MAGIC,
                "owned tmpfs retained until retirement",
            )?;
            if self.mount_id != 0 {
                need(
                    require_detached(mount)? == self.mount_id,
                    "same owned mount at retirement",
                )?;
            } else {
                require_detached(mount)?;
            }
        }
        drop(self.mount.take());
        Ok(())
    }
}

/// Opaque, non-Clone construction; an exported descriptor needs a real retired
/// tree witness. Unknown Drop keeps all resources, including the actual flock.
#[derive(Debug)]
pub(crate) struct PreparedDevices {
    resources: Option<DeviceResources>,
    exported: bool,
}

#[derive(Debug)]
pub(crate) struct DeviceRetirement {
    pub(crate) device_nodes: usize,
    pub(crate) owned_mount_descriptor_closed: bool,
    pub(crate) after_owned_tree_exit: bool,
}
impl PreparedDevices {
    pub(crate) fn prepare(witness: &OwnedNamespaceWitness<'_>) -> Result<Self> {
        require_initial_broker()?;
        witness.revalidate_live_admission()?;
        let result = Self::prepare_bound(witness)?;
        witness.revalidate_live_admission()?;
        Ok(result)
    }
    fn prepare_bound(witness: &OwnedNamespaceWitness<'_>) -> Result<Self> {
        require_initial_broker()?;
        require_tree(witness)?;
        let lease = witness.identity_lease()?;
        let retention = lease.broker_retain_reservation()?;
        let (uids, gids) = lease.broker_ranges();
        let userns = witness.user_namespace().try_clone()?;
        let pidns = witness
            .descendant_pid_namespace()
            .ok_or(DeviceError::Rejected("actual tree is required"))?
            .try_clone()?;
        let mut result = Self {
            exported: false,
            resources: Some(DeviceResources {
                mount: None,
                mount_id: 0,
                root_node: (0, 0),
                nodes: Vec::new(),
                userns_node: node(&userns)?,
                pidns_node: node(&pidns)?,
                userns,
                pidns,
                host_uid: lease.host_uid(),
                cohort: lease.broker_cohort().to_owned(),
                uids,
                gids,
                reservation_retention: retention,
            }),
        };
        let resources = result
            .resources
            .as_mut()
            .ok_or(DeviceError::Rejected("device guard absent"))?;
        resources.matches(witness)?;
        resources.mount = Some(fresh_tmpfs()?);
        let mount = resources
            .mount
            .as_ref()
            .ok_or(DeviceError::Rejected("new private mount absent"))?;
        resources.mount_id = require_detached(mount)?;
        resources.root_node = node(mount)?;
        resources.nodes = create_devices(mount)?;
        idmap_mount(mount, &resources.userns)?;
        resources.verify_for_transfer()?;
        resources.matches(witness)?;
        Ok(result)
    }
    pub(crate) fn descriptor_for_transfer<'a>(
        &'a mut self,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<BorrowedFd<'a>> {
        require_initial_broker()?;
        witness.revalidate_live_admission()?;
        self.descriptor_after_admission(witness)
    }
    fn descriptor_after_admission<'a>(
        &'a mut self,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<BorrowedFd<'a>> {
        need(!self.exported, "one private dev FD transfer attempt")?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(DeviceError::Rejected("device mount retired"))?;
        resources.matches(witness)?;
        resources.verify_for_transfer()?;
        // Mark before any descriptor can leave. A failed send cannot recover
        // the no-transfer cleanup privilege.
        self.exported = true;
        Ok(resources
            .mount
            .as_ref()
            .ok_or(DeviceError::Rejected("device mount absent"))?
            .as_fd())
    }
    pub(crate) fn retire_untransferred(mut self) -> Result<DeviceRetirement> {
        need(
            !self.exported,
            "exported dev requires actual owned tree retirement",
        )?;
        self.cleanup(false)
    }
    pub(crate) fn retire_after_tree(
        mut self,
        retired: &RetiredTreeWitness<'_>,
    ) -> Result<DeviceRetirement> {
        let r = self
            .resources
            .as_ref()
            .ok_or(DeviceError::Rejected("device mount retired"))?;
        retired.verify_mount_retirement(&r.userns, r.host_uid, &r.cohort)?;
        self.cleanup(true)
    }
    fn cleanup(&mut self, after_owned_tree_exit: bool) -> Result<DeviceRetirement> {
        let r = self
            .resources
            .as_mut()
            .ok_or(DeviceError::Rejected("device mount retired"))?;
        let nodes = r.nodes.len();
        r.close_owned_mount()?;
        drop(self.resources.take());
        Ok(DeviceRetirement {
            device_nodes: nodes,
            owned_mount_descriptor_closed: true,
            after_owned_tree_exit,
        })
    }
}
impl Drop for PreparedDevices {
    fn drop(&mut self) {
        if !self.exported {
            if let Some(r) = self.resources.as_mut() {
                if r.close_owned_mount().is_ok() {
                    drop(self.resources.take());
                    return;
                }
            }
        }
        if let Some(r) = self.resources.take() {
            // No LOCK_UN: this duplicate owns the same flock description as
            // the namespace keeper. Unproven lifetime cannot recycle its IDs.
            std::mem::forget(r);
        }
    }
}

/// Root-only real-syscall controls use a separate type with a test fixture
/// witness. This entry and its admission exception do not exist in production.
#[cfg(test)]
pub(crate) mod private_control {
    use super::*;
    pub(crate) struct PrivateControlDevices(PreparedDevices);
    pub(crate) fn prepare_private_control_devices(
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<PrivateControlDevices> {
        require_initial_broker()?;
        let prepared = PreparedDevices::prepare_bound(witness)?;
        Ok(PrivateControlDevices(prepared))
    }
    impl PrivateControlDevices {
        pub(crate) fn verify_original_nodes(&self) -> Result<()> {
            self.0
                .resources
                .as_ref()
                .ok_or(DeviceError::Rejected("private test mount absent"))?
                .verify_for_transfer()
        }
        pub(crate) fn descriptor_for_transfer<'a>(
            &'a mut self,
            witness: &OwnedNamespaceWitness<'_>,
        ) -> Result<BorrowedFd<'a>> {
            self.verify_original_nodes()?;
            self.0.descriptor_after_admission(witness)
        }
        pub(crate) fn retire_untransferred(self) -> Result<DeviceRetirement> {
            self.0.retire_untransferred()
        }
        pub(crate) fn retire_after_tree(
            self,
            retired: &RetiredTreeWitness<'_>,
        ) -> Result<DeviceRetirement> {
            self.0.retire_after_tree(retired)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{OpenOptionsExt, symlink};
    fn directory(path: &std::path::Path) -> File {
        std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | O_SAFE)
            .open(path)
            .unwrap()
    }

    #[test]
    fn seven_fixed_device_roles_and_numbers_are_exact() {
        let actual: Vec<_> = DEVICES
            .iter()
            .map(|s| (s.name.to_bytes(), s.major, s.minor))
            .collect();
        let expected: Vec<(&[u8], u32, u32)> = vec![
            (b"null", 1, 3),
            (b"zero", 1, 5),
            (b"full", 1, 7),
            (b"random", 1, 8),
            (b"urandom", 1, 9),
            (b"tty", 5, 0),
            (b"fuse", 10, 229),
        ];
        assert_eq!(actual, expected);
        for spec in DEVICES {
            assert_eq!(spec_for(spec.name.to_bytes()).unwrap(), spec);
        }
        let mut names: Vec<_> = DEVICES.iter().map(|s| s.name.to_bytes()).collect();
        names.sort();
        names.dedup();
        assert_eq!(names.len(), 7);
    }
    #[test]
    fn privileged_or_path_derived_roles_are_rejected() {
        for name in [
            b"console".as_slice(),
            b"kmsg",
            b"kmsg_debug",
            b"log",
            b"loop-control",
            b"loop0",
            b"binder",
            b"hwbinder",
            b"vndbinder",
            b"dri",
            b"ptmx",
            b"pts",
            b"socket",
            b"fd",
            b"/dev/null",
            b"../null",
            b"null/child",
            b"null\0",
            b"",
        ] {
            assert!(spec_for(name).is_err(), "{name:?}");
        }
    }
    #[test]
    fn id_map_requires_complete_original_group_semantics() {
        let range = IdRange {
            start: 200_000,
            count: 65_536,
        };
        map_is_exact(b"         0     200000      65536\n", range).unwrap();
        for raw in [
            b"0 200000 65536".as_slice(),
            b"0 200000 65536\n1 1 1\n",
            b"0 200000 65536\n\n",
            b"1 200000 65536\n",
            b"0 200001 65536\n",
            b"0 200000 65535\n",
            b"0 200000 65536 extra\n",
            b"0 +200000 65536\n",
            b"0 -1 65536\n",
            b"0 18446744073709551616 65536\n",
            b"0 \xff 65536\n",
        ] {
            assert!(map_is_exact(raw, range).is_err(), "{raw:?}");
        }
    }
    #[test]
    fn actual_directory_enumeration_is_complete_and_bounded() {
        let temp = tempfile::tempdir().unwrap();
        let root = directory(temp.path());
        assert!(directory_names(&root).unwrap().is_empty());
        for spec in DEVICES {
            std::fs::write(
                temp.path().join(spec.name.to_str().unwrap()),
                b"not-a-device",
            )
            .unwrap();
        }
        let mut expected: Vec<_> = DEVICES.iter().map(|s| s.name.to_bytes().to_vec()).collect();
        expected.sort();
        assert_eq!(directory_names(&root).unwrap(), expected);
        std::fs::write(temp.path().join("extra"), b"unapproved").unwrap();
        assert!(directory_names(&root).is_err());
    }
    #[test]
    fn real_regular_file_and_symlink_cannot_be_device_witnesses() {
        let temp = tempfile::tempdir().unwrap();
        let root = directory(temp.path());
        std::fs::write(temp.path().join("regular"), b"ordinary file").unwrap();
        symlink("regular", temp.path().join("null")).unwrap();
        let regular = open_at(&root, c"regular", libc::O_PATH).unwrap();
        let link = open_at(&root, c"null", libc::O_PATH).unwrap();
        let m = regular.metadata().unwrap();
        assert!(verify_device(&regular, DEVICES[0], m.uid(), m.gid(), m.dev()).is_err());
        assert!(link.metadata().unwrap().file_type().is_symlink());
        assert!(verify_device(&link, DEVICES[0], m.uid(), m.gid(), m.dev()).is_err());
        std::fs::hard_link(temp.path().join("regular"), temp.path().join("alias")).unwrap();
        assert_eq!(regular.metadata().unwrap().nlink(), 2);
        assert!(verify_device(&regular, DEVICES[0], m.uid(), m.gid(), m.dev()).is_err());
    }
    #[test]
    fn wrong_retirement_state_cannot_claim_a_mount_was_closed() {
        let missing = PreparedDevices {
            resources: None,
            exported: false,
        };
        assert!(missing.retire_untransferred().is_err());
        let attempted = PreparedDevices {
            resources: None,
            exported: true,
        };
        assert!(matches!(
            attempted.retire_untransferred(),
            Err(DeviceError::Rejected(
                "exported dev requires actual owned tree retirement"
            ))
        ));
    }
}
