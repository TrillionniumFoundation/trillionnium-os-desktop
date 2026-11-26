//! Durable recovery of a single inode label attempt, including uncertain
//! syscall outcomes. This internal core is not a physical installation API.
//! The source-bound plan and live once adapter own its only production caller.
use super::{LABEL, LabelDerivation, Snapshot, apply_one, only_ctime_changed, set, snapshot};
use crate::{Result, boot_files::FilePin, ensure, fs, model::Identity};
use rustix::fs::{AtFlags, FileType, Mode, OFlags, RenameFlags};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs::File,
    io::Write,
    os::unix::fs::FileExt,
    path::{Path, PathBuf},
};

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
        let tree = fs::Tree::open(&fs::absolute_string(&self.path)?, self.identity.uid)?;
        for actual in [fs::stat(&tree.root)?, fs::stat(&self.held)?] {
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
impl DurableAttempt {
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
        let pin = records.publish("PREIMAGE.json", &preimage)?;
        let (intent, intent_identity, _) = records.read("PREIMAGE.json")?;
        let result = Self {
            records,
            preimage,
            pin,
            intent,
            intent_identity,
            recovery: file,
        };
        result.validate_intent()?;
        ensure(
            snapshot(&result.recovery)? == result.preimage.before,
            "label inode changed before its durable intent",
        )?;
        Ok(result)
    }

    fn reopen(records: Records, pin: &FilePin, recovery: File) -> Result<Self> {
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
        value.classify(value.restored_intent()?)?;
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

    fn apply(&self) -> Result<LabelDerivation> {
        self.validate_intent()?;
        ensure(
            !self.restored_intent()? && !self.records.exists("APPLIED.json")?,
            "a completed or recovering label attempt cannot be reapplied",
        )?;
        ensure(
            snapshot(&self.recovery)? == self.preimage.before,
            "label preimage changed before mutation",
        )?;
        // recovery remains open even if the following call changes the xattr
        // and then fails during proc custody or complete snapshot validation.
        let result = apply_one(
            self.recovery.try_clone()?,
            &self.preimage.before,
            &self.preimage.desired,
            &self.preimage.attribute,
        );
        match result {
            Ok(derivation) => {
                self.validate_intent()?;
                derivation.revalidate()?;
                self.records.publish(
                    "APPLIED.json",
                    &json!({
                    "schema":"droidloom.original-label-applied.v1","preimage":self.pin,
                    "before":derivation.before,"after":derivation.after}),
                )?;
                derivation.revalidate()?;
                Ok(derivation)
            }
            Err(error) => {
                // An observation is diagnostic only. Even failure to publish
                // it leaves the fsynced preimage and recovery FD intact.
                let actual = self.classify(false);
                let observation = match actual {
                    Ok((current, applied)) => json!({"recognized_current":current,
                        "label_present_after_error":applied}),
                    Err(ref read_error) => json!({"unresolved_error":read_error.to_string()}),
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
        if !self.records.exists("RESTORED.json")? {
            self.records.publish(
                "RESTORED.json",
                &json!({
                "schema":"droidloom.original-label-restored.v1","preimage":self.pin,
                "observed_before_restore":observed,"after":restored}),
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
