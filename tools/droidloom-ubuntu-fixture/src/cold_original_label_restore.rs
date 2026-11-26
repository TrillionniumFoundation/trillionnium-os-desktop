//! Complete label rollback after actual original-kernel retirement. The named
//! path and persistent ext4 generation are both checked. Working data is read
//! at its returned private location, never through the restored original pair.
use super::super::super::OriginalLabelRestoration;
use super::super::runtime::{self, EvolutionKind, ExactEvolution};
use super::*;
use crate::cold_original_qualification::OriginalRetirement;

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RestoredRow {
    ordinal: u32,
    prelabel: Snapshot,
    current_before: Snapshot,
    restored: Snapshot,
    original_preimage: Option<FilePin>,
    restoration: Option<FilePin>,
    recognized_history: Option<FilePin>,
    target_write: bool,
}

pub(crate) struct OriginalLabelRestorationTransaction<'a> {
    retirement: &'a OriginalRetirement,
    scope: RootScope,
    plan: TransactionPlan,
    seal: Arc<PlanSeal>,
    pair: OriginalPairRestored,
    renamed: BTreeMap<PathBuf, (Snapshot, FilePin, EvolutionKind)>,
    active: Option<RuntimeRestoreAttempt>,
}

/// This type exists only after every actual target and original pair has been
/// read back. It is not deserializable and does not grant any forward phase.
pub(crate) struct OriginalLabelsRestored {
    candidate: String,
    normal_sources: FilePin,
    pair_intent: FilePin,
    plan: Arc<PlanSeal>,
    report: FilePin,
    targets: Vec<Target>,
    rows: Vec<RestoredRow>,
}

fn physical(alias: &Alias, work: &Path) -> Result<PathBuf> {
    Ok(match alias.placement {
        Placement::Root => alias.physical.clone(),
        Placement::PendingSelection => work.join(data::PENDING),
        Placement::WorkingPair => {
            Path::new(data::WORKING).join(alias.logical.strip_prefix(data::ORIGINAL)?)
        }
    })
}
fn actual_named(scope: &RootScope, target: &Target, work: &Path) -> Result<(File, Snapshot)> {
    let held = scope.open_named(&physical(&target.aliases[0], work)?)?;
    let current = snapshot(&held)?;
    ensure(
        current.handle == target.before.handle,
        "returned label path has another ext4 inode generation",
    )?;
    ensure(
        snapshot(&scope.reopen_generation(&target.before.handle)?)? == current,
        "returned named inode differs from the persistent generation handle",
    )?;
    for alias in &target.aliases {
        ensure(
            snapshot(&scope.open_named(&physical(alias, work)?)?)? == current,
            "returned hardlink aliases no longer name the same complete inode",
        )?;
    }
    Ok((held, current))
}
fn validate_original(
    original: &DurableAttempt,
    target: &Target,
    seal: &PlanSeal,
    candidate: &str,
) -> Result<()> {
    original.validate_intent()?;
    ensure(
        original.preimage.before == target.before
            && original.preimage.desired == target.desired
            && original.preimage.attribute == LABEL
            && original.preimage.ordinal == target.ordinal
            && original.preimage.candidate_id == candidate
            && original.preimage.logical_path == target.aliases[0].logical
            && pin_equal(&original.preimage.source_plan, &seal.pin),
        "restoration preimage is outside the complete original source plan",
    )
}
fn load_original(
    records: &Path,
    held: File,
    target: &Target,
    seal: &PlanSeal,
    candidate: &str,
) -> Result<DurableAttempt> {
    let records = Records::open(records)?;
    let pin = record_pin(&records, "PREIMAGE.json")?;
    let original = DurableAttempt::load_unclassified(records, &pin, held)?;
    validate_original(&original, target, seal, candidate)?;
    Ok(original)
}
fn compatible_owned(before: &Snapshot, current: &Snapshot) -> Result<()> {
    let a = &before.identity;
    let b = &current.identity;
    ensure(
        before.handle == current.handle
            && before.attributes == current.attributes
            && (a.dev, a.ino, a.mode, a.uid, a.gid, a.nlink)
                == (b.dev, b.ino, b.mode, b.uid, b.gid, b.nlink),
        "owned state evolution changed a generation, authority, links or unrelated attributes",
    )
}
fn epoch(records: &Records, retirement: &OriginalRetirement) -> Result<Records> {
    let path = records
        .path
        .join(format!("retirement-{}", retirement.report_pin().sha256));
    match std::fs::symlink_metadata(&path) {
        Ok(_) => {}
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            crate::boot_files::private_dir(&path)?
        }
        Err(e) => return Err(e.into()),
    }
    Records::open(&path)
}

pub(super) fn seal_pair_label_outcomes(
    retirement: &OriginalRetirement,
    data: &OriginalDataTransaction,
) -> Result<()> {
    if data.transaction.observe(true)?.0 != data::Layout::Switched {
        return Ok(());
    }
    let path = retirement.authority().work().join("labels/LABEL-PLAN.json");
    match std::fs::symlink_metadata(&path) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(e) => return Err(e.into()),
        Ok(_) => {}
    }
    let pin = crate::boot_files::pin_file(&path)?;
    let plan: TransactionPlan = serde_json::from_slice(&data::root_pin(&pin, 512 * 1024 * 1024)?)?;
    validate_target_layout(&plan)?;
    ensure(
        plan.candidate_id == retirement.candidate_id()
            && pin_equal(&plan.normal_sources, retirement.source_pin())
            && pin_equal(&plan.pair_intent, data.intent()),
        "pre-rename label evidence belongs to another transaction",
    )?;
    let scope = RootScope::original(&data.transaction.intent.cold_clone)?;
    let seal = PlanSeal::open(&pin)?;
    for target in &plan.targets {
        if !target.aliases.iter().any(|a| {
            ["/var/lib/droidloom/users/1000", data::ORIGINAL]
                .contains(&a.logical.to_str().unwrap_or(""))
        }) {
            continue;
        }
        let dir = record_directory(&plan.work_directory, target.ordinal);
        match std::fs::symlink_metadata(&dir) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue,
            Err(e) => return Err(e.into()),
            Ok(_) => {}
        }
        let records = Records::open(&dir)?;
        if !records.exists("PREIMAGE.json")? {
            records.verify_unpublished_preimage()?;
            continue;
        }
        if records.exists("APPLIED.json")? {
            continue;
        }
        retirement.authority().verify_label_plan(&pin)?;
        ensure(
            retirement.report()["scope"] == "verified-unbooted-abort",
            "a booted candidate cannot invent missing original label application evidence",
        )?;
        let held = scope.open_named(&target.aliases[0].physical)?;
        let original = load_original(&dir, held, target, &seal, &plan.candidate_id)?;
        let current = snapshot(&original.recovery)?;
        if current == target.before {
            continue;
        }
        let mut desired = target.before.attributes.clone();
        desired.insert(LABEL.into(), target.desired.clone());
        ensure(
            current.attributes == desired,
            "unbooted label attempt has an unknown pre-rename xattr outcome",
        )?;
        // No xattr write: retain the actual uncertain label result before the
        // owned directory rename changes that inode's clocks again.
        original.applied_readback()?;
    }
    seal.full_readback()?;
    retirement.revalidate()
}

impl<'a> OriginalLabelRestorationTransaction<'a> {
    pub(crate) fn resume(
        retirement: &'a OriginalRetirement,
        data: &OriginalDataTransaction,
        source_plan: &FilePin,
    ) -> Result<Self> {
        retirement.revalidate()?;
        data.binding(retirement.authority())?;
        retirement.authority().verify_label_plan(source_plan)?;
        ensure(
            source_plan.path == retirement.authority().work().join("labels/LABEL-PLAN.json"),
            "label restoration cannot substitute another source plan",
        )?;
        let seal = Arc::new(PlanSeal::open(source_plan)?);
        let plan: TransactionPlan =
            serde_json::from_slice(&data::root_pin(source_plan, 512 * 1024 * 1024)?)?;
        validate_target_layout(&plan)?;
        ensure(
            plan.candidate_id == retirement.candidate_id()
                && pin_equal(&plan.normal_sources, retirement.source_pin())
                && pin_equal(&plan.pair_intent, data.intent())
                && pin_equal(data.intent(), retirement.pair_intent()),
            "retired labels belong to another normal source or data transaction",
        )?;
        let pair = OriginalPairRestored::resume_for_labels(retirement, data)?;
        let mut renamed = pair
            .derived_snapshots(retirement, data)?
            .into_iter()
            .map(|(p, s)| (p, (s, pair.report().clone(), EvolutionKind::PairRename)))
            .collect::<BTreeMap<_, _>>();
        for (p, (s, pin)) in selection::withdrawn_evolution(retirement, data)? {
            ensure(
                renamed
                    .insert(p, (s, pin, EvolutionKind::SelectionRename))
                    .is_none(),
                "ambiguous owned directory restoration provenance",
            )?;
        }
        let scope = RootScope::original(&data.transaction.intent.cold_clone)?;
        ensure(
            snapshot(&scope.open_named(Path::new("/"))?)?.handle == plan.scope.root_handle,
            "returned original root has another persistent generation",
        )?;
        let value = Self {
            retirement,
            scope,
            plan,
            seal,
            pair,
            renamed,
            active: None,
        };
        value.fence(data)?;
        value.seal.full_readback()?;
        Ok(value)
    }
    fn fence(&self, data: &OriginalDataTransaction) -> Result<()> {
        self.retirement.revalidate()?;
        self.seal.revalidate()?;
        self.scope.revalidate()?;
        ensure(
            pin_equal(&self.plan.normal_sources, self.retirement.source_pin())
                && pin_equal(&self.plan.pair_intent, data.intent()),
            "restoration owner/source binding changed",
        )?;
        data.binding(self.retirement.authority())?;
        ensure(
            data.transaction.observe(true)?
                == (data::Layout::Ready, data::SelectionState::Original),
            "label restoration left the actually restored original pair layout",
        )
    }
    fn evolution(&self, target: &Target, current: &Snapshot) -> Result<Option<ExactEvolution>> {
        let path = &target.aliases[0].logical;
        let value = if [
            "/var/lib/droidloom/users/1000/data/data.img",
            "/var/lib/droidloom/users/1000/data/metadata.img",
        ]
        .contains(&path.to_str().unwrap_or(""))
        {
            self.retirement.verify_working_identity(&current.identity)?;
            Some(ExactEvolution {
                kind: EvolutionKind::WorkingBacking,
                actual: current.clone(),
                evidence: self.retirement.report_pin().clone(),
            })
        } else if path == Path::new("/boot/grub/grubenv") {
            self.retirement.verify_grubenv_identity(&current.identity)?;
            Some(ExactEvolution {
                kind: EvolutionKind::GrubEnvironment,
                actual: current.clone(),
                evidence: self.retirement.report_pin().clone(),
            })
        } else if let Some((actual, pin, kind)) = self.renamed.get(path) {
            ensure(
                actual == current,
                "owned rename target changed before label restoration",
            )?;
            Some(ExactEvolution {
                kind: *kind,
                actual: actual.clone(),
                evidence: pin.clone(),
            })
        } else {
            None
        };
        Ok(value)
    }
    fn admit_history(
        &self,
        target: &Target,
        previous: &Snapshot,
        current: &Snapshot,
        completed: bool,
    ) -> Result<()> {
        ensure(
            previous.handle == current.handle && previous.attributes == current.attributes,
            "restored history changed the inode generation or an unrelated attribute",
        )?;
        let logical = &target.aliases[0].logical;
        if self.renamed.contains_key(logical) {
            ensure(
                only_ctime_changed(&previous.identity, &current.identity),
                "restored owned directory acquired unexplained metadata changes",
            )
        } else if logical == Path::new("/boot/grub/grubenv") {
            self.retirement.verify_grubenv_identity(&current.identity)?;
            compatible_owned(previous, current)?;
            ensure(
                previous.identity.size == current.identity.size,
                "restored GRUB size changed",
            )
        } else if target.aliases[0].placement == Placement::WorkingPair {
            if ["data.img", "metadata.img"]
                .contains(&logical.file_name().and_then(|n| n.to_str()).unwrap_or(""))
            {
                self.retirement.verify_working_identity(&current.identity)?;
                compatible_owned(previous, current)?;
                ensure(
                    previous.identity.size == current.identity.size,
                    "retired working backing size changed",
                )
            } else {
                ensure(
                    only_ctime_changed(&previous.identity, &current.identity),
                    "restored proof inode changed",
                )
            }
        } else {
            for alias in &target.aliases {
                let class = runtime::runtime_class(&alias.logical, &self.plan.candidate_id);
                if class.is_none() && !completed {
                    ensure(
                        only_ctime_changed(&previous.identity, &current.identity),
                        "uncertain restoration of an immutable inode changed another field",
                    )?;
                } else {
                    runtime::admit_current(previous, current, class)?;
                }
            }
            Ok(())
        }
    }
    fn history(
        &self,
        path: &Path,
        held: &File,
        target: &Target,
        current: &Snapshot,
    ) -> Result<Option<FilePin>> {
        let original_records = Records::open(path)?;
        let directory = File::from(rustix::fs::openat(
            &original_records.held,
            ".",
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::CLOEXEC | OFlags::NOFOLLOW,
            Mode::empty(),
        )?);
        let mut names = Vec::new();
        for entry in rustix::fs::Dir::read_from(&directory)? {
            let entry = entry?;
            let name = entry.file_name().to_str()?;
            if let Some(hash) = name.strip_prefix("retirement-") {
                ensure(fs::valid_digest(hash), "unknown restoration epoch name")?;
                names.push(name.to_owned());
            }
        }
        ensure(
            names.len() <= 64,
            "bounded actual original restoration attempts required",
        )?;
        names.sort();
        for name in names {
            let old = Records::open(&path.join(&name))?;
            if !old.exists("CURRENT-PREIMAGE.json")? {
                continue;
            }
            let pin = record_pin(&old, "CURRENT-PREIMAGE.json")?;
            let (_, _, bytes) = old.read("CURRENT-PREIMAGE.json")?;
            let current_record: Value = serde_json::from_slice(&bytes)?;
            let actual_retirement: FilePin =
                serde_json::from_value(current_record["retirement"].clone())?;
            ensure(
                name == format!("retirement-{}", actual_retirement.sha256),
                "restoration epoch is not its sealed actual retirement",
            )?;
            let prior: Value =
                serde_json::from_slice(&data::root_pin(&actual_retirement, 32 * 1024 * 1024)?)?;
            ensure(
                prior["schema"] == "droidloom.original-once-retirement.v1"
                    && prior["candidate_id"] == self.plan.candidate_id
                    && prior["normal_sources"] == serde_json::to_value(&self.plan.normal_sources)?,
                "historical restoration did not belong to this actual retired source",
            )?;
            let original = load_original(
                path,
                held.try_clone()?,
                target,
                &self.seal,
                &self.plan.candidate_id,
            )?;
            let attempt = RuntimeRestoreAttempt::open_evidence(original, old, &pin)?;
            let previous = attempt.historical_restored_snapshot()?;
            if previous.attributes != current.attributes || previous.handle != current.handle {
                continue;
            }
            self.admit_history(target, &previous, current, attempt.has_completed_result()?)?;
            return Ok(Some(pin));
        }
        Ok(None)
    }
    fn untouched(&self, target: &Target, current: &Snapshot) -> Result<()> {
        if let Some((expected, _, _)) = self.renamed.get(&target.aliases[0].logical) {
            ensure(
                expected == current,
                "unlabeled owned rename no longer has its actual recorded inode",
            )?;
            compatible_owned(&target.before, current)
        } else {
            ensure(
                *current == target.before,
                "unapplied label target changed without a durable intent",
            )
        }
    }
    fn verify_saved_row(
        &self,
        data: &OriginalDataTransaction,
        target: &Target,
        row: &RestoredRow,
    ) -> Result<()> {
        ensure(
            row.ordinal == target.ordinal && row.prelabel == target.before,
            "complete restoration row has another original source target",
        )?;
        let (held, current) =
            actual_named(&self.scope, target, self.retirement.authority().work())?;
        ensure(
            current == row.restored
                && current.attributes.get(LABEL) == target.before.attributes.get(LABEL),
            "complete restoration row is no longer the actual old-label inode",
        )?;
        let path = record_directory(&self.plan.work_directory, target.ordinal);
        let Some(original_pin) = &row.original_preimage else {
            ensure(
                row.restoration.is_none()
                    && row.recognized_history.is_none()
                    && row.current_before == row.restored,
                "unapplied target invented a restoration",
            )?;
            if std::fs::symlink_metadata(&path).is_ok() {
                Records::open(&path)?.verify_unpublished_preimage()?;
            }
            return self.untouched(target, &current);
        };
        let original = load_original(&path, held, target, &self.seal, &self.plan.candidate_id)?;
        ensure(
            pin_equal(original_pin, &original.pin),
            "saved target uses another original preimage",
        )?;
        let Some(restored_pin) = &row.restoration else {
            ensure(
                !original.records.exists("APPLIED.json")?
                    && row.current_before == row.restored
                    && row.recognized_history.is_none(),
                "unapplied target has conflicting actual label evidence",
            )?;
            return self.untouched(target, &current);
        };
        let parent = restored_pin
            .path
            .parent()
            .ok_or("restoration evidence parent missing")?;
        let name = parent
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or("restoration epoch missing")?;
        ensure(
            parent.parent() == Some(path.as_path())
                && name
                    .strip_prefix("retirement-")
                    .is_some_and(fs::valid_digest)
                && restored_pin
                    .path
                    .file_name()
                    .and_then(|n| n.to_str())
                    .is_some_and(|n| matches!(n, "RESTORED.json" | "RESTORED-OBSERVATION.json")),
            "complete restoration evidence left its exact source inode epoch",
        )?;
        let result: Value =
            serde_json::from_slice(&data::root_pin(restored_pin, 32 * 1024 * 1024)?)?;
        ensure(
            result["schema"] == "droidloom.current-label-restored.v1"
                && result["original_preimage"] == serde_json::to_value(original_pin)?
                && result["retirement"] == serde_json::to_value(self.retirement.report_pin())?,
            "complete restoration was not produced by this actual retirement",
        )?;
        let current_pin: FilePin = serde_json::from_value(result["current_preimage"].clone())?;
        let current_dir = current_pin
            .path
            .parent()
            .ok_or("current restoration preimage parent missing")?;
        let current_name = current_dir
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or("current preimage epoch missing")?;
        ensure(
            current_dir.parent() == Some(path.as_path())
                && current_pin.path.file_name()
                    == Some(std::ffi::OsStr::new("CURRENT-PREIMAGE.json"))
                && current_name
                    .strip_prefix("retirement-")
                    .is_some_and(fs::valid_digest),
            "current restoration evidence left the actual source inode",
        )?;
        let evidence = RuntimeRestoreAttempt::open_evidence(
            load_original(
                &path,
                original.recovery.try_clone()?,
                target,
                &self.seal,
                &self.plan.candidate_id,
            )?,
            Records::open(current_dir)?,
            &current_pin,
        )?;
        if let Some(history) = &row.recognized_history {
            ensure(
                pin_equal(history, &current_pin)
                    && result["recognized_without_target_write"] == true
                    && row.current_before == row.restored,
                "recognized restoration changed its actual current snapshot",
            )?;
            self.admit_history(
                target,
                &evidence.historical_restored_snapshot()?,
                &row.current_before,
                evidence.has_completed_result()?,
            )?;
        } else {
            ensure(
                evidence.current_snapshot() == &row.current_before
                    && current_dir == parent
                    && name == format!("retirement-{}", self.retirement.report_pin().sha256),
                "restoration current preimage is not this actual source-bound write",
            )?;
        }
        let step = OriginalLabelRestoration {
            candidate_id: self.plan.candidate_id.clone(),
            logical_path: target.aliases[0].logical.clone(),
            plan: self.seal.clone(),
            original_preimage: original_pin.clone(),
            restored: restored_pin.clone(),
            core: LabelDerivation {
                file: original.recovery.try_clone()?,
                before: row.current_before.clone(),
                after: row.restored.clone(),
            },
        };
        step.revalidate()?;
        data.binding(self.retirement.authority())
    }
    pub(crate) fn restore(
        &mut self,
        data: &OriginalDataTransaction,
    ) -> Result<OriginalLabelsRestored> {
        // A successful xattr syscall can precede a failed publication or owner
        // ctime rebind. Reconcile only that held active write, without another
        // target mutation, before invoking the otherwise strict full fence.
        if let Some(attempt) = self.active.as_ref() {
            if attempt.classify()?.1 {
                let target = self
                    .plan
                    .targets
                    .get(attempt.ordinal() as usize)
                    .ok_or("active restoration ordinal missing")?;
                let (core, pin) = attempt.restore()?;
                let step = OriginalLabelRestoration {
                    candidate_id: self.plan.candidate_id.clone(),
                    logical_path: target.aliases[0].logical.clone(),
                    plan: self.seal.clone(),
                    original_preimage: attempt.original_pin().clone(),
                    restored: pin,
                    core,
                };
                self.scope.accept_root_restoration(&step)?;
                self.retirement.accept_label_restoration(&step)?;
            }
        }
        self.fence(data)?;
        self.seal.full_readback()?;
        let report_path = self.plan.work_directory.join(format!(
            "LABELS-RESTORED-{}.json",
            self.retirement.report_pin().sha256
        ));
        match std::fs::symlink_metadata(&report_path) {
            Ok(_) => {
                let report = crate::boot_files::pin_file(&report_path)?;
                let value: Value =
                    serde_json::from_slice(&data::root_pin(&report, 512 * 1024 * 1024)?)?;
                let rows: Vec<RestoredRow> = serde_json::from_value(value["targets"].clone())?;
                let actual = OriginalLabelsRestored {
                    candidate: self.plan.candidate_id.clone(),
                    normal_sources: self.plan.normal_sources.clone(),
                    pair_intent: self.plan.pair_intent.clone(),
                    plan: self.seal.clone(),
                    report,
                    targets: self.plan.targets.clone(),
                    rows,
                };
                actual.verify_complete(self.retirement, data)?;
                return Ok(actual);
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            Err(e) => return Err(e.into()),
        }
        let mut rows = Vec::with_capacity(self.plan.targets.len());
        for index in 0..self.plan.targets.len() {
            let target = self.plan.targets[index].clone();
            let (held, current) =
                actual_named(&self.scope, &target, self.retirement.authority().work())?;
            let path = record_directory(&self.plan.work_directory, target.ordinal);
            let exists = match std::fs::symlink_metadata(&path) {
                Ok(_) => true,
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => false,
                Err(e) => return Err(e.into()),
            };
            if !exists {
                self.fence(data)?;
                self.untouched(&target, &current)?;
                rows.push(RestoredRow {
                    ordinal: target.ordinal,
                    prelabel: target.before.clone(),
                    current_before: current.clone(),
                    restored: current,
                    original_preimage: None,
                    restoration: None,
                    recognized_history: None,
                    target_write: false,
                });
                continue;
            }
            let records = Records::open(&path)?;
            if !records.exists("PREIMAGE.json")? {
                self.fence(data)?;
                records.verify_unpublished_preimage()?;
                self.untouched(&target, &current)?;
                rows.push(RestoredRow {
                    ordinal: target.ordinal,
                    prelabel: target.before.clone(),
                    current_before: current.clone(),
                    restored: current,
                    original_preimage: None,
                    restoration: None,
                    recognized_history: None,
                    target_write: false,
                });
                continue;
            }
            let original =
                load_original(&path, held, &target, &self.seal, &self.plan.candidate_id)?;
            let original_pin = original.pin.clone();
            let mut ours = target.before.attributes.clone();
            ours.insert(LABEL.into(), target.desired.clone());
            // A prior fsynced current preimage plus this same-generation old
            // label is a recognizable completed/uncertain restoration. The
            // new real retirement may contain legitimate mutable growth.
            if current.attributes != ours
                && current.attributes.get(LABEL) == target.before.attributes.get(LABEL)
            {
                if let Some(history) = self.history(&path, &original.recovery, &target, &current)? {
                    self.fence(data)?;
                    let now = epoch(&records, self.retirement)?;
                    let durability = now.sync_target(&original.recovery, &current)?;
                    let value = json!({"schema":"droidloom.current-label-restored.v1","current_preimage":history,
                        "original_preimage":original_pin,"retirement":self.retirement.report_pin(),
                        "before":current,"after":current,"target_metadata_durability":durability,
                        "recognized_without_target_write":true});
                    let result = if now.exists("RESTORED-OBSERVATION.json")? {
                        let (_, _, body) = now.read("RESTORED-OBSERVATION.json")?;
                        ensure(
                            serde_json::from_slice::<Value>(&body)? == value,
                            "restored observation changed",
                        )?;
                        record_pin(&now, "RESTORED-OBSERVATION.json")?
                    } else {
                        now.publish("RESTORED-OBSERVATION.json", &value)?
                    };
                    let step = OriginalLabelRestoration {
                        candidate_id: self.plan.candidate_id.clone(),
                        logical_path: target.aliases[0].logical.clone(),
                        plan: self.seal.clone(),
                        original_preimage: original_pin.clone(),
                        restored: result.clone(),
                        core: LabelDerivation {
                            file: original.recovery.try_clone()?,
                            before: current.clone(),
                            after: current.clone(),
                        },
                    };
                    step.revalidate()?;
                    self.scope.accept_root_restoration(&step)?;
                    self.retirement.accept_label_restoration(&step)?;
                    rows.push(RestoredRow {
                        ordinal: target.ordinal,
                        prelabel: target.before.clone(),
                        current_before: current.clone(),
                        restored: current,
                        original_preimage: Some(original_pin),
                        restoration: Some(result),
                        recognized_history: Some(history),
                        target_write: false,
                    });
                    continue;
                }
            }
            if !original.records.exists("APPLIED.json")? {
                self.fence(data)?;
                if current == target.before {
                    rows.push(RestoredRow {
                        ordinal: target.ordinal,
                        prelabel: target.before.clone(),
                        current_before: current.clone(),
                        restored: current,
                        original_preimage: Some(original_pin),
                        restoration: None,
                        recognized_history: None,
                        target_write: false,
                    });
                    continue;
                }
                original.applied_readback()?;
            }
            let now = epoch(&records, self.retirement)?;
            let attempt = if now.exists("CURRENT-PREIMAGE.json")? {
                let pin = record_pin(&now, "CURRENT-PREIMAGE.json")?;
                RuntimeRestoreAttempt::reopen(original, now, &pin)?
            } else {
                self.fence(data)?;
                let evolution = self.evolution(&target, &current)?;
                if evolution.is_none() {
                    let (_, after) = RuntimeRestoreAttempt::applied(&original)?;
                    for alias in &target.aliases {
                        runtime::admit_current(
                            &after,
                            &current,
                            runtime::runtime_class(&alias.logical, &self.plan.candidate_id),
                        )?;
                    }
                }
                RuntimeRestoreAttempt::prepare_exact(
                    original,
                    now,
                    self.retirement.report_pin(),
                    evolution,
                )?
            };
            self.active = Some(attempt);
            let attempt = self
                .active
                .as_ref()
                .ok_or("restoration recovery descriptor was lost")?;
            let (_, done) = attempt.classify()?;
            if !done {
                self.fence(data)?;
            }
            let (core, pin) = attempt.restore()?;
            let row = RestoredRow {
                ordinal: target.ordinal,
                prelabel: target.before.clone(),
                current_before: core.before.clone(),
                restored: core.after.clone(),
                original_preimage: Some(original_pin.clone()),
                restoration: Some(pin.clone()),
                recognized_history: None,
                target_write: core.before.attributes.get(LABEL)
                    != target.before.attributes.get(LABEL),
            };
            let step = OriginalLabelRestoration {
                candidate_id: self.plan.candidate_id.clone(),
                logical_path: target.aliases[0].logical.clone(),
                plan: self.seal.clone(),
                original_preimage: original_pin,
                restored: pin,
                core,
            };
            step.revalidate()?;
            self.scope.accept_root_restoration(&step)?;
            self.retirement.accept_label_restoration(&step)?;
            let (_, actual) =
                actual_named(&self.scope, &target, self.retirement.authority().work())?;
            ensure(
                actual == row.restored,
                "restored named inode changed before completion",
            )?;
            self.fence(data)?;
            rows.push(row);
            self.active.take();
        }
        self.fence(data)?;
        self.seal.full_readback()?;
        let excluded = self
            .scope
            .verify_restored_exclusions(&self.plan.scope, data)?;
        let record = json!({"schema":"droidloom.original-labels-restored.v1","candidate_id":self.plan.candidate_id,
            "normal_sources":self.plan.normal_sources,"source_plan":self.seal.pin,"pair_intent":self.plan.pair_intent,
            "pair_restoration":self.pair.report(),"actual_retirement":self.retirement.report_pin(),
            "complete_target_count":rows.len(),"targets":rows,"retained_exclusions":excluded,"original_pair_labels_written":false,
            "normal_shutdown_claimed":self.retirement.report()["scope"]=="verified-normal-return",
            "production_ready":false});
        let report = match std::fs::symlink_metadata(&report_path) {
            Ok(_) => {
                let pin = crate::boot_files::pin_file(&report_path)?;
                ensure(
                    serde_json::from_slice::<Value>(&data::root_pin(&pin, 512 * 1024 * 1024)?)?
                        == record,
                    "complete label restoration report changed",
                )?;
                pin
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                plan::save(&report_path, &record)?
            }
            Err(e) => return Err(e.into()),
        };
        let value = OriginalLabelsRestored {
            candidate: self.plan.candidate_id.clone(),
            normal_sources: self.plan.normal_sources.clone(),
            pair_intent: self.plan.pair_intent.clone(),
            plan: self.seal.clone(),
            report,
            targets: self.plan.targets.clone(),
            rows,
        };
        value.verify_complete(self.retirement, data)?;
        Ok(value)
    }
}

impl OriginalLabelsRestored {
    pub(crate) fn report(&self) -> &FilePin {
        &self.report
    }
    pub(crate) fn source_plan(&self) -> &FilePin {
        &self.plan.pin
    }
    pub(crate) fn verify_complete(
        &self,
        retirement: &OriginalRetirement,
        data: &OriginalDataTransaction,
    ) -> Result<()> {
        retirement.revalidate()?;
        data.binding(retirement.authority())?;
        self.plan.full_readback()?;
        ensure(
            self.candidate == retirement.candidate_id()
                && pin_equal(&self.normal_sources, retirement.source_pin())
                && pin_equal(&self.pair_intent, data.intent())
                && self.rows.len() == self.targets.len()
                && data.transaction.observe(true)?
                    == (data::Layout::Ready, data::SelectionState::Original),
            "complete restoration no longer belongs to this actual original retirement",
        )?;
        let report: Value =
            serde_json::from_slice(&data::root_pin(&self.report, 512 * 1024 * 1024)?)?;
        ensure(
            report["schema"] == "droidloom.original-labels-restored.v1"
                && report["source_plan"] == serde_json::to_value(&self.plan.pin)?
                && report["actual_retirement"] == serde_json::to_value(retirement.report_pin())?
                && report["candidate_id"] == self.candidate
                && report["normal_sources"] == serde_json::to_value(&self.normal_sources)?
                && report["pair_intent"] == serde_json::to_value(&self.pair_intent)?
                && report["complete_target_count"] == self.targets.len()
                && report["targets"] == serde_json::to_value(&self.rows)?,
            "complete restoration proof differs",
        )?;
        let context =
            OriginalLabelRestorationTransaction::resume(retirement, data, &self.plan.pin)?;
        ensure(
            context.plan.targets.len() == self.targets.len(),
            "complete restoration target count differs",
        )?;
        for (target, row) in self.targets.iter().zip(&self.rows) {
            ensure(
                row.ordinal == target.ordinal
                    && row.prelabel == target.before
                    && row.restored.handle == target.before.handle
                    && row.restored.attributes.get(LABEL) == target.before.attributes.get(LABEL),
                "complete restoration skipped or replaced a source inode",
            )?;
            context.verify_saved_row(data, target, row)?;
        }
        let plan: TransactionPlan =
            serde_json::from_slice(&data::root_pin(&self.plan.pin, 512 * 1024 * 1024)?)?;
        validate_target_layout(&plan)?;
        context
            .scope
            .verify_restored_exclusions(&plan.scope, data)?;
        self.plan.full_readback()?;
        retirement.revalidate()
    }
    pub(crate) fn preserved_metadata_derivations(
        &self,
        retirement: &OriginalRetirement,
        data: &OriginalDataTransaction,
    ) -> Result<Value> {
        self.verify_complete(retirement, data)?;
        let fixed = [
            "/etc/passwd",
            "/etc/group",
            "/etc/shadow",
            "/etc/gshadow",
            "/etc/ssh",
            "/etc/ssh/sshd_config",
            "/home/alex",
        ];
        let mut rows = BTreeMap::new();
        for (target, row) in self.targets.iter().zip(&self.rows) {
            for alias in &target.aliases {
                let path = alias
                    .logical
                    .to_str()
                    .ok_or("canonical preservation path missing")?;
                if fixed.contains(&path) || alias.logical.parent() == Some(Path::new("/etc/ssh")) {
                    ensure(rows.insert(path.to_owned(),json!({"prelabel":row.prelabel,"current":row.current_before,
                        "restored":row.restored,"original_preimage":row.original_preimage,
                        "actual_restoration":row.restoration,"recognized_history":row.recognized_history})).is_none(),
                        "ambiguous preserved account/SSH/home derivation")?;
                }
            }
        }
        for path in fixed {
            ensure(
                rows.contains_key(path),
                "fixed preserved account/SSH/home path is missing",
            )?;
        }
        Ok(
            json!({"schema":"droidloom.original-preserved-label-metadata.v1","candidate_id":self.candidate,
            "normal_sources":self.normal_sources,"source_plan":self.plan.pin,"label_restoration":self.report,
            "actual_retirement":retirement.report_pin(),"paths":rows}),
        )
    }
}
