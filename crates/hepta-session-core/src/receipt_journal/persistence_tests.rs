//! Unit-test-only persistence cutpoints. No public API, feature or production
//! environment input enables them. All operations use real private host files.
//! Process kills observe page-cache state; they are NOT physical power loss.
use super::*;
use std::cell::RefCell;
use std::collections::BTreeMap;
use std::os::unix::fs::DirBuilderExt;
use std::sync::atomic::{AtomicU64, Ordering};

pub(crate) const ID: JournalId = JournalId([0x67; 16]);
const FIRST: &str = "segment-0000000000000001.journal";
const SECOND: &str = "segment-0000000000000002.journal";
static UNIQUE: AtomicU64 = AtomicU64::new(1);

pub(crate) enum Action {
    Error(i32),
    #[allow(dead_code)] // Used by the independent harness=false process target.
    Pause(PathBuf),
}
struct Injection {
    target: String,
    action: Action,
    trace: Vec<String>,
    reached: bool,
}
thread_local! {
    static INJECTION: RefCell<Option<Injection>> = const { RefCell::new(None) };
}
pub(crate) struct Armed;
impl Armed {
    pub(crate) fn new(target: &str, action: Action) -> Self {
        INJECTION.with(|slot| {
            let mut slot = slot.borrow_mut();
            assert!(slot.is_none(), "no nested persistence injector");
            *slot = Some(Injection {
                target: target.into(),
                action,
                trace: Vec::new(),
                reached: false,
            });
        });
        Self
    }
    pub(super) fn reached(&self) -> bool {
        INJECTION.with(|slot| slot.borrow().as_ref().unwrap().reached)
    }
    fn trace(&self) -> Vec<String> {
        INJECTION.with(|slot| slot.borrow().as_ref().unwrap().trace.clone())
    }
}
impl Drop for Armed {
    fn drop(&mut self) {
        INJECTION.with(|slot| *slot.borrow_mut() = None);
    }
}

pub(super) fn point(name: &str) -> Result<(), JournalError> {
    let action = INJECTION.with(|slot| {
        let mut slot = slot.borrow_mut();
        let injection = slot.as_mut()?;
        injection.trace.push(name.into());
        if injection.target != name {
            return None;
        }
        assert!(!injection.reached, "a persistence cutpoint must fire once");
        injection.reached = true;
        Some(match &injection.action {
            Action::Error(code) => Action::Error(*code),
            Action::Pause(path) => Action::Pause(path.clone()),
        })
    });
    match action {
        None => Ok(()),
        Some(Action::Error(code)) => Err(map_io_error(io::Error::from_raw_os_error(code))),
        Some(Action::Pause(checkpoint)) => {
            // The checkpoint is outside the tested store. Only this isolated
            // child reads test environment; production code has no such switch.
            let mut signal = File::create(checkpoint).unwrap();
            signal.write_all(name.as_bytes()).unwrap();
            signal.sync_all().unwrap();
            loop {
                std::thread::park();
            }
        }
    }
}
pub(super) fn before_write<W: Write>(
    prefix: &str,
    writer: &mut W,
    bytes: &[u8],
) -> Result<(), JournalError> {
    point(&format!("{prefix}.before_write"))?;
    let partial = format!("{prefix}.partial_write");
    let armed = INJECTION.with(|slot| {
        slot.borrow()
            .as_ref()
            .is_some_and(|item| item.target == partial)
    });
    if armed {
        assert!(bytes.len() > 1);
        // A real prefix write, not a synthetic file state or a successful short
        // write reported as complete. The following cut never returns success.
        writer
            .write_all(&bytes[..bytes.len() / 2])
            .map_err(map_io_error)?;
        point(&partial)?;
        panic!("partial write fault must not return success");
    }
    Ok(())
}

pub(crate) struct Temp(pub(crate) PathBuf);
impl Temp {
    pub(crate) fn new() -> Self {
        let root = std::env::temp_dir().join(format!(
            "hepta-persistence-cuts-{}-{}",
            std::process::id(),
            UNIQUE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
        Self(root)
    }
    pub(crate) fn store(&self) -> PathBuf {
        self.0.join("store")
    }
}
impl Drop for Temp {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
pub(crate) fn event(id: &str, lifecycle: LifecycleState) -> ReceiptEvent {
    ReceiptEvent {
        receipt_id: id.into(),
        plan_revision: "2026-08-29-d6".into(),
        image_id: "persistence-cut-fixture".into(),
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
        effect_class: EffectClass::Observation,
        privacy_class: PrivacyClass::Internal,
        request_sha256: [1; 32],
        response_sha256: None,
        error_code: lifecycle.is_terminal().then(|| "internal".into()),
        detail: None,
        monotonic_ms: 100,
        wall_clock_unix_ms: 200,
    }
}
pub(crate) fn prepared(root: &Path) -> ReceiptJournal {
    let mut journal = ReceiptJournal::create_managed(root, ID, 1).unwrap();
    journal
        .append(event("prior", LifecycleState::Requested))
        .unwrap();
    journal
        .append(event("prior", LifecycleState::Interrupted))
        .unwrap();
    journal
}
fn snapshot(root: &Path) -> BTreeMap<String, Vec<u8>> {
    if !root.exists() {
        return BTreeMap::new();
    }
    fs::read_dir(root)
        .unwrap()
        .map(|entry| {
            let entry = entry.unwrap();
            (
                entry.file_name().into_string().unwrap(),
                fs::read(entry.path()).unwrap(),
            )
        })
        .collect()
}

#[test]
fn managed_reopen_requires_a_durability_barrier() {
    let temp = Temp::new();
    drop(prepared(&temp.store()));
    // A clean filename on restart does not prove a previous writer completed
    // its file and directory sync. The new writer must not be returned if the
    // new barrier fails, even when inspection sees valid complete bytes.
    let armed = Armed::new("reopen.before_directory_sync", Action::Error(5));
    let result = ReceiptJournal::open_managed(temp.store(), ID, ManagedOpenPolicy::STRICT);
    assert!(
        armed.reached(),
        "reopen omitted directory durability barrier: {:?}",
        armed.trace()
    );
    assert!(
        result.is_err(),
        "failed durability barrier must not return a writer"
    );
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum DiskState {
    Prior,
    Blocked,
    Prepared,
    Published,
}
use DiskState::*;
// Independent expected disk states; do not infer the expectation from whatever
// the implementation happens to leave behind. Every cut must be reached.
pub(crate) const ROTATION_CUTS: &[(&str, DiskState)] = &[
    ("seal.before_sync", Prior),
    ("seal.after_sync", Prior),
    ("segment.before_create", Prior),
    ("segment.after_create", Blocked),
    ("commit.before_write", Blocked),
    ("commit.partial_write", Blocked),
    ("commit.after_write", Prepared),
    ("commit.before_sync", Prepared),
    ("commit.after_sync", Prepared),
    ("segment.before_parent_sync", Prepared),
    ("segment.after_parent_sync", Prepared),
    ("publish.before_file_sync", Prepared),
    ("publish.after_file_sync", Prepared),
    ("publish.before_rename", Prepared),
    ("publish.after_rename", Published),
    ("publish.before_directory_sync", Published),
    ("publish.after_directory_sync", Published),
];
pub(crate) const INITIALIZATION_CUTS: &[(&str, DiskState)] = &[
    ("initialize.before_directory_create", Blocked),
    ("initialize.after_directory_create", Blocked),
    ("initialize.before_parent_sync", Blocked),
    ("initialize.after_parent_sync", Blocked),
    ("initialize.before_marker_create", Blocked),
    ("initialize.after_marker_create", Blocked),
    ("marker.before_write", Blocked),
    ("marker.partial_write", Blocked),
    ("marker.after_write", Blocked),
    ("initialize.before_marker_sync", Blocked),
    ("initialize.after_marker_sync", Blocked),
    ("initialize.before_directory_sync", Blocked),
    ("initialize.after_directory_sync", Blocked),
    ("segment.before_create", Blocked),
    ("segment.after_create", Blocked),
    ("commit.before_write", Blocked),
    ("commit.partial_write", Blocked),
    ("commit.after_write", Prepared),
    ("commit.before_sync", Prepared),
    ("commit.after_sync", Prepared),
    ("segment.before_parent_sync", Prepared),
    ("segment.after_parent_sync", Prepared),
    ("publish.before_file_sync", Prepared),
    ("publish.after_file_sync", Prepared),
    ("publish.before_rename", Prepared),
    ("publish.after_rename", Published),
    ("publish.before_directory_sync", Published),
    ("publish.after_directory_sync", Published),
];
pub(crate) const REOPEN_CUTS: &[&str] = &[
    "reopen.before_active_sync",
    "reopen.after_active_sync",
    "reopen.before_directory_sync",
    "reopen.after_directory_sync",
];
pub(crate) const APPEND_CUTS: &[&str] = &[
    "commit.before_write",
    "commit.partial_write",
    "commit.after_write",
    "commit.before_sync",
    "commit.after_sync",
];
pub(crate) const REPAIR_CUTS: &[&str] = &[
    "repair.before_truncate",
    "repair.after_truncate",
    "repair.before_sync",
    "repair.after_sync",
];
fn assert_error(result: Result<impl Sized, JournalError>, code: i32, target: &str) {
    let error = result
        .err()
        .unwrap_or_else(|| panic!("fault at {target} returned success"));
    // Compare the same public error mapping, without accepting an unrelated
    // precondition failure as evidence of an exercised I/O failure boundary.
    assert_eq!(
        error.to_string(),
        map_io_error(io::Error::from_raw_os_error(code)).to_string(),
        "{target}"
    );
}
pub(crate) fn assert_publication(root: &Path, state: DiskState, has_prior: bool) {
    let before = snapshot(root);
    let existed = root.exists();
    let prior = before.get(FIRST).cloned();
    if state == Blocked {
        for policy in [ManagedOpenPolicy::STRICT, ManagedOpenPolicy::RECOVER_CRASH] {
            assert!(ReceiptJournal::open_managed(root, ID, policy).is_err());
            assert_eq!(snapshot(root), before, "failed open changed bytes");
            assert_eq!(
                root.exists(),
                existed,
                "failed open created/reset directory"
            );
        }
        return;
    }
    if state == Prepared {
        assert!(before.contains_key("next.pending"));
        assert!(ReceiptJournal::open_managed(root, ID, ManagedOpenPolicy::STRICT).is_err());
        assert_eq!(snapshot(root), before, "strict open published or repaired");
    } else {
        assert!(!before.contains_key("next.pending"));
    }
    let mut writer =
        ReceiptJournal::open_managed(root, ID, ManagedOpenPolicy::RECOVER_CRASH).unwrap();
    let expected = if has_prior && state != Prior {
        SECOND
    } else {
        FIRST
    };
    assert_eq!(writer.path(), root.join(expected));
    assert!(!root.join("next.pending").exists());
    if has_prior {
        assert_eq!(
            fs::read(root.join(FIRST)).unwrap(),
            prior.unwrap(),
            "prior segment changed"
        );
        assert!(
            writer
                .append(event("prior", LifecycleState::Requested))
                .is_err()
        );
    }
    let sequence = if has_prior { 3 } else { 1 };
    assert_eq!(
        writer
            .append(event("new", LifecycleState::Requested))
            .unwrap()
            .sequence,
        sequence
    );
    writer
        .append(event("new", LifecycleState::Interrupted))
        .unwrap();
    drop(writer);
    let mut writer = ReceiptJournal::open_managed(root, ID, ManagedOpenPolicy::STRICT).unwrap();
    assert!(
        writer
            .append(event("new", LifecycleState::Requested))
            .is_err()
    );
    if has_prior {
        assert!(
            writer
                .append(event("prior", LifecycleState::Requested))
                .is_err()
        );
    }
    assert_eq!(
        writer
            .append(event("next", LifecycleState::Requested))
            .unwrap()
            .sequence,
        sequence + 2
    );
}
pub(crate) fn recovered_pending(root: &Path) {
    let writer = prepared(root);
    let armed = Armed::new("publish.before_rename", Action::Error(5));
    assert_error(writer.rotate_managed(2), 5, "publish.before_rename");
    assert!(armed.reached());
    drop(armed);
}
pub(crate) fn with_torn_tail(root: &Path) {
    let mut writer = prepared(root);
    let armed = Armed::new("commit.partial_write", Action::Error(28));
    assert!(
        writer
            .append(event("partial", LifecycleState::Requested))
            .is_err()
    );
    assert!(armed.reached());
    drop(armed);
    drop(writer);
}
pub(crate) fn prepared_unresolved(root: &Path) {
    let writer = prepared(root);
    let (_, mut writer) = writer.rotate_managed(2).unwrap();
    for state in [LifecycleState::Requested, LifecycleState::Dispatched] {
        let mut value = event("uncertain", state);
        value.effect_class = EffectClass::PotentialExternalEffect;
        writer.append(value).unwrap();
    }
}
pub(crate) fn assert_unresolved_preserved(root: &Path) {
    let before = snapshot(root);
    let mut writer = ReceiptJournal::open_managed(root, ID, ManagedOpenPolicy::STRICT).unwrap();
    let report = writer.inspect().unwrap();
    assert_eq!(writer.path(), root.join(SECOND));
    assert_eq!(report.unresolved.len(), 1);
    assert_eq!(report.unresolved[0].receipt_id, "uncertain");
    assert_eq!(report.unresolved[0].replay, ReplayDirective::NeverAutomatic);
    assert!(
        report
            .records
            .iter()
            .all(|r| r.event.outcome.is_none() && r.event.response_sha256.is_none())
    );
    assert!(
        writer
            .append(event("prior", LifecycleState::Requested))
            .is_err()
    );
    assert!(
        writer
            .append(event("uncertain", LifecycleState::Requested))
            .is_err()
    );
    assert_eq!(
        snapshot(root),
        before,
        "open invented receipt or changed facts"
    );
}

#[test]
fn managed_rotation_io_failures_preserve_state_at_every_cut() {
    for code in [5, 28] {
        for &(target, state) in ROTATION_CUTS {
            let temp = Temp::new();
            let root = temp.store();
            let writer = prepared(&root);
            let armed = Armed::new(target, Action::Error(code));
            let result = writer.rotate_managed(2);
            assert!(armed.reached(), "missing cut {target}: {:?}", armed.trace());
            assert_error(result, code, target);
            drop(armed);
            assert_publication(&root, state, true);
            eprintln!("persistence-error case=rotate point={target} errno={code} recovered=PASS");
        }
    }
}
#[test]
fn managed_initialization_io_failures_never_reset_partial_store() {
    for code in [5, 28] {
        for &(target, state) in INITIALIZATION_CUTS {
            let temp = Temp::new();
            let root = temp.store();
            let armed = Armed::new(target, Action::Error(code));
            let result = ReceiptJournal::create_managed(&root, ID, 1);
            assert!(armed.reached(), "missing cut {target}: {:?}", armed.trace());
            assert_error(result, code, target);
            drop(armed);
            assert_publication(&root, state, false);
            eprintln!(
                "persistence-error case=initialize point={target} errno={code} recovered=PASS"
            );
        }
    }
}
#[test]
fn managed_reopen_io_failures_return_no_writer_and_preserve_facts() {
    for code in [5, 28] {
        for &target in REOPEN_CUTS {
            let temp = Temp::new();
            let root = temp.store();
            prepared_unresolved(&root);
            let before = snapshot(&root);
            let armed = Armed::new(target, Action::Error(code));
            let result = ReceiptJournal::open_managed(&root, ID, ManagedOpenPolicy::STRICT);
            assert!(armed.reached(), "missing cut {target}");
            assert_error(result, code, target);
            drop(armed);
            assert_eq!(snapshot(&root), before);
            assert_unresolved_preserved(&root);
            eprintln!("persistence-error case=reopen point={target} errno={code} recovered=PASS");
        }
    }
}
#[test]
fn managed_pending_recovery_io_failures_never_lose_predecessors() {
    for code in [5, 28] {
        for &(target, state) in ROTATION_CUTS
            .iter()
            .filter(|(p, _)| p.starts_with("publish."))
        {
            let temp = Temp::new();
            let root = temp.store();
            recovered_pending(&root);
            let armed = Armed::new(target, Action::Error(code));
            let result = ReceiptJournal::open_managed(&root, ID, ManagedOpenPolicy::RECOVER_CRASH);
            assert!(armed.reached(), "missing cut {target}");
            assert_error(result, code, target);
            drop(armed);
            assert_publication(&root, state, true);
            eprintln!("persistence-error case=pending point={target} errno={code} recovered=PASS");
        }
    }
}
pub(crate) fn assert_append_cut(root: &Path, target: &str) {
    let partial = target == "commit.partial_write";
    let complete = !partial && target != "commit.before_write";
    let before = snapshot(root);
    if partial {
        assert!(ReceiptJournal::open_managed(root, ID, ManagedOpenPolicy::STRICT).is_err());
        assert_eq!(snapshot(root), before);
    }
    let mut writer =
        ReceiptJournal::open_managed(root, ID, ManagedOpenPolicy::RECOVER_CRASH).unwrap();
    let report = writer.inspect().unwrap();
    assert_eq!(report.records.len(), if complete { 3 } else { 2 });
    assert!(
        writer
            .append(event("prior", LifecycleState::Requested))
            .is_err()
    );
    if complete {
        assert_eq!(report.unresolved.len(), 1);
        assert_eq!(report.unresolved[0].receipt_id, "new");
        assert!(
            writer
                .append(event("new", LifecycleState::Requested))
                .is_err()
        );
        assert_eq!(
            snapshot(root),
            before,
            "complete unacknowledged record changed"
        );
    } else {
        assert!(report.unresolved.is_empty());
        assert_eq!(
            writer
                .append(event("new", LifecycleState::Requested))
                .unwrap()
                .sequence,
            3
        );
    }
}
#[test]
fn managed_append_io_failures_poison_writer_and_keep_complete_records() {
    for code in [5, 28] {
        for &target in APPEND_CUTS {
            let temp = Temp::new();
            let root = temp.store();
            let mut writer = prepared(&root);
            let armed = Armed::new(target, Action::Error(code));
            let result = writer.append(event("new", LifecycleState::Requested));
            assert!(armed.reached(), "missing cut {target}");
            assert_error(result, code, target);
            drop(armed);
            assert!(matches!(
                writer.append(event("other", LifecycleState::Requested)),
                Err(JournalError::WriterPoisoned)
            ));
            drop(writer);
            assert_append_cut(&root, target);
            eprintln!("persistence-error case=append point={target} errno={code} recovered=PASS");
        }
    }
}
pub(crate) fn assert_repaired(root: &Path) {
    let mut writer =
        ReceiptJournal::open_managed(root, ID, ManagedOpenPolicy::RECOVER_CRASH).unwrap();
    let report = writer.inspect().unwrap();
    assert_eq!(report.records.len(), 2);
    assert_eq!(report.tail, TailStatus::Clean);
    assert!(
        writer
            .append(event("prior", LifecycleState::Requested))
            .is_err()
    );
    drop(writer);
    let stable = snapshot(root);
    drop(ReceiptJournal::open_managed(root, ID, ManagedOpenPolicy::STRICT).unwrap());
    assert_eq!(snapshot(root), stable);
}
#[test]
fn managed_tail_repair_io_failures_recover_only_the_validated_prefix() {
    for code in [5, 28] {
        for &target in REPAIR_CUTS {
            let temp = Temp::new();
            let root = temp.store();
            with_torn_tail(&root);
            let before = snapshot(&root);
            let armed = Armed::new(target, Action::Error(code));
            let result = ReceiptJournal::open_managed(&root, ID, ManagedOpenPolicy::RECOVER_CRASH);
            assert!(armed.reached(), "missing cut {target}");
            assert_error(result, code, target);
            drop(armed);
            let after = snapshot(&root);
            for (name, bytes) in after {
                if name == FIRST {
                    assert!(before[&name].starts_with(&bytes));
                } else {
                    assert_eq!(before[&name], bytes);
                }
            }
            assert_repaired(&root);
            eprintln!("persistence-error case=repair point={target} errno={code} recovered=PASS");
        }
    }
}

#[test]
fn managed_reopen_barrier_order_and_no_receipt_changes() {
    let temp = Temp::new();
    prepared_unresolved(&temp.store());
    let before = snapshot(&temp.store());
    let armed = Armed::new("unreachable-observe-only", Action::Error(5));
    drop(ReceiptJournal::open_managed(temp.store(), ID, ManagedOpenPolicy::STRICT).unwrap());
    assert_eq!(armed.trace(), REOPEN_CUTS);
    assert!(!armed.reached());
    drop(armed);
    assert_eq!(snapshot(&temp.store()), before);
}
#[test]
fn managed_corrupt_store_is_rejected_before_barrier_or_mutation() {
    for tamper in ["identity", "unknown_entry", "complete_corruption"] {
        let temp = Temp::new();
        let root = temp.store();
        drop(prepared(&root));
        match tamper {
            "identity" => {
                fs::write(root.join("store.v1"), [0; 56]).unwrap();
            }
            "unknown_entry" => {
                fs::write(root.join("unknown"), b"preserve").unwrap();
            }
            _ => {
                let mut bytes = fs::read(root.join(FIRST)).unwrap();
                *bytes.last_mut().unwrap() ^= 1;
                fs::write(root.join(FIRST), bytes).unwrap();
            }
        }
        let before = snapshot(&root);
        let armed = Armed::new("unreachable", Action::Error(5));
        assert!(ReceiptJournal::open_managed(&root, ID, ManagedOpenPolicy::RECOVER_CRASH).is_err());
        assert!(
            armed.trace().is_empty(),
            "invalid store reached mutating persistence path"
        );
        drop(armed);
        assert_eq!(snapshot(&root), before);
    }
}
#[test]
fn persistence_injection_is_thread_local_and_removed_on_drop() {
    let temp = Temp::new();
    let root = temp.store();
    let armed = Armed::new("initialize.before_directory_create", Action::Error(5));
    let separate = root.clone();
    std::thread::spawn(move || {
        drop(ReceiptJournal::create_managed(separate, ID, 1).unwrap());
    })
    .join()
    .unwrap();
    assert!(!armed.reached());
    assert!(armed.trace().is_empty());
    drop(armed);
    drop(ReceiptJournal::open_managed(root, ID, ManagedOpenPolicy::STRICT).unwrap());
}
