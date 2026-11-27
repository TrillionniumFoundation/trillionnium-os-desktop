//! Durable recovery of a single inode label attempt, including uncertain
//! syscall outcomes. This internal core is not a physical installation API.
//! The source-bound plan and live once adapter own its only production caller.
use super::{LABEL, LabelDerivation, Snapshot, apply_one, only_ctime_changed, set, snapshot};
use crate::{Result, boot_files::FilePin, ensure, fs, model::Identity};
use rustix::fs::{AtFlags, FileType, Mode, OFlags, RenameFlags, ResolveFlags};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs::File,
    io::Write,
    os::unix::fs::FileExt,
    path::{Path, PathBuf},
};

#[path = "cold_working_label_writer.rs"]
mod working_writer;
pub(crate) use working_writer::{WorkingLabelTransaction, WorkingLabelsApplied, WorkingLabelsRestored};

#[path = "cold_original_label_runtime.rs"]
mod runtime;
pub(super) use runtime::RuntimeRestoreAttempt;
#[path = "cold_original_label_transaction.rs"]
mod transaction;
pub(crate) use transaction::{
    OriginalLabelRestorationTransaction, OriginalLabelTransaction, OriginalLabelsApplied,
    OriginalLabelsRestored, OriginalPairRestored,
};
pub(in crate::cold_original_data) use transaction::{
    restore_retired_pair, withdraw_labeled_selection,
};

#[path = "cold_original_label_batch.rs"]
mod batch;
use batch::{BATCH_LIMIT, RecordBatch, sync_targets};

#[cfg(test)]
#[path = "cold_original_label_directory_tests.rs"]
mod directory_tests;

const LIMIT: u64 = 32 * 1024 * 1024;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Preimage {
    schema: String,
    candidate_id: String,
    source_plan: FilePin,
    ordinal: u32,
    logical_path: PathBuf,
    before: Snapshot,
    desired: Vec<u8>,
    attribute: String,
}

struct Records {
    path: PathBuf,
    held: File,
    identity: Identity,
}
impl Records {
    fn open(path: &Path) -> Result<Self> {
        let tree = fs::Tree::open(
            &fs::absolute_string(path)?,
            rustix::process::geteuid().as_raw(),
        )?;
        let identity = fs::stat(&tree.root)?;
        ensure(
            identity.mode & 0o7777 == 0o700,
            "label journal must be private",
        )?;
        let value = Self {
            path: path.to_owned(),
            held: tree.root,
            identity,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        // The original Tree::open path grammar and final owner/mode gates
        // remain unchanged. Resolve the same absolute path without following
        // any component symlink in one kernel operation, rather than reopening
        // every ancestor separately for every immutable journal read.
        let named = File::from(rustix::fs::openat2(
            rustix::fs::CWD,
            fs::absolute_string(&self.path)?,
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::CLOEXEC | OFlags::NOFOLLOW,
            Mode::empty(),
            ResolveFlags::NO_SYMLINKS | ResolveFlags::NO_MAGICLINKS,
        )?);
        for actual in [fs::stat(&named)?, fs::stat(&self.held)?] {
            ensure(
                (actual.dev, actual.ino, actual.mode, actual.uid, actual.gid)
                    == (
                        self.identity.dev,
                        self.identity.ino,
                        self.identity.mode,
                        self.identity.uid,
                        self.identity.gid,
                    ),
                "label journal directory custody changed",
            )?;
        }
        Ok(())
    }
    fn sync_target(&self, target: &File, expected: &Snapshot) -> Result<Value> {
        self.revalidate()?;
        ensure(
            expected.identity.dev == self.identity.dev && snapshot(target)? == *expected,
            "label durability anchor and actual target filesystem differ",
        )?;
        // O_PATH cannot fsync an inode. This ordinary held directory belongs
        // to exactly the same filesystem as the target and durable preimage.
        // syncfs flushes target xattr metadata, not merely journal contents.
        rustix::fs::syncfs(&self.held)?;
        self.revalidate()?;
        ensure(
            snapshot(target)? == *expected,
            "label changed across its filesystem durability barrier",
        )?;
        Ok(
            json!({"operation":"syncfs","filesystem_dev":self.identity.dev,
            "anchor_identity":fs::stat(&self.held)?,"target_identity":expected.identity,
            "target_handle":expected.handle}),
        )
    }
    fn read(&self, name: &str) -> Result<(File, Identity, Vec<u8>)> {
        self.revalidate()?;
        let file = File::from(rustix::fs::openat(
            &self.held,
            name,
            OFlags::RDONLY
                | OFlags::NOFOLLOW
                | OFlags::CLOEXEC
                | OFlags::NONBLOCK
                | OFlags::NOATIME,
            Mode::empty(),
        )?);
        let before = fs::stat(&file)?;
        ensure(
            FileType::from_raw_mode(before.mode) == FileType::RegularFile
                && before.uid == self.identity.uid
                && before.gid == self.identity.gid
                && before.nlink == 1
                && before.mode & 0o7777 == 0o400
                && before.size > 0
                && before.size <= LIMIT,
            "label journal record custody differs",
        )?;
        ensure(
            fs::xattrs(&file)?.is_empty(),
            "label evidence has ACL or capability",
        )?;
        let mut bytes = vec![0; before.size as usize];
        file.read_exact_at(&mut bytes, 0)?;
        let named = fs::identity(&rustix::fs::statat(
            &self.held,
            name,
            AtFlags::SYMLINK_NOFOLLOW,
        )?);
        ensure(
            fs::stat(&file)? == before && named == before,
            "label journal record changed while reading",
        )?;
        Ok((file, before, bytes))
    }
    fn exists(&self, name: &str) -> Result<bool> {
        self.revalidate()?;
        match rustix::fs::statat(&self.held, name, AtFlags::SYMLINK_NOFOLLOW) {
            Ok(_) => Ok(true),
            Err(rustix::io::Errno::NOENT) => Ok(false),
            Err(e) => Err(e.into()),
        }
    }
    fn verify_unpublished_preimage(&self) -> Result<()> {
        self.revalidate()?;
        ensure(
            !self.exists("PREIMAGE.json")?,
            "published label preimage cannot be replaced",
        )?;
        let mut count = 0;
        for entry in rustix::fs::Dir::read_from(&self.held)? {
            let entry = entry?;
            let name = entry.file_name().to_str()?;
            if matches!(name, "." | "..") {
                continue;
            }
            count += 1;
            ensure(count <= 16, "too many interrupted preimage publications")?;
            let pending = name == "PREIMAGE.json.pending";
            let preserved = name.strip_prefix("PREIMAGE.json.pending.interrupted-");
            ensure(
                pending || preserved.is_some(),
                "unpublished preimage directory has an unrelated record",
            )?;
            let file = File::from(rustix::fs::openat(
                &self.held,
                name,
                OFlags::RDONLY
                    | OFlags::NOFOLLOW
                    | OFlags::CLOEXEC
                    | OFlags::NONBLOCK
                    | OFlags::NOATIME,
                Mode::empty(),
            )?);
            let id = fs::stat(&file)?;
            ensure(
                FileType::from_raw_mode(id.mode) == FileType::RegularFile
                    && id.uid == self.identity.uid
                    && id.gid == self.identity.gid
                    && id.nlink == 1
                    && id.mode & 0o7777 == 0o400
                    && id.size <= LIMIT
                    && fs::xattrs(&file)?.is_empty(),
                "interrupted preimage file lost custody",
            )?;
            let mut body = vec![0; id.size as usize];
            file.read_exact_at(&mut body, 0)?;
            if let Some(suffix) = preserved {
                ensure(
                    suffix == format!("{}-{}", id.ino, fs::digest(&body)),
                    "preserved interrupted preimage no longer has its recorded bytes/inode",
                )?;
            }
            ensure(
                fs::stat(&file)? == id
                    && fs::identity(&rustix::fs::statat(
                        &self.held,
                        name,
                        AtFlags::SYMLINK_NOFOLLOW,
                    )?) == id,
                "interrupted preimage changed during actual readback",
            )?;
        }
        self.revalidate()
    }
    fn preserve_interrupted(&self, name: &str) -> Result<()> {
        if !self.exists(name)? {
            return Ok(());
        }
        let file = File::from(rustix::fs::openat(
            &self.held,
            name,
            OFlags::RDONLY
                | OFlags::NOFOLLOW
                | OFlags::CLOEXEC
                | OFlags::NONBLOCK
                | OFlags::NOATIME,
            Mode::empty(),
        )?);
        let before = fs::stat(&file)?;
        ensure(
            FileType::from_raw_mode(before.mode) == FileType::RegularFile
                && before.uid == self.identity.uid
                && before.gid == self.identity.gid
                && before.nlink == 1
                && before.mode & 0o7777 == 0o400
                && before.size <= LIMIT,
            "interrupted label journal entry lost custody",
        )?;
        ensure(
            fs::xattrs(&file)?.is_empty(),
            "interrupted journal entry has execution authority",
        )?;
        let mut bytes = vec![0; before.size as usize];
        file.read_exact_at(&mut bytes, 0)?;
        ensure(
            fs::stat(&file)? == before
                && fs::identity(&rustix::fs::statat(
                    &self.held,
                    name,
                    AtFlags::SYMLINK_NOFOLLOW,
                )?) == before,
            "interrupted label journal entry changed during preservation",
        )?;
        let preserved = format!("{name}.interrupted-{}-{}", before.ino, fs::digest(&bytes));
        rustix::fs::renameat_with(
            &self.held,
            name,
            &self.held,
            preserved.as_str(),
            RenameFlags::NOREPLACE,
        )?;
        self.held.sync_all()?;
        let after = fs::stat(&file)?;
        ensure(
            only_ctime_changed(&before, &after)
                && fs::identity(&rustix::fs::statat(
                    &self.held,
                    preserved.as_str(),
                    AtFlags::SYMLINK_NOFOLLOW,
                )?) == after,
            "interrupted journal entry preservation changed its inode",
        )?;
        Ok(())
    }
    fn publish(&self, name: &str, value: &impl Serialize) -> Result<FilePin> {
        self.revalidate()?;
        let bytes = serde_json::to_vec(value)?;
        ensure(
            !bytes.is_empty() && bytes.len() as u64 <= LIMIT,
            "bounded label journal record required",
        )?;
        ensure(
            !self.exists(name)?,
            "label evidence publication is create-only",
        )?;
        let pending = format!("{name}.pending");
        self.preserve_interrupted(&pending)?;
        let mut file = File::from(rustix::fs::openat(
            &self.held,
            pending.as_str(),
            OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o400),
        )?);
        file.write_all(&bytes)?;
        rustix::fs::fchmod(&file, Mode::from_raw_mode(0o400))?;
        file.sync_all()?;
        self.held.sync_all()?;
        self.revalidate()?;
        rustix::fs::renameat_with(
            &self.held,
            pending.as_str(),
            &self.held,
            name,
            RenameFlags::NOREPLACE,
        )?;
        self.held.sync_all()?;
        let (actual, _, readback) = self.read(name)?;
        ensure(
            fs::stat(&actual)? == fs::stat(&file)? && readback == bytes,
            "durable label evidence readback differs",
        )?;
        Ok(FilePin {
            path: self.path.join(name),
            bytes: bytes.len() as u64,
            sha256: fs::digest(&bytes),
        })
    }
}

/// Owns an independent recovery descriptor even if apply_one consumes its
/// clone and returns Err after a successful xattr syscall. No receipt flag
/// constructs this type; reopening validates the complete immutable preimage.
struct DurableAttempt {
    records: Records,
    preimage: Preimage,
    pin: FilePin,
    intent: File,
    intent_identity: Identity,
    recovery: File,
}
struct PendingAttempt {
    records: Records,
    preimage: Preimage,
    recovery: File,
}
impl DurableAttempt {
    fn stage(
        records: Records,
        file: File,
        candidate_id: &str,
        source_plan: &FilePin,
        ordinal: u32,
        logical_path: &Path,
        desired: &[u8],
        attribute: &str,
        batch: &mut RecordBatch,
    ) -> Result<PendingAttempt> {
        ensure(
            attribute == LABEL || cfg!(test),
            "only SELinux labels may be journaled",
        )?;
        ensure(
            fs::valid_digest(candidate_id)
                && fs::valid_digest(&source_plan.sha256)
                && source_plan.bytes > 0
                && logical_path.is_absolute()
                && !desired.is_empty()
                && desired.len() <= 4096,
            "label preimage is not source-bound",
        )?;
        let before = snapshot(&file)?;
        ensure(
            before.identity.dev == records.identity.dev,
            "label preimage and inode must share the durable filesystem",
        )?;
        let preimage = Preimage {
            schema: "droidloom.original-label-preimage.v1".into(),
            candidate_id: candidate_id.into(),
            source_plan: source_plan.clone(),
            ordinal,
            logical_path: logical_path.to_owned(),
            before,
            desired: desired.to_vec(),
            attribute: attribute.into(),
        };
        batch.stage(&records, "PREIMAGE.json", &preimage)?;
        ensure(
            snapshot(&file)? == preimage.before,
            "label inode changed while its preimage was staged",
        )?;
        Ok(PendingAttempt {
            records,
            preimage,
            recovery: file,
        })
    }

    fn seal_preparations(pending: Vec<PendingAttempt>, batch: RecordBatch) -> Result<Vec<Self>> {
        let pins = batch.publish()?;
        ensure(
            pending.len() == pins.len() && !pending.is_empty(),
            "label preparation batch membership differs",
        )?;
        pending
            .into_iter()
            .zip(pins)
            .map(|(draft, pin)| {
                ensure(
                    pin.path == draft.records.path.join("PREIMAGE.json"),
                    "batch preimage pin does not name its held source target",
                )?;
                let (intent, intent_identity, _) = draft.records.read("PREIMAGE.json")?;
                let value = Self {
                    records: draft.records,
                    preimage: draft.preimage,
                    pin,
                    intent,
                    intent_identity,
                    recovery: draft.recovery,
                };
                value.validate_intent()?;
                ensure(
                    snapshot(&value.recovery)? == value.preimage.before,
                    "label target changed across its durable batch preimage",
                )?;
                Ok(value)
            })
            .collect()
    }

    fn prepare(
        records: Records,
        file: File,
        candidate_id: &str,
        source_plan: &FilePin,
        ordinal: u32,
        logical_path: &Path,
        desired: &[u8],
        attribute: &str,
    ) -> Result<Self> {
        let mut batch = RecordBatch::new();
        let pending = Self::stage(
            records,
            file,
            candidate_id,
            source_plan,
            ordinal,
            logical_path,
            desired,
            attribute,
            &mut batch,
        )?;
        Self::seal_preparations(vec![pending], batch)?
            .pop()
            .ok_or_else(|| "sealed label preparation missing".into())
    }

    fn reopen(records: Records, pin: &FilePin, recovery: File) -> Result<Self> {
        let value = Self::load_unclassified(records, pin, recovery)?;
        value.classify(value.restored_intent()?)?;
        Ok(value)
    }
    fn load_unclassified(records: Records, pin: &FilePin, recovery: File) -> Result<Self> {
        ensure(
            pin.path == records.path.join("PREIMAGE.json"),
            "label preimage is outside its journal",
        )?;
        let (intent, intent_identity, bytes) = records.read("PREIMAGE.json")?;
        ensure(
            bytes.len() as u64 == pin.bytes && fs::digest(&bytes) == pin.sha256,
            "label preimage complete bytes differ",
        )?;
        let preimage: Preimage = serde_json::from_slice(&bytes)?;
        ensure(
            preimage.schema == "droidloom.original-label-preimage.v1"
                && fs::valid_digest(&preimage.candidate_id)
                && fs::valid_digest(&preimage.source_plan.sha256)
                && preimage.source_plan.bytes > 0
                && preimage.logical_path.is_absolute()
                && (preimage.attribute == LABEL || cfg!(test))
                && !preimage.desired.is_empty()
                && preimage.desired.len() <= 4096
                && preimage.before.identity.dev == records.identity.dev,
            "label preimage scope differs",
        )?;
        let value = Self {
            records,
            preimage,
            pin: pin.clone(),
            intent,
            intent_identity,
            recovery,
        };
        value.validate_intent()?;
        Ok(value)
    }

    fn validate_intent(&self) -> Result<()> {
        let (named, identity, bytes) = self.records.read("PREIMAGE.json")?;
        ensure(
            identity == self.intent_identity
                && fs::stat(&self.intent)? == identity
                && fs::stat(&named)? == identity
                && bytes.len() as u64 == self.pin.bytes
                && fs::digest(&bytes) == self.pin.sha256,
            "held label preimage was changed or replaced",
        )
    }

    fn restored_intent(&self) -> Result<bool> {
        if !self.records.exists("RESTORE-INTENT.json")? {
            return Ok(false);
        }
        let (_, _, bytes) = self.records.read("RESTORE-INTENT.json")?;
        let actual: Value = serde_json::from_slice(&bytes)?;
        ensure(
            actual
                == json!({"schema":"droidloom.original-label-restore-intent.v1","preimage":self.pin}),
            "label restore intent differs from its immutable preimage",
        )?;
        Ok(true)
    }

    fn classify(&self, restoring: bool) -> Result<(Snapshot, bool)> {
        self.validate_intent()?;
        let current = snapshot(&self.recovery)?;
        let mut expected = self.preimage.before.attributes.clone();
        expected.insert(
            self.preimage.attribute.clone(),
            self.preimage.desired.clone(),
        );
        let applied = current.attributes == expected;
        let original = current.attributes == self.preimage.before.attributes;
        ensure(
            only_ctime_changed(&self.preimage.before.identity, &current.identity)
                && current.handle == self.preimage.before.handle
                && (applied || original),
            "label attempt has an unknown inode or xattr outcome",
        )?;
        if original && !restoring {
            ensure(
                current.identity == self.preimage.before.identity,
                "unapplied label inode changed without a restoration intent",
            )?;
        }
        Ok((current, applied && !original))
    }

    /// An internal provisional result is not an OriginalLabelDerivation. Its
    /// durable PREIMAGE and independent recovery FD already exist; a batch
    /// filesystem barrier and durable APPLIED record are still mandatory.
    fn apply_uncommitted(&self) -> Result<LabelDerivation> {
        self.validate_intent()?;
        ensure(
            !self.restored_intent()? && !self.records.exists("APPLIED.json")?,
            "a completed or recovering label attempt cannot be reapplied",
        )?;
        ensure(
            snapshot(&self.recovery)? == self.preimage.before,
            "label preimage changed before mutation",
        )?;
        match apply_one(
            self.recovery.try_clone()?,
            &self.preimage.before,
            &self.preimage.desired,
            &self.preimage.attribute,
        ) {
            Ok(derivation) => {
                self.validate_intent()?;
                derivation.revalidate()?;
                Ok(derivation)
            }
            Err(error) => {
                let observation = match self.classify(false) {
                    Ok((current, applied)) => {
                        json!({"recognized_current":current,"label_present_after_error":applied})
                    }
                    Err(read_error) => json!({"unresolved_error":read_error.to_string()}),
                };
                let _ = self.records.publish(
                    "UNCERTAIN.json",
                    &json!({
                    "schema":"droidloom.original-label-uncertain.v1","preimage":self.pin,
                    "operation_error":error.to_string(),"observation":observation}),
                );
                Err(error)
            }
        }
    }

    fn application_record(&self, core: &LabelDerivation) -> Result<Option<FilePin>> {
        if !self.records.exists("APPLIED.json")? {
            return Ok(None);
        }
        let (_, _, bytes) = self.records.read("APPLIED.json")?;
        let value: Value = serde_json::from_slice(&bytes)?;
        ensure(
            value["schema"] == "droidloom.original-label-applied.v1"
                && value["preimage"] == serde_json::to_value(&self.pin)?
                && value["before"] == serde_json::to_value(&self.preimage.before)?
                && value["after"] == serde_json::to_value(&core.after)?
                && value["target_metadata_durability"]["operation"] == "syncfs"
                && value["target_metadata_durability"]["filesystem_dev"] == core.after.identity.dev,
            "durable application does not describe this actual inode",
        )?;
        Ok(Some(FilePin {
            path: self.records.path.join("APPLIED.json"),
            bytes: bytes.len() as u64,
            sha256: fs::digest(&bytes),
        }))
    }

    fn readback_uncommitted(&self) -> Result<LabelDerivation> {
        self.validate_intent()?;
        ensure(
            !self.restored_intent()?,
            "a restoring label cannot become an application",
        )?;
        let (current, _) = self.classify(false)?;
        let mut expected = self.preimage.before.attributes.clone();
        expected.insert(
            self.preimage.attribute.clone(),
            self.preimage.desired.clone(),
        );
        ensure(
            current.attributes == expected,
            "readback cannot invent a label that the kernel has not applied",
        )?;
        let core = LabelDerivation {
            file: self.recovery.try_clone()?,
            before: self.preimage.before.clone(),
            after: current,
        };
        core.revalidate()?;
        self.application_record(&core)?;
        Ok(core)
    }

    fn complete_applications(
        attempts: &[&Self],
        cores: &[LabelDerivation],
    ) -> Result<Vec<FilePin>> {
        ensure(
            !attempts.is_empty() && attempts.len() <= BATCH_LIMIT && attempts.len() == cores.len(),
            "bounded complete label application batch required",
        )?;
        let mut outputs = Vec::with_capacity(attempts.len());
        let mut missing = Vec::new();
        for (index, (attempt, core)) in attempts.iter().zip(cores).enumerate() {
            attempt.validate_intent()?;
            ensure(
                !attempt.restored_intent()?
                    && core.before == attempt.preimage.before
                    && snapshot(&attempt.recovery)? == core.after,
                "provisional application lost its durable source or actual recovery inode",
            )?;
            core.revalidate()?;
            let record = attempt.application_record(core)?;
            if record.is_none() {
                missing.push(index);
            }
            outputs.push(record);
        }
        if !missing.is_empty() {
            let targets = missing
                .iter()
                .map(|&i| (&attempts[i].records, &attempts[i].recovery, &cores[i].after))
                .collect::<Vec<_>>();
            let barriers = sync_targets(&targets)?;
            let mut records = RecordBatch::new();
            for (&index, barrier) in missing.iter().zip(barriers) {
                let attempt = attempts[index];
                let core = &cores[index];
                records.stage(
                    &attempt.records,
                    "APPLIED.json",
                    &json!({
                    "schema":"droidloom.original-label-applied.v1","preimage":attempt.pin,
                    "before":core.before,"after":core.after,"target_metadata_durability":barrier}),
                )?;
            }
            for (&index, pin) in missing.iter().zip(records.publish()?) {
                outputs[index] = Some(pin);
            }
        }
        for (attempt, core) in attempts.iter().zip(cores) {
            attempt.validate_intent()?;
            core.revalidate()?;
            ensure(
                snapshot(&attempt.recovery)? == core.after,
                "application changed after batch publication",
            )?;
            attempt
                .application_record(core)?
                .ok_or("completed application record missing")?;
        }
        outputs
            .into_iter()
            .map(|pin| pin.ok_or_else(|| "actual application pin missing".into()))
            .collect()
    }

    fn apply(&self) -> Result<LabelDerivation> {
        let core = self.apply_uncommitted()?;
        Self::complete_applications(&[self], std::slice::from_ref(&core))?;
        Ok(core)
    }
    /// Reconcile a completed or uncertain write without another target write.
    fn applied_readback(&self) -> Result<LabelDerivation> {
        let core = self.readback_uncommitted()?;
        Self::complete_applications(&[self], std::slice::from_ref(&core))?;
        Ok(core)
    }

    fn restore(&self) -> Result<Snapshot> {
        self.validate_intent()?;
        let already = self.restored_intent()?;
        let (observed, applied) = self.classify(already)?;
        if !already {
            self.records.publish(
                "RESTORE-INTENT.json",
                &json!({
                "schema":"droidloom.original-label-restore-intent.v1","preimage":self.pin}),
            )?;
        }
        self.validate_intent()?;
        ensure(
            snapshot(&self.recovery)? == observed,
            "label changed between recovery observation and mutation",
        )?;
        if applied {
            set(
                &self.recovery,
                &self.preimage.attribute,
                self.preimage
                    .before
                    .attributes
                    .get(&self.preimage.attribute)
                    .map(Vec::as_slice),
            )?;
        }
        let (restored, still_applied) = self.classify(true)?;
        ensure(
            !still_applied && restored.attributes == self.preimage.before.attributes,
            "label restoration has not reached its exact preimage",
        )?;
        let durability = self.records.sync_target(&self.recovery, &restored)?;
        if !self.records.exists("RESTORED.json")? {
            self.records.publish(
                "RESTORED.json",
                &json!({
                "schema":"droidloom.original-label-restored.v1","preimage":self.pin,
                "observed_before_restore":observed,"after":restored,"target_metadata_durability":durability}),
            )?;
        } else {
            let (_, _, bytes) = self.records.read("RESTORED.json")?;
            let record: Value = serde_json::from_slice(&bytes)?;
            ensure(
                record["schema"] == "droidloom.original-label-restored.v1"
                    && record["preimage"] == serde_json::to_value(&self.pin)?
                    && record["after"] == serde_json::to_value(&restored)?,
                "restored label result no longer describes the actual inode",
            )?;
        }
        ensure(
            snapshot(&self.recovery)? == restored,
            "restored label changed after durable publication",
        )?;
        Ok(restored)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    const TEST_LABEL: &str = "user.droidloom.journal-test-label";
    fn inode(path: &Path) -> File {
        File::from(
            rustix::fs::open(
                path,
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .unwrap(),
        )
    }
    fn prepare(tmp: &Path) -> DurableAttempt {
        std::fs::create_dir(tmp.join("journal")).unwrap();
        std::fs::set_permissions(tmp.join("journal"), std::fs::Permissions::from_mode(0o700))
            .unwrap();
        std::fs::write(tmp.join("inode"), b"original content").unwrap();
        let plan = FilePin {
            path: tmp.join("source-plan.json"),
            bytes: 7,
            sha256: "a".repeat(64),
        };
        DurableAttempt::prepare(
            Records::open(&tmp.join("journal")).unwrap(),
            inode(&tmp.join("inode")),
            &"b".repeat(64),
            &plan,
            0,
            Path::new("/var/log/owned-test"),
            b"candidate",
            TEST_LABEL,
        )
        .unwrap()
    }
    #[test]
    fn interruption_before_preimage_publication_preserves_partial_evidence() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-unpublished-label-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let dir = tmp.path().join("journal");
        std::fs::create_dir(&dir).unwrap();
        std::fs::set_permissions(&dir, std::fs::Permissions::from_mode(0o700)).unwrap();
        let target = tmp.path().join("inode");
        std::fs::write(&target, b"unchanged original").unwrap();
        let held = inode(&target);
        let before = snapshot(&held).unwrap();
        let pending = dir.join("PREIMAGE.json.pending");
        std::fs::write(&pending, b"interrupted publication").unwrap();
        std::fs::set_permissions(&pending, std::fs::Permissions::from_mode(0o400)).unwrap();
        let records = Records::open(&dir).unwrap();
        records.verify_unpublished_preimage().unwrap();
        let plan = FilePin {
            path: tmp.path().join("source-plan"),
            bytes: 1,
            sha256: "a".repeat(64),
        };
        let actual = DurableAttempt::prepare(
            records,
            held,
            &"b".repeat(64),
            &plan,
            0,
            Path::new("/var/log/owned-test"),
            b"candidate",
            TEST_LABEL,
        )
        .unwrap();
        assert_eq!(actual.preimage.before, before);
        assert_eq!(snapshot(&actual.recovery).unwrap(), before);
        let saved = std::fs::read_dir(&dir)
            .unwrap()
            .filter_map(|row| {
                let row = row.unwrap();
                row.file_name()
                    .to_str()
                    .filter(|name| name.starts_with("PREIMAGE.json.pending.interrupted-"))
                    .map(|_| row.path())
            })
            .collect::<Vec<_>>();
        assert_eq!(saved.len(), 1);
        assert_eq!(
            std::fs::read(&saved[0]).unwrap(),
            b"interrupted publication"
        );
        assert!(actual.records.verify_unpublished_preimage().is_err());
    }
    #[test]
    fn uncertain_application_is_read_back_without_another_target_write() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-label-readback-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let attempt = prepare(tmp.path());
        set(&attempt.recovery, TEST_LABEL, Some(b"candidate")).unwrap();
        let current = snapshot(&attempt.recovery).unwrap();
        let first = attempt.applied_readback().unwrap();
        assert_eq!(first.before, attempt.preimage.before);
        assert_eq!(first.after, current);
        assert_eq!(snapshot(&attempt.recovery).unwrap(), current);
        let again = attempt.applied_readback().unwrap();
        assert_eq!(again.after, current);
        set(&attempt.recovery, "user.unrelated", Some(b"unexpected")).unwrap();
        assert!(attempt.applied_readback().is_err());
    }

    #[test]
    fn durable_preimage_recovers_a_write_with_no_success_record() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-label-test-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let attempt = prepare(tmp.path());
        // Exactly the uncertain boundary: the kernel write succeeded but no
        // derivation/APPLIED record was returned or published.
        set(&attempt.recovery, TEST_LABEL, Some(b"candidate")).unwrap();
        assert!(!attempt.records.exists("APPLIED.json").unwrap());
        let pin = attempt.pin.clone();
        drop(attempt);
        let reopened = DurableAttempt::reopen(
            Records::open(&tmp.path().join("journal")).unwrap(),
            &pin,
            inode(&tmp.path().join("inode")),
        )
        .unwrap();
        assert!(reopened.classify(false).unwrap().1);
        let restored = reopened.restore().unwrap();
        assert_eq!(restored.attributes, reopened.preimage.before.attributes);
        assert_eq!(
            std::fs::read(tmp.path().join("inode")).unwrap(),
            b"original content"
        );
    }
    #[test]
    fn successful_apply_and_interrupted_restore_are_reopened_from_actual_xattrs() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-label-test-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let attempt = prepare(tmp.path());
        attempt.apply().unwrap();
        attempt
            .records
            .publish(
                "RESTORE-INTENT.json",
                &json!({
            "schema":"droidloom.original-label-restore-intent.v1","preimage":attempt.pin}),
            )
            .unwrap();
        set(&attempt.recovery, TEST_LABEL, None).unwrap();
        let pin = attempt.pin.clone();
        drop(attempt);
        let reopened = DurableAttempt::reopen(
            Records::open(&tmp.path().join("journal")).unwrap(),
            &pin,
            inode(&tmp.path().join("inode")),
        );
        // Reopen must honor the durable restoration intent, not infer an
        // unexplained ctime change from the absence of the new label.
        let reopened = reopened.unwrap();
        reopened.restore().unwrap();
    }
    #[test]
    fn error_after_kernel_write_keeps_preimage_and_recovery_descriptor() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-label-test-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let attempt = prepare(tmp.path());
        // Publication is forced to fail after apply_one has successfully
        // changed the inode. No caller receives its LabelDerivation.
        std::fs::create_dir(tmp.path().join("journal/APPLIED.json.pending")).unwrap();
        assert!(attempt.apply().is_err());
        assert!(attempt.classify(false).unwrap().1);
        attempt.restore().unwrap();
        assert_eq!(
            snapshot(&attempt.recovery).unwrap().attributes,
            attempt.preimage.before.attributes
        );
    }
    #[test]
    fn partial_restore_receipt_is_preserved_before_recovery_continues() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-label-test-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let attempt = prepare(tmp.path());
        attempt.apply().unwrap();
        let pending = tmp.path().join("journal/RESTORED.json.pending");
        std::fs::write(&pending, b"{truncated").unwrap();
        std::fs::set_permissions(&pending, std::fs::Permissions::from_mode(0o400)).unwrap();
        attempt.restore().unwrap();
        let names = std::fs::read_dir(tmp.path().join("journal"))
            .unwrap()
            .map(|e| e.unwrap().file_name().to_string_lossy().into_owned())
            .collect::<Vec<_>>();
        assert!(
            names
                .iter()
                .any(|n| n.starts_with("RESTORED.json.pending.interrupted-"))
        );
        assert!(!pending.exists());
    }
    #[test]
    fn replaced_evidence_or_target_and_unrelated_changes_never_restore() {
        for which in 0..3 {
            let tmp = tempfile::Builder::new()
                .prefix(".p4-label-test-")
                .tempdir_in(std::env::current_dir().unwrap())
                .unwrap();
            let attempt = prepare(tmp.path());
            attempt.apply().unwrap();
            match which {
                0 => {
                    let p = tmp.path().join("journal/PREIMAGE.json");
                    let b = std::fs::read(&p).unwrap();
                    std::fs::rename(&p, tmp.path().join("old-proof")).unwrap();
                    std::fs::write(&p, b).unwrap();
                    std::fs::set_permissions(p, std::fs::Permissions::from_mode(0o400)).unwrap();
                    assert!(attempt.restore().is_err());
                }
                1 => {
                    set(
                        &attempt.recovery,
                        "user.droidloom.unrelated",
                        Some(b"foreign change"),
                    )
                    .unwrap();
                    assert!(attempt.restore().is_err());
                }
                _ => {
                    std::fs::rename(tmp.path().join("inode"), tmp.path().join("old-inode"))
                        .unwrap();
                    std::fs::write(tmp.path().join("inode"), b"original content").unwrap();
                    assert!(
                        DurableAttempt::reopen(
                            Records::open(&tmp.path().join("journal")).unwrap(),
                            &attempt.pin,
                            inode(&tmp.path().join("inode"))
                        )
                        .is_err()
                    );
                }
            }
        }
    }
}

#[cfg(test)]
#[path = "cold_original_label_scale_tests.rs"]
mod scale_tests;
#[cfg(test)]
#[path = "cold_original_label_batch_scale_tests.rs"]
mod batch_scale_tests;
