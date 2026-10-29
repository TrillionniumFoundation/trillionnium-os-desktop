//! Private client retention, never the original owner's publication ledger.
//! The one-way marker is durable before any transport attempt. It is never
//! deleted/rearmed by this API, even when a reply says zero bytes were written.
use serde::{Deserialize, Serialize};
use std::ffi::CString;
use std::fs::File;
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path, PathBuf};
use trill_ui_core::notes::sha256_hex;

const MAX_BYTES: u64 = 96 * 1024;
fn bad() -> io::Error {
    io::Error::other("objective private client retention invalid")
}
pub struct PrivateDirectory {
    dir: File,
    path: PathBuf,
}
impl PrivateDirectory {
    pub fn open(path: &Path) -> io::Result<Self> {
        if !path.is_absolute() {
            return Err(bad());
        }
        let mut file = File::open("/")?;
        for part in path.components() {
            match part {
                Component::RootDir => {}
                Component::Normal(name) => {
                    use std::os::unix::ffi::OsStrExt;
                    let name = CString::new(name.as_bytes()).map_err(|_| bad())?;
                    let fd = unsafe {
                        libc::openat(
                            file.as_raw_fd(),
                            name.as_ptr(),
                            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                        )
                    };
                    if fd < 0 {
                        return Err(io::Error::last_os_error());
                    }
                    file = unsafe { File::from_raw_fd(fd) };
                }
                _ => return Err(bad()),
            }
        }
        let m = file.metadata()?;
        if !m.is_dir()
            || m.uid() != trill_ui_core::host_peer::current_effective_uid()
            || m.mode() & 0o777 != 0o700
        {
            return Err(bad());
        }
        Ok(Self {
            dir: file,
            path: path.to_owned(),
        })
    }
    fn verify_live(&self) -> io::Result<()> {
        let reopened = Self::open(&self.path)?;
        let before = self.dir.metadata()?;
        let now = reopened.dir.metadata()?;
        if before.dev() != now.dev() || before.ino() != now.ino() {
            return Err(bad());
        }
        Ok(())
    }
    fn open_file(&self, name: &str, flags: i32) -> io::Result<File> {
        if name.is_empty()
            || name.contains('/')
            || name.contains('\0')
            || name == "."
            || name == ".."
        {
            return Err(bad());
        }
        let name = CString::new(name).map_err(|_| bad())?;
        let fd = unsafe {
            libc::openat(
                self.dir.as_raw_fd(),
                name.as_ptr(),
                flags | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
                0o600,
            )
        };
        if fd < 0 {
            return Err(io::Error::last_os_error());
        }
        let file = unsafe { File::from_raw_fd(fd) };
        let m = file.metadata()?;
        if !m.is_file()
            || m.uid() != trill_ui_core::host_peer::current_effective_uid()
            || m.mode() & 0o777 != 0o600
            || m.nlink() != 1
            || m.len() > MAX_BYTES
        {
            return Err(bad());
        }
        Ok(file)
    }
    fn read(&self, name: &str) -> io::Result<Vec<u8>> {
        let mut bytes = Vec::new();
        self.open_file(name, libc::O_RDONLY)?
            .take(MAX_BYTES + 1)
            .read_to_end(&mut bytes)?;
        if bytes.len() as u64 > MAX_BYTES {
            return Err(bad());
        }
        Ok(bytes)
    }
}
pub fn read_private(path: &Path) -> io::Result<String> {
    let parent = PrivateDirectory::open(path.parent().ok_or_else(bad)?)?;
    String::from_utf8(parent.read(path.file_name().and_then(|v| v.to_str()).ok_or_else(bad)?)?)
        .map_err(|_| bad())
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Marker {
    schema_version: u16,
    owner_agent_id: String,
    attempt_identity: String,
    envelope_sha256: String,
    envelope_raw: String,
}
pub struct Retention {
    directory: PrivateDirectory,
    _lock: File,
    poisoned: bool,
}
impl Retention {
    pub fn open(path: &Path) -> io::Result<Self> {
        let directory = PrivateDirectory::open(path)?;
        let lock = directory.open_file("objective-client.lock", libc::O_RDWR | libc::O_CREAT)?;
        if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(Self {
            directory,
            _lock: lock,
            poisoned: false,
        })
    }
    fn verify_live(&self) -> io::Result<()> {
        self.directory.verify_live()?;
        let reopened = self
            .directory
            .open_file("objective-client.lock", libc::O_RDONLY)?;
        let before = self._lock.metadata()?;
        let now = reopened.metadata()?;
        if before.dev() != now.dev() || before.ino() != now.ino() {
            return Err(bad());
        }
        Ok(())
    }
    pub fn was_attempted(&self, owner: &str, identity: &str, raw: &str) -> io::Result<bool> {
        self.verify_live()?;
        if identity.len() != 64
            || !identity
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err(bad());
        }
        let hash = sha256_hex(raw.as_bytes());
        let bytes = match self.directory.read(&format!("{identity}.attempt")) {
            Ok(b) => b,
            Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(false),
            Err(e) => return Err(e),
        };
        let marker: Marker = serde_json::from_slice(&bytes).map_err(|_| bad())?;
        if marker.schema_version != 1
            || marker.owner_agent_id != owner
            || marker.attempt_identity != identity
            || marker.envelope_sha256 != hash
            || marker.envelope_raw != raw
        {
            return Err(bad());
        }
        Ok(true)
    }
    pub fn begin_once(&mut self, owner: &str, identity: &str, raw: &str) -> io::Result<()> {
        if self.poisoned || self.was_attempted(owner, identity, raw)? {
            return Err(bad());
        }
        let hash = sha256_hex(raw.as_bytes());
        let marker = serde_json::to_vec(&Marker {
            schema_version: 1,
            owner_agent_id: owner.into(),
            attempt_identity: identity.into(),
            envelope_sha256: hash,
            envelope_raw: raw.into(),
        })
        .map_err(io::Error::other)?;
        if marker.len() as u64 > MAX_BYTES {
            return Err(bad());
        }
        let mut nonce = [0; 16];
        File::open("/dev/urandom")?.read_exact(&mut nonce)?;
        let temporary = format!("{}.pending", trill_ui_core::desktop::encode_hex(&nonce));
        let result = (|| -> io::Result<()> {
            let mut file = self
                .directory
                .open_file(&temporary, libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL)?;
            file.write_all(&marker)?;
            file.sync_all()?;
            let old = CString::new(temporary.as_str()).map_err(|_| bad())?;
            let new = CString::new(format!("{identity}.attempt")).map_err(|_| bad())?;
            if unsafe {
                libc::renameat2(
                    self.directory.dir.as_raw_fd(),
                    old.as_ptr(),
                    self.directory.dir.as_raw_fd(),
                    new.as_ptr(),
                    libc::RENAME_NOREPLACE,
                )
            } != 0
            {
                return Err(io::Error::last_os_error());
            }
            self.directory.dir.sync_all()?;
            self.verify_live()?;
            Ok(())
        })();
        if result.is_err() {
            self.poisoned = true;
        }
        result
    }
}

#[cfg(test)]
pub(super) mod tests {
    use super::*;
    use std::fs::{self, DirBuilder, OpenOptions};
    use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt};
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(1);
    pub struct Root(pub PathBuf);
    impl Root {
        pub fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "objective-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            DirBuilder::new().mode(0o700).create(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Root {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    pub fn write(path: &Path, raw: &[u8]) {
        let mut f = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(path)
            .unwrap();
        f.write_all(raw).unwrap();
    }
    fn reopen_after_exec(path: &Path) -> Retention {
        // Other parallel Session tests fork real children. CLOEXEC descriptors
        // can transiently share this flock between fork and exec; closing our
        // File alone does not prove that every inherited description is gone.
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(3);
        loop {
            match Retention::open(path) {
                Ok(retained) => return retained,
                Err(e)
                    if e.kind() == io::ErrorKind::WouldBlock
                        && std::time::Instant::now() < deadline =>
                {
                    std::thread::sleep(std::time::Duration::from_millis(5))
                }
                Err(e) => panic!("retention reopen failed: {e}"),
            }
        }
    }
    #[test]
    fn atomic_marker_survives_reopen_and_never_rearms() {
        let root = Root::new();
        let raw = "original exact bytes";
        let mut retained = Retention::open(&root.0).unwrap();
        assert!(!retained
            .was_attempted("owner", &sha256_hex(b"identity"), raw)
            .unwrap());
        retained
            .begin_once("owner", &sha256_hex(b"identity"), raw)
            .unwrap();
        assert!(retained
            .begin_once("owner", &sha256_hex(b"identity"), raw)
            .is_err());
        assert!(Retention::open(&root.0).is_err());
        drop(retained);
        let retained = reopen_after_exec(&root.0);
        assert!(retained
            .was_attempted("owner", &sha256_hex(b"identity"), raw)
            .unwrap());
        assert!(retained
            .was_attempted("different-owner", &sha256_hex(b"identity"), raw)
            .is_err());
        assert!(!retained
            .was_attempted(
                "owner",
                &sha256_hex(b"other identity"),
                "different exact bytes"
            )
            .unwrap());
    }
    #[test]
    fn no_symlink_hardlink_or_public_directory_envelope() {
        let root = Root::new();
        let file = root.0.join("original");
        write(&file, b"original");
        assert_eq!(read_private(&file).unwrap(), "original");
        std::os::unix::fs::symlink(&file, root.0.join("link")).unwrap();
        assert!(read_private(&root.0.join("link")).is_err());
        fs::hard_link(&file, root.0.join("hard")).unwrap();
        assert!(read_private(&file).is_err());
        fs::remove_file(root.0.join("hard")).unwrap();
        fs::set_permissions(&root.0, fs::Permissions::from_mode(0o755)).unwrap();
        assert!(read_private(&file).is_err());
    }
    #[test]
    fn replaced_lock_fails_before_marker_publication() {
        let root = Root::new();
        let mut retained = Retention::open(&root.0).unwrap();
        fs::remove_file(root.0.join("objective-client.lock")).unwrap();
        write(&root.0.join("objective-client.lock"), b"");
        assert!(retained
            .begin_once("owner", &sha256_hex(b"identity"), "raw")
            .is_err());
        assert!(!root
            .0
            .join(format!("{}.attempt", sha256_hex(b"identity")))
            .exists());
    }
    #[test]
    fn replacement_directory_is_detected() {
        let root = Root::new();
        let original = root.0.join("retained");
        DirBuilder::new().mode(0o700).create(&original).unwrap();
        let mut retained = Retention::open(&original).unwrap();
        fs::rename(&original, root.0.join("old")).unwrap();
        DirBuilder::new().mode(0o700).create(&original).unwrap();
        assert!(retained
            .begin_once("owner", &sha256_hex(b"identity"), "raw")
            .is_err());
    }
    #[test]
    fn corrupted_marker_is_never_treated_as_no_attempt() {
        let root = Root::new();
        let mut retained = Retention::open(&root.0).unwrap();
        retained
            .begin_once("owner", &sha256_hex(b"identity"), "raw")
            .unwrap();
        drop(retained);
        fs::write(
            root.0.join(format!("{}.attempt", sha256_hex(b"identity"))),
            b"{}",
        )
        .unwrap();
        assert!(reopen_after_exec(&root.0)
            .was_attempted("owner", &sha256_hex(b"identity"), "raw")
            .is_err());
    }
}
