//! Actual same-ELF working parent and its one fixed preparation child.
//! Preparation emits source inputs only. Complete remains owned by the
//! physical application's existing factories and private completion channel.
use super::*;
use serde_json::Value;
use droidloom_supervisor::control::physical_qualification_channel::{
    WorkingPreparationChannel, WorkingPreparationDocument,
};
use droidloom_update::working_preparation_materials::{WorkingPreparationMaterials, WorkingApkMaterials};
#[path = "working_install.rs"]
mod working_install;

/// No caller-supplied path, package, epoch, budget or success report is accepted.
pub fn run_owned_working_qualification() -> Result<Value, String> {
    let mut owner = droidloom_supervisor::working_qualification::WorkingQualificationOwner::acquire()?;
    if let Err(reason) = publish_working_native_source(&mut owner) {
        let record = owner.record_failure(&reason);
        return Err(format!("{reason}; initial source publication failure record={record:?}"));
    }
    let captured = droidloom_supervisor::control::physical_qualification_channel::
        capture_prepared_working_run(owner)?;
    captured.guard()?;
    let receipt = captured.write_receipt()?;
    let value = serde_json::json!({
        "schema":"droidloom.working-qualification-parent-completed.v1",
        "receipt":receipt,"actual_capture":captured.observation(),
        "parent_unit_retirement_pending":true,"normal_return_required":true,
        "permanent_acceptance_granted":false,"production_ready":false
    });
    captured.guard()?;
    Ok(value)
}

fn document<T: Serialize>(value: &T) -> Result<Vec<u8>, String> {
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|e|e.to_string())?;
    bytes.push(b'\n');
    Ok(bytes)
}
fn pin(value: Value) -> Result<FilePin, String> {
    serde_json::from_value(value).map_err(|e|e.to_string())
}

/// Called only by the actual installed Apps preparation mode. Its acquisition
/// verifies FD3, the original parent, executable, unit, Boot and current Main.
pub fn prepare_owned_working_inputs() -> Result<(), String> {
    let mut channel = WorkingPreparationChannel::acquire()?;
    let materials = WorkingPreparationMaterials::capture().map_err(|e|e.to_string())?;
    let source_end = channel.deadline().min(std::time::Instant::now()
        + std::time::Duration::from_secs(droidloom_supervisor::native_working_install::SOURCE_CAPTURE_SECONDS));
    let originals = WorkingApkMaterials::capture(&materials, source_end).map_err(|e|e.to_string())?;
    let installations = working_install::WorkingOriginalInstallations::run(&mut channel, &originals)?;
    channel.write_document(WorkingPreparationDocument::Installation, &document(&installations.comparison()?)?)?;
    installations.guard(&mut channel, &originals)?;
    // Even a normally rejected last package receives the complete readonly
    // source/actual-PM report. No partial install report can authorize a PLAN.
    let bindings = runtime_prepare::prepare_working(&mut channel, &materials)?;
    channel.write_document(WorkingPreparationDocument::RuntimeBindings, &bindings.report_bytes()?)?;
    // The original all-41 preparation may be partial. Keep its entire report,
    // then fail before a PLAN if any actual source/PM binding is unresolved.
    installations.guard(&mut channel, &originals)?;
    installations.require_complete()?;
    let runtime = bindings.runtime_plan()?;
    bindings.guard(&mut channel)?;
    let runtime_pin = pin(channel.write_document(
        WorkingPreparationDocument::RuntimePlan, &document(&runtime)?)?)?;
    let mut cases = droidloom_update::prepare_working_native_cases(&mut channel)
        .map_err(|e|e.to_string())?;
    cases.guard(channel.deadline()).map_err(|e|e.to_string())?;
    let case_summary = cases.comparison();
    channel.write_document(WorkingPreparationDocument::CaseInputs, &document(&case_summary)?)?;
    let mut applications = Vec::new();
    for expected in physical_gate_roster::PACKAGES {
        let mut requested = Vec::new();
        for route in expected.cases {
            let prepared = cases.case(route.package(), &serde_json::to_value(route)
                .map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
            requested.push(prepared);
        }
        applications.push(serde_json::json!({"package":expected.package,"cases":requested}));
    }
    let whole = serde_json::json!({
        "schema":"droidloom.physical-application-plan.v1",
        "runtime_plan":runtime_pin,"applications":applications
    });
    let gates: GateRegistry = serde_json::from_slice(materials.bytes(
        droidloom_update::working_preparation_materials::PreparationMaterial::GateRegistry
    ).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
    physical_acceptance::validate_prepared_working_plan(&whole, &runtime, &gates)?;
    bindings.guard(&mut channel)?;
    cases.guard(channel.deadline()).map_err(|e|e.to_string())?;
    materials.guard().map_err(|e|e.to_string())?;
    let plan = channel.retain_plan(&document(&whole)?)?;
    cases.guard(channel.deadline()).map_err(|e|e.to_string())?;
    bindings.guard(&mut channel)?;
    // The channel flushes the complete stdout document before its private
    // Ready frame and retains these input owners until the parent's ACK.
    installations.guard(&mut channel, &originals)?;
    channel.complete(plan)?;
    Ok(())
}
