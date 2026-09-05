//! Semantic corruption remains corruption even when an attacker recomputes hashes.
use super::*;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(1);
struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "hepta-binding-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn path(&self) -> PathBuf {
        self.0.join("journal.hjr")
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn event(state: LifecycleState) -> ReceiptEvent {
    ReceiptEvent {
        receipt_id: "bound-1".into(),
        plan_revision: "2026-08-29-d6".into(),
        image_id: "image-1".into(),
        servo_commit: "670ae8a70801b162e186f81cbb5bdd2d59c39108".into(),
        browserd_version: "0.1.0".into(),
        session_id: "session-1".into(),
        session_generation: 1,
        document_generation: 1,
        semantic_snapshot_revision: 1,
        mutation_epoch: 1,
        source: ReceiptSource::Agent,
        operation: "page.observe".into(),
        lifecycle: state,
        outcome: None,
        effect_class: EffectClass::Observation,
        privacy_class: PrivacyClass::SecretRedacted,
        request_sha256: [1; 32],
        response_sha256: None,
        error_code: None,
        detail: None,
        monotonic_ms: 10,
        wall_clock_unix_ms: 20,
    }
}
type Mutation = (&'static str, fn(&mut ReceiptEvent));
fn mutations() -> Vec<Mutation> {
    vec![
        ("plan", |e| e.plan_revision = "2026-08-28-d5".into()),
        ("image", |e| e.image_id = "image-2".into()),
        ("servo", |e| e.servo_commit = "a".repeat(40)),
        ("version", |e| e.browserd_version = "0.2.0".into()),
        ("session", |e| e.session_id = "session-2".into()),
        ("session_generation", |e| e.session_generation += 1),
        ("document_generation", |e| e.document_generation += 1),
        ("semantic_revision", |e| e.semantic_snapshot_revision += 1),
        ("mutation_epoch", |e| e.mutation_epoch += 1),
        ("source", |e| e.source = ReceiptSource::Human),
        ("operation", |e| e.operation = "page.navigate".into()),
        ("effect", |e| {
            e.effect_class = EffectClass::PotentialExternalEffect
        }),
        ("privacy", |e| {
            e.privacy_class = PrivacyClass::Public;
            e.detail = Some("must-not-escape".into());
        }),
        ("request_digest", |e| e.request_sha256 = [2; 32]),
    ]
}
fn completed() -> ReceiptEvent {
    let mut e = event(LifecycleState::Completed);
    e.outcome = Some(ReceiptOutcome::Succeeded);
    e.response_sha256 = Some([3; 32]);
    e.monotonic_ms = 30;
    e
}

#[test]
fn lifecycle_binding_rejects_every_identity_drift_before_writing() {
    for (field, mutate) in mutations() {
        let dir = Directory::new();
        let path = dir.path();
        let mut writer = ReceiptJournal::create(&path, JournalId([41; 16]), 1).unwrap();
        writer.append(event(LifecycleState::Requested)).unwrap();
        let before = fs::read(&path).unwrap();
        let mut dispatch = event(LifecycleState::Dispatched);
        mutate(&mut dispatch);
        assert!(
            writer.append(dispatch).is_err(),
            "admitted drift in {field}"
        );
        assert_eq!(
            fs::read(&path).unwrap(),
            before,
            "modified file for {field}"
        );
        writer.append(event(LifecycleState::Dispatched)).unwrap();
        writer.append(completed()).unwrap();
        assert_eq!(writer.inspect().unwrap().records.len(), 3);
    }
}
#[test]
fn lifecycle_binding_checks_identity_again_after_reopen() {
    for (field, mutate) in mutations() {
        let dir = Directory::new();
        let path = dir.path();
        let mut writer = ReceiptJournal::create(&path, JournalId([42; 16]), 1).unwrap();
        writer.append(event(LifecycleState::Requested)).unwrap();
        drop(writer);
        let mut writer = ReceiptJournal::open(&path, OpenPolicy::STRICT).unwrap();
        let before = fs::read(&path).unwrap();
        let mut dispatch = event(LifecycleState::Dispatched);
        mutate(&mut dispatch);
        assert!(
            writer.append(dispatch).is_err(),
            "reopen lost {field} binding"
        );
        assert_eq!(fs::read(&path).unwrap(), before);
    }
}
#[test]
fn lifecycle_binding_recomputed_record_digest_does_not_hide_semantic_corruption() {
    for (field, mutate) in mutations() {
        let dir = Directory::new();
        let path = dir.path();
        let mut writer = ReceiptJournal::create(&path, JournalId([43; 16]), 1).unwrap();
        let record = writer.append(event(LifecycleState::Requested)).unwrap();
        drop(writer);
        let mut dispatch = event(LifecycleState::Dispatched);
        mutate(&mut dispatch);
        let (mut bytes, _) = encode_record(2, record.record_sha256, &dispatch).unwrap();
        bytes.extend_from_slice(b"HPTREC01");
        OpenOptions::new()
            .append(true)
            .open(&path)
            .unwrap()
            .write_all(&bytes)
            .unwrap();
        let before = fs::read(&path).unwrap();
        assert!(
            matches!(inspect_path(&path), Err(JournalError::Corruption { .. })),
            "accepted forged {field}"
        );
        assert!(
            ReceiptJournal::open_chain([&path], JournalId([43; 16]), OpenPolicy::RECOVER_CRASH)
                .is_err()
        );
        assert_eq!(fs::read(&path).unwrap(), before, "repaired corrupt {field}");
    }
}
#[test]
fn lifecycle_binding_envelope_rejects_request_effect_and_privacy_drift() {
    for (field, mutate) in mutations() {
        let mut terminal = completed();
        mutate(&mut terminal);
        let records = vec![
            event(LifecycleState::Requested),
            event(LifecycleState::Dispatched),
            terminal,
        ]
        .into_iter()
        .enumerate()
        .map(|(i, event)| RecoveredRecord {
            sequence: i as u64 + 1,
            record_sha256: [9; 32],
            event,
        })
        .collect::<Vec<_>>();
        assert!(
            ReceiptEnvelope::from_records(&records).is_err(),
            "export hid {field} drift"
        );
    }
}
#[test]
fn lifecycle_binding_preserves_multiclock_journal_and_rejects_negative_export_duration() {
    let dir = Directory::new();
    let path = dir.path();
    let mut writer = ReceiptJournal::create(&path, JournalId([44; 16]), 1).unwrap();
    writer.append(event(LifecycleState::Requested)).unwrap();
    let mut dispatch = event(LifecycleState::Dispatched);
    dispatch.monotonic_ms = 9;
    writer.append(dispatch).unwrap();
    let mut terminal = completed();
    terminal.monotonic_ms = 8;
    writer.append(terminal).unwrap();
    assert_eq!(writer.last_monotonic_ms(), 10);
    let report = writer.inspect().unwrap();
    assert!(ReceiptEnvelope::from_records(&report.records).is_err());
}
#[test]
fn lifecycle_binding_independent_receipt_clocks_and_equal_timestamps_remain_valid() {
    let dir = Directory::new();
    let mut writer = ReceiptJournal::create(dir.path(), JournalId([45; 16]), 1).unwrap();
    let mut a = event(LifecycleState::Requested);
    a.monotonic_ms = 100;
    writer.append(a.clone()).unwrap();
    let mut b = event(LifecycleState::Requested);
    b.receipt_id = "independent".into();
    b.monotonic_ms = 1;
    writer.append(b.clone()).unwrap();
    b.lifecycle = LifecycleState::Dispatched;
    writer.append(b).unwrap();
    a.lifecycle = LifecycleState::Dispatched;
    a.wall_clock_unix_ms = 1;
    writer.append(a).unwrap();
    assert_eq!(writer.inspect().unwrap().records.len(), 4);
}

#[test]
fn lifecycle_binding_forensic_export_rejects_drift_before_creating_output() {
    for (field, mutate) in mutations() {
        let dir = Directory::new();
        let mut writer = ReceiptJournal::create(dir.path(), JournalId([46; 16]), 1).unwrap();
        writer.append(event(LifecycleState::Requested)).unwrap();
        writer.append(event(LifecycleState::Dispatched)).unwrap();
        let mut report = writer.inspect().unwrap();
        mutate(&mut report.records[1].event);
        let output = dir.0.join("untrusted.jsonl");
        assert!(
            export_journal_redacted_jsonl(&report, &output).is_err(),
            "forensic export hid {field} drift"
        );
        assert!(!output.exists(), "failed export created output for {field}");
    }
}

#[test]
fn lifecycle_binding_forensic_export_keeps_valid_unresolved_redaction() {
    let dir = Directory::new();
    let mut writer = ReceiptJournal::create(dir.path(), JournalId([47; 16]), 1).unwrap();
    writer.append(event(LifecycleState::Requested)).unwrap();
    writer.append(event(LifecycleState::Dispatched)).unwrap();
    let report = writer.inspect().unwrap();
    let output = dir.0.join("forensic.jsonl");
    export_journal_redacted_jsonl(&report, &output).unwrap();
    let text = fs::read_to_string(output).unwrap();
    assert_eq!(text.lines().count(), 2);
    assert!(text.lines().all(|line| line.contains("\"detail\":null")));
    assert!(!text.contains("succeeded"));
    assert!(export_redacted_jsonl(&report, dir.0.join("public.jsonl")).is_err());
    assert!(!dir.0.join("public.jsonl").exists());
}

#[test]
fn lifecycle_binding_rotated_chain_rejects_rehashed_active_drift_without_repair() {
    for (field, mutate) in mutations() {
        let dir = Directory::new();
        let first = dir.path();
        let second = dir.0.join("successor.hjr");
        let id = JournalId([48; 16]);
        let mut writer = ReceiptJournal::create(&first, id, 1).unwrap();
        writer.append(event(LifecycleState::Requested)).unwrap();
        writer.append(event(LifecycleState::Dispatched)).unwrap();
        writer.append(completed()).unwrap();
        let (_, mut writer) = writer.rotate(&second, 2).unwrap();
        let mut request = event(LifecycleState::Requested);
        request.receipt_id = "next-receipt".into();
        let record = writer.append(request.clone()).unwrap();
        drop(writer);
        let mut dispatch = request;
        dispatch.lifecycle = LifecycleState::Dispatched;
        mutate(&mut dispatch);
        let (mut bytes, _) =
            encode_record(record.sequence + 1, record.record_sha256, &dispatch).unwrap();
        bytes.extend_from_slice(b"HPTREC01");
        OpenOptions::new()
            .append(true)
            .open(&second)
            .unwrap()
            .write_all(&bytes)
            .unwrap();
        let first_before = fs::read(&first).unwrap();
        let second_before = fs::read(&second).unwrap();
        assert!(
            inspect_chain([&first, &second]).is_err(),
            "chain inspection accepted {field} drift"
        );
        assert!(
            ReceiptJournal::open_chain([&first, &second], id, OpenPolicy::RECOVER_CRASH).is_err()
        );
        assert_eq!(fs::read(&first).unwrap(), first_before);
        assert_eq!(
            fs::read(&second).unwrap(),
            second_before,
            "repaired {field} semantic corruption"
        );
    }
}
