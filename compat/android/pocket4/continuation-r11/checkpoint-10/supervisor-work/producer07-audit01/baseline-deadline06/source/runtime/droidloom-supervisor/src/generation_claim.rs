//! Persistent admission marker for a relay-owned cell generation.
//!
//! A marker is outside systemd's RuntimeDirectory. Losing the daemon, dropping
//! a handle, restarting a service, changing the cell's runtime path, or opting
//! out of the relay never clears an unfinished generation. Only the lifecycle
//! owner may remove it after all exact process/broker/domain/network retirement
//! checks have completed. Recovery of an abandoned marker is deliberately
//! unavailable through the ordinary start/recover API.

use std::ffi::{CStr, CString};
use std::fs::{File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
#[cfg(test)]
use std::path::Path;

pub(crate) const PRODUCTION_STORE: &str = "/var/lib/droidloom/lifecycle-claims";

fn name(uid: u32) -> CString {
    CString::new(format!("u{uid}.active")).expect("decimal UID has no NUL")
}
fn failure(message: &'static str) -> io::Error {
    io::Error::other(message)
}
fn openat_file(directory: RawFd, name: &CStr, flags: i32, mode: u32) -> io::Result<File> {
    // SAFETY: the C string and the owned directory descriptor remain valid.
    let raw = unsafe {
        libc::openat(
            directory,
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            mode,
        )
    };
    if raw < 0 {
        Err(io::Error::last_os_error())
    } else {
        // SAFETY: openat returned one fresh descriptor.
        Ok(unsafe { File::from_raw_fd(raw) })
    }
}
fn validate_directory(file: &File, owner: u32, private: bool) -> io::Result<()> {
    let metadata = file.metadata()?;
    if !metadata.is_dir()
        || metadata.uid() != owner
        || metadata.mode() & 0o022 != 0
        || (private && metadata.mode() & 0o077 != 0)
    {
        return Err(failure(
            "generation directory has an unsafe type, owner or mode",
        ));
    }
    Ok(())
}

pub(crate) struct Store {
    directory: File,
    owner: u32,
}

impl Store {
    /// Opens the fixed package-owned hierarchy. Read-only admission does not
    /// create directories, and a missing hierarchy means no old marker exists.
    pub(crate) fn production(create: bool) -> io::Result<Option<Self>> {
        if unsafe { libc::geteuid() } != 0 {
            return Err(failure(
                "generation admission requires the root lifecycle owner",
            ));
        }
        let mut directory = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open("/")?;
        validate_directory(&directory, 0, false)?;
        let components: Vec<&str> = PRODUCTION_STORE
            .trim_start_matches('/')
            .split('/')
            .collect();
        for (index, component) in components.iter().enumerate() {
            let component = CString::new(*component).expect("fixed path component");
            let private = index + 1 == components.len();
            let opened = openat_file(
                directory.as_raw_fd(),
                &component,
                libc::O_RDONLY | libc::O_DIRECTORY,
                0,
            );
            let next = match opened {
                Ok(file) => file,
                Err(error) if error.kind() == io::ErrorKind::NotFound && !create => {
                    return Ok(None);
                }
                Err(error) if error.kind() == io::ErrorKind::NotFound && create => {
                    let mode = if private { 0o700 } else { 0o755 };
                    // SAFETY: held parent and fixed component; no path traversal.
                    if unsafe { libc::mkdirat(directory.as_raw_fd(), component.as_ptr(), mode) }
                        != 0
                    {
                        let error = io::Error::last_os_error();
                        if error.kind() != io::ErrorKind::AlreadyExists {
                            return Err(error);
                        }
                    }
                    let file = openat_file(
                        directory.as_raw_fd(),
                        &component,
                        libc::O_RDONLY | libc::O_DIRECTORY,
                        0,
                    )?;
                    // Persist creation before any later namespace or network work.
                    directory.sync_all()?;
                    file
                }
                Err(error) => return Err(error),
            };
            validate_directory(&next, 0, private)?;
            directory = next;
        }
        Ok(Some(Self {
            directory,
            owner: 0,
        }))
    }

    pub(crate) fn require_unclaimed(&self, uid: u32) -> io::Result<()> {
        match openat_file(self.directory.as_raw_fd(), &name(uid), libc::O_PATH, 0) {
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(error),
            // Any existing inode, including a malformed marker or symlink,
            // denies recovery. Its contents can never grant admission.
            Ok(_) => Err(failure(
                "unfinished cell generation requires explicit retirement proof",
            )),
        }
    }

    /// Creates and persists the exclusion record before starting any resource.
    /// An I/O failure after O_EXCL intentionally leaves a blocking marker.
    pub(crate) fn claim(&self, uid: u32, record: &[u8]) -> io::Result<Claim> {
        if record.is_empty() || record.len() > 32 * 1024 {
            return Err(failure("generation record length is outside its bound"));
        }
        let marker_name = name(uid);
        let mut marker = openat_file(
            self.directory.as_raw_fd(),
            &marker_name,
            libc::O_RDWR | libc::O_CREAT | libc::O_EXCL,
            0o600,
        )?;
        let metadata = marker.metadata()?;
        if !metadata.is_file()
            || metadata.uid() != self.owner
            || metadata.nlink() != 1
            || metadata.mode() & 0o077 != 0
        {
            return Err(failure("new generation marker has unsafe ownership"));
        }
        marker.write_all(record)?;
        marker.sync_all()?;
        self.directory.sync_all()?;
        Ok(Claim {
            directory: self.directory.try_clone()?,
            marker,
            marker_name,
            identity: (metadata.dev(), metadata.ino()),
            owner: self.owner,
            record: record.to_vec(),
            released: false,
            release_failed: false,
        })
    }

    #[cfg(test)]
    fn test(directory: &Path) -> io::Result<Self> {
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(directory)?;
        let owner = unsafe { libc::geteuid() };
        validate_directory(&file, owner, true)?;
        Ok(Self {
            directory: file,
            owner,
        })
    }
}

pub(crate) fn require_no_pending_generation(uid: u32) -> io::Result<()> {
    match Store::production(false)? {
        Some(store) => store.require_unclaimed(uid),
        None => Ok(()),
    }
}

pub(crate) struct Claim {
    directory: File,
    marker: File,
    marker_name: CString,
    identity: (u64, u64),
    owner: u32,
    record: Vec<u8>,
    released: bool,
    release_failed: bool,
}

impl Claim {
    /// Internal final operation only: the caller must already have joined the
    /// exact broker, reaped owner/init, proved its held domain empty, and
    /// completed network/runtime cleanup. No fallible operation follows unlink.
    ///
    /// The callback keeps the final real retirement check inside this boundary.
    /// It must inspect owned handles; a status string or PID-number lookup is
    /// not a retirement proof.
    pub(crate) fn release_after(
        &mut self,
        prove_retired: impl FnOnce() -> io::Result<()>,
    ) -> io::Result<()> {
        if self.release_failed {
            return Err(failure("generation release is poisoned"));
        }
        if self.released {
            return Ok(());
        }
        let result = (|| {
            prove_retired()?;
            let named = openat_file(
                self.directory.as_raw_fd(),
                &self.marker_name,
                libc::O_RDONLY,
                0,
            )?;
            let metadata = named.metadata()?;
            let held = self.marker.metadata()?;
            if (metadata.dev(), metadata.ino()) != self.identity
                || (held.dev(), held.ino()) != self.identity
                || !metadata.is_file()
                || metadata.uid() != self.owner
                || metadata.nlink() != 1
                || metadata.mode() & 0o077 != 0
            {
                return Err(failure("generation marker identity changed"));
            }
            let mut bytes = Vec::new();
            named.take(32 * 1024 + 1).read_to_end(&mut bytes)?;
            if bytes != self.record {
                return Err(failure("generation record changed"));
            }
            // All fallible proof/cleanup work precedes this one final removal.
            // A power loss may resurrect an old marker (denying admission);
            // it cannot leave an old process alive across that reboot.
            if unsafe { libc::unlinkat(self.directory.as_raw_fd(), self.marker_name.as_ptr(), 0) }
                != 0
            {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        })();
        if result.is_ok() {
            self.released = true;
        } else {
            self.release_failed = true;
        }
        result
    }
}

// There is deliberately no Drop implementation that removes a marker.

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};
    use std::process::{Child, Command, Stdio};

    fn directory() -> tempfile::TempDir {
        let temp = tempfile::tempdir().unwrap();
        std::fs::set_permissions(temp.path(), std::fs::Permissions::from_mode(0o700)).unwrap();
        temp
    }
    struct OwnedChild(Child);
    impl std::ops::Deref for OwnedChild {
        type Target = Child;
        fn deref(&self) -> &Child {
            &self.0
        }
    }
    impl std::ops::DerefMut for OwnedChild {
        fn deref_mut(&mut self) -> &mut Child {
            &mut self.0
        }
    }
    impl Drop for OwnedChild {
        fn drop(&mut self) {
            if self.0.try_wait().ok().flatten().is_none() {
                let _ = self.0.kill();
            }
            let _ = self.0.wait();
        }
    }
    fn child() -> OwnedChild {
        OwnedChild(
            Command::new("/bin/sleep")
                .arg("30")
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap(),
        )
    }

    #[test]
    fn abandoned_claim_survives_handle_and_store_reconstruction() {
        let temp = directory();
        let store = Store::test(temp.path()).unwrap();
        let claim = store.claim(1000, b"generation A\n").unwrap();
        drop(claim);
        drop(store);
        let restarted = Store::test(temp.path()).unwrap();
        assert!(restarted.require_unclaimed(1000).is_err());
        assert!(restarted.claim(1000, b"generation B\n").is_err());
        assert_eq!(
            std::fs::read(temp.path().join("u1000.active")).unwrap(),
            b"generation A\n"
        );
    }

    #[test]
    fn live_owned_child_prevents_release_and_later_retry_stays_poisoned() {
        let temp = directory();
        let store = Store::test(temp.path()).unwrap();
        let mut claim = store.claim(1000, b"owned child generation\n").unwrap();
        let mut owned = child();
        assert!(
            claim
                .release_after(|| {
                    if owned.try_wait()?.is_none() {
                        return Err(failure("owned process still alive"));
                    }
                    Ok(())
                })
                .is_err()
        );
        owned.kill().unwrap();
        owned.wait().unwrap();
        assert!(claim.release_after(|| Ok(())).is_err());
        drop(claim);
        drop(store);
        assert!(
            Store::test(temp.path())
                .unwrap()
                .require_unclaimed(1000)
                .is_err()
        );
    }

    #[test]
    fn successful_owned_child_retirement_releases_exact_marker_once() {
        let temp = directory();
        let store = Store::test(temp.path()).unwrap();
        let mut claim = store.claim(1000, b"owned complete generation\n").unwrap();
        let mut owned = OwnedChild(Command::new("/bin/true").spawn().unwrap());
        let status = owned.wait().unwrap();
        assert!(status.success());
        claim
            .release_after(|| {
                if owned.try_wait()?.is_none() {
                    return Err(failure("owned child not reaped"));
                }
                Ok(())
            })
            .unwrap();
        claim
            .release_after(|| panic!("released proof must not rerun"))
            .unwrap();
        assert!(store.require_unclaimed(1000).is_ok());
        assert!(store.claim(1000, b"new generation\n").is_ok());
    }

    #[test]
    fn replacing_marker_inode_cannot_release_another_generation() {
        let temp = directory();
        let store = Store::test(temp.path()).unwrap();
        let mut claim = store.claim(1000, b"original\n").unwrap();
        std::fs::rename(
            temp.path().join("u1000.active"),
            temp.path().join("retained-original"),
        )
        .unwrap();
        let replacement = store.claim(1000, b"replacement\n").unwrap();
        assert!(claim.release_after(|| Ok(())).is_err());
        assert_eq!(
            std::fs::read(temp.path().join("u1000.active")).unwrap(),
            b"replacement\n"
        );
        drop(replacement);
    }

    #[test]
    fn symlink_or_malformed_existing_inode_never_grants_admission() {
        let temp = directory();
        let store = Store::test(temp.path()).unwrap();
        symlink("/missing", temp.path().join("u1000.active")).unwrap();
        assert!(store.require_unclaimed(1000).is_err());
        assert!(store.claim(1000, b"new\n").is_err());
        std::fs::remove_file(temp.path().join("u1000.active")).unwrap();
        std::fs::create_dir(temp.path().join("u1000.active")).unwrap();
        assert!(store.require_unclaimed(1000).is_err());
    }

    #[test]
    fn private_owner_directory_and_record_bounds_are_required() {
        let temp = directory();
        std::fs::set_permissions(temp.path(), std::fs::Permissions::from_mode(0o777)).unwrap();
        assert!(Store::test(temp.path()).is_err());
        std::fs::set_permissions(temp.path(), std::fs::Permissions::from_mode(0o700)).unwrap();
        let store = Store::test(temp.path()).unwrap();
        assert!(store.claim(1000, b"").is_err());
        assert!(store.claim(1000, &vec![0; 32769]).is_err());
        assert!(store.require_unclaimed(1000).is_ok());
    }
}
