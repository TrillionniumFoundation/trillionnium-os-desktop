//! Application-owned durable Notes data and an observation-only recovery path.
//!
//! The original Hepta writer still owns authorization, operation history and
//! terminal state. This store keeps exactly the document and the protocol's
//! one unacknowledged receipt. Reopening an old incarnation permits observation
//! and exact retirement only; it never restores an effect capability.

use crate::notes::{NotesDocument, NotesResponse, NotesTargetIdentity};
use std::ffi::CString;
use std::fs::{self, DirBuilder, File};
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt};
use std::path::Path;

#[path = "notes_catalog.rs"]
mod catalog;
pub use catalog::{SavedNote, SavedNotes};

const MAX_CHECKPOINT_BYTES: u64 = 16 * 1024;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Mode {
    Application,
    RecoveryOnly,
}

/// One exclusively locked application incarnation. File/directory errors
/// freeze the instance because a failed sync can have an uncertain outcome.
/// The caller must then close it and recover from the original on-disk state.
pub struct NotesStore {
    root_directory: File,
    directory: File,
    _lock: File,
    document: NotesDocument,
    mode: Mode,
    frozen: bool,
}

impl NotesStore {
    /// Create a fresh incarnation. Existing names are never reset or adopted,
    /// including a partially created directory left by a crashed predecessor.
    pub fn create(root: &Path, target: NotesTargetIdentity) -> io::Result<Self> {
        let document = NotesDocument::new(target.clone()).map_err(protocol_error)?;
        let (root_directory, directory) = open_directory(root, &target, Mode::Application)?;
        let lock = lock_directory(&directory)?;
        let mut store = Self {
            root_directory,
            directory,
            _lock: lock,
            document,
            mode: Mode::Application,
            frozen: false,
        };
        let bytes = store.document.checkpoint().map_err(protocol_error)?;
        store.persist(&bytes)?;
        Ok(store)
    }

    /// Open an exited incarnation for independent reconciliation. A live
    /// application or another recovery process retains the same exclusive lock.
    pub fn recover(root: &Path, target: &NotesTargetIdentity) -> io::Result<Self> {
        target.validate().map_err(protocol_error)?;
        let (root_directory, directory) = open_directory(root, target, Mode::RecoveryOnly)?;
        let lock = lock_directory(&directory)?;
        let file = open_file(&directory, "document.json", libc::O_RDONLY)?;
        let mut raw = Vec::new();
        file.take(MAX_CHECKPOINT_BYTES + 1).read_to_end(&mut raw)?;
        let document = NotesDocument::restore_checkpoint(&raw, target).map_err(protocol_error)?;
        Ok(Self {
            root_directory,
            directory,
            _lock: lock,
            document,
            mode: Mode::RecoveryOnly,
            frozen: false,
        })
    }

    pub fn text(&self) -> &str {
        self.document.text()
    }

    pub fn revision(&self) -> u64 {
        self.document.revision()
    }

    pub fn is_frozen(&self) -> bool {
        self.frozen
    }

    /// List closed notes in this store's already-open private state directory.
    /// This projection contains no effect receipt or reusable authority.
    pub fn saved_notes(&self) -> io::Result<SavedNotes> {
        self.require_application()?;
        catalog::list(&self.root_directory, self.document.target())
    }

    /// Explicitly copy a selected saved text into this fresh incarnation.
    /// The predecessor remains untouched, including any pending receipt. A
    /// new local revision is saved under this application's original target.
    pub fn reopen_text(&mut self, source: &SavedNote, expected_revision: u64) -> io::Result<()> {
        self.require_application()?;
        if expected_revision != 0
            || self.document.revision() != expected_revision
            || !self.document.text().is_empty()
            || self.document.target() == &source.target
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "reopen requires this fresh, unchanged empty note",
            ));
        }
        let saved = catalog::read(&self.root_directory, &source.target)?;
        if saved.reference.checkpoint_sha256 != source.checkpoint_sha256
            || saved.reference.revision != source.revision
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "saved note changed; refresh before reopening",
            ));
        }
        // Do not restore_checkpoint into this live application: that would
        // import the predecessor's target, revision and effect receipts.
        self.local_edit(saved.text)
    }

    /// Return Applied only after the text and original receipt are durable.
    pub fn apply_exact(&mut self, raw: &[u8]) -> io::Result<NotesResponse> {
        self.require_application()?;
        let mut next = self.document.clone();
        let receipt = next.apply_exact(raw).map_err(protocol_error)?;
        self.commit(next)?;
        Ok(receipt)
    }

    /// A local edit participates in the same persisted CAS revision domain.
    pub fn local_edit(&mut self, text: String) -> io::Result<()> {
        self.require_application()?;
        let mut next = self.document.clone();
        next.local_edit(text).map_err(protocol_error)?;
        self.commit(next)
    }

    /// Only Observe and exact original-owner retirement are parsed here.
    /// An old mutation frame is rejected, even after an application restart.
    pub fn recovery_exact(&mut self, raw: &[u8]) -> io::Result<Vec<u8>> {
        self.require_available()?;
        let mut next = self.document.clone();
        let response = next.recovery_exact(raw).map_err(protocol_error)?;
        self.commit(next)?;
        Ok(response)
    }

    fn require_application(&self) -> io::Result<()> {
        self.require_available()?;
        if self.mode != Mode::Application {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "recovered Notes incarnation is observation-only",
            ));
        }
        Ok(())
    }

    fn require_available(&self) -> io::Result<()> {
        if self.frozen {
            return Err(io::Error::other("Notes storage outcome requires recovery"));
        }
        Ok(())
    }

    fn commit(&mut self, next: NotesDocument) -> io::Result<()> {
        let bytes = next.checkpoint().map_err(protocol_error)?;
        if bytes != self.document.checkpoint().map_err(protocol_error)? {
            self.persist(&bytes)?;
        }
        self.document = next;
        Ok(())
    }

    fn persist(&mut self, bytes: &[u8]) -> io::Result<()> {
        let result = replace_checkpoint(&self.directory, bytes);
        if result.is_err() {
            self.frozen = true;
        }
        result
    }
}

fn protocol_error(error: crate::notes::NotesProtocolError) -> io::Error {
    io::Error::new(
        io::ErrorKind::InvalidData,
        format!("Notes protocol: {error:?}"),
    )
}

fn private_directory(file: &File) -> io::Result<()> {
    let metadata = file.metadata()?;
    if !metadata.is_dir()
        || metadata.uid() != unsafe { libc::geteuid() }
        || metadata.mode() & 0o077 != 0
    {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Notes data directory must be private and owned by this account",
        ));
    }
    Ok(())
}

fn open_directory(
    root: &Path,
    target: &NotesTargetIdentity,
    mode: Mode,
) -> io::Result<(File, File)> {
    if !root.is_absolute() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Notes state path must be absolute",
        ));
    }
    if mode == Mode::Application {
        match DirBuilder::new().mode(0o700).create(root) {
            Ok(()) => {
                let parent = root
                    .parent()
                    .ok_or_else(|| io::Error::other("Notes state parent"))?;
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
    let directory = open_incarnation(&parent, target, mode == Mode::Application)?;
    Ok((parent, directory))
}

fn open_incarnation(parent: &File, target: &NotesTargetIdentity, create: bool) -> io::Result<File> {
    target.validate().map_err(protocol_error)?;
    // Every component is derived from a validated, bounded typed identity.
    let name = CString::new(format!(
        "{}-{}-{}",
        target.session_instance, target.task_id, target.incarnation
    ))?;
    if create {
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

fn open_file(directory: &File, name: &str, flags: libc::c_int) -> io::Result<File> {
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
            "Notes state file custody",
        ));
    }
    Ok(file)
}

fn lock_directory(directory: &File) -> io::Result<File> {
    let lock = open_file(directory, "lock", libc::O_RDWR | libc::O_CREAT)?;
    if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(lock)
}

fn replace_checkpoint(directory: &File, bytes: &[u8]) -> io::Result<()> {
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
