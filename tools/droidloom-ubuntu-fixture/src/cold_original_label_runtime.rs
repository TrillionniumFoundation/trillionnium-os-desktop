//! A fresh, durable restoration preimage after actual runtime retirement.
//! This private core grants no retirement authority; the only product caller
//! must hold the once owner's opaque OriginalRetirement at every write fence.
use super::*;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(super) enum RuntimeClass {
    Log,
    Cache,
    Temporary,
    UserHome,
    ServiceHome,
    OnceEvidence,
    SystemdState,
    RandomSeed,
}
fn below(path: &str, prefix: &str) -> bool {
    path == prefix
        || path
            .strip_prefix(prefix)
            .is_some_and(|v| v.starts_with('/'))
}
pub(super) fn runtime_class(path: &Path, candidate: &str) -> Option<RuntimeClass> {
    if path == Path::new("/var/lib/systemd/random-seed") {
        return Some(RuntimeClass::RandomSeed);
    }
    if super::super::service_state::state_path(path) {
        return Some(RuntimeClass::SystemdState);
    }
    let path = path.to_str()?;
    if below(path, "/home/alex/work")
        || below(path, "/var/lib/droidloom-qualification")
        || below(path, "/var/lib/droidloom/users/1000/data")
    {
        return None;
    }
    for (prefix, class) in [
        ("/var/log", RuntimeClass::Log),
        ("/var/cache", RuntimeClass::Cache),
        ("/var/tmp", RuntimeClass::Temporary),
        ("/home/alex", RuntimeClass::UserHome),
    ] {
        if below(path, prefix) {
            return Some(class);
        }
    }
    // Exact original service homes, read from the preserved original passwd.
    // Package state, source archives and arbitrary /var/lib prefixes are not
    // mutable by implication. Unknown paths keep the strict applied snapshot.
    for prefix in [
        "/var/spool/lpd",
        "/var/spool/news",
        "/var/spool/uucp",
        "/var/lib/usbmux",
        "/var/lib/tpm",
        "/var/lib/misc",
        "/var/lib/sss",
        "/var/lib/fwupd",
        "/var/lib/saned",
        "/var/lib/geoclue",
        "/var/lib/gnome-remote-desktop",
        "/var/lib/colord",
        "/var/lib/gdm3",
        "/var/lib/openvpn/chroot",
        "/var/lib/hepta-runtime",
    ] {
        if below(path, prefix) {
            return Some(RuntimeClass::ServiceHome);
        }
    }
    if fs::valid_digest(candidate)
        && below(
            path,
            &format!("/var/lib/droidloom/qualification/original-once-{candidate}/runtime-evidence"),
        )
    {
        return Some(RuntimeClass::OnceEvidence);
    }
    None
}
pub(super) fn admit_current(
    applied: &Snapshot,
    current: &Snapshot,
    class: Option<RuntimeClass>,
) -> Result<()> {
    let mut original_attributes = applied.attributes.clone();
    let mut current_attributes = current.attributes.clone();
    if class == Some(RuntimeClass::RandomSeed) {
        let name = super::super::service_state::CREDITABLE;
        for attrs in [&original_attributes, &current_attributes] {
            ensure(
                attrs.get(name).is_none_or(|value| value == b"1"),
                "normal random-seed creditable state is not absent or exactly one byte 1",
            )?;
        }
        original_attributes.remove(name);
        current_attributes.remove(name);
        ensure(
            FileType::from_raw_mode(current.identity.mode) == FileType::RegularFile
                && current.identity.mode & 0o7777 == 0o600
                && current.identity.uid == 0
                && current.identity.gid == 0,
            "normal random-seed state lost its exact root-only authority",
        )?;
    }
    ensure(
        applied.handle == current.handle && original_attributes == current_attributes,
        "post-runtime label or an unrelated xattr no longer matches the actual applied inode",
    )?;
    // A source-defined mutable directory can contain unchanged symlinks (for
    // example /var/log/README). Full equality already proves the strict
    // applied generation, F9 and every attribute; it needs no mutable inode
    // contract. Changed symlinks and special objects still fail below.
    if applied == current {
        return Ok(());
    }
    if class.is_none() {
        return ensure(
            applied == current,
            "immutable label source changed during runtime",
        );
    }
    let a = &applied.identity;
    let b = &current.identity;
    ensure(
        (a.dev, a.ino, a.mode, a.uid, a.gid) == (b.dev, b.ino, b.mode, b.uid, b.gid)
            && if FileType::from_raw_mode(a.mode) == FileType::Directory {
                b.nlink >= 2
            } else {
                a.nlink == b.nlink
            },
        "mutable runtime inode lost its identity, type, authority or hardlink contract",
    )?;
    ensure(
        matches!(
            FileType::from_raw_mode(a.mode),
            FileType::RegularFile | FileType::Directory
        ),
        "only existing normal files and directories have a mutable runtime metadata contract",
    )
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(super) enum EvolutionKind {
    WorkingBacking,
    GrubEnvironment,
    PairRename,
    SelectionRename,
}
/// Private data, never mutation authority. The full restore adapter obtains
/// these exact observations from the real retirement and completed rename
/// objects before constructing the current preimage.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct ExactEvolution {
    pub(super) kind: EvolutionKind,
    pub(super) actual: Snapshot,
    pub(super) evidence: FilePin,
}
impl ExactEvolution {
    fn validate(
        &self,
        original: &DurableAttempt,
        applied: &Snapshot,
        current: &Snapshot,
        retirement: &FilePin,
    ) -> Result<()> {
        let path = &original.preimage.logical_path;
        let allowed = match self.kind {
            EvolutionKind::WorkingBacking => [
                "/var/lib/droidloom/users/1000/data/data.img",
                "/var/lib/droidloom/users/1000/data/metadata.img",
            ]
            .contains(&path.to_str().unwrap_or("")),
            EvolutionKind::GrubEnvironment => path == Path::new("/boot/grub/grubenv"),
            EvolutionKind::PairRename => [
                "/var/lib/droidloom/users/1000",
                "/var/lib/droidloom/users/1000/data",
            ]
            .contains(&path.to_str().unwrap_or("")),
            EvolutionKind::SelectionRename => [
                "/etc/droidloom/production",
                "/etc/droidloom/production/selected.json",
            ]
            .contains(&path.to_str().unwrap_or("")),
        };
        ensure(
            allowed
                && self.actual == *current
                && applied.handle == current.handle
                && applied.attributes == current.attributes,
            "owned runtime evolution is outside its fixed inode or changed another attribute",
        )?;
        let a = &applied.identity;
        let b = &current.identity;
        ensure(
            (a.dev, a.ino, a.mode, a.uid, a.gid, a.nlink)
                == (b.dev, b.ino, b.mode, b.uid, b.gid, b.nlink),
            "owned runtime evolution changed inode authority or links",
        )?;
        if matches!(
            self.kind,
            EvolutionKind::WorkingBacking | EvolutionKind::GrubEnvironment
        ) {
            ensure(
                a.size == b.size && FileType::from_raw_mode(b.mode) == FileType::RegularFile,
                "bounded working backing or GRUB environment size/type changed",
            )?;
        }
        let value: Value = serde_json::from_slice(&super::super::super::root_pin(
            &self.evidence,
            32 * 1024 * 1024,
        )?)?;
        match self.kind {
            EvolutionKind::WorkingBacking | EvolutionKind::GrubEnvironment => {
                ensure(
                    self.evidence.path == retirement.path
                        && self.evidence.sha256 == retirement.sha256
                        && self.evidence.bytes == retirement.bytes
                        && value["schema"] == "droidloom.original-once-retirement.v1"
                        && value["candidate_id"] == original.preimage.candidate_id,
                    "owned runtime state is not this actual sealed retirement",
                )?;
                if self.kind == EvolutionKind::GrubEnvironment {
                    ensure(
                        value["grubenv_identity"] == serde_json::to_value(&current.identity)?,
                        "GRUB state differs from its actual retirement readback",
                    )?;
                } else {
                    let sync = &value["working_data"]["actual_synchronization"];
                    let rows = sync["backings"]
                        .as_array()
                        .ok_or("actual retired backing snapshots missing")?;
                    ensure(
                        sync["schema"] == "droidloom.working-pair-recovery-fsync.v1"
                            && rows.len() == 2
                            && rows
                                .iter()
                                .filter(|row| {
                                    row["before"] == row["after"]
                                        && row["after"]
                                            == serde_json::to_value(&current.identity)
                                                .unwrap_or(Value::Null)
                                })
                                .count()
                                == 1,
                        "working current preimage differs from the actual two-fd fsync readback",
                    )?;
                }
            }
            EvolutionKind::PairRename => ensure(
                value["schema"] == "droidloom.original-pair-restoration-result.v1"
                    && if path == Path::new("/var/lib/droidloom/users/1000") {
                        value["parent"]["snapshot"] == serde_json::to_value(current)?
                    } else {
                        value["working"] == serde_json::to_value(current)?
                    },
                "pair directory lacks its exact completed rename readback",
            )?,
            EvolutionKind::SelectionRename => ensure(
                value["schema"] == "droidloom.original-selection-label-result.v1"
                    && if path == Path::new("/etc/droidloom/production") {
                        value["parent"]["snapshot"] == serde_json::to_value(current)?
                    } else {
                        value["candidate"] == serde_json::to_value(current)?
                    },
                "selection directory/inode lacks its exact completed withdrawal readback",
            )?,
        }
        Ok(())
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct CurrentPreimage {
    schema: String,
    original_preimage: FilePin,
    applied: FilePin,
    retirement: FilePin,
    class: Option<RuntimeClass>,
    evolution: Option<ExactEvolution>,
    current: Snapshot,
}

/// The fresh current snapshot is immutable once the first restoration write
/// may occur. Continued writes require another genuine retirement, not ignored
/// clocks or a rewritten original copy/preimage receipt.
pub(in crate::cold_original_data::labels) struct RuntimeRestoreAttempt {
    original: DurableAttempt,
    records: Records,
    current: CurrentPreimage,
    pin: FilePin,
    intent: File,
    intent_identity: Identity,
}
pub(super) struct PendingRuntimeAttempt {
    original: DurableAttempt,
    records: Records,
    current: CurrentPreimage,
}
pub(super) struct ProvisionalRestoration {
    pub(super) core: LabelDerivation,
    observed: Snapshot,
}
impl RuntimeRestoreAttempt {
    pub(super) fn applied(original: &DurableAttempt) -> Result<(FilePin, Snapshot)> {
        original.validate_intent()?;
        let (_, _, bytes) = original.records.read("APPLIED.json")?;
        let value: Value = serde_json::from_slice(&bytes)?;
        let after: Snapshot = serde_json::from_value(value["after"].clone())?;
        let mut expected = original.preimage.before.attributes.clone();
        expected.insert(
            original.preimage.attribute.clone(),
            original.preimage.desired.clone(),
        );
        ensure(
            value["schema"] == "droidloom.original-label-applied.v1"
                && value["preimage"] == serde_json::to_value(&original.pin)?
                && value["before"] == serde_json::to_value(&original.preimage.before)?
                && only_ctime_changed(&original.preimage.before.identity, &after.identity)
                && after.handle == original.preimage.before.handle
                && after.attributes == expected
                && value["target_metadata_durability"]["operation"] == "syncfs"
                && value["target_metadata_durability"]["filesystem_dev"] == after.identity.dev,
            "runtime restoration lacks its actual source-bound durable label application",
        )?;
        Ok((
            FilePin {
                path: original.records.path.join("APPLIED.json"),
                bytes: bytes.len() as u64,
                sha256: fs::digest(&bytes),
            },
            after,
        ))
    }
    pub(in crate::cold_original_data::labels) fn prepare(
        original: DurableAttempt,
        records: Records,
        retirement: &FilePin,
    ) -> Result<Self> {
        Self::prepare_exact(original, records, retirement, None)
    }
    pub(in crate::cold_original_data::labels) fn stage_exact(
        original: DurableAttempt,
        records: Records,
        retirement: &FilePin,
        evolution: Option<ExactEvolution>,
        batch: &mut RecordBatch,
    ) -> Result<PendingRuntimeAttempt> {
        ensure(
            fs::valid_digest(&retirement.sha256) && retirement.bytes > 0,
            "actual enclosing retirement evidence pin required",
        )?;
        let (applied, after) = Self::applied(&original)?;
        let current = snapshot(&original.recovery)?;
        let class = runtime_class(
            &original.preimage.logical_path,
            &original.preimage.candidate_id,
        );
        if let Some(exact) = &evolution {
            exact.validate(&original, &after, &current, retirement)?;
        } else {
            admit_current(&after, &current, class)?;
        }
        ensure(
            current.identity.dev == records.identity.dev,
            "runtime restore preimage requires same-filesystem durability",
        )?;
        let current = CurrentPreimage {
            schema: "droidloom.current-label-restore-preimage.v1".into(),
            original_preimage: original.pin.clone(),
            applied,
            retirement: retirement.clone(),
            class,
            evolution,
            current,
        };
        batch.stage(&records, "CURRENT-PREIMAGE.json", &current)?;
        ensure(
            snapshot(&original.recovery)? == current.current,
            "runtime inode changed while its current preimage was staged",
        )?;
        Ok(PendingRuntimeAttempt {
            original,
            records,
            current,
        })
    }
    pub(super) fn seal_preparations(
        pending: Vec<PendingRuntimeAttempt>,
        batch: RecordBatch,
    ) -> Result<Vec<Self>> {
        let pins = batch.publish()?;
        ensure(
            !pending.is_empty() && pending.len() == pins.len(),
            "runtime restoration preparation batch membership differs",
        )?;
        pending
            .into_iter()
            .zip(pins)
            .map(|(draft, pin)| {
                ensure(
                    pin.path == draft.records.path.join("CURRENT-PREIMAGE.json"),
                    "current batch preimage pin names another runtime target",
                )?;
                let (intent, intent_identity, _) = draft.records.read("CURRENT-PREIMAGE.json")?;
                let value = Self {
                    original: draft.original,
                    records: draft.records,
                    current: draft.current,
                    pin,
                    intent,
                    intent_identity,
                };
                value.validate()?;
                ensure(
                    snapshot(&value.original.recovery)? == value.current.current,
                    "runtime target changed across its durable batch current preimage",
                )?;
                Ok(value)
            })
            .collect()
    }
    pub(in crate::cold_original_data::labels) fn prepare_exact(
        original: DurableAttempt,
        records: Records,
        retirement: &FilePin,
        evolution: Option<ExactEvolution>,
    ) -> Result<Self> {
        let mut batch = RecordBatch::new();
        let pending = Self::stage_exact(original, records, retirement, evolution, &mut batch)?;
        Self::seal_preparations(vec![pending], batch)?
            .pop()
            .ok_or_else(|| "sealed runtime preparation missing".into())
    }
    pub(in crate::cold_original_data::labels) fn reopen(
        original: DurableAttempt,
        records: Records,
        pin: &FilePin,
    ) -> Result<Self> {
        let value = Self::open_evidence(original, records, pin)?;
        value.classify()?;
        Ok(value)
    }
    pub(super) fn open_evidence(
        original: DurableAttempt,
        records: Records,
        pin: &FilePin,
    ) -> Result<Self> {
        let (intent, intent_identity, bytes) = records.read("CURRENT-PREIMAGE.json")?;
        ensure(
            pin.path == records.path.join("CURRENT-PREIMAGE.json")
                && pin.bytes == bytes.len() as u64
                && pin.sha256 == fs::digest(&bytes),
            "complete current restoration preimage differs",
        )?;
        let current: CurrentPreimage = serde_json::from_slice(&bytes)?;
        let value = Self {
            original,
            records,
            current,
            pin: pin.clone(),
            intent,
            intent_identity,
        };
        value.validate()?;
        Ok(value)
    }
    fn validate(&self) -> Result<()> {
        self.original.validate_intent()?;
        let (_, identity, bytes) = self.records.read("CURRENT-PREIMAGE.json")?;
        let (applied, after) = Self::applied(&self.original)?;
        ensure(
            identity == self.intent_identity
                && fs::stat(&self.intent)? == identity
                && bytes.len() as u64 == self.pin.bytes
                && fs::digest(&bytes) == self.pin.sha256
                && self.current.schema == "droidloom.current-label-restore-preimage.v1"
                && serde_json::to_value(&self.current.original_preimage)?
                    == serde_json::to_value(&self.original.pin)?
                && serde_json::to_value(&self.current.applied)? == serde_json::to_value(&applied)?
                && self.current.class
                    == runtime_class(
                        &self.original.preimage.logical_path,
                        &self.original.preimage.candidate_id,
                    ),
            "held current restoration evidence or its fixed source class changed",
        )?;
        if let Some(exact) = &self.current.evolution {
            exact.validate(
                &self.original,
                &after,
                &self.current.current,
                &self.current.retirement,
            )
        } else {
            admit_current(&after, &self.current.current, self.current.class)
        }
    }
    pub(super) fn classify(&self) -> Result<(Snapshot, bool)> {
        self.validate()?;
        let actual = snapshot(&self.original.recovery)?;
        let mut restored = self.current.current.attributes.clone();
        match self
            .original
            .preimage
            .before
            .attributes
            .get(&self.original.preimage.attribute)
        {
            Some(old) => {
                restored.insert(self.original.preimage.attribute.clone(), old.clone());
            }
            None => {
                restored.remove(&self.original.preimage.attribute);
            }
        }
        let done = actual.attributes == restored;
        ensure(
            only_ctime_changed(&self.current.current.identity, &actual.identity)
                && actual.handle == self.current.current.handle
                && (done || actual.attributes == self.current.current.attributes),
            "runtime restore has an unknown target or concurrent metadata/xattr outcome",
        )?;
        Ok((actual, done))
    }
    pub(super) fn preimage_pin(&self) -> &FilePin {
        &self.pin
    }
    pub(super) fn original_pin(&self) -> &FilePin {
        &self.original.pin
    }
    pub(super) fn current_snapshot(&self) -> &Snapshot {
        &self.current.current
    }
    pub(super) fn ordinal(&self) -> u32 {
        self.original.preimage.ordinal
    }
    pub(super) fn has_completed_result(&self) -> Result<bool> {
        self.records.exists("RESTORED.json")
    }
    pub(super) fn historical_restored_snapshot(&self) -> Result<Snapshot> {
        self.validate()?;
        let mut expected = self.current.current.clone();
        match self
            .original
            .preimage
            .before
            .attributes
            .get(&self.original.preimage.attribute)
        {
            Some(old) => {
                expected
                    .attributes
                    .insert(self.original.preimage.attribute.clone(), old.clone());
            }
            None => {
                expected
                    .attributes
                    .remove(&self.original.preimage.attribute);
            }
        }
        if self.records.exists("RESTORED.json")? {
            let (_, _, body) = self.records.read("RESTORED.json")?;
            let actual: Value = serde_json::from_slice(&body)?;
            let after: Snapshot = serde_json::from_value(actual["after"].clone())?;
            ensure(
                actual["schema"] == "droidloom.current-label-restored.v1"
                    && actual["current_preimage"] == serde_json::to_value(&self.pin)?
                    && actual["original_preimage"] == serde_json::to_value(&self.original.pin)?
                    && actual["before"] == serde_json::to_value(&self.current.current)?
                    && after.handle == expected.handle
                    && after.attributes == expected.attributes
                    && only_ctime_changed(&expected.identity, &after.identity)
                    && actual["target_metadata_durability"]["operation"] == "syncfs"
                    && actual["target_metadata_durability"]["filesystem_dev"] == after.identity.dev,
                "historical restored inode lacks its exact current preimage and actual metadata barrier",
            )?;
            return Ok(after);
        }
        Ok(expected)
    }
    pub(super) fn restore_uncommitted(&self) -> Result<ProvisionalRestoration> {
        let (observed, done) = self.classify()?;
        if !done {
            set(
                &self.original.recovery,
                &self.original.preimage.attribute,
                self.original
                    .preimage
                    .before
                    .attributes
                    .get(&self.original.preimage.attribute)
                    .map(Vec::as_slice),
            )?;
        }
        let (after, done) = self.classify()?;
        ensure(
            done,
            "runtime label restoration did not reach the exact original label",
        )?;
        let core = LabelDerivation {
            file: self.original.recovery.try_clone()?,
            before: self.current.current.clone(),
            after,
        };
        core.revalidate()?;
        Ok(ProvisionalRestoration { core, observed })
    }
    fn restoration_record(&self, provisional: &ProvisionalRestoration) -> Result<Option<FilePin>> {
        if !self.records.exists("RESTORED.json")? {
            return Ok(None);
        }
        let (_, _, bytes) = self.records.read("RESTORED.json")?;
        let record: Value = serde_json::from_slice(&bytes)?;
        ensure(
            record["schema"] == "droidloom.current-label-restored.v1"
                && record["current_preimage"] == serde_json::to_value(&self.pin)?
                && record["original_preimage"] == serde_json::to_value(&self.original.pin)?
                && record["retirement"] == serde_json::to_value(&self.current.retirement)?
                && record["before"] == serde_json::to_value(&self.current.current)?
                && record["after"] == serde_json::to_value(&provisional.core.after)?
                && record["target_metadata_durability"]["operation"] == "syncfs"
                && record["target_metadata_durability"]["filesystem_dev"]
                    == provisional.core.after.identity.dev,
            "existing runtime restoration result differs from the actual source/current inode",
        )?;
        Ok(Some(FilePin {
            path: self.records.path.join("RESTORED.json"),
            bytes: bytes.len() as u64,
            sha256: fs::digest(&bytes),
        }))
    }
    pub(super) fn complete_restorations(
        attempts: &[&Self],
        provisional: &[ProvisionalRestoration],
    ) -> Result<Vec<FilePin>> {
        ensure(
            !attempts.is_empty()
                && attempts.len() <= BATCH_LIMIT
                && attempts.len() == provisional.len(),
            "bounded complete runtime restoration batch required",
        )?;
        let mut outputs = Vec::with_capacity(attempts.len());
        let mut missing = Vec::new();
        for (index, (attempt, provisional)) in attempts.iter().zip(provisional).enumerate() {
            attempt.validate()?;
            let (current, done) = attempt.classify()?;
            ensure(
                done && current == provisional.core.after
                    && provisional.core.before == attempt.current.current,
                "provisional restoration no longer names the actual current preimage outcome",
            )?;
            provisional.core.revalidate()?;
            let result = attempt.restoration_record(provisional)?;
            if result.is_none() {
                missing.push(index);
            }
            outputs.push(result);
        }
        if !missing.is_empty() {
            let targets = missing
                .iter()
                .map(|&i| {
                    (
                        &attempts[i].records,
                        &attempts[i].original.recovery,
                        &provisional[i].core.after,
                    )
                })
                .collect::<Vec<_>>();
            let barriers = sync_targets(&targets)?;
            let mut records = RecordBatch::new();
            for (&index, barrier) in missing.iter().zip(barriers) {
                let attempt = attempts[index];
                let result = &provisional[index];
                records.stage(&attempt.records,"RESTORED.json",&json!({
                    "schema":"droidloom.current-label-restored.v1","current_preimage":attempt.pin,
                    "original_preimage":attempt.original.pin,"retirement":attempt.current.retirement,
                    "before":attempt.current.current,"observed_before_retry":result.observed,
                    "after":result.core.after,"target_metadata_durability":barrier,
                    "original_content_claimed_unchanged":attempt.current.class.is_none() && attempt.current.evolution.is_none()}))?;
            }
            for (&index, pin) in missing.iter().zip(records.publish()?) {
                outputs[index] = Some(pin);
            }
        }
        for (attempt, result) in attempts.iter().zip(provisional) {
            attempt.validate()?;
            result.core.revalidate()?;
            let (current, done) = attempt.classify()?;
            ensure(
                done && current == result.core.after,
                "runtime target changed after batch restoration publication",
            )?;
            attempt
                .restoration_record(result)?
                .ok_or("complete runtime restoration record missing")?;
        }
        outputs
            .into_iter()
            .map(|pin| pin.ok_or_else(|| "actual runtime restoration pin missing".into()))
            .collect()
    }
    pub(in crate::cold_original_data::labels) fn restore(
        &self,
    ) -> Result<(LabelDerivation, FilePin)> {
        let provisional = self.restore_uncommitted()?;
        let pin = Self::complete_restorations(&[self], std::slice::from_ref(&provisional))?
            .pop()
            .ok_or("completed runtime restoration missing")?;
        Ok((provisional.core, pin))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    #[test]
    fn an_actual_unchanged_log_symlink_is_exact_but_changed_or_replaced_symlinks_are_not_mutable() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-exact-log-symlink-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let target = tmp.path().join("target");
        let link = tmp.path().join("inode");
        std::fs::write(&target, b"unmodified link target").unwrap();
        std::os::unix::fs::symlink("target", &link).unwrap();
        let held = File::from(
            rustix::fs::open(
                &link,
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .unwrap(),
        );
        let target_held = File::open(&target).unwrap();
        let target_before = snapshot(&target_held).unwrap();
        let before = snapshot(&held).unwrap();
        assert_eq!(
            FileType::from_raw_mode(before.identity.mode),
            FileType::Symlink
        );
        let class = runtime_class(Path::new("/var/log/README"), &"b".repeat(64));
        assert_eq!(class, Some(RuntimeClass::Log));
        admit_current(&before, &snapshot(&held).unwrap(), class).unwrap();
        // The existing specialized seed authority is not bypassed by the
        // equality branch; it still requires its normal root-only file.
        assert!(admit_current(&before, &before, Some(RuntimeClass::RandomSeed)).is_err());

        let mut times = rustix::fs::Timestamps {
            last_access: Default::default(),
            last_modification: Default::default(),
        };
        times.last_access.tv_sec = before.identity.mtime_sec as _;
        times.last_access.tv_nsec = before.identity.mtime_nsec as _;
        times.last_modification.tv_sec = (before.identity.mtime_sec + 1) as _;
        times.last_modification.tv_nsec = before.identity.mtime_nsec as _;
        rustix::fs::utimensat(
            &File::open(tmp.path()).unwrap(),
            "inode",
            &times,
            rustix::fs::AtFlags::SYMLINK_NOFOLLOW,
        )
        .unwrap();
        let changed = snapshot(&held).unwrap();
        assert_eq!(before.handle, changed.handle);
        assert_ne!(before.identity, changed.identity);
        assert!(admit_current(&before, &changed, class).is_err());
        assert_eq!(target_before, snapshot(&target_held).unwrap());

        std::fs::rename(&link, tmp.path().join("retained-alias")).unwrap();
        std::os::unix::fs::symlink("target", &link).unwrap();
        let replaced = File::from(
            rustix::fs::open(
                &link,
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .unwrap(),
        );
        assert!(admit_current(&before, &snapshot(&replaced).unwrap(), class).is_err());
        assert_eq!(std::fs::read(&target).unwrap(), b"unmodified link target");
    }
    #[test]
    #[ignore = "root-only isolated security.selinux symlink apply/current/restore; no physical authority"]
    fn an_actual_log_symlink_completes_durable_current_preimage_and_label_restore() {
        assert!(rustix::process::geteuid().is_root());
        let tmp = tempfile::Builder::new()
            .prefix(".p4-exact-selinux-symlink-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        for name in ["apply", "restore"] {
            std::fs::create_dir(tmp.path().join(name)).unwrap();
            std::fs::set_permissions(
                tmp.path().join(name),
                std::fs::Permissions::from_mode(0o700),
            )
            .unwrap();
        }
        let target = tmp.path().join("target");
        std::fs::write(&target, b"target must retain its metadata and bytes").unwrap();
        std::os::unix::fs::symlink("target", tmp.path().join("inode")).unwrap();
        let held = File::from(
            rustix::fs::open(
                tmp.path().join("inode"),
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .unwrap(),
        );
        let target_held = File::open(&target).unwrap();
        let target_before = snapshot(&target_held).unwrap();
        let before = snapshot(&held).unwrap();
        crate::boot_files::write_new(
            &tmp.path().join("source-plan"),
            b"isolated core test source\n",
            0o400,
        )
        .unwrap();
        crate::boot_files::write_new(
            &tmp.path().join("retirement"),
            b"isolated test only; no OriginalRetirement constructed\n",
            0o400,
        )
        .unwrap();
        let source = crate::boot_files::pin_file(&tmp.path().join("source-plan")).unwrap();
        let retirement = crate::boot_files::pin_file(&tmp.path().join("retirement")).unwrap();
        let original = DurableAttempt::prepare(
            Records::open(&tmp.path().join("apply")).unwrap(),
            held,
            &"b".repeat(64),
            &source,
            0,
            Path::new("/var/log/README"),
            b"u:object_r:p4_linux_native_config_t:s0",
            "security.selinux",
        )
        .unwrap();
        original.apply().unwrap();
        let runtime = RuntimeRestoreAttempt::prepare(
            original,
            Records::open(&tmp.path().join("restore")).unwrap(),
            &retirement,
        )
        .unwrap();
        let (restored, _) = runtime.restore().unwrap();
        assert!(runtime.has_completed_result().unwrap());
        assert_eq!(restored.after.handle, before.handle);
        assert_eq!(restored.after.attributes, before.attributes);
        assert!(only_ctime_changed(
            &before.identity,
            &restored.after.identity
        ));
        assert_eq!(snapshot(&target_held).unwrap(), target_before);
        assert_eq!(
            std::fs::read(&target).unwrap(),
            b"target must retain its metadata and bytes"
        );
        assert_eq!(
            std::fs::read_link(tmp.path().join("inode")).unwrap(),
            Path::new("target")
        );
    }
    #[test]
    fn historical_restore_uses_the_actual_synchronized_after_ctime() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-restore-history-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let original = setup(tmp.path(), "/etc/immutable-test");
        let attempt =
            RuntimeRestoreAttempt::prepare(original, recovery(tmp.path()), &retirement(tmp.path()))
                .unwrap();
        let (actual, _) = attempt.restore().unwrap();
        assert!(attempt.has_completed_result().unwrap());
        assert_eq!(
            attempt.historical_restored_snapshot().unwrap(),
            actual.after
        );
        assert!(
            admit_current(
                &actual.after,
                &snapshot(&attempt.original.recovery).unwrap(),
                None
            )
            .is_ok()
        );
    }
    fn setup(root: &Path, path: &str) -> DurableAttempt {
        std::fs::create_dir(root.join("apply")).unwrap();
        std::fs::set_permissions(root.join("apply"), std::fs::Permissions::from_mode(0o700))
            .unwrap();
        std::fs::write(root.join("inode"), b"runtime original bytes").unwrap();
        let held = File::from(
            rustix::fs::open(
                root.join("inode"),
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .unwrap(),
        );
        let pin = FilePin {
            path: root.join("source-plan"),
            bytes: 1,
            sha256: "a".repeat(64),
        };
        let source = DurableAttempt::prepare(
            Records::open(&root.join("apply")).unwrap(),
            held,
            &"b".repeat(64),
            &pin,
            0,
            Path::new(path),
            b"candidate",
            "user.droidloom.runtime-label",
        )
        .unwrap();
        source.apply().unwrap();
        source
    }
    fn recovery(root: &Path) -> Records {
        std::fs::create_dir(root.join("restore")).unwrap();
        std::fs::set_permissions(root.join("restore"), std::fs::Permissions::from_mode(0o700))
            .unwrap();
        Records::open(&root.join("restore")).unwrap()
    }
    fn retirement(root: &Path) -> FilePin {
        FilePin {
            path: root.join("actual-retirement"),
            bytes: 1,
            sha256: "c".repeat(64),
        }
    }
    #[test]
    fn normal_seed_contract_only_allows_its_exact_creditable_attribute() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-seed-contract-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let original = setup(tmp.path(), "/var/lib/systemd/random-seed");
        // This is a pure metadata-contract check; no synthetic identity is
        // submitted to a physical writer or used as retirement authority.
        let mut before = snapshot(&original.recovery).unwrap();
        before.identity.uid = 0;
        before.identity.gid = 0;
        before.identity.mode = (before.identity.mode & !0o7777) | 0o600;
        let mut current = before.clone();
        current.identity.mtime_sec += 1;
        current.attributes.insert(
            super::super::super::service_state::CREDITABLE.into(),
            b"1".to_vec(),
        );
        admit_current(&before, &current, Some(RuntimeClass::RandomSeed)).unwrap();
        assert!(admit_current(&before, &current, Some(RuntimeClass::Log)).is_err());
        let mut wrong = current.clone();
        wrong.attributes.insert("user.other".into(), b"1".to_vec());
        assert!(admit_current(&before, &wrong, Some(RuntimeClass::RandomSeed)).is_err());
        wrong = current.clone();
        wrong.attributes.insert(
            super::super::super::service_state::CREDITABLE.into(),
            b"yes".to_vec(),
        );
        assert!(admit_current(&before, &wrong, Some(RuntimeClass::RandomSeed)).is_err());
        wrong = current.clone();
        wrong.identity.ino += 1;
        assert!(admit_current(&before, &wrong, Some(RuntimeClass::RandomSeed)).is_err());
    }
    #[test]
    fn actual_runtime_append_is_preserved_while_only_our_label_is_restored() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-current-restore-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let original = setup(tmp.path(), "/var/log/owned-test");
        std::fs::OpenOptions::new()
            .append(true)
            .open(tmp.path().join("inode"))
            .unwrap()
            .write_all(b" genuine normal runtime append")
            .unwrap();
        let current = snapshot(&original.recovery).unwrap();
        let attempt =
            RuntimeRestoreAttempt::prepare(original, recovery(tmp.path()), &retirement(tmp.path()))
                .unwrap();
        let (actual, _) = attempt.restore().unwrap();
        assert!(only_ctime_changed(
            &current.identity,
            &actual.after.identity
        ));
        assert_eq!(
            actual.after.attributes.get("user.droidloom.runtime-label"),
            None
        );
        assert_eq!(
            std::fs::read(tmp.path().join("inode")).unwrap(),
            b"runtime original bytes genuine normal runtime append"
        );
    }
    #[test]
    fn immutable_or_later_unknown_metadata_and_xattrs_do_not_restore() {
        for kind in 0..3 {
            let tmp = tempfile::Builder::new()
                .prefix(".p4-current-reject-")
                .tempdir_in(std::env::current_dir().unwrap())
                .unwrap();
            let original = setup(
                tmp.path(),
                if kind == 0 {
                    "/var/lib/dpkg/status"
                } else {
                    "/home/alex/Documents/owned-test"
                },
            );
            if kind == 0 {
                std::fs::write(
                    tmp.path().join("inode"),
                    b"changed immutable package database",
                )
                .unwrap();
            }
            if kind == 1 {
                set(
                    &original.recovery,
                    "user.unrelated",
                    Some(b"unadmitted attribute change"),
                )
                .unwrap();
            }
            let result = RuntimeRestoreAttempt::prepare(
                original,
                recovery(tmp.path()),
                &retirement(tmp.path()),
            );
            if kind < 2 {
                assert!(result.is_err());
            } else {
                let attempt = result.unwrap();
                std::fs::write(
                    tmp.path().join("inode"),
                    b"concurrent post-retirement write",
                )
                .unwrap();
                assert!(attempt.restore().is_err());
                assert_eq!(
                    snapshot(&attempt.original.recovery)
                        .unwrap()
                        .attributes
                        .get("user.droidloom.runtime-label"),
                    Some(&b"candidate".to_vec())
                );
            }
        }
    }
}
