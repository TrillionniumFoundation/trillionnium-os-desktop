//! Explicit offline, byte-preserving legacy-chain copy. No cutover or replay.
use super::*;
use std::collections::{BTreeSet, HashSet};

/// This name deliberately prevents every unmanaged write entry point from
/// admitting a prefix of an incomplete import. It is not an auto-recovery file.
pub(super) const MIGRATION_PENDING: &str = "migration.pending";

/// One original segment and its independent private copy. These digests prove
/// byte equality, not authenticity against an attacker that controls both trees.
#[derive(Debug, Clone, Eq, PartialEq)]
pub struct CopiedReceiptSegment {
    pub source: PathBuf,
    pub destination: PathBuf,
    pub bytes: u64,
    pub sha256: Digest,
}

/// Returned only after marker publication and directory sync. It contains no
/// receipt payload. This is a copy receipt, NOT a writer, service cutover,
/// archive-deletion permit, signed attestation, or anti-rollback checkpoint.
#[derive(Debug, Clone, Eq, PartialEq)]
#[must_use = "verify the copy and perform a separately controlled service cutover"]
pub struct ReceiptMigrationReport {
    pub journal_id: JournalId,
    pub segments: Vec<CopiedReceiptSegment>,
    pub record_count: u64,
    pub unresolved_receipts: usize,
    pub next_sequence: u64,
    pub last_record_sha256: Digest,
}

struct LegacySource {
    pinned: Vec<chain::PinnedSegment>,
    digests: Vec<Digest>,
    record_count: u64,
    unresolved_receipts: usize,
    next_sequence: u64,
    last_record_sha256: Digest,
}

impl LegacySource {
    fn acquire<I, P>(paths: I, id: JournalId) -> Result<Self, JournalError>
    where
        I: IntoIterator<Item = P>,
        P: AsRef<Path>,
    {
        id.validate()?;
        let paths = chain::bounded_paths(paths)?;
        let mut pinned = Vec::with_capacity(paths.len());
        let mut identities = HashSet::new();
        let mut total_bytes = 0_u64;
        for path in paths {
            validate_root_name(&path)?;
            reject_unmanaged_access(&path)?;
            let identity = validate_existing_path_identity(&path)?;
            if !identities.insert(identity) {
                return Err(invalid("migration source repeats an inode"));
            }
            // Read-only descriptors and inode locks only. Do NOT open a legacy
            // writer or acquire/rewrite any .writer-lock sidecar.
            let file = open_existing_file_checked(&path, false, identity)?;
            lock_file(&file)?;
            let bytes = file.metadata().map_err(map_io_error)?.len();
            total_bytes = total_bytes
                .checked_add(bytes)
                .ok_or_else(|| invalid("migration byte count overflow"))?;
            if bytes > MAX_SEGMENT_BYTES || total_bytes > MAX_CHAIN_BYTES {
                return Err(invalid("migration byte bound exceeded"));
            }
            let segment = chain::PinnedSegment {
                path,
                file,
                identity,
                bytes,
            };
            segment.verify_current()?;
            pinned.push(segment);
        }
        // Reuse the actual on-disk decoder and complete-chain admission rules.
        // A torn active tail is NOT repaired by this operation.
        let mut inspected = Vec::with_capacity(pinned.len());
        for segment in &mut pinned {
            let bytes = read_segment_bytes(&mut segment.file)?;
            if bytes.len() as u64 != segment.bytes {
                return Err(invalid("migration source changed during inspection"));
            }
            let report = recover_bytes(&bytes)?;
            if report.header.journal_id != id {
                return Err(invalid("migration journal ID mismatch"));
            }
            inspected.push((report, sha256(&bytes)));
        }
        let progress = chain::validate_reports(&inspected, false)?;
        let last = &inspected.last().expect("bounded nonempty source").0;
        let source = Self {
            record_count: inspected.iter().map(|(r, _)| r.records.len() as u64).sum(),
            unresolved_receipts: progress
                .values()
                .filter(|p| !p.last_state.is_terminal())
                .count(),
            next_sequence: last.next_sequence,
            last_record_sha256: last.last_record_sha256,
            digests: inspected.iter().map(|(_, digest)| *digest).collect(),
            pinned,
        };
        for item in &source.pinned {
            item.verify_current()?;
        }
        Ok(source)
    }

    fn read_unchanged(&mut self, index: usize) -> Result<Vec<u8>, JournalError> {
        let item = &mut self.pinned[index];
        item.verify_current()?;
        let bytes = read_segment_bytes(&mut item.file)?;
        if bytes.len() as u64 != item.bytes || sha256(&bytes) != self.digests[index] {
            return Err(invalid("migration source bytes changed while locked"));
        }
        item.verify_current()?;
        Ok(bytes)
    }

    fn verify_all(&mut self) -> Result<(), JournalError> {
        for index in 0..self.pinned.len() {
            self.read_unchanged(index)?;
        }
        Ok(())
    }
}

fn verify_staging(
    root: &Path,
    directory: &File,
    directory_id: (u64, u64),
    marker: &chain::PinnedSegment,
    segments: &mut [chain::PinnedSegment],
    digests: &[Digest],
    id: JournalId,
) -> Result<(), JournalError> {
    if identity(&directory_metadata(root)?) != directory_id
        || identity(&directory.metadata().map_err(map_io_error)?) != directory_id
    {
        return Err(invalid("migration destination directory changed"));
    }
    marker.verify_current()?;
    let mut bytes = [0; MARKER_BYTES];
    marker
        .file
        .read_exact_at(&mut bytes, 0)
        .map_err(map_io_error)?;
    if bytes != marker_bytes(id) {
        return Err(invalid("migration marker bytes changed"));
    }
    let mut expected: BTreeSet<_> = (1..=segments.len()).map(segment_name).collect();
    expected.insert(MIGRATION_PENDING.to_owned());
    let mut actual = BTreeSet::new();
    for (count, entry) in fs::read_dir(root).map_err(map_io_error)?.enumerate() {
        if count > MAX_CHAIN_SEGMENTS {
            return Err(invalid("migration staging inventory bound exceeded"));
        }
        let entry = entry.map_err(map_io_error)?;
        validate_existing_path_identity(&entry.path())?;
        actual.insert(
            entry
                .file_name()
                .into_string()
                .map_err(|_| invalid("migration entry is not UTF-8"))?,
        );
    }
    if actual != expected {
        return Err(invalid("migration staging inventory changed"));
    }
    for (segment, expected) in segments.iter_mut().zip(digests) {
        segment.verify_current()?;
        if sha256(&read_segment_bytes(&mut segment.file)?) != *expected {
            return Err(invalid("migration destination digest mismatch"));
        }
        segment.verify_current()?;
    }
    Ok(())
}

impl ReceiptJournal {
    /// Copy a caller-selected COMPLETE legacy chain to a NEW managed directory.
    /// Sources are opened read-only, locked, strictly validated and never repaired,
    /// rewritten, renamed or removed. All original v1 bytes, identities, privacy
    /// classes and unresolved facts are preserved. No operation is executed.
    ///
    /// The caller must stop the legacy service and choose its authoritative full
    /// chain; omission of an otherwise unknown last segment cannot be detected.
    /// The new private directory is reserved with create-new semantics. Until all
    /// copied files are verified and synced, migration.pending blocks writer APIs.
    /// Publishing it as store.v1 is the in-directory commit point. Errors after
    /// that point may leave a complete copy; never infer absence or retry over it.
    /// Partial destinations are preserved and NEVER automatically resumed/adopted.
    ///
    /// The returned report is not a writer or service configuration change. The
    /// source remains present; separately arrange single-writer cutover. Locks
    /// serialize cooperating local processes, not malicious same-UID/root writes.
    pub fn copy_legacy_chain_to_managed<I, P>(
        paths: I,
        expected_journal_id: JournalId,
        destination: impl AsRef<Path>,
    ) -> Result<ReceiptMigrationReport, JournalError>
    where
        I: IntoIterator<Item = P>,
        P: AsRef<Path>,
    {
        let root = destination.as_ref();
        validate_root_name(root)?;
        validate_new_path(root)?;
        // Finish all source validation before creating any destination entry.
        let mut source = LegacySource::acquire(paths, expected_journal_id)?;
        #[cfg(test)]
        persistence_tests::point("migration.before_directory_create")?;
        fs::DirBuilder::new()
            .mode(0o700)
            .create(root)
            .map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("migration.after_directory_create")?;
        sync_parent(root)?;
        let (directory, directory_id) = lock_directory(root)?;
        if fs::read_dir(root).map_err(map_io_error)?.next().is_some() {
            return Err(invalid("migration destination is not empty"));
        }
        let marker_path = root.join(MIGRATION_PENDING);
        let mut marker_file = create_private_file(&marker_path, true)?;
        lock_file(&marker_file)?;
        let bytes = marker_bytes(expected_journal_id);
        #[cfg(test)]
        persistence_tests::before_write("migration_marker", &mut marker_file, &bytes)?;
        marker_file.write_all(&bytes).map_err(map_io_error)?;
        marker_file.sync_all().map_err(map_io_error)?;
        directory.sync_all().map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("migration.after_marker_sync")?;
        let marker = chain::PinnedSegment {
            identity: identity(&marker_file.metadata().map_err(map_io_error)?),
            path: marker_path,
            file: marker_file,
            bytes: MARKER_BYTES as u64,
        };
        let mut copies = Vec::with_capacity(source.pinned.len());
        let mut details = Vec::with_capacity(source.pinned.len());
        for index in 0..source.pinned.len() {
            let path = root.join(segment_name(index + 1));
            let bytes = source.read_unchanged(index)?;
            let mut file = create_private_file(&path, true)?;
            lock_file(&file)?;
            #[cfg(test)]
            persistence_tests::before_write(
                &format!("migration_segment_{index}"),
                &mut file,
                &bytes,
            )?;
            file.write_all(&bytes).map_err(map_io_error)?;
            #[cfg(test)]
            persistence_tests::point(&format!("migration_segment_{index}.before_sync"))?;
            file.sync_all().map_err(map_io_error)?;
            #[cfg(test)]
            persistence_tests::point(&format!("migration_segment_{index}.after_sync"))?;
            copies.push(chain::PinnedSegment {
                identity: identity(&file.metadata().map_err(map_io_error)?),
                path: path.clone(),
                file,
                bytes: bytes.len() as u64,
            });
            details.push(CopiedReceiptSegment {
                source: source.pinned[index].path.clone(),
                destination: path,
                bytes: bytes.len() as u64,
                sha256: source.digests[index],
            });
        }
        source.verify_all()?;
        verify_staging(
            root,
            &directory,
            directory_id,
            &marker,
            &mut copies,
            &source.digests,
            expected_journal_id,
        )?;
        // Both marker bytes AND all copied data precede marker publication.
        directory.sync_all().map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("migration.before_publish")?;
        // Fresh private directory and the directory lock prevent cooperating
        // writers from introducing a competing target. No hostile-root claim.
        validate_new_path(&root.join(MARKER))?;
        fs::rename(&marker.path, root.join(MARKER)).map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("migration.after_publish")?;
        directory.sync_all().map_err(map_io_error)?;
        #[cfg(test)]
        persistence_tests::point("migration.after_directory_sync")?;
        let guard = ManagedDirectory {
            root: root.to_owned(),
            directory,
            identity: directory_id,
            marker: marker.file,
            marker_identity: marker.identity,
            marker_bytes: marker_bytes(expected_journal_id),
            segments: copies.len(),
        };
        guard.verify_current()?;
        source.verify_all()?;
        for (copy, expected) in copies.iter_mut().zip(&source.digests) {
            copy.verify_current()?;
            if sha256(&read_segment_bytes(&mut copy.file)?) != *expected {
                return Err(invalid("migration post-publication digest mismatch"));
            }
        }
        Ok(ReceiptMigrationReport {
            journal_id: expected_journal_id,
            segments: details,
            record_count: source.record_count,
            unresolved_receipts: source.unresolved_receipts,
            next_sequence: source.next_sequence,
            last_record_sha256: source.last_record_sha256,
        })
    }
}

#[cfg(test)]
#[path = "migration_tests.rs"]
mod tests;
