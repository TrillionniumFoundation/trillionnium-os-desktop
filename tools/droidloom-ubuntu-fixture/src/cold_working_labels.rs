//! Full normal H2 label evidence. All constructors remain inside this module;
//! a source comparison, serialized receipt, or caller Boolean cannot make a
//! batch. The full-root writer retains the live owner and actual inode FDs.
use super::{LABEL, LabelDerivation, PlanSeal, Snapshot, only_ctime_changed};
use crate::{
    Result,
    boot_files::FilePin,
    cold_original_qualification::{WorkingLabelSourceIdentity, WorkingRuntimeSources},
    ensure,
    model::Identity,
};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
    rc::Rc,
    sync::Arc,
};

/// A comparison supplied from a caller's already-held full inode checkpoint.
/// Handle bytes and every xattr value use lowercase hexadecimal, as the normal
/// publication custody does. This tuple carries no authority of its own.
pub(crate) type WorkingLabelCheckpoint<'a> =
    (&'a Identity, i32, &'a str, &'a BTreeMap<String, String>);

struct Origin {
    source: WorkingLabelSourceIdentity,
    plan: Arc<PlanSeal>,
}
impl Origin {
    fn revalidate(&self) -> Result<()> {
        self.plan.revalidate()?;
        ensure(
            self.plan.pin.path == self.source.work().join("working-labels/LABEL-PLAN.json"),
            "working label plan left this owner's fixed private journal",
        )?;
        self.source.revalidate_normal_source()?;
        self.plan.revalidate()
    }
}

/// One completed normal lookup -> PREIMAGE -> held syscall -> syncfs -> APPLIED
/// transition. There is no public constructor, Clone, or Deserialize.
pub(crate) struct WorkingLabelDerivation {
    origin: Rc<Origin>,
    ordinal: u32,
    paths: Vec<PathBuf>,
    preimage: FilePin,
    applied: FilePin,
    core: LabelDerivation,
}

fn require_member_checkpoint(snapshot: &Snapshot, value: (&Identity, i32, &str)) -> Result<()> {
    ensure(
        &snapshot.identity == value.0
            && snapshot.handle.handle_type == value.1
            && hex::encode(&snapshot.handle.bytes) == value.2,
        "working member checkpoint differs in full F9 or inode generation",
    )
}

fn require_checkpoint(snapshot: &Snapshot, value: WorkingLabelCheckpoint<'_>) -> Result<()> {
    let (identity, handle_type, handle, attributes) = value;
    let actual_attributes = snapshot
        .attributes
        .iter()
        .map(|(name, bytes)| (name.clone(), hex::encode(bytes)))
        .collect::<BTreeMap<_, _>>();
    ensure(
        &snapshot.identity == identity
            && snapshot.handle.handle_type == handle_type
            && hex::encode(&snapshot.handle.bytes) == handle
            && &actual_attributes == attributes,
        "working label checkpoint differs in full F9, generation, or xattrs",
    )
}
impl WorkingLabelDerivation {
    pub(crate) fn candidate_id(&self) -> &str {
        self.origin.source.candidate()
    }
    pub(crate) fn source_plan(&self) -> &FilePin {
        &self.origin.plan.pin
    }
    pub(crate) fn paths(&self) -> &[PathBuf] {
        &self.paths
    }
    pub(crate) fn before_identity(&self) -> &Identity {
        &self.core.before.identity
    }
    pub(crate) fn after_identity(&self) -> &Identity {
        &self.core.after.identity
    }
    pub(crate) fn require_transition(
        &self,
        path: &Path,
        before: WorkingLabelCheckpoint<'_>,
        after: WorkingLabelCheckpoint<'_>,
    ) -> Result<()> {
        self.revalidate()?;
        ensure(
            self.paths.iter().any(|known| known == path),
            "working label transition is outside its actual normal plan aliases",
        )?;
        require_checkpoint(&self.core.before, before)?;
        require_checkpoint(&self.core.after, after)?;
        self.revalidate()
    }
    /// Directory inventories hold each child's F9 and generation, but do not
    /// invent an xattr checkpoint. The real proof retains and validates both
    /// complete xattr snapshots before comparing that narrower held inventory.
    pub(crate) fn require_member_transition(
        &self,
        path: &Path,
        before: (&Identity, i32, &str),
        after: (&Identity, i32, &str),
    ) -> Result<()> {
        self.revalidate()?;
        ensure(
            self.paths.iter().any(|known| known == path),
            "working member transition is outside its actual normal plan aliases",
        )?;
        require_member_checkpoint(&self.core.before, before)?;
        require_member_checkpoint(&self.core.after, after)?;
        self.revalidate()
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.origin.revalidate()?;
        self.core.revalidate()?;
        ensure(
            !self.paths.is_empty(),
            "working label transition has no actual path",
        )?;
        let preimage: serde_json::Value =
            serde_json::from_slice(&super::super::root_pin(&self.preimage, 32 * 1024 * 1024)?)?;
        let label = self
            .core
            .after
            .attributes
            .get(LABEL)
            .ok_or("actual working normal label missing")?;
        // The unchanged private per-inode journal is the physical write core.
        // Its schema never grants the old once qualification owner or phase.
        ensure(
            preimage["schema"] == "droidloom.original-label-preimage.v1"
                && preimage["candidate_id"] == self.candidate_id()
                && preimage["ordinal"] == self.ordinal
                && preimage["logical_path"] == self.paths[0].to_string_lossy().as_ref()
                && preimage["source_plan"] == serde_json::to_value(self.source_plan())?
                && preimage["attribute"] == LABEL
                && preimage["desired"] == serde_json::to_value(label)?
                && preimage["before"] == serde_json::to_value(&self.core.before)?,
            "working label preimage is outside this actual source-bound transition",
        )?;
        let mut wanted = self.core.before.attributes.clone();
        wanted.insert(LABEL.into(), label.clone());
        ensure(
            only_ctime_changed(&self.core.before.identity, &self.core.after.identity)
                && self.core.before.handle == self.core.after.handle
                && wanted == self.core.after.attributes,
            "working label operation changed an unrelated inode field or xattr",
        )?;
        let applied: serde_json::Value =
            serde_json::from_slice(&super::super::root_pin(&self.applied, 32 * 1024 * 1024)?)?;
        ensure(
            applied["schema"] == "droidloom.original-label-applied.v1"
                && applied["preimage"] == serde_json::to_value(&self.preimage)?
                && applied["before"] == serde_json::to_value(&self.core.before)?
                && applied["after"] == serde_json::to_value(&self.core.after)?
                && applied["target_metadata_durability"]["operation"] == "syncfs"
                && applied["target_metadata_durability"]["filesystem_dev"]
                    == self.core.after.identity.dev,
            "working label completion lacks this durable held-inode operation",
        )?;
        self.core.revalidate()?;
        self.origin.revalidate()
    }
}

/// All actual writes in one bounded syncfs batch. Consumers must validate every
/// parent/child difference against these records before advancing any full
/// source or publication guard. Applying a record one at a time is insufficient.
pub(crate) struct WorkingLabelBatch {
    origin: Rc<Origin>,
    records: Vec<WorkingLabelDerivation>,
}
impl WorkingLabelBatch {
    pub(crate) fn candidate_id(&self) -> &str {
        self.origin.source.candidate()
    }
    pub(crate) fn source_plan(&self) -> &FilePin {
        &self.origin.plan.pin
    }
    pub(crate) fn records(&self) -> &[WorkingLabelDerivation] {
        &self.records
    }
    pub(crate) fn require_source(&self, source: &WorkingRuntimeSources) -> Result<()> {
        self.origin.source.require_source(source)?;
        self.revalidate()
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.origin.revalidate()?;
        ensure(
            (1..=64).contains(&self.records.len()),
            "working label batch is empty or exceeds the actual bounded write cohort",
        )?;
        let mut ordinals = BTreeSet::new();
        let mut inodes = BTreeSet::new();
        let mut paths = BTreeSet::new();
        for record in &self.records {
            ensure(
                Rc::ptr_eq(&self.origin, &record.origin)
                    && ordinals.insert(record.ordinal)
                    && inodes.insert((
                        record.core.after.identity.dev,
                        record.core.after.identity.ino,
                    )),
                "working label batch mixes owners, plans, ordinals, or inode writes",
            )?;
            for path in &record.paths {
                ensure(
                    path.is_absolute()
                        && path.components().all(|part| {
                            matches!(
                                part,
                                std::path::Component::RootDir | std::path::Component::Normal(_)
                            )
                        })
                        && paths.insert(path),
                    "working label batch aliases are ambiguous or noncanonical",
                )?;
            }
            record.revalidate()?;
        }
        self.origin.revalidate()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{fs::OpenOptions, io::Write, os::unix::fs::OpenOptionsExt};

    fn checkpoint(snapshot: &Snapshot) -> (String, BTreeMap<String, String>) {
        (
            hex::encode(&snapshot.handle.bytes),
            snapshot
                .attributes
                .iter()
                .map(|(key, value)| (key.clone(), hex::encode(value)))
                .collect(),
        )
    }
    fn actual_file() -> (tempfile::TempDir, std::fs::File, Snapshot) {
        let directory = tempfile::Builder::new()
            .prefix(".p4-working-label-proof-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(directory.path().join("input"))
            .unwrap();
        file.write_all(b"source-owned exact inode\n").unwrap();
        file.sync_all().unwrap();
        let observed = super::super::snapshot(&file).unwrap();
        (directory, file, observed)
    }
    #[test]
    fn working_label_checkpoint_binds_actual_inode_generation_and_all_f9() {
        let (_directory, _file, observed) = actual_file();
        let (handle, attributes) = checkpoint(&observed);
        let good = (
            &observed.identity,
            observed.handle.handle_type,
            handle.as_str(),
            &attributes,
        );
        require_checkpoint(&observed, good).unwrap();
        let mut changed = observed.identity.clone();
        changed.nlink += 1;
        assert!(require_checkpoint(&observed, (&changed, good.1, good.2, good.3)).is_err());
        let mut changed = observed.identity.clone();
        changed.uid += 1;
        assert!(require_checkpoint(&observed, (&changed, good.1, good.2, good.3)).is_err());
        assert!(
            require_checkpoint(&observed, (&observed.identity, good.1 + 1, good.2, good.3))
                .is_err()
        );
        let mut changed = observed.handle.bytes.clone();
        changed[0] ^= 1;
        assert!(
            require_checkpoint(
                &observed,
                (&observed.identity, good.1, &hex::encode(changed), good.3)
            )
            .is_err()
        );
    }
    #[test]
    fn working_label_checkpoint_rejects_same_bytes_different_actual_inode() {
        let (_directory_a, _file_a, first) = actual_file();
        let (_directory_b, _file_b, second) = actual_file();
        let (handle, attributes) = checkpoint(&second);
        assert!(
            require_checkpoint(
                &first,
                (
                    &second.identity,
                    second.handle.handle_type,
                    &handle,
                    &attributes
                )
            )
            .is_err()
        );
    }
    #[test]
    fn working_label_checkpoint_requires_complete_xattr_inventory_and_values() {
        let (_directory, file, original) = actual_file();
        rustix::fs::fsetxattr(
            &file,
            "user.p4-working-label-proof",
            b"first",
            rustix::fs::XattrFlags::empty(),
        )
        .unwrap();
        let actual = super::super::snapshot(&file).unwrap();
        let (handle, attributes) = checkpoint(&actual);
        require_checkpoint(
            &actual,
            (
                &actual.identity,
                actual.handle.handle_type,
                &handle,
                &attributes,
            ),
        )
        .unwrap();
        let mut missing = attributes.clone();
        missing.remove("user.p4-working-label-proof");
        assert!(
            require_checkpoint(
                &actual,
                (
                    &actual.identity,
                    actual.handle.handle_type,
                    &handle,
                    &missing
                )
            )
            .is_err()
        );
        let mut changed = attributes.clone();
        changed.insert("user.p4-working-label-proof".into(), hex::encode(b"second"));
        assert!(
            require_checkpoint(
                &actual,
                (
                    &actual.identity,
                    actual.handle.handle_type,
                    &handle,
                    &changed
                )
            )
            .is_err()
        );
        let (old_handle, old_attributes) = checkpoint(&original);
        assert!(
            require_checkpoint(
                &actual,
                (
                    &original.identity,
                    original.handle.handle_type,
                    &old_handle,
                    &old_attributes
                )
            )
            .is_err()
        );
    }

    #[test]
    fn working_label_checkpoint_member_tuple_keeps_full_f9_and_generation() {
        let (_directory, file, observed) = actual_file();
        let handle = hex::encode(&observed.handle.bytes);
        require_member_checkpoint(
            &observed,
            (&observed.identity, observed.handle.handle_type, &handle),
        )
        .unwrap();
        let mut changed = observed.identity.clone();
        changed.ctime_nsec += 1;
        assert!(
            require_member_checkpoint(&observed, (&changed, observed.handle.handle_type, &handle),)
                .is_err()
        );
        assert!(
            require_member_checkpoint(
                &observed,
                (&observed.identity, observed.handle.handle_type + 1, &handle),
            )
            .is_err()
        );
        let (_other_directory, _other_file, other) = actual_file();
        assert!(
            require_member_checkpoint(
                &observed,
                (
                    &other.identity,
                    other.handle.handle_type,
                    &hex::encode(&other.handle.bytes)
                ),
            )
            .is_err()
        );
        rustix::fs::fsetxattr(
            &file,
            "user.p4-working-member-proof",
            b"actual",
            rustix::fs::XattrFlags::empty(),
        )
        .unwrap();
        let after = super::super::snapshot(&file).unwrap();
        assert!(
            require_member_checkpoint(
                &after,
                (&observed.identity, observed.handle.handle_type, &handle),
            )
            .is_err()
        );
    }
}
