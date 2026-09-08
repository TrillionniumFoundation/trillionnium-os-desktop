use super::*;
use hepta_session_core::{ReceiptEvent, ReceiptSource, TailStatus};
use std::io::Write;
use std::sync::atomic::{AtomicU64, Ordering};
static UNIQUE: AtomicU64 = AtomicU64::new(0);
struct Temp(PathBuf);
impl Temp {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "hepta-d3-store-{}-{}",
            std::process::id(),
            UNIQUE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn path(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
}
impl Drop for Temp {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn event(id: &str, lifecycle: ReceiptLifecycleState, privacy: PrivacyClass) -> ReceiptEvent {
    ReceiptEvent {
        receipt_id: id.into(),
        plan_revision: "2026-08-29-d6".into(),
        image_id: "store-fixture".into(),
        servo_commit: "670ae8a70801b162e186f81cbb5bdd2d59c39108".into(),
        browserd_version: "0.1.0".into(),
        session_id: "session-1".into(),
        session_generation: 1,
        document_generation: 1,
        semantic_snapshot_revision: 1,
        mutation_epoch: 0,
        source: ReceiptSource::Agent,
        operation: "page_observe".into(),
        lifecycle,
        outcome: None,
        effect_class: ReceiptEffectClass::PotentialExternalEffect,
        privacy_class: privacy,
        request_sha256: [1; 32],
        response_sha256: None,
        error_code: None,
        detail: None,
        monotonic_ms: 500,
        wall_clock_unix_ms: 1000,
    }
}
#[test]
fn recovery_preserves_secret_redaction_and_never_invents_a_result() {
    let temp = Temp::new();
    let path = temp.path("active");
    let mut writer = open_or_create(&path, &[]).unwrap();
    for state in [
        ReceiptLifecycleState::Requested,
        ReceiptLifecycleState::Dispatched,
    ] {
        writer
            .append(event("secret-op", state, PrivacyClass::SecretRedacted))
            .unwrap();
    }
    drop(writer);
    let mut writer = open_or_create(&path, &[]).unwrap();
    assert_eq!(
        reconcile_unresolved(&mut writer).expect("secret receipt must remain recoverable"),
        1
    );
    assert_eq!(reconcile_unresolved(&mut writer).unwrap(), 0);
    let report = writer.inspect().unwrap();
    let terminal = &report.records.last().unwrap().event;
    assert_eq!(terminal.lifecycle, ReceiptLifecycleState::Indeterminate);
    assert_eq!(terminal.detail, None);
    assert_eq!(terminal.response_sha256, None);
    assert_eq!(terminal.outcome, None);
}
#[test]
fn explicit_chain_reopen_recovers_only_active_facts_and_inherits_clock() {
    let temp = Temp::new();
    let first = temp.path("first");
    let second = temp.path("second");
    let mut writer = open_or_create(&first, &[]).unwrap();
    writer
        .append(event(
            "prior",
            ReceiptLifecycleState::Requested,
            PrivacyClass::Internal,
        ))
        .unwrap();
    reconcile_unresolved(&mut writer).unwrap();
    let (_, mut writer) = writer.rotate(&second, 2).unwrap();
    writer
        .append(event(
            "active",
            ReceiptLifecycleState::Requested,
            PrivacyClass::Internal,
        ))
        .unwrap();
    drop(writer);
    let mut writer = open_or_create(&second, &[first]).unwrap();
    assert_eq!(reconcile_unresolved(&mut writer).unwrap(), 1);
    let report = writer.inspect().unwrap();
    assert!(report.unresolved.is_empty());
    assert_eq!(report.tail, TailStatus::Clean);
    assert!(report.records.last().unwrap().event.monotonic_ms > 501);
    assert!(
        writer
            .append(event(
                "prior",
                ReceiptLifecycleState::Requested,
                PrivacyClass::Internal
            ))
            .is_err()
    );
}
#[test]
fn missing_active_never_creates_an_empty_replacement_for_an_existing_chain() {
    let temp = Temp::new();
    let active = temp.path("absent");
    let prior = temp.path("prior");
    assert!(open_or_create(&active, &[prior]).is_err());
    assert!(!active.exists());
}
#[test]
fn wrong_journal_identity_does_not_truncate_its_tail() {
    let temp = Temp::new();
    let path = temp.path("wrong-id");
    drop(ReceiptJournal::create(&path, JournalId([1; 16]), 1).unwrap());
    std::fs::OpenOptions::new()
        .append(true)
        .open(&path)
        .unwrap()
        .write_all(b"HPTREC01")
        .unwrap();
    let before = fs::read(&path).unwrap();
    assert!(open_or_create(&path, &[]).is_err());
    assert_eq!(fs::read(&path).unwrap(), before);
}
#[test]
fn configured_paths_are_exact_and_not_silently_normalized() {
    let active = Path::new(JOURNAL_PATH);
    assert!(parse_predecessors(active, None).unwrap().is_empty());
    let prior = format!("{JOURNAL_ROOT}/first.journal");
    assert_eq!(
        parse_predecessors(active, Some(&prior)).unwrap(),
        vec![PathBuf::from(&prior)]
    );
    for invalid in [
        "".to_owned(),
        format!("{prior}:{prior}"),
        format!("{prior}:"),
        JOURNAL_PATH.into(),
        "/tmp/foreign".into(),
        format!("{JOURNAL_ROOT}/./a"),
        format!("{JOURNAL_ROOT}//a"),
        format!("{JOURNAL_ROOT}/a/../b"),
        format!("{JOURNAL_ROOT}/a\nb"),
        format!("{JOURNAL_ROOT}/a\\b"),
    ] {
        assert!(
            parse_predecessors(active, Some(&invalid)).is_err(),
            "accepted {invalid:?}"
        );
    }
}
#[test]
fn overlong_predecessor_configuration_is_rejected() {
    let text = (0..64)
        .map(|n| format!("{JOURNAL_ROOT}/segment-{n}"))
        .collect::<Vec<_>>()
        .join(":");
    assert!(parse_predecessors(Path::new(JOURNAL_PATH), Some(&text)).is_err());
}
#[test]
fn dangling_active_link_is_not_treated_as_a_missing_file() {
    let temp = Temp::new();
    let active = temp.path("link");
    let target = temp.path("missing");
    std::os::unix::fs::symlink(&target, &active).unwrap();
    assert!(open_or_create(&active, &[]).is_err());
    assert!(!target.exists());
}

#[test]
fn managed_configuration_is_opt_in_and_never_mixes_legacy_paths() {
    use std::ffi::OsStr;
    let root = format!("{JOURNAL_ROOT}/managed");
    assert_eq!(parse_managed_path(None, true, true).unwrap(), None);
    assert_eq!(
        parse_managed_path(Some(OsStr::new(&root)), false, false).unwrap(),
        Some(PathBuf::from(&root))
    );
    for (journal, predecessors) in [(true, false), (false, true), (true, true)] {
        assert!(parse_managed_path(Some(OsStr::new(&root)), journal, predecessors).is_err());
    }
    for bad in [
        "",
        "/tmp/not-development",
        "/var/lib/hepta-browserd/development/../escape",
    ] {
        assert!(parse_managed_path(Some(OsStr::new(bad)), false, false).is_err());
    }
}
#[test]
fn managed_storage_reopens_latest_head_and_reconciles_without_replaying() {
    let temp = Temp::new();
    let root = temp.path("managed");
    let mut writer = open_or_create_managed(&root).unwrap();
    writer
        .append(event(
            "prior",
            ReceiptLifecycleState::Requested,
            PrivacyClass::Internal,
        ))
        .unwrap();
    assert_eq!(reconcile_unresolved(&mut writer).unwrap(), 1);
    let (_, mut writer) = writer.rotate_managed(2).unwrap();
    for state in [
        ReceiptLifecycleState::Requested,
        ReceiptLifecycleState::Dispatched,
    ] {
        writer
            .append(event("external", state, PrivacyClass::SecretRedacted))
            .unwrap();
    }
    drop(writer);
    let mut writer = open_or_create_managed(&root).unwrap();
    assert_eq!(reconcile_unresolved(&mut writer).unwrap(), 1);
    assert_eq!(reconcile_unresolved(&mut writer).unwrap(), 0);
    let report = writer.inspect().unwrap();
    let terminal = &report.records.last().unwrap().event;
    assert_eq!(terminal.lifecycle, ReceiptLifecycleState::Indeterminate);
    assert_eq!(terminal.detail, None);
    assert_eq!(terminal.outcome, None);
    assert!(
        writer
            .append(event(
                "prior",
                ReceiptLifecycleState::Requested,
                PrivacyClass::Internal
            ))
            .is_err()
    );
}
#[test]
fn existing_uninitialized_or_legacy_directory_is_not_reinitialized() {
    let temp = Temp::new();
    let root = temp.path("managed");
    fs::create_dir(&root).unwrap();
    fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
    assert!(open_or_create_managed(&root).is_err());
    assert_eq!(fs::read_dir(&root).unwrap().count(), 0);
    drop(open_or_create(&root.join("legacy"), &[]).unwrap());
    let before = fs::read(root.join("legacy")).unwrap();
    assert!(open_or_create_managed(&root).is_err());
    assert_eq!(fs::read(root.join("legacy")).unwrap(), before);
    assert!(!root.join("store.v1").exists());
}
