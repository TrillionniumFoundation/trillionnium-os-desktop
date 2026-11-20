//! The original two source-owner lock OFDs for a native application leaf.
//!
//! These fixed locks are never created, replaced or extended. Shared readers
//! retain both through child retirement and the final source bookend. A nested
//! observation CLI uses the same shared order and cannot deadlock its parent.
use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::fd::AsRawFd;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::Path;

const LOCKS: [(&str, [u64; 9]); 2] = [
    (
        "/home/alex/work/pocket4-android-final/.CONTINUATION_CURRENT.lock",
        [66306, 41719172, 33152, 0, 0, 1, 0, 1794130437217307659, 1794130437217307659],
    ),
    (
        "/home/alex/work/pocket4-android-final/.qpr1-kernel-control-8b88.lock",
        [66306, 41719533, 33152, 0, 0, 1, 0, 1794178693266232511, 1794178693266232511],
    ),
];

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, message)
}

fn identity(meta: &fs::Metadata) -> io::Result<[u64; 9]> {
    let ns = |seconds: i64, nanos: i64| -> io::Result<u64> {
        u64::try_from(i128::from(seconds) * 1_000_000_000 + i128::from(nanos))
            .map_err(|_| invalid("negative original lock timestamp"))
    };
    Ok([
        meta.dev(), meta.ino(), u64::from(meta.mode()), u64::from(meta.uid()),
        u64::from(meta.gid()), meta.nlink(), meta.len(),
        ns(meta.mtime(), meta.mtime_nsec())?, ns(meta.ctime(), meta.ctime_nsec())?,
    ])
}

/// A read lease over both original Pocket4 source-owner locks.
pub struct NativeApplicationSourceLocks {
    files: Vec<File>,
    pid: u32,
}

impl NativeApplicationSourceLocks {
    /// Acquire the original shared lock OFDs in their fixed order, without waiting.
    pub fn acquire() -> io::Result<Self> {
        Self::acquire_mode(libc::LOCK_SH)
    }

    /// Acquire both original exclusive OFDs for an explicitly requested root
    /// release adoption. This changes no owner, expiry, lock file or rule.
    pub fn acquire_for_adoption() -> io::Result<Self> {
        Self::acquire_mode(libc::LOCK_EX)
    }

    fn acquire_mode(mode: libc::c_int) -> io::Result<Self> {
        // SAFETY: getuid/geteuid have no arguments and do not mutate process state.
        if unsafe { libc::getuid() } != 0 || unsafe { libc::geteuid() } != 0 {
            return Err(invalid("original root application controller required"));
        }
        let mut guard = Self { files: Vec::new(), pid: std::process::id() };
        for (path, expected) in LOCKS {
            if Path::new(path).canonicalize()? != Path::new(path) {
                return Err(invalid("source lock path is not canonical"));
            }
            let file = OpenOptions::new().read(true)
                .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC).open(path)?;
            if identity(&file.metadata()?)? != expected
                || identity(&fs::symlink_metadata(path)?)? != expected
            {
                return Err(invalid("original source lock inode or metadata differs"));
            }
            // SAFETY: file owns the open lock FD. No lock file is created or mutated.
            if unsafe { libc::flock(file.as_raw_fd(), mode | libc::LOCK_NB) } != 0 {
                return Err(io::Error::last_os_error());
            }
            guard.files.push(file);
        }
        guard.validate()?;
        Ok(guard)
    }

    /// Revalidate both original lock identities in the acquiring process.
    pub fn validate(&self) -> io::Result<()> {
        if self.pid != std::process::id() || self.files.len() != LOCKS.len() {
            return Err(invalid("same process original source lock lease required"));
        }
        for ((path, expected), file) in LOCKS.iter().zip(&self.files) {
            if identity(&file.metadata()?)? != *expected
                || identity(&fs::symlink_metadata(path)?)? != *expected
            {
                return Err(invalid("held original source lock changed"));
            }
        }
        Ok(())
    }
}

// Closing the owned Files releases each flock, including partially acquired
// leases. Explicit LOCK_UN is unnecessary and would affect a forked same OFD.

