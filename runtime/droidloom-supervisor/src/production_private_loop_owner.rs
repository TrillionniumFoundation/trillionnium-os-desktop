//! Fresh detached tmpfs and finite aliases for the 38 fixed original APEX roles.
//! No caller path, label, extent or ioctl opcode is accepted. Unknown binding
//! outcomes retain the original descriptors, source and private mount.
use crate::production_execution_profile::apex_inputs::{self, archive::VerifiedArchive};
#[path = "production_capex_archive.rs"]
pub(crate) mod compressed;
use crate::production_mac::{MacError, MacPreflight, MacPrivateLoopWitness, PrivateLoopNode};
use crate::production_selection::ProductionSelection;
use compressed::{ImmutableCapex, MatchedDecompressedCapex};
use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::{CStr, CString};
use std::fs::File;
use std::io::{self, Read};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::MetadataExt;
use std::rc::Rc;
use std::time::Instant;
use thiserror::Error;
const DIRECTORY: &CStr = c"droidloom-apex-devices";
const CONTROL: &CStr = c"loop-control";
const TMPFS_MAGIC: i64 = 0x0102_1994;
const SYSFS_MAGIC: i64 = 0x6265_6572;
const MOUNTINFO_MAX: usize = 16 * 1024 * 1024;
const FLAGS: u32 = 1 | 4;
const SAFE: i32 = libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK;

#[derive(Debug, Error)]
pub(crate) enum PrivateLoopError {
    #[error("private loop owner rejected: {0}")]
    Rejected(&'static str),
    #[error("private loop remains busy; original ownership retained")]
    Busy,
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Mac(#[from] MacError),
}
type Result<T> = std::result::Result<T, PrivateLoopError>;
fn need(ok: bool, why: &'static str) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(PrivateLoopError::Rejected(why))
    }
}
fn zero(rc: libc::c_long) -> Result<()> {
    if rc == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error().into())
    }
}
fn new_fd(rc: libc::c_long) -> Result<File> {
    if rc < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let fd = i32::try_from(rc).map_err(|_| PrivateLoopError::Rejected("descriptor overflow"))?;
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn open(parent: &File, name: &CStr, flags: i32) -> Result<File> {
    new_fd(unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), flags | SAFE) } as libc::c_long)
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Stamp {
    dev: u64,
    ino: u64,
    rdev: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    size: u64,
    mtime: (i64, i64),
    ctime: (i64, i64),
}
impl Stamp {
    fn of(file: &File) -> Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            dev: m.dev(),
            ino: m.ino(),
            rdev: m.rdev(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            links: m.nlink(),
            size: m.len(),
            mtime: (m.mtime(), m.mtime_nsec()),
            ctime: (m.ctime(), m.ctime_nsec()),
        })
    }
    fn same_directory(self, other: Self) -> bool {
        (self.dev, self.ino, self.rdev, self.mode, self.uid, self.gid)
            == (
                other.dev, other.ino, other.rdev, other.mode, other.uid, other.gid,
            )
    }
    fn after_unlink(self, other: Self) -> bool {
        self.links > 0
            && other.links == 0
            && self.same_directory(other)
            && self.size == other.size
            && self.mtime == other.mtime
    }
}
fn node_kind(file: &File, kind: u32, mode: u32, rdev: Option<u64>) -> Result<Stamp> {
    let s = Stamp::of(file)?;
    need(
        s.mode == (kind | mode)
            && s.uid == 0
            && s.gid == 0
            && (kind == libc::S_IFDIR || s.links == 1)
            && rdev.is_none_or(|dev| s.rdev == dev),
        "exact private inode type, mode, root ownership, links and device",
    )?;
    Ok(s)
}
fn mount_id(file: &File) -> Result<u64> {
    let mut s: libc::statx = unsafe { std::mem::zeroed() };
    zero(unsafe {
        libc::syscall(
            libc::SYS_statx,
            file.as_raw_fd(),
            c"".as_ptr(),
            libc::AT_EMPTY_PATH,
            0x1000_u32,
            &mut s,
        )
    })?;
    need(
        s.stx_mask & 0x1000 != 0 && s.stx_mnt_id != 0,
        "actual held mount ID",
    )?;
    Ok(s.stx_mnt_id)
}
fn statfs(file: &File) -> Result<libc::statfs> {
    let mut s: libc::statfs = unsafe { std::mem::zeroed() };
    zero(unsafe { libc::fstatfs(file.as_raw_fd(), &mut s) } as libc::c_long)?;
    Ok(s)
}
fn filesystem(file: &File) -> Result<(i64, [u8; 8], u64)> {
    let s = statfs(file)?;
    const _: () = assert!(std::mem::size_of::<libc::fsid_t>() == 8);
    let fsid = unsafe { std::mem::transmute::<libc::fsid_t, [u8; 8]>(s.f_fsid) };
    let mut v: libc::statvfs = unsafe { std::mem::zeroed() };
    zero(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut v) } as libc::c_long)?;
    Ok((s.f_type as i64, fsid, v.f_flag as u64))
}
fn tmpfs_limits(file: &File) -> Result<()> {
    let s = statfs(file)?;
    need(
        s.f_type as i64 == TMPFS_MAGIC
            && s.f_bsize > 0
            && (s.f_blocks as u64).checked_mul(s.f_bsize as u64) == Some(65536)
            && s.f_files == 64,
        "actual private tmpfs retains 64 KiB and 64 inode limits",
    )
}
fn mount_inventory_absent(bytes: &[u8], id: u64) -> Result<()> {
    need(
        !bytes.is_empty() && bytes.len() <= MOUNTINFO_MAX && bytes.ends_with(b"\n"),
        "complete bounded mount inventory",
    )?;
    let text = std::str::from_utf8(bytes)
        .map_err(|_| PrivateLoopError::Rejected("mount inventory encoding"))?;
    let mut ids = BTreeSet::new();
    for row in text.lines() {
        let fields: Vec<_> = row.split_ascii_whitespace().collect();
        need(
            fields.len() >= 10 && fields.iter().filter(|v| **v == "-").count() == 1,
            "complete mount inventory row",
        )?;
        let current = fields[0]
            .parse::<u64>()
            .map_err(|_| PrivateLoopError::Rejected("mount inventory ID"))?;
        need(
            current != 0 && current != id && ids.insert(current),
            "private mount attached or duplicate inventory ID",
        )?;
    }
    Ok(())
}
fn detached(file: &File, id: u64) -> Result<()> {
    need(mount_id(file)? == id, "same held private mount")?;
    let f = File::open("/proc/thread-self/mountinfo")?;
    need(
        filesystem(&f)?.0 == 0x9fa0,
        "mount inventory must be actual procfs",
    )?;
    let mut raw = Vec::new();
    f.take((MOUNTINFO_MAX + 1) as u64).read_to_end(&mut raw)?;
    mount_inventory_absent(&raw, id)?;
    need(
        mount_id(file)? == id,
        "private mount changed during complete inventory",
    )
}
fn fresh_tmpfs() -> Result<(File, File)> {
    let context = new_fd(unsafe { libc::syscall(libc::SYS_fsopen, c"tmpfs".as_ptr(), 1_u32) })?;
    for (key, value) in [
        (c"mode", c"0700"),
        (c"uid", c"0"),
        (c"gid", c"0"),
        (c"size", c"65536"),
        (c"nr_inodes", c"64"),
    ] {
        zero(unsafe {
            libc::syscall(
                libc::SYS_fsconfig,
                context.as_raw_fd(),
                1_u32,
                key.as_ptr(),
                value.as_ptr(),
                0,
            )
        })?;
    }
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
    let mount = new_fd(unsafe {
        libc::syscall(libc::SYS_fsmount, context.as_raw_fd(), 1_u32, 2_u32 | 8_u32)
    })?;
    let root = open(&mount, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
    need(
        Stamp::of(&mount)? == Stamp::of(&root)?,
        "fresh mount root descriptor custody",
    )?;
    Ok((mount, root))
}
fn names(directory: &File) -> Result<BTreeSet<Vec<u8>>> {
    let file = open(directory, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
    let raw = unsafe { libc::fdopendir(file.as_raw_fd()) };
    if raw.is_null() {
        return Err(io::Error::last_os_error().into());
    }
    std::mem::forget(file);
    struct Directory(*mut libc::DIR);
    impl Drop for Directory {
        fn drop(&mut self) {
            unsafe {
                libc::closedir(self.0);
            }
        }
    }
    let guard = Directory(raw);
    let mut observed = BTreeSet::new();
    let mut count = 0;
    loop {
        unsafe {
            *libc::__errno_location() = 0;
        }
        let entry = unsafe { libc::readdir(guard.0) };
        if entry.is_null() {
            let error = io::Error::last_os_error();
            if error.raw_os_error() != Some(0) {
                return Err(error.into());
            }
            break;
        }
        count += 1;
        need(count <= 64, "bounded finite private-directory inventory")?;
        let array = unsafe { &(*entry).d_name };
        let len = array
            .iter()
            .position(|b| *b == 0)
            .ok_or(PrivateLoopError::Rejected("unterminated directory name"))?;
        let name: Vec<u8> = array[..len].iter().map(|b| *b as u8).collect();
        if name == b"." || name == b".." {
            continue;
        }
        need(
            !name.is_empty() && !name.contains(&b'/') && observed.insert(name),
            "unique ordinary private-directory entries",
        )?;
    }
    Ok(observed)
}
fn loop_name(index: u32) -> Result<CString> {
    need(index < 1_048_576, "bounded loop index")?;
    CString::new(format!("loop{index}")).map_err(|_| PrivateLoopError::Rejected("loop name"))
}
fn parse_device(bytes: &[u8]) -> Result<u64> {
    need(
        !bytes.is_empty() && bytes.len() <= 128 && bytes.ends_with(b"\n"),
        "complete bounded loop sysfs number",
    )?;
    let text = std::str::from_utf8(&bytes[..bytes.len() - 1])
        .map_err(|_| PrivateLoopError::Rejected("loop sysfs encoding"))?;
    let (major, minor) = text
        .split_once(':')
        .ok_or(PrivateLoopError::Rejected("loop sysfs separator"))?;
    let parse = |v: &str| -> Result<u32> {
        need(
            !v.is_empty()
                && (v == "0" || !v.starts_with('0'))
                && v.bytes().all(|b| b.is_ascii_digit()),
            "canonical sysfs device integer",
        )?;
        v.parse()
            .map_err(|_| PrivateLoopError::Rejected("sysfs device integer overflow"))
    };
    let (major, minor) = (parse(major)?, parse(minor)?);
    need(
        major == 7 && minor < (1 << 20),
        "actual Linux loop block device major and minor range",
    )?;
    Ok(libc::makedev(major, minor))
}
fn actual_loop_device(index: u32) -> Result<u64> {
    let name = loop_name(index)?;
    // Only the kernel-owned class symlink under original sysfs is followed.
    let sys = File::open("/sys")?;
    let (magic, fsid, _) = filesystem(&sys)?;
    need(magic == SYSFS_MAGIC, "actual original sysfs")?;
    let path = CString::new(format!("block/{}/dev", name.to_str().unwrap())).unwrap();
    #[repr(C)]
    struct OpenHow {
        flags: u64,
        mode: u64,
        resolve: u64,
    }
    let how = OpenHow {
        flags: (libc::O_RDONLY | SAFE) as u64,
        mode: 0,
        resolve: 0x08 | 0x02 | 0x01,
    };
    let f = new_fd(unsafe {
        libc::syscall(
            libc::SYS_openat2,
            sys.as_raw_fd(),
            path.as_ptr(),
            &how,
            std::mem::size_of::<OpenHow>(),
        )
    })?;
    let before = Stamp::of(&f)?;
    let observed = filesystem(&f)?;
    need(
        observed.0 == magic
            && observed.1 == fsid
            && before.uid == 0
            && before.mode & libc::S_IFMT == libc::S_IFREG,
        "kernel sysfs device file on original filesystem",
    )?;
    let mut raw = Vec::new();
    (&f).take(129).read_to_end(&mut raw)?;
    let result = parse_device(&raw)?;
    need(
        Stamp::of(&f)? == before,
        "loop sysfs metadata changed during full read",
    )?;
    Ok(result)
}
fn require_requested_block_size(raw: &[u8]) -> Result<()> {
    need(
        raw == b"4096\n",
        "actual requested loop logical block size is exactly 4096",
    )
}
fn requested_loop_geometry(index: u32, expected_device: u64) -> Result<()> {
    need(
        actual_loop_device(index)? == expected_device,
        "same requested loop device before geometry read",
    )?;
    let name = loop_name(index)?;
    let sys = File::open("/sys")?;
    let (magic, fsid, _) = filesystem(&sys)?;
    need(
        magic == SYSFS_MAGIC,
        "actual original sysfs for requested loop geometry",
    )?;
    let path = CString::new(format!(
        "block/{}/queue/logical_block_size",
        name.to_str().unwrap(),
    ))
    .unwrap();
    #[repr(C)]
    struct OpenHow {
        flags: u64,
        mode: u64,
        resolve: u64,
    }
    let how = OpenHow {
        flags: (libc::O_RDONLY | SAFE) as u64,
        mode: 0,
        resolve: 0x08 | 0x02 | 0x01,
    };
    let file = new_fd(unsafe {
        libc::syscall(
            libc::SYS_openat2,
            sys.as_raw_fd(),
            path.as_ptr(),
            &how,
            std::mem::size_of::<OpenHow>(),
        )
    })?;
    let before = Stamp::of(&file)?;
    let observed = filesystem(&file)?;
    need(
        observed.0 == magic
            && observed.1 == fsid
            && before.uid == 0
            && before.mode & libc::S_IFMT == libc::S_IFREG
            && before.mode & 0o222 == 0,
        "kernel-owned readonly queue attribute on the same sysfs",
    )?;
    let mut raw = Vec::new();
    (&file).take(16).read_to_end(&mut raw)?;
    require_requested_block_size(&raw)?;
    need(
        Stamp::of(&file)? == before && actual_loop_device(index)? == expected_device,
        "requested loop geometry and device identity remain stable",
    )
}
#[repr(C)]
pub(crate) struct LoopStatus {
    device: u64,
    inode: u64,
    rdevice: u64,
    offset: u64,
    size_limit: u64,
    number: u32,
    encrypt_type: u32,
    encrypt_key_size: u32,
    flags: u32,
    file_name: [u8; 64],
    crypt_name: [u8; 64],
    encrypt_key: [u8; 32],
    init: [u64; 2],
}
#[repr(C)]
pub(crate) struct LoopConfig {
    fd: u32,
    block_size: u32,
    info: LoopStatus,
    reserved: [u64; 8],
}
const _: () =
    assert!(std::mem::size_of::<LoopStatus>() == 232 && std::mem::size_of::<LoopConfig>() == 304);
fn source(file: &File, archive: &VerifiedArchive) -> Result<Stamp> {
    archive.matches(file)?;
    apex_inputs::original_builtin(archive.index()).map_err(PrivateLoopError::Rejected)?;
    let stamp = Stamp::of(file)?;
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    if flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    need(
        stamp.mode & libc::S_IFMT == libc::S_IFREG
            && flags & libc::O_ACCMODE == libc::O_RDONLY
            && filesystem(file)?.2 & 15 == 7
            && archive
                .offset()
                .checked_add(archive.payload_bytes())
                .is_some_and(|n| n <= stamp.size),
        "held O_RDONLY original builtin APEX on readonly nosuid nodev executable filesystem",
    )?;
    Ok(stamp)
}
/// A requested-source binding retains the entire original-FD witness, not only
/// its sealed bytes. Cloning this private enum clones the same original owner.
#[derive(Clone)]
enum CompressedCustody {
    Direct(Rc<ImmutableCapex>),
    Requested(Rc<MatchedDecompressedCapex>),
}
impl CompressedCustody {
    fn file(&self) -> io::Result<&File> {
        match self {
            Self::Direct(output) => output.file(),
            Self::Requested(original) => original.sealed_backing()?.file(),
        }
    }
    fn matches(&self, file: &File, archive: &VerifiedArchive) -> io::Result<()> {
        match self {
            Self::Direct(output) => output.matches(file, archive),
            Self::Requested(original) => {
                original.revalidate()?;
                original.sealed_backing()?.matches(file, archive)?;
                original.revalidate()
            }
        }
    }
    fn attest_requested(&self, end: Option<Instant>) -> Result<()> {
        if let Self::Requested(original) = self {
            original.attest_current_bytes(end.ok_or(PrivateLoopError::Rejected(
                "original requested-source deadline absent",
            ))?)?;
        }
        Ok(())
    }
}
fn attachment_deadline(end: Option<Instant>) -> Result<()> {
    need(
        end.is_none_or(|end| Instant::now() < end),
        "original requested-source attachment deadline expired",
    )
}

fn protected_source(
    file: &File,
    archive: &VerifiedArchive,
    compressed: Option<&CompressedCustody>,
) -> Result<Stamp> {
    if let Some(output) = compressed {
        output.matches(file, archive)?;
        let stamp = Stamp::of(file)?;
        need(
            archive
                .offset()
                .checked_add(archive.payload_bytes())
                .is_some_and(|n| n <= stamp.size),
            "sealed CAPEX payload remains inside the exact immutable output",
        )?;
        Ok(stamp)
    } else {
        source(file, archive)
    }
}
fn owned(status: &LoopStatus, stamp: Stamp, index: u32, archive: &VerifiedArchive) -> Result<()> {
    need(
        status.device == stamp.dev
            && status.inode == stamp.ino
            && status.number == index
            && status.offset == archive.offset()
            && status.size_limit == archive.payload_bytes()
            && status.flags == FLAGS
            && status.encrypt_type == 0
            && status.encrypt_key_size == 0
            && status.encrypt_key == [0; 32],
        "exact original readonly autoclear APEX loop binding",
    )
}
struct Alias {
    stamp: Stamp,
    apex_index: usize,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum PoolRetirement {
    Active,
    ControlUnlinked,
    ControlVerified,
    DirectoryUnlinked,
    Retired,
}
struct Inner {
    mount: File,
    root: File,
    root_stamp: Stamp,
    directory: Option<File>,
    directory_stamp: Stamp,
    control: Option<File>,
    control_stamp: Stamp,
    mount_id: u64,
    fsid: [u8; 8],
    mac: MacPrivateLoopWitness,
    aliases: BTreeMap<u32, Alias>,
    retirement: PoolRetirement,
    pending_alias: Option<u32>,
}
impl Inner {
    fn directory(&self) -> Result<&File> {
        self.directory
            .as_ref()
            .ok_or(PrivateLoopError::Rejected("private directory retired"))
    }
    fn control(&self) -> Result<&File> {
        self.control
            .as_ref()
            .ok_or(PrivateLoopError::Rejected("private control retired"))
    }
    fn validate(&self, mac: &MacPreflight, selection: &ProductionSelection) -> Result<()> {
        need(
            self.retirement == PoolRetirement::Active && self.pending_alias.is_none(),
            "private pool has an unfinished owned mutation or retirement",
        )?;
        self.validate_linked_layout(mac, selection, self.directory_stamp, None)
    }
    fn validate_linked_layout(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        directory_stamp: Stamp,
        excluded_alias: Option<u32>,
    ) -> Result<()> {
        self.mac.revalidate(mac, selection)?;
        need(
            Stamp::of(&self.root)? == self.root_stamp
                && Stamp::of(&self.mount)? == self.root_stamp
                && Stamp::of(self.directory()?)? == directory_stamp
                && Stamp::of(self.control()?)? == self.control_stamp,
            "original full private directory and control identities",
        )?;
        let (magic, fsid, flags) = filesystem(&self.root)?;
        need(
            magic == TMPFS_MAGIC
                && fsid == self.fsid
                && flags & 15 == 10
                && mount_id(self.directory()?)? == self.mount_id
                && mount_id(self.control()?)? == self.mount_id,
            "same private tmpfs with NOSUID/NOEXEC and devices enabled",
        )?;
        tmpfs_limits(&self.root)?;
        detached(&self.mount, self.mount_id)?;
        need(
            names(&self.root)? == BTreeSet::from([DIRECTORY.to_bytes().to_vec()]),
            "exact private tmpfs root contents",
        )?;
        need(
            Stamp::of(&open(
                &self.root,
                DIRECTORY,
                libc::O_PATH | libc::O_DIRECTORY,
            )?)? == directory_stamp,
            "original private directory name",
        )?;
        let mut expected = BTreeSet::from([CONTROL.to_bytes().to_vec()]);
        need(
            Stamp::of(&open(self.directory()?, CONTROL, libc::O_PATH)?)? == self.control_stamp,
            "original private control name",
        )?;
        for (&index, alias) in &self.aliases {
            if excluded_alias == Some(index) {
                continue;
            }
            let name = loop_name(index)?;
            expected.insert(name.to_bytes().to_vec());
            let observed = open(self.directory()?, &name, libc::O_PATH)?;
            need(
                Stamp::of(&observed)? == alias.stamp && mount_id(&observed)? == self.mount_id,
                "original private loop name and mount",
            )?;
        }
        need(
            names(self.directory()?)? == expected,
            "complete finite private loop inventory",
        )?;
        for (file, role) in [
            (&self.root, PrivateLoopNode::Root),
            (self.directory()?, PrivateLoopNode::Directory),
            (self.control()?, PrivateLoopNode::Control),
        ] {
            self.mac.node(mac, selection, file, role)?;
        }
        need(
            Stamp::of(&self.root)? == self.root_stamp
                && Stamp::of(self.directory()?)? == directory_stamp,
            "private directories changed during complete observation",
        )?;
        self.mac.revalidate(mac, selection)?;
        Ok(())
    }
    // Retirement keeps every original descriptor until the final checks succeed.
    // A successful unlink is journaled before any subsequent fallible observation.
    fn retirement_layout(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<(Stamp, Stamp, Stamp)> {
        need(
            self.aliases.is_empty() && self.pending_alias.is_none(),
            "aliases still hold retirement custody",
        )?;
        self.mac.revalidate(mac, selection)?;
        let root = Stamp::of(&self.root)?;
        let directory = Stamp::of(self.directory()?)?;
        let control = Stamp::of(self.control()?)?;
        let directory_unlinked = match self.retirement {
            PoolRetirement::ControlUnlinked => {
                need(
                    root == self.root_stamp
                        && directory.same_directory(self.directory_stamp)
                        && directory.links == 2
                        && self.control_stamp.after_unlink(control),
                    "only original control unlink may advance metadata",
                )?;
                false
            }
            PoolRetirement::ControlVerified => {
                need(
                    root == self.root_stamp
                        && directory == self.directory_stamp
                        && control == self.control_stamp
                        && control.links == 0,
                    "same verified control retirement state",
                )?;
                false
            }
            PoolRetirement::DirectoryUnlinked => {
                need(
                    root.same_directory(self.root_stamp)
                        && root.links == 2
                        && self.directory_stamp.after_unlink(directory)
                        && control == self.control_stamp
                        && control.links == 0,
                    "only original private directory unlink may advance metadata",
                )?;
                true
            }
            _ => {
                return Err(PrivateLoopError::Rejected(
                    "not an owned partial retirement",
                ));
            }
        };
        need(
            Stamp::of(&self.mount)? == root,
            "original mount and root remain the same inode",
        )?;
        let (magic, fsid, flags) = filesystem(&self.root)?;
        need(
            magic == TMPFS_MAGIC
                && fsid == self.fsid
                && flags & 15 == 10
                && mount_id(self.directory()?)? == self.mount_id
                && mount_id(self.control()?)? == self.mount_id,
            "retirement retains original bounded private tmpfs",
        )?;
        tmpfs_limits(&self.root)?;
        detached(&self.mount, self.mount_id)?;
        let expected = if directory_unlinked {
            BTreeSet::new()
        } else {
            BTreeSet::from([DIRECTORY.to_bytes().to_vec()])
        };
        need(
            names(&self.root)? == expected,
            "complete root inventory matches the recorded retirement phase",
        )?;
        if !directory_unlinked {
            need(
                names(self.directory()?)?.is_empty(),
                "linked private directory remains empty",
            )?;
            need(
                Stamp::of(&open(
                    &self.root,
                    DIRECTORY,
                    libc::O_PATH | libc::O_DIRECTORY,
                )?)? == directory,
                "original linked private directory during retirement",
            )?;
        }
        for (file, role) in [
            (&self.root, PrivateLoopNode::Root),
            (self.directory()?, PrivateLoopNode::Directory),
            (self.control()?, PrivateLoopNode::Control),
        ] {
            self.mac.node(mac, selection, file, role)?;
        }
        self.mac.revalidate(mac, selection)?;
        need(
            Stamp::of(&self.root)? == root
                && Stamp::of(&self.mount)? == root
                && Stamp::of(self.directory()?)? == directory
                && Stamp::of(self.control()?)? == control,
            "original retirement descriptors unchanged throughout observation",
        )?;
        Ok((root, directory, control))
    }
    fn changed_directory(&mut self) -> Result<()> {
        let current = Stamp::of(self.directory()?)?;
        need(
            current.same_directory(self.directory_stamp)
                && current.links == 2
                && Stamp::of(&self.root)? == self.root_stamp,
            "only the owned child-name mutation may advance directory timestamps",
        )?;
        self.directory_stamp = current;
        Ok(())
    }
}
// Not externally constructible. Issued only immediately after actual
// requested CONFIGURE Ok(true), for the device already in its original slot.
pub(crate) struct RequestedConfigureSuccess {
    _private: (),
}

/// One finite pool; never installed under a host or guest pathname.
pub(crate) struct PrivateLoopOwner {
    inner: Option<Rc<RefCell<Inner>>>,
}
impl PrivateLoopOwner {
    pub(crate) fn create(mac: &MacPreflight, selection: &ProductionSelection) -> Result<Self> {
        let witness = mac.private_loop_creation(selection)?;
        let (mount, root) = fresh_tmpfs()?;
        let initial = node_kind(&root, libc::S_IFDIR, 0o700, None)?;
        need(
            initial.links == 2 && names(&root)?.is_empty(),
            "fresh empty private root",
        )?;
        let (magic, fsid, flags) = filesystem(&root)?;
        need(
            magic == TMPFS_MAGIC && flags & 15 == 10,
            "fresh private tmpfs flags",
        )?;
        tmpfs_limits(&root)?;
        let id = mount_id(&mount)?;
        detached(&mount, id)?;
        witness.node(mac, selection, &root, PrivateLoopNode::Root)?;
        zero(
            unsafe { libc::mkdirat(root.as_raw_fd(), DIRECTORY.as_ptr(), 0o700) } as libc::c_long,
        )?;
        let directory = open(&root, DIRECTORY, libc::O_RDONLY | libc::O_DIRECTORY)?;
        let dir_initial = node_kind(&directory, libc::S_IFDIR, 0o700, None)?;
        let root_stamp = Stamp::of(&root)?;
        need(
            initial.same_directory(root_stamp)
                && root_stamp.links == 3
                && dir_initial.links == 2
                && names(&directory)?.is_empty()
                && mount_id(&directory)? == id,
            "exact owned private directory creation",
        )?;
        witness.node(mac, selection, &directory, PrivateLoopNode::Directory)?;
        witness.revalidate(mac, selection)?;
        zero(unsafe {
            libc::mknodat(
                directory.as_raw_fd(),
                CONTROL.as_ptr(),
                libc::S_IFCHR | 0o600,
                libc::makedev(10, 237),
            )
        } as libc::c_long)?;
        let control = open(&directory, CONTROL, libc::O_RDWR)?;
        let control_stamp =
            node_kind(&control, libc::S_IFCHR, 0o600, Some(libc::makedev(10, 237)))?;
        let directory_stamp = Stamp::of(&directory)?;
        need(
            directory_stamp.same_directory(dir_initial)
                && directory_stamp.links == 2
                && Stamp::of(&root)? == root_stamp,
            "exact owned control creation",
        )?;
        witness.node(mac, selection, &control, PrivateLoopNode::Control)?;
        let inner = Inner {
            mount,
            root,
            root_stamp,
            directory: Some(directory),
            directory_stamp,
            control: Some(control),
            control_stamp,
            mount_id: id,
            fsid,
            mac: witness,
            aliases: BTreeMap::new(),
            retirement: PoolRetirement::Active,
            pending_alias: None,
        };
        inner.validate(mac, selection)?;
        Ok(Self {
            inner: Some(Rc::new(RefCell::new(inner))),
        })
    }
    pub(crate) fn revalidate(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<()> {
        self.inner
            .as_ref()
            .ok_or(PrivateLoopError::Rejected("private owner retired"))?
            .try_borrow()
            .map_err(|_| PrivateLoopError::Rejected("private owner is already in use"))?
            .validate(mac, selection)
    }
    pub(crate) fn attach(
        &mut self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        original: &File,
        archive: VerifiedArchive,
    ) -> Result<PrivateLoopDevice> {
        // This public builtin entry point keeps the original readonly-system
        // checks. It cannot accept an ordinary writable decompression output.
        source(original, &archive)?;
        self.attach_source(mac, selection, original, Rc::new(archive), None, None)
    }

    pub(crate) fn attach_compressed(
        &mut self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        output: Rc<ImmutableCapex>,
    ) -> Result<PrivateLoopDevice> {
        let original = output.file()?.try_clone()?;
        let archive = output.archive()?;
        self.attach_source(
            mac,
            selection,
            &original,
            archive,
            Some(CompressedCustody::Direct(output)),
            None,
        )
    }

    /// Data custody only: the production request adapter must separately hold
    /// the actual original apexd actor, request, namespace epoch and MAC pair.
    /// No mutable /data inode is sent to LOOP_CONFIGURE.
    /// Only the original runtime slot can issue this sink. The full actual
    /// device enters it before CONFIGURE, and stays there across every error.
    pub(crate) fn attach_requested_retained(
        &mut self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        matched: Rc<MatchedDecompressedCapex>,
        end: Instant,
        retained: &mut crate::production_runtime_assets::RequestedDeviceCustody<'_>,
    ) -> Result<()> {
        retained.require_matched(mac, selection, &matched)?;
        attachment_deadline(Some(end))?;
        let sealed = matched.sealed_backing()?;
        let original = sealed.file()?.try_clone()?;
        let archive = sealed.archive()?;
        self.attach_requested_source_retained(
            mac, selection, &original, archive, matched, end, retained,
        )
    }

    fn attach_requested_source_retained(
        &mut self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        original: &File,
        archive: Rc<VerifiedArchive>,
        matched: Rc<MatchedDecompressedCapex>,
        end: Instant,
        retained: &mut crate::production_runtime_assets::RequestedDeviceCustody<'_>,
    ) -> Result<()> {
        let compressed = Some(CompressedCustody::Requested(matched));
        let end = Some(end);
        attachment_deadline(end)?;
        if let Some(output) = &compressed {
            output.attest_requested(end)?;
        }
        let stamp = protected_source(original, &archive, compressed.as_ref())?;
        let inner = self
            .inner
            .as_ref()
            .ok_or(PrivateLoopError::Rejected("private owner retired"))?;
        for _ in 0..64 {
            attachment_deadline(end)?;
            retained.begin_attempt()?;
            let vacant = retained.vacant()?;
            let mut state = inner
                .try_borrow_mut()
                .map_err(|_| PrivateLoopError::Rejected("private owner is already in use"))?;
            state.validate(mac, selection)?;
            need(
                state.aliases.len() < 38
                    && !state
                        .aliases
                        .values()
                        .any(|v| v.apex_index == archive.index()),
                "one private loop for each of the 38 fixed original APEX sources",
            )?;
            let index = state.mac.get_free(mac, selection, state.control()?)?;
            need(
                !state.aliases.contains_key(&index),
                "kernel returned an already-owned loop index",
            )?;
            let rdev = actual_loop_device(index)?;
            let name = loop_name(index)?;
            state.validate(mac, selection)?;
            zero(unsafe {
                libc::mknodat(
                    state.directory()?.as_raw_fd(),
                    name.as_ptr(),
                    libc::S_IFBLK | 0o600,
                    rdev,
                )
            } as libc::c_long)?;
            let file = open(state.directory()?, &name, libc::O_RDWR)?;
            let node = node_kind(&file, libc::S_IFBLK, 0o600, Some(rdev))?;
            state.changed_directory()?;
            need(
                mount_id(&file)? == state.mount_id,
                "new loop inode on original private mount",
            )?;
            state
                .mac
                .node(mac, selection, &file, PrivateLoopNode::Block)?;
            state.aliases.insert(
                index,
                Alias {
                    stamp: node,
                    apex_index: archive.index(),
                },
            );
            // Slot owns the full device before any later check or ioctl.
            let mut device = vacant.insert(PrivateLoopDevice {
                inner: Rc::clone(inner),
                file: Some(file),
                index,
                node,
                source: stamp,
                archive: Rc::clone(&archive),
                compressed: compressed.clone(),
                state: BindingState::Unconfigured,
            });
            state.validate(mac, selection)?;
            drop(state);
            if let Some(output) = &compressed {
                output.attest_requested(end)?;
            }
            need(
                protected_source(original, &archive, compressed.as_ref())? == stamp,
                "same original source before configure",
            )?;
            let mut config: LoopConfig = unsafe { std::mem::zeroed() };
            config.fd = u32::try_from(original.as_raw_fd())
                .map_err(|_| PrivateLoopError::Rejected("original source descriptor"))?;
            // Exact requested CP3A geometry; old builtin/direct source body is unchanged.
            config.block_size = 4096;
            config.info.offset = archive.offset();
            config.info.size_limit = archive.payload_bytes();
            config.info.flags = FLAGS;
            attachment_deadline(end)?;
            device.state = BindingState::Uncertain;
            let configured = {
                let state = inner.borrow();
                state.mac.configure(mac, selection, device.held()?, &config)
            };
            match configured {
                Ok(true) => {
                    device.state = BindingState::Owned;
                    device.record_owned_configuration(RequestedConfigureSuccess { _private: () });
                    attachment_deadline(end)?;
                    if let Some(output) = &compressed {
                        output.attest_requested(end)?;
                    }
                    need(
                        protected_source(original, &archive, compressed.as_ref())? == stamp,
                        "original source changed during configure",
                    )?;
                    device.revalidate(mac, selection)?;
                    attachment_deadline(end)?;
                    return Ok(());
                }
                Ok(false) => {
                    // Only actual CONFIGURE EBUSY plus successful epoch checks reaches here.
                    // The foreign binding is never adopted or cleared.
                    device.state = BindingState::Unconfigured;
                    device.unlink_unconfigured(mac, selection)?;
                    drop(device);
                    retained.discard_retired_after_busy()?;
                }
                Err(error) => return Err(error.into()),
            }
        }
        Err(PrivateLoopError::Busy)
    }

    fn attach_source(
        &mut self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        original: &File,
        archive: Rc<VerifiedArchive>,
        compressed: Option<CompressedCustody>,
        end: Option<Instant>,
    ) -> Result<PrivateLoopDevice> {
        attachment_deadline(end)?;
        if let Some(output) = &compressed {
            output.attest_requested(end)?;
        }
        let stamp = protected_source(original, &archive, compressed.as_ref())?;
        let inner = self
            .inner
            .as_ref()
            .ok_or(PrivateLoopError::Rejected("private owner retired"))?;
        for _ in 0..64 {
            attachment_deadline(end)?;
            let mut state = inner
                .try_borrow_mut()
                .map_err(|_| PrivateLoopError::Rejected("private owner is already in use"))?;
            state.validate(mac, selection)?;
            need(
                state.aliases.len() < 38
                    && !state
                        .aliases
                        .values()
                        .any(|v| v.apex_index == archive.index()),
                "one private loop for each of the 38 fixed original APEX sources",
            )?;
            let index = state.mac.get_free(mac, selection, state.control()?)?;
            need(
                !state.aliases.contains_key(&index),
                "kernel returned an already-owned loop index",
            )?;
            let rdev = actual_loop_device(index)?;
            let name = loop_name(index)?;
            state.validate(mac, selection)?;
            zero(unsafe {
                libc::mknodat(
                    state.directory()?.as_raw_fd(),
                    name.as_ptr(),
                    libc::S_IFBLK | 0o600,
                    rdev,
                )
            } as libc::c_long)?;
            let file = open(state.directory()?, &name, libc::O_RDWR)?;
            let node = node_kind(&file, libc::S_IFBLK, 0o600, Some(rdev))?;
            state.changed_directory()?;
            need(
                mount_id(&file)? == state.mount_id,
                "new loop inode on original private mount",
            )?;
            state
                .mac
                .node(mac, selection, &file, PrivateLoopNode::Block)?;
            state.aliases.insert(
                index,
                Alias {
                    stamp: node,
                    apex_index: archive.index(),
                },
            );
            state.validate(mac, selection)?;
            drop(state);
            let mut device = PrivateLoopDevice {
                inner: Rc::clone(inner),
                file: Some(file),
                index,
                node,
                source: stamp,
                archive: Rc::clone(&archive),
                compressed: compressed.clone(),
                state: BindingState::Unconfigured,
            };
            if let Some(output) = &compressed {
                output.attest_requested(end)?;
            }
            need(
                protected_source(original, &archive, compressed.as_ref())? == stamp,
                "same original source before configure",
            )?;
            let mut config: LoopConfig = unsafe { std::mem::zeroed() };
            config.fd = u32::try_from(original.as_raw_fd())
                .map_err(|_| PrivateLoopError::Rejected("original source descriptor"))?;
            // The real CP3A apexd config uses 4096. Only this new requested
            // branch adopts that geometry; old builtin/direct paths stay zero.
            if matches!(&compressed, Some(CompressedCustody::Requested(_))) {
                config.block_size = 4096;
            }
            config.info.offset = archive.offset();
            config.info.size_limit = archive.payload_bytes();
            config.info.flags = FLAGS;
            attachment_deadline(end)?;
            device.state = BindingState::Uncertain;
            let configured = {
                let state = inner.borrow();
                state.mac.configure(mac, selection, device.held()?, &config)
            };
            match configured {
                Ok(true) => {
                    device.state = BindingState::Owned;
                    attachment_deadline(end)?;
                    if let Some(output) = &compressed {
                        output.attest_requested(end)?;
                    }
                    need(
                        protected_source(original, &archive, compressed.as_ref())? == stamp,
                        "original source changed during configure",
                    )?;
                    device.revalidate(mac, selection)?;
                    attachment_deadline(end)?;
                    return Ok(device);
                }
                Ok(false) => {
                    // Only actual CONFIGURE EBUSY plus successful epoch checks reaches here.
                    // The foreign binding is never adopted or cleared.
                    device.state = BindingState::Unconfigured;
                    device.unlink_unconfigured(mac, selection)?;
                }
                Err(error) => return Err(error.into()),
            }
        }
        Err(PrivateLoopError::Busy)
    }
    /// Called after all corresponding guest/helper/mount consumers retire.
    pub(crate) fn retire(
        &mut self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<()> {
        let shared = self
            .inner
            .as_ref()
            .ok_or(PrivateLoopError::Rejected("private owner retired"))?;
        need(
            Rc::strong_count(shared) == 1,
            "private loop handles still hold mount custody",
        )?;
        let mut state = shared
            .try_borrow_mut()
            .map_err(|_| PrivateLoopError::Rejected("private owner is already in use"))?;
        need(
            state.aliases.is_empty() && state.pending_alias.is_none(),
            "private loop aliases still present",
        )?;
        loop {
            match state.retirement {
                PoolRetirement::Active => {
                    state.validate(mac, selection)?;
                    zero(unsafe {
                        libc::unlinkat(state.directory()?.as_raw_fd(), CONTROL.as_ptr(), 0)
                    } as libc::c_long)?;
                    state.retirement = PoolRetirement::ControlUnlinked;
                }
                PoolRetirement::ControlUnlinked => {
                    let (_, directory, control) = state.retirement_layout(mac, selection)?;
                    state.directory_stamp = directory;
                    state.control_stamp = control;
                    state.retirement = PoolRetirement::ControlVerified;
                }
                PoolRetirement::ControlVerified => {
                    state.retirement_layout(mac, selection)?;
                    zero(unsafe {
                        libc::unlinkat(
                            state.root.as_raw_fd(),
                            DIRECTORY.as_ptr(),
                            libc::AT_REMOVEDIR,
                        )
                    } as libc::c_long)?;
                    state.retirement = PoolRetirement::DirectoryUnlinked;
                }
                PoolRetirement::DirectoryUnlinked => {
                    state.retirement_layout(mac, selection)?;
                    state.retirement = PoolRetirement::Retired;
                    drop(state.control.take());
                    drop(state.directory.take());
                    break;
                }
                PoolRetirement::Retired => {
                    return Err(PrivateLoopError::Rejected("private owner already retired"));
                }
            }
        }
        drop(state);
        drop(self.inner.take());
        Ok(())
    }
}
impl std::fmt::Debug for PrivateLoopOwner {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PrivateLoopOwner")
            .field("retired", &self.inner.is_none())
            .finish_non_exhaustive()
    }
}
impl Drop for PrivateLoopOwner {
    fn drop(&mut self) {
        if let Some(inner) = self.inner.take() {
            std::mem::forget(inner);
        }
    }
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum BindingState {
    Unconfigured,
    Uncertain,
    Owned,
    AliasUnlinked,
    Retired,
}
/// The alias and original source retain the same private mount owner.
pub(crate) struct PrivateLoopDevice {
    inner: Rc<RefCell<Inner>>,
    file: Option<File>,
    index: u32,
    node: Stamp,
    source: Stamp,
    archive: Rc<VerifiedArchive>,
    compressed: Option<CompressedCustody>,
    state: BindingState,
}
impl PrivateLoopDevice {
    fn revalidate_source(&self) -> Result<()> {
        self.archive.revalidate()?;
        if self.state == BindingState::Owned
            && matches!(&self.compressed, Some(CompressedCustody::Requested(_)))
        {
            // Fixed readonly sysfs observation avoids adding a generic block
            // ioctl or accepting a later geometry mutation by another owner.
            requested_loop_geometry(self.index, self.node.rdev)?;
        }
        if let Some(output) = &self.compressed {
            output.matches(output.file()?, &self.archive)?;
            need(
                Stamp::of(output.file()?)? == self.source,
                "same kernel-sealed CAPEX output and complete requested-source custody throughout loop ownership",
            )?;
        }
        Ok(())
    }

    fn held(&self) -> Result<&File> {
        self.file.as_ref().ok_or(PrivateLoopError::Rejected(
            "private loop descriptor retired",
        ))
    }
    fn inode(&self, mac: &MacPreflight, selection: &ProductionSelection) -> Result<()> {
        let state = self
            .inner
            .try_borrow()
            .map_err(|_| PrivateLoopError::Rejected("private owner is already in use"))?;
        state.validate(mac, selection)?;
        let alias = state
            .aliases
            .get(&self.index)
            .ok_or(PrivateLoopError::Rejected(
                "private loop absent from original owner",
            ))?;
        need(
            alias.stamp == self.node
                && alias.apex_index == self.archive.index()
                && Stamp::of(self.held()?)? == self.node,
            "same original held loop alias and source role",
        )?;
        state
            .mac
            .node(mac, selection, self.held()?, PrivateLoopNode::Block)?;
        Ok(())
    }
    pub(crate) fn revalidate(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<()> {
        need(
            self.state == BindingState::Owned,
            "only exact owned loop binding can be used",
        )?;
        self.revalidate_source()?;
        self.inode(mac, selection)?;
        let state = self.inner.borrow();
        let status =
            state
                .mac
                .status(mac, selection, self.held()?)?
                .ok_or(PrivateLoopError::Rejected(
                    "owned loop unexpectedly unbound",
                ))?;
        owned(&status, self.source, self.index, &self.archive)?;
        drop(state);
        self.revalidate_source()?;
        self.inode(mac, selection)
    }
    pub(crate) fn file(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<&File> {
        self.revalidate(mac, selection)?;
        self.held()
    }
    pub(crate) fn device_number(&self) -> u64 {
        self.node.rdev
    }
    pub(crate) fn apex_index(&self) -> usize {
        self.archive.index()
    }
    fn finish_unlink(&mut self, mac: &MacPreflight, selection: &ProductionSelection) -> Result<()> {
        need(
            self.state == BindingState::AliasUnlinked,
            "only recorded successful alias unlink may resume",
        )?;
        let mut state = self
            .inner
            .try_borrow_mut()
            .map_err(|_| PrivateLoopError::Rejected("private owner is already in use"))?;
        need(
            state.retirement == PoolRetirement::Active && state.pending_alias == Some(self.index),
            "same original pending alias retirement",
        )?;
        let alias = state
            .aliases
            .get(&self.index)
            .ok_or(PrivateLoopError::Rejected("pending alias identity lost"))?;
        need(
            alias.stamp == self.node && alias.apex_index == self.archive.index(),
            "same original pending alias and source role",
        )?;
        let after = Stamp::of(self.held()?)?;
        need(
            self.node.after_unlink(after) && mount_id(self.held()?)? == state.mount_id,
            "same held alias after its recorded unlink",
        )?;
        state
            .mac
            .node(mac, selection, self.held()?, PrivateLoopNode::Block)?;
        let directory = Stamp::of(state.directory()?)?;
        need(
            directory.same_directory(state.directory_stamp) && directory.links == 2,
            "only owned alias unlink may advance directory metadata",
        )?;
        state.validate_linked_layout(mac, selection, directory, Some(self.index))?;
        state
            .mac
            .node(mac, selection, self.held()?, PrivateLoopNode::Block)?;
        need(
            Stamp::of(self.held()?)? == after && Stamp::of(state.directory()?)? == directory,
            "unlinked alias and directory unchanged throughout retirement",
        )?;
        state.mac.revalidate(mac, selection)?;
        self.revalidate_source()?;
        state.directory_stamp = directory;
        state.aliases.remove(&self.index);
        state.pending_alias = None;
        self.state = BindingState::Retired;
        drop(self.file.take());
        Ok(())
    }
    fn unlink_unconfigured(
        &mut self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<()> {
        if self.state == BindingState::Unconfigured {
            self.inode(mac, selection)?;
            let name = loop_name(self.index)?;
            let mut state = self
                .inner
                .try_borrow_mut()
                .map_err(|_| PrivateLoopError::Rejected("private owner is already in use"))?;
            let leaf = open(state.directory()?, &name, libc::O_PATH)?;
            need(
                Stamp::of(&leaf)? == self.node && Stamp::of(self.held()?)? == self.node,
                "original private alias before removal",
            )?;
            zero(
                unsafe { libc::unlinkat(state.directory()?.as_raw_fd(), name.as_ptr(), 0) }
                    as libc::c_long,
            )?;
            state.pending_alias = Some(self.index);
            self.state = BindingState::AliasUnlinked;
        } else {
            need(
                self.state == BindingState::AliasUnlinked,
                "never unlink a possibly bound loop",
            )?;
        }
        self.finish_unlink(mac, selection)
    }
    pub(crate) fn retire(
        &mut self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<()> {
        need(
            matches!(
                self.state,
                BindingState::Owned | BindingState::Unconfigured | BindingState::AliasUnlinked
            ),
            "only owned binding or its recorded retirement may retire",
        )?;
        self.revalidate_source()?;
        if self.state == BindingState::Owned {
            self.inode(mac, selection)?;
            {
                let state = self.inner.borrow();
                if let Some(status) = state.mac.status(mac, selection, self.held()?)? {
                    owned(&status, self.source, self.index, &self.archive)?;
                    state.mac.clear(mac, selection, self.held()?)?;
                }
                if state.mac.status(mac, selection, self.held()?)?.is_some() {
                    return Err(PrivateLoopError::Busy);
                }
            }
            self.state = BindingState::Unconfigured;
        }
        self.revalidate_source()?;
        self.unlink_unconfigured(mac, selection)
    }
}
impl std::fmt::Debug for PrivateLoopDevice {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PrivateLoopDevice")
            .field("index", &self.index)
            .field("state", &self.state)
            .field("rdev", &self.node.rdev)
            .finish_non_exhaustive()
    }
}

impl PrivateLoopDevice {
    /// Only an actual completed original retirement can release a retained
    /// requested slot. No status bit or caller rdev can create this proof.
    pub(crate) fn require_retired_custody(&self) -> Result<()> {
        need(
            self.state == BindingState::Retired && self.file.is_none(),
            "requested device has not completed actual original retirement",
        )?;
        let inner = self
            .inner
            .try_borrow()
            .map_err(|_| PrivateLoopError::Rejected("private owner is already in use"))?;
        need(
            !inner.aliases.contains_key(&self.index) && inner.pending_alias != Some(self.index),
            "retired requested alias remains in the original private owner",
        )
    }
}

impl Drop for PrivateLoopDevice {
    fn drop(&mut self) {
        if self.state != BindingState::Retired {
            if let Some(file) = self.file.take() {
                std::mem::forget(file);
            }
            std::mem::forget(Rc::clone(&self.inner));
            std::mem::forget(Rc::clone(&self.archive));
            if let Some(output) = &self.compressed {
                // Requested includes the original source FD/flags/F9 witness.
                std::mem::forget(output.clone());
            }
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn requested_geometry_rejects_kernel_attribute_truncation_and_aliases() {
        require_requested_block_size(b"4096\n").unwrap();
        for bad in [
            b"".as_slice(),
            b"4096",
            b"512\n",
            b"04096\n",
            b"8192\n",
            b"4096\nextra",
            b"4096\0",
            b"4096\r\n",
            b"-4096\n",
        ] {
            assert!(require_requested_block_size(bad).is_err(), "{bad:?}");
        }
    }
    #[test]
    fn inventory_observes_foreign_member_and_symlink() {
        let dir = tempfile::tempdir().unwrap();
        let held = File::open(dir.path()).unwrap();
        assert!(names(&held).unwrap().is_empty());
        std::fs::write(dir.path().join("loop-control"), b"wrong inode").unwrap();
        std::os::unix::fs::symlink("loop-control", dir.path().join("loop0")).unwrap();
        assert_eq!(
            names(&held).unwrap(),
            BTreeSet::from([b"loop-control".to_vec(), b"loop0".to_vec()])
        );
        assert!(open(&held, c"loop0", libc::O_RDWR).is_err());
        assert!(
            node_kind(
                &open(&held, CONTROL, libc::O_RDONLY).unwrap(),
                libc::S_IFCHR,
                0o600,
                Some(libc::makedev(10, 237))
            )
            .is_err()
        );
    }
    #[test]
    fn same_bytes_on_replacement_inode_are_rejected() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("original");
        std::fs::write(&p, b"same").unwrap();
        let held = File::open(&p).unwrap();
        let initial = Stamp::of(&held).unwrap();
        std::fs::rename(&p, dir.path().join("old")).unwrap();
        std::fs::write(&p, b"same").unwrap();
        assert_ne!(Stamp::of(&File::open(&p).unwrap()).unwrap(), initial);
        assert_eq!(Stamp::of(&held).unwrap().ino, initial.ino);
    }
    #[test]
    fn device_numbers_require_canonical_sysfs_form() {
        assert_eq!(
            parse_device(b"7:1048575\n").unwrap(),
            libc::makedev(7, 1048575)
        );
        for bad in [
            b"7:0".as_slice(),
            b"7:00\n",
            b"8:0\n",
            b"7:-1\n",
            b"7:1048576\n",
            b"7:1\nextra\n",
            b"7: 1\n",
            b"07:1\n",
        ] {
            assert!(parse_device(bad).is_err(), "{bad:?}");
        }
        assert!(loop_name(1_048_576).is_err());
    }
    #[test]
    fn inventory_rejects_attachment_truncation_and_duplicate_id() {
        let row = b"41 1 0:42 / / rw - tmpfs tmpfs rw\n";
        assert!(mount_inventory_absent(row, 42).is_ok());
        assert!(mount_inventory_absent(row, 41).is_err());
        assert!(mount_inventory_absent(&row[..row.len() - 1], 42).is_err());
        assert!(mount_inventory_absent(&[row.as_slice(), row.as_slice()].concat(), 42).is_err());
        assert!(mount_inventory_absent(b"41 1\n", 42).is_err());
    }
    #[test]
    fn unlink_retains_the_original_descriptor_and_rejects_later_mutation() {
        use std::io::Write;
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("owned");
        let mut held = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .open(&path)
            .unwrap();
        held.write_all(b"original").unwrap();
        let before = Stamp::of(&held).unwrap();
        assert!(!before.after_unlink(before));
        std::fs::remove_file(&path).unwrap();
        let after = Stamp::of(&held).unwrap();
        assert!(before.after_unlink(after));
        assert!(!path.exists());
        std::fs::write(&path, b"original").unwrap();
        assert!(!before.after_unlink(Stamp::of(&File::open(&path).unwrap()).unwrap()));
        held.write_all(b"changed contents").unwrap();
        assert!(!before.after_unlink(Stamp::of(&held).unwrap()));
    }
    #[test]
    fn directory_retirement_keeps_only_the_original_unlinked_inode() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("owned");
        std::fs::create_dir(&path).unwrap();
        let held = File::open(&path).unwrap();
        let before = Stamp::of(&held).unwrap();
        assert_eq!(before.links, 2);
        assert!(names(&held).unwrap().is_empty());
        std::fs::remove_dir(&path).unwrap();
        let after = Stamp::of(&held).unwrap();
        assert!(before.same_directory(after));
        assert_eq!(after.links, 0);
        // Filesystem-specific size changes are not a portable ordinary-file fixture.
        // The production after_unlink size/mtime check is for the fixed private tmpfs.
        std::fs::create_dir(&path).unwrap();
        let replacement = File::open(&path).unwrap();
        assert!(!before.after_unlink(Stamp::of(&replacement).unwrap()));
    }
}
