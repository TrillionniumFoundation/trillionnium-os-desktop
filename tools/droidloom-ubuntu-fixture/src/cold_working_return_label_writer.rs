//! Full reverse of the actual working label plan after a new original-kernel
//! owner has retired the candidate and acquired all four real backing OFDs.
//! A history file supplies comparisons only. Every mutation requires the fresh
//! owner, source custody, complete data custody, and actual bounded freezer.
use super::super::{
    LABEL, PlanSeal, Snapshot, only_ctime_changed,
    scope::{Inventory, RootScope},
    snapshot,
};
use super::{
    BATCH_LIMIT, DurableAttempt, RecordBatch, Records,
    returned_proof::WorkingReturnedLabelRestoration,
    runtime::{self, EvolutionKind, ExactEvolution, RuntimeRestoreAttempt},
    working_writer::{Plan, Target},
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_data::{self as data, WorkingReturnData},
    cold_original_qualification::{WorkingRecoverySources, WorkingReturnQuiescence},
    ensure, fs,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    path::{Path, PathBuf},
    rc::Rc,
    sync::Arc,
};

#[path = "cold_working_return_label_history.rs"]
mod history;
pub(crate) use history::WorkingReturnedLabelHistory;

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Row {
    ordinal: u32,
    before: Snapshot,
    after: Snapshot,
    original_preimage: Option<FilePin>,
    current_preimage: Option<FilePin>,
    completed: Option<FilePin>,
    recognized_history: Option<FilePin>,
    target_write: bool,
}

pub(crate) struct WorkingReturnedLabelTransaction {
    sources: Rc<WorkingRecoverySources>,
    plan: Plan,
    seal: Arc<PlanSeal>,
    scope: RootScope,
    inventory: Inventory,
    extra: BTreeMap<PathBuf, File>,
    current: BTreeMap<PathBuf, Snapshot>,
    active: Vec<RuntimeRestoreAttempt>,
    rows: BTreeMap<u32, Row>,
}

/// Created only after every pre-existing target has its original label and
/// all excluded original data inodes have been read back without a mutation.
pub(crate) struct WorkingReturnedLabels {
    transaction: WorkingReturnedLabelTransaction,
    report: FilePin,
    report_file: File,
    report_snapshot: Snapshot,
}

fn same_pin(a: &FilePin, b: &FilePin) -> bool {
    a.path == b.path && a.bytes == b.bytes && a.sha256 == b.sha256
}
fn record_pin(records: &Records, name: &str) -> Result<FilePin> {
    let (_, _, bytes) = records.read(name)?;
    Ok(FilePin {
        path: records.path.join(name),
        bytes: bytes.len() as u64,
        sha256: fs::digest(&bytes),
    })
}
fn record_directory(plan: &Plan, ordinal: u32) -> PathBuf {
    plan.work.join(format!("inode-{ordinal:08}"))
}
fn exists(path: &Path) -> Result<bool> {
    match std::fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(e) => Err(e.into()),
    }
}
fn epoch(records: &Records, data: &WorkingReturnData) -> Result<Records> {
    let path = records
        .path
        .join(format!("retirement-{}", data.report().sha256));
    if !exists(&path)? {
        files::private_dir(&path)?;
    }
    Records::open(&path)
}
fn validate_plan(plan: &Plan, sources: &WorkingRecoverySources) -> Result<()> {
    ensure(
        plan.schema == "droidloom.working-label-transaction-plan.v1"
            && plan.candidate_id == sources.candidate()
            && plan.work == sources.work().join("working-labels")
            && same_pin(&plan.boot_intent, sources.boot_intent())
            && same_pin(&plan.normal_sources, sources.normal_sources().source_pin())
            && plan.boot_publication.path
                == sources.work().join("working-grub-files/PUBLISHED.json")
            && !plan.targets.is_empty()
            && plan.targets.len() <= 2_000_000,
        "returned label plan is outside this actual normal boot/source closure",
    )?;
    let publication: Value =
        serde_json::from_slice(&data::root_pin(&plan.boot_publication, 32 * 1024 * 1024)?)?;
    ensure(
        publication["schema"] == "droidloom.working-runtime-observed.v1"
            && publication["candidate_id"] == sources.candidate()
            && publication["restored"] == false,
        "returned label plan has no actual working boot-file publication",
    )?;
    let mut names = BTreeSet::new();
    let mut inodes = BTreeSet::new();
    let mut ordinary = BTreeMap::new();
    let mut separate = BTreeSet::new();
    for (index, target) in plan.targets.iter().enumerate() {
        ensure(
            target.ordinal as usize == index
                && !target.paths.is_empty()
                && !target.desired.is_empty()
                && target.desired.len() <= 4096
                && inodes.insert((target.before.identity.dev, target.before.identity.ino)),
            "returned label plan has duplicate or unbounded actual inode groups",
        )?;
        for path in &target.paths {
            fs::absolute_string(path)?;
            ensure(
                names.insert(path.clone()),
                "returned label plan repeats an alias",
            )?;
            if target.separate {
                separate.insert(path.clone());
            } else {
                ordinary.insert(path.clone(), target.before.clone());
            }
        }
    }
    let expected = plan
        .scope
        .entries
        .iter()
        .map(|e| (e.path.clone(), e.snapshot.clone()))
        .collect::<BTreeMap<_, _>>();
    let mut extras = data::WORKING_MEMBERS
        .iter()
        .map(|name| Path::new(data::ORIGINAL).join(name))
        .collect::<BTreeSet<_>>();
    extras.insert(PathBuf::from(data::ORIGINAL));
    extras.insert(PathBuf::from(data::SELECTED));
    ensure(
        ordinary == expected && separate == extras && extras.len() == 11,
        "returned label plan changed the complete ordinary or separate fixed target roster",
    )
}

impl WorkingReturnedLabelTransaction {
    pub(crate) fn reopen(
        data: &WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<Self> {
        data.revalidate()?;
        let sources = data.sources().clone();
        window.require_sources(&sources)?;
        let pin = files::pin_file(&sources.work().join("working-labels/LABEL-PLAN.json"))?;
        let seal = Arc::new(PlanSeal::open(&pin)?);
        let plan: Plan = serde_json::from_slice(&data::root_pin(&pin, 512 * 1024 * 1024)?)?;
        validate_plan(&plan, &sources)?;
        let scope = RootScope::original(sources.cold_clone())?;
        ensure(
            snapshot(&scope.open_named(Path::new("/"))?)?.handle == plan.scope.root_handle,
            "returned original root is a different persistent filesystem generation",
        )?;
        let inventory = scope.collect()?;
        let extra = data
            .held_working_label_targets()?
            .into_iter()
            .map(|(path, file, _)| (path, file))
            .collect::<BTreeMap<_, _>>();
        ensure(
            extra.len() == 11,
            "fresh returned data lost its exact held separate targets",
        )?;
        let value = Self {
            sources,
            plan,
            seal,
            scope,
            inventory,
            extra,
            current: BTreeMap::new(),
            active: Vec::new(),
            rows: BTreeMap::new(),
        };
        value.fence(data, window)?;
        value.seal.full_readback()?;
        Ok(value)
    }
    fn fence(&self, data: &WorkingReturnData, window: &WorkingReturnQuiescence) -> Result<()> {
        ensure(
            Rc::ptr_eq(&self.sources, data.sources()),
            "returned label data belongs to another fresh factory",
        )?;
        window.require_sources(&self.sources)?;
        data.revalidate_custody()?;
        self.seal.revalidate()?;
        self.scope.revalidate()
    }
    fn actual(&self, target: &Target) -> Result<(File, Snapshot)> {
        let open = |path: &Path| -> Result<File> {
            if target.separate {
                Ok(self
                    .extra
                    .get(path)
                    .ok_or("returned separate target lost its actual held FD")?
                    .try_clone()?)
            } else {
                self.scope.open_named(path)
            }
        };
        let file = open(&target.paths[0])?;
        let current = snapshot(&file)?;
        ensure(
            current.handle == target.before.handle
                && snapshot(&self.scope.reopen_generation(&target.before.handle)?)? == current,
            "returned target differs from the actual named/held persistent inode generation",
        )?;
        for path in &target.paths {
            ensure(
                snapshot(&open(path)?)? == current,
                "returned hardlink aliases differ from the held actual inode",
            )?;
        }
        Ok((file, current))
    }
    fn original(&self, target: &Target, file: File) -> Result<DurableAttempt> {
        let records = Records::open(&record_directory(&self.plan, target.ordinal))?;
        let pin = record_pin(&records, "PREIMAGE.json")?;
        let original = DurableAttempt::load_unclassified(records, &pin, file)?;
        original.validate_intent()?;
        ensure(
            original.preimage.before == target.before
                && original.preimage.desired == target.desired
                && original.preimage.attribute == LABEL
                && original.preimage.ordinal == target.ordinal
                && original.preimage.candidate_id == self.plan.candidate_id
                && original.preimage.logical_path == target.paths[0]
                && same_pin(&original.preimage.source_plan, &self.seal.pin),
            "returned label preimage differs from its complete actual normal plan",
        )?;
        Ok(original)
    }
    fn preparation_only(&self, data: &WorkingReturnData) -> Result<()> {
        ensure(
            data.retirement().candidate_boot_id().is_none()
                && self.sources.owner().boot_id() == self.sources.original_boot_id(),
            "a booted candidate cannot reconstruct missing pre-boot label applications",
        )
    }
    fn evolution(
        &self,
        target: &Target,
        current: &Snapshot,
        data: &WorkingReturnData,
    ) -> Option<ExactEvolution> {
        let path = &target.paths[0];
        let (kind, evidence) = if [
            "/var/lib/droidloom/users/1000/data/data.img",
            "/var/lib/droidloom/users/1000/data/metadata.img",
        ]
        .contains(&path.to_str().unwrap_or(""))
        {
            (EvolutionKind::WorkingReturnedBacking, data.report())
        } else if ["/etc/droidloom/production", data::SELECTED]
            .contains(&path.to_str().unwrap_or(""))
        {
            (EvolutionKind::WorkingReturnedSelection, data.report())
        } else if path == Path::new("/boot/grub/grubenv") {
            (
                EvolutionKind::WorkingReturnedGrubEnvironment,
                data.retirement().report_pin(),
            )
        } else {
            return None;
        };
        Some(ExactEvolution {
            kind,
            actual: current.clone(),
            evidence: evidence.clone(),
        })
    }
    fn history(
        &self,
        target: &Target,
        file: &File,
        current: &Snapshot,
        data: &WorkingReturnData,
    ) -> Result<Option<FilePin>> {
        let root = record_directory(&self.plan, target.ordinal);
        let records = Records::open(&root)?;
        let directory = File::from(rustix::fs::openat(
            &records.held,
            ".",
            rustix::fs::OFlags::RDONLY
                | rustix::fs::OFlags::DIRECTORY
                | rustix::fs::OFlags::NOFOLLOW
                | rustix::fs::OFlags::CLOEXEC,
            rustix::fs::Mode::empty(),
        )?);
        let mut epochs = Vec::new();
        for entry in rustix::fs::Dir::read_from(&directory)? {
            let entry = entry?;
            let name = entry.file_name().to_str()?;
            if let Some(hash) = name.strip_prefix("retirement-") {
                ensure(fs::valid_digest(hash), "unknown returned label epoch")?;
                epochs.push(name.to_owned());
            }
        }
        ensure(
            epochs.len() <= 64,
            "returned label history exceeds its finite recovery bound",
        )?;
        epochs.sort();
        for name in epochs {
            let old = Records::open(&root.join(&name))?;
            if !old.exists("CURRENT-PREIMAGE.json")? {
                continue;
            }
            let pin = record_pin(&old, "CURRENT-PREIMAGE.json")?;
            let (_, _, bytes) = old.read("CURRENT-PREIMAGE.json")?;
            let value: Value = serde_json::from_slice(&bytes)?;
            let retirement: FilePin = serde_json::from_value(value["retirement"].clone())?;
            let prior: Value =
                serde_json::from_slice(&data::root_pin(&retirement, 32 * 1024 * 1024)?)?;
            ensure(
                name == format!("retirement-{}", retirement.sha256)
                    && prior["schema"] == "droidloom.working-returned-data-custody.v1"
                    && prior["candidate_id"] == self.sources.candidate()
                    && prior["normal_sources"] == serde_json::to_value(&self.plan.normal_sources)?
                    && prior["boot_intent"] == serde_json::to_value(self.sources.boot_intent())?,
                "restored label history is outside the actual source-bound returned data epochs",
            )?;
            let attempt = RuntimeRestoreAttempt::open_evidence(
                self.original(target, file.try_clone()?)?,
                old,
                &pin,
            )?;
            let previous = attempt.historical_restored_snapshot()?;
            if previous.handle != current.handle || previous.attributes != current.attributes {
                continue;
            }
            if self.evolution(target, current, data).is_some() {
                ensure(
                    (
                        previous.identity.dev,
                        previous.identity.ino,
                        previous.identity.mode,
                        previous.identity.uid,
                        previous.identity.gid,
                        previous.identity.nlink,
                    ) == (
                        current.identity.dev,
                        current.identity.ino,
                        current.identity.mode,
                        current.identity.uid,
                        current.identity.gid,
                        current.identity.nlink,
                    ) && previous.identity.size == current.identity.size,
                    "returned owned history changed its fixed inode authority or geometry",
                )?;
            } else {
                for path in &target.paths {
                    let class = runtime::runtime_class(path, &self.plan.candidate_id);
                    if class.is_none() && !attempt.has_completed_result()? {
                        ensure(
                            only_ctime_changed(&previous.identity, &current.identity),
                            "uncertain immutable restoration changed more than its own ctime",
                        )?;
                    } else {
                        runtime::admit_current(&previous, current, class)?;
                    }
                }
            }
            return Ok(Some(pin));
        }
        Ok(None)
    }
    fn adopt(
        &mut self,
        target: &Target,
        proof: &WorkingReturnedLabelRestoration,
        data: &mut WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<()> {
        window.verify_window_custody()?;
        self.sources
            .owner()
            .accept_label_restoration_custody(proof)?;
        data.retirement().accept_label_restoration_custody(proof)?;
        data.accept_label_restoration(proof)?;
        self.scope.accept_returned_working_label(proof)?;
        let (_, actual) = self.actual(target)?;
        for path in &target.paths {
            self.current.insert(path.clone(), actual.clone());
        }
        self.fence(data, window)
    }
    fn finish_active(
        &mut self,
        data: &mut WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<()> {
        // If a syscall succeeded but its acknowledgement or metadata adoption
        // failed, read and seal that same held attempt before any strict stale
        // checkpoint or next mutation. restore() never repeats a completed set.
        for index in 0..self.active.len() {
            let ordinal = self.active[index].ordinal();
            let target = self
                .plan
                .targets
                .get(ordinal as usize)
                .ok_or("active returned target missing")?
                .clone();
            window.verify_window_custody()?;
            let (_, done) = self.active[index].classify()?;
            if !done {
                self.fence(data, window)?;
            }
            let (core, pin) = self.active[index].restore()?;
            let row = Row {
                ordinal,
                before: core.before.clone(),
                after: core.after.clone(),
                original_preimage: Some(self.active[index].original_pin().clone()),
                current_preimage: Some(self.active[index].preimage_pin().clone()),
                completed: Some(pin.clone()),
                recognized_history: None,
                target_write: core.before.attributes.get(LABEL)
                    != target.before.attributes.get(LABEL),
            };
            let proof = WorkingReturnedLabelRestoration::completed(
                self.sources.clone(),
                self.seal.clone(),
                target.paths.clone(),
                &self.active[index],
                core,
                &pin,
            )?;
            self.adopt(&target, &proof, data, window)?;
            self.rows.insert(ordinal, row);
        }
        self.active.clear();
        Ok(())
    }
    fn one(
        &mut self,
        target: &Target,
        data: &mut WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<()> {
        self.fence(data, window)?;
        let (file, current) = self.actual(target)?;
        let path = record_directory(&self.plan, target.ordinal);
        if !exists(&path)? || !Records::open(&path)?.exists("PREIMAGE.json")? {
            self.preparation_only(data)?;
            if exists(&path)? {
                Records::open(&path)?.verify_unpublished_preimage()?;
            }
            ensure(
                current == target.before,
                "unapplied returned target changed without a durable preimage",
            )?;
            self.rows.insert(
                target.ordinal,
                Row {
                    ordinal: target.ordinal,
                    before: current.clone(),
                    after: current,
                    original_preimage: None,
                    current_preimage: None,
                    completed: None,
                    recognized_history: None,
                    target_write: false,
                },
            );
            return Ok(());
        }
        let records = Records::open(&path)?;
        let original = self.original(target, file)?;
        let mut ours = target.before.attributes.clone();
        ours.insert(LABEL.into(), target.desired.clone());
        if current.attributes != ours
            && current.attributes.get(LABEL) == target.before.attributes.get(LABEL)
        {
            if let Some(history) = self.history(target, &original.recovery, &current, data)? {
                self.fence(data, window)?;
                let now = epoch(&records, data)?;
                let durability = now.sync_target(&original.recovery, &current)?;
                let value = json!({"schema":"droidloom.working-returned-label-observation.v1",
                    "candidate_id":self.sources.candidate(),"source_plan":self.seal.pin,
                    "original_preimage":original.pin,"actual_retirement":data.report(),
                    "recognized_history":history,"before":current,"after":current,
                    "target_metadata_durability":durability,"target_write":false});
                let pin = if now.exists("RESTORED-OBSERVATION.json")? {
                    let (_, _, raw) = now.read("RESTORED-OBSERVATION.json")?;
                    ensure(
                        serde_json::from_slice::<Value>(&raw)? == value,
                        "returned old-label observation changed",
                    )?;
                    record_pin(&now, "RESTORED-OBSERVATION.json")?
                } else {
                    now.publish("RESTORED-OBSERVATION.json", &value)?
                };
                for p in &target.paths {
                    self.current.insert(p.clone(), current.clone());
                }
                self.rows.insert(
                    target.ordinal,
                    Row {
                        ordinal: target.ordinal,
                        before: current.clone(),
                        after: current,
                        original_preimage: Some(original.pin),
                        current_preimage: None,
                        completed: Some(pin),
                        recognized_history: Some(history),
                        target_write: false,
                    },
                );
                return self.fence(data, window);
            }
        }
        if !original.records.exists("APPLIED.json")? {
            self.preparation_only(data)?;
            if current == target.before {
                self.rows.insert(
                    target.ordinal,
                    Row {
                        ordinal: target.ordinal,
                        before: current.clone(),
                        after: current,
                        original_preimage: Some(original.pin),
                        current_preimage: None,
                        completed: None,
                        recognized_history: None,
                        target_write: false,
                    },
                );
                return Ok(());
            }
            original.applied_readback()?;
        }
        let now = epoch(&records, data)?;
        let attempt = if now.exists("CURRENT-PREIMAGE.json")? {
            let pin = record_pin(&now, "CURRENT-PREIMAGE.json")?;
            RuntimeRestoreAttempt::reopen(original, now, &pin)?
        } else {
            let evolution = self.evolution(target, &current, data);
            if evolution.is_none() {
                let (_, applied) = RuntimeRestoreAttempt::applied(&original)?;
                for p in &target.paths {
                    runtime::admit_current(
                        &applied,
                        &current,
                        runtime::runtime_class(p, &self.plan.candidate_id),
                    )?;
                }
            }
            RuntimeRestoreAttempt::prepare_exact(original, now, data.report(), evolution)?
        };
        self.active.push(attempt);
        self.finish_active(data, window)
    }
    fn batch(
        &mut self,
        targets: &[Target],
        data: &mut WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<bool> {
        let mut admitted = Vec::new();
        for target in targets {
            self.fence(data, window)?;
            let (file, current) = self.actual(target)?;
            let path = record_directory(&self.plan, target.ordinal);
            if !exists(&path)? {
                return Ok(false);
            }
            let records = Records::open(&path)?;
            if !records.exists("PREIMAGE.json")? || !records.exists("APPLIED.json")? {
                return Ok(false);
            }
            let mut ours = target.before.attributes.clone();
            ours.insert(LABEL.into(), target.desired.clone());
            if current.attributes != ours {
                return Ok(false);
            }
            let next = records
                .path
                .join(format!("retirement-{}", data.report().sha256));
            if exists(&next)? && Records::open(&next)?.exists("CURRENT-PREIMAGE.json")? {
                return Ok(false);
            }
            let original = self.original(target, file)?;
            let evolution = self.evolution(target, &current, data);
            if evolution.is_none() {
                let (_, applied) = RuntimeRestoreAttempt::applied(&original)?;
                for path in &target.paths {
                    runtime::admit_current(
                        &applied,
                        &current,
                        runtime::runtime_class(path, &self.plan.candidate_id),
                    )?;
                }
            }
            admitted.push((original, records, evolution));
        }
        let mut records = RecordBatch::new();
        let mut pending = Vec::new();
        for (original, journal, evolution) in admitted {
            self.fence(data, window)?;
            pending.push(RuntimeRestoreAttempt::stage_exact(
                original,
                epoch(&journal, data)?,
                data.report(),
                evolution,
                &mut records,
            )?);
        }
        self.active = RuntimeRestoreAttempt::seal_preparations(pending, records)?;
        let mut provisional = Vec::new();
        for index in 0..self.active.len() {
            self.fence(data, window)?;
            provisional.push(self.active[index].restore_uncommitted()?);
            let (_, actual) = self.actual(&targets[index])?;
            ensure(
                actual == provisional[index].core.after,
                "returned ordinary batch alias changed after its actual xattr syscall",
            )?;
        }
        let refs = self.active.iter().collect::<Vec<_>>();
        let completed = RuntimeRestoreAttempt::complete_restorations(&refs, &provisional)?;
        for (index, (actual, pin)) in provisional.into_iter().zip(completed).enumerate() {
            let target = &targets[index];
            let row = Row {
                ordinal: target.ordinal,
                before: actual.core.before.clone(),
                after: actual.core.after.clone(),
                original_preimage: Some(self.active[index].original_pin().clone()),
                current_preimage: Some(self.active[index].preimage_pin().clone()),
                completed: Some(pin.clone()),
                recognized_history: None,
                target_write: actual.core.before.attributes.get(LABEL)
                    != target.before.attributes.get(LABEL),
            };
            let proof = WorkingReturnedLabelRestoration::completed(
                self.sources.clone(),
                self.seal.clone(),
                target.paths.clone(),
                &self.active[index],
                actual.core,
                &pin,
            )?;
            self.adopt(target, &proof, data, window)?;
            self.rows.insert(target.ordinal, row);
        }
        self.active.clear();
        Ok(true)
    }
    pub(crate) fn restore(
        &mut self,
        data: &mut WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<()> {
        self.finish_active(data, window)?;
        self.fence(data, window)?;
        let mut sensitive = self.sources.owner().label_sensitive_paths();
        sensitive.extend(data.retirement().label_sensitive_paths());
        sensitive.extend(data.label_sensitive_paths());
        sensitive.insert(PathBuf::from("/"));
        let is_sensitive = |t: &Target| t.paths.iter().any(|p| sensitive.contains(p));
        let mut index = 0;
        while index < self.plan.targets.len() {
            if self.rows.contains_key(&(index as u32)) {
                index += 1;
                continue;
            }
            let target = self.plan.targets[index].clone();
            if !is_sensitive(&target) {
                let end = (index + 1..self.plan.targets.len().min(index + BATCH_LIMIT))
                    .take_while(|i| {
                        !is_sensitive(&self.plan.targets[*i])
                            && !self.rows.contains_key(&(*i as u32))
                    })
                    .last()
                    .map_or(index + 1, |i| i + 1);
                let targets = self.plan.targets[index..end].to_vec();
                if self.batch(&targets, data, window)? {
                    index = end;
                    continue;
                }
            }
            self.one(&target, data, window)?;
            index += 1;
            if index % 1000 == 0 {
                eprintln!(
                    "working-return-labels targets={}/{}",
                    index,
                    self.plan.targets.len()
                );
            }
        }
        self.verify_complete(data, window)
    }
    fn verify_complete(
        &self,
        data: &WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<()> {
        self.fence(data, window)?;
        ensure(
            self.active.is_empty() && self.rows.len() == self.plan.targets.len(),
            "returned complete label result has unfinished targets",
        )?;
        self.seal.full_readback()?;
        for target in &self.plan.targets {
            let row = self
                .rows
                .get(&target.ordinal)
                .ok_or("returned label row missing")?;
            let (_, actual) = self.actual(target)?;
            ensure(
                row.ordinal == target.ordinal
                    && actual == row.after
                    && actual.handle == target.before.handle
                    && actual.attributes.get(LABEL) == target.before.attributes.get(LABEL),
                "returned complete target no longer carries its exact original label",
            )?;
        }
        self.scope
            .verify_returned_working_inventory(&self.inventory, &self.current, data)?;
        data.revalidate()?;
        self.fence(data, window)
    }
    pub(crate) fn seal(
        self,
        data: &WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<WorkingReturnedLabels> {
        self.verify_complete(data, window)?;
        let path = self
            .plan
            .work
            .join(format!("LABELS-RETURNED-{}.json", data.report().sha256));
        let value = json!({"schema":"droidloom.working-labels-returned.v1","candidate_id":self.sources.candidate(),
            "normal_sources":self.plan.normal_sources,"source_plan":self.seal.pin,
            "actual_data_retirement":data.report(),"actual_boot_retirement":data.retirement().report_pin(),
            "actual_freezer":window.intent_pin(),"targets":self.rows.values().collect::<Vec<_>>(),
            "complete_target_count":self.rows.len(),"original_backing_labels_written":false,
            "normal_return_observed":data.retirement().normal_return_observed(),"production_ready":false});
        let directory = Records::open(&self.plan.work)?;
        let name = path
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or("returned label report name")?;
        let report = if directory.exists(name)? {
            let (_, _, body) = directory.read(name)?;
            ensure(
                serde_json::from_slice::<Value>(&body)? == value,
                "returned completion report differs from the actual held result",
            )?;
            record_pin(&directory, name)?
        } else {
            directory.publish(name, &value)?
        };
        let (report_file, _) = files::open_pin(&report)?;
        let report_snapshot = snapshot(&report_file)?;
        Ok(WorkingReturnedLabels {
            transaction: self,
            report,
            report_file,
            report_snapshot,
        })
    }
}
impl WorkingReturnedLabels {
    pub(crate) fn require_data(
        &self,
        data: &WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<()> {
        ensure(
            Rc::ptr_eq(&self.transaction.sources, data.sources()),
            "returned labels cannot transfer to another fresh data owner",
        )?;
        ensure(
            snapshot(&self.report_file)? == self.report_snapshot
                && snapshot(
                    &fs::Tree::open("/", 0)?.file(&fs::absolute_string(&self.report.path)?)?,
                )? == self.report_snapshot,
            "complete returned label report lost its actual held inode",
        )?;
        self.transaction.verify_complete(data, window)
    }
    pub(crate) fn report(&self) -> &FilePin {
        &self.report
    }
    pub(crate) fn preserved_metadata(&self, paths: &BTreeSet<PathBuf>) -> Result<Value> {
        self.transaction.sources.revalidate_custody()?;
        let mut result = BTreeMap::new();
        for path in paths {
            let target = self
                .transaction
                .plan
                .targets
                .iter()
                .find(|t| t.paths.contains(path))
                .ok_or("normal package preservation target outside complete returned plan")?;
            ensure(
                !target.separate,
                "normal package metadata cannot select private data",
            )?;
            let actual = &self.transaction.rows[&target.ordinal].after;
            ensure(
                snapshot(&self.transaction.scope.open_named(path)?)? == *actual,
                "normal preserved returned inode changed",
            )?;
            result.insert(
                path.clone(),
                json!({"prelabel":target.before,"restored":actual}),
            );
        }
        Ok(json!({"paths":result}))
    }
}
