//! Full normal H2 labels over the retained original host and exchanged working
//! pair. Durable inode attempts are the same physical core used by the original
//! writer; ownership, plan, batch adoption and completion are working-specific.
use super::super::{
    LABEL, LabelDerivation, PlanSeal, Snapshot, plan,
    scope::{Entry, Inventory, RootScope, matcher_type},
    snapshot,
    working::{
        Origin, Restoration, WorkingEvolutionProof, WorkingLabelBatch, WorkingLabelDerivation,
    },
};
use super::runtime::{EvolutionKind, ExactEvolution, RuntimeRestoreAttempt};
use super::{BATCH_LIMIT, DurableAttempt, RecordBatch, Records, sync_targets};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_qualification::{
        PublishedWorkingBootFiles, WorkingPackages, WorkingQuiescence, WorkingRuntimeSources,
    },
    ensure, fs,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
    fs::File,
    path::{Path, PathBuf},
    rc::Rc,
    sync::Arc,
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Target {
    pub(super) ordinal: u32,
    pub(super) paths: Vec<PathBuf>,
    pub(super) before: Snapshot,
    pub(super) desired: Vec<u8>,
    pub(super) separate: bool,
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Plan {
    pub(super) schema: String,
    pub(super) candidate_id: String,
    pub(super) work: PathBuf,
    pub(super) boot_intent: FilePin,
    pub(super) boot_publication: FilePin,
    pub(super) normal_sources: FilePin,
    pub(super) scope: Inventory,
    pub(super) targets: Vec<Target>,
    pub(super) actual_lookup_commands: FilePin,
}
#[derive(Clone, Copy, PartialEq, Eq)]
enum Phase {
    Applying,
    Applied,
    Restoring,
    Restored,
}
struct Shared {
    scope: RootScope,
    extra: BTreeMap<PathBuf, File>,
    current: BTreeMap<PathBuf, Snapshot>,
    phase: Phase,
    selection: Option<Rc<crate::cold_original_data::WorkingSelectionProof>>,
    grub: Option<Rc<super::super::WorkingGrubProof>>,
}
#[derive(Clone, Copy, PartialEq, Eq)]
enum AttemptKind {
    Application,
    Restoration,
}
struct Active {
    index: usize,
    attempt: DurableAttempt,
}

/// Its constructor consumes actual source/boot/freezer observations, not a
/// parsed label plan. Every error retains the per-inode recovery descriptions.
pub(crate) struct WorkingLabelTransaction {
    origin: Rc<Origin>,
    plan: Rc<Plan>,
    shared: Rc<RefCell<Shared>>,
    active: Vec<Active>,
    active_kind: AttemptKind,
    evolved: Option<(usize, RuntimeRestoreAttempt, WorkingEvolutionProof)>,
    pending: Option<WorkingLabelBatch>,
    completed: BTreeSet<usize>,
    application_records: BTreeMap<usize, FilePin>,
    restoration_records: BTreeMap<usize, FilePin>,
    forward_failed: bool,
}
pub(crate) struct WorkingLabelsApplied {
    origin: Rc<Origin>,
    plan: Rc<Plan>,
    shared: Rc<RefCell<Shared>>,
    report: FilePin,
}
pub(crate) struct WorkingLabelsRestored {
    origin: Rc<Origin>,
    plan: Rc<Plan>,
    shared: Rc<RefCell<Shared>>,
    report: FilePin,
}
fn record_pin(records: &Records, name: &str) -> Result<FilePin> {
    let (_, _, body) = records.read(name)?;
    Ok(FilePin {
        path: records.path.join(name),
        bytes: body.len() as u64,
        sha256: fs::digest(&body),
    })
}
fn seal_report(work: &Path, name: &str, value: &Value) -> Result<FilePin> {
    let records = Records::open(work)?;
    if records.exists(name)? {
        let (_, _, bytes) = records.read(name)?;
        ensure(
            serde_json::from_slice::<Value>(&bytes)? == *value,
            "working completion record differs from the actual retained transaction",
        )?;
        record_pin(&records, name)
    } else {
        records.publish(name, value)
    }
}
fn record_directory(work: &Path, index: usize) -> PathBuf {
    work.join(format!("inode-{index:08}"))
}
fn held(shared: &Shared, target: &Target) -> Result<File> {
    let path = target
        .paths
        .first()
        .ok_or("working label target has no normal path")?;
    if target.separate {
        shared
            .extra
            .get(path)
            .ok_or("working separate target lost its actual OFD")?
            .try_clone()
            .map_err(Into::into)
    } else {
        shared.scope.open_named(path)
    }
}
fn verify_target(shared: &Shared, target: &Target, expected: &Snapshot) -> Result<()> {
    for path in &target.paths {
        let file = if target.separate {
            shared
                .extra
                .get(path)
                .ok_or("working separate alias lost its held inode")?
                .try_clone()?
        } else {
            shared.scope.open_named(path)?
        };
        ensure(
            snapshot(&file)? == *expected,
            "working full label target changed F9/generation/xattrs",
        )?;
    }
    Ok(())
}
fn verify_inventory(plan: &Plan, shared: &Shared) -> Result<()> {
    match &shared.selection {
        Some(proof) => {
            shared
                .scope
                .verify_working_selection_inventory(&plan.scope, &shared.current, proof)?
        }
        None => shared
            .scope
            .verify_inventory_updates(&plan.scope, &shared.current)?,
    };
    for target in &plan.targets {
        let expected = shared
            .current
            .get(&target.paths[0])
            .unwrap_or(&target.before);
        verify_target(shared, target, expected)?;
    }
    Ok(())
}
fn metadata(plan: &Plan, shared: &Shared, paths: &BTreeSet<PathBuf>) -> Result<Value> {
    let mut out = BTreeMap::new();
    for path in paths {
        let target = plan
            .targets
            .iter()
            .find(|target| target.paths.iter().any(|p| p == path))
            .ok_or("normal preserved path is outside the complete actual working plan")?;
        ensure(
            !target.separate,
            "normal package preservation cannot select private Android data",
        )?;
        let after = shared.current.get(path).unwrap_or(&target.before);
        ensure(
            snapshot(&shared.scope.open_named(path)?)? == *after,
            "normal preserved inode changed after working label restoration",
        )?;
        out.insert(
            path.clone(),
            json!({"prelabel":target.before,"restored":after}),
        );
    }
    Ok(json!({"paths":out}))
}
// Intents for the complete bounded cohort are durable before its first reverse
// effect. An interrupted reverse is reconciled from the same recovery FDs;
// an already-restored inode is never written again merely to recreate a receipt.
fn restore_attempts_batched(
    attempts: &[&DurableAttempt],
    guard: &mut impl FnMut() -> Result<()>,
) -> Result<Vec<Snapshot>> {
    ensure(
        (1..=BATCH_LIMIT).contains(&attempts.len()),
        "bounded actual restore cohort required",
    )?;
    let mut observations = Vec::new();
    let mut intents = RecordBatch::new();
    for attempt in attempts {
        guard()?;
        attempt.validate_intent()?;
        let already = attempt.restored_intent()?;
        let observed = attempt.classify(already)?;
        if !already {
            intents.stage(
                &attempt.records,
                "RESTORE-INTENT.json",
                &json!({
                    "schema":"droidloom.original-label-restore-intent.v1", "preimage":attempt.pin
                }),
            )?;
        }
        observations.push(observed);
    }
    intents.publish()?;
    for (attempt, (observed, applied)) in attempts.iter().zip(&observations) {
        guard()?;
        attempt.validate_intent()?;
        ensure(
            attempt.restored_intent()? && snapshot(&attempt.recovery)? == *observed,
            "working label changed between durable reverse intent and effect",
        )?;
        if *applied {
            super::set(
                &attempt.recovery,
                &attempt.preimage.attribute,
                attempt
                    .preimage
                    .before
                    .attributes
                    .get(&attempt.preimage.attribute)
                    .map(Vec::as_slice),
            )?;
        }
        guard()?;
    }
    let after = attempts
        .iter()
        .map(|attempt| {
            let (after, applied) = attempt.classify(true)?;
            ensure(
                !applied && after.attributes == attempt.preimage.before.attributes,
                "working reverse did not restore the full original attribute inventory",
            )?;
            Ok(after)
        })
        .collect::<Result<Vec<_>>>()?;
    let targets = attempts
        .iter()
        .zip(&after)
        .map(|(attempt, after)| (&attempt.records, &attempt.recovery, after))
        .collect::<Vec<_>>();
    let barriers = sync_targets(&targets)?;
    let mut completions = RecordBatch::new();
    for (((attempt, (observed, _)), after), barrier) in
        attempts.iter().zip(&observations).zip(&after).zip(barriers)
    {
        if attempt.records.exists("RESTORED.json")? {
            let (_, _, bytes) = attempt.records.read("RESTORED.json")?;
            let record: Value = serde_json::from_slice(&bytes)?;
            ensure(
                record["schema"] == "droidloom.original-label-restored.v1"
                    && record["preimage"] == serde_json::to_value(&attempt.pin)?
                    && record["after"] == serde_json::to_value(after)?
                    && record["target_metadata_durability"]["operation"] == "syncfs"
                    && record["target_metadata_durability"]["filesystem_dev"] == after.identity.dev,
                "existing reverse completion differs from its actual same held inode",
            )?;
        } else {
            completions.stage(
                &attempt.records,
                "RESTORED.json",
                &json!({
                    "schema":"droidloom.original-label-restored.v1","preimage":attempt.pin,
                    "observed_before_restore":observed,"after":after,
                    "target_metadata_durability":barrier
                }),
            )?;
        }
    }
    completions.publish()?;
    for (attempt, after) in attempts.iter().zip(&after) {
        guard()?;
        attempt.validate_intent()?;
        ensure(
            snapshot(&attempt.recovery)? == *after,
            "working restored inode changed after durable batch completion",
        )?;
    }
    Ok(after)
}

impl WorkingLabelTransaction {
    pub(crate) fn prepare(
        boot: &PublishedWorkingBootFiles,
        frozen: &WorkingQuiescence,
    ) -> Result<Self> {
        boot.guard()?;
        let source = boot.runtime().source();
        frozen.require_source(source)?;
        source.prepare_working_label_custody()?;
        let extras = source.working_label_targets()?;
        ensure(
            extras.len() == 11,
            "working labels lost the ten pair inodes and selection",
        )?;
        let scope = RootScope::original(&source.retained_cold_clone()?)?;
        let inventory = scope.collect()?;
        let work = source.work().join("working-labels");
        files::private_dir(&work)?;
        let lookup = work.join("normal-contexts");
        files::private_dir(&lookup)?;
        let mut entries = inventory.entries.clone();
        let ordinary = entries.len();
        let mut extra = BTreeMap::new();
        for (path, file) in extras {
            let observed = snapshot(&file)?;
            entries.push(Entry {
                path: path.clone(),
                matcher_type: matcher_type(observed.identity.mode)?.into(),
                snapshot: observed,
            });
            ensure(
                extra.insert(path, file).is_none(),
                "duplicate actual separate working target",
            )?;
        }
        let (labels, commands) = source.label_sources().lookup_entries(&entries, &lookup)?;
        plan::verify_hardlink_labels(
            &entries
                .iter()
                .map(|e| (&e.snapshot, e.path.as_path()))
                .collect::<Vec<_>>(),
            &labels,
        )?;
        let mut groups: BTreeMap<(u64, u64), Target> = BTreeMap::new();
        let mut names = BTreeSet::new();
        for (index, (entry, desired)) in entries.into_iter().zip(labels).enumerate() {
            ensure(
                names.insert(entry.path.clone()),
                "ambiguous normal working label alias",
            )?;
            let key = (entry.snapshot.identity.dev, entry.snapshot.identity.ino);
            let separate = index >= ordinary;
            if let Some(target) = groups.get_mut(&key) {
                ensure(
                    target.before == entry.snapshot
                        && target.desired == desired
                        && target.separate == separate,
                    "working hardlink differs across source scope or normal context",
                )?;
                target.paths.push(entry.path);
            } else {
                groups.insert(
                    key,
                    Target {
                        ordinal: 0,
                        paths: vec![entry.path],
                        before: entry.snapshot,
                        desired,
                        separate,
                    },
                );
            }
        }
        let mut targets = groups.into_values().collect::<Vec<_>>();
        for (index, target) in targets.iter_mut().enumerate() {
            target.ordinal = index.try_into()?;
        }
        let actual = Plan {
            schema: "droidloom.working-label-transaction-plan.v1".into(),
            candidate_id: source.candidate().into(),
            work: work.clone(),
            boot_intent: source.boot_intent().clone(),
            boot_publication: boot.summary().clone(),
            normal_sources: source.label_sources().source_pin().clone(),
            scope: inventory,
            targets,
            actual_lookup_commands: commands,
        };
        let shared = Shared {
            scope,
            extra,
            current: BTreeMap::new(),
            phase: Phase::Applying,
            selection: None,
            grub: None,
        };
        verify_inventory(&actual, &shared)?;
        frozen.require_source(source)?;
        boot.guard()?;
        let pin = plan::save(&work.join("LABEL-PLAN.json"), &actual)?;
        let seal = Arc::new(PlanSeal::open(&pin)?);
        seal.full_readback()?;
        let value = Self {
            origin: Rc::new(Origin {
                source: source.label_source_identity()?,
                plan: seal,
            }),
            plan: Rc::new(actual),
            shared: Rc::new(RefCell::new(shared)),
            active: Vec::new(),
            active_kind: AttemptKind::Application,
            evolved: None,
            pending: None,
            completed: BTreeSet::new(),
            application_records: BTreeMap::new(),
            restoration_records: BTreeMap::new(),
            forward_failed: false,
        };
        value.guard_source(boot, frozen)?;
        Ok(value)
    }
    pub(crate) fn accept_grub(
        &mut self,
        boot: &mut PublishedWorkingBootFiles,
        frozen: &WorkingQuiescence,
        proof: Rc<super::super::WorkingGrubProof>,
    ) -> Result<()> {
        frozen.require_identity(&self.origin.source)?;
        proof.require_identity(&self.origin.source)?;
        proof.guard()?;
        ensure(
            serde_json::to_value(proof.label_plan())?
                == serde_json::to_value(&self.origin.plan.pin)?,
            "working GRUB mutation belongs to another completed normal label plan",
        )?;
        let path = PathBuf::from("/boot/grub/grubenv");
        {
            let shared = self.shared.borrow();
            ensure(
                shared.phase == Phase::Applied && self.active.is_empty() && self.pending.is_none(),
                "working GRUB mutation overlaps an unfinished normal label operation",
            )?;
            let repeated = shared
                .grub
                .as_ref()
                .is_some_and(|old| old.report().sha256 == proof.report().sha256);
            let expected = if repeated {
                proof.after()
            } else {
                proof.before()
            };
            ensure(
                shared.current.get(&path) == Some(expected),
                "working GRUB did not begin at this exact normal label checkpoint",
            )?;
        }
        boot.accept_working_grub(&proof)?;
        let mut shared = self.shared.borrow_mut();
        shared.current.insert(path, proof.after().clone());
        shared.grub = Some(proof);
        drop(shared);
        verify_inventory(&self.plan, &self.shared.borrow())?;
        boot.guard_label_custody()
    }
    pub(crate) fn accept_selection(
        &mut self,
        boot: &mut PublishedWorkingBootFiles,
        frozen: &WorkingQuiescence,
        proof: Rc<crate::cold_original_data::WorkingSelectionProof>,
    ) -> Result<()> {
        frozen.require_identity(&self.origin.source)?;
        proof.require_identity(&self.origin.source)?;
        proof.guard()?;
        ensure(
            serde_json::to_value(proof.label_plan())?
                == serde_json::to_value(&self.origin.plan.pin)?,
            "working selection belongs to another completed normal label plan",
        )?;
        let parent = PathBuf::from("/etc/droidloom/production");
        let candidate = PathBuf::from("/etc/droidloom/production/selected.json");
        {
            let shared = self.shared.borrow();
            ensure(
                shared.phase == Phase::Applied && self.active.is_empty() && self.pending.is_none(),
                "working selection entered an unfinished label batch or restoration",
            )?;
            let repeated = shared
                .selection
                .as_ref()
                .is_some_and(|old| old.report().sha256 == proof.report().sha256);
            let expected_parent = if repeated {
                &proof.parent_after().snapshot
            } else {
                &proof.parent_before().snapshot
            };
            let expected_candidate = if repeated {
                proof.candidate_after()
            } else {
                proof.candidate_before()
            };
            ensure(
                shared.current.get(&parent) == Some(expected_parent)
                    && shared.current.get(&candidate) == Some(expected_candidate),
                "working selected rename did not start at both actual normal label checkpoints",
            )?;
        }
        boot.accept_selection(Rc::clone(&proof))?;
        let mut shared = self.shared.borrow_mut();
        shared
            .current
            .insert(parent, proof.parent_after().snapshot.clone());
        shared
            .current
            .insert(candidate, proof.candidate_after().clone());
        shared.selection = Some(proof);
        drop(shared);
        verify_inventory(&self.plan, &self.shared.borrow())?;
        boot.guard_label_custody()?;
        frozen.verify()
    }
    fn guard_source(
        &self,
        boot: &PublishedWorkingBootFiles,
        frozen: &WorkingQuiescence,
    ) -> Result<()> {
        self.origin.source.require_source(boot.runtime().source())?;
        self.origin.plan.revalidate()?;
        self.origin.source.revalidate_normal_source()?;
        frozen.require_source(boot.runtime().source())?;
        boot.guard_label_custody()?;
        self.shared
            .try_borrow()
            .map_err(|_| "working label state already borrowed")?
            .scope
            .revalidate()
    }
    fn guard(
        &self,
        boot: &PublishedWorkingBootFiles,
        packages: &WorkingPackages,
        frozen: &WorkingQuiescence,
    ) -> Result<()> {
        self.guard_source(boot, frozen)?;
        packages.guard_label_custody()
    }
    fn attempt(&self, index: usize) -> Result<DurableAttempt> {
        let target = &self.plan.targets[index];
        let records = Records::open(&record_directory(&self.plan.work, index))?;
        let pin = record_pin(&records, "PREIMAGE.json")?;
        let file = held(&self.shared.borrow(), target)?;
        let attempt = DurableAttempt::reopen(records, &pin, file)?;
        ensure(
            attempt.preimage.before == target.before
                && attempt.preimage.desired == target.desired
                && attempt.preimage.attribute == LABEL
                && attempt.preimage.ordinal == target.ordinal
                && attempt.preimage.candidate_id == self.plan.candidate_id
                && attempt.preimage.logical_path == target.paths[0]
                && serde_json::to_value(&attempt.preimage.source_plan)?
                    == serde_json::to_value(&self.origin.plan.pin)?,
            "working inode journal differs from its actual immutable normal plan",
        )?;
        Ok(attempt)
    }
    fn adopt_pending(
        &mut self,
        boot: &mut PublishedWorkingBootFiles,
        packages: &mut WorkingPackages,
        frozen: &WorkingQuiescence,
    ) -> Result<()> {
        let Some(batch) = self.pending.as_ref() else {
            return Ok(());
        };
        frozen.verify()?;
        batch.require_source(boot.runtime().source())?;
        self.shared.borrow_mut().scope.accept_working_batch(batch)?;
        packages.accept_working_label_batch(batch)?;
        boot.accept_working_label_batch(batch)?;
        packages.guard_label_custody()?;
        frozen.verify()?;
        for record in batch.records() {
            let index = record.ordinal as usize;
            ensure(
                index < self.plan.targets.len(),
                "working batch ordinal outside complete plan",
            )?;
            let target = &self.plan.targets[index];
            ensure(
                record.paths == target.paths,
                "working batch changed its actual normal aliases",
            )?;
            for path in &record.paths {
                self.shared
                    .borrow_mut()
                    .current
                    .insert(path.clone(), record.core.after.clone());
            }
            if record.restoration.is_some() {
                self.completed.remove(&index);
                self.restoration_records
                    .insert(index, record.restoration.as_ref().unwrap().restored.clone());
            } else {
                self.completed.insert(index);
                self.application_records.insert(
                    index,
                    record
                        .applied
                        .as_ref()
                        .ok_or("working applied record missing")?
                        .clone(),
                );
            }
        }
        self.active.clear();
        self.evolved = None;
        self.pending = None;
        self.guard(boot, packages, frozen)
    }
    fn complete_active_applications(&mut self) -> Result<()> {
        ensure(
            self.pending.is_none() && self.active_kind == AttemptKind::Application,
            "working unresolved batch cannot change operation",
        )?;
        let mut indices = Vec::new();
        let mut cores = Vec::new();
        for (offset, active) in self.active.iter().enumerate() {
            let now = snapshot(&active.attempt.recovery)?;
            let mut expected = active.attempt.preimage.before.attributes.clone();
            expected.insert(LABEL.into(), active.attempt.preimage.desired.clone());
            if now.attributes == expected {
                cores.push(active.attempt.readback_uncommitted()?);
                indices.push(offset);
            } else {
                ensure(
                    now == active.attempt.preimage.before,
                    "working interrupted label has an unknown actual outcome",
                )?;
            }
        }
        if cores.is_empty() {
            self.active.clear();
            return Ok(());
        }
        let references = indices
            .iter()
            .map(|&i| &self.active[i].attempt)
            .collect::<Vec<_>>();
        let applications = DurableAttempt::complete_applications(&references, &cores)?;
        let records = indices
            .into_iter()
            .zip(cores)
            .zip(applications)
            .map(|((i, core), applied)| {
                let active = &self.active[i];
                let target = &self.plan.targets[active.index];
                WorkingLabelDerivation {
                    origin: Rc::clone(&self.origin),
                    ordinal: target.ordinal,
                    paths: target.paths.clone(),
                    preimage: active.attempt.pin.clone(),
                    applied: Some(applied),
                    restoration: None,
                    core,
                }
            })
            .collect();
        self.pending = Some(WorkingLabelBatch {
            origin: Rc::clone(&self.origin),
            records,
        });
        self.pending.as_ref().unwrap().revalidate()
    }
    pub(crate) fn apply(
        &mut self,
        boot: &mut PublishedWorkingBootFiles,
        packages: &mut WorkingPackages,
        frozen: &WorkingQuiescence,
    ) -> Result<WorkingLabelsApplied> {
        ensure(
            !self.forward_failed && self.shared.borrow().phase == Phase::Applying,
            "working label forward cannot be replayed after failure or restoration",
        )?;
        let result = self.apply_inner(boot, packages, frozen);
        if result.is_err() {
            self.forward_failed = true;
        }
        result
    }
    fn apply_inner(
        &mut self,
        boot: &mut PublishedWorkingBootFiles,
        packages: &mut WorkingPackages,
        frozen: &WorkingQuiescence,
    ) -> Result<WorkingLabelsApplied> {
        self.guard(boot, packages, frozen)?;
        self.origin.plan.full_readback()?;
        let mut start = 0;
        while start < self.plan.targets.len() {
            self.guard(boot, packages, frozen)?;
            let end = (start + BATCH_LIMIT).min(self.plan.targets.len());
            let mut records = RecordBatch::new();
            let mut staged = Vec::new();
            for index in start..end {
                let target = &self.plan.targets[index];
                let shared = self.shared.borrow();
                verify_target(&shared, target, &target.before)?;
                let file = held(&shared, target)?;
                let directory = record_directory(&self.plan.work, index);
                files::private_dir(&directory)?;
                let records_for_inode = Records::open(&directory)?;
                staged.push(DurableAttempt::stage(
                    records_for_inode,
                    file,
                    &self.plan.candidate_id,
                    &self.origin.plan.pin,
                    target.ordinal,
                    &target.paths[0],
                    &target.desired,
                    LABEL,
                    &mut records,
                )?);
            }
            let attempts = DurableAttempt::seal_preparations(staged, records)?;
            self.active = attempts
                .into_iter()
                .zip(start..end)
                .map(|(attempt, index)| Active { index, attempt })
                .collect();
            self.active_kind = AttemptKind::Application;
            for active in &self.active {
                frozen.verify()?;
                self.origin.source.revalidate_normal_source()?;
                active.attempt.apply_uncommitted()?;
            }
            self.complete_active_applications()?;
            self.adopt_pending(boot, packages, frozen)?;
            self.active.clear();
            start = end;
            if start % 1024 < BATCH_LIMIT || start == self.plan.targets.len() {
                eprintln!(
                    "working-label-apply targets={}/{}",
                    start,
                    self.plan.targets.len()
                );
            }
        }
        ensure(
            self.completed.len() == self.plan.targets.len(),
            "working labels lost a durable target completion",
        )?;
        self.guard(boot, packages, frozen)?;
        verify_inventory(&self.plan, &self.shared.borrow())?;
        self.origin.plan.full_readback()?;
        boot.guard()?;
        let report = seal_report(
            &self.plan.work,
            "LABELS-APPLIED.json",
            &json!({
                "schema":"droidloom.working-labels-applied.v1","candidate_id":self.plan.candidate_id,
                "source_plan":self.origin.plan.pin,"boot_intent":self.plan.boot_intent,
                "applications_count":self.application_records.len(),
            "applications_index_sha256":fs::digest(&serde_json::to_vec(&self.application_records)?),
                "complete_actual_target_count":self.plan.targets.len(),"selected_published":false,"boot_armed":false
            }),
        )?;
        self.shared.borrow_mut().phase = Phase::Applied;
        let actual = WorkingLabelsApplied {
            origin: Rc::clone(&self.origin),
            plan: Rc::clone(&self.plan),
            shared: Rc::clone(&self.shared),
            report,
        };
        actual.require_source(boot.runtime().source())?;
        Ok(actual)
    }
    fn prepare_evolved_restoration(
        &self,
        index: usize,
        proof: WorkingEvolutionProof,
    ) -> Result<(usize, RuntimeRestoreAttempt, WorkingEvolutionProof)> {
        proof.require_identity(&self.origin.source)?;
        proof.require_retired()?;
        let target = &self.plan.targets[index];
        let current = self
            .shared
            .borrow()
            .current
            .get(&target.paths[0])
            .ok_or("selected working current checkpoint absent")?
            .clone();
        verify_target(&self.shared.borrow(), target, &current)?;
        let records = Records::open(&record_directory(&self.plan.work, index))?;
        let original_pin = record_pin(&records, "PREIMAGE.json")?;
        let original = DurableAttempt::load_unclassified(
            records,
            &original_pin,
            held(&self.shared.borrow(), target)?,
        )?;
        ensure(
            original.preimage.before == target.before
                && original.preimage.desired == target.desired
                && original.preimage.logical_path == target.paths[0]
                && original.preimage.ordinal == target.ordinal
                && original.preimage.candidate_id == self.plan.candidate_id
                && serde_json::to_value(&original.preimage.source_plan)?
                    == serde_json::to_value(&self.origin.plan.pin)?,
            "working selected restore original preimage differs from the actual full normal plan",
        )?;
        let (_, applied) = RuntimeRestoreAttempt::applied(&original)?;
        proof.require_label_evolution(&target.paths[0], &applied, &current)?;
        let directory = record_directory(&self.plan.work, index).join(match &proof {
            WorkingEvolutionProof::Selection(_) => "working-selected-restoration",
            WorkingEvolutionProof::Grub(_) => "working-grub-restoration",
        });
        files::private_dir(&directory)?;
        let records = Records::open(&directory)?;
        let attempt = if records.exists("CURRENT-PREIMAGE.json")? {
            let pin = record_pin(&records, "CURRENT-PREIMAGE.json")?;
            RuntimeRestoreAttempt::reopen(original, records, &pin)?
        } else {
            RuntimeRestoreAttempt::prepare_exact(
                original,
                records,
                proof.report(),
                Some(ExactEvolution {
                    kind: match &proof {
                        WorkingEvolutionProof::Selection(_) => {
                            EvolutionKind::WorkingSelectionRename
                        }
                        WorkingEvolutionProof::Grub(_) => EvolutionKind::WorkingGrubEnvironment,
                    },
                    actual: current.clone(),
                    evidence: proof.report().clone(),
                }),
            )?
        };
        ensure(
            attempt.current_snapshot() == &current,
            "working selected durable current preimage changed",
        )?;
        Ok((index, attempt, proof))
    }
    fn restore_selected_active(&mut self, frozen: &WorkingQuiescence) -> Result<()> {
        let (index, attempt, proof) = self
            .evolved
            .as_ref()
            .ok_or("working selected restoration absent")?;
        ensure(
            self.pending.is_none() && self.active.is_empty(),
            "working selected reverse overlaps another unresolved label batch",
        )?;
        frozen.verify()?;
        self.origin.source.revalidate_normal_source()?;
        let (core, restored) = attempt.restore()?;
        frozen.verify()?;
        self.origin.source.revalidate_normal_source()?;
        let target = &self.plan.targets[*index];
        let record = WorkingLabelDerivation {
            origin: Rc::clone(&self.origin),
            ordinal: target.ordinal,
            paths: target.paths.clone(),
            preimage: attempt.original_pin().clone(),
            applied: Some(
                self.application_records
                    .get(index)
                    .ok_or("selected application receipt absent")?
                    .clone(),
            ),
            restoration: Some(Restoration {
                original: target.before.clone(),
                intent: attempt.preimage_pin().clone(),
                restored,
                evolution: Some(proof.clone()),
            }),
            core,
        };
        self.pending = Some(WorkingLabelBatch {
            origin: Rc::clone(&self.origin),
            records: vec![record],
        });
        self.pending.as_ref().unwrap().revalidate()
    }
    fn restore_active(&mut self, frozen: &WorkingQuiescence) -> Result<()> {
        ensure(
            self.pending.is_none() && self.active_kind == AttemptKind::Restoration,
            "working restoration cannot replace an unresolved application",
        )?;
        let attempts = self
            .active
            .iter()
            .map(|active| &active.attempt)
            .collect::<Vec<_>>();
        let afters = restore_attempts_batched(&attempts, &mut || {
            frozen.verify()?;
            self.origin.source.revalidate_normal_source()
        })?;
        let mut records = Vec::new();
        for (active, after) in self.active.iter().zip(afters) {
            let restored = record_pin(&active.attempt.records, "RESTORED.json")?;
            // This is the actual adopted APPLIED checkpoint. A lost completion
            // can observe the already-restored inode, never fabricate a new
            // APPLIED predecessor from that later observation.
            let before = self
                .shared
                .borrow()
                .current
                .get(&self.plan.targets[active.index].paths[0])
                .ok_or("working reverse lost its actual adopted application")?
                .clone();
            let applied = if active.attempt.records.exists("APPLIED.json")? {
                Some(record_pin(&active.attempt.records, "APPLIED.json")?)
            } else {
                None
            };
            let core = LabelDerivation {
                file: active.attempt.recovery.try_clone()?,
                before,
                after,
            };
            records.push(WorkingLabelDerivation {
                origin: Rc::clone(&self.origin),
                ordinal: active.index.try_into()?,
                paths: self.plan.targets[active.index].paths.clone(),
                preimage: active.attempt.pin.clone(),
                applied,
                restoration: Some(Restoration {
                    original: active.attempt.preimage.before.clone(),
                    intent: record_pin(&active.attempt.records, "RESTORE-INTENT.json")?,
                    restored,
                    evolution: None,
                }),
                core,
            });
        }
        if !records.is_empty() {
            self.pending = Some(WorkingLabelBatch {
                origin: Rc::clone(&self.origin),
                records,
            });
            self.pending.as_ref().unwrap().revalidate()?;
        }
        Ok(())
    }
    pub(crate) fn restore(
        &mut self,
        boot: &mut PublishedWorkingBootFiles,
        packages: &mut WorkingPackages,
        frozen: &WorkingQuiescence,
    ) -> Result<WorkingLabelsRestored> {
        self.forward_failed = true;
        if self.shared.borrow().phase == Phase::Restored {
            return self.restored_result(boot.runtime().source());
        }
        frozen.verify()?;
        self.adopt_pending(boot, packages, frozen)?;
        if self.evolved.is_some() {
            self.restore_selected_active(frozen)?;
            self.adopt_pending(boot, packages, frozen)?;
        }
        if !self.active.is_empty() {
            match self.active_kind {
                AttemptKind::Application => self.complete_active_applications()?,
                AttemptKind::Restoration => self.restore_active(frozen)?,
            }
            self.adopt_pending(boot, packages, frozen)?;
            self.active.clear();
        }
        self.shared.borrow_mut().phase = Phase::Restoring;
        while !self.completed.is_empty() {
            self.guard(boot, packages, frozen)?;
            let evolution = self.shared.borrow().selection.clone();
            if let Some(proof) = evolution {
                ensure(
                    !proof.selected(),
                    "working label reverse needs actual selected withdrawal",
                )?;
                let selected = self.completed.iter().rev().copied().find(|index| {
                    let path = self.plan.targets[*index].paths[0].as_path();
                    path == Path::new("/etc/droidloom/production")
                        || path == Path::new("/etc/droidloom/production/selected.json")
                });
                if let Some(index) = selected {
                    self.evolved = Some(self.prepare_evolved_restoration(
                        index,
                        WorkingEvolutionProof::Selection(proof),
                    )?);
                    self.restore_selected_active(frozen)?;
                    self.adopt_pending(boot, packages, frozen)?;
                    continue;
                }
            }
            let grub = self.shared.borrow().grub.clone();
            if let Some(proof) = grub {
                ensure(
                    !proof.armed(),
                    "working labels cannot reverse an armed GRUB selection",
                )?;
                let index =
                    self.completed.iter().rev().copied().find(|i| {
                        self.plan.targets[*i].paths[0] == Path::new("/boot/grub/grubenv")
                    });
                if let Some(index) = index {
                    self.evolved =
                        Some(self.prepare_evolved_restoration(
                            index,
                            WorkingEvolutionProof::Grub(proof),
                        )?);
                    self.restore_selected_active(frozen)?;
                    self.adopt_pending(boot, packages, frozen)?;
                    continue;
                }
            }
            let indices = self
                .completed
                .iter()
                .rev()
                .take(BATCH_LIMIT)
                .copied()
                .collect::<Vec<_>>();
            self.active = indices
                .into_iter()
                .map(|index| self.attempt(index).map(|attempt| Active { index, attempt }))
                .collect::<Result<_>>()?;
            self.active_kind = AttemptKind::Restoration;
            self.restore_active(frozen)?;
            self.adopt_pending(boot, packages, frozen)?;
            self.active.clear();
        }
        self.guard(boot, packages, frozen)?;
        verify_inventory(&self.plan, &self.shared.borrow())?;
        for target in &self.plan.targets {
            let actual = self
                .shared
                .borrow()
                .current
                .get(&target.paths[0])
                .cloned()
                .unwrap_or_else(|| target.before.clone());
            ensure(
                actual.attributes == target.before.attributes,
                "working restoration retained a nonoriginal attribute",
            )?;
        }
        self.origin.plan.full_readback()?;
        boot.guard()?;
        seal_report(
            &self.plan.work,
            "LABELS-RESTORED.json",
            &json!({
                "schema":"droidloom.working-labels-restored.v1","candidate_id":self.plan.candidate_id,
                "source_plan":self.origin.plan.pin,"boot_intent":self.plan.boot_intent,
                "restorations_count":self.restoration_records.len(),
            "restorations_index_sha256":fs::digest(&serde_json::to_vec(&self.restoration_records)?),
                "complete_actual_target_count":self.plan.targets.len(),"boot_armed":false
            }),
        )?;
        self.shared.borrow_mut().phase = Phase::Restored;
        self.restored_result(boot.runtime().source())
    }
    fn restored_result(&self, source: &WorkingRuntimeSources) -> Result<WorkingLabelsRestored> {
        ensure(
            self.shared.borrow().phase == Phase::Restored
                && self.completed.is_empty()
                && self.active.is_empty()
                && self.pending.is_none(),
            "working label restoration is incomplete",
        )?;
        self.origin.source.require_source(source)?;
        let report = files::pin_file(&self.plan.work.join("LABELS-RESTORED.json"))?;
        Ok(WorkingLabelsRestored {
            origin: Rc::clone(&self.origin),
            plan: Rc::clone(&self.plan),
            shared: Rc::clone(&self.shared),
            report,
        })
    }
}
impl WorkingLabelsApplied {
    pub(crate) fn require_identity(
        &self,
        source: &crate::cold_original_qualification::WorkingLabelSourceIdentity,
    ) -> Result<()> {
        self.origin.source.require_identity(source)?;
        self.origin.plan.revalidate()?;
        self.origin.source.revalidate_normal_source()?;
        let shared = self
            .shared
            .try_borrow()
            .map_err(|_| "working labels already changing")?;
        ensure(
            shared.phase == Phase::Applied,
            "working full labels are not applied",
        )?;
        files::read_pin(&self.report, 512 * 1024 * 1024)?;
        verify_inventory(&self.plan, &shared)
    }
    pub(crate) fn source_plan(&self) -> &FilePin {
        &self.origin.plan.pin
    }
    pub(crate) fn require_source(&self, source: &WorkingRuntimeSources) -> Result<()> {
        self.origin.source.require_source(source)?;
        self.origin.plan.revalidate()?;
        self.origin.source.revalidate_normal_source()?;
        let shared = self
            .shared
            .try_borrow()
            .map_err(|_| "working label publication is being changed")?;
        ensure(
            shared.phase == Phase::Applied,
            "working applied labels have been withdrawn",
        )?;
        files::read_pin(&self.report, 512 * 1024 * 1024)?;
        verify_inventory(&self.plan, &shared)?;
        source.revalidate()
    }
    pub(crate) fn report(&self) -> &FilePin {
        &self.report
    }
}
impl WorkingLabelsRestored {
    pub(crate) fn publish_package_preservation(&self, value: &Value) -> Result<FilePin> {
        self.origin.plan.revalidate()?;
        ensure(
            self.shared.borrow().phase == Phase::Restored
                && value["schema"] == "droidloom.working-package-preservation.v1"
                && value["candidate_id"] == self.plan.candidate_id
                && value["intent"] == serde_json::to_value(&self.plan.boot_intent)?
                && value["actual_label_restoration"] == serde_json::to_value(&self.report)?,
            "working preservation is outside its actual completed label transaction",
        )?;
        seal_report(
            self.origin.source.work(),
            &format!("NORMAL-PACKAGE-PRESERVATION-{}.json", self.report.sha256),
            value,
        )
    }
    pub(crate) fn require_identity(
        &self,
        source: &crate::cold_original_qualification::WorkingLabelSourceIdentity,
    ) -> Result<()> {
        self.origin.source.require_identity(source)?;
        self.origin.plan.revalidate()?;
        self.origin.source.revalidate_normal_source()?;
        ensure(
            self.shared.borrow().phase == Phase::Restored,
            "working restoration proof is not final",
        )?;
        files::read_pin(&self.report, 512 * 1024 * 1024)?;
        Ok(())
    }
    pub(crate) fn report(&self) -> &FilePin {
        &self.report
    }
    pub(crate) fn metadata(&self, paths: &BTreeSet<PathBuf>) -> Result<Value> {
        self.origin.plan.revalidate()?;
        ensure(
            self.shared.borrow().phase == Phase::Restored,
            "working metadata lacks actual complete restoration",
        )?;
        metadata(&self.plan, &self.shared.borrow(), paths)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    const ATTRIBUTE: &str = "user.droidloom.working-restore-test";
    fn attempt(root: &Path, index: usize) -> DurableAttempt {
        let target = root.join(format!("target-{index}"));
        std::fs::write(&target, b"actual original public content").unwrap();
        let directory = root.join(format!("inode-{index}"));
        std::fs::create_dir(&directory).unwrap();
        std::fs::set_permissions(&directory, std::fs::Permissions::from_mode(0o700)).unwrap();
        DurableAttempt::prepare(
            Records::open(&directory).unwrap(),
            File::open(&target).unwrap(),
            &"b".repeat(64),
            &FilePin {
                path: root.join("plan"),
                bytes: 1,
                sha256: "a".repeat(64),
            },
            index.try_into().unwrap(),
            &PathBuf::from(format!("/usr/owned/{index}")),
            b"candidate",
            ATTRIBUTE,
        )
        .unwrap()
    }
    #[test]
    fn working_batched_restore_recovers_a_lost_completion_without_another_inode_write() {
        let root = tempfile::Builder::new()
            .prefix(".p4-working-restore-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let attempt = attempt(root.path(), 0);
        let applied = attempt.apply().unwrap();
        let mut calls = 0;
        let failed = restore_attempts_batched(&[&attempt], &mut || {
            calls += 1;
            ensure(
                calls != 3,
                "injected interruption after actual reverse syscall",
            )
        });
        assert!(failed.is_err());
        assert!(attempt.restored_intent().unwrap());
        assert!(!attempt.records.exists("RESTORED.json").unwrap());
        let actual = snapshot(&attempt.recovery).unwrap();
        assert_eq!(actual.attributes, attempt.preimage.before.attributes);
        assert_ne!(actual, applied.after);
        let restored = restore_attempts_batched(&[&attempt], &mut || Ok(())).unwrap();
        assert_eq!(restored, vec![actual.clone()]);
        assert_eq!(snapshot(&attempt.recovery).unwrap(), actual);
        let (_, _, body) = attempt.records.read("RESTORED.json").unwrap();
        let record: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(
            record["observed_before_restore"],
            serde_json::to_value(&actual).unwrap()
        );
        assert_eq!(record["after"], serde_json::to_value(&actual).unwrap());
        let (_, _, body) = attempt.records.read("APPLIED.json").unwrap();
        let application: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(
            application["after"],
            serde_json::to_value(&applied.after).unwrap()
        );
        let (_, _, before_receipt) = attempt.records.read("RESTORED.json").unwrap();
        assert_eq!(
            restore_attempts_batched(&[&attempt], &mut || Ok(())).unwrap(),
            vec![actual]
        );
        assert_eq!(
            attempt.records.read("RESTORED.json").unwrap().2,
            before_receipt
        );
    }
    #[test]
    fn working_batched_restore_checks_every_original_before_its_first_reverse_effect() {
        let root = tempfile::Builder::new()
            .prefix(".p4-working-restore-foreign-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let attempts = (0..2).map(|i| attempt(root.path(), i)).collect::<Vec<_>>();
        let applied = attempts
            .iter()
            .map(|a| a.apply().unwrap())
            .collect::<Vec<_>>();
        super::super::set(&attempts[1].recovery, "user.unrelated", Some(b"foreign")).unwrap();
        assert!(
            restore_attempts_batched(&attempts.iter().collect::<Vec<_>>(), &mut || Ok(())).is_err()
        );
        assert_eq!(snapshot(&attempts[0].recovery).unwrap(), applied[0].after);
        assert!(!attempts[0].records.exists("RESTORED.json").unwrap());
        assert!(!attempts[1].records.exists("RESTORED.json").unwrap());
    }
    #[test]
    fn working_batched_restore_uses_five_real_barriers_for_sixty_four_complete_inodes() {
        let root = tempfile::Builder::new()
            .prefix(".p4-working-restore-batch-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let attempts = (0..BATCH_LIMIT)
            .map(|i| attempt(root.path(), i))
            .collect::<Vec<_>>();
        for attempt in &attempts {
            attempt.apply().unwrap();
        }
        super::super::batch::BARRIERS.with(|count| count.set(0));
        let restored =
            restore_attempts_batched(&attempts.iter().collect::<Vec<_>>(), &mut || Ok(())).unwrap();
        assert_eq!(super::super::batch::BARRIERS.with(|count| count.get()), 5);
        assert_eq!(restored.len(), BATCH_LIMIT);
        for (attempt, after) in attempts.iter().zip(restored) {
            assert_eq!(after.attributes, attempt.preimage.before.attributes);
            assert_eq!(after.handle, attempt.preimage.before.handle);
            assert_eq!(snapshot(&attempt.recovery).unwrap(), after);
            assert!(attempt.records.exists("RESTORED.json").unwrap());
        }
    }
}
