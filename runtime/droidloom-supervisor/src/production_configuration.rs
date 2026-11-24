//! One setup lock for package writers and production activation readers.
//!
//! A directory lock is only a cooperative filesystem lock. The fixed guards
//! additionally hold and revalidate the real configuration parent chain.
//! Neither guard proves resource retirement or authorizes package replacement.
use sha2::{Digest, Sha256};
use std::ffi::CStr;
use std::fs::{File, Metadata};
use std::io::{self, Write};
use std::os::fd::{AsFd, AsRawFd, BorrowedFd, FromRawFd};
use std::os::unix::fs::FileExt;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};

const LOCK: &CStr = c"setup.lock";
const MAINTENANCE: &CStr = c"package-maintenance.json";

fn rejected(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, message)
}

#[derive(Clone, Copy)]
struct Custody {
    uid: u32,
    gid: u32,
}

const ROOT: Custody = Custody { uid: 0, gid: 0 };

#[derive(Clone, Debug, Eq, PartialEq)]
struct DirectoryIdentity {
    device: u64,
    inode: u64,
    mode: u32,
    uid: u32,
    gid: u32,
}

impl DirectoryIdentity {
    fn read(file: &File, custody: Custody) -> io::Result<Self> {
        let metadata = file.metadata()?;
        if !metadata.is_dir()
            || metadata.uid() != custody.uid
            || metadata.gid() != custody.gid
            || metadata.mode() & 0o022 != 0
        {
            return Err(rejected("unsafe configuration lock parent"));
        }
        // Directory contents legitimately change while the exclusive owner
        // writes configuration; its inode, custody and permissions must not.
        Ok(Self {
            device: metadata.dev(),
            inode: metadata.ino(),
            mode: metadata.mode(),
            uid: metadata.uid(),
            gid: metadata.gid(),
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct LockIdentity {
    device: u64,
    inode: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    modified: (i64, i64),
    changed: (i64, i64),
}

impl LockIdentity {
    fn read(metadata: Metadata, custody: Custody) -> io::Result<Self> {
        if !metadata.is_file()
            || metadata.uid() != custody.uid
            || metadata.gid() != custody.gid
            || metadata.nlink() != 1
            || metadata.mode() & 0o7022 != 0
        {
            return Err(rejected("unsafe configuration setup.lock"));
        }
        Ok(Self {
            device: metadata.dev(),
            inode: metadata.ino(),
            mode: metadata.mode(),
            uid: metadata.uid(),
            gid: metadata.gid(),
            links: metadata.nlink(),
            bytes: metadata.len(),
            modified: (metadata.mtime(), metadata.mtime_nsec()),
            changed: (metadata.ctime(), metadata.ctime_nsec()),
        })
    }
}

#[derive(Clone, Copy)]
enum Access {
    InspectExisting,
    Shared,
    Exclusive,
}

fn open_at(parent: &File, name: &CStr, flags: i32, mode: libc::mode_t) -> io::Result<File> {
    let descriptor = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            mode,
        )
    };
    if descriptor < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(unsafe { File::from_raw_fd(descriptor) })
    }
}

fn directory_at(parent: &File, name: &CStr, custody: Custody) -> io::Result<File> {
    let file = open_at(
        parent,
        name,
        libc::O_PATH | libc::O_DIRECTORY | libc::O_NONBLOCK,
        0,
    )?;
    DirectoryIdentity::read(&file, custody)?;
    Ok(file)
}

/// The shared implementation of the held-directory setup.lock primitive.
///
/// This public primitive permits ordinary isolated filesystem tests in the
/// package helper. It cannot construct either fixed production guard and is
/// not accepted by the selection reader as activation authority.
pub struct DirectorySetupLock {
    directory: File,
    directory_identity: DirectoryIdentity,
    custody: Custody,
    file: File,
    identity: LockIdentity,
}

impl DirectorySetupLock {
    pub fn exclusive_at(directory: &File, uid: u32, gid: u32) -> io::Result<Self> {
        Self::acquire(directory, Custody { uid, gid }, Access::Exclusive)
    }

    fn acquire(directory: &File, custody: Custody, access: Access) -> io::Result<Self> {
        // Preserve the original pre-create custody check; accepting a received
        // descriptor must not make the normal lock creator mutate an unsafe parent.
        let original_directory = DirectoryIdentity::read(directory, custody)?;
        let (flags, mode) = match access {
            Access::InspectExisting => (libc::O_RDONLY, 0),
            // flock and the same-OFD lseek challenge never modify lock bytes.
            // Keeping the description read-only also prevents SCM_RIGHTS from
            // granting the broker an unused write capability on setup.lock.
            Access::Shared | Access::Exclusive => (libc::O_RDONLY | libc::O_CREAT, 0o600),
        };
        let file = open_at(directory, LOCK, flags | libc::O_NONBLOCK, mode)?;
        let held = Self::from_file(directory, custody, file, access)?;
        if held.directory_identity != original_directory {
            return Err(rejected(
                "configuration lock parent changed during creation",
            ));
        }
        Ok(held)
    }

    fn from_file(
        directory: &File,
        custody: Custody,
        file: File,
        access: Access,
    ) -> io::Result<Self> {
        let directory_identity = DirectoryIdentity::read(directory, custody)?;
        let identity = LockIdentity::read(file.metadata()?, custody)?;
        let named = open_at(directory, LOCK, libc::O_PATH | libc::O_NONBLOCK, 0)?;
        let status_flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
        if status_flags < 0 {
            return Err(io::Error::last_os_error());
        }
        let descriptor_flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFD) };
        if descriptor_flags < 0 {
            return Err(io::Error::last_os_error());
        }
        if LockIdentity::read(named.metadata()?, custody)? != identity
            || status_flags & libc::O_ACCMODE != libc::O_RDONLY
            || descriptor_flags & libc::FD_CLOEXEC == 0
        {
            return Err(rejected(
                "received descriptor is not the named read-only close-on-exec setup lock",
            ));
        }
        let operation = match access {
            Access::InspectExisting | Access::Shared => libc::LOCK_SH,
            Access::Exclusive => libc::LOCK_EX,
        };
        if unsafe { libc::flock(file.as_raw_fd(), operation | libc::LOCK_NB) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let held = Self {
            directory: directory.try_clone()?,
            directory_identity,
            custody,
            file,
            identity,
        };
        held.revalidate()?;
        Ok(held)
    }

    pub fn revalidate(&self) -> io::Result<()> {
        let named = open_at(&self.directory, LOCK, libc::O_PATH | libc::O_NONBLOCK, 0)?;
        if DirectoryIdentity::read(&self.directory, self.custody)? != self.directory_identity
            || LockIdentity::read(self.file.metadata()?, self.custody)? != self.identity
            || LockIdentity::read(named.metadata()?, self.custody)? != self.identity
        {
            return Err(rejected("the held setup.lock or its parent changed"));
        }
        Ok(())
    }
}

impl AsFd for DirectorySetupLock {
    fn as_fd(&self) -> BorrowedFd<'_> {
        self.file.as_fd()
    }
}

// No explicit LOCK_UN: a future authenticated SCM_RIGHTS duplicate shares the
// same open-file description. Closing one duplicate must not unlock another.
struct FixedConfigurationLock {
    root_path: PathBuf,
    root: File,
    root_identity: DirectoryIdentity,
    etc: File,
    etc_identity: DirectoryIdentity,
    base: File,
    base_identity: DirectoryIdentity,
    custody: Custody,
    lock: DirectorySetupLock,
}

impl FixedConfigurationLock {
    fn fixed(access: Access) -> io::Result<Self> {
        if unsafe { libc::getuid() } != 0 || unsafe { libc::geteuid() } != 0 {
            return Err(rejected(
                "the fixed configuration guard requires the root broker with real/effective UID 0",
            ));
        }
        Self::at(Path::new("/"), ROOT, access)
    }

    // Private to this module; only fixed() and ordinary local fixtures call it.
    fn at(root_path: &Path, custody: Custody, access: Access) -> io::Result<Self> {
        Self::at_with_received(root_path, custody, access, None)
    }

    fn received(file: File) -> io::Result<Self> {
        if unsafe { libc::getuid() } != 0 || unsafe { libc::geteuid() } != 0 {
            return Err(rejected(
                "received fixed lock requires the actual root broker",
            ));
        }
        Self::at_with_received(Path::new("/"), ROOT, Access::Exclusive, Some(file))
    }

    fn at_with_received(
        root_path: &Path,
        custody: Custody,
        access: Access,
        received: Option<File>,
    ) -> io::Result<Self> {
        use std::os::unix::fs::OpenOptionsExt;
        let root = File::options()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(root_path)?;
        let root_identity = DirectoryIdentity::read(&root, custody)?;
        let etc = directory_at(&root, c"etc", custody)?;
        let etc_identity = DirectoryIdentity::read(&etc, custody)?;
        let base = directory_at(&etc, c"droidloom", custody)?;
        let base_identity = DirectoryIdentity::read(&base, custody)?;
        let lock = match received {
            Some(file) => DirectorySetupLock::from_file(&base, custody, file, Access::Exclusive)?,
            None => DirectorySetupLock::acquire(&base, custody, access)?,
        };
        let held = Self {
            root_path: root_path.to_path_buf(),
            root,
            root_identity,
            etc,
            etc_identity,
            base,
            base_identity,
            custody,
            lock,
        };
        held.revalidate()?;
        Ok(held)
    }

    fn revalidate(&self) -> io::Result<()> {
        use std::os::unix::fs::OpenOptionsExt;
        let root = File::options()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&self.root_path)?;
        let etc = directory_at(&self.root, c"etc", self.custody)?;
        let base = directory_at(&self.etc, c"droidloom", self.custody)?;
        if DirectoryIdentity::read(&root, self.custody)? != self.root_identity
            || DirectoryIdentity::read(&self.root, self.custody)? != self.root_identity
            || DirectoryIdentity::read(&etc, self.custody)? != self.etc_identity
            || DirectoryIdentity::read(&self.etc, self.custody)? != self.etc_identity
            || DirectoryIdentity::read(&base, self.custody)? != self.base_identity
            || DirectoryIdentity::read(&self.base, self.custody)? != self.base_identity
        {
            return Err(rejected("the fixed configuration parent chain changed"));
        }
        self.lock.revalidate()
    }

    fn activation_allowed(&self) -> io::Result<()> {
        self.revalidate()?;
        let production = match directory_at(&self.base, c"production", self.custody) {
            Ok(file) => file,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(()),
            Err(error) => return Err(error),
        };
        let mut metadata = std::mem::MaybeUninit::<libc::stat>::uninit();
        let rc = unsafe {
            libc::fstatat(
                production.as_raw_fd(),
                MAINTENANCE.as_ptr(),
                metadata.as_mut_ptr(),
                libc::AT_SYMLINK_NOFOLLOW,
            )
        };
        if rc == 0 {
            return Err(rejected(
                "package maintenance prevents production activation",
            ));
        }
        let error = io::Error::last_os_error();
        if error.kind() != io::ErrorKind::NotFound {
            return Err(error);
        }
        self.revalidate()
    }
}

/// Exclusive fixed /etc/droidloom/setup.lock for the package helper.
///
/// Acquiring it does not permit Stop, replacement, selection publication or
/// fence removal; each operation still needs its own real owner contract.
pub struct PackageConfigurationLock(FixedConfigurationLock);

impl PackageConfigurationLock {
    pub fn acquire() -> io::Result<Self> {
        FixedConfigurationLock::fixed(Access::Exclusive).map(Self)
    }

    pub fn revalidate(&self) -> io::Result<()> {
        self.0.revalidate()
    }
}

impl AsFd for PackageConfigurationLock {
    fn as_fd(&self) -> BorrowedFd<'_> {
        self.0.lock.as_fd()
    }
}

/// A received duplicate of the helper's actual fixed exclusive open-file
/// description. It is never made by opening an arbitrary descriptor pathname.
/// Its constructor verifies the fixed parents, full named inode and real flock.
pub(crate) struct ReceivedPackageConfigurationLock(FixedConfigurationLock);

impl ReceivedPackageConfigurationLock {
    pub(crate) fn from_received(file: File) -> io::Result<Self> {
        FixedConfigurationLock::received(file).map(Self)
    }

    pub(crate) fn revalidate(&self) -> io::Result<()> {
        self.0.revalidate()
    }

    pub(crate) fn require_unfenced(&self) -> io::Result<()> {
        self.0.activation_allowed()
    }

    pub(crate) fn observe_fence(&self, expected: &[u8]) -> io::Result<MaintenanceFence> {
        MaintenanceFence::read(&self.0, expected)
    }

    pub(crate) fn revalidate_fence(&self, fence: &MaintenanceFence) -> io::Result<()> {
        fence.revalidate(&self.0)
    }

    pub(crate) fn confirm_fence_durable(&self, fence: &MaintenanceFence) -> io::Result<()> {
        fence.revalidate(&self.0)?;
        fence.file.sync_all()?;
        fence.directory.sync_all()?;
        fence.revalidate(&self.0)
    }
}

impl AsFd for ReceivedPackageConfigurationLock {
    fn as_fd(&self) -> BorrowedFd<'_> {
        self.0.lock.as_fd()
    }
}

impl PackageConfigurationLock {
    pub(crate) fn require_unfenced(&self) -> io::Result<()> {
        self.0.activation_allowed()
    }

    pub(crate) fn create_maintenance_fence(&self, body: &[u8]) -> io::Result<MaintenanceFence> {
        self.0.activation_allowed()?;
        if body.is_empty() || body.len() > 4096 {
            return Err(rejected(
                "package maintenance body is outside its fixed bound",
            ));
        }
        let directory = open_at(
            &self.0.base,
            c"production",
            libc::O_RDONLY | libc::O_DIRECTORY,
            0,
        )?;
        DirectoryIdentity::read(&directory, self.0.custody)?;
        // Failure after create intentionally leaves this deny fence present.
        // There is no unlink, overwrite, grant parser or automatic rollback.
        let mut file = open_at(
            &directory,
            MAINTENANCE,
            libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL,
            0o600,
        )?;
        file.write_all(body)?;
        file.sync_all()?;
        if unsafe { libc::fchmod(file.as_raw_fd(), 0o400) } != 0 {
            return Err(io::Error::last_os_error());
        }
        file.sync_all()?;
        directory.sync_all()?;
        drop(file);
        self.0.revalidate()?;
        MaintenanceFence::read(&self.0, body)
    }

    pub(crate) fn revalidate_fence(&self, fence: &MaintenanceFence) -> io::Result<()> {
        fence.revalidate(&self.0)
    }
}

/// The actual newly created deny inode, retained even when the peer or later
/// package operation fails. This type cannot authorize resource replacement.
pub(crate) struct MaintenanceFence {
    directory: File,
    directory_identity: DirectoryIdentity,
    file: File,
    identity: LockIdentity,
    body: Vec<u8>,
}

impl MaintenanceFence {
    fn read(guard: &FixedConfigurationLock, expected: &[u8]) -> io::Result<Self> {
        guard.revalidate()?;
        if expected.is_empty() || expected.len() > 4096 {
            return Err(rejected("invalid fixed maintenance observation length"));
        }
        let directory = open_at(
            &guard.base,
            c"production",
            libc::O_RDONLY | libc::O_DIRECTORY,
            0,
        )?;
        let directory_identity = DirectoryIdentity::read(&directory, guard.custody)?;
        let file = open_at(
            &directory,
            MAINTENANCE,
            libc::O_RDONLY | libc::O_NONBLOCK,
            0,
        )?;
        let identity = LockIdentity::read(file.metadata()?, guard.custody)?;
        if identity.bytes != expected.len() as u64 || identity.mode & 0o7777 != 0o400 {
            return Err(rejected(
                "maintenance inode is not the exact sealed transaction",
            ));
        }
        let value = Self {
            directory,
            directory_identity,
            file,
            identity,
            body: expected.to_vec(),
        };
        value.revalidate(guard)?;
        Ok(value)
    }

    fn revalidate(&self, guard: &FixedConfigurationLock) -> io::Result<()> {
        guard.revalidate()?;
        let named_directory = open_at(
            &guard.base,
            c"production",
            libc::O_PATH | libc::O_DIRECTORY,
            0,
        )?;
        let named = open_at(
            &self.directory,
            MAINTENANCE,
            libc::O_PATH | libc::O_NONBLOCK,
            0,
        )?;
        if DirectoryIdentity::read(&named_directory, guard.custody)? != self.directory_identity
            || DirectoryIdentity::read(&self.directory, guard.custody)? != self.directory_identity
            || LockIdentity::read(self.file.metadata()?, guard.custody)? != self.identity
            || LockIdentity::read(named.metadata()?, guard.custody)? != self.identity
        {
            return Err(rejected("original package maintenance inode changed"));
        }
        let mut actual = vec![0; self.body.len()];
        self.file.read_exact_at(&mut actual, 0)?;
        if actual != self.body
            || LockIdentity::read(self.file.metadata()?, guard.custody)? != self.identity
        {
            return Err(rejected("original maintenance bytes changed"));
        }
        guard.revalidate()
    }

    pub(crate) fn binding(&self) -> [u8; 32] {
        let mut hash = Sha256::new();
        hash.update(b"droidloom-package-maintenance-inode-v1\0");
        for n in [
            self.identity.device,
            self.identity.inode,
            self.identity.mode as u64,
            self.identity.uid as u64,
            self.identity.gid as u64,
            self.identity.links,
            self.identity.bytes,
            self.identity.modified.0 as u64,
            self.identity.modified.1 as u64,
            self.identity.changed.0 as u64,
            self.identity.changed.1 as u64,
        ] {
            hash.update(n.to_le_bytes());
        }
        hash.update(&self.body);
        hash.finalize().into()
    }
}

/// Only a fresh shared fixed-root lock with no maintenance fence can precede
/// selection loading. It is held across the complete activation decision.
pub(crate) struct ConfigurationReadGuard(FixedConfigurationLock);

impl ConfigurationReadGuard {
    /// Hold the installed configuration read lock without creating or writing any inode.
    pub(crate) fn inspect_existing() -> io::Result<Self> {
        let held = Self(FixedConfigurationLock::fixed(Access::InspectExisting)?);
        held.revalidate()?;
        Ok(held)
    }

    pub(crate) fn acquire() -> io::Result<Self> {
        match Self::inspect_existing() {
            Err(error) if error.kind()==io::ErrorKind::NotFound => {
                let held=Self(FixedConfigurationLock::fixed(Access::Shared)?);
                held.revalidate()?;
                Ok(held)
            }
            result=>result,
        }
    }

    pub(crate) fn revalidate(&self) -> io::Result<()> {
        self.0.activation_allowed()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
    use std::process::{Command, Stdio};

    fn fixture() -> (tempfile::TempDir, Custody) {
        let directory = tempfile::tempdir().unwrap();
        fs::create_dir_all(directory.path().join("etc/droidloom/production")).unwrap();
        let custody = Custody {
            uid: unsafe { libc::getuid() },
            gid: unsafe { libc::getgid() },
        };
        (directory, custody)
    }

    #[test]
    fn existing_calibration_reader_never_creates_or_writes_the_setup_lock() {
        let (root,custody)=fixture();
        let lock=root.path().join("etc/droidloom/setup.lock");
        assert!(FixedConfigurationLock::at(root.path(),custody,Access::InspectExisting).is_err());
        assert!(!lock.exists());
        drop(FixedConfigurationLock::at(root.path(),custody,Access::Exclusive).unwrap());
        let reader=FixedConfigurationLock::at(root.path(),custody,Access::InspectExisting).unwrap();
        assert_eq!(unsafe{libc::fcntl(reader.lock.as_fd().as_raw_fd(),libc::F_GETFL)} & libc::O_ACCMODE,libc::O_RDONLY);
        assert!(FixedConfigurationLock::at(root.path(),custody,Access::Exclusive).is_err());
        reader.activation_allowed().unwrap();
        drop(reader);
        assert!(FixedConfigurationLock::at(root.path(),custody,Access::Exclusive).is_ok());
    }

    #[test]
    fn setup_readers_exclude_a_real_package_writer_process() {
        const ROOT_ENV: &str = "DROIDLOOM_CONFIGURATION_LOCK_TEST_ROOT";
        const EXPECT_ENV: &str = "DROIDLOOM_CONFIGURATION_LOCK_TEST_EXPECT";
        if let Some(root) = std::env::var_os(ROOT_ENV) {
            let custody = Custody {
                uid: unsafe { libc::getuid() },
                gid: unsafe { libc::getgid() },
            };
            let result = FixedConfigurationLock::at(Path::new(&root), custody, Access::Exclusive);
            match std::env::var(EXPECT_ENV).unwrap().as_str() {
                "blocked" => assert!(
                    matches!(result, Err(ref error) if error.raw_os_error() == Some(libc::EWOULDBLOCK))
                ),
                "acquired" => result.unwrap().revalidate().unwrap(),
                _ => panic!("unexpected isolated test phase"),
            }
            return;
        }
        let (directory, custody) = fixture();
        let first = FixedConfigurationLock::at(directory.path(), custody, Access::Shared).unwrap();
        let second = FixedConfigurationLock::at(directory.path(), custody, Access::Shared).unwrap();
        let child = |expect: &str| {
            let output = Command::new(std::env::current_exe().unwrap())
                .args(["--exact", "production_configuration::tests::setup_readers_exclude_a_real_package_writer_process", "--nocapture"])
                .env(ROOT_ENV, directory.path()).env(EXPECT_ENV, expect)
                .stdin(Stdio::null()).output().unwrap();
            assert!(
                output.status.success(),
                "{}",
                String::from_utf8_lossy(&output.stderr)
            );
            assert!(String::from_utf8_lossy(&output.stdout).contains("1 passed; 0 failed"));
        };
        child("blocked");
        drop(first);
        child("blocked");
        drop(second);
        child("acquired");
        let exclusive =
            FixedConfigurationLock::at(directory.path(), custody, Access::Exclusive).unwrap();
        let duplicate = exclusive.lock.file.try_clone().unwrap();
        drop(exclusive);
        child("blocked");
        drop(duplicate);
        child("acquired");
    }

    #[test]
    fn setup_lock_and_fixed_parent_replacements_are_rejected() {
        let (directory, custody) = fixture();
        let held =
            FixedConfigurationLock::at(directory.path(), custody, Access::Exclusive).unwrap();
        let base = directory.path().join("etc/droidloom");
        fs::rename(base.join("setup.lock"), base.join("old.lock")).unwrap();
        fs::write(base.join("setup.lock"), b"").unwrap();
        assert!(held.revalidate().is_err());
        drop(held);
        let held =
            FixedConfigurationLock::at(directory.path(), custody, Access::Exclusive).unwrap();
        fs::rename(&base, directory.path().join("etc/previous")).unwrap();
        fs::create_dir(&base).unwrap();
        assert!(held.revalidate().is_err());
        drop(held);
        let directory_fd = File::options()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY)
            .open(&base)
            .unwrap();
        std::os::unix::fs::symlink("absent", base.join("setup.lock")).unwrap();
        assert!(DirectorySetupLock::exclusive_at(&directory_fd, custody.uid, custody.gid).is_err());
        fs::remove_file(base.join("setup.lock")).unwrap();
        fs::write(base.join("setup.lock"), b"").unwrap();
        fs::hard_link(base.join("setup.lock"), base.join("second-link")).unwrap();
        assert!(DirectorySetupLock::exclusive_at(&directory_fd, custody.uid, custody.gid).is_err());
        fs::remove_file(base.join("second-link")).unwrap();
        fs::set_permissions(base.join("setup.lock"), fs::Permissions::from_mode(0o666)).unwrap();
        assert!(DirectorySetupLock::exclusive_at(&directory_fd, custody.uid, custody.gid).is_err());
    }

    #[test]
    fn received_setup_lock_requires_readonly_same_description_and_rejects_replacements() {
        let (directory, custody) = fixture();
        let held =
            FixedConfigurationLock::at(directory.path(), custody, Access::Exclusive).unwrap();
        let base = directory.path().join("etc/droidloom");
        let duplicate = held.lock.file.try_clone().unwrap();
        let received = FixedConfigurationLock::at_with_received(
            directory.path(),
            custody,
            Access::Exclusive,
            Some(duplicate),
        )
        .unwrap();
        received.revalidate().unwrap();
        assert_eq!(unsafe { libc::fcntl(received.lock.as_fd().as_raw_fd(), libc::F_GETFL) } & libc::O_ACCMODE, libc::O_RDONLY);
        assert_eq!(received.lock.file.write_at(b"not permitted", 0).unwrap_err().raw_os_error(), Some(libc::EBADF));
        let readonly = File::open(base.join("setup.lock")).unwrap();
        assert!(
            FixedConfigurationLock::at_with_received(
                directory.path(),
                custody,
                Access::Exclusive,
                Some(readonly)
            )
            .is_err()
        );
        let writable = File::options()
            .read(true)
            .write(true)
            .open(base.join("setup.lock"))
            .unwrap();
        assert!(matches!(FixedConfigurationLock::at_with_received(
            directory.path(), custody, Access::Exclusive, Some(writable)),
            Err(error) if error.kind() == io::ErrorKind::PermissionDenied));
        let independent = File::open(base.join("setup.lock")).unwrap();
        assert!(matches!(FixedConfigurationLock::at_with_received(
            directory.path(), custody, Access::Exclusive, Some(independent)),
            Err(error) if error.raw_os_error() == Some(libc::EWOULDBLOCK)));
        let foreign = File::options()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(base.join("foreign.lock"))
            .unwrap();
        assert!(
            FixedConfigurationLock::at_with_received(
                directory.path(),
                custody,
                Access::Exclusive,
                Some(foreign)
            )
            .is_err()
        );
        fs::rename(base.join("setup.lock"), base.join("previous.lock")).unwrap();
        fs::write(base.join("setup.lock"), b"").unwrap();
        assert!(received.revalidate().is_err());
        assert!(
            FixedConfigurationLock::at_with_received(
                directory.path(),
                custody,
                Access::Exclusive,
                Some(held.lock.file.try_clone().unwrap())
            )
            .is_err()
        );
        let unsafe_path = directory.path().join("unsafe-parent");
        fs::create_dir(&unsafe_path).unwrap();
        fs::set_permissions(&unsafe_path, fs::Permissions::from_mode(0o777)).unwrap();
        let unsafe_parent = File::options()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY)
            .open(&unsafe_path)
            .unwrap();
        assert!(
            DirectorySetupLock::exclusive_at(&unsafe_parent, custody.uid, custody.gid).is_err()
        );
        assert!(!unsafe_path.join("setup.lock").exists());
    }

    #[test]
    fn durable_package_fence_survives_disconnect_and_rejects_replacement() {
        use std::io::Read;
        use std::os::unix::net::UnixStream;
        let (directory, custody) = fixture();
        let held = PackageConfigurationLock(
            FixedConfigurationLock::at(directory.path(), custody, Access::Exclusive).unwrap(),
        );
        let body = br#"{"resource_retirement_grant":false,"ordinary_fixture":true}"#;
        let fence = held.create_maintenance_fence(body).unwrap();
        held.revalidate_fence(&fence).unwrap();
        let original_binding = fence.binding();
        let original_inode = fence.file.metadata().unwrap().ino();
        let receiver = ReceivedPackageConfigurationLock(
            FixedConfigurationLock::at_with_received(
                directory.path(),
                custody,
                Access::Exclusive,
                Some(held.0.lock.file.try_clone().unwrap()),
            )
            .unwrap(),
        );
        let observed = receiver.observe_fence(body).unwrap();
        receiver.confirm_fence_durable(&observed).unwrap();
        assert_eq!(observed.binding(), original_binding);
        let (left, mut right) = UnixStream::pair().unwrap();
        drop(left);
        assert_eq!(right.read(&mut [0_u8; 1]).unwrap(), 0);
        drop(right);
        drop(observed);
        drop(receiver);
        drop(fence);
        drop(held);
        let path = directory
            .path()
            .join("etc/droidloom/production/package-maintenance.json");
        assert_eq!(fs::read(&path).unwrap(), body);
        assert_eq!(fs::metadata(&path).unwrap().ino(), original_inode);
        let read_guard =
            FixedConfigurationLock::at(directory.path(), custody, Access::Shared).unwrap();
        assert!(read_guard.activation_allowed().is_err());
        drop(read_guard);
        let writer = PackageConfigurationLock(
            FixedConfigurationLock::at(directory.path(), custody, Access::Exclusive).unwrap(),
        );
        assert!(writer.create_maintenance_fence(body).is_err());
        let original = MaintenanceFence::read(&writer.0, body).unwrap();
        fs::rename(&path, path.with_extension("saved")).unwrap();
        fs::write(&path, body).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o400)).unwrap();
        assert!(writer.revalidate_fence(&original).is_err());
        assert!(writer.require_unfenced().is_err());
    }

    #[test]
    fn maintenance_fence_rejects_malformed_and_dangling_nodes() {
        let (directory, custody) = fixture();
        let held = FixedConfigurationLock::at(directory.path(), custody, Access::Shared).unwrap();
        let path = directory
            .path()
            .join("etc/droidloom/production/package-maintenance.json");
        held.activation_allowed().unwrap();
        fs::write(&path, b"not a retirement grant").unwrap();
        assert!(held.activation_allowed().is_err());
        fs::remove_file(&path).unwrap();
        std::os::unix::fs::symlink("absent", &path).unwrap();
        assert!(held.activation_allowed().is_err());
        fs::remove_file(&path).unwrap();
        fs::create_dir(&path).unwrap();
        assert!(held.activation_allowed().is_err());
        fs::remove_dir(&path).unwrap();
        held.activation_allowed().unwrap();
    }
}
