//! Private physical checkpoint IO shared by the original application stores.
//! These bytes contain application data and one receipt, never operation history.
use std::ffi::CString;
use std::fs::{self, DirBuilder, File};
use std::io::{self, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt};
use std::path::Path;

pub(crate) const MAX_CHECKPOINT_BYTES: u64 = 16 * 1024;
#[derive(Clone, Copy, PartialEq, Eq)]
pub(crate) enum Mode {
    Application,
    RecoveryOnly,
}

pub(crate) struct IncarnationLock(File);

impl std::ops::Deref for IncarnationLock {
    type Target = File;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl Drop for IncarnationLock {
    fn drop(&mut self) {
        // A concurrent fork can retain the open description until exec even
        // though its fd is CLOEXEC. Retiring this owner must release its lock
        // now, rather than wait for an unrelated child's inherited fd to close.
        let _ = unsafe { libc::flock(self.0.as_raw_fd(), libc::LOCK_UN) };
    }
}

fn private_directory(file: &File) -> io::Result<()> {
    let metadata = file.metadata()?;
    if !metadata.is_dir()
        || metadata.uid() != unsafe { libc::geteuid() }
        || metadata.mode() & 0o077 != 0
    {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Application data directory must be private and owned by this account",
        ));
    }
    Ok(())
}

pub(crate) fn open_root(root: &Path, create: bool) -> io::Result<File> {
    if !root.is_absolute() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Application state path must be absolute",
        ));
    }
    if create {
        match DirBuilder::new().mode(0o700).create(root) {
            Ok(()) => {
                let parent = root
                    .parent()
                    .ok_or_else(|| io::Error::other("Application state parent"))?;
                fs::OpenOptions::new()
                    .read(true)
                    .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                    .open(parent)?
                    .sync_all()?;
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(error),
        }
    }
    let parent = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(root)?;
    private_directory(&parent)?;
    Ok(parent)
}

pub(crate) fn open_directory(root: &Path, incarnation: &str, mode: Mode) -> io::Result<File> {
    let parent = open_root(root, mode == Mode::Application)?;
    // The only callers derive this component from a validated typed target.
    if incarnation.is_empty()
        || incarnation.len() > 96
        || !incarnation
            .bytes()
            .all(|b| b.is_ascii_hexdigit() || b == b'-')
    {
        return Err(io::Error::other("invalid application checkpoint directory"));
    }
    let name = CString::new(incarnation)?;
    if mode == Mode::Application {
        let result = unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) };
        if result != 0 {
            return Err(io::Error::last_os_error());
        }
        parent.sync_all()?;
    }
    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    let directory = unsafe { File::from_raw_fd(fd) };
    private_directory(&directory)?;
    Ok(directory)
}

pub(crate) fn open_file(directory: &File, name: &str, flags: libc::c_int) -> io::Result<File> {
    let name = CString::new(name)?;
    let fd = unsafe {
        libc::openat(
            directory.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
            0o600,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    let metadata = file.metadata()?;
    if !metadata.is_file()
        || metadata.uid() != unsafe { libc::geteuid() }
        || metadata.nlink() != 1
        || metadata.mode() & 0o077 != 0
        || metadata.len() > MAX_CHECKPOINT_BYTES
    {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Application state file custody",
        ));
    }
    Ok(file)
}

pub(crate) fn lock_directory(directory: &File) -> io::Result<IncarnationLock> {
    let lock = open_file(directory, "lock", libc::O_RDWR | libc::O_CREAT)?;
    if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(IncarnationLock(lock))
}

pub(crate) fn replace_checkpoint(directory: &File, bytes: &[u8]) -> io::Result<()> {
    if bytes.is_empty() || bytes.len() as u64 > MAX_CHECKPOINT_BYTES {
        return Err(io::Error::other("application checkpoint bound"));
    }
    // Under the incarnation's lock, a previous interrupted pre-rename write
    // may be discarded. It is never interpreted as a committed receipt.
    match open_file(directory, "next.json", libc::O_RDONLY) {
        Ok(_) => {
            if unsafe { libc::unlinkat(directory.as_raw_fd(), c"next.json".as_ptr(), 0) } != 0 {
                return Err(io::Error::last_os_error());
            }
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(error),
    }
    let mut file = open_file(
        directory,
        "next.json",
        libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL,
    )?;
    file.write_all(bytes)?;
    file.sync_all()?;
    if unsafe {
        libc::renameat(
            directory.as_raw_fd(),
            c"next.json".as_ptr(),
            directory.as_raw_fd(),
            c"document.json".as_ptr(),
        )
    } != 0
    {
        return Err(io::Error::last_os_error());
    }
    directory.sync_all()
}
