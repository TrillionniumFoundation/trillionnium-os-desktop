//! The sole full original-root label writer. Source objects and the once
//! owner's live typed phase fence are mandatory; no JSON success authorizes a
//! write. PREIMAGE and the recovery FD exist before each target syscall.
use super::super::{
    OriginalLabelDerivation, OriginalLabelSources, PersistentHandle, PlanSeal, plan,
    scope::{self, Entry, Inventory, RootScope},
};
use super::*;
use crate::cold_original_data::{self as data, OriginalDataTransaction};
use crate::cold_original_qualification::{OriginalDataStep, OriginalQualificationAuthority};
use std::{
    collections::{BTreeMap, BTreeSet},
    sync::Arc,
};
#[path = "cold_original_label_selection.rs"]
mod selection;
pub(in crate::cold_original_data) use selection::withdraw as withdraw_labeled_selection;
#[path = "cold_original_label_pair_restore.rs"]
mod pair_restore;
pub(crate) use pair_restore::OriginalPairRestored;
pub(in crate::cold_original_data) use pair_restore::restore_pair as restore_retired_pair;
#[path = "cold_original_label_restore.rs"]
mod restore;
pub(crate) use restore::{OriginalLabelRestorationTransaction, OriginalLabelsRestored};

const SCHEMA: &str = "droidloom.original-label-transaction-plan.v1";
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum Placement {
    Root,
    WorkingPair,
    PendingSelection,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Alias {
    logical: PathBuf,
    physical: PathBuf,
    placement: Placement,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Target {
    ordinal: u32,
    aliases: Vec<Alias>,
    before: Snapshot,
    desired: Vec<u8>,
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct TransactionPlan {
    schema: String,
    candidate_id: String,
    work_directory: PathBuf,
    root_uuid: String,
    normal_sources: FilePin,
    pair_intent: FilePin,
    scope: Inventory,
    targets: Vec<Target>,
    actual_lookup_commands: FilePin,
}

/// Live ownership of actual source admission and the complete immutable plan.
/// Reopening validates original root/generation and every normal source again.
/// It neither constructs nor advances qualification authority.
pub(crate) struct OriginalLabelTransaction<'a> {
    sources: &'a OriginalLabelSources,
    scope: RootScope,
    plan: TransactionPlan,
    seal: Arc<PlanSeal>,
    // Kept across an Err, including a successful syscall followed by failed
    // readback/publication. The caller still owns this transaction and FD.
    active_attempt: Option<DurableAttempt>,
}
/// Only a complete actual target readback constructs this object. Publication
/// of selected.json must consume this held source/plan/target evidence.
pub(crate) struct OriginalLabelsApplied {
    candidate_id: String,
    pair_intent: FilePin,
    plan: Arc<PlanSeal>,
    report: FilePin,
    // Complete source plan plus each real APPLIED record is retained. An
    // untrusted aggregate list or `labels_applied` boolean is never a source.
    targets: Vec<Target>,
    applications: Vec<FilePin>,
    paths: BTreeMap<PathBuf, usize>,
}
fn path_index(targets: &[Target]) -> Result<BTreeMap<PathBuf, usize>> {
    let mut paths = BTreeMap::new();
    for (index, target) in targets.iter().enumerate() {
        ensure(
            target.ordinal as usize == index,
            "label target ordinal differs from its complete plan",
        )?;
        for alias in &target.aliases {
            ensure(
                paths.insert(alias.logical.clone(), index).is_none(),
                "ambiguous source label path",
            )?;
        }
    }
    Ok(paths)
}
#[cfg(test)]
mod index_tests {
    use super::*;
    #[test]
    fn complete_representative_target_index_is_unique_and_linear_to_visit() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-label-index-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let file = File::from(
            rustix::fs::open(
                tmp.path(),
                OFlags::PATH | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .unwrap(),
        );
        let before = snapshot(&file).unwrap();
        let mut targets = (0..100_000)
            .map(|n| Target {
                ordinal: n,
                aliases: vec![Alias {
                    logical: PathBuf::from(format!("/usr/source/{n}")),
                    physical: PathBuf::from(format!("/usr/source/{n}")),
                    placement: Placement::Root,
                }],
                before: before.clone(),
                desired: b"u:object_r:p4_linux_root_t:s0\0".to_vec(),
            })
            .collect::<Vec<_>>();
        let index = path_index(&targets).unwrap();
        assert_eq!(index.len(), targets.len());
        for (n, target) in targets.iter().enumerate() {
            assert_eq!(index.get(&target.aliases[0].logical), Some(&n));
        }
        targets[99_999].aliases[0].logical = targets[0].aliases[0].logical.clone();
        assert!(path_index(&targets).is_err());
        println!(
            "actual indexed complete plan: targets=100000 indexed_lookups=100000 duplicate_rejected=true"
        );
    }
}
fn pin_equal(a: &FilePin, b: &FilePin) -> bool {
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
fn record_directory(work: &Path, ordinal: u32) -> PathBuf {
    work.join(format!("inode-{ordinal:06}"))
}
fn snapshot_matches_handle(scope: &RootScope, alias: &Alias, expected: &Snapshot) -> Result<File> {
    let named = scope.open_named(&alias.physical)?;
    let generation = scope.reopen_generation(&expected.handle)?;
    ensure(
        snapshot(&named)? == *expected && snapshot(&generation)? == *expected,
        "source label path or ext4 generation no longer names the expected inode",
    )?;
    Ok(named)
}
fn pair_entries(
    data: &OriginalDataTransaction,
    authority: &OriginalQualificationAuthority,
) -> Result<Vec<(Entry, Alias)>> {
    data.binding(authority)?;
    let tx = &data.transaction;
    ensure(
        tx.observe(false)? == (data::Layout::Switched, data::SelectionState::Original),
        "full labels require the exact exchanged working pair before selection",
    )?;
    let mut result = Vec::new();
    let paths = std::iter::once((
        PathBuf::from(data::ORIGINAL),
        PathBuf::from(data::ORIGINAL),
        Placement::WorkingPair,
    ))
    .chain(data::WORKING_MEMBERS.iter().map(|name| {
        (
            Path::new(data::ORIGINAL).join(name),
            Path::new(data::ORIGINAL).join(name),
            Placement::WorkingPair,
        )
    }))
    .chain(std::iter::once((
        PathBuf::from(data::SELECTED),
        authority.work().join(data::PENDING),
        Placement::PendingSelection,
    )));
    let scope = RootScope::original(&tx.intent.cold_clone)?;
    for (logical, physical, placement) in paths {
        let held = scope.open_named(&physical)?;
        let before = snapshot(&held)?;
        if logical == Path::new(data::ORIGINAL) {
            ensure(
                data::stable(&before.identity, &tx.intent.working.directory),
                "working directory differs from its exact exchange lineage",
            )?;
        } else if placement == Placement::WorkingPair {
            let name = logical
                .file_name()
                .and_then(|n| n.to_str())
                .ok_or("working member name missing")?;
            ensure(
                before.identity == tx.intent.working.members[name].identity,
                "working member was labeled or changed before source admission",
            )?;
        } else {
            ensure(
                before.identity == tx.intent.new_selection.identity,
                "pending selected inode was changed before source admission",
            )?;
        }
        result.push((
            Entry {
                path: logical.clone(),
                matcher_type: scope::matcher_type(before.identity.mode)?.into(),
                snapshot: before,
            },
            Alias {
                logical,
                physical,
                placement,
            },
        ));
    }
    data.binding(authority)?;
    authority.verify_label_preparation()?;
    Ok(result)
}
fn validate_target_layout(plan: &TransactionPlan) -> Result<()> {
    ensure(
        plan.schema == SCHEMA
            && fs::valid_digest(&plan.candidate_id)
            && plan.root_uuid == "01c27223-3933-481e-9836-7bd0ef1be8c9"
            && plan.scope.schema == "droidloom.original-root-label-scope.v1"
            && plan.scope.root_uuid == plan.root_uuid
            && !plan.targets.is_empty()
            && plan.targets.len() <= 1_000_000,
        "complete original label transaction identity differs",
    )?;
    let mut physical = BTreeSet::new();
    let mut logical = BTreeSet::new();
    let mut extra = BTreeSet::new();
    let normal = plan
        .scope
        .entries
        .iter()
        .map(|e| (e.path.clone(), &e.snapshot))
        .collect::<BTreeMap<_, _>>();
    let mut normal_seen = BTreeSet::new();
    let mut inodes = BTreeSet::new();
    for (ordinal, target) in plan.targets.iter().enumerate() {
        ensure(
            target.ordinal as usize == ordinal
                && !target.aliases.is_empty()
                && inodes.insert((target.before.identity.dev, target.before.identity.ino))
                && target.before.identity.dev == plan.scope.root_identity.dev
                && !target.desired.is_empty()
                && target.desired.len() <= 4096,
            "duplicate/malformed complete label target",
        )?;
        let context = target
            .desired
            .strip_suffix(&[0])
            .ok_or("raw source context lacks its terminator")?;
        ensure(
            context.starts_with(b"u:object_r:")
                && context.ends_with(b":s0")
                && context
                    .iter()
                    .all(|b| b.is_ascii_alphanumeric() || b"_:".contains(b)),
            "target source context is not a canonical normal Linux inode label",
        )?;
        for alias in &target.aliases {
            ensure(
                physical.insert(alias.physical.clone()) && logical.insert(alias.logical.clone()),
                "duplicate full label path",
            )?;
            match alias.placement {
                Placement::Root => {
                    ensure(
                        alias.logical == alias.physical
                            && normal.get(&alias.logical) == Some(&&target.before),
                        "normal label target is outside the complete source inventory",
                    )?;
                    normal_seen.insert(alias.logical.clone());
                }
                Placement::WorkingPair => {
                    ensure(
                        alias.logical == alias.physical
                            && (alias.logical == Path::new(data::ORIGINAL)
                                || alias.logical.parent() == Some(Path::new(data::ORIGINAL))
                                    && alias
                                        .logical
                                        .file_name()
                                        .and_then(|v| v.to_str())
                                        .is_some_and(|n| data::WORKING_MEMBERS.contains(&n))),
                        "separate labels must name the exact working directory and nine members",
                    )?;
                    extra.insert(alias.logical.clone());
                }
                Placement::PendingSelection => {
                    ensure(
                        alias.logical == Path::new(data::SELECTED)
                            && alias.physical
                                == plan
                                    .work_directory
                                    .parent()
                                    .ok_or("label owner work missing")?
                                    .join(data::PENDING),
                        "selected label target is not the exact privately prepared inode",
                    )?;
                    extra.insert(alias.logical.clone());
                }
            }
        }
        if FileType::from_raw_mode(target.before.identity.mode) == FileType::Directory {
            ensure(
                target.aliases.len() == 1,
                "directory aliases cannot enter the physical root label plan",
            )?;
        } else {
            ensure(
                target.aliases.len() as u64 == target.before.identity.nlink,
                "all hardlink aliases must be in the same source-bound label target",
            )?;
        }
    }
    let wanted = std::iter::once(PathBuf::from(data::ORIGINAL))
        .chain(
            data::WORKING_MEMBERS
                .iter()
                .map(|n| Path::new(data::ORIGINAL).join(n)),
        )
        .chain(std::iter::once(PathBuf::from(data::SELECTED)))
        .collect::<BTreeSet<_>>();
    ensure(
        extra == wanted && normal_seen == normal.keys().cloned().collect(),
        "full normal root, exact nine-member pair or selected inode coverage differs",
    )
}
impl<'a> OriginalLabelTransaction<'a> {
    pub(crate) fn prepare(
        authority: &OriginalQualificationAuthority,
        sources: &'a OriginalLabelSources,
        data: &OriginalDataTransaction,
    ) -> Result<Self> {
        authority.verify_label_preparation()?;
        sources.revalidate()?;
        ensure(
            sources.fresh_initramfs_report()["normal_materials"]["deployment_id"]
                == authority.candidate_id(),
            "label sources and qualification candidate differ",
        )?;
        let extras = pair_entries(data, authority)?;
        let scope = RootScope::original(&data.transaction.intent.cold_clone)?;
        let inventory = scope.collect()?;
        let work = authority.work().join("labels");
        crate::boot_files::private_dir(&work)?;
        let lookup = work.join("normal-contexts");
        crate::boot_files::private_dir(&lookup)?;
        let mut entries = inventory.entries.clone();
        let mut aliases = entries
            .iter()
            .map(|e| Alias {
                logical: e.path.clone(),
                physical: e.path.clone(),
                placement: Placement::Root,
            })
            .collect::<Vec<_>>();
        for (entry, alias) in extras {
            entries.push(entry);
            aliases.push(alias);
        }
        let (labels, commands) = sources.lookup_entries(&entries, &lookup)?;
        plan::verify_hardlink_labels(
            &entries
                .iter()
                .map(|e| (&e.snapshot, e.path.as_path()))
                .collect::<Vec<_>>(),
            &labels,
        )?;
        let mut groups: BTreeMap<(u64, u64), Target> = BTreeMap::new();
        for ((entry, alias), desired) in entries.iter().zip(aliases).zip(labels) {
            let key = (entry.snapshot.identity.dev, entry.snapshot.identity.ino);
            match groups.get_mut(&key) {
                Some(target) => {
                    ensure(
                        target.before == entry.snapshot && target.desired == desired,
                        "hardlink preimage/context differs",
                    )?;
                    target.aliases.push(alias);
                }
                None => {
                    groups.insert(
                        key,
                        Target {
                            ordinal: 0,
                            aliases: vec![alias],
                            before: entry.snapshot.clone(),
                            desired,
                        },
                    );
                }
            }
        }
        let mut targets = groups.into_values().collect::<Vec<_>>();
        for (index, target) in targets.iter_mut().enumerate() {
            target.ordinal = index.try_into()?;
        }
        let plan = TransactionPlan {
            schema: SCHEMA.into(),
            candidate_id: authority.candidate_id().into(),
            work_directory: work.clone(),
            root_uuid: inventory.root_uuid.clone(),
            normal_sources: sources.source_pin().clone(),
            pair_intent: data.intent().clone(),
            scope: inventory,
            targets,
            actual_lookup_commands: commands,
        };
        validate_target_layout(&plan)?;
        scope.verify_inventory(&plan.scope)?;
        for target in &plan.targets {
            for alias in &target.aliases {
                snapshot_matches_handle(&scope, alias, &target.before)?;
            }
        }
        sources.revalidate()?;
        authority.verify_label_preparation()?;
        data.binding(authority)?;
        let pin = plan::save(&work.join("LABEL-PLAN.json"), &plan)?;
        let value = Self {
            sources,
            scope,
            plan,
            seal: Arc::new(PlanSeal::open(&pin)?),
            active_attempt: None,
        };
        value.seal.full_readback()?;
        Ok(value)
    }
    pub(crate) fn resume(
        authority: &OriginalQualificationAuthority,
        sources: &'a OriginalLabelSources,
        data: &OriginalDataTransaction,
        source_plan: &FilePin,
    ) -> Result<Self> {
        authority.verify_label_plan(source_plan)?;
        sources.revalidate()?;
        ensure(
            source_plan.path == authority.work().join("labels/LABEL-PLAN.json"),
            "recovery cannot substitute a differently named label plan",
        )?;
        let seal = Arc::new(PlanSeal::open(source_plan)?);
        let plan: TransactionPlan =
            serde_json::from_slice(&data::root_pin(source_plan, 512 * 1024 * 1024)?)?;
        validate_target_layout(&plan)?;
        ensure(
            plan.candidate_id == authority.candidate_id()
                && plan.work_directory == authority.work().join("labels")
                && pin_equal(&plan.normal_sources, sources.source_pin())
                && pin_equal(&plan.pair_intent, data.intent()),
            "reopened complete label plan belongs to another source or data lineage",
        )?;
        let scope = RootScope::original(&data.transaction.intent.cold_clone)?;
        let root = snapshot(&scope.open_named(Path::new("/"))?)?;
        ensure(
            root.handle == plan.scope.root_handle
                && only_ctime_changed(&plan.scope.root_identity, &root.identity),
            "reopened original root is outside its actual label derivation",
        )?;
        let value = Self {
            sources,
            scope,
            plan,
            seal,
            active_attempt: None,
        };
        value.validate_owner(authority, data)?;
        Ok(value)
    }
    pub(crate) fn source_plan(&self) -> &FilePin {
        &self.seal.pin
    }
    fn validate_owner(
        &self,
        authority: &OriginalQualificationAuthority,
        data: &OriginalDataTransaction,
    ) -> Result<()> {
        self.seal.revalidate()?;
        self.sources.revalidate()?;
        authority.verify_label_plan(&self.seal.pin)?;
        ensure(
            self.plan.candidate_id == authority.candidate_id()
                && self.plan.work_directory == authority.work().join("labels")
                && pin_equal(&self.plan.pair_intent, data.intent())
                && pin_equal(&self.plan.normal_sources, self.sources.source_pin()),
            "held label transaction no longer belongs to the same source owner",
        )?;
        data.binding(authority)
    }
    fn attempt(&self, target: &Target) -> Result<DurableAttempt> {
        let path = record_directory(&self.plan.work_directory, target.ordinal);
        let records = Records::open(&path)?;
        let preimage = record_pin(&records, "PREIMAGE.json")?;
        let held = self.scope.open_named(&target.aliases[0].physical)?;
        let attempt = DurableAttempt::reopen(records, &preimage, held)?;
        ensure(
            attempt.preimage.before == target.before
                && attempt.preimage.desired == target.desired
                && attempt.preimage.attribute == LABEL
                && attempt.preimage.ordinal == target.ordinal
                && attempt.preimage.candidate_id == self.plan.candidate_id
                && attempt.preimage.logical_path == target.aliases[0].logical
                && pin_equal(&attempt.preimage.source_plan, &self.seal.pin),
            "durable per-inode preimage is outside its complete source plan",
        )?;
        Ok(attempt)
    }
    /// All target writes are guarded by actual typed LabelsIntent. An existing
    /// recognized write can only be re-read and synchronized; it is never
    /// silently discarded or treated as an unmodified inode.
    pub(crate) fn apply(
        &mut self,
        authority: &OriginalQualificationAuthority,
        data: &OriginalDataTransaction,
    ) -> Result<OriginalLabelsApplied> {
        if let Some(attempt) = self.active_attempt.as_ref() {
            let current = snapshot(&attempt.recovery)?;
            let mut expected = attempt.preimage.before.attributes.clone();
            expected.insert(LABEL.into(), attempt.preimage.desired.clone());
            if current.attributes == expected {
                let core = attempt.applied_readback()?;
                let step = OriginalLabelDerivation {
                    candidate_id: self.plan.candidate_id.clone(),
                    logical_path: attempt.preimage.logical_path.clone(),
                    plan: self.seal.clone(),
                    preimage: attempt.pin.clone(),
                    applied: record_pin(&attempt.records, "APPLIED.json")?,
                    core,
                };
                self.scope.accept_root_label(&step)?;
                authority.accept_label_derivation(&step)?;
            }
        }
        self.validate_owner(authority, data)?;
        self.seal.full_readback()?;
        let mut applications = Vec::new();
        let mut updates = BTreeMap::new();
        for target in &self.plan.targets {
            self.validate_owner(authority, data)?;
            let path = record_directory(&self.plan.work_directory, target.ordinal);
            let records = match std::fs::symlink_metadata(&path) {
                Ok(_) => Records::open(&path)?,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                    authority.verify_data_step(OriginalDataStep::Label)?;
                    crate::boot_files::private_dir(&path)?;
                    Records::open(&path)?
                }
                Err(error) => return Err(error.into()),
            };
            let attempt = if records.exists("PREIMAGE.json")? {
                self.attempt(target)?
            } else {
                authority.verify_data_step(OriginalDataStep::Label)?;
                self.scope.revalidate()?;
                for alias in &target.aliases {
                    snapshot_matches_handle(&self.scope, alias, &target.before)?;
                }
                records.verify_unpublished_preimage()?;
                let held = self.scope.open_named(&target.aliases[0].physical)?;
                DurableAttempt::prepare(
                    records,
                    held,
                    &self.plan.candidate_id,
                    &self.seal.pin,
                    target.ordinal,
                    &target.aliases[0].logical,
                    &target.desired,
                    LABEL,
                )?
            };
            self.active_attempt = Some(attempt);
            let attempt = self
                .active_attempt
                .as_ref()
                .ok_or("actual active label recovery descriptor missing")?;
            let current = snapshot(&attempt.recovery)?;
            let mut desired = target.before.attributes.clone();
            desired.insert(LABEL.into(), target.desired.clone());
            let core = if current.attributes == desired {
                // No target write in this branch. Its opaque actual derivation
                // restores the precise expected ctime of a held once lock.
                attempt.applied_readback()?
            } else {
                authority.verify_data_step(OriginalDataStep::Label)?;
                ensure(current == target.before, "unapplied source inode changed")?;
                attempt.apply()?
            };
            let applied = record_pin(&attempt.records, "APPLIED.json")?;
            let derivation = OriginalLabelDerivation {
                candidate_id: self.plan.candidate_id.clone(),
                logical_path: target.aliases[0].logical.clone(),
                plan: self.seal.clone(),
                preimage: attempt.pin.clone(),
                applied: applied.clone(),
                core,
            };
            derivation.revalidate()?;
            self.scope.accept_root_label(&derivation)?;
            authority.accept_label_derivation(&derivation)?;
            for alias in &target.aliases {
                snapshot_matches_handle(&self.scope, alias, &derivation.core.after)?;
                if alias.placement != Placement::PendingSelection {
                    updates.insert(alias.logical.clone(), derivation.core.after.clone());
                }
            }
            authority.verify_data_step(OriginalDataStep::Label)?;
            self.validate_owner(authority, data)?;
            applications.push(applied);
            self.active_attempt.take();
        }
        self.scope
            .verify_inventory_updates(&self.plan.scope, &updates)?;
        self.seal.full_readback()?;
        self.sources.revalidate()?;
        authority.verify_data_step(OriginalDataStep::Label)?;
        let report_value = json!({
            "schema":"droidloom.original-labels-applied.v1","candidate_id":self.plan.candidate_id,
            "source_plan":self.seal.pin,"pair_intent":self.plan.pair_intent,"applications":applications,
            "complete_actual_target_count":self.plan.targets.len(),"selected_published":false,
            "qualification_boot_authorized":false,"runtime_or_migration_accepted":false});
        let report_path = self.plan.work_directory.join("LABELS-APPLIED.json");
        let report = match std::fs::symlink_metadata(&report_path) {
            Ok(_) => {
                let pinned = crate::boot_files::pin_file(&report_path)?;
                let actual: Value =
                    serde_json::from_slice(&data::root_pin(&pinned, 512 * 1024 * 1024)?)?;
                ensure(
                    actual == report_value,
                    "existing complete label result differs from actual readback",
                )?;
                pinned
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                plan::save(&report_path, &report_value)?
            }
            Err(error) => return Err(error.into()),
        };
        let value = OriginalLabelsApplied {
            candidate_id: self.plan.candidate_id.clone(),
            pair_intent: self.plan.pair_intent.clone(),
            plan: self.seal.clone(),
            report,
            paths: path_index(&self.plan.targets)?,
            targets: self.plan.targets.clone(),
            applications,
        };
        value.verify_selection_ready(authority, data)?;
        Ok(value)
    }
}
impl OriginalLabelsApplied {
    pub(crate) fn report(&self) -> &FilePin {
        &self.report
    }
    pub(crate) fn source_plan(&self) -> &FilePin {
        &self.plan.pin
    }
    pub(crate) fn publish_selection(
        &self,
        authority: &OriginalQualificationAuthority,
        data: &OriginalDataTransaction,
    ) -> Result<Value> {
        selection::publish(self, authority, data)
    }
    pub(crate) fn verify_published(
        &self,
        authority: &OriginalQualificationAuthority,
        data: &OriginalDataTransaction,
    ) -> Result<()> {
        self.plan.full_readback()?;
        authority.verify_label_plan(&self.plan.pin)?;
        ensure(
            self.candidate_id == authority.candidate_id()
                && pin_equal(&self.pair_intent, data.intent())
                && data.transaction.observe(true)?
                    == (data::Layout::Switched, data::SelectionState::Candidate),
            "published labels are outside the same exchanged actual data transaction",
        )?;
        let (parent, selected) = selection::published_evolution(self, authority, data)?;
        let scope = RootScope::original(&data.transaction.intent.cold_clone)?;
        for target in &self.targets {
            let source = self.applied_snapshot(&target.aliases[0].logical)?;
            for alias in &target.aliases {
                let (physical, expected) = if alias.placement == Placement::PendingSelection {
                    (PathBuf::from(data::SELECTED), &selected)
                } else if alias.logical == Path::new("/etc/droidloom/production") {
                    (alias.physical.clone(), &parent)
                } else {
                    (alias.physical.clone(), &source)
                };
                let actual = snapshot(&scope.open_named(&physical)?)?;
                let generation = snapshot(&scope.reopen_generation(&expected.handle)?)?;
                ensure(
                    actual == *expected && generation == *expected,
                    "source label or exact selected rename changed before physical arm",
                )?;
            }
        }
        self.plan.full_readback()?;
        authority.verify_current_owner()
    }
    fn applied_snapshot(&self, path: &Path) -> Result<Snapshot> {
        self.plan.revalidate()?;
        let index = *self
            .paths
            .get(path)
            .ok_or("source-bound label target is missing")?;
        let target = self
            .targets
            .get(index)
            .ok_or("indexed label target missing")?;
        let pin = self
            .applications
            .get(index)
            .ok_or("indexed actual label application missing")?;
        ensure(
            target.ordinal as usize == index
                && target.aliases.iter().any(|alias| alias.logical == path),
            "source label index differs from its exact complete target",
        )?;
        let value: Value = serde_json::from_slice(&data::root_pin(pin, 32 * 1024 * 1024)?)?;
        let after: Snapshot = serde_json::from_value(value["after"].clone())?;
        let mut attrs = target.before.attributes.clone();
        attrs.insert(LABEL.into(), target.desired.clone());
        ensure(
            value["schema"] == "droidloom.original-label-applied.v1"
                && value["before"] == serde_json::to_value(&target.before)?
                && only_ctime_changed(&target.before.identity, &after.identity)
                && target.before.handle == after.handle
                && after.attributes == attrs
                && value["target_metadata_durability"]["operation"] == "syncfs",
            "target has no complete actual durable label application",
        )?;
        Ok(after)
    }
    pub(crate) fn verify_selection_ready(
        &self,
        authority: &OriginalQualificationAuthority,
        data: &OriginalDataTransaction,
    ) -> Result<()> {
        authority.verify_current_owner()?;
        data.binding(authority)?;
        self.plan.full_readback()?;
        authority.verify_label_plan(&self.plan.pin)?;
        ensure(
            self.candidate_id == authority.candidate_id()
                && pin_equal(&self.pair_intent, data.intent())
                && self.targets.len() == self.applications.len(),
            "actual complete labels and data transaction differ",
        )?;
        let report: Value =
            serde_json::from_slice(&data::root_pin(&self.report, 512 * 1024 * 1024)?)?;
        ensure(
            report["schema"] == "droidloom.original-labels-applied.v1"
                && report["candidate_id"] == self.candidate_id
                && report["source_plan"] == serde_json::to_value(&self.plan.pin)?
                && report["pair_intent"] == serde_json::to_value(&self.pair_intent)?
                && report["applications"] == serde_json::to_value(&self.applications)?,
            "complete label report differs from its held actual members",
        )?;
        let scope = RootScope::original(&data.transaction.intent.cold_clone)?;
        for (target, pin) in self.targets.iter().zip(&self.applications) {
            let value: Value = serde_json::from_slice(&data::root_pin(pin, 32 * 1024 * 1024)?)?;
            let after: Snapshot = serde_json::from_value(value["after"].clone())?;
            let mut desired = target.before.attributes.clone();
            desired.insert(LABEL.into(), target.desired.clone());
            ensure(
                value["schema"] == "droidloom.original-label-applied.v1"
                    && value["before"] == serde_json::to_value(&target.before)?
                    && only_ctime_changed(&target.before.identity, &after.identity)
                    && target.before.handle == after.handle
                    && after.attributes == desired
                    && value["target_metadata_durability"]["operation"] == "syncfs"
                    && value["target_metadata_durability"]["filesystem_dev"] == after.identity.dev,
                "source label application is incomplete or its actual target differs",
            )?;
            for alias in &target.aliases {
                snapshot_matches_handle(&scope, alias, &after)?;
            }
        }
        scope.revalidate()?;
        authority.verify_current_owner()?;
        self.plan.full_readback()
    }
}
