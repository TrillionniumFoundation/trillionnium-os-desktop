//! Service-loop handoff tests; no activation, socket, principal attestation or Servo claim.
use super::*;
use hepta_browser_actor::MechanismIdentity;
use hepta_session_core::{
    PrivacyClass, ReceiptEffectClass, ReceiptEvent, ReceiptLifecycleState as State, ReceiptSource,
};
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
static UNIQUE: AtomicU64 = AtomicU64::new(0);
struct Store(
    PathBuf,
    hepta_browser_actor::engine_dispatch::EngineThreadOwner<AtomicFixtureRuntime>,
);
impl Drop for Store {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn ready_state() -> (Store, Option<SessionState>) {
    let path = std::env::temp_dir().join(format!(
        "hepta-service-rotation-{}-{}",
        std::process::id(),
        UNIQUE.fetch_add(1, Ordering::Relaxed)
    ));
    let mut journal = storage::open_or_create_managed(&path).unwrap();
    let mut count = 0;
    while !journal.managed_rotation_due() {
        count += 1;
        assert!(count < 2000);
        for lifecycle in [State::Requested, State::Interrupted] {
            journal
                .append(ReceiptEvent {
                    receipt_id: format!("rotate-{count}"),
                    plan_revision: "2026-08-29-d6".into(),
                    image_id: "service-rotation-fixture".into(),
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
                    effect_class: ReceiptEffectClass::Observation,
                    privacy_class: PrivacyClass::Internal,
                    request_sha256: [1; 32],
                    response_sha256: None,
                    error_code: lifecycle.is_terminal().then(|| "internal".into()),
                    detail: Some("x".repeat(4096)),
                    monotonic_ms: 100,
                    wall_clock_unix_ms: 200,
                })
                .unwrap();
        }
    }
    let peer = PeerIdentity {
        pid: Some(42),
        uid: 1000,
        gid: 1001,
    };
    let binding = PrincipalBinding::bind(
        TaskFlowPrincipal {
            principal_id: "fixture-principal".into(),
            expected_uid: 1000,
            expected_gid: 1001,
            expected_systemd_unit: "hepta-agent.service".into(),
            expected_cgroup_v2_path: "/system.slice/hepta-agent.service".into(),
            expected_executable_sha256: "1".repeat(64),
        },
        MechanismIdentity {
            peer,
            systemd_unit: "hepta-agent.service".into(),
            cgroup_v2_path: "/system.slice/hepta-agent.service".into(),
            executable_sha256: "1".repeat(64),
        },
    )
    .unwrap();
    let (runtime, owner) = hepta_browser_actor::engine_dispatch::engine_thread_pair(
        AtomicFixtureRuntime::default(),
        std::sync::Arc::new(|| {}),
    );
    let actor = BrowserActor::new(binding, runtime);
    let observer = actor.receipt_observer(journal, "service-fixture");
    (
        Store(path, owner),
        Some(SessionState {
            peer,
            peer_snapshot: PeerRuntimeSnapshot {
                pid: 42,
                uid: 1000,
                gid: 1001,
                start_time_ticks: 100,
                systemd_unit: Some("hepta-agent.service".into()),
                cgroup_v2_path: "/system.slice/hepta-agent.service".into(),
                executable_sha256: "1".repeat(64),
            },
            actor,
            observer,
        }),
    )
}
#[test]
fn service_rotates_only_an_idle_managed_writer_and_keeps_the_session() {
    let (store, mut state) = ready_state();
    let _owner_guard = &store.1;
    let prior = state.as_ref().unwrap().observer.journal_path().to_owned();
    let peer = state.as_ref().unwrap().peer;
    assert!(state.as_ref().unwrap().observer.managed_rotation_due());
    rotate_quiescent_store(&mut state).unwrap();
    let current = state.as_ref().unwrap();
    assert!(same_peer(current.peer, peer));
    assert_ne!(current.observer.journal_path(), prior);
    assert_eq!(
        current.observer.journal_path().file_name().unwrap(),
        "segment-0000000000000002.journal"
    );
    assert!(!current.observer.managed_rotation_due());
    assert!(!store.0.join("next.pending").exists());
    rotate_quiescent_store(&mut state).unwrap();
    assert_eq!(fs::read_dir(&store.0).unwrap().count(), 3);
    drop(state);
}
#[test]
fn service_rotation_failure_does_not_replace_an_uncertain_writer() {
    let (store, mut state) = ready_state();
    let _owner_guard = &store.1;
    fs::write(store.0.join("unexpected"), b"refuse").unwrap();
    assert!(rotate_quiescent_store(&mut state).is_err());
    assert!(state.is_none(), "failed consumed writer must not be reused");
    assert!(!store.0.join("segment-0000000000000002.journal").exists());
    assert!(!store.0.join("next.pending").exists());
}
#[test]
fn service_without_an_admitted_session_has_nothing_to_rotate() {
    let mut state = None;
    rotate_quiescent_store(&mut state).unwrap();
    assert!(state.is_none());
}
