//! A completed label history supplies comparisons to a newly acquired owner.
//! It never reconstructs a label writer, old lease, freezer or writable inode.
//! Once this handoff is durable, configuration and pair inverse may change
//! names. A later process therefore reopens their exact current roles instead
//! of replaying a full-root label operation through stale public paths.
use super::*;

const NAME: &str = "WORKING-LABELS-RESTORED.json";

pub(crate) struct WorkingReturnedLabelHistory {
    sources: Rc<WorkingRecoverySources>,
    handoff: Arc<PlanSeal>,
    report: Arc<PlanSeal>,
    plan: Arc<PlanSeal>,
    targets: BTreeMap<PathBuf, (Snapshot, Snapshot, bool)>,
}

fn source_rows(
    plan: &Plan,
    value: &Value,
) -> Result<BTreeMap<PathBuf, (Snapshot, Snapshot, bool)>> {
    ensure(
        value["schema"] == "droidloom.working-labels-returned.v1"
            && value["candidate_id"] == plan.candidate_id
            && value["normal_sources"] == serde_json::to_value(&plan.normal_sources)?
            && value["complete_target_count"] == plan.targets.len()
            && value["original_backing_labels_written"] == false
            && value["production_ready"] == false,
        "completed label comparison is not the complete normal source plan",
    )?;
    let rows: Vec<Row> = serde_json::from_value(value["targets"].clone())?;
    ensure(
        rows.len() == plan.targets.len(),
        "completed label comparison omitted an actual target",
    )?;
    let mut result = BTreeMap::new();
    for (target, row) in plan.targets.iter().zip(rows) {
        let mut original_attributes = target.before.attributes.clone();
        let mut returned_attributes = row.after.attributes.clone();
        if target
            .paths
            .iter()
            .all(|p| p == Path::new("/var/lib/systemd/random-seed"))
        {
            let key = "user.random-seed-creditable";
            for attrs in [&original_attributes, &returned_attributes] {
                ensure(
                    attrs.get(key).is_none_or(|v| v == b"1"),
                    "returned random-seed creditable value is outside its source contract",
                )?;
            }
            original_attributes.remove(key);
            returned_attributes.remove(key);
        }
        ensure(
            row.ordinal == target.ordinal
                && row.before.handle == target.before.handle
                && row.after.handle == target.before.handle
                && row.after.identity.dev == target.before.identity.dev
                && row.after.identity.ino == target.before.identity.ino
                && row.after.attributes.get(LABEL) == target.before.attributes.get(LABEL)
                && original_attributes == returned_attributes,
            "completed label comparison changed an ordinal, generation or original attributes",
        )?;
        for path in &target.paths {
            ensure(
                result
                    .insert(
                        path.clone(),
                        (target.before.clone(), row.after.clone(), target.separate),
                    )
                    .is_none(),
                "completed label comparison repeated a logical name",
            )?;
        }
    }
    Ok(result)
}

impl WorkingReturnedLabelHistory {
    pub(crate) fn exists(sources: &WorkingRecoverySources) -> Result<bool> {
        sources.revalidate_custody()?;
        exists(&sources.work().join(NAME))
    }

    pub(crate) fn seal(
        labels: &WorkingReturnedLabels,
        data: &WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<Self> {
        labels.require_data(data, window)?;
        let sources = data.sources();
        let value = json!({"schema":"droidloom.working-returned-label-comparison-source.v1",
            "candidate_id":sources.candidate(),"source_input":sources.owner().input_pin(),
            "boot_intent":sources.boot_intent(),"normal_sources":sources.normal_sources().source_pin(),
            "source_plan":labels.transaction.seal.pin,"completed_labels":labels.report(),
            "actual_data_retirement":data.report(),"actual_boot_retirement":data.retirement().report_pin(),
            "label_mutation_authority":false,"restoration_complete":false,"production_ready":false});
        let records = Records::open(sources.work())?;
        if records.exists(NAME)? {
            let (_, _, bytes) = records.read(NAME)?;
            ensure(
                serde_json::from_slice::<Value>(&bytes)? == value,
                "completed label handoff was already sealed by another exact result",
            )?;
        } else {
            records.publish(NAME, &value)?;
        }
        labels.require_data(data, window)?;
        Self::reopen(data, window)
    }

    pub(crate) fn reopen(
        data: &WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<Self> {
        data.revalidate()?;
        let sources = data.sources().clone();
        window.require_sources(&sources)?;
        let handoff_pin = files::pin_file(&sources.work().join(NAME))?;
        let handoff = Arc::new(PlanSeal::open(&handoff_pin)?);
        let value: Value = serde_json::from_slice(&data::root_pin(&handoff_pin, 1024 * 1024)?)?;
        ensure(
            value["schema"] == "droidloom.working-returned-label-comparison-source.v1"
                && value["candidate_id"] == sources.candidate()
                && value["source_input"] == serde_json::to_value(sources.owner().input_pin())?
                && value["boot_intent"] == serde_json::to_value(sources.boot_intent())?
                && value["normal_sources"]
                    == serde_json::to_value(sources.normal_sources().source_pin())?
                && value["label_mutation_authority"] == false
                && value["production_ready"] == false,
            "returned comparison handoff is outside this new owner's exact source closure",
        )?;
        let plan_pin: FilePin = serde_json::from_value(value["source_plan"].clone())?;
        ensure(
            plan_pin.path == sources.work().join("working-labels/LABEL-PLAN.json"),
            "returned comparison plan has another fixed location",
        )?;
        let plan_seal = Arc::new(PlanSeal::open(&plan_pin)?);
        let plan: Plan = serde_json::from_slice(&data::root_pin(&plan_pin, 512 * 1024 * 1024)?)?;
        validate_plan(&plan, &sources)?;
        let data_pin: FilePin = serde_json::from_value(value["actual_data_retirement"].clone())?;
        let report_pin: FilePin = serde_json::from_value(value["completed_labels"].clone())?;
        ensure(
            report_pin.path
                == sources
                    .work()
                    .join("working-labels")
                    .join(format!("LABELS-RETURNED-{}.json", data_pin.sha256))
                && data_pin.path.file_name() == Some(std::ffi::OsStr::new("DATA-RETIRED.json"))
                && data_pin.path.parent().and_then(Path::parent) == Some(sources.work()),
            "returned comparison has another fixed completed result or data epoch",
        )?;
        let prior_data: Value =
            serde_json::from_slice(&data::root_pin(&data_pin, 32 * 1024 * 1024)?)?;
        ensure(
            prior_data["schema"] == "droidloom.working-returned-data-custody.v1"
                && prior_data["candidate_id"] == sources.candidate()
                && prior_data["source_input"] == serde_json::to_value(sources.owner().input_pin())?
                && prior_data["pair_intent"] == serde_json::to_value(sources.data_intent())?
                && prior_data["actual_four_readonly_backing_locks_owned"] == true
                && prior_data["working_backings_synchronized"] == true
                && prior_data["original_backings_written"] == false,
            "returned comparison lost its completed retired pair provenance",
        )?;
        let report = Arc::new(PlanSeal::open(&report_pin)?);
        let body: Value = serde_json::from_slice(&data::root_pin(&report_pin, 512 * 1024 * 1024)?)?;
        ensure(
            body["source_plan"] == serde_json::to_value(&plan_pin)?
                && body["actual_data_retirement"] == serde_json::to_value(&data_pin)?
                && body["actual_boot_retirement"] == value["actual_boot_retirement"],
            "returned comparison completed report cross-link changed",
        )?;
        let result = Self {
            sources,
            handoff,
            report,
            plan: plan_seal,
            targets: source_rows(&plan, &body)?,
        };
        result.require_data(data, window)?;
        Ok(result)
    }

    pub(crate) fn require_data(
        &self,
        data: &WorkingReturnData,
        window: &WorkingReturnQuiescence,
    ) -> Result<()> {
        ensure(
            Rc::ptr_eq(&self.sources, data.sources()),
            "returned comparison cannot transfer to another fresh owner",
        )?;
        window.require_sources(&self.sources)?;
        data.revalidate_custody()?;
        self.revalidate()?;
        // These are freshly held real inodes, not descriptors reconstructed from
        // the history. Only the fixed inverse directory/selection rename may
        // have advanced ctime since completion; original images remain outside.
        for (logical, file, actual) in data.held_working_label_targets()? {
            let (_, restored, separate) = self
                .targets
                .get(&logical)
                .ok_or("returned comparison omits a fixed working backing or selection")?;
            ensure(
                *separate
                    && snapshot(&file)? == actual
                    && actual.handle == restored.handle
                    && actual.attributes == restored.attributes
                    && only_ctime_changed(&restored.identity, &actual.identity),
                "fresh working inode no longer matches its completed label comparison",
            )?;
        }
        self.revalidate()
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.sources.revalidate_custody()?;
        self.handoff.revalidate()?;
        self.report.revalidate()?;
        self.plan.revalidate()
    }
    pub(crate) fn report(&self) -> &FilePin {
        &self.report.pin
    }
    pub(crate) fn handoff(&self) -> &FilePin {
        &self.handoff.pin
    }
    pub(crate) fn snapshot_value_at(&self, path: &Path) -> Result<Value> {
        self.revalidate()?;
        let (_, after, separate) = self
            .targets
            .get(path)
            .ok_or("returned configuration target outside completed label plan")?;
        ensure(
            !separate,
            "ordinary configuration cannot select a private backing",
        )?;
        Ok(serde_json::to_value(after)?)
    }
    pub(crate) fn preserved_metadata(&self, paths: &BTreeSet<PathBuf>) -> Result<Value> {
        self.revalidate()?;
        let mut values = BTreeMap::new();
        for path in paths {
            let (before, after, separate) = self
                .targets
                .get(path)
                .ok_or("normal preservation path outside complete label comparison")?;
            ensure(
                !separate,
                "normal package metadata cannot name private data",
            )?;
            values.insert(path.clone(), json!({"prelabel":before,"restored":after}));
        }
        Ok(json!({"paths":values}))
    }
}
