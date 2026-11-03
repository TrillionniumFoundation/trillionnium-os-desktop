use os_control::{
    ManagementError, ManagementGrantConfig, ManagementGrantId, ManagementGrantState, PublisherId,
    ResourceDomainId, StableObjectId,
};

fn config() -> ManagementGrantConfig {
    ManagementGrantConfig {
        id: ManagementGrantId::from_u128(1),
        publisher: PublisherId::from_u128(2),
        target: ResourceDomainId::from_u128(3),
        stable_object_id: StableObjectId::from_u128(4),
        epoch: 1,
        issued_at_ns: 10,
        expires_at_ns: 100,
        max_cap_ns: 50_000_000,
    }
}

#[test]
fn closure_matches_the_original_instance_before_and_after_revoke() {
    let mut state = ManagementGrantState::new(config()).unwrap();
    let snapshot = state.snapshot().unwrap();
    assert!(state.owns_snapshot(&snapshot));
    let receipt = state.revoke_for_snapshot(&snapshot).unwrap();
    assert!(state.is_revoked());
    assert!(state.owns_snapshot(&snapshot));
    assert_eq!(state.revoke_for_snapshot(&snapshot), Ok(receipt));
    assert_eq!(state.snapshot(), Err(ManagementError::Revoked));
}

#[test]
fn identical_public_terms_cannot_revoke_a_replacement_instance() {
    let mut old = ManagementGrantState::new(config()).unwrap();
    let snapshot = old.snapshot().unwrap();
    old.revoke();
    drop(old);
    let mut replacement = ManagementGrantState::new(config()).unwrap();
    assert!(!replacement.owns_snapshot(&snapshot));
    assert_eq!(
        replacement.revoke_for_snapshot(&snapshot),
        Err(ManagementError::SnapshotMismatch)
    );
    assert!(!replacement.is_revoked());
    assert_eq!(replacement.current_epoch(), 1);
    let fresh = replacement.snapshot().unwrap();
    assert_ne!(fresh, snapshot);
    assert!(replacement.revoke_for_snapshot(&fresh).is_ok());
}

#[test]
fn retained_first_snapshot_never_matches_later_recreated_states() {
    let state = ManagementGrantState::new(config()).unwrap();
    let first = state.snapshot().unwrap();
    drop(state);
    for _ in 0..512 {
        let mut replacement = ManagementGrantState::new(config()).unwrap();
        let current = replacement.snapshot().unwrap();
        assert!(!replacement.owns_snapshot(&first));
        assert_eq!(
            replacement.revoke_for_snapshot(&first),
            Err(ManagementError::SnapshotMismatch)
        );
        assert!(replacement.owns_snapshot(&current));
        assert!(!replacement.is_revoked());
    }
}
