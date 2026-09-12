use trillionnium_contract_core::{
    DnsLabel, LeaseId, RequestId, RevisionClock, RevisionError, SessionId, Sha256Hex, UnixMillis,
};

fn assert_unchanged_after_navigation_error(mut clock: RevisionClock, expected: RevisionError) {
    let before = clock;
    assert_eq!(clock.on_navigation_commit(), Err(expected));
    assert_eq!(clock, before);
}

fn assert_unchanged_after_recovery_error(mut clock: RevisionClock, expected: RevisionError) {
    let before = clock;
    assert_eq!(clock.on_process_recovery(), Err(expected));
    assert_eq!(clock, before);
}

#[test]
fn registry_backed_identifier_alphabet_and_byte_bounds_are_executable() {
    let allowed = "AZaz09._:-";
    assert!(RequestId::parse("request_id", allowed).is_ok());
    assert!(SessionId::parse("session_id", allowed).is_ok());
    assert!(LeaseId::parse("lease_id", allowed).is_ok());

    let maximum = "a".repeat(128);
    assert!(RequestId::parse("request_id", maximum.clone()).is_ok());
    assert!(RequestId::parse("request_id", format!("{maximum}a")).is_err());

    for forbidden in ["/", "\\", " ", "\n", "\0", "é"] {
        assert!(
            RequestId::parse("request_id", format!("safe{forbidden}value")).is_err(),
            "forbidden identifier fragment was accepted: {forbidden:?}"
        );
    }
}

#[test]
fn registry_backed_digest_dns_and_time_domains_are_executable() {
    assert!(Sha256Hex::parse("0123456789abcdef".repeat(4)).is_ok());
    assert!(Sha256Hex::parse("0123456789ABCDEF".repeat(4)).is_err());
    assert!(Sha256Hex::parse("a".repeat(63)).is_err());
    assert!(Sha256Hex::parse("a".repeat(65)).is_err());

    assert!(DnsLabel::parse("a".repeat(63)).is_ok());
    for invalid in [
        String::new(),
        "a".repeat(64),
        "-leading".to_owned(),
        "trailing-".to_owned(),
        "Upper".to_owned(),
        "with.dot".to_owned(),
        "ümlaut".to_owned(),
    ] {
        assert!(
            DnsLabel::parse(invalid.clone()).is_err(),
            "invalid DNS label was accepted: {invalid:?}"
        );
    }

    let minimum: i64 = UnixMillis::new(i64::MIN).get();
    let maximum: i64 = UnixMillis::new(i64::MAX).get();
    assert_eq!(minimum, i64::MIN);
    assert_eq!(maximum, i64::MAX);
}

#[test]
fn revision_clock_initial_values_match_the_closed_registry() {
    assert_eq!(
        RevisionClock::new(),
        RevisionClock {
            session_generation: 1,
            document_generation: 1,
            semantic_snapshot_revision: 0,
            mutation_epoch: 0,
        }
    );
}

#[test]
fn every_navigation_counter_overflow_is_typed_and_atomic() {
    assert_unchanged_after_navigation_error(
        RevisionClock {
            document_generation: u64::MAX,
            semantic_snapshot_revision: 7,
            mutation_epoch: 11,
            ..RevisionClock::new()
        },
        RevisionError::DocumentGenerationExhausted,
    );
    assert_unchanged_after_navigation_error(
        RevisionClock {
            document_generation: 7,
            semantic_snapshot_revision: u64::MAX,
            mutation_epoch: 11,
            ..RevisionClock::new()
        },
        RevisionError::SemanticSnapshotRevisionExhausted,
    );
    assert_unchanged_after_navigation_error(
        RevisionClock {
            document_generation: 7,
            semantic_snapshot_revision: 11,
            mutation_epoch: u64::MAX,
            ..RevisionClock::new()
        },
        RevisionError::MutationEpochExhausted,
    );
}

#[test]
fn every_recovery_counter_overflow_is_typed_and_atomic() {
    assert_unchanged_after_recovery_error(
        RevisionClock {
            session_generation: u64::MAX,
            document_generation: 7,
            semantic_snapshot_revision: 11,
            mutation_epoch: 13,
        },
        RevisionError::SessionGenerationExhausted,
    );
    assert_unchanged_after_recovery_error(
        RevisionClock {
            session_generation: 5,
            document_generation: u64::MAX,
            semantic_snapshot_revision: 11,
            mutation_epoch: 13,
        },
        RevisionError::DocumentGenerationExhausted,
    );
    assert_unchanged_after_recovery_error(
        RevisionClock {
            session_generation: 5,
            document_generation: 7,
            semantic_snapshot_revision: u64::MAX,
            mutation_epoch: 13,
        },
        RevisionError::SemanticSnapshotRevisionExhausted,
    );
    assert_unchanged_after_recovery_error(
        RevisionClock {
            session_generation: 5,
            document_generation: 7,
            semantic_snapshot_revision: 11,
            mutation_epoch: u64::MAX,
        },
        RevisionError::MutationEpochExhausted,
    );
}

#[test]
fn single_counter_overflow_is_typed_and_non_mutating() {
    let mut dom = RevisionClock {
        mutation_epoch: u64::MAX,
        ..RevisionClock::new()
    };
    let dom_before = dom;
    assert_eq!(
        dom.on_dom_commit(),
        Err(RevisionError::MutationEpochExhausted)
    );
    assert_eq!(dom, dom_before);

    let mut snapshot = RevisionClock {
        semantic_snapshot_revision: u64::MAX,
        ..RevisionClock::new()
    };
    let snapshot_before = snapshot;
    assert_eq!(
        snapshot.on_semantic_snapshot(),
        Err(RevisionError::SemanticSnapshotRevisionExhausted)
    );
    assert_eq!(snapshot, snapshot_before);
}
