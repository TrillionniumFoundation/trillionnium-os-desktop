//! Disk-backed regression tests. No process creation, browser or effect execution.
use hepta_session_core::{
    JournalId, JournalOpenPolicy, ReceiptJournal, ReceiptLifecycleState as State,
};
use std::fs::{self, OpenOptions};
use std::io::Write;
#[path = "support/journal_chain_fixture.rs"]
mod fixture;
use fixture::*;

#[test]
fn isolated_rotated_open_must_not_reacquire_a_partial_receipt_namespace() {
    let root = Temp::new();
    let (_, second) = rotated(&root);
    let before = fs::read(&second).unwrap();
    assert!(
        ReceiptJournal::open(&second, JournalOpenPolicy::STRICT).is_err(),
        "rotated segment admitted without predecessor progress"
    );
    assert_eq!(fs::read(&second).unwrap(), before);
}
#[test]
fn rejected_isolated_recovery_must_not_truncate_a_torn_tail() {
    let root = Temp::new();
    let (_, second) = rotated(&root);
    OpenOptions::new()
        .append(true)
        .open(&second)
        .unwrap()
        .write_all(b"HPTREC01")
        .unwrap();
    let before = fs::read(&second).unwrap();
    let result = ReceiptJournal::open(&second, JournalOpenPolicy::RECOVER_CRASH);
    assert!(
        result.is_err(),
        "partial chain was admitted with repair authority"
    );
    assert_eq!(
        fs::read(&second).unwrap(),
        before,
        "rejected input was modified"
    );
}

#[test]
fn complete_reopen_restores_namespace_sequence_and_archived_clock() {
    let root = Temp::new();
    let (first, second) = rotated(&root);
    let mut writer =
        ReceiptJournal::open_chain([&first, &second], ID, JournalOpenPolicy::STRICT).unwrap();
    assert_eq!(writer.last_monotonic_ms(), 100);
    let before = fs::read(&second).unwrap();
    assert!(writer.append(event("prior-id", State::Requested)).is_err());
    assert_eq!(fs::read(&second).unwrap(), before);
    assert_eq!(
        writer
            .append(event("fresh-id", State::Requested))
            .unwrap()
            .sequence,
        3
    );
}

#[test]
fn active_tail_repair_requires_the_complete_valid_chain() {
    let root = Temp::new();
    let (first, second) = rotated(&root);
    OpenOptions::new()
        .append(true)
        .open(&second)
        .unwrap()
        .write_all(b"HPTREC01")
        .unwrap();
    let before_first = fs::read(&first).unwrap();
    let before_second = fs::read(&second).unwrap();
    assert!(ReceiptJournal::open_chain([&first, &second], ID, JournalOpenPolicy::STRICT).is_err());
    assert_eq!(fs::read(&second).unwrap(), before_second);
    let mut writer =
        ReceiptJournal::open_chain([&first, &second], ID, JournalOpenPolicy::RECOVER_CRASH)
            .unwrap();
    assert_eq!(fs::read(&first).unwrap(), before_first);
    assert_eq!(
        fs::read(&second).unwrap(),
        before_second[..before_second.len() - 8]
    );
    assert_eq!(
        writer.inspect().unwrap().tail,
        hepta_session_core::TailStatus::Clean
    );
    assert!(writer.append(event("prior-id", State::Requested)).is_err());
}

#[test]
fn identity_mismatch_is_rejected_before_tail_repair() {
    let root = Temp::new();
    let (first, second) = rotated(&root);
    OpenOptions::new()
        .append(true)
        .open(&second)
        .unwrap()
        .write_all(b"HPTREC01")
        .unwrap();
    let before = fs::read(&second).unwrap();
    assert!(
        ReceiptJournal::open_chain(
            [&first, &second],
            JournalId([9; 16]),
            JournalOpenPolicy::RECOVER_CRASH
        )
        .is_err()
    );
    assert_eq!(fs::read(&second).unwrap(), before);
}

#[test]
fn incomplete_reordered_and_duplicate_chains_are_rejected() {
    let root = Temp::new();
    let (first, second) = rotated(&root);
    for paths in [
        vec![&second],
        vec![&second, &first],
        vec![&first, &first],
        vec![],
    ] {
        assert!(ReceiptJournal::open_chain(paths, ID, JournalOpenPolicy::RECOVER_CRASH).is_err());
    }
}

#[test]
fn skipped_middle_segment_is_rejected_without_active_mutation() {
    let root = Temp::new();
    let (first, second) = rotated(&root);
    let mut writer =
        ReceiptJournal::open_chain([&first, &second], ID, JournalOpenPolicy::STRICT).unwrap();
    writer.append(event("middle-id", State::Requested)).unwrap();
    writer
        .append(event("middle-id", State::Interrupted))
        .unwrap();
    let third = root.path("segment-3.journal");
    let (_, writer) = writer.rotate(&third, 3).unwrap();
    drop(writer);
    let before = fs::read(&third).unwrap();
    assert!(
        ReceiptJournal::open_chain([&first, &third], ID, JournalOpenPolicy::RECOVER_CRASH).is_err()
    );
    assert_eq!(fs::read(&third).unwrap(), before);
    let mut writer =
        ReceiptJournal::open_chain([&first, &second, &third], ID, JournalOpenPolicy::STRICT)
            .unwrap();
    assert!(writer.append(event("middle-id", State::Requested)).is_err());
    assert!(writer.append(event("prior-id", State::Requested)).is_err());
    assert_eq!(
        writer
            .append(event("new-id", State::Requested))
            .unwrap()
            .sequence,
        5
    );
}

#[test]
fn corrupted_predecessor_is_not_repaired_and_does_not_modify_active_tail() {
    let root = Temp::new();
    let (first, second) = rotated(&root);
    let mut corrupt = fs::read(&first).unwrap();
    *corrupt.last_mut().unwrap() ^= 1;
    fs::write(&first, &corrupt).unwrap();
    OpenOptions::new()
        .append(true)
        .open(&second)
        .unwrap()
        .write_all(b"HPTREC01")
        .unwrap();
    let before = fs::read(&second).unwrap();
    assert!(
        ReceiptJournal::open_chain([&first, &second], ID, JournalOpenPolicy::RECOVER_CRASH)
            .is_err()
    );
    assert_eq!(fs::read(&first).unwrap(), corrupt);
    assert_eq!(fs::read(&second).unwrap(), before);
}

#[test]
fn torn_predecessor_is_never_repaired() {
    let root = Temp::new();
    let (first, second) = rotated(&root);
    OpenOptions::new()
        .append(true)
        .open(&first)
        .unwrap()
        .write_all(b"HPTREC01")
        .unwrap();
    let before = fs::read(&first).unwrap();
    assert!(
        ReceiptJournal::open_chain([&first, &second], ID, JournalOpenPolicy::RECOVER_CRASH)
            .is_err()
    );
    assert_eq!(fs::read(&first).unwrap(), before);
}

#[test]
fn predecessor_and_active_inode_locks_remain_held_until_drop() {
    let root = Temp::new();
    let (first, second) = rotated(&root);
    let writer =
        ReceiptJournal::open_chain([&first, &second], ID, JournalOpenPolicy::STRICT).unwrap();
    assert!(matches!(
        ReceiptJournal::open(&first, JournalOpenPolicy::RECOVER_CRASH),
        Err(hepta_session_core::JournalError::WriterBusy)
    ));
    assert!(matches!(
        ReceiptJournal::open_chain([&first, &second], ID, JournalOpenPolicy::RECOVER_CRASH),
        Err(hepta_session_core::JournalError::WriterBusy)
    ));
    drop(writer);
    assert!(ReceiptJournal::open_chain([&first, &second], ID, JournalOpenPolicy::STRICT).is_ok());
}

#[test]
fn live_rotation_also_retains_all_predecessor_locks() {
    let root = Temp::new();
    let (first, second) = rotated(&root);
    let mut writer =
        ReceiptJournal::open_chain([&first, &second], ID, JournalOpenPolicy::STRICT).unwrap();
    writer.append(event("second-id", State::Requested)).unwrap();
    writer
        .append(event("second-id", State::Interrupted))
        .unwrap();
    let third = root.path("segment-3.journal");
    let (_, writer) = writer.rotate(&third, 3).unwrap();
    for path in [&first, &second] {
        assert!(matches!(
            ReceiptJournal::open(path, JournalOpenPolicy::RECOVER_CRASH),
            Err(hepta_session_core::JournalError::WriterBusy)
        ));
    }
    drop(writer);
    assert!(
        ReceiptJournal::open_chain([&first, &second, &third], ID, JournalOpenPolicy::STRICT)
            .is_ok()
    );
}

#[test]
fn changed_predecessor_path_poisons_writer_before_append() {
    let root = Temp::new();
    let (first, second) = rotated(&root);
    let mut writer =
        ReceiptJournal::open_chain([&first, &second], ID, JournalOpenPolicy::STRICT).unwrap();
    fs::rename(&first, root.path("old-first")).unwrap();
    fs::copy(root.path("old-first"), &first).unwrap();
    let before = fs::read(&second).unwrap();
    assert!(writer.append(event("new-id", State::Requested)).is_err());
    assert!(matches!(
        writer.append(event("new-id", State::Requested)),
        Err(hepta_session_core::JournalError::WriterPoisoned)
    ));
    assert_eq!(fs::read(&second).unwrap(), before);
}

#[test]
fn aliases_and_symlinks_cannot_supply_a_chain() {
    use std::os::unix::fs::symlink;
    let root = Temp::new();
    let (first, second) = rotated(&root);
    let alias = root.path("alias");
    fs::hard_link(&first, &alias).unwrap();
    let link = root.path("link");
    symlink(&first, &link).unwrap();
    assert!(ReceiptJournal::open_chain([&first, &alias], ID, JournalOpenPolicy::STRICT).is_err());
    assert!(ReceiptJournal::open_chain([&link, &second], ID, JournalOpenPolicy::STRICT).is_err());
}

#[test]
fn unbounded_path_iterators_are_consumed_only_to_the_limit() {
    use std::cell::Cell;
    let count = Cell::new(0);
    let paths = std::iter::from_fn(|| {
        count.set(count.get() + 1);
        Some("/does-not-exist")
    });
    assert!(ReceiptJournal::open_chain(paths, ID, JournalOpenPolicy::STRICT).is_err());
    assert_eq!(
        count.get(),
        hepta_session_core::receipt_journal::MAX_CHAIN_SEGMENTS + 1
    );
}

#[test]
fn aggregate_sparse_file_budget_is_checked_before_decode_or_repair() {
    let root = Temp::new();
    let paths: Vec<_> = (0..3).map(|n| root.path(&format!("large-{n}"))).collect();
    for p in &paths {
        let writer = ReceiptJournal::create(p, ID, 1).unwrap();
        drop(writer);
        OpenOptions::new()
            .write(true)
            .open(p)
            .unwrap()
            .set_len(64 * 1024 * 1024)
            .unwrap();
    }
    assert!(ReceiptJournal::open_chain(&paths, ID, JournalOpenPolicy::RECOVER_CRASH).is_err());
    for p in paths {
        assert_eq!(fs::metadata(p).unwrap().len(), 64 * 1024 * 1024);
    }
}
