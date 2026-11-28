//! Fixed returned boot/runtime inverse, with current four-image custody.
//! Runtime evidence remains at its real names until every retirement reader
//! has finished; the report explicitly identifies those retained directories.
#[path = "cold_working_file_custody.rs"]
mod custody;
use super::super::{
    WorkingRecoverySources, WorkingReturnQuiescence, materials::Guard, owner::SealedInput,
};
use super::Payload;
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_data::WorkingReturnData,
    ensure, fs,
};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    path::{Path, PathBuf},
    rc::Rc,
};

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kind {
    Boot,
    Runtime,
}
pub(in crate::cold_original_qualification) struct WorkingReturnedFiles {
    sources: Rc<WorkingRecoverySources>,
    kind: Kind,
    transaction: custody::Transaction,
    retained: BTreeSet<PathBuf>,
    inputs: Vec<SealedInput>,
    guards: Vec<Guard>,
    report: Option<SealedInput>,
}
fn read_fixed(sources: &WorkingRecoverySources, name: &str) -> Result<(SealedInput, Value)> {
    let p = files::pin_file(&sources.work().join(name))?;
    ensure(
        p.bytes > 0 && p.bytes <= 32 * 1024 * 1024,
        "bounded returned normal input required",
    )?;
    let seal = SealedInput::open(&p)?;
    let value = serde_json::from_slice(&seal.read()?)?;
    Ok((seal, value))
}
impl WorkingReturnedFiles {
    pub(in crate::cold_original_qualification) fn boot(
        data: &WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<Self> {
        Self::open(data, window, Kind::Boot)
    }
    pub(in crate::cold_original_qualification) fn runtime(
        data: &WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<Self> {
        data.verify_original_restored()?;
        Self::open(data, window, Kind::Runtime)
    }
    fn open(
        data: &WorkingReturnData,
        window: &WorkingReturnQuiescence,
        kind: Kind,
    ) -> Result<Self> {
        data.revalidate()?;
        let sources = data.sources().clone();
        window.require_sources(&sources)?;
        let labels = data.returned_label_history()?;
        labels.require_data(data, window)?;
        let mut inputs = Vec::new();
        let mut guards = Vec::new();
        let mut required = BTreeMap::new();
        let mut optional = BTreeSet::new();
        let mut retained = BTreeSet::new();
        let directory = match kind {
            Kind::Runtime => {
                for file in sources.runtime_files() {
                    required.insert(
                        file.destination.clone(),
                        Payload::Regular {
                            source: file.source.clone(),
                            mode: file.mode,
                        },
                    );
                }
                ensure(
                    required.len() == 12,
                    "returned runtime lost its exact twelve source files",
                )?;
                for name in [
                    "/etc/droidloom/qualification",
                    "/etc/droidloom/host-mac",
                    "/etc/droidloom-maintenance",
                ] {
                    optional.insert(PathBuf::from(name));
                }
                let evidence = sources.configuration().runtime_evidence_directory();
                let parent = evidence
                    .parent()
                    .ok_or("returned evidence parent")?
                    .to_owned();
                for path in [parent, evidence] {
                    required.insert(path.clone(), Payload::Absent);
                    retained.insert(path);
                }
                "working-runtime-files"
            }
            Kind::Boot => {
                let (prepared, body) = read_fixed(&sources, "WORKING-RECOVERY-PREPARED.json")?;
                ensure(
                    body["schema"] == "droidloom.working-qualification-recovery-prepared.v1"
                        && body["candidate_id"] == sources.candidate()
                        && body["boot_intent"] == serde_json::to_value(sources.boot_intent())?
                        && body["same_four_backing_ofds_retained"] == true,
                    "returned initramfs is outside its source-owned working preparation",
                )?;
                let normal_pin: FilePin = serde_json::from_value(body["normal_prepared"].clone())?;
                let normal = SealedInput::open(&normal_pin)?;
                let actual: Value = serde_json::from_slice(&normal.read()?)?;
                let initrd: FilePin = serde_json::from_value(body["initrd"].clone())?;
                ensure(
                    actual["initrd"] == serde_json::to_value(&initrd)?
                        && actual["input"] == body["normal_producer_plan"]
                        && actual["recovery_recipe_input"] == body["recovery_recipe"]
                        && actual["recovery_image_readback"]["schema"]
                            == "droidloom.working-qualification-recovery-image-readback.v1",
                    "returned initramfs lost its actual maintained producer cross-links",
                )?;
                guards.push(Guard::open(&initrd)?);
                let custom = files::pin_file(&sources.work().join("WORKING-CUSTOM-GRUB.cfg"))?;
                ensure(
                    custom.bytes > 0 && custom.bytes <= 2 * 1024 * 1024,
                    "bounded returned custom GRUB source required",
                )?;
                guards.push(Guard::open(&custom)?);
                let base = Path::new("/boot/droidloom/working-qualification");
                optional.insert(base.to_owned());
                let candidate = base.join(sources.candidate());
                required.insert(candidate.clone(), Payload::Absent);
                required.insert(
                    candidate.join("initrd.img"),
                    Payload::Regular {
                        source: initrd,
                        mode: 0o400,
                    },
                );
                required.insert(
                    PathBuf::from("/boot/grub/custom.cfg"),
                    Payload::Regular {
                        source: custom,
                        mode: 0o644,
                    },
                );
                inputs.push(prepared);
                inputs.push(normal);
                "working-grub-files"
            }
        };
        let transaction = custody::Transaction::reopen_returned(
            sources.work().join(directory),
            sources.candidate().into(),
            &required,
            &optional,
            &retained,
            labels,
        )?;
        let value = Self {
            sources,
            kind,
            transaction,
            retained,
            inputs,
            guards,
            report: None,
        };
        value.fence(data, window)?;
        Ok(value)
    }
    fn fence(&self, data: &WorkingReturnData, window: &WorkingReturnQuiescence) -> Result<()> {
        data.require_sources(&self.sources)?;
        window.require_sources(&self.sources)?;
        if self.kind == Kind::Runtime {
            data.verify_original_restored()?;
        }
        for input in &self.inputs {
            input.revalidate()?;
        }
        for guard in &self.guards {
            guard.revalidate()?;
        }
        if let Some(report) = &self.report {
            report.revalidate()?;
        }
        self.transaction.guard()?;
        data.revalidate_custody()?;
        window.revalidate()
    }
    pub(in crate::cold_original_qualification) fn restore(
        &mut self,
        data: &WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<FilePin> {
        self.fence(data, window)?;
        if let Some(report) = &self.report {
            return Ok(report.pin().clone());
        }
        for index in (0..self.transaction.len()).rev() {
            if self.retained.contains(self.transaction.target(index)) {
                continue;
            }
            self.fence(data, window)?;
            // An error can follow the actual rename. Reconcile through the
            // held descriptors first; never blindly repeat an unknown effect.
            let operation = self.transaction.restore(index);
            let observation = self.transaction.reconcile_pending();
            observation?;
            self.fence(data, window)?;
            operation?;
        }
        ensure(
            self.transaction.all_restored_except(&self.retained),
            "returned normal files did not complete their finite inverse",
        )?;
        let details = self.transaction.returned_evidence(&self.retained)?;
        let kind = if self.kind == Kind::Boot {
            "boot"
        } else {
            "runtime"
        };
        let path = data
            .report()
            .path
            .parent()
            .ok_or("returned report directory")?
            .join(format!("{kind}-FILES-RESTORED.json"));
        let value = json!({"schema":"droidloom.working-returned-files.v1","candidate_id":self.sources.candidate(),
            "kind":kind,"fresh_owner":self.sources.owner().evidence(),"actual_data_retirement":data.report(),
            "completed_label_history":data.returned_label_history()?.handoff(),"actual_boot_retirement":data.retirement().report_pin(),
            "actual_freezer":window.intent_pin(),"details":details,"retained_evidence_paths":self.retained,
            "evidence_deleted":false,"production_ready":false});
        let bytes = serde_json::to_vec(&value)?;
        files::write_new(&path, &bytes, 0o400)?;
        File::open(path.parent().unwrap())?.sync_all()?;
        let pin = files::pin_file(&path)?;
        self.report = Some(SealedInput::open(&pin)?);
        self.fence(data, window)?;
        Ok(pin)
    }
}
