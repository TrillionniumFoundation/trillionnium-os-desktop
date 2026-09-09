//! Opt-in, append-only directory commit protocol for a complete receipt chain.
//!
//! Canonical numbered segment names are the chain-head record. A successor is
//! an immutable, fully synced header until its atomic rename and directory sync
//! complete. There is no mutable path list that can silently omit a successor.
//! This is local crash consistency, not authenticated anti-rollback storage.
use super::*;
use std::os::unix::fs::{DirBuilderExt, FileExt};

#[path = "migration.rs"]
mod migration;
pub use migration::{CopiedReceiptSegment, ReceiptMigrationReport};

const MARKER: &str = "store.v1";
const MAGIC: &[u8; 8] = b"HPTSTR01";
const MARKER_BYTES: usize = 56;
const PENDING: &str = "next.pending";
/// Conservative automatic service rotation trigger; hard chain bounds still apply.
pub const MANAGED_ROTATION_THRESHOLD_BYTES: u64 = 4 * 1024 * 1024;

/// Completing a fully prepared rotation is distinct from repairing record tails.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ManagedOpenPolicy {
    pub journal: OpenPolicy,
    pub complete_pending_rotation: bool,
}
impl ManagedOpenPolicy {
    pub const STRICT: Self = Self {
        journal: OpenPolicy::STRICT,
        complete_pending_rotation: false,
    };
    pub const RECOVER_CRASH: Self = Self {
        journal: OpenPolicy::RECOVER_CRASH,
        complete_pending_rotation: true,
    };
}

pub(super) struct ManagedDirectory {
    root: PathBuf,
    directory: File,
    identity: (u64, u64),
    marker: File,
    marker_identity: (u64, u64),
    marker_bytes: [u8; MARKER_BYTES],
    segments: usize,
}

fn invalid(reason: &str) -> JournalError {
    JournalError::InvalidInput(format!("managed journal: {reason}"))
}
fn segment_name(number: usize) -> String {
    format!("segment-{number:016}.journal")
}
fn marker_bytes(id: JournalId) -> [u8; MARKER_BYTES] {
    let mut bytes = [0; MARKER_BYTES];
    bytes[..8].copy_from_slice(MAGIC);
    bytes[8..24].copy_from_slice(&id.0);
    let digest = sha256(&bytes[..24]);
    bytes[24..].copy_from_slice(&digest);
    bytes
}
fn identity(metadata: &fs::Metadata) -> (u64, u64) {
    (metadata.dev(), metadata.ino())
}
fn validate_root_name(root: &Path) -> Result<(), JournalError> {
    // Require canonical absolute UTF-8 paths; do not canonicalize through links.
    let text = root.to_str().ok_or_else(|| invalid("root must be UTF-8"))?;
    if !root.is_absolute()
        || text.len() > 4000
        || text[1..]
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
        || text.chars().any(|c| c.is_control() || c.is_whitespace())
    {
        return Err(invalid("root must be a bounded canonical absolute path"));
    }
    Ok(())
}
fn directory_metadata(root: &Path) -> Result<fs::Metadata, JournalError> {
    validate_root_name(root)?;
    validate_parent_components(&root.join(MARKER))?;
    let metadata = fs::symlink_metadata(root).map_err(map_io_error)?;
    if !metadata.is_dir()
        || metadata.file_type().is_symlink()
        || metadata.permissions().mode() & 0o077 != 0
    {
        return Err(invalid("root must be a private non-symlink directory"));
    }
    Ok(metadata)
}
fn lock_directory(root: &Path) -> Result<(File, (u64, u64)), JournalError> {
    let expected = identity(&directory_metadata(root)?);
    let directory = OpenOptions::new()
        .read(true)
        .custom_flags(OPEN_NOFOLLOW_FLAG)
        .open(root)
        .map_err(map_io_error)?;
    let metadata = directory.metadata().map_err(map_io_error)?;
    if !metadata.is_dir() || identity(&metadata) != expected {
        return Err(invalid("directory changed while opening"));
    }
    lock_file(&directory)?;
    if identity(&directory_metadata(root)?) != expected {
        return Err(invalid("directory changed while locking"));
    }
    Ok((directory, expected))
}

impl ManagedDirectory {
    fn acquire(root: &Path, id: JournalId) -> Result<Self, JournalError> {
        id.validate()?;
        let (directory, directory_id) = lock_directory(root)?;
        let marker_identity = validate_existing_path_identity(&root.join(MARKER))?;
        let marker = open_existing_file_checked(&root.join(MARKER), false, marker_identity)?;
        let this = Self {
            root: root.to_owned(),
            directory,
            identity: directory_id,
            marker,
            marker_identity,
            marker_bytes: marker_bytes(id),
            segments: 0,
        };
        this.verify_anchor()?;
        Ok(this)
    }

    fn verify_anchor(&self) -> Result<(), JournalError> {
        if identity(&directory_metadata(&self.root)?) != self.identity
            || identity(&self.directory.metadata().map_err(map_io_error)?) != self.identity
            || validate_existing_path_identity(&self.root.join(MARKER))? != self.marker_identity
        {
            return Err(invalid("pinned directory or marker identity changed"));
        }
        let metadata = self.marker.metadata().map_err(map_io_error)?;
        if !metadata_matches_identity(&metadata, self.marker_identity)
            || metadata.len() != MARKER_BYTES as u64
        {
            return Err(invalid("marker metadata changed"));
        }
        let mut bytes = [0; MARKER_BYTES];
        self.marker
            .read_exact_at(&mut bytes, 0)
            .map_err(map_io_error)?;
        if bytes != self.marker_bytes {
            return Err(invalid("marker version, identity or digest mismatch"));
        }
        Ok(())
    }

    // The complete directory inventory is bounded and closed, not a glob that
    // skips suspicious names. Symlinks/aliases are checked before any recovery.
    fn inventory(&self) -> Result<(Vec<PathBuf>, bool), JournalError> {
        self.verify_anchor()?;
        let mut names = std::collections::BTreeSet::new();
        let mut pending = false;
        let mut marker = false;
        for (count, entry) in fs::read_dir(&self.root).map_err(map_io_error)?.enumerate() {
            if count >= MAX_CHAIN_SEGMENTS + 2 {
                return Err(invalid("directory entry bound exceeded"));
            }
            let entry = entry.map_err(map_io_error)?;
            validate_existing_path_identity(&entry.path())?;
            let name = entry
                .file_name()
                .into_string()
                .map_err(|_| invalid("non-UTF-8 entry"))?;
            if name == MARKER {
                marker = true;
            } else if name == PENDING {
                pending = true;
            } else {
                names.insert(name);
            }
        }
        if !marker || names.len() > MAX_CHAIN_SEGMENTS {
            return Err(invalid("marker missing or segment bound exceeded"));
        }
        let mut paths = Vec::with_capacity(names.len());
        for (index, name) in names.iter().enumerate() {
            if *name != segment_name(index + 1) {
                return Err(invalid("unknown entry, gap or noncanonical segment number"));
            }
            paths.push(self.root.join(name));
        }
        self.verify_anchor()?;
        Ok((paths, pending))
    }

    pub(super) fn verify_current(&self) -> Result<(), JournalError> {
        let (paths, pending) = self.inventory()?;
        if pending || paths.len() != self.segments {
            return Err(invalid("committed head inventory changed while open"));
        }
        Ok(())
    }

    // A canonical filename observed after a process crash does not certify that
    // the previous writer completed its rename/directory barrier. Likewise a
    // complete last record may only have reached the page cache before an error.
    // Re-establish durability under all locks before accepting another writer.
    fn stabilize_open(&self, next: &mut ReceiptJournal) -> Result<(), JournalError> {
        self.verify_current()?;
        next.check_live_state()?;
        #[cfg(test)]
        persistence_tests::point("reopen.before_active_sync")?;
        next.file.sync_all().map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("reopen.after_active_sync")?;
        #[cfg(test)]
        persistence_tests::point("reopen.before_directory_sync")?;
        self.directory.sync_all().map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("reopen.after_directory_sync")?;
        self.verify_current()?;
        next.check_live_state()?;
        Ok(())
    }

    fn publish(&mut self, next: &mut ReceiptJournal) -> Result<(), JournalError> {
        let (paths, pending) = self.inventory()?;
        if !pending
            || paths.len() != self.segments
            || self.segments >= MAX_CHAIN_SEGMENTS
            || next.path != self.root.join(PENDING)
            || next.header.segment_number != (self.segments + 1) as u64
            || next.end_offset != SEGMENT_HEADER_LEN as u64
        {
            return Err(invalid("pending successor identity/inventory mismatch"));
        }
        next.check_live_state()?;
        let report = next.inspect()?;
        if report.tail != TailStatus::Clean || !report.records.is_empty() {
            return Err(invalid(
                "pending successor must be one complete header only",
            ));
        }
        #[cfg(test)]
        persistence_tests::point("publish.before_file_sync")?;
        next.file.sync_all().map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("publish.after_file_sync")?;
        self.verify_anchor()?;
        let final_path = self.root.join(segment_name(self.segments + 1));
        // The pinned private directory and all inode locks serialize cooperating
        // writers. A same-UID actor that ignores locks is outside authenticity
        // guarantees; the strict inventory is rechecked before/after publication.
        match fs::symlink_metadata(&final_path) {
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            _ => {
                return Err(invalid(
                    "successor destination already exists or cannot be checked",
                ));
            }
        }
        #[cfg(test)]
        persistence_tests::point("publish.before_rename")?;
        fs::rename(&next.path, &final_path).map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("publish.after_rename")?;
        next.path = final_path;
        #[cfg(test)]
        persistence_tests::point("publish.before_directory_sync")?;
        self.directory.sync_all().map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("publish.after_directory_sync")?;
        self.segments += 1;
        self.verify_current()?;
        next.check_live_state()?;
        Ok(())
    }
}

pub(super) fn reject_unmanaged_access(path: &Path) -> Result<(), JournalError> {
    if let Some(parent) = path.parent() {
        for name in [MARKER, migration::MIGRATION_PENDING] {
            match fs::symlink_metadata(parent.join(name)) {
                Ok(_) => {
                    return Err(invalid(
                        "managed or migrating segments cannot be opened through unmanaged APIs",
                    ));
                }
                Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                Err(error) => return Err(map_io_error(error)),
            }
        }
    }
    Ok(())
}

impl ReceiptJournal {
    /// Initialize a NEW private store. Existing directories are never adopted,
    /// reset or silently migrated. Interrupted initialization remains evidence.
    pub fn create_managed(
        root: impl AsRef<Path>,
        id: JournalId,
        created_wall_clock_unix_ms: u64,
    ) -> Result<Self, JournalError> {
        id.validate()?;
        let root = root.as_ref();
        validate_root_name(root)?;
        validate_parent_components(root)?;
        #[cfg(test)]
        persistence_tests::point("initialize.before_directory_create")?;
        fs::DirBuilder::new()
            .mode(0o700)
            .create(root)
            .map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("initialize.after_directory_create")?;
        #[cfg(test)]
        persistence_tests::point("initialize.before_parent_sync")?;
        sync_parent(root)?;
        #[cfg(test)]
        persistence_tests::point("initialize.after_parent_sync")?;
        let (directory, directory_id) = lock_directory(root)?;
        if fs::read_dir(root).map_err(map_io_error)?.next().is_some() {
            return Err(invalid("new store is not empty"));
        }
        #[cfg(test)]
        persistence_tests::point("initialize.before_marker_create")?;
        let mut marker = create_private_file(&root.join(MARKER), true)?;
        #[cfg(test)]
        persistence_tests::point("initialize.after_marker_create")?;
        let bytes = marker_bytes(id);
        #[cfg(test)]
        persistence_tests::before_write("marker", &mut marker, &bytes)?;
        marker.write_all(&bytes).map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("marker.after_write")?;
        #[cfg(test)]
        persistence_tests::point("initialize.before_marker_sync")?;
        marker.sync_all().map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("initialize.after_marker_sync")?;
        #[cfg(test)]
        persistence_tests::point("initialize.before_directory_sync")?;
        directory.sync_all().map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("initialize.after_directory_sync")?;
        let marker_identity = identity(&marker.metadata().map_err(map_io_error)?);
        let mut guard = ManagedDirectory {
            root: root.to_owned(),
            directory,
            identity: directory_id,
            marker,
            marker_identity,
            marker_bytes: bytes,
            segments: 0,
        };
        guard.verify_anchor()?;
        let mut next = Self::create_segment(
            &root.join(PENDING),
            SegmentHeader {
                journal_id: id,
                segment_number: 1,
                first_sequence: 1,
                previous_segment_sha256: ZERO_DIGEST,
                previous_record_sha256: ZERO_DIGEST,
                created_wall_clock_unix_ms,
            },
            false,
            HashMap::new(),
            0,
            false,
        )?;
        guard.publish(&mut next)?;
        next.managed = Some(guard);
        next.check_live_state()?;
        Ok(next)
    }

    /// Select the complete current chain from a closed directory inventory.
    /// Recovery may publish only a fully validated empty linked successor.
    /// It never discards a corrupt pending file, skips a segment, or replays work.
    pub fn open_managed(
        root: impl AsRef<Path>,
        id: JournalId,
        policy: ManagedOpenPolicy,
    ) -> Result<Self, JournalError> {
        let mut guard = ManagedDirectory::acquire(root.as_ref(), id)?;
        let (mut paths, pending) = guard.inventory()?;
        guard.segments = paths.len();
        if pending {
            if !policy.complete_pending_rotation || paths.len() >= MAX_CHAIN_SEGMENTS {
                return Err(invalid(
                    "pending rotation requires explicit recovery within bounds",
                ));
            }
            paths.push(guard.root.join(PENDING));
            // This uses STRICT for the ENTIRE chain: a pending rotation makes
            // every committed file a predecessor, which must never be repaired.
            let mut next = Self::open_chain_impl(paths, Some(id), OpenPolicy::STRICT, false)?;
            guard.publish(&mut next)?;
            next.managed = Some(guard);
            next.check_live_state()?;
            Ok(next)
        } else {
            if paths.is_empty() {
                return Err(invalid("no committed segment or prepared first header"));
            }
            let mut next = Self::open_chain_impl(paths, Some(id), policy.journal, false)?;
            if next.header.segment_number != guard.segments as u64 {
                return Err(invalid("segment name/header mismatch"));
            }
            guard.stabilize_open(&mut next)?;
            next.managed = Some(guard);
            next.check_live_state()?;
            Ok(next)
        }
    }

    /// Rotate a quiescent managed journal. No arbitrary output path is accepted.
    /// On any failure the consumed handle is dropped: callers must reopen and
    /// inspect the durable directory, never retry against a guessed old head.
    pub fn rotate_managed(
        mut self,
        created_wall_clock_unix_ms: u64,
    ) -> Result<(SegmentSeal, Self), JournalError> {
        self.check_live_state()?;
        let mut guard = self
            .managed
            .take()
            .ok_or_else(|| invalid("not a managed journal"))?;
        let (seal, mut next) =
            self.rotate_impl(&guard.root.join(PENDING), created_wall_clock_unix_ms, false)?;
        guard.publish(&mut next)?;
        next.managed = Some(guard);
        next.check_live_state()?;
        Ok((seal, next))
    }

    /// True only after a complete request lifecycle and below no new authority.
    /// The caller decides when to consume the handle via rotate_managed.
    pub fn managed_rotation_due(&self) -> bool {
        self.managed.is_some()
            && self.end_offset >= MANAGED_ROTATION_THRESHOLD_BYTES
            && self
                .progress
                .values()
                .all(|item| item.last_state.is_terminal())
    }

    pub fn is_managed(&self) -> bool {
        self.managed.is_some()
    }
}
