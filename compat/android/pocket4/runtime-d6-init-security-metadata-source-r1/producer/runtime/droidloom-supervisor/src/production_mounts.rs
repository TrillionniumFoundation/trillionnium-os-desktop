//! Descriptor-owned, detached mounts for verified Android base images.
//!
//! This module never selects an arbitrary host path, attaches a mount in the
//! host namespace, changes on-disk ownership, or opens original data bodies.
//! Image authority comes from a root-owned manifest whose complete digest is
//! the cohort bound by the live namespace owner's non-serializable lease.
//! A descriptor transfer keeps an additional reference to the same reservation
//! lock until the actual owned PID 1 has been reaped and mount cleanup succeeds.
use std::ffi::{CStr, CString};
use std::fs::{File, Metadata};
use std::io::{self, Read};
use std::os::fd::{AsFd, AsRawFd, BorrowedFd, FromRawFd};
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};
use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::IdRange;
use crate::image_layout::AndroidImageLayout;
use crate::production_identity::IdentityError;
use crate::production_namespace::{NamespaceError, OwnedNamespaceWitness, RetiredTreeWitness};

#[path = "production_runtime_assets.rs"]
pub(crate) mod runtime_assets;

const MANIFEST_ROOT: &str = "/etc/droidloom/cohorts";
const IMAGE_ROOT: &str = "/var/lib/droidloom/cohorts";
const MAX_MANIFEST: u64 = 16 * 1024;
const MAX_IMAGE: u64 = 8 * 1024 * 1024 * 1024;
const O_SAFE: i32 = libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK;
const LOOP_CTL_GET_FREE: libc::c_ulong = 0x4c82;
const LOOP_CONFIGURE: libc::c_ulong = 0x4c0a;
const LOOP_GET_STATUS64: libc::c_ulong = 0x4c05;
const LOOP_CLR_FD: libc::c_ulong = 0x4c01;
const LO_FLAGS_READ_ONLY: u32 = 1;
const LO_FLAGS_AUTOCLEAR: u32 = 4;
const FSOPEN_CLOEXEC: u32 = 1;
const FSCONFIG_SET_FLAG: u32 = 0;
const FSCONFIG_SET_STRING: u32 = 1;
const FSCONFIG_CMD_CREATE: u32 = 6;
const FSMOUNT_CLOEXEC: u32 = 1;
const MOUNT_ATTR_RDONLY: u64 = 1;
const MOUNT_ATTR_NOSUID: u64 = 2;
const MOUNT_ATTR_NODEV: u64 = 4;
const MOUNT_ATTR_IDMAP: u64 = 0x0010_0000;
const READONLY_FLAGS: u64 = MOUNT_ATTR_RDONLY | MOUNT_ATTR_NOSUID | MOUNT_ATTR_NODEV;
const AT_EMPTY_PATH: u32 = 0x1000;
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const NSFS_MAGIC: libc::c_long = 0x6e73_6673;

#[derive(Debug, Error)]
pub(crate) enum MountError {
    #[error("production mount input rejected: {0}")]
    Rejected(&'static str),
    #[error("production mount input changed")]
    Changed,
    #[error("owned loop still has kernel references; reservation retained")]
    Busy,
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
    #[error(transparent)]
    Namespace(#[from] NamespaceError),
    #[error(transparent)]
    Identity(#[from] IdentityError),
}
type Result<T> = std::result::Result<T, MountError>;

fn require(ok: bool, reason: &'static str) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(MountError::Rejected(reason))
    }
}
fn syscall_fd(value: libc::c_long) -> Result<File> {
    if value < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let fd = i32::try_from(value).map_err(|_| MountError::Rejected("descriptor overflow"))?;
    // SAFETY: a successful syscall just returned this new owned descriptor.
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn zero_rc(value: i32) -> Result<()> {
    if value == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error().into())
    }
}
fn text_name(value: &str) -> Result<CString> {
    CString::new(value).map_err(|_| MountError::Rejected("embedded NUL"))
}
fn is_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct FileIdentity {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    mtime: (i64, i64),
    ctime: (i64, i64),
}
impl FileIdentity {
    fn of(m: &Metadata) -> Self {
        Self {
            dev: m.dev(),
            ino: m.ino(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            links: m.nlink(),
            bytes: m.len(),
            mtime: (m.mtime(), m.mtime_nsec()),
            ctime: (m.ctime(), m.ctime_nsec()),
        }
    }
    fn same_directory(self, other: Self) -> bool {
        (self.dev, self.ino, self.mode, self.uid, self.gid)
            == (other.dev, other.ino, other.mode, other.uid, other.gid)
    }
}
fn trusted_regular(m: &Metadata, owner: u32, maximum: u64) -> Result<()> {
    require(
        m.is_file()
            && m.uid() == owner
            && m.gid() == owner
            && m.nlink() == 1
            && m.mode() & 0o022 == 0
            && m.len() <= maximum,
        "bounded trusted singleton regular file",
    )
}
fn trusted_directory(path: &Path, owner: u32) -> Result<File> {
    require(path.is_absolute(), "absolute fixed directory required")?;
    // SAFETY: constant terminated root path and ordinary open flags.
    let mut fd =
        syscall_fd(
            unsafe { libc::open(c"/".as_ptr(), libc::O_RDONLY | libc::O_DIRECTORY | O_SAFE) }
                as libc::c_long,
        )?;
    for component in path.components() {
        match component {
            Component::RootDir => (),
            Component::Normal(name) => {
                let name = CString::new(name.as_encoded_bytes())
                    .map_err(|_| MountError::Rejected("directory NUL"))?;
                // SAFETY: held directory and a single terminated component.
                fd = syscall_fd(unsafe {
                    libc::openat(
                        fd.as_raw_fd(),
                        name.as_ptr(),
                        libc::O_RDONLY | libc::O_DIRECTORY | O_SAFE,
                    )
                } as libc::c_long)?;
            }
            _ => return Err(MountError::Rejected("directory traversal or alias")),
        }
        let m = fd.metadata()?;
        // Ancestors may be root-owned while a normal unprivileged unit test
        // owns its final fixture; both must exclude group/other writes.
        require(
            m.is_dir() && (m.uid() == 0 || m.uid() == owner) && m.mode() & 0o022 == 0,
            "trusted directory component",
        )?;
    }
    let m = fd.metadata()?;
    require(
        m.uid() == owner && m.gid() == owner,
        "exact final directory owner",
    )?;
    Ok(fd)
}
fn open_leaf(parent: &File, name: &CStr, flags: i32) -> Result<File> {
    // SAFETY: a held directory and a fixed, terminated single-component name.
    syscall_fd(
        unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), flags | O_SAFE) } as libc::c_long,
    )
}

#[derive(Debug)]
struct SealedFile {
    parent: File,
    parent_path: PathBuf,
    parent_identity: FileIdentity,
    name: CString,
    file: File,
    identity: FileIdentity,
    owner: u32,
}
impl SealedFile {
    fn open_guarded(
        parent_path: &Path,
        name: &str,
        owner: u32,
        maximum: u64,
        admit_metadata: impl Fn(&File) -> Result<()>,
    ) -> Result<Self> {
        require(
            !name.is_empty() && name != "." && name != ".." && !name.contains('/'),
            "single image filename",
        )?;
        let parent = trusted_directory(parent_path, owner)?;
        let parent_identity = FileIdentity::of(&parent.metadata()?);
        let name = text_name(name)?;
        // O_PATH performs the protected-inode exclusion before a public image
        // is even opened for reading. Special files never reach a body open.
        let probe = open_leaf(&parent, &name, libc::O_PATH)?;
        let meta = probe.metadata()?;
        trusted_regular(&meta, owner, maximum)?;
        admit_metadata(&probe)?;
        let file = open_leaf(&parent, &name, libc::O_RDONLY)?;
        require(
            FileIdentity::of(&file.metadata()?) == FileIdentity::of(&meta),
            "image replaced after metadata admission",
        )?;
        admit_metadata(&file)?;
        let result = Self {
            parent,
            parent_path: parent_path.into(),
            parent_identity,
            name,
            file,
            identity: FileIdentity::of(&meta),
            owner,
        };
        result.revalidate()?;
        Ok(result)
    }
    fn revalidate(&self) -> Result<()> {
        let parent = trusted_directory(&self.parent_path, self.owner)?;
        require(
            self.parent_identity
                .same_directory(FileIdentity::of(&parent.metadata()?))
                && self
                    .parent_identity
                    .same_directory(FileIdentity::of(&self.parent.metadata()?)),
            "selected image directory replaced",
        )?;
        let again = open_leaf(&parent, &self.name, libc::O_PATH)?;
        if self.identity != FileIdentity::of(&self.file.metadata()?)
            || self.identity != FileIdentity::of(&again.metadata()?)
        {
            return Err(MountError::Changed);
        }
        Ok(())
    }
    fn bounded_bytes(&self, limit: u64) -> Result<Vec<u8>> {
        require(self.identity.bytes <= limit, "bounded public manifest")?;
        let mut raw = vec![
            0;
            usize::try_from(self.identity.bytes)
                .map_err(|_| MountError::Rejected("size overflow"))?
        ];
        self.file.read_exact_at(&mut raw, 0)?;
        self.revalidate()?;
        Ok(raw)
    }
    fn verify_digest(&self, expected_bytes: u64, expected_sha: &str) -> Result<()> {
        require(
            self.identity.bytes == expected_bytes && is_digest(expected_sha),
            "exact image size and digest shape",
        )?;
        self.revalidate()?;
        let mut sha = Sha256::new();
        let mut offset = 0;
        let mut block = vec![0u8; 1024 * 1024];
        while offset < expected_bytes {
            let amount = usize::try_from((expected_bytes - offset).min(block.len() as u64))
                .map_err(|_| MountError::Rejected("image chunk overflow"))?;
            self.file.read_exact_at(&mut block[..amount], offset)?;
            sha.update(&block[..amount]);
            offset += amount as u64;
        }
        self.revalidate()?;
        require(
            format!("{:x}", sha.finalize()) == expected_sha,
            "complete image digest mismatch",
        )
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ImageDeclaration {
    file: String,
    bytes: u64,
    sha256: String,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CohortDeclaration {
    schema: u32,
    scope: String,
    layout: AndroidImageLayout,
    system: ImageDeclaration,
    vendor: ImageDeclaration,
}
impl CohortDeclaration {
    fn validate(&self) -> Result<()> {
        require(
            self.schema == 1
                && self.scope == "android_base_images_v1"
                && self.layout == AndroidImageLayout::GsiSystemAsRoot,
            "explicit supported Android base-image schema",
        )?;
        for (role, row) in [("system.img", &self.system), ("vendor.img", &self.vendor)] {
            require(
                row.file == role
                    && is_digest(&row.sha256)
                    && (4096..=MAX_IMAGE).contains(&row.bytes)
                    && row.bytes % 512 == 0,
                "fixed raw image role, aligned bounded size and complete digest",
            )?;
        }
        Ok(())
    }
}
#[derive(Debug, Clone, Copy, Eq, PartialEq)]
enum Filesystem {
    Ext4,
    Erofs,
}
impl Filesystem {
    fn detect(file: &File) -> Result<Self> {
        let mut erofs = [0u8; 4];
        file.read_exact_at(&mut erofs, 1024)?;
        if erofs == [0xe2, 0xe1, 0xf5, 0xe0] {
            return Ok(Self::Erofs);
        }
        let mut ext4 = [0u8; 2];
        file.read_exact_at(&mut ext4, 1080)?;
        require(
            ext4 == [0x53, 0xef],
            "only original raw ext4 or EROFS images",
        )?;
        Ok(Self::Ext4)
    }
    fn name(self) -> &'static CStr {
        match self {
            Self::Ext4 => c"ext4",
            Self::Erofs => c"erofs",
        }
    }
    fn magic(self) -> libc::c_long {
        match self {
            Self::Ext4 => 0xef53,
            Self::Erofs => 0xe0f5_e1e2u32 as libc::c_long,
        }
    }
}

/// Private construction binds full manifest/image bytes to the same live lease.
#[derive(Debug)]
pub(crate) struct VerifiedCohort {
    manifest: SealedFile,
    system: SealedFile,
    vendor: SealedFile,
    system_fs: Filesystem,
    vendor_fs: Filesystem,
    cohort: String,
    host_uid: u32,
}
impl VerifiedCohort {
    pub(crate) fn load(witness: &OwnedNamespaceWitness<'_>) -> Result<Self> {
        require(unsafe { libc::geteuid() } == 0, "actual root image broker")?;
        witness.revalidate_live_admission()?;
        let lease = witness.identity_lease()?;
        let cohort = lease.broker_cohort().to_owned();
        require(is_digest(&cohort), "reserved cohort digest")?;
        let manifest = SealedFile::open_guarded(
            Path::new(MANIFEST_ROOT),
            &format!("{cohort}.json"),
            0,
            MAX_MANIFEST,
            |f| {
                lease.broker_reject_backing_body(f)?;
                Ok(())
            },
        )?;
        lease.broker_reject_backing_body(&manifest.file)?;
        let raw = manifest.bounded_bytes(MAX_MANIFEST)?;
        require(
            format!("{:x}", Sha256::digest(&raw)) == cohort,
            "manifest bytes must be the reserved cohort",
        )?;
        let declaration: CohortDeclaration = serde_json::from_slice(&raw)?;
        declaration.validate()?;
        let parent = Path::new(IMAGE_ROOT).join(&cohort).join("images");
        let system = SealedFile::open_guarded(&parent, "system.img", 0, MAX_IMAGE, |f| {
            lease.broker_reject_backing_body(f)?;
            Ok(())
        })?;
        let vendor = SealedFile::open_guarded(&parent, "vendor.img", 0, MAX_IMAGE, |f| {
            lease.broker_reject_backing_body(f)?;
            Ok(())
        })?;
        require(
            (system.identity.dev, system.identity.ino)
                != (vendor.identity.dev, vendor.identity.ino),
            "distinct system and vendor inodes",
        )?;
        // Never read a reserved data inode even if an incorrect root manifest
        // or a bind-mount alias names it as an image.
        lease.broker_reject_backing_body(&system.file)?;
        lease.broker_reject_backing_body(&vendor.file)?;
        system.verify_digest(declaration.system.bytes, &declaration.system.sha256)?;
        vendor.verify_digest(declaration.vendor.bytes, &declaration.vendor.sha256)?;
        let system_fs = Filesystem::detect(&system.file)?;
        let vendor_fs = Filesystem::detect(&vendor.file)?;
        let result = Self {
            manifest,
            system,
            vendor,
            system_fs,
            vendor_fs,
            cohort,
            host_uid: lease.host_uid(),
        };
        result.revalidate(witness)?;
        Ok(result)
    }
    fn revalidate(&self, witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
        witness.revalidate_live_admission()?;
        let lease = witness.identity_lease()?;
        require(
            lease.host_uid() == self.host_uid && lease.broker_cohort() == self.cohort,
            "cohort belongs to the same namespace reservation",
        )?;
        for file in [&self.manifest, &self.system, &self.vendor] {
            lease.broker_reject_backing_body(&file.file)?;
            file.revalidate()?;
        }
        Ok(())
    }
    pub(crate) fn layout(&self) -> AndroidImageLayout {
        AndroidImageLayout::GsiSystemAsRoot
    }
}

fn read_proc_field(directory: &File, name: &CStr) -> Result<Vec<u8>> {
    let mut file = open_leaf(directory, name, libc::O_RDONLY)?;
    let mut b = Vec::new();
    file.by_ref().take(4097).read_to_end(&mut b)?;
    require(b.len() <= 4096, "bounded complete kernel namespace field")?;
    Ok(b)
}
fn verify_map(raw: &[u8], range: IdRange) -> Result<()> {
    let text = std::str::from_utf8(raw).map_err(|_| MountError::Rejected("kernel map encoding"))?;
    require(
        text.ends_with('\n') && text.lines().count() == 1,
        "one complete mapping row",
    )?;
    let fields: Vec<_> = text.split_ascii_whitespace().collect();
    require(
        fields.len() == 3
            && fields
                .iter()
                .all(|v| !v.is_empty() && v.bytes().all(|b| b.is_ascii_digit())),
        "exact decimal map",
    )?;
    let values = fields
        .iter()
        .map(|v| {
            v.parse::<u64>()
                .map_err(|_| MountError::Rejected("map overflow"))
        })
        .collect::<Result<Vec<_>>>()?;
    require(
        values == [0, u64::from(range.start), u64::from(range.count)],
        "actual complete selected map",
    )
}
fn require_complete_namespace(witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
    witness.revalidate()?;
    let (uids, gids) = witness.identity_lease()?.broker_ranges();
    verify_map(
        &read_proc_field(witness.proc_directory(), c"uid_map")?,
        uids,
    )?;
    verify_map(
        &read_proc_field(witness.proc_directory(), c"gid_map")?,
        gids,
    )?;
    require(
        read_proc_field(witness.proc_directory(), c"setgroups")? == b"allow\n",
        "original supplementary-group semantics required",
    )?;
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    zero_rc(unsafe { libc::fstatfs(witness.user_namespace().as_raw_fd(), &mut fs) })?;
    let kind = unsafe { libc::ioctl(witness.user_namespace().as_raw_fd(), NS_GET_NSTYPE, 0) };
    require(
        fs.f_type == NSFS_MAGIC && kind == libc::CLONE_NEWUSER,
        "actual held user namespace",
    )?;
    witness.revalidate()?;
    Ok(())
}

#[repr(C)]
struct LoopInfo64 {
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
struct LoopConfig {
    fd: u32,
    block_size: u32,
    info: LoopInfo64,
    reserved: [u64; 8],
}
const _: () = assert!(std::mem::size_of::<LoopInfo64>() == 232);
const _: () = assert!(std::mem::size_of::<LoopConfig>() == 304);
#[repr(C)]
struct MountAttr {
    attr_set: u64,
    attr_clr: u64,
    propagation: u64,
    userns_fd: u64,
}
const _: () = assert!(std::mem::size_of::<MountAttr>() == 32);

fn loop_status(file: &File) -> Result<Option<LoopInfo64>> {
    let mut info: LoopInfo64 = unsafe { std::mem::zeroed() };
    // SAFETY: exactly the Linux 232-byte output structure.
    let rc = unsafe { libc::ioctl(file.as_raw_fd(), LOOP_GET_STATUS64, &mut info) };
    if rc == 0 {
        return Ok(Some(info));
    }
    let error = io::Error::last_os_error();
    if error.raw_os_error() == Some(libc::ENXIO) {
        Ok(None)
    } else {
        Err(error.into())
    }
}
fn owned_loop_info(info: &LoopInfo64, source: FileIdentity, index: u32) -> Result<()> {
    require(
        info.device == source.dev
            && info.inode == source.ino
            && info.number == index
            && info.offset == 0
            && info.size_limit == 0
            && info.flags == (LO_FLAGS_READ_ONLY | LO_FLAGS_AUTOCLEAR)
            && info.encrypt_type == 0
            && info.encrypt_key_size == 0
            && info.encrypt_key == [0; 32],
        "exact own read-only autoclear loop binding",
    )
}
fn same_block_node(expected: FileIdentity, current: &Metadata, device: u64) -> bool {
    // udev may legitimately finalize the group/mode after LOOP_CONFIGURE.
    // A held node is identified by its inode and rdev, while remaining a
    // root-owned block device without other-user write permission.
    current.dev() == expected.dev
        && current.ino() == expected.ino
        && current.mode() & libc::S_IFMT == libc::S_IFBLK
        && current.uid() == 0
        && current.mode() & 0o002 == 0
        && current.rdev() == device
}
#[derive(Debug)]
struct LoopBinding {
    file: Option<File>,
    node: FileIdentity,
    device: u64,
    index: u32,
    source: FileIdentity,
}
impl LoopBinding {
    fn attach(source: &SealedFile) -> Result<Self> {
        source.revalidate()?;
        let control = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .custom_flags(O_SAFE)
            .open("/dev/loop-control")?;
        let cm = control.metadata()?;
        require(
            cm.mode() & libc::S_IFMT == libc::S_IFCHR
                && cm.uid() == 0
                && libc::major(cm.rdev()) == 10
                && libc::minor(cm.rdev()) == 237,
            "actual loop-control character device",
        )?;
        for _ in 0..64 {
            // SAFETY: GET_FREE has no argument; explicitly provide zero.
            let number = unsafe { libc::ioctl(control.as_raw_fd(), LOOP_CTL_GET_FREE, 0) };
            if number < 0 {
                return Err(io::Error::last_os_error().into());
            }
            let index = u32::try_from(number).map_err(|_| MountError::Rejected("loop number"))?;
            require(index < 1_048_576, "bounded loop index")?;
            let path = PathBuf::from(format!("/dev/loop{index}"));
            let fd = std::fs::OpenOptions::new()
                .read(true)
                .write(true)
                .custom_flags(O_SAFE)
                .open(&path)?;
            let meta = fd.metadata()?;
            let mut raw = Vec::new();
            File::open(format!("/sys/block/loop{index}/dev"))?
                .take(129)
                .read_to_end(&mut raw)?;
            require(raw.len() <= 128, "bounded kernel loop device metadata")?;
            let text = std::str::from_utf8(&raw)
                .map_err(|_| MountError::Rejected("loop sysfs encoding"))?;
            let (major, minor) = text
                .trim()
                .split_once(':')
                .ok_or(MountError::Rejected("loop sysfs device"))?;
            let major = major
                .parse::<u32>()
                .map_err(|_| MountError::Rejected("loop major"))?;
            let minor = minor
                .parse::<u32>()
                .map_err(|_| MountError::Rejected("loop minor"))?;
            require(
                meta.mode() & libc::S_IFMT == libc::S_IFBLK
                    && meta.uid() == 0
                    && major == 7
                    && meta.rdev() == libc::makedev(major, minor)
                    && FileIdentity::of(&meta)
                        == FileIdentity::of(&std::fs::symlink_metadata(&path)?),
                "held actual free loop node",
            )?;
            let mut config: LoopConfig = unsafe { std::mem::zeroed() };
            config.fd = u32::try_from(source.file.as_raw_fd())
                .map_err(|_| MountError::Rejected("source descriptor"))?;
            config.info.flags = LO_FLAGS_READ_ONLY | LO_FLAGS_AUTOCLEAR;
            // LOOP_CONFIGURE is the atomic bind/configure operation. A busy
            // device was allocated by someone else and is never cleared.
            let rc = unsafe { libc::ioctl(fd.as_raw_fd(), LOOP_CONFIGURE, &config) };
            if rc < 0 {
                let error = io::Error::last_os_error();
                if error.raw_os_error() == Some(libc::EBUSY) {
                    continue;
                }
                return Err(error.into());
            }
            return Ok(Self {
                file: Some(fd),
                node: FileIdentity::of(&meta),
                device: meta.rdev(),
                index,
                source: source.identity,
            });
        }
        Err(MountError::Busy)
    }
    fn file(&self) -> Result<&File> {
        self.file
            .as_ref()
            .ok_or(MountError::Rejected("loop already retired"))
    }
    fn verify(&self) -> Result<()> {
        let fd = self.file()?;
        require(
            same_block_node(self.node, &fd.metadata()?, self.device),
            "held loop descriptor changed",
        )?;
        let info =
            loop_status(fd)?.ok_or(MountError::Rejected("owned loop unexpectedly unbound"))?;
        owned_loop_info(&info, self.source, self.index)
    }
    fn retire(&mut self) -> Result<u64> {
        let fd = self.file()?;
        require(
            same_block_node(self.node, &fd.metadata()?, self.device),
            "retirement only through the held loop node",
        )?;
        if let Some(info) = loop_status(fd)? {
            owned_loop_info(&info, self.source, self.index)?;
            // This descriptor's exact backing inode was just proved to be
            // ours. Never clear an arbitrary loop path or a foreign binding.
            zero_rc(unsafe { libc::ioctl(fd.as_raw_fd(), LOOP_CLR_FD, 0) })?;
        }
        // A successful CLR_FD can defer until remaining kernel consumers
        // disappear. Only ENXIO from this held device proves it is unbound.
        if loop_status(fd)?.is_some() {
            return Err(MountError::Busy);
        }
        drop(self.file.take());
        Ok(self.device)
    }
}
impl Drop for LoopBinding {
    fn drop(&mut self) {
        if let Some(fd) = self.file.take() {
            // Only explicit, checked retirement releases an owned binding.
            // On uncertainty the surrounding mount guard also keeps its
            // reference to the real reservation lock.
            std::mem::forget(fd);
        }
    }
}

fn configure(context: &File, command: u32, key: &CStr, value: Option<&CStr>) -> Result<()> {
    let value = value.map_or(std::ptr::null(), CStr::as_ptr);
    let rc = unsafe {
        libc::syscall(
            libc::SYS_fsconfig,
            context.as_raw_fd(),
            command,
            key.as_ptr(),
            value,
            0,
        )
    };
    if rc == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error().into())
    }
}
fn fs_type(file: &File) -> Result<libc::c_long> {
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    zero_rc(unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) })?;
    Ok(fs.f_type)
}
fn mount_id(file: &File) -> Result<u64> {
    let mut stat: libc::statx = unsafe { std::mem::zeroed() };
    // The held mount descriptor prevents this mount ID from being reused.
    let rc = unsafe {
        libc::syscall(
            libc::SYS_statx,
            file.as_raw_fd(),
            c"".as_ptr(),
            AT_EMPTY_PATH,
            0x1000u32,
            &mut stat,
        )
    };
    if rc != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        stat.stx_mask & 0x1000 != 0 && stat.stx_mnt_id != 0,
        "kernel mount identity available",
    )?;
    Ok(stat.stx_mnt_id)
}
fn require_detached(file: &File) -> Result<u64> {
    let id = mount_id(file)?;
    let mut raw = Vec::new();
    File::open("/proc/self/mountinfo")?
        .take(16 * 1024 * 1024 + 1)
        .read_to_end(&mut raw)?;
    require(
        raw.len() <= 16 * 1024 * 1024,
        "complete bounded host mount inventory",
    )?;
    let text =
        std::str::from_utf8(&raw).map_err(|_| MountError::Rejected("mount inventory encoding"))?;
    for line in text.lines() {
        let observed = line
            .split_ascii_whitespace()
            .next()
            .ok_or(MountError::Rejected("mount inventory row"))?
            .parse::<u64>()
            .map_err(|_| MountError::Rejected("mount inventory ID"))?;
        require(
            observed != id,
            "mount must remain detached from broker namespace",
        )?;
    }
    require(mount_id(file)? == id, "held mount identity stable")?;
    Ok(id)
}
fn verify_readonly_mount(
    file: &File,
    fs: Filesystem,
    uids: IdRange,
    gids: IdRange,
    id: u64,
) -> Result<()> {
    require(
        file.metadata()?.is_dir()
            && file.metadata()?.uid() == uids.start
            && file.metadata()?.gid() == gids.start
            && fs_type(file)? == fs.magic(),
        "actual selected filesystem and mapped root IDs",
    )?;
    let mut vfs: libc::statvfs = unsafe { std::mem::zeroed() };
    zero_rc(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut vfs) })?;
    require(
        vfs.f_flag as u64 & READONLY_FLAGS == READONLY_FLAGS,
        "read-only nosuid nodev mount",
    )?;
    require(mount_id(file)? == id, "same held detached mount")?;
    Ok(())
}
fn detached_mount(
    binding: &LoopBinding,
    fs: Filesystem,
    userns: &File,
    uids: IdRange,
    gids: IdRange,
) -> Result<File> {
    binding.verify()?;
    let context =
        syscall_fd(unsafe { libc::syscall(libc::SYS_fsopen, fs.name().as_ptr(), FSOPEN_CLOEXEC) })?;
    let source = text_name(&format!("/proc/self/fd/{}", binding.file()?.as_raw_fd()))?;
    // A fixed self-FD path is resolved while that exact owned block FD is
    // held. No caller-provided path or reusable /dev/loopN name reaches fsopen.
    configure(&context, FSCONFIG_SET_STRING, c"source", Some(&source))?;
    configure(&context, FSCONFIG_SET_FLAG, c"ro", None)?;
    if fs == Filesystem::Ext4 {
        // Read-only ext4 alone can still attempt journal replay.
        configure(&context, FSCONFIG_SET_FLAG, c"noload", None)?;
    }
    let created = unsafe {
        libc::syscall(
            libc::SYS_fsconfig,
            context.as_raw_fd(),
            FSCONFIG_CMD_CREATE,
            std::ptr::null::<libc::c_char>(),
            std::ptr::null::<libc::c_char>(),
            0,
        )
    };
    if created != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let mount = syscall_fd(unsafe {
        libc::syscall(
            libc::SYS_fsmount,
            context.as_raw_fd(),
            FSMOUNT_CLOEXEC,
            READONLY_FLAGS as u32,
        )
    })?;
    let original = mount.metadata()?;
    require(
        original.is_dir() && original.uid() == 0 && original.gid() == 0,
        "original image root owned by Android root",
    )?;
    require_detached(&mount)?;
    let attr = MountAttr {
        attr_set: READONLY_FLAGS | MOUNT_ATTR_IDMAP,
        attr_clr: 0,
        propagation: 0,
        userns_fd: u64::try_from(userns.as_raw_fd())
            .map_err(|_| MountError::Rejected("namespace descriptor"))?,
    };
    let rc = unsafe {
        libc::syscall(
            libc::SYS_mount_setattr,
            mount.as_raw_fd(),
            c"".as_ptr(),
            AT_EMPTY_PATH,
            &attr,
            std::mem::size_of::<MountAttr>(),
        )
    };
    if rc != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let id = require_detached(&mount)?;
    verify_readonly_mount(&mount, fs, uids, gids, id)?;
    binding.verify()?;
    Ok(mount)
}

#[derive(Debug)]
struct MountedImage {
    role: &'static str,
    mount: Option<File>,
    binding: LoopBinding,
    fs: Filesystem,
    mount_id: u64,
}
#[derive(Debug)]
struct MountResources {
    images: Vec<MountedImage>,
    cohort: VerifiedCohort,
    userns: File,
    userns_identity: (u64, u64),
    uids: IdRange,
    gids: IdRange,
    reservation_retention: File,
}
impl MountResources {
    fn cleanup(&mut self) -> Result<Vec<u64>> {
        // Mount references must disappear before asking the kernel to detach
        // their exact owned backing devices.
        for image in &mut self.images {
            drop(image.mount.take());
        }
        let mut released = Vec::new();
        for image in &mut self.images {
            if image.binding.file.is_some() {
                released.push(image.binding.retire()?);
            }
        }
        Ok(released)
    }
    fn matches_witness(&self, witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
        witness.revalidate()?;
        let meta = witness.user_namespace().metadata()?;
        let lease = witness.identity_lease()?;
        require(
            (meta.dev(), meta.ino()) == self.userns_identity
                && lease.host_uid() == self.cohort.host_uid
                && lease.broker_cohort() == self.cohort.cohort
                && lease.broker_ranges() == (self.uids, self.gids),
            "same live namespace, cohort and reservation",
        )?;
        Ok(())
    }
}

/// Not Clone/Deserialize. An uncertain destructor quarantines descriptors and
/// the retained real reservation lock instead of claiming cleanup succeeded.
#[derive(Debug)]
pub(crate) struct PreparedMounts {
    resources: Option<MountResources>,
    exported: bool,
}
#[derive(Debug, Serialize)]
pub(crate) struct MountRetirement {
    images: usize,
    detached_descriptors_closed: bool,
    owned_loop_devices_observed_unbound: Vec<u64>,
    after_owned_tree_exit: bool,
}
impl PreparedMounts {
    pub(crate) fn prepare(
        witness: &OwnedNamespaceWitness<'_>,
        cohort: VerifiedCohort,
    ) -> Result<Self> {
        cohort.revalidate(witness)?;
        require_complete_namespace(witness)?;
        let lease = witness.identity_lease()?;
        let retention = lease.broker_retain_reservation()?;
        let (uids, gids) = lease.broker_ranges();
        let userns = witness.user_namespace().try_clone()?;
        let meta = userns.metadata()?;
        let mut guard = Self {
            exported: false,
            resources: Some(MountResources {
                images: Vec::new(),
                cohort,
                userns,
                userns_identity: (meta.dev(), meta.ino()),
                uids,
                gids,
                reservation_retention: retention,
            }),
        };
        let result: Result<()> = (|| {
            let resources = guard
                .resources
                .as_mut()
                .ok_or(MountError::Rejected("mount guard absent"))?;
            for (role, fs) in [
                ("system", resources.cohort.system_fs),
                ("vendor", resources.cohort.vendor_fs),
            ] {
                resources.matches_witness(witness)?;
                let source = if role == "system" {
                    &resources.cohort.system
                } else {
                    &resources.cohort.vendor
                };
                let binding = LoopBinding::attach(source)?;
                resources.images.push(MountedImage {
                    role,
                    mount: None,
                    binding,
                    fs,
                    mount_id: 0,
                });
                let index = resources.images.len() - 1;
                resources.images[index].binding.verify()?;
                let mount = detached_mount(
                    &resources.images[index].binding,
                    fs,
                    &resources.userns,
                    uids,
                    gids,
                )?;
                resources.images[index].mount_id = require_detached(&mount)?;
                resources.images[index].mount = Some(mount);
                resources.cohort.revalidate(witness)?;
            }
            require(resources.images.len() == 2, "complete two-image mount set")?;
            resources.matches_witness(witness)?;
            Ok(())
        })();
        result?;
        Ok(guard)
    }
    /// Marks an attempted transfer before any FD leaves this guard. A failed
    /// send does not silently regain the no-transfer cleanup privilege.
    pub(crate) fn descriptors_for_transfer<'a>(
        &'a mut self,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<[BorrowedFd<'a>; 2]> {
        require(!self.exported, "single owned descriptor transfer")?;
        self.resources
            .as_ref()
            .ok_or(MountError::Rejected("mounts already retired"))?
            .cohort
            .revalidate(witness)?;
        self.descriptors_after_authority_validation(witness)
    }

    fn descriptors_after_authority_validation<'a>(
        &'a mut self,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<[BorrowedFd<'a>; 2]> {
        require(!self.exported, "single owned descriptor transfer")?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("mounts already retired"))?;
        resources.matches_witness(witness)?;
        require_complete_namespace(witness)?;
        require(
            resources.images.len() == 2
                && resources.images[0].role == "system"
                && resources.images[1].role == "vendor",
            "fixed descriptor role order",
        )?;
        for image in &resources.images {
            image.binding.verify()?;
            let mount = image
                .mount
                .as_ref()
                .ok_or(MountError::Rejected("missing detached mount"))?;
            require(
                require_detached(mount)? == image.mount_id,
                "detached until actual transfer",
            )?;
            verify_readonly_mount(
                mount,
                image.fs,
                resources.uids,
                resources.gids,
                image.mount_id,
            )?;
        }
        self.exported = true;
        Ok([
            resources.images[0]
                .mount
                .as_ref()
                .ok_or(MountError::Rejected("system mount absent"))?
                .as_fd(),
            resources.images[1]
                .mount
                .as_ref()
                .ok_or(MountError::Rejected("vendor mount absent"))?
                .as_fd(),
        ])
    }
    pub(crate) fn retire_untransferred(mut self) -> Result<MountRetirement> {
        require(
            !self.exported,
            "transferred mounts require actual owned PID 1 retirement",
        )?;
        self.cleanup(false)
    }
    pub(crate) fn retire_after_tree(
        mut self,
        retired: &RetiredTreeWitness<'_>,
    ) -> Result<MountRetirement> {
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("mounts already retired"))?;
        retired.verify_mount_retirement(
            &resources.userns,
            resources.cohort.host_uid,
            &resources.cohort.cohort,
        )?;
        self.cleanup(true)
    }
    fn cleanup(&mut self, after_owned_tree_exit: bool) -> Result<MountRetirement> {
        let resources = self
            .resources
            .as_mut()
            .ok_or(MountError::Rejected("mounts already retired"))?;
        let images = resources.images.len();
        let released = resources.cleanup()?;
        // The real lock is released only after every owned loop was observed
        // unbound. Kernel cleanup uncertainty keeps it with the remaining FDs.
        drop(self.resources.take());
        Ok(MountRetirement {
            images,
            detached_descriptors_closed: true,
            owned_loop_devices_observed_unbound: released,
            after_owned_tree_exit,
        })
    }
}
impl Drop for PreparedMounts {
    fn drop(&mut self) {
        if !self.exported {
            if let Some(resources) = self.resources.as_mut() {
                if resources.cleanup().is_ok() {
                    drop(self.resources.take());
                    return;
                }
            }
        }
        if let Some(resources) = self.resources.take() {
            // This retains loop/mount/namespace FDs AND the duplicated flock
            // description. A JSON receipt cannot turn uncertainty into release.
            std::mem::forget(resources);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};
    fn fixture() -> tempfile::TempDir {
        // Reuse the same complete ancestor check as production. Development
        // checkouts may sit below a group-writable work directory.
        let owner = unsafe { libc::geteuid() };
        let cwd = std::env::current_dir().unwrap();
        let mut candidates: Vec<PathBuf> = cwd.ancestors().map(Path::to_path_buf).collect();
        for name in ["XDG_RUNTIME_DIR", "HOME"] {
            if let Some(path) = std::env::var_os(name) {
                candidates.push(PathBuf::from(path));
            }
        }
        for parent in candidates {
            if trusted_directory(&parent, owner).is_ok() {
                return tempfile::tempdir_in(parent).unwrap();
            }
        }
        panic!("test requires an owned directory beneath non-writable ancestors");
    }
    fn write(root: &Path, name: &str, bytes: &[u8]) {
        let p = root.join(name);
        std::fs::write(&p, bytes).unwrap();
        std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o600)).unwrap();
    }
    fn public_fixture(root: &Path, name: &str) -> Result<SealedFile> {
        SealedFile::open_guarded(root, name, unsafe { libc::geteuid() }, 1024 * 1024, |_| {
            Ok(())
        })
    }
    #[test]
    fn complete_public_digest_covers_tail_and_revalidation_rejects_same_bytes_replacement() {
        let dir = fixture();
        let bytes = vec![0x5a; 131072];
        write(dir.path(), "system.img", &bytes);
        let sha = format!("{:x}", Sha256::digest(&bytes));
        let seal = public_fixture(dir.path(), "system.img").unwrap();
        seal.verify_digest(bytes.len() as u64, &sha).unwrap();
        std::fs::rename(dir.path().join("system.img"), dir.path().join("original")).unwrap();
        write(dir.path(), "system.img", &bytes);
        assert!(seal.revalidate().is_err());
        let mut wrong = bytes.clone();
        *wrong.last_mut().unwrap() = 0x5b;
        write(dir.path(), "vendor.img", &wrong);
        let changed = public_fixture(dir.path(), "vendor.img").unwrap();
        assert!(changed.verify_digest(bytes.len() as u64, &sha).is_err());
    }
    #[test]
    fn metadata_admission_rejects_before_any_readable_descriptor_is_opened() {
        let dir = fixture();
        write(dir.path(), "system.img", b"public fixture only");
        let observed = std::cell::Cell::new(false);
        let result = SealedFile::open_guarded(
            dir.path(),
            "system.img",
            unsafe { libc::geteuid() },
            4096,
            |file| {
                let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
                assert_ne!(flags & libc::O_PATH, 0);
                let mut byte = [0u8; 1];
                assert_eq!(
                    file.read_at(&mut byte, 0).unwrap_err().raw_os_error(),
                    Some(libc::EBADF)
                );
                observed.set(true);
                Err(MountError::Rejected("protected inode"))
            },
        );
        assert!(observed.get() && result.is_err());
    }
    #[test]
    fn aliases_links_writable_files_and_fifos_never_become_image_authority() {
        let dir = fixture();
        write(dir.path(), "system.img", b"public fixture");
        symlink("system.img", dir.path().join("alias")).unwrap();
        assert!(public_fixture(dir.path(), "alias").is_err());
        std::fs::hard_link(dir.path().join("system.img"), dir.path().join("hard")).unwrap();
        assert!(public_fixture(dir.path(), "system.img").is_err());
        std::fs::remove_file(dir.path().join("hard")).unwrap();
        std::fs::set_permissions(
            dir.path().join("system.img"),
            std::fs::Permissions::from_mode(0o666),
        )
        .unwrap();
        assert!(public_fixture(dir.path(), "system.img").is_err());
        assert!(public_fixture(dir.path(), "../outside").is_err());
        let fifo = text_name(dir.path().join("fifo").to_str().unwrap()).unwrap();
        assert_eq!(unsafe { libc::mkfifo(fifo.as_ptr(), 0o600) }, 0);
        assert!(public_fixture(dir.path(), "fifo").is_err());
    }
    #[test]
    fn manifest_cannot_select_paths_another_layout_or_undeclared_inputs() {
        let good = serde_json::json!({"schema":1,"scope":"android_base_images_v1","layout":"gsi_system_as_root",
            "system":{"file":"system.img","bytes":4096,"sha256":"a".repeat(64)},
            "vendor":{"file":"vendor.img","bytes":4096,"sha256":"b".repeat(64)}});
        serde_json::from_value::<CohortDeclaration>(good.clone())
            .unwrap()
            .validate()
            .unwrap();
        for bad in [
            "../data.img",
            "/etc/passwd",
            "vendor.img",
            "system.img\u{0000}",
        ] {
            let mut v = good.clone();
            v["system"]["file"] = serde_json::json!(bad);
            assert!(
                serde_json::from_value::<CohortDeclaration>(v)
                    .unwrap()
                    .validate()
                    .is_err()
            );
        }
        let mut v = good.clone();
        v["layout"] = serde_json::json!("split_partitions");
        assert!(
            serde_json::from_value::<CohortDeclaration>(v)
                .unwrap()
                .validate()
                .is_err()
        );
        let mut v = good.clone();
        v["data"] = serde_json::json!({"file":"/var/lib/droidloom/data.img"});
        assert!(serde_json::from_value::<CohortDeclaration>(v).is_err());
        let mut v = good;
        v["system"]["bytes"] = serde_json::json!(MAX_IMAGE + 512);
        assert!(
            serde_json::from_value::<CohortDeclaration>(v)
                .unwrap()
                .validate()
                .is_err()
        );
    }
    #[test]
    fn writable_ancestor_is_rejected_before_metadata_or_body_admission() {
        let root = fixture();
        let parent = root.path().join("group-writable");
        std::fs::create_dir(&parent).unwrap();
        std::fs::set_permissions(&parent, std::fs::Permissions::from_mode(0o770)).unwrap();
        let leaf = parent.join("private");
        std::fs::create_dir(&leaf).unwrap();
        std::fs::set_permissions(&leaf, std::fs::Permissions::from_mode(0o700)).unwrap();
        write(&leaf, "system.img", b"public test image");
        let observed = std::cell::Cell::new(false);
        let result = SealedFile::open_guarded(
            &leaf,
            "system.img",
            unsafe { libc::geteuid() },
            4096,
            |_| {
                observed.set(true);
                Ok(())
            },
        );
        assert!(result.is_err() && !observed.get());
    }

    #[test]
    fn retained_actual_flock_survives_identity_lease_drop() {
        let (root, lease) = crate::production_identity::tests::broker_fixture();
        let retained = lease.broker_retain_reservation().unwrap();
        let contender = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open(root.path().join("registry/u1000.lease"))
            .unwrap();
        drop(lease);
        assert_eq!(
            unsafe { libc::flock(contender.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            -1
        );
        assert_eq!(io::Error::last_os_error().kind(), io::ErrorKind::WouldBlock);
        drop(retained);
        assert_eq!(
            unsafe { libc::flock(contender.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        // Ordinary File drop closes this test's sole new lock description.
    }
}

/// Fixed real-filesystem controls, absent from every non-test binary.
/// This type never constructs HostAdmission or a public cohort authority.
#[cfg(test)]
pub(crate) mod private_control {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};
    use std::process::{Command, Stdio};

    pub(crate) const FIXTURE_PARENT: &str = "/run/droidloom-mount-private-control-20261109-8b88-r1";
    const IMAGE_BYTES: u64 = 32 * 1024 * 1024;

    pub(crate) struct PrivateControlMounts {
        prepared: Option<PreparedMounts>,
        fixture: Option<tempfile::TempDir>,
        verification_files: [SealedFile; 2],
        digests: [String; 2],
    }

    fn write_private(path: &Path, raw: &[u8], mode: u32) -> Result<()> {
        use std::io::Write;
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(mode)
            .custom_flags(O_SAFE)
            .open(path)?;
        file.write_all(raw)?;
        file.sync_all()?;
        file.set_permissions(std::fs::Permissions::from_mode(mode))?;
        Ok(())
    }

    fn create_directory(path: &Path) -> Result<()> {
        std::fs::create_dir_all(path)?;
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755))?;
        Ok(())
    }

    fn digest(file: &SealedFile) -> Result<String> {
        let mut sha = Sha256::new();
        let mut block = vec![0u8; 1024 * 1024];
        let mut offset = 0;
        while offset < file.identity.bytes {
            let length = (file.identity.bytes - offset).min(block.len() as u64) as usize;
            file.file.read_exact_at(&mut block[..length], offset)?;
            sha.update(&block[..length]);
            offset += length as u64;
        }
        file.revalidate()?;
        Ok(format!("{:x}", sha.finalize()))
    }

    /// Only this fixed private control can construct synthetic image authority.
    /// Its underlying lease is the namespace tests' private fixture, never host
    /// account/grant authority. The ordinary production constructors stay gated.
    pub(crate) fn prepare_private_control_mounts(
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<PrivateControlMounts> {
        require(
            unsafe { libc::getuid() } == 0 && unsafe { libc::geteuid() } == 0,
            "separately reviewed root filesystem control",
        )?;
        witness.revalidate()?;
        require_complete_namespace(witness)?;
        let parent = trusted_directory(Path::new(FIXTURE_PARENT), 0)?;
        require(
            parent.metadata()?.mode() & 0o777 == 0o700,
            "fixed root-only private fixture parent",
        )?;
        let fixture = tempfile::Builder::new()
            .prefix("case-")
            .tempdir_in(FIXTURE_PARENT)?;
        let root = fixture.path();
        let system_tree = root.join("system-tree");
        let vendor_tree = root.join("vendor-tree");
        create_directory(&system_tree)?;
        create_directory(&vendor_tree)?;
        for name in [
            "system",
            "system/product",
            "system/system_ext",
            "vendor",
            "data",
            "metadata",
        ] {
            create_directory(&system_tree.join(name))?;
        }
        create_directory(&vendor_tree.join("etc"))?;
        symlink("/system/product", system_tree.join("product"))?;
        symlink("/system/system_ext", system_tree.join("system_ext"))?;
        write_private(
            &system_tree.join("system/readonly-probe"),
            b"private-system-readonly-probe\n",
            0o666,
        )?;
        write_private(
            &vendor_tree.join("readonly-probe"),
            b"private-vendor-readonly-probe\n",
            0o666,
        )?;
        for (role, tree) in [("system", &system_tree), ("vendor", &vendor_tree)] {
            let path = root.join(format!("{role}.img"));
            let file = std::fs::OpenOptions::new()
                .read(true)
                .write(true)
                .create_new(true)
                .mode(0o600)
                .custom_flags(O_SAFE)
                .open(&path)?;
            file.set_len(IMAGE_BYTES)?;
            file.sync_all()?;
            drop(file);
            let output = Command::new("/usr/sbin/mke2fs")
                .args([
                    "-q",
                    "-F",
                    "-t",
                    "ext4",
                    "-m",
                    "0",
                    "-E",
                    "lazy_itable_init=0,lazy_journal_init=0",
                    "-d",
                ])
                .arg(tree)
                .arg(&path)
                .env_clear()
                .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
                .env("LC_ALL", "C")
                .stdin(Stdio::null())
                .output()?;
            write_private(
                &root.join(format!("{role}-mke2fs.stdout")),
                &output.stdout,
                0o400,
            )?;
            write_private(
                &root.join(format!("{role}-mke2fs.stderr")),
                &output.stderr,
                0o400,
            )?;
            require(
                output.status.success(),
                "normal private mke2fs must actually succeed",
            )?;
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o400))?;
        }
        let lease = witness.identity_lease()?;
        let open_image = |name: &str| {
            SealedFile::open_guarded(root, name, 0, IMAGE_BYTES, |f| {
                lease.broker_reject_backing_body(f)?;
                Ok(())
            })
        };
        let system = open_image("system.img")?;
        let vendor = open_image("vendor.img")?;
        let digests = [digest(&system)?, digest(&vendor)?];
        for (file, sha) in [(&system, &digests[0]), (&vendor, &digests[1])] {
            file.verify_digest(IMAGE_BYTES, sha)?;
            require(
                Filesystem::detect(&file.file)? == Filesystem::Ext4,
                "actual newly formatted private ext4 required",
            )?;
        }
        let declaration = serde_json::json!({
            "schema":1, "scope":"private_test_ext4_images_only",
            "system":{"bytes":IMAGE_BYTES,"sha256":digests[0]},
            "vendor":{"bytes":IMAGE_BYTES,"sha256":digests[1]},
            "production_authority":false, "Android_exec":false
        });
        write_private(
            &root.join("fixture-manifest.json"),
            &serde_json::to_vec(&declaration)?,
            0o400,
        )?;
        let manifest =
            SealedFile::open_guarded(root, "fixture-manifest.json", 0, MAX_MANIFEST, |f| {
                lease.broker_reject_backing_body(f)?;
                Ok(())
            })?;
        let verification_files = [open_image("system.img")?, open_image("vendor.img")?];
        let cohort = VerifiedCohort {
            manifest,
            system,
            vendor,
            system_fs: Filesystem::Ext4,
            vendor_fs: Filesystem::Ext4,
            cohort: lease.broker_cohort().to_owned(),
            host_uid: lease.host_uid(),
        };
        let retention = lease.broker_retain_reservation()?;
        let (uids, gids) = lease.broker_ranges();
        let userns = witness.user_namespace().try_clone()?;
        let meta = userns.metadata()?;
        let mut prepared = PreparedMounts {
            exported: false,
            resources: Some(MountResources {
                images: Vec::new(),
                cohort,
                userns,
                userns_identity: (meta.dev(), meta.ino()),
                uids,
                gids,
                reservation_retention: retention,
            }),
        };
        // Same actual loop/fsopen/mount_setattr and owned cleanup as production.
        // The separate control type omits only the unavailable production
        // HostAdmission construction; it cannot escape cfg(test).
        let result: Result<()> = (|| {
            let resources = prepared
                .resources
                .as_mut()
                .ok_or(MountError::Rejected("private mount guard absent"))?;
            for role in ["system", "vendor"] {
                resources.matches_witness(witness)?;
                let source = if role == "system" {
                    &resources.cohort.system
                } else {
                    &resources.cohort.vendor
                };
                let binding = LoopBinding::attach(source)?;
                resources.images.push(MountedImage {
                    role,
                    mount: None,
                    binding,
                    fs: Filesystem::Ext4,
                    mount_id: 0,
                });
                let image = resources
                    .images
                    .last_mut()
                    .ok_or(MountError::Rejected("private image absent"))?;
                image.binding.verify()?;
                let mount = detached_mount(
                    &image.binding,
                    Filesystem::Ext4,
                    &resources.userns,
                    uids,
                    gids,
                )?;
                image.mount_id = require_detached(&mount)?;
                image.mount = Some(mount);
                witness.revalidate()?;
            }
            Ok(())
        })();
        if let Err(error) = result {
            // The PreparedMounts destructor attempts checked cleanup and
            // quarantines uncertain kernel resources. Keep their private names.
            std::mem::forget(fixture);
            return Err(error);
        }
        let result = PrivateControlMounts {
            prepared: Some(prepared),
            fixture: Some(fixture),
            verification_files,
            digests,
        };
        result.verify_images_unchanged()?;
        Ok(result)
    }

    impl PrivateControlMounts {
        pub(crate) fn verify_images_unchanged(&self) -> Result<()> {
            for (file, sha) in self.verification_files.iter().zip(&self.digests) {
                file.verify_digest(IMAGE_BYTES, sha)?;
            }
            Ok(())
        }

        pub(crate) fn descriptors_for_transfer<'a>(
            &'a mut self,
            witness: &OwnedNamespaceWitness<'_>,
        ) -> Result<[BorrowedFd<'a>; 2]> {
            self.verify_images_unchanged()?;
            self.prepared
                .as_mut()
                .ok_or(MountError::Rejected("private mounts retired"))?
                .descriptors_after_authority_validation(witness)
        }

        pub(crate) fn retire_after_tree(
            mut self,
            retired: &RetiredTreeWitness<'_>,
        ) -> Result<MountRetirement> {
            self.verify_images_unchanged()?;
            let prepared = self
                .prepared
                .take()
                .ok_or(MountError::Rejected("private mounts retired"))?;
            let result = match prepared.retire_after_tree(retired) {
                Ok(result) => result,
                Err(error) => {
                    if let Some(root) = self.fixture.take() {
                        std::mem::forget(root);
                    }
                    return Err(error);
                }
            };
            self.verify_images_unchanged()?;
            if let Some(root) = self.fixture.take() {
                root.close()?;
            }
            Ok(result)
        }
    }

    impl Drop for PrivateControlMounts {
        fn drop(&mut self) {
            if self.prepared.is_some() {
                if let Some(root) = self.fixture.take() {
                    std::mem::forget(root);
                }
            }
        }
    }
}
