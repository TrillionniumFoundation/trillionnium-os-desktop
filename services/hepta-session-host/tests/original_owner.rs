#![cfg(target_os = "linux")]

mod support;

use codex_hepta_memory::ObjectiveSenderObservationKind;
use hepta_os_observer::objective::SubmissionStatus;
use hepta_os_observer::objective::history::{HistoryStatus, PublicationOutcome};
use hepta_session_host::{HeptaSessionSubmission, HostError};
use std::sync::Arc;
use std::sync::atomic::Ordering;
use std::time::Duration;
use support::{ACCEPT, Fixture, HOLD, REFUSE};
use trill_session::objective_submission::{
    LocalSubmissionPhase, RequestOwnerIssue, SubmissionAdapterError,
};

fn persistence_unknown(result: Result<(), HostError>) {
    assert_eq!(
        result,
        Err(HostError::Submission(SubmissionAdapterError::Owner(
            RequestOwnerIssue::PersistenceUnknown
        )))
    );
}

fn publication(
    view: &trill_session::objective_submission::ObjectiveSubmissionView,
) -> (
    &hepta_os_observer::objective::history::HistoricalPublication,
    u64,
) {
    match view
        .first_observed_publication
        .as_ref()
        .expect("first original publication")
    {
        HistoryStatus::HistoricalPublication {
            publication,
            response_generation,
        } => (publication, *response_generation),
        _ => panic!("first observation must be an original publication"),
    }
}

fn admitted_submission(fixture: &Fixture) -> support::Submission {
    let mut submission = fixture.prepare().unwrap();
    let server = fixture.serve(Some(fixture.admitted()));
    submission.submit_once().unwrap();
    server.join().unwrap();
    submission
}

#[test]
fn exact_original_is_durable_before_connect_and_one_socket_send_is_never_rearmed() {
    let fixture = Fixture::new();
    let mut submission = fixture.prepare().unwrap();
    fixture.assert_no_connection();
    let retained = fixture.retained();
    assert_eq!(retained.len(), 1);
    assert_eq!(retained[0].exact_original(), fixture.original.as_bytes());
    assert!(
        fixture
            .snapshot(retained[0].clone())
            .observations
            .is_empty()
    );
    let server = fixture.serve(Some(fixture.admitted()));
    submission.submit_once().unwrap();
    let frame = server.join().unwrap();
    let expected = format!(
        "{{\"schema_version\":2,\"request_id\":19,\"spawn_generation\":1,\"method\":{{\"type\":\"objective_start\",\"request\":{}}}}}\n",
        fixture.original
    );
    assert_eq!(frame, expected.as_bytes());
    let view = submission.view();
    assert_eq!(view.phase, LocalSubmissionPhase::OriginalAttemptRetained);
    assert!(matches!(
        view.observed_submission,
        Some(SubmissionStatus::Admitted(_))
    ));
    assert!(view.submission_recorded);
    assert_eq!(fixture.snapshot(retained[0].clone()).observations.len(), 1);
    assert!(submission.submit_once().is_err());
    assert!(submission.cancel_before_send().is_err());
    assert!(matches!(
        fixture.prepare(),
        Err(HostError::Submission(SubmissionAdapterError::Owner(
            RequestOwnerIssue::AlreadyRetained
        )))
    ));
    fixture.assert_no_connection();
}

#[test]
fn lost_reply_recovers_exact_original_from_owner_enumeration_without_a_sender() {
    let fixture = Fixture::new();
    let mut submission = fixture.prepare().unwrap();
    let server = fixture.serve(None);
    submission.submit_once().unwrap();
    server.join().unwrap();
    assert!(matches!(
        submission.view().observed_submission,
        Some(SubmissionStatus::SubmitUnknown(_))
    ));
    drop(submission);
    let retained = fixture.retained().pop().unwrap();
    assert_eq!(retained.exact_original(), fixture.original.as_bytes());
    let mut recovered = fixture.recover(retained);
    assert!(matches!(
        recovered.view().observed_submission,
        Some(SubmissionStatus::SubmitUnknown(_))
    ));
    assert!(recovered.view().submission_recorded);
    assert!(recovered.submit_once().is_err());
    assert!(recovered.cancel_before_send().is_err());
    assert!(fixture.prepare().is_err());
    fixture.assert_no_connection();
}

#[test]
fn checkpoint_refusal_or_timeout_after_commit_never_rearms_a_fresh_prepare() {
    for mode in [REFUSE, HOLD] {
        let fixture = Fixture::new();
        fixture.checkpoint.mode.store(mode, Ordering::SeqCst);
        assert!(matches!(
            fixture.prepare(),
            Err(HostError::Submission(SubmissionAdapterError::Owner(
                RequestOwnerIssue::PersistenceUnknown
            )))
        ));
        assert_eq!(fixture.checkpoint.calls.load(Ordering::SeqCst), 1);
        assert!(fixture.writer.checkpoint_fenced());
        fixture.assert_no_connection();
        // The real original SQL commit exists even though the independent test
        // checkpoint refused or its future timed out. Recovery is observation-only.
        let retained = fixture.retained();
        assert_eq!(retained.len(), 1);
        assert_eq!(retained[0].exact_original(), fixture.original.as_bytes());
        fixture.checkpoint.mode.store(ACCEPT, Ordering::SeqCst);
        assert!(matches!(
            fixture.prepare(),
            Err(HostError::Submission(SubmissionAdapterError::Owner(
                RequestOwnerIssue::Refused
            )))
        ));
        let mut recovered = fixture.recover(retained[0].clone());
        // The original read/ACK can settle retained evidence, but it cannot
        // reopen the generation fenced by the failed checkpoint exchange.
        assert!(fixture.writer.checkpoint_fenced());
        assert!(matches!(
            fixture.prepare(),
            Err(HostError::Submission(SubmissionAdapterError::Owner(
                RequestOwnerIssue::Refused
            )))
        ));
        let retained_after_read_ack = fixture.retained();
        assert_eq!(retained_after_read_ack.len(), 1);
        assert_eq!(
            retained_after_read_ack[0].exact_original(),
            fixture.original.as_bytes()
        );
        assert!(recovered.submit_once().is_err());
        assert!(recovered.cancel_before_send().is_err());
        fixture.assert_no_connection();
    }
}

#[test]
fn live_revocation_after_prepare_consumes_permission_without_connect_or_local_cancel() {
    let fixture = Fixture::new();
    let mut submission = fixture.prepare().unwrap();
    fixture.verifier.revoked.store(true, Ordering::SeqCst);
    assert!(matches!(
        submission.submit_once(),
        Err(HostError::Submission(SubmissionAdapterError::Owner(
            RequestOwnerIssue::Refused
        )))
    ));
    fixture.assert_no_connection();
    fixture.verifier.revoked.store(false, Ordering::SeqCst);
    assert!(submission.submit_once().is_err());
    assert!(submission.cancel_before_send().is_err());
    assert!(fixture.prepare().is_err());
    let snapshot = fixture.snapshot(fixture.retained().pop().unwrap());
    assert!(snapshot.observations.is_empty());
    assert!(!snapshot.locally_cancelled);
    fixture.assert_no_connection();
}

#[test]
fn admission_receipt_ack_failure_requires_read_ack_without_unfencing_or_connecting() {
    for mode in [REFUSE, HOLD] {
        let fixture = Fixture::new();
        let mut submission = fixture.prepare().unwrap();
        let checkpoint = Arc::clone(&fixture.checkpoint);
        let server = fixture.serve_with(Some(fixture.admitted()), move || {
            checkpoint.mode.store(mode, Ordering::SeqCst);
        });
        persistence_unknown(submission.submit_once());
        server.join().unwrap();
        assert_eq!(fixture.checkpoint.calls.load(Ordering::SeqCst), 2);
        assert!(fixture.writer.checkpoint_fenced());
        let view = submission.view();
        assert!(matches!(
            view.observed_submission,
            Some(SubmissionStatus::Admitted(_))
        ));
        assert!(!view.submission_recorded);
        let request = fixture.retained().pop().unwrap();
        assert_eq!(fixture.snapshot(request.clone()).observations.len(), 1);
        assert!(submission.submit_once().is_err());
        fixture.checkpoint.mode.store(ACCEPT, Ordering::SeqCst);
        // An observation write retry is still a mutation. Even an exact retry
        // must not bypass the original owner's permanent checkpoint fence.
        assert_eq!(
            submission.retain_observed_submission(),
            Err(HostError::Submission(SubmissionAdapterError::Owner(
                RequestOwnerIssue::Refused
            )))
        );
        assert!(!submission.view().submission_recorded);
        let mut recovered = fixture.recover(request.clone());
        assert!(recovered.view().submission_recorded);
        assert_eq!(
            recovered.view().observed_submission,
            view.observed_submission
        );
        assert!(fixture.writer.checkpoint_fenced());
        assert_eq!(
            submission.retain_observed_submission(),
            Err(HostError::Submission(SubmissionAdapterError::Owner(
                RequestOwnerIssue::Refused
            )))
        );
        assert!(recovered.submit_once().is_err());
        assert!(recovered.cancel_before_send().is_err());
        assert_eq!(
            fixture.snapshot(request).observations.len(),
            1,
            "read acknowledgement preserves the one original receipt"
        );
        fixture.assert_no_connection();
    }
}

fn recovery_still_requires_ack(
    fixture: &Fixture,
    request: codex_hepta_memory::ObjectiveSenderRequest,
) {
    let result = HeptaSessionSubmission::recover_unknown(
        fixture.sender(),
        fixture.runtime.handle().clone(),
        request,
        Duration::from_secs(2),
    );
    assert!(matches!(
        result,
        Err(HostError::Submission(SubmissionAdapterError::Owner(
            RequestOwnerIssue::PersistenceUnknown
        )))
    ));
    fixture.assert_no_connection();
}

#[test]
fn recovered_submission_cannot_promote_a_committed_but_unacknowledged_receipt() {
    for mode in [REFUSE, HOLD] {
        let fixture = Fixture::new();
        let mut submission = fixture.prepare().unwrap();
        let checkpoint = Arc::clone(&fixture.checkpoint);
        let server = fixture.serve_with(Some(fixture.admitted()), move || {
            checkpoint.mode.store(mode, Ordering::SeqCst);
        });
        persistence_unknown(submission.submit_once());
        server.join().unwrap();
        assert!(!submission.view().submission_recorded);
        let request = fixture.retained().pop().unwrap();
        assert_eq!(fixture.snapshot(request.clone()).observations.len(), 1);
        drop(submission);
        recovery_still_requires_ack(&fixture, request.clone());
        assert_eq!(fixture.snapshot(request.clone()).observations.len(), 1);
        fixture.checkpoint.mode.store(ACCEPT, Ordering::SeqCst);
        let mut recovered = fixture.recover(request.clone());
        assert!(recovered.view().submission_recorded);
        assert!(matches!(
            recovered.view().observed_submission,
            Some(SubmissionStatus::Admitted(_))
        ));
        assert_eq!(fixture.snapshot(request).observations.len(), 1);
        assert!(recovered.submit_once().is_err());
        assert!(recovered.cancel_before_send().is_err());
        fixture.assert_no_connection();
    }
}

#[test]
fn recovered_history_cannot_promote_a_committed_but_unacknowledged_publication() {
    for mode in [REFUSE, HOLD] {
        let fixture = Fixture::new();
        let mut submission = admitted_submission(&fixture);
        let first = fixture.publication();
        let checkpoint = Arc::clone(&fixture.checkpoint);
        let server = fixture.serve_with(
            Some(fixture.history_reply(Some(first.clone()), 3)),
            move || {
                checkpoint.mode.store(mode, Ordering::SeqCst);
            },
        );
        persistence_unknown(submission.reconcile_once(fixture.history_origin()));
        server.join().unwrap();
        assert!(!submission.view().history_recorded);
        let request = fixture.retained().pop().unwrap();
        assert_eq!(fixture.snapshot(request.clone()).observations.len(), 2);
        drop(submission);
        recovery_still_requires_ack(&fixture, request.clone());
        assert_eq!(fixture.snapshot(request.clone()).observations.len(), 2);
        fixture.checkpoint.mode.store(ACCEPT, Ordering::SeqCst);
        let mut recovered = fixture.recover(request.clone());
        assert!(recovered.view().history_recorded && recovered.view().submission_recorded);
        assert_eq!(publication(&recovered.view()), (&first, 3));
        assert_eq!(fixture.snapshot(request).observations.len(), 2);
        assert!(recovered.submit_once().is_err());
        assert!(recovered.cancel_before_send().is_err());
        fixture.assert_no_connection();
    }
}

#[test]
fn recovered_local_cancellation_requires_ack_without_regranting_cancel_permission() {
    for mode in [REFUSE, HOLD] {
        let fixture = Fixture::new();
        let mut submission = fixture.prepare().unwrap();
        fixture.checkpoint.mode.store(mode, Ordering::SeqCst);
        persistence_unknown(submission.cancel_before_send());
        assert!(!submission.view().local_cancellation_recorded);
        let request = fixture.retained().pop().unwrap();
        assert!(fixture.snapshot(request.clone()).locally_cancelled);
        drop(submission);
        recovery_still_requires_ack(&fixture, request.clone());
        assert!(fixture.snapshot(request.clone()).locally_cancelled);
        fixture.checkpoint.mode.store(ACCEPT, Ordering::SeqCst);
        let mut recovered = fixture.recover(request.clone());
        assert!(recovered.view().local_cancellation_recorded);
        let snapshot = fixture.snapshot(request);
        assert!(snapshot.locally_cancelled && snapshot.observations.is_empty());
        assert!(recovered.submit_once().is_err());
        assert!(recovered.cancel_before_send().is_err());
        fixture.assert_no_connection();
    }
}

#[test]
fn admitted_publication_then_unknown_survive_recovery_with_the_original_first_response_generation()
{
    let fixture = Fixture::new();
    let mut submission = admitted_submission(&fixture);
    let first = fixture.publication();
    let server = fixture.serve(Some(fixture.history_reply(Some(first.clone()), 3)));
    submission.reconcile_once(fixture.history_origin()).unwrap();
    server.join().unwrap();
    assert_eq!(publication(&submission.view()), (&first, 3));
    let server = fixture.serve(Some(fixture.history_reply(None, 4)));
    submission.reconcile_once(fixture.history_origin()).unwrap();
    let frame = server.join().unwrap();
    let query: serde_json::Value = serde_json::from_slice(&frame).unwrap();
    assert_eq!(query["method"]["query"]["anchor"]["sequence"], 1);
    assert_eq!(
        query["method"]["query"]["anchor"]["chain_digest"],
        first.chain_digest
    );
    assert!(matches!(
        submission.view().last_history,
        Some(HistoryStatus::Unknown(_))
    ));
    assert_eq!(publication(&submission.view()), (&first, 3));
    drop(submission);
    let mut recovered = fixture.recover(fixture.retained().pop().unwrap());
    let view = recovered.view();
    assert!(matches!(
        view.observed_submission,
        Some(SubmissionStatus::Admitted(_))
    ));
    assert!(matches!(view.last_history, Some(HistoryStatus::Unknown(_))));
    assert!(view.history_recorded && view.submission_recorded);
    assert_eq!(publication(&view), (&first, 3));
    let server = fixture.serve(Some(fixture.history_reply(Some(first.clone()), 4)));
    recovered.reconcile_once(fixture.history_origin()).unwrap();
    server.join().unwrap();
    assert_eq!(
        publication(&recovered.view()),
        (&first, 3),
        "later reply must not replace the original first acknowledgement"
    );
    assert!(recovered.submit_once().is_err());
    fixture.assert_no_connection();
}

#[test]
fn wrong_canonical_body_digest_is_neither_displayed_nor_appended_as_a_publication() {
    let fixture = Fixture::new();
    let mut submission = admitted_submission(&fixture);
    let mut bad = fixture.publication();
    bad.signed_body_digest = "7".repeat(64);
    let server = fixture.serve(Some(fixture.history_reply(Some(bad), 3)));
    assert!(matches!(
        submission.reconcile_once(fixture.history_origin()),
        Err(HostError::Submission(SubmissionAdapterError::Owner(
            RequestOwnerIssue::IdentityMismatch
        )))
    ));
    server.join().unwrap();
    let view = submission.view();
    assert!(matches!(view.last_history, Some(HistoryStatus::Unknown(_))));
    assert!(view.first_observed_publication.is_none());
    assert!(!view.history_recorded);
    assert!(submission.retain_observed_history().is_err());
    let snapshot = fixture.snapshot(fixture.retained().pop().unwrap());
    assert_eq!(snapshot.observations.len(), 1);
    assert_eq!(
        snapshot.observations[0].kind(),
        ObjectiveSenderObservationKind::Submission
    );
    fixture.assert_no_connection();
}

#[test]
fn contradictory_publication_keeps_first_and_does_not_poison_the_original_chain() {
    let fixture = Fixture::new();
    let mut submission = admitted_submission(&fixture);
    let first = fixture.publication();
    let server = fixture.serve(Some(fixture.history_reply(Some(first.clone()), 3)));
    submission.reconcile_once(fixture.history_origin()).unwrap();
    server.join().unwrap();
    let mut different = first.clone();
    // Same anchor and canonical signed body: the original wire's shape/anchor
    // checks can pass. The retained original publication must still agree.
    different.profile_digest = "8".repeat(64);
    different.outcome = PublicationOutcome::ExplicitAbstain {
        objective_digest: "1".repeat(64),
        hard_constraint_digest: "2".repeat(64),
    };
    let server = fixture.serve(Some(fixture.history_reply(Some(different), 4)));
    assert!(matches!(
        submission.reconcile_once(fixture.history_origin()),
        Err(HostError::Submission(SubmissionAdapterError::Owner(
            RequestOwnerIssue::IdentityMismatch
        )))
    ));
    server.join().unwrap();
    let view = submission.view();
    assert!(matches!(view.last_history, Some(HistoryStatus::Unknown(_))));
    assert_eq!(publication(&view), (&first, 3));
    assert!(!view.history_recorded);
    let request = fixture.retained().pop().unwrap();
    assert_eq!(fixture.snapshot(request.clone()).observations.len(), 2);
    assert_eq!(publication(&fixture.recover(request).view()), (&first, 3));
    fixture.assert_no_connection();
}

#[test]
fn concurrent_recovery_cannot_display_a_publication_rejected_against_another_handles_retained_first()
 {
    let fixture = Fixture::new();
    let submission = admitted_submission(&fixture);
    drop(submission);
    let request = fixture.retained().pop().unwrap();
    let mut first_handle = fixture.recover(request.clone());
    let mut second_handle = fixture.recover(request.clone());
    assert!(second_handle.view().first_observed_publication.is_none());
    let first = fixture.publication();
    let server = fixture.serve(Some(fixture.history_reply(Some(first.clone()), 3)));
    first_handle
        .reconcile_once(fixture.history_origin())
        .unwrap();
    server.join().unwrap();
    let mut different = first.clone();
    different.profile_digest = "9".repeat(64);
    let server = fixture.serve(Some(fixture.history_reply(Some(different.clone()), 4)));
    assert!(matches!(
        second_handle.reconcile_once(fixture.history_origin()),
        Err(HostError::Submission(SubmissionAdapterError::Owner(
            RequestOwnerIssue::IdentityMismatch
        )))
    ));
    let frame = server.join().unwrap();
    let query: serde_json::Value = serde_json::from_slice(&frame).unwrap();
    assert_eq!(
        query["method"]["query"]["anchor"]["chain_digest"],
        first.chain_digest
    );
    let view = second_handle.view();
    assert!(matches!(view.last_history, Some(HistoryStatus::Unknown(_))));
    assert!(!view.history_recorded);
    if view.first_observed_publication.is_some() {
        assert_eq!(publication(&view), (&first, 3));
    }
    assert_eq!(fixture.snapshot(request.clone()).observations.len(), 2);
    assert_eq!(publication(&fixture.recover(request).view()), (&first, 3));
    fixture.assert_no_connection();
}

#[test]
fn durable_local_cancellation_recovers_without_send_or_cancellation_rights() {
    let fixture = Fixture::new();
    let mut submission = fixture.prepare().unwrap();
    submission.cancel_before_send().unwrap();
    assert!(submission.view().local_cancellation_recorded);
    let request = fixture.retained().pop().unwrap();
    let snapshot = fixture.snapshot(request.clone());
    assert!(snapshot.locally_cancelled);
    assert!(snapshot.observations.is_empty());
    drop(submission);
    let mut recovered = fixture.recover(request);
    assert!(recovered.view().local_cancellation_recorded);
    assert!(recovered.submit_once().is_err());
    assert!(recovered.cancel_before_send().is_err());
    assert!(fixture.prepare().is_err());
    fixture.assert_no_connection();
}

#[test]
fn tokio_context_is_rejected_before_retention_or_any_socket_operation() {
    let fixture = Fixture::new();
    fixture.runtime.block_on(async {
        assert!(matches!(fixture.prepare(), Err(HostError::InvalidWorker)));
    });
    assert!(fixture.retained().is_empty());
    fixture.assert_no_connection();
    let mut submission = fixture.prepare().unwrap();
    let request = fixture.retained().pop().unwrap();
    fixture.runtime.block_on(async {
        assert_eq!(submission.submit_once(), Err(HostError::InvalidWorker));
        assert_eq!(
            submission.cancel_before_send(),
            Err(HostError::InvalidWorker)
        );
        assert_eq!(
            submission.retain_observed_submission(),
            Err(HostError::InvalidWorker)
        );
        assert_eq!(
            submission.retain_local_cancellation(),
            Err(HostError::InvalidWorker)
        );
        assert_eq!(
            submission.reconcile_once(fixture.history_origin()),
            Err(HostError::InvalidWorker)
        );
        assert_eq!(
            submission.retain_observed_history(),
            Err(HostError::InvalidWorker)
        );
        assert!(matches!(
            HeptaSessionSubmission::recover_unknown(
                fixture.sender(),
                fixture.runtime.handle().clone(),
                request.clone(),
                Duration::from_secs(2)
            ),
            Err(HostError::InvalidWorker)
        ));
    });
    assert!(fixture.snapshot(request).observations.is_empty());
    assert_eq!(fixture.checkpoint.calls.load(Ordering::SeqCst), 1);
    fixture.assert_no_connection();
}
