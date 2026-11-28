//! The real returned working entrypoint. Every process acquires a new owner;
//! preserved records never revive the old Rc, four backing OFDs or freezer.
use super::{
    WorkingBootRetirement, WorkingRecoverySources, WorkingReturnExpectation,
    WorkingReturnGrubDisarmed, WorkingReturnOwner, WorkingReturnQuiescence,
    configurations::working_return::WorkingReturnedFiles, owner::SealedInput,
    working_return_packages::WorkingReturnedPackages,
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_data::{
        WorkingReturnData,
        labels::{WorkingReturnedLabelHistory, WorkingReturnedLabelTransaction},
    },
    ensure, fs,
};
use serde_json::{Value, json};
use std::{fs::File, path::Path, rc::Rc};

pub(super) fn recover(input: &Path, expected: &str) -> Result<Value> {
    ensure(
        fs::valid_digest(expected),
        "complete returned normal input digest required",
    )?;
    let pin = files::pin_file(input)?;
    ensure(pin.sha256 == expected, "returned normal input bytes differ")?;
    let source = SealedInput::open(&pin)?;
    let body: Value = serde_json::from_slice(&source.read()?)?;
    let candidate = body["candidate_id"]
        .as_str()
        .ok_or("returned candidate missing")?;
    ensure(
        body["schema"] == "droidloom.working-qualification-material-plan.v1"
            && fs::valid_digest(candidate),
        "returned caller lacks one exact normal working source",
    )?;
    let owner = Rc::new(WorkingReturnOwner::acquire(candidate, &pin)?);
    source.revalidate()?;
    recover_owner(owner)
}

/// Same-boot callers may enter only with WorkingReturnOwner::from_live's real
/// duplicated global locks. They must drop all previous backing owners first.
pub(super) fn recover_owner(owner: Rc<WorkingReturnOwner>) -> Result<Value> {
    let sources = Rc::new(WorkingRecoverySources::open(owner)?);
    // Settle the current one-shot selection before capturing boot retirement;
    // its held grubenv must never be refreshed from an old snapshot afterwards.
    let grub = WorkingReturnGrubDisarmed::disarm(sources.clone())?;
    grub.require_sources(&sources)?;
    let expectation = WorkingReturnExpectation {
        boot_intent: sources.boot_intent().clone(),
        normal_sources: sources.normal_sources().source_pin().clone(),
        return_config: sources.return_configuration_pin().clone(),
        original_boot_id: sources.original_boot_id().into(),
    };
    let retirement = Rc::new(WorkingBootRetirement::observe(
        sources.owner().clone(),
        &expectation,
    )?);
    grub.require_sources(&sources)?;
    let grub_report = grub.report_pin().clone();
    drop(grub);
    let mut data = WorkingReturnData::capture(sources.clone(), retirement.clone())?;
    // Masks and stop requests precede freezing: frozen package writers must
    // never be asked to process a normal SIGTERM while unable to run.
    let mut packages = WorkingReturnedPackages::prepare(&data)?;
    let mut window = WorkingReturnQuiescence::acquire(sources.clone(), retirement.clone())?;
    if WorkingReturnedLabelHistory::exists(&sources)? {
        let history = WorkingReturnedLabelHistory::reopen(&data, &window)?;
        data.resume_restoration(history, &window)?;
    } else {
        let mut transaction = WorkingReturnedLabelTransaction::reopen(&data, &window)?;
        transaction.restore(&mut data, &window)?;
        let completed = transaction.seal(&data, &window)?;
        data.begin_restoration(completed, &window)?;
    }
    packages.bind_labels(&data)?;
    let mut boot = WorkingReturnedFiles::boot(&data, &window)?;
    let boot_report = boot.restore(&data, &window)?;
    drop(boot);
    let pair_report = data.restore_original_pair(&window)?;
    let mut runtime = WorkingReturnedFiles::runtime(&data, &window)?;
    let runtime_report = runtime.restore(&data, &window)?;
    drop(runtime);
    let freezer = window.intent_pin().clone();
    window.finish()?;
    drop(window);
    // The completed label history now supplies only comparisons. Normal
    // package writers use their independently bound original snapshots and
    // actual cold owner; the 600-second label deadline is never renewed.
    data.verify_original_restored()?;
    packages.restore_packages(&data)?;
    let recovery_service_report =
        super::configurations::working_recovery_service::restore_returned(&data)?;
    let package_report = packages.finish(&data)?;
    data.verify_original_restored()?;
    retirement.revalidate()?;
    sources.revalidate()?;
    let evidence = sources.configuration().runtime_evidence_directory();
    let retained = vec![
        evidence
            .parent()
            .ok_or("returned evidence parent")?
            .to_owned(),
        evidence,
    ];
    let value = json!({"schema":"droidloom.working-original-return-completed.v1",
        "candidate_id":sources.candidate(),"input":sources.owner().input_pin(),"boot_intent":sources.boot_intent(),
        "actual_original_owner":sources.owner().evidence(),"current_grub_disarm":grub_report,
        "actual_boot_retirement":retirement.report_pin(),"actual_data_retirement":data.report(),
        "completed_label_history":data.returned_label_history()?.handoff(),"label_window":freezer,
        "boot_files_restored":boot_report,"original_pair_restored":pair_report,
        "runtime_files_restored":runtime_report,"normal_packages_restored":package_report,
        "automatic_recovery_service_restored":recovery_service_report,
        "retained_evidence_paths":retained,"evidence_deleted":false,
        "actual_four_original_working_image_ofds_retained":true,"original_images_written":false,
        "original_return_observed":retirement.normal_return_observed(),
        "candidate_boot_id":retirement.candidate_boot_id(),"permanent_default_changed":false,
        "application_business_accepted":false,"production_ready":false});
    let path = data
        .report()
        .path
        .parent()
        .ok_or("returned completion directory")?
        .join("RETURNED.json");
    let record = save(&path, &value)?;
    data.verify_original_restored()?;
    sources.revalidate()?;
    let terminal = save(
        &sources.work().join("WORKING-RETURN-COMPLETED.json"),
        &json!({
        "schema":"droidloom.working-return-terminal.v1","candidate_id":sources.candidate(),
        "boot_intent":sources.boot_intent(),"actual_completion":record,
        "actual_original_owner":sources.owner().evidence(),"production_ready":false}),
    )?;
    data.verify_original_restored()?;
    Ok(json!({"actual":value,"record":record,"terminal":terminal}))
}
fn save(path: &Path, value: &Value) -> Result<FilePin> {
    let bytes = serde_json::to_vec(value)?;
    files::write_new(path, &bytes, 0o400)?;
    File::open(path.parent().ok_or("returned completion parent")?)?.sync_all()?;
    let pin = files::pin_file(path)?;
    SealedInput::open(&pin)?.revalidate()?;
    Ok(pin)
}
