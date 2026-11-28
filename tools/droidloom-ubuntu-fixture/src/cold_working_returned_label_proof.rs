//! Completed label restoration bound to one fresh original-kernel owner.
//! Neither preserved JSON nor a matching candidate string can construct or
//! transfer this capability. The only constructor consumes a real completed
//! RuntimeRestoreAttempt and its synchronized held-inode derivation.
use super::super::{
    LABEL, LabelDerivation, PlanSeal, Snapshot, attributes, only_ctime_changed, snapshot,
};
use super::runtime::RuntimeRestoreAttempt;
use crate::{
    Result,
    boot_files::FilePin,
    cold_original_qualification::{WorkingRecoverySources, WorkingReturnOwner},
    ensure, fs,
    model::Identity,
};
use serde_json::Value;
use std::{
    fs::File,
    os::unix::fs::FileExt,
    path::{Path, PathBuf},
    rc::Rc,
    sync::Arc,
};

struct HeldRecord {
    pin: FilePin,
    file: File,
    snapshot: Snapshot,
}
impl HeldRecord {
    fn open(pin: &FilePin) -> Result<Self> {
        ensure(
            pin.bytes > 0 && pin.bytes <= 32 * 1024 * 1024 && fs::valid_digest(&pin.sha256),
            "returned label record has no complete bounded content pin",
        )?;
        let file = fs::Tree::open("/", 0)?.file(&fs::absolute_string(&pin.path)?)?;
        let state = snapshot(&file)?;
        ensure(
            state.identity.mode == 0o100400
                && state.identity.uid == 0
                && state.identity.gid == 0
                && state.identity.nlink == 1
                && state.identity.size == pin.bytes,
            "returned label record is not a real protected root inode",
        )?;
        let value = Self {
            pin: pin.clone(),
            file,
            snapshot: state,
        };
        value.json()?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        ensure(
            snapshot(&self.file)? == self.snapshot,
            "held returned label evidence changed",
        )?;
        let named = fs::Tree::open("/", 0)?.file(&fs::absolute_string(&self.pin.path)?)?;
        ensure(
            snapshot(&named)? == self.snapshot,
            "named returned label evidence changed its persistent inode",
        )
    }
    fn json(&self) -> Result<Value> {
        self.revalidate()?;
        let mut raw = vec![0_u8; usize::try_from(self.pin.bytes)?];
        self.file.read_exact_at(&mut raw, 0)?;
        ensure(
            self.file.read_at(&mut [0], self.pin.bytes)? == 0
                && fs::digest(&raw) == self.pin.sha256,
            "returned label evidence lost its complete held bytes",
        )?;
        self.revalidate()?;
        Ok(serde_json::from_slice(&raw)?)
    }
}

/// Evidence of exactly one completed xattr restoration. It owns the target FD,
/// full current/after snapshots, persistent inode generation, and the actual
/// synchronized result records. It is deliberately neither Clone nor Deserialize.
pub(crate) struct WorkingReturnedLabelRestoration {
    sources: Rc<WorkingRecoverySources>,
    plan: Arc<PlanSeal>,
    paths: Vec<PathBuf>,
    original: HeldRecord,
    applied: HeldRecord,
    current: HeldRecord,
    restored: HeldRecord,
    retirement: HeldRecord,
    core: LabelDerivation,
}
impl WorkingReturnedLabelRestoration {
    pub(super) fn completed(
        sources: Rc<WorkingRecoverySources>,
        plan: Arc<PlanSeal>,
        paths: Vec<PathBuf>,
        attempt: &RuntimeRestoreAttempt,
        core: LabelDerivation,
        restored: &FilePin,
    ) -> Result<Self> {
        sources.revalidate_normal_source_custody()?;
        plan.revalidate()?;
        ensure(
            plan.pin.path == sources.work().join("working-labels/LABEL-PLAN.json")
                && !paths.is_empty()
                && paths.len() <= 65536
                && paths.iter().all(|p| {
                    p.is_absolute()
                        && p.components().all(|c| {
                            matches!(
                                c,
                                std::path::Component::RootDir | std::path::Component::Normal(_)
                            )
                        })
                })
                && core.before == *attempt.current_snapshot()
                && core.after == attempt.historical_restored_snapshot()?,
            "returned label result is not the actual held normal-plan completion",
        )?;
        let original = HeldRecord::open(attempt.original_pin())?;
        let current = HeldRecord::open(attempt.preimage_pin())?;
        let current_json = current.json()?;
        let applied = HeldRecord::open(&serde_json::from_value(current_json["applied"].clone())?)?;
        let retirement =
            HeldRecord::open(&serde_json::from_value(current_json["retirement"].clone())?)?;
        let restored = HeldRecord::open(restored)?;
        let original_json = original.json()?;
        let prelabel: Snapshot = serde_json::from_value(original_json["before"].clone())?;
        ensure(
            original_json["schema"] == "droidloom.original-label-preimage.v1"
                && original_json["candidate_id"] == sources.candidate()
                && original_json["ordinal"] == attempt.ordinal()
                && original_json["source_plan"] == serde_json::to_value(&plan.pin)?
                && original_json["logical_path"] == fs::absolute_string(&paths[0])?
                && original_json["attribute"] == LABEL,
            "returned label original preimage belongs to another plan member",
        )?;
        let application = applied.json()?;
        let applied_snapshot: Snapshot = serde_json::from_value(application["after"].clone())?;
        let desired: Vec<u8> = serde_json::from_value(original_json["desired"].clone())?;
        let mut applied_attributes = prelabel.attributes.clone();
        applied_attributes.insert(LABEL.into(), desired);
        ensure(
            application["schema"] == "droidloom.original-label-applied.v1"
                && application["preimage"] == serde_json::to_value(&original.pin)?
                && application["before"] == serde_json::to_value(&prelabel)?
                && applied_snapshot.handle == prelabel.handle
                && only_ctime_changed(&prelabel.identity, &applied_snapshot.identity)
                && applied_snapshot.attributes == applied_attributes
                && application["target_metadata_durability"]["operation"] == "syncfs"
                && application["target_metadata_durability"]["filesystem_dev"]
                    == prelabel.identity.dev,
            "returned label lacks its actual original durable normal application",
        )?;
        let completion = restored.json()?;
        ensure(
            current_json["schema"] == "droidloom.current-label-restore-preimage.v1"
                && current_json["original_preimage"] == serde_json::to_value(&original.pin)?
                && current_json["current"] == serde_json::to_value(&core.before)?
                && completion["schema"] == "droidloom.current-label-restored.v1"
                && completion["current_preimage"] == serde_json::to_value(&current.pin)?
                && completion["original_preimage"] == serde_json::to_value(&original.pin)?
                && completion["retirement"] == serde_json::to_value(&retirement.pin)?
                && completion["before"] == serde_json::to_value(&core.before)?
                && completion["after"] == serde_json::to_value(&core.after)?
                && completion["target_metadata_durability"]["operation"] == "syncfs"
                && completion["target_metadata_durability"]["filesystem_dev"]
                    == core.after.identity.dev,
            "returned label result lost its exact current preimage or actual metadata barrier",
        )?;
        let mut restored_attributes = core.before.attributes.clone();
        match prelabel.attributes.get(LABEL) {
            Some(value) => {
                restored_attributes.insert(LABEL.into(), value.clone());
            }
            None => {
                restored_attributes.remove(LABEL);
            }
        }
        ensure(
            core.before.handle == prelabel.handle
                && core.after.handle == prelabel.handle
                && only_ctime_changed(&core.before.identity, &core.after.identity)
                && core.after.attributes == restored_attributes,
            "returned label restoration changed anything beyond its owned label and ctime",
        )?;
        let value = Self {
            sources,
            plan,
            paths,
            original,
            applied,
            current,
            restored,
            retirement,
            core,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(crate) fn require_owner(&self, owner: &WorkingReturnOwner) -> Result<()> {
        ensure(
            std::ptr::eq(self.sources.owner().as_ref(), owner),
            "returned label proof is owned by another actual fresh factory",
        )?;
        self.revalidate()
    }
    pub(crate) fn candidate_id(&self) -> &str {
        self.sources.candidate()
    }
    pub(crate) fn paths(&self) -> &[PathBuf] {
        &self.paths
    }
    pub(crate) fn source_plan(&self) -> &FilePin {
        &self.plan.pin
    }
    pub(crate) fn before_identity(&self) -> &Identity {
        &self.core.before.identity
    }
    pub(crate) fn after_identity(&self) -> &Identity {
        &self.core.after.identity
    }
    pub(crate) fn require_held_transition(
        &self,
        path: &Path,
        file: &File,
        before: &Identity,
    ) -> Result<Identity> {
        self.revalidate()?;
        ensure(
            self.paths.iter().any(|p| p == path)
                && (before == &self.core.before.identity || before == &self.core.after.identity),
            "returned label held checkpoint is outside this completed exact transition",
        )?;
        let actual = snapshot(file)?;
        ensure(
            actual == self.core.after
                && self.core.before.handle == self.core.after.handle
                && only_ctime_changed(&self.core.before.identity, &self.core.after.identity),
            "returned label target changed its inode generation, metadata or complete attributes",
        )?;
        self.revalidate()?;
        Ok(actual.identity)
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        // A successful label syscall precedes adoption of owner/retirement
        // ctime checkpoints. Only immutable normal-source custody is checked
        // here; recursively checking those old mutable checkpoints is invalid.
        self.sources.revalidate_normal_source_custody()?;
        self.plan.revalidate()?;
        for record in [
            &self.original,
            &self.applied,
            &self.current,
            &self.restored,
            &self.retirement,
        ] {
            record.revalidate()?;
        }
        self.core.revalidate()?;
        ensure(
            attributes(&self.core.file)? == self.core.after.attributes,
            "returned target complete xattrs changed after synchronized restoration",
        )?;
        self.plan.revalidate()?;
        self.sources.revalidate_normal_source_custody()
    }
}
