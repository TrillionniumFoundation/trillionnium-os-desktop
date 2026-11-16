//! Persistent pending-state admission, shared with daemon mutations and the UI
//! consumer. No lock re-acquisition is needed by a caller already holding flock.
//! The preparatory writer/retention lifecycle is test-only until real framework
//! task-creation authority exists; production never clears a pending intent.
use std::ffi::CStr;
use std::fs::{File, OpenOptions};
use std::io;
#[cfg(test)]
use std::io::Write;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::Path;
#[cfg(test)]
use std::sync::Mutex;

#[cfg(test)]
const LOCK: &CStr = c"android-digitalis-actions.lock";
const MARKER: &CStr = c"droidloom-settings-observation.pending.json";

pub(super) fn ensure_no_pending() -> io::Result<()> {
    ensure_no_pending_in(Path::new("/run/lock"), 0)
}

pub(super) fn ensure_no_pending_in(path: &Path, expected_owner: u32) -> io::Result<()> {
    let directory = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)?;
    if directory.metadata()?.uid() != expected_owner {
        return Err(fail(
            "pending action directory owner differs; mutation blocked",
        ));
    }
    match open(&directory, MARKER, libc::O_PATH) {
        Ok(_) => Err(fail(
            "unreconciled Settings action pending; mutation blocked without retry",
        )),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e),
    }
}

fn fail(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

fn open(directory: &File, name: &CStr, flags: i32) -> io::Result<File> {
    // SAFETY: held directory and NUL-terminated fixed basename; only new FD is owned.
    let fd = unsafe {
        libc::openat(
            directory.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            0o600,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: successful openat allocated this owned FD.
    Ok(unsafe { File::from_raw_fd(fd) })
}

#[cfg(test)]
fn private_regular(file: &File) -> io::Result<()> {
    let m = file.metadata()?;
    // SAFETY: geteuid has no pointer or ownership preconditions.
    let uid = unsafe { libc::geteuid() };
    if !m.is_file() || m.uid() != uid || m.nlink() != 1 || m.mode() & 0o7777 != 0o600 {
        return Err(fail(
            "action scope file is not an owned private regular inode",
        ));
    }
    Ok(())
}

#[cfg(test)]
pub(super) struct ActionScope<'a> {
    directory: File,
    lock: Option<File>,
    marker: Option<File>,
    retained: &'a Mutex<Option<File>>,
}

#[cfg(test)]
impl<'a> ActionScope<'a> {
    pub(super) fn acquire_in(path: &Path, retained: &'a Mutex<Option<File>>) -> io::Result<Self> {
        if retained
            .lock()
            .map_err(|_| fail("action custody mutex is poisoned"))?
            .is_some()
        {
            return Err(fail(
                "an unresolved Settings action still holds the shared action lock",
            ));
        }
        let directory = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(path)?;
        let metadata = directory.metadata()?;
        // SAFETY: geteuid has no pointer or ownership preconditions.
        if metadata.uid() != unsafe { libc::geteuid() } {
            return Err(fail("action lock directory owner differs"));
        }
        let lock = open(
            &directory,
            LOCK,
            libc::O_CREAT | libc::O_RDWR | libc::O_NONBLOCK,
        )?;
        private_regular(&lock)?;
        // SAFETY: this is a live owned FD; LOCK_NB prevents an unbounded wait.
        if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(io::Error::last_os_error());
        }
        match open(&directory, MARKER, libc::O_PATH) {
            Ok(_) => {
                return Err(fail(
                    "unreconciled Settings intent exists; no automatic retry or adoption",
                ));
            }
            Err(e) if e.kind() == io::ErrorKind::NotFound => {}
            Err(e) => return Err(e),
        }
        Ok(Self {
            directory,
            lock: Some(lock),
            marker: None,
            retained,
        })
    }

    pub fn before_start(&mut self, intent: &[u8]) -> io::Result<()> {
        if intent.is_empty() || intent.len() > 8192 || self.marker.is_some() {
            return Err(fail("invalid or repeated Settings intent"));
        }
        let marker = open(
            &self.directory,
            MARKER,
            libc::O_CREAT | libc::O_EXCL | libc::O_WRONLY,
        )?;
        // From this point a write/fsync error also preserves custody. No start
        // can be sent until both the marker and its directory are durable.
        self.marker = Some(marker);
        let file = self.marker.as_mut().expect("inserted above");
        private_regular(file)?;
        file.write_all(intent)?;
        file.sync_all()?;
        self.directory.sync_all()?;
        Ok(())
    }

    pub fn finish_after_verified_cleanup(&mut self) -> io::Result<()> {
        let marker = self
            .marker
            .as_ref()
            .ok_or_else(|| fail("Settings intent missing"))?;
        private_regular(marker)?;
        let current = open(&self.directory, MARKER, libc::O_RDONLY | libc::O_NONBLOCK)?;
        private_regular(&current)?;
        let a = marker.metadata()?;
        let b = current.metadata()?;
        if a.dev() != b.dev() || a.ino() != b.ino() {
            return Err(fail("Settings intent pathname changed; custody retained"));
        }
        // SAFETY: the directory is held; the exact private inode was checked
        // above while holding the shared action flock. No foreign path is used.
        if unsafe { libc::unlinkat(self.directory.as_raw_fd(), MARKER.as_ptr(), 0) } != 0 {
            return Err(io::Error::last_os_error());
        }
        self.directory.sync_all()?;
        self.marker = None;
        Ok(())
    }

    pub fn pending(&self) -> bool {
        self.marker.is_some()
    }
}

#[cfg(test)]
impl Drop for ActionScope<'_> {
    fn drop(&mut self) {
        if self.marker.is_none() {
            return;
        }
        if let Some(file) = self.lock.take() {
            match self.retained.lock() {
                Ok(mut retained) if retained.is_none() => *retained = Some(file),
                // Poisoning or an impossible second retained scope must not
                // silently release an unresolved global action flock.
                _ => std::mem::forget(file),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pending_reader_survives_writer_exit_and_rejects_unknown_path_states() {
        let d = tempfile::tempdir().unwrap();
        let uid = d.path().metadata().unwrap().uid();
        ensure_no_pending_in(d.path(), uid).unwrap();
        let marker = d.path().join(MARKER.to_str().unwrap());
        std::os::unix::fs::symlink(d.path().join("absent-target"), &marker).unwrap();
        assert!(ensure_no_pending_in(d.path(), uid).is_err());
        assert!(marker.symlink_metadata().unwrap().file_type().is_symlink());
        std::fs::remove_file(&marker).unwrap();
        std::fs::write(&marker, b"unresolved").unwrap();
        assert!(
            ensure_no_pending_in(d.path(), uid)
                .unwrap_err()
                .to_string()
                .contains("pending")
        );
        assert!(ensure_no_pending_in(d.path(), uid.wrapping_add(1)).is_err());
        assert!(ensure_no_pending_in(&d.path().join("missing"), uid).is_err());
        assert_eq!(std::fs::read(marker).unwrap(), b"unresolved");
    }
    #[test]
    fn shared_flock_excludes_a_separate_open_file_description() {
        let d = tempfile::tempdir().unwrap();
        let r = Mutex::new(None);
        let scope = ActionScope::acquire_in(d.path(), &r).unwrap();
        let other = OpenOptions::new()
            .read(true)
            .write(true)
            .open(d.path().join(LOCK.to_str().unwrap()))
            .unwrap();
        // SAFETY: valid separately opened FD; no blocking lock requested.
        assert_ne!(
            unsafe { libc::flock(other.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        drop(scope);
        // SAFETY: same valid FD, now no competing open description remains.
        assert_eq!(
            unsafe { libc::flock(other.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
    }
    #[test]
    fn uncertain_intent_survives_lock_release_and_blocks_daemon_restart() {
        let d = tempfile::tempdir().unwrap();
        let r = Mutex::new(None);
        let mut scope = ActionScope::acquire_in(d.path(), &r).unwrap();
        scope.before_start(b"{\"fixture_only\":true}").unwrap();
        drop(scope);
        assert!(r.lock().unwrap().is_some());
        assert!(ActionScope::acquire_in(d.path(), &r).is_err());
        r.lock().unwrap().take(); // model daemon death, not a production recovery API
        assert!(
            ActionScope::acquire_in(d.path(), &r)
                .err()
                .unwrap()
                .to_string()
                .contains("unreconciled")
        );
    }
    #[test]
    fn verified_cleanup_removes_only_its_held_marker_and_releases_flock() {
        let d = tempfile::tempdir().unwrap();
        let r = Mutex::new(None);
        let mut scope = ActionScope::acquire_in(d.path(), &r).unwrap();
        scope.before_start(b"{}").unwrap();
        scope.finish_after_verified_cleanup().unwrap();
        drop(scope);
        assert!(!d.path().join(MARKER.to_str().unwrap()).exists());
        assert!(ActionScope::acquire_in(d.path(), &r).is_ok());
    }
    #[test]
    fn replaced_marker_or_lock_symlink_is_not_followed_or_deleted() {
        let d = tempfile::tempdir().unwrap();
        let r = Mutex::new(None);
        let outside = d.path().join("outside");
        std::fs::write(&outside, b"keep").unwrap();
        std::os::unix::fs::symlink(&outside, d.path().join(LOCK.to_str().unwrap())).unwrap();
        assert!(ActionScope::acquire_in(d.path(), &r).is_err());
        std::fs::remove_file(d.path().join(LOCK.to_str().unwrap())).unwrap();
        let mut scope = ActionScope::acquire_in(d.path(), &r).unwrap();
        scope.before_start(b"{}").unwrap();
        let marker = d.path().join(MARKER.to_str().unwrap());
        std::fs::remove_file(&marker).unwrap();
        std::os::unix::fs::symlink(&outside, &marker).unwrap();
        assert!(scope.finish_after_verified_cleanup().is_err());
        drop(scope);
        assert_eq!(std::fs::read(&outside).unwrap(), b"keep");
        assert!(r.lock().unwrap().is_some());
    }
}
