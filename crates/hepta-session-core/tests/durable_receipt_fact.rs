//! Independent complete-chain fact tests; no browser dispatch or effect replay.
use hepta_session_core::{
    CommittedRecord, JournalError, ManagedOpenPolicy, ReceiptJournal,
    ReceiptLifecycleState as State, ReceiptOutcome,
};
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::Path;

#[allow(dead_code)]
#[path = "support/journal_chain_fixture.rs"]
mod fixture;
use fixture::{ID, Temp, event};

fn create_store(parent: &Temp) -> ReceiptJournal {
    assert_eq!(
        fs::metadata(&parent.0).unwrap().permissions().mode() & 0o777,
        0o700
    );
    let root = parent.path("store");
    assert!(!root.exists(), "managed creation owns the fresh child root");
    ReceiptJournal::create_managed(root, ID, 1).expect("create managed store")
}

fn complete(writer: &mut ReceiptJournal, id: &str) -> CommittedRecord {
    writer.append(event(id, State::Requested)).unwrap();
    writer.append(event(id, State::Dispatched)).unwrap();
    let mut completed = event(id, State::Completed);
    completed.outcome = Some(ReceiptOutcome::Succeeded);
    completed.response_sha256 = Some([2; 32]);
    completed.error_code = None;
    writer.append(completed).expect("durable terminal record")
}

fn reopen(root: &Path) -> ReceiptJournal {
    ReceiptJournal::open_managed(root, ID, ManagedOpenPolicy::STRICT)
        .expect("reopen complete managed chain")
}

fn assert_terminal_fact(writer: &mut ReceiptJournal, record: &CommittedRecord) {
    let fact = writer
        .receipt_fact("prior-request", [1; 32])
        .expect("read terminal fact from the locked complete chain");
    assert_eq!(fact.receipt_id(), "prior-request");
    assert_eq!(fact.request_sha256(), [1; 32]);
    assert_eq!(fact.lifecycle(), State::Completed);
    assert_eq!(fact.record_sha256(), record.record_sha256);
    assert!(writer.contains_receipt("prior-request").unwrap());
    assert!(!writer.has_unresolved_receipts().unwrap());
}

#[test]
fn managed_terminal_fact_and_deduplication_survive_rotation_and_reopen() {
    let parent = Temp::new();
    let root = parent.path("store");
    let mut writer = create_store(&parent);
    let committed = complete(&mut writer, "prior-request");
    assert_terminal_fact(&mut writer, &committed);

    let (_, mut writer) = writer.rotate_managed(2).expect("quiescent rotation");
    assert!(writer.inspect().unwrap().records.is_empty());
    assert_terminal_fact(&mut writer, &committed);
    drop(writer);

    let mut writer = reopen(&root);
    assert!(writer.inspect().unwrap().records.is_empty());
    assert_terminal_fact(&mut writer, &committed);
    let before = fs::read(writer.path()).unwrap();
    assert!(matches!(
        writer.append(event("prior-request", State::Requested)),
        Err(JournalError::InvalidTransition {
            from: Some(State::Completed),
            to: State::Requested,
            ..
        })
    ));
    assert_eq!(fs::read(writer.path()).unwrap(), before);
}

#[test]
fn exact_request_digest_is_required_for_a_terminal_fact() {
    let parent = Temp::new();
    let mut writer = create_store(&parent);
    let committed = complete(&mut writer, "prior-request");
    let (_, mut writer) = writer.rotate_managed(2).unwrap();
    let before = fs::read(writer.path()).unwrap();
    let mut different_digest = [1; 32];
    different_digest[31] ^= 1;
    assert!(matches!(
        writer.receipt_fact("prior-request", different_digest),
        Err(JournalError::InvalidInput(_))
    ));
    assert_eq!(fs::read(writer.path()).unwrap(), before);
    assert_terminal_fact(&mut writer, &committed);
}

#[test]
fn unknown_identifier_does_not_mint_a_durable_fact() {
    let parent = Temp::new();
    let mut writer = create_store(&parent);
    complete(&mut writer, "prior-request");
    let before = fs::read(writer.path()).unwrap();
    assert!(!writer.contains_receipt("unknown-request").unwrap());
    assert!(matches!(
        writer.receipt_fact("unknown-request", [1; 32]),
        Err(JournalError::InvalidInput(_))
    ));
    assert_eq!(fs::read(writer.path()).unwrap(), before);
    assert!(!writer.has_unresolved_receipts().unwrap());
}

#[test]
fn requested_and_dispatched_facts_keep_the_startup_latch_after_reopen() {
    for last_state in [State::Requested, State::Dispatched] {
        let parent = Temp::new();
        let root = parent.path("store");
        let mut writer = create_store(&parent);
        complete(&mut writer, "prior-request");
        let (_, mut writer) = writer.rotate_managed(2).unwrap();
        let mut latest = writer
            .append(event("unresolved-request", State::Requested))
            .unwrap();
        if last_state == State::Dispatched {
            latest = writer
                .append(event("unresolved-request", State::Dispatched))
                .unwrap();
        }
        assert!(writer.has_unresolved_receipts().unwrap());
        drop(writer);

        let mut writer = reopen(&root);
        assert!(writer.contains_receipt("prior-request").unwrap());
        assert!(writer.contains_receipt("unresolved-request").unwrap());
        assert!(writer.has_unresolved_receipts().unwrap());
        let fact = writer
            .receipt_fact("unresolved-request", [1; 32])
            .expect("unresolved fact is evidence, never terminal authority");
        assert_eq!(fact.lifecycle(), last_state);
        assert!(!fact.lifecycle().is_terminal());
        assert_eq!(fact.record_sha256(), latest.record_sha256);

        writer
            .append(event("unresolved-request", State::Interrupted))
            .expect("explicit durable interruption");
        assert!(!writer.has_unresolved_receipts().unwrap());
    }
}

#[test]
fn fact_lookup_refuses_in_place_predecessor_corruption_after_rotation() {
    let parent = Temp::new();
    let root = parent.path("store");
    let mut writer = create_store(&parent);
    complete(&mut writer, "prior-request");
    let predecessor = writer.path().to_owned();
    let (_, mut writer) = writer.rotate_managed(2).unwrap();
    let active_before = fs::read(writer.path()).unwrap();
    let mut corrupt = fs::read(&predecessor).unwrap();
    *corrupt.last_mut().expect("predecessor record digest") ^= 1;
    fs::write(&predecessor, &corrupt).expect("same-inode, same-length corruption");

    assert!(writer.contains_receipt("prior-request").is_err());
    assert!(writer.has_unresolved_receipts().is_err());
    assert!(writer.execution_reconciliation_facts().is_err());
    assert!(
        writer.receipt_fact("prior-request", [1; 32]).is_err(),
        "cached progress must not mint a fact from changed predecessor bytes"
    );
    assert_eq!(fs::read(writer.path()).unwrap(), active_before);
    assert_eq!(fs::read(&predecessor).unwrap(), corrupt);
    drop(writer);
    assert!(
        ReceiptJournal::open_managed(&root, ID, ManagedOpenPolicy::RECOVER_CRASH).is_err(),
        "recovery must not repair a committed predecessor to mint a fact"
    );
    assert_eq!(fs::read(&predecessor).unwrap(), corrupt);
}

#[test]
fn terminal_uncertainty_remains_visible_across_rotation_and_reopen() {
    let parent = Temp::new();
    let root = parent.path("store");
    let mut writer = create_store(&parent);
    complete(&mut writer, "prior-request");
    for (id, dispatched, terminal) in [
        ("unknown-completion", true, State::Indeterminate),
        ("post-dispatch-interruption", true, State::Interrupted),
        ("pre-dispatch-interruption", false, State::Interrupted),
    ] {
        writer.append(event(id, State::Requested)).unwrap();
        if dispatched {
            writer.append(event(id, State::Dispatched)).unwrap();
        }
        writer.append(event(id, terminal)).unwrap();
    }
    let (_, writer) = writer.rotate_managed(200).unwrap();
    drop(writer);
    let mut writer = reopen(&root);
    assert!(
        !writer.has_unresolved_receipts().unwrap(),
        "structural terminal state is distinct from execution certainty"
    );
    let facts = writer.execution_reconciliation_facts().unwrap();
    assert_eq!(facts.len(), 2);
    assert_eq!(facts[0].receipt_id(), "post-dispatch-interruption");
    assert_eq!(facts[0].lifecycle(), State::Interrupted);
    assert_eq!(facts[1].receipt_id(), "unknown-completion");
    assert_eq!(facts[1].lifecycle(), State::Indeterminate);
    for fact in facts {
        let original = writer
            .receipt_fact(fact.receipt_id(), fact.request_sha256())
            .unwrap();
        assert_eq!(fact.record_sha256(), original.record_sha256());
    }
    assert!(
        writer.inspect().unwrap().records.is_empty(),
        "fact inspection writes no new authority"
    );
}
