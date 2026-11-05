//! Application-owned durable Notes data and an observation-only recovery path.
//!
//! The original Hepta writer still owns authorization, operation history and
//! terminal state. This store keeps exactly the document and the protocol's
//! one unacknowledged receipt. Reopening an old incarnation permits observation
//! and exact retirement only; it never restores an effect capability.

use crate::app_checkpoint_store::{
    lock_directory, open_file, open_root, replace_checkpoint, IncarnationLock, Mode,
    MAX_CHECKPOINT_BYTES,
};
use crate::notes::{sha256_hex, NotesDocument, NotesResponse, NotesTargetIdentity};
use std::fs::{self, File};
use std::io::{self, Read};
use std::path::Path;
use std::time::UNIX_EPOCH;

pub const MAX_SAVED_NOTES: usize = 64;
const MAX_CATALOG_ENTRIES: usize = 4096;

/// A bounded selection of user text, not an effect capability. Reopening must
/// revalidate the source incarnation, revision and digest under its lock.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SavedNotesDocument {
    pub target: NotesTargetIdentity,
    pub revision: u64,
    pub text_sha256: String,
    pub preview: String,
    pub saved_unix_ms: u64,
}

#[derive(Clone, Debug, Default)]
pub struct SavedNotesListing {
    pub documents: Vec<SavedNotesDocument>,
    /// Locked, incomplete or invalid entries are not offered as documents.
    pub unavailable: usize,
    /// The fixed scan or presentation limit was reached; no completeness claim.
    pub truncated: bool,
}

/// One exclusively locked application incarnation. File/directory errors
/// freeze the instance because a failed sync can have an uncertain outcome.
/// The caller must then close it and recover from the original on-disk state.
pub struct NotesStore {
    directory: File,
    _lock: IncarnationLock,
    document: NotesDocument,
    mode: Mode,
    frozen: bool,
}

impl NotesStore {
    /// Preflight only: the existing canonical private storage root is opened
    /// with the original UID/directory guards. No document or lock is created.
    pub fn validate_existing_storage_root(root: &Path) -> io::Result<()> {
        if root.canonicalize()? != root {
            return Err(io::Error::other("Notes storage root must be canonical"));
        }
        let _directory = open_root(root, false)?;
        Ok(())
    }
    /// Create a fresh incarnation. Existing names are never reset or adopted,
    /// including a partially created directory left by a crashed predecessor.
    pub fn create(root: &Path, target: NotesTargetIdentity) -> io::Result<Self> {
        let document = NotesDocument::new(target.clone()).map_err(protocol_error)?;
        let directory = open_directory(root, &target, Mode::Application)?;
        let lock = lock_directory(&directory)?;
        let mut store = Self {
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
        let directory = open_directory(root, target, Mode::RecoveryOnly)?;
        let lock = lock_directory(&directory)?;
        let file = open_file(&directory, "document.json", libc::O_RDONLY)?;
        let mut raw = Vec::new();
        file.take(MAX_CHECKPOINT_BYTES + 1).read_to_end(&mut raw)?;
        let document = NotesDocument::restore_checkpoint(&raw, target).map_err(protocol_error)?;
        Ok(Self {
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

    pub fn target(&self) -> &NotesTargetIdentity {
        self.document.target()
    }

    pub fn revision(&self) -> u64 {
        self.document.revision()
    }

    pub fn is_frozen(&self) -> bool {
        self.frozen
    }

    /// Enumerate closed, validated application documents on this account.
    /// No checkpoint or receipt is modified. The current incarnation is never
    /// offered, and a live app/recovery helper retains its exclusive lock.
    /// This bounded filesystem operation belongs on a worker, not Draw.
    pub fn saved_documents(
        root: &Path,
        current: &NotesTargetIdentity,
    ) -> io::Result<SavedNotesListing> {
        current.validate().map_err(protocol_error)?;
        let _root = open_root(root, false)?;
        let mut listing = SavedNotesListing::default();
        for (index, entry) in fs::read_dir(root)?.enumerate() {
            if index >= MAX_CATALOG_ENTRIES {
                listing.truncated = true;
                break;
            }
            let entry = entry?;
            let Some(target) = identity_from_directory(&entry.file_name()) else {
                listing.unavailable += 1;
                continue;
            };
            if &target == current {
                continue;
            }
            let result = Self::recover(root, &target).and_then(|store| {
                let file = open_file(&store.directory, "document.json", libc::O_RDONLY)?;
                let saved = file
                    .metadata()?
                    .modified()?
                    .duration_since(UNIX_EPOCH)
                    .map_err(io::Error::other)?;
                Ok(SavedNotesDocument {
                    target,
                    revision: store.revision(),
                    text_sha256: sha256_hex(store.text().as_bytes()),
                    preview: store
                        .text()
                        .lines()
                        .next()
                        .unwrap_or("")
                        .chars()
                        .take(80)
                        .collect(),
                    saved_unix_ms: u64::try_from(saved.as_millis()).unwrap_or(u64::MAX),
                })
            });
            match result {
                // Empty windows that have never been edited are not saved work.
                Ok(document) if document.revision != 0 => listing.documents.push(document),
                Ok(_) => {}
                Err(_) => listing.unavailable += 1,
            }
        }
        listing.documents.sort_by(|left, right| {
            right.saved_unix_ms.cmp(&left.saved_unix_ms).then_with(|| {
                left.target
                    .destination_id()
                    .cmp(&right.target.destination_id())
            })
        });
        if listing.documents.len() > MAX_SAVED_NOTES {
            listing.documents.truncate(MAX_SAVED_NOTES);
            listing.truncated = true;
        }
        Ok(listing)
    }

    /// Explicitly copy saved text into this new, still-empty incarnation.
    /// Only text is copied: authorization, effect/retirement receipts and the
    /// old revision domain remain with the old target and original Hepta owner.
    /// The selected source is re-read under its lock, so a stale selection,
    /// live predecessor or intervening current edit cannot be overwritten.
    pub fn restore_saved_text(
        &mut self,
        root: &Path,
        source: &SavedNotesDocument,
        expected_revision: u64,
    ) -> io::Result<()> {
        self.require_application()?;
        if expected_revision != 0
            || self.document.revision() != expected_revision
            || !self.document.text().is_empty()
            || &source.target == self.document.target()
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "Saved Notes can only be opened in a new, unedited incarnation",
            ));
        }
        let previous = Self::recover(root, &source.target)?;
        if previous.revision() != source.revision
            || sha256_hex(previous.text().as_bytes()) != source.text_sha256
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Saved Notes changed after selection; refresh the document list",
            ));
        }
        // Start from a fresh model instead of cloning the old checkpoint.
        let mut next =
            NotesDocument::new(self.document.target().clone()).map_err(protocol_error)?;
        next.local_edit(previous.text().to_owned())
            .map_err(protocol_error)?;
        self.commit(next)
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

fn open_directory(root: &Path, target: &NotesTargetIdentity, mode: Mode) -> io::Result<File> {
    crate::app_checkpoint_store::open_directory(
        root,
        &format!(
            "{}-{}-{}",
            target.session_instance, target.task_id, target.incarnation
        ),
        mode,
    )
}

fn identity_from_directory(name: &std::ffi::OsStr) -> Option<NotesTargetIdentity> {
    let name = name.to_str()?;
    let mut parts = name.split('-');
    let target = NotesTargetIdentity {
        session_instance: parts.next()?.to_owned(),
        task_id: parts.next()?.parse().ok()?,
        incarnation: parts.next()?.to_owned(),
    };
    if parts.next().is_some()
        || target.validate().is_err()
        || name
            != format!(
                "{}-{}-{}",
                target.session_instance, target.task_id, target.incarnation
            )
    {
        return None;
    }
    Some(target)
}

#[cfg(test)]
#[path = "notes_store_lock_tests.rs"]
mod lock_tests;
