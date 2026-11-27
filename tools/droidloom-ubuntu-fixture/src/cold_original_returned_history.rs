//! Normal first-once history observed under a new actual cold owner.
//! Historical source/ELF identity is retained separately from this verifier.
//! No OriginalQualificationAuthority or OriginalRetirement is reconstructed.
use super::{
    configurations::ArchivedRuntime,
    materials,
    owner::{OriginalOwner, WorkingColdOwner},
    returned_custody::{HeldDirectory, HeldFile, Records},
    state::{Journal, Phase},
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_data::labels::OriginalLabelRestoreSources,
    cold_original_once_recovery::contract as c,
    ensure, fs,
    model::Identity,
};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
};

const MAX_RECORD: u64 = 128 * 1024 * 1024;
const MAX_LABEL_RECORD: u64 = 512 * 1024 * 1024;
pub(super) fn pin(value: &Value) -> Result<FilePin> {
    Ok(serde_json::from_value(value.clone())?)
}
fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .ok_or_else(|| format!("normal returned history lacks {key}").into())
}
fn phase(journal: &Journal, phase: Phase) -> Result<Value> {
    journal
        .observation(phase)?
        .ok_or_else(|| format!("returned history lacks phase {phase:?}").into())
}
fn inside(work: &Path, path: &Path) -> Result<()> {
    ensure(
        path.is_absolute()
            && path.starts_with(work)
            && path.components().all(|p| {
                !matches!(
                    p,
                    std::path::Component::ParentDir | std::path::Component::CurDir
                )
            }),
        "returned history reference escaped its fixed candidate work",
    )
}
fn read_in(
    records: &mut Records,
    work: &Path,
    value: &Value,
    limit: u64,
) -> Result<(FilePin, Value)> {
    let p = pin(value)?;
    inside(work, &p.path)?;
    let body = records.read(&p, limit)?;
    Ok((p, body))
}

/// This opaque observation keeps the old normal sources, current original
/// owner and complete returned event chain held. It confers no write permit.
enum ReturnedObserver {
    Original(OriginalOwner),
    Working(WorkingColdOwner),
}
impl ReturnedObserver {
    fn revalidate_working_label_custody(&self) -> Result<()> {
        match self {
            Self::Working(owner) => owner.revalidate_label_custody(),
            Self::Original(_) => {
                Err("working label custody cannot use the original once owner".into())
            }
        }
    }
    fn revalidate(&self) -> Result<()> {
        match self {
            Self::Original(v) => v.revalidate(),
            Self::Working(v) => v.revalidate(),
        }
    }
    fn boot_id(&self) -> &str {
        match self {
            Self::Original(v) => v.boot_id(),
            Self::Working(v) => v.boot_id(),
        }
    }
    fn evidence(&self) -> Value {
        match self {
            Self::Original(v) => v.evidence(),
            Self::Working(v) => v.evidence(),
        }
    }
}

pub(crate) struct ReturnedOnceHistory {
    owner: ReturnedObserver,
    journal: Journal,
    directories: Vec<HeldDirectory>,
    records: Records,
    sources: OriginalLabelRestoreSources,
    runtime: ArchivedRuntime,
    verifier: HeldFile,
    candidate: String,
    work: PathBuf,
    intent_pin: FilePin,
    intent: Value,
    admitted: Value,
    pair_pin: FilePin,
    pair: Value,
    retirement_pin: FilePin,
    retirement: Value,
    label_plan_pin: FilePin,
    label_plan: Value,
    labels_pin: FilePin,
    labels: Value,
    pair_restoration: Value,
}
impl ReturnedOnceHistory {
    pub(super) fn open(candidate: &str) -> Result<Self> {
        ensure(
            fs::valid_digest(candidate),
            "exact normal candidate digest required",
        )?;
        let boot = std::fs::read_to_string("/proc/sys/kernel/random/boot_id")?;
        let owner = OriginalOwner::acquire(boot.trim(), candidate)?;
        Self::open_observed(candidate, ReturnedObserver::Original(owner))
    }

    pub(super) fn open_working(
        candidate: &str,
        working_candidate: &str,
        input: &FilePin,
    ) -> Result<Self> {
        ensure(
            fs::valid_digest(candidate) && candidate != working_candidate,
            "working history requires a distinct complete first-once candidate",
        )?;
        let owner = WorkingColdOwner::acquire(working_candidate, input)?;
        Self::open_observed(candidate, ReturnedObserver::Working(owner))
    }

    fn open_observed(candidate: &str, owner: ReturnedObserver) -> Result<Self> {
        owner.revalidate()?;
        let work = Path::new("/var/lib/droidloom-qualification")
            .join(format!("original-once-{candidate}"));
        let work_guard = HeldDirectory::open(&work, 4096)?;
        let journal_guard = HeldDirectory::open(&work.join("journal"), 384)?;
        let intent_pin = files::pin_file(&work.join("INTENT.json"))?;
        let mut records = Records::new();
        let intent = records.read(&intent_pin, MAX_RECORD)?;
        ensure(
            intent["schema"] == "droidloom.original-once-intent.v1"
                && intent["candidate_id"] == candidate
                && intent["work_directory"] == serde_json::to_value(&work)?
                && intent["root_uuid"] == c::ROOT_UUID
                && intent["original_kernel"] == c::ORIGINAL_KERNEL
                && intent["original_entry"] == c::ORIGINAL_ENTRY,
            "returned intent lost its original-machine source binding",
        )?;
        let journal =
            Journal::reopen_read_only(&work.join("journal"), candidate, &intent_pin.sha256)?;
        ensure(
            journal.phase() == Some(Phase::Returned),
            "first once has not reached its actual returned terminal phase",
        )?;
        for name in journal_guard.names_observed() {
            let p = files::pin_file(&work.join("journal").join(name))?;
            let (_, id) = files::open_pin(&p)?;
            records.include_file(&p, 1024 * 1024, id.mode & 0o7777)?;
        }
        let admission = phase(&journal, Phase::Admitted)?;
        ensure(
            admission["materials"] == intent["admitted_materials"],
            "intent and journal admission differ",
        )?;
        let (admitted_pin, admitted) = read_in(
            &mut records,
            &work,
            &intent["admitted_materials"],
            MAX_RECORD,
        )?;
        ensure(
            admitted_pin.path == work.join("ADMITTED-MATERIALS.json")
                && admitted["schema"] == "droidloom.original-once-admitted-materials.v1"
                && admitted["candidate_id"] == candidate
                && admitted["normal_sources"] == intent["normal_sources"],
            "returned admission lost its normal source identity",
        )?;
        let input_pin = pin(&admitted["input"])?;
        let input = records.read(&input_pin, MAX_RECORD)?;
        ensure(
            input["schema"] == "droidloom.original-once-plan.v1"
                && input["candidate_id"] == candidate
                && input["original_boot_id"] == intent["original_boot_id"]
                && input["normal_producer"] == intent["normal_producer"],
            "historical plan and producer differ",
        )?;
        let normal_source_pin = pin(&intent["normal_sources"])?;
        let sources = OriginalLabelRestoreSources::reopen(&normal_source_pin)?;
        ensure(
            sources.historical_initramfs_readback() == &admitted["normal_initramfs"],
            "actual preserved normal-source readback differs from first admission",
        )?;
        let producer = pin(&intent["normal_producer"])?;
        materials::compare_candidates(
            candidate,
            sources.historical_initramfs_readback(),
            &admitted["fresh_owned"],
            &producer,
        )?;
        let retained = admitted["retained_sources"]
            .as_array()
            .ok_or("normal historical retained sources absent")?;
        ensure(
            !retained.is_empty() && retained.len() <= 512,
            "normal historical source roster bound",
        )?;
        let mut retained_names = BTreeSet::new();
        let mut producer_seen = false;
        for row in retained {
            let p = pin(&row["source"])?;
            let identity: Identity = serde_json::from_value(row["identity"].clone())?;
            ensure(
                retained_names.insert(p.path.clone()),
                "duplicate historical source input",
            )?;
            records.include_source(&p, &identity)?;
            if super::same_pin(&p, &producer) {
                producer_seen = true;
            }
        }
        ensure(
            producer_seen,
            "historical normal producer is not one of its actual retained inputs",
        )?;
        // The current executable is observed separately. It is never compared
        // to the old producer as if the two releases were the same.
        let verifier_path = std::fs::read_link("/proc/self/exe")?;
        let verifier_pin = files::pin_file(&verifier_path)?;
        let verifier = HeldFile::open(&verifier_pin, verifier_pin.bytes, None, false)?;
        let running = std::fs::File::open("/proc/self/exe")?;
        ensure(
            verifier.identity().mode & 0o100 != 0
                && fs::stat(&running)? == *verifier.identity()
                && fs::hash(&running)? == verifier_pin.sha256,
            "current historical verifier lost its actual executable identity",
        )?;

        for p in [
            Phase::PublicInstalled,
            Phase::NativeInstalled,
            Phase::CellPublished,
            Phase::PairExchanged,
            Phase::RecoveryInstalled,
            Phase::GrubPublished,
            Phase::LabelsApplied,
            Phase::SelectionPublished,
            Phase::Armed,
            Phase::SelectionWithdrawn,
            Phase::PairRestored,
            Phase::LabelsRestored,
            Phase::CellRestored,
            Phase::NativeRestored,
            Phase::PublicRestored,
            Phase::GrubRestored,
        ] {
            phase(&journal, p)?;
        }
        let returned = phase(&journal, Phase::Returned)?;
        ensure(
            returned["schema"] == "droidloom.original-once-completed.v1"
                && returned["candidate_id"] == candidate
                && returned["intent"] == serde_json::to_value(&intent_pin)?
                && returned["production_ready"] == false
                && returned["application_business_accepted"] == false
                && returned["permanent_default_changed"] == false,
            "returned mechanism history is not a business or permanent acceptance",
        )?;
        let labels_phase = phase(&journal, Phase::LabelsRestored)?;
        let (retirement_pin, retirement) = read_in(
            &mut records,
            &work,
            &labels_phase["actual_retirement"],
            32 * 1024 * 1024,
        )?;
        validate_retirement(
            &retirement,
            candidate,
            &intent_pin,
            &normal_source_pin,
            &intent,
        )?;
        let candidate_boot = text(&retirement, "candidate_boot_id")?;
        ensure(
            owner.boot_id() != candidate_boot,
            "candidate runtime is not a cold successor owner",
        )?;
        let (observation_pin, observation) = read_in(
            &mut records,
            &work,
            &retirement["original_observation"],
            32 * 1024 * 1024,
        )?;
        ensure(
            observation_pin.path.parent() == retirement_pin.path.parent()
                && observation_pin.path.file_name()
                    == Some(std::ffi::OsStr::new("ORIGINAL-RETURN-OBSERVATION.json"))
                && observation["schema"] == "droidloom.original-once-original-readback.v1"
                && observation["intent"] == serde_json::to_value(&intent_pin)?,
            "normal original-return observation has another source",
        )?;
        let actual = &observation["actual"];
        ensure(
            actual["schema"] == "droidloom.actual-original-return-observation.v1"
                && actual["original_kernel"] == c::ORIGINAL_KERNEL
                && actual["original_boot_id"] == retirement["original_boot_id"]
                && actual["grub"]["original_entry"] == c::ORIGINAL_ENTRY
                && actual["grub"]["original_default"] == c::ORIGINAL_ENTRY
                && actual["grubenv_list_exit"] == 0
                && actual["grubenv_fields"]
                    .as_object()
                    .ok_or("actual returned GRUB fields absent")?
                    .get("next_entry")
                    .is_none_or(|v| v == ""),
            "historical actual original return or original default differs",
        )?;
        let old_grub = command(
            &mut records,
            &work,
            candidate,
            &intent_pin,
            &observation["normal_grub_command"],
            "grub-read",
        )?;
        let old_journal = command(
            &mut records,
            &work,
            candidate,
            &intent_pin,
            &observation["normal_journal_command"],
            "retirement-journal",
        )?;
        ensure(
            old_journal == actual["journal"]
                && old_grub["after_fields"] == actual["grubenv_fields"]
                && old_grub["original"] == actual["grub"]
                && old_grub["after"]["sha256"] == actual["grubenv"]["sha256"],
            "stored return summary differs from the actual normal command outputs",
        )?;
        let (labels_pin, labels) = read_in(
            &mut records,
            &work,
            &labels_phase["actual"],
            MAX_LABEL_RECORD,
        )?;
        let (label_plan_pin, label_plan) = read_in(
            &mut records,
            &work,
            &labels["source_plan"],
            MAX_LABEL_RECORD,
        )?;
        let target_count = label_plan["targets"]
            .as_array()
            .ok_or("normal source label targets absent")?
            .len();
        let restored_count = labels["targets"]
            .as_array()
            .ok_or("normal returned label rows absent")?
            .len();
        ensure(
            target_count > 0
                && target_count == restored_count
                && labels["complete_target_count"].as_u64() == Some(target_count as u64),
            "normal complete labels have an absent or inconsistent target count",
        )?;
        ensure(
            labels["schema"] == "droidloom.original-labels-restored.v1"
                && labels["candidate_id"] == candidate
                && labels["normal_sources"] == intent["normal_sources"]
                && labels["actual_retirement"] == serde_json::to_value(&retirement_pin)?
                && labels["original_pair_labels_written"] == false
                && label_plan["schema"] == "droidloom.original-label-transaction-plan.v1"
                && label_plan["candidate_id"] == candidate
                && label_plan["normal_sources"] == intent["normal_sources"]
                && label_plan["pair_intent"] == labels["pair_intent"]
                && label_plan["root_uuid"] == c::ROOT_UUID
                && labels["normal_shutdown_claimed"] == true
                && labels["production_ready"] == false,
            "returned labels lack their exact complete normal source plan",
        )?;
        let (pair_pin, pair) = read_in(&mut records, &work, &labels["pair_intent"], 128 * 1024)?;
        ensure(
            pair_pin.path == work.join("DATA-EXCHANGE-INTENT.json")
                && pair["candidate_id"] == candidate
                && pair["work"] == serde_json::to_value(&work)?
                && pair["original_boot_id"] == intent["original_boot_id"]
                && pair["cold_clone"] == intent["cold_clone"]
                && pair["selection"] == intent["selection"],
            "returned pair belongs to another actual normal candidate",
        )?;
        let (_, pair_restoration) = read_in(
            &mut records,
            &work,
            &labels["pair_restoration"],
            32 * 1024 * 1024,
        )?;
        let (_, pair_preimage) = read_in(
            &mut records,
            &work,
            &pair_restoration["intent"],
            32 * 1024 * 1024,
        )?;
        ensure(
            pair_restoration["schema"] == "droidloom.original-pair-restoration-result.v1"
                && pair_preimage["schema"] == "droidloom.original-pair-restoration-intent.v1"
                && pair_preimage["candidate_id"] == candidate
                && pair_preimage["pair_intent"] == serde_json::to_value(&pair_pin)?,
            "returned pair lacks its source-owned actual reverse rename",
        )?;
        let (_, initial_retirement) = read_in(
            &mut records,
            &work,
            &pair_preimage["retirement"],
            32 * 1024 * 1024,
        )?;
        validate_retirement(
            &initial_retirement,
            candidate,
            &intent_pin,
            &normal_source_pin,
            &intent,
        )?;
        let (configuration_pin, configuration) = read_in(
            &mut records,
            &work,
            &labels_phase["configuration_source"],
            MAX_RECORD,
        )?;
        let cell_restore = phase(&journal, Phase::CellRestored)?;
        ensure(
            configuration["schema"] == "droidloom.original-once-configuration-restore-source.v1"
                && configuration["candidate_id"] == candidate
                && configuration["intent"] == serde_json::to_value(&intent_pin)?
                && configuration["actual_label_restoration"] == serde_json::to_value(&labels_pin)?
                && cell_restore["actual_configurations"]
                    == serde_json::to_value(&configuration_pin)?,
            "returned configuration stage has another actual source",
        )?;
        let runtime = ArchivedRuntime::open(
            &work,
            candidate,
            &configuration_pin,
            &configuration,
            &retirement_pin,
            &retirement,
        )?;
        runtime.verify_normal_return(
            candidate,
            &intent_pin,
            text(&intent, "original_boot_id")?,
            candidate_boot,
            actual,
        )?;
        for (stage, operation) in [
            (Phase::NativeRestored, "native-rollback"),
            (Phase::PublicRestored, "public-rollback"),
        ] {
            let event = phase(&journal, stage)?;
            let _actual = command(
                &mut records,
                &work,
                candidate,
                &intent_pin,
                &event["normal_rollback"],
                operation,
            )?;
        }
        let grub = phase(&journal, Phase::GrubRestored)?;
        let final_grub = command(
            &mut records,
            &work,
            candidate,
            &intent_pin,
            &grub["actual_original_grub"],
            "grub-read",
        )?;
        ensure(
            final_grub["original"]["original_entry"] == c::ORIGINAL_ENTRY
                && final_grub["original"]["original_default"] == c::ORIGINAL_ENTRY
                && final_grub["after_fields"]
                    .as_object()
                    .ok_or("final original GRUB fields absent")?
                    .get("next_entry")
                    .is_none_or(|v| v == ""),
            "normal final restoration left a different boot selection",
        )?;
        let result = Self {
            owner,
            journal,
            directories: vec![work_guard, journal_guard],
            records,
            sources,
            runtime,
            verifier,
            candidate: candidate.into(),
            work,
            intent_pin,
            intent,
            admitted,
            pair_pin,
            pair,
            retirement_pin,
            retirement,
            label_plan_pin,
            label_plan,
            labels_pin,
            labels,
            pair_restoration,
        };
        result.guard()?;
        Ok(result)
    }

    pub(crate) fn guard_working_label_custody(&self) -> Result<()> {
        self.owner.revalidate_working_label_custody()?;
        self.journal.revalidate_custody()?;
        ensure(
            self.journal.phase() == Some(Phase::Returned),
            "returned history phase changed",
        )?;
        for d in &self.directories {
            d.guard()?;
        }
        self.records.guard()?;
        self.sources.revalidate_custody()?;
        self.runtime.guard()?;
        self.verifier.guard_custody()?;
        let running = std::fs::File::open("/proc/self/exe")?;
        ensure(
            fs::stat(&running)? == *self.verifier.identity(),
            "historical observer executable changed",
        )?;
        self.owner.revalidate_working_label_custody()
    }

    pub(crate) fn guard(&self) -> Result<()> {
        self.owner.revalidate()?;
        self.journal.revalidate()?;
        ensure(
            self.journal.phase() == Some(Phase::Returned),
            "returned history phase changed",
        )?;
        for d in &self.directories {
            d.guard()?;
        }
        self.records.guard()?;
        self.sources.revalidate_custody()?;
        self.runtime.guard()?;
        self.verifier.guard_custody()?;
        let running = std::fs::File::open("/proc/self/exe")?;
        ensure(
            fs::stat(&running)? == *self.verifier.identity(),
            "historical observer executable changed",
        )?;
        self.owner.revalidate()
    }
    pub(super) fn accept_working_owner_labels(
        &mut self,
        batch: &crate::cold_original_data::labels::WorkingLabelBatch,
    ) -> Result<()> {
        match &mut self.owner {
            ReturnedObserver::Working(owner) => owner.accept_working_label_batch(batch)?,
            ReturnedObserver::Original(_) => {
                return Err("working labels cannot rebind the historical original owner".into());
            }
        }
        // All retained history, normal archive sources, and the entry verifier
        // stay strict. This is not a reconstruction of the old live retirement.
        self.guard_working_label_custody()
    }

    /// These are comparisons from the still-held returned source, not a new
    /// mutable owner or a reconstruction of its historical live retirement.
    pub(crate) fn current_boot_id(&self) -> &str {
        self.owner.boot_id()
    }
    pub(super) fn current_owner_evidence(&self) -> Value {
        self.owner.evidence()
    }
    pub(crate) fn retained_cold_clone(&self) -> Result<FilePin> {
        self.guard()?;
        let retained = pin(&self.intent["cold_clone"])?;
        ensure(
            serde_json::to_value(&retained)? == self.admitted["retained_cold_clone"],
            "returned cold source differs from its original retained admission",
        )?;
        inside(&self.work, &retained.path)?;
        Ok(retained)
    }
    pub(crate) fn candidate(&self) -> &str {
        &self.candidate
    }
    pub(crate) fn work(&self) -> &Path {
        &self.work
    }
    pub(crate) fn pair_pin(&self) -> &FilePin {
        &self.pair_pin
    }
    pub(crate) fn pair(&self) -> &Value {
        &self.pair
    }
    pub(crate) fn label_plan_pin(&self) -> &FilePin {
        &self.label_plan_pin
    }
    pub(crate) fn label_plan(&self) -> &Value {
        &self.label_plan
    }
    pub(crate) fn labels_pin(&self) -> &FilePin {
        &self.labels_pin
    }
    pub(crate) fn labels(&self) -> &Value {
        &self.labels
    }
    pub(crate) fn retirement_pin(&self) -> &FilePin {
        &self.retirement_pin
    }
    pub(crate) fn retirement(&self) -> &Value {
        &self.retirement
    }
    pub(crate) fn pair_restoration(&self) -> &Value {
        &self.pair_restoration
    }
    pub(crate) fn read_retirement_record(&mut self, pin: &FilePin) -> Result<Value> {
        let value = self.read_work_record(pin, 32 * 1024 * 1024)?;
        let source = serde_json::from_value(self.intent["normal_sources"].clone())?;
        validate_retirement(
            &value,
            &self.candidate,
            &self.intent_pin,
            &source,
            &self.intent,
        )?;
        ensure(
            value["candidate_boot_id"] == self.retirement["candidate_boot_id"],
            "historical label restoration belongs to another candidate boot",
        )?;
        Ok(value)
    }
    pub(crate) fn read_work_record(&mut self, pin: &FilePin, limit: u64) -> Result<Value> {
        ensure(
            limit <= MAX_LABEL_RECORD,
            "returned-history source read bound",
        )?;
        inside(&self.work, &pin.path)?;
        self.records.read(pin, limit)
    }
    pub(super) fn summary(&self) -> Value {
        json!({"candidate_id":self.candidate,"first_once_intent":self.intent_pin,
            "historical_normal_producer":self.intent["normal_producer"],
            "historical_normal_source":self.intent["normal_sources"],
            "historical_host_source_commit":self.admitted["normal_initramfs"]["host_source_commit"],
            "historical_host_source_tree":self.admitted["normal_initramfs"]["host_source_tree"],
            "actual_current_verifier":self.verifier.pin(),"actual_current_verifier_identity":self.verifier.identity(),
            "actual_current_original_owner":self.owner.evidence(),"historical_normal_retirement":self.retirement_pin,
            "historical_complete_labels":self.labels_pin,"historical_pair_intent":self.pair_pin,
            "held_runtime_archive":self.runtime.payload_pins(),"held_history_sources":self.records.pins(),
            "historical_producer_reused_as_live_authority":false,"business_authority":false,"mutation_authority":false})
    }
}
fn validate_retirement(
    v: &Value,
    candidate: &str,
    intent: &FilePin,
    source: &FilePin,
    original: &Value,
) -> Result<()> {
    let boot = text(v, "candidate_boot_id")?;
    let returned = text(v, "original_boot_id")?;
    let admitted = text(original, "original_boot_id")?;
    ensure(
        v["schema"] == "droidloom.original-once-retirement.v1"
            && v["scope"] == "verified-normal-return"
            && v["candidate_id"] == candidate
            && v["intent"] == serde_json::to_value(intent)?
            && v["normal_sources"] == serde_json::to_value(source)?
            && v["original_kernel"] == c::ORIGINAL_KERNEL
            && v["root_uuid"] == c::ROOT_UUID
            && v["original_entry"] == c::ORIGINAL_ENTRY
            && v["admitted_original_boot_id"] == admitted
            && c::uuid(boot)
            && c::uuid(returned)
            && c::uuid(admitted)
            && boot != returned
            && boot != admitted
            && returned != admitted
            && v["working_data"]["schema"] == "droidloom.actual-working-data-retired.v1"
            && v["working_data"]["candidate_id"] == candidate,
        "history is not the exact normal return and actual retired working pair",
    )
}
fn command(
    records: &mut Records,
    work: &Path,
    candidate: &str,
    intent: &FilePin,
    p: &Value,
    operation: &str,
) -> Result<Value> {
    let p = pin(p)?;
    let directory = p
        .path
        .parent()
        .ok_or("normal historical command parent absent")?;
    ensure(
        directory.parent() == Some(work.join("commands").as_path())
            && p.path.file_name() == Some(std::ffi::OsStr::new("RESULT.json")),
        "historical command is not in the fixed normal command directory",
    )?;
    let evidence = records.read(&p, 128 * 1024 * 1024)?;
    let input = pin(&evidence["input"])?;
    ensure(
        input.path == directory.join("INPUTS.json"),
        "historical command input moved",
    )?;
    let request = records.read(&input, 128 * 1024 * 1024)?;
    let output = &evidence["actual"];
    ensure(
        evidence["schema"] == "droidloom.original-once-command-evidence.v1"
            && request["schema"] == "droidloom.original-once-fixed-command.v1"
            && request["candidate_id"] == candidate
            && request["intent"] == serde_json::to_value(intent)?
            && request["operation"] == operation
            && output["schema"] == "droidloom.original-once-fixed-command-result.v1"
            && output["candidate_id"] == candidate
            && output["intent"] == serde_json::to_value(intent)?
            && output["operation"] == operation
            && evidence["command"]["exit_code"] == 0
            && evidence["command"]["timed_out"] == false,
        "foreign, failed or uncompleted historical normal command",
    )?;
    let log = pin(&evidence["command"]["log"])?;
    ensure(
        log.path == directory.join("normal-command.log"),
        "normal historical output path differs",
    )?;
    let actual_log = records.read_mode(&log, 64 * 1024 * 1024, 0o600)?;
    ensure(
        actual_log == *output,
        "normal historical summary differs from actual output bytes",
    )?;
    let program = evidence["command"]["program"]
        .as_str()
        .ok_or("normal held Python program absent")?;
    let fields = program.split('/').collect::<Vec<_>>();
    ensure(
        fields.len() == 5
            && fields[0].is_empty()
            && fields[1] == "proc"
            && fields[3] == "fd"
            && fields[2]
                .parse::<u32>()
                .ok()
                .is_some_and(|p| p > 1 && fields[2] == p.to_string())
            && fields[4]
                .parse::<u32>()
                .ok()
                .is_some_and(|fd| fd >= 3 && fields[4] == fd.to_string()),
        "historical command did not use its normal held Python descriptor",
    )?;
    let args = evidence["command"]["args"]
        .as_array()
        .ok_or("normal command argv absent")?;
    ensure(
        args.len() == 6
            && args[0] == "-I"
            && args[1] == "-B"
            && args[2] == "-c"
            && args[3] == super::commands::historical_driver_source()
            && args[4] == serde_json::to_value(work.join("cold-source"))?
            && args[5] == serde_json::to_value(&input.path)?,
        "historical normal command did not use the exact reviewed driver and fixed inputs",
    )?;
    Ok(output["result"].clone())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn returned_successor_retirement_requires_normal_scope_and_distinct_boots() {
        // These are only parser inputs. No source/owner/data factory is
        // constructed by this test or by this comparison function.
        let candidate = "a".repeat(64);
        let intent = FilePin {
            path: "/fixed/INTENT.json".into(),
            bytes: 1,
            sha256: "b".repeat(64),
        };
        let source = FilePin {
            path: "/fixed/SOURCE.json".into(),
            bytes: 1,
            sha256: "c".repeat(64),
        };
        let original = json!({"original_boot_id":"11111111-1111-4111-8111-111111111111"});
        let value = json!({
            "schema":"droidloom.original-once-retirement.v1","scope":"verified-normal-return",
            "candidate_id":candidate,"intent":intent,"normal_sources":source,
            "original_kernel":c::ORIGINAL_KERNEL,"root_uuid":c::ROOT_UUID,"original_entry":c::ORIGINAL_ENTRY,
            "admitted_original_boot_id":original["original_boot_id"],
            "candidate_boot_id":"22222222-2222-4222-8222-222222222222",
            "original_boot_id":"33333333-3333-4333-8333-333333333333",
            "working_data":{"schema":"droidloom.actual-working-data-retired.v1","candidate_id":candidate}
        });
        validate_retirement(&value, &candidate, &intent, &source, &original).unwrap();
        let mut failed = value.clone();
        failed["scope"] = json!("failed-normal-return");
        assert!(validate_retirement(&failed, &candidate, &intent, &source, &original).is_err());
        let mut same_boot = value.clone();
        same_boot["candidate_boot_id"] = same_boot["original_boot_id"].clone();
        assert!(validate_retirement(&same_boot, &candidate, &intent, &source, &original).is_err());
        let mut foreign = value;
        foreign["normal_sources"]["sha256"] = json!("d".repeat(64));
        assert!(validate_retirement(&foreign, &candidate, &intent, &source, &original).is_err());
    }
}
