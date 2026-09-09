//! Shared private disk fixtures; no executable or ignored tests.
use hepta_session_core::{
    JournalId, PrivacyClass, ReceiptEffectClass, ReceiptEvent, ReceiptJournal,
    ReceiptLifecycleState as State, ReceiptSource,
};
use std::fs;
use std::os::unix::fs::DirBuilderExt;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

pub(crate) const ID: JournalId = JournalId([0x53; 16]);
static UNIQUE: AtomicU64 = AtomicU64::new(1);
pub(crate) struct Temp(pub(crate) PathBuf);
impl Temp {
    pub(crate) fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "hepta-chain-reopen-{}-{}",
            std::process::id(),
            UNIQUE.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::DirBuilder::new()
            .mode(0o700)
            .create(&path)
            .expect("fresh private test directory");
        Self(path)
    }
    pub(crate) fn path(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
}
impl Drop for Temp {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
pub(crate) fn event(id: &str, state: State) -> ReceiptEvent {
    ReceiptEvent {
        receipt_id: id.into(),
        plan_revision: "2026-08-29-d6".into(),
        image_id: "chain-reopen-fixture".into(),
        servo_commit: "670ae8a70801b162e186f81cbb5bdd2d59c39108".into(),
        browserd_version: "0.1.0".into(),
        session_id: "session-1".into(),
        session_generation: 1,
        document_generation: 1,
        semantic_snapshot_revision: 1,
        mutation_epoch: 0,
        source: ReceiptSource::Agent,
        operation: "page_observe".into(),
        lifecycle: state,
        outcome: None,
        effect_class: ReceiptEffectClass::Observation,
        privacy_class: PrivacyClass::Internal,
        request_sha256: [1; 32],
        response_sha256: None,
        error_code: if state.is_terminal() {
            Some("internal".into())
        } else {
            None
        },
        detail: None,
        monotonic_ms: 100,
        wall_clock_unix_ms: 200,
    }
}
pub(crate) fn rotated(root: &Temp) -> (PathBuf, PathBuf) {
    let first = root.path("segment-1.journal");
    let second = root.path("segment-2.journal");
    let mut writer = ReceiptJournal::create(&first, ID, 1).expect("create");
    writer
        .append(event("prior-id", State::Requested))
        .expect("request");
    writer
        .append(event("prior-id", State::Interrupted))
        .expect("terminal");
    let (_, next) = writer.rotate(&second, 2).expect("rotate");
    drop(next);
    (first, second)
}
