//! Complete-chain restoration. Nothing here executes or replays an operation.
use super::*;
use std::collections::HashSet;

/// Admission bounds include the active segment. Reaching a bound is a typed
/// failure, not permission to prune receipt identities or skip predecessors.
pub const MAX_CHAIN_SEGMENTS: usize = 64;
pub const MAX_CHAIN_BYTES: u64 = 128 * 1024 * 1024;
pub const MAX_CHAIN_RECORDS: u64 = 131_072;

pub(super) struct PinnedSegment {
    pub(super) path: PathBuf,
    pub(super) file: File,
    pub(super) identity: (u64, u64),
    pub(super) bytes: u64,
}

impl PinnedSegment {
    pub(super) fn verify_current(&self) -> Result<(), JournalError> {
        if validate_existing_path_identity(&self.path)? != self.identity {
            return Err(JournalError::InsecurePath(
                "chain path changed while pinned".into(),
            ));
        }
        let metadata = self.file.metadata().map_err(map_io_error)?;
        if !metadata_matches_identity(&metadata, self.identity) || metadata.len() != self.bytes {
            return Err(JournalError::Corruption {
                offset: 0,
                reason: "chain predecessor inode or length changed while pinned".into(),
            });
        }
        Ok(())
    }
}

pub(super) fn bounded_paths<I, P>(paths: I) -> Result<Vec<PathBuf>, JournalError>
where
    I: IntoIterator<Item = P>,
    P: AsRef<Path>,
{
    let paths: Vec<_> = paths
        .into_iter()
        .take(MAX_CHAIN_SEGMENTS + 1)
        .map(|path| path.as_ref().to_owned())
        .collect();
    if paths.is_empty() || paths.len() > MAX_CHAIN_SEGMENTS {
        return Err(JournalError::InvalidInput(format!(
            "segment chain must contain 1..={MAX_CHAIN_SEGMENTS} paths"
        )));
    }
    Ok(paths)
}

pub(super) fn check_growth(
    predecessors: &[PinnedSegment],
    active_bytes: u64,
    record_count: u64,
) -> Result<(), JournalError> {
    let bytes = predecessors
        .iter()
        .try_fold(active_bytes, |sum, item| sum.checked_add(item.bytes))
        .ok_or_else(|| JournalError::InvalidInput("chain byte count overflow".into()))?;
    if bytes > MAX_CHAIN_BYTES || record_count > MAX_CHAIN_RECORDS {
        return Err(JournalError::InvalidInput(
            "complete journal chain exceeds byte/record bound".into(),
        ));
    }
    Ok(())
}

pub(super) fn validate_reports(
    inspected: &[(RecoveryReport, Digest)],
    allow_active_torn: bool,
) -> Result<HashMap<String, ReceiptProgress>, JournalError> {
    let first = &inspected[0].0;
    if first.header.segment_number != 1 {
        return Err(JournalError::Corruption {
            offset: 0,
            reason: "segment chain does not begin with segment one".into(),
        });
    }
    let mut progress: HashMap<String, ReceiptProgress> = HashMap::new();
    let mut records = 0_u64;
    for (index, (report, _)) in inspected.iter().enumerate() {
        if report.tail != TailStatus::Clean && (!allow_active_torn || index + 1 != inspected.len())
        {
            return Err(JournalError::TornTailNeedsRepair {
                offset: report.last_complete_offset,
            });
        }
        records = records
            .checked_add(report.records.len() as u64)
            .ok_or_else(|| JournalError::InvalidInput("chain record count overflow".into()))?;
        if records > MAX_CHAIN_RECORDS {
            return Err(JournalError::InvalidInput(
                "complete journal chain exceeds record bound".into(),
            ));
        }
        if index != 0 {
            let (previous, previous_digest) = &inspected[index - 1];
            let reason = if !previous.unresolved.is_empty() {
                Some("segment chain predecessor has unresolved receipts")
            } else if report.header.journal_id != first.header.journal_id {
                Some("segment chain entry has a different journal ID")
            } else if previous.header.segment_number.checked_add(1)
                != Some(report.header.segment_number)
            {
                Some("segment number is not contiguous")
            } else if report.header.first_sequence != previous.next_sequence {
                Some("first sequence is not contiguous")
            } else if report.header.previous_segment_sha256 != *previous_digest {
                Some("previous-segment digest link mismatch")
            } else if report.header.previous_record_sha256 != previous.last_record_sha256 {
                Some("previous-record digest link across segments mismatch")
            } else {
                None
            };
            if let Some(reason) = reason {
                return Err(JournalError::Corruption {
                    offset: 0,
                    reason: reason.into(),
                });
            }
        }
        for record in &report.records {
            let id = &record.event.receipt_id;
            let next =
                ReceiptProgress::advance(progress.get(id), &record.event).map_err(|error| {
                    JournalError::Corruption {
                        offset: 0,
                        reason: format!(
                            "segment chain entry {index} has invalid cross-segment receipt lifecycle or binding: {error}"
                        ),
                    }
                })?;
            progress.insert(id.clone(), next);
        }
    }
    Ok(progress)
}

impl ReceiptJournal {
    /// Restore an explicitly ordered complete chain and its global receipt namespace.
    ///
    /// The caller must select the authoritative active head; this method does not
    /// discover successors or authenticate a chain against malicious offline truncation.
    /// All inodes are nonblockingly locked and pinned for the writer's lifetime.
    /// Only the final segment's torn tail may be repaired, after identity, links,
    /// receipt lifecycles and resource limits pass. Predecessors are never repaired.
    pub fn open_chain<I, P>(
        paths: I,
        expected_journal_id: JournalId,
        policy: OpenPolicy,
    ) -> Result<Self, JournalError>
    where
        I: IntoIterator<Item = P>,
        P: AsRef<Path>,
    {
        expected_journal_id.validate()?;
        let paths = bounded_paths(paths)?;
        for path in &paths {
            managed::reject_unmanaged_access(path)?;
        }
        Self::open_chain_impl(paths, Some(expected_journal_id), policy, true)
    }

    pub(super) fn open_chain_impl<I, P>(
        paths: I,
        expected_journal_id: Option<JournalId>,
        policy: OpenPolicy,
        path_lease: bool,
    ) -> Result<Self, JournalError>
    where
        I: IntoIterator<Item = P>,
        P: AsRef<Path>,
    {
        let paths = bounded_paths(paths)?;
        let mut pinned = Vec::with_capacity(paths.len());
        let mut identities = HashSet::new();
        let mut total_bytes = 0_u64;
        // Acquire every inode lock before decoding or acquiring/updating a lease.
        // try_lock avoids deadlock even if two callers submit different orders.
        for (index, path) in paths.iter().enumerate() {
            let identity = validate_existing_path_identity(path)?;
            if !identities.insert(identity) {
                return Err(JournalError::InvalidInput(
                    "segment chain repeats an inode".into(),
                ));
            }
            let file = open_existing_file_checked(path, index + 1 == paths.len(), identity)?;
            lock_file(&file)?;
            let bytes = file.metadata().map_err(map_io_error)?.len();
            total_bytes = total_bytes
                .checked_add(bytes)
                .ok_or_else(|| JournalError::InvalidInput("chain byte count overflow".into()))?;
            if bytes > MAX_SEGMENT_BYTES || total_bytes > MAX_CHAIN_BYTES {
                return Err(JournalError::InvalidInput(
                    "complete journal chain exceeds byte bound".into(),
                ));
            }
            let item = PinnedSegment {
                path: path.clone(),
                file,
                identity,
                bytes,
            };
            item.verify_current()?;
            pinned.push(item);
        }
        let mut inspected = Vec::with_capacity(pinned.len());
        for item in &mut pinned {
            let bytes = read_segment_bytes(&mut item.file)?;
            if bytes.len() as u64 != item.bytes {
                return Err(JournalError::Corruption {
                    offset: 0,
                    reason: "chain changed during inspection".into(),
                });
            }
            let report = recover_bytes(&bytes)?;
            if let Some(expected) = expected_journal_id
                && report.header.journal_id != expected
            {
                return Err(JournalError::InvalidInput(
                    "receipt journal identity mismatch".into(),
                ));
            }
            inspected.push((report, sha256(&bytes)));
        }
        let progress = validate_reports(&inspected, policy.repair_torn_tail)?;
        let last_monotonic_ms = inspected
            .iter()
            .flat_map(|(report, _)| &report.records)
            .map(|record| record.event.monotonic_ms)
            .max()
            .unwrap_or(0);
        for item in &pinned {
            item.verify_current()?;
        }
        let mut active = pinned.pop().expect("bounded nonempty paths");
        let (report, _) = inspected.pop().expect("one report per path");
        let lease = if path_lease {
            Some(WriterLease::acquire(
                &active.path,
                policy.recover_stale_writer_lease,
            )?)
        } else {
            None
        };
        for item in &pinned {
            item.verify_current()?;
        }
        active.verify_current()?;
        if report.tail != TailStatus::Clean {
            #[cfg(test)]
            persistence_tests::point("repair.before_truncate")?;
            active
                .file
                .set_len(report.last_complete_offset)
                .map_err(map_io_error)?;
            #[cfg(test)]
            persistence_tests::point("repair.after_truncate")?;
            #[cfg(test)]
            persistence_tests::point("repair.before_sync")?;
            active.file.sync_data().map_err(map_io_error)?;
            #[cfg(test)]
            persistence_tests::point("repair.after_sync")?;
            let repaired = recover_file(&mut active.file)?;
            if repaired.tail != TailStatus::Clean
                || repaired.header != report.header
                || repaired.records != report.records
            {
                return Err(JournalError::Corruption {
                    offset: report.last_complete_offset,
                    reason: "torn-tail repair did not preserve the validated prefix".into(),
                });
            }
        }
        active
            .file
            .seek(SeekFrom::Start(report.last_complete_offset))
            .map_err(map_io_error)?;
        Ok(Self {
            path: active.path,
            file: active.file,
            _lease: lease,
            managed: None,
            predecessors: pinned,
            header: report.header,
            next_sequence: report.next_sequence,
            previous_record_sha256: report.last_record_sha256,
            progress,
            last_monotonic_ms,
            end_offset: report.last_complete_offset,
            file_device: active.identity.0,
            file_inode: active.identity.1,
            poisoned: false,
        })
    }
}

/// Read-only inspection is useful for diagnostics, not a substitute for the
/// lock-owning open_chain transaction. It never truncates data or creates leases.
pub(super) fn inspect<I, P>(paths: I) -> Result<Vec<RecoveryReport>, JournalError>
where
    I: IntoIterator<Item = P>,
    P: AsRef<Path>,
{
    let paths = bounded_paths(paths)?;
    let mut inspected = Vec::with_capacity(paths.len());
    let mut identities = HashSet::new();
    let mut total_bytes = 0_u64;
    for path in paths {
        let identity = validate_existing_path_identity(&path)?;
        if !identities.insert(identity) {
            return Err(JournalError::InvalidInput(
                "segment chain repeats an inode".into(),
            ));
        }
        let mut file = open_existing_file_checked(&path, false, identity)?;
        let size = file.metadata().map_err(map_io_error)?.len();
        total_bytes = total_bytes
            .checked_add(size)
            .ok_or_else(|| JournalError::InvalidInput("chain byte count overflow".into()))?;
        if size > MAX_SEGMENT_BYTES || total_bytes > MAX_CHAIN_BYTES {
            return Err(JournalError::InvalidInput(
                "complete journal chain exceeds byte bound".into(),
            ));
        }
        let bytes = read_segment_bytes(&mut file)?;
        if bytes.len() as u64 != size {
            return Err(JournalError::Corruption {
                offset: 0,
                reason: "chain changed during inspection".into(),
            });
        }
        inspected.push((recover_bytes(&bytes)?, sha256(&bytes)));
    }
    validate_reports(&inspected, false)?;
    Ok(inspected.into_iter().map(|(report, _)| report).collect())
}
