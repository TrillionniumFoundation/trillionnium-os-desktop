//! Original source-owner lock OFDs; paths and complete identities stay fixed.
//! User-owned parent traversal is isolated inside the fixed filesystem worker.
use crate::native_source_files::NativeSourceLock;
use std::io;

const LOCKS: [(&str, [u64; 9]); 2] = [
    (
        "/home/alex/work/pocket4-android-final/.CONTINUATION_CURRENT.lock",
        [
            66306,
            41719172,
            33152,
            0,
            0,
            1,
            0,
            1794130437217307659,
            1794130437217307659,
        ],
    ),
    (
        "/home/alex/work/pocket4-android-final/.qpr1-kernel-control-8b88.lock",
        [
            66306,
            41719533,
            33152,
            0,
            0,
            1,
            0,
            1794178693266232511,
            1794178693266232511,
        ],
    ),
];

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, message)
}

/// Both original source-owner lock OFDs, retained in their original order.
pub struct NativeApplicationSourceLocks {
    files: Vec<NativeSourceLock>,
    pid: u32,
    exclusive: bool,
}
impl NativeApplicationSourceLocks {
    pub fn acquire() -> io::Result<Self> {
        Self::acquire_mode(false)
    }
    pub fn acquire_for_adoption() -> io::Result<Self> {
        Self::acquire_mode(true)
    }
    fn acquire_mode(exclusive: bool) -> io::Result<Self> {
        if unsafe { libc::getuid() } != 0 || unsafe { libc::geteuid() } != 0 {
            return Err(invalid("original root application controller required"));
        }
        let mut guard = Self {
            files: Vec::new(),
            pid: std::process::id(),
            exclusive,
        };
        for (index, (_, expected)) in LOCKS.into_iter().enumerate() {
            guard
                .files
                .push(NativeSourceLock::open(index, expected, exclusive)?);
        }
        guard.validate()?;
        Ok(guard)
    }
    pub fn validate(&self) -> io::Result<()> {
        if self.pid != std::process::id() || self.files.len() != LOCKS.len() {
            return Err(invalid("same-process original source lock lease required"));
        }
        for file in &self.files {
            file.guard()?;
        }
        Ok(())
    }
    pub(crate) fn validate_for_adoption(&self) -> io::Result<()> {
        if !self.exclusive {
            return Err(invalid("both original exclusive source locks required"));
        }
        self.validate()
    }
}
// Closing the owned Files releases flock; no LOCK_UN affects a forked OFD.
