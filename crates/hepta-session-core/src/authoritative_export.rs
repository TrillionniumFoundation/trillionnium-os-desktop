//! Evidence-bearing receipt export from a locked, complete journal snapshot.
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
use crate::receipt_journal_impl::{JournalId, ManagedOpenPolicy, ReceiptJournal};

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
    let mut journal = ReceiptJournal::open_managed(root, journal_id, ManagedOpenPolicy::STRICT)?;
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
    use crate::receipt_journal_impl::persistence_tests::{Action, Armed};
    use crate::{
        PrivacyClass, ReceiptEffectClass as EffectClass, ReceiptEvent,
        ReceiptLifecycleState as LifecycleState, ReceiptOutcome, ReceiptSource,
        inspect_receipt_journal,
    };
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
        let mut writer =
            ReceiptJournal::create(&journal_path, JournalId([9; 16]), 1).expect("create journal");
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
        assert!(
            leftovers.is_empty(),
            "unpublished stage leaked: {leftovers:?}"
        );
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
