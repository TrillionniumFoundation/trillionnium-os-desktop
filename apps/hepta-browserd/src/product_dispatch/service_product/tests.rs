//! Ordinary private mechanics and complete real managed-store readback only.
//! No fixture Source/Binding, native effects, Report or product admission proof.
use super::*;
use hepta_session_core::JournalId;
use std::fs;
use std::os::unix::fs::DirBuilderExt;
use std::path::PathBuf;
use std::sync::atomic::AtomicU64;

static NEXT_STORE: AtomicU64 = AtomicU64::new(0);

struct StoreFixture(PathBuf);
impl StoreFixture {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "hepta-p2c-store-{}-{}",
            std::process::id(),
            NEXT_STORE.fetch_add(1, Ordering::SeqCst)
        ));
        fs::DirBuilder::new().mode(0o700).create(&path).unwrap();
        Self(path)
    }
    fn journal(&self) -> ReceiptJournal {
        ReceiptJournal::create_managed(self.0.join("receipts"), JournalId([0x62; 16]), 1).unwrap()
    }
}
impl Drop for StoreFixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn event(lifecycle: ReceiptLifecycleState, clock: u64) -> ReceiptEvent {
    ReceiptEvent {
        receipt_id: "original-history".to_owned(),
        plan_revision: "2026-08-29-d6".to_owned(),
        image_id: "source-test".to_owned(),
        servo_commit: "670ae8a70801b162e186f81cbb5bdd2d59c39108".to_owned(),
        browserd_version: "0.1.0".to_owned(),
        session_id: "source-session".to_owned(),
        session_generation: 1,
        document_generation: 1,
        semantic_snapshot_revision: 1,
        mutation_epoch: 0,
        source: ReceiptSource::Agent,
        operation: "page_navigate".to_owned(),
        lifecycle,
        outcome: (lifecycle == ReceiptLifecycleState::Completed)
            .then_some(ReceiptOutcome::Succeeded),
        effect_class: ReceiptEffectClass::PotentialExternalEffect,
        privacy_class: PrivacyClass::Internal,
        request_sha256: [0x73; 32],
        response_sha256: (lifecycle == ReceiptLifecycleState::Completed).then_some([0x74; 32]),
        error_code: matches!(
            lifecycle,
            ReceiptLifecycleState::Indeterminate | ReceiptLifecycleState::Interrupted
        )
        .then(|| "internal".to_owned()),
        detail: None,
        monotonic_ms: clock,
        wall_clock_unix_ms: clock + 100,
    }
}

#[test]
fn normal_actor_token_retirement_is_not_remote_cancel() {
    let latch = ServiceCancellationLatch::new();
    let token = CancellationToken::new();
    latch.install(token.clone()).unwrap();
    token.cancel();
    assert!(token.is_cancelled());
    assert!(latch.current().is_ok());
    latch.cancel();
    assert_eq!(latch.current(), Err(ProductDispatchError::Cancelled));
}

#[test]
fn actual_cancel_before_token_install_cannot_be_lost() {
    let latch = ServiceCancellationLatch::new();
    let token = CancellationToken::new();
    latch.cancel();
    assert_eq!(
        latch.install(token.clone()),
        Err(ProductDispatchError::Cancelled)
    );
    assert!(token.is_cancelled());
}

#[test]
fn local_unwind_denies_token_and_never_fabricates_remote_cancel() {
    let latch = Arc::new(ServiceCancellationLatch::new());
    let token = CancellationToken::new();
    latch.install(token.clone()).unwrap();
    let quarantine = Arc::new(AtomicBool::new(false));
    drop(InvocationUnwind {
        quarantine: quarantine.clone(),
        cancellation: latch.clone(),
        armed: true,
    });
    assert!(quarantine.load(Ordering::SeqCst));
    assert!(token.is_cancelled());
    assert!(latch.current().is_ok());
}

#[test]
fn receipt_digest_refuses_wrong_length_uppercase_and_zero() {
    assert!(parse_digest(&"73".repeat(32)).is_ok());
    for wrong in [
        "73".repeat(31),
        "AB".repeat(32),
        "00".repeat(32),
        "gx".repeat(32),
    ] {
        assert_eq!(
            parse_digest(&wrong),
            Err(ProductDispatchError::StorageUnavailable)
        );
    }
}

#[test]
fn actual_managed_requested_and_terminal_uncertainty_refuse_idle() {
    for terminal in [
        None,
        Some(ReceiptLifecycleState::Indeterminate),
        Some(ReceiptLifecycleState::Interrupted),
    ] {
        let fixture = StoreFixture::new();
        let mut journal = fixture.journal();
        lifecycle::validate_managed_history(&mut journal).unwrap();
        journal
            .append(event(ReceiptLifecycleState::Requested, 1))
            .unwrap();
        assert_eq!(
            lifecycle::validate_managed_history(&mut journal),
            Err(ProductDispatchError::RecoveryRequired)
        );
        if let Some(terminal) = terminal {
            journal
                .append(event(ReceiptLifecycleState::Dispatched, 2))
                .unwrap();
            journal.append(event(terminal, 3)).unwrap();
            let (_, mut next) = journal.rotate_managed(4).unwrap();
            assert!(!next.has_unresolved_receipts().unwrap());
            assert_eq!(
                lifecycle::validate_managed_history(&mut next),
                Err(ProductDispatchError::RecoveryRequired)
            );
        }
    }
}

#[test]
fn sealed_predecessor_duplicate_is_visible_from_complete_locked_history() {
    let fixture = StoreFixture::new();
    let mut journal = fixture.journal();
    journal
        .append(event(ReceiptLifecycleState::Requested, 1))
        .unwrap();
    journal
        .append(event(ReceiptLifecycleState::Dispatched, 2))
        .unwrap();
    let committed = journal
        .append(event(ReceiptLifecycleState::Completed, 3))
        .unwrap();
    let (_, mut next) = journal.rotate_managed(4).unwrap();
    lifecycle::validate_managed_history(&mut next).unwrap();
    assert!(next.contains_receipt("original-history").unwrap());
    let fact = next.receipt_fact("original-history", [0x73; 32]).unwrap();
    assert_eq!(fact.record_sha256().unwrap(), committed.record_sha256);
    fs::rename(
        fixture.0.join("receipts/segment-0000000000000001.journal"),
        fixture.0.join("preserved"),
    )
    .unwrap();
    fs::write(
        fixture.0.join("receipts/segment-0000000000000001.journal"),
        b"different source",
    )
    .unwrap();
    assert_eq!(
        lifecycle::validate_managed_history(&mut next),
        Err(ProductDispatchError::StorageUnavailable)
    );
}
