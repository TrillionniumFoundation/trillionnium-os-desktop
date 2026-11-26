//! Bounded same-filesystem write-ahead publication. These private types only
//! amortize durability barriers; they never grant source or target authority.
use super::*;
use std::collections::BTreeSet;

pub(super) const BATCH_LIMIT: usize = 64;
const BODY_LIMIT: usize = 8 * 1024 * 1024;

struct PendingRecord {
    records: Records,
    name: String,
    pending: String,
    file: File,
    identity: Identity,
    body: Vec<u8>,
}

pub(super) struct RecordBatch {
    entries: Vec<PendingRecord>,
    bytes: usize,
}

impl RecordBatch {
    pub(super) fn new() -> Self {
        Self {
            entries: Vec::new(),
            bytes: 0,
        }
    }
    pub(super) fn stage(
        &mut self,
        records: &Records,
        name: &str,
        value: &impl Serialize,
    ) -> Result<()> {
        ensure(
            matches!(
                name,
                "PREIMAGE.json"
                    | "CURRENT-PREIMAGE.json"
                    | "APPLIED.json"
                    | "RESTORED.json"
                    | "RESTORE-INTENT.json"
            ),
            "batch record name is outside the fixed label journal",
        )?;
        let body = serde_json::to_vec(value)?;
        ensure(
            !body.is_empty()
                && body.len() as u64 <= LIMIT
                && self.entries.len() < BATCH_LIMIT
                && self
                    .bytes
                    .checked_add(body.len())
                    .is_some_and(|n| n <= BODY_LIMIT),
            "label durability batch exceeds its bounded record/body budget",
        )?;
        records.revalidate()?;
        if let Some(first) = self.entries.first() {
            ensure(
                first.records.identity.dev == records.identity.dev,
                "a label durability batch cannot span filesystems",
            )?;
        }
        ensure(
            !self.entries.iter().any(|e| {
                e.records.identity.dev == records.identity.dev
                    && e.records.identity.ino == records.identity.ino
                    && e.name == name
            }),
            "duplicate label record in a durability batch",
        )?;
        ensure(!records.exists(name)?, "batch publication is create-only")?;
        let pending = format!("{name}.pending");
        records.preserve_interrupted(&pending)?;
        let mut file = File::from(rustix::fs::openat(
            &records.held,
            pending.as_str(),
            OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o400),
        )?);
        file.write_all(&body)?;
        rustix::fs::fchmod(&file, Mode::from_raw_mode(0o400))?;
        let identity = fs::stat(&file)?;
        let entry = PendingRecord {
            records: Records {
                path: records.path.clone(),
                held: records.held.try_clone()?,
                identity: records.identity.clone(),
            },
            name: name.into(),
            pending,
            file,
            identity,
            body,
        };
        entry.verify_pending()?;
        self.bytes += entry.body.len();
        self.entries.push(entry);
        Ok(())
    }
    /// No named record is exposed until every pending body and its directory
    /// entry has passed a real same-filesystem metadata/data barrier. A crash
    /// during the following renames can expose a subset, but every exposed
    /// record already has complete durable bytes. A second barrier commits
    /// those names before this function can return any usable preimage pin.
    pub(super) fn publish(mut self) -> Result<Vec<FilePin>> {
        if self.entries.is_empty() {
            return Ok(Vec::new());
        }
        for entry in &self.entries {
            entry.verify_pending()?;
        }
        sync_filesystem(&self.entries[0].records.held)?;
        for entry in &self.entries {
            entry.verify_pending()?;
        }
        for entry in &mut self.entries {
            entry.verify_pending()?;
            rustix::fs::renameat_with(
                &entry.records.held,
                entry.pending.as_str(),
                &entry.records.held,
                entry.name.as_str(),
                RenameFlags::NOREPLACE,
            )?;
            let after = fs::stat(&entry.file)?;
            ensure(
                only_ctime_changed(&entry.identity, &after),
                "batch record publication changed more than its rename ctime",
            )?;
            entry.identity = after;
            entry.verify_named()?;
        }
        sync_filesystem(&self.entries[0].records.held)?;
        self.entries
            .iter()
            .map(|entry| {
                entry.verify_named()?;
                Ok(FilePin {
                    path: entry.records.path.join(&entry.name),
                    bytes: entry.body.len() as u64,
                    sha256: fs::digest(&entry.body),
                })
            })
            .collect()
    }
}
impl PendingRecord {
    fn verify(&self, name: &str) -> Result<()> {
        self.records.revalidate()?;
        let (named, identity, bytes) = self.records.read(name)?;
        ensure(
            identity == self.identity
                && fs::stat(&self.file)? == self.identity
                && fs::stat(&named)? == self.identity
                && bytes == self.body
                && fs::xattrs(&self.file)?.is_empty(),
            "held batch record body, attributes or named inode changed",
        )
    }
    fn verify_pending(&self) -> Result<()> {
        ensure(
            !self.records.exists(&self.name)?,
            "batch output appeared before publication",
        )?;
        self.verify(&self.pending)
    }
    fn verify_named(&self) -> Result<()> {
        self.verify(&self.name)
    }
}

/// Every target has its own held recovery FD and exact before/after snapshot.
/// One syncfs covers only targets on the same observed filesystem; all are
/// read back individually before and after that real barrier.
pub(super) fn sync_targets(targets: &[(&Records, &File, &Snapshot)]) -> Result<Vec<Value>> {
    ensure(
        !targets.is_empty() && targets.len() <= BATCH_LIMIT,
        "bounded nonempty actual label target batch required",
    )?;
    let anchor = targets[0].0;
    let mut inodes = BTreeSet::new();
    for (records, held, expected) in targets {
        records.revalidate()?;
        ensure(
            records.identity.dev == anchor.identity.dev
                && expected.identity.dev == anchor.identity.dev
                && inodes.insert((expected.identity.dev, expected.identity.ino))
                && snapshot(held)? == **expected,
            "batch target filesystem, unique inode or complete snapshot differs",
        )?;
    }
    sync_filesystem(&anchor.held)?;
    let anchor_identity = fs::stat(&anchor.held)?;
    targets
        .iter()
        .map(|(records, held, expected)| {
            records.revalidate()?;
            ensure(
                snapshot(held)? == **expected,
                "a label target changed across the shared actual filesystem barrier",
            )?;
            Ok(
                json!({"operation":"syncfs","filesystem_dev":anchor.identity.dev,
            "anchor_identity":anchor_identity,"target_identity":expected.identity,
            "target_handle":expected.handle,"batch_target_count":targets.len()}),
            )
        })
        .collect()
}

pub(super) fn sync_filesystem(anchor: &File) -> Result<()> {
    rustix::fs::syncfs(anchor)?;
    #[cfg(test)]
    BARRIERS.with(|value| value.set(value.get() + 1));
    Ok(())
}

#[cfg(test)]
thread_local! { pub(super) static BARRIERS: std::cell::Cell<usize> = const { std::cell::Cell::new(0) }; }

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    const TEST_LABEL: &str = "user.droidloom.batch-label";
    fn held(path: &Path) -> File {
        File::from(
            rustix::fs::open(
                path,
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .unwrap(),
        )
    }
    fn records(path: &Path) -> Records {
        std::fs::create_dir(path).unwrap();
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700)).unwrap();
        Records::open(path).unwrap()
    }
    fn plan(root: &Path) -> FilePin {
        FilePin {
            path: root.join("source-plan"),
            bytes: 1,
            sha256: "a".repeat(64),
        }
    }
    fn stages(root: &Path, count: usize) -> (Vec<PendingAttempt>, RecordBatch) {
        let mut batch = RecordBatch::new();
        let mut pending = Vec::new();
        for index in 0..count {
            let target = root.join(format!("target-{index}"));
            if index % 2 == 0 {
                std::fs::write(&target, b"unchanged public body").unwrap();
            } else {
                std::fs::create_dir(&target).unwrap();
            }
            let record = records(&root.join(format!("inode-{index}")));
            pending.push(
                DurableAttempt::stage(
                    record,
                    held(&target),
                    &"b".repeat(64),
                    &plan(root),
                    index as u32,
                    Path::new(&format!("/usr/source/{index}")),
                    b"candidate",
                    TEST_LABEL,
                    &mut batch,
                )
                .unwrap(),
            );
        }
        (pending, batch)
    }
    #[test]
    fn sixty_four_actual_inodes_use_bounded_real_barriers_and_restore_every_preimage() {
        let root = tempfile::Builder::new()
            .prefix(".p4-label-batch-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        BARRIERS.with(|v| v.set(0));
        let (pending, batch) = stages(root.path(), BATCH_LIMIT);
        assert_eq!(BARRIERS.with(|v| v.get()), 0);
        for draft in &pending {
            assert_eq!(snapshot(&draft.recovery).unwrap(), draft.preimage.before);
        }
        let attempts = DurableAttempt::seal_preparations(pending, batch).unwrap();
        assert_eq!(BARRIERS.with(|v| v.get()), 2);
        let cores = attempts
            .iter()
            .map(|a| a.apply_uncommitted().unwrap())
            .collect::<Vec<_>>();
        assert!(
            attempts
                .iter()
                .all(|a| !a.records.exists("APPLIED.json").unwrap())
        );
        let refs = attempts.iter().collect::<Vec<_>>();
        let applied = DurableAttempt::complete_applications(&refs, &cores).unwrap();
        assert_eq!(applied.len(), BATCH_LIMIT);
        assert_eq!(BARRIERS.with(|v| v.get()), 5);
        let originals = attempts
            .iter()
            .map(|a| a.preimage.before.clone())
            .collect::<Vec<_>>();
        let mut pending = Vec::new();
        let mut batch = RecordBatch::new();
        let retirement = FilePin {
            path: root.path().join("actual-retirement"),
            bytes: 1,
            sha256: "c".repeat(64),
        };
        for (index, original) in attempts.into_iter().enumerate() {
            pending.push(
                RuntimeRestoreAttempt::stage_exact(
                    original,
                    records(&root.path().join(format!("return-{index}"))),
                    &retirement,
                    None,
                    &mut batch,
                )
                .unwrap(),
            );
        }
        let restoring = RuntimeRestoreAttempt::seal_preparations(pending, batch).unwrap();
        assert_eq!(BARRIERS.with(|v| v.get()), 7);
        let provisional = restoring
            .iter()
            .map(|a| a.restore_uncommitted().unwrap())
            .collect::<Vec<_>>();
        let refs = restoring.iter().collect::<Vec<_>>();
        let outputs = RuntimeRestoreAttempt::complete_restorations(&refs, &provisional).unwrap();
        assert_eq!(outputs.len(), BATCH_LIMIT);
        assert_eq!(BARRIERS.with(|v| v.get()), 10);
        for (index, (actual, original)) in provisional.iter().zip(originals).enumerate() {
            assert_eq!(actual.core.after.attributes, original.attributes);
            assert_eq!(actual.core.after.handle, original.handle);
            assert!(only_ctime_changed(
                &original.identity,
                &actual.core.after.identity
            ));
            assert_eq!(
                snapshot(&held(&root.path().join(format!("target-{index}")))).unwrap(),
                actual.core.after
            );
            if index % 2 == 0 {
                assert_eq!(
                    std::fs::read(root.path().join(format!("target-{index}"))).unwrap(),
                    b"unchanged public body"
                );
            }
        }
        println!(
            "actual targets=64 regular=32 directories=32 same_fs_barriers=10 complete_before_after_readback=64 restored=64"
        );
    }
    #[test]
    fn crash_between_preimage_renames_exposes_only_complete_durable_originals_and_no_writes() {
        let root = tempfile::Builder::new()
            .prefix(".p4-label-batch-crash-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let (pending, batch) = stages(root.path(), 4);
        let before = pending
            .iter()
            .map(|p| p.preimage.before.clone())
            .collect::<Vec<_>>();
        // Actual first phase, then a process interruption after just one
        // NOREPLACE publication. No DurableAttempt has been returned.
        for entry in &batch.entries {
            entry.verify_pending().unwrap();
        }
        sync_filesystem(&batch.entries[0].records.held).unwrap();
        let entry = &batch.entries[0];
        rustix::fs::renameat_with(
            &entry.records.held,
            entry.pending.as_str(),
            &entry.records.held,
            entry.name.as_str(),
            RenameFlags::NOREPLACE,
        )
        .unwrap();
        drop(batch);
        drop(pending);
        for (index, expected) in before.iter().enumerate() {
            assert_eq!(
                snapshot(&held(&root.path().join(format!("target-{index}")))).unwrap(),
                *expected
            );
            let records = Records::open(&root.path().join(format!("inode-{index}"))).unwrap();
            if index == 0 {
                let (_, _, bytes) = records.read("PREIMAGE.json").unwrap();
                let value: Preimage = serde_json::from_slice(&bytes).unwrap();
                assert_eq!(value.before, *expected);
            } else {
                records.verify_unpublished_preimage().unwrap();
            }
            assert!(!records.exists("APPLIED.json").unwrap());
        }
    }
    #[test]
    fn crash_after_partial_batch_syscalls_recovers_all_targets_from_original_generation() {
        let root = tempfile::Builder::new()
            .prefix(".p4-label-batch-outcome-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let (pending, batch) = stages(root.path(), 8);
        let attempts = DurableAttempt::seal_preparations(pending, batch).unwrap();
        let pins = attempts.iter().map(|a| a.pin.clone()).collect::<Vec<_>>();
        for attempt in attempts.iter().take(3) {
            attempt.apply_uncommitted().unwrap();
        }
        assert!(
            attempts
                .iter()
                .all(|a| !a.records.exists("APPLIED.json").unwrap())
        );
        drop(attempts);
        for (index, pin) in pins.iter().enumerate() {
            let attempt = DurableAttempt::reopen(
                Records::open(&root.path().join(format!("inode-{index}"))).unwrap(),
                pin,
                held(&root.path().join(format!("target-{index}"))),
            )
            .unwrap();
            assert_eq!(attempt.classify(false).unwrap().1, index < 3);
            let restored = attempt.restore().unwrap();
            assert_eq!(restored.attributes, attempt.preimage.before.attributes);
        }
    }
    #[test]
    fn partial_runtime_restoration_without_results_reopens_its_durable_current_preimages() {
        let root = tempfile::Builder::new()
            .prefix(".p4-label-batch-return-crash-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let (pending, batch) = stages(root.path(), 8);
        let attempts = DurableAttempt::seal_preparations(pending, batch).unwrap();
        let cores = attempts
            .iter()
            .map(|a| a.apply_uncommitted().unwrap())
            .collect::<Vec<_>>();
        DurableAttempt::complete_applications(&attempts.iter().collect::<Vec<_>>(), &cores)
            .unwrap();
        let original_pins = attempts.iter().map(|a| a.pin.clone()).collect::<Vec<_>>();
        let mut pending = Vec::new();
        let mut batch = RecordBatch::new();
        let retirement = FilePin {
            path: root.path().join("actual-retirement"),
            bytes: 1,
            sha256: "c".repeat(64),
        };
        for (index, attempt) in attempts.into_iter().enumerate() {
            pending.push(
                RuntimeRestoreAttempt::stage_exact(
                    attempt,
                    records(&root.path().join(format!("return-{index}"))),
                    &retirement,
                    None,
                    &mut batch,
                )
                .unwrap(),
            );
        }
        let attempts = RuntimeRestoreAttempt::seal_preparations(pending, batch).unwrap();
        let current_pins = attempts
            .iter()
            .map(|a| a.preimage_pin().clone())
            .collect::<Vec<_>>();
        for attempt in attempts.iter().take(3) {
            attempt.restore_uncommitted().unwrap();
        }
        for attempt in &attempts {
            assert!(!attempt.has_completed_result().unwrap());
        }
        drop(attempts);
        for (index, (original, current)) in original_pins.iter().zip(current_pins).enumerate() {
            let original = DurableAttempt::load_unclassified(
                Records::open(&root.path().join(format!("inode-{index}"))).unwrap(),
                original,
                held(&root.path().join(format!("target-{index}"))),
            )
            .unwrap();
            let before = original.preimage.before.clone();
            let attempt = RuntimeRestoreAttempt::reopen(
                original,
                Records::open(&root.path().join(format!("return-{index}"))).unwrap(),
                &current,
            )
            .unwrap();
            assert_eq!(attempt.classify().unwrap().1, index < 3);
            let (actual, _) = attempt.restore().unwrap();
            assert_eq!(actual.after.attributes, before.attributes);
            assert_eq!(actual.after.handle, before.handle);
            assert!(only_ctime_changed(&before.identity, &actual.after.identity));
        }
    }
    #[test]
    fn uncertain_batch_keeps_every_recovery_fd_and_rejects_foreign_xattrs_or_replaced_records() {
        let root = tempfile::Builder::new()
            .prefix(".p4-label-batch-foreign-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let (pending, batch) = stages(root.path(), 4);
        let attempts = DurableAttempt::seal_preparations(pending, batch).unwrap();
        let cores = attempts
            .iter()
            .map(|a| a.apply_uncommitted().unwrap())
            .collect::<Vec<_>>();
        set(&attempts[2].recovery, "user.unrelated", Some(b"foreign")).unwrap();
        let refs = attempts.iter().collect::<Vec<_>>();
        assert!(DurableAttempt::complete_applications(&refs, &cores).is_err());
        for attempt in &attempts {
            attempt.validate_intent().unwrap();
            assert!(!attempt.records.exists("APPLIED.json").unwrap());
        }
        assert!(attempts[2].restore().is_err());
        let old = attempts[0].records.path.join("PREIMAGE.json");
        let bytes = std::fs::read(&old).unwrap();
        std::fs::rename(&old, attempts[0].records.path.join("foreign-saved")).unwrap();
        std::fs::write(&old, bytes).unwrap();
        std::fs::set_permissions(&old, std::fs::Permissions::from_mode(0o400)).unwrap();
        assert!(attempts[0].restore().is_err());
        for attempt in [&attempts[1], &attempts[3]] {
            attempt.restore().unwrap();
        }
    }
}
