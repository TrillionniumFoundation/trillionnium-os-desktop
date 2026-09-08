//! Evidence-bearing receipt export from an exact, complete journal chain.
//!
//! Public callers cannot supply a `RecoveryReport` to the authoritative API.
//! Reports remain useful for forensic inspection, but they are ordinary public
//! data structures and therefore are not authentication capabilities.

use std::collections::HashMap;
use std::path::Path;

use crate::receipt_journal::{
    self, Digest, JournalError, RecoveredRecord, RecoveryReport, TailStatus,
};

/// Export canonical operation envelopes from an ordered, complete journal chain.
///
/// Each source path is reopened and decoded by `inspect_chain`; segment one is
/// mandatory and cross-segment IDs, numbers, sequence continuity, predecessor
/// digests, and record digests are verified from the stored bytes. Every
/// segment must have a clean tail and every receipt must have a terminal fact.
/// A caller-constructed `RecoveryReport` cannot enter this interface.
///
/// ```compile_fail
/// use hepta_session_core::{RecoveryReport, export_receipt_envelopes_jsonl};
/// fn fabricated(report: &RecoveryReport) {
///     let _ = export_receipt_envelopes_jsonl(report, "/tmp/evidence.jsonl");
/// }
/// ```
pub fn export_receipt_envelopes_jsonl<I, P>(
    source_chain: I,
    destination: impl AsRef<Path>,
) -> Result<Digest, JournalError>
where
    I: IntoIterator<Item = P>,
    P: AsRef<Path>,
{
    let reports = receipt_journal::inspect_chain(source_chain)?;
    validate_complete_reports(&reports)?;
    let combined = combine_verified_reports(reports)?;
    receipt_journal::export_receipt_envelopes_jsonl(&combined, destination)
}

/// Compatibility name for canonical public receipt envelopes.
///
/// Unlike the retired report-based function, this alias also requires an
/// ordered complete source chain and reopens the journal bytes itself.
pub fn export_redacted_jsonl<I, P>(
    source_chain: I,
    destination: impl AsRef<Path>,
) -> Result<Digest, JournalError>
where
    I: IntoIterator<Item = P>,
    P: AsRef<Path>,
{
    let reports = receipt_journal::inspect_chain(source_chain)?;
    validate_complete_reports(&reports)?;
    let combined = combine_verified_reports(reports)?;
    receipt_journal::export_redacted_jsonl(&combined, destination)
}

/// Export a forensic prefix from an already decoded report.
///
/// This output is deliberately **non-authoritative**. The report may be
/// caller-constructed and may represent a clean prefix before a torn tail. It
/// must not be used as admission, terminal-lifecycle, cutover, or release
/// evidence.
pub fn export_forensic_prefix_jsonl(
    report: &RecoveryReport,
    destination: impl AsRef<Path>,
) -> Result<Digest, JournalError> {
    receipt_journal::export_journal_redacted_jsonl(report, destination)
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
        JournalId, PrivacyClass, ReceiptEffectClass as EffectClass, ReceiptEvent, ReceiptJournal,
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

    fn complete_journal(path: &Path) {
        let mut journal =
            ReceiptJournal::create(path, JournalId([7; 16]), 1).expect("create journal");
        journal
            .append(event("receipt-1", LifecycleState::Requested))
            .expect("append requested");
        journal
            .append(event("receipt-1", LifecycleState::Dispatched))
            .expect("append dispatched");
        let mut completed = event("receipt-1", LifecycleState::Completed);
        completed.outcome = Some(ReceiptOutcome::Succeeded);
        completed.response_sha256 = Some(digest(2));
        journal.append(completed).expect("append completed");
    }

    #[test]
    fn exact_clean_complete_chain_exports() {
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
        // There is intentionally no authoritative API that accepts `report`;
        // the compile-fail example on the public function locks that boundary.
        fs::remove_dir_all(directory).expect("cleanup");
    }
}
