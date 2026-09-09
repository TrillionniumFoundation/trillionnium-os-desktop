#!/usr/bin/env python3
"""Close the reviewed S05 authoritative export and pathname-custody gaps."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def patch_receipt_journal() -> None:
    path = ROOT / "crates/hepta-session-core/src/receipt_journal.rs"
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};",
        "use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt, PermissionsExt};",
        "FileExt import",
    )
    text = replace_once(
        text,
        "    SegmentTooLarge(u64),\n    WriterPoisoned,",
        "    SegmentTooLarge(u64),\n    /// The final export name may have crossed the atomic publication boundary,\n    /// but a following directory/cleanup barrier did not complete. Callers must\n    /// inspect the destination and must never retry by overwriting it.\n    PublicationUncertain,\n    WriterPoisoned,",
        "publication error variant",
    )
    text = replace_once(
        text,
        "            Self::WriterPoisoned => formatter.write_str(\n",
        "            Self::PublicationUncertain => formatter.write_str(\n                \"receipt export publication is uncertain; inspect the no-replace destination before retrying\",\n            ),\n            Self::WriterPoisoned => formatter.write_str(\n",
        "publication display",
    )

    direct_publish = """    let digest = sha256(&bytes);
    let mut file = create_private_file(destination, true)?;
    commit_bytes(&mut file, &bytes)?;
    sync_parent(destination)?;
    Ok(digest)"""
    count = text.count(direct_publish)
    if count != 2:
        raise SystemExit(f"direct export publication: expected two matches, found {count}")
    text = text.replace(direct_publish, "    publish_private_bytes(destination, &bytes)")

    parent_pattern = re.compile(
        r"fn validate_parent_components\(path: &Path\) -> Result<\(\), JournalError> \{.*?\n\}\n\n(?=fn validate_new_path)",
        re.S,
    )
    parent_replacement = r'''fn effective_service_uid() -> Result<u32, JournalError> {
    // The product is Linux-only and already depends on procfs for peer
    // attestation. `/proc/self` is owned by the effective process identity,
    // avoiding an unsafe libc call while still failing closed if procfs is not
    // available in the execution environment.
    Ok(fs::metadata("/proc/self").map_err(map_io_error)?.uid())
}

fn ancestor_owner_is_trusted(owner: u32, effective_uid: u32) -> bool {
    owner == 0 || owner == effective_uid
}

fn validate_parent_components(path: &Path) -> Result<(), JournalError> {
    if path
        .components()
        .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(JournalError::InsecurePath(
            "parent traversal is not permitted".into(),
        ));
    }
    let parent = path.parent().ok_or_else(|| {
        JournalError::InsecurePath("path has no parent directory".into())
    })?;
    let effective_uid = effective_service_uid()?;
    let mut current = PathBuf::new();
    for component in parent.components() {
        match component {
            Component::RootDir => current.push(Path::new("/")),
            Component::CurDir => continue,
            Component::Normal(value) => current.push(value),
            Component::ParentDir | Component::Prefix(_) => {
                return Err(JournalError::InsecurePath(
                    "unsupported parent path component".into(),
                ));
            }
        }
        if current.as_os_str().is_empty() {
            continue;
        }
        let metadata = fs::symlink_metadata(&current).map_err(map_io_error)?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err(JournalError::InsecurePath(
                "journal parent contains a symlink or non-directory component".into(),
            ));
        }
        let mode = metadata.permissions().mode();
        let owner = metadata.uid();
        if !ancestor_owner_is_trusted(owner, effective_uid) {
            return Err(JournalError::InsecurePath(
                "journal parent is owned by an untrusted uid".into(),
            ));
        }
        let sticky_root_directory = owner == 0 && mode & 0o1000 != 0;
        if mode & 0o022 != 0 && !sticky_root_directory {
            return Err(JournalError::InsecurePath(
                "journal parent is group/other writable without trusted sticky-root custody".into(),
            ));
        }
    }
    Ok(())
}

'''
    text, count = parent_pattern.subn(parent_replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"parent custody replacement: expected one match, found {count}")

    snapshot_impl = r'''
/// Read an exact inode snapshot without changing the writer's file offset.
fn read_locked_segment(file: &File, expected_len: u64) -> Result<Vec<u8>, JournalError> {
    if expected_len > MAX_SEGMENT_BYTES {
        return Err(JournalError::SegmentTooLarge(expected_len));
    }
    let len = usize::try_from(expected_len).map_err(|_| {
        JournalError::InvalidInput("journal segment length is not addressable".into())
    })?;
    let mut bytes = vec![0_u8; len];
    let mut offset = 0_usize;
    while offset < len {
        let read = file
            .read_at(&mut bytes[offset..], offset as u64)
            .map_err(map_io_error)?;
        if read == 0 {
            return Err(JournalError::Corruption {
                offset: offset as u64,
                reason: "locked journal segment shortened during snapshot".into(),
            });
        }
        offset = offset.checked_add(read).ok_or_else(|| {
            JournalError::InvalidInput("journal snapshot offset overflow".into())
        })?;
    }
    if file.metadata().map_err(map_io_error)?.len() != expected_len {
        return Err(JournalError::Corruption {
            offset: expected_len,
            reason: "locked journal segment length changed during snapshot".into(),
        });
    }
    Ok(bytes)
}

impl ReceiptJournal {
    /// Open a caller-selected legacy chain under the same nonblocking writer
    /// lease and inode locks as a writer. Managed segments are rejected because
    /// only their pinned directory inventory can prove a complete current head.
    pub(crate) fn open_authoritative_chain<I, P>(paths: I) -> Result<Self, JournalError>
    where
        I: IntoIterator<Item = P>,
        P: AsRef<Path>,
    {
        let paths = chain::bounded_paths(paths)?;
        for path in &paths {
            managed::reject_unmanaged_access(path)?;
        }
        Self::open_chain_impl(paths, None, OpenPolicy::STRICT, true)
    }

    /// Decode the complete chain while every source inode and, for managed
    /// stores, the closed directory inventory remain locked and pinned.
    pub(crate) fn authoritative_reports(&mut self) -> Result<Vec<RecoveryReport>, JournalError> {
        self.check_live_state()?;
        let mut inspected = Vec::with_capacity(self.predecessors.len() + 1);
        for predecessor in &self.predecessors {
            predecessor.verify_current()?;
            let bytes = read_locked_segment(&predecessor.file, predecessor.bytes)?;
            inspected.push((recover_bytes(&bytes)?, sha256(&bytes)));
        }

        let active_identity = (self.file_device, self.file_inode);
        let active_metadata = self.file.metadata().map_err(map_io_error)?;
        if !metadata_matches_identity(&active_metadata, active_identity)
            || active_metadata.len() != self.end_offset
        {
            return Err(JournalError::Corruption {
                offset: self.end_offset,
                reason: "active journal identity or length changed during snapshot".into(),
            });
        }
        let active_bytes = read_locked_segment(&self.file, self.end_offset)?;
        inspected.push((recover_bytes(&active_bytes)?, sha256(&active_bytes)));
        chain::validate_reports(&inspected, false)?;
        self.check_live_state()?;
        Ok(inspected.into_iter().map(|(report, _)| report).collect())
    }

    pub(crate) fn revalidate_authoritative_snapshot(&mut self) -> Result<(), JournalError> {
        self.check_live_state()
    }
}

'''
    text = replace_once(
        text,
        "fn read_segment_bytes(file: &mut File) -> Result<Vec<u8>, JournalError> {",
        snapshot_impl + "fn read_segment_bytes(file: &mut File) -> Result<Vec<u8>, JournalError> {",
        "locked snapshot implementation",
    )

    atomic_publish = r'''
static EXPORT_STAGE_COUNTER: std::sync::atomic::AtomicU64 =
    std::sync::atomic::AtomicU64::new(1);

fn remove_unpublished_stage(path: &Path) {
    let _ = fs::remove_file(path);
    let _ = sync_parent(path);
}

/// Publish complete bytes without ever exposing a partial canonical filename.
///
/// The same-directory private inode is fully written, sync_all'd and reread
/// before an atomic no-replace hard link installs the final name. Any error
/// after that link is conservatively classified as publication uncertainty;
/// callers may inspect but must never overwrite or blindly retry the final
/// path.
fn publish_private_bytes(destination: &Path, bytes: &[u8]) -> Result<Digest, JournalError> {
    validate_new_path(destination)?;
    let parent = destination.parent().ok_or_else(|| {
        JournalError::InsecurePath("export destination has no parent".into())
    })?;
    let name = destination
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| JournalError::InsecurePath("export filename must be UTF-8".into()))?;

    #[cfg(test)]
    persistence_tests::point("export.before_stage_create")?;
    let mut selected = None;
    for _ in 0..32 {
        let sequence = EXPORT_STAGE_COUNTER.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        let stage = parent.join(format!(
            ".{name}.receipt-export-stage-{}-{sequence}",
            std::process::id()
        ));
        match create_private_file(&stage, true) {
            Ok(file) => {
                selected = Some((stage, file));
                break;
            }
            Err(JournalError::Io(error)) if error.kind() == io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(error),
        }
    }
    let (stage, mut file) = selected.ok_or_else(|| {
        JournalError::InvalidInput("could not allocate a unique export staging inode".into())
    })?;
    #[cfg(test)]
    persistence_tests::point("export.after_stage_create")?;

    if let Err(error) = commit_bytes(&mut file, bytes) {
        drop(file);
        remove_unpublished_stage(&stage);
        return Err(error);
    }
    if let Err(error) = file.sync_all().map_err(map_io_error) {
        drop(file);
        remove_unpublished_stage(&stage);
        return Err(error);
    }
    #[cfg(test)]
    if let Err(error) = persistence_tests::point("export.after_stage_sync") {
        drop(file);
        remove_unpublished_stage(&stage);
        return Err(error);
    }

    let expected_digest = sha256(bytes);
    let verified = read_locked_segment(&file, bytes.len() as u64);
    match verified {
        Ok(ref observed) if observed.as_slice() == bytes && sha256(observed) == expected_digest => {}
        Ok(_) => {
            drop(file);
            remove_unpublished_stage(&stage);
            return Err(JournalError::Corruption {
                offset: 0,
                reason: "export staging verification mismatch".into(),
            });
        }
        Err(error) => {
            drop(file);
            remove_unpublished_stage(&stage);
            return Err(error);
        }
    }
    drop(file);

    #[cfg(test)]
    if let Err(error) = persistence_tests::point("export.before_publish") {
        remove_unpublished_stage(&stage);
        return Err(error);
    }
    if let Err(error) = fs::hard_link(&stage, destination) {
        remove_unpublished_stage(&stage);
        return Err(map_io_error(error));
    }
    #[cfg(test)]
    if persistence_tests::point("export.after_publish").is_err() {
        return Err(JournalError::PublicationUncertain);
    }
    #[cfg(test)]
    if persistence_tests::point("export.before_directory_sync").is_err() {
        return Err(JournalError::PublicationUncertain);
    }
    if sync_parent(destination).is_err() {
        return Err(JournalError::PublicationUncertain);
    }
    #[cfg(test)]
    if persistence_tests::point("export.after_directory_sync").is_err() {
        return Err(JournalError::PublicationUncertain);
    }
    if fs::remove_file(&stage).is_err() {
        return Err(JournalError::PublicationUncertain);
    }
    if sync_parent(destination).is_err() {
        return Err(JournalError::PublicationUncertain);
    }
    Ok(expected_digest)
}

#[cfg(test)]
mod authoritative_path_tests {
    use super::*;

    #[test]
    fn ancestor_ownership_accepts_only_root_or_effective_service_uid() {
        assert!(ancestor_owner_is_trusted(0, 1000));
        assert!(ancestor_owner_is_trusted(1000, 1000));
        assert!(!ancestor_owner_is_trusted(1001, 1000));
        assert!(!ancestor_owner_is_trusted(u32::MAX, 1000));
    }
}

'''
    text = replace_once(
        text,
        "fn create_private_file(path: &Path, create_new: bool) -> Result<File, JournalError> {",
        atomic_publish + "fn create_private_file(path: &Path, create_new: bool) -> Result<File, JournalError> {",
        "atomic export publication",
    )

    path.write_text(text, encoding="utf-8")


def write_authoritative_export() -> None:
    path = ROOT / "crates/hepta-session-core/src/authoritative_export.rs"
    path.write_text(
        r'''//! Evidence-bearing receipt export from a locked, complete journal snapshot.
//!
//! Managed exports derive the full canonical inventory while holding the
//! managed directory and every segment lock. Legacy explicit chains acquire
//! the same writer lease and inode locks as a writer and reject managed segment
//! paths. Locks remain held through atomic no-replace publication.

use std::collections::HashMap;
use std::path::Path;

use crate::receipt_journal::{
    self, Digest, JournalError, RecoveredRecord, RecoveryReport, TailStatus,
};
use crate::receipt_journal_impl::{
    JournalId, ManagedOpenPolicy, ReceiptJournal,
};

/// Export canonical envelopes from a locked caller-selected legacy chain.
///
/// Managed segment paths are rejected; use
/// [`export_managed_receipt_envelopes_jsonl`] so the complete current inventory
/// is derived under the pinned directory lock. A live writer makes this call
/// fail closed instead of yielding a stale prefix.
pub fn export_receipt_envelopes_jsonl<I, P>(
    source_chain: I,
    destination: impl AsRef<Path>,
) -> Result<Digest, JournalError>
where
    I: IntoIterator<Item = P>,
    P: AsRef<Path>,
{
    let mut journal = ReceiptJournal::open_authoritative_chain(source_chain)?;
    export_locked_envelopes(&mut journal, destination.as_ref())
}

/// Export canonical envelopes from the complete current managed inventory.
///
/// The root directory lock and every segment inode lock are retained through
/// validation and publication. An active writer, pending/corrupt inventory,
/// unresolved receipt, or changed source fails closed.
pub fn export_managed_receipt_envelopes_jsonl(
    root: impl AsRef<Path>,
    journal_id: JournalId,
    destination: impl AsRef<Path>,
) -> Result<Digest, JournalError> {
    let mut journal = ReceiptJournal::open_managed(
        root,
        journal_id,
        ManagedOpenPolicy::STRICT,
    )?;
    export_locked_envelopes(&mut journal, destination.as_ref())
}

/// Compatibility alias for the locked legacy-chain envelope export.
pub fn export_redacted_jsonl<I, P>(
    source_chain: I,
    destination: impl AsRef<Path>,
) -> Result<Digest, JournalError>
where
    I: IntoIterator<Item = P>,
    P: AsRef<Path>,
{
    export_receipt_envelopes_jsonl(source_chain, destination)
}

/// Compatibility alias for the complete managed-root envelope export.
pub fn export_managed_redacted_jsonl(
    root: impl AsRef<Path>,
    journal_id: JournalId,
    destination: impl AsRef<Path>,
) -> Result<Digest, JournalError> {
    export_managed_receipt_envelopes_jsonl(root, journal_id, destination)
}

/// Export a forensic prefix from caller-supplied decoded data.
///
/// This is deliberately non-authoritative. Publication is atomic/no-replace,
/// but the supplied report is not an authenticated complete-chain snapshot.
pub fn export_forensic_prefix_jsonl(
    report: &RecoveryReport,
    destination: impl AsRef<Path>,
) -> Result<Digest, JournalError> {
    receipt_journal::export_journal_redacted_jsonl(report, destination)
}

fn export_locked_envelopes(
    journal: &mut ReceiptJournal,
    destination: &Path,
) -> Result<Digest, JournalError> {
    let reports = journal.authoritative_reports()?;
    validate_complete_reports(&reports)?;
    let combined = combine_verified_reports(reports)?;
    journal.revalidate_authoritative_snapshot()?;
    let digest = receipt_journal::export_receipt_envelopes_jsonl(&combined, destination)?;
    journal.revalidate_authoritative_snapshot()?;
    Ok(digest)
}

fn validate_complete_reports(reports: &[RecoveryReport]) -> Result<(), JournalError> {
    if reports.is_empty() {
        return Err(JournalError::InvalidInput(
            "authoritative export requires a non-empty complete journal chain".into(),
        ));
    }
    if reports[0].header.segment_number != 1 || reports[0].header.first_sequence != 1 {
        return Err(JournalError::InvalidInput(
            "authoritative export must begin with journal segment one".into(),
        ));
    }

    let mut expected_sequence = 1_u64;
    let mut last_digest = [0_u8; 32];
    let mut grouped: HashMap<String, Vec<RecoveredRecord>> = HashMap::new();

    for report in reports {
        if !matches!(report.tail, TailStatus::Clean) {
            return Err(JournalError::InvalidInput(format!(
                "authoritative export refuses torn tail in segment {}",
                report.header.segment_number
            )));
        }
        if !report.unresolved.is_empty() {
            return Err(JournalError::InvalidInput(format!(
                "authoritative export refuses {} unresolved receipt(s) in segment {}",
                report.unresolved.len(),
                report.header.segment_number
            )));
        }
        if report.header.first_sequence != expected_sequence {
            return Err(JournalError::InvalidInput(format!(
                "authoritative export sequence discontinuity at segment {}",
                report.header.segment_number
            )));
        }

        for record in &report.records {
            if record.sequence != expected_sequence {
                return Err(JournalError::InvalidInput(format!(
                    "authoritative export record sequence mismatch: expected {expected_sequence}, found {}",
                    record.sequence
                )));
            }
            record.event.validate()?;
            if record.record_sha256 == [0_u8; 32] {
                return Err(JournalError::InvalidInput(
                    "authoritative export refuses a zero record digest".into(),
                ));
            }
            last_digest = record.record_sha256;
            grouped
                .entry(record.event.receipt_id.clone())
                .or_default()
                .push(record.clone());
            expected_sequence = expected_sequence.checked_add(1).ok_or_else(|| {
                JournalError::InvalidInput("authoritative export record sequence overflow".into())
            })?;
        }

        if report.next_sequence != expected_sequence {
            return Err(JournalError::InvalidInput(format!(
                "authoritative export next_sequence mismatch in segment {}",
                report.header.segment_number
            )));
        }
        if report.last_record_sha256 != last_digest {
            return Err(JournalError::InvalidInput(format!(
                "authoritative export last-record digest mismatch in segment {}",
                report.header.segment_number
            )));
        }
    }

    for records in grouped.values() {
        receipt_journal::ReceiptEnvelope::from_records(records)?;
    }
    Ok(())
}

fn combine_verified_reports(
    mut reports: Vec<RecoveryReport>,
) -> Result<RecoveryReport, JournalError> {
    let first = reports.first().ok_or_else(|| {
        JournalError::InvalidInput(
            "authoritative export requires a non-empty complete journal chain".into(),
        )
    })?;
    let header = first.header.clone();
    let mut records = Vec::new();
    let mut last_complete_offset = 0_u64;
    let mut next_sequence = header.first_sequence;
    let mut last_record_sha256 = header.previous_record_sha256;

    for report in reports.drain(..) {
        last_complete_offset = last_complete_offset
            .checked_add(report.last_complete_offset)
            .ok_or_else(|| {
                JournalError::InvalidInput("authoritative export complete-offset overflow".into())
            })?;
        next_sequence = report.next_sequence;
        last_record_sha256 = report.last_record_sha256;
        records.extend(report.records);
    }

    Ok(RecoveryReport {
        header,
        records,
        tail: TailStatus::Clean,
        last_complete_offset,
        next_sequence,
        last_record_sha256,
        unresolved: Vec::new(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        PrivacyClass, ReceiptEffectClass as EffectClass, ReceiptEvent,
        ReceiptLifecycleState as LifecycleState, ReceiptOutcome, ReceiptSource,
        inspect_receipt_journal,
    };
    use crate::receipt_journal_impl::persistence_tests::{Action, Armed};
    use std::fs::{self, OpenOptions};
    use std::io::Write;
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT_TEMP: AtomicU64 = AtomicU64::new(1);

    fn temp_dir(label: &str) -> PathBuf {
        let nonce = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "hepta-authoritative-export-{label}-{}-{nonce}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir(&path).expect("create temp directory");
        path
    }

    fn digest(value: u8) -> Digest {
        [value; 32]
    }

    fn event(receipt_id: &str, lifecycle: LifecycleState) -> ReceiptEvent {
        ReceiptEvent {
            receipt_id: receipt_id.to_owned(),
            plan_revision: "2026-08-29-d6".to_owned(),
            image_id: "image-fixture".to_owned(),
            servo_commit: "670ae8a70801b162e186f81cbb5bdd2d59c39108".to_owned(),
            browserd_version: "0.1.0".to_owned(),
            session_id: "session-1".to_owned(),
            session_generation: 1,
            document_generation: 1,
            semantic_snapshot_revision: 1,
            mutation_epoch: 1,
            source: ReceiptSource::Agent,
            operation: "page.observe".to_owned(),
            lifecycle,
            outcome: None,
            effect_class: EffectClass::Observation,
            privacy_class: PrivacyClass::Internal,
            request_sha256: digest(1),
            response_sha256: None,
            error_code: None,
            detail: None,
            monotonic_ms: lifecycle as u64,
            wall_clock_unix_ms: 1_000 + lifecycle as u64,
        }
    }

    fn append_complete(journal: &mut ReceiptJournal, receipt_id: &str) {
        journal
            .append(event(receipt_id, LifecycleState::Requested))
            .expect("append requested");
        journal
            .append(event(receipt_id, LifecycleState::Dispatched))
            .expect("append dispatched");
        let mut completed = event(receipt_id, LifecycleState::Completed);
        completed.outcome = Some(ReceiptOutcome::Succeeded);
        completed.response_sha256 = Some(digest(2));
        journal.append(completed).expect("append completed");
    }

    fn complete_journal(path: &Path) {
        let mut journal =
            ReceiptJournal::create(path, JournalId([7; 16]), 1).expect("create journal");
        append_complete(&mut journal, "receipt-1");
    }

    #[test]
    fn exact_clean_complete_legacy_chain_exports_under_locks() {
        let directory = temp_dir("clean");
        let journal = directory.join("journal.bin");
        let output = directory.join("receipt.jsonl");
        complete_journal(&journal);

        let result = export_receipt_envelopes_jsonl([&journal], &output);
        assert!(result.is_ok());
        let text = fs::read_to_string(&output).expect("read export");
        assert!(text.contains("\"status\":\"succeeded\""));
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn live_legacy_writer_is_busy_and_emits_no_authoritative_artifact() {
        let directory = temp_dir("busy");
        let journal_path = directory.join("journal.bin");
        let output = directory.join("receipt.jsonl");
        let mut writer = ReceiptJournal::create(&journal_path, JournalId([9; 16]), 1)
            .expect("create journal");
        append_complete(&mut writer, "receipt-busy");
        let result = export_receipt_envelopes_jsonl([&journal_path], &output);
        assert!(matches!(result, Err(JournalError::WriterBusy)));
        assert!(!output.exists());
        drop(writer);
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn managed_export_uses_closed_inventory_and_rejects_segment_shortcuts() {
        let directory = temp_dir("managed");
        let root = directory.join("store");
        let output = directory.join("receipt.jsonl");
        let id = JournalId([10; 16]);
        let mut writer = ReceiptJournal::create_managed(&root, id, 1).expect("create store");
        append_complete(&mut writer, "receipt-first");
        let (_, mut writer) = writer.rotate_managed(2).expect("rotate store");
        append_complete(&mut writer, "receipt-second");
        drop(writer);

        let first = root.join("segment-0000000000000001.journal");
        let shortcut = directory.join("shortcut.jsonl");
        assert!(matches!(
            export_receipt_envelopes_jsonl([&first], &shortcut),
            Err(JournalError::InvalidInput(message)) if message.contains("managed")
        ));
        assert!(!shortcut.exists());

        export_managed_receipt_envelopes_jsonl(&root, id, &output)
            .expect("managed authoritative export");
        let text = fs::read_to_string(&output).expect("read managed export");
        assert!(text.contains("receipt-first"));
        assert!(text.contains("receipt-second"));
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn prepublication_failure_leaves_no_final_or_stage_file() {
        let directory = temp_dir("prepublish-failure");
        let journal = directory.join("journal.bin");
        let output = directory.join("receipt.jsonl");
        complete_journal(&journal);
        let armed = Armed::new("export.before_publish", Action::Error(5));
        let result = export_receipt_envelopes_jsonl([&journal], &output);
        drop(armed);
        assert!(result.is_err());
        assert!(!output.exists());
        let leftovers: Vec<_> = fs::read_dir(&directory)
            .expect("read directory")
            .map(|entry| entry.expect("entry").file_name())
            .filter(|name| name.to_string_lossy().contains("receipt-export-stage"))
            .collect();
        assert!(leftovers.is_empty(), "unpublished stage leaked: {leftovers:?}");
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn postpublication_failure_is_typed_and_final_name_is_never_partial() {
        let directory = temp_dir("postpublish-failure");
        let journal = directory.join("journal.bin");
        let output = directory.join("receipt.jsonl");
        complete_journal(&journal);
        let armed = Armed::new("export.after_publish", Action::Error(5));
        let result = export_receipt_envelopes_jsonl([&journal], &output);
        drop(armed);
        assert!(matches!(result, Err(JournalError::PublicationUncertain)));
        let text = fs::read_to_string(&output).expect("published complete output");
        assert!(text.ends_with('\n'));
        assert!(text.contains("\"status\":\"succeeded\""));
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn torn_suffix_is_rejected_even_after_a_terminal_prefix() {
        let directory = temp_dir("torn");
        let journal = directory.join("journal.bin");
        let output = directory.join("receipt.jsonl");
        complete_journal(&journal);
        let mut file = OpenOptions::new()
            .append(true)
            .open(&journal)
            .expect("open journal");
        file.write_all(b"HPTREC01partial")
            .expect("append torn suffix");
        file.sync_data().expect("sync torn suffix");
        drop(file);

        assert!(matches!(
            export_receipt_envelopes_jsonl([&journal], &output),
            Err(JournalError::TornTailNeedsRepair { .. })
        ));
        assert!(!output.exists());
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn incomplete_lifecycle_is_rejected() {
        let directory = temp_dir("unresolved");
        let journal = directory.join("journal.bin");
        let output = directory.join("receipt.jsonl");
        let mut writer =
            ReceiptJournal::create(&journal, JournalId([8; 16]), 1).expect("create journal");
        writer
            .append(event("receipt-open", LifecycleState::Requested))
            .expect("append requested");
        drop(writer);

        assert!(matches!(
            export_receipt_envelopes_jsonl([&journal], &output),
            Err(JournalError::InvalidInput(message)) if message.contains("unresolved")
        ));
        assert!(!output.exists());
        fs::remove_dir_all(directory).expect("cleanup");
    }

    #[test]
    fn caller_constructed_report_is_forensic_only() {
        let directory = temp_dir("fabricated");
        let journal = directory.join("journal.bin");
        let forensic = directory.join("forensic.jsonl");
        complete_journal(&journal);
        let mut report = inspect_receipt_journal(&journal).expect("inspect");
        report.records[0].sequence = 900;
        report.records[0].record_sha256 = digest(99);

        assert!(export_forensic_prefix_jsonl(&report, &forensic).is_ok());
        assert!(forensic.exists());
        fs::remove_dir_all(directory).expect("cleanup");
    }
}
''',
        encoding="utf-8",
    )


def patch_lib() -> None:
    path = ROOT / "crates/hepta-session-core/src/lib.rs"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    export_forensic_prefix_jsonl, export_receipt_envelopes_jsonl, export_redacted_jsonl,\n",
        "    export_forensic_prefix_jsonl, export_managed_receipt_envelopes_jsonl,\n    export_managed_redacted_jsonl, export_receipt_envelopes_jsonl, export_redacted_jsonl,\n",
        "crate-root managed export",
    )
    path.write_text(text, encoding="utf-8")


def patch_contract() -> None:
    path = ROOT / "contracts/receipt-journal.v1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["durability"]["create_and_export"] = (
        "same_directory_private_stage_write_sync_all_verify_atomic_no_replace_publish_then_directory_sync"
    )
    data["durability"]["export_partial_final_name_observable"] = False
    data["durability"]["export_post_publish_failure"] = "typed_PublicationUncertain_no_overwrite_retry"
    data["exports"].update(
        {
            "authoritative_legacy_chain": "locked_writer_lease_plus_every_segment_inode_lock",
            "authoritative_managed_api": "export_managed_receipt_envelopes_jsonl",
            "authoritative_managed_inventory": "closed_directory_inventory_under_pinned_directory_lock",
            "managed_explicit_segment_shortcut": "rejected",
            "active_writer": "fail_closed_WriterBusy",
            "locks_held_through_publication": True,
            "destination_publication": "synced_private_stage_atomic_no_replace_hard_link_directory_sync",
        }
    )
    data["managed_store"]["trusted_ancestor_owners"] = ["root", "effective_service_uid"]
    data["managed_store"]["attacker_owned_0755_ancestor"] = "reject"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def patch_docs() -> None:
    path = ROOT / "docs/architecture/DURABLE_RECEIPT_JOURNAL.md"
    text = path.read_text(encoding="utf-8")
    appendix = r'''

## Locked authoritative export and atomic publication

Authoritative output never accepts a caller-constructed recovery report. A
legacy explicit chain is opened under the normal writer lease and every segment
inode lock; managed segment paths are rejected from that API. Managed export
uses `export_managed_receipt_envelopes_jsonl`, which acquires the pinned managed
directory lock, derives the entire closed canonical inventory, and retains the
directory and every segment lock through validation and publication. A live
writer therefore fails closed instead of producing a stale prefix.

The canonical JSONL name is installed only after a private same-directory inode
has been fully written, `sync_all`'d, reread, length/digest verified, and linked
atomically with no replacement. The directory is then synchronized. Failures
before the link leave no canonical output; failures after the link return the
typed `PublicationUncertain` result and callers must inspect the destination
without overwriting or blindly retrying it. Forensic report export uses the same
atomic publication primitive but remains non-authoritative because its input is
caller-constructible.

Every mutable non-root ancestor of journal or export paths must be owned by the
effective service UID; root-owned ancestors are accepted, with a root-owned
sticky directory as the only group/other-writable exception. An attacker-owned
`0755` ancestor is rejected because its owner can replace child entries.
'''
    if "## Locked authoritative export and atomic publication" not in text:
        text = text.rstrip() + appendix + "\n"
    path.write_text(text, encoding="utf-8")

    managed = ROOT / "docs/architecture/MANAGED_RECEIPT_STORE.md"
    text = managed.read_text(encoding="utf-8")
    appendix = r'''

## Authoritative read snapshot

Managed authoritative export never accepts a segment list. It locks the pinned
store directory, validates the marker, derives the full contiguous inventory,
locks every segment, and holds those locks through an atomic no-replace JSONL
publication. Explicit-path APIs reject managed segments so omitting a later
canonical segment cannot masquerade as a complete export. A concurrently open
writer is a `WriterBusy` failure.

Path custody requires each non-root ancestor to be owned by the effective
service UID. Root-owned ancestors are trusted, and only root-owned sticky
directories may be group/other writable. An attacker-owned `0755` ancestor is
not trusted even though its mode has no group/other write bit.
'''
    if "## Authoritative read snapshot" not in text:
        text = text.rstrip() + appendix + "\n"
    managed.write_text(text, encoding="utf-8")


def patch_python_contract_test() -> None:
    path = ROOT / "tests/test_s05_receipt_recovery.py"
    text = path.read_text(encoding="utf-8")
    method = r'''
    def test_authoritative_export_is_locked_complete_and_atomic(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/receipt-journal.v1.json").read_text(encoding="utf-8")
        )
        exports = contract["exports"]
        self.assertEqual(
            exports["authoritative_managed_api"],
            "export_managed_receipt_envelopes_jsonl",
        )
        self.assertEqual(exports["managed_explicit_segment_shortcut"], "rejected")
        self.assertEqual(exports["active_writer"], "fail_closed_WriterBusy")
        self.assertIs(exports["locks_held_through_publication"], True)
        self.assertIs(
            contract["durability"]["export_partial_final_name_observable"], False
        )
        self.assertEqual(
            contract["durability"]["export_post_publish_failure"],
            "typed_PublicationUncertain_no_overwrite_retry",
        )
        self.assertEqual(
            contract["managed_store"]["attacker_owned_0755_ancestor"], "reject"
        )

        source = (
            ROOT / "crates/hepta-session-core/src/receipt_journal.rs"
        ).read_text(encoding="utf-8")
        authority = (
            ROOT / "crates/hepta-session-core/src/authoritative_export.rs"
        ).read_text(encoding="utf-8")
        for required in (
            "open_authoritative_chain",
            "authoritative_reports",
            "export_managed_receipt_envelopes_jsonl",
            "fs::hard_link(&stage, destination)",
            "PublicationUncertain",
            "ancestor_owner_is_trusted",
        ):
            self.assertIn(required, source + authority)
'''
    marker = "\n\nif __name__ == \"__main__\":\n"
    if "test_authoritative_export_is_locked_complete_and_atomic" not in text:
        if marker not in text:
            raise SystemExit("could not locate unittest footer")
        text = text.replace(marker, "\n" + method + marker, 1)
    path.write_text(text, encoding="utf-8")


patch_receipt_journal()
write_authoritative_export()
patch_lib()
patch_contract()
patch_docs()
patch_python_contract_test()
