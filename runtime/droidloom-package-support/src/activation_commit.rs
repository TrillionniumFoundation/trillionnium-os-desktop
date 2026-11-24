//! Normal first-activation installation of the fixed host, Android and kernel
//! products. Material inventories select bytes; only the original live
//! InstallationPermit authorizes mutations of the installed system.
use super::{
    Result,
    activation_android::{self, AndroidInputs},
    activation_files::{self as files, FileIdentity, FilePin, HeldFile},
    activation_host::{self, HostManifest},
    activation_labels::Labeler,
    activation_owner::InstallationPermit,
    activation_platform::{self, PlatformInputs},
};
use serde_json::{Value, json};
use std::{
    cell::{Cell, RefCell},
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, Metadata},
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::{fs::MetadataExt, process::CommandExt},
    },
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::atomic::{AtomicU64, Ordering},
    time::{Duration, Instant},
};

const MIB: u64 = 1024 * 1024;
const MAX_FILE: u64 = 8 * 1024 * MIB;
const STAGING: &str = "/var/lib/droidloom/activation-staging";
const CONFIGURATION: [&str; 3] = [
    "etc/droidloom/cell.json",
    "etc/droidloom/production/selected.json",
    "etc/droidloom/container-launcher.json",
];
const STATE: [&str; 2] = [
    "var/lib/droidloom-mac-calibration",
    "var/lib/droidloom/identity-reservations",
];
const LEGACY_DIRECTORIES: [&str; 2] = ["/usr/lib/droidloom", "/usr/share/droidloom"];
fn legacy_executable(path: &Path, id: &FileIdentity) -> bool {
    [
        "/usr/bin/droidloom-applications",
        "/usr/bin/droidloom-doctor",
        "/usr/bin/droidloom-wayland",
        "/usr/bin/droidloomctl",
        "/usr/lib/droidloom/droidloom-package-helper",
    ]
    .iter()
    .any(|p| path == Path::new(p))
        && id.uid == 1000
        && id.gid == 1000
        && id.mode == 0o100755
        && id.links == 1
}
const BOARD: &str = include_str!(
    "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
);
static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);
fn require(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}
fn relative(s: &str) -> Result<()> {
    require(
        !s.is_empty()
            && s.len() <= 1024
            && s.is_ascii()
            && !s.starts_with('/')
            && !s.contains('\\')
            && !s.bytes().any(|b| b.is_ascii_control())
            && s.split('/').all(|p| !p.is_empty() && p != "." && p != ".."),
        "unsafe fixed installed product path",
    )
}
fn root_file(pin: &FilePin, mode: u32) -> Result<HeldFile> {
    let file = HeldFile::open(pin, MAX_FILE)?;
    require(
        file.identity().uid == 0
            && file.identity().gid == 0
            && file.identity().mode & 0o7777 == mode,
        "installed/staged product custody or mode differs",
    )?;
    files::no_privilege_xattrs(file.file())?;
    Ok(file)
}
#[derive(Clone)]
struct ObservedFile {
    pin: FilePin,
    identity: FileIdentity,
}
impl ObservedFile {
    fn from_pin(pin: FilePin, mode: u32) -> Result<Self> {
        let file = root_file(&pin, mode)?;
        Ok(Self {
            pin,
            identity: file.identity().clone(),
        })
    }
    fn capture(path: &Path) -> Result<Self> {
        let pin = files::pin_file(path)?;
        let file = HeldFile::open(&pin, MAX_FILE)?;
        require(
            file.identity().uid == 0 && file.identity().gid == 0,
            "existing product is not root-owned",
        )?;
        files::no_privilege_xattrs(file.file())?;
        Ok(Self {
            pin,
            identity: file.identity().clone(),
        })
    }
    fn capture_original_product(path: &Path) -> Result<Self> {
        let pin = files::pin_file(path)?;
        let held = HeldFile::open(&pin, MAX_FILE)?;
        let identity = held.identity().clone();
        require(
            (identity.uid == 0 && identity.gid == 0) || legacy_executable(path, &identity),
            "existing product has neither root custody nor the fixed legacy executable identity",
        )?;
        files::no_privilege_xattrs(held.file())?;
        Ok(Self { pin, identity })
    }
    fn hold(&self) -> Result<HeldFile> {
        let held = HeldFile::open(&self.pin, MAX_FILE)?;
        require(
            held.identity() == &self.identity,
            "original product inode changed",
        )?;
        Ok(held)
    }
    fn revalidate(&self) -> Result<()> {
        let file = files::open_regular(&self.pin.path)?;
        require(
            FileIdentity::read(file.metadata()?)? == self.identity,
            "original installed product was replaced or modified",
        )?;
        files::no_privilege_xattrs(&file)
    }
}
struct Directory {
    path: PathBuf,
    fd: File,
    identity: (u64, u64, u32, u32, u32),
}
impl Directory {
    fn open(path: &Path, private: bool) -> Result<Self> {
        let fd = if path == Path::new("/") {
            File::open("/")?
        } else {
            let (parent, name) = files::parent(path)?;
            let raw = unsafe {
                libc::openat(
                    parent.as_raw_fd(),
                    name.as_ptr(),
                    libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
                    0,
                )
            };
            if raw < 0 {
                return Err(std::io::Error::last_os_error().into());
            }
            unsafe { File::from_raw_fd(raw) }
        };
        let m = fd.metadata()?;
        require(
            m.is_dir()
                && m.uid() == 0
                && m.gid() == 0
                && m.mode() & 0o7022 == 0
                && (!private || m.mode() & 0o7777 == 0o700),
            "product directory is not protected root storage",
        )?;
        Ok(Self {
            path: path.into(),
            fd,
            identity: (m.dev(), m.ino(), m.mode(), m.uid(), m.gid()),
        })
    }
    fn revalidate(&self) -> Result<()> {
        let fresh = Self::open(&self.path, false)?;
        let m = self.fd.metadata()?;
        require(
            fresh.identity == self.identity
                && (m.dev(), m.ino(), m.mode(), m.uid(), m.gid()) == self.identity,
            "original product directory was renamed, replaced or changed",
        )
    }
}
/// These two project directories were installed as uid 1000 by the legacy
/// package. Keep their original descriptors and observations until the original
/// services are retired. The transaction changes only these directory owners;
/// it never recursively changes Android data or adopts a JSON authority.
struct LegacyDirectory {
    path: PathBuf,
    fd: File,
    original: Metadata,
}
impl LegacyDirectory {
    fn open(path: &Path) -> Result<Self> {
        require(
            LEGACY_DIRECTORIES.iter().any(|p| path == Path::new(p)),
            "directory is outside the fixed legacy project roots",
        )?;
        Directory::open(path.parent().ok_or("legacy root parent missing")?, false)?.revalidate()?;
        let (parent, name) = files::parent(path)?;
        let raw = unsafe {
            libc::openat(
                parent.as_raw_fd(),
                name.as_ptr(),
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                0,
            )
        };
        if raw < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let fd = unsafe { File::from_raw_fd(raw) };
        let original = fd.metadata()?;
        require(
            original.is_dir()
                && original.mode() & 0o7777 == 0o755
                && ((original.uid() == 0 && original.gid() == 0)
                    || (original.uid() == 1000 && original.gid() == 1000)),
            "fixed legacy directory owner or mode differs",
        )?;
        files::no_privilege_xattrs(&fd)?;
        let value = Self {
            path: path.into(),
            fd,
            original,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        let m = self.fd.metadata()?;
        let named = fs::symlink_metadata(&self.path)?;
        require(
            same_except_ctime(&self.original, &m)
                && same_except_ctime(&self.original, &named)
                && (m.ctime(), m.ctime_nsec(), named.ctime(), named.ctime_nsec())
                    == (
                        self.original.ctime(),
                        self.original.ctime_nsec(),
                        self.original.ctime(),
                        self.original.ctime_nsec(),
                    ),
            "original legacy directory changed before ownership transfer",
        )?;
        Directory::open(
            self.path.parent().ok_or("legacy root parent missing")?,
            false,
        )?
        .revalidate()?;
        files::no_privilege_xattrs(&self.fd)
    }
    fn receipt(&self) -> Value {
        json!({"path":self.path,"device":self.original.dev(),"inode":self.original.ino(),
            "uid":self.original.uid(),"gid":self.original.gid(),"mode":self.original.mode(),
            "ctime":[self.original.ctime(),self.original.ctime_nsec()]})
    }
    fn seal(&self, permit: &InstallationPermit) -> Result<Value> {
        permit.revalidate()?;
        self.revalidate()?;
        if self.original.uid() != 0 {
            if unsafe { libc::fchown(self.fd.as_raw_fd(), 0, 0) } != 0 {
                return Err(std::io::Error::last_os_error().into());
            }
            self.fd.sync_all()?;
            files::sync_parent(&self.path)?;
        }
        let after = self.fd.metadata()?;
        let actual = Directory::open(&self.path, false)?;
        require(
            after.dev() == self.original.dev()
                && after.ino() == self.original.ino()
                && after.mode() == self.original.mode()
                && after.nlink() == self.original.nlink()
                && after.len() == self.original.len()
                && after.mtime() == self.original.mtime()
                && after.mtime_nsec() == self.original.mtime_nsec()
                && after.uid() == 0
                && after.gid() == 0
                && actual.identity.0 == self.original.dev()
                && actual.identity.1 == self.original.ino(),
            "fixed directory changed beyond its explicit ownership transfer",
        )?;
        permit.revalidate()?;
        actual.revalidate()?;
        Ok(
            json!({"original":self.receipt(),"installed_uid":after.uid(),"installed_gid":after.gid(),
            "same_original_directory":true,"recursive_ownership_change":false}),
        )
    }
}
fn same_except_ctime(a: &Metadata, b: &Metadata) -> bool {
    a.dev() == b.dev()
        && a.ino() == b.ino()
        && a.mode() == b.mode()
        && a.uid() == b.uid()
        && a.gid() == b.gid()
        && a.nlink() == b.nlink()
        && a.len() == b.len()
        && a.mtime() == b.mtime()
        && a.mtime_nsec() == b.mtime_nsec()
}
fn temporary(dest: &Path) -> Result<PathBuf> {
    let parent = dest.parent().ok_or("installed file has no parent")?;
    let leaf = dest
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or("non-UTF8 installed file")?;
    require(
        !leaf.is_empty() && leaf.len() <= 180,
        "installed basename exceeds temporary bound",
    )?;
    for _ in 0..128 {
        let n = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        let path = parent.join(format!(
            ".droidloom-commit-{}-{n}-{leaf}",
            std::process::id()
        ));
        match fs::symlink_metadata(&path) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(path),
            Err(e) => return Err(e.into()),
            Ok(_) => (),
        }
    }
    Err("create-only product temporary namespace exhausted".into())
}
fn rename_flags(source: &Path, dest: &Path, flags: u32) -> Result<()> {
    let (sp, sn) = files::parent(source)?;
    let (dp, dn) = files::parent(dest)?;
    if unsafe {
        libc::renameat2(
            sp.as_raw_fd(),
            sn.as_ptr(),
            dp.as_raw_fd(),
            dn.as_ptr(),
            flags,
        )
    } != 0
    {
        return Err(std::io::Error::last_os_error().into());
    }
    files::sync_parent(source)?;
    files::sync_parent(dest)?;
    Ok(())
}
fn verify_published(source: &HeldFile, temp: &HeldFile, dest: &Path, mode: u32) -> Result<FilePin> {
    let before = temp.file().metadata()?;
    let actual = files::pin_file(dest)?;
    let opened = files::open_regular(dest)?;
    let m = opened.metadata()?;
    require(
        same_except_ctime(&before, &m)
            && actual.bytes == source.pin().bytes
            && actual.sha256 == source.pin().sha256
            && m.mode() & 0o7777 == mode,
        "atomically published product differs from its original copied inode or bytes",
    )?;
    source.revalidate()?;
    Ok(actual)
}
fn prepared_copy(
    source: &HeldFile,
    dest: &Path,
    mode: u32,
    labels: Option<&Labeler>,
) -> Result<(PathBuf, HeldFile)> {
    source.revalidate()?;
    let path = temporary(dest)?;
    let pin = source.copy_new(&path, mode)?;
    let file = files::open_regular(&path)?;
    if let Some(labels) = labels {
        labels.apply_file(&file, dest)?;
    }
    file.sync_all()?;
    let pin = FilePin {
        path: pin.path,
        bytes: pin.bytes,
        sha256: pin.sha256,
    };
    let held = HeldFile::open(&pin, MAX_FILE)?;
    require(
        held.identity().uid == unsafe { libc::geteuid() }
            && held.identity().gid == unsafe { libc::getegid() }
            && held.identity().mode & 0o7777 == mode,
        "new product lost writer custody",
    )?;
    files::no_privilege_xattrs(held.file())?;
    Ok((path, held))
}
/// Publication is create-only; labels are applied to the new original FD using
/// its final pathname before that inode becomes visible at the selected name.
pub(super) fn publish_new_file(
    source: &HeldFile,
    dest: &Path,
    mode: u32,
    labels: Option<&Labeler>,
) -> Result<FilePin> {
    let (temp, held) = prepared_copy(source, dest, mode, labels)?;
    held.revalidate()?;
    source.revalidate()?;
    rename_flags(&temp, dest, libc::RENAME_NOREPLACE)?;
    verify_published(source, &held, dest, mode)
}
/// Preserve the old ordinary bytes in a create-only backup before an atomic
/// exchange. An unexpected exchanged inode is preserved and fails the caller;
/// it is never silently unlinked or adopted as the original installed file.
pub(super) fn replace_file(
    source: &HeldFile,
    dest: &Path,
    backup: &Path,
    mode: u32,
    labels: Option<&Labeler>,
) -> Result<FilePin> {
    let old_pin = files::pin_file(dest)?;
    let old = HeldFile::open(&old_pin, MAX_FILE)?;
    require(
        (old.identity().uid == unsafe { libc::geteuid() }
            && old.identity().gid == unsafe { libc::getegid() })
            || (unsafe { libc::geteuid() } == 0 && legacy_executable(dest, old.identity())),
        "replacement target is outside this original writer's custody",
    )?;
    files::no_privilege_xattrs(old.file())?;
    require(
        (old.identity().device, old.identity().inode)
            != (source.identity().device, source.identity().inode),
        "replacement source aliases its live destination",
    )?;
    old.copy_new(backup, old.identity().mode & 0o777)?;
    files::sync_parent(backup)?;
    let (temp, new) = prepared_copy(source, dest, mode, labels)?;
    let original = old.file().metadata()?;
    old.revalidate()?;
    new.revalidate()?;
    source.revalidate()?;
    rename_flags(&temp, dest, libc::RENAME_EXCHANGE)?;
    let exchanged = files::open_regular(&temp)?;
    require(
        same_except_ctime(&original, &exchanged.metadata()?)
            && same_except_ctime(&original, &old.file().metadata()?)
            && files::hash_file(&exchanged, old.pin().bytes)? == old.pin().sha256,
        "atomic exchange observed an unexpected original target; preserve both products",
    )?;
    let actual = verify_published(source, &new, dest, mode)?;
    let (dp, dn) = files::parent(&temp)?;
    require(
        same_except_ctime(&original, &files::open_regular(&temp)?.metadata()?),
        "exchanged original changed before its exact-name removal",
    )?;
    if unsafe { libc::unlinkat(dp.as_raw_fd(), dn.as_ptr(), 0) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    files::sync_parent(&temp)?;
    Ok(actual)
}
#[derive(Clone)]
struct Link {
    path: PathBuf,
    target: PathBuf,
    identity: (u64, u64, u32, u32, u32, u64, i64, i64),
}
impl Link {
    fn read(path: &Path, target: &Path) -> Result<Self> {
        let (_, _) = files::parent(path)?;
        let m = fs::symlink_metadata(path)?;
        require(
            m.file_type().is_symlink()
                && m.uid() == 0
                && m.gid() == 0
                && m.nlink() == 1
                && fs::read_link(path)? == target,
            "fixed native link differs or escaped root custody",
        )?;
        Ok(Self {
            path: path.into(),
            target: target.into(),
            identity: (
                m.dev(),
                m.ino(),
                m.mode(),
                m.uid(),
                m.gid(),
                m.nlink(),
                m.ctime(),
                m.ctime_nsec(),
            ),
        })
    }
    fn revalidate(&self) -> Result<()> {
        require(
            Self::read(&self.path, &self.target)?.identity == self.identity,
            "original fixed native link changed",
        )
    }
}
fn unit_mask(path: &Path) -> bool {
    activation_android::UNITS
        .iter()
        .any(|n| path == Path::new("/etc/systemd/system").join(n))
}
fn replace_mask(source: &HeldFile, dest: &Path, backup: &Path, mask: &Link) -> Result<FilePin> {
    require(
        unit_mask(dest) && mask.path == dest && mask.target == Path::new("/dev/null"),
        "only the fixed original root-owned unit mask may be replaced",
    )?;
    mask.revalidate()?;
    std::os::unix::fs::symlink("/dev/null", backup)?;
    files::sync_parent(backup)?;
    let (temp, new) = prepared_copy(source, dest, 0o644, None)?;
    let original = fs::symlink_metadata(dest)?;
    mask.revalidate()?;
    new.revalidate()?;
    rename_flags(&temp, dest, libc::RENAME_EXCHANGE)?;
    let m = fs::symlink_metadata(&temp)?;
    require(
        same_except_ctime(&original, &m) && fs::read_link(&temp)? == Path::new("/dev/null"),
        "exchanged mask was not the original fixed mask; preserve it",
    )?;
    let actual = verify_published(source, &new, dest, 0o644)?;
    let (parent, name) = files::parent(&temp)?;
    require(
        same_except_ctime(&original, &fs::symlink_metadata(&temp)?),
        "original mask changed before removal",
    )?;
    if unsafe { libc::unlinkat(parent.as_raw_fd(), name.as_ptr(), 0) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    files::sync_parent(&temp)?;
    Ok(actual)
}
enum Original {
    Absent,
    Ordinary(ObservedFile),
    Mask(Link),
}
impl Original {
    fn revalidate(&self, path: &Path) -> Result<()> {
        match self {
            Self::Absent => match fs::symlink_metadata(path) {
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
                Err(e) => Err(e.into()),
                Ok(_) => Err("a previously absent product appeared".into()),
            },
            Self::Ordinary(f) => f.revalidate(),
            Self::Mask(link) => link.revalidate(),
        }
    }
    fn receipt(&self) -> Value {
        match self {
            Self::Absent => json!({"kind":"absent"}),
            Self::Ordinary(f) => json!({"kind":"ordinary","pin":f.pin,"identity":f.identity}),
            Self::Mask(l) => json!({"kind":"original_fixed_mask","path":l.path,"target":l.target,
                "device":l.identity.0,"inode":l.identity.1}),
        }
    }
}
struct Product {
    relative: String,
    source: ObservedFile,
    mode: u32,
    replace: bool,
}
fn add_product(
    products: &mut BTreeMap<String, Product>,
    root: &Path,
    name: &str,
    bytes: u64,
    sha256: &str,
    mode: u32,
    replace: bool,
) -> Result<()> {
    relative(name)?;
    require(
        !CONFIGURATION.contains(&name)
            && bytes > 0
            && bytes <= MAX_FILE
            && files::valid_digest(sha256)
            && [0o400, 0o444, 0o644, 0o755].contains(&mode),
        "product has a configuration path, invalid bytes or unsupported mode",
    )?;
    let source = ObservedFile::from_pin(
        FilePin {
            path: root.join(name),
            bytes,
            sha256: sha256.into(),
        },
        mode,
    )?;
    require(
        products
            .insert(
                name.into(),
                Product {
                    relative: name.into(),
                    source,
                    mode,
                    replace,
                },
            )
            .is_none(),
        "fixed installed products overlap",
    )?;
    Ok(())
}
fn parent_custody(path: &Path) -> Result<Vec<Value>> {
    let mut current = PathBuf::from("/");
    let mut result = Vec::new();
    let parent = path.parent().ok_or("product lacks a parent")?;
    let mut missing = false;
    for part in parent.components().skip(1) {
        current.push(part.as_os_str());
        if missing {
            continue;
        }
        match fs::symlink_metadata(&current) {
            Ok(_) => {
                if LEGACY_DIRECTORIES.iter().any(|p| current == Path::new(p)) {
                    let legacy = LegacyDirectory::open(&current)?;
                    result.push(json!({"fixed_legacy_directory":legacy.receipt(),"transfer_required":legacy.original.uid()!=0}));
                } else {
                    let dir = Directory::open(&current, false)?;
                    result.push(
                        json!({"path":current,"device":dir.identity.0,"inode":dir.identity.1,
                        "mode":dir.identity.2}),
                    );
                }
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => missing = true,
            Err(e) => return Err(e.into()),
        }
    }
    Ok(result)
}
fn fixed_module_tree(root: &Path, expected: &BTreeSet<String>) -> Result<()> {
    let mut pending = vec![root.to_owned()];
    let mut found = BTreeSet::new();
    while let Some(directory) = pending.pop() {
        Directory::open(&directory, false)?.revalidate()?;
        for entry in fs::read_dir(&directory)? {
            let path = entry?.path();
            let m = fs::symlink_metadata(&path)?;
            let name = path
                .strip_prefix(Path::new("/"))?
                .to_str()
                .ok_or("non-UTF8 module path")?
                .to_owned();
            require(
                m.uid() == 0 && m.gid() == 0,
                "installed module is not root-owned",
            )?;
            if m.is_dir() {
                require(
                    m.mode() & 0o7777 == 0o755
                        && expected
                            .iter()
                            .any(|n| n.starts_with(&(name.clone() + "/"))),
                    "installed module namespace has an extra or foreign directory",
                )?;
                pending.push(path);
            } else {
                require(
                    m.is_file()
                        && m.nlink() == 1
                        && m.mode() & 0o7777 == 0o644
                        && found.insert(name),
                    "installed module namespace contains an alias or special object",
                )?;
            }
            require(
                found.len() + pending.len() <= 9000,
                "installed module namespace exceeds its bound",
            )?;
        }
    }
    require(
        &found == expected,
        "complete installed kernel module namespace differs",
    )
}
fn new_area(work: &Directory, prefix: &str) -> Result<PathBuf> {
    work.revalidate()?;
    for i in 0..4096 {
        let path = work.path.join(format!("{prefix}-{i:04}"));
        let (parent, name) = files::parent(&path)?;
        if unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) } == 0 {
            Directory::open(&path, true)?.revalidate()?;
            files::sync_parent(&path)?;
            return Ok(path);
        }
        let e = std::io::Error::last_os_error();
        if e.raw_os_error() != Some(libc::EEXIST) {
            return Err(e.into());
        }
        Directory::open(&path, true)?.revalidate()?;
    }
    Err("fixed product operation directory budget exhausted".into())
}
struct OwnedCommand {
    child: Child,
    pidfd: File,
    reaped: bool,
}
impl OwnedCommand {
    fn exited(&self) -> Result<Option<bool>> {
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        if unsafe {
            libc::waitid(
                libc::P_PIDFD,
                self.pidfd.as_raw_fd() as u32,
                &mut info,
                libc::WEXITED | libc::WNOHANG | libc::WNOWAIT,
            )
        } != 0
        {
            return Err(std::io::Error::last_os_error().into());
        }
        if unsafe { info.si_pid() } == 0 {
            return Ok(None);
        }
        Ok(Some(
            info.si_code == libc::CLD_EXITED && unsafe { info.si_status() } == 0,
        ))
    }
    fn retire(&mut self) -> Result<()> {
        if self.reaped {
            return Ok(());
        }
        let pid = i32::try_from(self.child.id())?;
        if unsafe { libc::kill(-pid, libc::SIGKILL) } != 0
            && std::io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
        {
            return Err(std::io::Error::last_os_error().into());
        }
        self.child.wait()?;
        self.reaped = true;
        Ok(())
    }
}
impl Drop for OwnedCommand {
    fn drop(&mut self) {
        if !self.reaped {
            let _ = unsafe {
                libc::syscall(
                    libc::SYS_pidfd_send_signal,
                    self.pidfd.as_raw_fd(),
                    libc::SIGKILL,
                    std::ptr::null::<libc::siginfo_t>(),
                    0,
                )
            };
            let _ = self.retire();
        }
    }
}
enum NativeAction {
    Reload,
    Enable,
    Enabled,
}
fn systemctl(area: &Path, action: NativeAction, permit: &InstallationPermit) -> Result<Value> {
    permit.revalidate()?;
    let path = Path::new("/usr/bin/systemctl");
    let tool = ObservedFile::capture(path)?.hold()?;
    let header = tool.read_all(32 * MIB)?;
    require(
        header.starts_with(b"\x7fELF") && tool.identity().mode & 0o111 != 0,
        "normal systemctl is not a protected native executable",
    )?;
    let (name, verb) = match action {
        NativeAction::Reload => ("daemon-reload", "daemon-reload"),
        NativeAction::Enable => ("enable", "enable"),
        NativeAction::Enabled => ("is-enabled", "is-enabled"),
    };
    let mut args = vec!["--system", "--no-pager", "--no-ask-password", verb];
    if !matches!(action, NativeAction::Reload) {
        args.extend(activation_android::ENABLED);
    }
    let out_path = area.join(format!("{name}.stdout"));
    let err_path = area.join(format!("{name}.stderr"));
    let out = files::new_file(&out_path, 0o600)?;
    let err = files::new_file(&err_path, 0o600)?;
    let mut command = Command::new(format!("/proc/self/fd/{}", tool.file().as_raw_fd()));
    command
        .args(&args)
        .arg0("systemctl")
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LC_ALL", "C")
        .env("LANG", "C")
        .current_dir("/")
        .stdin(Stdio::null())
        .stdout(out.try_clone()?)
        .stderr(err.try_clone()?);
    unsafe {
        command.pre_exec(|| {
            if libc::setsid() < 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    tool.revalidate()?;
    permit.revalidate()?;
    let mut child = command.spawn()?;
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
    if raw < 0 {
        let e = std::io::Error::last_os_error();
        let _ = unsafe { libc::kill(-(child.id() as i32), libc::SIGKILL) };
        let _ = child.wait();
        return Err(e.into());
    }
    let mut owned = OwnedCommand {
        child,
        pidfd: unsafe { File::from_raw_fd(raw as i32) },
        reaped: false,
    };
    let start = Instant::now();
    let deadline = start + Duration::from_secs(120);
    let mut next = start;
    loop {
        require(
            Instant::now() < deadline,
            "normal service command exceeded its deadline",
        )?;
        require(
            out.metadata()?.len() <= MIB && err.metadata()?.len() <= MIB,
            "normal service command exceeded its output bound",
        )?;
        if Instant::now() >= next {
            permit.revalidate()?;
            tool.revalidate()?;
            next = Instant::now() + Duration::from_millis(250);
        }
        if let Some(success) = owned.exited()? {
            require(
                Instant::now() < deadline,
                "normal service command completed after its deadline",
            )?;
            owned.retire()?;
            out.sync_all()?;
            err.sync_all()?;
            permit.revalidate()?;
            tool.revalidate()?;
            require(
                success,
                &format!("normal systemctl {name} failed; see {}", err_path.display()),
            )?;
            let stdout = files::pin_file(&out_path)?;
            let stderr = files::pin_file(&err_path)?;
            require(
                stdout.bytes <= MIB && stderr.bytes <= MIB && Instant::now() < deadline,
                "normal service command final observation exceeded its bound",
            )?;
            if matches!(action, NativeAction::Enabled) {
                require(
                    HeldFile::open(&stdout, MIB)?.read_all(MIB)? == b"enabled\nenabled\n",
                    "the two fixed production services are not normally enabled",
                )?;
            }
            return Ok(
                json!({"executable":tool.pin(),"arguments":args,"stdout":stdout,
                "stderr":stderr,"exit_code":0,"elapsed_millis":start.elapsed().as_millis()}),
            );
        }
        std::thread::sleep(Duration::from_millis(20));
    }
}
pub(super) struct ProductInstaller {
    root: Directory,
    work: Directory,
    generation: Directory,
    products: BTreeMap<String, Product>,
    modules: BTreeSet<String>,
    module_root: PathBuf,
    kernel_paths: BTreeSet<PathBuf>,
    originals: RefCell<Option<BTreeMap<String, Original>>>,
    legacy_directories: RefCell<Option<Vec<LegacyDirectory>>>,
    attempted: Cell<bool>,
    completed: Cell<bool>,
}
impl ProductInstaller {
    pub(super) fn from_stage(
        root: &Path,
        work: &Path,
        host: &HostManifest,
        android: &AndroidInputs,
        platform: &PlatformInputs,
        receipt: &Value,
    ) -> Result<Self> {
        require(
            unsafe { libc::geteuid() } == 0
                && root.file_name().is_some_and(|v| v == "root")
                && work.file_name().is_some_and(|v| v == "work")
                && root.parent() == work.parent(),
            "product installer requires original root/work siblings",
        )?;
        let parent = root.parent().ok_or("product stage has no generation")?;
        require(
            parent.parent() == Some(Path::new(STAGING))
                && parent
                    .file_name()
                    .and_then(|v| v.to_str())
                    .is_some_and(files::valid_digest)
                && receipt["schema"] == "droidloom.pocket4-platform-staged.v1",
            "product stage generation or fixed platform schema differs",
        )?;
        let generation = Directory::open(parent, true)?;
        let root_guard = Directory::open(root, true)?;
        let work_guard = Directory::open(work, true)?;
        activation_host::validate_manifest(host)?;
        let mut products = BTreeMap::new();
        for row in &host.files {
            add_product(
                &mut products,
                root,
                &row.path,
                row.size,
                &row.sha256,
                row.mode,
                true,
            )?;
        }
        for name in activation_android::install_paths(android)? {
            if CONFIGURATION.contains(&name.as_str()) {
                continue;
            }
            let pin = files::pin_file(&root.join(&name))?;
            let mode = files::open_regular(&pin.path)?.metadata()?.mode() & 0o7777;
            let replace = name.starts_with("etc/droidloom/host-mac/")
                || name.starts_with("etc/systemd/system/");
            if name.starts_with("etc/droidloom/host-mac/") {
                require(mode == 0o400, "host MAC input mode differs")?;
            }
            if name.starts_with("etc/systemd/system/") {
                require(mode == 0o644, "ordinary native unit mode differs")?;
            }
            add_product(
                &mut products,
                root,
                &name,
                pin.bytes,
                &pin.sha256,
                mode,
                replace,
            )?;
        }
        let board: Value = serde_json::from_str(BOARD)?;
        let release = board["kernel"]["release"]
            .as_str()
            .ok_or("compiled kernel release missing")?;
        require(
            receipt["kernel"]["release"] == release
                && board["kernel"]["sha256"] == platform.kernel.image.sha256,
            "installed kernel generation differs from the compiled board",
        )?;
        let members = activation_platform::installation_module_members(&platform.kernel)?;
        let modules: BTreeSet<String> = members.keys().cloned().collect();
        require(
            modules.len() == 6813,
            "complete installed kernel member count differs",
        )?;
        for (name, (bytes, sha)) in members {
            add_product(&mut products, root, &name, bytes, &sha, 0o644, false)?;
        }
        let config_name = format!("usr/lib/modules/{release}/config-{release}");
        let config = products
            .get(&config_name)
            .ok_or("kernel source configuration missing")?
            .source
            .pin
            .clone();
        let boot = [
            (
                format!("boot/vmlinuz-{release}"),
                platform.kernel.image.bytes,
                platform.kernel.image.sha256.clone(),
            ),
            (
                format!("boot/initrd.img-{release}"),
                platform.initrd.image.bytes,
                platform.initrd.image.sha256.clone(),
            ),
            (
                format!("boot/config-{release}"),
                config.bytes,
                config.sha256,
            ),
        ];
        let mut kernel_paths = BTreeSet::new();
        for (name, bytes, sha) in boot {
            kernel_paths.insert(Path::new("/").join(&name));
            add_product(&mut products, root, &name, bytes, &sha, 0o644, false)?;
        }
        let native = receipt["native_packages"]
            .as_array()
            .ok_or("native payload receipt missing")?;
        require(native.len() == 2, "fixed native package set differs")?;
        for row in native {
            for pin in row["payload"]
                .as_array()
                .ok_or("native payload list missing")?
            {
                let path =
                    PathBuf::from(pin["path"].as_str().ok_or("native payload path missing")?);
                let name = path
                    .strip_prefix(root)?
                    .to_str()
                    .ok_or("non-UTF8 native payload")?;
                require(
                    !products.contains_key(name),
                    "normal dpkg payload overlaps an ordinary product",
                )?;
            }
        }
        require(
            !products.contains_key("usr/lib/x86_64-linux-gnu/libapparmor.so.1"),
            "normal dpkg SONAME alias cannot be an ordinary product",
        )?;
        let total = products.values().try_fold(0u64, |sum, p| {
            sum.checked_add(p.source.pin.bytes)
                .ok_or("product size overflow")
        })?;
        require(
            products.len() < 7500 && total <= 64 * 1024 * MIB,
            "fixed product inventory exceeds its complete release bound",
        )?;
        let result = Self {
            root: root_guard,
            work: work_guard,
            generation,
            products,
            modules,
            module_root: Path::new("/usr/lib/modules").join(release),
            kernel_paths,
            originals: RefCell::new(None),
            legacy_directories: RefCell::new(None),
            attempted: Cell::new(false),
            completed: Cell::new(false),
        };
        result.revalidate_stage()?;
        Ok(result)
    }
    fn revalidate_stage(&self) -> Result<()> {
        self.root.revalidate()?;
        self.work.revalidate()?;
        self.generation.revalidate()?;
        for product in self.products.values() {
            product.source.revalidate()?;
        }
        Ok(())
    }
    pub(super) fn preflight(&self) -> Result<Value> {
        require(
            !self.attempted.get(),
            "ordinary product installation already attempted",
        )?;
        self.revalidate_stage()?;
        let mut must_absent = self.kernel_paths.clone();
        must_absent.insert(self.module_root.clone());
        for path in &must_absent {
            Original::Absent.revalidate(path)?;
        }
        let mut legacy_directories = Vec::new();
        for path in LEGACY_DIRECTORIES {
            match fs::symlink_metadata(path) {
                Ok(_) => legacy_directories.push(LegacyDirectory::open(Path::new(path))?),
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
                Err(e) => return Err(e.into()),
            }
        }
        let mut originals = BTreeMap::new();
        let mut parents = BTreeMap::new();
        let mut rows = Vec::new();
        for (name, product) in &self.products {
            let dest = Path::new("/").join(name);
            if let Some(p) = dest.parent() {
                if !parents.contains_key(p) {
                    parents.insert(p.to_owned(), parent_custody(&dest)?);
                }
            }
            let original = match fs::symlink_metadata(&dest) {
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => Original::Absent,
                Err(e) => return Err(e.into()),
                Ok(m) if m.is_file() => {
                    let old = ObservedFile::capture_original_product(&dest)?;
                    if !product.replace {
                        require(
                            old.pin.bytes == product.source.pin.bytes
                                && old.pin.sha256 == product.source.pin.sha256
                                && old.identity.mode & 0o7777 == product.mode,
                            "immutable selected Android material already exists with different bytes or mode",
                        )?;
                    }
                    Original::Ordinary(old)
                }
                Ok(m) if m.file_type().is_symlink() && unit_mask(&dest) => {
                    Original::Mask(Link::read(&dest, Path::new("/dev/null"))?)
                }
                Ok(_) => {
                    return Err(format!(
                        "unsupported existing installed product: {}",
                        dest.display()
                    )
                    .into());
                }
            };
            rows.push(json!({"path":dest,"original":original.receipt()}));
            originals.insert(name.clone(), original);
        }
        for state in STATE {
            let path = Path::new("/").join(state);
            parent_custody(&path)?;
            match fs::symlink_metadata(&path) {
                Ok(_) => {
                    Directory::open(&path, true)?.revalidate()?;
                }
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
                Err(e) => return Err(e.into()),
            }
        }
        for name in activation_android::ENABLED {
            let path = Path::new("/etc/systemd/system/multi-user.target.wants").join(name);
            parent_custody(&path)?;
            match fs::symlink_metadata(&path) {
                Ok(_) => {
                    Link::read(&path, &Path::new("/etc/systemd/system").join(name))?
                        .revalidate()?;
                }
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
                Err(e) => return Err(e.into()),
            }
        }
        let tool = ObservedFile::capture(Path::new("/usr/bin/systemctl"))?;
        require(
            tool.identity.mode & 0o111 != 0,
            "normal systemctl is not executable",
        )?;
        self.revalidate_stage()?;
        let result = json!({"schema":"droidloom.ordinary-product-preflight.v1","originals":rows,
            "protected_existing_parents":parents,"new_kernel_targets_absent":must_absent,
            "complete_module_files":self.modules.len(),"normal_systemctl":tool.pin,
            "services_to_enable":activation_android::ENABLED,"start_requested":false,
            "live_system_modified":false,"installation_authority_issued":false});
        for directory in &legacy_directories {
            directory.revalidate()?;
        }
        *self.legacy_directories.borrow_mut() = Some(legacy_directories);
        *self.originals.borrow_mut() = Some(originals);
        Ok(result)
    }
    pub(super) fn install(&self, permit: &InstallationPermit) -> Result<Value> {
        require(
            self.generation.path.file_name().and_then(|n| n.to_str()) == Some(permit.plan()),
            "installation permit belongs to another original stage generation",
        )?;
        require(
            !self.attempted.replace(true),
            "ordinary product installation cannot be replayed",
        )?;
        permit.revalidate()?;
        self.revalidate_stage()?;
        let originals = self.originals.borrow();
        let originals = originals
            .as_ref()
            .ok_or("ordinary products have no actual preflight")?;
        for (name, old) in originals {
            old.revalidate(&Path::new("/").join(name))?;
        }
        Original::Absent.revalidate(&self.module_root)?;
        for path in &self.kernel_paths {
            Original::Absent.revalidate(path)?;
        }
        let area = new_area(&self.work, "product-install")?;
        let backups = area.join("originals");
        files::private_dir(&backups)?;
        let legacy_directories = self.legacy_directories.borrow();
        let legacy_directories = legacy_directories
            .as_ref()
            .ok_or("legacy directory observations missing")?;
        for directory in legacy_directories {
            directory.revalidate()?;
        }
        let mut directory_transfers = Vec::new();
        for directory in legacy_directories {
            directory_transfers.push(directory.seal(permit)?);
        }
        let mut installed = Vec::new();
        let mut next = Instant::now();
        for (name, product) in &self.products {
            if Instant::now() >= next {
                permit.revalidate()?;
                next = Instant::now() + Duration::from_millis(250);
            }
            let dest = Path::new("/").join(name);
            let old = originals
                .get(name)
                .ok_or("original product observation omitted")?;
            old.revalidate(&dest)?;
            let source = product.source.hold()?;
            let parent = Path::new(name)
                .parent()
                .and_then(Path::to_str)
                .ok_or("product parent missing")?;
            files::ensure_dir(Path::new("/"), parent)?;
            let actual = match old {
                Original::Absent => publish_new_file(&source, &dest, product.mode, None)?,
                Original::Ordinary(previous) if !product.replace => {
                    previous.revalidate()?;
                    previous.pin.clone()
                }
                Original::Ordinary(_) => {
                    files::ensure_dir(&backups, parent)?;
                    replace_file(&source, &dest, &backups.join(name), product.mode, None)?
                }
                Original::Mask(mask) => {
                    files::ensure_dir(&backups, parent)?;
                    replace_mask(&source, &dest, &backups.join(name), mask)?
                }
            };
            require(
                actual.bytes == source.pin().bytes && actual.sha256 == source.pin().sha256,
                "ordinary installed file differs from its complete selected bytes",
            )?;
            installed.push(actual);
        }
        for state in STATE {
            let path = Path::new("/").join(state);
            let parent = Path::new(state)
                .parent()
                .and_then(Path::to_str)
                .ok_or("state parent missing")?;
            files::ensure_dir(Path::new("/"), parent)?;
            match fs::symlink_metadata(&path) {
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => files::private_dir(&path)?,
                Err(e) => return Err(e.into()),
                Ok(_) => (),
            }
            Directory::open(&path, true)?.revalidate()?;
        }
        permit.revalidate()?;
        fixed_module_tree(&self.module_root, &self.modules)?;
        let reload = systemctl(&area, NativeAction::Reload, permit)?;
        let enable = systemctl(&area, NativeAction::Enable, permit)?;
        let enabled = systemctl(&area, NativeAction::Enabled, permit)?;
        self.revalidate_stage()?;
        permit.revalidate()?;
        self.completed.set(true);
        Ok(
            json!({"schema":"droidloom.ordinary-products-installed.v1","files":installed,
            "original_backups":backups,"fixed_directory_transfers":directory_transfers,"complete_module_files":self.modules.len(),
            "normal_daemon_reload":reload,"normal_enable":enable,"normal_enabled_readback":enabled,
            "services_started":false,"final_readback_required":true,"production_ready":false}),
        )
    }
    pub(super) fn observe_installed(
        &self,
        permit: &InstallationPermit,
    ) -> Result<InstalledProducts> {
        require(
            self.generation.path.file_name().and_then(|n| n.to_str()) == Some(permit.plan()),
            "installed observation crossed the original stage generation",
        )?;
        require(
            self.completed.get(),
            "ordinary normal installation did not complete",
        )?;
        permit.revalidate()?;
        self.revalidate_stage()?;
        let mut installed = Vec::new();
        let mut rows = Vec::new();
        let mut next = Instant::now();
        for product in self.products.values() {
            if Instant::now() >= next {
                permit.revalidate()?;
                next = Instant::now() + Duration::from_millis(250);
            }
            let source = &product.source.pin;
            let actual = ObservedFile::from_pin(
                FilePin {
                    path: Path::new("/").join(&product.relative),
                    bytes: source.bytes,
                    sha256: source.sha256.clone(),
                },
                product.mode,
            )?;
            rows.push(json!({"pin":actual.pin,"identity":actual.identity}));
            installed.push(actual);
        }
        fixed_module_tree(&self.module_root, &self.modules)?;
        let mut state = Vec::new();
        for path in STATE {
            state.push(Directory::open(&Path::new("/").join(path), true)?);
        }
        for path in LEGACY_DIRECTORIES {
            state.push(Directory::open(Path::new(path), false)?);
        }
        let mut links = Vec::new();
        for name in activation_android::ENABLED {
            links.push(Link::read(
                &Path::new("/etc/systemd/system/multi-user.target.wants").join(name),
                &Path::new("/etc/systemd/system").join(name),
            )?);
        }
        let area = new_area(&self.work, "product-readback")?;
        let enabled = systemctl(&area, NativeAction::Enabled, permit)?;
        permit.revalidate()?;
        self.revalidate_stage()?;
        let receipt = json!({"schema":"droidloom.ordinary-products-observed.v1","files":rows,
            "complete_module_files":self.modules.len(),"all_installed_bytes_verified":true,
            "original_final_inodes_observed":true,"normal_enabled_readback":enabled,
            "labels_applied_before_observation":true,"runtime_qualified":false,"production_ready":false});
        let result = InstalledProducts {
            installed,
            state,
            links,
            module_root: Directory::open(&self.module_root, false)?,
            modules: self.modules.clone(),
            receipt,
        };
        result.revalidate()?;
        Ok(result)
    }
}
pub(super) struct InstalledProducts {
    installed: Vec<ObservedFile>,
    state: Vec<Directory>,
    links: Vec<Link>,
    module_root: Directory,
    modules: BTreeSet<String>,
    receipt: Value,
}
impl InstalledProducts {
    pub(super) fn revalidate(&self) -> Result<()> {
        for f in &self.installed {
            f.revalidate()?;
        }
        for d in &self.state {
            d.revalidate()?;
        }
        for l in &self.links {
            l.revalidate()?;
        }
        self.module_root.revalidate()?;
        fixed_module_tree(&self.module_root.path, &self.modules)
    }
    pub(super) fn receipt(&self) -> Value {
        self.receipt.clone()
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn legacy_owner_exception_is_exactly_the_five_executable_paths() {
        let mut id = FileIdentity {
            device: 1,
            inode: 2,
            mode: 0o100755,
            uid: 1000,
            gid: 1000,
            links: 1,
            bytes: 3,
            modified_sec: 4,
            modified_nsec: 5,
            changed_sec: 6,
            changed_nsec: 7,
        };
        assert!(legacy_executable(Path::new("/usr/bin/droidloomctl"), &id));
        assert!(!legacy_executable(Path::new("/usr/bin/other"), &id));
        assert!(!legacy_executable(
            Path::new("/usr/bin/../bin/droidloomctl"),
            &id
        ));
        assert!(!legacy_executable(
            Path::new("/etc/droidloom/cell.json"),
            &id
        ));
        id.uid = 1001;
        assert!(!legacy_executable(Path::new("/usr/bin/droidloomctl"), &id));
        id.uid = 1000;
        id.mode = 0o100775;
        assert!(!legacy_executable(Path::new("/usr/bin/droidloomctl"), &id));
        id.mode = 0o100755;
        id.links = 2;
        assert!(!legacy_executable(Path::new("/usr/bin/droidloomctl"), &id));
    }
    #[test]
    fn atomic_replacement_preserves_old_bytes_and_publishes_new_inode() {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("source");
        let dest = dir.path().join("installed");
        let backup = dir.path().join("original");
        fs::write(&source, b"final source bytes").unwrap();
        fs::write(&dest, b"old bytes").unwrap();
        let pin = files::pin_file(&source).unwrap();
        let input = HeldFile::open(&pin, 1024).unwrap();
        let old_ino = fs::metadata(&dest).unwrap().ino();
        let actual = replace_file(&input, &dest, &backup, 0o644, None).unwrap();
        assert_eq!(fs::read(&backup).unwrap(), b"old bytes");
        assert_eq!(fs::read(&dest).unwrap(), b"final source bytes");
        assert_eq!(actual.sha256, pin.sha256);
        assert_ne!(fs::metadata(&dest).unwrap().ino(), old_ino);
        input.revalidate().unwrap();
        assert!(replace_file(&input, &dest, &backup, 0o644, None).is_err());
        assert_eq!(fs::read(&dest).unwrap(), b"final source bytes");
    }
    #[test]
    fn create_only_publication_refuses_a_late_destination_without_overwriting_it() {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("source");
        let dest = dir.path().join("new");
        fs::write(&source, b"new").unwrap();
        let input = HeldFile::open(&files::pin_file(&source).unwrap(), 64).unwrap();
        publish_new_file(&input, &dest, 0o644, None).unwrap();
        fs::write(&dest, b"do not overwrite").unwrap();
        assert!(publish_new_file(&input, &dest, 0o644, None).is_err());
        assert_eq!(fs::read(&dest).unwrap(), b"do not overwrite");
    }
    #[test]
    fn replacement_refuses_symlinks_hardlinks_and_source_aliases() {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("source");
        fs::write(&source, b"source").unwrap();
        let input = HeldFile::open(&files::pin_file(&source).unwrap(), 64).unwrap();
        let alias = dir.path().join("alias");
        std::os::unix::fs::symlink(&source, &alias).unwrap();
        assert!(replace_file(&input, &alias, &dir.path().join("b1"), 0o644, None).is_err());
        assert!(replace_file(&input, &source, &dir.path().join("b2"), 0o644, None).is_err());
        let linked = dir.path().join("linked");
        fs::hard_link(&source, &linked).unwrap();
        assert!(replace_file(&input, &linked, &dir.path().join("b3"), 0o644, None).is_err());
        assert_eq!(fs::read(&source).unwrap(), b"source");
    }
}
